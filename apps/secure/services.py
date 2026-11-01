"""N4 security domain services (CDC EF-12.4, MA1, acceptance scenario S5).

* Deposit (write-only channel): the agency — or the master — files an armed-guard / escort request.
  The depositor receives a receipt reference once; nothing is written to the operational database.
* Access reserved to SUR and CAP. Every access is logged nominatively in a hash chain, and accesses
  by a role other than SUR are notified to the port's security authority.
* Encrypted with the N4 keys only; never exported, never shown on a dashboard, never sent to AI.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import canonical_json, sha256_hex
from apps.core.roles import N4_ROLES
from apps.registry.services.errors import NotVisible, PermissionRefused, RuleViolation, StrongAuthRequired

from .models import SecureAccessLog, SecureAttachment, SecureChainHead, SecureItem, SecureSequence

log = logging.getLogger(__name__)
DEPOSIT_ROLES = {"AGE", "NAV", "SUR", "CAP"}
DB = "secure"


# ---------------------------------------------------------------------------- crypto
def _fernet():
    from cryptography.fernet import Fernet, MultiFernet

    keys = settings.FLUXAA_N4_KEYS
    if not keys:
        raise ImproperlyConfigured("FLUXAA_N4_KEYS must be set: the N4 domain is encrypted with its own keys.")
    return MultiFernet([Fernet(k.encode("ascii")) for k in keys])


def encrypt(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data, ensure_ascii=False).encode("utf-8")).decode("ascii")


def decrypt(token: str) -> dict:
    if not token:
        return {}
    return json.loads(_fernet().decrypt(token.encode("ascii")).decode("utf-8"))


# ---------------------------------------------------------------------------- access log
def _log(port_code: str, user, role: str, action: str, item=None, detail: str = "", request=None) -> SecureAccessLog:
    ip = None
    if request is not None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
    with transaction.atomic(using=DB):
        SecureChainHead.objects.using(DB).get_or_create(port_code=port_code)
        head = SecureChainHead.objects.using(DB).select_for_update().get(port_code=port_code)
        entry = SecureAccessLog(
            port_code=port_code, seq=head.last_seq + 1, item=item, at=timezone.now(), user_id=user.pk,
            user_label=f"{user.full_name} <{user.email}>"[:200], role=role, action=action, detail=detail[:300], ip=ip,
            prev_hash=head.last_hash,
        )
        material = {"seq": entry.seq, "port": port_code, "item": item.pk if item else None, "at": entry.at.isoformat(),
                    "user": entry.user_id, "label": entry.user_label, "role": role, "action": action,
                    "detail": entry.detail, "ip": ip, "prev": entry.prev_hash}
        entry.hash = sha256_hex(canonical_json(material))
        notify_authority = role != "SUR" and action != "CREATE"
        entry.notified = notify_authority
        entry.save(using=DB)
        head.last_seq = entry.seq
        head.last_hash = entry.hash
        head.save(using=DB, update_fields=["last_seq", "last_hash"])
    if notify_authority:
        _notify_authority(port_code, entry)
    return entry


def _notify_authority(port_code: str, entry: SecureAccessLog) -> None:
    from apps.core.models import Port

    port = Port.objects.filter(code=port_code).first()
    if port is None or not port.security_authority_email:
        return
    try:
        send_mail(
            "[FLUXAA Port] Accès N4 / N4 access",
            f"{entry.at:%Y-%m-%d %H:%M} UTC — {entry.user_label} ({entry.role}) — {entry.action}\n"
            "Détails dans l'espace sûreté. / Details in the security space.",
            settings.DEFAULT_FROM_EMAIL, [port.security_authority_email],
        )
    except Exception as exc:  # pragma: no cover
        log.warning("N4 authority notification failed: %s", exc)


def verify_chain(port_code: str) -> dict:
    previous = "0" * 64
    expected = 1
    count = 0
    for entry in SecureAccessLog.objects.using(DB).filter(port_code=port_code).order_by("seq"):
        count += 1
        material = {"seq": entry.seq, "port": port_code, "item": entry.item_id, "at": entry.at.isoformat(),
                    "user": entry.user_id, "label": entry.user_label, "role": entry.role, "action": entry.action,
                    "detail": entry.detail, "ip": entry.ip, "prev": entry.prev_hash}
        if entry.seq != expected or entry.prev_hash != previous or sha256_hex(canonical_json(material)) != entry.hash:
            return {"ok": False, "count": count, "broken_at": entry.seq}
        previous = entry.hash
        expected += 1
    return {"ok": True, "count": count, "broken_at": None}


# ---------------------------------------------------------------------------- rights
def n4_role(user, port=None) -> str | None:
    """SUR or CAP of the same port, else None. A user without the role gets 'not found' everywhere."""
    if user is None or not getattr(user, "is_authenticated", False) or not user.organization_id:
        return None
    if port is not None and user.organization.port_id != port.pk:
        return None
    roles = set(user.roles or []) & set(N4_ROLES)
    if not roles:
        return None
    return "SUR" if "SUR" in roles else "CAP"


def _item_for(user, reference_or_id, port) -> tuple[SecureItem, str]:
    role = n4_role(user, port)
    if role is None:
        raise NotVisible()
    qs = SecureItem.objects.using(DB).filter(port_code=port.code)
    item = qs.filter(reference=str(reference_or_id)).first()
    if item is None and str(reference_or_id).isdigit():
        item = qs.filter(pk=int(reference_or_id)).first()
    if item is None:
        raise NotVisible()
    return item, role


# ---------------------------------------------------------------------------- operations
def deposit(call, actor, *, kind: str, payload: dict, request=None) -> str:
    """Write-only deposit. Returns the receipt reference (shown once to the depositor)."""
    if not (set(actor.roles) & DEPOSIT_ROLES):
        raise NotVisible()
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    if kind not in SecureItem.Kind.values:
        raise RuleViolation(_("Unknown security request kind."))
    if not payload or not any(str(v).strip() for v in payload.values()):
        raise RuleViolation(_("The request is empty."))
    role = next(r for r in ("AGE", "NAV", "SUR", "CAP") if r in actor.roles)
    port = call.port
    year = timezone.now().year
    with transaction.atomic(using=DB):
        SecureSequence.objects.using(DB).get_or_create(port_code=port.code, year=year)
        seq = SecureSequence.objects.using(DB).select_for_update().get(port_code=port.code, year=year)
        seq.last_value += 1
        seq.save(using=DB, update_fields=["last_value"])
        reference = f"N4-{port.code}-{year}-{seq.last_value:04d}"
        due = None
        if kind == SecureItem.Kind.ARMED_GUARDS and call.eta:
            due = call.eta - timedelta(hours=24)  # A1.02: decision at ETA − 24 h
        item = SecureItem(
            reference=reference, port_code=port.code, call_id=call.pk, call_reference=call.reference,
            vessel_name=call.vessel.name, kind=kind, submitted_by_id=actor.user.pk if actor.user else 0,
            submitted_by_label=actor.label, submitted_role=role,
            submitted_org_label=str(actor.org) if actor.org else "", payload_enc=encrypt(payload), due_at=due,
        )
        item.save(using=DB)
    if actor.user is not None:
        _log(port.code, actor.user, role, "CREATE", item, detail=reference, request=request)
    _alert_security_users(port, reference)
    return reference


def _alert_security_users(port, reference: str) -> None:
    """E-mail without any detail (EF-18.3); no row is written in the operational database."""
    from apps.core.models import User

    emails = [u.email for u in User.objects.filter(organization__port=port, is_active=True) if "SUR" in (u.roles or [])]
    if not emails:
        return
    try:
        send_mail("[FLUXAA Port] Espace sûreté / Security space",
                  "Un nouvel élément attend dans l'espace sûreté. / A new item is waiting in the security space.\n"
                  f"{settings.SITE_URL}/surete/", settings.DEFAULT_FROM_EMAIL, emails)
    except Exception as exc:  # pragma: no cover
        log.warning("Security alert e-mail failed: %s", exc)


def list_items(user, port, request=None) -> list[SecureItem]:
    role = n4_role(user, port)
    if role is None:
        raise NotVisible()
    items = list(SecureItem.objects.using(DB).filter(port_code=port.code).order_by("-submitted_at"))
    _log(port.code, user, role, "LIST", detail=f"{len(items)} items", request=request)
    return items


def read_item(user, port, reference_or_id, request=None) -> dict:
    item, role = _item_for(user, reference_or_id, port)
    _log(port.code, user, role, "VIEW", item, request=request)
    return {"item": item, "payload": decrypt(item.payload_enc), "decision": decrypt(item.decision_enc),
            "attachments": list(item.attachments.using(DB).all()), "role": role}


def decide(user, port, reference_or_id, *, decision: str, modalities: str, strong_auth: bool, request=None) -> SecureItem:
    """A1.02 — the security authority decides and sets the modalities."""
    item, role = _item_for(user, reference_or_id, port)
    if role != "SUR":
        raise PermissionRefused(_("Only the security authority decides."))
    if not strong_auth:
        raise StrongAuthRequired()
    if decision not in (SecureItem.Status.APPROVED, SecureItem.Status.APPROVED_COND, SecureItem.Status.REFUSED):
        raise RuleViolation(_("Unknown decision."))
    if item.status not in (SecureItem.Status.SUBMITTED, SecureItem.Status.UNDER_REVIEW):
        raise RuleViolation(_("This item is not awaiting a decision."))
    if not modalities.strip():
        raise RuleViolation(_("State the modalities or the reason."))
    with transaction.atomic(using=DB):
        item.status = decision
        item.decision_enc = encrypt({"decision": decision, "modalities": modalities})
        item.decided_by_id = user.pk
        item.decided_by_label = f"{user.full_name} <{user.email}>"
        item.decided_at = timezone.now()
        item.save(using=DB)
    _log(port.code, user, role, "DECIDE", item, detail=decision, request=request)
    return item


def confirm(user, port, reference_or_id, *, what: str, request=None) -> SecureItem:
    """A1.03 / A1.04 — embarkation, disembarkation, anti-intrusion measures."""
    item, role = _item_for(user, reference_or_id, port)
    if role != "SUR":
        raise PermissionRefused(_("Only the security authority confirms."))
    field = {"embarked": "embarked_at", "disembarked": "disembarked_at", "anti_intrusion": "anti_intrusion_confirmed_at"}.get(what)
    if field is None:
        raise RuleViolation(_("Unknown confirmation."))
    if getattr(item, field) is not None:
        raise RuleViolation(_("Already confirmed."))
    setattr(item, field, timezone.now())
    if what == "disembarked":
        item.status = SecureItem.Status.EXECUTED
    item.save(using=DB)
    _log(port.code, user, role, "CONFIRM", item, detail=what, request=request)
    return item


def add_attachment(user, port, reference_or_id, uploaded, request=None) -> SecureAttachment:
    item, role = _item_for(user, reference_or_id, port)
    data = b"".join(uploaded.chunks()) if hasattr(uploaded, "chunks") else uploaded.read()
    if len(data) > 10 * 1024 * 1024:
        raise RuleViolation(_("File too large (10 MB maximum in the security space)."))
    token = _fernet().encrypt(data)
    attachment = SecureAttachment(item=item, name=getattr(uploaded, "name", "file")[:255],
                                  mime_type=getattr(uploaded, "content_type", "")[:120], size=len(data),
                                  sha256=hashlib.sha256(data).hexdigest(), data_enc=token, uploaded_by_id=user.pk,
                                  uploaded_by_label=f"{user.full_name} <{user.email}>")
    attachment.save(using=DB)
    _log(port.code, user, role, "ATTACH", item, detail=attachment.name, request=request)
    return attachment


def read_attachment(user, port, attachment_id, request=None) -> tuple[SecureAttachment, bytes]:
    role = n4_role(user, port)
    if role is None:
        raise NotVisible()
    attachment = SecureAttachment.objects.using(DB).filter(pk=attachment_id, item__port_code=port.code).first()
    if attachment is None:
        raise NotVisible()
    _log(port.code, user, role, "DOWNLOAD", attachment.item, detail=attachment.name, request=request)
    return attachment, _fernet().decrypt(bytes(attachment.data_enc))


def access_log(user, port, request=None) -> list[SecureAccessLog]:
    role = n4_role(user, port)
    if role is None:
        raise NotVisible()
    return list(SecureAccessLog.objects.using(DB).filter(port_code=port.code).order_by("-seq")[:500])
