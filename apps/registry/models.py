"""Operational registry of tanker port calls — the business objects of FLX-SPEC-001.

Founding principle: the platform is not a communication tool, it is a *registry*. Its value comes
from establishing facts that parties with diverging interests can rely on. Hence:

* every object hangs off a port call (EF-1.3) — enforced by NOT NULL foreign keys;
* journal, milestones, signatures, authorizations, values and messages are append-only;
* nothing is ever deleted (ORM guards + PostgreSQL triggers + database grants);
* templates, request types, reference lists and labels are data, never code (orientation 4).
"""
from __future__ import annotations

import secrets
import uuid
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.guards import AppendOnlyModel, NoDeleteModel
from apps.core.models import Berth, Organization, Port, pick
from apps.core.roles import ALL_ROLES, ANY_PARTY, Role

User = settings.AUTH_USER_MODEL


# ======================================================================================
# Enumerations
# ======================================================================================
class Confidentiality(models.TextChoices):
    N1 = "N1", _("N1 — Call (all parties)")
    N2 = "N2", _("N2 — Restricted")
    N3 = "N3", _("N3 — Bilateral")
    N4 = "N4", _("N4 — Security")


class Nature(models.TextChoices):
    F = "F", _("Provide a document")
    R = "R", _("Enter data")
    D = "D", _("Decide")
    C = "C", _("Confirm execution")
    S = "S", _("Sign / countersign")


class Criticality(models.TextChoices):
    BLOCKING = "B", _("Blocking")
    NORMAL = "N", _("Normal")


class Anchor(models.TextChoices):
    """Deadline anchors. Every deadline is relative: no absolute date can be stored (EF-5.3)."""

    NONE = "", _("Event-driven (no deadline)")
    NOM = "NOM", _("Nomination")
    ETA = "ETA", "ETA"
    ETB = "ETB", "ETB"
    ATB = "ATB", "ATB"
    T0 = "T0", "T0"
    T1 = "T1", "T1"
    ATD = "ATD", "ATD"
    NOR = "NOR", "NOR"


class TemplateKind(models.TextChoices):
    BASE = "BASE", _("Common base (M0)")
    OPERATION = "OPERATION", _("Operation model (M1–M8)")
    MODULE = "MODULE", _("Additional module (M9, MA1–MA3)")


class CallStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    DECLARED = "DECLARED", _("Declared")
    ACCEPTED = "ACCEPTED", _("Accepted")
    PLANNED = "PLANNED", _("Planned")
    APPROACHING = "APPROACHING", _("Approaching / at anchorage")
    AT_BERTH = "AT_BERTH", _("Alongside")
    IN_OPERATION = "IN_OPERATION", _("In operation")
    OPS_COMPLETE = "OPS_COMPLETE", _("Operations completed")
    SHIFTING = "SHIFTING", _("Shifting within the port")
    DEPARTED = "DEPARTED", _("Departed")
    CLOSED = "CLOSED", _("Closed")
    ARCHIVED = "ARCHIVED", _("Archived")
    REJECTED = "REJECTED", _("Rejected")
    CANCELLED = "CANCELLED", _("Cancelled")
    # The announcement's validity ran out before the vessel berthed (FLX-CDC-002 v1.5, EXG-R-02): the call is
    # obsolete and a new announcement is made
    EXPIRED = "EXPIRED", _("Obsolete (validity expired)")


# Life-cycle graph of a call (EF-1.2). Any transition outside this graph is refused.
CALL_TRANSITIONS: dict[str, set[str]] = {
    CallStatus.DRAFT: {CallStatus.DECLARED, CallStatus.CANCELLED, CallStatus.EXPIRED},
    CallStatus.DECLARED: {CallStatus.ACCEPTED, CallStatus.REJECTED, CallStatus.CANCELLED, CallStatus.EXPIRED},
    CallStatus.ACCEPTED: {CallStatus.PLANNED, CallStatus.CANCELLED, CallStatus.EXPIRED},
    CallStatus.PLANNED: {CallStatus.APPROACHING, CallStatus.CANCELLED, CallStatus.EXPIRED},
    CallStatus.APPROACHING: {CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.DEPARTED, CallStatus.EXPIRED},
    CallStatus.AT_BERTH: {CallStatus.IN_OPERATION, CallStatus.SHIFTING, CallStatus.DEPARTED},
    CallStatus.IN_OPERATION: {CallStatus.OPS_COMPLETE, CallStatus.SHIFTING},
    CallStatus.OPS_COMPLETE: {CallStatus.SHIFTING, CallStatus.DEPARTED},
    # between two stages of the same call (offshore → quay, quay → anchorage…): the next berthing resumes the chain
    CallStatus.SHIFTING: {CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.DEPARTED},
    CallStatus.DEPARTED: {CallStatus.CLOSED},
    CallStatus.CLOSED: {CallStatus.ARCHIVED},
    CallStatus.ARCHIVED: set(),
    CallStatus.REJECTED: set(),
    CallStatus.CANCELLED: set(),
    CallStatus.EXPIRED: set(),
}
# Statuses in which an announcement whose validity ran out becomes obsolete: before the vessel is alongside. A
# vessel already berthed or working is never cut off: its overrun is signalled and counted (billing).
EXPIRABLE_STATUSES = [CallStatus.DRAFT, CallStatus.DECLARED, CallStatus.ACCEPTED, CallStatus.PLANNED, CallStatus.APPROACHING]
# Operational chain along which a recorded milestone may move a call forward
OPERATIONAL_CHAIN = [
    CallStatus.PLANNED,
    CallStatus.APPROACHING,
    CallStatus.AT_BERTH,
    CallStatus.IN_OPERATION,
    CallStatus.OPS_COMPLETE,
    CallStatus.DEPARTED,
]
ACTIVE_STATUSES = [
    CallStatus.DECLARED, CallStatus.ACCEPTED, CallStatus.PLANNED, CallStatus.APPROACHING,
    CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.OPS_COMPLETE, CallStatus.SHIFTING,
]


class Transition(models.TextChoices):
    """Transitions that the platform refuses while blocking tasks are not done (EF-11)."""

    DECLARE = "DECLARE", _("Declare the call")
    GREEN_LIGHT = "GREEN_LIGHT", _("Grant the green light")
    BERTH_ASSIGN = "BERTH_ASSIGN", _("Assign a berth")
    MOVEMENT_AUTH = "MOVEMENT_AUTH", _("Issue the movement authorization")
    PILOT_BOARDING = "PILOT_BOARDING", _("Record pilot on board (arrival)")
    BERTHING = "BERTHING", _("Record the berthing (lines ashore, all fast, vessels alongside)")
    START_TRANSFER = "START_TRANSFER", _("Start the transfer")
    DOUBLE_BANKING = "DOUBLE_BANKING", _("Authorize double banking")
    HOT_WORK = "HOT_WORK", _("Authorize hot work")
    BL_ISSUE = "BL_ISSUE", _("Issue the bill of lading")
    DEPARTURE_CLEARANCE = "DEPARTURE_CLEARANCE", _("Issue the departure clearance")
    PILOT_BOARDING_DEP = "PILOT_BOARDING_DEP", _("Record pilot on board (departure)")
    DEPARTURE = "DEPARTURE", _("Record the departure (last line, vessel departed)")
    CLOSE = "CLOSE", _("Close the call")


class TaskStatus(models.TextChoices):
    PENDING = "PENDING", _("To do")
    DONE = "DONE", _("Done")
    NOT_APPLICABLE = "NA", _("Not applicable")


class AlertLevel(models.TextChoices):
    NONE = "NONE", _("On time")
    REMINDER = "REMINDER", _("Reminder")
    LATE = "LATE", _("Late")
    ESCALATED = "ESCALATED", _("Escalated")


class CountersignState(models.TextChoices):
    PENDING = "PENDING", _("Awaiting countersignature")
    COUNTERSIGNED = "COUNTERSIGNED", _("Countersigned")
    CONTESTED = "CONTESTED", _("Contested")
    TACIT = "TACIT", _("Tacit countersignature")


class EntrySource(models.TextChoices):
    ONLINE = "ONLINE", _("Online entry")
    OFFLINE = "OFFLINE", _("Offline entry (synchronised)")
    PAPER = "PAPER", _("Paper fallback (re-entered)")
    AIS = "AIS", _("AIS")
    SYSTEM = "SYSTEM", _("System")


class RequestStatus(models.TextChoices):
    CREATED = "CREATED", _("Created")
    SUBMITTED = "SUBMITTED", _("Submitted")
    UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
    APPROVED = "APPROVED", _("Approved")
    APPROVED_WITH_CONDITIONS = "APPROVED_COND", _("Approved with conditions")
    REFUSED = "REFUSED", _("Refused")
    INFO_REQUIRED = "INFO_REQUIRED", _("Further information required")
    SCHEDULED = "SCHEDULED", _("Scheduled")
    EXECUTED = "EXECUTED", _("Executed")
    CLOSED = "CLOSED", _("Closed")
    CANCELLED = "CANCELLED", _("Cancelled")
    EXPIRED = "EXPIRED", _("Expired")


REQUEST_TRANSITIONS: dict[str, set[str]] = {
    RequestStatus.CREATED: {RequestStatus.SUBMITTED, RequestStatus.CANCELLED},
    RequestStatus.SUBMITTED: {
        RequestStatus.UNDER_REVIEW, RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS,
        RequestStatus.REFUSED, RequestStatus.INFO_REQUIRED, RequestStatus.CANCELLED,
        RequestStatus.SCHEDULED, RequestStatus.EXECUTED,  # service orders (no deciding authority)
    },
    RequestStatus.UNDER_REVIEW: {
        RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS, RequestStatus.REFUSED,
        RequestStatus.INFO_REQUIRED, RequestStatus.CANCELLED,
    },
    RequestStatus.INFO_REQUIRED: {RequestStatus.SUBMITTED, RequestStatus.CANCELLED},
    RequestStatus.APPROVED: {RequestStatus.SCHEDULED, RequestStatus.EXECUTED, RequestStatus.CLOSED, RequestStatus.EXPIRED},
    RequestStatus.APPROVED_WITH_CONDITIONS: {
        RequestStatus.SCHEDULED, RequestStatus.EXECUTED, RequestStatus.CLOSED, RequestStatus.EXPIRED,
    },
    RequestStatus.SCHEDULED: {RequestStatus.EXECUTED, RequestStatus.CANCELLED, RequestStatus.EXPIRED},
    RequestStatus.EXECUTED: {RequestStatus.CLOSED},
    RequestStatus.REFUSED: {RequestStatus.CLOSED},
    RequestStatus.CLOSED: set(),
    RequestStatus.CANCELLED: set(),
    RequestStatus.EXPIRED: {RequestStatus.CLOSED},
}


class DocumentStatus(models.TextChoices):
    DRAFT = "DRAFT", _("Draft")
    ISSUED = "ISSUED", _("Issued")
    SIGNED = "SIGNED", _("Signed")
    CANCELLED = "CANCELLED", _("Cancelled")
    REPLACED = "REPLACED", _("Replaced")


class DisputeStatus(models.TextChoices):
    OPEN = "OPEN", _("Open")
    ANSWERED = "ANSWERED", _("Answered")
    CLOSED_AGREED = "CLOSED_AGREED", _("Closed — agreement")
    CLOSED_NOT_AGREED = "CLOSED_NOT_AGREED", _("Closed — no agreement")


class MeasurementParty(models.TextChoices):
    SHIP = "SHIP", _("Ship")
    SHORE = "SHORE", _("Shore")
    SURVEYOR = "SURVEYOR", _("Surveyor")


# Single emitter per value (rule 1)
MEASUREMENT_PARTY_ROLE = {
    MeasurementParty.SHIP: "NAV",
    MeasurementParty.SHORE: "TER",
    MeasurementParty.SURVEYOR: "INS",
}


class AlertKind(models.TextChoices):
    REMINDER = "REMINDER", _("Reminder")
    LATE = "LATE", _("Late task")
    ESCALATION = "ESCALATION", _("Escalation")
    HOLD_POINT = "HOLD_POINT", _("Hold point refusal")
    QUANTITY = "QUANTITY", _("Ship/shore discrepancy")
    AIS = "AIS", _("AIS divergence")
    COUNTERSIGN_TACIT = "TACIT", _("Tacit countersignature")
    CONFLICT = "CONFLICT", _("Synchronisation conflict")
    EXPIRY = "EXPIRY", _("Authorization expired")
    ASSISTANT = "ASSISTANT", _("Raised from the assistant review")


# ======================================================================================
# Reference data (per port, configured by the port's functional administrator)
# ======================================================================================
def _check_roles(value, field):
    unknown = [r for r in (value or []) if r not in ALL_ROLES and r != ANY_PARTY]
    if unknown:
        raise ValidationError({field: _("Unknown roles: %(r)s") % {"r": ", ".join(unknown)}})


class CargoKind(models.TextChoices):
    """What the vessel carries (FLX-CDC-002 v1.5, EXG-R-08): the platform is open to every cargo — the kind
    chooses the operation templates, the quantity units, the measurement methods and the safety checklist."""

    LIQUID = "LIQUID", _("Liquid bulk (petroleum, chemicals, vegetable oils, gas)")
    DRY = "DRY", _("Dry bulk (minerals, grain, clinker, fertiliser, coal…)")
    CONTAINER = "CONTAINER", _("Containers")
    GENERAL = "GENERAL", _("General cargo, breakbulk, project cargo, scrap")
    RORO = "RORO", _("Ro-ro: vehicles and rolling equipment")
    OTHER = "OTHER", _("Other (passengers, naval, fishing, research, no cargo)")


# Units of a declared quantity, by kind of cargo
QUANTITY_UNITS = [
    ("MT", "MT"), ("M3", "m³ @15°C"), ("BBL", "bbl @60°F"),
    ("TEU", "TEU"), ("BOX", _("boxes (containers)")), ("MOVES", _("moves (container)")),
    ("UNIT", _("units (vehicles, packages, pieces)")), ("M3B", _("m³ (bulk volume)")), ("PAX", _("passengers")),
]
UNITS_BY_CARGO = {
    CargoKind.LIQUID: ["MT", "M3", "BBL"], CargoKind.DRY: ["MT", "M3B"], CargoKind.CONTAINER: ["TEU", "BOX", "MOVES", "MT"],
    CargoKind.GENERAL: ["MT", "UNIT", "M3B"], CargoKind.RORO: ["UNIT", "MT"], CargoKind.OTHER: ["MT", "UNIT", "PAX"],
}


class VesselKind(models.TextChoices):
    TANKER_CRUDE = "TANKER_CRUDE", _("Crude oil tanker")
    TANKER_PRODUCT = "TANKER_PRODUCT", _("Product tanker")
    TANKER_CHEM = "TANKER_CHEM", _("Chemical tanker")
    GAS = "GAS", _("Gas carrier (LPG / LNG)")
    BULK = "BULK", _("Bulk carrier")
    CONTAINER = "CONTAINER", _("Container ship")
    GENERAL = "GENERAL", _("General cargo / multipurpose")
    RORO = "RORO", _("Ro-ro / vehicle carrier")
    REEFER = "REEFER", _("Reefer")
    PASSENGER = "PASSENGER", _("Passenger / cruise")
    OSV = "OSV", _("Offshore supply / service")
    TUG = "TUG", _("Tug / barge / workboat")
    NAVAL = "NAVAL", _("Naval / government vessel")
    FISHING = "FISHING", _("Fishing vessel")
    OTHER = "OTHER", _("Other")


class Vessel(models.Model):
    """Vessel particulars ("fiche navire"), per port. Created and maintained by the agency."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="vessels")
    imo = models.CharField(_("IMO number"), max_length=7)
    name = models.CharField(_("name"), max_length=120)
    flag = models.CharField(_("flag"), max_length=60, blank=True)
    vessel_kind = models.CharField(_("kind of vessel"), max_length=16, choices=VesselKind.choices, default=VesselKind.TANKER_PRODUCT)
    vessel_type = models.CharField(_("type (detail)"), max_length=60, blank=True, help_text=_("Crude, product, chemical, LPG, geared bulk carrier, PCTC…"))
    call_sign = models.CharField(_("call sign"), max_length=20, blank=True)
    mmsi = models.CharField(_("MMSI"), max_length=9, blank=True)
    dwt = models.PositiveIntegerField(_("DWT"), null=True, blank=True)
    loa_m = models.DecimalField(_("LOA (m)"), max_digits=6, decimal_places=2, null=True, blank=True)
    beam_m = models.DecimalField(_("beam (m)"), max_digits=5, decimal_places=2, null=True, blank=True)
    draft_m = models.DecimalField(_("summer draft (m)"), max_digits=5, decimal_places=2, null=True, blank=True)
    built_year = models.PositiveSmallIntegerField(_("year built"), null=True, blank=True)
    # particulars compared with the berth limits by the vetting checklist (EXG-R-10)
    displacement_t = models.PositiveIntegerField(_("displacement (t)"), null=True, blank=True)
    manifold_height_m = models.DecimalField(_("manifold height above waterline (m)"), max_digits=5, decimal_places=2, null=True, blank=True)
    air_draft_m = models.DecimalField(_("air draft (m)"), max_digits=5, decimal_places=2, null=True, blank=True)
    crane_swl_t = models.DecimalField(_("crane SWL (t)"), max_digits=5, decimal_places=1, null=True, blank=True)
    owner_name = models.CharField(_("registered owner"), max_length=160, blank=True)
    manager_name = models.CharField(_("manager / operator"), max_length=160, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()

    class Meta:
        ordering = ["name"]
        constraints = [models.UniqueConstraint(fields=["port", "imo"], name="uniq_vessel_imo_per_port")]
        verbose_name = _("vessel")
        verbose_name_plural = _("vessels")

    def __str__(self) -> str:
        return f"{self.name} (IMO {self.imo})"

    def clean(self):
        if not (self.imo.isdigit() and len(self.imo) == 7):
            raise ValidationError({"imo": _("An IMO number has seven digits.")})
        digits = [int(c) for c in self.imo]
        if sum(d * w for d, w in zip(digits[:6], range(7, 1, -1))) % 10 != digits[6]:
            raise ValidationError({"imo": _("Invalid IMO check digit.")})


class CallSequence(models.Model):
    """Gap-free yearly counters: calls [PORT]-[YYYY]-[SEQ] (EF-1.1), authorizations, disputes."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT)
    kind = models.CharField(max_length=4, default="CALL")
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port", "kind", "year"], name="uniq_call_sequence")]


class CallTemplate(models.Model):
    """A call model (M0…M9, MA1…MA3). Owned by the port authority; the engine is shared."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="templates")
    code = models.CharField(_("code"), max_length=10)
    kind = models.CharField(_("kind"), max_length=10, choices=TemplateKind.choices)
    name_fr = models.CharField(_("name (French)"), max_length=150)
    name_en = models.CharField(_("name (English)"), max_length=150)
    description_fr = models.TextField(_("description (French)"), blank=True)
    description_en = models.TextField(_("description (English)"), blank=True)
    berth_kinds = models.JSONField(
        _("applicable berth types"), default=list, blank=True, help_text=_("Empty = all types.")
    )
    cargo_kinds = models.JSONField(
        _("applicable kinds of cargo"), default=list, blank=True,
        help_text=_("Empty = every kind. The operation models of liquid bulk, dry bulk, containers… are offered by the kind of cargo of the call."),
    )
    requires_linked_call = models.BooleanField(
        _("links two calls"), default=False, help_text=_("STS and double banking connect two vessels.")
    )
    never_alone = models.BooleanField(_("cannot be used alone"), default=False, help_text=_("M9 grafts onto an operation."))
    # What the announcement asks for when this model is chosen (FLX-CDC-002 v1.6, EXG-R-11): the model's own
    # questions — grade and quantity of bunkers, hot work, number of holds, purpose and duration of a double
    # banking… — in the grammar of the request forms. The answers are kept on the call (operation_details), shown on
    # its overview and pre-fill the requests the model's tasks will raise (same keys).
    intake_schema = models.JSONField(
        _("questions asked at the announcement"), default=list, blank=True,
        help_text=_('List of {"key", "label_fr", "label_en", "type", "required", "options", "help_fr", "help_en"} — '
                    'the same grammar as the form of a request type; a key shared with the form of a request raised '
                    "by this model's tasks pre-fills that request."),
    )
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["port", "order", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_template_code_per_port")]
        verbose_name = _("call template")
        verbose_name_plural = _("call templates")

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"

    def clean(self):
        for field in self.intake_schema or []:
            if not isinstance(field, dict) or not field.get("key") or not field.get("type"):
                raise ValidationError({"intake_schema": _("Each field needs at least a key and a type.")})

    @property
    def name(self) -> str:
        return pick(self.name_fr, self.name_en)

    @property
    def published_version(self):
        return self.versions.filter(status=TemplateVersion.Status.PUBLISHED).order_by("-number").first()


class TemplateVersion(models.Model):
    """A frozen version of a template. A call keeps the version in force at its creation (EF-5.8)."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        PUBLISHED = "PUBLISHED", _("Published")
        RETIRED = "RETIRED", _("Retired")

    template = models.ForeignKey(CallTemplate, on_delete=models.PROTECT, related_name="versions")
    number = models.PositiveIntegerField(_("version"))
    status = models.CharField(_("status"), max_length=10, choices=Status.choices, default=Status.DRAFT)
    notes = models.TextField(_("change notes"), blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["template", "-number"]
        constraints = [models.UniqueConstraint(fields=["template", "number"], name="uniq_template_version")]
        verbose_name = _("template version")
        verbose_name_plural = _("template versions")

    def __str__(self) -> str:
        return f"{self.template.code} v{self.number} ({self.get_status_display()})"

    @property
    def is_editable(self) -> bool:
        return self.status == self.Status.DRAFT


class TemplateTask(models.Model):
    """A line of a call template (FLX-SPEC-002): who does what, by when, and whether it blocks."""

    version = models.ForeignKey(TemplateVersion, on_delete=models.PROTECT, related_name="tasks")
    number = models.CharField(_("number"), max_length=10, help_text=_("e.g. 01, 1.05, A1.02"))
    section_fr = models.CharField(_("section (French)"), max_length=150, blank=True)
    section_en = models.CharField(_("section (English)"), max_length=150, blank=True)
    title_fr = models.CharField(_("task (French)"), max_length=400)
    title_en = models.CharField(_("task (English)"), max_length=400)
    role = models.CharField(_("assigned role"), max_length=3, choices=[*Role.choices, (ANY_PARTY, _("Any party"))])
    co_roles = models.JSONField(
        _("co-signing roles"), default=list, blank=True,
        help_text=_("Roles that sign or countersign the task, e.g. [\"NAV\", \"TER\"]."),
    )
    joint = models.BooleanField(
        _("joint signature required"), default=False,
        help_text=_("The task is done only when the assigned role and every co-signing role have signed."),
    )
    nature = models.CharField(_("nature"), max_length=1, choices=Nature.choices)
    anchor = models.CharField(_("deadline anchor"), max_length=3, choices=Anchor.choices, blank=True)
    offset_minutes = models.IntegerField(_("offset from anchor (minutes)"), default=0)
    timing_fr = models.CharField(_("deadline label (French)"), max_length=60, blank=True)
    timing_en = models.CharField(_("deadline label (English)"), max_length=60, blank=True)
    criticality = models.CharField(_("criticality"), max_length=1, choices=Criticality.choices)
    confidentiality = models.CharField(
        _("confidentiality"), max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2
    )
    hold_basis = models.CharField(
        _("basis of the blocking character"), max_length=200, blank=True,
        help_text=_("Hold point of PRO-MAR-001 or regulatory obligation. Required for a blocking task."),
    )
    request_type_code = models.CharField(_("linked request type"), max_length=40, blank=True)
    request_side = models.CharField(
        _("request side"), max_length=8, blank=True,
        choices=[("submit", _("Completed by submitting the request")), ("decide", _("Completed by the decision"))],
    )
    milestone_codes = models.JSONField(_("milestones that complete the task"), default=list, blank=True)
    document_type_code = models.CharField(_("expected document type"), max_length=40, blank=True)
    auto_event = models.CharField(
        _("completed by platform event"), max_length=30, blank=True,
        choices=[("call.created", _("Call created")), ("call.declared", _("Call declared"))],
    )
    continuous = models.BooleanField(_("continuous task"), default=False, help_text=_("Kept open until T1 (pumping log, interruptions)."))
    per_vessel = models.BooleanField(_("one per vessel (×2)"), default=False)
    not_applicable_allowed = models.BooleanField(_("may be marked not applicable"), default=True)
    berth_kinds = models.JSONField(
        _("only for these operating areas"), default=list, blank=True,
        help_text=_("Operation × berth type: empty = every area; e.g. [\"JETTY\", \"SPM\"] for ship/shore interface tasks."),
    )
    # A green light (FLX-CDC-002 v1.5, EXG-R-03): a go-ahead given by a party — harbour master, naval base,
    # terminal, principal… — shown on the call's green-light panel, withdrawable with a reason
    green_light = models.BooleanField(_("green light"), default=False,
                                      help_text=_("Shown on the green-light panel of the call; the party may withdraw it with a reason."))
    cargo_kinds = models.JSONField(
        _("only for these kinds of cargo"), default=list, blank=True,
        help_text=_("Empty = every kind; e.g. [\"LIQUID\"] for a tanker-only task of the common base."),
    )
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["version", "order", "number"]
        constraints = [models.UniqueConstraint(fields=["version", "number"], name="uniq_task_number_per_version")]
        verbose_name = _("template task")
        verbose_name_plural = _("template tasks")

    def __str__(self) -> str:
        return f"{self.version.template.code}:{self.number} {self.title}"

    @property
    def title(self) -> str:
        return pick(self.title_fr, self.title_en)

    def clean(self):
        _check_roles([self.role], "role")
        _check_roles(self.co_roles, "co_roles")
        if self.criticality == Criticality.BLOCKING and not self.hold_basis.strip():
            raise ValidationError(
                {"hold_basis": _("A blocking task must be tied to a hold point of PRO-MAR-001 or to a regulatory obligation.")}
            )
        if not self.anchor and self.offset_minutes:
            raise ValidationError({"offset_minutes": _("An offset requires an anchor (ETA, ETB, ATB, T0, T1, ATD, NOR).")})
        if abs(self.offset_minutes) > 60 * 24 * 60:
            raise ValidationError({"offset_minutes": _("Offset out of range (60 days maximum).")})
        if self.confidentiality == Confidentiality.N4:
            raise ValidationError(
                {"confidentiality": _("N4 tasks live in the security domain and cannot be part of an operational template.")}
            )
        if self.version_id and not self.version.is_editable:
            raise ValidationError(_("A published version is frozen. Create a new draft version."))

    def save(self, *args, **kwargs):
        if self.version_id and not self.version.is_editable:
            from apps.core.guards import ImmutableRecordError

            raise ImmutableRecordError("A published template version is frozen; create a new draft version.")
        super().save(*args, **kwargs)


class HoldPoint(models.Model):
    """A guarded transition and the blocking template tasks it requires (EF-11)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="hold_points")
    transition = models.CharField(_("transition"), max_length=24, choices=Transition.choices)
    description_fr = models.CharField(_("description (French)"), max_length=300, blank=True)
    description_en = models.CharField(_("description (English)"), max_length=300, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port", "transition"], name="uniq_hold_point")]
        verbose_name = _("hold point")
        verbose_name_plural = _("hold points")

    def __str__(self) -> str:
        return f"{self.port.code} — {self.get_transition_display()}"


class HoldPointRequirement(models.Model):
    hold_point = models.ForeignKey(HoldPoint, on_delete=models.CASCADE, related_name="requirements")
    template_code = models.CharField(_("template"), max_length=10)
    task_number = models.CharField(_("task number"), max_length=10)

    class Meta:
        ordering = ["template_code", "task_number"]
        constraints = [
            models.UniqueConstraint(fields=["hold_point", "template_code", "task_number"], name="uniq_hold_requirement")
        ]

    def __str__(self) -> str:
        return f"{self.template_code}:{self.task_number}"


class InterruptionCause(models.Model):
    """Closed list of interruption causes, negotiated with the parties (EF-3.5)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="interruption_causes")
    code = models.CharField(_("code"), max_length=30)
    label_fr = models.CharField(_("label (French)"), max_length=200)
    label_en = models.CharField(_("label (English)"), max_length=200)
    attributable_to = models.CharField(
        _("attributable to"), max_length=10, blank=True,
        choices=[("SHIP", _("Ship")), ("SHORE", _("Shore")), ("THIRD", _("Third party / external")), ("WEATHER", _("Weather"))],
    )
    requires_reason = models.BooleanField(_("reason mandatory (\"Other\")"), default=False)
    is_active = models.BooleanField(_("active"), default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["port", "order", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_cause_code_per_port")]
        verbose_name = _("interruption cause")
        verbose_name_plural = _("interruption causes")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return pick(self.label_fr, self.label_en)


class MilestoneType(models.Model):
    """An event of FLX-SPEC-001 §7: single emitter, countersigners, contesters."""

    ORIGIN = "ORIGIN"  # interruptions: the party at the origin records (terminal by default)
    SYSTEM = "SYSTEM"  # recorded by the platform as a consequence of another act

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="milestone_types")
    code = models.CharField(_("code"), max_length=30)
    number = models.PositiveSmallIntegerField(_("matrix number"), default=0)
    label_fr = models.CharField(_("label (French)"), max_length=200)
    label_en = models.CharField(_("label (English)"), max_length=200)
    emitter_role = models.CharField(
        _("single emitter"), max_length=6,
        choices=[*Role.choices, (ORIGIN, _("Party at the origin")), (SYSTEM, _("Platform"))],
    )
    countersigner_roles = models.JSONField(_("countersigners"), default=list, blank=True)
    contester_roles = models.JSONField(_("may contest"), default=list, blank=True, help_text=_('["*"] = every party'))
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N1)
    ais_corroboration = models.BooleanField(_("AIS corroboration"), default=False)
    requires_cause = models.BooleanField(_("cause from the closed list required"), default=False)
    closes_type = models.CharField(_("closes the interval opened by"), max_length=30, blank=True)
    repeatable = models.BooleanField(_("may occur several times"), default=False)
    hold_point = models.CharField(_("guarded by hold point"), max_length=24, choices=Transition.choices, blank=True)
    sets_anchor = models.CharField(
        _("sets the actual time"), max_length=4, blank=True,
        choices=[("ATA", "ATA"), ("ATB", "ATB"), ("T0", "T0"), ("T1", "T1"), ("ATD", "ATD"), ("NOR", "NOR")],
    )
    sets_status = models.CharField(_("moves the call to"), max_length=14, choices=CallStatus.choices, blank=True)
    completes_tasks = models.JSONField(
        _("completes template tasks"), default=list, blank=True, help_text=_('e.g. ["M1:1.09"]')
    )
    auto_from_task = models.CharField(
        _("recorded automatically when this task is done"), max_length=16, blank=True, help_text=_('e.g. "M0:28"')
    )
    field_entry = models.BooleanField(_("offered in the field app"), default=True)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["port", "order", "number"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_milestone_type_per_port")]
        verbose_name = _("milestone type")
        verbose_name_plural = _("milestone types")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return pick(self.label_fr, self.label_en)

    def clean(self):
        _check_roles(self.countersigner_roles, "countersigner_roles")
        _check_roles([r for r in self.contester_roles if r != "*"], "contester_roles")
        if self.confidentiality == Confidentiality.N4:
            raise ValidationError({"confidentiality": _("N4 events belong to the security domain.")})


class RequestType(models.Model):
    """A configurable request/authorization type (EF-2.2): no development per type."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="request_types")
    code = models.CharField(_("code"), max_length=40)
    label_fr = models.CharField(_("label (French)"), max_length=200)
    label_en = models.CharField(_("label (English)"), max_length=200)
    description_fr = models.TextField(blank=True)
    description_en = models.TextField(blank=True)
    requester_roles = models.JSONField(_("requesting roles"), default=list)
    decision_roles = models.JSONField(_("deciding authorities"), default=list)
    executor_role = models.CharField(_("executing role"), max_length=3, blank=True, choices=Role.choices)
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    refusal_confidentiality = models.CharField(
        _("confidentiality of the refusal reason"), max_length=2, choices=Confidentiality.choices,
        default=Confidentiality.N2,
    )
    form_schema = models.JSONField(
        _("form fields"), default=list, blank=True,
        help_text=_('List of {"key", "label_fr", "label_en", "type", "required", "options"}.'),
    )
    expected_documents = models.JSONField(_("expected document types"), default=list, blank=True)
    processing_minutes = models.PositiveIntegerField(_("processing time (minutes)"), default=240)
    validity_hours = models.PositiveIntegerField(
        _("default validity of the authorization (hours)"), default=72,
        help_text=_("An authorization always carries an expiry date (EF-2.5)."),
    )
    is_vetting = models.BooleanField(_("vessel acceptance (vetting)"), default=False)
    hold_point = models.CharField(_("decision guarded by"), max_length=24, choices=Transition.choices, blank=True)
    submit_completes = models.JSONField(_("submission completes tasks"), default=list, blank=True)
    decision_completes = models.JSONField(_("decision completes tasks"), default=list, blank=True)
    execution_completes = models.JSONField(_("execution completes tasks"), default=list, blank=True)
    approval_milestone = models.CharField(_("milestone recorded on approval"), max_length=30, blank=True)
    approval_status = models.CharField(_("call status on approval"), max_length=14, blank=True, choices=CallStatus.choices)
    refusal_status = models.CharField(_("call status on refusal"), max_length=14, blank=True, choices=CallStatus.choices)
    assigns_berth = models.BooleanField(_("the decision assigns a berth"), default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["port", "order", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_request_type_per_port")]
        verbose_name = _("request type")
        verbose_name_plural = _("request types")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return pick(self.label_fr, self.label_en)

    def clean(self):
        _check_roles(self.requester_roles, "requester_roles")
        _check_roles(self.decision_roles, "decision_roles")
        overlap = set(self.requester_roles) & set(self.decision_roles)
        if overlap:
            raise ValidationError(
                {"decision_roles": _("A requesting role can never decide (rule 2): %(r)s") % {"r": ", ".join(sorted(overlap))}}
            )
        if self.confidentiality == Confidentiality.N4:
            raise ValidationError({"confidentiality": _("N4 requests are filed in the security domain.")})
        for field in self.form_schema or []:
            if not isinstance(field, dict) or not field.get("key") or not field.get("type"):
                raise ValidationError({"form_schema": _("Each field needs at least a key and a type.")})


class DocumentType(models.Model):
    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="document_types")
    code = models.CharField(_("code"), max_length=40)
    label_fr = models.CharField(_("label (French)"), max_length=200)
    label_en = models.CharField(_("label (English)"), max_length=200)
    default_confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    issuer_roles = models.JSONField(_("issuing roles"), default=list, blank=True)
    signer_roles = models.JSONField(_("required signatories"), default=list, blank=True)
    audience_roles = models.JSONField(_("additional readers (N2)"), default=list, blank=True)
    # readers limited to the issuer and the list above: the coordinating roles (agency, harbour master, port
    # management) and the owner are NOT added by the N2 rule — a laboratory's quality certificate is read by the
    # terminal, the trader, the vessel, the surveyor and the port only (FLX-CDC-002 v1.4, EXG-Q-06)
    readers_exact = models.BooleanField(
        _("readers limited to the list above"), default=False,
        help_text=_("When set, only the issuer and the readers listed above see the document: the agency, the "
                    "harbour master, the port management and the owner are not added automatically."),
    )
    retention_years = models.PositiveSmallIntegerField(_("retention (years)"), default=10)
    generated = models.BooleanField(_("generated from the registry"), default=False)
    is_bill_of_lading = models.BooleanField(_("bill of lading (locked)"), default=False)
    is_active = models.BooleanField(default=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["port", "order", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_doc_type_per_port")]
        verbose_name = _("document type")
        verbose_name_plural = _("document types")

    def __str__(self) -> str:
        return self.label

    @property
    def label(self) -> str:
        return pick(self.label_fr, self.label_en)


class ReportAccess(models.Model):
    """Who reads each live report and board of the port — decided at parametrage, never in code (FLX-CDC-002
    v1.4, EXG-Q-08): the pumping log, the tank measurements once validated, the ship/shore safety checklist and
    the port call board. The documents (time sheet, statement of facts, certificates) have their readers on
    their document type."""

    class Report(models.TextChoices):
        PUMPING_LOG = "PUMPING_LOG", _("Pumping log (ship and shore readings, deviation)")
        MEASUREMENTS = "MEASUREMENTS", _("Measurements and validated tank readings")
        SAFETY_CHECKLIST = "SAFETY_CHECKLIST", _("Ship/shore safety checklist (reading)")
        CALL_BOARD = "CALL_BOARD", _("Port call board (expected, alongside, departed)")

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="report_access")
    code = models.CharField(_("report"), max_length=20, choices=Report.choices)
    reader_roles = models.JSONField(_("reading roles"), default=list, blank=True)
    note = models.CharField(_("note"), max_length=300, blank=True)

    class Meta:
        ordering = ["port", "code"]
        constraints = [models.UniqueConstraint(fields=["port", "code"], name="uniq_report_access_per_port")]
        verbose_name = _("report access")
        verbose_name_plural = _("report access")

    def __str__(self) -> str:
        return f"{self.get_code_display()} — {', '.join(self.reader_roles)}"

    def clean(self):
        _check_roles(self.reader_roles, "reader_roles")


# Readers of each report when the port has not decided otherwise (ReportAccess rows are created at bootstrap)
DEFAULT_REPORT_READERS: dict[str, list[str]] = {
    # the harbour master, the surveyor, the superintendent and the trader (owner / charterer side), the port
    # management, the agency that coordinates the call — and the two parties that keep it
    "PUMPING_LOG": ["NAV", "TER", "CAP", "INS", "COM", "DIR", "AGE"],
    "MEASUREMENTS": ["NAV", "TER", "CAP", "INS", "COM", "DIR", "AGE"],
    "SAFETY_CHECKLIST": ["NAV", "TER", "CAP", "APO", "INS", "AGE", "SUR", "DIR"],
    "CALL_BOARD": ["AGE", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "PRE", "DIR"],
}


class PortDefaultParty(models.Model):
    """Organisations automatically invited on every call of the port (authorities, nautical services…)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="default_parties")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    role = models.CharField(max_length=3, choices=Role.choices)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port", "organization", "role"], name="uniq_default_party")]
        verbose_name = _("default party")
        verbose_name_plural = _("default parties")

    def __str__(self) -> str:
        return f"{self.organization} — {self.role}"


# ======================================================================================
# The call
# ======================================================================================
class StsRole(models.TextChoices):
    DONOR = "DONOR", _("Delivers the cargo (discharging vessel)")
    RECEIVER = "RECEIVER", _("Receives the cargo (receiving vessel)")


class PortCall(NoDeleteModel):
    """A vessel's call ("escale"), whatever its cargo. Created by the agency only (EF-1.1); reference immutable."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="calls")
    reference = models.CharField(_("reference"), max_length=30, unique=True, editable=False)
    vessel = models.ForeignKey(Vessel, on_delete=models.PROTECT, related_name="calls")
    voyage_number = models.CharField(_("voyage number"), max_length=40, blank=True)
    agency = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+", verbose_name=_("agency"))
    status = models.CharField(_("status"), max_length=14, choices=CallStatus.choices, default=CallStatus.DRAFT)
    requested_berth_kind = models.CharField(_("operating area"), max_length=12, choices=Berth.Kind.choices)
    requested_berth = models.ForeignKey(Berth, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    berth = models.ForeignKey(Berth, on_delete=models.PROTECT, null=True, blank=True, related_name="calls")
    cargo_kind = models.CharField(_("kind of cargo"), max_length=10, choices=CargoKind.choices, default=CargoKind.LIQUID)
    product = models.CharField(_("product / nature of the cargo"), max_length=120, blank=True)
    quantity = models.DecimalField(_("declared quantity"), max_digits=14, decimal_places=3, null=True, blank=True)
    quantity_unit = models.CharField(_("unit"), max_length=8, default="MT", choices=QUANTITY_UNITS)
    last_port = models.CharField(_("last port"), max_length=80, blank=True)
    next_port = models.CharField(_("next port"), max_length=80, blank=True)
    # Performance basis of the time sheet (FLX-CDC-002 v1.4, EXG-Q-02): the pumping time the charter-party or the
    # terminal allows, and the cargo batch the terminal nominates
    planned_pump_hours = models.DecimalField(_("planned pumping time (h)"), max_digits=6, decimal_places=2, null=True, blank=True)
    batch_reference = models.CharField(_("batch reference"), max_length=60, blank=True)
    # Estimates (agency) — every relative deadline is recomputed when they change (EF-5.4)
    eta = models.DateTimeField(_("ETA"))
    etb = models.DateTimeField(_("ETB"), null=True, blank=True)
    ets = models.DateTimeField(_("estimated start of operations"), null=True, blank=True)
    etc = models.DateTimeField(_("estimated completion"), null=True, blank=True)
    etd = models.DateTimeField(_("ETD"), null=True, blank=True)
    # Actuals — set only by recorded milestones
    ata = models.DateTimeField(_("actual arrival"), null=True, blank=True, editable=False)
    atb = models.DateTimeField(_("all fast"), null=True, blank=True, editable=False)
    t0 = models.DateTimeField(_("start of transfer"), null=True, blank=True, editable=False)
    t1 = models.DateTimeField(_("end of transfer"), null=True, blank=True, editable=False)
    atd = models.DateTimeField(_("actual departure"), null=True, blank=True, editable=False)
    nor_at = models.DateTimeField(_("NOR tendered"), null=True, blank=True, editable=False)
    linked_call = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    link_kind = models.CharField(
        max_length=12, blank=True,
        choices=[("STS", _("STS partner")), ("INNER", _("Inner vessel (double banking)")), ("OUTER", _("Outer vessel"))],
    )
    # In a ship-to-ship transfer each vessel has its own call, its own agency and its own team (EXG-R-05): this
    # says which of the two this vessel is
    sts_role = models.CharField(_("role in the STS transfer"), max_length=8, choices=StsRole.choices, blank=True)
    # What the agency declared at the announcement for each operation model chosen (v1.6, EXG-R-11): the answers
    # to the model's own questions, keyed by template code — {"M4": {"grade": "VLSFO", "quantity_mt": 450}, …}
    operation_details = models.JSONField(_("information declared for each operation"), default=dict, blank=True)
    # Validity of the announcement (EXG-R-02): fixed at creation, kept for billing; the call is obsolete after it
    # unless the vessel is already alongside
    validity_days = models.PositiveSmallIntegerField(_("validity of the announcement (days)"), default=15)
    valid_until = models.DateTimeField(_("announcement valid until"), null=True, blank=True)
    expired_at = models.DateTimeField(_("became obsolete at"), null=True, blank=True)
    renewed_from = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="renewals",
                                     verbose_name=_("announced again from"))
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    declared_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-eta"]
        indexes = [models.Index(fields=["port", "status"]), models.Index(fields=["port", "eta"])]
        verbose_name = _("port call")
        verbose_name_plural = _("port calls")

    def __str__(self) -> str:
        return f"{self.reference} — {self.vessel.name}"

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = PortCall.objects.filter(pk=self.pk).values_list("reference", flat=True).first()
            if original is not None and original != self.reference:
                from apps.core.guards import ImmutableRecordError

                raise ImmutableRecordError("A call reference is immutable.")
        super().save(*args, **kwargs)

    def anchor_time(self, anchor: str):
        """Actual time when known, otherwise the best estimate."""
        if anchor == Anchor.NOM:
            return self.created_at
        if anchor == Anchor.ETA:
            return self.ata or self.eta
        if anchor == Anchor.ETB:
            return self.atb or self.etb or (self.eta + timedelta(hours=6) if self.eta else None)
        if anchor == Anchor.ATB:
            return self.atb or self.etb
        if anchor == Anchor.T0:
            return self.t0 or self.ets or (self.atb + timedelta(hours=3) if self.atb else None) or (
                self.etb + timedelta(hours=3) if self.etb else None
            )
        if anchor == Anchor.T1:
            return self.t1 or self.etc
        if anchor == Anchor.ATD:
            return self.atd or self.etd
        if anchor == Anchor.NOR:
            return self.nor_at
        return None

    @property
    def is_terminal_state(self) -> bool:
        return self.status in {CallStatus.CLOSED, CallStatus.ARCHIVED, CallStatus.REJECTED, CallStatus.CANCELLED,
                               CallStatus.EXPIRED}

    @property
    def is_sts(self) -> bool:
        return self.link_kind == "STS" or bool(self.sts_role)

    @property
    def validity_remaining(self) -> timedelta | None:
        """Time left before the announcement runs out (negative once overrun); None when no validity was fixed."""
        if self.valid_until is None:
            return None
        return self.valid_until - timezone.now()

    @property
    def validity_overrun(self) -> bool:
        return self.valid_until is not None and timezone.now() > self.valid_until and not self.is_terminal_state

    def billing_basis(self) -> dict:
        """What the port bills on (EXG-R-02): the validity fixed at the announcement, the time actually spent in
        the port and any overrun of the validity."""
        end = self.atd or self.closed_at or self.expired_at or timezone.now()
        in_port = (end - self.ata) if self.ata else None
        overrun = (end - self.valid_until) if self.valid_until and end > self.valid_until else None
        return {"validity_days": self.validity_days, "valid_from": self.created_at, "valid_until": self.valid_until,
                "arrived_at": self.ata, "departed_at": self.atd, "closed_at": self.closed_at, "expired_at": self.expired_at,
                "hours_in_port": round(in_port.total_seconds() / 3600, 1) if in_port else None,
                "overrun_hours": round(overrun.total_seconds() / 3600, 1) if overrun else None}

    @property
    def template_codes(self) -> list[str]:
        return list(self.template_uses.values_list("template_version__template__code", flat=True))


class CallStage(NoDeleteModel):
    """One operating area of a call, in sequence: a call may go from the roads or an STS area to the quay, from
    a buoy to the quay, from the quay back to an anchorage… Each stage has its own berth, its own operations
    (templates added when the stage is planned), its own berthing and leaving times. The first stage is created
    with the call; the agency or the harbour master plans the next ones; a movement authorization in force is
    needed to leave a stage (SHIFT_START) and to berth at the next one."""

    class Status(models.TextChoices):
        PLANNED = "PLANNED", _("Planned")
        CURRENT = "CURRENT", _("Current")
        DONE = "DONE", _("Done")
        CANCELLED = "CANCELLED", _("Cancelled")

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="stages")
    order = models.PositiveSmallIntegerField(_("order"))
    berth_kind = models.CharField(_("operating area"), max_length=12, choices=Berth.Kind.choices)
    berth = models.ForeignKey(Berth, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                              verbose_name=_("berth / area"))
    operations = models.JSONField(_("operation templates of this stage"), default=list, blank=True)
    planned_from = models.DateTimeField(_("planned from"), null=True, blank=True)
    planned_to = models.DateTimeField(_("planned to"), null=True, blank=True)
    atb = models.DateTimeField(_("all fast / alongside at this stage"), null=True, blank=True)
    atd = models.DateTimeField(_("left this stage"), null=True, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PLANNED)
    reason = models.CharField(_("reason"), max_length=300, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(default=timezone.now)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["call", "order"]
        constraints = [models.UniqueConstraint(fields=["call", "order"], name="uniq_call_stage_order")]
        verbose_name = _("call stage")
        verbose_name_plural = _("call stages")

    def __str__(self) -> str:
        return f"{self.call.reference} — {self.order}. {self.get_berth_kind_display()}"

    @property
    def label(self) -> str:
        where = self.berth.code if self.berth_id else self.get_berth_kind_display()
        return f"{self.order}. {where}"


class CallTemplateUse(models.Model):
    """Which template versions a call instantiated — kept forever for interpretability."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="template_uses")
    template_version = models.ForeignKey(TemplateVersion, on_delete=models.PROTECT, related_name="+")

    class Meta:
        constraints = [models.UniqueConstraint(fields=["call", "template_version"], name="uniq_call_template")]


class CallParty(NoDeleteModel):
    """Role on a call (EF-12.1): dated and revocable; revocation never purges history."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="parties")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="call_roles")
    role = models.CharField(max_length=3, choices=Role.choices)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_until = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    revoke_reason = models.CharField(max_length=300, blank=True)
    granted_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    is_default = models.BooleanField(default=False)
    # TER or PRE party designated to speak for the shore side when several organisations hold that role on the call
    shore_side = models.BooleanField(default=False)
    # Controlled access given by the principal agent (FLX-CDC-002 v1.5, EXG-R-04): the whole file, a part of it
    # (the tabs listed in *scopes*, with the right to act in them) or reading only
    class Access(models.TextChoices):
        FULL = "FULL", _("Full access (every tab, acts within its role)")
        PARTIAL = "PARTIAL", _("Partial access (the tabs listed, acts within them)")
        READ = "READ", _("Reading only (every tab, no act)")

    access = models.CharField(_("access to the file"), max_length=7, choices=Access.choices, default=Access.FULL)
    scopes = models.JSONField(_("tabs of a partial access"), default=list, blank=True,
                              help_text=_("Tab codes, e.g. [\"taches\", \"documents\"]."))
    access_set_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    access_set_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["call", "organization", "role"], condition=Q(revoked_at__isnull=True),
                name="uniq_active_call_party",
            )
        ]
        indexes = [models.Index(fields=["organization", "role"])]
        verbose_name = _("role on call")
        verbose_name_plural = _("roles on call")

    def __str__(self) -> str:
        return f"{self.call.reference} — {self.organization} ({self.role})"

    def is_active_at(self, when=None) -> bool:
        when = when or timezone.now()
        return (
            self.revoked_at is None
            and self.valid_from <= when
            and (self.valid_until is None or when < self.valid_until)
        )

    @property
    def is_principal(self) -> bool:
        """The principal agent: the agency that created the call answers for the file and grants the others their access."""
        return self.role == "AGE" and self.organization_id == self.call.agency_id


def _new_token() -> str:
    return secrets.token_urlsafe(32)


class MasterAccessLink(NoDeleteModel):
    """Account-less access to one call (EF-13): the master's, or a party's (terminal, surveyor, owner, provider,
    marine service) that has no account. Limited validity, revocable, traced; never a deciding role."""

    class Channel(models.TextChoices):
        EMAIL = "EMAIL", _("E-mail")
        QR = "QR", _("QR code handed over")
        PRINT = "PRINT", _("Printed")
        SMS = "SMS", _("SMS")
        OTHER = "OTHER", _("Other")

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="master_links")
    master_name = models.CharField(_("holder's name"), max_length=160, blank=True,
                                   help_text=_("Nominative: entered at issuance, or by the holder at first use."))
    role = models.CharField(_("role exercised"), max_length=3, default="NAV")
    organization = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="access_links", verbose_name=_("party organisation"))
    auto_issued = models.BooleanField(_("issued by the platform at the declaration"), default=False)
    sent_to = models.EmailField(_("sent to"), blank=True)
    vessel_position = models.CharField(
        max_length=6, default="OWN", choices=[("OWN", _("Own vessel")), ("INNER", _("Inner vessel (double banking)"))]
    )
    token_hash = models.CharField(max_length=64, unique=True, editable=False)
    code_hash = models.CharField(max_length=64, unique=True, editable=False)
    issued_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    issued_at = models.DateTimeField(auto_now_add=True)
    delivery_channel = models.CharField(max_length=6, choices=Channel.choices, default=Channel.EMAIL)
    delivery_note = models.CharField(max_length=300, blank=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    revoke_reason = models.CharField(max_length=300, blank=True)
    last_used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-issued_at"]
        verbose_name = _("access link")
        verbose_name_plural = _("access links")

    def __str__(self) -> str:
        return f"{self.call.reference} — {self.master_name or self.organization or self.role} ({self.role})"

    @property
    def is_master(self) -> bool:
        return self.role == "NAV"

    @property
    def holder_name(self) -> str:
        return self.master_name

    def is_valid(self, when=None) -> bool:
        """The master's link ends shortly after departure (the ship leaves); a party's link lasts until the
        closure of the call, within its own expiry."""
        when = when or timezone.now()
        if self.revoked_at is not None or when >= self.expires_at:
            return False
        call = self.call
        if self.is_master and call.atd and when >= call.atd + timedelta(hours=call.port.master_link_grace_hours):
            return False
        return not call.is_terminal_state


# ======================================================================================
# Tasks
# ======================================================================================
class Task(NoDeleteModel):
    """A task instantiated from a template version, assigned to a role — never to a person (EF-5.2)."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="tasks")
    stage = models.ForeignKey(CallStage, on_delete=models.PROTECT, null=True, blank=True, related_name="tasks",
                              help_text=_("Empty for the tasks of the call as a whole (common base and first stage); "
                                          "set for the tasks added with a later stage."))
    template_task = models.ForeignKey(TemplateTask, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    template_code = models.CharField(max_length=10, blank=True)
    number = models.CharField(max_length=10)
    section_fr = models.CharField(max_length=150, blank=True)
    section_en = models.CharField(max_length=150, blank=True)
    title_fr = models.CharField(max_length=400)
    title_en = models.CharField(max_length=400)
    role = models.CharField(max_length=3)
    co_roles = models.JSONField(default=list, blank=True)
    joint = models.BooleanField(default=False)
    nature = models.CharField(max_length=1, choices=Nature.choices)
    criticality = models.CharField(max_length=1, choices=Criticality.choices)
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    anchor = models.CharField(max_length=3, choices=Anchor.choices, blank=True)
    offset_minutes = models.IntegerField(default=0)
    timing_fr = models.CharField(max_length=60, blank=True)
    timing_en = models.CharField(max_length=60, blank=True)
    request_type_code = models.CharField(max_length=40, blank=True)
    request_side = models.CharField(max_length=8, blank=True)
    milestone_codes = models.JSONField(default=list, blank=True)
    document_type_code = models.CharField(max_length=40, blank=True)
    auto_event = models.CharField(max_length=30, blank=True)
    continuous = models.BooleanField(default=False)
    not_applicable_allowed = models.BooleanField(default=True)
    is_ad_hoc = models.BooleanField(_("ad hoc task"), default=False)
    green_light = models.BooleanField(default=False)
    # a document the agency asked for at the announcement, beyond the templates (EXG-R-06)
    requested_at_creation = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    due_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=8, choices=TaskStatus.choices, default=TaskStatus.PENDING)
    alert_level = models.CharField(max_length=10, choices=AlertLevel.choices, default=AlertLevel.NONE)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_role = models.CharField(max_length=3, blank=True)
    completed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    completed_by_master = models.ForeignKey(
        MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    completion_note = models.TextField(blank=True)
    na_reason = models.TextField(blank=True)
    evidence = models.CharField(max_length=60, blank=True, help_text="kind:id of the object proving completion")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["call", "order", "number"]
        indexes = [models.Index(fields=["call", "role"]), models.Index(fields=["status", "due_at"])]
        verbose_name = _("task")
        verbose_name_plural = _("tasks")

    def __str__(self) -> str:
        return f"{self.call.reference} {self.code} {self.title}"

    @property
    def code(self) -> str:
        return f"{self.template_code}:{self.number}" if self.template_code else self.number

    @property
    def title(self) -> str:
        return pick(self.title_fr, self.title_en)

    @property
    def section(self) -> str:
        return pick(self.section_fr, self.section_en)

    @property
    def timing(self) -> str:
        return pick(self.timing_fr, self.timing_en)

    @property
    def is_blocking(self) -> bool:
        return self.criticality == Criticality.BLOCKING

    @property
    def is_open(self) -> bool:
        return self.status == TaskStatus.PENDING

    @property
    def all_roles(self) -> list[str]:
        return [self.role, *[r for r in self.co_roles if r != self.role]]


class TaskSignature(AppendOnlyModel):
    """Signature / countersignature / contest on a task (joint tasks, co-signed entries)."""

    class Kind(models.TextChoices):
        SIGNED = "SIGNED", _("Signed")
        COUNTERSIGNED = "COUNTERSIGNED", _("Countersigned")
        CONTESTED = "CONTESTED", _("Contested")
        TACIT = "TACIT", _("Tacit countersignature")

    task = models.ForeignKey(Task, on_delete=models.PROTECT, related_name="signatures")
    role = models.CharField(max_length=3)
    kind = models.CharField(max_length=14, choices=Kind.choices)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    signer_label = models.CharField(max_length=200)
    signed_at = models.DateTimeField(default=timezone.now)
    comment = models.TextField(blank=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["signed_at"]


# ======================================================================================
# Milestones (events) and countersignatures
# ======================================================================================
class Milestone(AppendOnlyModel):
    """A dated fact with a single emitter (EF-3). Corrections are new, linked records."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="milestones")
    type = models.ForeignKey(MilestoneType, on_delete=models.PROTECT, related_name="+")
    stage = models.ForeignKey(CallStage, on_delete=models.PROTECT, null=True, blank=True, related_name="milestones",
                              help_text=_("The stage of the call the milestone belongs to (a call may berth several times)."))
    declared_at = models.DateTimeField(_("declared time"))
    recorded_at = models.DateTimeField(_("system time"), default=timezone.now)
    device_recorded_at = models.DateTimeField(_("time captured on the device"), null=True, blank=True)
    deferred = models.BooleanField(_("deferred entry"), default=False)
    source = models.CharField(max_length=8, choices=EntrySource.choices, default=EntrySource.ONLINE)
    emitter_role = models.CharField(max_length=6)
    emitter_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    emitter_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    emitter_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    emitter_label = models.CharField(max_length=200)
    countersigner_roles = models.JSONField(default=list, blank=True)
    cause = models.ForeignKey(InterruptionCause, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    cause_reason = models.CharField(max_length=300, blank=True)
    related = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="followers")
    is_rectification = models.BooleanField(default=False)
    rectification_reason = models.CharField(max_length=300, blank=True)
    is_conflict = models.BooleanField(_("competing entry"), default=False)
    note = models.TextField(blank=True)
    payload = models.JSONField(default=dict, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["declared_at", "recorded_at"]
        indexes = [models.Index(fields=["call", "type"])]
        verbose_name = _("milestone")
        verbose_name_plural = _("milestones")

    def __str__(self) -> str:
        return f"{self.call.reference} {self.type.code} {self.declared_at:%Y-%m-%d %H:%M}"


class MilestoneSignature(AppendOnlyModel):
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, related_name="signatures")
    role = models.CharField(max_length=3)
    state = models.CharField(max_length=14, choices=CountersignState.choices)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    signer_label = models.CharField(max_length=200)
    at = models.DateTimeField(default=timezone.now)
    comment = models.TextField(blank=True)
    dispute = models.ForeignKey("Dispute", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["at"]


# ======================================================================================
# Requests, authorizations
# ======================================================================================
class ServiceRequest(NoDeleteModel):
    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="requests")
    type = models.ForeignKey(RequestType, on_delete=models.PROTECT, related_name="+")
    reference = models.CharField(max_length=40, unique=True)
    status = models.CharField(max_length=14, choices=RequestStatus.choices, default=RequestStatus.CREATED)
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    requester_role = models.CharField(max_length=3)
    requester_org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    requester_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    # organisation that carries out a service order (e.g. the waste contractor) when several hold the role
    provider_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    data = models.JSONField(default=dict, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    decision = models.CharField(max_length=14, blank=True, choices=RequestStatus.choices)
    decision_role = models.CharField(max_length=3, blank=True)
    decision_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    decision_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    decision_reason = models.TextField(blank=True)
    decision_conditions = models.TextField(blank=True)
    scheduled_for = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["call", "status"])]
        verbose_name = _("request")
        verbose_name_plural = _("requests")

    def __str__(self) -> str:
        return f"{self.reference} — {self.type.label}"


class Authorization(AppendOnlyModel):
    """Distinct object produced by an approval (EF-2.5). Always carries an expiry date."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="authorizations")
    request = models.OneToOneField(ServiceRequest, on_delete=models.PROTECT, related_name="authorization")
    number = models.CharField(max_length=40, unique=True)
    type_code = models.CharField(max_length=40)
    issuer_role = models.CharField(max_length=3)
    issuer_org = models.ForeignKey(Organization, on_delete=models.PROTECT, related_name="+")
    issuer_user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="+")
    issuer_label = models.CharField(max_length=200)
    scope = models.TextField()
    conditions = models.TextField(blank=True)
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    signed_at = models.DateTimeField(default=timezone.now)
    seal = models.CharField(max_length=64)
    verification_code = models.CharField(max_length=12, unique=True)
    berth = models.ForeignKey(Berth, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["-signed_at"]

    def __str__(self) -> str:
        return self.number

    def clean(self):
        if not self.valid_until:
            raise ValidationError(_("An authorization without an expiry date cannot be recorded."))
        if self.valid_from and self.valid_until <= self.valid_from:
            raise ValidationError(_("The expiry must follow the effective date."))

    def save(self, *args, **kwargs):
        if not self.valid_until:
            raise ValidationError(_("An authorization without an expiry date cannot be recorded."))
        super().save(*args, **kwargs)

    @property
    def is_cancelled(self) -> bool:
        return self.events.filter(kind=AuthorizationEvent.Kind.CANCELLED).exists()

    def is_valid(self, when=None) -> bool:
        when = when or timezone.now()
        return self.valid_from <= when < self.valid_until and not self.is_cancelled


class AuthorizationEvent(AppendOnlyModel):
    class Kind(models.TextChoices):
        CANCELLED = "CANCELLED", _("Cancelled")
        VERIFIED = "VERIFIED", _("Verified (public code)")

    authorization = models.ForeignKey(Authorization, on_delete=models.PROTECT, related_name="events")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reason = models.CharField(max_length=300, blank=True)


# ======================================================================================
# Documents
# ======================================================================================
def document_upload_to(instance, filename):
    safe = "".join(c for c in filename if c.isalnum() or c in "._-")[-80:] or "file"
    return f"calls/{instance.call.port.code}/{instance.call.reference}/{uuid.uuid4().hex}_{safe}"


class Document(NoDeleteModel):
    """A document of the call (EF-7). Signed = frozen; a change creates a new version."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="documents")
    type = models.ForeignKey(DocumentType, on_delete=models.PROTECT, related_name="+")
    title = models.CharField(_("title"), max_length=250)
    version = models.PositiveIntegerField(default=1)
    previous = models.OneToOneField("self", on_delete=models.PROTECT, null=True, blank=True, related_name="next_version")
    status = models.CharField(max_length=10, choices=DocumentStatus.choices, default=DocumentStatus.ISSUED)
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    counterpart_role = models.CharField(_("counterpart (N3)"), max_length=3, blank=True)
    # extra readers of this one document (N2): the roles that could read the act it stems from — the requester
    # of a decided request reads the written act of the decision whatever the audience of the document type
    audience_roles = models.JSONField(_("readers of this document (N2)"), default=list, blank=True)
    issuer_role = models.CharField(max_length=3)
    issuer_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    issuer_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    issuer_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    issuer_label = models.CharField(max_length=200)
    file = models.FileField(upload_to=document_upload_to, max_length=300)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(_("fingerprint (SHA-256)"), max_length=64)
    required_signers = models.JSONField(default=list, blank=True)
    generated = models.BooleanField(default=False)
    retention_until = models.DateField(null=True, blank=True)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, null=True, blank=True, related_name="documents")
    deferred = models.BooleanField(default=False)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["call", "type"])]
        verbose_name = _("document")
        verbose_name_plural = _("documents")

    def __str__(self) -> str:
        return f"{self.title} v{self.version}"

    @property
    def has_own_title(self) -> bool:
        return self.title not in (self.type.label_fr, self.type.label_en, "")

    @property
    def display_title(self) -> str:
        """The issuer's title, or the type label in the reader's language when no title was given."""
        return self.title if self.has_own_title else self.type.label

    def title_in(self, language: str) -> str:
        if self.has_own_title:
            return self.title
        return (self.type.label_en or self.type.label_fr) if language == "en" else (self.type.label_fr or self.type.label_en)

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = Document.objects.filter(pk=self.pk).values("sha256", "file", "status").first()
            if original and (original["sha256"] != self.sha256 or original["file"] != self.file.name):
                from apps.core.guards import ImmutableRecordError

                raise ImmutableRecordError("A document's content is frozen; upload a new version instead.")
            if original and original["status"] in {DocumentStatus.CANCELLED, DocumentStatus.REPLACED} and (
                original["status"] != self.status
            ):
                from apps.core.guards import ImmutableRecordError

                raise ImmutableRecordError("A cancelled or replaced document cannot change state.")
        super().save(*args, **kwargs)


class DocumentSignature(AppendOnlyModel):
    document = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="signatures")
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    signer_label = models.CharField(max_length=200)
    signed_at = models.DateTimeField(default=timezone.now)
    document_sha256 = models.CharField(max_length=64)
    signature_image = models.TextField(blank=True, help_text="Hand-drawn signature (PNG data URL), optional")
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["signed_at"]


# ======================================================================================
# Measurements and pumping log
# ======================================================================================
class Measurement(NoDeleteModel):
    """A quantity measured by ship, shore and surveyor (EF-8.1). The platform never picks a reference."""

    class Kind(models.TextChoices):
        INITIAL = "INITIAL", _("Initial gauging")
        FINAL = "FINAL", _("Final gauging")
        OBQ = "OBQ", _("On-board quantity (OBQ)")
        ROB = "ROB", _("Remaining on board (ROB)")
        BL = "BL", _("Bill of lading figure")
        # dry bulk, general cargo and containers (FLX-CDC-002 v1.5, EXG-R-08)
        DRAFT_INITIAL = "DRAFT_I", _("Draft survey — initial")
        DRAFT_FINAL = "DRAFT_F", _("Draft survey — final")
        SCALE = "SCALE", _("Shore scale / weighbridge / belt scale")
        TALLY = "TALLY", _("Tally / count (units, boxes, TEU)")
        OTHER = "OTHER", _("Other")

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="measurements")
    kind = models.CharField(max_length=8, choices=Kind.choices)
    product = models.CharField(max_length=120, blank=True)
    unit = models.CharField(max_length=8, default="MT", choices=QUANTITY_UNITS)
    tolerance_pct = models.DecimalField(max_digits=5, decimal_places=3, default=Decimal("0.300"))
    created_role = models.CharField(max_length=3)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.call.reference} {self.get_kind_display()} ({self.unit})"

    def current_values(self) -> dict[str, "MeasurementValue"]:
        latest: dict[str, MeasurementValue] = {}
        for value in self.values.order_by("entered_at", "id"):
            latest[value.party] = value
        return latest

    PAIRS = (("SHIP", "SHORE"), ("SHIP", "SURVEYOR"), ("SHORE", "SURVEYOR"))

    def differences(self) -> list[dict]:
        """Every pair of declared figures, compared both ways round: no figure is ever the reference."""
        values = self.current_values()
        rows = []
        for a, b in self.PAIRS:
            va, vb = values.get(a), values.get(b)
            if va is None or vb is None:
                continue
            diff = va.value - vb.value
            pct = (diff / vb.value * 100) if vb.value else None
            rows.append({"a": a, "b": b, "difference": diff, "percent": pct,
                         "exceeds": pct is not None and abs(pct) > self.tolerance_pct})
        return rows

    def discrepancy(self):
        """The ship/shore difference of EF-8.1 — the one that carries the tolerance (EF-8.2)."""
        return next((row for row in self.differences() if (row["a"], row["b"]) == ("SHIP", "SHORE")), None)

    @property
    def is_complete(self) -> bool:
        """EF-8.1: a quantity carries a ship value and a shore value (the surveyor's when there is one)."""
        values = self.current_values()
        return MeasurementParty.SHIP in values and MeasurementParty.SHORE in values

    def exceeds_tolerance(self) -> bool:
        d = self.discrepancy()
        return bool(d and d["exceeds"])


class MeasurementValue(AppendOnlyModel):
    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT, related_name="values")
    party = models.CharField(max_length=8, choices=MeasurementParty.choices)
    value = models.DecimalField(max_digits=16, decimal_places=3)
    temperature_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    density = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    entered_role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    entered_label = models.CharField(max_length=200)
    declared_at = models.DateTimeField(default=timezone.now)
    entered_at = models.DateTimeField(default=timezone.now)
    deferred = models.BooleanField(default=False)
    source = models.CharField(max_length=8, choices=EntrySource.choices, default=EntrySource.ONLINE)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["entered_at"]


class TankReading(AppendOnlyModel):
    """One tank of one side of a measurement (FLX-CDC-002 v1.4, EXG-Q-05): the ship's cargo tanks are read by the
    ship, the terminal's shore tanks by the terminal. A reading is written once; a correction is a new reading
    that supersedes it. It is shown to the other parties only once the surveyor has validated it (TankReadingReview);
    until then the side that entered it and the surveyor see it."""

    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT, related_name="tank_readings")
    side = models.CharField(max_length=5, choices=[("SHIP", _("Ship tank")), ("SHORE", _("Shore tank"))])
    tank = models.CharField(_("tank"), max_length=40)
    level_mm = models.DecimalField(_("ullage / innage (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    temperature_c = models.DecimalField(_("temperature (°C)"), max_digits=6, decimal_places=2, null=True, blank=True)
    free_water_mm = models.DecimalField(_("free water (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    density = models.DecimalField(_("density @15 °C"), max_digits=7, decimal_places=4, null=True, blank=True)
    tov_m3 = models.DecimalField(_("TOV (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    gov_m3 = models.DecimalField(_("GOV (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    vcf = models.DecimalField(_("VCF"), max_digits=7, decimal_places=5, null=True, blank=True)
    gsv_m3 = models.DecimalField(_("GSV (m³ @15 °C)"), max_digits=12, decimal_places=3, null=True, blank=True)
    weight_mt = models.DecimalField(_("weight (t)"), max_digits=12, decimal_places=3, null=True, blank=True)
    entered_role = models.CharField(max_length=3)
    entered_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    entered_label = models.CharField(max_length=200)
    declared_at = models.DateTimeField(default=timezone.now)
    entered_at = models.DateTimeField(default=timezone.now)
    supersedes = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    note = models.CharField(max_length=300, blank=True)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["entered_at", "id"]
        indexes = [models.Index(fields=["measurement", "side"])]
        verbose_name = _("tank reading")
        verbose_name_plural = _("tank readings")

    def __str__(self) -> str:
        return f"{self.measurement} — {self.get_side_display()} {self.tank}"

    def latest_review(self):
        return self.reviews.order_by("-reviewed_at", "-id").first()

    @property
    def state(self) -> str:
        review = self.latest_review()
        return review.state if review else TankReadingReview.State.PENDING

    @property
    def is_validated(self) -> bool:
        return self.state == TankReadingReview.State.VALIDATED

    @property
    def quantity(self):
        """The figure a tank contributes to its side's total: the weight, else the GSV, else the GOV / TOV."""
        for value in (self.weight_mt, self.gsv_m3, self.gov_m3, self.tov_m3):
            if value is not None:
                return value
        return None


class TankReadingReview(AppendOnlyModel):
    """The surveyor's validation (or rejection, with a reason) of a tank reading: written once; the latest review
    of a reading is its state."""

    class State(models.TextChoices):
        PENDING = "PENDING", _("Awaiting the surveyor")
        VALIDATED = "VALIDATED", _("Validated by the surveyor")
        REJECTED = "REJECTED", _("Rejected by the surveyor")

    reading = models.ForeignKey(TankReading, on_delete=models.PROTECT, related_name="reviews")
    state = models.CharField(max_length=9, choices=State.choices)
    role = models.CharField(max_length=3, default="INS")
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    reviewer_label = models.CharField(max_length=200)
    reviewed_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=300, blank=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["reviewed_at", "id"]


class PumpingLogSheet(NoDeleteModel):
    """The header of one side's pumping log (FLX-CDC-002 v1.4, EXG-Q-01; structure of the terminal pumping logs
    of the industry): the tank concerned, the product, the calibration of the tank (m³ per metre), density and
    VCF, the planned quantity, the expected rate and pressure, the start and expected stop levels, the estimated
    times. The ship opens its own sheet, the terminal its own: the platform compares the two sides reading by
    reading and never designates a reference figure."""

    class Side(models.TextChoices):
        SHIP = "SHIP", _("Ship (delivered / received on board)")
        SHORE = "SHORE", _("Shore (received / delivered by the terminal)")

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="pumping_sheets")
    side = models.CharField(max_length=5, choices=Side.choices)
    tank = models.CharField(_("tank"), max_length=40, blank=True, help_text=_("Shore tank or ship tank(s) concerned."))
    product = models.CharField(_("product"), max_length=120, blank=True)
    start_level_mm = models.DecimalField(_("start dip / ullage (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    expected_stop_level_mm = models.DecimalField(_("expected stop dip / ullage (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    m3_per_metre = models.DecimalField(_("tank calibration (m³ per metre)"), max_digits=10, decimal_places=3, null=True, blank=True)
    density = models.DecimalField(_("density (t/m³)"), max_digits=7, decimal_places=4, null=True, blank=True)
    vcf = models.DecimalField(_("VCF"), max_digits=7, decimal_places=5, null=True, blank=True)
    planned_quantity_m3 = models.DecimalField(_("planned quantity (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    planned_quantity_mt = models.DecimalField(_("planned quantity (t)"), max_digits=12, decimal_places=3, null=True, blank=True)
    expected_rate_m3h = models.DecimalField(_("expected rate (m³/h)"), max_digits=9, decimal_places=2, null=True, blank=True)
    expected_pressure_bar = models.DecimalField(_("expected pressure (bar)"), max_digits=7, decimal_places=2, null=True, blank=True)
    estimated_start = models.DateTimeField(_("estimated start"), null=True, blank=True)
    estimated_completion = models.DateTimeField(_("estimated completion"), null=True, blank=True)
    # completion, entered by the same side when the transfer ends
    actual_stop_level_mm = models.DecimalField(_("actual stop dip / ullage (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    final_volume_m3 = models.DecimalField(_("final volume (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    opened_role = models.CharField(max_length=3)
    opened_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_label = models.CharField(max_length=200)
    opened_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["call", "side", "opened_at"]
        verbose_name = _("pumping log sheet")
        verbose_name_plural = _("pumping log sheets")

    def __str__(self) -> str:
        return f"{self.call.reference} — {self.get_side_display()} {self.tank}".strip()

    @property
    def tons_per_metre(self):
        """Tonnes per metre of level: m³/m × density × VCF (the terminal log's own formula)."""
        if self.m3_per_metre is None or self.density is None:
            return None
        return self.m3_per_metre * self.density * (self.vcf if self.vcf is not None else Decimal("1"))

    def tons(self, m3):
        """Observed cubic metres converted to tonnes with the sheet's density and VCF, when both are known."""
        if m3 is None or self.density is None:
            return None
        return m3 * self.density * (self.vcf if self.vcf is not None else Decimal("1"))


class PumpingLogEntry(AppendOnlyModel):
    """One reading of the pumping log, by the ship or by the terminal (FLX-CDC-002 v1.4, EXG-Q-01). Manual in V1;
    the same table accepts an automatic feed without schema change (EF-8.3). Besides the manifold pressure, the
    rate and the temperature, a reading carries the tank level and the quantities of the terminal pumping logs:
    the quantity moved since the previous reading, the cumulated quantity, in m³ and in tonnes. What the platform
    computes from the sheet (calibration, density, VCF) is stored with the reading so that the record is frozen."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="pumping_log")
    sheet = models.ForeignKey(PumpingLogSheet, on_delete=models.PROTECT, null=True, blank=True, related_name="entries")
    declared_at = models.DateTimeField()
    recorded_at = models.DateTimeField(default=timezone.now)
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    entered_label = models.CharField(max_length=200)
    tank = models.CharField(_("tank"), max_length=40, blank=True)
    manifold_pressure_bar = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    flow_rate_m3h = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)
    temperature_c = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    level_mm = models.DecimalField(_("tank dip / ullage (mm)"), max_digits=8, decimal_places=1, null=True, blank=True)
    hourly_m3 = models.DecimalField(_("moved since the previous reading (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    cumulative_m3 = models.DecimalField(_("cumulated (m³)"), max_digits=12, decimal_places=3, null=True, blank=True)
    cumulative_mt = models.DecimalField(_("cumulated (t)"), max_digits=12, decimal_places=3, null=True, blank=True)
    note = models.CharField(max_length=300, blank=True)
    source = models.CharField(max_length=10, default="MANUAL", choices=[("MANUAL", _("Manual")), ("AUTOMATIC", _("Automatic"))])
    device_id = models.CharField(max_length=80, blank=True)
    deferred = models.BooleanField(default=False)
    client_uuid = models.UUIDField(null=True, blank=True, unique=True)

    class Meta:
        ordering = ["declared_at"]

    @property
    def side(self) -> str:
        """The side that keeps the reading: the master's entries are the ship's, the terminal's the shore's."""
        if self.sheet_id is not None and self.sheet is not None:
            return self.sheet.side
        return "SHIP" if self.role == "NAV" else "SHORE"


# ======================================================================================
# Ship/shore safety checklist (ISGOTT structure), completed on line by both sides
# ======================================================================================
class SafetyChecklist(NoDeleteModel):
    """The ship/shore safety checklist of a call (FLX-CDC-002 v1.4, EXG-Q-10): the items, in the platform's own
    words after the ISGOTT structure, are frozen in the record when it is opened; the ship ticks its items, the
    terminal its own, the joint items need both; the agreements of the pre-transfer conference are written in;
    the repetitive checks are re-ticked at the agreed interval. Each tick is an append-only answer; the two
    signatures close the list, complete task M0:28 and record the SSSCL_SIGNED milestone."""

    class Status(models.TextChoices):
        OPEN = "OPEN", _("Being completed")
        SIGNED = "SIGNED", _("Signed by both sides")
        CANCELLED = "CANCELLED", _("Cancelled")

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="safety_checklists")
    stage = models.ForeignKey(CallStage, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    version = models.PositiveSmallIntegerField(default=1)
    # the standard the list follows (v1.5): ISGOTT for liquid bulk, the BLU Code for dry bulk, the platform's cargo
    # operations checklist for containers, general cargo, ro-ro and other calls
    standard = models.CharField(_("standard"), max_length=12, default="SSSCL",
                                choices=[("SSSCL", "ISGOTT — SSSCL"), ("BLU", _("BLU Code — dry bulk")),
                                         ("CARGO", _("Cargo operations (containers, general cargo, ro-ro)"))])
    items = models.JSONField(_("items"), default=list, blank=True)
    repeat_interval_h = models.DecimalField(_("interval of the repetitive checks (h)"), max_digits=4, decimal_places=1,
                                            null=True, blank=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.OPEN)
    opened_role = models.CharField(max_length=3)
    opened_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_label = models.CharField(max_length=200)
    opened_at = models.DateTimeField(default=timezone.now)
    signed_at = models.DateTimeField(null=True, blank=True)
    cancel_reason = models.CharField(max_length=300, blank=True)
    document = models.ForeignKey(Document, on_delete=models.PROTECT, null=True, blank=True, related_name="+")

    class Meta:
        ordering = ["call", "version"]
        constraints = [models.UniqueConstraint(fields=["call", "version"], name="uniq_safety_checklist_version")]
        verbose_name = _("ship/shore safety checklist")
        verbose_name_plural = _("ship/shore safety checklists")

    def __str__(self) -> str:
        return f"{self.call.reference} — {self.standard} v{self.version}"

    def current_answers(self) -> dict[tuple[str, str], "SafetyCheckAnswer"]:
        """The latest answer per (item, side)."""
        latest: dict[tuple[str, str], SafetyCheckAnswer] = {}
        for answer in self.answers.order_by("answered_at", "id"):
            latest[(answer.item_code, answer.side)] = answer
        return latest

    def signed_sides(self) -> set[str]:
        return set(self.signatures.values_list("side", flat=True))


class SafetyCheckAnswer(AppendOnlyModel):
    """One tick (yes / no / not applicable), an agreed value or a remark on one item, by one side."""

    class State(models.TextChoices):
        YES = "YES", _("Yes — checked")
        NO = "NO", _("No")
        NA = "NA", _("Not applicable")

    checklist = models.ForeignKey(SafetyChecklist, on_delete=models.PROTECT, related_name="answers")
    item_code = models.CharField(max_length=12)
    side = models.CharField(max_length=5, choices=[("SHIP", _("Ship")), ("SHORE", _("Shore"))])
    state = models.CharField(max_length=3, choices=State.choices, blank=True)
    value = models.CharField(_("agreed value"), max_length=300, blank=True)
    remark = models.CharField(max_length=300, blank=True)
    repetition = models.PositiveSmallIntegerField(default=0, help_text=_("0 for the initial check, then 1, 2… for the repeated checks"))
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    author_label = models.CharField(max_length=200)
    answered_at = models.DateTimeField(default=timezone.now)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["answered_at", "id"]
        indexes = [models.Index(fields=["checklist", "item_code"])]


class SafetyChecklistSignature(AppendOnlyModel):
    checklist = models.ForeignKey(SafetyChecklist, on_delete=models.PROTECT, related_name="signatures")
    side = models.CharField(max_length=5, choices=[("SHIP", _("Ship")), ("SHORE", _("Shore"))])
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    signer_label = models.CharField(max_length=200)
    signed_at = models.DateTimeField(default=timezone.now)
    comment = models.CharField(max_length=300, blank=True)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["signed_at"]
        constraints = [models.UniqueConstraint(fields=["checklist", "side"], name="uniq_checklist_signature_side")]


# ======================================================================================
# Disputes
# ======================================================================================
class Dispute(NoDeleteModel):
    """First-class contest (EF-4). Never blocks the operation; the platform never arbitrates."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="disputes")
    reference = models.CharField(max_length=40, unique=True)
    subject = models.CharField(_("subject"), max_length=250)
    target_kind = models.CharField(
        max_length=14,
        choices=[("MILESTONE", _("Milestone")), ("MEASUREMENT", _("Measurement")), ("AUTHORIZATION", _("Authorization")),
                 ("DOCUMENT", _("Document")), ("TASK", _("Task")), ("OTHER", _("Other"))],
    )
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    status = models.CharField(max_length=18, choices=DisputeStatus.choices, default=DisputeStatus.OPEN)
    opened_role = models.CharField(max_length=3)
    opened_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    opened_label = models.CharField(max_length=200)
    counterpart_role = models.CharField(max_length=3, blank=True)
    # set when the disputed item has an author: the counterpart is that organisation, not every holder of the role
    counterpart_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    counterpart_master = models.BooleanField(default=False)
    auto_created = models.BooleanField(default=False, help_text="Created by the platform on a synchronisation conflict")
    opened_at = models.DateTimeField(default=timezone.now)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-opened_at"]

    def __str__(self) -> str:
        return f"{self.reference} — {self.subject}"


class DisputeEntry(AppendOnlyModel):
    class Kind(models.TextChoices):
        STATEMENT = "STATEMENT", _("Statement")
        RESPONSE = "RESPONSE", _("Response")
        CLOSURE = "CLOSURE", _("Closure")

    dispute = models.ForeignKey(Dispute, on_delete=models.PROTECT, related_name="entries")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    author_label = models.CharField(max_length=200)
    text = models.TextField()
    at = models.DateTimeField(default=timezone.now)
    seal = models.CharField(max_length=64)

    class Meta:
        ordering = ["at"]


# ======================================================================================
# Correspondence — no free messaging: every thread belongs to a call (EF-9)
# ======================================================================================
class Thread(NoDeleteModel):
    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="threads")
    subject = models.CharField(_("subject"), max_length=250)
    confidentiality = models.CharField(max_length=2, choices=Confidentiality.choices, default=Confidentiality.N2)
    participant_roles = models.JSONField(_("participating roles"), default=list)
    related_kind = models.CharField(max_length=14, blank=True)
    related_id = models.PositiveBigIntegerField(null=True, blank=True)
    created_role = models.CharField(max_length=3)
    created_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_message_at", "-created_at"]

    def __str__(self) -> str:
        return self.subject


class Message(AppendOnlyModel):
    thread = models.ForeignKey(Thread, on_delete=models.PROTECT, related_name="messages")
    role = models.CharField(max_length=3)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    author_label = models.CharField(max_length=200)
    body = models.TextField()
    document = models.ForeignKey(Document, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["sent_at"]


# ======================================================================================
# Alerts and notifications
# ======================================================================================
class Alert(AppendOnlyModel):
    """Every alert emitted is a piece of the file (EF-6.4): time-stamped, kept, on the statement of facts."""

    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, related_name="alerts")
    kind = models.CharField(max_length=10, choices=AlertKind.choices)
    task = models.ForeignKey(Task, on_delete=models.PROTECT, null=True, blank=True, related_name="alerts")
    milestone = models.ForeignKey(Milestone, on_delete=models.PROTECT, null=True, blank=True, related_name="alerts")
    measurement = models.ForeignKey(Measurement, on_delete=models.PROTECT, null=True, blank=True, related_name="alerts")
    blocking = models.BooleanField(default=False)
    recipient_roles = models.JSONField(default=list)
    message_fr = models.CharField(max_length=500)
    message_en = models.CharField(max_length=500)
    emitted_at = models.DateTimeField(default=timezone.now)
    template_code = models.CharField(max_length=10, blank=True)

    class Meta:
        ordering = ["-emitted_at"]

    @property
    def message(self) -> str:
        return pick(self.message_fr, self.message_en)


class Notification(NoDeleteModel):
    """Per-user notification. Always derived from an object or a deadline (EF-18.2)."""

    user = models.ForeignKey(User, on_delete=models.PROTECT, related_name="notifications")
    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    alert = models.ForeignKey(Alert, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    dedupe_key = models.CharField(max_length=160)
    title_fr = models.CharField(max_length=300)
    title_en = models.CharField(max_length=300)
    url = models.CharField(max_length=300, blank=True)
    realtime = models.BooleanField(default=False)
    blocking = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    read_at = models.DateTimeField(null=True, blank=True)
    email_sent_at = models.DateTimeField(null=True, blank=True)
    sms_sent_at = models.DateTimeField(null=True, blank=True)
    digest_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [models.UniqueConstraint(fields=["user", "dedupe_key"], name="uniq_notification_per_event")]

    @property
    def title(self) -> str:
        return pick(self.title_fr, self.title_en)


# ======================================================================================
# Journal (hash-chained, append-only) and access audit
# ======================================================================================
class ChainHead(models.Model):
    """Head of a hash chain. Row-locked during appends so that the chain stays linear."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="+")
    chain = models.CharField(max_length=10, choices=[("journal", "journal"), ("audit", "audit")])
    last_seq = models.PositiveBigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default="0" * 64)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port", "chain"], name="uniq_chain_head")]


class JournalEntry(AppendOnlyModel):
    """The call journal: every act, refusal and alert, chained cryptographically (ENF-4.1)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="+")
    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, null=True, blank=True, related_name="journal")
    seq = models.PositiveBigIntegerField()
    at = models.DateTimeField(default=timezone.now)
    actor_role = models.CharField(max_length=6, blank=True)
    actor_user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    actor_master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    actor_org = models.ForeignKey(Organization, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    actor_label = models.CharField(max_length=200)
    action = models.CharField(max_length=60)
    object_kind = models.CharField(max_length=30, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    visible_roles = models.JSONField(default=list, help_text="Roles that may read this entry; ['*'] = every party")
    summary_fr = models.CharField(max_length=500)
    summary_en = models.CharField(max_length=500)
    payload = models.JSONField(default=dict, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)
    timestamp_provider = models.CharField(max_length=20, default="local")
    timestamp_token = models.TextField(blank=True)

    class Meta:
        ordering = ["seq"]
        constraints = [models.UniqueConstraint(fields=["port", "seq"], name="uniq_journal_seq")]
        indexes = [models.Index(fields=["call", "seq"]), models.Index(fields=["action"])]

    @property
    def summary(self) -> str:
        return pick(self.summary_fr, self.summary_en)


class AuditEntry(AppendOnlyModel):
    """Who saw, entered, approved, exported what and when (ENF-3.4). Chained like the journal."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    call = models.ForeignKey(PortCall, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    seq = models.PositiveBigIntegerField()
    at = models.DateTimeField(default=timezone.now)
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    master = models.ForeignKey(MasterAccessLink, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    actor_label = models.CharField(max_length=200)
    action = models.CharField(max_length=40)
    object_kind = models.CharField(max_length=30, blank=True)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    detail = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["seq"]
        indexes = [models.Index(fields=["port", "seq"]), models.Index(fields=["call", "at"])]


# ======================================================================================
# Outbound events to third-party systems (single window / PCS) — orientation 5
# ======================================================================================
class WebhookSubscription(models.Model):
    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="webhooks")
    name = models.CharField(max_length=120)
    url = models.URLField(max_length=400)
    secret = models.CharField(max_length=128, default=_new_token)
    actions = models.JSONField(default=list, blank=True, help_text="Journal actions to publish; empty = all N1 actions")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("webhook subscription")
        verbose_name_plural = _("webhook subscriptions")

    def __str__(self) -> str:
        return self.name


class WebhookDelivery(models.Model):
    subscription = models.ForeignKey(WebhookSubscription, on_delete=models.PROTECT, related_name="deliveries")
    entry = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name="+")
    status = models.CharField(max_length=8, default="PENDING", choices=[("PENDING", "PENDING"), ("SENT", "SENT"), ("FAILED", "FAILED")])
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["status", "next_attempt_at"])]
