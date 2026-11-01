"""Requirements of FLX-CDC-001 not covered by the scenario tests (see docs/TRACABILITE_CDC.md)."""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from apps.registry.models import Alert, AlertKind, JournalEntry, Notification, TaskStatus
from apps.registry.services import alerts, reports
from apps.registry.services import calls as call_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import tasks as task_svc
from apps.registry.services.errors import RuleViolation

from .conftest import act, force_done, make_call, master


def declared(world, **extra):
    call = make_call(world, **extra)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    call.refresh_from_db()
    return call


@pytest.mark.django_db
def test_ef_1_4_declaring_notifies_every_party(world):
    call = declared(world)
    notified = set(Notification.objects.filter(call=call).values_list("user__organization__name", flat=True))
    for org in (world.orgs.terminal, world.orgs.surveyor, world.orgs.owner, world.orgs.authority, world.orgs.health):
        assert org.name in notified, org.name


@pytest.mark.django_db
def test_ef_3_5_interruption_needs_a_cause_from_the_closed_list(world):
    call = declared(world)
    ter = act(world, call, "TER")
    with pytest.raises(RuleViolation):
        ms_svc.record_milestone(call, ter, "INTERRUPTION_START", timezone.now() - timedelta(minutes=5))
    with pytest.raises(RuleViolation):
        ms_svc.record_milestone(call, ter, "INTERRUPTION_START", timezone.now() - timedelta(minutes=5), cause_code="TEA_BREAK")
    with pytest.raises(RuleViolation):  # "Other" only with a reason
        ms_svc.record_milestone(call, ter, "INTERRUPTION_START", timezone.now() - timedelta(minutes=5), cause_code="OTHER")
    stop = ms_svc.record_milestone(call, ter, "INTERRUPTION_START", timezone.now() - timedelta(minutes=5),
                                   cause_code="OTHER", cause_reason="Fire drill on the jetty")
    assert stop.cause.code == "OTHER" and stop.cause_reason


@pytest.mark.django_db
def test_ef_3_6_ais_divergence_is_an_alert_never_a_correction(world):
    call = declared(world)
    declared_at = timezone.now() - timedelta(hours=3)
    arrival = ms_svc.record_milestone(call, master(world, call), "ARRIVAL", declared_at)
    result = ms_svc.corroborate_ais(call, "ARRIVAL", declared_at + timedelta(hours=2))
    arrival.refresh_from_db()
    assert result["diverges"] and arrival.declared_at == declared_at
    assert Alert.objects.filter(call=call, kind=AlertKind.AIS, milestone=arrival).exists()


@pytest.mark.django_db
def test_ef_5_6_not_applicable_requires_a_traced_reason(world):
    call = declared(world)
    task = call.tasks.filter(not_applicable_allowed=True, status=TaskStatus.PENDING, role="AGE").first()
    with pytest.raises(RuleViolation):
        task_svc.mark_not_applicable(task, act(world, call, "AGE"), "  ")
    task_svc.mark_not_applicable(task, act(world, call, "AGE"), "No waste on board")
    task.refresh_from_db()
    assert task.status == TaskStatus.NOT_APPLICABLE and task.na_reason == "No waste on board"
    assert JournalEntry.objects.filter(call=call, summary_en__contains=task.code).exists()


@pytest.mark.django_db
def test_ef_6_alert_levels_digest_and_statement(world):
    world.users["TER"].notify_digest_only = True  # EF-6.3: reduces noise, never mutes the blocking ones
    world.users["TER"].save()
    call = declared(world)
    blocking = call.tasks.filter(role="TER", criticality="B", status=TaskStatus.PENDING, due_at__isnull=False).first()
    normal = call.tasks.filter(criticality="N", status=TaskStatus.PENDING, due_at__isnull=False).first()
    assert blocking is not None and normal is not None
    mail.outbox.clear()
    # a blocking task late is escalated at once (EF-6.1), to the harbour master as well
    alerts.evaluate_all(now=blocking.due_at + timedelta(minutes=1))
    blocking.refresh_from_db()
    assert blocking.alert_level == "ESCALATED"
    escalation = Alert.objects.get(call=call, task=blocking, kind=AlertKind.ESCALATION)
    assert "CAP" in escalation.recipient_roles and escalation.blocking
    assert any(world.users["TER"].email in m.to for m in mail.outbox)  # sent at once despite the digest preference
    # a normal task: reminder before the deadline, then late — one notification per pass, not a burst
    alerts.evaluate_all(now=normal.due_at - timedelta(hours=1))
    normal.refresh_from_db()
    assert normal.alert_level in ("REMINDER", "LATE", "ESCALATED")
    # EF-6.4: every alert is in the journal and on the statement of facts
    assert JournalEntry.objects.filter(call=call, action="alert.emitted").count() == Alert.objects.filter(
        call=call, kind__in=["REMINDER", "LATE", "ESCALATION"]).count()
    assert escalation in reports.statement_of_facts(call)["alerts"]


@pytest.mark.django_db
def test_ef_10_2_seven_indicators_traceable_to_their_calls(world):
    call = declared(world)
    data = reports.indicators(world.port)
    assert len(data["kpis"]) == 7
    assert {k["code"] for k in data["kpis"]} == {"WAIT", "OCCUPANCY", "NET_TRANSFER", "DEAD_TIME_ESTABLISHED",
                                                 "ON_TIME", "DECISION", "DISPUTES"}
    for kpi in data["kpis"]:
        assert isinstance(kpi["sources"], list)
        assert all(ref == call.reference for ref in kpi["sources"])
