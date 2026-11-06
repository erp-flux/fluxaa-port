"""Standard forms (ISGOTT, OCIMF, IMO FAL / ISPS, MARPOL, API MPMS) generated from the registry in one structure,
printable, filed into the call as generated documents under the role that produces them."""
from __future__ import annotations

from datetime import timedelta
from html import unescape

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core.models import Organization
from apps.registry.models import JournalEntry
from apps.registry.services import calls as call_svc
from apps.registry.services import forms
from apps.registry.services import milestones as ms_svc
from apps.registry.services.context import actor_for_call
from apps.registry.services.errors import PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call, master
from .test_web import login


@pytest.mark.django_db
def test_every_form_shares_the_same_structure_and_is_prefilled_from_the_registry(world):
    call = make_call(world, operations=("M1", "M4"))
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    nav = master(world, call)
    ms_svc.record_milestone(call, nav, "ARRIVAL", timezone.now() - timedelta(hours=3))
    ms_svc.record_milestone(call, act(world, call, "AGE"), "NOR_TENDERED", timezone.now() - timedelta(hours=2))
    seq = JournalEntry.objects.filter(call=call).order_by("-seq").first().seq
    for code, form in forms.FORMS.items():
        html = unescape(forms.render(call, code))
        # 1. header band: port, bilingual title, reference standard, form number of the call
        assert f"{call.port.name} ({call.port.code})" in html and form.title[1] in html and form.standard[1] in html
        issued = call.documents.filter(type__code=form.document_type, title__startswith=form.title[0]).count()
        assert f"{code}-{call.reference}-{issued + 1:02d}" in html and call.vessel.name in html and call.vessel.imo in html
        # 2. body: at least one section; 3. one signature column per signing role; 4. sealed footer
        assert "<h2>" in html and "<h2>Signatures</h2>" in html and f"n° {seq}" in html
        for role, (_fr, en) in form.signers:
            assert en in html and f"({role})" in html
    nor = forms.render(call, "NOR")
    assert "NOR tendered on" in nor and "Arrival at the port limit" in nor and "Gasoil" in nor
    assert "chargement / loading" not in nor  # M1 is a discharge
    # a form keeps blank lines for what the registry does not know, it never invents a value
    assert 'class="blank"' in forms.render(call, "ULLAGE")


@pytest.mark.django_db
def test_forms_are_offered_by_role_and_by_operation(world):
    call = make_call(world)  # discharge at the quay, no STS, no bunkering
    codes = {f.code for f in forms.available(call, act(world, call, "TER"))}
    assert {"SSSCL", "PRE_TRANSFER", "ULLAGE", "HOSES", "PROTEST"} <= codes
    assert "NOR" not in codes and "TIME_SHEET" not in codes and "STS" not in codes and "BDN" not in codes
    assert {f.code for f in forms.available(call, act(world, call, "AGE"))} >= {"NOR", "TIME_SHEET", "FAL", "WASTE", "PROTEST"}
    assert {f.code for f in forms.available(call, act(world, call, "SUR"))} == {"DOS"}
    assert {f.code for f in forms.available(call, master(world, call))} >= {"NOR", "SSSCL", "FAL", "DOS", "MDH", "PILOT_CARD"}
    sts = make_call(world, kind="STS_AREA", operations=("M3",))
    assert "STS" in {f.code for f in forms.available(sts, act(world, sts, "PRE"))}
    bunkers = make_call(world, operations=("M1", "M4"))
    assert "BDN" in {f.code for f in forms.available(bunkers, act(world, bunkers, "PRE"))}
    with pytest.raises(RuleViolation):
        forms.render(call, "NOPE")


@pytest.mark.django_db
def test_filing_a_form_makes_a_generated_document_under_the_right_role(world, client):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    ter = act(world, call, "TER")
    doc = forms.issue(call, ter, "SSSCL")
    assert doc.generated and doc.issuer_role == "TER" and doc.type.code == "SSSCL" and doc.version == 1
    assert doc.mime_type == "text/html" and doc.sha256 and doc.original_name.endswith("_ssscl.html")
    assert "Ship/shore safety checklist" in doc.title
    # filing again makes the next version of the same document
    again = forms.issue(call, ter, "SSSCL")
    assert again.version == 2 and again.previous_id == doc.pk
    # the number on the paper follows the versions
    assert f"SSSCL-{call.reference}-03" in forms.render(call, "SSSCL")
    # the form is generated under a role that produces it: the surveyor does not file the ship/shore checklist
    with pytest.raises(PermissionRefused):
        forms.issue(call, act(world, call, "INS"), "SSSCL")
    with pytest.raises(RuleViolation):
        forms.issue(call, ter, "NOPE")
    # web: the list, the printable page and the filing action, with access journalised
    login(client, world, "TER")
    page = client.get(f"/escales/{call.pk}/formulaires/")
    assert page.status_code == 200 and b"SSSCL" in page.content and b"NOR" not in page.content.split(b"issued by the other parties")[0]
    printable = client.get(f"/escales/{call.pk}/formulaires/HOSES/")
    assert printable.status_code == 200 and b"Hose / arm connection" in printable.content
    assert client.get(f"/escales/{call.pk}/formulaires/NOR/").status_code == 404  # not the terminal's form
    response = client.post(f"/escales/{call.pk}/action/form_issue/", {"code": "HOSES"})
    assert response.status_code == 302 and call.documents.filter(type__code="HOSE_RECORD", generated=True).exists()
    tab = client.get(f"/escales/{call.pk}/?tab=documents")
    assert tab.status_code == 200 and b"Standard forms" in tab.content
    # API: list, render, file
    token = Token.objects.create(user=world.users["TER"]).key
    auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
    listed = client.get(f"/api/v1/calls/{call.reference}/forms/", **auth).json()["results"]
    assert {f["code"] for f in listed} >= {"SSSCL", "HOSES"} and all(f["signers"] for f in listed)
    assert client.get(f"/api/v1/calls/{call.reference}/forms/NOR/", **auth).status_code == 404
    rendered = client.get(f"/api/v1/calls/{call.reference}/forms/PRE_TRANSFER/", **auth)
    assert rendered.status_code == 200 and b"pre-transfer meeting" in rendered.content
    filed = client.post(f"/api/v1/calls/{call.reference}/forms/PRE_TRANSFER/", **auth)
    assert filed.status_code == 201 and filed.json()["type"] == "PRE_TRANSFER_MINUTES"


@pytest.mark.django_db
def test_a_party_without_account_files_its_forms_through_its_link(world, client, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    second = Organization.objects.create(port=world.port, name="Second Surveyor Ltd", allowed_roles=["INS"],
                                         email="ops@second-surveyor.test")
    call = make_call(world, parties=[(world.orgs.terminal, "TER"), (world.orgs.surveyor, "INS"), (second, "INS"),
                                     (world.orgs.owner, "COM")])
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    mail.outbox.clear()
    call_svc.declare_call(call, act(world, call, "AGE"))
    link = call.master_links.get(organization=second)
    token = [m for m in mail.outbox if "ops@second-surveyor.test" in m.to][0].body.split("/bord/")[1].split("/")[0]
    client.get(f"/bord/{token}/")
    client.post("/bord/nom/", {"name": "Fatmata Conteh"})
    page = client.get(f"/escales/{call.pk}/formulaires/")
    assert page.status_code == 200 and b"ULLAGE" in page.content
    response = client.post(f"/escales/{call.pk}/action/form_issue/", {"code": "ULLAGE"})
    assert response.status_code == 302
    doc = call.documents.get(type__code="ULLAGE_REPORT")
    assert doc.issuer_role == "INS" and doc.issuer_org == second and doc.issuer_master_id == link.pk
    assert "Fatmata Conteh" in doc.issuer_label
    holder = actor_for_call(call, master=link)
    assert "DOS" not in {f.code for f in forms.available(call, holder)}  # never the security declaration


@pytest.mark.django_db
def test_every_party_issues_the_documents_the_call_asks_of_it(world):
    """Each role has its own family of forms, answering the tasks and requests addressed to it; a form of an
    operation the call does not include is not offered."""
    from apps.registry import catalog

    call = make_call(world, operations=("M1",))  # discharge at the quay
    families = {code for code, _label, _members in forms.grouped(list(forms.FORMS.values()))}
    assert families == {"AGE", "NAV", "TER", "CAP", "APO", "ADM", "SUR", "SVC", "INS", "COM", "PRE"}
    assert len(forms.FORMS) >= 70
    # the document type of every form names the issuing roles of the form
    issuers = {d["code"]: set(d["issuer_roles"]) for d in catalog.DOCUMENT_TYPES}
    assert all(f.roles <= issuers[f.document_type] for f in forms.FORMS.values())
    # every "provide a document" task of a module that is on the call is answered by a form, or the task names an
    # outside document (certificates, authorizations of the State, plans)
    answered = {ref for f in forms.FORMS.values() for ref in f.answers}
    outside = {"M0:02", "M0:03", "M1:1.01", "M2:2.01", "M3:3.02", "M4:4.02", "M5:5.01", "M6:6.03", "M6:6.09", "M7:7.01",
               "M7:7.03", "M7:7.07", "M7:7.12", "M0:13", "M0:36"}
    for tpl in catalog.TEMPLATES:
        for _sec, t in tpl["tasks"]:
            if t["nature"] == "F":
                ref = f"{tpl['code']}:{t['number']}"
                assert ref in answered or ref in outside, ref
    # every decided request type has its written act, issued by its deciding roles
    for rtype in catalog.REQUEST_TYPES:
        if rtype["decision_roles"]:
            form = forms.FORMS[f"AUTH_{rtype['code']}"]
            assert form.roles == set(rtype["decision_roles"]) and f"REQ:{rtype['code']}" in form.answers
    # offered by operation: no STS, bunkering, works or double banking forms on a plain discharge
    offered = {f.code for f in forms.for_call(call)}
    assert {"ARRIVAL_NOTICE", "SANCTIONS_CHECK", "BALLAST_NOTIFICATION", "DISCHARGE_PLAN", "TERMINAL_RECEIPT", "QUANTITY_CERT",
            "EMPTY_TANKS_CERT", "AUTH_GREEN_LIGHT", "AUTH_BERTH", "AUTH_FREE_PRATIQUE", "MOVEMENT_ORDER", "WASTE_RECEIPT",
            "CARGO_DECLARATION", "CP_RECAP"} <= offered
    assert not {"STS_COMPATIBILITY", "BUNKER_CHECKLIST", "HOT_WORK_PERMIT", "DOUBLE_BANKING_STUDY", "LOADING_PLAN",
                "BILL_OF_LADING", "AUTH_HOT_WORK", "GAS_FREE_CERT"} & offered
    works = make_call(world, operations=("M1", "M7"))
    assert {"HOT_WORK_PERMIT", "AUTH_HOT_WORK", "GAS_FREE_CERT", "WORKS_CREW", "ENCLOSED_SPACE_PERMIT"} <= {f.code for f in forms.for_call(works)}
    with pytest.raises(RuleViolation):
        forms.issue(call, act(world, call, "CAP"), "AUTH_HOT_WORK")  # not an operation of this call
    # by role: the harbour master's acts, the customs' acts, the surveyor's certificates, the owner's instructions
    assert {f.code for f in forms.available(call, act(world, call, "CAP"))} >= {"AUTH_GREEN_LIGHT", "AUTH_MOVEMENT", "AUTH_DEPARTURE_CLEARANCE", "BERTH_LIMITS"}
    assert {f.code for f in forms.available(call, act(world, call, "ADM"))} == {"AUTH_FREE_PRATIQUE", "AUTH_CUSTOMS_IMMIGRATION", "AUTH_OUTWARD_FORMALITIES"}
    assert {f.code for f in forms.available(call, act(world, call, "APO"))} == {"AUTH_BERTH", "AUTH_VESSEL_ACCEPTANCE"}
    assert {f.code for f in forms.available(call, act(world, call, "SVC"))} == {"MOVEMENT_ORDER", "SERVICE_NOTE", "PILOT_CARD", "INCIDENT_REPORT"}
    assert {f.code for f in forms.available(call, act(world, call, "COM"))} == {"CP_RECAP", "LOI"}
    assert {"QUANTITY_CERT", "QUALITY_CERT", "SAMPLING_RECORD", "EMPTY_TANKS_CERT", "ULLAGE"} <= {f.code for f in forms.available(call, act(world, call, "INS"))}


@pytest.mark.django_db
def test_the_written_act_of_a_decision_carries_the_authorization_and_its_verification_code(world, client):
    from apps.registry.models import RequestStatus
    from apps.registry.services import requests as req_svc

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    force_done(call, ["M0:06", "M0:07"])  # the green light is guarded by the vessel acceptance
    cap = act(world, call, "CAP")
    # before any decision: the act is blank, no verification block
    blank = unescape(forms.render(call, "AUTH_GREEN_LIGHT", cap))
    assert "Public verification" not in blank and 'class="blank"' in blank
    req = req_svc.create_request(call, act(world, call, "AGE"), "GREEN_LIGHT", {})
    auth = req_svc.decide_request(req, cap, RequestStatus.APPROVED, conditions="Pilot compulsory")
    html = unescape(forms.render(call, "AUTH_GREEN_LIGHT", cap))
    assert auth.number in html and auth.verification_code in html and f"/verifier/{auth.verification_code}/" in html
    assert "Pilot compulsory" in html and req.reference in html and "data:image/svg+xml" in html  # QR of the public address
    # the act was filed by the decision itself as a generated AUTHORIZATION document under the deciding role;
    # another act of another type does not replace it (one document per form), a re-issue is the next version
    doc = call.documents.get(type__code="AUTHORIZATION", title__startswith="Autorisation — Feu vert")
    assert doc.issuer_role == "CAP" and doc.generated and doc.version == 1 and doc.status == "ISSUED"
    other = forms.issue(call, cap, "AUTH_MOVEMENT")
    assert other.version == 1 and other.previous_id is None
    again = forms.issue(call, cap, "AUTH_GREEN_LIGHT")
    assert again.version == 2 and again.previous_id == doc.pk
    # the agency cannot issue the port's act; the act type is generated only (never uploaded)
    with pytest.raises(PermissionRefused):
        forms.issue(call, act(world, call, "AGE"), "AUTH_GREEN_LIGHT")
    login(client, world, "CAP")
    page = client.get(f"/escales/{call.pk}/formulaires/")
    assert page.status_code == 200 and b"AUTH_GREEN_LIGHT" in page.content and b"Harbour master" in page.content
    assert b"v2" in page.content  # the forms page shows the act as filed, at its current version
    printable = client.get(f"/escales/{call.pk}/formulaires/AUTH_GREEN_LIGHT/")
    assert printable.status_code == 200 and auth.verification_code.encode() in printable.content
    token = Token.objects.create(user=world.users["CAP"]).key
    listed = client.get(f"/api/v1/calls/{call.reference}/forms/", HTTP_AUTHORIZATION=f"Bearer {token}").json()["results"]
    act_json = next(f for f in listed if f["code"] == "AUTH_GREEN_LIGHT")
    assert act_json["family"] == "CAP" and "REQ:GREEN_LIGHT" in act_json["answers"] and act_json["document_type"] == "AUTHORIZATION"


@pytest.mark.django_db
def test_the_bill_of_lading_form_stays_behind_its_lock(world):
    from apps.registry.services.errors import HoldPointRefused

    call = make_call(world, operations=("M2",))  # loading
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    age = act(world, call, "AGE")
    assert "BILL_OF_LADING" in {f.code for f in forms.available(call, age)}
    assert "Bill of lading" in forms.render(call, "BILL_OF_LADING", age)  # the preview is free
    with pytest.raises(HoldPointRefused):  # issuing it is the act the hold point guards (M2:2.16 first)
        forms.issue(call, age, "BILL_OF_LADING")


@pytest.mark.django_db
def test_the_documents_of_the_call_appear_as_soon_as_their_act_is_taken(world, client):
    """A party does not have to come back to the forms page to produce the paperwork of what it just did: the
    clearance of the harbour master, the formalities of customs, the notice of readiness, the time sheet are
    filed among the documents of the call by the decision, the milestone or the statement that produces them."""
    from apps.registry.models import RequestStatus
    from apps.registry.services import reports
    from apps.registry.services import requests as req_svc

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    age, cap, ter = act(world, call, "AGE"), act(world, call, "CAP"), act(world, call, "TER")
    # the vessel acceptance (N2, vetting) is approved: its act is filed with the request's confidentiality
    vet = req_svc.create_request(call, ter, "VESSEL_ACCEPTANCE", {
        "product": "Gasoil", "inspection": "SIRE 2.0 — 2026-08-01, no open observation",
        "last_cargoes": "ULSD / ULSD / Jet A-1", "vetting_result": "Accepted"})
    req_svc.decide_request(vet, cap, RequestStatus.APPROVED)
    vet_act = call.documents.get(type__code="AUTHORIZATION", title__startswith="Autorisation — Acceptation de navire")
    assert vet_act.confidentiality == "N2" and vet_act.issuer_role == "CAP" and vet_act.generated
    # the green light is approved: its act carries the verification code; a movement request is refused: the
    # written refusal is filed too, without its reason (restricted, S7) and without verification block
    force_done(call, ["M0:06", "M0:07"])
    green = call.requests.get(type__code="GREEN_LIGHT")
    auth = req_svc.decide_request(green, cap, RequestStatus.APPROVED)
    approval = call.documents.get(type__code="AUTHORIZATION", title__startswith="Autorisation — Feu vert")
    assert auth.verification_code in approval.file.open("rb").read().decode()
    move = req_svc.create_request(call, age, "MOVEMENT", {"movement": "ARRIVAL", "requested_time": "2026-11-03T06:00:00+00:00"})
    req_svc.decide_request(move, cap, RequestStatus.REFUSED, reason="Pilot boat unavailable")
    refusal = call.documents.get(type__code="AUTHORIZATION", title__startswith="Autorisation — Autorisation de mouvement")
    html = unescape(refusal.file.open("rb").read().decode())
    assert "Refused" in html or "Refusée" in html
    assert "Pilot boat unavailable" not in html and "Public verification" not in html
    # every party of the call sees the N1 acts in its documents tab; the N2 vetting act is read by the terminal
    # (its requester) but not by the surveyor
    login(client, world, "TER")
    tab = client.get(f"/escales/{call.pk}/?tab=documents")
    assert tab.status_code == 200 and b"Green light" in tab.content and b"Vessel acceptance" in tab.content
    login(client, world, "INS")
    tab = client.get(f"/escales/{call.pk}/?tab=documents")
    assert b"Green light" in tab.content and b"Vessel acceptance" not in tab.content
    # the notice of readiness tendered by the agency is filed as the NOR form, under the agency's role
    ms_svc.record_milestone(call, age, "NOR_TENDERED", timezone.now() - timedelta(minutes=5))
    nor = call.documents.get(type__code="NOR")
    assert nor.generated and nor.issuer_role == "AGE" and nor.confidentiality == "N1"
    assert call.documents.filter(generated=True, title__startswith="Notice de disponibilité").count() == 1
    # the statement of facts brings the time sheet with it
    for field in ("ata", "atb", "t0", "t1", "atd"):
        setattr(call, field, timezone.now() - timedelta(hours=10))
    call.status = "DEPARTED"
    call.save()
    reports.issue_statement_of_facts(call, age, remarks="")
    assert call.documents.filter(type__code="SOF", generated=True).exists()
    assert call.documents.filter(type__code="TIME_SHEET", generated=True, issuer_role="AGE").exists()
    # a paperwork problem never blocks the act: an actor without the form's role still gets its decision recorded
    from apps.registry.services.forms import auto_issue

    assert auto_issue(call, act(world, call, "INS"), "AUTH_MOVEMENT") is None
