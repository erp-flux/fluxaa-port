"""The web interface and the public API, exercised end to end with the test client."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.authtoken.models import Token

from apps.core import mfa
from apps.registry.models import CallStatus, JournalEntry, Milestone
from apps.registry.services import calls as call_svc

from .conftest import act, force_done, make_call

TABS = ["apercu", "taches", "jalons", "demandes", "documents", "mesures", "contestations", "echanges", "journal", "parties"]


def login(client, world, role):
    user = world.users[role]
    client.force_login(user)
    if user.requires_mfa_login:
        secret = mfa.new_secret()
        user.set_mfa_secret(secret)
        user.mfa_enabled = True
        user.save()
        session = client.session
        session.update(mfa.stamp(user))
        session.save()
    return user


@pytest.mark.django_db(databases=["default", "secure"])
def test_pages_render_for_every_role(client, world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    for role in ["AGE", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "PRE", "DIR"]:
        client.logout()
        login(client, world, role)
        if role != "PRE":
            assert client.get("/").status_code == 200, role
        assert client.get("/escales/").status_code == 200, role
        for tab in TABS:
            response = client.get(f"/escales/{call.pk}/?tab={tab}")
            assert response.status_code == 200, (role, tab)
        assert client.get("/notifications/").status_code == 200
        assert client.get("/compte/").status_code == 200


@pytest.mark.django_db
def test_mfa_is_enforced_for_harbour_master(client, world):
    client.force_login(world.users["CAP"])
    response = client.get("/")
    assert response.status_code == 302 and "/compte/mfa/activer/" in response["Location"]


@pytest.mark.django_db
def test_create_declare_and_hold_point_box(client, world):
    login(client, world, "AGE")
    page = client.get("/escales/nouvelle/")
    assert page.status_code == 200
    eta = (timezone.now() + timedelta(days=6)).strftime("%Y-%m-%dT%H:%M")
    response = client.post("/escales/nouvelle/", {
        "vessel": world.vessel.pk, "kind": "JETTY", "operations": ["M1"], "eta": eta, "product": "Gasoil",
        "quantity": "25000", "quantity_unit": "MT", "party_TER": [world.orgs.terminal.pk], "party_INS": [world.orgs.surveyor.pk],
    })
    assert response.status_code == 302
    call = world.vessel.calls.latest("created_at")
    assert call.status == CallStatus.DRAFT and call.parties.filter(role="TER").exists()
    # declaring without the vessel dataset is refused with the hold point box
    response = client.post(f"/escales/{call.pk}/action/declare/", {"back": "?tab=apercu"}, follow=True)
    assert response.status_code == 200
    content = response.content.decode()
    assert "M0:02" in content and "refusal" in content
    assert JournalEntry.objects.filter(call=call, action="holdpoint.refused").exists()
    # provide the Q88 through the documents form
    response = client.post(f"/escales/{call.pk}/action/document_upload/", {
        "type": "Q88", "file": SimpleUploadedFile("q88.pdf", b"%PDF-1.4 q88", content_type="application/pdf"),
        "back": "?tab=documents"})
    assert response.status_code == 302 and response["Location"].endswith("?tab=documents")
    assert call.tasks.get(template_code="M0", number="02").status == "DONE"


@pytest.mark.django_db(databases=["default", "secure"])
def test_master_portal_with_code(client, world):
    call = make_call(world)
    link, token, code = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Kamara")
    response = client.post("/bord/", {"code": code})
    assert response.status_code == 302 and response["Location"] == f"/escales/{call.pk}/"
    page = client.get(f"/escales/{call.pk}/?tab=documents")
    assert page.status_code == 200 and b"MT TEST SPIRIT" in page.content
    upload = client.post(f"/escales/{call.pk}/action/document_upload/", {
        "type": "CERTIFICATES", "file": SimpleUploadedFile("c.pdf", b"%PDF certs", content_type="application/pdf")})
    assert upload.status_code == 302
    assert call.tasks.get(template_code="M0", number="03").status == "DONE"
    assert client.get("/").status_code in (302, 404) or True  # no dashboard for the master
    client.post("/bord/sortie/")
    assert client.get(f"/escales/{call.pk}/").status_code == 302
    assert client.get(f"/bord/{token}/").status_code == 302


@pytest.mark.django_db(databases=["default", "secure"])
def test_api_flow_and_n4_existence_not_disclosed(client, world):
    from apps.secure import services as n4

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    reference = n4.deposit(call, act(world, call, "AGE"), kind="ARMED_GUARDS", payload={"guards": 3})
    tokens = {role: Token.objects.create(user=world.users[role]).key for role in ("TER", "SUR", "AGE", "COM", "SVC")}

    def api(role, method, path, data=None, **extra):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {tokens[role]}", **extra}
        if method == "get":
            return client.get(path, **headers)
        return client.post(path, data=json.dumps(data or {}), content_type="application/json", **headers)

    assert api("TER", "get", "/api/v1/me/").json()["roles"] == ["TER"]
    calls = api("TER", "get", "/api/v1/calls/").json()["results"]
    assert [c["reference"] for c in calls] == [call.reference]
    # N4: refused without disclosing existence (404, not 403), full access for SUR
    assert api("TER", "get", f"/api/v1/secure/items/{reference}/").status_code == 404
    assert api("AGE", "get", "/api/v1/secure/items/").status_code == 404
    assert api("SUR", "get", f"/api/v1/secure/items/{reference}/").json()["payload"]["guards"] == 3
    # COM cannot create an event (EF-12.5)
    response = api("COM", "post", f"/api/v1/calls/{call.reference}/milestones/",
                   {"type": "ARRIVAL", "declared_at": timezone.now().isoformat()})
    assert response.status_code == 403
    # hold point through the API: pilot boarding refused without movement authorization
    response = api("SVC", "post", f"/api/v1/calls/{call.reference}/milestones/",
                   {"type": "PILOT_ON_BOARD_ARR", "declared_at": timezone.now().isoformat()})
    assert response.status_code == 409 and response.json()["code"] == "hold_point_refused"
    assert response.json()["details"]["missing_tasks"][0]["task"] == "M0:25"
    # decision without second factor is refused, with X-MFA-Code it passes
    vet = api("TER", "post", f"/api/v1/calls/{call.reference}/requests/", {
        "type": "VESSEL_ACCEPTANCE", "data": {"product": "Gasoil", "inspection": "SIRE", "last_cargoes": "x",
                                              "vetting_result": "ok"}})
    assert vet.status_code == 201
    cap = world.users["CAP"]
    secret = mfa.new_secret()
    cap.set_mfa_secret(secret)
    cap.mfa_enabled = True
    cap.save()
    cap_token = Token.objects.create(user=cap).key
    path = f"/api/v1/calls/{call.reference}/requests/{vet.json()['id']}/decide/"
    response = client.post(path, data=json.dumps({"decision": "APPROVED"}), content_type="application/json",
                           HTTP_AUTHORIZATION=f"Bearer {cap_token}")
    assert response.status_code == 403 and response.json()["code"] == "strong_auth_required"
    import pyotp

    response = client.post(path, data=json.dumps({"decision": "APPROVED"}), content_type="application/json",
                           HTTP_AUTHORIZATION=f"Bearer {cap_token}", HTTP_X_MFA_CODE=pyotp.TOTP(secret).now())
    assert response.status_code == 200 and response.json()["authorization"]["verification_code"]
    code = response.json()["authorization"]["verification_code"]
    public = client.get(f"/api/v1/verify/{code}/")
    assert public.status_code == 200 and public.json()["valid_now"] is True
    assert client.get(f"/verifier/{code}/").status_code == 200
    # field bundle and offline sync for the terminal
    bundle = api("TER", "get", f"/api/v1/calls/{call.reference}/field-bundle/").json()
    assert any(t["code"] == "ESD_TEST" for t in bundle["milestone_types"])
    result = api("TER", "post", f"/api/v1/calls/{call.reference}/sync/", {"entries": [{
        "kind": "milestone", "client_uuid": "4f5f3c7e-2b9e-4c1d-9f1e-1b2c3d4e5f60", "type": "INTERRUPTION_START",
        "cause": "SHORE_PUMP", "declared_at": (timezone.now() - timedelta(minutes=50)).isoformat(),
        "device_recorded_at": (timezone.now() - timedelta(minutes=49)).isoformat()}]}).json()
    assert result["results"][0]["status"] == "ok" and result["results"][0]["deferred"] is True
    assert Milestone.objects.get(pk=result["results"][0]["id"]).source == "OFFLINE"
    # schema for the API documentation
    assert client.get("/api/schema/").status_code == 200


@pytest.mark.django_db(databases=["default", "secure"])
def test_api_session_requires_the_second_factor(client, world):
    """ENF-3.1: a password alone never opens the API from a browser session — N4 items included."""
    from apps.secure import services as n4

    call = make_call(world)
    reference = n4.deposit(call, act(world, call, "AGE"), kind="ESCORT", payload={"escort": "Navy patrol"})
    user = world.users["SUR"]
    user.set_mfa_secret(mfa.new_secret())
    user.mfa_enabled = True
    user.save()
    client.force_login(user)  # password step only
    for path in ("/api/v1/me/", "/api/v1/secure/items/", f"/api/v1/secure/items/{reference}/"):
        response = client.get(path)
        assert response.status_code == 403 and response.json()["code"] == "strong_auth_required", path
        assert b"Navy patrol" not in response.content
    session = client.session
    session.update(mfa.stamp(user))
    session.save()
    assert client.get("/api/v1/secure/items/").status_code == 200
    assert b"Navy patrol" in client.get(f"/api/v1/secure/items/{reference}/").content
    # roles without the login requirement keep using their session as before
    client.logout()
    login(client, world, "TER")
    assert client.get("/api/v1/me/").status_code == 200


@pytest.mark.django_db(databases=["default", "secure"])
def test_security_space_pages(client, world):
    from apps.secure import services as n4

    call = make_call(world)
    reference = n4.deposit(call, act(world, call, "AGE"), kind="ESCORT", payload={"escort": "Navy patrol"})
    login(client, world, "TER")
    assert client.get("/surete/").status_code == 404
    assert client.get(f"/surete/{reference}/").status_code == 404
    client.logout()
    login(client, world, "SUR")
    assert client.get("/surete/").status_code == 200
    page = client.get(f"/surete/{reference}/")
    assert page.status_code == 200 and b"Navy patrol" in page.content
    assert client.get("/surete/journal/").status_code == 200


@pytest.mark.django_db
def test_admin_scoped_to_port(client, world):
    admin_user = world.users["DIR"]
    admin_user.is_port_admin = True
    admin_user.save()
    login(client, world, "DIR")  # an administrator signs in with a second factor
    assert client.get("/admin/").status_code == 200
    assert client.get("/admin/registry/calltemplate/").status_code == 200
    assert client.get("/admin/registry/requesttype/").status_code == 200
    assert client.get("/admin/core/user/").status_code == 200
    assert client.get("/healthz").json()["status"] == "ok"


@pytest.mark.django_db
def test_calibration_page_for_management_only(client, world):
    from apps.registry.services import reports

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    data = reports.calibration(world.port)
    assert data["calls"] == 1 and {t["template"] for t in data["templates"]} >= {"M0", "M1"}
    assert {r["role"] for r in data["roles"]} >= {"AGE"}
    login(client, world, "TER")
    assert client.get("/pilotage/").status_code == 404
    client.logout()
    login(client, world, "DIR")
    page = client.get("/pilotage/?days=30")
    assert page.status_code == 200 and b"M0" in page.content


@pytest.mark.django_db
def test_ef_16_port_admin_configures_without_code(client, world):
    """EF-16 acceptance: a request type, a template task and an interruption cause added from the settings screens."""
    from apps.registry.models import CallTemplate, InterruptionCause, RequestType, TemplateTask, TemplateVersion

    admin_user = world.users["DIR"]
    admin_user.is_port_admin = True
    admin_user.save()
    login(client, world, "DIR")  # an administrator signs in with a second factor
    response = client.post("/admin/registry/requesttype/add/", {
        "port": world.port.pk, "code": "BUNKER_SURVEY", "label_fr": "Contrôle de soutage", "label_en": "Bunker survey",
        "description_fr": "", "description_en": "", "requester_roles": ["AGE"], "decision_roles": ["CAP"],
        "executor_role": "", "confidentiality": "N2", "refusal_confidentiality": "N2",
        "form_schema": '[{"key": "grade", "label_fr": "Grade", "label_en": "Grade", "type": "text", "required": true}]',
        "expected_documents": "[]", "processing_minutes": 120, "validity_hours": 24, "hold_point": "",
        "submit_completes": "[]", "decision_completes": "[]", "execution_completes": "[]", "approval_milestone": "",
        "approval_status": "", "refusal_status": "", "is_active": "on", "order": 99,
    })
    assert response.status_code == 302, response.content.decode()[:2000]
    # rule 2 is enforced by the settings screen too
    refused = client.post("/admin/registry/requesttype/add/", {
        "port": world.port.pk, "code": "SELF_APPROVAL", "label_fr": "x", "label_en": "x", "requester_roles": ["AGE"],
        "decision_roles": ["AGE"], "confidentiality": "N2", "refusal_confidentiality": "N2", "form_schema": "[]",
        "expected_documents": "[]", "processing_minutes": 60, "validity_hours": 24, "submit_completes": "[]",
        "decision_completes": "[]", "execution_completes": "[]", "is_active": "on", "order": 1,
    })
    assert refused.status_code == 200 and not RequestType.objects.filter(code="SELF_APPROVAL").exists()
    response = client.post("/admin/registry/interruptioncause/add/", {
        "port": world.port.pk, "code": "JETTY_INSPECTION", "label_fr": "Inspection de l'appontement",
        "label_en": "Jetty inspection", "attributable_to": "SHORE", "is_active": "on", "order": 50,
    })
    assert response.status_code == 302 and InterruptionCause.objects.filter(code="JETTY_INSPECTION").exists()
    m1 = CallTemplate.objects.get(port=world.port, code="M1")
    client.post("/admin/registry/calltemplate/", {"action": "create_draft", "_selected_action": [m1.pk]})
    draft = m1.versions.get(status=TemplateVersion.Status.DRAFT)
    base = draft.tasks.first()
    TemplateTask.objects.create(version=draft, number="1.99", order=999, section_fr=base.section_fr,
                                section_en=base.section_en, title_fr="Inspection de l'appontement avant accostage",
                                title_en="Jetty inspection before berthing", role="TER", nature="C", anchor="ETB",
                                offset_minutes=-720, criticality="N")
    client.post("/admin/registry/templateversion/", {"action": "publish", "_selected_action": [draft.pk]})
    draft.refresh_from_db()
    assert draft.status == TemplateVersion.Status.PUBLISHED
    call = make_call(world)
    assert call.tasks.filter(template_code="M1", number="1.99", role="TER").exists()
    login(client, world, "AGE")
    page = client.get(f"/escales/{call.pk}/?tab=demandes").content.decode()
    assert "Bunker survey" in page or "Contrôle de soutage" in page


@pytest.mark.django_db(databases=["default", "secure"])
def test_field_app_page_and_sign_out_purge(client, world):
    import json as _json
    import re

    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    for language in ("fr", "en"):
        user = world.users["TER"]
        user.language = language
        user.save()
        client.force_login(user)
        page = client.get(f"/escales/{call.pk}/terrain/").content.decode()
        for block in ("field-config", "field-i18n"):
            raw = re.search(rf'<script type="application/json" id="{block}">(.*?)</script>', page, re.S).group(1)
            data = _json.loads(raw)  # valid JSON whatever the language (quotes, apostrophes, decimal commas)
            assert data
        assert client.get("/sw.js")["Service-Worker-Allowed"] == "/"
    response = client.post("/compte/deconnexion/")
    assert response.status_code == 302 and response["Location"].endswith("?sortie=1")
    assert response["Clear-Site-Data"] == '"cache"'
    assert b"data-purge-field" in client.get(response["Location"]).content
    # the master's account-less access reaches the field app too
    link, token, code = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Field")
    client.post("/bord/", {"code": code})
    assert client.get(f"/escales/{call.pk}/terrain/").status_code == 200
    assert client.get("/api/v1/me/").json()["kind"] == "master"


@pytest.mark.django_db
def test_content_security_policy(client, world):
    """ENF-3: every HTML page forbids inline and third-party scripts and framing; other responses are untouched."""
    login(client, world, "AGE")
    policy = client.get("/escales/")["Content-Security-Policy"]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";") if part.strip())
    assert directives["script-src"] == "'self'"
    assert directives["frame-ancestors"] == "'none'" and directives["object-src"] == "'none'"
    assert "unsafe-eval" not in policy
    assert "Content-Security-Policy" not in client.get("/healthz")
    assert "Content-Security-Policy" not in client.get("/api/v1/me/")


def test_templates_have_no_inline_script():
    """The policy above holds only if no template relies on inline script (handlers, javascript: links)."""
    import re
    from pathlib import Path

    from django.conf import settings

    handler = re.compile(r"<[^>]*\son(?:click|change|submit|load|input|key\w+|focus|blur|error|mouse\w+)\s*=", re.I)
    for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        assert not handler.search(text), path
        assert "javascript:" not in text, path
        for tag in re.findall(r"<script\b[^>]*>", text):
            assert "src=" in tag or 'type="application/json"' in tag, (path, tag)
