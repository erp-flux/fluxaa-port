from datetime import datetime
from decimal import Decimal, InvalidOperation

from django import template
from django.utils import formats, timezone
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from apps.core.models import pick
from apps.core.roles import role_label

register = template.Library()

STATE_CLASS = {"COUNTERSIGNED": "done", "TACIT": "tacit", "CONTESTED": "contested", "PENDING": "pending"}
ALERT_CLASS = {"REMINDER": "reminder", "LATE": "late", "ESCALATED": "escalated"}


@register.filter
def role_name(code):
    return role_label(code)


@register.filter
def get(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def state_class(state):
    return STATE_CLASS.get(state, "pending")


@register.filter
def state_label(state):
    return {
        "COUNTERSIGNED": _("countersigned"), "TACIT": _("tacit"), "CONTESTED": _("contested"), "PENDING": _("pending"),
    }.get(state, state)


@register.filter
def alert_class(level):
    return ALERT_CLASS.get(level, "")


@register.filter
def alert_label(level):
    return {"REMINDER": _("Due soon"), "LATE": _("Late"), "ESCALATED": _("Escalated")}.get(level, "")


@register.filter
def task_status_class(status):
    return {"DONE": "done", "NA": "na"}.get(status, "pending")


@register.filter
def bilingual(obj, field):
    return pick(getattr(obj, f"{field}_fr", "") or obj.get(f"{field}_fr", ""), getattr(obj, f"{field}_en", "") or obj.get(f"{field}_en", "")) \
        if isinstance(obj, dict) else pick(getattr(obj, f"{field}_fr", ""), getattr(obj, f"{field}_en", ""))


@register.filter
def nature_label(code):
    return {"F": _("Provide a document"), "R": _("Enter data"), "D": _("Decide"), "C": _("Confirm execution"),
            "S": _("Sign")}.get(code, code)


@register.filter
def short_hash(value, length=12):
    return (value or "")[: int(length)]


def _format_value(value, field: dict) -> str:
    """Human rendering of a value entered through a configurable request form."""
    if value is None or value == "":
        return "—"
    ftype = field.get("type", "text")
    if isinstance(value, bool) or ftype == "boolean":
        return _("Yes") if value in (True, "true", "True", "on", "1", 1) else _("No")
    if ftype == "select":
        for option in field.get("options") or []:
            if isinstance(option, dict) and str(option.get("value")) == str(value):
                return pick(option.get("label_fr", ""), option.get("label_en", "")) or str(value)
        return str(value)
    if ftype == "datetime" or (isinstance(value, str) and len(value) >= 16 and value[4:5] == "-" and "T" in value):
        moment = parse_datetime(value) if isinstance(value, str) else value
        if isinstance(moment, datetime):
            if timezone.is_naive(moment):
                moment = timezone.make_aware(moment)
            return formats.date_format(timezone.localtime(moment), "d/m/Y H:i")
    if ftype in ("number", "integer"):
        try:
            return formats.number_format(Decimal(str(value)).normalize(), use_l10n=True, force_grouping=True)
        except (InvalidOperation, ValueError):
            return str(value)
    return str(value)


@register.filter
def request_fields(req):
    """(label, value) pairs of a request's form data, labelled and formatted after the type's form schema."""
    schema = [f for f in (req.type.form_schema or []) if isinstance(f, dict) and f.get("key")]
    by_key = {f["key"]: f for f in schema}
    data = req.data or {}
    keys = [f["key"] for f in schema if f["key"] in data] + [k for k in data if k not in by_key]
    rows = []
    for key in keys:
        field = by_key.get(key, {})
        label = pick(field.get("label_fr", ""), field.get("label_en", "")) or key.replace("_", " ").capitalize()
        rows.append((label, _format_value(data[key], field)))
    return rows


@register.filter
def auth_state(auth):
    """valid / expired / cancelled / upcoming — computed at display time, whatever the scheduler has done."""
    if auth.is_cancelled:
        return "cancelled"
    now = timezone.now()
    if now < auth.valid_from:
        return "upcoming"
    return "valid" if now < auth.valid_until else "expired"


@register.filter
def auth_state_label(state):
    return {"valid": _("valid"), "expired": _("expired"), "cancelled": _("cancelled"),
            "upcoming": _("not yet in force")}.get(state, state)


@register.filter
def auth_state_class(state):
    return {"valid": "done", "expired": "na", "cancelled": "contested", "upcoming": "pending"}.get(state, "pending")


@register.filter
def label_parts(label):
    """Split a frozen actor label "Name — Organisation" into its two parts for display."""
    name, _sep, rest = (label or "").partition(" — ")
    return name, rest
