"""Integrity, rights and invariants — the acceptance criteria attached to EF-1 … EF-18 and ENF-3/4."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.utils import timezone

from apps.core.guards import ImmutableRecordError
from apps.registry.models import (
    Authorization,
    CallParty,
    JournalEntry,
    RequestStatus,
    TemplateTask,
    Thread,
)
from apps.registry.services import calls as call_svc
from apps.registry.services import correspondence, journal, rights
from apps.registry.services import milestones as ms_svc
from apps.registry.services import requests as req_svc
from apps.registry.services.context import actor_for_call
from apps.registry.services.errors import NotVisible, PermissionRefused, RuleViolation, StrongAuthRequired

from .conftest import act, force_done, make_call


def declared(world, **kw):
    call = make_call(world, **kw)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    call.refresh_from_db()
    return call


@pytest.mark.django_db
def test_database_refuses_update_and_delete(world):
    call = declared(world)
    entry = JournalEntry.objects.filter(call=call).first()
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE registry_journalentry SET summary_fr = 'altered' WHERE id = %s", [entry.pk])
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("DELETE FROM registry_portcall WHERE id = %s", [call.pk])
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("TRUNCATE registry_milestone CASCADE")
    with pytest.raises(DatabaseError), transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("UPDATE registry_portcall SET reference = 'X' WHERE id = %s", [call.pk])
    with pytest.raises(ImmutableRecordError):
        call.delete()
    with pytest.raises(ImmutableRecordError):
        JournalEntry.objects.filter(call=call).update(summary_fr="x")
    with pytest.raises(ImmutableRecordError):
        entry.save()


@pytest.mark.django_db
def test_journal_chain_detects_tampering(world):
    declared(world)
    assert journal.verify_chain(world.port)["ok"]
    victim = JournalEntry.objects.filter(port=world.port).order_by("seq")[1]
    with connection.cursor() as cur:  # a superuser bypassing the triggers is still detected
        cur.execute("SET LOCAL session_replication_role = replica")
        cur.execute("UPDATE registry_journalentry SET summary_fr = 'falsifié' WHERE id = %s", [victim.pk])
        cur.execute("SET LOCAL session_replication_role = origin")
    result = journal.verify_chain(world.port)
    assert not result["ok"] and result["broken_at"] == victim.seq


@pytest.mark.django_db
def test_only_agency_creates_and_rights_on_call(world):
    with pytest.raises(PermissionRefused):
        call_svc.create_call(world.users["TER"], vessel=world.vessel, eta=timezone.now(), requested_berth_kind="JETTY",
                             operations=["M1"])
    call = declared(world)
    # EF-5.7: a terminal user cannot list the agency's tasks
    ter_tasks = rights.visible_tasks(act(world, call, "TER"), call)
    assert ter_tasks.exists()
    assert not ter_tasks.filter(role="AGE").exclude(co_roles__contains=["TER"]).exists()
    assert rights.visible_tasks(act(world, call, "AGE"), call).filter(role="TER").exists()
    # EF-12.5: owners/charterers cannot create an event
    with pytest.raises(PermissionRefused):
        ms_svc.record_milestone(call, act(world, call, "COM"), "ARRIVAL", timezone.now())
    # single emitter: the terminal cannot record "all fast"
    with pytest.raises(PermissionRefused):
        ms_svc.record_milestone(call, act(world, call, "TER"), "ALL_FAST", timezone.now())
    # revocation removes access immediately, history kept
    party = call.parties.get(organization=world.orgs.terminal, role="TER")
    call_svc.revoke_party(call, act(world, call, "AGE"), party, "terminal changed")
    with pytest.raises(NotVisible):
        actor_for_call(call, user=world.users["TER"])
    assert CallParty.objects.filter(pk=party.pk, revoked_at__isnull=False).exists()
    # draft calls are invisible to the other parties
    draft = make_call(world)
    with pytest.raises(NotVisible):
        rights.ensure_visible(rights.draft_visible(act(world, draft, "CAP"), draft))


@pytest.mark.django_db
def test_rule_two_request_decision_and_strong_auth(world):
    call = declared(world)
    vet = req_svc.create_request(call, act(world, call, "TER"), "VESSEL_ACCEPTANCE", {
        "product": "Gasoil", "inspection": "SIRE", "last_cargoes": "x", "vetting_result": "ok"})
    with pytest.raises(PermissionRefused):  # the requesting role never decides
        req_svc.decide_request(vet, act(world, call, "TER"), RequestStatus.APPROVED)
    with pytest.raises(StrongAuthRequired):
        req_svc.decide_request(vet, act(world, call, "CAP", strong=False), RequestStatus.APPROVED)
    with pytest.raises(RuleViolation):  # a refusal states its reason
        req_svc.decide_request(vet, act(world, call, "CAP"), RequestStatus.REFUSED, reason="")
    with pytest.raises(RuleViolation):  # an authorization always expires after its effective date
        req_svc.decide_request(vet, act(world, call, "CAP"), RequestStatus.APPROVED,
                               valid_from=timezone.now(), valid_until=timezone.now() - timedelta(hours=1))
    auth = req_svc.decide_request(vet, act(world, call, "CAP"), RequestStatus.APPROVED)
    assert auth.valid_until > auth.valid_from and len(auth.verification_code) == 10
    info = req_svc.verify_authorization(auth.verification_code)
    assert info["valid_now"] and info["vessel"] == "MT TEST SPIRIT"
    with pytest.raises(ImmutableRecordError):
        Authorization.objects.filter(pk=auth.pk).update(valid_until=None)
    expired = req_svc.expire_authorizations(auth.valid_until + timedelta(minutes=1))
    assert expired == 1


@pytest.mark.django_db
def test_disputes_never_rejected_and_block_closure(world):
    from apps.registry.services import disputes

    call = declared(world)
    force_done(call, ["M0:25"])
    fast = ms_svc.record_milestone(call, act(world, call, "SVC"), "ALL_FAST", timezone.now())
    ms_svc.countersign_milestone(fast, act(world, call, "TER"), contest=True,
                                 comment="Time recorded by the shore is 14:05")
    dispute = call.disputes.get()
    assert not hasattr(disputes, "reject")
    with pytest.raises(PermissionRefused):  # the harbour master cannot impose an "agreement"
        disputes.close(dispute, act(world, call, "CAP"), agreed=True, text="settled")
    from apps.registry.services import holdpoints

    _t, _m, reasons = holdpoints.evaluate(call, "CLOSE")
    assert any("contestation" in fr for fr, _en in reasons)
    disputes.respond(dispute, act(world, call, "SVC"), "Our pilot log shows 13:58")
    disputes.close(dispute, act(world, call, "TER"), agreed=False, text="No agreement")
    _t, _m, reasons = holdpoints.evaluate(call, "CLOSE")
    assert not any("contestation" in fr for fr, _en in reasons)


@pytest.mark.django_db
def test_no_free_messaging_and_bilateral_threads(world):
    call = declared(world)
    with pytest.raises(RuleViolation):
        correspondence.create_thread(None, act(world, call, "AGE"), subject="x", participant_roles=["TER"], body="y")
    thread = correspondence.create_thread(call, act(world, call, "AGE"), subject="Shore tank line-up",
                                          participant_roles=["TER"], body="Please confirm tanks", confidentiality="N3")
    assert rights.thread_visible(act(world, call, "TER"), thread)
    assert not rights.thread_visible(act(world, call, "INS"), thread)
    assert not rights.thread_visible(act(world, call, "DIR"), thread)
    assert Thread.objects.filter(call__isnull=True).count() == 0


@pytest.mark.django_db
def test_templates_versioned_and_frozen(world):
    task = TemplateTask.objects.filter(version__template__port=world.port, version__template__code="M0").first()
    task.title_fr = "changed"
    with pytest.raises(ImmutableRecordError):
        task.save()
    call = declared(world)
    use = call.template_uses.select_related("template_version").first()
    assert use.template_version.number == 1


@pytest.mark.django_db
def test_master_access_without_account(world):
    call = declared(world)
    link, token, code = call_svc.issue_master_link(call, act(world, call, "AGE"), master_name="Capt. Ade")
    assert call_svc.authenticate_master(token=token) == link
    assert call_svc.authenticate_master(code=code.lower()) == link
    nav = actor_for_call(call, master=link)
    force_done(call, ["M0:25"])
    fast = ms_svc.record_milestone(call, act(world, call, "SVC"), "ALL_FAST", timezone.now())
    sig = ms_svc.countersign_milestone(fast, nav)
    assert sig.signer_label.startswith("Capt. Ade") and sig.master_id == link.pk
    with pytest.raises(PermissionRefused):  # no right to create a request
        req_svc.create_request(call, nav, "BERTH", {})
    call_svc.revoke_master_link(link, act(world, call, "AGE"), "crew change")
    assert call_svc.authenticate_master(token=token) is None


@pytest.mark.django_db
def test_operation_area_selects_tasks_and_modules(world):
    partner = make_call(world, operations=("M1",))
    sts = make_call(world, operations=("M3",), kind="STS_AREA", linked_call=partner, link_kind="STS",
                    parties=[(world.orgs.sts, "PRE"), (world.orgs.surveyor, "INS"), (world.orgs.owner, "COM")])
    codes = set(sts.template_codes)
    assert {"M0", "M3", "MA3"} <= codes  # anchorage stay added by nature of the area
    assert not sts.tasks.filter(template_code="M0", number__in=["26", "27", "28", "29", "31"]).exists()
    assert sts.tasks.filter(template_code="M0", number="35b").exists()
    alone = make_call(world, operations=("M3",), kind="STS_AREA")
    force_done(alone, ["M0:02", "M0:03", "M0:05"])
    with pytest.raises(RuleViolation):  # STS links two calls: no declaration without the partner
        call_svc.declare_call(alone, act(world, alone, "AGE"))
    partner.refresh_from_db()
    assert partner.linked_call_id == sts.pk and partner.link_kind == "STS"  # reciprocal link
    with pytest.raises(RuleViolation):
        make_call(world, operations=("M1",), kind="ANCHORAGE")  # discharge is a quay operation


@pytest.mark.django_db
def test_measurement_single_emitter_and_discrepancy(world):
    from apps.registry.models import Alert, Measurement
    from apps.registry.services import measurements as meas

    call = declared(world)
    m = meas.create_measurement(call, act(world, call, "INS"), Measurement.Kind.FINAL)
    with pytest.raises(PermissionRefused):
        meas.add_value(m, act(world, call, "TER"), "SHIP", 100)
    meas.add_value(m, act(world, call, "TER"), "SHORE", "1000")
    assert not m.is_complete
    from apps.registry.services import holdpoints

    _t, _m, reasons = holdpoints.evaluate(call, "CLOSE")
    assert any("incomplète" in fr for fr, _en in reasons)
    from .conftest import master

    meas.add_value(m, master(world, call), "SHIP", "1010")
    assert m.exceeds_tolerance()
    assert Alert.objects.filter(call=call, kind="QUANTITY").exists()
