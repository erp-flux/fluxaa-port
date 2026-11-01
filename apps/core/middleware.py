"""Request context: language, port time zone, and enforcement of strong authentication."""
from __future__ import annotations

import zoneinfo

from django.conf import settings
from django.shortcuts import redirect
from django.utils import timezone, translation

from . import mfa

EXEMPT_PREFIXES = ("/static/", "/i18n/", "/healthz", "/compte/", "/bord/", "/verifier/", "/api/", "/favicon",
                   "/manifest.webmanifest", "/sw.js")


class PortContextMiddleware:
    """Activate the user's language (or the port's default) and the port time zone for display."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        port = None
        if user is not None and user.is_authenticated and user.organization_id:
            port = user.organization.port
            language = user.language or request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) or port.default_language
            translation.activate(language)
            request.LANGUAGE_CODE = language
        request.port = port
        if port is not None:
            try:
                timezone.activate(zoneinfo.ZoneInfo(port.timezone))
            except zoneinfo.ZoneInfoNotFoundError:
                timezone.deactivate()
        response = self.get_response(request)
        timezone.deactivate()
        return response


class ContentSecurityPolicyMiddleware:
    """Content Security Policy on every HTML page (ENF-3): scripts only from the platform's own files — no inline
    script, no third-party origin — and nothing can frame the pages. A response that already carries its own policy
    (an HTML document served from the registry) keeps it."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        policy = settings.FLUXAA_CONTENT_SECURITY_POLICY
        if (policy and "Content-Security-Policy" not in response
                and response.get("Content-Type", "").startswith("text/html")):
            response["Content-Security-Policy"] = policy
        return response


class MfaEnforcementMiddleware:
    """CAP, APO and SUR cannot use the web application without a verified second factor."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            settings.FLUXAA_MFA_ENFORCED
            and user is not None
            and user.is_authenticated
            and user.requires_mfa_login
            and not request.path.startswith(EXEMPT_PREFIXES)
            and not request.path.startswith("/admin/logout")
        ):
            if not user.mfa_enabled:
                return redirect("core:mfa_setup")
            if not mfa.session_verified(request):
                return redirect(f"/compte/mfa/verifier/?next={request.get_full_path()}")
        return self.get_response(request)
