"""A call with several stages: lightering at the STS area, then discharge of the remainder at the quay."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.registry.models import CallStage, CallStatus, RequestStatus
from apps.registry.services import calls as call_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import reports, stages
from apps.registry.services import requests as req_svc
from apps.registry.services.errors import HoldPointRefused, PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call, master
from .test_web import login


def now(minutes=0):
    return timezone.now() + timedelta(minutes=minutes)


def decide(world, call, code, requester, decider, data, **extra):
    req = req_svc.create_request(call, act(world, call, requester), code, data)
    return req_svc.decide_request(req, act(world, call, decider), RequestStatus.APPROVED, **extra)


@pytest.mark.django_db(databases=["default", "secure"])
def test_offshore_then_quay_in_one_call(world, client):
    port = world.port
    sts_parties = [(world.orgs.waste, "PRE"), (world.orgs.surveyor, "INS"), (world.orgs.owner, "COM"),
                   (world.orgs.terminal, "TER")]
    partner = make_call(world, kind="STS_AREA", operations=("M3",), parties=sts_parties)
    call = make_call(world, kind="STS_AREA", operations=("M3",), parties=sts_parties, linked_call=partner, link_kind="STS")
    # born with its first stage
    first = call.stages.get()
    assert first.order == 1 and first.status == CallStage.Status.CURRENT and first.berth_kind == "STS_AREA"
    assert "M3" in first.operations and "MA3" in first.operations
    assert not call.tasks.filter(template_code="M1").exists()

    # the agency plans the second stage at the quay: discharge (M1) — tasks created at once, for everyone
    age = act(world, call, "AGE")
    with pytest.raises(RuleViolation):
        stages.add_stage(call, age, berth_kind="JETTY", operations=["M3"])  # STS does not apply alongside
    with pytest.raises(PermissionRefused):
        stages.add_stage(call, act(world, call, "TER"), berth_kind="JETTY", operations=["M1"])
    second = stages.add_stage(call, age, berth_kind="JETTY", operations=["M1"], planned_from=now(60 * 30),
                              reason="discharge of the remainder at the quay")
    assert second.order == 2 and second.status == CallStage.Status.PLANNED and second.operations == ["M1"]
    assert call.tasks.filter(template_code="M1").exists() and "M1" in call.template_codes
    assert call.tasks.filter(template_code="M1", number="1.04").exists()
    # a shift cannot be recorded before the next stage is planned… but now it is; it still needs a movement
    # authorization in force, like the pilot's boarding
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, age)
    decide(world, call, "VESSEL_ACCEPTANCE", "TER", "CAP", {"product": "Crude", "inspection": "SIRE", "last_cargoes": "x",
                                                            "vetting_result": "ok"}, valid_until=now(60 * 24 * 30))
    req_svc.decide_request(call.requests.get(type__code="GREEN_LIGHT"), act(world, call, "CAP"), RequestStatus.APPROVED)
    sts_area = port.berths.filter(kind="STS_AREA").first()
    jetty = port.berths.filter(kind="JETTY").first()
    decide(world, call, "BERTH", "AGE", "APO", {"window_from": now(60).isoformat(), "arrival_draft": 12.0}, berth=sts_area)
    call.refresh_from_db()
    assert call.berth == sts_area and call.stages.get(order=1).berth == sts_area
    # the berth of the quay stage goes to that stage, not to the call (the vessel is still offshore)
    decide(world, call, "BERTH", "AGE", "APO", {"window_from": now(60 * 30).isoformat(), "arrival_draft": 11.0}, berth=jetty)
    call.refresh_from_db()
    second.refresh_from_db()
    assert call.berth == sts_area and second.berth == jetty

    nav = master(world, call)
    svc = act(world, call, "SVC")
    decide(world, call, "FREE_PRATIQUE", "AGE", "ADM", {"crew": 22}, valid_from=now(-200), valid_until=now(60 * 48))
    decide(world, call, "CUSTOMS_IMMIGRATION", "AGE", "ADM", {"crew_list": True}, valid_from=now(-200), valid_until=now(60 * 48))
    decide(world, call, "MOVEMENT", "AGE", "CAP", {"movement": "ARRIVAL", "requested_time": now().isoformat()},
           valid_from=now(-180), valid_until=now(-60))  # covers the arrival only
    ms_svc.record_milestone(call, nav, "ARRIVAL", now(-150))
    force_done(call, ["M3:3.03"])
    poac = act(world, call, "PRE")
    ms_svc.record_milestone(call, poac, "STS_ALONGSIDE", now(-120))
    call.refresh_from_db()
    assert call.status == CallStatus.AT_BERTH and call.atb is not None
    assert call.stages.get(order=1).atb is not None
    force_done(call, [f"M3:3.{n:02d}" for n in range(1, 12)])
    ms_svc.record_milestone(call, poac, "STS_TRANSFER_START", now(-100))
    ms_svc.record_milestone(call, poac, "STS_TRANSFER_END", now(-40))
    call.refresh_from_db()
    assert call.status == CallStatus.OPS_COMPLETE and call.t0 is not None and call.t1 is not None
    first_t0, first_t1 = call.t0, call.t1

    # leaving the STS area: a shift authorization in force at the time, then the milestone by the marine services
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, svc, "SHIFT_START", now(-30))  # the arrival authorization has lapsed by then
    decide(world, call, "MOVEMENT", "AGE", "CAP", {"movement": "SHIFT", "requested_time": now(-30).isoformat()},
           valid_from=now(-35), valid_until=now(60 * 12))
    shift = ms_svc.record_milestone(call, svc, "SHIFT_START", now(-30))
    call.refresh_from_db()
    assert call.status == CallStatus.SHIFTING and shift.stage.order == 1
    done_stage, current = call.stages.get(order=1), stages.current(call)
    assert done_stage.status == CallStage.Status.DONE and done_stage.atd == shift.declared_at
    assert current.order == 2 and call.berth == jetty and call.requested_berth_kind == "JETTY"

    # berthing at the quay: the usual milestones, scoped to the second stage (a second "all fast" is no conflict)
    ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_ARR", now(-25))
    ms_svc.record_milestone(call, svc, "FIRST_LINE", now(-20))
    all_fast = ms_svc.record_milestone(call, svc, "ALL_FAST", now(-15))
    call.refresh_from_db()
    assert not all_fast.is_conflict and all_fast.stage == current
    assert call.status == CallStatus.AT_BERTH and call.atb == call.stages.get(order=1).atb  # first berthing stays
    assert call.stages.get(order=2).atb == all_fast.declared_at
    ter = act(world, call, "TER")
    force_done(call, ["M0:09c", "M0:27", "M0:28", "M0:29", "M0:31", "M1:1.04", "M1:1.05", "M1:1.06", "M1:1.07"])
    ms_svc.record_milestone(call, ter, "HOSES_CONNECTED", now(-12))
    start = ms_svc.record_milestone(call, ter, "TRANSFER_START", now(-10))
    end = ms_svc.record_milestone(call, ter, "TRANSFER_END", now(-2))
    call.refresh_from_db()
    assert not start.is_conflict and not end.is_conflict
    assert call.status == CallStatus.OPS_COMPLETE
    assert call.t0 == first_t0 and call.t1 == end.declared_at and call.t1 != first_t1  # first start, last end

    # the statement of facts shows the stages and tags each milestone with its stage
    html = reports.render_statement(call)
    assert "Stages of the call" in html and "SHIFT" in html.upper()
    # a third stage can still be planned, but not after departure; planned stages can be cancelled, never deleted
    third = stages.add_stage(call, act(world, call, "CAP"), berth_kind="ANCHORAGE", operations=["M6"], reason="wait for tide")
    assert third.status == CallStage.Status.PLANNED and call.tasks.filter(template_code="M6").exists()
    stages.cancel_stage(call, age, third, "not needed")
    third.refresh_from_db()
    assert third.status == CallStage.Status.CANCELLED and call.stages.count() == 3
    with pytest.raises(RuleViolation):
        ms_svc.record_milestone(call, svc, "SHIFT_START", now(-1))  # nothing planned any more
    # the web overview and the API show the stages
    login(client, world, "AGE")
    page = client.get(f"/escales/{call.pk}/")
    assert page.status_code == 200 and b"Stages of the call" in page.content or "tapes de l" in page.content.decode()
    from rest_framework.authtoken.models import Token

    token = Token.objects.create(user=world.users["AGE"]).key
    data = client.get(f"/api/v1/calls/{call.reference}/stages/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["results"]
    assert [s["order"] for s in data] == [1, 2, 3] and data[0]["status"] == "DONE" and data[1]["berth"] == jetty.code
