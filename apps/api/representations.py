"""JSON representations, always filtered by what the actor may see (EF-12.2)."""
from __future__ import annotations

from apps.core.models import pick
from apps.registry.models import Task
from apps.registry.services import calls as call_svc
from apps.registry.services import holdpoints, intake, rights
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
        "cargo_kind": call.cargo_kind, "sts_role": call.sts_role or None,
        "validity": {"days": call.validity_days, "valid_until": dt(call.valid_until), "expired_at": dt(call.expired_at),
                     "overrun": call.validity_overrun, "renewed_from": call.renewed_from.reference if call.renewed_from_id else None},
    }


def call_detail(call, actor) -> dict:
    data = call_summary(call)
    data.update({
        "port": {"code": call.port.code, "name": call.port.name, "timezone": call.port.timezone},
        "agency": str(call.agency), "voyage": call.voyage_number,
        "your_roles": sorted(actor.roles),
        "estimates": {k: dt(getattr(call, k)) for k in ("eta", "etb", "ets", "etc", "etd")},
        "actuals": {k: dt(getattr(call, k)) for k in ("ata", "nor_at", "atb", "t0", "t1", "atd")},
        "parties": [{"id": p.pk, "organization": str(p.organization), "role": p.role, "principal": p.is_principal,
                     "access": p.access, "scopes": p.scopes} for p in
                    call.parties.filter(revoked_at__isnull=True).select_related("organization")],
        "your_access": {"level": rights.access_of(actor, call)[0], "tabs": sorted(rights.access_of(actor, call)[1] or []) or None,
                        "principal_agent": rights.is_principal_agent(actor, call)},
        "billing_basis": {k: (dt(v) if hasattr(v, "isoformat") else v) for k, v in call.billing_basis().items()},
        "linked_call": ({"reference": call.linked_call.reference, "vessel": call.linked_call.vessel.name, "kind": call.link_kind,
                         "reciprocal": call.linked_call.linked_call_id == call.pk,
                         "confirmed": call_svc.link_confirmed(call)} if call.linked_call_id else None),
        # the other calls naming this one — the daughter vessels of a mother vessel, a vessel alongside (v1.6)
        "named_by": [{"reference": o.reference, "vessel": o.vessel.name, "agency": o.agency.name, "kind": o.link_kind or "STS",
                      "sts_role": o.sts_role or None, "status": o.status} for o in call_svc.incoming_links(call, actor)],
        "stages": [{"order": s.order, "berth_kind": s.berth_kind, "berth": s.berth.code if s.berth_id else None,
                    "operations": s.operations, "status": s.status, "atb": dt(s.atb), "atd": dt(s.atd)}
                   for s in call.stages.select_related("berth").order_by("order")],
    })
    if rights.can_see_full_call(actor):
        data.update({"product": call.product, "quantity": str(call.quantity) if call.quantity is not None else None,
                     "quantity_unit": call.quantity_unit})
        # what the agency declared for each operation at the announcement, raw and labelled (v1.6, EXG-R-11): like the
        # product and the quantity, not for a provider — it reads what concerns it in the request addressed to it
        data["operation_details"] = call.operation_details or {}
        data["declared"] = [{"template": d["code"], "name": d["name"], "items": [{"label": k, "value": v} for k, v in d["rows"]]}
                            for d in intake.declared(call)]
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
        "green_light": task.green_light, "requested_at_creation": task.requested_at_creation,
        "completed_at": dt(task.completed_at), "completed_role": task.completed_role, "na_reason": task.na_reason,
        "signed_roles": sorted({s.role for s in task.signatures.all() if s.kind == "SIGNED"}),
    }


def green_light_dict(row: dict) -> dict:
    task = row["task"]
    return {"task_id": task.pk, "code": task.code, "title": task.title, "role": task.role, "state": row["state"],
            "given_by": row["by"] or None, "given_at": dt(row["at"]), "withdrawable": row["withdrawable"],
            "request": row["request"].reference if row["request"] is not None else None, "note": task.completion_note or None}


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


def num(value):
    return str(value) if value is not None else None


def measurement_dict(m, actor=None) -> dict:
    current = m.current_values()
    discrepancy = m.discrepancy()
    data = {
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
    if actor is not None:
        from apps.registry.services.measurements import tank_totals

        totals = tank_totals(m, actor)
        data["tanks"] = {side: {"validated_total": str(row["validated"]), "validated_count": row["count"],
                                "pending": row["pending"], "rejected": row["rejected"],
                                "readings": [tank_reading_dict(r) for r in row["readings"]]}
                         for side, row in totals.items()}
    return data


def tank_reading_dict(r) -> dict:
    review = r.latest_review()
    return {"id": r.pk, "side": r.side, "tank": r.tank, "state": r.state, "quantity": num(r.quantity),
            "level_mm": num(r.level_mm), "temperature_c": num(r.temperature_c), "free_water_mm": num(r.free_water_mm),
            "density": num(r.density), "tov_m3": num(r.tov_m3), "gov_m3": num(r.gov_m3), "vcf": num(r.vcf),
            "gsv_m3": num(r.gsv_m3), "weight_mt": num(r.weight_mt), "by": r.entered_label, "declared_at": dt(r.declared_at),
            "supersedes": r.supersedes_id, "note": r.note, "seal": r.seal,
            "review": {"state": review.state, "by": review.reviewer_label, "at": dt(review.reviewed_at), "note": review.note}
            if review else None}


def pumping_sheet_dict(s) -> dict:
    return {"id": s.pk, "side": s.side, "tank": s.tank, "product": s.product, "start_level_mm": num(s.start_level_mm),
            "expected_stop_level_mm": num(s.expected_stop_level_mm), "m3_per_metre": num(s.m3_per_metre),
            "density": num(s.density), "vcf": num(s.vcf), "tons_per_metre": num(s.tons_per_metre),
            "planned_quantity_m3": num(s.planned_quantity_m3), "planned_quantity_mt": num(s.planned_quantity_mt),
            "expected_rate_m3h": num(s.expected_rate_m3h), "expected_pressure_bar": num(s.expected_pressure_bar),
            "estimated_start": dt(s.estimated_start), "estimated_completion": dt(s.estimated_completion),
            "actual_stop_level_mm": num(s.actual_stop_level_mm), "final_volume_m3": num(s.final_volume_m3),
            "closed_at": dt(s.closed_at), "opened_by": s.opened_label, "opened_at": dt(s.opened_at), "note": s.note}


def pumping_entry_dict(p) -> dict:
    return {"id": p.pk, "declared_at": dt(p.declared_at), "side": p.side, "sheet": p.sheet_id, "tank": p.tank, "role": p.role,
            "by": p.entered_label, "pressure_bar": num(p.manifold_pressure_bar), "rate_m3h": num(p.flow_rate_m3h),
            "temperature_c": num(p.temperature_c), "level_mm": num(p.level_mm), "hourly_m3": num(p.hourly_m3),
            "cumulative_m3": num(p.cumulative_m3), "cumulative_mt": num(p.cumulative_mt), "note": p.note,
            "source": p.source, "deferred": p.deferred}


def checklist_dict(c, parts=None) -> dict:
    data = {"id": c.pk, "version": c.version, "status": c.status, "opened_by": c.opened_label, "opened_at": dt(c.opened_at),
            "signed_at": dt(c.signed_at), "repeat_interval_h": num(c.repeat_interval_h), "signed_sides": sorted(c.signed_sides()),
            "document": c.document_id}
    if parts is not None:
        data["parts"] = [{"code": part["code"], "title_fr": part["fr"], "title_en": part["en"],
                          "items": [{"code": row["item"]["code"], "fr": row["item"]["fr"], "en": row["item"]["en"],
                                     "kind": row["item"]["kind"], "sides": row["sides"], "repetitive": row["item"].get("repetitive", False),
                                     "ship": answer_dict(row["ship"]), "shore": answer_dict(row["shore"]), "value": row["value"],
                                     "repetitions": [answer_dict(a) for a in row["repetitions"]]}
                                    for row in part["items"]]} for part in parts]
    return data


def answer_dict(a) -> dict | None:
    if a is None:
        return None
    return {"state": a.state, "value": a.value, "remark": a.remark, "repetition": a.repetition, "by": a.author_label,
            "at": dt(a.answered_at), "seal": a.seal}


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
