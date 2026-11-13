"""Preparing the declaration of a call (FLX-CDC-002 v1.4, EXG-Q-09).

The declaration is a hold point: it waits for the vessel dataset, the master's certificates and the sanctions
screening. The agency that created the call is told what is missing and who answers for it, with a way to act at
once: provide the document itself (the agency may file the certificates on the master's behalf), confirm the
check, hand the master his access — which now carries, by e-mail, the list of what is expected from him — and
remind a party of a pending task. Every reminder is a notification and a journal entry, never a free message.
"""
from __future__ import annotations

from django.conf import settings
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import User
from apps.core.roles import role_label

from ..models import JournalEntry, Nature, Task, TaskStatus, Transition
from . import holdpoints, journal
from .calls import call_url
from .errors import PermissionRefused, RuleViolation
from .notifications import notify


def master_link(call):
    """The master's valid access link of the call, if any."""
    now = timezone.now()
    for link in call.master_links.filter(role="NAV", revoked_at__isnull=True, expires_at__gt=now).order_by("-issued_at"):
        if link.is_valid(now):
            return link
    return None


def responsible(call, task: Task) -> list[dict]:
    """Who answers for a task: each organisation holding its role (or a co-role) on the call, with whether its
    people can act — an account holding the role, or, for the ship, the master's access link."""
    now = timezone.now()
    rows = []
    for role in task.all_roles:
        if role == "ANY":
            continue
        if role == "NAV":
            link = master_link(call)
            rows.append({"role": role, "label": role_label(role), "organization": None, "name": str(call.vessel),
                         "can_act": link is not None, "link": link, "users": 0,
                         "how": _("master's access link") if link else _("no valid master access: issue it (Parties tab)")})
            continue
        parties = [p for p in call.parties.filter(role=role, revoked_at__isnull=True).select_related("organization")
                   if p.is_active_at(now)]
        for party in parties:
            users = User.objects.filter(organization=party.organization, is_active=True, roles__contains=[role]).count()
            links = call.master_links.filter(role=role, organization=party.organization, revoked_at__isnull=True,
                                             expires_at__gt=now).exists()
            rows.append({"role": role, "label": role_label(role), "organization": party.organization,
                         "name": party.organization.name, "can_act": users > 0 or links, "users": users, "link": None,
                         "how": _("%(n)d account(s)") % {"n": users} if users else (_("access link") if links else _("no account, no link"))})
        if not parties:
            rows.append({"role": role, "label": role_label(role), "organization": None, "name": _("(no party holds this role)"),
                         "can_act": False, "users": 0, "link": None, "how": _("invite the party (Parties tab)")})
    return rows


def hint(task: Task) -> dict:
    """How the task is completed, for the screen: the document to provide, the check to confirm, the request to
    file or decide, the milestone to record."""
    if task.document_type_code:
        return {"kind": "document", "code": task.document_type_code, "tab": "documents",
                "query": f"?tab=documents&type={task.document_type_code}&task={task.pk}"}
    if task.request_type_code:
        return {"kind": "request", "code": task.request_type_code, "tab": "demandes",
                "query": f"?tab=demandes&type={task.request_type_code}" if task.request_side == "submit" else "?tab=demandes"}
    if task.milestone_codes:
        return {"kind": "milestone", "code": ", ".join(task.milestone_codes), "tab": "jalons", "query": "?tab=jalons"}
    return {"kind": "confirm" if task.nature in (Nature.C, Nature.R) else "task", "code": "", "tab": "taches", "query": "?tab=taches&mine=1"}


def last_reminder(call, task: Task):
    return JournalEntry.objects.filter(call=call, action="task.reminded", object_id=task.pk, object_kind="task").order_by("-seq").first()


def readiness(call, actor=None) -> dict:
    """What the declaration waits for, who answers for each item, and what the actor may do about it."""
    tasks, _entries, reasons = holdpoints.evaluate(call, Transition.DECLARE)
    items = []
    for task in tasks:
        who = responsible(call, task)
        can_act = actor is not None and (task.role in actor.roles or bool(set(task.co_roles) & set(actor.roles))
                                         or task.role == "ANY") and not actor.has("COM")
        reminder = last_reminder(call, task)
        items.append({"task": task, "responsible": who, "hint": hint(task), "can_act": can_act,
                      "can_remind": actor is not None and actor.has("AGE", "CAP"),
                      "reminded_at": reminder.at if reminder else None,
                      "needs_master_link": task.role == "NAV" and master_link(call) is None})
    return {"items": items, "reasons": reasons, "ready": not items and not reasons}


def remind(call, actor, task: Task) -> int:
    """The agency or the harbour master reminds the party of a pending task: a real-time notification to every
    account holding the role on the call; for the ship, an e-mail to the address the master's access was sent to.
    Returns the number of people reached."""
    if not actor.has("AGE", "CAP"):
        raise PermissionRefused(_("The agency or the harbour master sends the reminders."))
    if task.call_id != call.pk or task.status != TaskStatus.PENDING:
        raise RuleViolation(_("This task is not pending."))
    now = timezone.now()
    reached = 0
    roles = [r for r in task.all_roles if r != "ANY"]
    if "NAV" in roles:
        link = master_link(call)
        if link is None:
            raise RuleViolation(_("The master has no valid access: issue it from the Parties tab — the access e-mail "
                                  "lists what is expected from him."))
        if link.sent_to:
            reached += int(send_task_reminder(call, link.sent_to, [task], lang=call.port.default_language))
        else:
            raise RuleViolation(_("The master's access was handed over without an e-mail address: remind him by the "
                                  "channel it was handed with (%(channel)s).") % {"channel": link.get_delivery_channel_display()})
    account_roles = [r for r in roles if r != "NAV" and r not in actor.roles]  # the sender does not remind itself
    if account_roles:
        reached += notify(call, account_roles, key=f"remind:{task.pk}:{now:%Y%m%d%H%M}", realtime=True,
                          title_fr=f"{call.reference} : rappel — tâche {task.code} « {task.title_fr} » attendue de {', '.join(role_label(r) for r in account_roles)}",
                          title_en=f"{call.reference}: reminder — task {task.code} “{task.title_en}” expected from {', '.join(account_roles)}",
                          url=call_url(call) + hint(task)["query"], exclude_user=None)
    journal.record(port=call.port, call=call, actor=actor, action="task.reminded", obj=task, object_kind="task",
                   visible_roles=sorted({"AGE", "CAP", *roles}),
                   summary_fr=f"Rappel envoyé pour la tâche {task.code} « {task.title_fr} » ({', '.join(role_label(r) for r in roles)}) — {reached} destinataire(s)",
                   summary_en=f"Reminder sent for task {task.code} “{task.title_en}” ({', '.join(roles)}) — {reached} recipient(s)",
                   payload={"reached": reached, "roles": roles})
    return reached


def master_pending_tasks(call) -> list[Task]:
    return list(call.tasks.filter(status=TaskStatus.PENDING).filter(role="NAV").order_by("order"))


def access_mail(call, link, token: str, code: str, email: str) -> bool:
    """The master's access, sent by e-mail with the list of what the platform expects from him before the
    declaration and the arrival — so that whoever is concerned by the missing information holds the means to
    provide it (EXG-Q-09)."""
    lang = call.port.default_language or "fr"
    url = f"{settings.SITE_URL}{reverse('registry:master_token', args=[token])}"
    entry = f"{settings.SITE_URL}{reverse('registry:master_entry')}"
    pending = master_pending_tasks(call)
    if lang == "en":
        lines = [f"- {t.code} {t.title_en}" + (f" (before {t.due_at:%Y-%m-%d %H:%M} UTC)" if t.due_at else "") for t in pending]
        subject = f"[FLUXAA Port] Call {call.reference} — {call.vessel.name}: your access as master"
        body = (f"Captain {link.master_name},\n\nThe port of {call.port.name} expects your vessel {call.vessel.name} "
                f"(call {call.reference}, ETA {call.eta:%Y-%m-%d %H:%M} UTC). Your agency {call.agency} has opened your "
                f"access to the call:\n{url}\n\nOr go to {entry} and enter the code {code}.\n\n"
                "What the port expects from you now:\n" + ("\n".join(lines) if lines else "- nothing yet") +
                "\n\nThis access is personal and nominative; it is valid until shortly after your departure. Do not "
                "forward it.\n")
    else:
        lines = [f"- {t.code} {t.title_fr}" + (f" (avant le {t.due_at:%d/%m/%Y %H:%M} UTC)" if t.due_at else "") for t in pending]
        subject = f"[FLUXAA Port] Escale {call.reference} — {call.vessel.name} : votre accès capitaine"
        body = (f"Commandant {link.master_name},\n\nLe port de {call.port.name} attend votre navire {call.vessel.name} "
                f"(escale {call.reference}, ETA {call.eta:%d/%m/%Y %H:%M} UTC). Votre agence {call.agency} a ouvert votre "
                f"accès à l'escale :\n{url}\n\nOu rendez-vous sur {entry} et saisissez le code {code}.\n\n"
                "Ce que le port attend de vous dès maintenant :\n" + ("\n".join(lines) if lines else "- rien pour l'instant") +
                "\n\nCet accès est personnel et nominatif ; il est valable jusqu'à peu après votre appareillage. Ne le "
                "transmettez pas.\n")
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        return True
    except Exception as exc:  # pragma: no cover — depends on SMTP
        import logging

        logging.getLogger("fluxaa.notifications").warning("Master access e-mail to %s failed: %s", email, exc)
        return False


def send_task_reminder(call, email: str, tasks: list[Task], *, lang: str = "fr") -> bool:
    """A reminder of pending tasks to the master, at the address his access was sent to (no link is resent: the
    one he holds stays valid)."""
    entry = f"{settings.SITE_URL}{reverse('registry:master_entry')}"
    if lang == "en":
        subject = f"[FLUXAA Port] Call {call.reference} — {call.vessel.name}: reminder"
        body = (f"The port of {call.port.name} is still expecting from the master of {call.vessel.name} (call {call.reference}):\n"
                + "\n".join(f"- {t.code} {t.title_en}" for t in tasks)
                + f"\n\nOpen the call with the access you received, or go to {entry} and enter your code.\n")
    else:
        subject = f"[FLUXAA Port] Escale {call.reference} — {call.vessel.name} : rappel"
        body = (f"Le port de {call.port.name} attend toujours du capitaine du {call.vessel.name} (escale {call.reference}) :\n"
                + "\n".join(f"- {t.code} {t.title_fr}" for t in tasks)
                + f"\n\nOuvrez l'escale avec l'accès reçu, ou rendez-vous sur {entry} et saisissez votre code.\n")
    try:
        send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        return True
    except Exception as exc:  # pragma: no cover
        import logging

        logging.getLogger("fluxaa.notifications").warning("Reminder e-mail to %s failed: %s", email, exc)
        return False
