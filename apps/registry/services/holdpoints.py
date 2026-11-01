"""Hold points: the platform does not only record, it *prevents* (EF-11, FLX-SPEC-001 §8).

Configurable part: HoldPoint/HoldPointRequirement rows derived from the blocking tasks of the
templates (modifiable by the port's functional administrator, never bypassable by a user).
Non-configurable invariants, coded here because no role may lift them:
  * bill of lading — impossible without the principal's written documentary instructions (task 2.16)
    and an agreed quantity (EF-7.4, S8);
  * berth assignment and green light — impossible without a valid, unexpired vessel acceptance
    (EF-2.6, PRO-MAR-001 §3.2.2.1, S7);
  * call closure — impossible while a dispute is not closed or a measurement is incomplete (EF-4.3, EF-8);
  * a decision task opens a hold point only while the authorization it produced is in force.
"""
from __future__ import annotations

from datetime import timezone as dt_timezone

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import override

from apps.core.roles import role_label

from ..models import (
    Alert,
    AlertKind,
    Authorization,
    DisputeStatus,
    HoldPoint,
    HoldPointRequirement,
    Nature,
    TaskStatus,
    Transition,
)
from . import journal
from .errors import HoldPointRefused, LockRefused

BL_INSTRUCTION_TASK = ("M2", "2.16")
BL_QUANTITY_TASK = ("M2", "2.15")


def is_requirement(task) -> bool:
    """A hold point of the port waits for this task (it cannot be waved aside by a third party)."""
    return bool(task.template_code) and HoldPointRequirement.objects.filter(
        hold_point__port_id=task.call.port_id, template_code=task.template_code, task_number=task.number).exists()


def _missing_entry(task) -> dict:
    return {
        "task": task.code,
        "title_fr": task.title_fr,
        "title_en": task.title_en,
        "role": task.role,
        "co_roles": task.co_roles,
        "nature": task.nature,
        "expected_action": str(Nature(task.nature).label),
        "due_at": task.due_at.isoformat() if task.due_at else None,
    }


def _message(transition: str, missing: list[dict], reasons: list[str], lang: str) -> str:
    with override(lang):
        head = _("Refused: “%(transition)s” is not possible yet.") % {"transition": str(Transition(transition).label)}
        lines = [head]
        for item in missing:
            title = item["title_en"] if lang == "en" else item["title_fr"]
            roles = ", ".join(role_label(r) for r in [item["role"], *item.get("co_roles", [])] if r)
            lines.append(
                _("Missing task %(code)s “%(title)s” — responsible: %(roles)s — expected action: %(action)s.")
                % {"code": item["task"], "title": title, "roles": roles, "action": str(Nature(item["nature"]).label)}
            )
        lines.extend(reasons)
        return "\n".join(lines)


UNRESOLVED_DISPUTES = (DisputeStatus.OPEN, DisputeStatus.ANSWERED)  # an answer settles nothing


def _authorization_lapsed(call, task, at) -> bool:
    """A decision task is satisfied by the authorization it produced, not by its flag: an authorization that has
    expired, is not yet in force at *at* or was cancelled no longer opens the hold point (EF-2.4)."""
    if task.status != TaskStatus.DONE or task.request_side != "decide" or not task.request_type_code:
        return False
    if task.request_type_code == "VESSEL_ACCEPTANCE":
        return False  # checked below as a non-configurable invariant, with its own message
    from ..models import RequestType

    rtype = RequestType.objects.filter(port=call.port, code=task.request_type_code).first()
    if rtype is None or not rtype.decision_roles:
        return False  # a service order without decision issues no authorization
    return not any(a.is_valid(at) for a in Authorization.objects.filter(call=call, type_code=task.request_type_code))


def evaluate(call, transition: str, at=None, *, stage=None) -> tuple[list, list[dict], list[str]]:
    """Return (missing_tasks, missing_entries, invariant_reasons_fr_en) without side effects. *at* is the time of
    the act being checked (a milestone entered afterwards is judged at its declared time). *stage* is the stage
    of the call the act belongs to (the current one by default; the next one for a shift): the tasks tied to
    another stage do not guard it."""
    at = (at or timezone.now()).astimezone(dt_timezone.utc)
    missing_tasks = []
    reasons: list[tuple[str, str]] = []
    hold_point = HoldPoint.objects.filter(port=call.port, transition=transition).prefetch_related("requirements").first()
    if hold_point:
        required = {(r.template_code, r.task_number) for r in hold_point.requirements.all()}
        stage_id = stage.pk if stage is not None else call.stages.filter(status="CURRENT").values_list("pk", flat=True).first()
        for task in call.tasks.filter(template_code__in={code for code, _n in required}):
            if (task.template_code, task.number) not in required:
                continue
            if task.stage_id is not None and task.stage_id != stage_id:
                continue  # the tasks of another stage of the call do not guard this one
            if task.status == TaskStatus.PENDING:
                missing_tasks.append(task)
            elif _authorization_lapsed(call, task, at):
                reasons.append((
                    f"L'autorisation issue de la tâche {task.code} « {task.title_fr} » n'est pas en vigueur à "
                    f"{at:%d/%m/%Y %H:%M} UTC (expirée, pas encore valable ou annulée) : une nouvelle demande doit être "
                    f"décidée par {role_label(task.role)}.",
                    f"The authorization from task {task.code} “{task.title_en}” is not in force at "
                    f"{at:%Y-%m-%d %H:%M} UTC (expired, not yet valid or cancelled): a new request must be decided "
                    f"by {task.role}.",
                ))

    if transition == Transition.BL_ISSUE:
        instruction = call.tasks.filter(template_code=BL_INSTRUCTION_TASK[0], number=BL_INSTRUCTION_TASK[1]).first()
        if instruction is None or instruction.status != TaskStatus.DONE:
            if instruction is not None and instruction not in missing_tasks:
                missing_tasks.append(instruction)
            if instruction is None:
                reasons.append((
                    "Le verrou du connaissement exige l'instruction documentaire écrite du mandant (tâche 2.16).",
                    "The bill of lading lock requires the principal's written documentary instructions (task 2.16).",
                ))
        quantity = call.tasks.filter(template_code=BL_QUANTITY_TASK[0], number=BL_QUANTITY_TASK[1]).first()
        if quantity is None or quantity.status != TaskStatus.DONE:
            reasons.append((
                "Aucun accord sur la quantité n'est enregistré (certificat de quantité, tâche 2.15).",
                "No agreement on the quantity is recorded (certificate of quantity, task 2.15).",
            ))
        from ..models import Measurement

        if call.disputes.filter(status__in=UNRESOLVED_DISPUTES, target_kind="MEASUREMENT").exists() or any(
            m.exceeds_tolerance() for m in Measurement.objects.filter(call=call, kind=Measurement.Kind.FINAL)
        ):
            reasons.append((
                "Les quantités font l'objet d'une contestation non close ou d'un écart hors tolérance.",
                "The quantities are under a dispute that is not closed, or outside tolerance.",
            ))

    # PRO-MAR-001 §3.2.2.1 (4): the acceptance conditions both the berth assignment and the green light
    if transition in (Transition.BERTH_ASSIGN, Transition.GREEN_LIGHT) and call.tasks.filter(
        request_type_code="VESSEL_ACCEPTANCE"
    ).exists():
        valid = [
            a for a in Authorization.objects.filter(call=call, type_code="VESSEL_ACCEPTANCE")
            if a.is_valid(at)
        ]
        if not valid:
            reasons.append((
                "Aucune acceptation de navire (vetting) valide : le port n'attribue pas de poste à un navire non accepté ou dont l'acceptation est expirée.",
                "No valid vessel acceptance (vetting): the port does not assign a berth to a vessel that is not accepted or whose acceptance has expired.",
            ))

    if transition == Transition.CLOSE:
        open_disputes = call.disputes.filter(status__in=UNRESOLVED_DISPUTES).count()
        if open_disputes:
            reasons.append((
                f"{open_disputes} contestation(s) non close(s) : la clôture est refusée tant que les parties ne les "
                f"ont pas closes, avec ou sans accord.",
                f"{open_disputes} dispute(s) not closed: closure is refused until the parties close them, with or "
                f"without agreement.",
            ))
        incomplete = [m for m in call.measurements.all() if not m.is_complete]
        if incomplete:
            reasons.append((
                f"{len(incomplete)} mesure(s) incomplète(s) : la valeur bord ou la valeur terre manque.",
                f"{len(incomplete)} incomplete measurement(s): the ship or the shore value is missing.",
            ))

    entries = [_missing_entry(t) for t in missing_tasks]
    return missing_tasks, entries, reasons


def check(call, transition: str, at=None, *, stage=None) -> None:
    """Raise HoldPointRefused (or LockRefused for the bill of lading) when the transition is not allowed."""
    _tasks, entries, reasons = evaluate(call, transition, at, stage=stage)
    if not entries and not reasons:
        return
    reasons_fr = [fr for fr, _en in reasons]
    reasons_en = [en for _fr, en in reasons]
    from django.utils.translation import get_language

    lang = "en" if (get_language() or "fr").startswith("en") else "fr"
    message = _message(transition, entries, reasons_en if lang == "en" else reasons_fr, lang)
    exc_class = LockRefused if transition == Transition.BL_ISSUE else HoldPointRefused
    exc = exc_class(transition, entries, reasons_en if lang == "en" else reasons_fr, message=message)
    exc.reasons_fr = reasons_fr
    exc.reasons_en = reasons_en
    raise exc


def record_refusal(call, actor, exc: HoldPointRefused, attempted: str) -> None:
    """Every refusal is written to the call journal, readable by the harbour master (EF-11.3)."""
    summary_fr = _message(exc.transition, exc.missing, getattr(exc, "reasons_fr", exc.reasons), "fr")
    summary_en = _message(exc.transition, exc.missing, getattr(exc, "reasons_en", exc.reasons), "en")
    roles = sorted({"CAP", "AGE", *(actor.roles if actor and not actor.is_system else [])})
    journal.record(
        port=call.port, call=call, actor=actor, action="holdpoint.refused", object_kind="call", visible_roles=roles,
        summary_fr=summary_fr.replace("\n", " · "), summary_en=summary_en.replace("\n", " · "),
        payload={"transition": exc.transition, "attempted": attempted, "missing": exc.missing,
                 "reasons_fr": getattr(exc, "reasons_fr", []), "reasons_en": getattr(exc, "reasons_en", [])},
    )
    Alert.objects.create(
        call=call, kind=AlertKind.HOLD_POINT, blocking=True, recipient_roles=roles,
        message_fr=summary_fr.split("\n")[0][:500], message_en=summary_en.split("\n")[0][:500],
    )
