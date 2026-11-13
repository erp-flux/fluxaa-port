"""Version 1.4 — loss control and the ship/shore interface (FLX-CDC-002 §6.12, EXG-Q-01 to EXG-Q-10): the pumping
log kept by both sides, the tank readings validated by the surveyor, the quality certificate's readers, the time
sheet read by every party, the isolation between agencies and the port call board, the notifications, the report
access decided at parametrage, the preparation of the declaration, the on-line ship/shore safety checklist."""
from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core.models import Organization, User
from apps.registry.models import (
    Alert,
    DocumentType,
    JournalEntry,
    Notification,
    ReportAccess,
    SafetyChecklist,
    TaskStatus,
)
from apps.registry.services import board, exports, forms, preparation, rights
from apps.registry.services import calls as call_svc
from apps.registry.services import checklist as cl_svc
from apps.registry.services import documents as doc_svc
from apps.registry.services import measurements as meas_svc
from apps.registry.services.errors import PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call, master
from .test_web import login


def now(minutes=0):
    return timezone.now() + timedelta(minutes=minutes)


def declared(world, **extra):
    call = make_call(world, **extra)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    return call


def pdf(name="f.pdf"):
    return SimpleUploadedFile(name, b"%PDF-1.4 demo", content_type="application/pdf")


# ============================================================================ EXG-Q-01 pumping log, both sides
@pytest.mark.django_db
def test_the_pumping_log_is_kept_by_the_ship_and_the_terminal_and_compared_reading_by_reading(world):
    call = declared(world)
    ter, nav, ins, com, age, svc = (act(world, call, "TER"), master(world, call), act(world, call, "INS"),
                                    act(world, call, "COM"), act(world, call, "AGE"), act(world, call, "SVC"))
    shore = meas_svc.open_pumping_sheet(call, ter, tank="TK-101", start_level_mm="1325", m3_per_metre="1684",
                                        density="0.7463", vcf="0.9824", planned_quantity_m3="32000", expected_rate_m3h="1200")
    assert shore.side == "SHORE" and shore.planned_quantity_mt == (Decimal("32000") * Decimal("0.7463") * Decimal("0.9824")).quantize(Decimal("0.001"))
    assert shore.tons_per_metre == Decimal("1684") * Decimal("0.7463") * Decimal("0.9824")
    ship = meas_svc.open_pumping_sheet(call, nav, tank="1P-6S", density="0.7463", vcf="0.9824")
    assert ship.side == "SHIP"
    # the owner reads, never writes; the surveyor neither; the marine services do not even read
    with pytest.raises(PermissionRefused):
        meas_svc.open_pumping_sheet(call, com, tank="x")
    with pytest.raises(PermissionRefused):
        meas_svc.add_pumping_entry(call, ins, declared_at=now(-120), sheet=shore, level_mm="2000")
    t0 = now(-180)
    # the terminal enters levels: the moved and cumulated quantities come from the calibration
    e1 = meas_svc.add_pumping_entry(call, ter, declared_at=t0, sheet=shore, level_mm="2310", manifold_pressure_bar="6.2",
                                    note="start of discharge")
    assert e1.hourly_m3 == Decimal("1658.740") and e1.cumulative_m3 == Decimal("1658.740")  # (2310 − 1325) / 1000 × 1684
    assert e1.cumulative_mt == (Decimal("1658.740") * Decimal("0.7463") * Decimal("0.9824")).quantize(Decimal("0.001"))
    e2 = meas_svc.add_pumping_entry(call, ter, declared_at=t0 + timedelta(hours=1), sheet=shore, level_mm="3000")
    assert e2.hourly_m3 == Decimal("1161.960") and e2.cumulative_m3 == Decimal("2820.700") and e2.flow_rate_m3h == Decimal("1161.96")
    # the ship enters what it delivered; the platform pairs the readings of the same hour
    meas_svc.add_pumping_entry(call, nav, declared_at=t0 + timedelta(minutes=3), sheet=ship, hourly_m3="1657")
    meas_svc.add_pumping_entry(call, nav, declared_at=t0 + timedelta(hours=1, minutes=4), sheet=ship, hourly_m3="1162")
    rows = meas_svc.compare_sides(call)
    assert len(rows) == 2 and rows[0]["shore"].pk == e1.pk and rows[0]["ship"].hourly_m3 == Decimal("1657")
    assert rows[0]["hourly_deviation"] == Decimal("1.740") and rows[0]["hourly_pct"] == Decimal("0.105") and not rows[0]["exceeds"]
    assert rows[1]["cumulative_deviation"] == Decimal("1.700") and not rows[1]["exceeds"]
    assert not Alert.objects.filter(call=call, kind="QUANTITY").exists()
    # a third hour with a shore reading 0.4 % above the ship's: the alert of the terminal logs, told at once
    meas_svc.add_pumping_entry(call, ter, declared_at=t0 + timedelta(hours=2), sheet=shore, level_mm="3697")  # 1173.7 m³
    meas_svc.add_pumping_entry(call, nav, declared_at=t0 + timedelta(hours=2, minutes=2), sheet=ship, hourly_m3="1169")
    rows = meas_svc.compare_sides(call)
    assert rows[2]["hourly_pct"] > Decimal("0.3") and rows[2]["exceeds"]
    alert = Alert.objects.get(call=call, kind="QUANTITY")
    assert "investigation" in alert.message_fr and "%" in alert.message_en
    assert Notification.objects.filter(call=call, dedupe_key__startswith="pumping-dev:", realtime=True,
                                       user=world.users["CAP"]).exists()
    assert Notification.objects.filter(call=call, dedupe_key__startswith="pumping-dev:", user=world.users["COM"]).exists()
    # the readers decided at parametrage: harbour master, surveyor, owner (trader, superintendent), agency, management
    for actor in (ins, com, age, act(world, call, "CAP"), act(world, call, "DIR"), ter, nav):
        assert rights.can_read_report(actor, "PUMPING_LOG")
    assert not rights.can_read_report(svc, "PUMPING_LOG") and not rights.can_read_report(act(world, call, "PRE"), "PUMPING_LOG")
    summary = meas_svc.pumping_summary(call)
    assert summary["SHORE"]["count"] == 3 and summary["SHIP"]["count"] == 3 and summary["SHORE"]["cumulative_m3"] == Decimal("3994.448")
    # the sheet is completed by its side; the printed pumping log is generated by either side, read by the readers
    meas_svc.close_pumping_sheet(shore, ter, actual_stop_level_mm="3697")
    shore.refresh_from_db()
    assert shore.final_volume_m3 == Decimal("3994.448")
    with pytest.raises(RuleViolation):
        meas_svc.add_pumping_entry(call, ter, declared_at=t0 + timedelta(hours=3), sheet=shore, level_mm="4000")
    doc = forms.issue(call, ter, "PUMPING_LOG")
    assert doc.type.code == "PUMPING_LOG" and rights.document_visible(com, doc) and rights.document_visible(ins, doc)
    assert not rights.document_visible(svc, doc)
    html = doc.file.read().decode()
    assert "1658.740" in html and "investigation" in html and "+0.1" in html


@pytest.mark.django_db
def test_the_port_decides_who_reads_the_pumping_log_and_the_measurements(world):
    call = declared(world)
    age, svc = act(world, call, "AGE"), act(world, call, "SVC")
    assert rights.measurements_visible(age) and rights.can_read_report(age, "PUMPING_LOG") and not rights.measurements_visible(svc)
    access = ReportAccess.objects.get(port=world.port, code="PUMPING_LOG")
    access.reader_roles = [r for r in access.reader_roles if r != "AGE"] + ["SVC"]
    access.save()
    ReportAccess.objects.filter(port=world.port, code="MEASUREMENTS").update(reader_roles=["NAV", "TER", "INS", "CAP", "SVC"])
    assert not rights.can_read_report(age, "PUMPING_LOG") and rights.can_read_report(svc, "PUMPING_LOG")
    assert not rights.measurements_visible(age) and rights.measurements_visible(svc)
    # the screen and the API follow the setting
    from django.test import Client

    client = Client()
    login(client, world, "AGE")
    page = client.get(f"/escales/{call.pk}/?tab=mesures").content.decode()
    assert "not visible to your role" in page or "Quantities" not in page
    token = Token.objects.create(user=world.users["AGE"]).key
    assert client.get(f"/api/v1/calls/{call.reference}/pumping-log/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404
    # the bootstrap never overwrites the port's own setting
    from apps.registry.bootstrap import bootstrap_port

    bootstrap_port("SLFNA")
    assert ReportAccess.objects.get(port=world.port, code="PUMPING_LOG").reader_roles == access.reader_roles


# ============================================================================ EXG-Q-05 tank readings, validated by the surveyor
@pytest.mark.django_db
def test_tank_readings_are_entered_by_their_side_and_shown_to_the_others_once_the_surveyor_validated_them(world):
    call = declared(world)
    ter, nav, ins, com, age, cap = (act(world, call, "TER"), master(world, call), act(world, call, "INS"),
                                    act(world, call, "COM"), act(world, call, "AGE"), act(world, call, "CAP"))
    m = meas_svc.create_measurement(call, ins, "INITIAL")
    # the ship reads its cargo tanks; the terminal cannot read a ship tank, the owner reads nothing
    with pytest.raises(PermissionRefused):
        meas_svc.add_tank_reading(m, ter, side="SHIP", tank="1P", gov_m3="5000")
    with pytest.raises(PermissionRefused):
        meas_svc.add_tank_reading(m, com, tank="1P", gov_m3="5000")
    with pytest.raises(RuleViolation):
        meas_svc.add_tank_reading(m, nav, tank="1P")  # at least one figure
    r1 = meas_svc.add_tank_reading(m, nav, tank="1P", level_mm="412", temperature_c="29.5", gov_m3="5342.1", vcf="0.98241", density="0.8412")
    assert r1.side == "SHIP" and r1.gsv_m3 == Decimal("5248.132") and r1.weight_mt == Decimal("4414.729") and r1.state == "PENDING"
    r2 = meas_svc.add_tank_reading(m, nav, tank="1S", gov_m3="5338.4", vcf="0.98241", density="0.8412")
    s1 = meas_svc.add_tank_reading(m, ter, tank="T-12", gov_m3="2231.3", vcf="0.98230", density="0.8412")
    assert s1.side == "SHORE"
    # pending: the side that entered it and the surveyor see it; nobody else
    assert rights.tank_reading_visible(nav, r1) and rights.tank_reading_visible(ins, r1)
    for other in (ter, com, age, cap):
        assert not rights.tank_reading_visible(other, r1)
    assert rights.tank_reading_visible(ter, s1) and not rights.tank_reading_visible(nav, s1)
    assert Notification.objects.filter(call=call, user=world.users["INS"], dedupe_key__startswith=f"tank:{m.pk}:SHIP", realtime=True).exists()
    assert meas_svc.tank_totals(m, com)["SHIP"]["readings"] == [] and meas_svc.tank_totals(m, com)["SHIP"]["pending"] == 2
    # only the surveyor validates; a rejection states its reason; the side corrects with a new reading
    with pytest.raises(PermissionRefused):
        meas_svc.review_tank_reading(r1, ter, validate=True)
    with pytest.raises(RuleViolation):
        meas_svc.review_tank_reading(r2, ins, validate=False)
    meas_svc.review_tank_reading(r1, ins, validate=True)
    meas_svc.review_tank_reading(r2, ins, validate=False, note="temperature inconsistent")
    with pytest.raises(RuleViolation):
        meas_svc.review_tank_reading(r1, ins, validate=False, note="twice")
    assert r1.is_validated and r2.state == "REJECTED"
    assert Notification.objects.filter(call=call, user=world.users["AGE"], dedupe_key=f"tank:{r2.pk}:rejected", realtime=True).exists()
    for reader in (ter, com, age, cap, ins):
        assert rights.tank_reading_visible(reader, r1)
    assert not rights.tank_reading_visible(com, r2)
    r3 = meas_svc.add_tank_reading(m, nav, tank="1S", gov_m3="5338.4", vcf="0.98241", density="0.8412", temperature_c="29.6", supersedes=r2)
    current = {r.tank: r for r in meas_svc.current_readings(m, "SHIP")}
    assert current["1S"].pk == r3.pk and r3.state == "PENDING"
    with pytest.raises(RuleViolation):
        meas_svc.review_tank_reading(r2, ins, validate=True)  # superseded
    totals = meas_svc.tank_totals(m, com)
    assert totals["SHIP"]["count"] == 1 and totals["SHIP"]["validated"] == r1.weight_mt and totals["SHIP"]["pending"] == 1
    # the export keeps the same rule: the owner receives the validated readings only
    data, _files = exports.call_payload(call, com)
    readings = data["measurements"][0]["tank_readings"]
    assert [r["tank"] for r in readings] == ["1P"] and readings[0]["state"] == "VALIDATED"
    own, _files = exports.call_payload(call, nav)
    assert sorted(r["tank"] for r in own["measurements"][0]["tank_readings"]) == ["1P", "1S", "1S"]


# ============================================================================ EXG-Q-06 quality certificate readers
@pytest.mark.django_db
def test_the_laboratory_quality_certificate_is_read_by_the_terminal_the_trader_the_vessel_the_surveyor_and_the_port_only(world):
    call = declared(world)
    ins = act(world, call, "INS")
    dtype = DocumentType.objects.get(port=world.port, code="QUALITY_CERT")
    assert dtype.readers_exact and sorted(dtype.audience_roles) == ["APO", "CAP", "COM", "DIR", "NAV", "TER"]
    before = Notification.objects.count()
    doc = doc_svc.upload_document(call, ins, "QUALITY_CERT", pdf("quality.pdf"), title="Certificate of quality — Gasoil")
    for role in ("TER", "COM", "CAP", "APO", "DIR"):
        assert rights.document_visible(act(world, call, role), doc), role
    assert rights.document_visible(master(world, call), doc)
    for role in ("AGE", "SVC", "ADM", "SUR", "PRE"):
        assert not rights.document_visible(act(world, call, role), doc), role
    # the readers are told, not the others
    told = {n.user.roles[0] for n in Notification.objects.filter(pk__gt=0, call=call, dedupe_key=f"document:{doc.pk}:issued")}
    assert {"TER", "COM", "CAP", "APO", "DIR"} <= told and "AGE" not in told and "SVC" not in told
    assert Notification.objects.count() > before
    # the port administrator may widen the list; the agency is then a reader
    dtype.audience_roles = [*dtype.audience_roles, "AGE"]
    dtype.save()
    doc.refresh_from_db()
    assert rights.document_visible(act(world, call, "AGE"), doc)


# ============================================================================ EXG-Q-02 time sheet read by every party
@pytest.mark.django_db
def test_the_time_sheet_follows_the_terminal_structure_and_is_read_by_every_party(world):
    call = declared(world, planned_pump_hours="24", batch_reference="B-7")
    ter = act(world, call, "TER")
    doc = forms.issue(call, ter, "TIME_SHEET")
    assert doc.confidentiality == "N1" and doc.issuer_role == "TER"
    for role in ("AGE", "COM", "CAP", "SVC", "ADM", "SUR", "INS", "DIR"):
        assert rights.document_visible(act(world, call, role), doc), role
    assert rights.document_visible(master(world, call), doc)
    html = doc.file.read().decode()
    for marker in ("General information", "Standard activities", "Non-standard activities and stoppages", "Quantities and performance",
                   "Time summary", "Exclusions", "Planned pump time", "24", "B-7", "Delay counted", "Attributable to", "For surveyor"):
        assert marker in html, marker
    # the pumping-log and time-sheet forms carry the lecture of the call: no reading, blank rows, no error
    assert "Pumping log" in forms.render(call, "PUMPING_LOG")


# ============================================================================ EXG-Q-03 / EXG-Q-04 isolation and the board
@pytest.mark.django_db
def test_another_agency_sees_the_call_on_the_board_but_nothing_operational_of_it(world, client):
    call = declared(world)
    rival_org = Organization.objects.create(port=world.port, name="Rival Agency", allowed_roles=["AGE"])
    rival = User.objects.create_user(email="rival@test.local", password="pw-test-123456", full_name="Rival", organization=rival_org, roles=["AGE"])
    assert not rights.call_queryset_for_user(rival).filter(pk=call.pk).exists()
    rows = board.rows(world.port, rival)
    row = next(r for r in rows if r["call"].pk == call.pk)
    assert row["link"] is False and row["vessel"] == world.vessel.name and row["agency"] == str(call.agency) and row["operations"] == ["M1"]
    assert "parties" not in row and "tasks" not in row and "documents" not in row
    # the nature of the cargo and the tonnage follow the port's choice (v1.5): shown as on the placement conference,
    # or hidden — never the parties, the tasks, the documents, the measurements
    assert row["cargo"] == "Gasoil" and row["quantity"].startswith("30")
    world.port.board_shows_cargo = False
    world.port.save(update_fields=["board_shows_cargo"])
    row = next(r for r in board.rows(world.port, rival) if r["call"].pk == call.pk)
    assert row["cargo"] == "" and row["quantity"] == ""
    client.force_login(rival)
    page = client.get("/escales/port/")
    assert page.status_code == 200
    html = page.content.decode()
    assert world.vessel.name in html and "consultation only" in html and f"/escales/{call.pk}/" not in html
    assert "Gasoil" not in html and "30000" not in html  # product and quantity hidden by the port's choice
    for url in (f"/escales/{call.pk}/", f"/escales/{call.pk}/?tab=mesures", f"/escales/{call.pk}/liste-de-controle/", f"/escales/{call.pk}/formulaires/"):
        assert client.get(url).status_code == 404, url
    token = Token.objects.create(user=rival).key
    assert client.get(f"/api/v1/calls/{call.reference}/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404
    assert client.get(f"/api/v1/calls/{call.reference}/pumping-log/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404
    api_rows = client.get("/api/v1/board/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["results"]
    mine = next(r for r in api_rows if r["vessel"] == world.vessel.name)
    # the call number is on the conference like the "ATP" number of the port's own sheet; nothing operational
    assert mine["reference"] == call.reference and mine["party"] is False and mine["cargo"] is None and "product" not in mine
    # notifications of the call never reach the rival agency
    assert not Notification.objects.filter(call=call, user=rival).exists()
    # the agency of the call opens it from the board; the port decides who consults the board at all
    client.force_login(world.users["AGE"])
    assert f"/escales/{call.pk}/" in client.get("/escales/port/").content.decode()
    ReportAccess.objects.filter(port=world.port, code="CALL_BOARD").update(reader_roles=["CAP", "APO", "DIR"])
    assert client.get("/escales/port/").status_code == 404
    client.force_login(rival)
    assert client.get("/api/v1/board/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404


# ============================================================================ EXG-Q-09 preparing the declaration
@pytest.mark.django_db
def test_the_agency_is_told_what_the_declaration_waits_for_and_holds_the_means_to_resolve_it(world, client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call = make_call(world)
    age = act(world, call, "AGE")
    # at the creation: the agency's other people are told what is missing (the creator knows)
    other = User.objects.create_user(email="age2@test.local", password="pw-test-123456", full_name="Other", organization=world.orgs.agency, roles=["AGE"])
    call2 = make_call(world)
    assert Notification.objects.filter(call=call2, user=other, dedupe_key=f"draft:{call2.pk}").exists()
    assert not Notification.objects.filter(call=call2, user=world.users["AGE"], dedupe_key=f"draft:{call2.pk}").exists()
    ready = preparation.readiness(call, age)
    codes = [item["task"].code for item in ready["items"]]
    assert codes == ["M0:02", "M0:03", "M0:05"] and not ready["ready"]
    certificates = next(item for item in ready["items"] if item["task"].code == "M0:03")
    assert certificates["needs_master_link"] and certificates["can_act"]  # the agency may file them for the master
    assert certificates["responsible"][0]["role"] == "NAV" and not certificates["responsible"][0]["can_act"]
    assert certificates["hint"]["kind"] == "document" and certificates["hint"]["code"] == "CERTIFICATES"
    # a reminder to the ship needs the master's access first
    with pytest.raises(RuleViolation):
        preparation.remind(call, age, certificates["task"])
    # the master's access, e-mailed with what the port expects from him
    mail.outbox.clear()
    link, _token, code = call_svc.issue_master_link(call, age, master_name="Capt. Test", send_to="master@vessel.test")
    assert link.sent_to == "master@vessel.test" and len(mail.outbox) == 1
    body = mail.outbox[0].body
    assert code in body and "M0:03" in body and "certificates" in body.lower()
    assert JournalEntry.objects.filter(call=call, action="master_link.sent").exists()
    reached = preparation.remind(call, age, certificates["task"])
    assert reached == 1 and len(mail.outbox) == 2 and "M0:03" in mail.outbox[1].body
    assert preparation.last_reminder(call, certificates["task"]) is not None
    # the refusal box of the declaration names who answers for each item, with the actions
    login(client, world, "AGE")
    response = client.post(f"/escales/{call.pk}/action/declare/", {"back": "?tab=apercu"})
    assert response.status_code == 302
    page = client.get(f"/escales/{call.pk}/?tab=apercu").content.decode()
    assert "Refused by the platform" in page and "Who answers for it" in page and "Provide the document" in page
    assert "Remind" in page and "Before the declaration" in page
    # the agency files the certificates on the master's behalf: task M0:03 is done, the declaration opens
    doc_svc.upload_document(call, age, "Q88", pdf("q88.pdf"))
    doc = doc_svc.upload_document(call, age, "CERTIFICATES", pdf("certificates.pdf"))
    assert doc.issuer_role == "AGE"
    assert call.tasks.get(template_code="M0", number="03").status == TaskStatus.DONE
    force_done(call, ["M0:05"])
    assert preparation.readiness(call, age)["ready"]
    call_svc.declare_call(call, age)
    call.refresh_from_db()
    assert call.status == "DECLARED"
    # a reminder of an account-holding party reaches its people in real time
    call3 = declared(world)
    vetting = call3.tasks.get(template_code="M0", number="06")
    reached = preparation.remind(call3, act(world, call3, "CAP"), vetting)
    assert reached == 1 and Notification.objects.filter(call=call3, user=world.users["TER"], realtime=True, dedupe_key__startswith=f"remind:{vetting.pk}").exists()
    with pytest.raises(PermissionRefused):
        preparation.remind(call3, act(world, call3, "TER"), vetting)


# ============================================================================ EXG-Q-10 the on-line safety checklist
@pytest.mark.django_db
def test_the_ship_and_the_terminal_complete_and_sign_the_safety_checklist_on_line(world):
    call = declared(world)
    ter, nav, ins, com, cap, age = (act(world, call, "TER"), master(world, call), act(world, call, "INS"),
                                    act(world, call, "COM"), act(world, call, "CAP"), act(world, call, "AGE"))
    with pytest.raises(PermissionRefused):
        cl_svc.open_checklist(call, ins)
    checklist = cl_svc.open_checklist(call, ter, repeat_interval_h="4")
    assert checklist.status == "OPEN" and len(checklist.items) >= 40 and checklist.repeat_interval_h == Decimal("4")
    with pytest.raises(RuleViolation):
        cl_svc.open_checklist(call, nav)  # one at a time
    assert Notification.objects.filter(call=call, user=world.users["AGE"], dedupe_key=f"checklist:{checklist.pk}:opened").exists()
    # readers: both sides, and the roles the port decided; the owner is not one of them by default
    assert cl_svc.visible(cap, call) and cl_svc.visible(ins, call) and cl_svc.visible(age, call) and cl_svc.visible(nav, call)
    assert not cl_svc.visible(com, call) and not cl_svc.can_complete(cap, call)
    # each side answers its own items; a joint item needs both; a "no" states what is to be done
    with pytest.raises(PermissionRefused):
        cl_svc.answer(checklist, ter, item_code="1A.1", state="YES")
    with pytest.raises(RuleViolation):
        cl_svc.answer(checklist, nav, item_code="1A.1", state="NO")
    cl_svc.answer(checklist, nav, item_code="1A.1", state="NO", remark="O2 at 9 %, purging")
    assert Notification.objects.filter(call=call, user=world.users["TER"], dedupe_key__contains=":1A.1:SHIP:no:", realtime=True).exists()
    with pytest.raises(RuleViolation):
        cl_svc.sign(checklist, nav)  # a "no" remains, items missing
    for item in checklist.items:
        for who, side in ((nav, "SHIP"), (ter, "SHORE")):
            if side not in (["SHIP", "SHORE"] if item["side"] == "BOTH" else [item["side"]]):
                continue
            if item["kind"] == "value":
                if side == "SHORE":
                    cl_svc.answer(checklist, who, item_code=item["code"], value="4" if item["code"] == "5A.8" else "agreed")
            else:
                cl_svc.answer(checklist, who, item_code=item["code"], state="YES")
    progress = cl_svc.progress(checklist)
    assert progress["SHIP"]["missing"] == [] and progress["SHIP"]["no"] == [] and progress["SHORE"]["missing"] == []
    assert progress["agreements"]["missing"] == []
    assert checklist.current_answers()[("1A.1", "SHIP")].state == "YES"  # the latest answer counts, the "no" stays in the record
    assert checklist.answers.filter(item_code="1A.1", side="SHIP").count() == 2
    task = call.tasks.get(template_code="M0", number="28")
    cl_svc.sign(checklist, nav)
    assert checklist.signed_sides() == {"SHIP"} and task.signatures.filter(role="NAV", kind="SIGNED").exists()
    assert Notification.objects.filter(call=call, user=world.users["TER"], dedupe_key=f"checklist:{checklist.pk}:signed:SHIP").exists()
    with pytest.raises(RuleViolation):
        cl_svc.sign(checklist, nav)
    cl_svc.sign(checklist, ter)
    checklist.refresh_from_db()
    task.refresh_from_db()
    assert checklist.status == "SIGNED" and task.status == TaskStatus.DONE
    assert call.milestones.filter(type__code="SSSCL_SIGNED").exists()
    assert checklist.document is not None and checklist.document.type.code == "SSSCL" and checklist.document.generated
    html = checklist.document.file.read().decode()
    assert "✔" in html and "O2 at 9 %" not in html  # the printed form carries the current answers
    assert Notification.objects.filter(call=call, user=world.users["CAP"], dedupe_key=f"checklist:{checklist.pk}:signed", realtime=True).exists()
    # after the signature: only the repetitive checks are answered again, as repetitions
    with pytest.raises(RuleViolation):
        cl_svc.answer(checklist, nav, item_code="1A.1", state="YES")
    rep = cl_svc.answer(checklist, nav, item_code="2.1", state="YES")
    assert rep.repetition == 1 and cl_svc.progress(checklist)["due"] is not None
    assert checklist.answers.filter(repetition__gte=1).count() == 1
    # the start of the transfer waits for this checklist (hold point M0:28) — it is now open on that count
    from apps.registry.services import holdpoints

    _tasks, missing, _reasons = holdpoints.evaluate(call, "START_TRANSFER")
    assert "M0:28" not in [m["task"] for m in missing]
    # the harbour master cancels an open checklist only
    with pytest.raises(RuleViolation):
        cl_svc.cancel(checklist, cap, "wrong vessel")


@pytest.mark.django_db
def test_the_checklist_screen_and_api_serve_both_sides(world, client):
    call = declared(world)
    login(client, world, "TER")
    page = client.get(f"/escales/{call.pk}/liste-de-controle/")
    assert page.status_code == 200 and "Open the checklist" in page.content.decode()
    response = client.post(f"/escales/{call.pk}/action/checklist_open/", {"repeat_interval_h": "4"})
    assert response.status_code == 302
    checklist = SafetyChecklist.objects.get(call=call)
    response = client.post(f"/escales/{call.pk}/action/checklist_answer/", {
        "part": "1B", "item_code": ["1B.1", "1B.2"], "state_1B.1": "YES", "state_1B.2": "NO", "remark_1B.2": "line-up to check"})
    assert response.status_code == 302
    answers = checklist.current_answers()
    assert answers[("1B.1", "SHORE")].state == "YES" and answers[("1B.2", "SHORE")].remark == "line-up to check"
    page = client.get(f"/escales/{call.pk}/liste-de-controle/").content.decode()
    assert "line-up to check" in page and 'name="state_1B.1" value="YES" checked' in page
    # the API of the terminal, then the master's by his link
    token = Token.objects.create(user=world.users["TER"]).key
    data = client.get(f"/api/v1/calls/{call.reference}/safety-checklist/", HTTP_AUTHORIZATION=f"Bearer {token}").json()
    assert data["checklist"]["status"] == "OPEN" and data["progress"]["SHORE"]["answered"] == 1
    part = next(p for p in data["checklist"]["parts"] if p["code"] == "1B")
    assert next(i for i in part["items"] if i["code"] == "1B.2")["shore"]["state"] == "NO"
    response = client.post(f"/api/v1/calls/{call.reference}/safety-checklist/answer/",
                           data=json.dumps({"items": [{"item_code": "1B.2", "state": "YES"}]}), content_type="application/json",
                           HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 200 and response.json()["progress"]["SHORE"]["answered"] == 2
    # the owner reads neither the page nor the API by default
    login(client, world, "COM")
    assert client.get(f"/escales/{call.pk}/liste-de-controle/").status_code == 404


# ============================================================================ EXG-Q-07 every action is told
@pytest.mark.django_db
def test_the_team_is_told_of_the_readings_the_validations_the_certificates_and_the_checklist(world):
    call = declared(world)
    ter, nav, ins = act(world, call, "TER"), master(world, call), act(world, call, "INS")
    sheet = meas_svc.open_pumping_sheet(call, ter, tank="TK-1", m3_per_metre="1000", start_level_mm="1000")
    assert Notification.objects.filter(call=call, dedupe_key=f"pumping-sheet:{sheet.pk}", user=world.users["COM"]).exists()
    t = now(-60).replace(minute=0)
    for i in range(3):
        meas_svc.add_pumping_entry(call, ter, declared_at=t + timedelta(minutes=10 * i), sheet=sheet, level_mm=str(1100 + 50 * i))
    # anti-noise: the readers are told once per side and window, however many readings come in
    assert Notification.objects.filter(call=call, dedupe_key__startswith=f"pumping:{call.pk}:SHORE:", user=world.users["CAP"]).count() == 1
    m = meas_svc.create_measurement(call, ins, "FINAL")
    r = meas_svc.add_tank_reading(m, nav, tank="1P", weight_mt="100")
    meas_svc.review_tank_reading(r, ins, validate=True)
    assert Notification.objects.filter(call=call, dedupe_key__startswith=f"tank:{m.pk}:SHIP:validated", user=world.users["COM"]).exists()
    mv = meas_svc.add_value(m, ter, "SHORE", "100.2")
    assert Notification.objects.filter(call=call, dedupe_key=f"quantity:{m.pk}:{mv.pk}", user=world.users["COM"]).exists()


# ============================================================================ the API of the readings
@pytest.mark.django_db
def test_the_api_serves_the_pumping_log_and_the_tank_readings_of_both_sides(world, client):
    call = declared(world)
    tokens = {role: Token.objects.create(user=world.users[role]).key for role in ("TER", "INS", "COM", "SVC")}

    def api(role, method, path, data=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {tokens[role]}"}
        if method == "get":
            return client.get(path, **headers)
        return client.post(path, data=json.dumps(data or {}), content_type="application/json", **headers)

    sheet = api("TER", "post", f"/api/v1/calls/{call.reference}/pumping-sheets/",
                {"tank": "TK-2", "m3_per_metre": "1500", "start_level_mm": "500", "density": "0.84", "vcf": "0.99", "planned_quantity_m3": "20000"})
    assert sheet.status_code == 201 and sheet.json()["tons_per_metre"] == "1247.4000"
    entry = api("TER", "post", f"/api/v1/calls/{call.reference}/pumping-log/",
                {"sheet_id": sheet.json()["id"], "declared_at": now(-30).isoformat(), "level_mm": "1500", "pressure_bar": "6.1"})
    assert entry.status_code == 201 and entry.json()["hourly_m3"] == "1500.000" and entry.json()["cumulative_mt"] == "1247.400"
    log = api("COM", "get", f"/api/v1/calls/{call.reference}/pumping-log/").json()
    assert len(log["results"]) == 1 and log["results"][0]["side"] == "SHORE" and log["tolerance_pct"] == "0.300"
    assert api("SVC", "get", f"/api/v1/calls/{call.reference}/pumping-log/").status_code == 404
    assert api("COM", "post", f"/api/v1/calls/{call.reference}/pumping-log/", {"declared_at": now().isoformat(), "level_mm": "1"}).status_code == 403
    measurement = api("INS", "post", f"/api/v1/calls/{call.reference}/measurements/", {"kind": "FINAL", "unit": "MT"}).json()
    reading = api("TER", "post", f"/api/v1/calls/{call.reference}/measurements/{measurement['id']}/tanks/",
                  {"tank": "TK-2", "gov_m3": "19000", "vcf": "0.99", "density": "0.84"})
    assert reading.status_code == 201 and reading.json()["state"] == "PENDING" and reading.json()["weight_mt"] == "15800.400"
    # pending: the owner sees no tank yet; the surveyor validates through the API; then the owner reads it
    assert api("COM", "get", f"/api/v1/calls/{call.reference}/measurements/").json()["results"][0]["tanks"]["SHORE"]["readings"] == []
    review = api("INS", "post", f"/api/v1/calls/{call.reference}/measurements/{measurement['id']}/tanks/{reading.json()['id']}/review/", {"decision": "validate"})
    assert review.status_code == 200 and review.json()["state"] == "VALIDATED"
    tanks = api("COM", "get", f"/api/v1/calls/{call.reference}/measurements/").json()["results"][0]["tanks"]["SHORE"]
    assert tanks["validated_count"] == 1 and tanks["validated_total"] == "15800.400"
    closed = api("TER", "post", f"/api/v1/calls/{call.reference}/pumping-sheets/{sheet.json()['id']}/close/", {"actual_stop_level_mm": "1500"})
    assert closed.status_code == 200 and closed.json()["final_volume_m3"] == "1500.000"


@pytest.mark.django_db
def test_the_measurements_tab_shows_each_side_its_tanks_and_the_pumping_log_with_the_deviation(world, client):
    call = declared(world)
    ter, nav, ins = act(world, call, "TER"), master(world, call), act(world, call, "INS")
    m = meas_svc.create_measurement(call, ins, "INITIAL")
    r = meas_svc.add_tank_reading(m, nav, tank="1P", weight_mt="4000")
    meas_svc.add_tank_reading(m, ter, tank="T-1", weight_mt="3990")
    sheet = meas_svc.open_pumping_sheet(call, ter, tank="T-1", m3_per_metre="1000", start_level_mm="0")
    ship = meas_svc.open_pumping_sheet(call, nav, tank="1P")
    t = now(-120)
    meas_svc.add_pumping_entry(call, ter, declared_at=t, sheet=sheet, level_mm="1000")
    meas_svc.add_pumping_entry(call, nav, declared_at=t + timedelta(minutes=5), sheet=ship, hourly_m3="990")
    login(client, world, "TER")
    page = client.get(f"/escales/{call.pk}/?tab=mesures").content.decode()
    assert "T-1" in page and "awaiting the surveyor" in page and "1P" not in page.split("Pumping log")[0].split("Ship tanks")[1].split("Shore tanks")[0]
    assert "stop for investigation" in page and "Shore pumping reading" in page and "Complete the sheet" in page
    login(client, world, "INS")
    page = client.get(f"/escales/{call.pk}/?tab=mesures").content.decode()
    assert "Validate" in page and "Reject the reading" in page and "1P" in page
    response = client.post(f"/escales/{call.pk}/action/tank_review/", {"reading_id": r.pk, "decision": "validate"})
    assert response.status_code == 302 and r.is_validated
    login(client, world, "COM")
    page = client.get(f"/escales/{call.pk}/?tab=mesures").content.decode()
    assert "1P" in page and 'name="decision"' not in page and "Read a tank" not in page and "T-1" in page  # T-1: the sheet summary
