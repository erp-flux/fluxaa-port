"""Account views: sign-in, two-factor authentication, profile, language, API token."""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from rest_framework.authtoken.models import Token

from apps.registry.services import journal

from . import mfa, throttle
from .models import Language


def healthz(request):
    from django.db import connections

    try:
        with connections["default"].cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


class LoginView(auth_views.LoginView):
    """Password step. Failed attempts are limited per account and per address (apps.core.throttle)."""

    template_name = "core/login.html"
    redirect_authenticated_user = True

    def _limits(self):
        username = self.request.POST.get("username", "").strip().lower()
        address = throttle.client_ip(self.request)
        return (("login-account-ip", f"{username}|{address}"), ("login-ip", address), ("login-account", username))

    def post(self, request, *args, **kwargs):
        if any(throttle.blocked(scope, identifier) for scope, identifier in self._limits()):
            context = self.get_context_data(form=self.get_form(), throttled=True)
            return self.render_to_response(context, status=429)
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        for scope, identifier in self._limits():
            throttle.failure(scope, identifier)
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        user = form.get_user()
        if user.port:
            journal.audit(port=user.port, user=user, action="login", request=self.request)
        return response


def admin_login(request):
    """The settings screens have no sign-in page of their own: the platform's applies (attempt limits, second
    factor), then the administrator comes back to the page asked for."""
    from urllib.parse import quote

    target = request.GET.get("next", "/admin/")
    if not url_has_allowed_host_and_scheme(target, {request.get_host()}):
        target = "/admin/"
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect(target)
        # signed in, without access to the settings: say so instead of looping between the two sign-in pages
        messages.error(request, _("Your account has no access to the settings of the port."))
        return redirect("/")
    return redirect(f"{reverse('core:login')}?next={quote(target)}")


@require_POST
def logout_view(request):
    from django.contrib.auth import logout

    logout(request)
    # "?sortie=1": the next page removes the call data cached for offline use on this device
    # (field pages and bundles), never the entries still waiting to be sent.
    response = redirect(f"{reverse('core:login')}?sortie=1")
    response["Clear-Site-Data"] = '"cache"'
    return response


def _safe_next(request, fallback="/"):
    target = request.POST.get("next") or request.GET.get("next") or fallback
    return target if url_has_allowed_host_and_scheme(target, {request.get_host()}) else fallback


@require_POST
def language(request):
    code = request.POST.get("language", "fr")
    if code not in Language.values:
        code = "fr"
    if request.user.is_authenticated:
        request.user.language = code
        request.user.save(update_fields=["language"])
    response = HttpResponseRedirect(_safe_next(request))
    response.set_cookie(settings.LANGUAGE_COOKIE_NAME, code, max_age=365 * 24 * 3600, samesite="Lax")
    return response


def _second_factor_changed(request, user, *, replaced: bool) -> None:
    """Trace the enrolment in the access journal and tell the person by e-mail: an enrolment they did not make is
    the sign of a stolen password."""
    if user.port:
        journal.audit(port=user.port, user=user, action="mfa.changed" if replaced else "mfa.enabled", request=request)
    if user.email:
        with translation.override(user.language or "fr"):
            subject = _("[FLUXAA Port] Two-factor authentication changed on your account")
            body = _("A new authenticator application has just been registered for your account (%(email)s). If you "
                     "did not do it, contact your port administrator at once: your password is known to someone else.") \
                % {"email": user.email}
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=True)


@login_required
def mfa_setup(request):
    """Enrol an authenticator application. Replacing an enrolled one requires a code from it: a password alone must
    never be enough to take over the second factor. A lost phone is handled by the port administrator, who resets
    the enrolment (user settings), an act recorded in the access journal."""
    user = request.user
    replacing = bool(user.mfa_enabled)
    secret = request.session.get("mfa_pending_secret")
    if not secret:
        secret = mfa.new_secret()
        request.session["mfa_pending_secret"] = secret
    status = 200
    if request.method == "POST":
        if mfa.attempts_exhausted(user):
            messages.error(request, _("Too many incorrect codes. Wait up to fifteen minutes before trying again."))
            status = 429
        elif replacing and not mfa.verify_user(user, request.POST.get("current_code", "")):
            messages.error(request, _("The code of your current authenticator application is not valid."))
        elif mfa.verify(secret, request.POST.get("code", "")):
            user.set_mfa_secret(secret)
            user.mfa_enabled = True
            user.save(update_fields=["mfa_secret_encrypted", "mfa_enabled"])
            request.session.pop("mfa_pending_secret", None)
            mfa.mark_session(request)
            _second_factor_changed(request, user, replaced=replacing)
            messages.success(request, _("Two-factor authentication is active."))
            return redirect(_safe_next(request, "/"))
        else:
            throttle.failure("mfa", user.pk)
            messages.error(request, _("The code is not valid. Check the time of your phone and try again."))
    uri = mfa.provisioning_uri(user, secret)
    return render(request, "core/mfa_setup.html", {"qr": mfa.svg_data_uri(mfa.qr_svg(uri)), "secret": secret,
                                                   "replacing": replacing, "next": request.GET.get("next", "/")},
                  status=status)


@login_required
def mfa_verify(request):
    user = request.user
    if not user.mfa_enabled:
        return redirect(f"/compte/mfa/activer/?next={_safe_next(request)}")
    status = 200
    if request.method == "POST":
        if mfa.attempts_exhausted(user):
            messages.error(request, _("Too many incorrect codes. Wait up to fifteen minutes before trying again."))
            status = 429
        elif mfa.verify_user(user, request.POST.get("code", "")):
            mfa.mark_session(request)
            return redirect(_safe_next(request, "/"))
        else:
            messages.error(request, _("The code is not valid."))
    return render(request, "core/mfa_verify.html", {"next": request.GET.get("next", request.POST.get("next", "/"))},
                  status=status)


@login_required
def profile(request):
    user = request.user
    token = None
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "digest":
            user.notify_digest_only = request.POST.get("notify_digest_only") == "on"
            user.save(update_fields=["notify_digest_only"])
            messages.success(request, _("Notification preference saved."))
        elif action == "token":
            if user.requires_mfa_login and not mfa.session_is_strong(request):
                return redirect("/compte/mfa/verifier/?next=/compte/")
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user).key
            if user.port:
                journal.audit(port=user.port, user=user, action="api_token.created", request=request)
            messages.warning(request, _("Copy this token now: it will not be shown again."))
        elif action == "revoke":
            Token.objects.filter(user=user).delete()
            messages.success(request, _("API token revoked."))
    return render(request, "core/profile.html", {"token": token, "has_token": Token.objects.filter(user=user).exists()})
