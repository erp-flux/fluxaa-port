"""Task actions (EF-5): complete, sign jointly, countersign, mark not applicable, ad hoc tasks; since 1.5 the
green lights (given and withdrawn, EXG-R-03) and the documents asked for at the announcement (EXG-R-06)."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.roles import ANY_PARTY, role_label

from ..models import Anchor, CallStatus, Criticality, DocumentType, Nature, Task, TaskSignature, TaskStatus
from . import journal
from .errors import PermissionRefused, RuleViolation, ensure_open
from .notifications import notify
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
    if acting == "COM" and not task.green_light:
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
    done = _finish(task, actor, role=acting, evidence=f"manual:{acting}", note=note)
    if task.green_light:
        notify(call, ["AGE", "CAP", "NAV", "TER"], key=f"green:{task.pk}:given:{timezone.now():%Y%m%d%H%M}", realtime=True,
               exclude_user=actor.user, url=f"/escales/{call.pk}/?tab=apercu#feux-verts",
               title_fr=f"{call.reference} : feu vert donné par {role_label(acting)} — {task.title_fr}",
               title_en=f"{call.reference}: green light given by {acting} — {task.title_en}")
    return done


@transaction.atomic
def withdraw_green_light(task: Task, actor, reason: str, *, role: str | None = None) -> Task:
    """A green light given is withdrawn by the party that gave it (or by the harbour master), with a reason: the
    task is pending again, the hold points it guards close again, everyone concerned is told at once (EXG-R-03).
    The harbour master's own green light is a decision on a request: it is withdrawn by cancelling the
    authorization, not here."""
    call = task.call
    ensure_open(call)
    if not task.green_light:
        raise RuleViolation(_("Only a green light can be withdrawn."))
    if task.request_type_code:
        raise RuleViolation(_("This green light is a decision on a request: withdraw it by cancelling the authorization."))
    if task.status != TaskStatus.DONE:
        raise RuleViolation(_("This green light has not been given."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    acting = actor.pick_role({task.role, "CAP"}, role)
    task.status = TaskStatus.PENDING
    task.completion_note = f"{task.completion_note}\n" if task.completion_note else ""
    task.completion_note += _("withdrawn by %(role)s: %(reason)s") % {"role": role_label(acting), "reason": reason.strip()}
    task.completed_at = None
    task.completed_role = ""
    task.completed_by = None
    task.completed_by_master = None
    task.evidence = ""
    task.save(update_fields=["status", "completion_note", "completed_at", "completed_role", "completed_by",
                             "completed_by_master", "evidence"])
    journal.record(port=call.port, call=call, actor=actor, role=acting, action="task.green_light_withdrawn", obj=task,
                   visible_roles=task_roles_visible(task),
                   summary_fr=f"Feu vert retiré — {task.title_fr} — {reason}",
                   summary_en=f"Green light withdrawn — {task.title_en} — {reason}", payload={"reason": reason})
    notify(call, ["AGE", "CAP", "NAV", "TER", "APO"], key=f"green:{task.pk}:withdrawn:{timezone.now():%Y%m%d%H%M}", realtime=True,
           exclude_user=actor.user, url=f"/escales/{call.pk}/?tab=apercu#feux-verts",
           title_fr=f"{call.reference} : FEU VERT RETIRÉ par {role_label(acting)} — {task.title_fr} — {reason}",
           title_en=f"{call.reference}: GREEN LIGHT WITHDRAWN by {acting} — {task.title_en} — {reason}")
    return task


def green_lights(call) -> list[dict]:
    """The green-light panel of a call: every green light of its templates, with its state, who gave it and when."""
    rows = []
    for task in call.tasks.filter(green_light=True).order_by("order", "number"):
        state = "GIVEN" if task.status == TaskStatus.DONE else ("NA" if task.status == TaskStatus.NOT_APPLICABLE else "PENDING")
        decision = None
        if task.request_type_code:
            req = call.requests.filter(type__code=task.request_type_code).order_by("-submitted_at", "-pk").first()
            if req is not None and req.decision:
                decision = req
                if req.decision == "REFUSED":
                    state = "REFUSED"
        rows.append({"task": task, "state": state, "request": decision,
                     "by": task.completed_by_master.master_name if task.completed_by_master else (task.completed_by.get_full_name() or task.completed_by.email if task.completed_by else ""),
                     "at": task.completed_at, "withdrawable": state == "GIVEN" and not task.request_type_code})
    return rows


@transaction.atomic
def request_documents(call, actor, *, document_types: list[str], custom: list[dict]) -> list[Task]:
    """The documents the agency asks for at the announcement beyond the templates (EXG-R-06): types of the port's
    catalogue, and others named freely (an open list). Each becomes a "provide a document" task of the type's
    issuing role — never blocking: a blocking task comes from the templates."""
    acting = actor.pick_role({"AGE", "CAP"})
    created = []
    existing = {(t.document_type_code, t.title_fr.strip().lower()) for t in call.tasks.all()}
    types = {d.code: d for d in DocumentType.objects.filter(port=call.port, is_active=True)}
    order = call.tasks.count()
    for code in document_types:
        dtype = types.get(code)
        if dtype is None or any(t[0] == code for t in existing):
            continue  # unknown type, or already expected by a template task
        role = (dtype.issuer_roles or ["AGE"])[0]
        order += 1
        created.append(Task(
            call=call, template_code="", number=f"D{order:02d}", title_fr=f"Fournir : {dtype.label_fr}",
            title_en=f"Provide: {dtype.label_en}", role=role, co_roles=["AGE"] if role != "AGE" else [], nature=Nature.F,
            criticality=Criticality.NORMAL, anchor=Anchor.ETA, offset_minutes=-24 * 60, timing_fr="ETA − 24 h",
            timing_en="ETA − 24 h", document_type_code=code, requested_at_creation=True, created_by=actor.user, order=order,
        ))
        existing.add((code, ""))
    for row in custom:
        label = (row.get("label") or "").strip()
        if not label or ("OTHER", label.lower()) in existing:
            continue
        role = row.get("role") or "AGE"
        if role not in ("AGE", "NAV", "TER", "COM", "INS", "PRE", "SVC", "ADM", "SUR", "CAP", "APO"):
            raise RuleViolation(_("Unknown role for a document: %(role)s") % {"role": role})
        try:
            hours = int(row.get("hours_before_eta") or 24)
        except (TypeError, ValueError):
            hours = 24
        order += 1
        created.append(Task(
            call=call, template_code="", number=f"D{order:02d}", title_fr=f"Fournir : {label}", title_en=f"Provide: {label}",
            role=role, co_roles=["AGE"] if role != "AGE" else [], nature=Nature.F, criticality=Criticality.NORMAL,
            anchor=Anchor.ETA, offset_minutes=-hours * 60, timing_fr=f"ETA − {hours} h", timing_en=f"ETA − {hours} h",
            document_type_code="OTHER", requested_at_creation=True, created_by=actor.user, order=order,
        ))
        existing.add(("OTHER", label.lower()))
    if not created:
        return []
    tasks = Task.objects.bulk_create(created)
    from .calls import compute_due

    for task in tasks:
        task.due_at = compute_due(task, call)
    Task.objects.bulk_update(tasks, ["due_at"])
    journal.record(port=call.port, call=call, actor=actor, role=acting, action="documents.requested", obj=call,
                   summary_fr="Documents demandés à l'annonce : " + ", ".join(f"{t.title_fr[10:]} ({role_label(t.role)})" for t in tasks),
                   summary_en="Documents asked for at the announcement: " + ", ".join(f"{t.title_en[9:]} ({t.role})" for t in tasks),
                   payload={"tasks": [t.number for t in tasks]})
    if call.status != CallStatus.DRAFT:  # at the announcement the parties learn it with the declaration
        notify(call, sorted({t.role for t in tasks}), key=f"documents:{call.pk}:requested:{timezone.now():%Y%m%d%H%M}",
               exclude_user=actor.user, url=f"/escales/{call.pk}/?tab=documents",
               title_fr=f"{call.reference} : documents attendus — " + ", ".join(t.title_fr[10:] for t in tasks),
               title_en=f"{call.reference}: documents expected — " + ", ".join(t.title_en[9:] for t in tasks))
    return tasks


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
