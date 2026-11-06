"""The parties of a call are an open list: any number of organisations, registered in the port or named on the
spot with their kind (suggested or free), invited at the announcement or later, and convened with their own way
in at the declaration."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.core.models import Organization
from apps.core.parties import PARTY_KINDS, kinds_for_role, normalize_kind
from apps.registry.models import JournalEntry
from apps.registry.services import calls as call_svc
from apps.registry.services.context import port_actor
from apps.registry.services.errors import PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call
from .test_web import login


def test_the_catalogue_of_party_kinds_is_a_suggestion_not_a_restriction():
    assert len(PARTY_KINDS) >= 50 and {role for _c, role, _fr, _en in PARTY_KINDS} >= {"AGE", "NAV", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "PRE"}
    assert {code for code, _fr, _en in kinds_for_role("PRE")} >= {"STS_PROVIDER", "BUNKER_SUPPLIER", "WASTE_CONTRACTOR", "SHIP_CHANDLER", "DIVING"}
    assert {code for code, _fr, _en in kinds_for_role("INS")} >= {"CARGO_SURVEYOR", "LABORATORY", "CLASS_SOCIETY", "MARINE_CHEMIST"}
    # a known label, in either language and whatever the case, becomes its code; anything else stays as typed
    assert normalize_kind("laboratoire d'analyses") == "LABORATORY" and normalize_kind("Laboratory") == "LABORATORY"
    assert normalize_kind("BUNKER_SUPPLIER") == "BUNKER_SUPPLIER"
    assert normalize_kind("Société de nettoyage de citernes à Freetown") == "Société de nettoyage de citernes à Freetown"
    assert normalize_kind("  ") == ""


@pytest.mark.django_db
def test_the_agency_announces_a_call_with_any_number_of_parties_registered_or_new(world, client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    login(client, world, "AGE")
    page = client.get("/escales/nouvelle/")
    assert page.status_code == 200 and b"data-parties" in page.content and b"kinds-PRE" in page.content
    assert b"Test Waste" in page.content and b"new organisation" in page.content
    eta = (timezone.now() + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M")
    response = client.post("/escales/nouvelle/", {
        "vessel": world.vessel.pk, "kind": "JETTY", "operations": ["M1"], "eta": eta, "product": "Gasoil",
        "quantity": "25000", "quantity_unit": "MT",
        # six rows: two registered organisations, three new ones (two of the same role), one empty row
        "party_role": ["TER", "INS", "INS", "PRE", "PRE", "COM"],
        "party_org": [str(world.orgs.terminal.pk), str(world.orgs.surveyor.pk), "new", "new", "new", ""],
        "party_name": ["", "", "Sierra Petroleum Laboratory", "Freetown Pilots & Tugs", "Kissy Bunkers Ltd", ""],
        "party_kind": ["", "", "Laboratoire d'analyses", "Pilotage and towage, Kissy", "bunker supplier", ""],
        "party_email": ["", "", "lab@spl.test", "", "ops@kissybunkers.test", ""],
        "party_phone": ["", "", "+232 76 000 000", "", "", ""],
    })
    assert response.status_code == 302, response.content.decode()[:500]
    call = world.vessel.calls.latest("created_at")
    roles = sorted((p.organization.name, p.role) for p in call.parties.filter(revoked_at=None))
    assert ("Test Terminal", "TER") in roles and ("Test Surveyor", "INS") in roles
    assert ("Sierra Petroleum Laboratory", "INS") in roles and ("Freetown Pilots & Tugs", "PRE") in roles and ("Kissy Bunkers Ltd", "PRE") in roles
    assert ("Port Authority", "CAP") in roles  # the port's default parties still come automatically
    lab = Organization.objects.get(port=world.port, name="Sierra Petroleum Laboratory")
    assert lab.kind == "LABORATORY" and lab.kind_label in ("Laboratoire d'analyses", "Laboratory") and lab.allowed_roles == ["INS"]
    assert lab.email == "lab@spl.test" and lab.phone == "+232 76 000 000" and lab.is_active
    pilots = Organization.objects.get(port=world.port, name="Freetown Pilots & Tugs")
    assert pilots.kind == "Pilotage and towage, Kissy"  # a free wording is kept as typed
    assert Organization.objects.get(port=world.port, name="Kissy Bunkers Ltd").kind == "BUNKER_SUPPLIER"
    # the registration of each new organisation is an act of the port journal
    created = JournalEntry.objects.filter(port=world.port, action="organization.created")
    assert created.count() == 3 and all(e.call_id is None and "AGE" in e.visible_roles for e in created)
    # at the declaration, the new parties without account receive their own way in by e-mail (when they have one)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    mail.outbox.clear()
    call_svc.declare_call(call, act(world, call, "AGE"))
    assert call.master_links.filter(organization=lab, role="INS").exists()
    assert any("lab@spl.test" in m.to for m in mail.outbox) and any("ops@kissybunkers.test" in m.to for m in mail.outbox)
    assert call.master_links.filter(organization=pilots).exists()  # issued, to be handed over by QR or print
    assert not any("Test Terminal" in m.subject for m in mail.outbox if "your access" in m.subject)  # it has an account
    # the parties tab lists them all, with the open invitation form
    tab = client.get(f"/escales/{call.pk}/?tab=parties")
    assert tab.status_code == 200 and b"Sierra Petroleum Laboratory" in tab.content and b"data-parties" in tab.content
    # an announcement posted with a nameless new row is refused with a message, nothing created
    before = world.vessel.calls.count()
    response = client.post("/escales/nouvelle/", {
        "vessel": world.vessel.pk, "kind": "JETTY", "operations": ["M1"], "eta": eta,
        "party_role": ["PRE"], "party_org": ["new"], "party_name": [" "], "party_kind": [""], "party_email": [""], "party_phone": [""],
    })
    assert response.status_code == 200 and b"Name the organisation" in response.content and world.vessel.calls.count() == before


@pytest.mark.django_db
def test_a_party_is_invited_later_on_the_call_registered_or_new(world, client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    login(client, world, "AGE")
    mail.outbox.clear()
    response = client.post(f"/escales/{call.pk}/action/party_add/", {
        "role": "PRE", "organization": "new", "party_name": "Atlantic Divers", "party_kind": "Plongée / travaux sous-marins",
        "party_email": "dive@atlantic.test", "party_phone": "", "back": "?tab=parties"})
    assert response.status_code == 302
    divers = Organization.objects.get(port=world.port, name="Atlantic Divers")
    assert divers.kind == "DIVING" and call.parties.filter(organization=divers, role="PRE", revoked_at=None).exists()
    assert call.master_links.filter(organization=divers).exists() and any("dive@atlantic.test" in m.to for m in mail.outbox)
    # a registered organisation is still picked from the list
    response = client.post(f"/escales/{call.pk}/action/party_add/", {"role": "PRE", "organization": world.orgs.sts.pk, "back": "?tab=parties"})
    assert response.status_code == 302 and call.parties.filter(organization=world.orgs.sts, role="PRE").exists()
    # the same name again: the existing organisation is reused, not duplicated
    actor = port_actor(world.users["AGE"])
    again = call_svc.register_organization(actor, name="atlantic divers", role="PRE")
    assert again == divers and Organization.objects.filter(port=world.port, name__iexact="atlantic divers").count() == 1
    # limits: the agency invites the operational parties only, and a known organisation keeps the roles the port gave it
    with pytest.raises(PermissionRefused):
        call_svc.register_organization(actor, name="Another Harbour Master", role="CAP")
    with pytest.raises(RuleViolation):
        call_svc.register_organization(actor, name="Test Terminal", role="PRE")  # registered as TER only
    with pytest.raises(RuleViolation):
        call_svc.register_organization(actor, name="X", role="PRE")
    with pytest.raises(PermissionRefused):
        call_svc.register_organization(port_actor(world.users["TER"]), name="Someone", role="PRE")
    # the harbour master may invite any role, including a new authority
    cap = port_actor(world.users["CAP"])
    inspectorate = call_svc.register_organization(cap, name="Flag State Inspectorate", role="ADM", kind="Maritime authority (port / flag State)")
    assert inspectorate.kind == "MARITIME_AUTHORITY" and inspectorate.allowed_roles == ["ADM"]


@pytest.mark.django_db
def test_the_api_takes_the_open_party_list_too(world, client):
    from rest_framework.authtoken.models import Token

    token = Token.objects.create(user=world.users["AGE"]).key
    auth = {"HTTP_AUTHORIZATION": f"Bearer {token}", "content_type": "application/json"}
    eta = (timezone.now() + timedelta(days=5)).isoformat()
    created = client.post("/api/v1/calls/", {
        "vessel_imo": world.vessel.imo, "operating_area": "JETTY", "operations": ["M1"], "eta": eta,
        "parties": [{"organization_id": world.orgs.terminal.pk, "role": "TER"},
                    {"name": "Bissau Marine Surveys", "role": "INS", "kind": "Cargo surveyor (quantity, quality)", "email": "ops@bms.test"}],
    }, **auth)
    assert created.status_code == 201, created.content
    reference = created.json()["reference"]
    org = Organization.objects.get(port=world.port, name="Bissau Marine Surveys")
    assert org.kind == "CARGO_SURVEYOR" and org.allowed_roles == ["INS"]
    invited = client.post(f"/api/v1/calls/{reference}/actions/invite/", {"name": "Guinea Water Supply", "role": "PRE", "kind": "Fournisseur d'eau douce"}, **auth)
    assert invited.status_code == 200, invited.content
    water = Organization.objects.get(port=world.port, name="Guinea Water Supply")
    assert water.kind == "WATER_SUPPLIER"
    call = world.vessel.calls.get(reference=reference)
    assert {(p.organization.name, p.role) for p in call.parties.all()} >= {("Bissau Marine Surveys", "INS"), ("Guinea Water Supply", "PRE"), ("Test Terminal", "TER")}
    refused = client.post(f"/api/v1/calls/{reference}/actions/invite/", {"name": "Another Authority", "role": "CAP"}, **auth)
    assert refused.status_code == 403
