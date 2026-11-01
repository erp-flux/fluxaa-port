"""AI assistance of CDC EF-17 — four uses, none of them in the chain of authorization.

* extraction of fields from a Q88, certificates or a bill of lading → an ``ExtractionReview`` whose
  values are shown "pre-filled" and saved only when a person validates them;
* draft of the agency's remarks for the statement of facts → a draft the agency edits; the statement
  is then signed by people;
* consistency review of a call → findings; a person decides whether to raise one as an alert;
* summary of an exchange → a text shown to the reader, nothing recorded in the call;
* brief of the port and questions on its registry (direction, authority, harbour master) → a text that
  cites the calls it draws on, computed from the same registry everyone reads.

The assistant never approves, signs, closes or corrects anything, and never sees the N4 domain.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop

from apps.core.numbers import parse_decimal
from apps.registry.models import Alert, AlertKind
from apps.registry.services import journal, rights
from apps.registry.services.errors import NotVisible, PermissionRefused, RuleViolation

from . import client, payloads
from .models import AssistantRun, ExtractionReview

# ============================================================================ schemas
FIELD = {
    "type": "object",
    "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                   "evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
    "required": ["value", "evidence"],
    "additionalProperties": False,
}

# Q88 fields → vessel record (name and IMO are only cross-checked, never overwritten)
# Labels are English on purpose: they also instruct the model. Screens translate them (gettext_noop).
Q88_FIELDS = [
    ("name", gettext_noop("Vessel name")), ("imo", gettext_noop("IMO number")), ("flag", gettext_noop("Flag")), ("vessel_type", gettext_noop("Vessel type")),
    ("call_sign", gettext_noop("Call sign")), ("mmsi", gettext_noop("MMSI")), ("dwt", gettext_noop("Summer deadweight (t)")),
    ("loa_m", gettext_noop("Length overall (m)")), ("beam_m", gettext_noop("Beam / breadth (m)")), ("draft_m", gettext_noop("Summer draft (m)")),
    ("built_year", gettext_noop("Year built")), ("owner_name", gettext_noop("Registered owner")), ("manager_name", gettext_noop("Manager / operator")),
]
Q88_APPLICABLE = {"flag", "vessel_type", "call_sign", "mmsi", "dwt", "loa_m", "beam_m", "draft_m", "built_year",
                  "owner_name", "manager_name"}
BL_FIELDS = [
    ("bl_number", gettext_noop("Bill of lading number")), ("bl_date", gettext_noop("Date of issue (YYYY-MM-DD)")),
    ("vessel_name", gettext_noop("Vessel name")), ("port_of_loading", gettext_noop("Port of loading")),
    ("port_of_discharge", gettext_noop("Port of discharge")), ("product", gettext_noop("Product / grade")),
    ("quantity", gettext_noop("Quantity (number only)")), ("unit", gettext_noop("Unit of the quantity (MT, M3, BBL…)")),
    ("shipper", gettext_noop("Shipper")), ("consignee", gettext_noop("Consignee")),
]
KINDS = {
    "Q88": {"roles": {"AGE", "NAV"}, "fields": Q88_FIELDS},
    "CERTIFICATES": {"roles": {"AGE", "NAV", "CAP", "APO", "ADM"}},
    "BL": {"roles": {"AGE", "NAV", "TER", "INS"}, "fields": BL_FIELDS},
}
CERTIFICATES_SCHEMA = {
    "type": "object",
    "properties": {
        "vessel_imo": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        "certificates": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "number": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "issued_by": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "expiry_date": {"anyOf": [{"type": "string", "format": "date"}, {"type": "null"}]},
                "evidence": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            "required": ["name", "number", "issued_by", "expiry_date", "evidence"],
            "additionalProperties": False,
        }},
    },
    "required": ["vessel_imo", "certificates"],
    "additionalProperties": False,
}
FINDINGS_SCHEMA = {
    "type": "object",
    "properties": {"findings": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "severity": {"type": "string", "enum": ["high", "medium", "low"]},
            "title": {"type": "string"},
            "detail": {"type": "string"},
            "references": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["severity", "title", "detail", "references"],
        "additionalProperties": False,
    }}},
    "required": ["findings"],
    "additionalProperties": False,
}
TEXT_SCHEMA = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"],
               "additionalProperties": False}

EXTRACTION_SYSTEM = (
    "You read maritime documents for the operational registry of a tanker call. Copy values exactly as "
    "they appear in the document. Never guess, never compute, never complete a missing value: when a value "
    "is absent or illegible, return null. For each value, give as evidence a short quote of the line it "
    "comes from. People will check every value before anything is recorded."
)


def _language_name() -> str:
    from django.utils import translation

    return "French" if (translation.get_language() or "fr").startswith("fr") else "English"


def _fields_schema(fields) -> dict:
    return {"type": "object", "properties": {key: FIELD for key, _label in fields},
            "required": [key for key, _label in fields], "additionalProperties": False}


# ============================================================================ plumbing
def _require_enabled(call=None, port=None) -> None:
    if not client.enabled_for(port or call.port):
        raise RuleViolation(_("AI assistance is not enabled for this port."))


def _role(actor, allowed) -> str:
    if actor.is_link:  # an account-less access (master or party link) never triggers a third-party processing
        raise PermissionRefused(_("The assistant is not available through an access link."))
    return actor.pick_role(allowed)


def _run(call, actor, role: str, feature: str, *, system: str, content: list[dict], schema: dict,
         inventory: list[str], max_tokens: int = 4096, port=None) -> AssistantRun:
    """Send one request, keep its trace whatever happens, and return the run (*call* is None at port level)."""
    port = port or call.port
    sent = json.dumps({"system": system, "content": content, "schema": schema}, sort_keys=True, default=str)
    digest = hashlib.sha256(sent.encode("utf-8")).hexdigest()
    started = time.monotonic()
    output, status, error = {}, AssistantRun.Status.OK, ""
    try:
        output = client.ask(system=system, content=content, schema=schema, max_tokens=max_tokens)
    except client.AssistantUnavailable as exc:
        status, error = AssistantRun.Status.ERROR, str(exc)[:300]
    run = AssistantRun.objects.create(
        port=port, call=call, feature=feature, requested_by=actor.user, requested_role=role,
        model=settings.FLUXAA_AI_MODEL, input_digest=digest, input_inventory=inventory, output=output,
        status=status, error=error, duration_ms=int((time.monotonic() - started) * 1000),
    )
    journal.audit(port=port, call=call, user=actor.user, master=None, action="assistant", obj=run,
                  object_kind="assistant", detail=f"{feature} {status}")
    if status == AssistantRun.Status.ERROR:
        raise client.AssistantUnavailable(error)
    return run


def _text(value) -> str:
    return "" if value is None else str(value).strip()


# ============================================================================ 1. extraction
def extraction_kind(doc) -> str | None:
    return doc.type.code if doc.type.code in KINDS else None


def can_extract(actor, doc) -> bool:
    kind = extraction_kind(doc)
    return bool(kind and not actor.is_link and set(actor.roles) & KINDS[kind]["roles"]
                and rights.document_visible(actor, doc) and doc.status in ("ISSUED", "SIGNED"))


def extract(doc, actor) -> ExtractionReview:
    call = doc.call
    _require_enabled(call)
    kind = extraction_kind(doc)
    if kind is None:
        raise RuleViolation(_("The assistant reads Q88, certificates and bills of lading only."))
    if not rights.document_visible(actor, doc):
        raise NotVisible()
    role = _role(actor, KINDS[kind]["roles"])
    blocks, inventory = payloads.document_content(doc)
    if kind == "CERTIFICATES":
        schema = CERTIFICATES_SCHEMA
        task = ("List every statutory or insurance certificate in this document with its number, issuing "
                "authority and expiry date (YYYY-MM-DD). Also give the vessel's IMO number if printed.")
    else:
        fields = KINDS[kind]["fields"]
        schema = {"type": "object", "properties": {"fields": _fields_schema(fields)}, "required": ["fields"],
                  "additionalProperties": False}
        task = "Extract these fields: " + "; ".join(f"{key} = {label}" for key, label in fields) + "."
    run = _run(call, actor, role, AssistantRun.Feature.EXTRACT, system=EXTRACTION_SYSTEM,
               content=blocks + [{"type": "text", "text": task}], schema=schema, inventory=inventory)
    proposed = run.output if kind == "CERTIFICATES" else (run.output.get("fields") or {})
    return ExtractionReview.objects.create(run=run, call=call, document=doc, kind=kind, proposed=proposed)


def _coerce_vessel_value(field: str, raw: str):
    if field in ("dwt", "built_year"):
        number = parse_decimal(raw)
        if number != number.to_integral_value() or number < 0:
            raise ValueError(field)
        return int(number)
    if field in ("loa_m", "beam_m", "draft_m"):
        number = parse_decimal(raw)
        if number <= 0:
            raise ValueError(field)
        return number.quantize(Decimal("0.01"))
    if field == "mmsi" and not (raw.isdigit() and len(raw) == 9):
        raise ValueError(field)
    return raw


@transaction.atomic
def validate_extraction(review: ExtractionReview, actor, accepted: dict | list) -> ExtractionReview:
    """A person validates the values (possibly corrected). Only then does anything reach the registry."""
    if review.call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    if review.status != ExtractionReview.Status.PROPOSED:
        raise RuleViolation(_("This extraction has already been handled."))
    doc = review.document
    if not rights.document_visible(actor, doc):
        raise NotVisible()
    now = timezone.now()
    if review.kind == "Q88":
        role = _role(actor, {"AGE"})  # the vessel record is maintained by the agency
        vessel = review.call.vessel
        changed = {}
        for field, raw in (accepted or {}).items():
            raw = _text(raw)
            if field not in Q88_APPLICABLE or not raw:
                continue
            try:
                value = _coerce_vessel_value(field, raw)
            except (ValueError, ArithmeticError):
                raise RuleViolation(_("“%(f)s” is not a valid value for the vessel record.") % {"f": field})
            if getattr(vessel, field) != value:
                changed[field] = {"from": _text(getattr(vessel, field)), "to": _text(value)}
                setattr(vessel, field, value)
        if changed:
            vessel.save()
        validated = {"applied_to_vessel": changed}
        summary = ", ".join(sorted(changed)) or "—"
        journal.record(
            port=review.call.port, call=review.call, actor=actor, role=role, action="vessel.updated", obj=vessel,
            visible_roles=["*"], payload={"fields": changed, "assistant_run": review.run_id, "document": doc.pk},
            summary_fr=f"Fiche navire mise à jour après validation d'une extraction du Q88 : {summary}",
            summary_en=f"Vessel record updated after validating an extraction from the Q88: {summary}",
        )
    elif review.kind == "CERTIFICATES":
        role = _role(actor, KINDS["CERTIFICATES"]["roles"])
        certificates = []
        for row in accepted or []:
            name = _text(row.get("name"))
            if not name:
                continue
            expiry = _text(row.get("expiry_date"))
            if expiry:
                try:
                    date.fromisoformat(expiry)
                except ValueError:
                    raise RuleViolation(_("Expiry dates are written YYYY-MM-DD."))
            certificates.append({"name": name, "number": _text(row.get("number")), "expiry_date": expiry})
        validated = {"certificates": certificates}
        journal.record(
            port=review.call.port, call=review.call, actor=actor, role=role, action="document.data_validated",
            obj=doc, visible_roles=["AGE", "NAV", "CAP", "APO", "ADM", doc.issuer_role],
            payload={"certificates": certificates, "assistant_run": review.run_id},
            summary_fr=f"Échéances de {len(certificates)} certificat(s) validées à partir du document v{doc.version}",
            summary_en=f"Expiry dates of {len(certificates)} certificate(s) validated from document v{doc.version}",
        )
    else:  # BL
        role = _role(actor, KINDS["BL"]["roles"])
        validated = {key: _text((accepted or {}).get(key)) for key, _label in BL_FIELDS}
        if validated.get("quantity"):
            try:
                validated["quantity"] = str(parse_decimal(validated["quantity"]))
            except ValueError:
                raise RuleViolation(_("The quantity must be a number."))
        journal.record(
            port=review.call.port, call=review.call, actor=actor, role=role, action="document.data_validated",
            obj=doc, visible_roles=["AGE", "NAV", "TER", "INS", "COM"],
            payload={"bill_of_lading": validated, "assistant_run": review.run_id},
            summary_fr=f"Données du connaissement validées (nº {validated.get('bl_number') or '—'})",
            summary_en=f"Bill of lading data validated (no. {validated.get('bl_number') or '—'})",
        )
    review.status = ExtractionReview.Status.APPLIED
    review.validated = validated
    review.validated_by = actor.user
    review.validated_label = actor.label
    review.validated_at = now
    review.save()
    return review


def dismiss_extraction(review: ExtractionReview, actor) -> ExtractionReview:
    if review.status != ExtractionReview.Status.PROPOSED:
        raise RuleViolation(_("This extraction has already been handled."))
    if not rights.document_visible(actor, review.document):
        raise NotVisible()
    _role(actor, KINDS[review.kind]["roles"])
    review.status = ExtractionReview.Status.DISMISSED
    review.validated_by = actor.user
    review.validated_label = actor.label
    review.validated_at = timezone.now()
    review.save()
    return review


# ============================================================================ 2. consistency review
REVIEW_ROLES = {"AGE", "CAP", "APO", "TER", "INS"}

REVIEW_SYSTEM = (
    "You assist the parties of a tanker call in a port. You receive the registry of the call as the reader "
    "is allowed to see it (roles stand for organisations). Point out inconsistencies a careful operator "
    "would check: a time sequence that is impossible or unusual, a milestone that should exist and does "
    "not, a ship/shore/surveyor difference, a document or authorization that expires before it is needed, "
    "a contested or tacit countersignature that matters. You never decide and never correct: each finding "
    "is a question for a person. Cite the objects you rely on in references (e.g. milestone ALL_FAST, "
    "task M0:28). Report nothing you cannot support from the data. Write in {language}."
)


def deterministic_findings(call, actor) -> list[dict]:
    """Rule checks that need no AI (always available): expiries known from validated certificates."""
    findings = []
    deadline = call.atd or call.etd
    if deadline is None:
        return findings
    for review in ExtractionReview.objects.filter(call=call, kind="CERTIFICATES", status="APPLIED"):
        if not rights.document_visible(actor, review.document):
            continue
        for cert in (review.validated or {}).get("certificates", []):
            try:
                expiry = date.fromisoformat(cert.get("expiry_date") or "")
            except ValueError:
                continue
            if expiry <= timezone.localtime(deadline).date():
                findings.append({
                    "severity": "high", "source": "rule",
                    "title": _("Certificate expiring before departure: %(c)s") % {"c": cert["name"]},
                    "detail": _("Expiry %(e)s, departure %(d)s.") % {"e": expiry.isoformat(),
                                                                     "d": timezone.localtime(deadline).date().isoformat()},
                    "references": [f"document {review.document.type.code} v{review.document.version}"],
                })
    return findings


def review_call(call, actor) -> AssistantRun:
    _require_enabled(call)
    role = _role(actor, REVIEW_ROLES)
    digest, inventory = payloads.call_digest(call, actor)
    system = REVIEW_SYSTEM.replace("{language}", _language_name())
    return _run(call, actor, role, AssistantRun.Feature.REVIEW, system=system,
                content=[{"type": "text", "text": json.dumps(digest, ensure_ascii=False)}],
                schema=FINDINGS_SCHEMA, inventory=inventory)


@transaction.atomic
def raise_finding(run: AssistantRun, index: int, actor) -> Alert:
    """A person decides that a finding deserves an alert: the alert is theirs, its origin is stated."""
    if run.call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    if run.feature != AssistantRun.Feature.REVIEW or run.requested_by_id != getattr(actor.user, "pk", None):
        raise PermissionRefused(_("Only the person who ran the review can raise its findings."))
    findings = (run.output or {}).get("findings") or []
    if not 0 <= index < len(findings):
        raise RuleViolation(_("Unknown finding."))
    finding = findings[index]
    role = _role(actor, REVIEW_ROLES)
    text = f"{finding.get('title', '')} — {finding.get('detail', '')}"[:430]
    alert = Alert.objects.create(
        call=run.call, kind=AlertKind.ASSISTANT, recipient_roles=sorted({"AGE", "CAP", role}),
        message_fr=f"[Revue assistée, signalée par {role}] {text}"[:500],
        message_en=f"[Assisted review, raised by {role}] {text}"[:500],
    )
    journal.record(
        port=run.call.port, call=run.call, actor=actor, role=role, action="alert.raised", obj=alert,
        visible_roles=sorted({"AGE", "CAP", role}), payload={"assistant_run": run.pk, "finding": index},
        summary_fr=f"Alerte signalée à partir de la revue assistée : {finding.get('title', '')}"[:480],
        summary_en=f"Alert raised from the assisted review: {finding.get('title', '')}"[:480],
    )
    return alert


# ============================================================================ 3. summary of an exchange
def summarize_thread(thread, actor) -> AssistantRun:
    call = thread.call
    _require_enabled(call)
    role = _role(actor, set(actor.roles))
    content, inventory = payloads.thread_content(thread, actor)
    system = ("Summarise this exchange between the parties of a tanker call for a busy reader: what was asked, "
              "what was answered or agreed, what remains open and who must act. Roles stand for organisations. "
              f"Do not add anything that is not in the messages. At most 120 words, in {_language_name()}.")
    return _run(call, actor, role, AssistantRun.Feature.SUMMARY, system=system,
                content=[{"type": "text", "text": json.dumps(content, ensure_ascii=False)}],
                schema=TEXT_SCHEMA, inventory=inventory, max_tokens=1024)


# ============================================================================ 4. draft remarks of the statement of facts
def draft_remarks(call, actor) -> AssistantRun:
    _require_enabled(call)
    role = _role(actor, {"AGE"})
    digest, inventory = payloads.call_digest(call, actor)
    system = ("You draft the 'remarks' section of a statement of facts for the agency of a tanker call. State "
              "facts only, from the registry provided: waiting time, interruptions with their causes and "
              "durations, contested or tacit countersignatures, open disputes, deferred entries. No opinion, "
              "no attribution of responsibility beyond what the registry records. Short paragraphs, at most "
              f"200 words, in {_language_name()}. The agency will review and edit this draft before anyone signs.")
    return _run(call, actor, role, AssistantRun.Feature.REMARKS, system=system,
                content=[{"type": "text", "text": json.dumps(digest, ensure_ascii=False)}],
                schema=TEXT_SCHEMA, inventory=inventory, max_tokens=1500)


# ============================================================================ 5. brief of the port, 6. questions
PORT_ROLES = {"DIR", "CAP", "APO"}
QUESTION_MAX_CHARS = 600
PORT_RULES = (
    "You assist the management of a tanker port with a copy of its operational registry, given as JSON. "
    "Roles stand for organisations; no person is named and none may be. Use only what the JSON contains: "
    "when something is not in it, say that the registry does not show it. Never guess times, quantities or "
    "causes, never attribute responsibility beyond what the registry records, never recommend approving, "
    "refusing, signing or closing anything: people decide. Cite the call references (e.g. TGLFW-2026-0012) "
    "next to every fact. Times are ISO 8601 in UTC unless stated; the port's time zone is given."
)


def port_brief(port, actor, *, visible_calls) -> AssistantRun:
    """The brief of the port for the people who run it: what is under way, what waits, what disagrees."""
    _require_enabled(port=port)
    role = _role(actor, PORT_ROLES)
    digest, inventory = payloads.port_digest(port, actor, visible_calls=visible_calls)
    system = (PORT_RULES + " Write the brief of the port for the harbour master and the direction, for this moment: "
              "1) calls alongside or in operation and where they stand; 2) calls expected, with their next step; "
              "3) decisions waiting for an authority and tasks that are late, by call; 4) disputes open, alerts of "
              "the last 24 hours and discrepancies between the AIS picture and the registry; 5) the indicators of "
              "the last 90 days in one sentence. Short paragraphs, plain words, at most 280 words, in "
              f"{_language_name()}. Omit a section that has nothing to report.")
    return _run(None, actor, role, AssistantRun.Feature.BRIEF, system=system, port=port,
                content=[{"type": "text", "text": json.dumps(digest, ensure_ascii=False)}],
                schema=TEXT_SCHEMA, inventory=inventory, max_tokens=2000)


def ask_port(port, actor, question: str, *, visible_calls) -> AssistantRun:
    """A question on the registry of the port, answered from the digest the asker may see."""
    _require_enabled(port=port)
    role = _role(actor, PORT_ROLES)
    question = (question or "").strip()
    if not question:
        raise RuleViolation(_("Write the question."))
    if len(question) > QUESTION_MAX_CHARS:
        raise RuleViolation(_("The question is too long (%(n)d characters at most).") % {"n": QUESTION_MAX_CHARS})
    digest, inventory = payloads.port_digest(port, actor, visible_calls=visible_calls)
    system = (PORT_RULES + " Answer the question of the reader from the registry only, at most 200 words, in "
              f"{_language_name()}. If the question asks for an opinion, an authorization or a decision, say that "
              "the registry does not decide and give the facts the reader needs instead. If the question concerns "
              "a period the JSON does not cover, say so and point to the statistics page of the platform.")
    content = [{"type": "text", "text": json.dumps(digest, ensure_ascii=False)},
               {"type": "text", "text": "Question: " + question}]
    run = _run(None, actor, role, AssistantRun.Feature.QUESTION, system=system, port=port, content=content,
               schema=TEXT_SCHEMA, inventory=inventory, max_tokens=1500)
    return run
