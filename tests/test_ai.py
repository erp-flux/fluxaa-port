"""EF-17 — the assistant proposes, people decide; the N4 domain never reaches it."""
from __future__ import annotations

import json
import pathlib
import re
from types import SimpleNamespace

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from apps.ai import client as ai_client
from apps.ai import services as ai
from apps.ai.models import AssistantRun, ExtractionReview
from apps.registry.models import Alert, JournalEntry
from apps.registry.services import calls as call_svc
from apps.registry.services import correspondence, reports
from apps.registry.services.documents import upload_document
from apps.registry.services.errors import PermissionRefused, RuleViolation

from .conftest import act, force_done, make_call, master

N4_MARKER = "ESCORT-ROUTE-SECRET-4471"


class FakeProvider:
    """Stands for the AI provider: records every request, answers after the schema it receives."""

    def __init__(self):
        self.requests = []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        schema = kwargs["output_config"]["format"]["schema"]
        props = schema["properties"]
        if "fields" in props:
            keys = props["fields"]["required"]
            answer = {"fields": {k: {"value": None, "evidence": None} for k in keys}}
            answer["fields"].update({"imo": {"value": "9999993", "evidence": "IMO No. 9999993"},
                                     "dwt": {"value": "45 500", "evidence": "Summer DWT 45,500 t"},
                                     "flag": {"value": "Liberia", "evidence": "Flag: Liberia"},
                                     "quantity": {"value": "29 950,5", "evidence": "Quantity 29,950.5 MT"}})
        elif "certificates" in props:
            answer = {"vessel_imo": "9999993", "certificates": [
                {"name": "IOPP", "number": "L-123", "issued_by": "Liberia", "expiry_date": "2027-01-31", "evidence": "IOPP"},
                {"name": "P&I blue card", "number": None, "issued_by": None,
                 "expiry_date": timezone.now().date().isoformat(), "evidence": "valid until"}]}
        elif "findings" in props:
            answer = {"findings": [{"severity": "high", "title": "NOR before arrival?", "detail": "Check the order.",
                                    "references": ["milestone NOR_TENDERED"]}]}
        else:
            answer = {"text": "Draft written from the registry."}
        return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(answer))])


@pytest.fixture
def provider(monkeypatch):
    fake = FakeProvider()
    monkeypatch.setattr(ai_client, "get_client", lambda: fake)
    return fake


@pytest.fixture
def ai_on(world, settings):
    settings.FLUXAA_AI_ENABLED = True
    settings.FLUXAA_AI_MODEL = "claude-sonnet-5-5"
    world.port.ai_assistance_enabled = True
    world.port.ai_agreement_reference = "DPA-PORT-2026-01"
    world.port.save()
    return world


def pdf(name: str) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, b"%PDF-1.4 demo content", content_type="application/pdf")


def declared(world):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    call.refresh_from_db()
    return call


@pytest.mark.django_db
def test_assistance_is_off_unless_the_platform_and_the_port_both_opt_in(world, provider, settings):
    call = declared(world)
    doc = upload_document(call, act(world, call, "AGE"), "Q88", pdf("q88.pdf"))
    settings.FLUXAA_AI_ENABLED = True
    with pytest.raises(RuleViolation):  # the port has not opted in
        ai.extract(doc, act(world, call, "AGE"))
    world.port.ai_assistance_enabled = True
    world.port.save()
    with pytest.raises(RuleViolation):  # opted in without the reference of its agreement
        ai.extract(doc, act(world, call, "AGE"))
    assert provider.requests == [] and not AssistantRun.objects.exists()


@pytest.mark.django_db
def test_extraction_stays_a_proposal_until_a_person_validates_it(client, ai_on, provider):
    world = ai_on
    call = declared(world)
    doc = upload_document(call, act(world, call, "AGE"), "Q88", pdf("q88.pdf"))
    review = ai.extract(doc, act(world, call, "AGE"))
    request = provider.requests[0]
    assert request["model"] == "claude-sonnet-5-5"
    assert request["messages"][0]["content"][0]["type"] == "document"
    assert request["output_config"]["format"]["type"] == "json_schema"
    world.vessel.refresh_from_db()
    assert review.status == "PROPOSED" and world.vessel.dwt == 45000  # nothing written yet
    run = review.run
    assert run.input_inventory == [f"document:{doc.pk}"] and len(run.input_digest) == 64

    client.force_login(world.users["AGE"])
    page = client.get(f"/escales/{call.pk}/assistant/verification/{review.pk}/").content.decode()
    assert 'class="prefilled"' in page and "prefill-tag" in page  # visually distinguished (EF-17)
    response = client.post(f"/escales/{call.pk}/assistant/verification/{review.pk}/",
                           {"decision": "validate", "keep": ["dwt", "flag"], "value_dwt": "45 500", "value_flag": "Liberia"})
    assert response.status_code == 302
    world.vessel.refresh_from_db()
    review.refresh_from_db()
    assert world.vessel.dwt == 45500 and review.status == "APPLIED" and review.validated_by == world.users["AGE"]
    entry = JournalEntry.objects.get(call=call, action="vessel.updated")
    assert entry.payload["assistant_run"] == run.pk and entry.actor_user == world.users["AGE"]
    with pytest.raises(RuleViolation):
        ai.validate_extraction(review, act(world, call, "AGE"), {"dwt": "1"})


@pytest.mark.django_db
def test_terminal_cannot_update_the_vessel_record_and_master_has_no_assistant(ai_on, provider):
    world = ai_on
    call = declared(world)
    doc = upload_document(call, act(world, call, "AGE"), "Q88", pdf("q88.pdf"))
    review = ai.extract(doc, act(world, call, "AGE"))
    with pytest.raises(PermissionRefused):
        ai.validate_extraction(review, act(world, call, "TER"), {"dwt": "1"})
    with pytest.raises(PermissionRefused):
        ai.review_call(call, master(world, call))


@pytest.mark.django_db
def test_certificates_feed_a_rule_check_and_findings_become_alerts_only_by_a_person(ai_on, provider):
    world = ai_on
    call = declared(world)
    nav = master(world, call)
    doc = upload_document(call, nav, "CERTIFICATES", pdf("certs.pdf"))
    review = ai.extract(doc, act(world, call, "AGE"))
    ai.validate_extraction(review, act(world, call, "AGE"), review.proposed["certificates"])
    findings = ai.deterministic_findings(call, act(world, call, "AGE"))
    assert [f["title"] for f in findings] == ["Certificate expiring before departure: P&I blue card"]
    run = ai.review_call(call, act(world, call, "AGE"))
    assert not Alert.objects.filter(call=call, kind="ASSISTANT").exists()  # a finding is not an alert
    alert = ai.raise_finding(run, 0, act(world, call, "AGE"))
    assert alert.kind == "ASSISTANT" and "raised by AGE" in alert.message_en
    with pytest.raises(PermissionRefused):  # only the person who ran the review
        ai.raise_finding(run, 0, act(world, call, "CAP"))


@pytest.mark.django_db(databases=["default", "secure"])
def test_no_n4_object_ever_reaches_the_assistant(ai_on, provider):
    from apps.secure import services as n4

    world = ai_on
    call = declared(world)
    n4.deposit(call, act(world, call, "AGE"), kind="ESCORT", payload={"escort": N4_MARKER, "details": N4_MARKER})
    thread = correspondence.create_thread(call, act(world, call, "TER"), subject="Rate", participant_roles=["NAV", "AGE"],
                                          body="Reduce to 600 m3/h at 15:50.")
    doc = upload_document(call, act(world, call, "AGE"), "Q88", pdf("q88.pdf"))
    for role in ("AGE", "CAP"):  # CAP can read the security space; the assistant still never does
        ai.review_call(call, act(world, call, role))
    ai.extract(doc, act(world, call, "AGE"))
    ai.summarize_thread(thread, act(world, call, "AGE"))
    call.status = "DEPARTED"
    ai.draft_remarks(call, act(world, call, "AGE"))
    sent = json.dumps(provider.requests, default=str)
    assert len(provider.requests) == 5
    assert N4_MARKER not in sent and "ESCORT" not in sent
    # structural guarantee: the assistance code never imports the security domain
    import_secure = re.compile(r"^\s*(from\s+apps\.secure|import\s+apps\.secure|from\s+apps\s+import\s+.*\bsecure\b)", re.M)
    for source in pathlib.Path(ai.__file__).parent.rglob("*.py"):
        assert not import_secure.search(source.read_text()), source.name


@pytest.mark.django_db
def test_payload_is_scoped_to_the_reader_and_carries_no_person(ai_on, provider):
    world = ai_on
    call = declared(world)
    upload_document(call, act(world, call, "COM"), "CP_RECAP", pdf("recap.pdf"), counterpart_role="AGE")
    ai.review_call(call, act(world, call, "TER"))
    sent = json.dumps(provider.requests[-1]["messages"], default=str)
    assert "CP_RECAP" not in sent  # bilateral COM/AGE document, invisible to the terminal
    for user in world.users.values():
        assert user.full_name not in sent and user.email not in sent
    ai.review_call(call, act(world, call, "AGE"))
    assert "CP_RECAP" in json.dumps(provider.requests[-1]["messages"], default=str)


def test_the_assistant_code_has_no_path_into_decisions():
    forbidden = ["decide_request", "sign_task", "countersign_task", "sign_document", "close_call", "archive_call",
                 "countersign_milestone", "record_milestone", "issue_statement_of_facts", "add_value", "execute_request"]
    for source in pathlib.Path(ai.__file__).parent.glob("*.py"):
        text = source.read_text()
        for name in forbidden:
            assert name not in text, f"{source.name} references {name}"


@pytest.mark.django_db
def test_statement_states_remarks_drafted_with_the_assistant(world):
    call = declared(world)
    call.status = "DEPARTED"
    call.save(update_fields=["status"])
    doc = reports.issue_statement_of_facts(call, act(world, call, "AGE"), remarks="Waiting 6 h at anchorage.",
                                           remarks_assisted=True)
    html = doc.file.open("rb").read().decode()
    assert "Waiting 6 h at anchorage." in html and "Drafted with the AI assistant" in html


@pytest.mark.django_db
def test_provider_failure_is_traced_and_never_breaks_the_registry(ai_on, monkeypatch):
    world = ai_on
    call = declared(world)

    class Down:
        messages = None

        def __init__(self):
            self.messages = self

        def create(self, **kwargs):
            raise TimeoutError("provider down")

    monkeypatch.setattr(ai_client, "get_client", lambda: Down())
    with pytest.raises(ai_client.AssistantUnavailable):
        ai.review_call(call, act(world, call, "AGE"))
    run = AssistantRun.objects.get(call=call)
    assert run.status == "ERROR" and "TimeoutError" in run.error
    assert ExtractionReview.objects.count() == 0
    call.refresh_from_db()
    assert call.status == "DECLARED"


@pytest.mark.django_db(databases=["default", "secure"])
def test_call_pages_show_the_assistant_only_when_enabled(client, world, provider, settings):
    call = declared(world)
    upload_document(call, act(world, call, "AGE"), "Q88", pdf("q88.pdf"))
    correspondence.create_thread(call, act(world, call, "AGE"), subject="Docs", participant_roles=["TER"], body="Q88 sent.")
    client.force_login(world.users["AGE"])
    page = client.get(f"/escales/{call.pk}/?tab=documents").content.decode()
    assert "/assistant/" not in page  # off by default
    settings.FLUXAA_AI_ENABLED = True
    world.port.ai_assistance_enabled = True
    world.port.ai_agreement_reference = "DPA-PORT-2026-01"
    world.port.save()
    for tab in ("apercu", "documents", "echanges", "mesures"):
        response = client.get(f"/escales/{call.pk}/?tab={tab}")
        assert response.status_code == 200, tab
    assert "/assistant/extraction/" in client.get(f"/escales/{call.pk}/?tab=documents").content.decode()
    response = client.post(f"/escales/{call.pk}/assistant/revue/")
    assert response.status_code == 302
    overview = client.get(f"/escales/{call.pk}/?tab=apercu").content.decode()
    assert "NOR before arrival?" in overview and "/alerte/0/" in overview
    thread = call.threads.get()
    client.post(f"/escales/{call.pk}/assistant/echange/{thread.pk}/")
    assert "Draft written from the registry." in client.get(f"/escales/{call.pk}/?tab=echanges").content.decode()


# ============================================================================ port level: brief and questions
@pytest.mark.django_db(databases=["default", "secure"])
def test_port_brief_and_question_draw_on_the_registry_the_reader_may_see(ai_on, provider):
    from apps.registry.services import rights
    from apps.secure import services as n4

    world = ai_on
    call = declared(world)
    n4.deposit(call, act(world, call, "AGE"), kind="ESCORT", payload={"escort": N4_MARKER, "details": N4_MARKER})
    port = world.port
    from apps.registry.services.context import port_actor

    dir_actor = port_actor(world.users["DIR"])
    visible = rights.call_queryset_for_user(world.users["DIR"])
    run = ai.port_brief(port, dir_actor, visible_calls=visible)
    assert run.feature == "BRIEF" and run.call is None and run.port == port and run.status == "OK"
    assert run.output["text"] == "Draft written from the registry."
    sent = provider.requests[-1]["messages"][0]["content"][0]["text"]
    digest = json.loads(sent)
    assert digest["calls"][0]["reference"] == call.reference and "indicators_90_days" in digest and "ais" in digest
    assert digest["calls"][0]["pending_decisions"][0]["type"] == "GREEN_LIGHT"
    sent = json.dumps(provider.requests[-1], default=str)
    assert N4_MARKER not in sent and "ESCORT" not in sent
    for user in world.users.values():
        assert user.full_name not in sent and user.email not in sent
    assert f"call:{call.pk}" in run.input_inventory and "ais:board" in run.input_inventory
    # a question goes with the same digest; an empty or oversized question is refused before any request
    question = ai.ask_port(port, dir_actor, "Which calls wait for a decision?", visible_calls=visible)
    assert question.feature == "QUESTION" and "Question: Which calls" in json.dumps(provider.requests[-1], default=str)
    with pytest.raises(RuleViolation):
        ai.ask_port(port, dir_actor, "   ", visible_calls=visible)
    with pytest.raises(RuleViolation):
        ai.ask_port(port, dir_actor, "x" * (ai.QUESTION_MAX_CHARS + 1), visible_calls=visible)
    assert len(provider.requests) == 2
    # the port-level features are for the management of the port, not for the parties of a call
    with pytest.raises(PermissionRefused):
        ai.port_brief(port, port_actor(world.users["TER"]), visible_calls=rights.call_queryset_for_user(world.users["TER"]))
    assert JournalEntry.objects.filter(action="assistant").count() == 0  # audit trail, not the call journal
    assert AssistantRun.objects.filter(call__isnull=True).count() == 2


@pytest.mark.django_db(databases=["default", "secure"])
def test_port_assistant_page(client, world, provider, settings):
    declared(world)
    client.force_login(world.users["DIR"])
    assert client.get("/assistant/").status_code == 404  # off by default, and absent from the menu
    assert 'href="/assistant/"' not in client.get("/").content.decode()
    settings.FLUXAA_AI_ENABLED = True
    world.port.ai_assistance_enabled = True
    world.port.ai_agreement_reference = "DPA-PORT-2026-01"
    world.port.save()
    assert 'href="/assistant/"' in client.get("/").content.decode()
    page = client.get("/assistant/")
    assert page.status_code == 200 and "Draft written" not in page.content.decode()
    assert client.post("/assistant/", {"action": "brief"}).status_code == 302
    assert client.post("/assistant/", {"action": "ask", "question": "What is alongside?"}).status_code == 302
    html = client.get("/assistant/").content.decode()
    assert html.count("Draft written from the registry.") == 2 and "ais:board" in html
    # another person does not see these results: they are personal
    client.logout()
    client.force_login(world.users["CAP"])
    from apps.core import mfa

    cap = world.users["CAP"]
    cap.set_mfa_secret(mfa.new_secret())
    cap.mfa_enabled = True
    cap.save()
    session = client.session
    session.update(mfa.stamp(cap))
    session.save()
    assert "Draft written" not in client.get("/assistant/").content.decode()
    client.logout()
    client.force_login(world.users["TER"])
    assert client.get("/assistant/").status_code == 404
