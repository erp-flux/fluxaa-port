"""Public API v1 (CDC architecture orientation 5). Every rule is enforced by the services layer."""
from __future__ import annotations

from datetime import datetime

from django.http import FileResponse, HttpResponse
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.ais import services as ais_svc
from apps.core.models import Berth, Organization
from apps.registry.models import (
    ACTIVE_STATUSES,
    Document,
    Measurement,
    Milestone,
    MilestoneType,
    PortCall,
    ServiceRequest,
    Task,
    Thread,
    Vessel,
)
from apps.registry.services import calls as call_svc
from apps.registry.services import correspondence, disputes, exports, journal, reports, rights
from apps.registry.services import documents as doc_svc
from apps.registry.services import forms as form_svc
from apps.registry.services import measurements as meas_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import requests as req_svc
from apps.registry.services import stages as stage_svc
from apps.registry.services import tasks as task_svc
from apps.registry.services.access import call_and_actor
from apps.registry.services.context import port_actor
from apps.registry.services.errors import NotVisible, PermissionRefused, RuleViolation
from apps.registry.services.sync import process_batch

from . import representations as rep

JSON = OpenApiTypes.OBJECT


def when(value, field="datetime") -> datetime | None:
    if value in (None, ""):
        return None
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None:
        raise RuleViolation(f"Invalid date/time for '{field}' (ISO 8601 expected).")
    return parsed


class CallAPIView(APIView):
    permission_classes = [IsAuthenticated]
    # reading a call's records through the API is written to the access journal, as on screen (ENF-3.4)
    audit_kind = ""

    def resolve(self, request, reference):
        call, actor = call_and_actor(request, reference)
        if request.method == "GET" and self.audit_kind:
            journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                          object_kind=self.audit_kind, detail="api", request=request._request)
        return call, actor


# ============================================================================ identity & calls
class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JSON, summary="Current identity, organisation and roles")
    def get(self, request):
        user = request.user
        if getattr(user, "master", None) is not None:
            link = user.master
            return Response({"kind": "master" if link.is_master else "link", "name": link.master_name,
                             "organization": str(link.organization) if link.organization_id else None,
                             "call": link.call.reference, "link": link.pk, "roles": [link.role],
                             "expires_at": rep.dt(link.expires_at)})
        return Response({"kind": "user", "name": user.full_name, "email": user.email,
                         "organization": str(user.organization) if user.organization_id else None,
                         "port": user.port.code if user.port else None, "roles": sorted(user.role_set),
                         "mfa_enabled": user.mfa_enabled})


class CallListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="calls_list", responses=JSON, summary="Calls on which your organisation holds a role")
    def get(self, request):
        user = request.user
        if getattr(user, "master", None) is not None:
            return Response({"results": [rep.call_summary(user.master.call)]})
        qs = rights.call_queryset_for_user(user).select_related("vessel", "berth")
        if request.query_params.get("active") in ("1", "true"):
            qs = qs.filter(status__in=ACTIVE_STATUSES)
        if status := request.query_params.get("status"):
            qs = qs.filter(status=status)
        role_set = user.role_set
        results = [rep.call_summary(c) for c in qs.order_by("-eta")[:200] if c.status != "DRAFT" or "AGE" in role_set]
        return Response({"results": results})

    @extend_schema(request=JSON, responses=JSON, summary="Create a call (shipping agency only)")
    def post(self, request):
        data = request.data
        actor = port_actor(request.user)
        vessel = Vessel.objects.filter(port=actor.port, imo=str(data.get("vessel_imo", ""))).first()
        if vessel is None:
            raise RuleViolation("Unknown vessel: register it first (POST /api/v1/vessels/).")
        parties = []
        for item in data.get("parties", []):  # an open list: a registered organisation, or a new one by name
            if item.get("organization_id"):
                org = Organization.objects.filter(port=actor.port, pk=item.get("organization_id")).first()
                if org is None:
                    raise RuleViolation("Unknown organisation in parties.")
            else:
                org = call_svc.register_organization(actor, name=str(item.get("name", "")), role=str(item.get("role", "")),
                                                     kind=str(item.get("kind", "")), email=str(item.get("email", "")),
                                                     phone=str(item.get("phone", "")))
            parties.append((org, item.get("role")))
        berth = Berth.objects.filter(port=actor.port, code=data.get("requested_berth")).first() if data.get("requested_berth") else None
        linked = PortCall.objects.filter(port=actor.port, reference=data.get("linked_call")).first() if data.get("linked_call") else None
        call = call_svc.create_call(
            request.user, vessel=vessel, eta=when(data.get("eta"), "eta"), requested_berth_kind=data.get("operating_area"),
            operations=data.get("operations", []), modules=data.get("modules", []), requested_berth=berth,
            etb=when(data.get("etb")), ets=when(data.get("ets")), etc=when(data.get("etc")), etd=when(data.get("etd")),
            product=data.get("product", ""), quantity=data.get("quantity") or None,
            quantity_unit=data.get("quantity_unit", "MT"), voyage_number=data.get("voyage", ""),
            last_port=data.get("last_port", ""), next_port=data.get("next_port", ""), parties=parties,
            linked_call=linked, link_kind=data.get("link_kind", ""),
        )
        return Response(rep.call_detail(call, call_and_actor(request, call.reference)[1]), status=201)


class VesselView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=JSON, responses=JSON, summary="Register a vessel (agency)")
    def post(self, request):
        actor = port_actor(request.user)
        if "AGE" not in actor.roles:
            raise PermissionRefused("Vessel records are created by the agency.")
        data = request.data
        vessel = Vessel(port=actor.port, imo=str(data.get("imo", "")), name=data.get("name", ""),
                        flag=data.get("flag", ""), vessel_type=data.get("type", ""), dwt=data.get("dwt") or None)
        from django.core.exceptions import ValidationError

        try:
            vessel.full_clean()
        except ValidationError as exc:
            raise RuleViolation("; ".join(f"{k}: {', '.join(v)}" for k, v in exc.message_dict.items()))
        vessel.save()
        return Response({"id": vessel.pk, "imo": vessel.imo, "name": vessel.name}, status=201)


class CallDetailView(CallAPIView):
    @extend_schema(operation_id="calls_retrieve", responses=JSON, summary="Call detail as visible by you")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                      object_kind="call", request=request._request)
        return Response(rep.call_detail(call, actor))


class CallActionView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Life-cycle action: declare | estimates | cancel | close-request | close | archive | statement-of-facts | invite")
    def post(self, request, reference, action):
        call, actor = self.resolve(request, reference)
        data = request.data
        if action == "declare":
            call_svc.declare_call(call, actor)
        elif action == "estimates":
            call_svc.update_estimates(call, actor, reason=data.get("reason", ""),
                                      **{k: when(data.get(k), k) for k in call_svc.ESTIMATE_FIELDS if data.get(k)})
        elif action == "cancel":
            call_svc.cancel_call(call, actor, data.get("reason", ""))
        elif action == "close-request":
            call_svc.confirm_closure(call, actor)
        elif action == "close":
            call_svc.close_call(call, actor)
        elif action == "archive":
            call_svc.archive_call(call, actor)
        elif action == "statement-of-facts":
            doc = reports.issue_statement_of_facts(call, actor)
            return Response(rep.document_dict(doc), status=201)
        elif action == "invite":  # the open list of the parties: a registered organisation, or a new one by name
            if data.get("organization_id"):
                org = Organization.objects.filter(port=call.port, pk=data.get("organization_id")).first()
                if org is None:
                    raise RuleViolation("Unknown organisation.")
            else:
                org = call_svc.register_organization(actor, name=str(data.get("name", "")), role=str(data.get("role", "")),
                                                     kind=str(data.get("kind", "")), email=str(data.get("email", "")),
                                                     phone=str(data.get("phone", "")))
            call_svc.add_party(call, actor, org, str(data.get("role", "")))
        else:
            raise NotVisible()
        call.refresh_from_db()
        return Response(rep.call_detail(call, actor))


# ============================================================================ tasks
class TaskListView(CallAPIView):
    audit_kind = "tasks"

    @extend_schema(responses=JSON, summary="Tasks visible to your roles (EF-5.7)")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        tasks = rights.visible_tasks(actor, call).prefetch_related("signatures")
        return Response({"results": [rep.task_dict(t) for t in tasks]})


class TaskActionView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="complete | sign | countersign | not-applicable")
    def post(self, request, reference, task_id, action):
        call, actor = self.resolve(request, reference)
        task = Task.objects.filter(call=call, pk=task_id).first()
        if task is None or not rights.task_visible(actor, task):
            raise NotVisible()
        data = request.data
        if action == "complete":
            task_svc.complete_task(task, actor, note=data.get("note", ""), role=data.get("role"))
        elif action == "sign":
            task_svc.sign_task(task, actor, role=data.get("role"), comment=data.get("note", ""))
        elif action == "countersign":
            task_svc.countersign_task(task, actor, contest=bool(data.get("contest")), comment=data.get("comment", ""),
                                      role=data.get("role"))
        elif action == "not-applicable":
            task_svc.mark_not_applicable(task, actor, data.get("reason", ""), role=data.get("role"))
        else:
            raise NotVisible()
        task.refresh_from_db()
        return Response(rep.task_dict(task))


# ============================================================================ milestones
class MilestoneListView(CallAPIView):
    audit_kind = "milestones"

    @extend_schema(responses=JSON, summary="Milestones (contradictory timeline)")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        items = rights.visible_milestones(actor, call).prefetch_related("signatures")
        return Response({"results": [rep.milestone_dict(m) for m in items]})

    @extend_schema(request=JSON, responses=JSON, summary="Record a milestone (single emitter; hold points apply)")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        data = request.data
        related = None
        if data.get("related_id"):
            related = Milestone.objects.filter(call=call, pk=data["related_id"]).first()
        rectifies = Milestone.objects.filter(call=call, pk=data["rectifies_id"]).first() if data.get("rectifies_id") else None
        m = ms_svc.record_milestone(
            call, actor, data.get("type", ""), when(data.get("declared_at"), "declared_at"),
            cause_code=data.get("cause", ""), cause_reason=data.get("cause_reason", ""), note=data.get("note", ""),
            related=related, as_role=data.get("role"), rectifies=rectifies,
            rectification_reason=data.get("rectification_reason", ""), client_uuid=data.get("client_uuid") or None,
            source="PAPER" if data.get("paper") else "ONLINE",
        )
        return Response(rep.milestone_dict(m), status=201)


class MilestoneCountersignView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Countersign or contest a milestone")
    def post(self, request, reference, milestone_id):
        call, actor = self.resolve(request, reference)
        m = Milestone.objects.filter(call=call, pk=milestone_id).first()
        if m is None or not rights.milestone_visible(actor, m):
            raise NotVisible()
        ms_svc.countersign_milestone(m, actor, contest=bool(request.data.get("contest")),
                                     comment=request.data.get("comment", ""), as_role=request.data.get("role"))
        return Response(rep.milestone_dict(m))


# ============================================================================ requests
class RequestListView(CallAPIView):
    audit_kind = "requests"

    @extend_schema(responses=JSON, summary="Requests and authorizations visible to you")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        return Response({"results": [rep.request_dict(r, actor) for r in rights.visible_requests(actor, call)]})

    @extend_schema(operation_id="requests_create", request=JSON, responses=JSON, summary="Create (and submit) a request")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        req = req_svc.create_request(call, actor, request.data.get("type", ""), request.data.get("data", {}),
                                     submit=request.data.get("submit", True) is not False, as_role=request.data.get("role"),
                                     provider=request.data.get("provider"))
        return Response(rep.request_dict(req, actor), status=201)


class RequestActionView(CallAPIView):
    @extend_schema(operation_id="requests_action", request=JSON, responses=JSON,
                   summary="submit | review | decide (2FA: X-MFA-Code) | schedule | execute | cancel")
    def post(self, request, reference, request_id, action):
        call, actor = self.resolve(request, reference)
        req = ServiceRequest.objects.filter(call=call, pk=request_id).select_related("type").first()
        if req is None or not rights.request_visible(actor, req):
            raise NotVisible()
        data = request.data
        if action == "submit":
            req_svc.submit_request(req, actor)
        elif action == "review":
            req_svc.take_under_review(req, actor)
        elif action == "decide":
            berth = Berth.objects.filter(port=call.port, code=data.get("berth")).first() if data.get("berth") else None
            req_svc.decide_request(req, actor, data.get("decision", ""), reason=data.get("reason", ""),
                                   conditions=data.get("conditions", ""), valid_from=when(data.get("valid_from")),
                                   valid_until=when(data.get("valid_until")), berth=berth, scope=data.get("scope", ""))
        elif action == "schedule":
            req_svc.schedule_request(req, actor, when(data.get("scheduled_for"), "scheduled_for"))
        elif action == "execute":
            req_svc.execute_request(req, actor, note=data.get("note", ""))
        elif action == "cancel":
            req_svc.cancel_request(req, actor, data.get("reason", ""))
        else:
            raise NotVisible()
        req.refresh_from_db()
        return Response(rep.request_dict(req, actor))


# ============================================================================ documents
class StageListView(CallAPIView):
    audit_kind = "stages"

    @extend_schema(operation_id="stages_list", responses=JSON, summary="Stages of the call (areas in sequence)")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        return Response({"results": [_stage_json(s) for s in stage_svc.summary(call)]})

    @extend_schema(operation_id="stages_create", request=JSON, responses=JSON,
                   summary="Plan the next stage (agency or harbour master): berth_kind, operations[], berth?, planned_from?, planned_to?, reason?")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        data = request.data
        berth = Berth.objects.filter(port=call.port, code=data.get("berth")).first() if data.get("berth") else None
        operations = data.get("operations") or []
        if isinstance(operations, str):
            operations = [operations]
        stage = stage_svc.add_stage(call, actor, berth_kind=str(data.get("berth_kind", "")), operations=list(operations),
                                    berth=berth, planned_from=when(data.get("planned_from"), "planned_from"),
                                    planned_to=when(data.get("planned_to"), "planned_to"), reason=str(data.get("reason", "")))
        return Response(_stage_json(next(s for s in stage_svc.summary(call) if s["order"] == stage.order)), status=201)


class StageCancelView(CallAPIView):
    @extend_schema(operation_id="stages_cancel", request=JSON, responses=JSON, summary="Cancel a planned stage (reason)")
    def post(self, request, reference, stage_id):
        call, actor = self.resolve(request, reference)
        stage = call.stages.filter(pk=stage_id).first()
        if stage is None:
            raise NotVisible()
        stage_svc.cancel_stage(call, actor, stage, str(request.data.get("reason", "")))
        return Response(_stage_json(next(s for s in stage_svc.summary(call) if s["order"] == stage.order)))


def _stage_json(row: dict) -> dict:
    return {**row, "planned_from": rep.dt(row["planned_from"]), "planned_to": rep.dt(row["planned_to"]),
            "atb": rep.dt(row["atb"]), "atd": rep.dt(row["atd"])}


class FormListView(CallAPIView):
    audit_kind = "forms"

    @extend_schema(operation_id="forms_list", responses=JSON,
                   summary="Standard forms you may generate on this call (one structure: header, body, signatures, seal)")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        return Response({"results": [_form_json(f) for f in form_svc.available(call, actor)]})


class FormView(CallAPIView):
    @extend_schema(operation_id="forms_render", responses=OpenApiTypes.BINARY,
                   summary="The form rendered as a printable HTML page, pre-filled from the registry")
    def get(self, request, reference, code):
        call, actor = self.resolve(request, reference)
        form = form_svc.FORMS.get(code)
        if form is None or form not in form_svc.available(call, actor):
            raise NotVisible()
        journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                      object_kind=f"form:{code}", detail="api", request=request._request)
        return HttpResponse(form_svc.render(call, code, actor), content_type="text/html; charset=utf-8")

    @extend_schema(operation_id="forms_file", request=None, responses=JSON,
                   summary="Generate the form and file it in the call's documents (fingerprinted, under your role)")
    def post(self, request, reference, code):
        call, actor = self.resolve(request, reference)
        doc = form_svc.issue(call, actor, code)
        return Response(rep.document_dict(doc), status=201)


def _form_json(form) -> dict:
    family_fr, family_en = form.family_label
    return {"code": form.code, "document_type": form.document_type, "title_fr": form.title[0], "title_en": form.title[1],
            "standard_fr": form.standard[0], "standard_en": form.standard[1], "roles": sorted(form.roles),
            "family": form.family, "family_fr": family_fr, "family_en": family_en,
            "purpose_fr": form.purpose[0] if form.purpose else "", "purpose_en": form.purpose[1] if form.purpose else "",
            "answers": list(form.answers), "templates": sorted(form.templates), "needs_link": form.needs_link,
            "signers": [{"role": role, "label_fr": fr, "label_en": en} for role, (fr, en) in form.signers],
            "landscape": form.landscape}


class DocumentListView(CallAPIView):
    audit_kind = "documents"

    @extend_schema(responses=JSON, summary="Documents visible to you")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        return Response({"results": [rep.document_dict(d) for d in rights.visible_documents(actor, call)]})

    @extend_schema(request={"multipart/form-data": JSON}, responses=JSON, summary="Upload a document (multipart: file, type)")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        uploaded = request.FILES.get("file")
        if uploaded is None:
            raise RuleViolation("A file is required.")
        task = Task.objects.filter(call=call, pk=request.data.get("task_id")).first() if request.data.get("task_id") else None
        previous = Document.objects.filter(call=call, pk=request.data.get("previous_id")).first() if request.data.get("previous_id") else None
        doc = doc_svc.upload_document(call, actor, request.data.get("type", ""), uploaded,
                                      title=request.data.get("title", ""), confidentiality=request.data.get("confidentiality", ""),
                                      counterpart_role=request.data.get("counterpart_role", ""), task=task, previous=previous,
                                      as_role=request.data.get("role"))
        return Response(rep.document_dict(doc), status=201)


class DocumentDownloadView(CallAPIView):
    @extend_schema(responses=OpenApiTypes.BINARY, summary="Download a document (access is audited)")
    def get(self, request, reference, document_id):
        call, actor = self.resolve(request, reference)
        doc = Document.objects.filter(call=call, pk=document_id).select_related("type").first()
        if doc is None or not rights.document_visible(actor, doc):
            raise NotVisible()
        journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="download", obj=doc,
                      request=request._request)
        # the type recognised from the content (PDF, images) or the platform's own HTML; anything a party
        # declared is served as plain bytes, never as a script or a page of this site
        known = doc.mime_type in doc_svc.SNIFFED_TYPES or (doc.generated and doc.mime_type == "text/html")
        response = FileResponse(doc.file.open("rb"), as_attachment=True, filename=doc.original_name,
                                content_type=doc.mime_type if known else "application/octet-stream")
        response["Content-Security-Policy"] = "sandbox; default-src 'none'"
        return response


class DocumentSignView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Sign a document (optional hand-drawn signature PNG)")
    def post(self, request, reference, document_id):
        call, actor = self.resolve(request, reference)
        doc = Document.objects.filter(call=call, pk=document_id).first()
        if doc is None or not rights.document_visible(actor, doc):
            raise NotVisible()
        doc_svc.sign_document(doc, actor, signature_image=request.data.get("signature_image", ""),
                              as_role=request.data.get("role"))
        doc.refresh_from_db()
        return Response(rep.document_dict(doc))


# ============================================================================ measurements & pumping log
class MeasurementListView(CallAPIView):
    audit_kind = "measurements"

    @extend_schema(responses=JSON, summary="Measurements (ship / shore / surveyor)")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        if not rights.measurements_visible(actor):
            raise NotVisible()
        return Response({"results": [rep.measurement_dict(m) for m in call.measurements.all()]})

    @extend_schema(request=JSON, responses=JSON, summary="Open a measurement")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        m = meas_svc.create_measurement(call, actor, request.data.get("kind", ""), unit=request.data.get("unit", "MT"),
                                        product=request.data.get("product", ""))
        return Response(rep.measurement_dict(m), status=201)


class MeasurementValueView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Add your party's value (single emitter)")
    def post(self, request, reference, measurement_id):
        call, actor = self.resolve(request, reference)
        m = Measurement.objects.filter(call=call, pk=measurement_id).first()
        if m is None or not rights.measurements_visible(actor):
            raise NotVisible()
        data = request.data
        meas_svc.add_value(m, actor, data.get("party", ""), data.get("value"), temperature=data.get("temperature_c"),
                           density=data.get("density"), declared_at=when(data.get("declared_at")), note=data.get("note", ""))
        return Response(rep.measurement_dict(m), status=201)


class PumpingLogView(CallAPIView):
    audit_kind = "pumping"

    @extend_schema(responses=JSON, summary="Pumping log")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        if not rights.measurements_visible(actor):
            raise NotVisible()
        return Response({"results": [{"declared_at": rep.dt(p.declared_at), "role": p.role, "by": p.entered_label,
                                      "pressure_bar": str(p.manifold_pressure_bar) if p.manifold_pressure_bar is not None else None,
                                      "rate_m3h": str(p.flow_rate_m3h) if p.flow_rate_m3h is not None else None,
                                      "temperature_c": str(p.temperature_c) if p.temperature_c is not None else None,
                                      "source": p.source, "deferred": p.deferred} for p in call.pumping_log.all()]})

    @extend_schema(request=JSON, responses=JSON, summary="Add a pumping-log reading (manual or automatic feed)")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        data = request.data
        entry = meas_svc.add_pumping_entry(call, actor, declared_at=when(data.get("declared_at"), "declared_at"),
                                           manifold_pressure_bar=data.get("pressure_bar"), flow_rate_m3h=data.get("rate_m3h"),
                                           temperature_c=data.get("temperature_c"), note=data.get("note", ""),
                                           device_id=data.get("device_id", ""), automatic=bool(data.get("automatic")))
        return Response({"id": entry.pk}, status=201)


# ============================================================================ disputes & correspondence
class DisputeListView(CallAPIView):
    audit_kind = "disputes"

    @extend_schema(responses=JSON, summary="Disputes")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        items = [d for d in call.disputes.all() if rights.dispute_header_visible(actor, d)]
        return Response({"results": [rep.dispute_dict(d, actor) for d in items]})

    @extend_schema(operation_id="disputes_create", request=JSON, responses=JSON, summary="Open a dispute")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        data = request.data
        d = disputes.open_dispute(call, actor, target_kind=data.get("target_kind", "OTHER"), target_id=data.get("target_id"),
                                  subject=data.get("subject", ""), statement=data.get("statement", ""),
                                  as_role=data.get("role"), counterpart_role=data.get("counterpart_role", ""))
        return Response(rep.dispute_dict(d, actor), status=201)


class DisputeActionView(CallAPIView):
    @extend_schema(operation_id="disputes_action", request=JSON, responses=JSON, summary="respond | close (agreed true/false) — no 'reject' exists")
    def post(self, request, reference, dispute_id, action):
        call, actor = self.resolve(request, reference)
        d = call.disputes.filter(pk=dispute_id).first()
        if d is None or not rights.dispute_header_visible(actor, d):
            raise NotVisible()
        if action == "respond":
            disputes.respond(d, actor, request.data.get("text", ""))
        elif action == "close":
            disputes.close(d, actor, agreed=bool(request.data.get("agreed")), text=request.data.get("text", ""))
        else:
            raise NotVisible()
        d.refresh_from_db()
        return Response(rep.dispute_dict(d, actor))


class ThreadListView(CallAPIView):
    audit_kind = "threads"

    @extend_schema(responses=JSON, summary="Correspondence threads of the call")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        threads = [t for t in call.threads.all() if rights.thread_visible(actor, t)]
        return Response({"results": [{"id": t.pk, "subject": t.subject, "confidentiality": t.confidentiality,
                                      "participants": t.participant_roles,
                                      "messages": [{"role": m.role, "by": m.author_label, "body": m.body, "at": rep.dt(m.sent_at)}
                                                   for m in t.messages.all()]} for t in threads]})

    @extend_schema(request=JSON, responses=JSON, summary="Open a thread (always attached to the call)")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        data = request.data
        t = correspondence.create_thread(call, actor, subject=data.get("subject", ""),
                                         participant_roles=data.get("participants", []), body=data.get("body", ""),
                                         confidentiality=data.get("confidentiality", "N2"),
                                         related_kind=data.get("related_kind", ""), related_id=data.get("related_id"))
        return Response({"id": t.pk}, status=201)


class ThreadMessageView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Post a message in a thread")
    def post(self, request, reference, thread_id):
        call, actor = self.resolve(request, reference)
        t = Thread.objects.filter(call=call, pk=thread_id).first()
        if t is None or not rights.thread_visible(actor, t):
            raise NotVisible()
        msg = correspondence.post_message(t, actor, request.data.get("body", ""))
        return Response({"id": msg.pk}, status=201)


# ============================================================================ journal, export, sync, field bundle
class JournalView(CallAPIView):
    audit_kind = "journal"

    @extend_schema(responses=JSON, summary="Call journal (hash-chained), filtered by your roles")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        entries = [e for e in call.journal.order_by("seq") if journal.entry_visible(e, actor)]
        return Response({"results": [rep.journal_dict(e) for e in entries]})


class ExportView(CallAPIView):
    @extend_schema(responses=OpenApiTypes.BINARY, summary="Export (zip, documented open format) — COM and DIR")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        payload = exports.export_call(call, actor, request=request._request)
        response = HttpResponse(payload, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{call.reference}.zip"'
        return response


class SyncView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Offline synchronisation batch (field app)")
    def post(self, request, reference):
        call, actor = self.resolve(request, reference)
        entries = request.data.get("entries", [])
        if not isinstance(entries, list) or len(entries) > 500:
            raise RuleViolation("Send between 1 and 500 entries.")
        return Response({"results": process_batch(call, actor, entries)})


class FieldBundleView(CallAPIView):
    audit_kind = "field-bundle"

    @extend_schema(responses=JSON, summary="Everything the field app needs to work offline for this call")
    def get(self, request, reference):
        call, actor = self.resolve(request, reference)
        types = MilestoneType.objects.filter(port=call.port, is_active=True, field_entry=True).order_by("order")
        recordable = []
        for t in types:
            if t.emitter_role == MilestoneType.ORIGIN:
                ok = bool(set(actor.roles) & set(ms_svc.ORIGIN_ROLES))
            else:
                ok = t.emitter_role in actor.roles
            if ok:
                recordable.append({"code": t.code, "label": t.label, "requires_cause": t.requires_cause,
                                   "closes": t.closes_type, "repeatable": t.repeatable, "hold_point": t.hold_point})
        milestones = list(rights.visible_milestones(actor, call).prefetch_related("signatures"))
        open_interruptions = [m for m in milestones if m.type.code == "INTERRUPTION_START"
                              and not any(f.type.code == "INTERRUPTION_END" and f.related_id == m.pk for f in milestones)]
        to_countersign = [m for m in milestones if set(m.countersigner_roles) & set(actor.roles)
                          and ms_svc.state_by_role(m).get(next(iter(set(m.countersigner_roles) & set(actor.roles)))) == "PENDING"]
        tasks = rights.visible_tasks(actor, call).filter(status="PENDING").prefetch_related("signatures")
        return Response({
            "call": rep.call_detail(call, actor),
            "roles": sorted(actor.roles),
            "milestone_types": recordable,
            "causes": [{"code": c.code, "label": c.label, "requires_reason": c.requires_reason}
                       for c in call.port.interruption_causes.filter(is_active=True)],
            "open_interruptions": [rep.milestone_dict(m) for m in open_interruptions],
            "to_countersign": [rep.milestone_dict(m) for m in to_countersign],
            "recent_milestones": [rep.milestone_dict(m) for m in milestones[-30:]],
            "tasks": [rep.task_dict(t) for t in tasks if actor.has(t.role) or t.role == "ANY" or set(t.co_roles) & set(actor.roles)],
            "measurements": [rep.measurement_dict(m) for m in call.measurements.all()] if rights.measurements_visible(actor) else [],
        })


# ============================================================================ dashboard, AIS, verification
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=JSON, summary="Real-time board and indicators (no N4 object, in any form)")
    def get(self, request):
        user = request.user
        if getattr(user, "master", None) is not None or not (set(user.role_set) & rights.roles_with("V", "dashboard")):
            raise NotVisible()
        qs = rights.call_queryset_for_user(user).select_related("vessel", "berth").exclude(status="DRAFT")
        board = {}
        for call in qs.filter(status__in=ACTIVE_STATUSES + ["DEPARTED"]).order_by("eta"):
            board.setdefault(call.status, []).append(rep.call_summary(call))
        return Response({"board": board, "indicators": reports.indicators(user.port, visible_calls=qs)})


class AisView(APIView):
    """Integration endpoint for an AIS provider (integration account with scope 'ais')."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=JSON, responses=JSON, summary="AIS observation: {imo|mmsi, event: ARRIVAL|DEPARTED, time}")
    def post(self, request):
        user = request.user
        if not getattr(user, "is_integration", False) or "ais" not in (user.integration_scopes or []):
            raise PermissionRefused("Reserved to an AIS integration account.")
        data = request.data
        vessel_q = Vessel.objects.filter(port=user.port)
        vessel = vessel_q.filter(imo=str(data.get("imo", ""))).first() or (
            vessel_q.filter(mmsi=str(data.get("mmsi", ""))).first() if data.get("mmsi") else None)
        if vessel is None:
            raise NotVisible()
        call = PortCall.objects.filter(port=user.port, vessel=vessel, status__in=ACTIVE_STATUSES + ["DEPARTED"]).order_by("-eta").first()
        if call is None:
            raise NotVisible()
        event = {"ARRIVAL": "ARRIVAL", "DEPARTED": "DEPARTED"}.get(str(data.get("event", "")).upper())
        if event is None:
            raise RuleViolation("event must be ARRIVAL or DEPARTED.")
        return Response(ms_svc.corroborate_ais(call, event, when(data.get("time"), "time")))


class AisPositionsView(APIView):
    """The AIS board: positions posted by a receiver or a provider (scope 'ais'), read by every party of the port."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=JSON, responses=JSON,
                   summary="AIS position reports: {reports: [{mmsi, lat, lon, observed_at?, speed_kn?, course_deg?, "
                           "heading_deg?, nav_status?, imo?, name?, call_sign?, destination?, draught_m?}]}")
    def post(self, request):
        user = request.user
        if not getattr(user, "is_integration", False) or "ais" not in (user.integration_scopes or []):
            raise PermissionRefused("Reserved to an AIS integration account.")
        if user.port is None:
            raise NotVisible()
        data = request.data
        reports = data if isinstance(data, list) else (data or {}).get("reports")
        if not isinstance(reports, list) or len(reports) > 5000:
            raise RuleViolation("reports must be a list of at most 5000 position reports.")
        return Response(ais_svc.ingest(user.port, reports, source=f"api:{user.pk}"))

    @extend_schema(responses=JSON, summary="Latest position of every vessel heard in the port waters (24 h)")
    def get(self, request):
        user = request.user
        if user.port is None:
            raise NotVisible()
        data = ais_svc.board(user.port, visible_calls=rights.call_queryset_for_user(user))
        journal.audit(port=user.port, user=user, action="view", object_kind="ais_board", detail="api", request=request)
        return Response(ais_svc.positions_json(data))


class VerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "verify"

    @extend_schema(responses=JSON, summary="Public verification of an authorization by its code")
    def get(self, request, code):
        info = req_svc.verify_authorization(code)
        if info is None:
            raise NotVisible()
        return Response({k: (rep.dt(v) if hasattr(v, "isoformat") else v) for k, v in info.items()})


# ============================================================================ N4 security domain
class SecureDepositView(CallAPIView):
    @extend_schema(request=JSON, responses=JSON, summary="Write-only N4 deposit (armed guards, escort…) — returns a receipt")
    def post(self, request, reference):
        from apps.secure import services as n4

        call, actor = self.resolve(request, reference)
        receipt = n4.deposit(call, actor, kind=request.data.get("kind", ""), payload=request.data.get("payload", {}),
                             request=request._request)
        return Response({"receipt": receipt}, status=201)


class SecureItemListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="secure_items_list", responses=JSON, summary="N4 items (security authority and harbour master only)")
    def get(self, request):
        from apps.secure import services as n4

        user = request.user
        if getattr(user, "master", None) is not None:
            raise NotVisible()
        items = n4.list_items(user, user.port, request=request._request)
        return Response({"results": [{"reference": i.reference, "kind": i.kind, "status": i.status,
                                      "call": i.call_reference, "vessel": i.vessel_name,
                                      "submitted_at": rep.dt(i.submitted_at), "due_at": rep.dt(i.due_at)} for i in items]})


class SecureItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="secure_items_retrieve", responses=JSON, summary="Read an N4 item (access logged nominatively)")
    def get(self, request, reference):
        from apps.secure import services as n4

        user = request.user
        if getattr(user, "master", None) is not None:
            raise NotVisible()
        content = n4.read_item(user, user.port, reference, request=request._request)
        item = content["item"]
        return Response({"reference": item.reference, "kind": item.kind, "status": item.status, "call": item.call_reference,
                         "vessel": item.vessel_name, "submitted_by": item.submitted_by_label,
                         "submitted_at": rep.dt(item.submitted_at), "payload": content["payload"],
                         "decision": content["decision"]})

    @extend_schema(request=JSON, responses=JSON, summary="Decide on an N4 item (SUR, 2FA)")
    def post(self, request, reference):
        from apps.core import mfa
        from apps.secure import services as n4

        user = request.user
        if getattr(user, "master", None) is not None:
            raise NotVisible()
        item = n4.decide(user, user.port, reference, decision=request.data.get("decision", ""),
                         modalities=request.data.get("modalities", ""), strong_auth=mfa.request_is_strong(request),
                         request=request._request)
        return Response({"reference": item.reference, "status": item.status})
