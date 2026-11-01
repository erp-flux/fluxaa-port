"""Statistics of the port: computed from the registry, visible to the management roles, exportable."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import CallStatus, PortCall, RequestStatus
from apps.registry.services import calls as call_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import requests as req_svc
from apps.registry.services import stats
from apps.registry.services.context import actor_for_call

from .conftest import act, force_done, make_call
from .test_web import login


def past_calls(world):
    now = timezone.now()
    first = make_call(world, eta=now - timedelta(days=40))
    second = make_call(world, eta=now - timedelta(days=10))
    PortCall.objects.filter(pk=second.pk).update(quantity=20000, product="Jet A-1")
    second.refresh_from_db()
    for call in (first, second):
        force_done(call, ["M0:02", "M0:03", "M0:05"])
        call_svc.declare_call(call, act(world, call, "AGE"))
    # the first call went through: an interruption during the transfer, then arrival, berthing, departure, closed
    eta = first.eta
    ter = act(world, first, "TER")
    link, _token, _code = call_svc.issue_master_link(first, act(world, first, "AGE"), master_name="Capt. Test",
                                                     expires_at=now + timedelta(days=1))
    nav = actor_for_call(first, master=link)
    stop = ms_svc.record_milestone(first, ter, "INTERRUPTION_START", eta + timedelta(hours=20), cause_code="SHORE_TANK_SWITCH")
    ms_svc.record_milestone(first, ter, "INTERRUPTION_END", eta + timedelta(hours=21, minutes=30), related=stop)
    ms_svc.countersign_milestone(stop, nav)  # established contradictorily
    PortCall.objects.filter(pk=first.pk).update(status=CallStatus.CLOSED, ata=eta, atb=eta + timedelta(hours=10),
                                                atd=eta + timedelta(hours=40), berth=world.port.berths.filter(kind="JETTY").first())
    first.refresh_from_db()
    # one decision on the second call, 6 h after submission
    vet = req_svc.create_request(second, act(world, second, "TER"), "VESSEL_ACCEPTANCE", {
        "product": "Jet A-1", "inspection": "SIRE", "last_cargoes": "x", "vetting_result": "ok"})
    req_svc.decide_request(vet, act(world, second, "CAP"), RequestStatus.APPROVED)
    vet.refresh_from_db()
    second.requests.filter(pk=vet.pk).update(submitted_at=vet.decided_at - timedelta(hours=6))
    return first, second


@pytest.mark.django_db
def test_compute_counts_what_the_registry_holds(world):
    first, second = past_calls(world)
    start, end = stats.period(None, None, days=365)
    data = stats.compute(world.port, start, end)
    assert data["totals"]["calls"] == 2 and data["totals"]["completed"] == 1 and data["totals"]["cancelled"] == 0
    assert data["totals"]["quantity_mt"] == 50000.0
    assert data["totals"]["waiting_h"] == 10.0 and data["totals"]["stay_h"] == 40.0
    assert sum(m["calls"] for m in data["monthly"]) == 2 and len(data["months"]) in (12, 13)
    assert dict(data["operations"]) and sum(dict(data["operations"]).values()) == 2
    assert dict(data["products"]) == {"Gasoil": 30000.0, "Jet A-1": 20000.0}
    jetty = next(b for b in data["berths"] if b["berth"].kind == "JETTY")
    assert jetty["calls"] == 1 and jetty["hours"] == 30.0 and 0 < jetty["rate_pct"] < 1
    assert data["totals"]["interruptions"] == 1 and data["totals"]["interruption_hours"] == 1.5
    assert data["totals"]["established_pct"] == 100.0
    assert data["causes"][0]["attribution"] == "SHORE" and data["causes"][0]["count"] == 1
    decision = next(d for d in data["decisions"] if "etting" in d["type"] or "vetting" in d["type"].lower())
    assert decision["count"] == 1 and decision["avg_h"] == 6.0 and decision["roles"] == "CAP"
    assert data["countersign"]["countersigned"] == 1 and data["countersign"]["contested"] == 0
    assert data["disputes"]["opened"] == 0
    assert data["totals"]["milestones"] == 2 and data["sources"].get("ONLINE") == 2
    # the period filter: nothing before the calls
    old_start, old_end = stats.period((timezone.now() - timedelta(days=400)).date(), (timezone.now() - timedelta(days=300)).date())
    assert stats.compute(world.port, old_start, old_end)["totals"]["calls"] == 0
    csv_text = stats.to_csv(data)
    assert "month;calls;completed" in csv_text and "Jet A-1;20000.0" in csv_text and "SHORE" in csv_text


@pytest.mark.django_db
def test_bar_chart_geometry():
    chart = stats.bar_chart([("01/26", 2), ("02/26", None), ("03/26", 4)])
    assert len(chart["bars"]) == 3 and chart["bars"][1]["value"] is None and chart["bars"][1]["h"] == 0
    assert chart["bars"][2]["h"] > chart["bars"][0]["h"] > 0
    assert [g["value"] for g in chart["grid"]] == ["1", "2", "3", "4"]  # small counts: one line per unit
    assert stats.bar_chart([])["bars"] == [] and stats.bar_chart([("a", None)])["grid"] == []


@pytest.mark.django_db(databases=["default", "secure"])
def test_statistics_page_roles_and_export(client, world):
    past_calls(world)
    login(client, world, "DIR")
    response = client.get("/statistiques/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "<svg" in html and "Jet A-1" in html and "130,7" not in html
    response = client.get("/statistiques/?from=2020-01-01&to=2020-12-31")
    assert response.status_code == 200
    response = client.get("/statistiques/?format=csv")
    assert response.status_code == 200 and response["Content-Type"].startswith("text/csv")
    assert "month;calls" in response.content.decode()
    # not for the parties of a call, nor for the master's access
    for role in ("TER", "AGE", "INS"):
        client.logout()
        login(client, world, role)
        assert client.get("/statistiques/").status_code == 404, role
    client.logout()
    login(client, world, "CAP")
    assert client.get("/statistiques/").status_code == 200
