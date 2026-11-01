"""JSON representations, always filtered by what the actor may see (EF-12.2)."""
from __future__ import annotations

from apps.core.models import pick
from apps.registry.models import Task
from apps.registry.services import holdpoints, rights
from apps.registry.services.milestones import overall_state, state_by_role


def dt(value):
    return value.isoformat() if value else None


def call_summary(call) -> dict:
    return {
        "reference": call.reference, "status": call.status, "status_label": str(call.get_status_display()),
        "vessel": {"name": call.vessel.name, "imo": call.vessel.imo},
        "operating_area": call.requested_berth_kind, "berth": call.berth.code if call.berth else None,
        "eta": dt(call.eta), "etb": dt(call.etb), "etd": dt(call.etd), "ata": dt(call.ata), "atb": dt(call.atb),
        "atd": dt(call.atd), "templates": call.template_codes,
    }


def call_detail(call, actor) -> dict:
    data = call_summary(call)
    data.update({
        "port": {"code": call.port.code, "name": call.port.name, "timezone": call.port.timezone},
        "agency": str(call.agency), "voyage": call.voyage_number,
        "your_roles": sorted(actor.roles),
        "estimates": {k: dt(getattr(call, k)) for k in ("eta", "etb", "ets", "etc", "etd")},
        "actuals": {k: dt(getattr(call, k)) for k in ("ata", "nor_at", "atb", "t0", "t1", "atd")},
        "parties": [{"organization": str(p.organization), "role": p.role} for p in
                    call.parties.filter(revoked_at__isnull=True).select_related("organization")],
        "stages": [{"order": s.order, "berth_kind": s.berth_kind, "berth": s.berth.code if s.berth_id else None,
                    "operations": s.operations, "status": s.status, "atb": dt(s.atb), "atd": dt(s.atd)}
                   for s in call.stages.select_related("berth").order_by("order")],
    })
    if rights.can_see_full_call(actor):
        data.update({"product": call.product, "quantity": str(call.quantity) if call.quantity is not None else None,
                     "quantity_unit": call.quantity_unit})
        data["hold_points"] = {}
        for transition in ("GREEN_LIGHT", "BERTH_ASSIGN", "MOVEMENT_AUTH", "START_TRANSFER", "DEPARTURE_CLEARANCE", "CLOSE"):
            _tasks, missing, reasons = holdpoints.evaluate(call, transition)
            data["hold_points"][transition] = {"ready": not missing and not reasons, "missing": [m["task"] for m in missing]}
    return data


def task_dict(task: Task) -> dict:
    return {
        "id": task.pk, "code": task.code, "title": task.title, "title_fr": task.title_fr, "title_en": task.title_en,
        "section": task.section, "role": task.role, "co_roles": task.co_roles, "joint": task.joint, "nature": task.nature,
        "blocking": task.is_blocking, "due_at": dt(task.due_at), "timing": task.timing, "status": task.status,
        "alert_level": task.alert_level, "request_type": task.request_type_code, "milestones": task.milestone_codes,
        "document_type": task.document_type_code, "continuous": task.continuous, "ad_hoc": task.is_ad_hoc,
        "completed_at": dt(task.completed_at), "completed_role": task.completed_role, "na_reason": task.na_reason,
        "signed_roles": sorted({s.role for s in task.signatures.all() if s.kind == "SIGNED"}),
    }


def milestone_dict(m) -> dict:
    return {
        "id": m.pk, "type": m.type.code, "label": m.type.label, "declared_at": dt(m.declared_at),
        "recorded_at": dt(m.recorded_at), "device_recorded_at": dt(m.device_recorded_at), "deferred": m.deferred,
        "source": m.source, "emitter_role": m.emitter_role, "emitter": m.emitter_label,
        "cause": {"code": m.cause.code, "label": m.cause.label} if m.cause else None, "cause_reason": m.cause_reason,
        "related_id": m.related_id, "rectification": m.is_rectification, "conflict": m.is_conflict,
        "countersigner_roles": m.countersigner_roles, "countersignatures": state_by_role(m),
        "countersignature_state": overall_state(m), "client_uuid": str(m.client_uuid) if m.client_uuid else None,
    }


def request_dict(req, actor) -> dict:
    data = {
        "id": req.pk, "reference": req.reference, "type": req.type.code, "label": req.type.label, "status": req.status,
        "status_label": str(req.get_status_display()), "confidentiality": req.confidentiality,
        "requester_role": req.requester_role, "data": req.data, "submitted_at": dt(req.submitted_at),
        "due_at": dt(req.due_at), "decision": req.decision, "decision_role": req.decision_role,
        "decided_at": dt(req.decided_at), "conditions": req.decision_conditions,
        "decision_roles": req.type.decision_roles, "executor_role": req.type.executor_role,
        "provider": {"id": req.provider_org_id, "name": req.provider_org.name} if req.provider_org_id else None,
    }
    if req.decision_reason and rights.can_see_refusal_reason(actor, req):
        data["reason"] = req.decision_reason
    try:
        auth = req.authorization
    except Exception:
        auth = None
    if auth is not None:
        data["authorization"] = {"number": auth.number, "valid_from": dt(auth.valid_from), "valid_until": dt(auth.valid_until),
                                 "verification_code": auth.verification_code, "berth": auth.berth.code if auth.berth else None,
                                 "cancelled": auth.is_cancelled}
    return data


def document_dict(doc) -> dict:
    return {
        "id": doc.pk, "type": doc.type.code, "type_label": doc.type.label, "title": doc.display_title, "version": doc.version,
        "status": doc.status, "confidentiality": doc.confidentiality, "issuer_role": doc.issuer_role,
        "issuer": doc.issuer_label, "issued_at": dt(doc.issued_at), "sha256": doc.sha256, "size": doc.size,
        "mime_type": doc.mime_type, "required_signers": doc.required_signers,
        "signatures": [{"role": s.role, "signer": s.signer_label, "at": dt(s.signed_at)} for s in doc.signatures.all()],
        "deferred": doc.deferred, "download": f"/api/v1/calls/{doc.call.reference}/documents/{doc.pk}/download/",
    }


def measurement_dict(m) -> dict:
    current = m.current_values()
    discrepancy = m.discrepancy()
    return {
        "id": m.pk, "kind": m.kind, "unit": m.unit, "product": m.product, "tolerance_pct": str(m.tolerance_pct),
        "values": {party: {"value": str(v.value), "by": v.entered_label, "at": dt(v.entered_at), "deferred": v.deferred}
                   for party, v in current.items()},
        "complete": m.is_complete,
        "discrepancy": {"difference": str(discrepancy["difference"]),
                        "percent": f"{discrepancy['percent']:.3f}" if discrepancy["percent"] is not None else None}
        if discrepancy else None,
        "differences": [{"a": d["a"], "b": d["b"], "difference": str(d["difference"]),
                         "percent": f"{d['percent']:.3f}" if d["percent"] is not None else None, "exceeds": d["exceeds"]}
                        for d in m.differences()],
        "exceeds_tolerance": m.exceeds_tolerance(),
    }


def dispute_dict(d, actor) -> dict:
    data = {"id": d.pk, "reference": d.reference, "subject": d.subject, "target": d.target_kind, "target_id": d.target_id,
            "status": d.status, "opened_role": d.opened_role, "opened_by": d.opened_label,
            "counterpart_role": d.counterpart_role, "opened_at": dt(d.opened_at), "closed_at": dt(d.closed_at),
            "automatic": d.auto_created}
    if rights.dispute_content_visible(actor, d):
        data["entries"] = [{"kind": e.kind, "role": e.role, "by": e.author_label, "text": e.text, "at": dt(e.at)}
                           for e in d.entries.all()]
    return data


def journal_dict(e) -> dict:
    return {"seq": e.seq, "at": dt(e.at), "action": e.action, "role": e.actor_role, "actor": e.actor_label,
            "summary": e.summary, "hash": e.hash, "prev_hash": e.prev_hash}


def label(fr: str, en: str) -> str:
    return pick(fr, en)
