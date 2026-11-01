"""The eight business acceptance scenarios of FLX-CDC-001 §6.

"A scenario partially satisfied is a failed scenario": each test asserts every expected outcome.
"""
from __future__ import annotations

import io
import json
import time
import uuid
import zipfile
from datetime import timedelta

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from apps.registry.models import (
    Alert,
    CallStatus,
    CountersignState,
    Dispute,
    DocumentStatus,
    JournalEntry,
    Measurement,
    Milestone,
    Notification,
    RequestStatus,
    TaskStatus,
)
from apps.registry.services import calls as call_svc
from apps.registry.services import documents as doc_svc
from apps.registry.services import journal, reports, rights
from apps.registry.services import measurements as meas_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import requests as req_svc
from apps.registry.services import tasks as task_svc
from apps.registry.services.errors import HoldPointRefused, LockRefused, NotVisible
from apps.registry.services.exports import call_payload, export_call
from apps.registry.services.sync import process_batch

from .conftest import act, force_done, make_call, master
from .conftest import sys as system_actor_for


def upload(name="file.pdf", content=b"%PDF-1.4 test"):
    return ContentFile(content, name=name)


def task(call, code):
    template_code, number = code.split(":")
    return call.tasks.get(template_code=template_code, number=number)


def request_and_decide(world, call, code, requester, decider, data=None, **decision):
    req = req_svc.create_request(call, act(world, call, requester), code, data or {})
    req_svc.decide_request(req, act(world, call, decider), decision.pop("decision", RequestStatus.APPROVED), **decision)
    req.refresh_from_db()
    return req


def now(minutes=0):
    return timezone.now() + timedelta(minutes=minutes)


# ======================================================================================== S1
@pytest.mark.django_db(databases=["default", "secure"])
def test_s1_nominal_discharge_call(world):
    call = make_call(world)
    port = world.port
    assert call.reference.startswith("SLFNA-")
    assert call.tasks.filter(template_code="M0").count() > 30 and call.tasks.filter(template_code="M1").exists()
    assert task(call, "M0:01").status == TaskStatus.DONE  # created by the agency

    age = act(world, call, "AGE")
    doc_svc.upload_document(call, age, "Q88", upload("q88.pdf"))
    nav = master(world, call)
    doc_svc.upload_document(call, nav, "CERTIFICATES", upload("certs.pdf"))
    task_svc.complete_task(task(call, "M0:05"), age, note="screened")
    call_svc.declare_call(call, age)
    call.refresh_from_db()
    assert call.status == CallStatus.DECLARED

    # vetting circuit: depot → port
    vet = req_svc.create_request(call, act(world, call, "TER"), "VESSEL_ACCEPTANCE", {
        "product": "Gasoil", "inspection": "SIRE 2.0 — 2026-08-01, no open observation",
        "last_cargoes": "ULSD / ULSD / Jet A-1", "vetting_result": "Accepted"})
    req_svc.decide_request(vet, act(world, call, "CAP"), RequestStatus.APPROVED, valid_until=now(60 * 24 * 30))
    green = call.requests.get(type__code="GREEN_LIGHT")
    req_svc.decide_request(green, act(world, call, "CAP"), RequestStatus.APPROVED)
    call.refresh_from_db()
    assert call.status == CallStatus.ACCEPTED

    berth = port.berths.get(code="KISSY-JETTY")
    request_and_decide(world, call, "BERTH", "AGE", "APO",
                       {"window_from": now(60).isoformat(), "arrival_draft": 11.2}, berth=berth)
    call.refresh_from_db()
    assert call.status == CallStatus.PLANNED and call.berth == berth

    request_and_decide(world, call, "FREE_PRATIQUE", "AGE", "ADM", {"crew": 22})
    request_and_decide(world, call, "CUSTOMS_IMMIGRATION", "AGE", "ADM", {"crew_list": True})
    # authorizations in force from before the times at which the milestones below are declared
    request_and_decide(world, call, "MOVEMENT", "AGE", "CAP", {"movement": "ARRIVAL", "requested_time": now().isoformat()},
                       valid_from=now(-120))
    pilots = req_svc.create_request(call, age, "MARINE_SERVICES", {"movement": "ARRIVAL", "requested_time": now().isoformat()})
    req_svc.schedule_request(pilots, act(world, call, "SVC"), now(30))
    assert task(call, "M0:18").status == TaskStatus.DONE

    ms_svc.record_milestone(call, nav, "ARRIVAL", now(-60))
    call.refresh_from_db()
    assert call.status == CallStatus.APPROACHING
    nor = ms_svc.record_milestone(call, age, "NOR_TENDERED", now(-55))
    ms_svc.countersign_milestone(nor, act(world, call, "TER"))
    ms_svc.countersign_milestone(nor, act(world, call, "COM"))
    assert task(call, "M0:24").status == TaskStatus.DONE

    svc = act(world, call, "SVC")
    ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_ARR", now(-50))
    ms_svc.record_milestone(call, svc, "FIRST_LINE", now(-40))
    ms_svc.record_milestone(call, svc, "ALL_FAST", now(-35))
    ms_svc.record_milestone(call, nav, "GANGWAY", now(-34))
    call.refresh_from_db()
    assert call.status == CallStatus.AT_BERTH and task(call, "M0:26").status == TaskStatus.DONE

    ter = act(world, call, "TER")
    for code in ("M0:27", "M0:28"):
        task_svc.sign_task(task(call, code), ter)
        task_svc.sign_task(task(call, code), nav)
        assert task(call, code).status == TaskStatus.DONE
    assert call.milestones.filter(type__code="SSSCL_SIGNED").exists()
    ms_svc.record_milestone(call, ter, "ESD_TEST", now(-30))
    task_svc.complete_task(task(call, "M0:31"), ter)
    task_svc.complete_task(task(call, "M1:1.04"), nav)
    ins = act(world, call, "INS")
    ms_svc.record_milestone(call, ins, "INITIAL_GAUGING", now(-28))
    task_svc.complete_task(task(call, "M1:1.06"), ter)
    task_svc.complete_task(task(call, "M1:1.07"), ins)
    ms_svc.record_milestone(call, ter, "HOSES_CONNECTED", now(-27))
    ms_svc.record_milestone(call, ter, "TRANSFER_START", now(-26))
    ms_svc.record_milestone(call, ter, "FULL_RATE", now(-25))
    call.refresh_from_db()
    assert call.status == CallStatus.IN_OPERATION and task(call, "M1:1.10").status == TaskStatus.DONE

    meas_svc.add_pumping_entry(call, ter, declared_at=now(-24), manifold_pressure_bar=6.5, flow_rate_m3h=1200,
                               temperature_c=31)
    stop = ms_svc.record_milestone(call, ter, "INTERRUPTION_START", now(-20), cause_code="SHORE_TANK_SWITCH")
    ms_svc.record_milestone(call, ter, "INTERRUPTION_END", now(-15), related=stop)
    ms_svc.countersign_milestone(stop, nav)
    ms_svc.record_milestone(call, nav, "TOPPING_OFF", now(-10))
    ms_svc.record_milestone(call, ter, "TRANSFER_END", now(-8))
    ms_svc.record_milestone(call, ter, "LINES_DRAINED", now(-7))
    ms_svc.record_milestone(call, ter, "HOSES_DISCONNECTED", now(-6))
    ms_svc.record_milestone(call, ins, "FINAL_GAUGING", now(-5))
    call.refresh_from_db()
    assert call.status == CallStatus.OPS_COMPLETE
    assert task(call, "M1:1.13").status == TaskStatus.DONE and task(call, "M1:1.15").status == TaskStatus.DONE

    m = meas_svc.create_measurement(call, ins, Measurement.Kind.FINAL, unit="MT")
    meas_svc.add_value(m, nav, "SHIP", "29950.000")
    meas_svc.add_value(m, ter, "SHORE", "29900.000")
    assert m.is_complete and not m.exceeds_tolerance()
    task_svc.complete_task(task(call, "M1:1.11"), ter)
    task_svc.complete_task(task(call, "M1:1.12"), ter)

    ms_svc.record_milestone(call, act(world, call, "PRE"), "WASTE_DELIVERED", now(-4))
    request_and_decide(world, call, "OUTWARD_FORMALITIES", "AGE", "ADM")
    request_and_decide(world, call, "DEPARTURE_CLEARANCE", "AGE", "CAP", {"requested_time": now().isoformat()},
                       valid_from=now(-60))
    ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_DEP", now(-3))
    ms_svc.record_milestone(call, svc, "LAST_LINE", now(-2))
    ms_svc.record_milestone(call, nav, "DEPARTED", now(-1))
    call.refresh_from_db()
    assert call.status == CallStatus.DEPARTED and task(call, "M0:35").status == TaskStatus.DONE

    sof = reports.issue_statement_of_facts(call, age)
    doc_svc.sign_document(sof, nav)
    doc_svc.sign_document(sof, ter)
    sof.refresh_from_db()
    assert sof.status == DocumentStatus.SIGNED and task(call, "M0:36").status == TaskStatus.DONE
    html = sof.file.open("rb").read().decode("utf-8")
    assert "Kissy" in html and call.reference in html

    call_svc.confirm_closure(call, age)
    call_svc.close_call(call, act(world, call, "CAP"))
    call.refresh_from_db()
    assert call.status == CallStatus.CLOSED and task(call, "M0:39").status == TaskStatus.DONE
    assert not JournalEntry.objects.filter(call=call, action="holdpoint.refused").exists()  # no unjustified block
    assert journal.verify_chain(port)["ok"]


# ======================================================================================== S2
@pytest.mark.django_db
def test_s2_hold_point_refusal_then_allowed(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    force_done(call, ["M0:27", "M0:28", "M0:31", "M1:1.04", "M1:1.05", "M1:1.06", "M1:1.07"])
    ter = act(world, call, "TER")
    with pytest.raises(HoldPointRefused) as exc:
        ms_svc.record_milestone(call, ter, "TRANSFER_START", now())
    missing = [m["task"] for m in exc.value.missing]
    assert missing == ["M0:29"]
    assert exc.value.missing[0]["role"] == "TER"
    assert "M0:29" in exc.value.message and "Terminal" in exc.value.message
    refusal = JournalEntry.objects.get(call=call, action="holdpoint.refused")
    assert "CAP" in refusal.visible_roles
    assert not call.milestones.filter(type__code="TRANSFER_START").exists()
    ms_svc.record_milestone(call, ter, "ESD_TEST", now(-1))
    ms_svc.record_milestone(call, ter, "TRANSFER_START", now())
    assert call.milestones.filter(type__code="TRANSFER_START").exists()


# ======================================================================================== S3
@pytest.mark.django_db
def test_s3_eta_revision_cascade_without_burst(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    before = {t.pk: t.due_at for t in call.tasks.filter(anchor="ETA")}
    notes_before = Notification.objects.count()
    started = time.monotonic()
    call_svc.update_estimates(call, act(world, call, "AGE"), eta=call.eta + timedelta(hours=8), reason="weather")
    assert time.monotonic() - started < 60
    for t in call.tasks.filter(anchor="ETA"):
        if before[t.pk] is not None and t.status == TaskStatus.PENDING:
            assert t.due_at - before[t.pk] == timedelta(hours=8)
    per_user = {}
    for n in Notification.objects.all()[: Notification.objects.count() - notes_before or None]:
        per_user[n.user_id] = per_user.get(n.user_id, 0) + 1
    new = Notification.objects.order_by("-pk")[: Notification.objects.count() - notes_before]
    counts = {}
    for n in new:
        counts[n.user_id] = counts.get(n.user_id, 0) + 1
    assert counts and max(counts.values()) == 1  # at most one notification per recipient


# ======================================================================================== S4
@pytest.mark.django_db
def test_s4_tacit_countersignature(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    gauging = ms_svc.record_milestone(call, act(world, call, "INS"), "INITIAL_GAUGING", now(-1))
    assert ms_svc.overall_state(gauging) == CountersignState.PENDING
    created = ms_svc.apply_tacit_countersignatures(now(call.port.countersign_delay_minutes + 1))
    assert created == 2
    states = ms_svc.state_by_role(gauging)
    assert states == {"NAV": CountersignState.TACIT, "TER": CountersignState.TACIT}
    assert ms_svc.overall_state(gauging) == CountersignState.TACIT != CountersignState.COUNTERSIGNED
    html = reports.render_statement(call)
    assert "tacite" in html.lower() and "tacit" in html.lower()


# ======================================================================================== S5
@pytest.mark.django_db(databases=["default", "secure"])
def test_s5_n4_partitioning(world, client):
    from apps.secure import services as n4
    from apps.secure.models import SecureAccessLog

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    journal_before = JournalEntry.objects.count()
    notes_before = Notification.objects.count()
    alerts_before = Alert.objects.count()
    reference = n4.deposit(call, act(world, call, "AGE"), kind="ARMED_GUARDS",
                           payload={"guards": 4, "embark": "2026-11-02T06:00Z", "company": "Escort Co"})
    assert reference.startswith("N4-SLFNA-")
    # No trace in the operational database: no journal entry, no notification, no alert, nothing in exports
    assert JournalEntry.objects.count() == journal_before
    assert Notification.objects.count() == notes_before and Alert.objects.count() == alerts_before
    for role in ("AGE", "TER", "INS", "DIR"):
        user = world.users[role]
        with pytest.raises(NotVisible):
            n4.list_items(user, world.port)
        with pytest.raises(NotVisible):
            n4.read_item(user, world.port, reference)
    data, _files = call_payload(call, act(world, call, "DIR"))
    assert reference not in json.dumps(data) and "guards" not in json.dumps(data).lower()
    # Security authority: full access, logged nominatively
    content = n4.read_item(world.users["SUR"], world.port, reference)
    assert content["payload"]["guards"] == 4
    log = SecureAccessLog.objects.using("secure").filter(action="VIEW").first()
    assert log.user_label.startswith("User SUR") and log.role == "SUR"
    n4.read_item(world.users["CAP"], world.port, reference)
    assert SecureAccessLog.objects.using("secure").filter(role="CAP", action="VIEW", notified=True).exists()
    assert n4.verify_chain(world.port.code)["ok"]


# ======================================================================================== S6
@pytest.mark.django_db
def test_s6_offline_conflict_creates_dispute(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    force_done(call, ["M0:25"])
    svc = act(world, call, "SVC")
    online = ms_svc.record_milestone(call, svc, "ALL_FAST", now(-30))
    device_time = now(-25)
    results = process_batch(call, svc, [{
        "kind": "milestone", "client_uuid": str(uuid.uuid4()), "type": "ALL_FAST",
        "declared_at": now(-28).isoformat(), "device_recorded_at": device_time.isoformat(),
    }])
    assert results[0]["status"] == "conflict" and results[0]["deferred"] is True
    offline = Milestone.objects.get(pk=results[0]["id"])
    assert offline.is_conflict and offline.deferred and offline.device_recorded_at == device_time
    assert offline.recorded_at > offline.device_recorded_at  # double timestamp kept
    call.refresh_from_db()
    assert call.atb == online.declared_at  # nothing overwritten
    dispute = Dispute.objects.get(call=call, auto_created=True)
    assert dispute.target_id == online.pk and dispute.status == "OPEN"
    # idempotent replay
    again = process_batch(call, svc, [{"kind": "milestone", "client_uuid": str(offline.client_uuid), "type": "ALL_FAST",
                                       "declared_at": now(-28).isoformat(), "device_recorded_at": device_time.isoformat()}])
    assert again[0]["id"] == offline.pk
    html = reports.render_statement(call)
    assert "différée" in html and "deferred" in html.lower()


# ======================================================================================== S7
@pytest.mark.django_db
def test_s7_vetting_refusal(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    vet = req_svc.create_request(call, act(world, call, "TER"), "VESSEL_ACCEPTANCE", {
        "product": "Gasoil", "inspection": "CDI 2026", "last_cargoes": "x", "vetting_result": "Not accepted"})
    reason = "Détention PSC récente pour défaut du gaz inerte"
    req_svc.decide_request(vet, act(world, call, "CAP"), RequestStatus.REFUSED, reason=reason)
    vet.refresh_from_db()
    assert rights.can_see_refusal_reason(act(world, call, "AGE"), vet)
    assert rights.can_see_refusal_reason(act(world, call, "COM"), vet)
    for role in ("TER", "INS", "PRE", "DIR", "APO"):
        assert not rights.can_see_refusal_reason(act(world, call, role), vet), role
    for entry in JournalEntry.objects.filter(call=call):
        assert reason not in entry.summary_fr and reason not in json.dumps(entry.payload, ensure_ascii=False)
    exported = export_call(call, act(world, call, "DIR"))
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert reason not in archive.read("call.json").decode("utf-8")
    exported = export_call(call, act(world, call, "COM"))
    with zipfile.ZipFile(io.BytesIO(exported)) as archive:
        assert reason not in archive.read("call.json").decode("utf-8")
    green = call.requests.get(type__code="GREEN_LIGHT")
    with pytest.raises(HoldPointRefused):
        req_svc.decide_request(green, act(world, call, "CAP"), RequestStatus.APPROVED)
    force_done(call, ["M0:09"])
    berth_req = req_svc.create_request(call, act(world, call, "AGE"), "BERTH",
                                       {"window_from": now(60).isoformat(), "arrival_draft": 10})
    with pytest.raises(HoldPointRefused) as exc:
        req_svc.decide_request(berth_req, act(world, call, "APO"), RequestStatus.APPROVED,
                               berth=world.port.berths.get(code="KISSY-JETTY"))
    assert any("vetting" in r.lower() for r in exc.value.reasons)
    call.refresh_from_db()
    assert call.berth is None


# ======================================================================================== S8
@pytest.mark.django_db
def test_s8_bill_of_lading_lock(world, client):
    call = make_call(world, operations=("M2",))
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    age = act(world, call, "AGE")
    with pytest.raises(LockRefused):
        doc_svc.upload_document(call, age, "BILL_OF_LADING", upload("bl.pdf"))
    with pytest.raises(LockRefused):  # not even the platform / an administrator
        doc_svc.upload_document(call, system_actor_for(call), "BILL_OF_LADING", upload("bl.pdf"))
    assert JournalEntry.objects.filter(call=call, action="holdpoint.refused").count() == 2
    assert not call.documents.filter(type__code="BILL_OF_LADING").exists()
    with pytest.raises(Exception):
        task_svc.mark_not_applicable(task(call, "M2:2.16"), age, "try to lift the lock")
    doc_svc.upload_document(call, act(world, call, "COM"), "DOC_INSTRUCTIONS", upload("instructions.pdf"),
                            task=task(call, "M2:2.16"))
    doc_svc.upload_document(call, act(world, call, "INS"), "QQ_CERT", upload("cq.pdf"), task=task(call, "M2:2.15"))
    bl = doc_svc.upload_document(call, age, "BILL_OF_LADING", upload("bl.pdf"))
    assert bl.status == DocumentStatus.ISSUED
    assert task(call, "M2:2.17").status == TaskStatus.DONE
