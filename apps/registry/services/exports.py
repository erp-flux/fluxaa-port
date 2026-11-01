"""Exports (EF-10.4, EF-15): open, documented format (docs/FORMAT_EXPORT.md), filtered by rights,
with signature and timestamp metadata. N4 objects never appear (they are not in this database), and
vetting refusal reasons are absent from every export (EF-2 acceptance criterion)."""
from __future__ import annotations

import io
import json
import zipfile

from django.utils import timezone

from apps.core.crypto import canonical_json, seal, sha256_hex

from ..models import JournalEntry, PortCall
from . import journal
from .errors import PermissionRefused
from .milestones import overall_state, state_by_role
from .rights import (
    alert_visible,
    can_export,
    dispute_content_visible,
    dispute_header_visible,
    document_visible,
    measurements_visible,
    request_visible,
    task_visible,
    visible_milestones,
)

FORMAT_VERSION = "fluxaa-port-export/1.0"


def _dt(value):
    return value.isoformat() if value else None


def call_payload(call: PortCall, actor) -> tuple[dict, list]:
    """Structured content of a call as visible by *actor*; returns (data, files[(arcname, document)])."""
    files = []
    data = {
        "reference": call.reference,
        "port": {"code": call.port.code, "name": call.port.name, "timezone": call.port.timezone},
        "status": call.status,
        "vessel": {"imo": call.vessel.imo, "name": call.vessel.name, "flag": call.vessel.flag,
                   "type": call.vessel.vessel_type, "dwt": call.vessel.dwt},
        "voyage": call.voyage_number,
        "agency": str(call.agency),
        "operating_area": call.requested_berth_kind,
        "berth": call.berth.code if call.berth else None,
        "product": call.product,
        "quantity": str(call.quantity) if call.quantity is not None else None,
        "quantity_unit": call.quantity_unit,
        "templates": [{"code": u.template_version.template.code, "version": u.template_version.number}
                      for u in call.template_uses.select_related("template_version__template")],
        "estimates": {k: _dt(getattr(call, k)) for k in ("eta", "etb", "ets", "etc", "etd")},
        "actuals": {k: _dt(getattr(call, k)) for k in ("ata", "nor_at", "atb", "t0", "t1", "atd")},
        "parties": [{"organization": str(p.organization), "role": p.role, "valid_from": _dt(p.valid_from),
                     "valid_until": _dt(p.valid_until), "revoked_at": _dt(p.revoked_at)}
                    for p in call.parties.select_related("organization")],
        "milestones": [
            {"id": m.pk, "type": m.type.code, "declared_at": _dt(m.declared_at), "recorded_at": _dt(m.recorded_at),
             "device_recorded_at": _dt(m.device_recorded_at), "deferred": m.deferred, "source": m.source,
             "emitter_role": m.emitter_role, "emitter": m.emitter_label,
             "cause": m.cause.code if m.cause else None, "cause_reason": m.cause_reason, "related": m.related_id,
             "rectification": m.is_rectification, "conflict": m.is_conflict, "seal": m.seal,
             "countersignatures": state_by_role(m), "countersignature_state": overall_state(m)}
            for m in visible_milestones(actor, call)
        ],
        "tasks": [
            {"code": t.code, "title_fr": t.title_fr, "title_en": t.title_en, "role": t.role, "nature": t.nature,
             "criticality": t.criticality, "due_at": _dt(t.due_at), "status": t.status,
             "completed_at": _dt(t.completed_at), "completed_role": t.completed_role, "na_reason": t.na_reason}
            for t in call.tasks.all() if task_visible(actor, t)
        ],
        "requests": [],
        "documents": [],
        "measurements": [],
        "pumping_log": [],
        "disputes": [],
        "alerts": [{"kind": a.kind, "emitted_at": _dt(a.emitted_at), "message_fr": a.message_fr,
                    "message_en": a.message_en, "blocking": a.blocking} for a in call.alerts.all()
                   if alert_visible(actor, a)],
    }
    for req in call.requests.select_related("type"):
        if not request_visible(actor, req):
            continue
        item = {"reference": req.reference, "type": req.type.code, "status": req.status, "requester_role": req.requester_role,
                "data": req.data, "submitted_at": _dt(req.submitted_at), "decision": req.decision,
                "decision_role": req.decision_role, "decided_at": _dt(req.decided_at), "conditions": req.decision_conditions}
        if req.decision_reason and not req.type.is_vetting:
            item["reason"] = req.decision_reason  # vetting refusal reasons are never exported
        auth = getattr(req, "authorization", None)
        if auth is not None:
            item["authorization"] = {"number": auth.number, "valid_from": _dt(auth.valid_from),
                                     "valid_until": _dt(auth.valid_until), "seal": auth.seal,
                                     "verification_code": auth.verification_code, "cancelled": auth.is_cancelled}
        data["requests"].append(item)
    for doc in call.documents.select_related("type"):
        if not document_visible(actor, doc):
            continue
        arcname = f"documents/{doc.pk}_{doc.original_name}"
        data["documents"].append({
            "id": doc.pk, "type": doc.type.code, "title": doc.title, "version": doc.version, "status": doc.status,
            "confidentiality": doc.confidentiality, "issuer_role": doc.issuer_role, "issuer": doc.issuer_label,
            "issued_at": _dt(doc.issued_at), "sha256": doc.sha256, "file": arcname,
            "signatures": [{"role": s.role, "signer": s.signer_label, "at": _dt(s.signed_at), "seal": s.seal,
                            "document_sha256": s.document_sha256} for s in doc.signatures.all()],
        })
        files.append((arcname, doc))
    if measurements_visible(actor):
        for m in call.measurements.all():
            data["measurements"].append({
                "kind": m.kind, "unit": m.unit, "tolerance_pct": str(m.tolerance_pct),
                "values": [{"party": v.party, "value": str(v.value), "role": v.entered_role, "by": v.entered_label,
                            "declared_at": _dt(v.declared_at), "entered_at": _dt(v.entered_at), "deferred": v.deferred,
                            "supersedes": v.supersedes_id, "seal": v.seal} for v in m.values.all()],
                "complete": m.is_complete,
                "differences": [{"between": f"{d['a']}-{d['b']}", "difference": str(d["difference"]),
                                 "percent": f"{d['percent']:.3f}" if d["percent"] is not None else None,
                                 "outside_tolerance": d["exceeds"] if (d["a"], d["b"]) == ("SHIP", "SHORE") else None}
                                for d in m.differences()],
            })
        data["pumping_log"] = [{"declared_at": _dt(p.declared_at), "recorded_at": _dt(p.recorded_at), "role": p.role,
                                "pressure_bar": str(p.manifold_pressure_bar) if p.manifold_pressure_bar is not None else None,
                                "rate_m3h": str(p.flow_rate_m3h) if p.flow_rate_m3h is not None else None,
                                "temperature_c": str(p.temperature_c) if p.temperature_c is not None else None,
                                "source": p.source, "deferred": p.deferred} for p in call.pumping_log.all()]
    for d in call.disputes.all():
        if not dispute_header_visible(actor, d):
            continue
        item = {"reference": d.reference, "subject": d.subject, "target": d.target_kind, "status": d.status,
                "opened_role": d.opened_role, "counterpart_role": d.counterpart_role, "opened_at": _dt(d.opened_at),
                "closed_at": _dt(d.closed_at), "automatic": d.auto_created}
        if dispute_content_visible(actor, d):
            item["entries"] = [{"kind": e.kind, "role": e.role, "by": e.author_label, "text": e.text, "at": _dt(e.at),
                                "seal": e.seal} for e in d.entries.all()]
        data["disputes"].append(item)
    data["journal"] = [
        {"seq": e.seq, "at": _dt(e.at), "action": e.action, "role": e.actor_role, "actor": e.actor_label,
         "summary_fr": e.summary_fr, "summary_en": e.summary_en, "hash": e.hash, "prev_hash": e.prev_hash,
         "timestamp_provider": e.timestamp_provider}
        for e in JournalEntry.objects.filter(call=call).order_by("seq") if journal.entry_visible(e, actor)
    ]
    return data, files


def export_call(call: PortCall, actor, request=None) -> bytes:
    if not can_export(actor):
        raise PermissionRefused("Export is reserved to owners/charterers and port management (FLX-SPEC-001 §5).")
    data, files = call_payload(call, actor)
    buffer = io.BytesIO()
    manifest = {"format": FORMAT_VERSION, "generated_at": timezone.now().isoformat(), "exported_by": actor.label,
                "exported_roles": sorted(actor.roles), "call": call.reference, "files": {}}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
        archive.writestr("call.json", body)
        manifest["files"]["call.json"] = sha256_hex(body)
        for arcname, doc in files:
            try:
                with doc.file.open("rb") as handle:
                    content = handle.read()
            except FileNotFoundError:
                continue
            archive.writestr(arcname, content)
            manifest["files"][arcname] = sha256_hex(content)
        manifest["seal"] = seal(manifest["files"])
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="export", obj=call,
                  detail=f"{len(files)} files", request=request)
    return buffer.getvalue()


def export_port(port, user, request=None) -> bytes:
    """Reversibility export for the port authority (EF-15): every call, journal and audit chain.

    *user* is the port's functional administrator (or the platform operator); ``None`` stands for the
    server's command line (manage.py export_port), which is traced as such.
    """
    from .context import system_actor

    if user is not None and not (user.is_port_admin and user.port and user.port.pk == port.pk) and not user.is_superuser:
        raise PermissionRefused("Reserved to the port's functional administrator.")
    actor = system_actor(port)
    buffer = io.BytesIO()
    manifest = {"format": FORMAT_VERSION, "scope": "port", "port": port.code, "generated_at": timezone.now().isoformat(),
                "files": {}}
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for call in PortCall.objects.filter(port=port).order_by("reference"):
            data, files = call_payload(call, actor)
            for req in data["requests"]:
                req.pop("reason", None) if req.get("type") == "VESSEL_ACCEPTANCE" else None
            body = json.dumps(data, ensure_ascii=False, indent=2, default=str)
            name = f"calls/{call.reference}/call.json"
            archive.writestr(name, body)
            manifest["files"][name] = sha256_hex(body)
            for arcname, doc in files:
                try:
                    with doc.file.open("rb") as handle:
                        content = handle.read()
                except FileNotFoundError:
                    continue
                full = f"calls/{call.reference}/{arcname}"
                archive.writestr(full, content)
                manifest["files"][full] = sha256_hex(content)
        from ..models import AuditEntry

        # Both chains are exported with the exact material that was hashed, so that anyone can recompute
        # them without the platform (scripts/verifier_export.py; docs/FORMAT_EXPORT.md §5).
        audit_rows = [{"material": journal.audit_material(a), "hash": a.hash}
                      for a in AuditEntry.objects.filter(port=port).order_by("seq")]
        body = canonical_json(audit_rows)
        archive.writestr("audit.json", body)
        manifest["files"]["audit.json"] = sha256_hex(body)
        journal_rows = [{"material": journal.journal_material(e), "call_reference": e.call.reference if e.call_id else None,
                         "hash": e.hash, "timestamp_provider": e.timestamp_provider, "timestamp_token": e.timestamp_token}
                        for e in JournalEntry.objects.filter(port=port).select_related("call").order_by("seq")]
        body = canonical_json(journal_rows)
        archive.writestr("journal.json", body)
        manifest["files"]["journal.json"] = sha256_hex(body)
        # traces of the AI assistance (EF-17): what was asked, on which data, what a person validated
        from apps.ai.models import AssistantRun, ExtractionReview

        assistant_rows = {
            "runs": [{"id": r.pk, "call": r.call.reference, "feature": r.feature, "at": _dt(r.created_at),
                      "role": r.requested_role, "user": r.requested_by.email if r.requested_by_id else None,
                      "model": r.model, "input_digest": r.input_digest, "input_inventory": r.input_inventory,
                      "status": r.status, "error": r.error, "output": r.output}
                     for r in AssistantRun.objects.filter(port=port).select_related("call", "requested_by").order_by("pk")],
            "extractions": [{"run": x.run_id, "call": x.call.reference, "document": x.document_id, "kind": x.kind,
                             "proposed": x.proposed, "status": x.status, "validated": x.validated,
                             "validated_by": x.validated_label, "validated_at": _dt(x.validated_at)}
                            for x in ExtractionReview.objects.filter(call__port=port).select_related("call").order_by("pk")],
        }
        body = json.dumps(assistant_rows, ensure_ascii=False, indent=2, default=str)
        archive.writestr("assistant.json", body)
        manifest["files"]["assistant.json"] = sha256_hex(body)
        manifest["seal"] = seal(manifest["files"])
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    journal.audit(port=port, user=user, action="export.port", detail="reversibility export", request=request,
                  label="" if user is not None else "FLUXAA — command line export")
    return buffer.getvalue()
