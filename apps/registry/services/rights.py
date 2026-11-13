"""Server-side rights engine — FLX-SPEC-001 §5 (objects × roles) and §6 (four confidentiality levels).

No right is ever enforced by the interface alone (EF-12.2): views and the API call these
functions, and querysets are filtered here. An object the actor may not see is reported as
"not found" so that its existence is never disclosed.
"""
from __future__ import annotations

from django.db.models import Q
from django.utils.translation import gettext as _

from apps.core.roles import AUDIT_ROLES, EXPORT_ROLES, OVERVIEW_ROLES, role_label

from ..models import (
    DEFAULT_REPORT_READERS,
    CallStatus,
    Confidentiality,
    Dispute,
    Document,
    Milestone,
    ReportAccess,
    ServiceRequest,
    Task,
    Thread,
)
from .errors import NotVisible, PermissionRefused

# FLX-SPEC-001 §5 — verbs: C create · V view · S enter/modify · A approve/decide · Cs countersign
# Ct contest · K close · E export. Encoded literally; V is listed wherever the matrix grants it.
MATRIX: dict[str, dict[str, set[str]]] = {
    "call": {
        "AGE": {"C", "S", "K", "V"}, "NAV": {"V"}, "TER": {"V"}, "CAP": {"A", "K", "V"}, "APO": {"S", "V"},
        "SVC": {"V"}, "ADM": {"V"}, "SUR": {"V"}, "INS": {"V"}, "COM": {"V", "E"}, "PRE": {"V"}, "DIR": {"V", "E"},
    },
    "vessel": {
        "AGE": {"C", "S", "V"}, "NAV": {"V", "Ct"}, "TER": {"V"}, "CAP": {"A", "V"}, "APO": {"V"}, "SVC": {"V"},
        "ADM": {"V"}, "SUR": {"V"}, "INS": {"V"}, "COM": {"V"}, "PRE": set(), "DIR": {"V"},
    },
    "party": {
        "AGE": {"C", "V"}, "NAV": {"V"}, "TER": {"V"}, "CAP": {"A", "V"}, "APO": {"V"}, "SVC": {"V"}, "ADM": {"V"},
        "SUR": {"V"}, "INS": {"V"}, "COM": {"V"}, "PRE": {"V"}, "DIR": {"V"},
    },
    "request": {
        "AGE": {"C", "S", "V"}, "NAV": {"V", "Ct"}, "TER": {"C", "S", "V"}, "CAP": {"A", "V"}, "APO": {"A", "V"},
        "SVC": {"V"}, "ADM": {"A", "V"}, "SUR": {"A", "V"}, "INS": set(), "COM": {"V"}, "PRE": {"C", "S", "V"},
        "DIR": {"V"},
    },
    "authorization": {
        "AGE": {"V"}, "NAV": {"V"}, "TER": {"V"}, "CAP": {"C", "A", "V"}, "APO": {"C", "A", "V"}, "SVC": {"V"},
        "ADM": {"C", "A", "V"}, "SUR": {"C", "A", "V"}, "INS": set(), "COM": {"V"}, "PRE": {"V"}, "DIR": {"V", "E"},
    },
    "milestone": {
        "AGE": {"S", "Cs", "V"}, "NAV": {"Cs", "Ct", "V"}, "TER": {"S", "Cs", "V"}, "CAP": {"V", "Ct"},
        "APO": {"V"}, "SVC": {"S", "V"}, "ADM": {"S", "V"}, "SUR": {"S", "V"}, "INS": {"S", "Cs", "V"},
        "COM": {"V", "Ct"}, "PRE": {"S"}, "DIR": {"V", "E"},
    },
    "measurement": {
        "AGE": {"V"}, "NAV": {"S", "Cs", "V"}, "TER": {"S", "Cs", "V"}, "CAP": {"V"}, "APO": set(), "SVC": set(),
        "ADM": set(), "SUR": set(), "INS": {"S", "Cs", "V"}, "COM": {"V", "Ct"}, "PRE": set(), "DIR": {"V", "E"},
    },
    "dispute": {
        "AGE": {"C", "V"}, "NAV": {"C", "V"}, "TER": {"C", "V"}, "CAP": {"V", "A"}, "APO": {"V"}, "SVC": {"V"},
        "ADM": {"V"}, "SUR": {"V"}, "INS": {"C", "V"}, "COM": {"C", "V"}, "PRE": {"V"}, "DIR": {"V", "E"},
    },
    "document": {
        "AGE": {"C", "S", "V"}, "NAV": {"C", "Cs", "V"}, "TER": {"C", "S", "V"}, "CAP": {"V", "A"}, "APO": {"V"},
        "SVC": {"V"}, "ADM": {"C", "A", "V"}, "SUR": {"C", "V"}, "INS": {"C", "S", "V"}, "COM": {"V"}, "PRE": {"C"},
        "DIR": {"V", "E"},
    },
    "correspondence": {
        **{r: {"C", "V"} for r in ("AGE", "NAV", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "PRE")},
        "DIR": {"V"},
    },
    "berth": {
        "AGE": {"V"}, "NAV": set(), "TER": {"V"}, "CAP": {"A", "V"}, "APO": {"C", "S", "A", "V"}, "SVC": {"S", "V"},
        "ADM": set(), "SUR": set(), "INS": set(), "COM": set(), "PRE": set(), "DIR": {"V"},
    },
    "dashboard": {r: {"V"} for r in ("AGE", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "PRE")}
    | {"DIR": {"V", "E"}, "NAV": set()},
    "audit": {"CAP": {"V"}, "SUR": {"V"}, "DIR": {"V", "E"}},
}

# Roles that coordinate the call and see restricted (N2) objects in addition to emitter/recipients
N2_SUPERVISORS = frozenset({"AGE", "CAP", "DIR"})


def can(actor, verb: str, kind: str) -> bool:
    if actor is None:
        return False
    if actor.is_system:
        return True
    table = MATRIX.get(kind, {})
    return any(verb in table.get(role, set()) for role in actor.roles)


def require(actor, verb: str, kind: str, message: str | None = None) -> None:
    if not can(actor, verb, kind):
        raise PermissionRefused(message or _("Your role on this call does not allow this action."))


def roles_with(verb: str, kind: str) -> set[str]:
    return {role for role, verbs in MATRIX.get(kind, {}).items() if verb in verbs}


def only_provider(actor) -> bool:
    """Providers see only their own service, not the full call (FLX-SPEC-001 §5 note 4)."""
    return actor is not None and not actor.is_system and actor.roles and set(actor.roles) <= {"PRE"}


def acts_for(actor, role: str, org_id, *, by_master: bool = False) -> bool:
    """The actor acts for the party that made a record: same role and, for a shore party, same organisation —
    whether the record was made from an account or from the organisation's access link. Several organisations
    may hold one role on a call (two providers, owner and charterer, two surveyors): the role alone never lets
    one of them read, replace, cancel or close what another one issued. The ship is one party: any valid
    master link of the call speaks for it."""
    if actor is None:
        return False
    if actor.is_system:
        return True
    if role not in actor.roles:
        return False
    if role == "NAV":
        return actor.is_master
    if actor.is_master:
        return False
    return actor.org is not None and actor.org.pk == org_id


def is_document_issuer(actor, doc: Document) -> bool:
    return acts_for(actor, doc.issuer_role, doc.issuer_org_id, by_master=doc.issuer_master_id is not None)


def is_dispute_opener(actor, dispute: Dispute) -> bool:
    return acts_for(actor, dispute.opened_role, dispute.opened_org_id, by_master=dispute.opened_master_id is not None)


# ============================================================================ calls
def can_see_full_call(actor) -> bool:
    """The product, the quantity and what the agency declared at the announcement (v1.6): for every reader of the
    call but a provider, who reads what concerns it in the request addressed to it"""
    return not only_provider(actor)


# ============================================================================ tasks (EF-5.7)
def task_visible(actor, task: Task) -> bool:
    if actor.is_system or actor.has(*OVERVIEW_ROLES):
        return True
    if task.role == "ANY":
        return not only_provider(actor) or "PRE" in task.all_roles
    return bool(set(task.all_roles) & set(actor.roles))


def visible_tasks(actor, call):
    qs = call.tasks.all()
    if actor.is_system or actor.has(*OVERVIEW_ROLES):
        return qs
    roles = list(actor.roles)
    cond = Q(role__in=roles)
    for role in roles:
        cond |= Q(co_roles__contains=[role]) if _json_contains_supported() else Q(co_roles__icontains=f'"{role}"')
    if not only_provider(actor):
        cond |= Q(role="ANY")
    return qs.filter(cond)


def _json_contains_supported() -> bool:
    from django.db import connection

    return connection.vendor == "postgresql"


# ============================================================================ milestones
SHORE_ROLES = ("TER", "PRE")


def shore_org_id(call, role: str):
    """The organisation that speaks for the shore side in *role* — the terminal at a berth, the provider operating at
    sea (FLX-SPEC-001 §7): the party the agency or the harbour master designated, else the only organisation holding
    that role on the call. With several and none designated, none of them speaks for the shore side."""
    from django.utils import timezone

    now = timezone.now()
    parties = [p for p in call.parties.filter(role=role, revoked_at__isnull=True) if p.is_active_at(now)]
    designated = [p for p in parties if p.shore_side]
    if designated:
        return designated[0].organization_id
    organisations = {p.organization_id for p in parties}
    return next(iter(organisations)) if len(organisations) == 1 else None


def speaks_for_shore(actor, role: str, call) -> bool:
    if actor.is_system:
        return True
    return actor.org is not None and actor.org.pk == shore_org_id(call, role)


def provider_answers_for(actor, milestone: Milestone) -> bool:
    """A provider is the countersigner of this milestone (addressed to "PRE") as the shore side of the call."""
    return "PRE" in (milestone.countersigner_roles or []) and speaks_for_shore(actor, "PRE", milestone.call)


def milestone_visible(actor, milestone: Milestone) -> bool:
    if actor.is_system:
        return True
    if not can(actor, "V", "milestone") and not can(actor, "S", "milestone"):
        return False
    if only_provider(actor):
        own = milestone.emitter_role == "PRE" and actor.org is not None and milestone.emitter_org_id == actor.org.pk
        return own or provider_answers_for(actor, milestone)
    return True


def visible_milestones(actor, call):
    qs = call.milestones.select_related("type", "cause").all()
    if actor.is_system:
        return qs
    if only_provider(actor):
        shore = speaks_for_shore(actor, "PRE", call)
        own = Q(emitter_role="PRE", emitter_org=actor.org)
        return qs.filter(own | Q(countersigner_roles__contains=["PRE"])) if shore else qs.filter(own)
    return qs


# ============================================================================ requests & authorizations
def request_visible_roles(req: ServiceRequest) -> set[str]:
    rtype = req.type
    if req.confidentiality == Confidentiality.N1:
        roles = {"AGE", "NAV", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "COM", "DIR"}
    elif req.confidentiality == Confidentiality.N3:
        roles = set()
    else:
        roles = set(N2_SUPERVISORS)
    roles |= {req.requester_role, *rtype.decision_roles}
    if rtype.executor_role:
        roles.add(rtype.executor_role)
    if rtype.is_vetting:
        roles |= {"COM"}  # the refusal reason goes to agency and owner (S7); the request itself too
    roles.discard("INS")  # FLX-SPEC-001 §5: no right on requests/authorizations
    return roles


def request_visible(actor, req: ServiceRequest) -> bool:
    if actor.is_system:
        return True
    roles = request_visible_roles(req)
    if only_provider(actor):
        # a provider sees the requests it made and the service orders it carries out — not the other providers'
        org_id = actor.org.pk if actor.org is not None else None
        provider = req.provider_org_id or (sole_holder(req.call, "PRE") if req.type.executor_role == "PRE" else None)
        return (req.requester_role == "PRE" and req.requester_org_id == org_id) or (
            req.type.executor_role == "PRE" and provider is not None and provider == org_id)
    return bool(roles & set(actor.roles))


def sole_holder(call, role: str):
    """The organisation holding *role* on the call, when it is the only one."""
    from django.utils import timezone

    now = timezone.now()
    organisations = {p.organization_id for p in call.parties.filter(role=role, revoked_at__isnull=True)
                     if p.is_active_at(now)}
    return next(iter(organisations)) if len(organisations) == 1 else None


def visible_requests(actor, call):
    qs = call.requests.select_related("type", "provider_org").all()
    if actor.is_system:
        return qs
    return [r for r in qs if request_visible(actor, r)]


def can_see_refusal_reason(actor, req: ServiceRequest) -> bool:
    """Vetting refusal reasons are N3: agency, owner and the instructing service only (EF-2.6, S7)."""
    if actor.is_system:
        return True
    if req.type.refusal_confidentiality == Confidentiality.N3 or req.type.is_vetting:
        allowed = {"AGE", "COM"}
        if req.decision_role:
            allowed.add(req.decision_role)
        return bool(allowed & set(actor.roles))
    return request_visible(actor, req)


# ============================================================================ documents
def document_readers(doc: Document) -> set[str]:
    """The roles that read a restricted (N2) document besides its issuer: the listed readers and the required
    signers, plus — unless the document type limits its readers to that list — the coordinating roles (agency,
    harbour master, port management) and the owner. A laboratory's quality certificate limits its readers
    (FLX-CDC-002 v1.4, EXG-Q-06): the agency does not read it."""
    allowed = set(doc.required_signers or []) | set(doc.type.audience_roles or []) | set(doc.audience_roles or [])
    if not doc.type.readers_exact:
        allowed |= set(N2_SUPERVISORS) | {"COM"}
    return allowed


def document_visible(actor, doc: Document) -> bool:
    if actor.is_system:
        return True
    roles = set(actor.roles)
    if is_document_issuer(actor, doc):
        return True
    if only_provider(actor):
        return False
    if doc.confidentiality == Confidentiality.N1:
        return bool(roles & roles_with("V", "document"))
    if doc.confidentiality == Confidentiality.N3:
        return doc.counterpart_role in roles  # the issuing side is its own organisation, checked above
    return bool(roles & document_readers(doc))


def visible_documents(actor, call):
    qs = call.documents.select_related("type").all()
    if actor.is_system:
        return qs
    return [d for d in qs if document_visible(actor, d)]


# ============================================================================ reports decided at parametrage
def report_readers(port, code: str) -> set[str]:
    """The roles that read a live report of the port (pumping log, validated measurements, safety checklist,
    call board): the port administrator's setting, else the catalogue's default (FLX-CDC-002 v1.4, EXG-Q-08)."""
    row = ReportAccess.objects.filter(port=port, code=code).first()
    if row is not None:
        return set(row.reader_roles or [])
    return set(DEFAULT_REPORT_READERS.get(code, []))


def can_read_report(actor, code: str) -> bool:
    if actor is None:
        return False
    if actor.is_system:
        return True
    return bool(set(actor.roles) & report_readers(actor.port, code))


# ============================================================================ measurements
def measurements_visible(actor) -> bool:
    """Quantities and validated tank readings: the readers the port decided at parametrage."""
    return can_read_report(actor, "MEASUREMENTS")


def acts_for_side(actor, side: str, org_id=None) -> bool:
    """The actor is the party of *side*: the ship through the master's link (or a NAV account), the shore through
    the terminal that entered the record (or, with no record yet, the terminal that speaks for the shore)."""
    if actor is None:
        return False
    if actor.is_system:
        return True
    if side == "SHIP":
        return "NAV" in actor.roles
    if "TER" not in actor.roles:
        return False
    if org_id is not None:
        return actor.org is not None and actor.org.pk == org_id
    return True


def tank_reading_visible(actor, reading) -> bool:
    """A validated reading is read by the measurement readers; a pending or rejected one by its own side and the
    surveyor only (FLX-CDC-002 v1.4, EXG-Q-05)."""
    if actor.is_system:
        return True
    if reading.is_validated:
        return measurements_visible(actor)
    return "INS" in actor.roles or acts_for_side(actor, reading.side, reading.entered_org_id)


# ============================================================================ disputes
def dispute_header_visible(actor, dispute: Dispute) -> bool:
    if actor.is_system:
        return True
    if only_provider(actor):
        return is_dispute_opener(actor, dispute) or is_dispute_counterpart(actor, dispute)
    return can(actor, "V", "dispute")


def is_dispute_counterpart(actor, dispute: Dispute) -> bool:
    """The party a dispute is addressed to: the author of the disputed item when it has one, else the role."""
    if not dispute.counterpart_role:
        return False
    if dispute.counterpart_org_id is not None or dispute.counterpart_master:
        return acts_for(actor, dispute.counterpart_role, dispute.counterpart_org_id, by_master=dispute.counterpart_master)
    if dispute.counterpart_role in SHORE_ROLES and dispute.counterpart_role in actor.roles:
        return speaks_for_shore(actor, dispute.counterpart_role, dispute.call)
    return dispute.counterpart_role in actor.roles


def dispute_content_visible(actor, dispute: Dispute) -> bool:
    """Statements are bilateral (N3): the two parties plus the harbour master."""
    if actor.is_system:
        return True
    return is_dispute_opener(actor, dispute) or is_dispute_counterpart(actor, dispute) or "CAP" in actor.roles


# ============================================================================ correspondence
def is_thread_creator(actor, thread: Thread) -> bool:
    org_id = thread.created_org_id
    if org_id is None and thread.created_by_id is not None:  # threads opened before the organisation was recorded
        org_id = thread.created_by.organization_id
    return acts_for(actor, thread.created_role, org_id, by_master=thread.created_master_id is not None)


def thread_visible(actor, thread: Thread) -> bool:
    """The creating side within its own organisation, and the invited parties."""
    if actor.is_system:
        return True
    roles = set(actor.roles)
    invited = set(thread.participant_roles or []) - {thread.created_role}
    if thread.confidentiality == Confidentiality.N1:
        return not only_provider(actor) or bool(roles & invited) or is_thread_creator(actor, thread)
    if "DIR" in roles and thread.confidentiality == Confidentiality.N2:
        return True
    return bool(roles & invited) or is_thread_creator(actor, thread)


# ============================================================================ alerts
def alert_visible(actor, alert) -> bool:
    """An alert is a record addressed to some roles; the harbour master and the port management see them all."""
    if actor.is_system or actor.has("CAP", "DIR"):
        return True
    recipients = set(alert.recipient_roles or [])
    return "*" in recipients or bool(recipients & set(actor.roles))


# ============================================================================ audit / export
def can_read_audit(actor) -> bool:
    return actor.is_system or actor.has(*AUDIT_ROLES)


def can_export(actor) -> bool:
    return actor.is_system or actor.has(*EXPORT_ROLES)


def ensure_visible(predicate: bool) -> None:
    if not predicate:
        raise NotVisible()


def responsible_label(role: str) -> str:
    return role_label(role)


def call_queryset_for_user(user):
    """Calls on which the user's organisation holds an active role that the user may exercise."""
    from django.utils import timezone

    from ..models import PortCall

    if not user.is_authenticated or not user.organization_id:
        return PortCall.objects.none()
    now = timezone.now()
    # one filter() call: every condition applies to the same party row (an expired role must not be completed by
    # the dates of another one)
    return PortCall.objects.filter(
        Q(parties__valid_until__isnull=True) | Q(parties__valid_until__gt=now),
        port_id=user.organization.port_id,
        parties__organization_id=user.organization_id,
        parties__role__in=list(user.role_set) or ["-"],
        parties__revoked_at__isnull=True,
        parties__valid_from__lte=now,
    ).distinct()


# ============================================================================ controlled access (v1.5, EXG-R-04)
def is_principal_agent(actor, call) -> bool:
    """The agency that created the call: it declares, revises, cancels and closes it, and grants the other
    parties their access. A co-nominated agency acts within the access it was given."""
    return actor.is_system or (actor.has("AGE") and actor.org is not None and actor.org.pk == call.agency_id)


def access_of(actor, call) -> tuple[str, set[str] | None]:
    """The access the actor holds on the file: ``("FULL", None)`` — every tab, acts within its role —,
    ``("PARTIAL", {tabs})`` — the tabs listed, acts within them —, ``("READ", None)`` — every tab, no act.
    The system, the account-less links (a master, a party's link: their role is their whole access), the
    principal agent and the port's own parties hold the file in full."""
    if actor.is_system or actor.master is not None or actor.org is None:
        return "FULL", None
    if is_principal_agent(actor, call):
        return "FULL", None
    from django.utils import timezone

    now = timezone.now()
    rows = [p for p in call.parties.all() if p.organization_id == actor.org.pk and p.role in actor.roles and p.is_active_at(now)]
    if not rows or any(p.access == "FULL" for p in rows):
        return "FULL", None
    partial = [p for p in rows if p.access == "PARTIAL"]
    if partial:
        scopes = set()
        for p in partial:
            scopes.update(p.scopes or [])
        return "PARTIAL", scopes
    return "READ", None


def allowed_tabs(actor, call) -> set[str] | None:
    """The tabs of the file the actor may open (None = every tab)."""
    access, scopes = access_of(actor, call)
    return scopes if access == "PARTIAL" else None


def can_act_in(actor, call, scope: str) -> bool:
    """May the actor act (enter, decide, upload…) in this part of the file? Reading only never acts; a partial
    access acts in its tabs only."""
    access, scopes = access_of(actor, call)
    if access == "READ":
        return False
    if access == "PARTIAL":
        return scope in (scopes or set())
    return True


def require_act(actor, call, scope: str) -> None:
    access, scopes = access_of(actor, call)
    if access == "READ":
        raise PermissionRefused(_("Your access to this call is reading only: the principal agent gives the right to act."))
    if access == "PARTIAL" and scope not in (scopes or set()):
        raise PermissionRefused(_("Your access to this call does not cover this part of the file (%(scope)s): the principal "
                                  "agent gives it.") % {"scope": scope})


def draft_visible(actor, call) -> bool:
    """A draft call is visible to its agency (and to the master, who provides certificates) until declared."""
    return call.status != CallStatus.DRAFT or actor.has("AGE", "NAV") or actor.is_system
