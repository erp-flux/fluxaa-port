"""The ship/shore safety checklist completed on line by both sides (FLX-CDC-002 v1.4, EXG-Q-10).

The ship (master's link) and the terminal (the one that speaks for the shore side) each tick their items; the
joint items need both ticks; the written agreements of the pre-transfer conference are entered by either side and
read by both; the repetitive checks are ticked again at the agreed interval, after the signature too. Each tick is
an append-only answer. A side signs when all its items are answered (yes or not applicable); when both have signed
the checklist is closed, the joint task M0:28 is signed for both roles — which records the SSSCL_SIGNED milestone
(a hold point of the start of transfer) — and the printed form, pre-filled with the ticks, is filed in the call.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal

from .. import checklists
from ..models import SafetyCheckAnswer, SafetyChecklist, SafetyChecklistSignature, TaskStatus
from . import journal
from .calls import call_url
from .errors import PermissionRefused, RuleViolation, ensure_open
from .notifications import notify
from .rights import can_read_report, speaks_for_shore

SIDE_ROLE = {"SHIP": "NAV", "SHORE": "TER"}
CHECKLIST_TASK = ("M0", "28")


def _side_of(actor, call) -> tuple[str, str]:
    if "NAV" in actor.roles:
        return "SHIP", "NAV"
    if "TER" in actor.roles:
        if not speaks_for_shore(actor, "TER", call):
            raise PermissionRefused(_("The checklist is completed by the terminal that speaks for the shore side on this call."))
        return "SHORE", "TER"
    raise PermissionRefused(_("The ship/shore safety checklist is completed by the ship and the terminal."))


def visible(actor, call) -> bool:
    """The two sides always read it; the other parties as the port decided at parametrage."""
    if actor.is_system or "NAV" in actor.roles or "TER" in actor.roles:
        return True
    return can_read_report(actor, "SAFETY_CHECKLIST")


def can_complete(actor, call) -> bool:
    try:
        _side_of(actor, call)
    except PermissionRefused:
        return False
    return True


def current(call) -> SafetyChecklist | None:
    """The checklist in use: the open one, else the latest signed one."""
    return (call.safety_checklists.exclude(status=SafetyChecklist.Status.CANCELLED).order_by("-version").first())


def open_checklist(call, actor, *, repeat_interval_h=None) -> SafetyChecklist:
    """Either side opens the checklist of the call (one open at a time); a signed one is kept and a new version
    is opened for a new stage or a renewed conference."""
    ensure_open(call)
    side, role = _side_of(actor, call)
    if call.safety_checklists.filter(status=SafetyChecklist.Status.OPEN).exists():
        raise RuleViolation(_("A checklist is already being completed."))
    version = call.safety_checklists.count() + 1
    interval = Decimal(str(repeat_interval_h)) if repeat_interval_h not in (None, "") else None
    stage = call.stages.filter(status="CURRENT").first()
    standard = checklists.standard_for(call.cargo_kind)  # ISGOTT, BLU Code or the cargo operations list (v1.5)
    with transaction.atomic():
        checklist = SafetyChecklist.objects.create(
            call=call, stage=stage, version=version, standard=standard, items=checklists.catalogue(standard),
            repeat_interval_h=interval, opened_role=role, opened_by=actor.user, opened_master=actor.master,
            opened_label=actor.label,
        )
        journal.record(port=call.port, call=call, actor=actor, role=role, action="checklist.opened", obj=checklist,
                       visible_roles=_readers(call),
                       summary_fr=f"Liste de contrôle navire/terre v{version} ouverte par {'le navire' if side == 'SHIP' else 'le terminal'}",
                       summary_en=f"Ship/shore safety checklist v{version} opened by the {'ship' if side == 'SHIP' else 'terminal'}")
    other = "TER" if side == "SHIP" else "NAV"
    notify(call, [other, "AGE"], key=f"checklist:{checklist.pk}:opened", exclude_user=actor.user,
           title_fr=f"{call.reference} : liste de contrôle navire/terre ouverte — à compléter par {'le terminal' if other == 'TER' else 'le navire'}",
           title_en=f"{call.reference}: ship/shore safety checklist opened — to be completed by the {'terminal' if other == 'TER' else 'ship'}",
           url=checklist_url(call), realtime=True)
    return checklist


def get_or_open(call, actor) -> SafetyChecklist:
    checklist = call.safety_checklists.filter(status=SafetyChecklist.Status.OPEN).first()
    return checklist or open_checklist(call, actor)


def checklist_url(call) -> str:
    return call_url(call).rstrip("/") + "/liste-de-controle/"


def _readers(call) -> list[str]:
    from .rights import report_readers

    return sorted(report_readers(call.port, "SAFETY_CHECKLIST") | {"NAV", "TER"})


def _item(checklist: SafetyChecklist, code: str) -> dict:
    item = next((i for i in checklist.items if i["code"] == code), None)
    if item is None:
        raise RuleViolation(_("Unknown checklist item: %(code)s") % {"code": code})
    return item


def answer(checklist: SafetyChecklist, actor, *, item_code: str, state: str = "", value: str = "", remark: str = "",
           repetition: int = 0) -> SafetyCheckAnswer:
    """One tick, value or remark by one side. After the signature only the repetitive checks (part 6, "R" items)
    are answered again, as repetitions."""
    call = checklist.call
    ensure_open(call)
    side, role = _side_of(actor, call)
    item = _item(checklist, item_code)
    if side not in checklists.sides_of(item):
        raise PermissionRefused(_("This item is answered by the other side."))
    state = (state or "").upper()
    if item["kind"] == "value":
        state = ""
        if not value.strip():
            raise RuleViolation(_("Write the agreed value."))
    elif state and state not in SafetyCheckAnswer.State.values:
        raise RuleViolation(_("Unknown answer."))
    elif not state and not remark.strip():
        raise RuleViolation(_("Tick the item (yes, no, not applicable) or write a remark."))
    if checklist.status == SafetyChecklist.Status.SIGNED:
        if not item.get("repetitive"):
            raise RuleViolation(_("The checklist is signed: only the repetitive checks are answered again."))
        repetition = max(1, int(repetition or 0) or (_last_repetition(checklist, side) + 1))
    elif checklist.status != SafetyChecklist.Status.OPEN:
        raise RuleViolation(_("This checklist is cancelled."))
    if state == SafetyCheckAnswer.State.NO and not remark.strip():
        raise RuleViolation(_("A “no” states what is to be done (remark)."))
    now = timezone.now()
    with transaction.atomic():
        row = SafetyCheckAnswer(checklist=checklist, item_code=item_code, side=side, state=state, value=value.strip()[:300],
                                remark=remark.strip()[:300], repetition=repetition, role=role, user=actor.user,
                                master=actor.master, author_label=actor.label, answered_at=now)
        row.seal = seal({"checklist": checklist.pk, "item": item_code, "side": side, "state": state, "value": row.value,
                         "remark": row.remark, "repetition": repetition, "by": actor.label, "at": now.isoformat()})
        row.save()
        journal.record(port=call.port, call=call, actor=actor, role=role, action="checklist.answer", obj=checklist,
                       visible_roles=_readers(call),
                       summary_fr=f"Liste de contrôle {item_code} ({'navire' if side == 'SHIP' else 'terre'}) : "
                                  + (row.value if row.value else _state_fr(state))
                                  + (f" — {row.remark}" if row.remark else "") + (f" [répétition {repetition}]" if repetition else ""),
                       summary_en=f"Checklist {item_code} ({'ship' if side == 'SHIP' else 'shore'}): "
                                  + (row.value if row.value else _state_en(state))
                                  + (f" — {row.remark}" if row.remark else "") + (f" [repetition {repetition}]" if repetition else ""),
                       payload={"item": item_code, "side": side, "state": state, "repetition": repetition, "seal": row.seal})
    if state == SafetyCheckAnswer.State.NO:
        other = "TER" if side == "SHIP" else "NAV"
        notify(call, [other, "AGE", "CAP"], key=f"checklist:{checklist.pk}:{item_code}:{side}:no:{now:%Y%m%d%H%M}", realtime=True,
               title_fr=f"{call.reference} : liste de contrôle — point {item_code} répondu « non » par {'le navire' if side == 'SHIP' else 'le terminal'} : {row.remark}",
               title_en=f"{call.reference}: checklist — item {item_code} answered “no” by the {'ship' if side == 'SHIP' else 'terminal'}: {row.remark}",
               url=checklist_url(call))
    return row


def _state_fr(state: str) -> str:
    return {"YES": "oui — vérifié", "NO": "non", "NA": "sans objet", "": "remarque"}.get(state, state)


def _state_en(state: str) -> str:
    return {"YES": "yes — checked", "NO": "no", "NA": "not applicable", "": "remark"}.get(state, state)


def _last_repetition(checklist: SafetyChecklist, side: str) -> int:
    row = checklist.answers.filter(side=side).order_by("-repetition").first()
    return row.repetition if row else 0


def answer_many(checklist: SafetyChecklist, actor, rows: list[dict]) -> list[SafetyCheckAnswer]:
    """The whole form posted at once: only the items whose answer changed are recorded."""
    current_answers = checklist.current_answers()
    try:
        side, _role = _side_of(actor, checklist.call)
    except PermissionRefused:
        raise
    recorded = []
    for row in rows:
        code = row.get("item_code", "")
        item = next((i for i in checklist.items if i["code"] == code), None)
        if item is None or side not in checklists.sides_of(item):
            continue
        state = (row.get("state") or "").upper()
        value = (row.get("value") or "").strip()
        remark = (row.get("remark") or "").strip()
        repetition = int(row.get("repetition") or 0)
        previous = current_answers.get((code, side))
        if item["kind"] == "value":
            if not value or (previous is not None and previous.value == value and previous.remark == remark):
                continue
        else:
            if not state and not remark:
                continue
            if previous is not None and previous.state == state and previous.remark == remark and previous.repetition == repetition:
                continue
        recorded.append(answer(checklist, actor, item_code=code, state=state, value=value, remark=remark, repetition=repetition))
    return recorded


def progress(checklist: SafetyChecklist) -> dict:
    """Per side: items to answer, answered, answered “no”; the agreements written; what blocks the signature."""
    answers = checklist.current_answers()
    report = {}
    for side in ("SHIP", "SHORE"):
        items = [i for i in checklist.items if side in checklists.sides_of(i) and i["kind"] == "check"]
        answered = [i for i in items if (i["code"], side) in answers and answers[(i["code"], side)].state in ("YES", "NA")]
        noes = [i for i in items if (i["code"], side) in answers and answers[(i["code"], side)].state == "NO"]
        report[side] = {"total": len(items), "answered": len(answered), "no": [i["code"] for i in noes],
                        "missing": [i["code"] for i in items if (i["code"], side) not in answers or answers[(i["code"], side)].state not in ("YES", "NA")],
                        "signed": side in checklist.signed_sides()}
    agreements = [i for i in checklist.items if i["kind"] == "value"]
    written = [i["code"] for i in agreements if any((i["code"], s) in answers and answers[(i["code"], s)].value for s in ("SHIP", "SHORE"))]
    report["agreements"] = {"total": len(agreements), "written": len(written),
                            "missing": [i["code"] for i in agreements if i["code"] not in written]}
    report["due"] = repetition_due(checklist)
    return report


def repetition_due(checklist: SafetyChecklist):
    """When the next repetitive check is due: the agreed interval after the latest repetition (or the signature)."""
    if checklist.status != SafetyChecklist.Status.SIGNED or not checklist.repeat_interval_h:
        return None
    last = checklist.answers.filter(repetition__gte=1).order_by("-answered_at").first()
    base = last.answered_at if last else checklist.signed_at
    return base + timedelta(hours=float(checklist.repeat_interval_h)) if base else None


def sign(checklist: SafetyChecklist, actor, *, comment: str = "") -> SafetyChecklistSignature:
    """A side signs once every one of its items is answered yes or not applicable and the agreements are written;
    the second signature closes the checklist, signs task M0:28 for both roles and files the printed form."""
    call = checklist.call
    ensure_open(call)
    side, role = _side_of(actor, call)
    if checklist.status != SafetyChecklist.Status.OPEN:
        raise RuleViolation(_("This checklist is not open for signature."))
    if side in checklist.signed_sides():
        raise RuleViolation(_("Your side has already signed."))
    state = progress(checklist)
    if state[side]["no"]:
        raise RuleViolation(_("Items answered “no” must be resolved before signing: %(codes)s.")
                            % {"codes": ", ".join(state[side]["no"])})
    if state[side]["missing"]:
        raise RuleViolation(_("Items not yet checked: %(codes)s.") % {"codes": ", ".join(state[side]["missing"])})
    if state["agreements"]["missing"]:
        raise RuleViolation(_("Agreements not yet written (part 5A): %(codes)s.")
                            % {"codes": ", ".join(state["agreements"]["missing"])})
    now = timezone.now()
    with transaction.atomic():
        signature = SafetyChecklistSignature(checklist=checklist, side=side, role=role, user=actor.user, master=actor.master,
                                             signer_label=actor.label, signed_at=now, comment=comment.strip()[:300])
        signature.seal = seal({"checklist": checklist.pk, "side": side, "by": actor.label, "at": now.isoformat()})
        signature.save()
        journal.record(port=call.port, call=call, actor=actor, role=role, action="checklist.signed", obj=checklist,
                       visible_roles=_readers(call),
                       summary_fr=f"Liste de contrôle navire/terre signée pour {'le navire' if side == 'SHIP' else 'le terminal'} par {actor.label}",
                       summary_en=f"Ship/shore safety checklist signed for the {'ship' if side == 'SHIP' else 'terminal'} by {actor.label}",
                       payload={"side": side, "seal": signature.seal})
        _sign_task(call, actor, role)
        both = {"SHIP", "SHORE"} <= checklist.signed_sides()
        if both:
            checklist.status = SafetyChecklist.Status.SIGNED
            checklist.signed_at = now
            if checklist.repeat_interval_h is None:
                agreed = checklist.current_answers()
                for key in (("5A.8", "SHIP"), ("5A.8", "SHORE")):
                    text = agreed[key].value if key in agreed else ""
                    try:
                        checklist.repeat_interval_h = Decimal(text.replace(",", ".").split()[0]) if text else None
                        if checklist.repeat_interval_h is not None:
                            break
                    except (ArithmeticError, ValueError, IndexError):
                        checklist.repeat_interval_h = None
            checklist.save(update_fields=["status", "signed_at", "repeat_interval_h"])
            journal.record(port=call.port, call=call, actor=actor, role=role, action="checklist.completed", obj=checklist,
                           visible_roles=_readers(call),
                           summary_fr="Liste de contrôle navire/terre signée par les deux parties — vérifications répétées à suivre",
                           summary_en="Ship/shore safety checklist signed by both sides — repetitive checks to follow")
    if both:
        _file_form(checklist, actor, role)
        notify(call, ["NAV", "TER", "AGE", "CAP", "INS"], key=f"checklist:{checklist.pk}:signed", realtime=True,
               title_fr=f"{call.reference} : liste de contrôle navire/terre signée par le navire et le terminal",
               title_en=f"{call.reference}: ship/shore safety checklist signed by the ship and the terminal",
               url=checklist_url(call))
    else:
        other = "TER" if side == "SHIP" else "NAV"
        notify(call, [other, "AGE"], key=f"checklist:{checklist.pk}:signed:{side}", realtime=True,
               title_fr=f"{call.reference} : liste de contrôle signée par {'le navire' if side == 'SHIP' else 'le terminal'} — votre signature est attendue",
               title_en=f"{call.reference}: checklist signed by the {'ship' if side == 'SHIP' else 'terminal'} — your signature is expected",
               url=checklist_url(call))
    return signature


def _sign_task(call, actor, role: str) -> None:
    """The joint task "complete and jointly sign the ship/shore safety checklist" is signed for the side."""
    from .tasks import sign_task

    task = call.tasks.filter(template_code=CHECKLIST_TASK[0], number=CHECKLIST_TASK[1], status=TaskStatus.PENDING).first()
    if task is None or role not in task.all_roles:
        return
    if task.signatures.filter(role=role, kind="SIGNED").exists():
        return
    sign_task(task, actor, role=role, comment=_("signed on the on-line checklist"))


def _file_form(checklist: SafetyChecklist, actor, role: str) -> None:
    from .forms import auto_issue

    doc = auto_issue(checklist.call, actor, checklists.document_code(checklist.standard), as_role=role)
    if doc is not None:
        checklist.document = doc
        checklist.save(update_fields=["document"])


def cancel(checklist: SafetyChecklist, actor, reason: str) -> SafetyChecklist:
    """The harbour master or the agency cancels an open checklist (a new one is then opened)."""
    ensure_open(checklist.call)
    if not actor.has("CAP", "AGE"):
        raise PermissionRefused(_("The agency or the harbour master cancels a checklist."))
    if checklist.status != SafetyChecklist.Status.OPEN:
        raise RuleViolation(_("Only an open checklist can be cancelled."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    checklist.status = SafetyChecklist.Status.CANCELLED
    checklist.cancel_reason = reason.strip()[:300]
    checklist.save(update_fields=["status", "cancel_reason"])
    journal.record(port=checklist.call.port, call=checklist.call, actor=actor, action="checklist.cancelled", obj=checklist,
                   visible_roles=_readers(checklist.call),
                   summary_fr=f"Liste de contrôle v{checklist.version} annulée — {reason}",
                   summary_en=f"Checklist v{checklist.version} cancelled — {reason}")
    return checklist


def rows(checklist: SafetyChecklist, actor=None) -> list[dict]:
    """The items grouped by part, with the current answer of each side and what the actor may tick."""
    answers = checklist.current_answers()
    try:
        my_side = _side_of(actor, checklist.call)[0] if actor is not None else None
    except PermissionRefused:
        my_side = None
    parts = []
    for code, fr, en in checklists.parts(checklist.standard):
        items = []
        for item in checklist.items:
            if item["part"] != code:
                continue
            sides = checklists.sides_of(item)
            ship = answers.get((item["code"], "SHIP"))
            shore = answers.get((item["code"], "SHORE"))
            repetitions = list(checklist.answers.filter(item_code=item["code"], repetition__gte=1).order_by("answered_at")) if item.get("repetitive") else []
            items.append({"item": item, "sides": sides, "ship": ship, "shore": shore, "repetitions": repetitions,
                          "mine": my_side in sides, "my_answer": ship if my_side == "SHIP" else shore,
                          "value": (ship.value if ship is not None and ship.value else (shore.value if shore is not None else ""))})
        if items:
            parts.append({"code": code, "fr": fr, "en": en, "items": items,
                          "repeatable": any(i["item"].get("repetitive") and i["mine"] for i in items)})
    return parts
