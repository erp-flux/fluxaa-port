"""The announcement adapts to the operation (FLX-CDC-002 v1.6, EXG-R-11).

Every operation model carries the questions the port asks when it is chosen (``CallTemplate.intake_schema``, the
grammar of the request forms); the agency answers them on the announcement form, the answers are kept on the call
(``PortCall.operation_details``, keyed by template code), shown on its overview, exported, and they pre-fill the
requests the model's tasks will raise — the keys are those of the request forms.
"""
from __future__ import annotations

from datetime import datetime
from decimal import InvalidOperation

from django.utils import formats, timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core.models import pick
from apps.core.numbers import parse_decimal

from ..models import CallTemplate, PortCall, RequestType
from .errors import RuleViolation

FIELD_TYPES = ("text", "textarea", "number", "integer", "datetime", "boolean", "select")


def field_view(field: dict) -> dict:
    """A schema field with its labels, help and choices in the active language."""
    return {
        **field,
        "label": pick(field.get("label_fr", ""), field.get("label_en", "")),
        "help": pick(field.get("help_fr", ""), field.get("help_en", "")),
        "choices": [(o["value"], pick(o.get("label_fr", ""), o.get("label_en", ""))) for o in field.get("options", [])],
    }


def templates_with_intake(port) -> list[dict]:
    """The models of the port that ask something at the announcement, with their fields ready to render."""
    out = []
    for template in CallTemplate.objects.filter(port=port, is_active=True).exclude(intake_schema=[]).order_by("order", "code"):
        out.append({"code": template.code, "name": template.name, "kind": template.kind,
                    "fields": [field_view(f) for f in template.intake_schema or []]})
    return out


def _coerce(field: dict, raw, label: str):
    ftype = field.get("type", "text")
    if ftype == "boolean":
        return bool(raw) and str(raw).lower() not in ("0", "false", "no", "off", "")
    value = (str(raw) if raw is not None else "").strip()
    if value == "":
        return None
    if ftype == "integer":
        try:
            number = parse_decimal(value)
            if number != number.to_integral_value():
                raise ValueError(value)
            return int(number)
        except (InvalidOperation, ValueError):
            raise RuleViolation(_("%(label)s: a whole number is expected.") % {"label": label}) from None
    if ftype == "number":
        try:
            return float(parse_decimal(value))
        except (InvalidOperation, ValueError):
            raise RuleViolation(_("%(label)s: a number is expected.") % {"label": label}) from None
    if ftype == "datetime":
        if isinstance(raw, datetime):
            parsed = raw
        else:
            parsed = parse_datetime(value)
        if parsed is None:
            raise RuleViolation(_("%(label)s: a date and time are expected.") % {"label": label})
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed.isoformat()
    if ftype == "select":
        allowed = {o["value"] for o in field.get("options", [])}
        if allowed and value not in allowed:
            raise RuleViolation(_("%(label)s: choose one of the options offered.") % {"label": label})
        return value
    return value[:2000] if ftype == "textarea" else value[:300]


def parse_intake(port, codes: list[str], values, *, prefix: str = "op_") -> dict:
    """The answers posted for the models chosen, validated against each model's questions.

    *values* is a mapping or a callable ``(name) -> raw``; the form names the field of model M4 ``op_M4_grade``,
    the API sends ``{"M4": {"grade": …}}`` (see :func:`parse_intake_mapping`). A required question of a chosen
    model without an answer is refused; questions of models not chosen are ignored."""
    getter = values if callable(values) else values.get
    details: dict[str, dict] = {}
    for template in CallTemplate.objects.filter(port=port, code__in=codes).exclude(intake_schema=[]):
        answers = {}
        for field in template.intake_schema or []:
            key = field.get("key")
            if not key:
                continue
            label = f"{template.code} — {pick(field.get('label_fr', ''), field.get('label_en', '')) or key}"
            value = _coerce(field, getter(f"{prefix}{template.code}_{key}"), label)
            if field.get("required") and field.get("type") != "boolean" and (value is None or value == ""):
                raise RuleViolation(_("%(label)s is required for this operation.") % {"label": label})
            if value is not None and value != "" and not (field.get("type") == "boolean" and value is False):
                answers[key] = value
        if answers:
            details[template.code] = answers
    return details


def parse_intake_mapping(port, codes: list[str], mapping: dict | None) -> dict:
    """The API form: ``{"M4": {"grade": "VLSFO", …}}``."""
    mapping = mapping or {}
    if not isinstance(mapping, dict) or any(not isinstance(v, dict) for v in mapping.values()):
        raise RuleViolation(_("operation_details is an object keyed by template code."))

    def getter(name: str):
        code, _sep, key = name[len("op_"):].partition("_")
        return mapping.get(code, {}).get(key)

    return parse_intake(port, codes, getter)


def declared(call: PortCall) -> list[dict]:
    """What the agency declared for each operation, ready to show: model name and (label, value) pairs."""
    details = call.operation_details or {}
    if not details:
        return []
    templates = {t.code: t for t in CallTemplate.objects.filter(port=call.port, code__in=list(details))}
    out = []
    # the models in the port's own order, the answers in the order of the questions (the stored object has none)
    for code in sorted(details, key=lambda c: (templates[c].order if c in templates else 999, c)):
        answers = details[code] or {}
        template = templates.get(code)
        schema = {f.get("key"): f for f in (template.intake_schema if template else []) or []}
        ordered = [k for k in schema if k in answers] + [k for k in answers if k not in schema]
        rows = []
        for key in ordered:
            field = schema.get(key, {"key": key, "label_fr": key, "label_en": key, "type": "text"})
            rows.append((pick(field.get("label_fr", key), field.get("label_en", key)), display_value(field, answers[key])))
        out.append({"code": code, "name": template.name if template else code, "rows": rows})
    return out


def display_value(field: dict, value) -> str:
    ftype = field.get("type", "text")
    if ftype == "boolean":
        return _("yes") if value else _("no")
    if ftype == "select":
        for o in field.get("options", []):
            if o.get("value") == value:
                return pick(o.get("label_fr", ""), o.get("label_en", "")) or str(value)
        return str(value)
    if ftype == "datetime":
        parsed = parse_datetime(str(value))
        if parsed is not None:
            return timezone.localtime(parsed).strftime("%d/%m/%Y %H:%M")
    if ftype in ("number", "integer") and isinstance(value, (int, float)) and not isinstance(value, bool):
        # a number is read the way the reader's language writes it: 1 200 and 450,5 in French, 1,200 and 450.5 in English
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return formats.number_format(value, use_l10n=True, force_grouping=True)
    return str(value)


# Facts about the vessel, declared once at the announcement and true for any request that asks for them
SHARED_KEYS = {"last_cargoes"}


def prefill_for_request(call: PortCall, request_type: RequestType) -> dict:
    """The values a request form starts with — never more than the registry can vouch for:

    * the announcement's answers to the questions of the models **whose tasks raise this request** (the bunkering
      request from the bunkering model, the ballast discharge from the ballast model…), for the keys the form
      shares. A key shared by chance with another model is not carried: the volume of ballast is not the volume
      of waste, the duration of a double banking is not the duration of an immobilisation;
    * the facts about the vessel the agency declared once (``SHARED_KEYS``: the last three cargoes), whichever
      model asked for them;
    * what the call itself says (product, quantity, requested berth) and the partner vessel of its link."""
    details = call.operation_details or {}
    target = {f.get("key"): f for f in request_type.form_schema or [] if f.get("key")}
    keys = set(target)
    if not keys:
        return {}
    raising = set(call.tasks.filter(request_type_code=request_type.code).values_list("template_code", flat=True))
    asked = {t.code: {f.get("key"): f for f in t.intake_schema or []}
             for t in CallTemplate.objects.filter(port=call.port, code__in=list(details))}
    values: dict = {}

    def carry(code: str, key: str, value) -> None:
        source = asked.get(code, {}).get(key, {})
        accepted = {o.get("value") for o in target[key].get("options", [])}
        if source.get("type") == "select" and value not in accepted:
            # a choice of the announcement carried into a free-text field reads in words, not as a code
            value = display_value(source, value)
        values[key] = value

    for code in sorted(details):
        for key, value in (details[code] or {}).items():
            if key in keys and key not in values and (code in raising or key in SHARED_KEYS):
                carry(code, key, value)
    if "product" in keys and call.product:
        values.setdefault("product", call.product)
    if "quantity" in keys and call.quantity is not None:
        values.setdefault("quantity", float(call.quantity))
    if "requested_berth" in keys and call.requested_berth_id:
        values.setdefault("requested_berth", call.requested_berth.code)
    partner = call.linked_call
    if partner is not None:
        if "partner_vessel" in keys and "partner_vessel" not in values:
            values["partner_vessel"] = f"{partner.vessel.name} (IMO {partner.vessel.imo}) — {partner.reference}"
        if "inner_vessel" in keys and "inner_vessel" not in values:
            inner = partner if call.link_kind == "OUTER" else call if call.link_kind == "INNER" else None
            if inner is not None:
                values["inner_vessel"] = f"{inner.vessel.name} (IMO {inner.vessel.imo}) — {inner.reference}"
    # datetime values are kept in ISO form: the datetime-local input wants minutes precision, local time; a whole
    # number kept as a float shows as a whole number
    for field in request_type.form_schema or []:
        key = field.get("key")
        if key in values and field.get("type") == "datetime":
            parsed = parse_datetime(str(values[key]))
            if parsed is not None:
                values[key] = timezone.localtime(parsed).strftime("%Y-%m-%dT%H:%M")
        elif key in values and isinstance(values[key], float) and values[key].is_integer():
            values[key] = int(values[key])
    return values
