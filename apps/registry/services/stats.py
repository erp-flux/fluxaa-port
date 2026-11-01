"""Statistics of a port over a period (EF-10.2 extended): every figure is computed from the registry when the
page is opened, never stored, and every series names what it counts so that it can be rebuilt by hand.

Figures are grouped by calendar month of the ETA (calls) or of the event (decisions, disputes, signatures).
Nothing here decides anything: the page serves the direction, the authority and the harbour master to see the
port as it is, and FLUXAA to compare ports on a national instance.
"""
from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.db.models import Count
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.core.models import Berth

from ..models import (
    Alert,
    CallStatus,
    CountersignState,
    Dispute,
    DisputeStatus,
    Document,
    Milestone,
    MilestoneSignature,
    PortCall,
    RequestStatus,
    ServiceRequest,
    Task,
    TaskStatus,
    TemplateKind,
)
from .reports import _hours, interruptions, time_sheet

DEFAULT_DAYS = 365


def _month(moment) -> str:
    local = timezone.localtime(moment) if timezone.is_aware(moment) else moment
    return f"{local.year:04d}-{local.month:02d}"


def months_between(start: datetime, end: datetime) -> list[str]:
    out, cursor = [], date(start.year, start.month, 1)
    last = date(end.year, end.month, 1)
    while cursor <= last:
        out.append(f"{cursor.year:04d}-{cursor.month:02d}")
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return out


def _avg(values) -> float | None:
    values = [v for v in values if v is not None]
    return round(sum(values) / len(values), 1) if values else None


def _median(values) -> float | None:
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    mid = len(values) // 2
    return round(values[mid] if len(values) % 2 else (values[mid - 1] + values[mid]) / 2, 1)


def _pct(part, whole) -> float | None:
    return round(part / whole * 100, 1) if whole else None


def _label(obj, attr_fr: str, attr_en: str) -> str:
    return getattr(obj, attr_en if translation.get_language() == "en" else attr_fr)


def period(start: date | None, end: date | None, *, days: int = DEFAULT_DAYS) -> tuple[datetime, datetime]:
    """[start, end) as aware datetimes; defaults to the last *days* days ending today."""
    tz = timezone.get_current_timezone()
    end_day = end or timezone.localdate()
    start_day = start or (end_day - timedelta(days=days))
    if start_day >= end_day:
        start_day = end_day - timedelta(days=1)
    return (timezone.make_aware(datetime.combine(start_day, datetime.min.time()), tz),
            timezone.make_aware(datetime.combine(end_day + timedelta(days=1), datetime.min.time()), tz))


def compute(port, start: datetime, end: datetime, *, visible_calls=None) -> dict:
    months = months_between(start, end)
    calls = PortCall.objects.filter(port=port, eta__gte=start, eta__lt=end).exclude(status=CallStatus.DRAFT)
    if visible_calls is not None:
        calls = calls.filter(pk__in=visible_calls.values("pk"))
    calls = list(calls.select_related("vessel", "berth").prefetch_related("template_uses__template_version__template"))
    call_ids = [c.pk for c in calls]

    # ---------------------------------------------------------------- calls, quantities, durations per month
    per_month = {m: {"month": m, "calls": 0, "completed": 0, "cancelled": 0, "quantity_mt": Decimal("0"),
                     "waiting_h": [], "transfer_h": [], "stay_h": []} for m in months}
    operations, areas, products = Counter(), Counter(), defaultdict(lambda: Decimal("0"))
    occupancy = defaultdict(float)
    interruption_rows = []
    for call in calls:
        bucket = per_month.setdefault(_month(call.eta), {"month": _month(call.eta), "calls": 0, "completed": 0,
                                                         "cancelled": 0, "quantity_mt": Decimal("0"),
                                                         "waiting_h": [], "transfer_h": [], "stay_h": []})
        bucket["calls"] += 1
        if call.status in (CallStatus.CLOSED, CallStatus.ARCHIVED, CallStatus.DEPARTED):
            bucket["completed"] += 1
        if call.status in (CallStatus.CANCELLED, CallStatus.REJECTED):
            bucket["cancelled"] += 1
        if call.quantity and (call.quantity_unit or "MT") == "MT":
            bucket["quantity_mt"] += call.quantity
            products[call.product or _("(product not stated)")] += call.quantity
        if call.ata and call.atb:
            bucket["waiting_h"].append(_hours(call.atb - call.ata))
        if call.ata and call.atd:
            bucket["stay_h"].append(_hours(call.atd - call.ata))
        sheet = time_sheet(call)
        if sheet["transfer_net_h"] is not None:
            bucket["transfer_h"].append(sheet["transfer_net_h"])
        for use in call.template_uses.all():
            template = use.template_version.template
            if template.kind == TemplateKind.OPERATION:
                operations[_label(template, "name_fr", "name_en")] += 1
        areas[call.get_requested_berth_kind_display()] += 1
        if call.berth_id and call.atb and call.atd:
            occupancy[call.berth_id] += _hours(call.atd - call.atb) or 0
        for row in interruptions(call):
            row["call"] = call
            interruption_rows.append(row)
    monthly = []
    for m in months:
        b = per_month[m]
        monthly.append({"month": m, "calls": b["calls"], "completed": b["completed"], "cancelled": b["cancelled"],
                        "quantity_mt": float(b["quantity_mt"]), "waiting_h": _avg(b["waiting_h"]),
                        "transfer_h": _avg(b["transfer_h"]), "stay_h": _avg(b["stay_h"])})

    # ---------------------------------------------------------------- berths
    berths = []
    hours_in_period = (end - start).total_seconds() / 3600
    for berth in Berth.objects.filter(port=port).order_by("kind", "code"):
        n = sum(1 for c in calls if c.berth_id == berth.pk)
        hours = round(occupancy.get(berth.pk, 0.0), 1)
        berths.append({"berth": berth, "calls": n, "hours": hours,
                       "rate_pct": round(min(hours / hours_in_period * 100, 100), 1) if berth.kind == "JETTY" else None})

    # ---------------------------------------------------------------- interruptions
    by_cause, by_attribution = {}, Counter()
    total_hours = established_hours = 0.0
    for row in interruption_rows:
        cause = row["cause"]
        key = _label(cause, "label_fr", "label_en") if cause else _("(no cause)")
        entry = by_cause.setdefault(key, {"cause": key, "attribution": row["attribution"], "count": 0, "hours": 0.0})
        entry["count"] += 1
        hours = row["duration_h"] or 0
        entry["hours"] = round(entry["hours"] + hours, 1)
        by_attribution[row["attribution"] or "?"] += hours
        total_hours += hours
        if row["established"]:
            established_hours += hours
    causes = sorted(by_cause.values(), key=lambda e: (-e["hours"], -e["count"]))

    # ---------------------------------------------------------------- decisions
    decided = (ServiceRequest.objects.filter(call__port=port, decided_at__gte=start, decided_at__lt=end,
                                             submitted_at__isnull=False)
               .select_related("type", "call"))
    if visible_calls is not None:
        decided = decided.filter(call__in=visible_calls.values("pk"))
    decisions = {}
    for req in decided:
        key = _label(req.type, "label_fr", "label_en")
        entry = decisions.setdefault(key, {"type": key, "count": 0, "refused": 0, "conditions": 0, "hours": [],
                                           "roles": set()})
        entry["count"] += 1
        entry["hours"].append(_hours(req.decided_at - req.submitted_at))
        entry["roles"].add(req.decision_role)
        if req.decision == RequestStatus.REFUSED:
            entry["refused"] += 1
        if req.decision == RequestStatus.APPROVED_WITH_CONDITIONS:
            entry["conditions"] += 1
    decision_rows = []
    for entry in sorted(decisions.values(), key=lambda e: -e["count"]):
        decision_rows.append({"type": entry["type"], "count": entry["count"], "refused": entry["refused"],
                              "conditions": entry["conditions"], "avg_h": _avg(entry["hours"]),
                              "median_h": _median(entry["hours"]), "max_h": round(max(entry["hours"]), 1),
                              "roles": ", ".join(sorted(entry["roles"]))})

    # ---------------------------------------------------------------- disputes and countersignatures
    disputes = Dispute.objects.filter(call__port=port, opened_at__gte=start, opened_at__lt=end)
    if visible_calls is not None:
        disputes = disputes.filter(call__in=visible_calls.values("pk"))
    disputes = list(disputes)
    closed = [d for d in disputes if d.closed_at]
    dispute_stats = {
        "opened": len(disputes), "open": sum(1 for d in disputes if d.status in (DisputeStatus.OPEN, DisputeStatus.ANSWERED)),
        "agreed": sum(1 for d in disputes if d.status == DisputeStatus.CLOSED_AGREED),
        "not_agreed": sum(1 for d in disputes if d.status == DisputeStatus.CLOSED_NOT_AGREED),
        "auto": sum(1 for d in disputes if d.auto_created),
        "days_to_close": _avg((d.closed_at - d.opened_at).total_seconds() / 86400 for d in closed),
        "by_kind": dict(Counter(d.get_target_kind_display() for d in disputes)),
    }
    signatures = MilestoneSignature.objects.filter(milestone__call__port=port, at__gte=start, at__lt=end)
    if visible_calls is not None:
        signatures = signatures.filter(milestone__call__in=visible_calls.values("pk"))
    sig_counts = Counter(signatures.values_list("state", flat=True))
    total_sig = sum(sig_counts.values())
    countersign = {
        "total": total_sig, "countersigned": sig_counts.get(CountersignState.COUNTERSIGNED, 0),
        "tacit": sig_counts.get(CountersignState.TACIT, 0), "contested": sig_counts.get(CountersignState.CONTESTED, 0),
        "tacit_pct": _pct(sig_counts.get(CountersignState.TACIT, 0), total_sig),
        "contested_pct": _pct(sig_counts.get(CountersignState.CONTESTED, 0), total_sig),
    }

    # ---------------------------------------------------------------- entries, documents, alerts, tasks
    milestones = Milestone.objects.filter(call__port=port, recorded_at__gte=start, recorded_at__lt=end)
    if visible_calls is not None:
        milestones = milestones.filter(call__in=visible_calls.values("pk"))
    source_counts = dict(Counter(milestones.values_list("source", flat=True)))
    deferred = milestones.filter(deferred=True).count()
    documents = Document.objects.filter(call__port=port, created_at__gte=start, created_at__lt=end)
    if visible_calls is not None:
        documents = documents.filter(call__in=visible_calls.values("pk"))
    alerts = Alert.objects.filter(call__port=port, emitted_at__gte=start, emitted_at__lt=end)
    if visible_calls is not None:
        alerts = alerts.filter(call__in=visible_calls.values("pk"))
    alert_counts = {row["kind"]: row["n"] for row in alerts.values("kind").annotate(n=Count("pk"))}
    tasks = Task.objects.filter(call__in=call_ids, status=TaskStatus.DONE, due_at__isnull=False, completed_at__isnull=False)
    by_role = {}
    for task in tasks.only("role", "due_at", "completed_at", "criticality"):
        entry = by_role.setdefault(task.role, {"role": task.role, "done": 0, "on_time": 0, "blocking": 0, "blocking_on_time": 0})
        entry["done"] += 1
        on_time = task.completed_at <= task.due_at
        entry["on_time"] += int(on_time)
        if task.criticality == "B":
            entry["blocking"] += 1
            entry["blocking_on_time"] += int(on_time)
    task_rows = []
    for entry in sorted(by_role.values(), key=lambda e: e["role"]):
        task_rows.append({**entry, "on_time_pct": _pct(entry["on_time"], entry["done"]),
                          "blocking_on_time_pct": _pct(entry["blocking_on_time"], entry["blocking"])})

    waiting_all = [v for b in per_month.values() for v in b["waiting_h"]]
    transfer_all = [v for b in per_month.values() for v in b["transfer_h"]]
    stay_all = [v for b in per_month.values() for v in b["stay_h"]]
    return {
        "port": port, "start": start, "end": end, "months": months, "monthly": monthly,
        "totals": {
            "calls": len(calls), "completed": sum(m["completed"] for m in monthly),
            "cancelled": sum(m["cancelled"] for m in monthly),
            "quantity_mt": float(sum((b["quantity_mt"] for b in per_month.values()), Decimal("0"))),
            "waiting_h": _avg(waiting_all), "waiting_median_h": _median(waiting_all),
            "transfer_h": _avg(transfer_all), "stay_h": _avg(stay_all),
            "interruption_hours": round(total_hours, 1), "interruptions": len(interruption_rows),
            "established_pct": _pct(established_hours, total_hours),
            "decisions": sum(r["count"] for r in decision_rows),
            "decision_h": _avg(h for e in decisions.values() for h in e["hours"]),
            "documents": documents.count(), "milestones": milestones.count(), "deferred": deferred,
            "alerts": sum(alert_counts.values()),
        },
        "operations": sorted(operations.items(), key=lambda kv: -kv[1]),
        "areas": sorted(areas.items(), key=lambda kv: -kv[1]),
        "products": sorted(((k, float(v)) for k, v in products.items()), key=lambda kv: -kv[1])[:10],
        "berths": berths, "causes": causes,
        "attribution": sorted(((k, round(v, 1)) for k, v in by_attribution.items()), key=lambda kv: -kv[1]),
        "decisions": decision_rows, "disputes": dispute_stats, "countersign": countersign,
        "sources": source_counts, "alerts": alert_counts, "tasks": task_rows,
    }


# ------------------------------------------------------------------------------------------------- charts
def bar_chart(points: list[tuple[str, float | None]], *, unit: str = "", decimals: int = 0, width: int = 760,
              height: int = 220) -> dict:
    """Geometry of a simple bar chart for the template (one bar per point, value written above)."""
    values = [v for _k, v in points if v is not None]
    top = max(values) if values else 0
    left, bottom, gap = 44, 36, 6
    inner_w, inner_h = width - left - 12, height - bottom - 24
    n = max(len(points), 1)
    bar_w = max((inner_w - gap * (n - 1)) / n, 2)
    bars = []
    for i, (label, value) in enumerate(points):
        h = (value or 0) / top * inner_h if top else 0
        x = left + i * (bar_w + gap)
        bars.append({"x": round(x, 1), "y": round(height - bottom - h, 1), "w": round(bar_w, 1), "h": round(h, 1),
                     "label": label, "value": None if value is None else (f"{value:.{decimals}f}"),
                     "lx": round(x + bar_w / 2, 1)})
    grid = []
    if decimals == 0 and 0 < top <= 6:  # small counts: one line per unit, no rounded duplicates
        steps = [(k, k) for k in range(1, int(top) + 1)]
    else:
        steps = [(top * k / 3, k / 3) for k in range(1, 4)]
    for value, share in steps:
        if top:
            grid.append({"y": round(height - bottom - inner_h * share, 1), "value": f"{value:.{decimals}f}"})
    return {"width": width, "height": height, "bars": bars, "grid": grid, "unit": unit, "baseline": height - bottom,
            "left": left, "right": width - 12, "every": max(1, n // 12)}


def to_csv(data: dict) -> str:
    """Every table of the page, flattened: one block per subject, separated by a blank line."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["port", data["port"].code, "from", data["start"].date().isoformat(), "to",
                     (data["end"] - timedelta(days=1)).date().isoformat()])
    writer.writerow([])
    writer.writerow(["month", "calls", "completed", "cancelled", "quantity_mt", "waiting_h", "transfer_h", "stay_h"])
    for m in data["monthly"]:
        writer.writerow([m["month"], m["calls"], m["completed"], m["cancelled"], m["quantity_mt"], m["waiting_h"],
                         m["transfer_h"], m["stay_h"]])
    writer.writerow([])
    writer.writerow(["operation", "calls"])
    writer.writerows(data["operations"])
    writer.writerow([])
    writer.writerow(["area", "calls"])
    writer.writerows(data["areas"])
    writer.writerow([])
    writer.writerow(["product", "quantity_mt"])
    writer.writerows(data["products"])
    writer.writerow([])
    writer.writerow(["berth", "kind", "calls", "hours", "rate_pct"])
    for b in data["berths"]:
        writer.writerow([b["berth"].code, b["berth"].kind, b["calls"], b["hours"], b["rate_pct"]])
    writer.writerow([])
    writer.writerow(["interruption_cause", "attribution", "count", "hours"])
    for c in data["causes"]:
        writer.writerow([c["cause"], c["attribution"], c["count"], c["hours"]])
    writer.writerow([])
    writer.writerow(["decision_type", "roles", "count", "refused", "with_conditions", "avg_h", "median_h", "max_h"])
    for d in data["decisions"]:
        writer.writerow([d["type"], d["roles"], d["count"], d["refused"], d["conditions"], d["avg_h"], d["median_h"], d["max_h"]])
    writer.writerow([])
    writer.writerow(["disputes_opened", "open", "agreed", "not_agreed", "auto", "days_to_close"])
    d = data["disputes"]
    writer.writerow([d["opened"], d["open"], d["agreed"], d["not_agreed"], d["auto"], d["days_to_close"]])
    writer.writerow([])
    writer.writerow(["countersignatures", "countersigned", "tacit", "contested", "tacit_pct", "contested_pct"])
    c = data["countersign"]
    writer.writerow([c["total"], c["countersigned"], c["tacit"], c["contested"], c["tacit_pct"], c["contested_pct"]])
    writer.writerow([])
    writer.writerow(["alert_kind", "count"])
    writer.writerows(sorted(data["alerts"].items()))
    writer.writerow([])
    writer.writerow(["role", "tasks_done", "on_time", "on_time_pct", "blocking", "blocking_on_time", "blocking_on_time_pct"])
    for t in data["tasks"]:
        writer.writerow([t["role"], t["done"], t["on_time"], t["on_time_pct"], t["blocking"], t["blocking_on_time"],
                         t["blocking_on_time_pct"]])
    return out.getvalue()
