"""AIS board: ingestion, NMEA decoding, projection, discrepancies, visibility, purge and the API."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.ais import nmea, services
from apps.ais.models import VesselPosition, VesselStatic
from apps.core.models import User
from apps.registry.models import CallStatus
from apps.registry.services import calls as call_svc
from apps.registry.services import milestones as ms_svc

from .conftest import act, force_done, make_call, master
from .test_web import login

SAMPLE_NMEA = "!AIVDM,1,1,,A,13aEOK?P00PD2wVMdLDRhgvL289?,0*26"  # type 1 position report, MMSI 244670316


def give_map(port):
    port.map_lat_min, port.map_lat_max = Decimal("8.35"), Decimal("8.58")
    port.map_lon_min, port.map_lon_max = Decimal("-13.55"), Decimal("-13.12")
    port.save()
    jetty = port.berths.filter(kind="JETTY").first()
    jetty.latitude, jetty.longitude = Decimal("8.4950"), Decimal("-13.2200")
    jetty.save()
    anchorage = port.berths.filter(kind="ANCHORAGE").first()
    anchorage.latitude, anchorage.longitude, anchorage.radius_m = Decimal("8.4400"), Decimal("-13.3000"), 1500
    anchorage.save()
    return jetty, anchorage


@pytest.mark.django_db
def test_ingest_normalises_deduplicates_and_rejects(world):
    port = world.port
    at = timezone.now() - timedelta(minutes=5)
    reports = [
        {"mmsi": "636099993", "lat": "8.4951", "lon": "-13.2201", "observed_at": at.isoformat(), "speed_kn": 0.1,
         "course_deg": 95.0, "heading_deg": 511, "nav_status": 5, "name": " MT TEST SPIRIT ", "imo": "9999993"},
        {"mmsi": "636099993", "lat": "8.4951", "lon": "-13.2201", "observed_at": at.isoformat()},  # same instant twice
        {"mmsi": "", "lat": "8.4", "lon": "-13.3"},                                                   # no MMSI
        {"mmsi": "123456789", "lat": "95", "lon": "-13.3"},                                           # off the globe
        {"mmsi": "123456789", "lat": "91.0", "lon": "181"},
    ]
    counts = services.ingest(port, reports, source="test")
    assert counts["stored"] == 1 and counts["duplicates"] == 1 and counts["rejected"] == 3
    position = VesselPosition.objects.get(port=port, mmsi="636099993")
    assert position.heading_deg is None  # 511 = not available
    assert position.nav_status == 5 and position.source == "test"
    static = VesselStatic.objects.get(port=port, mmsi="636099993")
    assert static.name == "MT TEST SPIRIT" and static.imo == "9999993"


@pytest.mark.django_db
def test_nmea_sentence_is_decoded_to_a_report():
    reports = nmea.decode_sentences([SAMPLE_NMEA, "garbage,not,a,sentence", ""])
    assert len(reports) == 1
    report = reports[0]
    assert report["mmsi"] == "244670316"
    assert 51.0 < float(report["lat"]) < 53.0 and 3.0 < float(report["lon"]) < 5.0  # Dutch coast
    assert report["observed_at"] is not None


@pytest.mark.django_db
def test_board_projects_matches_calls_and_flags_discrepancies(world):
    port = world.port
    jetty, anchorage = give_map(port)
    assert port.has_map
    world.vessel.mmsi = "636099993"
    world.vessel.save()
    call = make_call(world, eta=timezone.now() - timedelta(hours=2))
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    now = timezone.now()
    services.ingest(port, [
        # the expected vessel is heard moored at the anchorage, no arrival recorded yet
        {"mmsi": "636099993", "lat": "8.4405", "lon": "-13.3010", "observed_at": (now - timedelta(minutes=3)).isoformat(),
         "speed_kn": 0.2, "nav_status": 1},
        # a vessel of another port's business, passing by inside the box
        {"mmsi": "999000001", "lat": "8.40", "lon": "-13.20", "observed_at": (now - timedelta(minutes=10)).isoformat(),
         "speed_kn": 11.5, "course_deg": 250, "name": "MT TRANSIT"},
        # outside the box: listed, not drawn
        {"mmsi": "999000002", "lat": "7.90", "lon": "-13.90", "observed_at": (now - timedelta(minutes=10)).isoformat()},
        # too old for the board
        {"mmsi": "999000003", "lat": "8.45", "lon": "-13.30", "observed_at": (now - timedelta(hours=30)).isoformat()},
    ], source="test")
    data = services.board(port, now=now)
    assert data["box"]["width"] == services.BOARD_WIDTH and 240 <= data["box"]["height"] <= 1600
    names = {v["mmsi"]: v for v in data["vessels"]}
    assert set(names) == {"636099993", "999000001", "999000002"}
    assert names["636099993"]["inside"] and names["999000001"]["inside"] and not names["999000002"]["inside"]
    assert names["636099993"]["call"] == call and names["636099993"]["klass"] == "expected"
    assert names["999000001"]["call"] is None and names["999000001"]["klass"] == "none"
    assert data["on_board"] == 2 and data["with_call"] == 1
    # the berths are drawn where they are, the anchorage with its radius in board units
    drawn = {b["berth"].code: b for b in data["berths"]}
    assert drawn[jetty.code]["r"] == 0 and drawn[anchorage.code]["r"] > 0
    x, y, inside = services.project(data["box"], 8.4950, -13.2200)
    assert inside and abs(x - drawn[jetty.code]["x"]) < 0.01 and abs(y - drawn[jetty.code]["y"]) < 0.01
    # a vessel of an expected call heard moored inside the box, without ARRIVAL: a discrepancy, not a milestone
    kinds = {d["kind"] for d in data["discrepancies"]}
    assert kinds == {"arrived_undeclared"} and call.milestones.count() == 0
    assert names["636099993"]["position_text"] == "08°26.43' N 013°18.06' W"
    # once the master records the arrival, the discrepancy disappears
    ms_svc.record_milestone(call, master(world, call), "ARRIVAL", now - timedelta(minutes=30))
    data = services.board(port, now=now)
    assert data["discrepancies"] == []
    # JSON for the API: no model instance, references only
    payload = json.loads(json.dumps(services.positions_json(data)))
    assert payload["vessels"][0]["call"] == call.reference and payload["discrepancies"] == []


@pytest.mark.django_db
def test_departed_vessel_still_moored_is_a_discrepancy(world):
    port = world.port
    give_map(port)
    world.vessel.mmsi = "636099993"
    world.vessel.save()
    call = make_call(world, eta=timezone.now() - timedelta(days=2))
    now = timezone.now()
    from apps.registry.models import PortCall

    PortCall.objects.filter(pk=call.pk).update(status=CallStatus.DEPARTED, atd=now - timedelta(hours=3))
    services.ingest(port, [{"mmsi": "636099993", "lat": "8.4951", "lon": "-13.2201", "speed_kn": 0.0,
                            "observed_at": (now - timedelta(minutes=5)).isoformat()}], source="test")
    data = services.board(port, now=now)
    assert [d["kind"] for d in data["discrepancies"]] == ["still_here"]
    assert data["vessels"][0]["klass"] == "departed"


@pytest.mark.django_db
def test_board_shows_only_the_calls_the_viewer_may_open(world):
    """The terminal is a party of call A only: next to the vessel it sees call A, not the agency's other call."""
    port = world.port
    give_map(port)
    world.vessel.mmsi = "636099993"
    world.vessel.save()
    other = make_call(world, parties=[(world.orgs.owner, "COM")])  # no terminal on this one
    force_done(other, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(other, act(world, other, "AGE"))
    services.ingest(port, [{"mmsi": "636099993", "lat": "8.4951", "lon": "-13.2201"}], source="test")
    from apps.registry.services import rights

    visible = rights.call_queryset_for_user(world.users["TER"])
    data = services.board(port, visible_calls=visible)
    assert data["vessels"][0]["call"] is None  # the terminal is not a party: the call is not named
    data = services.board(port, visible_calls=rights.call_queryset_for_user(world.users["CAP"]))
    assert data["vessels"][0]["call"] == other


@pytest.mark.django_db
def test_purge_keeps_the_retention_of_the_port(world):
    port = world.port
    port.ais_retention_days = 10
    port.save()
    now = timezone.now()
    services.ingest(port, [
        {"mmsi": "636099993", "lat": "8.4", "lon": "-13.3", "observed_at": (now - timedelta(days=11)).isoformat()},
        {"mmsi": "636099993", "lat": "8.4", "lon": "-13.3", "observed_at": (now - timedelta(days=2)).isoformat()},
    ], source="test")
    assert services.purge(now) == 1
    assert VesselPosition.objects.filter(port=port).count() == 1


@pytest.mark.django_db(databases=["default", "secure"])
def test_board_page_and_api(client, world):
    port = world.port
    give_map(port)
    services.ingest(port, [{"mmsi": "636099993", "lat": "8.4951", "lon": "-13.2201", "name": "MT TEST SPIRIT"}], source="test")
    login(client, world, "CAP")
    response = client.get("/carte/")
    assert response.status_code == 200
    html = response.content.decode()
    assert "<svg" in html and "MT TEST SPIRIT" in html and "viewBox=\"0 0 1000 " in html
    assert "879,9" not in html  # SVG numbers are never localised
    assert client.get("/carte/", HTTP_HX_REQUEST="true").status_code == 200
    # the master's access has no board: the nav bar and the page are for the port's parties
    client.logout()
    assert client.get("/carte/").status_code in (302, 403)
    # API: an integration account of scope 'ais' posts, everyone of the port reads
    feed = User.objects.create_user(email="ais@integration.test", password="pw-test-123456", full_name="AIS feed",
                                    organization=world.orgs.authority, roles=[], is_integration=True,
                                    integration_scopes=["ais"])
    token = Token.objects.create(user=feed).key
    response = client.post("/api/v1/ais/positions/", data=json.dumps({"reports": [
        {"mmsi": "999000001", "lat": 8.40, "lon": -13.20, "speed_kn": 11.5, "name": "MT TRANSIT"}]}),
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200 and response.json()["stored"] == 1
    reader = Token.objects.create(user=world.users["TER"]).key
    response = client.post("/api/v1/ais/positions/", data=json.dumps({"reports": []}), content_type="application/json",
                           HTTP_AUTHORIZATION=f"Bearer {reader}")
    assert response.status_code == 403  # a party of the port cannot feed the board
    response = client.get("/api/v1/ais/positions/", HTTP_AUTHORIZATION=f"Bearer {reader}")
    assert response.status_code == 200
    assert {v["mmsi"] for v in response.json()["vessels"]} == {"636099993", "999000001"}
