"""Version 1.5 — every cargo, every party under control (FLX-CDC-002 §6.13, EXG-R-01 to EXG-R-10): tasks and
requests carried out in line, the validity of an announcement and its obsolescence, the green lights of the
harbour master, the naval base, the terminal and the principal, the controlled access given by the principal
agent, the two vessels of an STS transfer, the documents asked for at the announcement, the placement conference
and the berth occupation plan, the operation models of dry bulk, containers, general cargo and ro-ro, the
checklists by kind of cargo, the vetting grid against the berth limits."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core.models import Organization, User
from apps.registry.models import CallStatus, JournalEntry, Notification, TaskStatus, Vessel
from apps.registry.services import board, forms, rights, scheduler
from apps.registry.services import calls as call_svc
from apps.registry.services import checklist as cl_svc
from apps.registry.services import documents as doc_svc
from apps.registry.services import measurements as meas_svc
from apps.registry.services import tasks as task_svc
from apps.registry.services.context import actor_for_call
from apps.registry.services.errors import HoldPointRefused, PermissionRefused, RuleViolation
from apps.registry.services.forms.cargo import vetting_rows, vetting_verdict

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


def second_agency(world, name="Second Agency"):
    org = Organization.objects.create(port=world.port, name=name, allowed_roles=["AGE"], email="second@agency.test")
    user = User.objects.create_user(email=f"{name.split()[0].lower()}@agency.test", password="pw-test-123456",
                                    full_name=f"User {name}", organization=org, roles=["AGE"])
    return org, user


# ============================================================================ EXG-R-02 validity of the announcement
@pytest.mark.django_db
def test_the_announcement_is_valid_for_a_period_then_obsolete_and_announced_again(world, settings):
    port = world.port
    assert port.default_validity_days == 15 and port.max_validity_days == 90
    call = make_call(world, validity_days=3)
    assert call.validity_days == 3 and call.valid_until is not None
    assert abs((call.valid_until - call.created_at) - timedelta(days=3)) < timedelta(seconds=5)
    with pytest.raises(RuleViolation):
        make_call(world, validity_days=200)  # above the port's ceiling
    default = make_call(world)
    assert default.validity_days == 15
    # reminders before the end, then obsolescence when the vessel is not alongside
    call.valid_until = now(60 * 20)
    call.save(update_fields=["valid_until"])
    summary = scheduler.watch_validity(now())
    assert summary["reminded"] >= 1 and Notification.objects.filter(call=call, dedupe_key=f"validity:{call.pk}:24h").exists()
    call.valid_until = now(-5)
    call.save(update_fields=["valid_until"])
    summary = scheduler.watch_validity(now())
    call.refresh_from_db()
    assert summary["expired"] == 1 and call.status == CallStatus.EXPIRED and call.expired_at is not None and call.is_terminal_state
    assert Notification.objects.filter(call=call, dedupe_key=f"expired:{call.pk}", user=world.users["CAP"]).exists()
    assert JournalEntry.objects.filter(call=call, action="call.status", payload__to="EXPIRED").exists()
    # the obsolete call is read only; the master's link is no longer valid; the agency announces it again
    with pytest.raises(RuleViolation):
        call_svc.update_estimates(call, act(world, call, "AGE"), eta=now(60))
    renewed = call_svc.renew_call(call, act(world, call, "AGE"))
    assert renewed.status == CallStatus.DRAFT and renewed.renewed_from_id == call.pk and renewed.validity_days == 3
    assert renewed.vessel_id == call.vessel_id and renewed.product == "Gasoil" and renewed.template_codes == ["M0", "M1"]
    assert set(renewed.parties.filter(is_default=False).values_list("role", flat=True)) >= {"AGE", "TER", "INS", "COM", "PRE"}
    with pytest.raises(RuleViolation):
        call_svc.renew_call(call, act(world, call, "AGE"))  # once
    # a vessel alongside is never cut off: its overrun is signalled daily and counted for billing
    alongside = declared(world, validity_days=2)
    alongside.status = CallStatus.AT_BERTH
    alongside.ata = now(-60 * 50)
    alongside.atb = now(-60 * 49)
    alongside.valid_until = now(-60 * 3)
    alongside.save(update_fields=["status", "ata", "atb", "valid_until"])
    summary = scheduler.watch_validity(now())
    alongside.refresh_from_db()
    assert summary["overrun"] >= 1 and alongside.status == CallStatus.AT_BERTH and alongside.validity_overrun
    basis = alongside.billing_basis()
    assert basis["validity_days"] == 2 and basis["overrun_hours"] and basis["hours_in_port"] >= 49
    # these durations run with the clock: the generated specification neutralises them, so that its --check does not
    # fail a few minutes after the examples were rendered (1.6)
    from apps.core.management.commands.generate_spec import volatile

    assert volatile('"hours_in_port": 49.2, "overrun_hours": 1.3') == volatile('"hours_in_port": 51.9, "overrun_hours": 4')


# ============================================================================ EXG-R-03 green lights
@pytest.mark.django_db
def test_four_green_lights_guard_the_movements_and_the_operations_and_may_be_withdrawn(world, client):
    call = declared(world, green_lights=False)
    lights = task_svc.green_lights(call)
    assert [(g["task"].number, g["task"].role, g["state"]) for g in lights] == [
        ("09", "CAP", "PENDING"), ("09b", "SUR", "PENDING"), ("09c", "TER", "PENDING"), ("09d", "COM", "PENDING")]
    sur, ter, com, cap = act(world, call, "SUR"), act(world, call, "TER"), act(world, call, "COM"), act(world, call, "CAP")
    # the naval base's green light guards the movement authorization and the berthing
    force_done(call, ["M0:09", "M0:10", "M0:11", "M0:21", "M0:22"])
    with pytest.raises(HoldPointRefused) as refusal:
        from apps.registry.services import holdpoints

        holdpoints.check(call, "MOVEMENT_AUTH")
    assert "09b" in str(refusal.value)
    naval = call.tasks.get(template_code="M0", number="09b")
    task_svc.complete_task(naval, sur, note="checked against the watch list")
    from apps.registry.services import holdpoints

    holdpoints.check(call, "MOVEMENT_AUTH")  # open now
    assert Notification.objects.filter(call=call, dedupe_key__startswith=f"green:{naval.pk}:given").exists()
    # the principal's commercial green light is given by the owner / charterer — the one entry it may make
    commercial = call.tasks.get(template_code="M0", number="09d")
    task_svc.complete_task(commercial, com)
    assert commercial.status == TaskStatus.DONE and commercial.completed_role == "COM"
    # withdrawn with a reason by the party that gave it: pending again, everyone told, the hold point closes
    with pytest.raises(RuleViolation):
        task_svc.withdraw_green_light(naval, sur, "")
    with pytest.raises(PermissionRefused):
        task_svc.withdraw_green_light(naval, ter, "not mine")
    task_svc.withdraw_green_light(naval, sur, "vessel on the watch list — further checks")
    naval.refresh_from_db()
    assert naval.status == TaskStatus.PENDING and "withdrawn" in naval.completion_note
    with pytest.raises(HoldPointRefused):
        holdpoints.check(call, "MOVEMENT_AUTH")
    assert Notification.objects.filter(call=call, dedupe_key__startswith=f"green:{naval.pk}:withdrawn", user=world.users["AGE"]).exists()
    assert JournalEntry.objects.filter(call=call, action="task.green_light_withdrawn").exists()
    # the harbour master's own light is a decision: never withdrawn here
    with pytest.raises(RuleViolation):
        task_svc.withdraw_green_light(call.tasks.get(template_code="M0", number="09"), cap, "x")
    # the panel on the overview, with the buttons of the viewer's role
    login(client, world, "SUR")
    html = client.get(f"/escales/{call.pk}/").content.decode()
    assert 'id="feux-verts"' in html and "Give the green light" in html and "light-pending" in html
    response = client.post(f"/escales/{call.pk}/action/task_complete/", {"task_id": naval.pk, "note": "ok", "back": "?tab=apercu"})
    assert response.status_code == 302
    naval.refresh_from_db()
    assert naval.status == TaskStatus.DONE
    html = client.get(f"/escales/{call.pk}/").content.decode()
    assert "Withdraw the green light" in html
    # the API panel
    token = Token.objects.create(user=world.users["CAP"]).key
    panel = client.get(f"/api/v1/calls/{call.reference}/green-lights/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["results"]
    assert {g["code"]: g["state"] for g in panel} == {"M0:09": "GIVEN", "M0:09b": "GIVEN", "M0:09c": "PENDING", "M0:09d": "GIVEN"}


# ============================================================================ EXG-R-04 controlled access, co-agencies
@pytest.mark.django_db
def test_the_principal_agent_gives_each_party_all_or_part_of_the_file(world, client):
    second, second_user = second_agency(world)
    call = make_call(world, parties=[(world.orgs.terminal, "TER", "PARTIAL", ["taches", "documents"]),
                                     (world.orgs.surveyor, "INS", "READ", []), (second, "AGE", "FULL", [])])
    ter_party = call.parties.get(organization=world.orgs.terminal)
    assert ter_party.access == "PARTIAL" and ter_party.scopes == ["taches", "documents"]
    assert call.parties.get(organization=world.orgs.surveyor).access == "READ"
    ter, ins, age2 = act(world, call, "TER"), act(world, call, "INS"), actor_for_call(call, user=second_user)
    assert rights.access_of(ter, call) == ("PARTIAL", {"taches", "documents"})
    assert rights.access_of(ins, call) == ("READ", None)
    assert rights.access_of(age2, call) == ("FULL", None) and not rights.is_principal_agent(age2, call)
    assert rights.is_principal_agent(act(world, call, "AGE"), call)
    # a partial access acts in its tabs only; a reading access never acts
    rights.require_act(ter, call, "documents")
    with pytest.raises(PermissionRefused):
        rights.require_act(ter, call, "mesures")
    with pytest.raises(PermissionRefused):
        rights.require_act(ins, call, "taches")
    # the co-agency holds the file but does not declare, revise or cancel it: the principal does
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    with pytest.raises(PermissionRefused):
        call_svc.declare_call(call, age2)
    with pytest.raises(PermissionRefused):
        call_svc.update_estimates(call, age2, eta=now(60))
    call_svc.declare_call(call, act(world, call, "AGE"))
    # the principal changes an access; the party is told
    call_svc.set_party_access(call, act(world, call, "AGE"), ter_party, "PARTIAL", ["taches", "documents", "mesures"])
    ter_party.refresh_from_db()
    assert ter_party.scopes == ["taches", "documents", "mesures"] and ter_party.access_set_by == world.users["AGE"]
    assert Notification.objects.filter(call=call, user=world.users["TER"], dedupe_key__startswith=f"party:{ter_party.pk}:access").exists()
    with pytest.raises(PermissionRefused):
        call_svc.set_party_access(call, age2, ter_party, "FULL")  # the co-agency does not
    with pytest.raises(RuleViolation):
        call_svc.set_party_access(call, act(world, call, "CAP"), call.parties.get(role="CAP"), "READ")  # the port's parties keep their access
    # on screen: the tabs offered follow the access, the actions outside it are refused
    login(client, world, "INS")
    html = client.get(f"/escales/{call.pk}/?tab=taches").content.decode()
    assert "Reading only" in html and "does not allow acting on the tasks" in html
    for tab in ("apercu", "parties", "taches", "demandes", "jalons", "documents", "mesures", "contestations", "echanges", "journal"):
        html = client.get(f"/escales/{call.pk}/?tab={tab}").content.decode()
        assert "/action/" not in html, tab  # reading only: no act offered on any tab, not one form
    assert "/action/form_issue/" not in client.get(f"/escales/{call.pk}/formulaires/").content.decode()
    response = client.post(f"/escales/{call.pk}/action/measurement_open/", {"kind": "INITIAL", "unit": "MT"})
    assert response.status_code == 302 and client.get(f"/escales/{call.pk}/?tab=mesures").status_code == 200
    assert not call.measurements.exists()  # refused: reading only
    login(client, world, "TER")
    html = client.get(f"/escales/{call.pk}/?tab=jalons").content.decode()
    nav = html.split('<nav class="tabs"')[1].split("</nav>")[0]
    assert "Partial access" in html and 'href="?tab=jalons"' not in nav and 'href="?tab=mesures"' in nav and 'href="?tab=taches"' in nav
    # the API applies the same scopes
    token = Token.objects.create(user=world.users["TER"]).key
    assert client.get(f"/api/v1/calls/{call.reference}/milestones/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 404
    assert client.get(f"/api/v1/calls/{call.reference}/tasks/", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
    detail = client.get(f"/api/v1/calls/{call.reference}/", HTTP_AUTHORIZATION=f"Bearer {token}").json()
    assert detail["your_access"] == {"level": "PARTIAL", "tabs": ["documents", "mesures", "taches"], "principal_agent": False}
    token2 = Token.objects.create(user=second_user).key
    assert client.get(f"/api/v1/calls/{call.reference}/", HTTP_AUTHORIZATION=f"Bearer {token2}").json()["your_access"]["level"] == "FULL"
    # the principal's party list on screen offers the access change
    login(client, world, "AGE")
    html = client.get(f"/escales/{call.pk}/?tab=parties").content.decode()
    assert "principal agent" in html and "Set the access" in html


# ============================================================================ EXG-R-05 the two vessels of an STS transfer
@pytest.mark.django_db
def test_an_sts_transfer_creates_the_partner_vessel_s_own_call_with_its_own_agency_and_team(world):
    second, second_user = second_agency(world)
    partner_vessel = Vessel.objects.create(port=world.port, imo="9074729", name="MT PARTNER", flag="Panama", vessel_type="Product tanker", dwt=30000)
    sts_parties = [(world.orgs.sts, "PRE"), (world.orgs.surveyor, "INS"), (world.orgs.owner, "COM")]
    call = make_call(world, kind="STS_AREA", operations=("M3",), parties=sts_parties, sts_role="DONOR",
                     sts_partner={"vessel": partner_vessel, "agency": second})
    partner = call.linked_call
    assert partner is not None and partner.vessel_id == partner_vessel.pk and partner.sts_role == "RECEIVER" and call.sts_role == "DONOR"
    assert partner.linked_call_id == call.pk and partner.link_kind == "STS" and call.is_sts and partner.is_sts
    assert partner.agency_id == second.pk and partner.template_codes == call.template_codes
    # the partner call belongs to the other agency, with its own team; the announcing agency keeps a co-agency access
    assert partner.parties.filter(organization=second, role="AGE").exists()
    assert partner.parties.filter(organization=world.orgs.agency, role="AGE").exists()
    assert rights.is_principal_agent(actor_for_call(partner, user=second_user), partner)
    assert not rights.is_principal_agent(actor_for_call(partner, user=world.users["AGE"]), partner)
    assert Notification.objects.filter(call=partner, user=second_user, dedupe_key=f"sts:{partner.pk}:nominated").exists()
    assert JournalEntry.objects.filter(call=partner, action="call.linked").exists()
    with pytest.raises(RuleViolation):
        make_call(world, kind="STS_AREA", operations=("M3",), parties=sts_parties, sts_role="DONOR",
                  sts_partner={"vessel": partner_vessel, "agency": second, "role": "DONOR"})  # both cannot deliver
    # each master keeps the log of his own vessel; the comparison reads the partner's log as the other side
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    donor_master = master(world, call)
    link, _t, _c = call_svc.issue_master_link(partner, actor_for_call(partner, user=second_user), master_name="Capt. Receiver")
    receiver_master = actor_for_call(partner, master=link)
    meas_svc.open_pumping_sheet(call, donor_master, tank="1P-6S", start_level_mm="1500", m3_per_metre="900", density="0.84", vcf="0.98")
    meas_svc.open_pumping_sheet(partner, receiver_master, tank="2P-5S", start_level_mm="9000", m3_per_metre="900", density="0.84", vcf="0.98")
    t = now(-180)
    for i, (donor_level, receiver_level) in enumerate([(2500, 8000), (3500, 7010), (4500, 6020)]):
        meas_svc.add_pumping_entry(call, donor_master, declared_at=t + timedelta(hours=i), level_mm=str(donor_level))
        meas_svc.add_pumping_entry(partner, receiver_master, declared_at=t + timedelta(hours=i) + timedelta(minutes=5), level_mm=str(receiver_level))
    rows = meas_svc.compare_sides(call)
    assert len(rows) == 3 and all(r["shore"] is not None and r["ship"] is not None for r in rows)
    assert rows[1]["hourly_deviation"] == Decimal("891.000") - Decimal("900.000")  # partner − ship
    assert meas_svc.counterpart_label(call)[1].startswith("partner vessel (MT PARTNER)")
    summary = meas_svc.pumping_summary(call)
    assert summary["SHORE"]["count"] == 3 and summary["SHORE"]["sheets"][0].call_id == partner.pk


# ============================================================================ EXG-R-06 documents asked for at the announcement
@pytest.mark.django_db
def test_the_agency_asks_for_the_documents_it_expects_at_the_announcement_and_afterwards(world, client):
    call = make_call(world, expected_documents=["INSURANCE", "Q88", "NOPE"],
                     custom_documents=[{"label": "Certificat d'origine", "role": "COM", "hours_before_eta": 48},
                                       {"label": "", "role": "AGE"}])
    asked = list(call.tasks.filter(requested_at_creation=True).order_by("order"))
    assert [(t.document_type_code, t.role, t.title_fr) for t in asked] == [
        ("INSURANCE", "COM", "Fournir : Attestation d'assurance"), ("OTHER", "COM", "Fournir : Certificat d'origine")]
    assert asked[1].due_at == call.eta - timedelta(hours=48) and asked[0].co_roles == ["AGE"] and not asked[0].is_blocking
    assert "Q88" not in {t.document_type_code for t in asked}  # already expected by the common base (M0:02)
    assert JournalEntry.objects.filter(call=call, action="documents.requested").exists()
    # providing the document completes the task, like any task; asked for again afterwards from the documents tab
    doc_svc.upload_document(call, act(world, call, "COM"), "INSURANCE", pdf(), task=asked[0])
    asked[0].refresh_from_db()
    assert asked[0].status == TaskStatus.DONE
    login(client, world, "AGE")
    response = client.post(f"/escales/{call.pk}/action/documents_request/", {
        "expected_documents": ["LOI"], "custom_doc_label": ["Certificat phytosanitaire"], "custom_doc_role": ["AGE"],
        "custom_doc_hours": ["12"], "back": "?tab=documents"})
    assert response.status_code == 302
    assert call.tasks.filter(requested_at_creation=True).count() == 4
    html = client.get(f"/escales/{call.pk}/?tab=documents").content.decode()
    assert "Certificat phytosanitaire" in html and "Ask for other documents" in html
    # the announcement form lists the documents the templates require and the optional types
    html = client.get("/escales/nouvelle/").content.decode()
    assert "Documents expected" in html and 'name="expected_documents"' in html and 'name="custom_doc_label"' in html
    assert "M0:02" in html and 'data-template="MB1"' in html


# ============================================================================ EXG-R-01 tasks and requests carried out in line
@pytest.mark.django_db
def test_every_task_of_a_role_is_carried_out_from_the_tasks_tab(world, client):
    call = declared(world)
    # the terminal: a document task with its upload form, a milestone task with its form
    login(client, world, "TER")
    html = client.get(f"/escales/{call.pk}/?tab=taches").content.decode()
    assert "Upload and complete the task" in html and 'name="task_id"' in html
    # the agency files the berth request from the task line
    login(client, world, "AGE")
    html = client.get(f"/escales/{call.pk}/?tab=taches").content.decode()
    assert "File the request" in html and 'name="type" value="BERTH"' in html
    berth_task = call.tasks.get(template_code="M0", number="10")
    response = client.post(f"/escales/{call.pk}/action/request_create/", {"type": "BERTH", "back": f"?tab=taches#t{berth_task.pk}",
                                                                           "window_from": now(60 * 24 * 8).strftime("%Y-%m-%dT%H:%M"), "arrival_draft": "9.5"})
    assert response.status_code == 302
    berth_task.refresh_from_db()
    assert berth_task.status == TaskStatus.DONE and call.requests.filter(type__code="BERTH").exists()
    # the port authority decides it from its own task line
    login(client, world, "APO")
    html = client.get(f"/escales/{call.pk}/?tab=taches").content.decode()
    assert "Record the decision" in html


# ============================================================================ EXG-R-08 every kind of cargo
@pytest.mark.django_db
def test_a_dry_bulk_call_gets_its_own_models_checklist_and_forms(world):
    bulker = Vessel.objects.create(port=world.port, imo="9311012", name="MV CLINKER QUEEN", vessel_kind="BULK", dwt=55000)
    with pytest.raises(RuleViolation):
        make_call(world, operations=("M1",), cargo_kind="DRY")  # a liquid-bulk model on a dry-bulk call
    call = call_svc.create_call(world.users["AGE"], vessel=bulker, eta=now(60 * 24 * 5), requested_berth_kind="JETTY",
                                operations=["MB1"], parties=[(world.orgs.terminal, "TER"), (world.orgs.surveyor, "INS"), (world.orgs.owner, "COM")],
                                product="Clinker", quantity=38242, quantity_unit="MT", cargo_kind="DRY")
    codes = {t.code for t in call.tasks.all()}
    assert "MB1:B1.05" in codes and "MB1:B1.12" in codes and "M0:31b" in codes and "M0:29" not in codes and "M0:31" not in codes
    assert "M0:09c" in codes and "M0:09d" in codes
    # the checklist follows the BLU Code, the forms are those of dry bulk, not the tanker's
    force_done(call, ["M0:02", "M0:03", "M0:05", "M0:09b", "M0:09c", "M0:09d"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    checklist = cl_svc.open_checklist(call, act(world, call, "TER"))
    assert checklist.standard == "BLU" and checklist.items[0]["code"] == "1.1" and len(checklist.items) == 22
    offered = {f.code for f in forms.for_call(call)}
    assert {"DRAFT_SURVEY", "BLU_CHECKLIST", "BLU_AGREEMENT", "STOWAGE_PLAN", "CARGO_MANIFEST", "HOLD_INSPECTION", "TIME_SHEET"} <= offered
    assert not {"PUMPING_LOG", "SSSCL", "ULLAGE", "HOSES", "PAEC"} & offered
    assert "Draft survey" in forms.render(call, "DRAFT_SURVEY") and "Clinker" in forms.render(call, "CARGO_MANIFEST")
    # the quantities of a dry cargo: draft surveys and the shore scale, compared like the tanker's figures
    m = meas_svc.create_measurement(call, act(world, call, "INS"), "DRAFT_F", product="Clinker", unit="MT")
    meas_svc.add_value(m, master(world, call), "SHIP", "38200")
    meas_svc.add_value(m, act(world, call, "TER"), "SHORE", "38242")
    assert m.discrepancy()["exceeds"] is False
    # the time sheet names the operation and the milestones of the cargo operations drive the call
    from apps.registry.services import milestones as ms_svc

    force_done(call, ["M0:27", "M0:28", "M0:31b", "MB1:B1.04", "MB1:B1.05", "MB1:B1.06", "MB1:B1.07"])
    call.status = CallStatus.AT_BERTH
    call.atb = now(-60)
    call.save(update_fields=["status", "atb"])
    ms_svc.record_milestone(call, act(world, call, "TER"), "CARGO_OPS_START", now(-30))
    call.refresh_from_db()
    assert call.status == CallStatus.IN_OPERATION and call.t0 is not None
    assert "dry bulk discharge" in forms.render(call, "TIME_SHEET")


@pytest.mark.django_db
def test_containers_general_cargo_ro_ro_and_any_other_call(world):
    box_ship = Vessel.objects.create(port=world.port, imo="9074743", name="MSC TEST", vessel_kind="CONTAINER", dwt=90000)
    call = call_svc.create_call(world.users["AGE"], vessel=box_ship, eta=now(60 * 24 * 3), requested_berth_kind="JETTY",
                                operations=["MC1"], parties=[(world.orgs.terminal, "TER")], product="Tcs/Tcs",
                                quantity=1501, quantity_unit="MOVES", cargo_kind="CONTAINER")
    assert call.get_quantity_unit_display() and call.tasks.filter(template_code="MC1").count() == 13
    force_done(call, ["M0:02", "M0:03", "M0:05", "M0:09b", "M0:09c", "M0:09d"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    checklist = cl_svc.open_checklist(call, act(world, call, "TER"))
    assert checklist.standard == "CARGO" and checklist.items[0]["part"] == "A"
    offered = {f.code for f in forms.for_call(call)}
    assert {"CARGO_SAFETY_CHECKLIST", "BAY_PLAN", "DG_DECLARATION", "OUTTURN_REPORT", "TALLY_SHEET"} <= offered and "BLU_AGREEMENT" not in offered
    assert "Container bay plan" in forms.render(call, "BAY_PLAN")
    # ro-ro and the generic model for anything else
    car_carrier = Vessel.objects.create(port=world.port, imo="9074755", name="GRANDE TEST", vessel_kind="RORO")
    roro = call_svc.create_call(world.users["AGE"], vessel=car_carrier, eta=now(60 * 24 * 4), requested_berth_kind="JETTY",
                                operations=["MR1"], parties=[], product="Véhicules", quantity=1200, quantity_unit="UNIT", cargo_kind="RORO")
    assert roro.tasks.filter(template_code="MR1", number="R1.04").exists()
    warship = Vessel.objects.create(port=world.port, imo="9074767", name="RNV TEST", vessel_kind="NAVAL")
    other = call_svc.create_call(world.users["AGE"], vessel=warship, eta=now(60 * 24 * 2), requested_berth_kind="JETTY",
                                 operations=["MX1"], parties=[], product="Navire de guerre — relâche", cargo_kind="OTHER")
    assert other.tasks.filter(template_code="MX1").count() == 9 and "MATES_RECEIPT" not in {f.code for f in forms.for_call(other)}


# ============================================================================ EXG-R-07 placement conference and berth occupation
@pytest.mark.django_db
def test_the_board_is_the_placement_conference_and_the_occupation_plan(world, client):
    call = declared(world)
    doc_svc.upload_document(call, act(world, call, "AGE"), "FAL_FORMS", pdf())
    groups = dict((k, rows) for k, _l, rows in board.grouped(world.port, world.users["AGE"]))
    row = next(r for r in groups["expected"] if r["call"].pk == call.pk)
    assert row["fal"] is True and row["manifest"] is False and row["cargo"] == "Gasoil" and row["quantity"] == "30 000 MT"
    csv = board.to_csv(world.port, world.users["AGE"])
    assert "MT TEST SPIRIT" in csv and "OUI/YES" in csv
    plan = board.occupation(world.port, world.users["AGE"], now(-60 * 24 * 30), now(60 * 24 * 30))
    assert any(r["call"].pk == call.pk and r["state"] == "expected" and r["trader"] == "Test Owner" for r in plan)
    login(client, world, "CAP")
    assert "Placement conference" in client.get("/escales/port/").content.decode()
    assert client.get("/escales/port/?format=csv")["Content-Type"].startswith("text/csv")
    html = client.get("/escales/port/occupation/").content.decode()
    assert "Berth occupation plan" in html and "MT TEST SPIRIT" in html
    token = Token.objects.create(user=world.users["CAP"]).key
    assert client.get("/api/v1/board/occupation/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["results"]


# ============================================================================ EXG-R-10 vetting grid against the berth limits
@pytest.mark.django_db
def test_the_vetting_grid_reads_the_berth_limits_against_the_vessel(world):
    call = make_call(world)
    berth = world.port.berths.filter(kind="JETTY").first()
    berth.max_loa_m, berth.max_draft_m, berth.max_beam_m, berth.max_vessel_age_years = 187, 13, 32, 25
    berth.save()
    call.requested_berth = berth
    call.save(update_fields=["requested_berth"])
    v = call.vessel
    v.loa_m, v.draft_m, v.beam_m, v.built_year = Decimal("185.93"), Decimal("14.5"), Decimal("32.2"), 2005
    v.save()
    rows = {r["fr"]: r["status"] for r in vetting_rows(call)}
    assert rows["LOA maximale (m)"] == "Y" and rows["Tirant d'eau maximal au poste (m)"] == "K" and rows["Largeur maximale (m)"] == "N"
    assert vetting_verdict(vetting_rows(call))[1].startswith("UNSUITABLE")
    v.beam_m = Decimal("31.5")
    v.save()
    assert vetting_verdict(vetting_rows(call))[1].startswith("SUITABLE WITH CAUTIONS")
    assert "Vessel vetting checklist" in forms.render(call, "VETTING_CHECKLIST")
    assert "Pre-arrival exchange" in forms.render(call, "PAEC") and "Cargo handling plan" in forms.render(call, "CARGO_HANDLING_PLAN")


# ============================================================================ the announcement screen and the API
@pytest.mark.django_db
def test_the_announcement_screen_and_the_api_carry_the_new_fields(world, client):
    login(client, world, "AGE")
    html = client.get("/escales/nouvelle/").content.decode()
    for marker in ('name="cargo_kind"', 'name="validity_days"', 'name="sts_role"', 'name="partner_vessel"', 'name="party_access"', 'data-cargo="DRY"'):
        assert marker in html, marker
    eta = now(60 * 24 * 6)
    response = client.post("/escales/nouvelle/", {
        "vessel": "", "new_imo": "9074779", "new_name": "mv new bulker", "new_kind": "BULK", "new_flag": "Togo", "new_dwt": "30000",
        "cargo_kind": "DRY", "product": "Urée", "quantity": "30740", "quantity_unit": "MT", "kind": "JETTY",
        "operations": ["MB1"], "eta": eta.strftime("%Y-%m-%dT%H:%M"), "validity_days": "10", "op_MB1_geared": "YES",
        "party_role": ["TER"], "party_org": [str(world.orgs.terminal.pk)], "party_name": [""], "party_kind": [""], "party_email": [""],
        "party_phone": [""], "party_access": ["PARTIAL:taches,documents"], "custom_doc_label": ["Certificat d'origine"],
        "custom_doc_role": ["AGE"], "custom_doc_hours": ["24"]})
    assert response.status_code == 302, response.content[:500]
    page = client.get(response["Location"]).content.decode()
    call = world.port.calls.order_by("-pk").first()
    assert call is not None, page[page.find("flash"):page.find("flash") + 400]
    assert call.cargo_kind == "DRY" and call.validity_days == 10 and call.vessel.name == "MV NEW BULKER" and call.vessel.vessel_kind == "BULK"
    assert call.parties.get(organization=world.orgs.terminal).scopes == ["taches", "documents"]
    assert call.tasks.filter(requested_at_creation=True).count() == 1 and "MB1" in call.template_codes
    token = Token.objects.create(user=world.users["AGE"]).key
    created = client.post("/api/v1/calls/", {
        "vessel_imo": "9074779", "eta": now(60 * 24 * 7).isoformat(), "operating_area": "JETTY", "operations": ["MB2"],
        "cargo_kind": "DRY", "product": "Clinker", "quantity": 46300, "quantity_unit": "MT", "validity_days": 20,
        "operation_details": {"MB2": {"geared": "NO", "imsbc_group": "C"}},
        "parties": [{"organization_id": world.orgs.terminal.pk, "role": "TER", "access": "READ"}],
        "expected_documents": ["INSURANCE"], "custom_documents": [{"label": "Certificat d'origine", "role": "COM"}]},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert created.status_code == 201, created.content[:300]
    body = created.json()
    assert body["cargo_kind"] == "DRY" and body["validity"]["days"] == 20 and body["your_access"]["principal_agent"] is True
    assert next(p for p in body["parties"] if p["role"] == "TER")["access"] == "READ"
    assert body["billing_basis"]["validity_days"] == 20
