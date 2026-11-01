"""Access of the parties without an account: convened at the declaration, nominative, valid until closure,
never a decision (extension of EF-13)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.core.models import Organization
from apps.registry.models import CallStatus, JournalEntry, MasterAccessLink, PortCall
from apps.registry.services import calls as call_svc
from apps.registry.services import documents as doc_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services.context import actor_for_call
from apps.registry.services.errors import NotVisible, PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call


def declared_with_second_surveyor(world, *, email="ops@second-surveyor.test", name="Second Surveyor Ltd"):
    second = Organization.objects.create(port=world.port, name=name, allowed_roles=["INS"], email=email)
    call = make_call(world, parties=[(world.orgs.terminal, "TER"), (world.orgs.surveyor, "INS"), (second, "INS"),
                                     (world.orgs.owner, "COM")])
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    mail.outbox.clear()
    call_svc.declare_call(call, act(world, call, "AGE"))
    call.refresh_from_db()
    return call, second


@pytest.mark.django_db
def test_declaration_convenes_every_party_with_its_own_way_in(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call, second = declared_with_second_surveyor(world)
    # parties with an account: the usual notification, no link
    assert not call.master_links.filter(organization=world.orgs.surveyor).exists()
    # the organisation without any account holding its role: one link, e-mailed, valid until closure
    link = call.master_links.get(organization=second, role="INS")
    assert link.auto_issued and link.sent_to == "ops@second-surveyor.test" and link.master_name == ""
    assert link.is_valid() and link.expires_at > timezone.now() + timedelta(days=30)
    sent = [m for m in mail.outbox if "ops@second-surveyor.test" in m.to]
    assert len(sent) == 1 and call.reference in sent[0].subject and "/bord/" in sent[0].body
    assert JournalEntry.objects.filter(call=call, action="party_link.issued").count() == 1
    # declaring again later does not issue a second link while one is open
    assert call_svc.convene_parties(call, act(world, call, "AGE")) == []


@pytest.mark.django_db
def test_link_holder_enters_consults_and_files_but_never_decides(client, world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call, second = declared_with_second_surveyor(world)
    link = call.master_links.get(organization=second)
    body = [m for m in mail.outbox if "ops@second-surveyor.test" in m.to][0].body
    token = body.split("/bord/")[1].split("/")[0]
    # the link opens the call only after the holder gives their name
    response = client.get(f"/bord/{token}/")
    assert response.status_code == 302 and response["Location"].endswith("/bord/nom/")
    assert client.get(f"/escales/{call.pk}/").status_code == 302  # not yet
    assert client.post("/bord/nom/", {"name": "A."}).status_code == 200  # too short
    response = client.post("/bord/nom/", {"name": "Fatmata Conteh"})
    assert response.status_code == 302 and response["Location"] == f"/escales/{call.pk}/"
    link.refresh_from_db()
    assert link.master_name == "Fatmata Conteh"
    page = client.get(f"/escales/{call.pk}/?tab=documents")
    assert page.status_code == 200 and b"Fatmata Conteh" in page.content
    # entries are nominative and attributed to the organisation of the link
    upload = client.post(f"/escales/{call.pk}/action/document_upload/", {
        "type": "QQ_CERT", "file": SimpleUploadedFile("qq.pdf", b"%PDF qq", content_type="application/pdf")})
    assert upload.status_code == 302
    doc = call.documents.get(type__code="QQ_CERT")
    assert doc.issuer_role == "INS" and doc.issuer_org == second and doc.issuer_master == link
    assert "Fatmata Conteh" in doc.issuer_label and "Second Surveyor" in doc.issuer_label
    holder = actor_for_call(call, master=link)
    milestone = ms_svc.record_milestone(call, holder, "INITIAL_GAUGING", timezone.now() - timedelta(minutes=10))
    assert milestone.emitter_org == second and milestone.emitter_label.startswith("Fatmata Conteh")
    # the first surveyor (an account) does not act for the second one's records, and vice versa
    other = act(world, call, "INS")
    with pytest.raises(PermissionRefused):
        doc_svc.cancel_document(doc, other, "not mine")
    own = doc_svc.upload_document(call, other, "QUALITY_CERT", SimpleUploadedFile("q.pdf", b"%PDF q", content_type="application/pdf"))
    with pytest.raises(PermissionRefused):
        doc_svc.cancel_document(own, holder, "not mine either")
    # never a decision, never the assistant, no dashboard
    assert "CAP" not in holder.roles and not holder.strong_auth and holder.is_link and not holder.is_master
    assert client.get("/").status_code in (302, 404)
    assert client.get("/assistant/").status_code in (302, 404)


@pytest.mark.django_db
def test_party_link_lasts_until_closure_and_ends_with_the_role(world, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    call, second = declared_with_second_surveyor(world)
    link = call.master_links.get(organization=second)
    # unlike the master's link, a party's link survives the departure: documents and figures come after
    PortCall.objects.filter(pk=call.pk).update(status=CallStatus.DEPARTED, atd=timezone.now() - timedelta(days=3))
    link.call.refresh_from_db()
    assert link.is_valid()
    master_link, _t, _c = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Test",
                                                     expires_at=timezone.now() + timedelta(days=5))
    master_link.call.refresh_from_db()
    assert not master_link.is_valid()  # the ship has left
    # closure ends every link
    PortCall.objects.filter(pk=call.pk).update(status=CallStatus.CLOSED)
    link.call.refresh_from_db()
    assert not link.is_valid()
    # revoking the role revokes the link, and the link no longer opens the call
    call2, second2 = declared_with_second_surveyor(world, email="", name="Third Surveyor Ltd")
    link2 = call2.master_links.get(organization=second2)
    assert link2.sent_to == "" and JournalEntry.objects.filter(call=call2, action="party_link.unsent").exists()
    party = call2.parties.get(organization=second2, role="INS")
    call_svc.revoke_party(call2, act(world, call2, "CAP"), party, "contract ended")
    link2.refresh_from_db()
    assert link2.revoked_at is not None
    with pytest.raises(NotVisible):
        actor_for_call(call2, master=link2)


@pytest.mark.django_db
def test_agency_issues_and_harbour_master_revokes_a_party_link(client, world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    terminal = call.parties.get(role="TER")
    link, token, code = call_svc.issue_party_link(call, act(world, call, "AGE"), party=terminal, holder_name="Kofi Mensah",
                                                  channel="QR")
    assert link.role == "TER" and link.organization == world.orgs.terminal and not link.auto_issued
    # deciding roles never get a link
    with pytest.raises(RuleViolation):
        call_svc.issue_party_link(call, act(world, call, "AGE"), party=call.parties.get(role="CAP"), holder_name="x")
    # the terminal's own account user cannot issue links
    with pytest.raises(PermissionRefused):
        call_svc.issue_party_link(call, act(world, call, "TER"), party=terminal, holder_name="x")
    # code entry opens the call directly (the name is known)
    response = client.post("/bord/", {"code": code})
    assert response.status_code == 302 and response["Location"] == f"/escales/{call.pk}/"
    assert client.get(f"/escales/{call.pk}/?tab=jalons").status_code == 200
    client.post("/bord/sortie/")
    call_svc.revoke_master_link(link, act(world, call, "CAP"), "handed to someone else")
    assert client.get(f"/bord/{token}/").status_code == 302
    assert MasterAccessLink.objects.get(pk=link.pk).revoked_at is not None
    # web: the agency issues from the Parties tab
    from .test_web import login

    login(client, world, "AGE")
    response = client.post(f"/escales/{call.pk}/action/party_link/", {"party_id": terminal.pk, "holder_name": "Ama Owusu",
                                                                     "channel": "EMAIL"})
    assert response.status_code == 302
    page = client.get(f"/escales/{call.pk}/?tab=parties")
    assert page.status_code == 200 and b"Ama Owusu" in page.content and b"/bord/" in page.content
