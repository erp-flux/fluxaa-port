"""Documents generated from the registry, never typed (EF-7.3): statement of facts, time sheet,
pumping log — and the port indicators (EF-10.2), each traceable to its source events."""
from __future__ import annotations

from datetime import timedelta

from django.core.files.base import ContentFile
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from ..models import (
    ACTIVE_STATUSES,
    Alert,
    CallStatus,
    CountersignState,
    DisputeStatus,
    DocumentStatus,
    JournalEntry,
    PortCall,
    ServiceRequest,
    Task,
    TaskStatus,
)
from .errors import PermissionRefused, RuleViolation
from .milestones import overall_state, state_by_role


def _hours(delta) -> float | None:
    return round(delta.total_seconds() / 3600, 2) if delta is not None else None


def interruptions(call: PortCall) -> list[dict]:
    starts = call.milestones.filter(type__code="INTERRUPTION_START", is_conflict=False).select_related("cause")
    ends = {m.related_id: m for m in call.milestones.filter(type__code="INTERRUPTION_END")}
    rows = []
    for start in starts:
        end = ends.get(start.pk)
        duration = (end.declared_at - start.declared_at) if end else None
        state = overall_state(start)
        rows.append({
            "start": start, "end": end, "duration_h": _hours(duration), "cause": start.cause,
            "attribution": start.cause.attributable_to if start.cause else "",
            "emitter_role": start.emitter_role, "state": state,
            "established": state == CountersignState.COUNTERSIGNED,
            "deferred": start.deferred or (end.deferred if end else False),
        })
    return rows


def statement_of_facts(call: PortCall, *, remarks: str = "", remarks_assisted: bool = False, remarks_by: str = "") -> dict:
    milestones = []
    for m in call.milestones.select_related("type", "cause", "stage").prefetch_related("signatures").order_by("declared_at", "recorded_at"):
        milestones.append({"m": m, "states": state_by_role(m), "overall": overall_state(m)})
    last = JournalEntry.objects.filter(call=call).order_by("-seq").first()
    open_disputes = call.disputes.exclude(status__in=[DisputeStatus.CLOSED_AGREED, DisputeStatus.CLOSED_NOT_AGREED])
    return {
        "call": call,
        "vessel": call.vessel,
        "parties": call.parties.filter(revoked_at__isnull=True).select_related("organization").order_by("role"),
        "stages": list(call.stages.select_related("berth").order_by("order")),
        "milestones": milestones,
        "interruptions": interruptions(call),
        "alerts": Alert.objects.filter(call=call).order_by("emitted_at"),  # EF-6.4: every alert is on the statement
        "open_disputes": open_disputes,
        "tacit_count": sum(1 for row in milestones if CountersignState.TACIT in row["states"].values()),
        "deferred_count": sum(1 for row in milestones if row["m"].deferred),
        "generated_at": timezone.now(),
        "registry_hash": last.hash if last else "",
        "registry_seq": last.seq if last else 0,
        "time_sheet": time_sheet(call),
        "remarks": remarks.strip(), "remarks_assisted": remarks_assisted, "remarks_by": remarks_by,
    }


def time_sheet(call: PortCall) -> dict:
    stops = interruptions(call)
    by_attr: dict[str, float] = {}
    total_stop = 0.0
    for row in stops:
        if row["duration_h"]:
            key = row["attribution"] or "UNSPECIFIED"
            by_attr[key] = round(by_attr.get(key, 0) + row["duration_h"], 2)
            total_stop += row["duration_h"]
    gross = _hours(call.t1 - call.t0) if call.t0 and call.t1 else None
    return {
        "waiting_h": _hours(call.atb - call.ata) if call.ata and call.atb else None,
        "nor_to_berth_h": _hours(call.atb - call.nor_at) if call.nor_at and call.atb else None,
        "berth_to_start_h": _hours(call.t0 - call.atb) if call.atb and call.t0 else None,
        "transfer_gross_h": gross,
        "stops_h": round(total_stop, 2),
        "stops_by_attribution": by_attr,
        "transfer_net_h": round(gross - total_stop, 2) if gross is not None else None,
        "end_to_departure_h": _hours(call.atd - call.t1) if call.t1 and call.atd else None,
        "stay_h": _hours(call.atd - call.ata) if call.ata and call.atd else None,
    }


def render_statement(call: PortCall, **remarks) -> str:
    return render_to_string("registry/reports/statement_of_facts.html", statement_of_facts(call, **remarks))


@transaction.atomic
def issue_statement_of_facts(call: PortCall, actor, *, remarks: str = "", remarks_assisted: bool = False):
    """Task 36: the agency produces the consolidated statement of facts; master and terminal sign.

    The facts come from the registry only (EF-7.3). The agency may add remarks — typed by it, or drafted
    with the assistant and then reviewed (EF-17): the statement says so, and people sign it.
    """
    from .documents import upload_document

    if "AGE" not in actor.roles:
        raise PermissionRefused(_("The statement of facts is produced by the agency."))
    if call.status not in (CallStatus.OPS_COMPLETE, CallStatus.DEPARTED):
        raise RuleViolation(_("The statement of facts is produced after the end of operations."))
    previous = call.documents.filter(type__code="SOF", status__in=[DocumentStatus.ISSUED, DocumentStatus.SIGNED]).first()
    html = render_statement(call, remarks=(remarks or "")[:4000], remarks_assisted=bool(remarks and remarks_assisted),
                            remarks_by=actor.label)
    content = ContentFile(html.encode("utf-8"), name=f"{call.reference}_statement_of_facts.html")
    content.content_type = "text/html"
    task = call.tasks.filter(template_code="M0", number="36", status=TaskStatus.PENDING).first()
    statement = upload_document(call, actor, "SOF", content, title=f"Rapport des faits / Statement of facts — {call.reference}",
                                generated=True, previous=previous, task=task, as_role="AGE")
    from .forms import auto_issue

    auto_issue(call, actor, "TIME_SHEET", as_role="AGE")  # the time sheet goes with the statement of facts (M0:37)
    return statement


# ============================================================================ indicators (EF-10.2)
def indicators(port, *, days: int = 90, visible_calls=None) -> dict:
    """Seven indicators, each reconstructible from the registry with its source calls."""
    since = timezone.now() - timedelta(days=days)
    calls = PortCall.objects.filter(port=port, eta__gte=since)
    if visible_calls is not None:
        calls = calls.filter(pk__in=visible_calls.values("pk"))
    calls = list(calls.select_related("vessel"))

    def avg(values):
        values = [v for v in values if v is not None]
        return round(sum(values) / len(values), 2) if values else None

    waiting = [(c.reference, _hours(c.atb - c.ata)) for c in calls if c.ata and c.atb]
    occupancy = [(c.reference, _hours(c.atd - c.atb)) for c in calls if c.atb and c.atd]
    net = []
    dead_total = 0.0
    dead_established = 0.0
    for c in calls:
        sheet = time_sheet(c)
        if sheet["transfer_net_h"] is not None:
            net.append((c.reference, sheet["transfer_net_h"]))
        for row in interruptions(c):
            if row["duration_h"]:
                dead_total += row["duration_h"]
                if row["established"]:
                    dead_established += row["duration_h"]
    tasks = Task.objects.filter(call__in=[c.pk for c in calls], status=TaskStatus.DONE, due_at__isnull=False,
                                criticality="B")
    on_time = sum(1 for t in tasks if t.completed_at and t.completed_at <= t.due_at)
    decisions = ServiceRequest.objects.filter(call__in=[c.pk for c in calls], decided_at__isnull=False,
                                              submitted_at__isnull=False)
    decision_hours = [(r.call.reference, _hours(r.decided_at - r.submitted_at)) for r in decisions.select_related("call")]
    open_disputes = sum(c.disputes.filter(status=DisputeStatus.OPEN).count() for c in calls)
    return {
        "period_days": days,
        "calls": len(calls),
        "active": sum(1 for c in calls if c.status in ACTIVE_STATUSES),
        "kpis": [
            {"code": "WAIT", "label_fr": "Attente moyenne en rade (h)", "label_en": "Average waiting at anchorage (h)",
             "value": avg(v for _r, v in waiting), "sources": [r for r, _v in waiting]},
            {"code": "OCCUPANCY", "label_fr": "Occupation moyenne du poste (h)", "label_en": "Average berth occupancy (h)",
             "value": avg(v for _r, v in occupancy), "sources": [r for r, _v in occupancy]},
            {"code": "NET_TRANSFER", "label_fr": "Durée nette moyenne de transfert (h)", "label_en": "Average net transfer time (h)",
             "value": avg(v for _r, v in net), "sources": [r for r, _v in net]},
            {"code": "DEAD_TIME_ESTABLISHED",
             "label_fr": "Part des temps morts à cause établie contradictoirement (%)",
             "label_en": "Share of dead time with a contradictorily established cause (%)",
             "value": round(dead_established / dead_total * 100, 1) if dead_total else None,
             "sources": [c.reference for c in calls if interruptions(c)]},
            {"code": "ON_TIME", "label_fr": "Tâches bloquantes faites à l'heure (%)", "label_en": "Blocking tasks done on time (%)",
             "value": round(on_time / tasks.count() * 100, 1) if tasks.count() else None,
             "sources": sorted({t.call.reference for t in tasks.select_related("call")})},
            {"code": "DECISION", "label_fr": "Délai moyen de décision des autorités (h)",
             "label_en": "Average decision time of authorities (h)",
             "value": avg(v for _r, v in decision_hours), "sources": sorted({r for r, _v in decision_hours})},
            {"code": "DISPUTES", "label_fr": "Contestations ouvertes", "label_en": "Open disputes",
             "value": open_disputes, "sources": [c.reference for c in calls if c.disputes.filter(status=DisputeStatus.OPEN).exists()]},
        ],
    }


# ============================================================================ calibration (EF-6.5, ENF-8)
def calibration(port, *, days: int = 90) -> dict:
    """What the port administrator needs to tune templates and delays: alert volume per template,
    notifications received per person and per call, late tasks and entry delays per role."""
    from collections import defaultdict

    from ..models import AlertLevel, CallTemplateUse, Milestone, Notification

    since = timezone.now() - timedelta(days=days)
    calls = list(PortCall.objects.filter(port=port, eta__gte=since).exclude(status=CallStatus.DRAFT))
    call_ids = [c.pk for c in calls]
    now = timezone.now()

    templates: dict[str, dict] = defaultdict(lambda: {"calls": set(), "alerts": 0, "by_kind": defaultdict(int)})
    for use in CallTemplateUse.objects.filter(call__in=call_ids).select_related("template_version__template"):
        templates[use.template_version.template.code]["calls"].add(use.call_id)
    for alert in Alert.objects.filter(call__in=call_ids):
        row = templates[alert.template_code or "—"]
        row["calls"].add(alert.call_id)
        row["alerts"] += 1
        row["by_kind"][alert.kind] += 1
    template_rows = []
    for code, row in sorted(templates.items()):
        n = len(row["calls"])
        template_rows.append({"template": code, "calls": n, "alerts": row["alerts"],
                              "alerts_per_call": round(row["alerts"] / n, 1) if n else None,
                              "by_kind": dict(sorted(row["by_kind"].items()))})

    per_pair = defaultdict(int)
    for user_id, call_id in Notification.objects.filter(call__in=call_ids).values_list("user_id", "call_id"):
        per_pair[(user_id, call_id)] += 1
    counts = sorted(per_pair.values())
    notifications = {
        "pairs": len(counts),
        "average": round(sum(counts) / len(counts), 1) if counts else None,
        "max": counts[-1] if counts else None,
        "over_threshold": sum(1 for c in counts if c > 15),  # EF-6 acceptance: < 15 per recipient
    }

    roles: dict[str, dict] = defaultdict(lambda: {"due": 0, "late": 0, "delays": [], "entry": []})
    for task in Task.objects.filter(call__in=call_ids, due_at__isnull=False).exclude(status=TaskStatus.NOT_APPLICABLE):
        row = roles[task.role]
        if task.status == TaskStatus.DONE and task.completed_at:
            row["due"] += 1
            if task.completed_at > task.due_at:
                row["late"] += 1
                row["delays"].append(_hours(task.completed_at - task.due_at))
        elif task.due_at < now:
            row["due"] += 1
            row["late"] += 1
    for m in Milestone.objects.filter(call__in=call_ids).exclude(source="SYSTEM"):
        roles[m.emitter_role]["entry"].append(max(0.0, (m.recorded_at - m.declared_at).total_seconds() / 60))
    role_rows = []
    for role, row in sorted(roles.items()):
        role_rows.append({
            "role": role, "tasks_due": row["due"], "late": row["late"],
            "late_pct": round(row["late"] / row["due"] * 100, 1) if row["due"] else None,
            "average_delay_h": round(sum(row["delays"]) / len(row["delays"]), 1) if row["delays"] else None,
            "milestones": len(row["entry"]),
            "average_entry_delay_min": round(sum(row["entry"]) / len(row["entry"]), 1) if row["entry"] else None,
        })
    escalated = Task.objects.filter(call__in=call_ids, alert_level=AlertLevel.ESCALATED).count()
    return {"period_days": days, "calls": len(calls), "templates": template_rows, "notifications": notifications,
            "roles": role_rows, "escalated_tasks": escalated}
