"""Call life cycle (EF-1), template instantiation and relative deadlines (EF-5), roles on call
(EF-12.1) and account-less master access (EF-13)."""
from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta

from django.db import models, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import Berth, Organization
from apps.core.roles import role_label

from ..models import (
    ACTIVE_STATUSES,
    CALL_TRANSITIONS,
    EXPIRABLE_STATUSES,
    OPERATIONAL_CHAIN,
    AlertLevel,
    Authorization,
    CallParty,
    CallSequence,
    CallStage,
    CallStatus,
    CallTemplate,
    CallTemplateUse,
    CargoKind,
    MasterAccessLink,
    PortCall,
    PortDefaultParty,
    StsRole,
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

# Roles the agency may invite on its own call; authorities come from the port's default parties. Since 1.5 the
# principal agent may also nominate another agency on its call (EXG-R-04): a co-agency, with the access it grants.
AGENCY_INVITABLE_ROLES = {"TER", "INS", "COM", "PRE", "SVC", "AGE"}
# The tabs of the call file a partial access may be limited to (CallParty.scopes)
SCOPES = ("apercu", "parties", "taches", "demandes", "jalons", "documents", "mesures", "contestations", "echanges", "journal")
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


def register_organization(actor: Actor, *, name: str, role: str, kind: str = "", email: str = "", phone: str = "") -> Organization:
    """A party the port does not know yet, named by the agency (or the harbour master) when it invites it: the
    list of the parties of a call is open. The organisation is created in the port with the one role it is
    invited for; the port administrator completes or corrects it in the settings. Recorded in the port journal."""
    name = " ".join((name or "").split())
    if len(name) < 2:
        raise RuleViolation(_("Name the organisation you invite."))
    if role not in AGENCY_INVITABLE_ROLES and "CAP" not in actor.roles:
        raise PermissionRefused(_("The agency may invite terminals, surveyors, owners/charterers, providers and marine services only."))
    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("Only the agency or the harbour master invites a new organisation."))
    existing = Organization.objects.filter(port=actor.port, name__iexact=name).first()
    if existing is not None:
        if not existing.is_active:
            raise RuleViolation(_("%(org)s exists but is inactive: ask the port administrator.") % {"org": existing.name})
        if role not in (existing.allowed_roles or []):
            raise RuleViolation(_("%(org)s is registered in the port without the role %(role)s: ask the port administrator.")
                                % {"org": existing.name, "role": role_label(role)})
        return existing
    from apps.core.parties import normalize_kind

    org = Organization(port=actor.port, name=name, kind=normalize_kind(kind), allowed_roles=[role], email=(email or "").strip().lower(),
                       phone=(phone or "").strip()[:40], is_active=True)
    org.full_clean()
    org.save()
    journal.record(
        port=actor.port, actor=actor, action="organization.created", obj=org, object_kind="organization",
        summary_fr=f"Organisation {org.name} enregistrée ({role_label(role)}{', ' + org.kind if org.kind else ''})",
        summary_en=f"Organisation {org.name} registered ({role_label(role)}{', ' + org.kind if org.kind else ''})",
        visible_roles=["CAP", "APO", "DIR", "AGE"], payload={"role": role, "kind": org.kind, "email": org.email},
    )
    return org


def partner_agency(actor: Actor, *, organization: Organization | None = None, name: str = "", email: str = "",
                   phone: str = "") -> Organization | None:
    """The agency of the other vessel of a transfer or of a double banking, when that vessel has no call yet (v1.6):
    a registered agency of the port, or one the port does not know yet — named on the spot like any party of a
    call (``register_organization``, role AGE: the port's administrator completes it and opens its accounts).
    None: the announcing agency itself acts for both vessels."""
    if organization is not None:
        return organization
    if " ".join((name or "").split()):
        return register_organization(actor, name=name, role="AGE", kind="SHIPPING_AGENT", email=email, phone=phone)
    return None


def agency_has_account(agency: Organization) -> bool:
    """Somebody can sign in for this organisation (an active user, not a technical account)."""
    from apps.core.models import User

    return User.objects.filter(organization=agency, is_active=True, is_integration=False).exists()


def _tell_port_of_agency_without_account(partner: PortCall, agency: Organization, user) -> bool:
    """The other vessel's call was created under an agency nobody can sign in for yet (just named, or registered
    without a user): only that agency may declare it, so the port's administrators are told at once."""
    if agency_has_account(agency):
        return False
    from .notifications import notify_port_admins

    notify_port_admins(
        partner.port, key=f"agency_without_account:{agency.pk}:{partner.pk}", url=f"/admin/core/organization/{agency.pk}/change/",
        title_fr=f"{agency.name} n'a pas encore de compte : {user.organization} l'a désignée comme agence de {partner.vessel.name} "
                 f"({partner.reference}) — ouvrez ses comptes, elle seule déclare l'escale de son navire",
        title_en=f"{agency.name} has no account yet: {user.organization} named it as the agency of {partner.vessel.name} "
                 f"({partner.reference}) — open its accounts, it alone declares its vessel's call")
    return True


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
            if tt.cargo_kinds and (call.cargo_kind or "LIQUID") not in tt.cargo_kinds:
                continue  # a line of the common base reserved to a kind of cargo (v1.5)
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
                auto_event=tt.auto_event, continuous=tt.continuous, green_light=tt.green_light,
                not_applicable_allowed=tt.not_applicable_allowed, order=order,
            ))
    created = Task.objects.bulk_create(tasks)
    for task in created:
        task.due_at = compute_due(task, call)
    Task.objects.bulk_update(created, ["due_at"])
    return created


def _check_templates(port, berth_kind: str, operations: list[str], modules: list[str], linked_call,
                     cargo_kind: str = "") -> list[str]:
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
        if cargo_kind and tpl.cargo_kinds and cargo_kind not in tpl.cargo_kinds:
            raise RuleViolation(
                _("Template %(code)s does not apply to this kind of cargo (%(kind)s).") % {"code": code, "kind": CargoKind(cargo_kind).label}
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
    one_way = False
    try:
        partner_role = _role_on_partner(actor, partner)
    except NotVisible:
        # another agency's call the port's board shows: named, never opened — the link stays one-way until the
        # harbour master authorises the STS area or the double banking (v1.6, EXG-R-11)
        if not _on_board(actor, partner):
            raise
        partner_role, one_way = "", True
    ensure_open(partner)
    _check_sts_roles(call.sts_role, partner, link_kind)
    with transaction.atomic():
        call.linked_call = partner
        call.link_kind = link_kind
        fields = ["linked_call", "link_kind", "updated_at"]
        if link_kind == "STS" and not call.sts_role and partner.sts_role:
            call.sts_role = _inverse_sts_role(partner.sts_role)
            fields.append("sts_role")
        call.save(update_fields=fields)
        _journal_link(call, partner, actor, link_kind)
        if partner.linked_call_id is None and not one_way:
            partner.linked_call = call
            partner.link_kind = RECIPROCAL_LINK[link_kind]
            partner.save(update_fields=["linked_call", "link_kind", "updated_at"])
            _journal_link(partner, call, actor, partner.link_kind, role=partner_role if partner_role != "SYS" else "")
    if one_way and actor.user is not None:
        _notify_partner_link(call, partner, actor.user, one_way=True)
    return call


def _inverse_sts_role(role: str) -> str:
    return StsRole.RECEIVER if role == StsRole.DONOR else StsRole.DONOR


def _check_sts_roles(sts_role: str, partner: PortCall, link_kind: str) -> None:
    """In a transfer one vessel delivers and the other receives: two calls of the same side are not partners."""
    if (link_kind or "STS") == "STS" and sts_role and partner.sts_role and sts_role == partner.sts_role:
        raise RuleViolation(_("One vessel delivers the cargo and the other receives it."))


def link_confirmed(call: PortCall) -> bool:
    """Whether the link of *call* to its partner stands for both files: the two calls belong to the same agency,
    or the partner points back, or the harbour master authorised the configuration (the STS area and window, the
    double banking). Until then a call of another agency is only *named*: nothing of its file is read through
    the link — a mother vessel may be named by several daughter vessels of different agencies (v1.6)."""
    partner = call.linked_call
    if partner is None:
        return False
    if partner.agency_id == call.agency_id or partner.linked_call_id == call.pk:
        return True
    code = "DOUBLE_BANKING" if call.link_kind in ("OUTER", "INNER") else "STS_ZONE"
    return call.requests.filter(type__code=code, status__in=["APPROVED", "APPROVED_WITH_CONDITIONS"]).exists()


def incoming_links(call: PortCall, actor: Actor | None = None) -> list[PortCall]:
    """The other calls that name this one as their partner — the daughter vessels of a mother vessel, the vessels
    announced alongside a vessel at the berth. A draft of another agency is its agency's own: it is not shown."""
    rows = (PortCall.objects.filter(linked_call=call).exclude(pk=call.linked_call_id or 0)
            .exclude(status__in=[CallStatus.CANCELLED, CallStatus.REJECTED, CallStatus.EXPIRED])
            .select_related("vessel", "agency").order_by("eta", "pk"))
    org_id = actor.org.pk if actor is not None and actor.org is not None else None
    return [c for c in rows if c.status != CallStatus.DRAFT or c.agency_id == org_id]


def validity_for(port, validity_days) -> int:
    """The validity of an announcement, in days: the agency's choice within the port's ceiling, the port's
    default otherwise (EXG-R-02)."""
    if validity_days in (None, ""):
        return port.default_validity_days
    try:
        days = int(validity_days)
    except (TypeError, ValueError):
        raise RuleViolation(_("The validity of the announcement is a number of days.")) from None
    if days < 1 or days > port.max_validity_days:
        raise RuleViolation(_("The validity of the announcement is between 1 and %(max)d days for this port.")
                            % {"max": port.max_validity_days})
    return days


@transaction.atomic
def create_call(user, *, vessel: Vessel, eta, requested_berth_kind: str, operations: list[str],
                modules: list[str] | None = None, requested_berth: Berth | None = None, etb=None, ets=None, etc=None,
                etd=None, product: str = "", quantity=None, quantity_unit: str = "MT", voyage_number: str = "",
                last_port: str = "", next_port: str = "", parties: list[tuple] | None = None,
                linked_call: PortCall | None = None, link_kind: str = "", planned_pump_hours=None,
                batch_reference: str = "", cargo_kind: str = "LIQUID", validity_days=None, sts_role: str = "",
                sts_partner: dict | None = None, expected_documents: list[str] | None = None,
                custom_documents: list[dict] | None = None, renewed_from: PortCall | None = None,
                operation_details: dict | None = None, db_partner: dict | None = None) -> PortCall:
    """Only the agency creates a call (EF-1.1). Tasks of M0 + operations + modules are instantiated.

    Since 1.5: the kind of cargo chooses the operation models and the safety checklist (EXG-R-08); the
    announcement is valid for a period kept for billing (EXG-R-02); *parties* may carry the access each one gets
    — ``(organisation, role)`` or ``(organisation, role, access, scopes)`` (EXG-R-04); an STS transfer creates the
    partner vessel's own call at once, with its own agency and team (EXG-R-05: ``sts_partner`` = {"vessel", "agency",
    "role"}); the documents expected beyond the templates are asked for at the announcement (EXG-R-06).

    Since 1.6 (EXG-R-11): ``operation_details`` keeps the answers to each model's own questions; a double banking
    names the other vessel at the announcement (``db_partner`` = {"call"} — a call of any agency, visible on the
    port's board —, or {"vessel", "agency"} for a vessel without a call yet, whose call is created under its own
    agency — and "position": OUTER (this vessel comes alongside the other) or INNER (this vessel is at the berth)).
    A link to another agency's call stays one-way until the harbour master authorises the double banking, or links
    the calls himself; that agency and the harbour master are told at once."""
    actor = port_actor(user)
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("Only a shipping agency can create a call."))
    port = actor.port
    cargo_kind = cargo_kind or CargoKind.LIQUID
    if cargo_kind not in CargoKind.values:
        raise RuleViolation(_("Unknown kind of cargo."))
    if sts_role and sts_role not in StsRole.values:
        raise RuleViolation(_("Unknown role in the STS transfer."))
    days = validity_for(port, validity_days)
    linked_role = ""
    one_way = False
    db_partner = dict(db_partner or {})
    if db_partner.get("position") not in (None, "", "OUTER", "INNER"):
        raise RuleViolation(_("In a double banking this vessel is either outside or inside."))
    if db_partner.get("call") is not None:
        if linked_call is not None and linked_call.pk != db_partner["call"].pk:
            raise RuleViolation(_("One partner call at a time: the STS partner or the double-banking partner."))
        linked_call, link_kind = db_partner["call"], db_partner.get("position") or "OUTER"
    if linked_call is not None:
        if linked_call.port_id != port.id:
            raise RuleViolation(_("The partner call belongs to another port."))
        try:
            linked_role = _role_on_partner(actor, linked_call)
        except NotVisible:
            if _on_board(actor, linked_call):
                # another agency's vessel — at the berth (double banking) or at the STS area (the mother vessel
                # several daughter vessels come to): named from the port's board, the link waits for the harbour master
                one_way = True
            else:
                raise RuleViolation(_("Partner call not found among your calls nor on the port's placement conference: "
                                      "the harbour master links the calls of two different agencies.")) from None
        link_kind = link_kind or "STS"
        _check_sts_roles(sts_role, linked_call, link_kind)
        if link_kind == "STS" and not sts_role and linked_call.sts_role:
            sts_role = _inverse_sts_role(linked_call.sts_role)  # the other side of the transfer
    call = _build_call(
        port, user, actor, agency=user.organization, vessel=vessel, eta=eta, requested_berth_kind=requested_berth_kind,
        operations=list(operations), modules=list(modules or []), requested_berth=requested_berth, etb=etb, ets=ets,
        etc=etc, etd=etd, product=product, quantity=quantity, quantity_unit=quantity_unit, voyage_number=voyage_number,
        last_port=last_port, next_port=next_port, parties=parties, linked_call=linked_call, link_kind=link_kind,
        planned_pump_hours=planned_pump_hours, batch_reference=batch_reference, cargo_kind=cargo_kind,
        validity_days=days, sts_role=sts_role, renewed_from=renewed_from, operation_details=operation_details,
    )
    if linked_call is not None and linked_call.linked_call_id is None and not one_way:
        linked_call.linked_call = call
        linked_call.link_kind = RECIPROCAL_LINK.get(link_kind or "STS", "STS")
        linked_call.save(update_fields=["linked_call", "link_kind", "updated_at"])
        _journal_link(linked_call, call, actor, linked_call.link_kind, role=linked_role)
    if linked_call is not None and (link_kind in ("OUTER", "INNER") or one_way):
        _notify_partner_link(call, linked_call, user, one_way=one_way)
    if sts_partner and sts_partner.get("vessel") is not None:
        _create_sts_partner(call, user, actor, **sts_partner)
    if db_partner.get("vessel") is not None and db_partner.get("call") is None:
        _create_db_partner(call, user, actor, vessel=db_partner["vessel"], agency=db_partner.get("agency"),
                           position=db_partner.get("position") or "OUTER")
    if expected_documents or custom_documents:
        from .tasks import request_documents

        request_documents(call, actor, document_types=list(expected_documents or []), custom=list(custom_documents or []))
    _complete_auto(call, "call.created", actor)
    # what the declaration waits for, told to the agency at once (its other people too): the vessel dataset, the
    # master's certificates — which the agency may file for him —, the sanctions screening (EXG-Q-09)
    pending = [t for t in call.tasks.filter(status=TaskStatus.PENDING, template_code="M0")
               if (t.template_code, t.number) in {("M0", "02"), ("M0", "03"), ("M0", "05")}]
    if pending:
        notify(call, ["AGE"], key=f"draft:{call.pk}", exclude_user=user, url=call_url(call),
               title_fr=f"{call.reference} créée en brouillon — avant de déclarer : " + ", ".join(f"{t.code} {t.title_fr}" for t in pending),
               title_en=f"{call.reference} created as a draft — before declaring: " + ", ".join(f"{t.code} {t.title_en}" for t in pending))
    return call


def _build_call(port, user, actor: Actor, *, agency: Organization, vessel: Vessel, eta, requested_berth_kind: str,
                operations: list[str], modules: list[str], requested_berth, etb, ets, etc, etd, product, quantity,
                quantity_unit, voyage_number, last_port, next_port, parties, linked_call, link_kind,
                planned_pump_hours, batch_reference, cargo_kind, validity_days: int, sts_role: str,
                renewed_from=None, co_agency: Organization | None = None, operation_details: dict | None = None) -> PortCall:
    """The record of a call and everything instantiated with it: stage, roles, tasks, journal."""
    if vessel.port_id != port.id:
        raise RuleViolation(_("This vessel is not registered in this port."))
    if requested_berth is not None and (requested_berth.port_id != port.id or requested_berth.kind != requested_berth_kind):
        raise RuleViolation(_("The requested berth does not match the operating area."))
    for auto_code, kinds in (("MA2", {Berth.Kind.SPM}), ("MA3", {Berth.Kind.ANCHORAGE, Berth.Kind.STS_AREA})):
        if requested_berth_kind in kinds and auto_code not in modules and CallTemplate.objects.filter(
            port=port, code=auto_code, is_active=True
        ).exists():
            modules.append(auto_code)  # SPM module / anchorage stay apply by nature of the area
    codes = _check_templates(port, requested_berth_kind, list(operations), modules, linked_call, cargo_kind)
    versions = _published_versions(port, codes)

    now = timezone.now()
    year = now.year
    reference = f"{port.code}-{year}-{next_number(port, 'CALL', year):04d}"
    call = PortCall.objects.create(
        port=port, reference=reference, vessel=vessel, voyage_number=voyage_number, agency=agency,
        requested_berth_kind=requested_berth_kind, requested_berth=requested_berth, product=product,
        quantity=quantity, quantity_unit=quantity_unit, last_port=last_port, next_port=next_port, eta=eta, etb=etb,
        ets=ets, etc=etc, etd=etd, linked_call=linked_call, link_kind=link_kind, created_by=user,
        planned_pump_hours=planned_pump_hours or None, batch_reference=(batch_reference or "")[:60],
        cargo_kind=cargo_kind, validity_days=validity_days, valid_until=now + timedelta(days=validity_days),
        sts_role=sts_role, renewed_from=renewed_from, operation_details=dict(operation_details or {}),
    )
    for version in versions:
        CallTemplateUse.objects.create(call=call, template_version=version)
    CallStage.objects.create(call=call, order=1, berth_kind=requested_berth_kind, operations=codes[1:], planned_from=etb,
                             planned_to=etd, status=CallStage.Status.CURRENT, created_by=user)

    # Roles on the call: the principal agency, the port's default parties, then the parties named by the agency
    CallParty.objects.create(call=call, organization=agency, role="AGE", granted_by=user)
    if co_agency is not None and co_agency.pk != agency.pk:
        CallParty.objects.create(call=call, organization=co_agency, role="AGE", granted_by=user,
                                 access_set_by=user, access_set_at=now)
    for default in PortDefaultParty.objects.filter(port=port).select_related("organization"):
        if default.organization.is_active:
            CallParty.objects.get_or_create(
                call=call, organization=default.organization, role=default.role, revoked_at=None,
                defaults={"granted_by": user, "is_default": True},
            )
    for row in parties or []:
        org, role = row[0], row[1]
        access = row[2] if len(row) > 2 and row[2] else CallParty.Access.FULL
        scopes = list(row[3]) if len(row) > 3 and row[3] else []
        _grant(call, actor, org, role, user, access=access, scopes=scopes)

    instantiate_tasks(call, versions)
    journal.record(
        port=port, call=call, actor=actor, role="AGE", action="call.created", obj=call,
        summary_fr=f"Escale {reference} créée pour {vessel.name} — modèles {', '.join(codes)} — {CargoKind(cargo_kind).label} — "
                   f"annonce valable {validity_days} j (jusqu'au {call.valid_until:%d/%m/%Y %H:%M} UTC)",
        summary_en=f"Call {reference} created for {vessel.name} — templates {', '.join(codes)} — {cargo_kind} — "
                   f"announcement valid {validity_days} d (until {call.valid_until:%Y-%m-%d %H:%M} UTC)",
        payload={"templates": {v.template.code: v.number for v in versions}, "eta": eta, "berth_kind": requested_berth_kind,
                 "cargo_kind": cargo_kind, "validity_days": validity_days, "valid_until": call.valid_until,
                 "operation_details": dict(operation_details or {}),
                 "sts_role": sts_role, "renewed_from": renewed_from.reference if renewed_from else None},
    )
    return call


def _create_sts_partner(call: PortCall, user, actor: Actor, *, vessel: Vessel, agency: Organization | None = None,
                        role: str = "") -> PortCall:
    """The partner vessel of an STS transfer gets its own call at once (EXG-R-05): the other side of the transfer,
    its own agency when one is named — the principal agent keeps a co-agency access on it — and its own team."""
    partner_role = role or (StsRole.RECEIVER if call.sts_role == StsRole.DONOR else StsRole.DONOR)
    if call.sts_role and partner_role == call.sts_role:
        raise RuleViolation(_("One vessel delivers the cargo and the other receives it."))
    partner_agency = agency or user.organization
    if partner_agency.port_id != call.port_id or "AGE" not in (partner_agency.allowed_roles or []):
        raise RuleViolation(_("The partner vessel's agency must be an agency of this port."))
    if vessel.pk == call.vessel_id:
        raise RuleViolation(_("The partner vessel is another vessel."))
    stage = call.stages.filter(status="CURRENT").first()
    operations = [c for c in (stage.operations if stage else call.template_codes) if c != "M0"]
    partner = _build_call(
        call.port, user, actor, agency=partner_agency, vessel=vessel, eta=call.eta, requested_berth_kind=call.requested_berth_kind,
        operations=[c for c in operations if CallTemplate.objects.filter(port=call.port, code=c, kind=TemplateKind.OPERATION).exists()],
        modules=[c for c in operations if CallTemplate.objects.filter(port=call.port, code=c, kind=TemplateKind.MODULE).exists()],
        requested_berth=call.requested_berth, etb=call.etb, ets=call.ets, etc=call.etc, etd=call.etd, product=call.product,
        quantity=call.quantity, quantity_unit=call.quantity_unit, voyage_number="", last_port="", next_port="",
        parties=None, linked_call=call, link_kind="STS", planned_pump_hours=call.planned_pump_hours,
        batch_reference=call.batch_reference, cargo_kind=call.cargo_kind, validity_days=call.validity_days,
        sts_role=partner_role, co_agency=user.organization if partner_agency.pk != user.organization_id else None,
        operation_details={"M3": dict((call.operation_details or {}).get("M3", {}))} if (call.operation_details or {}).get("M3") else None,
    )
    if not call.sts_role:
        call.sts_role = StsRole.DONOR if partner_role == StsRole.RECEIVER else StsRole.RECEIVER
    call.linked_call = partner
    call.link_kind = "STS"
    call.save(update_fields=["linked_call", "link_kind", "sts_role", "updated_at"])
    _journal_link(call, partner, actor, "STS", role="AGE")
    _journal_link(partner, call, actor, "STS", role="AGE")
    if partner_agency.pk != user.organization_id:
        notify(partner, ["AGE"], key=f"sts:{partner.pk}:nominated", organizations=[partner_agency.pk], realtime=True,
               url=call_url(partner), exclude_user=user,
               title_fr=f"{partner.reference} : escale créée pour {vessel.name} — navire {StsRole(partner_role).label} du transfert STS avec {call.vessel.name} ({call.reference}), annoncée par {user.organization}",
               title_en=f"{partner.reference}: call created for {vessel.name} — {partner_role} vessel of the STS transfer with {call.vessel.name} ({call.reference}), announced by {user.organization}")
        _tell_port_of_agency_without_account(partner, partner_agency, user)
    return partner


def _on_board(actor: Actor, partner: PortCall) -> bool:
    """A call of another agency may be named as the vessel at the berth when this agency sees it on the port's
    board (the placement conference): declared or further, not finished, at a berth or planned there."""
    from .rights import can_read_report

    return (partner.status in ACTIVE_STATUSES and not partner.is_terminal_state and partner.status != CallStatus.DRAFT
            and can_read_report(actor, "CALL_BOARD"))


def _notify_partner_link(call: PortCall, partner: PortCall, user, *, one_way: bool) -> None:
    """The other vessel's agency, its master and the harbour master learn at once that a vessel names theirs as its
    partner: for a double banking the inner vessel's express consent is never presumed (M9:9.02); for a
    ship-to-ship transfer the area and the window are the harbour master's to authorise (M3:3.03)."""
    if call.link_kind not in ("OUTER", "INNER"):
        role_fr = f" ({StsRole(call.sts_role).label})" if call.sts_role else ""
        tail_fr = (" — le lien entre les deux escales attend l'autorisation de zone et de fenêtre STS de la capitainerie"
                   if one_way else " — les deux escales sont liées")
        tail_en = (" — the link between the two calls waits for the harbour master's STS area and window authorization"
                   if one_way else " — the two calls are linked")
        notify(partner, ["AGE", "CAP", "NAV"], key=f"sts_link:{call.pk}:{partner.pk}", realtime=True, url=call_url(partner),
               exclude_user=user,
               title_fr=f"{call.vessel.name} ({call.reference}, {call.agency}){role_fr} annonce un transbordement navire-navire avec "
                        f"{partner.vessel.name} ({partner.reference})" + tail_fr,
               title_en=f"{call.vessel.name} ({call.reference}, {call.agency}) announces a ship-to-ship transfer with "
                        f"{partner.vessel.name} ({partner.reference})" + tail_en)
        return
    this_outside = call.link_kind == "OUTER"
    what_fr = (f"{call.vessel.name} ({call.reference}) annonce un accostage à couple de {partner.vessel.name} ({partner.reference})"
               if this_outside else
               f"{call.vessel.name} ({call.reference}) annonce qu'elle recevra {partner.vessel.name} ({partner.reference}) à couple")
    what_en = (f"{call.vessel.name} ({call.reference}) announces a double banking alongside {partner.vessel.name} ({partner.reference})"
               if this_outside else
               f"{call.vessel.name} ({call.reference}) announces that {partner.vessel.name} ({partner.reference}) will berth alongside")
    tail_fr = (" — le lien entre les deux escales attend l'autorisation d'accostage à couple de la capitainerie ; l'accord exprès du navire intérieur est requis"
               if one_way else " — les deux escales sont liées ; l'accord exprès du navire intérieur est requis")
    tail_en = (" — the link between the two calls waits for the harbour master's double-banking authorization; the inner vessel's express consent is required"
               if one_way else " — the two calls are linked; the inner vessel's express consent is required")
    notify(partner, ["AGE", "CAP", "NAV"], key=f"double_banking:{call.pk}:{partner.pk}", realtime=True, url=call_url(partner),
           exclude_user=user, title_fr=what_fr + tail_fr, title_en=what_en + tail_en)


def _create_db_partner(call: PortCall, user, actor: Actor, *, vessel: Vessel, agency: Organization | None, position: str) -> PortCall:
    """The other vessel of a double banking has no call yet: it gets its own, under its own agency when one is
    named — the announcing agency keeps a co-agency access on it —, with the same operations and the double-banking
    module, linked both ways."""
    partner_agency = agency or user.organization
    if partner_agency.port_id != call.port_id or "AGE" not in (partner_agency.allowed_roles or []):
        raise RuleViolation(_("The partner vessel's agency must be an agency of this port."))
    if vessel.pk == call.vessel_id:
        raise RuleViolation(_("The partner vessel is another vessel."))
    stage = call.stages.filter(status="CURRENT").first()
    codes = [c for c in (stage.operations if stage else call.template_codes) if c != "M0"]
    kinds = {t.code: t.kind for t in CallTemplate.objects.filter(port=call.port, code__in=codes)}
    modules = [c for c in codes if kinds.get(c) == TemplateKind.MODULE]
    if "M9" not in modules and CallTemplate.objects.filter(port=call.port, code="M9", is_active=True).exists():
        modules.append("M9")
    link_kind = RECIPROCAL_LINK[position]
    partner = _build_call(
        call.port, user, actor, agency=partner_agency, vessel=vessel, eta=call.eta, requested_berth_kind=call.requested_berth_kind,
        operations=[c for c in codes if kinds.get(c) == TemplateKind.OPERATION], modules=modules,
        requested_berth=call.requested_berth, etb=call.etb, ets=call.ets, etc=call.etc, etd=call.etd, product="",
        quantity=None, quantity_unit=call.quantity_unit, voyage_number="", last_port="", next_port="", parties=None,
        linked_call=call, link_kind=link_kind, planned_pump_hours=None, batch_reference="", cargo_kind=call.cargo_kind,
        validity_days=call.validity_days, sts_role="", co_agency=user.organization if partner_agency.pk != user.organization_id else None,
        operation_details={"M9": dict((call.operation_details or {}).get("M9", {}))},
    )
    call.linked_call = partner
    call.link_kind = position
    call.save(update_fields=["linked_call", "link_kind", "updated_at"])
    _journal_link(call, partner, actor, position, role="AGE")
    _journal_link(partner, call, actor, link_kind, role="AGE")
    if partner_agency.pk != user.organization_id:
        notify(partner, ["AGE"], key=f"double_banking:{partner.pk}:nominated", organizations=[partner_agency.pk], realtime=True,
               url=call_url(partner), exclude_user=user,
               title_fr=f"{partner.reference} : escale créée pour {vessel.name} — accostage à couple avec {call.vessel.name} ({call.reference}), annoncé par {user.organization}",
               title_en=f"{partner.reference}: call created for {vessel.name} — double banking with {call.vessel.name} ({call.reference}), announced by {user.organization}")
        _tell_port_of_agency_without_account(partner, partner_agency, user)
    return partner


def complete_reciprocal_link(call: PortCall, actor: Actor) -> bool:
    """A one-way link (another agency's vessel named at the announcement) becomes reciprocal once the harbour
    master authorises the double banking: both files then show each other."""
    partner = call.linked_call
    if partner is None or partner.linked_call_id is not None or call.link_kind not in RECIPROCAL_LINK:
        return False
    partner.linked_call = call
    partner.link_kind = RECIPROCAL_LINK[call.link_kind]
    fields = ["linked_call", "link_kind", "updated_at"]
    if call.link_kind == "STS" and call.sts_role and not partner.sts_role:
        partner.sts_role = _inverse_sts_role(call.sts_role)
        fields.append("sts_role")
    partner.save(update_fields=fields)
    _journal_link(partner, call, actor, partner.link_kind, role="CAP" if actor.has("CAP") else "")
    return True


def berth_occupation(port, berth, start, end, *, exclude=None) -> list[PortCall]:
    """The calls that hold or expect the same berth over the window: what the announcing agency should know before
    asking for it — the port's placement conference, berth by berth."""
    if berth is None or start is None:
        return []
    end = end or (start + timedelta(hours=36))
    calls = PortCall.objects.filter(port=port, status__in=ACTIVE_STATUSES).filter(
        models.Q(berth=berth) | models.Q(requested_berth=berth)).select_related("vessel", "agency")
    if exclude is not None:
        calls = calls.exclude(pk=exclude.pk)
    rows = []
    for other in calls:
        other_start = other.atb or other.etb or other.eta
        other_end = other.atd or other.etd or (other_start + timedelta(hours=36) if other_start else None)
        if other_start is None:
            continue
        if other_start < end and (other_end is None or other_end > start):
            rows.append(other)
    return rows


def renew_call(call: PortCall, actor: Actor) -> PortCall:
    """An obsolete (or cancelled) announcement is made again (EXG-R-02): a new draft call with the same vessel,
    operations, cargo and parties, a new validity, and a link to the announcement it renews."""
    from .rights import is_principal_agent

    if "AGE" not in actor.roles or actor.user is None or not is_principal_agent(actor, call):
        raise PermissionRefused(_("The principal agent announces the call again."))
    if call.status not in (CallStatus.EXPIRED, CallStatus.CANCELLED, CallStatus.REJECTED):
        raise RuleViolation(_("Only an obsolete, cancelled or rejected announcement is made again."))
    if call.renewals.exclude(status__in=[CallStatus.CANCELLED, CallStatus.EXPIRED, CallStatus.REJECTED]).exists():
        raise RuleViolation(_("This announcement has already been made again."))
    stage = call.stages.order_by("order").first()
    operations = [c for c in (stage.operations if stage else call.template_codes) if c != "M0"]
    kinds = {t.code: t.kind for t in CallTemplate.objects.filter(port=call.port, code__in=operations)}
    parties = [(p.organization, p.role, p.access, p.scopes) for p in call.parties.filter(revoked_at__isnull=True, is_default=False)
               .exclude(organization=call.agency, role="AGE").select_related("organization")]
    now = timezone.now()
    new = create_call(
        actor.user, vessel=call.vessel, eta=call.eta if call.eta > now else now + timedelta(days=1),
        requested_berth_kind=call.requested_berth_kind, operations=[c for c in operations if kinds.get(c) == TemplateKind.OPERATION],
        modules=[c for c in operations if kinds.get(c) == TemplateKind.MODULE and c not in ("MA2", "MA3")],
        requested_berth=call.requested_berth, etb=call.etb, ets=call.ets, etc=call.etc, etd=call.etd,
        product=call.product, quantity=call.quantity, quantity_unit=call.quantity_unit, voyage_number=call.voyage_number,
        last_port=call.last_port, next_port=call.next_port, parties=parties, planned_pump_hours=call.planned_pump_hours,
        batch_reference=call.batch_reference, cargo_kind=call.cargo_kind, validity_days=call.validity_days,
        sts_role=call.sts_role, renewed_from=call, operation_details=dict(call.operation_details or {}),
    )
    journal.record(port=call.port, call=call, actor=actor, role="AGE", action="call.renewed", obj=call,
                   summary_fr=f"Annonce refaite : nouvelle escale {new.reference}", summary_en=f"Announced again: new call {new.reference}",
                   payload={"new_call": new.reference})
    return new


def expire_call(call: PortCall, actor: Actor | None = None) -> bool:
    """The announcement's validity ran out before the vessel was alongside: the call is obsolete (EXG-R-02). The
    agency, the harbour master and the port authority are told at once; the agency announces the call again."""
    if call.status not in EXPIRABLE_STATUSES or call.valid_until is None or call.valid_until > timezone.now():
        return False
    actor = actor or system(call)
    with transaction.atomic():
        call.expired_at = timezone.now()
        call.save(update_fields=["expired_at", "updated_at"])
        _set_status(call, CallStatus.EXPIRED, actor,
                    reason=f"validité de l'annonce échue le {call.valid_until:%d/%m/%Y %H:%M} UTC ({call.validity_days} j)")
    notify(call, ["AGE", "CAP", "APO"], key=f"expired:{call.pk}", realtime=True, url=call_url(call),
           title_fr=f"{call.reference} ({call.vessel.name}) : annonce obsolète — validité de {call.validity_days} j échue le "
                    f"{call.valid_until:%d/%m %H:%M} UTC ; l'agence doit refaire l'annonce",
           title_en=f"{call.reference} ({call.vessel.name}): announcement obsolete — the {call.validity_days}-day validity ran out on "
                    f"{call.valid_until:%Y-%m-%d %H:%M} UTC; the agency must announce the call again")
    return True


def _complete_auto(call, event: str, actor: Actor) -> None:
    from .tasks import system_complete

    for task in call.tasks.filter(auto_event=event, status=TaskStatus.PENDING):
        system_complete(task, actor, evidence=f"call:{call.pk}", note=event)


# ============================================================================ roles on call
def _check_scopes(access: str, scopes) -> list[str]:
    if access not in CallParty.Access.values:
        raise RuleViolation(_("Unknown access."))
    scopes = [str(code) for code in (scopes or []) if str(code) in SCOPES]
    if access == CallParty.Access.PARTIAL and not scopes:
        raise RuleViolation(_("A partial access names at least one tab of the file."))
    return scopes if access == CallParty.Access.PARTIAL else []


def _grant(call, actor: Actor, org: Organization, role: str, user=None, *, access: str = "FULL", scopes=None) -> CallParty:
    if org.port_id != call.port_id or not org.is_active:
        raise RuleViolation(_("This organisation is not active in this port."))
    if role not in (org.allowed_roles or []):
        raise RuleViolation(
            _("%(org)s cannot hold the role %(role)s.") % {"org": org, "role": role_label(role)}
        )
    if not actor.is_system and "CAP" not in actor.roles:
        if "AGE" not in actor.roles or role not in AGENCY_INVITABLE_ROLES:
            raise PermissionRefused(_("The agency may invite terminals, surveyors, owners/charterers, providers, marine services and co-agencies only."))
    if role == "AGE" and org.pk == call.agency_id:
        raise RuleViolation(_("This agency is the principal agent of the call."))
    scopes = _check_scopes(access, scopes)
    party, created = CallParty.objects.get_or_create(
        call=call, organization=org, role=role, revoked_at=None,
        defaults={"granted_by": user, "access": access, "scopes": scopes,
                  "access_set_by": user if access != CallParty.Access.FULL else None,
                  "access_set_at": timezone.now() if access != CallParty.Access.FULL else None},
    )
    return party


def set_party_access(call, actor: Actor, party: CallParty, access: str, scopes=None) -> CallParty:
    """The principal agent (or the harbour master) gives a party all or part of the file (EXG-R-04): every tab,
    the tabs listed, or reading only. The port's own parties and the principal agent keep their full access."""
    ensure_open(call)
    if actor.user is None:
        raise PermissionRefused(_("The principal agent or the harbour master sets the access of a party."))
    principal = actor.has("AGE") and actor.org is not None and actor.org.pk == call.agency_id
    if not principal and not actor.has("CAP"):
        raise PermissionRefused(_("The principal agent or the harbour master sets the access of a party."))
    if party.call_id != call.pk or party.revoked_at is not None:
        raise RuleViolation(_("This role is not active on the call."))
    if party.is_principal or party.is_default:
        raise RuleViolation(_("The principal agent and the port's own parties keep their full access."))
    scopes = _check_scopes(access, scopes)
    party.access = access
    party.scopes = scopes
    party.access_set_by = actor.user
    party.access_set_at = timezone.now()
    party.save(update_fields=["access", "scopes", "access_set_by", "access_set_at"])
    label = CallParty.Access(access).label
    journal.record(port=call.port, call=call, actor=actor, action="party.access", obj=party,
                   summary_fr=f"Accès de {party.organization} ({party.role}) : {label}" + (f" — {', '.join(scopes)}" if scopes else ""),
                   summary_en=f"Access of {party.organization} ({party.role}): {label}" + (f" — {', '.join(scopes)}" if scopes else ""),
                   payload={"access": access, "scopes": scopes, "organization": party.organization_id, "role": party.role})
    notify(call, [party.role], key=f"party:{party.pk}:access:{timezone.now():%Y%m%d%H%M}", organizations=[party.organization_id],
           url=call_url(call), exclude_user=actor.user,
           title_fr=f"{call.reference} : votre accès au dossier — {label}" + (f" ({', '.join(scopes)})" if scopes else ""),
           title_en=f"{call.reference}: your access to the file — {label}" + (f" ({', '.join(scopes)})" if scopes else ""))
    return party


def add_party(call, actor: Actor, org: Organization, role: str, valid_until=None, *, access: str = "FULL", scopes=None) -> CallParty:
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    party = _grant(call, actor, org, role, actor.user, access=access, scopes=scopes)
    if valid_until:
        party.valid_until = valid_until
        party.save(update_fields=["valid_until"])
    access_fr = "" if party.access == CallParty.Access.FULL else f" — accès {CallParty.Access(party.access).label}" + (f" ({', '.join(party.scopes)})" if party.scopes else "")
    journal.record(
        port=call.port, call=call, actor=actor, action="party.granted", obj=party,
        summary_fr=f"Rôle {role} accordé à {org}{access_fr}", summary_en=f"Role {role} granted to {org}{access_fr}",
        payload={"organization": org.pk, "role": role, "valid_until": valid_until, "access": party.access, "scopes": party.scopes},
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
    if target == CallStatus.EXPIRED and call.expired_at is None:
        call.expired_at = timezone.now()
        fields.append("expired_at")
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
    from .rights import is_principal_agent

    if "AGE" not in actor.roles or not is_principal_agent(actor, call):
        raise PermissionRefused(_("Only the principal agent declares the call."))
    if call.status != CallStatus.DRAFT:
        raise RuleViolation(_("Only a draft call can be declared."))

    if call.linked_call_id is None and _requires_link(call) and not PortCall.objects.filter(linked_call=call).exclude(
            status__in=[CallStatus.DRAFT, CallStatus.CANCELLED, CallStatus.REJECTED, CallStatus.EXPIRED]).exists():
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
    from .rights import is_principal_agent

    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    changes = {}
    berth_assigned = Authorization.objects.filter(call=call, type_code="BERTH").exists()
    for field, value in values.items():
        if field not in ESTIMATE_FIELDS or value is None:
            continue
        owner = "APO" if field == "etb" and berth_assigned else "AGE"
        if owner not in actor.roles or (owner == "AGE" and not is_principal_agent(actor, call)):
            raise PermissionRefused(
                _("%(field)s is entered by %(role)s only (single emitter).") % {"field": field.upper(), "role": role_label(owner) if owner != "AGE" else _("the principal agent")}
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
    from .rights import is_principal_agent

    if "AGE" not in actor.roles or not is_principal_agent(actor, call):
        raise PermissionRefused(_("Only the principal agent can cancel its call."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    with transaction.atomic():
        _set_status(call, CallStatus.CANCELLED, actor, reason=reason)
    notify(call, ["*"], key=f"cancelled:{call.pk}", title_fr=f"Escale {call.reference} annulée — {reason}",
           title_en=f"Call {call.reference} cancelled — {reason}", url=call_url(call), realtime=True)
    return call


def confirm_closure(call: PortCall, actor: Actor) -> None:
    """Task 39, agency side: the agency confirms the file is complete (C)."""
    from .rights import is_principal_agent
    from .tasks import sign_task

    if "AGE" not in actor.roles or not is_principal_agent(actor, call):
        raise PermissionRefused(_("Only the principal agent confirms the closure request."))
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
                      vessel_position: str = "OWN", expires_at=None, send_to: str = "") -> tuple[MasterAccessLink, str, str]:
    """Return (link, token, code). Token and code are shown once and never stored in clear. With *send_to*, the
    platform e-mails the access to the master with the list of what the port expects from him (EXG-Q-09)."""
    if "AGE" not in actor.roles:
        raise PermissionRefused(_("The access link is issued by the agency."))
    if not master_name.strip():
        raise RuleViolation(_("The master's name is required: the signature is nominative."))
    send_to = (send_to or "").strip()
    link, token, code = _issue_link(call, actor, role="NAV", organization=None, holder_name=master_name, channel=channel,
                                    note=note, vessel_position=vessel_position, expires_at=expires_at, send_to=send_to)
    if send_to:
        from .preparation import access_mail

        if access_mail(call, link, token, code, send_to):
            journal.record(port=call.port, call=call, actor=actor, role="AGE", action="master_link.sent", obj=link,
                           visible_roles=["AGE", "CAP"],
                           summary_fr=f"Accès capitaine envoyé par courriel à {send_to} avec la liste des éléments attendus du navire",
                           summary_en=f"Master access e-mailed to {send_to} with the list of what is expected from the vessel")
    return link, token, code


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
                auto=False, send_to=""):
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
        sent_to=send_to or (organization.email if auto and organization is not None and organization.email else ""),
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
