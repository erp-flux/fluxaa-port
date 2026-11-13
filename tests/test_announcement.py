"""Version 1.6 — the announcement adapts to the operation (FLX-CDC-002 v1.6, EXG-R-11): each model's own
questions, the double banking named at the announcement (the other vessel and its agency, of any agency), the
requests pre-filled from the announcement, the berth occupation known before asking."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core.models import Organization, User
from apps.registry.models import JournalEntry, Notification, PortCall, RequestStatus, RequestType, Vessel
from apps.registry.services import calls as call_svc
from apps.registry.services import exports, rights
from apps.registry.services import intake as intake_svc
from apps.registry.services import requests as req_svc
from apps.registry.services.context import actor_for_call
from apps.registry.services.errors import RuleViolation

from .conftest import act, force_done, make_call
from .test_web import login


def now(minutes=0):
    return timezone.now() + timedelta(minutes=minutes)


def second_agency(world, name="Second Agency"):
    org = Organization.objects.create(port=world.port, name=name, allowed_roles=["AGE"], email="second@agency.test")
    user = User.objects.create_user(email=f"{name.split()[0].lower()}@agency.test", password="pw-test-123456",
                                    full_name=f"User {name}", organization=org, roles=["AGE"])
    return org, user


def announcement(world, client, **fields):
    """The web form of the announcement, with the minimum the port requires, plus *fields*."""
    eta = now(60 * 24 * 6)
    data = {"vessel": str(world.vessel.pk), "cargo_kind": "LIQUID", "product": "Gasoil", "quantity": "30000", "quantity_unit": "MT",
            "kind": "JETTY", "operations": ["M1"], "eta": eta.strftime("%Y-%m-%dT%H:%M"),
            "etb": (eta + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M"), "etd": (eta + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M"),
            "validity_days": "10", "party_role": ["TER"], "party_org": [str(world.orgs.terminal.pk)], "party_name": [""],
            "party_kind": [""], "party_email": [""], "party_phone": [""], "party_access": ["FULL"],
            "custom_doc_label": [""], "custom_doc_role": ["AGE"], "custom_doc_hours": ["24"]}
    data.update(fields)
    return client.post("/escales/nouvelle/", data)


# ============================================================================ the model's own questions
@pytest.mark.django_db
def test_each_operation_model_asks_its_own_questions_and_the_answers_follow_the_call(world, client):
    login(client, world, "AGE")
    html = client.get("/escales/nouvelle/").content.decode()
    # one hidden block per model that asks something; its required questions only bind once it is shown
    assert html.count("data-intake=") >= 14 and 'data-intake="M4"' in html and 'name="op_M4_grade"' in html
    assert 'name="op_M4_quantity_mt" value="" data-required="1"' in html and "data-double-banking" in html
    # a required question of a chosen model without an answer is refused, the form comes back filled
    refused = announcement(world, client, operations=["M1", "M4"], op_M4_grade="VLSFO", op_M4_supplier="Bunker Co", op_M4_delivery_mode="BARGE",
                           op_M1_max_rate_m3h="1 200")
    assert refused.status_code == 200 and "M4" in refused.content.decode() and "Quantit" in refused.content.decode()
    assert 'value="Bunker Co"' in refused.content.decode() and world.port.calls.count() == 0
    # the answers are kept by model, typed, and the questions of models not chosen are ignored
    response = announcement(world, client, operations=["M1", "M4"], op_M4_grade="VLSFO", op_M4_quantity_mt="450", op_M4_supplier="Bunker Co",
                            op_M4_delivery_mode="BARGE", op_M4_terminal_agreement="1", op_M1_max_rate_m3h="1 200",
                            op_M1_inert_gas="YES", op_M7_works="ignored: M7 not chosen")
    assert response.status_code == 302, response.content[:400]
    call = world.port.calls.order_by("-pk").first()
    assert call.operation_details == {"M4": {"grade": "VLSFO", "quantity_mt": 450.0, "supplier": "Bunker Co", "delivery_mode": "BARGE",
                                             "terminal_agreement": True},
                                      "M1": {"max_rate_m3h": 1200.0, "inert_gas": "YES"}}
    overview = client.get(f"/escales/{call.pk}/").content.decode()
    assert "declare-a-l-annonce" in overview and "Bunker Co" in overview and "VLSFO" in overview
    # shown model by model in the port's order, the answers in the order of the questions (not of the stored object)
    shown = intake_svc.declared(call)
    assert [d["code"] for d in shown] == ["M1", "M4"]
    assert [label for label, _value in shown[1]["rows"]][:3] == ["Bunker grade(s)", "Total quantity (t)", "Intended bunker supplier"]
    # the bunkering request starts pre-filled with what the announcement said (same keys)
    requests_tab = client.get(f"/escales/{call.pk}/?tab=demandes&type=BUNKERING").content.decode()
    # a choice of the announcement carried into a free-text field of the request reads in words, not as a code
    assert 'name="grade" value="VLSFO 0.5%"' in requests_tab and 'name="quantity_mt" value="450"' in requests_tab
    assert 'name="supplier" value="Bunker Co"' in requests_tab and "pre-filled" in requests_tab.lower() or "prérempli" in requests_tab.lower()
    # the journal carries the answers
    assert JournalEntry.objects.filter(call=call, action="call.created", payload__operation_details__M4__grade="VLSFO").exists()


@pytest.mark.django_db
def test_the_answers_are_validated_against_the_model_s_questions(world):
    with pytest.raises(RuleViolation):
        intake_svc.parse_intake(world.port, ["M0", "M4"], {"op_M4_grade": "KEROSENE", "op_M4_quantity_mt": "10",
                                                            "op_M4_supplier": "x", "op_M4_delivery_mode": "BARGE"}.get)
    with pytest.raises(RuleViolation):
        intake_svc.parse_intake(world.port, ["M0", "MB1"], {"op_MB1_holds": "five", "op_MB1_geared": "YES"}.get)
    with pytest.raises(RuleViolation):
        intake_svc.parse_intake_mapping(world.port, ["M0", "M4"], {"M4": "not an object"})
    details = intake_svc.parse_intake_mapping(world.port, ["M0", "MB1"], {"MB1": {"holds": "5", "geared": "NO", "imsbc_group": "C"},
                                                                          "MC1": {"reefers": 3}})
    assert details == {"MB1": {"holds": 5, "geared": "NO", "imsbc_group": "C"}}
    assert intake_svc.parse_intake(world.port, ["M0", "M1"], {}.get) == {}


# ============================================================================ double banking at the announcement
@pytest.mark.django_db
def test_a_double_banking_names_the_vessel_at_the_berth_and_links_the_two_calls(world, client):
    inner = make_call(world, operations=("M1",))
    force_done(inner, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(inner, act(world, inner, "AGE"))
    outer_vessel = Vessel.objects.create(port=world.port, imo="9074731", name="MT OUTER", flag="Panama", vessel_type="Product tanker", dwt=20000)
    login(client, world, "AGE")
    html = client.get("/escales/nouvelle/").content.decode()
    assert f'<option value="{inner.pk}"' in html and "MT TEST SPIRIT" in html  # the port's board names the vessel at the berth
    # the berth occupation is known before asking: the fragment the form fetches
    berth = world.port.berths.filter(kind="JETTY").first()
    inner.requested_berth = berth
    inner.save(update_fields=["requested_berth"])
    fragment = client.get("/escales/nouvelle/occupation/", {"requested_berth": berth.pk, "eta": inner.eta.strftime("%Y-%m-%dT%H:%M"),
                                                           "etb": inner.etb.strftime("%Y-%m-%dT%H:%M"), "etd": inner.etd.strftime("%Y-%m-%dT%H:%M")}).content.decode()
    assert "data-berth-occupation" in fragment and inner.reference in fragment and "M9" in fragment
    # an announcement with the module M9 and no other vessel is refused
    refused = announcement(world, client, vessel=str(outer_vessel.pk), operations=["M1"], modules=["M9"], op_M9_purpose="LIGHTERING",
                           op_M9_duration_h="12", op_M9_loading_condition="ballast → loaded")
    assert refused.status_code == 200 and world.port.calls.count() == 1
    response = announcement(world, client, vessel=str(outer_vessel.pk), operations=["M1"], modules=["M9"], db_position="OUTER",
                            db_partner_call=str(inner.pk), op_M9_purpose="LIGHTERING", op_M9_duration_h="12",
                            op_M9_loading_condition="ballast → loaded", op_M9_fenders_by="TERMINAL")
    assert response.status_code == 302, response.content[:400]
    outer = world.port.calls.order_by("-pk").first()
    inner.refresh_from_db()
    assert outer.linked_call_id == inner.pk and outer.link_kind == "OUTER" and "M9" in outer.template_codes
    assert inner.linked_call_id == outer.pk and inner.link_kind == "INNER"  # the agency links its own calls at once
    assert outer.operation_details["M9"]["purpose"] == "LIGHTERING" and outer.operation_details["M9"]["duration_h"] == 12.0
    overview = client.get(f"/escales/{outer.pk}/").content.decode()
    assert "accostage-a-couple" in overview and inner.reference in overview
    # the other vessel's file is told; the double-banking request starts pre-filled with the inner vessel
    assert Notification.objects.filter(call=inner, dedupe_key=f"double_banking:{outer.pk}:{inner.pk}").exists()
    rtype = RequestType.objects.get(port=world.port, code="DOUBLE_BANKING")
    prefill = intake_svc.prefill_for_request(outer, rtype)
    assert prefill["purpose"] == "Lightering or top-off at the berth" and prefill["duration_h"] == 12.0 and "MT TEST SPIRIT" in prefill["inner_vessel"]
    tasks_tab = client.get(f"/escales/{outer.pk}/?tab=taches").content.decode()
    assert 'name="inner_vessel" value="MT TEST SPIRIT' in tasks_tab


@pytest.mark.django_db
def test_another_agency_s_vessel_at_the_berth_is_named_and_the_link_waits_for_the_harbour_master(world, client):
    inner = make_call(world, operations=("M1",))
    force_done(inner, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(inner, act(world, inner, "AGE"))
    second, second_user = second_agency(world)
    outer_vessel = Vessel.objects.create(port=world.port, imo="9074731", name="MT OUTER", flag="Panama", vessel_type="Product tanker", dwt=20000)
    outer = call_svc.create_call(second_user, vessel=outer_vessel, eta=inner.eta, requested_berth_kind="JETTY", operations=["M1"],
                                 modules=["M9"], parties=[(world.orgs.terminal, "TER")], etb=inner.etb, etd=inner.etd,
                                 product="Gasoil", quantity=5000, operation_details={"M9": {"purpose": "BUNKER", "duration_h": 6, "loading_condition": "x"}},
                                 db_partner={"call": inner, "position": "OUTER"})
    inner.refresh_from_db()
    # one-way: the outer file points at the inner vessel, the inner file is told but not linked yet
    assert outer.linked_call_id == inner.pk and outer.link_kind == "OUTER" and inner.linked_call_id is None
    assert Notification.objects.filter(call=inner, user=world.users["AGE"], dedupe_key=f"double_banking:{outer.pk}:{inner.pk}").exists()
    assert Notification.objects.filter(call=inner, user=world.users["CAP"]).filter(dedupe_key=f"double_banking:{outer.pk}:{inner.pk}").exists()
    login(client, world, "AGE")
    overview = client.get(f"/escales/{inner.pk}/").content.decode()
    assert "accostage-a-couple" not in overview  # nothing on the inner file until the harbour master authorises
    # the harbour master's double-banking authorization makes the link reciprocal
    force_done(outer, ["M9:9.02", "M9:9.04", "M9:9.06", "M9:9.08"])
    req = req_svc.create_request(outer, actor_for_call(outer, user=second_user), "DOUBLE_BANKING",
                                 data={"purpose": "Soutage", "duration_h": "6", "inner_vessel": "MT TEST SPIRIT"})
    req_svc.decide_request(req, act(world, outer, "CAP"), RequestStatus.APPROVED)
    inner.refresh_from_db()
    assert inner.linked_call_id == outer.pk and inner.link_kind == "INNER"
    assert JournalEntry.objects.filter(call=inner, action="call.linked").exists()
    overview = client.get(f"/escales/{inner.pk}/").content.decode()
    assert "accostage-a-couple" in overview and outer.reference in overview
    # a call the board does not show (a draft) cannot be named by another agency
    draft = make_call(world, operations=("M1",))
    with pytest.raises(RuleViolation):
        call_svc.create_call(second_user, vessel=outer_vessel, eta=inner.eta, requested_berth_kind="JETTY", operations=["M1"],
                             modules=["M9"], parties=[(world.orgs.terminal, "TER")], product="Gasoil",
                             db_partner={"call": draft, "position": "OUTER"})


@pytest.mark.django_db
def test_the_other_vessel_without_a_call_gets_its_own_under_its_own_agency(world):
    second, second_user = second_agency(world)
    other = Vessel.objects.create(port=world.port, imo="9074731", name="MT OTHER", flag="Panama", vessel_type="Product tanker", dwt=20000)
    call = make_call(world, operations=("M1",), modules=("M9",), db_partner={"vessel": other, "agency": second, "position": "INNER"},
                     operation_details={"M9": {"purpose": "SIMOPS", "duration_h": 20, "loading_condition": "both loaded"}})
    partner = call.linked_call
    assert partner is not None and partner.vessel_id == other.pk and partner.agency_id == second.pk
    assert call.link_kind == "INNER" and partner.link_kind == "OUTER" and partner.linked_call_id == call.pk
    assert "M9" in partner.template_codes and partner.operation_details == {"M9": {"purpose": "SIMOPS", "duration_h": 20, "loading_condition": "both loaded"}}
    assert partner.parties.filter(organization=second, role="AGE").exists() and partner.parties.filter(organization=world.orgs.agency, role="AGE").exists()
    assert rights.is_principal_agent(actor_for_call(partner, user=second_user), partner)
    assert Notification.objects.filter(call=partner, user=second_user, dedupe_key=f"double_banking:{partner.pk}:nominated").exists()
    with pytest.raises(RuleViolation):
        make_call(world, operations=("M1",), modules=("M9",), db_partner={"vessel": world.vessel, "position": "OUTER"})  # itself
    with pytest.raises(RuleViolation):
        make_call(world, operations=("M1",), modules=("M9",), db_partner={"vessel": other, "position": "SIDEWAYS"})


@pytest.mark.django_db
def test_the_api_announces_with_the_answers_and_the_double_banking(world, client):
    inner = make_call(world, operations=("M1",))
    force_done(inner, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(inner, act(world, inner, "AGE"))
    Vessel.objects.create(port=world.port, imo="9074731", name="MT OUTER", flag="Panama", vessel_type="Product tanker", dwt=20000)
    token = Token.objects.create(user=world.users["AGE"]).key
    created = client.post("/api/v1/calls/", {
        "vessel_imo": "9074731", "eta": now(60 * 24 * 7).isoformat(), "operating_area": "JETTY", "operations": ["M1"], "modules": ["M9"],
        "cargo_kind": "LIQUID", "product": "Gasoil", "quantity": 5000, "quantity_unit": "MT", "validity_days": 10,
        "parties": [{"organization_id": world.orgs.terminal.pk, "role": "TER"}],
        "operation_details": {"M9": {"purpose": "LIGHTERING", "duration_h": 10, "loading_condition": "ballast"}, "M1": {"max_rate_m3h": 900}},
        "double_banking": {"position": "OUTER", "call_reference": inner.reference}},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert created.status_code == 201, created.content[:400]
    body = created.json()
    assert body["operation_details"]["M9"]["purpose"] == "LIGHTERING" and body["operation_details"]["M1"]["max_rate_m3h"] == 900
    assert body["linked_call"] == {"reference": inner.reference, "vessel": "MT TEST SPIRIT", "kind": "OUTER", "reciprocal": True, "confirmed": True}
    assert any(d["template"] == "M9" for d in body["declared"])
    refused = client.post("/api/v1/calls/", {
        "vessel_imo": "9074731", "eta": now(60 * 24 * 7).isoformat(), "operating_area": "JETTY", "operations": ["M1", "M4"],
        "operation_details": {"M4": {"grade": "VLSFO"}}}, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert refused.status_code in (400, 409) and "quantit" in refused.content.decode().lower()
    outer = PortCall.objects.get(reference=body["reference"])
    payload, _files = exports.call_payload(outer, act(world, outer, "AGE"))
    assert payload["link_kind"] == "OUTER" and payload["operation_details"]["M9"]["purpose"] == "LIGHTERING"
    assert exports.FORMAT_VERSION == "fluxaa-port-export/1.3"


# ============================================================================ the parties an operation brings, the berth's limits
@pytest.mark.django_db
def test_the_announcement_proposes_the_parties_of_the_operation_and_reads_the_berth_limits(world, client):
    from decimal import Decimal

    from apps.core.parties import PARTIES_BY_OPERATION, PARTY_KINDS, parties_for_operation

    kinds = {code for code, _r, _fr, _en in PARTY_KINDS}
    for code, hints in PARTIES_BY_OPERATION.items():
        for kind, _fr, _en in hints:
            assert kind in kinds, (code, kind)  # every suggestion is a kind of the open catalogue, with its role
    assert [h["role"] for h in parties_for_operation("M3")][0] == "PRE" and "POAC" in parties_for_operation("M3")[0]["label"]
    assert {h["role"] for h in parties_for_operation("MB1")} == {"TER", "PRE", "INS", "COM"}
    login(client, world, "AGE")
    html = client.get("/escales/nouvelle/").content.decode()
    # the hints are in the page, one per template, hidden until the model is ticked (the script shows them)
    assert "data-party-hints" in html and 'data-add-party-role="PRE"' in html and 'li data-template="M4" hidden' in html
    assert html.count('data-add-party-role=') >= 40
    # the vessel against the berth's acceptance limits, read before the berth is asked for
    berth = world.port.berths.filter(kind="JETTY").first()
    berth.max_loa_m, berth.max_draft_m, berth.max_dwt, berth.cargo_kinds = Decimal("200.0"), Decimal("12.00"), 50000, ["LIQUID"]
    berth.save()
    world.vessel.loa_m, world.vessel.draft_m = Decimal("183.0"), Decimal("12.50")
    world.vessel.save()
    eta = now(60 * 24 * 6)
    params = {"requested_berth": berth.pk, "eta": eta.strftime("%Y-%m-%dT%H:%M"), "etd": (eta + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M"),
              "vessel": world.vessel.pk, "cargo_kind": "LIQUID"}
    fragment = client.get("/escales/nouvelle/occupation/", params).content.decode()
    assert "data-berth-fit" in fragment and "183" in fragment and "✓" in fragment and "✗" not in fragment
    assert "SUITABLE WITH CAUTIONS" in fragment or "APTE SOUS VIGILANCE" in fragment  # the draft is a caution, not a bar
    assert "data-berth-kind" not in fragment
    # a berth that does not receive the kind of cargo chosen says so; a new vessel is read by its DWT alone
    fragment = client.get("/escales/nouvelle/occupation/", {**params, "cargo_kind": "DRY", "vessel": "", "new_imo": "9074731",
                                                           "new_name": "MV NEW", "new_dwt": "60000"}).content.decode()
    assert "data-berth-kind" in fragment and "data-berth-fit" in fragment and "60000" in fragment and "✗" in fragment
    assert "UNSUITABLE" in fragment or "INAPTE" in fragment


# ============================================================================ STS: the mother vessel of another agency
@pytest.mark.django_db
def test_an_sts_partner_of_another_agency_is_named_from_the_board_and_confirmed_by_the_harbour_master(world, client):
    from apps.registry.services import measurements as meas_svc

    # the mother vessel: announced and declared by the first agency at the STS area, as the donor
    daughter0 = Vessel.objects.create(port=world.port, imo="9074731", name="MT DAUGHTER ONE", flag="Panama", vessel_type="Product tanker", dwt=20000)
    mother = make_call(world, operations=("M3",), kind="STS_AREA", sts_role="DONOR",
                       sts_partner={"vessel": daughter0, "agency": None})
    force_done(mother, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(mother, act(world, mother, "AGE"))
    first = mother.linked_call
    assert first is not None and first.sts_role == "RECEIVER" and call_svc.link_confirmed(mother) and call_svc.link_confirmed(first)
    # a second daughter vessel, of another agency, names the mother from the port's board
    org2, user2 = second_agency(world)
    daughter = Vessel.objects.create(port=world.port, imo="9074743", name="MT DAUGHTER TWO", flag="Togo", vessel_type="Product tanker", dwt=15000)
    client.force_login(user2)
    html = client.get("/escales/nouvelle/").content.decode()
    assert "Calls of the port — other agencies" in html and f'<option value="{mother.pk}"' in html and "MT TEST SPIRIT" in html
    eta = now(60 * 24 * 5)
    response = client.post("/escales/nouvelle/", {
        "vessel": str(daughter.pk), "cargo_kind": "LIQUID", "product": "Gasoil", "quantity": "12000", "quantity_unit": "MT", "kind": "STS_AREA",
        "operations": ["M3"], "linked_call": str(mother.pk), "eta": eta.strftime("%Y-%m-%dT%H:%M"), "validity_days": "10",
        "party_role": ["TER"], "party_org": [""], "party_name": [""], "party_kind": [""], "party_email": [""], "party_phone": [""],
        "party_access": ["FULL"], "custom_doc_label": [""], "custom_doc_role": ["AGE"], "custom_doc_hours": ["24"]})
    assert response.status_code == 302, response.content[:600]
    second = PortCall.objects.filter(vessel=daughter).get()
    mother.refresh_from_db()
    # one-way: the daughter names the mother, takes the other side of the transfer; the mother's own link is untouched
    assert second.linked_call_id == mother.pk and second.link_kind == "STS" and second.sts_role == "RECEIVER"
    assert mother.linked_call_id == first.pk and not call_svc.link_confirmed(second)
    assert Notification.objects.filter(call=mother, dedupe_key=f"sts_link:{second.pk}:{mother.pk}").exists()
    # nothing of the mother's file is read through an unconfirmed link, and her file cannot be opened
    assert meas_svc.counterpart_entries(second)[1] == []
    overview = client.get(f"/escales/{second.pk}/").content.decode()
    assert 'id="transbordement"' in overview and mother.reference in overview and "to be confirmed" in overview
    assert f'href="/escales/{mother.pk}/"' not in overview and client.get(f"/escales/{mother.pk}/").status_code == 404
    # two donors are not partners
    third_vessel = Vessel.objects.create(port=world.port, imo="9074755", name="MT WRONG SIDE", flag="Togo", vessel_type="Product tanker", dwt=9000)
    with pytest.raises(RuleViolation):
        call_svc.create_call(user2, vessel=third_vessel, eta=eta, requested_berth_kind="STS_AREA", operations=["M3"],
                             linked_call=mother, link_kind="STS", sts_role="DONOR")
    # the mother's file lists the vessels naming her once they are declared (a draft is its agency's own)
    login(client, world, "AGE")
    assert 'id="navires-lies"' not in client.get(f"/escales/{mother.pk}/").content.decode()
    force_done(second, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(second, actor_for_call(second, user=user2))
    page = client.get(f"/escales/{mother.pk}/").content.decode()
    assert 'id="navires-lies"' in page and "MT DAUGHTER TWO" in page and second.reference in page
    # the harbour master's STS area and window authorization confirms the link
    req = req_svc.create_request(second, actor_for_call(second, user=user2), "STS_ZONE",
                                 {"partner_vessel": "MT TEST SPIRIT", "window_from": now(60 * 24 * 5).isoformat(),
                                  "window_to": now(60 * 24 * 6).isoformat(), "poac": "Capt. A. Mensah"})
    req_svc.decide_request(req, act(world, second, "CAP"), RequestStatus.APPROVED)
    assert call_svc.link_confirmed(second)
    mother.refresh_from_db()
    assert mother.linked_call_id == first.pk  # the mother keeps her first partner; the second is confirmed by the authorization
    # the API says who names the call and whether the link stands
    token, _created = Token.objects.get_or_create(user=world.users["AGE"])
    body = client.get(f"/api/v1/calls/{mother.reference}/", HTTP_AUTHORIZATION=f"Bearer {token.key}").json()
    assert [n["reference"] for n in body["named_by"]] == [second.reference] and body["linked_call"]["confirmed"] is True


# ============================================================================ what a request may start with, and who reads the answers
@pytest.mark.django_db
def test_a_request_starts_only_with_what_its_own_model_and_the_call_say(world):
    """The volume of ballast is not the volume of waste, the duration of a repair is not the duration of a double
    banking: an answer is carried into a request only from the model whose tasks raise that request."""
    berth = world.port.berths.filter(kind="JETTY").first()
    call = make_call(world, operations=("M2", "M5", "M7"), requested_berth=berth, operation_details={
        "M2": {"last_cargoes": "gasoil / jet A-1 / gasoil", "tank_condition": "CLEAN"},
        "M5": {"volume_m3": 3200.0, "method": "D2"},
        "M7": {"works": "Overhaul of main engine unit 3", "hot_work": "NO", "immobilisation": "YES", "duration_h": 18.0}})

    def prefill(code):
        return intake_svc.prefill_for_request(call, RequestType.objects.get(port=world.port, code=code))

    # from the model that raises the request — a choice read in words in a free-text field
    assert prefill("BALLAST_DISCHARGE") == {"volume_m3": 3200, "method": "D-2 — treatment system (BWMS) in service"}
    assert prefill("IMMOBILIZATION") == {"duration_h": 18} and prefill("HOT_WORK") == {"works": "Overhaul of main engine unit 3"}
    # a key shared by name only is not carried: waste ≠ ballast, gas freeing ≠ ballast method, double banking ≠ repair
    assert prefill("WASTE_COLLECTION") == {} and prefill("GAS_FREEING") == {} and prefill("DOUBLE_BANKING") == {}
    assert prefill("BERTH") == {} and prefill("BUNKERING") == {}
    # the vetting request reads the call itself (product, quantity, berth) and the last three cargoes, declared once
    assert prefill("VESSEL_ACCEPTANCE") == {"product": "Gasoil", "quantity": 30000, "requested_berth": berth.code,
                                            "last_cargoes": "gasoil / jet A-1 / gasoil"}


@pytest.mark.django_db
def test_a_provider_does_not_read_what_the_agency_declared_at_the_announcement(world, client):
    """Bunker supplier, grade and quantity, last cargoes… are commercial like the product and the quantity: a
    provider named on the call reads what concerns it in the request addressed to it, not the announcement."""
    call = make_call(world, operations=("M1", "M4"), operation_details={
        "M4": {"grade": "VLSFO", "quantity_mt": 450.0, "supplier": "Bunker Co", "delivery_mode": "BARGE"}})
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))  # a draft is the agency's alone
    assert not rights.can_see_full_call(act(world, call, "PRE")) and rights.can_see_full_call(act(world, call, "TER"))
    # the terminal reads it, on the page and through the API
    login(client, world, "TER")
    overview = client.get(f"/escales/{call.pk}/").content.decode()
    assert "declare-a-l-annonce" in overview and "Bunker Co" in overview
    ter = Token.objects.create(user=world.users["TER"]).key
    body = client.get(f"/api/v1/calls/{call.reference}/", HTTP_AUTHORIZATION=f"Bearer {ter}").json()
    assert body["operation_details"]["M4"]["supplier"] == "Bunker Co" and body["declared"][0]["template"] == "M4"
    # the provider sees the call it serves, not the announcement's answers
    client.logout()
    login(client, world, "PRE")
    page = client.get(f"/escales/{call.pk}/")
    assert page.status_code == 200 and "declare-a-l-annonce" not in page.content.decode() and "Bunker Co" not in page.content.decode()
    pre = Token.objects.create(user=world.users["PRE"]).key
    answer = client.get(f"/api/v1/calls/{call.reference}/", HTTP_AUTHORIZATION=f"Bearer {pre}")
    assert answer.status_code == 200 and "operation_details" not in answer.json() and "declared" not in answer.json()
    assert "product" not in answer.json() and "Bunker Co" not in answer.content.decode()


@pytest.mark.django_db
def test_a_decimal_answer_prefills_the_request_in_french_too(world, client):
    """450.5 t declared at the announcement: a number input given the French « 450,5 » would be emptied by the browser."""
    call = make_call(world, operations=("M1", "M4"), operation_details={
        "M4": {"grade": "MGO", "quantity_mt": 450.5, "supplier": "Bunker Co", "delivery_mode": "TRUCK"}})
    user = login(client, world, "AGE")
    user.language = "fr"
    user.save(update_fields=["language"])
    page = client.get(f"/escales/{call.pk}/?tab=demandes&type=BUNKERING").content.decode()
    assert 'name="quantity_mt" value="450.5"' in page and "450,5" not in page.split('name="quantity_mt"')[1][:40]
    assert "prérempli" in page.lower()
    # where it is read, not typed, the same number is written the French way
    assert "450,5" in client.get(f"/escales/{call.pk}/").content.decode()


# ============================================================================ the second vessel's agency, a refused announcement
@pytest.mark.django_db
def test_the_second_vessel_s_agency_may_be_one_the_port_does_not_know_yet(world, client):
    """A transfer names the other vessel and its agency — which is not necessarily the announcing one, nor one already
    registered: named on the spot, it gets the other vessel's call, and the port's administrator is told."""
    admin = world.users["DIR"]
    admin.is_port_admin = True
    admin.save(update_fields=["is_port_admin"])
    login(client, world, "AGE")
    page = client.get("/escales/nouvelle/").content.decode()
    assert 'name="partner_agency_name"' in page and 'name="db_agency_name"' in page
    eta = now(60 * 24 * 6)
    response = announcement(world, client, kind="STS_AREA", operations=["M3"], sts_role="DONOR", partner_imo="9074755",
                            partner_name="MT Daughter New", partner_flag="Togo", partner_kind="TANKER_PRODUCT", partner_dwt="18000",
                            partner_agency_name="  Golfe   Shipping Agency ", partner_agency_email="OPS@golfe-shipping.test",
                            op_M3_window_from=(eta + timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M"),
                            op_M3_window_to=(eta + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M"), op_M3_poac="Capt. Test — STS Services")
    assert response.status_code == 302, response.content.decode()[:800]
    call = world.port.calls.get(vessel=world.vessel)
    partner = call.linked_call
    agency = Organization.objects.get(port=world.port, name="Golfe Shipping Agency")
    assert agency.allowed_roles == ["AGE"] and agency.kind == "SHIPPING_AGENT" and agency.email == "ops@golfe-shipping.test"
    # the other vessel has its own call under its own agency, the other side of the transfer; the announcing agency
    # keeps an associated-agency access on it — and cannot declare it
    assert partner.vessel.imo == "9074755" and partner.agency_id == agency.pk and partner.sts_role == "RECEIVER"
    assert partner.parties.filter(organization=world.orgs.agency, role="AGE", revoked_at__isnull=True).exists()
    assert not rights.is_principal_agent(act(world, partner, "AGE"), partner)
    with pytest.raises(Exception, match="principal agent"):
        call_svc.declare_call(partner, act(world, partner, "AGE"))
    # nobody can sign in for that agency yet: the port's administrator is told, and so is the announcing agent
    note = Notification.objects.get(user=admin, dedupe_key=f"agency_without_account:{agency.pk}:{partner.pk}")
    assert note.call_id is None and "Golfe Shipping Agency" in note.title_en and f"/admin/core/organization/{agency.pk}/change/" == note.url
    followed = client.get(response.url).content.decode()
    assert "has no account on the platform yet" in followed and partner.reference in followed
    assert JournalEntry.objects.filter(action="organization.created", object_id=agency.pk).exists()
    # an agency already registered is found by its name, never duplicated; the API names one the same way
    outer_vessel = Vessel.objects.create(port=world.port, imo="9074767", name="MT OUTER API", flag="Panama", vessel_type="Product tanker", dwt=9000)
    Vessel.objects.create(port=world.port, imo="9074779", name="MT INNER API", flag="Panama", vessel_type="Product tanker", dwt=30000)
    token = Token.objects.create(user=world.users["AGE"]).key
    created = client.post("/api/v1/calls/", {
        "vessel_imo": outer_vessel.imo, "eta": now(60 * 24 * 9).isoformat(), "operating_area": "JETTY", "operations": ["M1"], "modules": ["M9"],
        "cargo_kind": "LIQUID", "product": "Gasoil", "quantity": 4000, "validity_days": 10,
        "operation_details": {"M9": {"purpose": "LIGHTERING", "duration_h": 8, "loading_condition": "ballast → loaded"}},
        "double_banking": {"position": "OUTER", "vessel_imo": "9074779", "agency_name": "golfe shipping agency"}},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert created.status_code == 201, created.content[:600]
    inner = PortCall.objects.get(vessel__imo="9074779")
    assert inner.agency_id == agency.pk and inner.link_kind == "INNER" and Organization.objects.filter(port=world.port, name__iexact="golfe shipping agency").count() == 1


@pytest.mark.django_db
def test_a_refused_announcement_registers_nothing_and_comes_back_as_typed(world, client):
    """Whatever refuses it — here a required answer of the bunkering model, missed after the two new vessels, a new
    party and the partner's new agency were registered —, nothing is left half registered and nothing typed is lost."""
    login(client, world, "AGE")
    vessels, orgs = Vessel.objects.count(), Organization.objects.count()
    refused = announcement(world, client, vessel="", new_imo="9074755", new_name="MT Brand New", new_flag="Togo", new_kind="TANKER_PRODUCT",
                           new_dwt="18000", kind="STS_AREA", operations=["M3", "M4"], sts_role="DONOR", partner_imo="9074767",
                           partner_name="MT Other New", partner_flag="Togo", partner_kind="TANKER_PRODUCT",
                           partner_agency_name="Golfe Shipping Agency", partner_agency_email="ops@golfe-shipping.test",
                           party_role=["INS"], party_org=["new"], party_name=["Brand New Laboratory"], party_kind=["Laboratoire d'analyses"],
                           op_M3_poac="Capt. Test — STS Services", op_M4_grade="VLSFO", op_M4_supplier="Bunker Co", op_M4_delivery_mode="BARGE")
    body = refused.content.decode()
    assert refused.status_code == 200 and world.port.calls.count() == 0
    assert Vessel.objects.count() == vessels and Organization.objects.count() == orgs
    assert not JournalEntry.objects.filter(action="organization.created").exists() and Notification.objects.count() == 0
    # the reason is said (the bunker quantity is required), and the form comes back as it was typed
    assert "M4" in body and "Quantit" in body
    assert 'value="9074755"' in body and 'value="MT BRAND NEW"' not in body and 'value="MT Brand New"' in body
    assert 'value="9074767"' in body and 'value="Golfe Shipping Agency"' in body and 'value="ops@golfe-shipping.test"' in body
    assert 'value="Brand New Laboratory"' in body and 'value="Capt. Test — STS Services"' in body
    # the same form with the missing answer goes through: the IMO numbers were not left registered by the refusal
    response = announcement(world, client, vessel="", new_imo="9074755", new_name="MT Brand New", new_flag="Togo", new_kind="TANKER_PRODUCT",
                            new_dwt="18000", kind="STS_AREA", operations=["M3", "M4"], sts_role="DONOR", partner_imo="9074767",
                            partner_name="MT Other New", partner_flag="Togo", partner_kind="TANKER_PRODUCT",
                            partner_agency_name="Golfe Shipping Agency", partner_agency_email="ops@golfe-shipping.test",
                            party_role=["INS"], party_org=["new"], party_name=["Brand New Laboratory"], party_kind=["Laboratoire d'analyses"],
                            op_M3_poac="Capt. Test — STS Services", op_M4_grade="VLSFO", op_M4_supplier="Bunker Co", op_M4_delivery_mode="BARGE",
                            op_M4_quantity_mt="450")
    assert response.status_code == 302, response.content.decode()[:800]
    assert Vessel.objects.count() == vessels + 2 and world.port.calls.count() == 2


@pytest.mark.django_db
def test_the_api_refuses_an_invalid_record_as_the_caller_s_mistake_and_registers_nothing(world, client):
    """An organisation named with an e-mail that is not one: a 400 said field by field, never a server error — and
    the organisation named just before it in the same request is not left registered."""
    token = Token.objects.create(user=world.users["AGE"]).key
    orgs = Organization.objects.count()
    answer = client.post("/api/v1/calls/", {
        "vessel_imo": world.vessel.imo, "eta": now(60 * 24 * 7).isoformat(), "operating_area": "JETTY", "operations": ["M1"],
        "cargo_kind": "LIQUID", "product": "Gasoil", "quantity": 5000, "validity_days": 10,
        "parties": [{"name": "First New Surveyor", "role": "INS"}, {"name": "Second New Lab", "role": "INS", "email": "not-an-e-mail"}]},
        content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert answer.status_code == 400, answer.content[:400]
    body = answer.json()
    assert body["code"] == "validation_error" and "email" in body["details"]
    assert Organization.objects.count() == orgs and world.port.calls.count() == 0
