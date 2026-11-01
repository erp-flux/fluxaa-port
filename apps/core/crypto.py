"""Cryptographic helpers for the operational domain.

* ``seal`` produces an HMAC-SHA256 over canonical JSON — used for journal chaining, signatures
  and authorizations (CDC ENF-4.1 / ENF-4.3).
* ``encrypt_main`` / ``decrypt_main`` protect small secrets (TOTP seeds) with a Fernet key derived
  from FLUXAA_SIGNING_KEY. The N4 domain uses its own, distinct keys (apps/secure/crypto.py).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import date, datetime
from decimal import Decimal

from cryptography.fernet import Fernet
from django.conf import settings


def _default(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def canonical_json(data) -> str:
    """Deterministic JSON used for every hash and signature."""
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_default)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def seal(data) -> str:
    """HMAC-SHA256 of the canonical JSON of *data* with the platform signing key."""
    key = settings.FLUXAA_SIGNING_KEY.encode("utf-8")
    return hmac.new(key, canonical_json(data).encode("utf-8"), hashlib.sha256).hexdigest()


def verify_seal(data, signature: str) -> bool:
    return hmac.compare_digest(seal(data), signature or "")


def _main_fernet() -> Fernet:
    digest = hashlib.sha256(("fluxaa-main-domain:" + settings.FLUXAA_SIGNING_KEY).encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_main(plaintext: str) -> str:
    return _main_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_main(token: str) -> str:
    return _main_fernet().decrypt(token.encode("ascii")).decode("utf-8")
