"""Two-factor authentication (TOTP, RFC 6238) — mandatory for CAP, APO, SUR and for every decision
(CDC ENF-3.1). Works with any authenticator app; no SMS dependency."""
from __future__ import annotations

import base64
import io
import time

import pyotp
import qrcode
import qrcode.image.svg
from django.conf import settings

from . import throttle

SESSION_KEY = "fluxaa_mfa_verified_at"
SESSION_USER_KEY = "fluxaa_mfa_verified_user"
ISSUER = "FLUXAA Port"


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)


def qr_svg(uri: str) -> str:
    img = qrcode.make(uri, image_factory=qrcode.image.svg.SvgPathImage, box_size=8, border=2)
    buffer = io.BytesIO()
    img.save(buffer)
    return buffer.getvalue().decode("utf-8")


def verify(secret: str, code: str) -> bool:
    if not secret or not code:
        return False
    return pyotp.TOTP(secret).verify(code.replace(" ", "").strip(), valid_window=1)


def verify_user(user, code: str) -> bool:
    """Check a code against the person's enrolled authenticator. Failures are counted: past the limit
    (throttle.LIMITS["mfa"]) every code is refused until the window ends, the right one included."""
    if not user.mfa_enabled or not code or throttle.blocked("mfa", user.pk):
        return False
    if verify(user.get_mfa_secret(), code):
        return True
    throttle.failure("mfa", user.pk)
    return False


def attempts_exhausted(user) -> bool:
    return throttle.blocked("mfa", user.pk)


def stamp(user) -> dict:
    """Session values recording that this person has just passed the second factor."""
    return {SESSION_KEY: int(time.time()), SESSION_USER_KEY: user.pk}


def mark_session(request) -> None:
    """After a successful check: new session key (no fixation), stamp bound to the person signed in."""
    request.session.cycle_key()
    request.session.update(stamp(request.user))


def session_verified(request) -> bool:
    """The second factor was passed in this browser session, by the person signed in to it."""
    user = getattr(request, "user", None)
    session = getattr(request, "session", None)
    return bool(user is not None and user.is_authenticated and user.mfa_enabled and session is not None
                and session.get(SESSION_KEY) and session.get(SESSION_USER_KEY) == user.pk)


def session_is_strong(request) -> bool:
    """True when the session passed a TOTP check recently enough for a decision (step-up)."""
    return session_verified(request) and time.time() - request.session[SESSION_KEY] <= settings.FLUXAA_MFA_STEPUP_SECONDS


def request_is_strong(request) -> bool:
    """Web: the session step-up. API: the X-MFA-Code header, checked on each request; a browser session (field app)
    may use its step-up, but a bearer token never borrows one — whoever holds the cookie."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    code = request.META.get("HTTP_X_MFA_CODE", "")
    if code:
        return verify_user(user, code)
    authenticator = getattr(request, "successful_authenticator", None)
    if authenticator is not None and not getattr(authenticator, "uses_browser_session", False):
        return False
    return session_is_strong(request)


def svg_data_uri(svg: str) -> str:
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode("utf-8")).decode("ascii")
