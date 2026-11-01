"""API authentication: personal bearer tokens, and the master's account-less link (EF-13)."""
from __future__ import annotations

from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware
from django.utils.translation import gettext as _
from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, SessionAuthentication, TokenAuthentication

from apps.core import mfa
from apps.registry.services.access import master_from_session
from apps.registry.services.calls import authenticate_master


class BearerTokenAuthentication(TokenAuthentication):
    """`Authorization: Bearer <token>` — tokens are created from the user profile (after 2FA when required)."""

    keyword = "Bearer"


class SecondFactorRequired(exceptions.AuthenticationFailed):
    """Reported as `403 strong_auth_required` by apps.api.exceptions."""

    default_code = "strong_auth_required"


class MfaSessionAuthentication(SessionAuthentication):
    """Browser session (field app, CSRF enforced). For the roles that must sign in with a second factor
    (FLUXAA_MFA_REQUIRED_ROLES, ENF-3.1), the session only counts once that factor has been verified — exactly as for
    the web pages, so a password alone never opens the API, the N4 items included."""

    uses_browser_session = True  # its step-up may serve for decisions (apps.core.mfa.request_is_strong)

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user = result[0]
        if (settings.FLUXAA_MFA_ENFORCED and getattr(user, "requires_mfa_login", False)
                and not mfa.session_verified(request._request)):
            raise SecondFactorRequired(_("Enter your two-factor code in the application before using it from this "
                                         "browser."))
        return result


class MasterPrincipal:
    """Stands for the master in DRF: authenticated, but no account and no organisation."""

    is_authenticated = True
    is_active = True
    is_anonymous = False
    is_staff = False
    is_superuser = False
    pk = None
    id = None
    organization_id = None
    roles: list = []
    mfa_enabled = False

    def __init__(self, link):
        self.master = link

    def __str__(self) -> str:
        return f"{self.master.role} link {self.master.master_name}"


class _CSRFCheck(CsrfViewMiddleware):
    def _reject(self, request, reason):
        return reason


class MasterAuthentication(BaseAuthentication):
    """`Authorization: Master <token>` (the master's link or a party's link) or the session opened through
    /bord/<token> (with CSRF check)."""

    def authenticate(self, request):
        header = request.META.get("HTTP_AUTHORIZATION", "")
        if header.startswith("Master "):
            link = authenticate_master(token=header[7:].strip(), request=request._request)
            if link is None:
                raise exceptions.AuthenticationFailed("Invalid, expired or revoked access link.")
            if not link.master_name:
                raise exceptions.AuthenticationFailed("This access link carries no name yet: open it in a browser "
                                                      "and enter your name first (every act is nominative).")
            return MasterPrincipal(link), None
        django_user = getattr(request._request, "user", None)
        if django_user is not None and django_user.is_authenticated:
            return None  # a signed-in account always takes precedence over a master session
        link = master_from_session(request._request)
        if link is None or not link.master_name:
            return None
        check = _CSRFCheck(lambda req: None)
        check.process_request(request._request)
        reason = check.process_view(request._request, None, (), {})
        if reason:
            raise exceptions.PermissionDenied(f"CSRF Failed: {reason}")
        return MasterPrincipal(link), None

    def authenticate_header(self, request):
        return "Master"
