"""Call life cycle (EF-1), template instantiation and relative deadlines (EF-5), roles on call
(EF-12.1) and account-less master access (EF-13)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import Berth, Organization
from apps.core.roles import role_label

from ..models import (
    CALL_TRANSITIONS,
    OPERATIONAL_CHAIN,
    AlertLevel,
    Authorization,
    CallParty,
    CallSequence,
    CallStage,
    CallStatus,
    CallTemplate,
    CallTemplateUse,
    MasterAccessLink,
    PortCall,
    PortDefaultParty,
    Task,
    TaskStatus,
    TemplateKind,
    TemplateVersion,
    Transition,
    Vessel,
)
from . import holdpoints, journal
from .context import Actor, actor_for_call, port_actor, system_actor
from .errors import HoldPointRefused, NotVisible, PermissionRefused, RuleViolation, ensure_open
from .notifications import notify

# Roles the agency may invite on its own call; authorities come from the port's default parties
AGENCY_INVITABLE_ROLES = {"TER", "INS", "COM", "PRE", "SVC"}
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def next_number(port, kind: str, year: int | None = None) -> int:
    year = year or timezone.now().year
    with transaction.atomic():
        CallSequence.objects.get_or_create(port=port, kind=kind, year=year)
        seq = CallSequence.objects.select_for_update().get(port=port, kind=kind, year=year)
        seq.last_value += 1
        seq.save(update_fields=["last_value"])
        return seq.last_value


def call_url(call) -> str:
    return f"/escales/{call.pk}/"


# ============================================================================ deadlines
def compute_due(task: Task, call: PortCall):
    if not task.anchor:
        return None
    base = call.anchor_time(task.anchor)
    if base is None:
        return None
    return base + timedelta(minutes=task.offset_minutes)


def alert_level_for(task: Task, port, now=None) -> str:
    now = now or timezone.now()
    if task.status != TaskStatus.PENDING or task.due_at is None or task.continuous:
        return AlertLevel.NONE
    if now >= task.due_at:
        if task.is_blocking or now - task.due_at >= timedelta(minutes=port.escalation_after_minutes):
            return AlertLevel.ESCALATED
        return AlertLevel.LATE
    if now >= task.due_at - timedelta(hours=port.reminder_lead_hours):
        return AlertLevel.REMINDER
    return AlertLevel.NONE


LEVEL_RANK = {AlertLevel.NONE: 0, AlertLevel.REMINDER: 1, AlertLevel.LATE: 2, AlertLevel.ESCALATED: 3}


def recompute_deadlines(call: PortCall) -> int:
    """Cascade after a revision of an anchor (EF-5.4, S3). Silent: lateness states are re-evaluated,
    but a level that goes *down* is reset without notification and no notification is sent here."""
    now = timezone.now()
    changed = []
    for task in call.tasks.filter(status=TaskStatus.PENDING):
        due = compute_due(task, call)
        level = task.alert_level
        target = alert_level_for(Task(due_at=due, status=task.status, criticality=task.criticality,
                                      continuous=task.continuous), call.port, now)
        if LEVEL_RANK[target] < LEVEL_RANK[level]:
            level = target  # the deadline moved away: lateness withdrawn silently
        if due != task.due_at or level != task.alert_level:
            task.due_at = due
            task.alert_level = level
            changed.append(task)
    if changed:
        Task.objects.bulk_update(changed, ["due_at", "alert_level"])
    return len(changed)


# ============================================================================ creation
def _published_versions(port, codes: list[str]) -> list[TemplateVersion]:
    versions = []
    for code in codes:
        template = CallTemplate.objects.filter(port=port, code=code, is_active=True).first()
        if template is None:
            raise RuleViolation(_("Unknown or inactive call template: %(code)s") % {"code": code})
        version = template.published_version
        if version is None:
            raise RuleViolation(_("Template %(code)s has no published version.") % {"code": code})
        versions.append(version)
    return versions


def instantiate_tasks(call: PortCall, versions: list[TemplateVersion], *, berth_kind: str | None = None,
                      stage=None, only_new: bool = False) -> list[Task]:
    """Instantiate every line of the templates — no manual entry (EF-5.1). *berth_kind* is the operating area the
    tasks are for (the call's own, or a later stage's); *stage* ties the tasks to a later stage of the call;
    *only_new* skips the lines the call already holds (a template reused by a later stage adds only the tasks
    specific to the new area, such as the quay-side lines of the common base)."""
    tasks = []
    berth_kind = berth_kind or call.requested_berth_kind
    order = call.tasks.count()
    existing = set(call.tasks.values_list("template_code", "number")) if only_new else set()
    for version in versions:
        code = version.template.code
        for tt in version.tasks.all().order_by("order", "number"):
            if tt.berth_kinds and berth_kind not in tt.berth_kinds:
                continue  # operation × berth type (FLX-SPEC-002 §0.1)
            if (code, tt.number) in existing:
                continue
            order += 1
            tasks.append(Task(
                call=call, stage=stage, template_task=tt, template_code=code, number=tt.number,
                section_fr=tt.section_fr, section_en=tt.section_en, title_fr=tt.title_fr, title_en=tt.title_en,
                role=tt.role, co_roles=list(tt.co_roles or []), joint=tt.joint, nature=tt.nature,
                criticality=tt.criticality, confidentiality=tt.confidentiality, anchor=tt.anchor,
                offset_minutes=tt.offset_minutes, timing_fr=tt.timing_fr, timing_en=tt.timing_en,
                request_type_code=tt.request_type_code, request_side=tt.request_side,
                milestone_codes=list(tt.milestone_codes or []), document_type_code=tt.document_type_code,
                auto_event=tt.auto_event, continuous=tt.continuous,
                not_applicable_allowed=tt.not_applicable_allowed, order=order,
            ))
    created = Task.objects.bulk_create(tasks)
    for task in created:
        task.due_at = compute_due(task, call)
    Task.objects.bulk_update(created, ["due_at"])
    return created


def _check_templates(port, berth_kind: str, operations: list[str], modules: list[str], linked_call) -> list[str]:
    codes = ["M0", *operations, *modules]
    if len(set(codes)) != len(codes):
        raise RuleViolation(_("A template is selected twice."))
    templates = {t.code: t for t in CallTemplate.objects.filter(port=port, code__in=codes)}
    if "M0" not in templates or templates["M0"].kind != TemplateKind.BASE:
        raise RuleViolation(_("The common base M0 is missing for this port."))
    if not operations:
        raise RuleViolation(_("Select at least one operation model (discharge, loading, STS…)."))
    for code in operations:
        if code not in templates or templates[code].kind != TemplateKind.OPERATION:
            raise RuleViolation(_("%(code)s is not an operation model.") % {"code": code})
    for code in modules:
        if code not in templates or templates[code].kind != TemplateKind.MODULE:
            raise RuleViolation(_("%(code)s is not an additional module.") % {"code": code})
    for code in codes:
        tpl = templates[code]
        if tpl.berth_kinds and berth_kind not in tpl.berth_kinds:
            raise RuleViolation(
                _("Template %(code)s does not apply to this operating area.") % {"code": code}
            )
    return codes


RECIPROCAL_LINK = {"STS": "STS", "INNER": "OUTER", "OUTER": "INNER"}


def _requires_link(call) -> bool:
    return CallTemplate.objects.filter(port=call.port, code__in=call.template_codes, requires_linked_call=True).exists()


def _role_on_partner(actor: Actor, partner: PortCall) -> str:
    """The agency links its own calls; calls of two different agencies are linked by the harbour master, who is a
    party to both. Anyone else gets "not found": another agency's call is never disclosed."""
    if actor.is_system:
        return "SYS"
    if actor.user is None:
        raise NotVisible()
    from .rights import draft_visible

    partner_actor = actor_for_call(partner, user=actor.user)  # NotVisible without a role on the partner call
    roles = {"AGE", "CAP"} & set(partner_actor.roles)
    if not roles or not draft_visible(partner_actor, partner):
        raise NotVisible()
    return sorted(roles)[0]


def _journal_link(call: PortCall, partner: PortCall, actor: Actor, link_kind: str, role: str = "") -> None:
    journal.record(port=call.port, call=call, actor=actor, action="call.linked", obj=call, role=role,
                   summary_fr=f"Escale liée à {partner.reference} ({partner.vessel.name})",
                   summary_en=f"Call linked to {partner.reference} ({partner.vessel.name})",
                   payload={"partner": partner.reference, "kind": link_kind})


def link_partner(call: PortCall, actor: Actor, partner: PortCall, link_kind: str = "STS") -> PortCall:
    """STS and double banking connect two calls; each keeps its own master and its own tasks. The link is
    written in the journal of both calls."""
    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("The partner call is indicated by the agency."))
    if partner.pk == call.pk or partner.port_id != call.port_id:
        raise RuleViolation(_("Choose another call of the same port."))
    if link_kind not in RECIPROCAL_LINK:
        raise RuleViolation(_("Unknown link."))
    ensure_open(call)
    partner_role = _role_on_partner(actor, partner)
    ensure_open(partner)
    with transaction.atomic():
        call.linked_call = partner
        call.link_kind = link_kind
        call.save(update_fields=["linked_call", "link_kind", "updated_at"])
        _journal_link(call, partner, actor, link_kind)
        if partner.linked_call_id is None:
            partner.linked_call = call
            partner.link_kind = RECIPROCAL_LINK[link_kind]
            partner.save(update_fields=["linked_call", "link_kind", "updated_at"])
            _journal_link(partner, call, actor, partner.link_kind, role=partner_role if partner_role != "SYS" else "")
    return call


@transaction.atomic
def create_call(user, *, vessel: Vessel, eta, requested_berth_kind: str, operations: list[str],
                modules: list[str] | None = None, requested_berth: Berth | None = None, etb=None, ets=None, etc=None,
                etd=None, product: str = "", quantity=None, quantity_unit: str = "MT", voyage_number: str = "",
                last_port: str = "", next_port: str = "", parties: list[tuple[Organization, str]] | None = None,
                linked_call: PortCall | None = None, link_kind: str = "") -> PortCall:
    """Only the agency creates a call (EF-1.1). Tasks of M0 + operations + modules are instantiated."""
    actor = port_actor(user)
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("Only a shipping agency can create a call."))
    port = actor.port
    modules = list(modules or [])
    if vessel.port_id != port.id:
        raise RuleViolation(_("This vessel is not registered in this port."))
    if requested_berth is not None and (requested_berth.port_id != port.id or requested_berth.kind != requested_berth_kind):
        raise RuleViolation(_("The requested berth does not match the operating area."))
    if linked_call is not None and linked_call.port_id != port.id:
        raise RuleViolation(_("The partner call belongs to another port."))
    linked_role = ""
    if linked_call is not None:
        try:
            linked_role = _role_on_partner(actor, linked_call)
        except NotVisible:
            raise RuleViolation(_("Partner call not found among your calls: the harbour master links the calls of "
                                  "two different agencies.")) from None
    for auto_code, kinds in (("MA2", {Berth.Kind.SPM}), ("MA3", {Berth.Kind.ANCHORAGE, Berth.Kind.STS_AREA})):
        if requested_berth_kind in kinds and auto_code not in modules and CallTemplate.objects.filter(
            port=port, code=auto_code, is_active=True
        ).exists():
            modules.append(auto_code)  # SPM module / anchorage stay apply by nature of the area
    codes = _check_templates(port, requested_berth_kind, list(operations), modules, linked_call)
    versions = _published_versions(port, codes)

    year = timezone.now().year
    reference = f"{port.code}-{year}-{next_number(port, 'CALL', year):04d}"
    call = PortCall.objects.create(
        port=port, reference=reference, vessel=vessel, voyage_number=voyage_number, agency=user.organization,
        requested_berth_kind=requested_berth_kind, requested_berth=requested_berth, product=product,
        quantity=quantity, quantity_unit=quantity_unit, last_port=last_port, next_port=next_port, eta=eta, etb=etb,
        ets=ets, etc=etc, etd=etd, linked_call=linked_call, link_kind=link_kind, created_by=user,
    )
    for version in versions:
        CallTemplateUse.objects.create(call=call, template_version=version)
    CallStage.objects.create(call=call, order=1, berth_kind=requested_berth_kind, operations=codes[1:], planned_from=etb,
                             planned_to=etd, status=CallStage.Status.CURRENT, created_by=user)

    # Roles on the call: the agency, the port's default parties, then the parties named by the agency
    CallParty.objects.create(call=call, organization=user.organization, role="AGE", granted_by=user)
    for default in PortDefaultParty.objects.filter(port=port).select_related("organization"):
        if default.organization.is_active:
            CallParty.objects.get_or_create(
                call=call, organization=default.organization, role=default.role, revoked_at=None,
                defaults={"granted_by": user, "is_default": True},
            )
    for org, role in parties or []:
        _grant(call, actor, org, role, user)

    instantiate_tasks(call, versions)
    if linked_call is not None and linked_call.linked_call_id is None:
        linked_call.linked_call = call
        linked_call.link_kind = RECIPROCAL_LINK.get(link_kind or "STS", "STS")
        linked_call.save(update_fields=["linked_call", "link_kind", "updated_at"])
        _journal_link(linked_call, call, actor, linked_call.link_kind, role=linked_role)
    journal.record(
        port=port, call=call, actor=actor, role="AGE", action="call.created", obj=call,
        summary_fr=f"Escale {reference} créée pour {vessel.name} — modèles {', '.join(codes)}",
        summary_en=f"Call {reference} created for {vessel.name} — templates {', '.join(codes)}",
        payload={"templates": {v.template.code: v.number for v in versions}, "eta": eta, "berth_kind": requested_berth_kind},
    )
    _complete_auto(call, "call.created", actor)
    return call


def _complete_auto(call, event: str, actor: Actor) -> None:
    from .tasks import system_complete

    for task in call.tasks.filter(auto_event=event, status=TaskStatus.PENDING):
        system_complete(task, actor, evidence=f"call:{call.pk}", note=event)


# ============================================================================ roles on call
def _grant(call, actor: Actor, org: Organization, role: str, user=None) -> CallParty:
    if org.port_id != call.port_id or not org.is_active:
        raise RuleViolation(_("This organisation is not active in this port."))
    if role not in (org.allowed_roles or []):
        raise RuleViolation(
            _("%(org)s cannot hold the role %(role)s.") % {"org": org, "role": role_label(role)}
        )
    if not actor.is_system and "CAP" not in actor.roles:
        if "AGE" not in actor.roles or role not in AGENCY_INVITABLE_ROLES:
            raise PermissionRefused(_("The agency may invite terminals, surveyors, owners/charterers, providers and marine services only."))
    party, created = CallParty.objects.get_or_create(
        call=call, organization=org, role=role, revoked_at=None, defaults={"granted_by": user},
    )
    return party


def add_party(call, actor: Actor, org: Organization, role: str, valid_until=None) -> CallParty:
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    party = _grant(call, actor, org, role, actor.user)
    if valid_until:
        party.valid_until = valid_until
        party.save(update_fields=["valid_until"])
    journal.record(
        port=call.port, call=call, actor=actor, action="party.granted", obj=party,
        summary_fr=f"Rôle {role} accordé à {org}", summary_en=f"Role {role} granted to {org}",
        payload={"organization": org.pk, "role": role, "valid_until": valid_until},
    )
    if call.status != CallStatus.DRAFT:
        notify(call, [role], key=f"party:{party.pk}", title_fr=f"Vous êtes invité sur l'escale {call.reference}",
               title_en=f"You are invited on call {call.reference}", url=call_url(call), organizations=[org.pk])
        convene_parties(call, actor, parties=[party])
    from .requests import assign_pending_providers

    assign_pending_providers(call, role, actor)  # orders created before the provider joined
    return party


def designate_shore_side(call, actor: Actor, party: CallParty) -> CallParty:
    """When several organisations hold TER (or PRE) on a call, the agency or the harbour master designates the one
    that speaks for the shore side: it records the shore-side milestones and the shore figure, and countersigns for
    the shore (FLX-SPEC-001 §7)."""
    ensure_open(call)
    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("The agency or the harbour master designates the shore side."))
    if party.call_id != call.id or party.revoked_at is not None or party.role not in ("TER", "PRE"):
        raise RuleViolation(_("Only an active terminal or provider of the call can speak for the shore side."))
    with transaction.atomic():
        call.parties.filter(role=party.role, shore_side=True).exclude(pk=party.pk).update(shore_side=False)
        party.shore_side = True
        party.save(update_fields=["shore_side"])
        journal.record(
            port=call.port, call=call, actor=actor, action="party.shore_side", obj=party,
            summary_fr=f"{party.organization} désigné pour parler au nom du côté terre ({party.role})",
            summary_en=f"{party.organization} designated to speak for the shore side ({party.role})",
        )
    return party


def revoke_party(call, actor: Actor, party: CallParty, reason: str) -> CallParty:
    """Revocation removes access immediately and never purges what the organisation entered (EF-12.5)."""
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    if party.call_id != call.id or party.revoked_at is not None:
        raise RuleViolation(_("This role is not active on the call."))
    if "CAP" not in actor.roles:
        if "AGE" not in actor.roles or party.is_default or party.role not in AGENCY_INVITABLE_ROLES:
            raise PermissionRefused(_("Only the harbour master may revoke this role."))
    party.revoked_at = timezone.now()
    party.revoked_by = actor.user
    party.revoke_reason = reason
    party.save(update_fields=["revoked_at", "revoked_by", "revoke_reason"])
    for link in call.master_links.filter(role=party.role, organization=party.organization, revoked_at__isnull=True):
        revoke_master_link(link, actor, _("role revoked: %(r)s") % {"r": reason})
    journal.record(
        port=call.port, call=call, actor=actor, action="party.revoked", obj=party,
        summary_fr=f"Rôle {party.role} retiré à {party.organization} — {reason}",
        summary_en=f"Role {party.role} revoked from {party.organization} — {reason}",
    )
    return party


# ============================================================================ life cycle
def _set_status(call, target: str, actor: Actor, *, reason: str = "") -> None:
    if target not in CALL_TRANSITIONS.get(call.status, set()):
        raise RuleViolation(
            _("Transition from “%(a)s” to “%(b)s” is not part of the call life cycle.")
            % {"a": CallStatus(call.status).label, "b": CallStatus(target).label}
        )
    previous = call.status
    call.status = target
    fields = ["status", "updated_at"]
    if target == CallStatus.DECLARED:
        call.declared_at = timezone.now()
        fields.append("declared_at")
    if target in {CallStatus.CLOSED}:
        call.closed_at = timezone.now()
        fields.append("closed_at")
    call.save(update_fields=fields)
    journal.record(
        port=call.port, call=call, actor=actor, action="call.status", obj=call,
        summary_fr=f"Statut : {CallStatus(previous).label} → {CallStatus(target).label}" + (f" — {reason}" if reason else ""),
        summary_en=f"Status: {previous} → {target}" + (f" — {reason}" if reason else ""),
        payload={"from": previous, "to": target, "reason": reason},
    )


def advance_from_milestone(call, target: str, actor: Actor) -> bool:
    """Move a call forward along the operational chain when a milestone is recorded (EF-1.2)."""
    if not target or call.status == target:
        return False
    if target in CALL_TRANSITIONS.get(call.status, set()):
        _set_status(call, target, actor)
        return True
    if call.status in OPERATIONAL_CHAIN and target in OPERATIONAL_CHAIN and call.status != CallStatus.PLANNED:
        if OPERATIONAL_CHAIN.index(target) > OPERATIONAL_CHAIN.index(call.status):
            previous = call.status
            call.status = target
            call.save(update_fields=["status", "updated_at"])
            journal.record(
                port=call.port, call=call, actor=actor, action="call.status", obj=call,
                summary_fr=f"Statut : {CallStatus(previous).label} → {CallStatus(target).label} (jalon enregistré)",
                summary_en=f"Status: {previous} → {target} (milestone recorded)",
                payload={"from": previous, "to": target, "reason": "milestone"},
            )
            return True
    return False


def with_refusal_log(call, actor: Actor, attempted: str, func, *args, **kwargs):
    """Run *func* atomically; if a hold point refuses, record the refusal outside the rolled-back
    transaction so that it stays in the journal (EF-11.3)."""
    try:
        with transaction.atomic():
            return func(*args, **kwargs)
    except HoldPointRefused as exc:
        holdpoints.record_refusal(call, actor, exc, attempted)
        raise


def declare_call(call: PortCall, actor: Actor) -> PortCall:
    """AGE declares the call and requests the green light; all parties are notified (EF-1.4)."""
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("Only the agency declares the call."))
    if call.status != CallStatus.DRAFT:
        raise RuleViolation(_("Only a draft call can be declared."))

    if call.linked_call_id is None and _requires_link(call):
        raise RuleViolation(_("STS and double banking link two vessels: indicate the partner call before declaring."))

    def _do():
        holdpoints.check(call, Transition.DECLARE)
        _set_status(call, CallStatus.DECLARED, actor)
        _complete_auto(call, "call.declared", actor)
        from ..models import RequestType
        from .requests import create_request

        if RequestType.objects.filter(port=call.port, code="GREEN_LIGHT", is_active=True).exists():
            if not call.requests.filter(type__code="GREEN_LIGHT").exists():
                create_request(call, actor, "GREEN_LIGHT", {}, as_role="AGE")
        return call

    with_refusal_log(call, actor, "declare", _do)
    notify(call, ["*"], key=f"declared:{call.pk}",
           title_fr=f"Nouvelle escale déclarée : {call.reference} — {call.vessel.name} (ETA {call.eta:%d/%m %H:%M} UTC)",
           title_en=f"New call declared: {call.reference} — {call.vessel.name} (ETA {call.eta:%d/%m %H:%M} UTC)",
           url=call_url(call), realtime=True, exclude_user=actor.user)
    from .requests import notify_submission

    for req in call.requests.filter(status="SUBMITTED").select_related("type", "call"):
        notify_submission(req)  # requests filed while the call was a draft reach their authority now
    convene_parties(call, actor)  # parties without an account receive their own way in (link until closure)
    return call


ESTIMATE_FIELDS = ("eta", "etb", "ets", "etc", "etd")


@transaction.atomic
def update_estimates(call: PortCall, actor: Actor, reason: str = "", **values) -> int:
    """Revise estimated times. Rule 1: the agency owns ETA/ETS/ETC/ETD; once a berth is assigned,
    ETB belongs to the port authority. Every relative deadline is recomputed in cascade."""
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    changes = {}
    berth_assigned = Authorization.objects.filter(call=call, type_code="BERTH").exists()
    for field, value in values.items():
        if field not in ESTIMATE_FIELDS or value is None:
            continue
        owner = "APO" if field == "etb" and berth_assigned else "AGE"
        if owner not in actor.roles:
            raise PermissionRefused(
                _("%(field)s is entered by %(role)s only (single emitter).") % {"field": field.upper(), "role": role_label(owner)}
            )
        old = getattr(call, field)
        if old != value:
            changes[field] = (old, value)
            setattr(call, field, value)
    if not changes:
        return 0
    if call.eta is None:
        raise RuleViolation(_("ETA is mandatory."))
    call.save(update_fields=[*changes.keys(), "updated_at"])
    count = recompute_deadlines(call)
    desc_fr = ", ".join(f"{k.upper()} {o:%d/%m %H:%M} → {n:%d/%m %H:%M}" if o else f"{k.upper()} → {n:%d/%m %H:%M}"
                        for k, (o, n) in changes.items())
    journal.record(
        port=call.port, call=call, actor=actor, action="call.estimates_revised", obj=call,
        summary_fr=f"Révision : {desc_fr}" + (f" — {reason}" if reason else ""),
        summary_en=f"Revision: {desc_fr}" + (f" — {reason}" if reason else ""),
        payload={k: {"from": o, "to": n} for k, (o, n) in changes.items()} | {"reason": reason, "tasks_rescheduled": count},
    )
    if call.status != CallStatus.DRAFT:
        stamp = timezone.now().strftime("%Y%m%d%H%M%S%f")
        notify(call, ["*"], key=f"estimates:{call.pk}:{stamp}",
               title_fr=f"{call.reference} : horaires révisés ({desc_fr})",
               title_en=f"{call.reference}: times revised ({desc_fr})", url=call_url(call), exclude_user=actor.user)
    return count


def cancel_call(call: PortCall, actor: Actor, reason: str) -> PortCall:
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("Only the agency can cancel its call."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    with transaction.atomic():
        _set_status(call, CallStatus.CANCELLED, actor, reason=reason)
    notify(call, ["*"], key=f"cancelled:{call.pk}", title_fr=f"Escale {call.reference} annulée — {reason}",
           title_en=f"Call {call.reference} cancelled — {reason}", url=call_url(call), realtime=True)
    return call


def confirm_closure(call: PortCall, actor: Actor) -> None:
    """Task 39, agency side: the agency confirms the file is complete (C)."""
    from .tasks import sign_task

    if "AGE" not in actor.roles:
        raise PermissionRefused(_("Only the agency confirms the closure request."))
    if call.status != CallStatus.DEPARTED:
        raise RuleViolation(_("The call can be closed only after departure."))
    task = call.tasks.filter(template_code="M0", number="39").first()
    if task is not None:
        sign_task(task, actor, role="AGE", comment="closure requested")
    journal.record(port=call.port, call=call, actor=actor, role="AGE", action="call.closure_requested", obj=call,
                   summary_fr="Clôture demandée par l'agence", summary_en="Closure requested by the agency")
    notify(call, ["CAP"], key=f"closure:{call.pk}", title_fr=f"{call.reference} : clôture à prononcer",
           title_en=f"{call.reference}: closure to be decided", url=call_url(call))


def close_call(call: PortCall, actor: Actor) -> PortCall:
    """CAP closes the call — refused while a dispute is open or the statement of facts is not signed."""
    from .errors import StrongAuthRequired
    from .tasks import sign_task

    if "CAP" not in actor.roles:
        raise PermissionRefused(_("Only the harbour master closes a call."))
    if not actor.strong_auth:
        raise StrongAuthRequired()
    if call.status != CallStatus.DEPARTED:
        raise RuleViolation(_("The call can be closed only after departure."))
    task = call.tasks.filter(template_code="M0", number="39").first()
    if task is not None and not task.signatures.filter(role="AGE").exists():
        raise RuleViolation(_("The agency has not requested the closure yet."))

    def _do():
        holdpoints.check(call, Transition.CLOSE)
        if task is not None and task.status == TaskStatus.PENDING:
            sign_task(task, actor, role="CAP", comment="closed by the harbour master")
        _set_status(call, CallStatus.CLOSED, actor)
        return call

    return with_refusal_log(call, actor, "close", _do)


def archive_call(call: PortCall, actor: Actor) -> PortCall:
    if "CAP" not in actor.roles:
        raise PermissionRefused(_("Only the harbour master archives a call."))
    with transaction.atomic():
        _set_status(call, CallStatus.ARCHIVED, actor)
    return call


# ============================================================================ master access (EF-13)
def _new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def _code_hash(code: str) -> str:
    return hashlib.sha256(("code:" + code.strip().upper().replace("-", "")).encode("utf-8")).hexdigest()


def _token_hash(token: str) -> str:
    return hashlib.sha256(("token:" + token.strip()).encode("utf-8")).hexdigest()


# Roles a party may exercise through an account-less link: the ones that enter and consult, never the ones
# that decide (CAP, APO, ADM, SUR keep an account with a second factor) nor the agency, which runs the call.
LINK_ROLES = frozenset({"TER", "INS", "COM", "PRE", "SVC"})


def issue_master_link(call: PortCall, actor: Actor, *, master_name: str, channel: str = "EMAIL", note: str = "",
                      vessel_position: str = "OWN", expires_at=None) -> tuple[MasterAccessLink, str, str]:
    """Return (link, token, code). Token and code are shown once and never stored in clear."""
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("The access link is issued by the agency."))
    if not master_name.strip():
        raise RuleViolation(_("The master's name is required: the signature is nominative."))
    return _issue_link(call, actor, role="NAV", organization=None, holder_name=master_name, channel=channel,
                       note=note, vessel_position=vessel_position, expires_at=expires_at)


def issue_party_link(call: PortCall, actor: Actor, *, party: CallParty, holder_name: str = "", channel: str = "EMAIL",
                     note: str = "", expires_at=None, auto: bool = False) -> tuple[MasterAccessLink, str, str]:
    """Account-less access of a party of the call (terminal, surveyor, owner, provider, marine service), valid
    until the closure of the call. Issued by the agency or the harbour master, or by the platform at the
    declaration for a party that has no account; the holder enters their name at first use when it is not
    known at issuance. Return (link, token, code)."""
    if not auto and "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("The access link of a party is issued by the agency or the harbour master."))
    if party.call_id != call.id or party.revoked_at is not None:
        raise RuleViolation(_("This role is not active on the call."))
    if party.role not in LINK_ROLES:
        raise RuleViolation(_("The role %(role)s decides or runs the call: it needs an account, not a link.")
                            % {"role": role_label(party.role)})
    return _issue_link(call, actor, role=party.role, organization=party.organization, holder_name=holder_name,
                       channel=channel, note=note, expires_at=expires_at, auto=auto)


def _issue_link(call, actor, *, role, organization, holder_name, channel, note, vessel_position="OWN", expires_at=None,
                auto=False):
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    now = timezone.now()
    if role == "NAV":
        limit = now + timedelta(days=call.port.master_link_max_days)
        if expires_at is None:
            expires_at = (call.etd + timedelta(hours=call.port.master_link_grace_hours)) if call.etd else limit
    else:
        limit = now + timedelta(days=call.port.party_link_max_days)
        if expires_at is None:
            expires_at = limit
    expires_at = min(expires_at, limit)
    if expires_at <= now:
        raise RuleViolation(_("The expiry must be in the future."))
    token = secrets.token_urlsafe(32)
    code = _new_code()
    link = MasterAccessLink.objects.create(
        call=call, master_name=holder_name.strip(), role=role, organization=organization, vessel_position=vessel_position,
        token_hash=_token_hash(token), code_hash=_code_hash(code), issued_by=actor.user, delivery_channel=channel,
        delivery_note=note, expires_at=expires_at, auto_issued=auto,
        sent_to=(organization.email if auto and organization is not None and organization.email else ""),
    )
    who = link.master_name or (str(organization) if organization is not None else "")
    acting = "AGE" if "AGE" in actor.roles else ("CAP" if "CAP" in actor.roles else "")
    if role == "NAV":
        summary_fr = f"Accès capitaine remis à {who} ({link.get_delivery_channel_display()}), expire le {expires_at:%d/%m/%Y %H:%M} UTC"
        summary_en = f"Master access issued to {who} ({channel}), expires {expires_at:%Y-%m-%d %H:%M} UTC"
    else:
        how = "émis par la plateforme à la déclaration" if auto else link.get_delivery_channel_display()
        summary_fr = f"Accès par lien {role} remis à {who} ({how}), valable jusqu'à la clôture, au plus tard le {expires_at:%d/%m/%Y} UTC"
        summary_en = f"{role} access link issued to {who} ({'issued by the platform at the declaration' if auto else channel}), valid until closure, at the latest {expires_at:%Y-%m-%d} UTC"
    journal.record(
        port=call.port, call=call, actor=actor, role=acting, action="master_link.issued" if role == "NAV" else "party_link.issued",
        obj=link, visible_roles=["AGE", "CAP"] + ([role] if role != "NAV" else []),
        summary_fr=summary_fr, summary_en=summary_en,
        payload={"channel": channel, "note": note, "expires_at": expires_at, "role": role,
                 "organization": organization.pk if organization is not None else None, "auto": auto},
    )
    return link, token, code


def convene_parties(call: PortCall, actor: Actor, *, parties=None) -> list[MasterAccessLink]:
    """At the declaration (and when a party joins later): every party of the call is told, with its own way in.
    Parties with accounts receive the usual notification; a party organisation without any active account
    holding its role receives an access link by e-mail, valid until the closure of the call."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.urls import reverse

    from apps.core.models import User

    if call.status == CallStatus.DRAFT:
        return []
    issued = []
    candidates = parties if parties is not None else call.parties.filter(revoked_at__isnull=True).select_related("organization")
    for party in candidates:
        if party.role not in LINK_ROLES or party.revoked_at is not None:
            continue
        has_account = User.objects.filter(organization=party.organization, is_active=True,
                                          roles__contains=[party.role]).exists()
        if has_account:
            continue
        if call.master_links.filter(role=party.role, organization=party.organization, revoked_at__isnull=True,
                                    expires_at__gt=timezone.now()).exists():
            continue  # one open link per party and role
        link, token, code = issue_party_link(call, actor, party=party, auto=True)
        issued.append(link)
        if party.organization.email:
            url = f"{settings.SITE_URL}{reverse('registry:master_token', args=[token])}"
            lang = (call.port.default_language or "fr")
            role = role_label(party.role)
            if lang == "en":
                subject = f"[FLUXAA Port] Call {call.reference} — {call.vessel.name}: your access as {role}"
                body = (f"{party.organization.name} takes part in the call {call.reference} ({call.vessel.name}, ETA "
                        f"{call.eta:%Y-%m-%d %H:%M} UTC) of the port of {call.port.name} as {role}.\n\n"
                        f"Open the call, enter your information and consult the file here:\n{url}\n\n"
                        f"Or go to {settings.SITE_URL}{reverse('registry:master_entry')} and enter the code {code}.\n\n"
                        "This access is personal and nominative: you will be asked for your name at first use. It is "
                        "valid until the closure of the call. Do not forward it. If your organisation has an account on "
                        "the platform, sign in with it instead.\n")
            else:
                subject = f"[FLUXAA Port] Escale {call.reference} — {call.vessel.name} : votre accès en tant que {role}"
                body = (f"{party.organization.name} participe à l'escale {call.reference} ({call.vessel.name}, ETA "
                        f"{call.eta:%d/%m/%Y %H:%M} UTC) du port de {call.port.name} en tant que {role}.\n\n"
                        f"Ouvrez l'escale, saisissez vos informations et consultez le dossier ici :\n{url}\n\n"
                        f"Ou rendez-vous sur {settings.SITE_URL}{reverse('registry:master_entry')} et saisissez le code {code}.\n\n"
                        "Cet accès est personnel et nominatif : votre nom vous sera demandé à la première utilisation. Il "
                        "est valable jusqu'à la clôture de l'escale. Ne le transmettez pas. Si votre organisation dispose "
                        "d'un compte sur la plateforme, connectez-vous avec ce compte.\n")
            try:
                send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [party.organization.email], fail_silently=False)
            except Exception as exc:  # pragma: no cover — depends on SMTP
                import logging

                logging.getLogger("fluxaa.notifications").warning("Access link e-mail to %s failed: %s",
                                                                   party.organization.email, exc)
        else:
            journal.record(port=call.port, call=call, actor=actor, action="party_link.unsent", obj=link,
                           visible_roles=["AGE", "CAP"],
                           summary_fr=f"{party.organization} ({party.role}) n'a ni compte ni adresse : l'accès est à remettre par l'agence (onglet Parties)",
                           summary_en=f"{party.organization} ({party.role}) has neither account nor address: the agency hands over the access (Parties tab)")
    return issued


def revoke_master_link(link: MasterAccessLink, actor: Actor, reason: str) -> MasterAccessLink:
    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("Only the agency or the harbour master may revoke this access."))
    if link.revoked_at is not None:
        return link
    link.revoked_at = timezone.now()
    link.revoked_by = actor.user
    link.revoke_reason = reason
    link.save(update_fields=["revoked_at", "revoked_by", "revoke_reason"])
    who = "capitaine" if link.is_master else f"{link.role} {link.organization or ''}".strip()
    journal.record(port=link.call.port, call=link.call, actor=actor,
                   action="master_link.revoked" if link.is_master else "party_link.revoked", obj=link,
                   visible_roles=["AGE", "CAP"] + ([] if link.is_master else [link.role]),
                   summary_fr=f"Accès {who} révoqué — {reason}",
                   summary_en=f"{'Master' if link.is_master else link.role} access revoked — {reason}")
    return link


def authenticate_master(*, token: str | None = None, code: str | None = None, request=None) -> MasterAccessLink | None:
    link = None
    if token:
        link = MasterAccessLink.objects.filter(token_hash=_token_hash(token)).select_related("call", "call__port").first()
    elif code:
        link = MasterAccessLink.objects.filter(code_hash=_code_hash(code)).select_related("call", "call__port").first()
    if link is None:
        return None
    if not link.is_valid():
        journal.audit(port=link.call.port, call=link.call, master=link, action="master.denied",
                      detail="expired or revoked link", request=request)
        return None
    link.last_used_at = timezone.now()
    link.save(update_fields=["last_used_at"])
    journal.audit(port=link.call.port, call=link.call, master=link, action="master.access", request=request)
    return link


def system(call) -> Actor:
    return system_actor(call.port)
