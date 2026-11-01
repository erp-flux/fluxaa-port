"""Task alerts and escalation (EF-6).

Levels: reminder (assigned role) → late (assigned role + agency) → escalation (organisation in
charge + harbour master; SMS). Each alert is recorded as a piece of the file and appears on the
statement of facts. Notifications are grouped per recipient and call for one evaluation pass, so a
cascade of deadline changes never produces a burst of messages (S3).
"""
from __future__ import annotations

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.core.roles import role_label

from ..models import ACTIVE_STATUSES, Alert, AlertKind, AlertLevel, PortCall, Task, TaskStatus
from . import journal
from .calls import LEVEL_RANK, alert_level_for, call_url
from .notifications import send_sms, users_for_roles

KIND_FOR_LEVEL = {AlertLevel.REMINDER: AlertKind.REMINDER, AlertLevel.LATE: AlertKind.LATE,
                  AlertLevel.ESCALATED: AlertKind.ESCALATION}


def recipients_for(task: Task, level: str) -> list[str]:
    roles = [task.role] if task.role != "ANY" else ["AGE"]
    if level in (AlertLevel.LATE, AlertLevel.ESCALATED):
        roles.append("AGE")
    if level == AlertLevel.ESCALATED:
        roles.append("CAP")
    return sorted(set(roles))


def evaluate_call(call: PortCall, now=None) -> list[Alert]:
    now = now or timezone.now()
    emitted: list[Alert] = []
    for task in call.tasks.filter(status=TaskStatus.PENDING, due_at__isnull=False):
        target = alert_level_for(task, call.port, now)
        if LEVEL_RANK[target] <= LEVEL_RANK[task.alert_level]:
            if LEVEL_RANK[target] < LEVEL_RANK[task.alert_level]:
                task.alert_level = target
                task.save(update_fields=["alert_level"])
            continue
        with transaction.atomic():
            task.alert_level = target
            task.save(update_fields=["alert_level"])
            roles = recipients_for(task, target)
            label_fr = {AlertLevel.REMINDER: "Rappel", AlertLevel.LATE: "Retard", AlertLevel.ESCALATED: "Escalade"}[target]
            label_en = {AlertLevel.REMINDER: "Reminder", AlertLevel.LATE: "Late", AlertLevel.ESCALATED: "Escalation"}[target]
            alert = Alert.objects.create(
                call=call, kind=KIND_FOR_LEVEL[target], task=task, blocking=task.is_blocking, recipient_roles=roles,
                template_code=task.template_code,
                message_fr=f"{label_fr} — tâche {task.code} « {task.title_fr} » ({role_label(task.role)}), échéance {task.due_at:%d/%m %H:%M} UTC",
                message_en=f"{label_en} — task {task.code} “{task.title_en}” ({task.role}), due {task.due_at:%Y-%m-%d %H:%M} UTC",
            )
            journal.record(port=call.port, call=call, actor=None, role="SYSTEM", action="alert.emitted", obj=alert,
                           visible_roles=sorted({*roles, "CAP", "AGE"}), summary_fr=alert.message_fr,
                           summary_en=alert.message_en, payload={"level": target, "task": task.code})
        emitted.append(alert)
    return emitted


def notify_grouped(call: PortCall, alerts: list[Alert], stamp: str) -> int:
    """One notification per recipient for the alerts of this pass (anti-burst)."""
    by_user: dict[int, list[Alert]] = defaultdict(list)
    users = {}
    for alert in alerts:
        for user in users_for_roles(call, alert.recipient_roles):
            by_user[user.pk].append(alert)
            users[user.pk] = user
    created = 0
    for user_pk, user_alerts in by_user.items():
        blocking = any(a.blocking or a.kind == AlertKind.ESCALATION for a in user_alerts)
        escalation = any(a.kind == AlertKind.ESCALATION for a in user_alerts)
        if len(user_alerts) == 1:
            title_fr, title_en = user_alerts[0].message_fr, user_alerts[0].message_en
        else:
            title_fr = f"{call.reference} : {len(user_alerts)} tâches en rappel, retard ou escalade"
            title_en = f"{call.reference}: {len(user_alerts)} tasks reminded, late or escalated"
        from ..models import Notification

        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    user=users[user_pk], call=call, alert=user_alerts[0], dedupe_key=f"alerts:{call.pk}:{stamp}",
                    title_fr=f"{call.reference} — {title_fr}"[:300] if len(user_alerts) == 1 else title_fr[:300],
                    title_en=f"{call.reference} — {title_en}"[:300] if len(user_alerts) == 1 else title_en[:300],
                    url=call_url(call) + "#taches", realtime=blocking, blocking=blocking,
                )
        except Exception:
            continue
        created += 1
        from .notifications import _send_email_now

        if blocking or not users[user_pk].notify_digest_only:
            _send_email_now(note)
        if escalation and users[user_pk].phone:
            send_sms(users[user_pk].phone, note.title_fr if (users[user_pk].language or "fr") == "fr" else note.title_en)
            note.sms_sent_at = timezone.now()
            note.save(update_fields=["sms_sent_at"])
    # Escalation also goes to the organisation in charge (its official phone / e-mail)
    for alert in alerts:
        if alert.kind == AlertKind.ESCALATION and alert.task_id:
            for party in call.parties.filter(role=alert.task.role, revoked_at__isnull=True).select_related("organization"):
                if party.organization.phone:
                    send_sms(party.organization.phone, alert.message_fr)
    return created


def evaluate_all(now=None) -> dict:
    now = now or timezone.now()
    stamp = now.strftime("%Y%m%d%H%M")
    total_alerts = 0
    total_notes = 0
    for call in PortCall.objects.filter(status__in=ACTIVE_STATUSES + ["DEPARTED"]).select_related("port"):
        alerts = evaluate_call(call, now)
        total_alerts += len(alerts)
        if alerts:
            total_notes += notify_grouped(call, alerts, stamp)
    return {"alerts": total_alerts, "notifications": total_notes}
