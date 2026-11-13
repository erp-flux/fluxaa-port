"""Web interface of the registry. Every action goes through the services layer, which enforces rights,
hold points and invariants; the views only collect input and present results."""
from __future__ import annotations

import functools
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from django.utils.translation import get_language, gettext_noop
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core import mfa, throttle
from apps.core.models import Berth, Organization, Port, pick
from apps.core.parties import kinds_for_role, parties_for_operation
from apps.core.roles import ALL_ROLES, role_label

from . import checklists
from .models import (
    ACTIVE_STATUSES,
    QUANTITY_UNITS,
    UNITS_BY_CARGO,
    CallParty,
    CallStatus,
    CallTemplate,
    CargoKind,
    Document,
    DocumentType,
    InterruptionCause,
    Measurement,
    MeasurementParty,
    Milestone,
    MilestoneType,
    PortCall,
    PumpingLogSheet,
    RequestType,
    ServiceRequest,
    StsRole,
    TankReading,
    Task,
    TaskStatus,
    TemplateKind,
    Thread,
    Vessel,
    VesselKind,
)
from .services import board as board_svc
from .services import calls as call_svc
from .services import checklist as checklist_svc
from .services import correspondence, disputes, exports, holdpoints, journal, preparation, reports, rights, stats
from .services import documents as doc_svc
from .services import forms as form_svc
from .services import intake as intake_svc
from .services import measurements as meas_svc
from .services import milestones as ms_svc
from .services import requests as req_svc
from .services import stages as stage_svc
from .services import tasks as task_svc
from .services.access import MASTER_SESSION_KEY, call_and_actor, master_from_session
from .services.context import port_actor
from .services.errors import HoldPointRefused, NotVisible, RegistryError, RuleViolation, StrongAuthRequired
from .services.forms import cargo as cargo_forms

TABS = [
    ("apercu", gettext_noop("Overview")), ("taches", gettext_noop("Tasks")), ("jalons", gettext_noop("Milestones")), ("demandes", gettext_noop("Requests")),
    ("documents", gettext_noop("Documents")), ("mesures", gettext_noop("Measurements")), ("contestations", gettext_noop("Disputes")),
    ("echanges", gettext_noop("Correspondence")), ("journal", gettext_noop("Journal")), ("parties", gettext_noop("Parties")),
]


# ============================================================================ helpers
def parse_local(value):
    """Parse a datetime-local value in the active (port) time zone."""
    if not value:
        return None
    parsed = parse_datetime(value)
    if parsed is None:
        raise ValidationError(_("Invalid date and time."))
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def refusal_context(exc: HoldPointRefused) -> dict:
    lang = "en" if (get_language() or "fr").startswith("en") else "fr"
    head = exc.message.split("\n")[0] if exc.message else ""
    from .models import Nature

    return {
        "head": head,
        "missing": [{"task": m["task"], "title": m["title_en"] if lang == "en" else m["title_fr"],
                     "roles": ", ".join(role_label(r) for r in [m["role"], *m.get("co_roles", [])]),
                     "action": str(Nature(m["nature"]).label)} for m in exc.missing],
        "reasons": exc.reasons,
    }


def pop_refusal(request):
    return request.session.pop("fluxaa_refusal", None)


def enrich_refusal(refusal: dict | None, call, actor) -> dict | None:
    """The refusal box names, for each missing task, the organisations that answer for it and whether they can
    act, and offers the actor its own way out: provide the document, confirm, remind the party, hand the master his
    access (FLX-CDC-002 v1.4, EXG-Q-09)."""
    if not refusal:
        return refusal
    tasks = {t.code: t for t in call.tasks.filter(status=TaskStatus.PENDING)}
    for item in refusal.get("missing", []):
        task = tasks.get(item["task"])
        if task is None:
            continue
        item["id"] = task.pk
        item["responsible"] = preparation.responsible(call, task)
        item["hint"] = preparation.hint(task)
        item["can_act"] = (task.role in actor.roles or bool(set(task.co_roles) & set(actor.roles)) or task.role == "ANY") \
            and not actor.has("COM")
        item["can_remind"] = actor.has("AGE", "CAP")
        item["needs_master_link"] = task.role == "NAV" and preparation.master_link(call) is None
    refusal["can_manage_parties"] = actor.has("AGE", "CAP")
    return refusal


def call_url(call, tab=None) -> str:
    url = reverse("registry:call_detail", args=[call.pk])
    return f"{url}?tab={tab}" if tab else url


def back_url(request) -> str:
    """Where to return after an action: a relative "?tab=…" is resolved against the call page."""
    back = request.POST.get("back") or ""
    if back.startswith(("?", "#")) and "/action/" in request.path:
        return request.path.split("/action/", 1)[0] + "/" + back
    if back.startswith("/") and not back.startswith("//"):
        return back
    return request.META.get("HTTP_REFERER", "/")


def web_action(view):
    """Translate business refusals into user messages; hold point refusals get the dedicated box."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except NotVisible:
            raise Http404
        except StrongAuthRequired:
            messages.warning(request, _("Confirm your identity with your second factor to take this decision."))
            from urllib.parse import quote

            return redirect(f"{reverse('core:mfa_verify')}?next={quote(back_url(request))}")
        except HoldPointRefused as exc:
            request.session["fluxaa_refusal"] = refusal_context(exc)
        except RegistryError as exc:
            messages.error(request, exc.message)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect(back_url(request))

    return wrapper


def resolve(request, pk):
    try:
        return call_and_actor(request, pk)
    except NotVisible:
        raise Http404


def account_or_master(view):
    """The master has no account: the account-less session opened by /bord/ is accepted."""

    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            link = master_from_session(request)
            if link is None:
                return redirect(f"{settings.LOGIN_URL and reverse(settings.LOGIN_URL)}?next={request.get_full_path()}")
            if not link.master_name:  # a party's link issued by the platform: the holder names themselves first
                return redirect("registry:link_name")
        return view(request, *args, **kwargs)

    return wrapper


# ============================================================================ strip (passage plan of a call)
def build_strip(call) -> dict | None:
    now = timezone.now()
    start = call.ata or call.eta
    end = call.atd or call.etd or (call.t1 + timedelta(hours=6) if call.t1 else None) or (start + timedelta(hours=48))
    if end <= start:
        end = start + timedelta(hours=24)
    span = (end - start).total_seconds()

    def pct(moment):
        return max(0.0, min(100.0, (moment - start).total_seconds() / span * 100))

    def seg(kind, a, b, label):
        if a is None:
            return None
        b = b or min(now, end)
        if b <= a:
            return None
        return {"kind": kind, "left": round(pct(a), 2), "width": round(pct(b) - pct(a), 2), "label": label}

    segs = []
    if call.ata:
        segs.append(seg("wait", call.ata, call.atb or (now if not call.atd else call.atd), _("Waiting")))
    if call.atb:
        segs.append(seg("alongside", call.atb, call.t0, _("Alongside, before transfer")))
    if call.t0:
        segs.append(seg("transfer", call.t0, call.t1, _("Transfer")))
    for stop in call.milestones.filter(type__code="INTERRUPTION_START", is_conflict=False).select_related("cause"):
        end_m = call.milestones.filter(type__code="INTERRUPTION_END", related=stop).first()
        segs.append(seg("stop", stop.declared_at, end_m.declared_at if end_m else None,
                        _("Interruption") + (f" — {stop.cause.label}" if stop.cause else "")))
    if call.t1:
        segs.append(seg("alongside", call.t1, call.atd, _("After transfer")))
    if now < end:
        segs.append({"kind": "future", "left": round(pct(max(now, start)), 2), "width": round(100 - pct(max(now, start)), 2),
                     "label": _("Estimated")})
    marks = []
    for label, moment in (("ATA", call.ata or call.eta), ("NOR", call.nor_at), ("ATB", call.atb or call.etb),
                          ("T0", call.t0), ("T1", call.t1), ("ATD", call.atd or call.etd)):
        if moment and start <= moment <= end:
            actual = {"ATA": call.ata, "ATB": call.atb, "ATD": call.atd}.get(label, moment)
            left = round(pct(moment), 2)
            marks.append({"label": label, "left": left, "time": moment, "estimate": actual is None, "end": left > 86})
    # avoid overlapping labels: keep marks at least 7 % apart
    spaced, last = [], -100.0
    for m in sorted(marks, key=lambda m: m["left"]):
        if m["left"] - last >= 7:
            spaced.append(m)
            last = m["left"]
    now_pct = round(pct(now), 2) if start < now < end else None
    return {"segments": [s for s in segs if s], "marks": spaced, "start": start, "end": end,
            "now": now_pct, "now_end": now_pct is not None and now_pct > 86}


# ============================================================================ dashboard
def build_plan(port, calls, now) -> dict:
    window_start = now - timedelta(hours=12)
    window_end = now + timedelta(hours=60)
    span = (window_end - window_start).total_seconds()

    def pct(moment):
        return (moment - window_start).total_seconds() / span * 100

    rows = []
    berths = list(Berth.objects.filter(port=port, is_active=True).order_by("kind", "code"))
    first_anchorage = next((b for b in berths if b.kind == Berth.Kind.ANCHORAGE), None)
    bars_by_berth = {b.pk: [] for b in berths}
    unassigned = []
    for call in calls:
        start = call.atb or call.etb
        end = call.atd or call.etd
        area_based = call.requested_berth_kind in (Berth.Kind.ANCHORAGE, Berth.Kind.STS_AREA)
        if area_based:
            start = call.ata or call.eta
        if start is None:
            continue
        end = end or start + timedelta(hours=36)
        if end < window_start or start > window_end:
            continue
        bar = {"call": call, "left": max(0, pct(start)), "right": min(100, pct(end)), "estimate": not (call.atb or call.ata),
               "op": call.status == CallStatus.IN_OPERATION, "late": getattr(call, "escalated", False)}
        bar["width"] = max(1.5, bar["right"] - bar["left"])
        target = call.berth or call.requested_berth
        if target is not None and target.pk in bars_by_berth:
            bars_by_berth[target.pk].append(bar)
        else:
            unassigned.append(bar)
        # a jetty-bound vessel waiting in the roads also appears on the anchorage lane
        if not area_based and first_anchorage and call.ata and (call.atb is None or call.atb > call.ata + timedelta(hours=1)):
            w_end = call.atb or now
            if w_end > window_start:
                bars_by_berth[first_anchorage.pk].append({
                    "call": call, "left": max(0, pct(call.ata)), "width": max(1.5, min(100, pct(w_end)) - max(0, pct(call.ata))),
                    "estimate": False, "op": False, "late": False, "waiting": True})
    for berth in berths:
        rows.append({"berth": berth, "bars": bars_by_berth[berth.pk]})
    if unassigned:
        rows.append({"berth": None, "bars": unassigned})
    scale = []
    for hours in range(0, 73, 12):
        moment = window_start + timedelta(hours=hours)
        scale.append({"left": round(hours / 72 * 100, 2), "time": moment})
    return {"rows": rows, "scale": scale, "now": round(pct(now), 2)}


@login_required
def dashboard(request):
    user = request.user
    if not (set(user.role_set) & rights.roles_with("V", "dashboard")):
        return redirect("registry:call_list")
    port = user.port
    if port is None:
        raise Http404
    now = timezone.now()
    visible = rights.call_queryset_for_user(user).exclude(status=CallStatus.DRAFT)
    calls = list(visible.filter(Q(status__in=ACTIVE_STATUSES) | Q(status=CallStatus.DEPARTED, atd__gte=now - timedelta(hours=24)))
                 .select_related("vessel", "berth", "requested_berth").order_by("eta"))
    escalated = set(Task.objects.filter(call__in=calls, alert_level="ESCALATED", status=TaskStatus.PENDING)
                    .values_list("call_id", flat=True))
    for call in calls:
        call.escalated = call.pk in escalated
    groups = [
        ("expected", _("Expected"), [c for c in calls if c.status in (CallStatus.DECLARED, CallStatus.ACCEPTED, CallStatus.PLANNED)]),
        ("roads", _("At anchorage / approaching / shifting"), [c for c in calls if c.status in (CallStatus.APPROACHING, CallStatus.SHIFTING)]),
        ("alongside", _("Alongside / in operation"), [c for c in calls if c.status in (CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.OPS_COMPLETE)]),
        ("departed", _("Departed (24 h)"), [c for c in calls if c.status == CallStatus.DEPARTED]),
    ]
    my_roles = list(user.role_set)
    my_tasks = (Task.objects.filter(call__in=[c.pk for c in calls], status=TaskStatus.PENDING, due_at__isnull=False)
                .filter(Q(role__in=my_roles)).select_related("call", "call__vessel").order_by("due_at")[:12])
    context = {
        "plan": build_plan(port, calls, now), "groups": groups, "my_tasks": my_tasks, "now": now,
        "kpis": reports.indicators(port, visible_calls=visible), "draft_count": rights.call_queryset_for_user(user)
        .filter(status=CallStatus.DRAFT).count() if "AGE" in my_roles else 0,
    }
    template = "registry/_dashboard_body.html" if request.headers.get("HX-Request") else "registry/dashboard.html"
    return render(request, template, context)


@login_required
def calibration(request):
    """Alert and workload calibration for the port administrator and management (EF-6.5, ENF-8)."""
    user = request.user
    if user.port is None or not (user.is_port_admin or "DIR" in user.role_set):
        raise Http404
    days = 90
    if (request.GET.get("days") or "").isdigit():
        days = max(7, min(365, int(request.GET["days"])))
    journal.audit(port=user.port, user=user, action="view", object_kind="calibration", detail=f"{days} days",
                  request=request)
    return render(request, "registry/calibration.html", {"data": reports.calibration(user.port, days=days),
                                                          "days": days})


STATISTICS_ROLES = {"DIR", "APO", "CAP"}


@login_required
def statistics(request):
    """Statistics of the port over a period (EF-10.2 extended): direction, authority, harbour master, port admin.

    A superuser of a national instance chooses the port with ?port=CODE. Every figure is recomputed from the
    registry; the CSV carries the same tables as the page.
    """
    user = request.user
    if not (set(user.role_set) & STATISTICS_ROLES or user.is_port_admin or user.is_superuser):
        raise Http404
    port = user.port
    if user.is_superuser and request.GET.get("port"):
        port = Port.objects.filter(code=request.GET["port"].upper()).first() or port
    if port is None:
        raise Http404
    start = parse_date(request.GET.get("from", "") or "")
    end = parse_date(request.GET.get("to", "") or "")
    period_start, period_end = stats.period(start, end)
    visible = None if (user.is_superuser or user.is_port_admin) else rights.call_queryset_for_user(user)
    data = stats.compute(port, period_start, period_end, visible_calls=visible)
    detail = f"{period_start.date()}→{(period_end - timedelta(days=1)).date()}"
    if request.GET.get("format") == "csv":
        journal.audit(port=port, user=user, action="export", object_kind="statistics", detail=detail, request=request)
        response = HttpResponse(stats.to_csv(data), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="fluxaa-{port.code}-statistiques-{detail}.csv"'
        return response
    journal.audit(port=port, user=user, action="view", object_kind="statistics", detail=detail, request=request)
    def label(month: str) -> str:  # "2026-03" → "03/26"
        return f"{month[5:]}/{month[2:4]}"

    charts = {
        "calls": stats.bar_chart([(label(m["month"]), m["calls"]) for m in data["monthly"]]),
        "quantity": stats.bar_chart([(label(m["month"]), m["quantity_mt"]) for m in data["monthly"]], unit="t"),
        "waiting": stats.bar_chart([(label(m["month"]), m["waiting_h"]) for m in data["monthly"]], unit="h", decimals=1),
        "transfer": stats.bar_chart([(label(m["month"]), m["transfer_h"]) for m in data["monthly"]], unit="h", decimals=1),
    }
    ports = Port.objects.order_by("code") if user.is_superuser else None
    return render(request, "registry/statistics.html", {
        "data": data, "charts": charts, "port": port, "ports": ports,
        "from": period_start.date().isoformat(), "to": (period_end - timedelta(days=1)).date().isoformat(),
    })


# ============================================================================ calls list and creation
@login_required
def call_list(request):
    user = request.user
    qs = rights.call_queryset_for_user(user).select_related("vessel", "berth")
    if "AGE" not in user.role_set:
        qs = qs.exclude(status=CallStatus.DRAFT)
    scope = request.GET.get("scope", "active")
    if scope == "active":
        qs = qs.filter(status__in=[CallStatus.DRAFT, *ACTIVE_STATUSES, CallStatus.DEPARTED])
    if q := request.GET.get("q", "").strip():
        qs = qs.filter(Q(reference__icontains=q) | Q(vessel__name__icontains=q) | Q(vessel__imo__icontains=q))
    return render(request, "registry/call_list.html", {"calls": qs.order_by("-eta")[:300], "scope": scope, "q": q,
                                                       "can_create": "AGE" in user.role_set})


def pk_of(value):
    """A posted identifier as an integer, or None when it is empty or not a number (then no object matches:
    the caller answers "not visible" or ignores it instead of a server error)."""
    try:
        return int(str(value).strip()) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


# The access a party row may be given at the announcement (v1.5): presets of CallParty.access + scopes; the
# Parties tab offers the fine-grained choice afterwards
ACCESS_PRESETS = [
    ("FULL", _("Full access")), ("READ", _("Reading only")),
    ("PARTIAL:taches,documents", _("Partial — tasks and documents")),
    ("PARTIAL:apercu,jalons,journal", _("Partial — follow-up (overview, milestones, journal)")),
    ("PARTIAL:mesures,documents", _("Partial — measurements and documents")),
    ("PARTIAL:demandes,taches", _("Partial — requests and tasks")),
    ("PARTIAL:apercu,taches,demandes,documents", _("Partial — operations (overview, tasks, requests, documents)")),
]
SCOPE_LABELS = [("apercu", _("Overview")), ("parties", _("Parties")), ("taches", _("Tasks")), ("demandes", _("Requests")),
                ("jalons", _("Milestones")), ("documents", _("Documents")), ("mesures", _("Measurements")),
                ("contestations", _("Disputes")), ("echanges", _("Correspondence")), ("journal", _("Journal"))]
DOC_ROLES = ["AGE", "NAV", "TER", "COM", "INS", "PRE", "SVC"]


def parse_access(value: str) -> tuple[str, list[str]]:
    value = (value or "FULL").strip()
    if value.startswith("PARTIAL"):
        return "PARTIAL", [c for c in value.partition(":")[2].split(",") if c]
    return ("READ" if value == "READ" else "FULL"), []


def party_rows(data) -> list[dict]:
    """The rows of the open party list as posted (empty rows kept for the form); three blank rows by default."""
    roles, orgs = data.getlist("party_role"), data.getlist("party_org")
    names, kinds = data.getlist("party_name"), data.getlist("party_kind")
    emails, phones, access = data.getlist("party_email"), data.getlist("party_phone"), data.getlist("party_access")
    rows = []
    for i in range(max(len(roles), len(orgs), len(names))):
        pick_ = lambda values: values[i] if i < len(values) else ""  # noqa: E731
        rows.append({"role": pick_(roles), "org": pick_(orgs), "name": pick_(names).strip(), "kind": pick_(kinds).strip(),
                     "email": pick_(emails).strip(), "phone": pick_(phones).strip(), "access": pick_(access) or "FULL"})
    for role in call_svc.AGENCY_INVITABLE_ROLES:  # the former fixed slots (party_TER=<id>…) are still accepted
        for org_id in data.getlist(f"party_{role}"):
            rows.append({"role": role, "org": org_id, "name": "", "kind": "", "email": "", "phone": "", "access": "FULL"})
    while len(rows) < 3:
        rows.append({"role": ["TER", "INS", "PRE"][len(rows)], "org": "", "name": "", "kind": "", "email": "", "phone": "", "access": "FULL"})
    return rows


def resolve_parties(actor, rows: list[dict]) -> list[tuple]:
    """(organisation, role, access, scopes) of the posted rows: a registered organisation by id, or a new one
    registered on the spot (services.calls.register_organization); rows without organisation nor name are ignored."""
    parties = []
    for row in rows:
        role = row["role"]
        if row["org"] and row["org"] != "new":
            org = Organization.objects.filter(port=actor.port, pk=pk_of(row["org"])).first()
            if org is None:
                raise NotVisible()
        elif row["name"] or row["org"] == "new":
            org = call_svc.register_organization(actor, name=row["name"], role=role, kind=row["kind"], email=row["email"],
                                                 phone=row["phone"])
        else:
            continue
        if all((org, role) != (p[0], p[1]) for p in parties):
            access, scopes = parse_access(row.get("access", "FULL"))
            parties.append((org, role, access, scopes))
    return parties


def custom_doc_rows(data) -> list[dict]:
    labels, roles, hours = data.getlist("custom_doc_label"), data.getlist("custom_doc_role"), data.getlist("custom_doc_hours")
    rows = []
    for i in range(max(len(labels), 1)):
        rows.append({"label": (labels[i] if i < len(labels) else "").strip(), "role": roles[i] if i < len(roles) else "AGE",
                     "hours": hours[i] if i < len(hours) else "24"})
    return rows


def template_documents(port) -> dict[str, list[dict]]:
    """The documents each published template requires: shown at the announcement for the operations chosen."""
    docs = {}
    for template in CallTemplate.objects.filter(port=port, is_active=True).order_by("order"):
        version = template.published_version
        if version is None:
            continue
        rows = [{"number": tt.number, "title": tt.title, "role": tt.role}
                for tt in version.tasks.exclude(document_type_code="").order_by("order", "number")]
        if rows:
            docs[template.code] = rows
    return docs


def _new_vessel(port, data, prefix: str):
    imo = (data.get(f"{prefix}_imo") or "").strip()
    if not imo:
        return None
    known = Vessel.objects.filter(port=port, imo=imo).first()
    if known is not None:
        raise RuleViolation(_("IMO %(imo)s is already registered in the port: %(name)s. Choose it in the list of registered vessels instead of registering it again.")
                            % {"imo": imo, "name": known.name})
    vessel = Vessel(port=port, imo=imo, name=(data.get(f"{prefix}_name") or "").strip().upper(),
                    flag=data.get(f"{prefix}_flag", ""), vessel_type=data.get(f"{prefix}_type", ""),
                    vessel_kind=data.get(f"{prefix}_kind") or "TANKER_PRODUCT", dwt=data.get(f"{prefix}_dwt") or None)
    vessel.full_clean()
    vessel.save()
    return vessel


def _announce(user, actor, port, data):
    """The announcement form turned into a call — and, for a transfer or a double banking whose other vessel has no
    call yet, into that vessel's call under its own agency. Every refusal is raised: the caller holds the
    transaction, so that nothing registered on the way (a new vessel, a new organisation) outlives a refusal."""
    vessel = Vessel.objects.filter(port=port, pk=pk_of(data.get("vessel"))).first()
    if vessel is None and data.get("new_imo"):
        vessel = _new_vessel(port, data, "new")
    if vessel is None:
        raise RuleViolation(_("Choose a vessel or register a new one."))
    parties = resolve_parties(actor, party_rows(data))
    berth = Berth.objects.filter(port=port, pk=pk_of(data.get("requested_berth"))).first() if data.get("requested_berth") else None
    partner = PortCall.objects.filter(port=port, pk=pk_of(data.get("linked_call"))).first() if data.get("linked_call") else None

    def agency_of(select: str, name: str, email: str):
        # a registered agency of the port, or one the port does not know yet, named on the spot (v1.6)
        chosen = Organization.objects.filter(port=port, pk=pk_of(data.get(select))).first() if data.get(select) else None
        return call_svc.partner_agency(actor, organization=chosen, name=data.get(name, ""), email=data.get(email, ""))

    sts_partner = None
    if partner is None and ("M3" in data.getlist("operations") or data.get("sts_role")):
        partner_vessel = Vessel.objects.filter(port=port, pk=pk_of(data.get("partner_vessel"))).first() if data.get("partner_vessel") else None
        if partner_vessel is None and data.get("partner_imo"):
            partner_vessel = _new_vessel(port, data, "partner")
        if partner_vessel is not None:
            sts_partner = {"vessel": partner_vessel, "agency": agency_of("partner_agency", "partner_agency_name", "partner_agency_email")}
    custom = [row for row in custom_doc_rows(data) if row["label"]]
    codes = ["M0", *data.getlist("operations"), *data.getlist("modules")]
    db_partner = None
    if "M9" in codes:
        db_call = PortCall.objects.filter(port=port, pk=pk_of(data.get("db_partner_call"))).first() if data.get("db_partner_call") else None
        db_vessel = Vessel.objects.filter(port=port, pk=pk_of(data.get("db_partner_vessel"))).first() if data.get("db_partner_vessel") else None
        if db_call is None and db_vessel is None and data.get("db_imo"):
            db_vessel = _new_vessel(port, data, "db")
        if db_call is None and db_vessel is None:
            raise RuleViolation(_("A double banking names the other vessel: a call of the port, a registered vessel or a new one."))
        db_agency = agency_of("db_partner_agency", "db_agency_name", "db_agency_email") if db_call is None else None
        db_partner = {"call": db_call, "vessel": db_vessel, "agency": db_agency, "position": data.get("db_position") or "OUTER"}
    operation_details = intake_svc.parse_intake(port, codes, data.get)
    call = call_svc.create_call(
        user, vessel=vessel, eta=parse_local(data.get("eta")), requested_berth_kind=data.get("kind", ""),
        operations=data.getlist("operations"), modules=data.getlist("modules"), requested_berth=berth,
        etb=parse_local(data.get("etb")), ets=parse_local(data.get("ets")), etc=parse_local(data.get("etc")),
        etd=parse_local(data.get("etd")), product=data.get("product", ""), quantity=data.get("quantity") or None,
        quantity_unit=data.get("quantity_unit", "MT"), voyage_number=data.get("voyage", ""),
        last_port=data.get("last_port", ""), next_port=data.get("next_port", ""), parties=parties,
        linked_call=partner, link_kind="STS" if partner else "",
        planned_pump_hours=data.get("planned_pump_hours") or None, batch_reference=data.get("batch_reference", ""),
        cargo_kind=data.get("cargo_kind") or "LIQUID", validity_days=data.get("validity_days") or None,
        sts_role=data.get("sts_role", ""), sts_partner=sts_partner,
        expected_documents=data.getlist("expected_documents"),
        custom_documents=[{"label": r["label"], "role": r["role"], "hours_before_eta": r["hours"]} for r in custom],
        operation_details=operation_details, db_partner=db_partner,
    )
    return call, sts_partner, db_partner, berth, codes


@login_required
@web_action
def call_create(request):
    user = request.user
    actor = port_actor(user)
    if "AGE" not in actor.roles:
        messages.error(request, _("Only a shipping agency can create a call."))
        return redirect("registry:call_list")
    port = actor.port
    templates = CallTemplate.objects.filter(port=port, is_active=True)
    data = request.POST
    posted = dict(data.items()) if request.method == "POST" else {}
    posted.update({"operations_list": data.getlist("operations"), "modules_list": data.getlist("modules"),
                   "expected_documents_list": data.getlist("expected_documents")})
    context = {
        "vessels": Vessel.objects.filter(port=port).order_by("name"),
        "vessel_kinds": VesselKind.choices, "cargo_kinds": CargoKind.choices, "sts_roles": StsRole.choices,
        "units": [(value, label, " ".join(k for k, allowed in UNITS_BY_CARGO.items() if value in allowed)) for value, label in QUANTITY_UNITS],
        "operations": templates.filter(kind=TemplateKind.OPERATION),
        "modules": templates.filter(kind=TemplateKind.MODULE),
        "berths": Berth.objects.filter(port=port, is_active=True),
        "kinds": Berth.Kind.choices,
        # the parties of a call: an open list — any number of rows, registered organisations or new ones
        "orgs": Organization.objects.filter(port=port, is_active=True).exclude(allowed_roles=[]).order_by("name"),
        "invitable": sorted(call_svc.AGENCY_INVITABLE_ROLES, key=["TER", "INS", "COM", "PRE", "SVC", "AGE"].index),
        "party_kinds": {role: kinds_for_role(role) for role in call_svc.AGENCY_INVITABLE_ROLES},
        "party_hints": {t.code: parties_for_operation(t.code, get_language() or "fr") for t in templates.order_by("order")
                        if parties_for_operation(t.code)},
        "party_rows": party_rows(data), "access_presets": ACCESS_PRESETS,
        "agencies": Organization.objects.filter(port=port, is_active=True, allowed_roles__contains=["AGE"]).exclude(pk=user.organization_id).order_by("name"),
        # only the agency's own calls: another agency's call is linked by the harbour master
        "partners": rights.call_queryset_for_user(request.user).filter(
            status__in=[CallStatus.DRAFT, *ACTIVE_STATUSES]).select_related("vessel"),
        "template_docs": template_documents(port),
        "optional_doc_types": DocumentType.objects.filter(port=port, is_active=True, generated=False).exclude(code="OTHER").order_by("label_fr"),
        "custom_rows": custom_doc_rows(data), "doc_roles": DOC_ROLES,
        # the announcement adapts to the operation (v1.6, EXG-R-11): each model's own questions, shown when it is
        # chosen; the vessel at the berth for a double banking — any agency's call the port's board shows
        "intake": _intake_with_values(intake_svc.templates_with_intake(port), posted),
        "db_candidates": _double_banking_candidates(port, actor),
        "sts_candidates": _sts_candidates(port, actor, user),
        "data": posted,
    }
    if request.method != "POST":
        return render(request, "registry/call_create.html", context)
    try:
        # one transaction: a refused announcement registers nothing on the way — neither the new vessel, nor a new
        # organisation, nor the other vessel's call — and the form comes back as it was typed
        with transaction.atomic():
            call, sts_partner, db_partner, berth, codes = _announce(user, actor, port, data)
    except NotVisible:
        raise
    except (RegistryError, ValidationError) as exc:
        messages.error(request, getattr(exc, "message", "") or " ".join(getattr(exc, "messages", [])) or str(exc))
        return render(request, "registry/call_create.html", context)
    messages.success(request, _("Call %(ref)s created as a draft: provide the vessel data, then declare it.") % {"ref": call.reference})
    if call.linked_call_id and (sts_partner is not None or db_partner is not None and db_partner.get("call") is None):
        messages.info(request, _("The partner vessel's call %(ref)s was created and linked to this one.") % {"ref": call.linked_call.reference})
    elif call.linked_call_id and db_partner is None and call.linked_call.agency_id != call.agency_id:
        messages.info(request, _("%(ref)s belongs to another agency: it has been told, and nothing of its file is read through the link until the harbour master authorises the STS area and window.") % {"ref": call.linked_call.reference})
    elif call.linked_call_id and db_partner is not None:
        if call.linked_call.linked_call_id == call.pk:
            messages.info(request, _("Linked to %(ref)s for the double banking: the inner vessel's express consent is required before the authorization.") % {"ref": call.linked_call.reference})
        else:
            messages.info(request, _("%(ref)s belongs to another agency: it has been told, and the two files will show each other once the harbour master authorises the double banking.") % {"ref": call.linked_call.reference})
    created_partner = call.linked_call if call.linked_call_id and (sts_partner is not None or db_partner is not None and db_partner.get("call") is None) else None
    if created_partner is not None and created_partner.agency_id != call.agency_id and not call_svc.agency_has_account(created_partner.agency):
        messages.warning(request, _("%(agency)s has no account on the platform yet: the port's administrator has been told. It alone declares %(ref)s; until its accounts are open you keep an associated-agency access on that call.")
                         % {"agency": created_partner.agency.name, "ref": created_partner.reference})
    occupied = call_svc.berth_occupation(port, berth, call.etb or call.eta, call.etd, exclude=call)
    if occupied and "M9" not in codes:
        messages.warning(request, _("%(berth)s is held or expected over the same window by %(who)s — ask for another berth, revise the times, or announce a double banking (M9).")
                         % {"berth": berth.code, "who": ", ".join(f"{o.vessel.name} ({o.reference}, {o.agency})" for o in occupied[:3])})
    return redirect(call_url(call))


def _intake_with_values(intake: list[dict], posted: dict) -> list[dict]:
    """The questions of each model with what the agency already typed (a refused form comes back filled)."""
    for template in intake:
        for field in template["fields"]:
            field["value"] = posted.get(f"op_{template['code']}_{field['key']}", "")
    return intake


def _sts_candidates(port, actor, user):
    """The vessels an announcing agency may name as the partner of a ship-to-ship transfer besides its own calls:
    the calls of the other agencies the port's board shows at the anchorage or the STS area — the mother vessel
    several daughter vessels of different agencies come to."""
    if not rights.can_read_report(actor, "CALL_BOARD"):
        return []
    return (PortCall.objects.filter(port=port, status__in=ACTIVE_STATUSES).exclude(status=CallStatus.DRAFT)
            .exclude(agency=user.organization)
            .filter(Q(requested_berth_kind__in=["STS_AREA", "ANCHORAGE"]) | Q(berth__kind__in=["STS_AREA", "ANCHORAGE"]) | ~Q(sts_role=""))
            .select_related("vessel", "agency", "berth", "requested_berth").order_by("eta"))


def _double_banking_candidates(port, actor):
    """The vessels an announcing agency may name as the other vessel of a double banking: the calls the port's
    board shows at a berth or expected there — of any agency."""
    if not rights.can_read_report(actor, "CALL_BOARD"):
        return []
    return (PortCall.objects.filter(port=port, status__in=ACTIVE_STATUSES).exclude(status=CallStatus.DRAFT)
            .filter(Q(requested_berth_kind="JETTY") | Q(berth__kind="JETTY")).select_related("vessel", "agency", "berth", "requested_berth")
            .order_by("etb", "eta"))


@login_required
def berth_occupation(request):
    """HTMX fragment of the announcement: who holds or expects the requested berth over the window asked (v1.6)."""
    actor = port_actor(request.user)
    if "AGE" not in actor.roles:
        return HttpResponse("")
    berth = Berth.objects.filter(port=actor.port, pk=pk_of(request.GET.get("requested_berth"))).first() if request.GET.get("requested_berth") else None
    try:
        start = parse_local(request.GET.get("etb")) or parse_local(request.GET.get("eta"))
        end = parse_local(request.GET.get("etd"))
    except ValidationError:
        start = end = None
    rows = call_svc.berth_occupation(actor.port, berth, start, end) if berth is not None and start is not None else []
    # the vessel against the berth's acceptance limits, before the berth is asked for (the terminal's vetting grid,
    # read at the announcement): a registered vessel's particulars, or the DWT typed for a new one
    vessel = Vessel.objects.filter(port=actor.port, pk=pk_of(request.GET.get("vessel"))).first() if request.GET.get("vessel") else None
    if vessel is None and (request.GET.get("new_dwt") or "").strip().isdigit():
        vessel = Vessel(port=actor.port, imo=request.GET.get("new_imo", ""), name=request.GET.get("new_name", ""),
                        dwt=int(request.GET.get("new_dwt")))
    fit = cargo_forms.vetting_rows_for(vessel, berth, start) if berth is not None and vessel is not None else []
    assessed = [r for r in fit if r["status"] != "Z"]
    verdict = cargo_forms.vetting_verdict(fit) if assessed else None
    cargo_kind = request.GET.get("cargo_kind", "")
    kind_mismatch = bool(berth is not None and berth.cargo_kinds and cargo_kind and cargo_kind not in berth.cargo_kinds)
    return render(request, "registry/_berth_occupation.html", {
        "berth": berth, "rows": rows, "start": start, "end": end, "vessel": vessel, "fit": assessed,
        "verdict": (verdict[1] if (get_language() or "fr").startswith("en") else verdict[0]) if verdict else None,
        "unsuitable": bool(verdict and verdict[1].startswith("UNSUITABLE")), "kind_mismatch": kind_mismatch,
        "berth_kinds": [CargoKind(k).label for k in (berth.cargo_kinds or [])] if berth is not None else [],
    })


# ============================================================================ call detail
@account_or_master
def call_detail(request, pk):
    call, actor = resolve(request, pk)
    tab = request.GET.get("tab", "apercu")
    full = rights.can_see_full_call(actor)
    access, scopes = rights.access_of(actor, call)  # the part of the file this party was given (v1.5)
    tabs = [(k, _(v)) for k, v in TABS if full or k in ("apercu", "taches", "jalons", "demandes", "documents", "echanges")]
    if scopes is not None:
        tabs = [(k, v) for k, v in tabs if k in scopes]
    if tab not in dict(tabs):
        tab = tabs[0][0] if tabs else "apercu"
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                  object_kind="call", detail=tab, request=request)
    tasks = rights.visible_tasks(actor, call).prefetch_related("signatures")
    context = {
        "call": call, "actor": actor, "tab": tab, "full": full, "now": timezone.now(),
        "tabs": tabs, "access": access, "access_scopes": sorted(scopes) if scopes else None,
        "can_act_here": rights.can_act_in(actor, call, tab), "is_principal": rights.is_principal_agent(actor, call),
        "strip": build_strip(call) if full else None,
        "refusal": enrich_refusal(pop_refusal(request), call, actor),
        "my_open_tasks": [t for t in tasks if t.status == TaskStatus.PENDING and (t.role in actor.roles or t.role == "ANY"
                          or set(t.co_roles) & set(actor.roles))][:8],
        "counts": {
            "taches": sum(1 for t in tasks if t.status == TaskStatus.PENDING),
            "contestations": call.disputes.filter(status="OPEN").count(),
        },
        "is_age": actor.has("AGE"), "is_cap": actor.has("CAP"), "is_master": actor.is_master,
        "security_filing": actor.has("AGE", "NAV", "SUR", "CAP") and not call.is_terminal_state,
        "linked": call.linked_call,
        # a partner of another agency is named, not opened: the header shows it without a link (v1.6)
        "linked_open": bool(call.linked_call_id and actor.user is not None
                            and rights.call_queryset_for_user(actor.user).filter(pk=call.linked_call_id).exists()),
        "link_confirmed": call_svc.link_confirmed(call) if call.linked_call_id else False,
        "incoming_links": call_svc.incoming_links(call, actor),
    }
    builder = TAB_BUILDERS.get(tab)
    if builder:
        context.update(builder(request, call, actor))
    if not context["can_act_here"]:
        _strip_acts(context)
    if request.user.is_authenticated:
        from apps.ai.views import tab_context  # optional EF-17 assistance; empty when switched off

        context.update(tab_context(request, call, actor, tab))
    return render(request, "registry/call_detail.html", context)


_ACT_FLAGS = ("is_age", "is_cap", "is_principal", "can_act_tasks", "security_filing")
# the lists whose mere presence opens a form: the roles one may invite, the milestones one may record, the document
# types one may provide, the access links one may issue
_ACT_LISTS = ("invitable", "recordable", "doc_types", "doc_tasks", "master_links", "party_links", "linkable")


def _strip_acts(context: dict, depth: int = 0) -> None:
    """A party in reading only, or whose partial access leaves this tab out, is offered no act on it (v1.5, EXG-R-05):
    the server refuses such a POST anyway (ACTION_SCOPES / rights.require_act), the screen does not pretend otherwise.
    Every `can_…` flag of the tab's context — on the context itself, in its lists and dicts, on the objects the tabs
    decorate (tasks, requests, documents, parties, readings…) — is turned off, and so are the role flags that open
    the role's own forms (ad hoc task, security deposit, documents asked for, estimates)."""
    if depth > 4:
        return
    if isinstance(context, dict):
        for key in list(context):
            if key in _ACT_FLAGS or (key.startswith("can_") and key != "can_act_here"):
                context[key] = False
            elif key in _ACT_LISTS:
                context[key] = []
            else:
                _strip_acts(context[key], depth + 1)
    elif isinstance(context, (list, tuple)):
        for item in context:
            _strip_acts(item, depth + 1)
    elif hasattr(context, "__dict__") and not isinstance(context, type):
        for key, value in list(vars(context).items()):
            if key.startswith("can_") and isinstance(value, bool):
                setattr(context, key, False)
            elif key == "execute":
                setattr(context, key, None)
            elif isinstance(value, (list, tuple, dict)) and not key.startswith("_"):
                _strip_acts(value, depth + 1)


def _tab_overview(request, call, actor):
    readiness = []
    for transition, label in (("DECLARE", _("Declaration")), ("GREEN_LIGHT", _("Green light")),
                              ("BERTH_ASSIGN", _("Berth assignment")), ("MOVEMENT_AUTH", _("Movement authorization")),
                              ("BERTHING", _("Berthing")),
                              ("START_TRANSFER", _("Start of transfer")), ("DEPARTURE_CLEARANCE", _("Departure clearance")),
                              ("CLOSE", _("Closure"))):
        _t, missing, reasons = holdpoints.evaluate(call, transition)
        readiness.append({"label": label, "ready": not missing and not reasons, "missing": missing,
                          "reasons": [pick(fr, en) for fr, en in reasons]})
    nor = call.milestones.filter(type__code="NOR_TENDERED", is_conflict=False).first()
    can_plan_stage = actor.has("AGE", "CAP") and not call.is_terminal_state and call.status != CallStatus.DEPARTED
    checklist = checklist_svc.current(call)
    lights = task_svc.green_lights(call)
    for light in lights:  # who may give or withdraw each green light from the panel
        t = light["task"]
        light["can_give"] = (t.status == TaskStatus.PENDING and not t.request_type_code and not call.is_terminal_state
                             and (t.role in actor.roles or set(t.co_roles) & set(actor.roles)))
        light["can_withdraw"] = light["withdrawable"] and not call.is_terminal_state and (t.role in actor.roles or actor.has("CAP"))
    return {
        "readiness": readiness, "nor": nor, "nor_states": ms_svc.state_by_role(nor) if nor else {},
        "green_lights": lights,
        "validity": call.billing_basis(), "can_renew": call.status in ("EXPIRED", "CANCELLED", "REJECTED") and rights.is_principal_agent(actor, call)
        and not call.renewals.exclude(status__in=["CANCELLED", "EXPIRED", "REJECTED"]).exists(),
        "renewal": call.renewals.exclude(status__in=["CANCELLED", "EXPIRED", "REJECTED"]).first(),
        # what the declaration waits for, who answers for it, what the viewer can do about it (EXG-Q-09)
        "declaration": preparation.readiness(call, actor) if call.status == CallStatus.DRAFT and actor.has("AGE", "CAP") else None,
        "checklist": checklist, "checklist_progress": checklist_svc.progress(checklist) if checklist else None,
        "checklist_label": checklists.label(checklist.standard if checklist else checklists.standard_for(call.cargo_kind)),
        "checklist_visible": checklist_svc.visible(actor, call), "checklist_can_complete": checklist_svc.can_complete(actor, call),
        "stages": list(call.stages.select_related("berth").order_by("order")),
        "can_plan_stage": can_plan_stage,
        "berth_kinds": Berth.Kind.choices,
        "berths": Berth.objects.filter(port=call.port, is_active=True).order_by("kind", "code") if can_plan_stage else [],
        "operation_templates": CallTemplate.objects.filter(port=call.port, kind=TemplateKind.OPERATION, is_active=True)
        .order_by("order") if can_plan_stage else [],
        "master_links": call.master_links.all() if actor.has("AGE", "CAP") else [],
        "parties": call.parties.filter(revoked_at__isnull=True).select_related("organization").order_by("role"),
        "estimate_fields": [("eta", "ETA", call.eta), ("etb", "ETB", call.etb), ("ets", _("Start of operations"), call.ets),
                            ("etc", _("Completion"), call.etc), ("etd", "ETD", call.etd)],
        # what the agency declared for each operation at the announcement (v1.6, EXG-R-11) — commercial like the
        # product and the quantity: a provider reads what concerns it in the request addressed to it, not here
        "declared": intake_svc.declared(call) if rights.can_see_full_call(actor) else [],
    }


def _tab_tasks(request, call, actor):
    tasks = list(rights.visible_tasks(actor, call).prefetch_related("signatures"))
    only_mine = request.GET.get("mine") == "1"
    if only_mine:
        tasks = [t for t in tasks if t.role in actor.roles or set(t.co_roles) & set(actor.roles) or t.role == "ANY"]
    groups: dict[str, list] = {}
    # a party in reading only, or whose partial access leaves the tasks out, is offered no act at all (v1.5, EXG-R-05):
    # the server refuses them anyway (ACTION_SCOPES), the screen does not pretend otherwise
    can_act_here = rights.can_act_in(actor, call, "taches")
    for t in tasks:
        t.can_act = can_act_here and t.status == TaskStatus.PENDING and (t.role in actor.roles or t.role == "ANY" or set(t.co_roles) & set(actor.roles))
        t.signed_roles = {s.role for s in t.signatures.all() if s.kind == "SIGNED"}
        t.can_sign = t.can_act and t.joint and any(r in actor.roles and r not in t.signed_roles for r in t.all_roles)
        t.can_complete = (t.can_act and not t.joint and not t.request_type_code and not t.milestone_codes
                          and not t.document_type_code and t.nature in ("C", "R", "D") and not actor.has("COM"))
        t.can_na = can_act_here and t.status == TaskStatus.PENDING and bool(task_svc.na_roles(t) & set(actor.roles)) \
            and not call.is_terminal_state
        # how the task is carried out, right here (v1.5, EXG-R-01): the document to upload, the request to file or
        # to decide, the milestone to record, the confirmation to give
        t.execute = _execution(call, actor, t) if t.can_act and not call.is_terminal_state else None
        key = t.template_code or _("Ad hoc")
        groups.setdefault(key, []).append(t)
    return {"task_groups": groups, "only_mine": only_mine, "can_act_tasks": can_act_here,
            "cause_list": InterruptionCause.objects.filter(port=call.port, is_active=True).order_by("order")}


def _execution(call, actor, t) -> dict | None:
    """What the tasks tab offers in line to carry a pending task out."""
    if t.document_type_code:
        dtype = DocumentType.objects.filter(port=call.port, code=t.document_type_code, is_active=True).first()
        if dtype is None:
            return None
        return {"kind": "document", "type": dtype, "generated": dtype.generated,
                "forms": [f for f in form_svc.available(call, actor) if f.document_type == dtype.code]}
    if t.request_type_code:
        rtype = RequestType.objects.filter(port=call.port, code=t.request_type_code, is_active=True).first()
        if rtype is None:
            return None
        if t.request_side == "decide":
            pending = [r for r in call.requests.filter(type=rtype, status__in=["SUBMITTED", "UNDER_REVIEW", "INFO_REQUIRED"]).order_by("-pk")
                       if rights.request_visible(actor, r)]
            return {"kind": "decide", "type": rtype, "requests": pending}
        # from the announcement's answers (v1.6) — which a provider does not read, like the product and the quantity
        prefill = intake_svc.prefill_for_request(call, rtype) if rights.can_see_full_call(actor) else {}
        fields = [{**intake_svc.field_view(f), "value": prefill.get(f.get("key"), "")}
                  for f in (rtype.form_schema or []) if isinstance(f, dict) and f.get("key")]
        return {"kind": "request", "type": rtype, "fields": fields, "prefilled": bool(prefill), "idprefix": f"xr{t.pk}_"}
    if t.milestone_codes:
        types = list(MilestoneType.objects.filter(port=call.port, code__in=t.milestone_codes, is_active=True).order_by("order"))
        recorded = set(call.milestones.filter(is_conflict=False).values_list("type__code", flat=True))
        return {"kind": "milestone", "types": [m for m in types if m.code not in recorded] or types,
                "can_record": any(m.emitter_role in actor.roles or m.emitter_role == "ORIGIN" for m in types)}
    return {"kind": "confirm"}


def _tab_milestones(request, call, actor):
    items = list(rights.visible_milestones(actor, call).prefetch_related("signatures"))
    # a terminal or provider that does not speak for the shore side neither countersigns nor contests in its name
    answering = set(actor.roles) - {r for r in rights.SHORE_ROLES
                                    if r in actor.roles and not rights.speaks_for_shore(actor, r, call)}
    rows = []
    for m in items:
        states = ms_svc.state_by_role(m)
        rows.append({"m": m, "states": states, "overall": ms_svc.overall_state(m),
                     "can_countersign": any(r in answering and states.get(r) == "PENDING" for r in m.countersigner_roles),
                     "can_contest": bool(answering & ((set(m.type.contester_roles) | {"AGE", "NAV", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM"}
                                                              if "*" in m.type.contester_roles else set(m.type.contester_roles))
                                                             | set(m.countersigner_roles))) and m.emitter_role not in actor.roles})
    types = []
    for t in MilestoneType.objects.filter(port=call.port, is_active=True).exclude(emitter_role=MilestoneType.SYSTEM).order_by("order"):
        if t.emitter_role == MilestoneType.ORIGIN:
            if set(actor.roles) & set(ms_svc.ORIGIN_ROLES) and not actor.has("COM"):
                types.append(t)
        elif t.emitter_role in actor.roles and t.field_entry:
            types.append(t)
    open_stops = [r["m"] for r in rows if r["m"].type.code == "INTERRUPTION_START"
                  and not any(x["m"].related_id == r["m"].pk and x["m"].type.code == "INTERRUPTION_END" for x in rows)]
    return {"milestone_rows": rows, "recordable": types, "open_stops": open_stops,
            "causes": InterruptionCause.objects.filter(port=call.port, is_active=True)}


def _tab_requests(request, call, actor):
    visible = rights.visible_requests(actor, call)
    for r in visible:
        r.reason_visible = bool(r.decision_reason) and rights.can_see_refusal_reason(actor, r)
        r.can_decide = r.status in ("SUBMITTED", "UNDER_REVIEW") and bool(set(r.type.decision_roles) & set(actor.roles)) \
            and r.requester_role not in actor.roles
        provider_ok = not r.type.executor_role or (actor.org is not None and r.provider_org_id == actor.org.pk) \
            or (r.provider_org_id is None and len(req_svc.provider_candidates(call, r.type)) == 1)
        r.can_execute = bool(r.type.executor_role in actor.roles) and provider_ok and r.status in (
            ("SUBMITTED", "APPROVED", "APPROVED_COND", "SCHEDULED") if not r.type.decision_roles else ("APPROVED", "APPROVED_COND", "SCHEDULED"))
        own = rights.acts_for(actor, r.requester_role, r.requester_org_id)
        r.provider_choices = req_svc.provider_candidates(call, r.type) if r.type.executor_role else []
        r.can_assign_provider = own and r.type.executor_role and r.provider_org_id is None \
            and r.status in req_svc.OPEN_ORDER_STATUSES and len(r.provider_choices) > 1 and not call.is_terminal_state
        r.can_cancel = own and r.status in ("CREATED", "SUBMITTED", "INFO_REQUIRED")
        r.can_resubmit = own and r.status == "INFO_REQUIRED"
        try:
            r.auth = r.authorization
        except Exception:
            r.auth = None
    creatable = [t for t in RequestType.objects.filter(port=call.port, is_active=True) if set(t.requester_roles) & set(actor.roles)]
    selected = next((t for t in creatable if t.code == request.GET.get("type")), None)
    fields, prefill = [], {}
    if selected:
        prefill = intake_svc.prefill_for_request(call, selected) if rights.can_see_full_call(actor) else {}  # (v1.6)
        for f in selected.form_schema or []:
            fields.append({**intake_svc.field_view(f), "value": prefill.get(f.get("key"), "")})
    providers = req_svc.provider_candidates(call, selected) if selected and selected.executor_role else []
    return {"requests": visible, "creatable": creatable, "selected_type": selected, "form_fields": fields, "prefilled": bool(prefill),
            "providers": providers if len(providers) > 1 else [],
            "berths": Berth.objects.filter(port=call.port, is_active=True, kind=call.requested_berth_kind),
            "strong": mfa.session_is_strong(request)}


def _tab_documents(request, call, actor):
    docs = rights.visible_documents(actor, call)
    for d in docs:
        signed = {s.role for s in d.signatures.all()}
        d.can_sign = d.status == "ISSUED" and any(r in actor.roles and r not in signed for r in d.required_signers)
        d.can_replace = rights.is_document_issuer(actor, d) and d.status in ("ISSUED", "SIGNED") and not d.generated \
            and not call.is_terminal_state
    types = [t for t in DocumentType.objects.filter(port=call.port, is_active=True, generated=False)
             if set(t.issuer_roles or rights.roles_with("C", "document")) & set(actor.roles)]
    my_doc_tasks = [t for t in call.tasks.filter(status=TaskStatus.PENDING).exclude(document_type_code="")
                    if t.role in actor.roles or set(t.co_roles) & set(actor.roles)]
    return {"documents": docs, "doc_types": types, "doc_tasks": my_doc_tasks, "forms": form_svc.available(call, actor),
            "preselect_task": request.GET.get("task"), "preselect_type": request.GET.get("type"),
            # the documents asked for at the announcement or afterwards, beyond the templates (v1.5, EXG-R-06)
            "expected_tasks": list(call.tasks.filter(requested_at_creation=True).order_by("order")),
            "optional_doc_types": DocumentType.objects.filter(port=call.port, is_active=True, generated=False).exclude(code="OTHER").order_by("label_fr")
            if actor.has("AGE", "CAP") else [], "doc_roles": DOC_ROLES}


def _tab_measurements(request, call, actor):
    quantities = rights.measurements_visible(actor) or actor.has("NAV", "TER", "INS")
    pumping_visible = rights.can_read_report(actor, "PUMPING_LOG") or actor.has("NAV", "TER")
    if not quantities and not pumping_visible:
        return {"measurements_hidden": True}
    rows = []
    my_side = "SHIP" if actor.has("NAV") else ("SHORE" if actor.has("TER") and rights.speaks_for_shore(actor, "TER", call) else "")
    if quantities:
        for m in call.measurements.all():
            totals = meas_svc.tank_totals(m, actor)
            for side in ("SHIP", "SHORE"):
                for r in totals[side]["readings"]:
                    r.review = r.latest_review()
                    r.can_review = actor.has("INS") and r.state == "PENDING" and not call.is_terminal_state
                    r.can_correct = my_side == side and r.state != "VALIDATED" and not call.is_terminal_state
            rows.append({"m": m, "values": m.current_values(), "differences": m.differences(), "tanks": totals,
                         "declared": {p: v.value for p, v in m.current_values().items()}})
    my_parties = [p for p, role in (("SHIP", "NAV"), ("SHORE", "TER"), ("SURVEYOR", "INS")) if role in actor.roles]
    summary = meas_svc.pumping_summary(call) if pumping_visible else None
    my_sheets = [sh for sh in call.pumping_sheets.filter(side=my_side, closed_at__isnull=True)] if my_side else []
    return {"measure_rows": rows, "my_parties": my_parties, "my_side": my_side,
            "tank_sides": [("SHIP", _("Ship tanks"), _("read by the ship")), ("SHORE", _("Shore tanks"), _("read by the terminal"))],
            "pumping": call.pumping_log.select_related("sheet") if pumping_visible else [],
            "pumping_rows": meas_svc.compare_sides(call) if pumping_visible else [], "pumping_summary": summary,
            "pumping_visible": pumping_visible, "quantities_visible": quantities, "my_sheets": my_sheets,
            "tolerance": call.port.quantity_tolerance_pct,
            "kinds": Measurement.Kind.choices, "parties_labels": dict(MeasurementParty.choices),
            "units": QUANTITY_UNITS, "counterpart": pick(*meas_svc.counterpart_label(call)),
            "can_open": actor.has("INS", "TER", "NAV") and not call.is_terminal_state,
            "can_pump": bool(my_side) and meas_svc.can_keep_log(actor, call) and not call.is_terminal_state,
            "can_read_tanks": bool(my_side) and not call.is_terminal_state,
            "can_contest": bool(set(actor.roles) & disputes.OPENING_ROLES) and not call.is_terminal_state,
            "contest_counterparts": [r for r in ("NAV", "TER", "INS", "AGE") if r not in actor.roles]}


def _tab_disputes(request, call, actor):
    items = [d for d in call.disputes.all() if rights.dispute_header_visible(actor, d)]
    for d in items:
        d.content_visible = rights.dispute_content_visible(actor, d)
        opener = rights.is_dispute_opener(actor, d)
        unresolved = d.status in ("OPEN", "ANSWERED") and call.status not in ("CLOSED", "ARCHIVED")
        d.can_respond = unresolved and (rights.is_dispute_counterpart(actor, d) or (d.status == "ANSWERED" and opener))
        d.can_close = unresolved and (opener or actor.has("CAP"))
        d.close_agreement = opener  # the harbour master records a closure without agreement only
    return {"disputes": items, "can_open_dispute": bool(set(actor.roles) & disputes.OPENING_ROLES)
            and not call.is_terminal_state}


def _tab_threads(request, call, actor):
    threads = [t for t in call.threads.prefetch_related("messages") if rights.thread_visible(actor, t)]
    return {"threads": threads, "all_roles": [(r, role_label(r)) for r in ALL_ROLES if r not in actor.roles],
            "can_write": bool(set(actor.roles) & correspondence.WRITERS)}


def _tab_journal(request, call, actor):
    entries = [e for e in call.journal.order_by("-seq")[:400] if journal.entry_visible(e, actor)]
    audit = []
    if rights.can_read_audit(actor):
        from .models import AuditEntry

        audit = AuditEntry.objects.filter(call=call).order_by("-seq")[:200]
    chain = journal.verify_chain(call.port) if actor.has("CAP", "DIR") else None
    return {"entries": entries, "audit": audit, "chain": chain}


def _tab_parties(request, call, actor):
    can_manage = actor.has("AGE", "CAP")
    orgs = Organization.objects.filter(port=call.port, is_active=True).order_by("name") if can_manage else []
    parties = list(call.parties.select_related("organization").order_by("role", "created_at"))
    shore = {role: rights.shore_org_id(call, role) for role in rights.SHORE_ROLES}
    holders = {role: {p.organization_id for p in parties if p.role == role and p.revoked_at is None}
               for role in rights.SHORE_ROLES}
    principal = rights.is_principal_agent(actor, call)
    for p in parties:  # same rule as calls.revoke_party: the agency revokes only the parties it invited
        p.can_revoke = p.revoked_at is None and (actor.has("CAP") or (
            actor.has("AGE") and not p.is_default and p.role in call_svc.AGENCY_INVITABLE_ROLES))
        # the principal agent (or the harbour master) sets the access of the parties it invited (v1.5)
        p.can_set_access = p.revoked_at is None and not p.is_default and not p.is_principal and (principal or actor.has("CAP")) \
            and not call.is_terminal_state
        p.principal = p.is_principal
        several = p.role in holders and len(holders[p.role]) > 1
        p.shore = several and p.revoked_at is None and shore.get(p.role) == p.organization_id
        p.can_designate = several and not p.shore and p.revoked_at is None and can_manage \
            and not call.is_terminal_state
    links = list(call.master_links.select_related("organization")) if can_manage else []
    return {"all_parties": parties,
            "master_links": [lk for lk in links if lk.role == "NAV"],
            "party_links": [lk for lk in links if lk.role != "NAV"],
            "linkable": [p for p in parties if p.revoked_at is None and p.role in call_svc.LINK_ROLES] if can_manage else [],
            "orgs": orgs, "invitable": sorted(call_svc.AGENCY_INVITABLE_ROLES) if actor.has("AGE") and not actor.has("CAP") else list(ALL_ROLES),
            "party_kinds": {role: kinds_for_role(role) for role in ALL_ROLES},
            "scope_labels": SCOPE_LABELS, "access_presets": ACCESS_PRESETS, "is_principal": principal,
            "new_link": request.session.pop("fluxaa_new_master_link", None)}


TAB_BUILDERS = {
    "apercu": _tab_overview, "taches": _tab_tasks, "jalons": _tab_milestones, "demandes": _tab_requests,
    "documents": _tab_documents, "mesures": _tab_measurements, "contestations": _tab_disputes, "echanges": _tab_threads,
    "journal": _tab_journal, "parties": _tab_parties,
}


# ============================================================================ actions
# The part of the file each action belongs to: a partial access acts in its tabs only, a reading access never
# acts (FLX-CDC-002 v1.5, EXG-R-04). Actions outside this map belong to the overview.
ACTION_SCOPES = {
    "party_add": "parties", "party_shore": "parties", "party_revoke": "parties", "party_link": "parties", "party_access": "parties",
    "master_link": "parties", "master_revoke": "parties", "link_revoke": "parties", "remind": "apercu",
    "task_complete": "taches", "task_sign": "taches", "task_na": "taches", "task_countersign": "taches", "task_adhoc": "taches",
    "green_withdraw": "apercu", "documents_request": "documents",
    "milestone": "jalons", "countersign": "jalons",
    "request_create": "demandes", "request_provider": "demandes", "request_review": "demandes", "request_decide": "demandes",
    "request_schedule": "demandes", "request_execute": "demandes", "request_cancel": "demandes", "request_submit": "demandes",
    "document_upload": "documents", "document_sign": "documents", "document_cancel": "documents", "statement": "documents",
    "form_issue": "documents",
    "measurement_open": "mesures", "measurement_value": "mesures", "pumping": "mesures", "sheet_open": "mesures",
    "sheet_close": "mesures", "tank_reading": "mesures", "tank_review": "mesures",
    "checklist_open": "apercu", "checklist_answer": "apercu", "checklist_sign": "apercu", "checklist_cancel": "apercu",
    "dispute_open": "contestations", "dispute_respond": "contestations", "dispute_close": "contestations",
    "thread_create": "echanges", "thread_post": "echanges",
}


@require_POST
@account_or_master
@web_action
def call_action(request, pk, action):
    call, actor = resolve(request, pk)
    data = request.POST
    back = back_url(request) if data.get("back") else call_url(call)
    done = _("Recorded.")
    rights.require_act(actor, call, ACTION_SCOPES.get(action, "apercu"))

    def task():
        t = Task.objects.filter(call=call, pk=pk_of(data.get("task_id"))).first()
        if t is None or not rights.task_visible(actor, t):
            raise NotVisible()
        return t

    def obj(model, key):
        o = model.objects.filter(call=call, pk=data.get(key)).first()
        if o is None:
            raise NotVisible()
        return o

    def visible_document():
        d = obj(Document, "document_id")
        if not rights.document_visible(actor, d):
            raise NotVisible()
        return d

    if action == "declare":
        call_svc.declare_call(call, actor)
        done = _("Call declared: every party has been notified and the green light requested.")
    elif action == "estimates":
        call_svc.update_estimates(call, actor, reason=data.get("reason", ""),
                                  **{f: parse_local(data.get(f)) for f in call_svc.ESTIMATE_FIELDS if data.get(f)})
        done = _("Times revised: deadlines recomputed.")
    elif action == "cancel":
        call_svc.cancel_call(call, actor, data.get("reason", ""))
    elif action == "stage_add":
        berth = Berth.objects.filter(port=call.port, pk=pk_of(data.get("berth"))).first() if data.get("berth") else None
        stage = stage_svc.add_stage(call, actor, berth_kind=data.get("berth_kind", ""), operations=data.getlist("operations"),
                                    berth=berth, planned_from=parse_local(data.get("planned_from")),
                                    planned_to=parse_local(data.get("planned_to")), reason=data.get("reason", ""))
        done = _("Stage %(n)d planned: its tasks have been created for every party.") % {"n": stage.order}
    elif action == "stage_cancel":
        stage = call.stages.filter(pk=pk_of(data.get("stage_id"))).first()
        if stage is None:
            raise NotVisible()
        stage_svc.cancel_stage(call, actor, stage, data.get("reason", ""))
    elif action == "close_request":
        call_svc.confirm_closure(call, actor)
        done = _("Closure requested from the harbour master.")
    elif action == "close":
        call_svc.close_call(call, actor)
        done = _("Call closed.")
    elif action == "archive":
        call_svc.archive_call(call, actor)
    elif action == "link":
        wanted = (data.get("partner") or "").strip().upper()
        partner = PortCall.objects.filter(port=call.port, reference=wanted).first() if wanted else None
        if partner is None and wanted.isdigit():
            partner = PortCall.objects.filter(port=call.port, pk=int(wanted)).first()
        if partner is None:
            raise NotVisible()
        call_svc.link_partner(call, actor, partner, data.get("link_kind", "STS"))
    elif action == "party_add":
        if data.get("organization") == "new" or (not data.get("organization") and data.get("party_name")):
            org = call_svc.register_organization(actor, name=data.get("party_name", ""), role=data.get("role", ""),
                                                 kind=data.get("party_kind", ""), email=data.get("party_email", ""),
                                                 phone=data.get("party_phone", ""))
        else:
            org = Organization.objects.filter(port=call.port, pk=pk_of(data.get("organization"))).first()
            if org is None:
                raise NotVisible()
        access, scopes = parse_access(data.get("access", "FULL"))
        call_svc.add_party(call, actor, org, data.get("role", ""), access=access, scopes=scopes)
    elif action == "party_shore":
        party = call.parties.filter(pk=pk_of(data.get("party_id"))).first()
        if party is None:
            raise NotVisible()
        call_svc.designate_shore_side(call, actor, party)
        done = _("Shore side designated.")
    elif action == "party_revoke":
        party = call.parties.filter(pk=pk_of(data.get("party_id"))).first()
        if party is None:
            raise NotVisible()
        call_svc.revoke_party(call, actor, party, data.get("reason", ""))
    elif action == "party_access":
        party = call.parties.filter(pk=pk_of(data.get("party_id"))).first()
        if party is None:
            raise NotVisible()
        access = data.get("access", "FULL")
        call_svc.set_party_access(call, actor, party, access, data.getlist("scopes"))
        done = _("Access of %(org)s set: %(access)s.") % {"org": party.organization, "access": CallParty.Access(access).label}
        back = call_url(call, "parties")
    elif action == "renew":
        new = call_svc.renew_call(call, actor)
        messages.success(request, _("Announcement made again: new call %(ref)s created as a draft (validity %(days)d days).")
                         % {"ref": new.reference, "days": new.validity_days})
        return redirect(call_url(new))
    elif action == "green_withdraw":
        task_svc.withdraw_green_light(task(), actor, data.get("reason", ""))
        done = _("Green light withdrawn: everyone concerned has been told.")
        back = call_url(call) + "#feux-verts"
    elif action == "documents_request":
        custom = [row for row in custom_doc_rows(data) if row["label"]]
        created = task_svc.request_documents(call, actor, document_types=data.getlist("expected_documents"),
                                             custom=[{"label": r["label"], "role": r["role"], "hours_before_eta": r["hours"]} for r in custom])
        done = _("%(n)d document(s) now expected on the call.") % {"n": len(created)}
        back = call_url(call, "documents")
    elif action == "master_link":
        link, token, code = call_svc.issue_master_link(call, actor, master_name=data.get("master_name", ""),
                                                       channel=data.get("channel", "EMAIL"), note=data.get("note", ""),
                                                       vessel_position=data.get("vessel_position", "OWN"),
                                                       send_to=data.get("send_to", ""))
        url = f"{settings.SITE_URL}{reverse('registry:master_token', args=[token])}"
        request.session["fluxaa_new_master_link"] = {"url": url, "code": code, "name": link.master_name,
                                                     "qr": mfa.svg_data_uri(mfa.qr_svg(url))}
        done = _("Access issued: hand the link or the code to the master now — they will not be shown again.")
        if link.sent_to:
            done = _("Access issued and e-mailed to %(email)s with the list of what the port expects from the master; "
                     "the link and the code are shown once below.") % {"email": link.sent_to}
        back = call_url(call, "parties")
    elif action == "remind":
        reached = preparation.remind(call, actor, task())
        done = _("Reminder sent (%(n)d recipient(s)) and recorded in the journal.") % {"n": reached}
    elif action == "party_link":
        party = call.parties.filter(pk=pk_of(data.get("party_id")), revoked_at__isnull=True).select_related("organization").first()
        if party is None:
            raise NotVisible()
        link, token, code = call_svc.issue_party_link(call, actor, party=party, holder_name=data.get("holder_name", ""),
                                                      channel=data.get("channel", "EMAIL"), note=data.get("note", ""))
        url = f"{settings.SITE_URL}{reverse('registry:master_token', args=[token])}"
        request.session["fluxaa_new_master_link"] = {
            "url": url, "code": code, "qr": mfa.svg_data_uri(mfa.qr_svg(url)),
            "name": f"{link.master_name or party.organization.name} — {role_label(party.role)}"}
        done = _("Access issued: hand the link or the code to the party now — they will not be shown again.")
        back = call_url(call, "parties")
    elif action in ("master_revoke", "link_revoke"):
        link = call.master_links.filter(pk=pk_of(data.get("link_id"))).first()
        if link is None:
            raise NotVisible()
        call_svc.revoke_master_link(link, actor, data.get("reason", "") or "—")
    elif action == "task_complete":
        task_svc.complete_task(task(), actor, note=data.get("note", ""))
    elif action == "task_sign":
        task_svc.sign_task(task(), actor, comment=data.get("note", ""))
    elif action == "task_na":
        task_svc.mark_not_applicable(task(), actor, data.get("reason", ""))
    elif action == "task_countersign":
        task_svc.countersign_task(task(), actor, contest=data.get("contest") == "1", comment=data.get("comment", ""))
    elif action == "task_adhoc":
        task_svc.create_ad_hoc_task(call, actor, title_fr=data.get("title_fr", ""), title_en=data.get("title_en", ""),
                                    role=data.get("role", ""), anchor=data.get("anchor", ""),
                                    offset_minutes=int(data.get("offset_hours") or 0) * 60)
    elif action == "milestone":
        related = Milestone.objects.filter(call=call, pk=pk_of(data.get("related_id"))).first() if data.get("related_id") else None
        ms_svc.record_milestone(call, actor, data.get("type", ""), parse_local(data.get("declared_at")) or timezone.now(),
                                cause_code=data.get("cause", ""), cause_reason=data.get("cause_reason", ""),
                                note=data.get("note", ""), related=related,
                                source="PAPER" if data.get("paper") == "1" else "ONLINE")
        done = _("Milestone recorded.")
    elif action == "countersign":
        milestone = obj(Milestone, "milestone_id")
        if not rights.milestone_visible(actor, milestone):
            raise NotVisible()
        ms_svc.countersign_milestone(milestone, actor, contest=data.get("contest") == "1",
                                     comment=data.get("comment", ""))
        done = _("Countersignature recorded.") if data.get("contest") != "1" else _("Contest recorded: a dispute is open.")
    elif action == "request_create":
        rtype = RequestType.objects.filter(port=call.port, code=data.get("type")).first()
        if rtype is None:
            raise NotVisible()
        values = {f["key"]: (data.get(f["key"]) == "on" if f.get("type") == "boolean" else
                             (parse_local(data.get(f["key"])).isoformat() if f.get("type") == "datetime" and data.get(f["key"]) else data.get(f["key"], "")))
                  for f in rtype.form_schema or []}
        req_svc.create_request(call, actor, rtype.code, values, provider=data.get("provider") or None)
        done = _("Request submitted to the competent authority.")
        back = call_url(call, "demandes")
    elif action == "request_provider":
        req = obj(ServiceRequest, "request_id")
        if not rights.request_visible(actor, req):
            raise NotVisible()
        req_svc.assign_provider(req, actor, data.get("provider") or None)
        done = _("Provider named.")
        back = call_url(call, "demandes")
    elif action in ("request_review", "request_decide", "request_schedule", "request_execute", "request_cancel", "request_submit"):
        req = obj(ServiceRequest, "request_id")
        if not rights.request_visible(actor, req):
            raise NotVisible()
        if action == "request_review":
            req_svc.take_under_review(req, actor)
        elif action == "request_decide":
            berth = Berth.objects.filter(port=call.port, pk=pk_of(data.get("berth"))).first() if data.get("berth") else None
            req_svc.decide_request(req, actor, data.get("decision", ""), reason=data.get("reason", ""),
                                   conditions=data.get("conditions", ""), valid_from=parse_local(data.get("valid_from")),
                                   valid_until=parse_local(data.get("valid_until")), berth=berth)
            done = _("Decision recorded.")
        elif action == "request_schedule":
            req_svc.schedule_request(req, actor, parse_local(data.get("scheduled_for")) or timezone.now())
        elif action == "request_execute":
            req_svc.execute_request(req, actor, note=data.get("note", ""))
        elif action == "request_cancel":
            req_svc.cancel_request(req, actor, data.get("reason", ""))
        elif action == "request_submit":
            req_svc.submit_request(req, actor)
    elif action == "document_upload":
        uploaded = request.FILES.get("file")
        if uploaded is None:
            messages.error(request, _("Choose a file."))
            return redirect(back)
        t = Task.objects.filter(call=call, pk=pk_of(data.get("task_id"))).first() if data.get("task_id") else None
        previous = Document.objects.filter(call=call, pk=pk_of(data.get("previous_id"))).first() if data.get("previous_id") else None
        doc_svc.upload_document(call, actor, data.get("type", ""), uploaded, title=data.get("title", ""),
                                confidentiality=data.get("confidentiality", ""),
                                counterpart_role=data.get("counterpart_role", ""), task=t, previous=previous)
        done = _("Document issued and fingerprinted.")
    elif action == "document_sign":
        doc_svc.sign_document(visible_document(), actor, signature_image=data.get("signature_image", ""))
        done = _("Document signed.")
    elif action == "document_cancel":
        doc_svc.cancel_document(visible_document(), actor, data.get("reason", ""))
    elif action == "statement":
        reports.issue_statement_of_facts(call, actor, remarks=data.get("remarks", ""),
                                         remarks_assisted=data.get("remarks_assisted") == "1")
        done = _("Statement of facts generated from the registry and sent for signature.")
        back = call_url(call, "documents")
    elif action == "form_issue":
        doc = form_svc.issue(call, actor, data.get("code", ""))
        done = _("Form %(title)s filed in the call's documents (version %(version)s).") % {
            "title": doc.display_title, "version": doc.version}
        back = call_url(call, "documents")
    elif action == "measurement_open":
        meas_svc.create_measurement(call, actor, data.get("kind", ""), unit=data.get("unit", "MT"))
    elif action == "measurement_value":
        if not rights.measurements_visible(actor):
            raise NotVisible()
        meas_svc.add_value(obj(Measurement, "measurement_id"), actor, data.get("party", ""), data.get("value"),
                           temperature=data.get("temperature_c"), density=data.get("density"), note=data.get("note", ""))
    elif action == "pumping":
        sheet = PumpingLogSheet.objects.filter(call=call, pk=pk_of(data.get("sheet_id"))).first() if data.get("sheet_id") else None
        meas_svc.add_pumping_entry(call, actor, declared_at=parse_local(data.get("declared_at")) or timezone.now(), sheet=sheet,
                                   tank=data.get("tank", ""), level_mm=data.get("level_mm"), hourly_m3=data.get("hourly_m3"),
                                   cumulative_m3=data.get("cumulative_m3"),
                                   manifold_pressure_bar=data.get("pressure_bar"), flow_rate_m3h=data.get("rate_m3h"),
                                   temperature_c=data.get("temperature_c"), note=data.get("note", ""))
        back = call_url(call, "mesures") + "#pompage"
    elif action == "sheet_open":
        figures = {name: data.get(name) for name in meas_svc.SHEET_FIELDS}
        meas_svc.open_pumping_sheet(call, actor, tank=data.get("tank", ""), product=data.get("product", ""),
                                    estimated_start=parse_local(data.get("estimated_start")),
                                    estimated_completion=parse_local(data.get("estimated_completion")),
                                    note=data.get("note", ""), **figures)
        done = _("Pumping log sheet opened: enter your readings as the transfer goes.")
        back = call_url(call, "mesures") + "#pompage"
    elif action == "sheet_close":
        sheet = PumpingLogSheet.objects.filter(call=call, pk=pk_of(data.get("sheet_id"))).first()
        if sheet is None:
            raise NotVisible()
        meas_svc.close_pumping_sheet(sheet, actor, actual_stop_level_mm=data.get("actual_stop_level_mm"),
                                     final_volume_m3=data.get("final_volume_m3"), note=data.get("note", ""))
        done = _("Sheet completed.")
        back = call_url(call, "mesures") + "#pompage"
    elif action == "tank_reading":
        m = obj(Measurement, "measurement_id")
        supersedes = TankReading.objects.filter(measurement=m, pk=pk_of(data.get("supersedes"))).first() if data.get("supersedes") else None
        figures = {name: data.get(name) for name in meas_svc.TANK_FIELDS}
        meas_svc.add_tank_reading(m, actor, tank=data.get("tank", ""), declared_at=parse_local(data.get("declared_at")),
                                  note=data.get("note", ""), supersedes=supersedes, **figures)
        done = _("Tank reading recorded: it is shown to the other parties once the surveyor has validated it.")
        back = call_url(call, "mesures") + f"#q{m.pk}"
    elif action == "tank_review":
        reading = TankReading.objects.filter(measurement__call=call, pk=pk_of(data.get("reading_id"))).first()
        if reading is None or not rights.tank_reading_visible(actor, reading):
            raise NotVisible()
        validate = data.get("decision") == "validate"
        meas_svc.review_tank_reading(reading, actor, validate=validate, note=data.get("note", ""))
        done = _("Reading validated: it is now visible to every reader of the measurements.") if validate else _("Reading rejected: the party is asked for a corrected reading.")
        back = call_url(call, "mesures") + f"#q{reading.measurement_id}"
    elif action == "checklist_open":
        checklist_svc.open_checklist(call, actor, repeat_interval_h=data.get("repeat_interval_h") or None)
        done = _("Ship/shore safety checklist opened.")
        back = reverse("registry:checklist", args=[call.pk])
    elif action == "checklist_answer":
        record = checklist_svc.current(call)
        if record is None:
            raise NotVisible()
        rows = []
        for code in data.getlist("item_code"):
            rows.append({"item_code": code, "state": data.get(f"state_{code}", ""), "value": data.get(f"value_{code}", ""),
                         "remark": data.get(f"remark_{code}", ""), "repetition": data.get("repetition", 0) or 0})
        recorded = checklist_svc.answer_many(record, actor, rows)
        done = _("%(n)d answer(s) recorded.") % {"n": len(recorded)} if recorded else _("Nothing new to record.")
        back = reverse("registry:checklist", args=[call.pk]) + (f"#{data.get('part')}" if data.get("part") else "")
    elif action == "checklist_sign":
        record = checklist_svc.current(call)
        if record is None:
            raise NotVisible()
        checklist_svc.sign(record, actor, comment=data.get("comment", ""))
        done = _("Checklist signed for your side.")
        back = reverse("registry:checklist", args=[call.pk])
    elif action == "checklist_cancel":
        record = checklist_svc.current(call)
        if record is None:
            raise NotVisible()
        checklist_svc.cancel(record, actor, data.get("reason", ""))
        back = reverse("registry:checklist", args=[call.pk])
    elif action == "dispute_open":
        disputes.open_dispute(call, actor, target_kind=data.get("target_kind", "OTHER"), target_id=data.get("target_id") or None,
                              subject=data.get("subject", ""), statement=data.get("statement", ""),
                              counterpart_role=data.get("counterpart_role", ""))
    elif action == "dispute_respond":
        d = call.disputes.filter(pk=pk_of(data.get("dispute_id"))).first()
        if d is None:
            raise NotVisible()
        disputes.respond(d, actor, data.get("text", ""))
    elif action == "dispute_close":
        d = call.disputes.filter(pk=pk_of(data.get("dispute_id"))).first()
        if d is None:
            raise NotVisible()
        disputes.close(d, actor, agreed=data.get("agreed") == "1", text=data.get("text", ""))
    elif action == "thread_create":
        correspondence.create_thread(call, actor, subject=data.get("subject", ""), participant_roles=data.getlist("participants"),
                                     body=data.get("body", ""), confidentiality=data.get("confidentiality", "N2"))
    elif action == "thread_post":
        t = Thread.objects.filter(call=call, pk=pk_of(data.get("thread_id"))).first()
        if t is None:
            raise NotVisible()
        correspondence.post_message(t, actor, data.get("body", ""))
    elif action == "secure_deposit":
        from apps.secure import services as n4

        receipt = n4.deposit(call, actor, kind=data.get("kind", ""), payload={
            "guards": data.get("guards", ""), "company": data.get("company", ""), "embark": data.get("embark", ""),
            "disembark": data.get("disembark", ""), "escort": data.get("escort", ""), "details": data.get("details", "")},
            request=request)
        messages.success(request, _("Filed in the security space. Receipt: %(r)s — keep it: this request will not appear "
                                    "anywhere else in the call.") % {"r": receipt})
        return redirect(call_url(call))
    else:
        raise Http404
    messages.success(request, done)
    return redirect(back)


# ============================================================================ documents, exports, reports
@account_or_master
def document_download(request, pk, doc_id):
    call, actor = resolve(request, pk)
    doc = Document.objects.filter(call=call, pk=doc_id).select_related("type").first()
    if doc is None or not rights.document_visible(actor, doc):
        raise Http404
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="download", obj=doc, request=request)
    # Shown in the browser: PDF and images recognised from their content, and the HTML documents the platform
    # generates itself (statement of facts). A file sent by a party is never rendered as a page of this site.
    html_generated = doc.mime_type == "text/html" and doc.generated
    inline = request.GET.get("inline") == "1" and (doc.mime_type in doc_svc.SNIFFED_TYPES or html_generated)
    response = FileResponse(doc.file.open("rb"), as_attachment=not inline, filename=doc.original_name,
                            content_type=doc.mime_type if inline else "application/octet-stream")
    response["Content-Security-Policy"] = ("sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                                           "form-action 'none'; base-uri 'none'; frame-ancestors 'none'")
    if doc.mime_type == "application/pdf" and inline:
        del response["Content-Security-Policy"]  # the browser's PDF viewer does not run in a sandboxed document
    return response


@login_required
def export_call(request, pk):
    call, actor = resolve(request, pk)
    try:
        payload = exports.export_call(call, actor, request=request)
    except RegistryError as exc:
        messages.error(request, exc.message)
        return redirect(call_url(call))
    response = HttpResponse(payload, content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{call.reference}.zip"'
    return response


@account_or_master
def statement_preview(request, pk):
    call, actor = resolve(request, pk)
    if not rights.can_see_full_call(actor):
        raise Http404
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                  object_kind="statement", request=request)
    response = HttpResponse(reports.render_statement(call))
    return response


@account_or_master
def form_list(request, pk):
    """The standard forms of the call, in one structure: what the registry knows is pre-filled, the rest is left
    to the people who complete and sign the paper (docs/FORMULAIRES.md)."""
    call, actor = resolve(request, pk)
    forms = form_svc.available(call, actor)
    filed = {}
    for doc in rights.visible_documents(actor, call):
        if doc.generated and doc.status in ("ISSUED", "SIGNED"):
            filed.setdefault(doc.title.rsplit(" — ", 1)[0], doc)  # one generated document per form title (the reference last)
    groups = [(code, label, [{"form": f, "filed": filed.get(f"{f.title[0]} / {f.title[1]}")} for f in members])
              for code, label, members in form_svc.grouped(forms)]
    others = form_svc.grouped([f for f in form_svc.for_call(call) if f not in forms])
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                  object_kind="forms", request=request)
    return render(request, "registry/forms.html", {"call": call, "actor": actor, "groups": groups, "count": len(forms),
                                                   "others": others, "others_count": sum(len(m) for _c, _l, m in others),
                                                   # a party without the right to act on the documents previews, but does not file (v1.5)
                                                   "can_issue": rights.can_act_in(actor, call, "documents")})


@account_or_master
def form_preview(request, pk, code):
    call, actor = resolve(request, pk)
    form = form_svc.FORMS.get(code)
    if form is None or form not in form_svc.available(call, actor):
        raise Http404
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                  object_kind=f"form:{code}", request=request)
    return HttpResponse(form_svc.render(call, code, actor))


@account_or_master
def checklist_page(request, pk):
    """The ship/shore safety checklist of the call, completed on line by the ship and the terminal (EXG-Q-10)."""
    call, actor = resolve(request, pk)
    if not checklist_svc.visible(actor, call):
        raise Http404
    record = checklist_svc.current(call)
    journal.audit(port=call.port, call=call, user=actor.user, master=actor.master, action="view", obj=call,
                  object_kind="checklist", request=request)
    can_complete = checklist_svc.can_complete(actor, call) and not call.is_terminal_state
    my_side = "SHIP" if actor.has("NAV") else ("SHORE" if actor.has("TER") else "")
    standard = record.standard if record else checklists.standard_for(call.cargo_kind)  # ISGOTT, BLU or CARGO (v1.5)
    context = {"call": call, "actor": actor, "checklist": record, "can_complete": can_complete, "my_side": my_side,
               "standard": standard, "standard_label": checklists.label(standard), "standard_basis": checklists.basis(standard),
               "form_code": checklists.document_code(standard),
               "parts": checklist_svc.rows(record, actor) if record else [],
               "progress": checklist_svc.progress(record) if record else None,
               "signed_sides": record.signed_sides() if record else set(),
               "can_cancel": actor.has("AGE", "CAP") and record is not None and record.status == "OPEN",
               "versions": list(call.safety_checklists.order_by("version")), "now": timezone.now(),
               "refusal": enrich_refusal(pop_refusal(request), call, actor), "is_master": actor.is_master,
               "next_repetition": (checklist_svc._last_repetition(record, my_side) + 1) if record and my_side else 1,
               "task": call.tasks.filter(template_code="M0", number="28").first()}
    return render(request, "registry/checklist.html", context)


@login_required
def board(request):
    """The port call board: every declared call of the port, for consultation by the agencies, the other parties of
    the port and the interested parties (EXG-Q-04); no operational data of another agency's call (EXG-Q-03)."""
    user = request.user
    if user.port is None:
        raise Http404
    actor = port_actor(user)
    if not rights.can_read_report(actor, "CALL_BOARD"):
        raise Http404
    journal.audit(port=user.port, user=user, action="view", object_kind="board", request=request)
    now = timezone.now()
    if request.GET.get("format") == "csv":
        response = HttpResponse(board_svc.to_csv(user.port, user, now), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="conference-placement-{user.port.code}-{now:%Y%m%d}.csv"'
        return response
    groups = board_svc.grouped(user.port, user, now)
    return render(request, "registry/board.html", {"groups": groups, "now": now, "port": user.port, "show_cargo": user.port.board_shows_cargo,
                                                   "total": sum(len(rows) for _k, _l, rows in groups)})


@login_required
def board_occupation(request):
    """The berth occupation plan of a period (v1.5, EXG-R-07): the calls per berth, as the terminals' own sheets."""
    user = request.user
    if user.port is None:
        raise Http404
    actor = port_actor(user)
    if not rights.can_read_report(actor, "CALL_BOARD"):
        raise Http404
    journal.audit(port=user.port, user=user, action="view", object_kind="board", detail="occupation", request=request)
    now = timezone.now()
    try:
        start = datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").replace(tzinfo=dt_timezone.utc)
    except ValueError:
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    try:
        end = datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").replace(hour=23, minute=59, tzinfo=dt_timezone.utc)
    except ValueError:
        end = (start + timedelta(days=45)).replace(day=1) - timedelta(minutes=1)
    if request.GET.get("format") == "csv":
        response = HttpResponse(board_svc.occupation_csv(user.port, user, start, end), content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="plan-occupation-{user.port.code}-{start:%Y%m}.csv"'
        return response
    plan = board_svc.occupation(user.port, user, start, end)
    return render(request, "registry/board_occupation.html", {"plan": plan, "start": start, "end": end, "port": user.port,
                                                              "show_cargo": user.port.board_shows_cargo})


@login_required
def notifications(request):
    notes = request.user.notifications.order_by("-created_at")[:200]
    if request.method == "POST":
        request.user.notifications.filter(read_at__isnull=True).update(read_at=timezone.now())
        return redirect("registry:notifications")
    return render(request, "registry/notifications.html", {"notes": notes})


# ============================================================================ master (account-less) and public verification
def master_entry(request):
    if request.method == "POST":
        address = throttle.client_ip(request)
        if throttle.blocked("master-ip", address):  # access codes are short: guessing must stay out of reach
            messages.error(request, _("Too many unsuccessful attempts. Wait up to fifteen minutes before trying again."))
            return render(request, "registry/master_entry.html", status=429)
        link = call_svc.authenticate_master(code=request.POST.get("code", ""), request=request)
        if link is None:
            throttle.failure("master-ip", address)
            messages.error(request, _("This code is not valid, has expired or was revoked. Ask your agent for a new access."))
            return render(request, "registry/master_entry.html")
        request.session.cycle_key()
        request.session[MASTER_SESSION_KEY] = link.pk
        if not link.master_name:
            return redirect("registry:link_name")
        return redirect(call_url(link.call))
    return render(request, "registry/master_entry.html")


def master_token(request, token):
    link = call_svc.authenticate_master(token=token, request=request)
    if link is None:
        messages.error(request, _("This link is not valid, has expired or was revoked. Ask your agent for a new access."))
        return redirect("registry:master_entry")
    request.session.cycle_key()
    request.session[MASTER_SESSION_KEY] = link.pk
    if not link.master_name:
        return redirect("registry:link_name")
    return redirect(call_url(link.call))


def link_name(request):
    """A party's access link issued by the platform carries no name yet: the holder gives theirs before any act,
    so that every entry, signature and countersignature stays nominative (EF-13)."""
    link = master_from_session(request)
    if link is None:
        return redirect("registry:master_entry")
    if link.master_name:
        return redirect(call_url(link.call))
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()[:160]
        if len(name) < 3:
            messages.error(request, _("Enter your full name."))
        else:
            link.master_name = name
            link.save(update_fields=["master_name"])
            journal.audit(port=link.call.port, call=link.call, master=link, action="link.named", obj=link,
                          object_kind="link", detail=name, request=request)
            return redirect(call_url(link.call))
    return render(request, "registry/link_name.html", {"link": link, "role": role_label(link.role)})


@require_POST
def master_logout(request):
    request.session.pop(MASTER_SESSION_KEY, None)
    response = redirect(f"{reverse('registry:master_entry')}?sortie=1")
    response["Clear-Site-Data"] = '"cache"'
    return response


def verify(request, code=None):
    code = code or request.GET.get("code", "").strip()
    info = req_svc.verify_authorization(code) if code else None
    return render(request, "registry/verify.html", {"code": code, "info": info, "searched": bool(code)})


# ============================================================================ field app (PWA)
@account_or_master
def field_app(request, pk):
    call, actor = resolve(request, pk)
    return render(request, "registry/field.html", {"call": call, "actor": actor})


def manifest(request):
    return JsonResponse({
        "name": "FLUXAA Port — terrain", "short_name": "FLUXAA", "start_url": "/escales/", "display": "standalone",
        "background_color": "#F1F5F7", "theme_color": "#2A2A2A", "lang": get_language() or "fr",
        "icons": [{"src": "/static/img/favicon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"}],
    }, content_type="application/manifest+json")


def service_worker(request):
    from django.contrib.staticfiles import finders

    path = finders.find("js/sw.js")
    if not path:
        raise Http404
    with open(path, "rb") as handle:
        response = HttpResponse(handle.read(), content_type="application/javascript")
    response["Service-Worker-Allowed"] = "/"
    response["Cache-Control"] = "no-cache"
    return response
