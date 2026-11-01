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
        assert f"{code}-{call.reference}-01" in html and call.vessel.name in html and call.vessel.imo in html
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
    assert page.status_code == 200 and b"SSSCL" in page.content and b"NOR" not in page.content.split(b"Other forms")[0]
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
