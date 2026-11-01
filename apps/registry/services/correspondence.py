"""Correspondence (EF-9): no free messaging — a thread always belongs to a call, ideally to an object."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.roles import ALL_ROLES

from ..models import Confidentiality, Message, Thread
from . import journal
from .calls import call_url
from .errors import PermissionRefused, RuleViolation, ensure_open
from .notifications import notify
from .rights import is_thread_creator, roles_with, thread_visible

WRITERS = roles_with("C", "correspondence")


@transaction.atomic
def create_thread(call, actor, *, subject: str, participant_roles: list[str], body: str,
                  confidentiality: str = Confidentiality.N2, related_kind: str = "", related_id=None,
                  as_role: str | None = None) -> Thread:
    if call is None:
        raise RuleViolation(_("A thread always belongs to a call."))
    ensure_open(call)
    role = actor.pick_role(WRITERS, as_role)
    participants = sorted({r for r in participant_roles if r in ALL_ROLES} | {role})
    if confidentiality == Confidentiality.N4:
        raise RuleViolation(_("Security matters go to the security space."))
    if confidentiality == Confidentiality.N3 and len(participants) != 2:
        raise RuleViolation(_("A bilateral thread involves exactly two parties."))
    if len(participants) < 2 and confidentiality != Confidentiality.N1:
        raise RuleViolation(_("Choose at least one other party."))
    if not subject.strip() or not body.strip():
        raise RuleViolation(_("Subject and message are required."))
    now = timezone.now()
    thread = Thread.objects.create(call=call, subject=subject[:250], confidentiality=confidentiality,
                                   participant_roles=participants, related_kind=related_kind, related_id=related_id,
                                   created_role=role, created_org=actor.org, created_by=actor.user,
                                   created_master=actor.master, last_message_at=now)
    Message.objects.create(thread=thread, role=role, user=actor.user, master=actor.master, author_label=actor.label,
                           body=body, sent_at=now)
    journal.record(port=call.port, call=call, actor=actor, role=role, action="thread.created", obj=thread,
                   visible_roles=["*"] if confidentiality == Confidentiality.N1 else participants,
                   summary_fr=f"Échange ouvert : {thread.subject}", summary_en=f"Thread opened: {thread.subject}")
    _notify(thread, role, key=f"thread:{thread.pk}:0", title_fr=f"{call.reference} : {thread.subject}",
            title_en=f"{call.reference}: {thread.subject}")
    return thread


def _notify(thread: Thread, author_role: str, **message) -> None:
    """The invited parties, and the creating side within its own organisation only."""
    invited = set(thread.participant_roles) - {thread.created_role, author_role}
    url = call_url(thread.call) + f"#fil-{thread.pk}"
    if invited:
        notify(thread.call, invited, url=url, **message)
    if author_role != thread.created_role:
        notify(thread.call, [thread.created_role], url=url, **message,
               organizations=[thread.created_org_id] if thread.created_org_id else None)


@transaction.atomic
def post_message(thread: Thread, actor, body: str, *, document=None, as_role: str | None = None) -> Message:
    if not thread_visible(actor, thread):
        raise PermissionRefused(_("You are not a participant of this thread."))
    ensure_open(thread.call)
    invited = set(thread.participant_roles) - {thread.created_role}
    allowed = (invited | ({thread.created_role} if is_thread_creator(actor, thread) else set())) & WRITERS
    if thread.confidentiality == Confidentiality.N1:
        allowed = WRITERS
    role = actor.pick_role(allowed, as_role)
    if not body.strip():
        raise RuleViolation(_("The message is empty."))
    if document is not None and document.call_id != thread.call_id:
        raise RuleViolation(_("The attachment belongs to another call."))
    now = timezone.now()
    msg = Message.objects.create(thread=thread, role=role, user=actor.user, master=actor.master, author_label=actor.label,
                                 body=body, document=document, sent_at=now)
    thread.last_message_at = now
    thread.save(update_fields=["last_message_at"])
    _notify(thread, role, key=f"thread:{thread.pk}:{msg.pk}",
            title_fr=f"{thread.call.reference} : nouveau message — {thread.subject}",
            title_en=f"{thread.call.reference}: new message — {thread.subject}")
    return msg
