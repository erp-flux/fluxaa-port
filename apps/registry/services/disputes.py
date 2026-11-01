"""Disputes (EF-4): first-class objects, never blocking the operation, never arbitrated by the platform.
Only "respond" and "close with / without agreement" exist — no "reject" function anywhere."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.roles import role_label

from ..models import Dispute, DisputeEntry, DisputeStatus
from . import journal
from .calls import call_url, next_number
from .errors import PermissionRefused, RuleViolation, ensure_not_closed, ensure_open
from .notifications import notify
from .rights import is_dispute_counterpart, is_dispute_opener, roles_with

OPENING_ROLES = roles_with("C", "dispute") | {"CAP", "SVC", "ADM", "APO", "PRE", "SUR"}
# what a dispute may concern; a MEASUREMENT dispute keeps the bill of lading locked until it is closed (EF-7.4)
TARGET_KINDS = ("MILESTONE", "TASK", "MEASUREMENT", "DOCUMENT", "REQUEST", "OTHER")


def _check_target(call, target_kind: str, target_id) -> int | None:
    if target_kind not in TARGET_KINDS:
        raise RuleViolation(_("Unknown subject of dispute."))
    if target_id in (None, ""):
        return None
    try:
        target_id = int(target_id)
    except (TypeError, ValueError):
        raise RuleViolation(_("Unknown subject of dispute.")) from None
    related = {"MILESTONE": call.milestones, "TASK": call.tasks, "MEASUREMENT": call.measurements,
               "DOCUMENT": call.documents, "REQUEST": call.requests}.get(target_kind)
    if related is None or not related.filter(pk=target_id).exists():
        raise RuleViolation(_("The disputed item does not belong to this call."))
    return target_id


def _author(call, target_kind: str, target_id) -> tuple[str, int | None, bool] | None:
    """(role, organisation, by the master) of the disputed item, when it has a single author."""
    if target_id is None:
        return None
    if target_kind == "MILESTONE":
        m = call.milestones.filter(pk=target_id).first()
        return (m.emitter_role, m.emitter_org_id, m.emitter_master_id is not None) if m else None
    if target_kind == "DOCUMENT":
        d = call.documents.filter(pk=target_id).first()
        return (d.issuer_role, d.issuer_org_id, d.issuer_master_id is not None) if d else None
    if target_kind == "TASK":
        t = call.tasks.filter(pk=target_id).select_related("completed_by", "completed_by_master").first()
        if t is None or not t.completed_role:
            return None
        org_id = t.completed_by.organization_id if t.completed_by else (
            t.completed_by_master.organization_id if t.completed_by_master else None)
        return (t.completed_role, org_id, t.completed_by_master_id is not None)
    if target_kind == "REQUEST":
        r = call.requests.filter(pk=target_id).first()
        return (r.requester_role, r.requester_org_id, False) if r else None
    return None


def _entry(dispute, actor, role, kind, text) -> DisputeEntry:
    now = timezone.now()
    return DisputeEntry.objects.create(
        dispute=dispute, kind=kind, role=role, user=actor.user if not actor.is_system else None, master=actor.master,
        author_label=actor.label, text=text, at=now,
        seal=seal({"dispute": dispute.reference, "kind": kind, "role": role, "text": text, "at": now.isoformat(),
                   "by": actor.label}),
    )


@transaction.atomic
def open_dispute(call, actor, *, target_kind: str, target_id: int | None, subject: str, statement: str,
                 as_role: str | None = None, auto: bool = False, counterpart_role: str = "") -> Dispute:
    ensure_open(call)
    if not statement.strip() or not subject.strip():
        raise RuleViolation(_("A dispute states its subject and grounds."))
    target_id = _check_target(call, target_kind, target_id)
    role = actor.pick_role(OPENING_ROLES, as_role) if not actor.is_system else (as_role or "SYS")
    year = timezone.now().year
    counterpart_role = counterpart_role if counterpart_role != role else ""
    author = _author(call, target_kind, target_id)
    counterpart_org, counterpart_master = None, False
    if author is not None and counterpart_role and author[0] == counterpart_role:
        counterpart_org, counterpart_master = author[1], author[2]  # addressed to the author, not to the role
    dispute = Dispute.objects.create(
        call=call, reference=f"DSP-{call.port.code}-{year}-{next_number(call.port, 'DSP', year):05d}",
        subject=subject[:250], target_kind=target_kind, target_id=target_id, opened_role=role, opened_org=actor.org,
        opened_user=actor.user if not actor.is_system else None, opened_master=actor.master,
        opened_label=actor.label, counterpart_role=counterpart_role, counterpart_org_id=counterpart_org,
        counterpart_master=counterpart_master, auto_created=auto,
    )
    _entry(dispute, actor, role, DisputeEntry.Kind.STATEMENT, statement)
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="dispute.opened", obj=dispute, visible_roles=["*"],
        summary_fr=f"Contestation {dispute.reference} ouverte par {role_label(role)} : {dispute.subject}"
        + (" (automatique — conflit de saisie)" if auto else ""),
        summary_en=f"Dispute {dispute.reference} opened by {role}: {dispute.subject}"
        + (" (automatic — conflicting entries)" if auto else ""),
        payload={"target_kind": target_kind, "target_id": target_id, "counterpart": dispute.counterpart_role},
    )
    recipients = {dispute.counterpart_role, "AGE", "CAP"} - {"", role}
    notify(call, recipients, key=f"dispute:{dispute.pk}", title_fr=f"{call.reference} : contestation {dispute.reference}",
           title_en=f"{call.reference}: dispute {dispute.reference}", url=call_url(call) + "#contestations")
    return dispute


@transaction.atomic
def respond(dispute: Dispute, actor, text: str) -> DisputeEntry:
    ensure_not_closed(dispute.call)
    if dispute.status in (DisputeStatus.CLOSED_AGREED, DisputeStatus.CLOSED_NOT_AGREED):
        raise RuleViolation(_("This dispute is closed."))
    if not text.strip():
        raise RuleViolation(_("The response is empty."))
    if dispute.counterpart_role:
        allowed = {dispute.counterpart_role} if is_dispute_counterpart(actor, dispute) else set()
    else:
        allowed = OPENING_ROLES - {dispute.opened_role}
    if dispute.status == DisputeStatus.ANSWERED and is_dispute_opener(actor, dispute):
        allowed = allowed | {dispute.opened_role}
    if not allowed:
        raise PermissionRefused(_("This dispute is addressed to another party."))
    role = actor.pick_role(allowed)
    entry = _entry(dispute, actor, role, DisputeEntry.Kind.RESPONSE, text)
    if dispute.status == DisputeStatus.OPEN and role != dispute.opened_role:
        dispute.status = DisputeStatus.ANSWERED
        dispute.save(update_fields=["status"])
    journal.record(port=dispute.call.port, call=dispute.call, actor=actor, role=role, action="dispute.answered",
                   obj=dispute, visible_roles=["*"], summary_fr=f"Contestation {dispute.reference} : réponse de {role_label(role)}",
                   summary_en=f"Dispute {dispute.reference}: response from {role}")
    notify(dispute.call, {dispute.opened_role, dispute.counterpart_role} - {role, ""},
           key=f"dispute:{dispute.pk}:entry:{entry.pk}", title_fr=f"{dispute.call.reference} : réponse sur {dispute.reference}",
           title_en=f"{dispute.call.reference}: response on {dispute.reference}", url=call_url(dispute.call) + "#contestations")
    return entry


@transaction.atomic
def close(dispute: Dispute, actor, *, agreed: bool, text: str) -> Dispute:
    """Closed by the party that opened it, or recorded by the harbour master. Never arbitrated."""
    ensure_not_closed(dispute.call)
    if dispute.status in (DisputeStatus.CLOSED_AGREED, DisputeStatus.CLOSED_NOT_AGREED):
        raise RuleViolation(_("This dispute is already closed."))
    if not text.strip():
        raise RuleViolation(_("State how the dispute ends."))
    # the party that opened it (same organisation: another holder of the role cannot settle it), or the harbour
    # master recording that it ends without agreement
    role = actor.pick_role({dispute.opened_role} if is_dispute_opener(actor, dispute) else {"CAP"})
    if role == "CAP" and dispute.opened_role != "CAP" and agreed:
        raise PermissionRefused(_("The harbour master records a closure without agreement only: an agreement belongs to the parties."))
    _entry(dispute, actor, role, DisputeEntry.Kind.CLOSURE, text)
    dispute.status = DisputeStatus.CLOSED_AGREED if agreed else DisputeStatus.CLOSED_NOT_AGREED
    dispute.closed_at = timezone.now()
    dispute.save(update_fields=["status", "closed_at"])
    journal.record(port=dispute.call.port, call=dispute.call, actor=actor, role=role, action="dispute.closed",
                   obj=dispute, visible_roles=["*"],
                   summary_fr=f"Contestation {dispute.reference} close {'par accord' if agreed else 'sans accord'}",
                   summary_en=f"Dispute {dispute.reference} closed {'with agreement' if agreed else 'without agreement'}")
    return dispute
