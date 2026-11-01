"""Task actions (EF-5): complete, sign jointly, countersign, mark not applicable, ad hoc tasks."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.roles import ANY_PARTY, role_label

from ..models import Anchor, Criticality, Nature, Task, TaskSignature, TaskStatus
from . import journal
from .errors import PermissionRefused, RuleViolation, ensure_open
from .rights import task_visible


def task_roles_visible(task: Task) -> list[str]:
    roles = {"AGE", "CAP", *task.all_roles}
    roles.discard(ANY_PARTY)
    return sorted(roles) if task.role != ANY_PARTY else ["*"]


def _finish(task: Task, actor, *, role: str, evidence: str = "", note: str = "") -> Task:
    task.status = TaskStatus.DONE
    task.completed_at = timezone.now()
    task.completed_role = role
    task.completed_by = actor.user if not actor.is_system else None
    task.completed_by_master = actor.master
    task.evidence = evidence[:60]
    task.completion_note = note
    task.save(update_fields=["status", "completed_at", "completed_role", "completed_by", "completed_by_master",
                             "evidence", "completion_note"])
    journal.record(
        port=task.call.port, call=task.call, actor=actor, role=role, action="task.completed", obj=task,
        visible_roles=task_roles_visible(task),
        summary_fr=f"Tâche {task.code} faite — {task.title_fr}",
        summary_en=f"Task {task.code} done — {task.title_en}",
        payload={"evidence": evidence, "note": note},
    )
    _after_completion(task, actor)
    return task


def _after_completion(task: Task, actor) -> None:
    """Platform consequences of a completed task (milestones recorded automatically, e.g. M0:28 → SSSCL)."""
    from ..models import MilestoneType
    from .milestones import record_system_milestone

    for mtype in MilestoneType.objects.filter(port=task.call.port, auto_from_task=task.code, is_active=True):
        record_system_milestone(task.call, mtype, actor, note=_("task %(code)s") % {"code": task.code})


def system_complete(task: Task, actor, *, evidence: str = "", note: str = "", role: str = "",
                    allow_joint: bool = False) -> Task | None:
    """Completion as a consequence of another authorised act (milestone, decision, document)."""
    if task.status != TaskStatus.PENDING:
        return None
    if task.joint and not allow_joint:
        return None  # joint tasks need explicit signatures of every role
    acting_role = role or next((r for r in task.all_roles if r in actor.roles), "")
    if not acting_role:
        # done as a consequence of another party's act (e.g. a request submitted by the terminal): the record
        # names the role that acted, not the role the task was assigned to
        acting_role = task.role if actor.is_system or not actor.roles else sorted(actor.roles)[0]
    return _finish(task, actor, role=acting_role, evidence=evidence, note=note)


def complete_by_codes(call, codes: list[str], actor, *, evidence: str = "", note: str = "") -> list[Task]:
    done = []
    for code in codes or []:
        if ":" not in code:
            continue
        template_code, number = code.split(":", 1)
        for task in call.tasks.filter(template_code=template_code, number=number, status=TaskStatus.PENDING):
            if task.milestone_codes:
                recorded = set(call.milestones.filter(is_conflict=False).values_list("type__code", flat=True))
                if not set(task.milestone_codes) <= recorded:
                    continue
            result = system_complete(task, actor, evidence=evidence, note=note)
            if result is not None:
                done.append(result)
    return done


@transaction.atomic
def complete_task(task: Task, actor, *, note: str = "", role: str | None = None) -> Task:
    """Manual completion of a 'confirm' (C) or 'enter data' (R) task by its assigned role."""
    call = task.call
    if not task_visible(actor, task):
        raise PermissionRefused(_("This task is not assigned to your role."))
    if task.status != TaskStatus.PENDING:
        raise RuleViolation(_("This task is already closed."))
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    allowed = set(actor.roles) if task.role == ANY_PARTY else ({task.role} | (set(task.co_roles) if task.nature == Nature.C else set()))
    acting = actor.pick_role(allowed, role)
    if acting == "COM":
        raise PermissionRefused(_("Owners and charterers have no data-entry right: they provide the documents requested from them."))
    if task.joint:
        raise RuleViolation(_("This task requires the signature of each party: use “Sign”."))
    if task.request_type_code:
        raise RuleViolation(_("This task is completed through its request (%(code)s).") % {"code": task.request_type_code})
    if task.milestone_codes:
        raise RuleViolation(_("This task is completed by recording its milestones."))
    if task.nature == Nature.F or task.document_type_code:
        raise RuleViolation(_("This task is completed by providing the expected document."))
    if task.nature == Nature.D:
        if not actor.strong_auth:
            from .errors import StrongAuthRequired

            raise StrongAuthRequired()
    if task.continuous:
        _check_continuous(task)
    return _finish(task, actor, role=acting, evidence=f"manual:{acting}", note=note)


def _check_continuous(task: Task) -> None:
    call = task.call
    if call.t1 is None:
        raise RuleViolation(_("A continuous task is closed after the end of transfer (T1)."))
    if task.number.endswith(".12"):  # interruptions: every interruption must be closed with a cause
        starts = call.milestones.filter(type__code="INTERRUPTION_START", is_conflict=False)
        ended = set(call.milestones.filter(type__code="INTERRUPTION_END").values_list("related_id", flat=True))
        if any(m.pk not in ended for m in starts):
            raise RuleViolation(_("An interruption is still open: record its end first."))
    if task.number.endswith(".11") and not call.pumping_log.exists():
        raise RuleViolation(_("The pumping log is empty."))


@transaction.atomic
def sign_task(task: Task, actor, *, role: str | None = None, comment: str = "") -> Task:
    """Signature of a joint task (e.g. ship/shore safety checklist, pre-transfer meeting)."""
    ensure_open(task.call)
    if task.status != TaskStatus.PENDING:
        raise RuleViolation(_("This task is already closed."))
    acting = actor.pick_role(set(task.all_roles), role)
    if acting == "COM":
        raise PermissionRefused(_("Owners and charterers have no data-entry right."))
    if task.signatures.filter(role=acting, kind=TaskSignature.Kind.SIGNED).exists():
        raise RuleViolation(_("Your role has already signed this task."))
    now = timezone.now()
    material = {"task": task.pk, "code": task.code, "role": acting, "at": now.isoformat(), "by": actor.label}
    TaskSignature.objects.create(task=task, role=acting, kind=TaskSignature.Kind.SIGNED, user=actor.user,
                                 master=actor.master, signer_label=actor.label, signed_at=now, comment=comment,
                                 seal=seal(material))
    journal.record(
        port=task.call.port, call=task.call, actor=actor, role=acting, action="task.signed", obj=task,
        visible_roles=task_roles_visible(task),
        summary_fr=f"{role_label(acting)} signe la tâche {task.code}", summary_en=f"{acting} signs task {task.code}",
    )
    signed = set(task.signatures.filter(kind=TaskSignature.Kind.SIGNED).values_list("role", flat=True))
    required = set(task.all_roles) if task.joint else {task.role}
    if required <= signed:
        _finish(task, actor, role=acting, evidence=f"signatures:{','.join(sorted(signed))}", note=comment)
    return task


@transaction.atomic
def countersign_task(task: Task, actor, *, contest: bool = False, comment: str = "", role: str | None = None) -> TaskSignature:
    """Countersignature (or contest) by a co-role of a completed, non-joint task."""
    ensure_open(task.call)
    if task.joint:
        raise RuleViolation(_("Joint tasks are signed, not countersigned."))
    if task.status != TaskStatus.DONE:
        raise RuleViolation(_("Only a completed task can be countersigned."))
    acting = actor.pick_role(set(task.co_roles) - {task.completed_role}, role)
    kind = TaskSignature.Kind.CONTESTED if contest else TaskSignature.Kind.COUNTERSIGNED
    if task.signatures.filter(role=acting, kind__in=[TaskSignature.Kind.COUNTERSIGNED, TaskSignature.Kind.CONTESTED]).exists():
        raise RuleViolation(_("Your role has already answered."))
    now = timezone.now()
    sig = TaskSignature.objects.create(
        task=task, role=acting, kind=kind, user=actor.user, master=actor.master, signer_label=actor.label,
        signed_at=now, comment=comment,
        seal=seal({"task": task.pk, "role": acting, "kind": kind, "at": now.isoformat(), "by": actor.label}),
    )
    journal.record(
        port=task.call.port, call=task.call, actor=actor, role=acting, action="task.countersigned", obj=task,
        visible_roles=task_roles_visible(task),
        summary_fr=f"Tâche {task.code} {'contestée' if contest else 'contresignée'} par {role_label(acting)}",
        summary_en=f"Task {task.code} {'contested' if contest else 'countersigned'} by {acting}",
    )
    if contest:
        from .disputes import open_dispute

        open_dispute(task.call, actor, target_kind="TASK", target_id=task.pk, as_role=acting,
                     subject=f"{task.code} — {task.title}", statement=comment or "—",
                     counterpart_role=task.completed_role)
    return sig


def na_roles(task: Task) -> set[str]:
    """Roles that may declare a task not applicable.

    For a decision, a request, or a task that a hold point waits for: only the role the task is assigned to — not a
    co-role, never a requester waving aside the decision it awaits — and, for a joint task (a safety checklist signed
    by both sides), not one signatory alone: only the harbour master, with its second factor. For the other tasks,
    its co-roles, the agency and the harbour master may also do it (coordination of the call)."""
    from . import holdpoints

    if not task.not_applicable_allowed:
        return set()
    if task.role == ANY_PARTY:
        return {"AGE", "CAP"}
    guarded = task.nature == Nature.D or bool(task.request_type_code) or holdpoints.is_requirement(task)
    if guarded and task.joint:
        return {"CAP"}
    if guarded:
        return {task.role}
    return {task.role, *task.co_roles, "AGE", "CAP"}


@transaction.atomic
def mark_not_applicable(task: Task, actor, reason: str, *, role: str | None = None) -> Task:
    """“Not applicable” with a mandatory, traced reason (EF-5.6). Who may say so: see na_roles."""
    ensure_open(task.call)
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    if task.status != TaskStatus.PENDING:
        raise RuleViolation(_("This task is already closed."))
    if not task.not_applicable_allowed:
        raise RuleViolation(_("This task cannot be marked not applicable."))
    acting = actor.pick_role(na_roles(task), role)
    if (task.nature == Nature.D or (task.joint and acting == "CAP")) and not actor.strong_auth:
        from .errors import StrongAuthRequired

        raise StrongAuthRequired()
    task.status = TaskStatus.NOT_APPLICABLE
    task.na_reason = reason
    task.completed_at = timezone.now()
    task.completed_role = acting
    task.completed_by = actor.user
    task.completed_by_master = actor.master
    task.save(update_fields=["status", "na_reason", "completed_at", "completed_role", "completed_by", "completed_by_master"])
    journal.record(
        port=task.call.port, call=task.call, actor=actor, role=acting, action="task.not_applicable", obj=task,
        visible_roles=task_roles_visible(task),
        summary_fr=f"Tâche {task.code} sans objet — {reason}", summary_en=f"Task {task.code} not applicable — {reason}",
    )
    return task


@transaction.atomic
def create_ad_hoc_task(call, actor, *, title_fr: str, title_en: str, role: str, nature: str = "C",
                       anchor: str = "", offset_minutes: int = 0) -> Task:
    """Ad hoc task, explicitly marked, never blocking (a blocking task needs a template basis)."""
    ensure_open(call)
    acting = actor.pick_role({"AGE", "CAP"})
    if anchor and anchor not in Anchor.values:
        raise RuleViolation(_("Unknown anchor."))
    task = Task.objects.create(
        call=call, template_code="", number=f"X{call.tasks.filter(is_ad_hoc=True).count() + 1:02d}",
        title_fr=title_fr, title_en=title_en or title_fr, role=role, nature=nature,
        criticality=Criticality.NORMAL, anchor=anchor, offset_minutes=offset_minutes, is_ad_hoc=True,
        created_by=actor.user, order=10_000 + call.tasks.count(),
    )
    from .calls import compute_due

    task.due_at = compute_due(task, call)
    task.save(update_fields=["due_at"])
    journal.record(port=call.port, call=call, actor=actor, role=acting, action="task.ad_hoc", obj=task,
                   visible_roles=task_roles_visible(task),
                   summary_fr=f"Tâche ad hoc {task.number} créée pour {role_label(role)} : {title_fr}",
                   summary_en=f"Ad hoc task {task.number} created for {role}: {task.title_en}")
    return task
