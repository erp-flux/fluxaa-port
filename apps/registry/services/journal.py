"""Hash-chained, append-only journal and access audit (CDC EF-3, ENF-3.4, ENF-4.1/4.2).

Each entry stores the hash of the previous one: altering or removing any past record breaks the
chain, which ``verify_chain`` detects. Time-stamping goes through a provider interface so that a
qualified RFC 3161 service can be plugged in later (open point O04) without rewriting the journal.
"""
from __future__ import annotations

import json
import logging

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.core.crypto import canonical_json, seal, sha256_hex

from ..models import AuditEntry, ChainHead, JournalEntry

log = logging.getLogger(__name__)
GENESIS = "0" * 64
EVERYONE = ["*"]


# ---------------------------------------------------------------------------- timestamping
class LocalTimestampProvider:
    """Server clock sealed with the platform key. Replaceable by a qualified TSA (ENF-4.2)."""

    name = "local"

    def stamp(self, digest: str, at) -> str:
        return seal({"digest": digest, "at": at.isoformat(), "provider": self.name})


class Rfc3161TimestampProvider(LocalTimestampProvider):
    """Placeholder for a qualified time-stamping authority (RFC 3161).

    Activate with FLUXAA_TIMESTAMP_PROVIDER=rfc3161 and FLUXAA_TSA_URL once the provider is chosen
    (point O04). Until a TSA client is configured, it falls back to the local seal and records why.
    """

    name = "rfc3161"

    def stamp(self, digest: str, at) -> str:  # pragma: no cover - depends on a remote TSA
        log.warning("RFC 3161 provider selected but no TSA client is configured; using local seal.")
        return "local-fallback:" + super().stamp(digest, at)


def timestamp_provider():
    if settings.FLUXAA_TIMESTAMP_PROVIDER == "rfc3161":
        return Rfc3161TimestampProvider()
    return LocalTimestampProvider()


# ---------------------------------------------------------------------------- hashing
def _normalise(payload: dict | None) -> dict:
    return json.loads(canonical_json(payload or {}))


def _journal_material(entry: JournalEntry) -> dict:
    return {
        "seq": entry.seq,
        "port": entry.port_id,
        "call": entry.call_id,
        "at": entry.at.isoformat(),
        "actor_role": entry.actor_role,
        "actor_user": entry.actor_user_id,
        "actor_master": entry.actor_master_id,
        "actor_org": entry.actor_org_id,
        "actor_label": entry.actor_label,
        "action": entry.action,
        "object_kind": entry.object_kind,
        "object_id": entry.object_id,
        "visible_roles": entry.visible_roles,
        "summary_fr": entry.summary_fr,
        "summary_en": entry.summary_en,
        "payload": entry.payload,
        "prev_hash": entry.prev_hash,
    }


def _audit_material(entry: AuditEntry) -> dict:
    return {
        "seq": entry.seq,
        "port": entry.port_id,
        "call": entry.call_id,
        "at": entry.at.isoformat(),
        "user": entry.user_id,
        "master": entry.master_id,
        "actor_label": entry.actor_label,
        "action": entry.action,
        "object_kind": entry.object_kind,
        "object_id": entry.object_id,
        "detail": entry.detail,
        "ip": entry.ip,
        "prev_hash": entry.prev_hash,
    }


def journal_material(entry: JournalEntry) -> dict:
    """Public form of the hashed material (used by the reversibility export)."""
    return _normalise(_journal_material(entry))


def audit_material(entry: AuditEntry) -> dict:
    return _normalise(_audit_material(entry))


def _lock_head(port, chain: str) -> ChainHead:
    ChainHead.objects.get_or_create(port=port, chain=chain)
    return ChainHead.objects.select_for_update().get(port=port, chain=chain)


# ---------------------------------------------------------------------------- journal
def record(
    *,
    port,
    call=None,
    actor=None,
    action: str,
    summary_fr: str,
    summary_en: str,
    obj=None,
    object_kind: str = "",
    visible_roles: list[str] | None = None,
    payload: dict | None = None,
    role: str = "",
) -> JournalEntry:
    """Append an entry to the port's journal chain."""
    with transaction.atomic():
        head = _lock_head(port, "journal")
        entry = JournalEntry(
            port=port,
            call=call,
            seq=head.last_seq + 1,
            at=timezone.now(),
            actor_role=role or (sorted(actor.roles)[0] if actor is not None and actor.roles else ""),
            actor_user=actor.user if actor is not None and not actor.is_system else None,
            actor_master=actor.master if actor is not None else None,
            actor_org=actor.org if actor is not None else None,
            actor_label=actor.label if actor is not None else "FLUXAA",
            action=action,
            object_kind=object_kind or (obj._meta.model_name if obj is not None else ""),
            object_id=obj.pk if obj is not None else None,
            visible_roles=list(visible_roles if visible_roles is not None else EVERYONE),
            summary_fr=summary_fr[:500],
            summary_en=summary_en[:500],
            payload=_normalise(payload),
            prev_hash=head.last_hash,
        )
        digest = sha256_hex(canonical_json(_journal_material(entry)))
        entry.hash = digest
        provider = timestamp_provider()
        entry.timestamp_provider = provider.name
        entry.timestamp_token = provider.stamp(digest, entry.at)
        entry.save()
        head.last_seq = entry.seq
        head.last_hash = digest
        head.save(update_fields=["last_seq", "last_hash"])
    _queue_webhooks(entry)
    return entry


def _queue_webhooks(entry: JournalEntry) -> None:
    """Outbox for third-party systems: only entries visible to every party (N1) are published."""
    if entry.visible_roles != EVERYONE or entry.call_id is None:
        return
    from ..models import WebhookDelivery, WebhookSubscription

    for sub in WebhookSubscription.objects.filter(port_id=entry.port_id, is_active=True):
        if sub.actions and entry.action not in sub.actions:
            continue
        WebhookDelivery.objects.create(subscription=sub, entry=entry)


def audit(*, port, action: str, user=None, master=None, call=None, obj=None, object_kind: str = "",
          detail: str = "", request=None, label: str = "") -> AuditEntry:
    """Append an access-audit entry (views, downloads, exports, master link uses)."""
    ip = None
    agent = ""
    if request is not None:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = (forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR")) or None
        agent = request.META.get("HTTP_USER_AGENT", "")[:300]
    if not label:
        if master is not None:
            label = f"{master.master_name} — Master"
        elif user is not None:
            label = getattr(user, "full_name", "") or getattr(user, "email", "")
        else:
            label = "FLUXAA"
    with transaction.atomic():
        head = _lock_head(port, "audit")
        entry = AuditEntry(
            port=port, call=call, seq=head.last_seq + 1, at=timezone.now(),
            user=user if user is not None and getattr(user, "pk", None) else None, master=master,
            actor_label=label[:200], action=action,
            object_kind=object_kind or (obj._meta.model_name if obj is not None else ""),
            object_id=obj.pk if obj is not None else None, detail=detail[:300], ip=ip, user_agent=agent,
            prev_hash=head.last_hash,
        )
        digest = sha256_hex(canonical_json(_audit_material(entry)))
        entry.hash = digest
        entry.save()
        head.last_seq = entry.seq
        head.last_hash = digest
        head.save(update_fields=["last_seq", "last_hash"])
    return entry


# ---------------------------------------------------------------------------- verification
def verify_chain(port, chain: str = "journal") -> dict:
    """Recompute the chain. Returns {"ok": bool, "count": n, "broken_at": seq|None, "reason": str}."""
    model, material = (JournalEntry, _journal_material) if chain == "journal" else (AuditEntry, _audit_material)
    previous = GENESIS
    expected_seq = 1
    count = 0
    for entry in model.objects.filter(port=port).order_by("seq").iterator():
        count += 1
        if entry.seq != expected_seq:
            return {"ok": False, "count": count, "broken_at": entry.seq, "reason": "sequence gap (missing entry)"}
        if entry.prev_hash != previous:
            return {"ok": False, "count": count, "broken_at": entry.seq, "reason": "previous hash mismatch"}
        recomputed = sha256_hex(canonical_json(material(entry)))
        if recomputed != entry.hash:
            return {"ok": False, "count": count, "broken_at": entry.seq, "reason": "content altered"}
        previous = entry.hash
        expected_seq += 1
    head = ChainHead.objects.filter(port=port, chain=chain).first()
    if head and (head.last_seq != expected_seq - 1 or head.last_hash != previous):
        return {"ok": False, "count": count, "broken_at": head.last_seq, "reason": "chain head mismatch (truncated)"}
    return {"ok": True, "count": count, "broken_at": None, "reason": ""}


def visible(entry_roles: list[str], actor) -> bool:
    """Journal filtering: explicit roles first; "*" means every party except providers (own service only)."""
    if actor is None:
        return False
    if actor.is_system:
        return True
    if set(entry_roles) & set(actor.roles):
        return True
    if "*" in entry_roles:
        return not (set(actor.roles) <= {"PRE"})
    return False


def entry_visible(entry: JournalEntry, actor) -> bool:
    """A journal entry for this reader: by its roles — and, for a provider, only what its own organisation did or
    the service orders it carries out (several providers on one call never read each other's records)."""
    if not visible(entry.visible_roles, actor):
        return False
    if actor.is_system:
        return True
    if entry.object_kind in ("thread", "document") and entry.object_id:
        # a bilateral exchange or document: its entries (subject, title) follow the object's own visibility, which
        # also tells apart two organisations holding the same role
        from ..models import Document, Thread
        from . import rights

        if entry.object_kind == "thread":
            thread = Thread.objects.filter(pk=entry.object_id).first()
            if thread is not None and not rights.thread_visible(actor, thread):
                return False
        else:
            document = Document.objects.filter(pk=entry.object_id).select_related("type").first()
            if document is not None and not rights.document_visible(actor, document):
                return False
    if not (set(actor.roles) <= {"PRE"}):
        return True
    org_id = actor.org.pk if actor.org is not None else None
    if org_id is not None and entry.actor_org_id == org_id:
        return True
    if entry.object_kind == "servicerequest" and entry.object_id:
        from ..models import ServiceRequest

        return ServiceRequest.objects.filter(pk=entry.object_id, provider_org_id=org_id).exists()
    return False
