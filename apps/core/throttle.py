"""Attempt limits for the secrets that can be guessed (ENF-3): password, two-factor code, master access code.

Only failures count. Past the limit, further attempts are refused until the window ends, without even checking
the secret, so that guessing stays out of reach. Counters live in the database so that every application process
shares them; keys are hashed (no e-mail address or IP address is stored in clear).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import AttemptWindow

logger = logging.getLogger(__name__)

# scope -> (failures allowed, window in seconds)
LIMITS = {
    "login-account-ip": (10, 900),  # one account from one address
    "login-ip": (30, 900),          # one address, whatever the accounts tried
    "login-account": (50, 900),     # one account from anywhere: guessing spread over many addresses — kept high
                                    # so that a single address cannot lock a person out of the platform
    "mfa": (5, 900),                # one account's two-factor code (the password is already known at this step)
    "master-ip": (10, 900),         # master access codes typed from one address
}


def client_ip(request) -> str:
    """Address of the client as seen by the HTTPS front end (Caddy replaces any X-Forwarded-For it receives)."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")) or "unknown"


def _key(scope: str, identifier) -> str:
    return hashlib.sha256(f"{scope}:{str(identifier).strip().lower()}".encode()).hexdigest()


def blocked(scope: str, identifier) -> bool:
    limit, window = LIMITS[scope]
    row = AttemptWindow.objects.filter(key=_key(scope, identifier)).first()
    return bool(row and row.failures >= limit and row.started_at > timezone.now() - timedelta(seconds=window))


def failure(scope: str, identifier) -> None:
    limit, window = LIMITS[scope]
    key, now = _key(scope, identifier), timezone.now()
    for _attempt in range(2):
        try:
            with transaction.atomic():
                row, _created = AttemptWindow.objects.select_for_update().get_or_create(
                    key=key, defaults={"started_at": now, "failures": 0})
                if row.started_at <= now - timedelta(seconds=window):
                    row.started_at, row.failures = now, 0
                row.failures += 1
                row.save(update_fields=["started_at", "failures"])
            if row.failures == limit:
                logger.warning("attempt limit reached for scope %s", scope)
            return
        except IntegrityError:  # created concurrently: retry once on the existing row
            continue
