"""Screens of the AI assistance (EF-17). Every result is shown as a proposal; people act."""
from __future__ import annotations

import functools

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.registry.models import Document, Thread
from apps.registry.services import journal, rights
from apps.registry.services.context import port_actor
from apps.registry.services.errors import NotVisible, PermissionRefused, RegistryError
from apps.registry.views import resolve

from . import client, services
from .models import AssistantRun, ExtractionReview

SESSION_KEY = "fluxaa_assistant"


def _call_url(call, tab: str, anchor: str = "") -> str:
    return f"{reverse('registry:call_detail', args=[call.pk])}?tab={tab}{anchor}"


def remember(request, call, feature: str, run_id: int, key: str = "") -> None:
    """Keep the last result of a feature for this call in the session (results are personal)."""
    store = request.session.get(SESSION_KEY, {})
    store[f"{call.pk}:{feature}:{key}"] = run_id
    request.session[SESSION_KEY] = store


def recall(request, call, feature: str, key: str = "") -> AssistantRun | None:
    run_id = request.session.get(SESSION_KEY, {}).get(f"{call.pk}:{feature}:{key}")
    if not run_id:
        return None
    return AssistantRun.objects.filter(pk=run_id, call=call, requested_by=request.user, status="OK").first()


def assistant_action(view):
    @functools.wraps(view)
    def wrapper(request, pk, *args, **kwargs):
        call, actor = resolve(request, pk)
        try:
            return view(request, call, actor, *args, **kwargs)
        except NotVisible:
            raise Http404
        except client.AssistantUnavailable as exc:
            messages.error(request, _("The assistant could not complete this request: %(e)s") % {"e": exc})
        except RegistryError as exc:
            messages.error(request, exc.message)
        return redirect(request.POST.get("next") or _call_url(call, "apercu"))

    return login_required(wrapper)


# ============================================================================ extraction
@require_POST
@assistant_action
def extract(request, call, actor, doc_id):
    doc = get_object_or_404(Document, pk=doc_id, call=call)
    review = services.extract(doc, actor)
    return redirect("ai:extraction", pk=call.pk, review_id=review.pk)


@assistant_action
def extraction(request, call, actor, review_id):
    review = get_object_or_404(ExtractionReview, pk=review_id, call=call)
    if not services.can_extract(actor, review.document):
        raise NotVisible()
    if request.method == "POST":
        if request.POST.get("decision") == "dismiss":
            services.dismiss_extraction(review, actor)
            messages.info(request, _("Proposal dismissed: nothing was recorded."))
            return redirect(_call_url(call, "documents"))
        if review.kind == "CERTIFICATES":
            rows = []
            for index in request.POST.getlist("row"):
                if request.POST.get(f"keep_{index}") == "1":
                    rows.append({"name": request.POST.get(f"name_{index}", ""),
                                 "number": request.POST.get(f"number_{index}", ""),
                                 "expiry_date": request.POST.get(f"expiry_{index}", "")})
            accepted = rows
        else:
            accepted = {key: request.POST.get(f"value_{key}", "") for key in request.POST.getlist("keep")}
        services.validate_extraction(review, actor, accepted)
        messages.success(request, _("Values validated and recorded under your name."))
        if review.kind == "BL" and (review.validated or {}).get("quantity"):
            return redirect(_call_url(call, "mesures", f"&prefill_bl={review.pk}"))
        return redirect(_call_url(call, "documents"))
    fields = []
    if review.kind != "CERTIFICATES":
        labels = dict(services.Q88_FIELDS if review.kind == "Q88" else services.BL_FIELDS)
        vessel = call.vessel
        for key, label in labels.items():
            proposal = (review.proposed or {}).get(key) or {}
            current = getattr(vessel, key, None) if review.kind == "Q88" else None
            fields.append({
                "key": key, "label": _(label), "value": proposal.get("value") or "", "evidence": proposal.get("evidence") or "",
                "current": "" if current in (None, "") else str(current),
                "applicable": review.kind != "Q88" or key in services.Q88_APPLICABLE,
            })
    imo_mismatch = False
    if review.kind == "Q88":
        proposed_imo = ((review.proposed or {}).get("imo") or {}).get("value") or ""
        imo_mismatch = bool(proposed_imo) and "".join(c for c in proposed_imo if c.isdigit()) != call.vessel.imo
    elif review.kind == "CERTIFICATES":
        proposed_imo = (review.proposed or {}).get("vessel_imo") or ""
        imo_mismatch = bool(proposed_imo) and "".join(c for c in proposed_imo if c.isdigit()) != call.vessel.imo
    return render(request, "ai/extraction.html", {
        "call": call, "actor": actor, "review": review, "fields": fields,
        "certificates": (review.proposed or {}).get("certificates", []) if review.kind == "CERTIFICATES" else [],
        "imo_mismatch": imo_mismatch, "editable": review.status == ExtractionReview.Status.PROPOSED,
    })


# ============================================================================ review, summary, remarks
@require_POST
@assistant_action
def review(request, call, actor):
    run = services.review_call(call, actor)
    remember(request, call, "REVIEW", run.pk)
    return redirect(_call_url(call, "apercu", "#assistant"))


@require_POST
@assistant_action
def raise_alert(request, call, actor, run_id, index):
    run = get_object_or_404(AssistantRun, pk=run_id, call=call, feature=AssistantRun.Feature.REVIEW)
    services.raise_finding(run, index, actor)
    raised = request.session.get(f"{SESSION_KEY}:raised", [])
    raised.append(f"{run.pk}:{index}")
    request.session[f"{SESSION_KEY}:raised"] = raised
    messages.success(request, _("Alert raised: it is recorded in the call journal under your name."))
    return redirect(_call_url(call, "apercu", "#assistant"))


@require_POST
@assistant_action
def summarize(request, call, actor, thread_id):
    thread = get_object_or_404(Thread, pk=thread_id, call=call)
    run = services.summarize_thread(thread, actor)
    remember(request, call, "SUMMARY", run.pk, key=str(thread.pk))
    return redirect(_call_url(call, "echanges", f"#fil-{thread.pk}"))


@require_POST
@assistant_action
def remarks(request, call, actor):
    run = services.draft_remarks(call, actor)
    remember(request, call, "REMARKS", run.pk)
    return redirect(_call_url(call, "apercu", "#statement"))


# ============================================================================ context for the call tabs
def tab_context(request, call, actor, tab: str) -> dict:
    """What the call page needs to show the assistant (nothing when it is off for the port)."""
    if not client.enabled_for(call.port) or actor.is_master:
        return {"assistant": None}
    context = {"enabled": True}
    if tab == "apercu":
        run = recall(request, call, "REVIEW")
        raised = set(request.session.get(f"{SESSION_KEY}:raised", []))
        if run:
            context["review"] = {"run": run, "findings": [
                dict(f, index=i, raised=f"{run.pk}:{i}" in raised) for i, f in enumerate(run.output.get("findings", []))]}
        context["rule_findings"] = services.deterministic_findings(call, actor)
        context["can_review"] = bool(set(actor.roles) & services.REVIEW_ROLES)
        remarks_run = recall(request, call, "REMARKS")
        context["remarks"] = remarks_run.output.get("text", "") if remarks_run else ""
    elif tab == "echanges":
        summaries = {}
        for key, run_id in request.session.get(SESSION_KEY, {}).items():
            if key.startswith(f"{call.pk}:SUMMARY:"):
                run = recall(request, call, "SUMMARY", key.rsplit(":", 1)[1])
                if run:
                    summaries[int(key.rsplit(":", 1)[1])] = run.output.get("text", "")
        context["summaries"] = summaries
    elif tab == "documents":
        context["reviews"] = {r.document_id: r for r in ExtractionReview.objects.filter(
            call=call, status=ExtractionReview.Status.PROPOSED, run__requested_by=request.user)}
    elif tab == "mesures":
        prefill = request.GET.get("prefill_bl")
        if prefill and prefill.isdigit():
            review_obj = ExtractionReview.objects.filter(pk=int(prefill), call=call, kind="BL", status="APPLIED").first()
            if review_obj:
                context["bl_prefill"] = (review_obj.validated or {}).get("quantity", "")
    return {"assistant": context}


def can_extract(actor, doc) -> bool:
    return services.can_extract(actor, doc)


# ============================================================================ port level: brief and questions
PORT_KEY = "port"


@login_required
def port(request):
    """The assistant of the port (EF-17 extended): a brief on demand and questions on the registry, for the
    direction, the authority and the harbour master. Results are personal and kept in the session only."""
    user = request.user
    the_port = getattr(user, "port", None)
    if the_port is None or not client.enabled_for(the_port) or not (set(user.role_set) & services.PORT_ROLES):
        raise Http404
    try:
        actor = port_actor(user)
    except PermissionRefused:
        raise Http404
    visible = rights.call_queryset_for_user(user)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "brief":
                run = services.port_brief(the_port, actor, visible_calls=visible)
                _remember_port(request, "BRIEF", run.pk)
            elif action == "ask":
                run = services.ask_port(the_port, actor, request.POST.get("question", ""), visible_calls=visible)
                _remember_port(request, "QUESTION", run.pk)
            else:
                raise Http404
        except client.AssistantUnavailable as exc:
            messages.error(request, _("The assistant could not complete this request: %(e)s") % {"e": exc})
        except RegistryError as exc:
            messages.error(request, exc.message)
        return redirect(reverse("ai:port") + ("#question" if action == "ask" else ""))
    journal.audit(port=the_port, user=user, action="view", object_kind="assistant_port", request=request)
    brief = _recall_port(request, "BRIEF")
    answer = _recall_port(request, "QUESTION")
    return render(request, "ai/port.html", {
        "port": the_port, "brief": brief, "answer": answer, "inventory": (answer or brief).input_inventory if (answer or brief) else [],
        "question": "", "max_chars": services.QUESTION_MAX_CHARS,
    })


def _remember_port(request, feature: str, run_id: int) -> None:
    store = request.session.get(SESSION_KEY, {})
    store[f"{PORT_KEY}:{feature}"] = run_id
    request.session[SESSION_KEY] = store


def _recall_port(request, feature: str) -> AssistantRun | None:
    run_id = request.session.get(SESSION_KEY, {}).get(f"{PORT_KEY}:{feature}")
    if not run_id:
        return None
    return AssistantRun.objects.filter(pk=run_id, call__isnull=True, port=request.user.port, requested_by=request.user,
                                       status="OK").first()
