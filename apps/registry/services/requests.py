"""Requests and authorizations — one engine for every type (EF-2).

Cycle: Created → Submitted → Under review → Approved | Approved with conditions | Refused |
Information required → Scheduled → Executed → Closed, plus Cancelled and Expired.
Rule 2: the requesting role never approves, even inside the same organisation.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.models import pick
from apps.core.numbers import parse_decimal
from apps.core.roles import role_label

from ..models import (
    CALL_TRANSITIONS,
    REQUEST_TRANSITIONS,
    Alert,
    AlertKind,
    Authorization,
    AuthorizationEvent,
    Confidentiality,
    MilestoneType,
    RequestStatus,
    RequestType,
    ServiceRequest,
)
from . import holdpoints, journal
from .calls import _set_status, call_url, next_number, with_refusal_log
from .errors import PermissionRefused, RuleViolation, StrongAuthRequired, ensure_open
from .notifications import notify
from .rights import acts_for, request_visible_roles
from .tasks import complete_by_codes

DECISIONS = {
    RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS, RequestStatus.REFUSED, RequestStatus.INFO_REQUIRED,
}
VERIFY_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def get_type(call, code: str) -> RequestType:
    rtype = RequestType.objects.filter(port=call.port, code=code, is_active=True).first()
    if rtype is None:
        raise RuleViolation(_("Unknown request type: %(code)s") % {"code": code})
    return rtype


def validate_form(rtype: RequestType, data: dict) -> dict:
    """Validate data against the configurable form (EF-2.2). Unknown keys are dropped."""
    clean = {}
    data = data or {}
    for field in rtype.form_schema or []:
        key, ftype = field["key"], field.get("type", "text")
        value = data.get(key)
        label = pick(field.get("label_fr", ""), field.get("label_en", "")) or key
        if value in (None, "", []):
            if field.get("required"):
                raise RuleViolation(_("Field “%(f)s” is required.") % {"f": label})
            continue
        if ftype in ("number", "integer"):
            try:
                number = parse_decimal(value)
                if ftype == "integer" and number != number.to_integral_value():
                    raise ValueError("not an integer")
                value = int(number) if ftype == "integer" else float(number)
            except (TypeError, ValueError):
                raise RuleViolation(_("Field “%(f)s” must be a number.") % {"f": label})
        elif ftype == "datetime":
            moment = value if isinstance(value, datetime) else parse_datetime(str(value))
            if moment is None:
                raise RuleViolation(_("Field “%(f)s” must be a date and time.") % {"f": label})
            if timezone.is_naive(moment):  # typed in port time (web form): anchor it in the port time zone
                moment = timezone.make_aware(moment, ZoneInfo(rtype.port.timezone))
            value = moment.astimezone(dt_timezone.utc).isoformat()
        elif ftype == "date":
            value = str(value)
        elif ftype == "select":
            options = {str(o.get("value")) for o in field.get("options", [])}
            if str(value) not in options:
                raise RuleViolation(_("Invalid choice for “%(f)s”.") % {"f": label})
            value = str(value)
        elif ftype == "boolean":
            value = value in (True, "true", "1", "on", 1)
        else:
            value = str(value)[:4000]
        clean[key] = value
    return clean


def _transition(req: ServiceRequest, target: str) -> None:
    if target not in REQUEST_TRANSITIONS.get(req.status, set()):
        raise RuleViolation(
            _("A request in state “%(a)s” cannot become “%(b)s”.")
            % {"a": RequestStatus(req.status).label, "b": RequestStatus(target).label}
        )
    req.status = target


def _visible(req) -> list[str]:
    roles = sorted(request_visible_roles(req))
    return ["*"] if req.confidentiality == Confidentiality.N1 else roles


def provider_candidates(call, rtype: RequestType) -> list:
    """Organisations holding the executor role of a service order on the call (e.g. the waste contractors)."""
    if not rtype.executor_role:
        return []
    now = timezone.now()
    orgs = {p.organization_id: p.organization for p in call.parties.filter(role=rtype.executor_role, revoked_at__isnull=True)
            .select_related("organization") if p.is_active_at(now)}
    return sorted(orgs.values(), key=lambda o: o.name)


def _provider(call, rtype: RequestType, chosen):
    """The provider of a service order: the one named, or the only organisation holding the executor role. When
    several hold it (two waste contractors, two towage companies…), the order names one: only it carries the order
    out, and a provider never sees another provider's orders."""
    candidates = provider_candidates(call, rtype)
    if chosen not in (None, ""):
        chosen_id = getattr(chosen, "pk", chosen)
        match = next((o for o in candidates if str(o.pk) == str(chosen_id)), None)
        if match is None:
            raise RuleViolation(_("Choose the provider among the organisations taking part in the call."))
        return match
    if len(candidates) > 1:
        raise RuleViolation(_("Several organisations can carry out this service on the call: choose the one who "
                              "will."))
    return candidates[0] if len(candidates) == 1 else None


@transaction.atomic
def create_request(call, actor, type_code: str, data: dict | None = None, *, submit: bool = True,
                   as_role: str | None = None, provider=None) -> ServiceRequest:
    rtype = get_type(call, type_code)
    ensure_open(call)
    role = actor.pick_role(rtype.requester_roles, as_role)
    clean = validate_form(rtype, data or {})
    provider_org = _provider(call, rtype, provider)
    number = call.requests.count() + 1
    req = ServiceRequest.objects.create(
        call=call, type=rtype, reference=f"{call.reference}-R{number:02d}", confidentiality=rtype.confidentiality,
        requester_role=role, requester_org=actor.org or call.agency, requester_user=actor.user, data=clean,
        provider_org=provider_org,
    )
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="request.created", obj=req, visible_roles=_visible(req),
        summary_fr=f"Demande {req.reference} créée : {rtype.label_fr}",
        summary_en=f"Request {req.reference} created: {rtype.label_en}",
        payload={"type": rtype.code},
    )
    if submit:
        submit_request(req, actor)
    return req


@transaction.atomic
def submit_request(req: ServiceRequest, actor) -> ServiceRequest:
    ensure_open(req.call)
    if not acts_for(actor, req.requester_role, req.requester_org_id):
        raise PermissionRefused(_("Only the requesting party submits the request."))
    _transition(req, RequestStatus.SUBMITTED)
    now = timezone.now()
    req.submitted_at = now
    req.due_at = now + timedelta(minutes=req.type.processing_minutes)
    req.save(update_fields=["status", "submitted_at", "due_at", "updated_at"])
    journal.record(
        port=req.call.port, call=req.call, actor=actor, role=req.requester_role, action="request.submitted", obj=req,
        visible_roles=_visible(req), summary_fr=f"Demande {req.reference} soumise ({req.type.label_fr})",
        summary_en=f"Request {req.reference} submitted ({req.type.label_en})",
    )
    complete_by_codes(req.call, req.type.submit_completes, actor, evidence=f"request:{req.pk}")
    notify_submission(req)
    return req


def notify_submission(req: ServiceRequest) -> None:
    """Tell the deciding authority — or, for a service order, its provider — that a request awaits it. On a draft
    call nobody else can see yet, this waits for the declaration (apps.registry.services.calls.declare_call)."""
    from ..models import CallStatus

    if req.call.status == CallStatus.DRAFT or req.status != RequestStatus.SUBMITTED:
        return
    blocking = req.call.tasks.filter(request_type_code=req.type.code, criticality="B").exists()
    key = f"request:{req.pk}:submitted:{req.submitted_at:%Y%m%d%H%M%S}"
    title_fr = f"{req.call.reference} : {req.type.label_fr} à instruire"
    title_en = f"{req.call.reference}: {req.type.label_en} to review"
    if req.type.decision_roles:
        notify(req.call, req.type.decision_roles, key=key, title_fr=title_fr, title_en=title_en,
               url=call_url(req.call) + "#demandes", realtime=blocking)
    elif req.type.executor_role:
        notify(req.call, [req.type.executor_role], key=key, title_fr=title_fr, title_en=title_en,
               url=call_url(req.call) + "#demandes", realtime=blocking,
               organizations=[req.provider_org_id] if req.provider_org_id else None)


@transaction.atomic
def take_under_review(req: ServiceRequest, actor) -> ServiceRequest:
    ensure_open(req.call)
    role = actor.pick_role(req.type.decision_roles)
    if role == req.requester_role:
        raise PermissionRefused(_("The requesting role cannot review its own request (rule 2)."))
    _transition(req, RequestStatus.UNDER_REVIEW)
    req.save(update_fields=["status", "updated_at"])
    journal.record(port=req.call.port, call=req.call, actor=actor, role=role, action="request.under_review", obj=req,
                   visible_roles=_visible(req), summary_fr=f"Demande {req.reference} en instruction",
                   summary_en=f"Request {req.reference} under review")
    return req


def _verification_code() -> str:
    while True:
        code = "".join(secrets.choice(VERIFY_ALPHABET) for _ in range(10))
        if not Authorization.objects.filter(verification_code=code).exists():
            return code


def decide_request(req: ServiceRequest, actor, decision: str, *, reason: str = "", conditions: str = "",
                   valid_from=None, valid_until=None, berth=None, scope: str = "") -> Authorization | None:
    """Decision by the competent authority. Requires strong authentication (ENF-3.1)."""
    call = req.call
    rtype = req.type
    ensure_open(call)
    if decision not in DECISIONS:
        raise RuleViolation(_("Unknown decision."))
    role = actor.pick_role(rtype.decision_roles)
    if role == req.requester_role or (actor.user is not None and actor.user == req.requester_user):
        raise PermissionRefused(_("The requesting role or person can never decide on its own request (rule 2)."))
    if not actor.strong_auth:
        raise StrongAuthRequired()
    if req.status not in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW):
        raise RuleViolation(_("This request is not awaiting a decision."))
    if decision in (RequestStatus.REFUSED, RequestStatus.INFO_REQUIRED) and not reason.strip():
        raise RuleViolation(_("A refusal or a request for information states its reason."))
    if decision == RequestStatus.APPROVED_WITH_CONDITIONS and not conditions.strip():
        raise RuleViolation(_("An approval with conditions states the conditions."))
    approving = decision in (RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS)
    now = timezone.now()
    if approving:
        valid_from = valid_from or now
        valid_until = valid_until or (valid_from + timedelta(hours=rtype.validity_hours))
        if valid_until <= valid_from:
            raise RuleViolation(_("The expiry must follow the effective date."))
        if rtype.assigns_berth:
            if berth is None or berth.port_id != call.port_id or not berth.is_active:
                raise RuleViolation(_("Select the berth or area assigned."))
            if berth.kind != call.requested_berth_kind and not call.stages.filter(
                status="PLANNED", berth_kind=berth.kind
            ).exists():
                raise RuleViolation(_("The berth assigned does not match the operating area of the call, nor of a "
                                      "planned stage."))

    def _do():
        if approving and rtype.hold_point:
            holdpoints.check(call, rtype.hold_point)
        _transition(req, decision)
        req.decision = decision
        req.decision_role = role
        req.decision_org = actor.org
        req.decision_user = actor.user
        req.decided_at = now
        req.decision_reason = reason
        req.decision_conditions = conditions
        req.save(update_fields=["status", "decision", "decision_role", "decision_org", "decision_user", "decided_at",
                                "decision_reason", "decision_conditions", "updated_at"])
        restricted_reason = rtype.is_vetting or rtype.refusal_confidentiality == Confidentiality.N3
        payload = {"decision": decision, "conditions": conditions}
        if reason and not (decision == RequestStatus.REFUSED and restricted_reason):
            payload["reason"] = reason
        journal.record(
            port=call.port, call=call, actor=actor, role=role, action="request.decided", obj=req,
            visible_roles=_visible(req),
            summary_fr=f"{rtype.label_fr} : {RequestStatus(decision).label}"
            + (f" — {conditions}" if conditions else "")
            + (f" — {reason}" if reason and "reason" in payload else ""),
            summary_en=f"{rtype.label_en}: {decision}" + (f" — {conditions}" if conditions else "")
            + (f" — {reason}" if reason and "reason" in payload else ""),
            payload=payload,
        )
        authorization = None
        if approving:
            authorization = _issue_authorization(req, actor, role, valid_from, valid_until, conditions, scope, berth)
            if rtype.approval_status and rtype.approval_status in CALL_TRANSITIONS.get(call.status, set()):
                _set_status(call, rtype.approval_status, actor)  # a second berth (later stage) leaves the status alone
            if rtype.approval_milestone:
                mtype = MilestoneType.objects.filter(port=call.port, code=rtype.approval_milestone, is_active=True).first()
                if mtype is not None:
                    from .milestones import record_system_milestone

                    record_system_milestone(call, mtype, actor, declared_at=now, emitter_role=role,
                                            note=authorization.number)
        elif decision == RequestStatus.REFUSED and rtype.refusal_status:
            _set_status(call, rtype.refusal_status, actor, reason=rtype.label_fr)
        if decision != RequestStatus.INFO_REQUIRED:
            complete_by_codes(call, rtype.decision_completes, actor, evidence=f"request:{req.pk}")
        return authorization

    authorization = with_refusal_log(call, actor, f"decide:{rtype.code}", _do)
    notify(call, {req.requester_role, "AGE"} | ({"COM"} if rtype.is_vetting else set()),
           key=f"request:{req.pk}:decided", realtime=True,
           title_fr=f"{call.reference} : {rtype.label_fr} — {RequestStatus(decision).label}",
           title_en=f"{call.reference}: {rtype.label_en} — {decision}", url=call_url(call) + "#demandes")
    return authorization


def _issue_authorization(req, actor, role, valid_from, valid_until, conditions, scope, berth) -> Authorization:
    call = req.call
    year = timezone.now().year
    number = f"AUT-{call.port.code}-{year}-{next_number(call.port, 'AUT', year):06d}"
    scope = scope or f"{req.type.label_fr} / {req.type.label_en} — {call.vessel.name} (IMO {call.vessel.imo}) — {call.reference}"
    auth = Authorization(
        call=call, request=req, number=number, type_code=req.type.code, issuer_role=role,
        issuer_org=actor.org, issuer_user=actor.user, issuer_label=actor.label, scope=scope, conditions=conditions,
        valid_from=valid_from, valid_until=valid_until, verification_code=_verification_code(), berth=berth,
    )
    auth.seal = seal({
        "number": number, "call": call.reference, "type": req.type.code, "issuer_role": role, "issuer": actor.label,
        "scope": scope, "conditions": conditions, "valid_from": valid_from.isoformat(),
        "valid_until": valid_until.isoformat(), "verification_code": auth.verification_code,
        "berth": berth.code if berth else None,
    })
    auth.save()
    if berth is not None:
        from . import stages as stage_svc
        from .calls import recompute_deadlines

        stage = stage_svc.assign_berth(call, berth)
        if stage is None or stage.status != stage.Status.PLANNED:
            call.berth = berth
            call.etb = valid_from
            call.save(update_fields=["berth", "etb", "updated_at"])
            recompute_deadlines(call)
        else:  # assigned to a later stage: the vessel is still at the current one
            stage.planned_from = stage.planned_from or valid_from
            stage.save(update_fields=["planned_from"])
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="authorization.issued", obj=auth,
        visible_roles=_visible(req),
        summary_fr=f"Autorisation {number} délivrée ({req.type.label_fr}), valable jusqu'au {valid_until:%d/%m/%Y %H:%M} UTC",
        summary_en=f"Authorization {number} issued ({req.type.label_en}), valid until {valid_until:%Y-%m-%d %H:%M} UTC",
        payload={"number": number, "valid_from": valid_from, "valid_until": valid_until, "seal": auth.seal,
                 "berth": berth.code if berth else None},
    )
    return auth


def _awaiting_decision(req: ServiceRequest) -> None:
    if req.type.decision_roles and req.status in (RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW,
                                                   RequestStatus.INFO_REQUIRED):
        raise RuleViolation(_("This request awaits the decision of the competent authority."))


OPEN_ORDER_STATUSES = (RequestStatus.CREATED, RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW,
                       RequestStatus.INFO_REQUIRED, RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS)


@transaction.atomic
def assign_provider(req: ServiceRequest, actor, organization) -> ServiceRequest:
    """The requesting party names the provider of an order: one created before its provider joined the call, or one
    that several organisations could carry out."""
    ensure_open(req.call)
    if not req.type.executor_role:
        raise RuleViolation(_("This request is not carried out by a provider."))
    if not acts_for(actor, req.requester_role, req.requester_org_id):
        raise PermissionRefused(_("Only the requesting party names the provider."))
    if req.status not in OPEN_ORDER_STATUSES or req.provider_org_id is not None:
        raise RuleViolation(_("The provider of this order can no longer be chosen."))
    provider = _provider(req.call, req.type, organization)
    if provider is None:
        raise RuleViolation(_("Choose the provider among the organisations taking part in the call."))
    req.provider_org = provider
    req.save(update_fields=["provider_org", "updated_at"])
    _journal_provider(req, actor)
    notify_submission(req)
    return req


def assign_pending_providers(call, role: str, actor) -> int:
    """After a provider joins the call: the open orders of its kind that no provider had yet are now its own when it
    is the only organisation holding the role."""
    candidates = None
    count = 0
    for req in call.requests.filter(type__executor_role=role, provider_org__isnull=True,
                                    status__in=OPEN_ORDER_STATUSES).select_related("type"):
        candidates = candidates if candidates is not None else provider_candidates(call, req.type)
        if len(candidates) == 1:
            req.provider_org = candidates[0]
            req.save(update_fields=["provider_org", "updated_at"])
            _journal_provider(req, actor)
            notify_submission(req)
            count += 1
    return count


def _journal_provider(req: ServiceRequest, actor) -> None:
    journal.record(port=req.call.port, call=req.call, actor=actor, action="request.provider", obj=req,
                   visible_roles=_visible(req),
                   summary_fr=f"{req.reference} : réalisée par {req.provider_org}",
                   summary_en=f"{req.reference}: carried out by {req.provider_org}")


def _executing_role(req: ServiceRequest, actor) -> str:
    """The role that schedules and carries out the order — and, for a named provider, its organisation only."""
    ensure_open(req.call)
    role = actor.pick_role({req.type.executor_role} if req.type.executor_role else set(req.type.decision_roles))
    if req.type.executor_role and role == req.type.executor_role and not actor.is_system:
        provider_id = req.provider_org_id
        if provider_id is None:
            candidates = provider_candidates(req.call, req.type)
            provider_id = candidates[0].pk if len(candidates) == 1 else None
        if provider_id is None or actor.org is None or actor.org.pk != provider_id:
            raise PermissionRefused(_("This service order is carried out by another provider."))
    return role


@transaction.atomic
def schedule_request(req: ServiceRequest, actor, when) -> ServiceRequest:
    """For a service order (pilotage, towage, mooring, waste…) scheduling is the provider's confirmation."""
    role = _executing_role(req, actor)
    _awaiting_decision(req)
    _transition(req, RequestStatus.SCHEDULED)
    req.scheduled_for = when
    req.save(update_fields=["status", "scheduled_for", "updated_at"])
    journal.record(port=req.call.port, call=req.call, actor=actor, role=role, action="request.scheduled", obj=req,
                   visible_roles=_visible(req), summary_fr=f"{req.reference} programmée le {when:%d/%m %H:%M} UTC",
                   summary_en=f"{req.reference} scheduled {when:%Y-%m-%d %H:%M} UTC")
    if not req.type.decision_roles:
        complete_by_codes(req.call, req.type.decision_completes, actor, evidence=f"request:{req.pk}")
    return req


@transaction.atomic
def execute_request(req: ServiceRequest, actor, note: str = "") -> ServiceRequest:
    role = _executing_role(req, actor)
    _awaiting_decision(req)
    _transition(req, RequestStatus.EXECUTED)
    req.executed_at = timezone.now()
    req.executed_by = actor.user
    req.save(update_fields=["status", "executed_at", "executed_by", "updated_at"])
    journal.record(port=req.call.port, call=req.call, actor=actor, role=role, action="request.executed", obj=req,
                   visible_roles=_visible(req), summary_fr=f"{req.reference} exécutée" + (f" — {note}" if note else ""),
                   summary_en=f"{req.reference} executed" + (f" — {note}" if note else ""))
    complete_by_codes(req.call, req.type.execution_completes, actor, evidence=f"request:{req.pk}")
    return req


@transaction.atomic
def cancel_request(req: ServiceRequest, actor, reason: str) -> ServiceRequest:
    ensure_open(req.call)
    if not acts_for(actor, req.requester_role, req.requester_org_id):
        raise PermissionRefused(_("Only the requesting party cancels its request."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    _transition(req, RequestStatus.CANCELLED)
    req.save(update_fields=["status", "updated_at"])
    journal.record(port=req.call.port, call=req.call, actor=actor, role=req.requester_role, action="request.cancelled",
                   obj=req, visible_roles=_visible(req), summary_fr=f"{req.reference} annulée — {reason}",
                   summary_en=f"{req.reference} cancelled — {reason}")
    return req


@transaction.atomic
def cancel_authorization(auth: Authorization, actor, reason: str) -> AuthorizationEvent:
    ensure_open(auth.call)
    if not acts_for(actor, auth.issuer_role, auth.issuer_org_id):
        raise PermissionRefused(_("Only the issuing authority cancels an authorization."))
    if not actor.strong_auth:
        raise StrongAuthRequired()
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    event = AuthorizationEvent.objects.create(authorization=auth, kind=AuthorizationEvent.Kind.CANCELLED,
                                              user=actor.user, reason=reason)
    journal.record(port=auth.call.port, call=auth.call, actor=actor, role=auth.issuer_role,
                   action="authorization.cancelled", obj=auth, visible_roles=_visible(auth.request),
                   summary_fr=f"Autorisation {auth.number} annulée — {reason}",
                   summary_en=f"Authorization {auth.number} cancelled — {reason}")
    return event


def expire_authorizations(now=None) -> int:
    """Approved requests whose authorization has expired become Expired; requester and agency are alerted."""
    now = now or timezone.now()
    count = 0
    candidates = ServiceRequest.objects.filter(
        status__in=[RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS, RequestStatus.SCHEDULED],
        authorization__valid_until__lte=now,
    ).exclude(call__status__in=["CLOSED", "ARCHIVED", "REJECTED", "CANCELLED"]).select_related(
        "call", "type", "authorization")  # a frozen call is never changed, not even by the platform
    for req in candidates:
        with transaction.atomic():
            req.status = RequestStatus.EXPIRED
            req.save(update_fields=["status", "updated_at"])
            journal.record(port=req.call.port, call=req.call, actor=None, role="SYSTEM", action="authorization.expired",
                           obj=req.authorization, visible_roles=_visible(req),
                           summary_fr=f"Autorisation {req.authorization.number} expirée ({req.type.label_fr})",
                           summary_en=f"Authorization {req.authorization.number} expired ({req.type.label_en})")
            Alert.objects.create(call=req.call, kind=AlertKind.EXPIRY, recipient_roles=[req.requester_role, "AGE"],
                                 message_fr=f"{req.type.label_fr} : autorisation {req.authorization.number} expirée",
                                 message_en=f"{req.type.label_en}: authorization {req.authorization.number} expired")
        notify(req.call, {req.requester_role, "AGE"}, key=f"expired:{req.authorization.pk}",
               title_fr=f"{req.call.reference} : autorisation {req.authorization.number} expirée",
               title_en=f"{req.call.reference}: authorization {req.authorization.number} expired",
               url=call_url(req.call) + "#demandes")
        count += 1
    return count


def verify_authorization(code: str) -> dict | None:
    """Public verification by code, without access to the call file (EF-2.5)."""
    auth = Authorization.objects.filter(verification_code=(code or "").strip().upper()).select_related(
        "call", "call__vessel", "call__port", "request__type").first()
    if auth is None:
        return None
    now = timezone.now()
    return {
        "number": auth.number,
        "type_fr": auth.request.type.label_fr,
        "type_en": auth.request.type.label_en,
        "port": auth.call.port.name,
        "vessel": auth.call.vessel.name,
        "imo": auth.call.vessel.imo,
        "issuer_role": role_label(auth.issuer_role),
        "valid_from": auth.valid_from,
        "valid_until": auth.valid_until,
        "cancelled": auth.is_cancelled,
        "valid_now": auth.is_valid(now),
        "seal": auth.seal[:16],
    }
