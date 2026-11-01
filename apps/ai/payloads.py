"""What may be sent to the AI provider — built only from what the requesting actor may see.

Three rules, each covered by tests:
  * the security domain (N4) is never read: this package does not import ``apps.secure`` and skips
    anything marked N4;
  * persons are replaced by their role on the call (no names, e-mails or phone numbers);
  * every object used is listed in the run's inventory, so that a request can be audited afterwards.
"""
from __future__ import annotations

import base64
import mimetypes

from django.utils.translation import gettext as _

from apps.registry.models import Confidentiality, TaskStatus
from apps.registry.services import rights

from .client import AssistantUnavailable

MAX_DOCUMENT_BYTES = 20 * 1024 * 1024
IMAGE_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}


def _iso(moment):
    return moment.isoformat() if moment else None


def _not_n4(obj) -> bool:
    return getattr(obj, "confidentiality", "") != Confidentiality.N4


# ============================================================================ documents
def document_content(doc) -> tuple[list[dict], list[str]]:
    if not _not_n4(doc):
        raise AssistantUnavailable(_("Security documents are never sent to the assistant."))
    mime = (doc.mime_type or mimetypes.guess_type(doc.original_name)[0] or "").lower()
    if mime != "application/pdf" and mime not in IMAGE_TYPES:
        raise AssistantUnavailable(_("Only PDF files and images can be read by the assistant."))
    if doc.size and doc.size > MAX_DOCUMENT_BYTES:
        raise AssistantUnavailable(_("This file is too large for the assistant (20 MB maximum)."))
    with doc.file.open("rb") as handle:
        data = base64.standard_b64encode(handle.read()).decode("ascii")
    block_type = "document" if mime == "application/pdf" else "image"
    return [{"type": block_type, "source": {"type": "base64", "media_type": mime, "data": data}}], [f"document:{doc.pk}"]


# ============================================================================ the call, as the actor sees it
def call_digest(call, actor) -> tuple[dict, list[str]]:
    """A structured, pseudonymised picture of the call restricted to what *actor* may see."""
    inventory = [f"call:{call.pk}"]
    digest = {
        "call": {
            "reference": call.reference, "status": call.status, "operating_area": call.requested_berth_kind,
            "berth": call.berth.code if call.berth else None, "operations": list(call.template_codes),
            "product": call.product, "declared_quantity": str(call.quantity) if call.quantity is not None else None,
            "unit": call.quantity_unit, "eta": _iso(call.eta), "etb": _iso(call.etb), "etd": _iso(call.etd),
            "ata": _iso(call.ata), "nor": _iso(call.nor_at), "atb": _iso(call.atb), "t0_start_of_transfer": _iso(call.t0),
            "t1_end_of_transfer": _iso(call.t1), "atd": _iso(call.atd), "port_time_zone": call.port.timezone,
        },
        "vessel": {"name": call.vessel.name, "imo": call.vessel.imo, "flag": call.vessel.flag,
                   "type": call.vessel.vessel_type, "dwt": call.vessel.dwt},
        "your_roles": sorted(actor.roles),
    }
    milestones = []
    for m in rights.visible_milestones(actor, call):
        from apps.registry.services.milestones import state_by_role

        milestones.append({
            "type": m.type.code, "label": m.type.label_en, "declared_at": _iso(m.declared_at),
            "recorded_at": _iso(m.recorded_at), "emitter_role": m.emitter_role, "source": m.source,
            "deferred_entry": m.deferred, "competing_entry": m.is_conflict,
            "cause": m.cause.label_en if m.cause else None, "cause_reason": m.cause_reason or None,
            "countersignatures": {role: state for role, state in state_by_role(m).items()},
        })
        inventory.append(f"milestone:{m.pk}")
    digest["milestones"] = milestones

    tasks = []
    for t in rights.visible_tasks(actor, call):
        if t.status != TaskStatus.PENDING:
            continue
        tasks.append({"code": t.code, "title": t.title_en, "role": t.role, "blocking": t.is_blocking,
                      "due_at": _iso(t.due_at), "alert": t.alert_level})
        inventory.append(f"task:{t.pk}")
    digest["open_tasks"] = tasks

    requests = []
    for r in rights.visible_requests(actor, call):
        if not _not_n4(r):
            continue
        auth = getattr(r, "authorization", None) if hasattr(r, "authorization") else None
        requests.append({"type": r.type.code, "label": r.type.label_en, "status": r.status,
                         "requester_role": r.requester_role, "decided_at": _iso(r.decided_at),
                         "authorization_valid_until": _iso(auth.valid_until) if auth else None})
        inventory.append(f"request:{r.pk}")
    digest["requests"] = requests

    documents = []
    for d in rights.visible_documents(actor, call):
        if not _not_n4(d):
            continue
        row = {"type": d.type.code, "label": d.type.label_en, "version": d.version, "status": d.status,
               "issuer_role": d.issuer_role, "issued_at": _iso(d.issued_at)}
        validated = d.extraction_reviews.filter(status="APPLIED").order_by("-validated_at").first()
        if validated and d.type.code == "CERTIFICATES":
            row["validated_certificates"] = (validated.validated or {}).get("certificates", [])
        documents.append(row)
        inventory.append(f"document:{d.pk}")
    digest["documents"] = documents

    if rights.measurements_visible(actor):
        measures = []
        for m in call.measurements.all():
            values = {party: str(v.value) for party, v in m.current_values().items()}
            measures.append({"kind": m.kind, "unit": m.unit, "tolerance_pct": str(m.tolerance_pct), "values": values,
                             "differences": [{"between": f"{d['a']}-{d['b']}", "difference": str(d["difference"]),
                                              "percent": f"{d['percent']:.3f}" if d["percent"] is not None else None}
                                             for d in m.differences()]})
            inventory.append(f"measurement:{m.pk}")
        digest["measurements"] = measures
        digest["pumping_log"] = [
            {"at": _iso(p.declared_at), "manifold_pressure_bar": str(p.manifold_pressure_bar or ""),
             "rate_m3h": str(p.flow_rate_m3h or ""), "temperature_c": str(p.temperature_c or "")}
            for p in call.pumping_log.all()
        ]

    disputes = []
    for d in call.disputes.all():
        if rights.dispute_header_visible(actor, d):
            disputes.append({"subject": d.subject, "status": d.status, "about": d.target_kind,
                             "opened_by_role": d.opened_role, "counterpart_role": d.counterpart_role})
            inventory.append(f"dispute:{d.pk}")
    digest["disputes"] = disputes
    return digest, inventory


def thread_content(thread, actor) -> tuple[dict, list[str]]:
    if not rights.thread_visible(actor, thread) or not _not_n4(thread):
        raise AssistantUnavailable(_("This exchange is not visible to your role."))
    messages = [{"role": m.role, "sent_at": _iso(m.sent_at), "text": m.body} for m in thread.messages.all()]
    return ({"subject": thread.subject, "participants": sorted(set(thread.participant_roles or []) | {thread.created_role}),
             "messages": messages},
            [f"thread:{thread.pk}"] + [f"message:{m.pk}" for m in thread.messages.all()])


def port_digest(port, actor, *, visible_calls, now=None) -> tuple[dict, list[str]]:
    """The port as the registry shows it to *actor* today: calls under way and expected, what waits for a
    decision, what is late, what is disputed, what the AIS board heard, and the indicators of the last 90 days.
    Same rules as the call digest: no person, nothing of the security domain, every source listed."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.ais import services as ais_svc
    from apps.registry.models import ACTIVE_STATUSES, Alert, CallStatus, DisputeStatus, RequestStatus
    from apps.registry.services import reports

    now = now or timezone.now()
    inventory = [f"port:{port.code}"]
    calls = (visible_calls.exclude(status=CallStatus.DRAFT)
             .filter(status__in=ACTIVE_STATUSES) | visible_calls.filter(status=CallStatus.DEPARTED,
                                                                          atd__gte=now - timedelta(hours=24)))
    rows = []
    for call in calls.select_related("vessel", "berth").order_by("eta"):
        inventory.append(f"call:{call.pk}")
        pending = [{"type": r.type.code, "label": r.type.label_en, "decision_roles": r.type.decision_roles,
                    "submitted_at": _iso(r.submitted_at)}
                   for r in call.requests.filter(status__in=(RequestStatus.SUBMITTED, RequestStatus.UNDER_REVIEW))
                   .select_related("type") if _not_n4(r)]
        tasks = call.tasks.filter(status=TaskStatus.PENDING, due_at__isnull=False)
        late = [{"code": t.code, "title": t.title_en, "role": t.role, "blocking": t.is_blocking,
                 "due_at": _iso(t.due_at), "alert": t.alert_level}
                for t in tasks.filter(due_at__lt=now).order_by("due_at")[:8]]
        last = call.milestones.filter(is_conflict=False).select_related("type").order_by("-declared_at").first()
        rows.append({
            "reference": call.reference, "status": call.status, "vessel": call.vessel.name, "imo": call.vessel.imo,
            "operating_area": call.requested_berth_kind, "berth": call.berth.code if call.berth else None,
            "operations": list(call.template_codes), "product": call.product,
            "declared_quantity": str(call.quantity) if call.quantity is not None else None, "unit": call.quantity_unit,
            "eta": _iso(call.eta), "etb": _iso(call.etb), "etd": _iso(call.etd), "ata": _iso(call.ata),
            "atb": _iso(call.atb), "atd": _iso(call.atd),
            "last_milestone": {"type": last.type.code, "label": last.type.label_en, "declared_at": _iso(last.declared_at),
                               "emitter_role": last.emitter_role} if last else None,
            "pending_decisions": pending, "late_tasks": late, "late_tasks_count": tasks.filter(due_at__lt=now).count(),
            "escalated_tasks": tasks.filter(alert_level="ESCALATED").count(),
            "open_disputes": call.disputes.filter(status__in=(DisputeStatus.OPEN, DisputeStatus.ANSWERED)).count(),
        })
    digest = {
        "port": {"code": port.code, "name": port.name, "time_zone": port.timezone, "now": _iso(now)},
        "your_roles": sorted(actor.roles),
        "calls": rows,
    }
    board = ais_svc.board(port, visible_calls=visible_calls, now=now)
    digest["ais"] = {
        "configured": board["box"] is not None, "vessels_heard_24h": len(board["vessels"]),
        "in_port_waters": board["on_board"],
        "vessels": [{"name": v["name"], "mmsi": v["mmsi"], "call": v["call"].reference if v["call"] else None,
                     "in_port_waters": v.get("inside"), "speed_kn": float(v["speed_kn"]) if v["speed_kn"] is not None else None,
                     "status": str(v["nav_status_label"]) or None, "minutes_since_report": v["age_minutes"]}
                    for v in board["vessels"]],
        "discrepancies": [{"kind": d["kind"], "call": d["call"].reference, "text": str(d["text"])} for d in board["discrepancies"]],
    }
    inventory.append("ais:board")
    alerts = Alert.objects.filter(call__in=calls, emitted_at__gte=now - timedelta(hours=24)).select_related("call")
    digest["alerts_24h"] = [{"call": a.call.reference, "kind": a.kind, "blocking": a.blocking, "message": a.message_en,
                             "emitted_at": _iso(a.emitted_at)} for a in alerts.order_by("-emitted_at")[:40]]
    indicators = reports.indicators(port, days=90, visible_calls=visible_calls)
    digest["indicators_90_days"] = {k["code"]: {"label": k["label_en"], "value": k["value"]} for k in indicators["kpis"]}
    inventory.append("indicators:90d")
    return digest, inventory
