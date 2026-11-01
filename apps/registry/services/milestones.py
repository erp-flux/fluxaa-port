"""Milestones (EF-3): single emitter, double timestamp, countersignature with qualified silence,
hold points, offline conflicts turned into disputes (EF-14.4), AIS corroboration (EF-3.6)."""
from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.roles import role_label

from ..models import (
    Alert,
    AlertKind,
    CountersignState,
    EntrySource,
    InterruptionCause,
    Milestone,
    MilestoneSignature,
    MilestoneType,
    PortCall,
    TaskStatus,
)
from . import holdpoints, journal
from .calls import advance_from_milestone, call_url, recompute_deadlines, with_refusal_log
from .errors import NotVisible, PermissionRefused, RuleViolation, ensure_open
from .notifications import notify
from .rights import SHORE_ROLES, shore_org_id, speaks_for_shore
from .tasks import complete_by_codes, system_complete

ORIGIN_ROLES = ("TER", "NAV", "PRE", "SVC", "CAP", "INS", "AGE")
FUTURE_TOLERANCE = timedelta(minutes=5)


def _material(m: Milestone) -> dict:
    return {
        "call": m.call_id, "type": m.type.code, "declared_at": m.declared_at.isoformat(),
        "recorded_at": m.recorded_at.isoformat(),
        "device_recorded_at": m.device_recorded_at.isoformat() if m.device_recorded_at else None,
        "emitter_role": m.emitter_role, "emitter": m.emitter_label, "cause": m.cause_id, "cause_reason": m.cause_reason,
        "related": m.related_id, "rectification": m.is_rectification, "source": m.source, "deferred": m.deferred,
        "note": m.note,
    }


def _counterpart(role: str, call=None) -> list[str]:
    """The party suffering the interruption countersigns (FLX-SPEC-001 §7, event 18)."""
    shore = "PRE" if call is not None and call.requested_berth_kind in ("ANCHORAGE", "STS_AREA") else "TER"
    if role in ("TER", "PRE"):
        return ["NAV"]
    if role == "NAV":
        return [shore]
    return [shore, "NAV"]


def is_deferred(source: str, device_recorded_at, recorded_at, declared_at=None) -> bool:
    """A deferred entry ("saisie différée", shown on every document): synchronised after the threshold, or — online
    too — declared for a time well before it was recorded (FLUXAA_LATE_ENTRY_SECONDS)."""
    if declared_at is not None and (recorded_at - declared_at).total_seconds() > settings.FLUXAA_LATE_ENTRY_SECONDS:
        return True
    if source in (EntrySource.OFFLINE, EntrySource.PAPER):
        if device_recorded_at is None:
            return True
        return (recorded_at - device_recorded_at).total_seconds() > settings.FLUXAA_DEFERRED_THRESHOLD_SECONDS
    return False


def get_type(call: PortCall, code: str) -> MilestoneType:
    mtype = MilestoneType.objects.filter(port=call.port, code=code, is_active=True).first()
    if mtype is None:
        raise RuleViolation(_("Unknown milestone type: %(code)s") % {"code": code})
    return mtype


def record_milestone(call: PortCall, actor, type_code: str, declared_at, *, cause_code: str = "",
                     cause_reason: str = "", note: str = "", related: Milestone | None = None,
                     source: str = EntrySource.ONLINE, device_recorded_at=None, client_uuid=None,
                     payload: dict | None = None, as_role: str | None = None, rectifies: Milestone | None = None,
                     rectification_reason: str = "") -> Milestone:
    if client_uuid:
        existing = Milestone.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            if existing.call_id != call.id:
                raise NotVisible()
            return existing  # idempotent synchronisation
    mtype = get_type(call, type_code)
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    if mtype.emitter_role == MilestoneType.SYSTEM:
        raise PermissionRefused(_("This milestone is recorded by the platform."))
    if mtype.emitter_role == MilestoneType.ORIGIN:
        role = actor.pick_role(ORIGIN_ROLES, as_role)
    else:
        if mtype.emitter_role not in actor.roles:
            raise PermissionRefused(
                _("“%(m)s” is recorded by %(role)s only (single emitter).")
                % {"m": mtype.label, "role": role_label(mtype.emitter_role)}
            )
        role = mtype.emitter_role
    # the shore side (terminal at a berth, operator at sea) is one organisation even when several hold the role
    shore_entry = role == "TER" or (role == "PRE" and (mtype.code.startswith("STS_") or mtype.emitter_role == MilestoneType.ORIGIN))
    if shore_entry and not speaks_for_shore(actor, role, call):
        raise PermissionRefused(_("Another organisation speaks for the shore side on this call: the agency or the "
                                  "harbour master designates it in the parties of the call."))
    now = timezone.now()
    if declared_at > now + FUTURE_TOLERANCE:
        raise RuleViolation(_("A milestone cannot be declared in the future."))
    cause = None
    if mtype.requires_cause:
        cause = InterruptionCause.objects.filter(port=call.port, code=cause_code, is_active=True).first()
        if cause is None:
            raise RuleViolation(_("An interruption requires a cause from the closed list."))
        if cause.requires_reason and not cause_reason.strip():
            raise RuleViolation(_("The cause “%(c)s” requires a reason.") % {"c": cause.label})
    if mtype.closes_type:
        if related is None or related.call_id != call.id or related.type.code != mtype.closes_type:
            raise RuleViolation(_("Indicate the interruption that ends."))
        if Milestone.objects.filter(related=related, type=mtype).exists():
            raise RuleViolation(_("This interruption is already closed."))
        if declared_at < related.declared_at:
            raise RuleViolation(_("The end cannot precede the start."))
        # single emitter: the end is recorded by the party that recorded the start (the other side countersigns)
        if not _same_emitter(actor, related):
            raise PermissionRefused(_("The end of an interruption is recorded by the party that recorded its start."))
        cause = related.cause
        role = related.emitter_role
    if rectifies is not None:
        if rectifies.call_id != call.id or rectifies.type_id != mtype.id:
            raise RuleViolation(_("A rectification concerns a milestone of the same type."))
        if rectifies.emitter_role != role or not _same_emitter(actor, rectifies):
            raise PermissionRefused(_("Only the emitter of a milestone can rectify it."))
        if not rectification_reason.strip():
            raise RuleViolation(_("A rectification requires a reason."))

    from . import stages as stage_svc

    guard_stage = None
    if mtype.code == "SHIFT_START":
        guard_stage = stage_svc.check_shift_possible(call)  # a shift goes somewhere: the next stage is planned first,
        # and its own movement authorization guards the departure
    stage = stage_svc.current(call)

    def _do() -> Milestone:
        lapsed = False
        if mtype.hold_point:
            # judged at the time of the fact — a rectification too, at its corrected time
            holdpoints.check(call, mtype.hold_point, at=declared_at, stage=guard_stage)
            # in order then, no longer now: the entry is shown as deferred and the harbour master is told
            _t, missing_now, reasons_now = holdpoints.evaluate(call, mtype.hold_point, at=now, stage=guard_stage)
            lapsed = bool(missing_now or reasons_now)
        conflict_with = None
        if not mtype.repeatable and rectifies is None and not mtype.closes_type:
            # one entry per milestone and per stage: a call that berths twice records two "all fast"
            conflict_with = call.milestones.filter(_stage_filter(stage), type=mtype, is_conflict=False,
                                                   is_rectification=False).first()
        countersigners = _counterpart(role, call) if mtype.emitter_role == MilestoneType.ORIGIN else [
            r for r in mtype.countersigner_roles if r != role
        ]
        milestone = Milestone(
            call=call, type=mtype, stage=stage, declared_at=declared_at, recorded_at=now, device_recorded_at=device_recorded_at,
            deferred=lapsed or is_deferred(source, device_recorded_at, now, declared_at), source=source,
            emitter_role=role,
            emitter_org=actor.org, emitter_user=actor.user if not actor.is_system else None,
            emitter_master=actor.master, emitter_label=actor.label, countersigner_roles=countersigners,
            cause=cause, cause_reason=cause_reason, related=rectifies or related,
            is_rectification=rectifies is not None, rectification_reason=rectification_reason,
            is_conflict=conflict_with is not None, note=note, payload=payload or {}, client_uuid=client_uuid,
        )
        milestone.seal = seal(_material(milestone))
        milestone.save()
        _journal_milestone(call, actor, role, milestone, conflict_with)
        if lapsed:
            Alert.objects.create(
                call=call, kind=AlertKind.HOLD_POINT, milestone=milestone, recipient_roles=["CAP", "AGE"],
                message_fr=f"« {mtype.label_fr} » déclaré à {declared_at:%d/%m %H:%M} UTC, quand l'autorisation était en "
                           f"vigueur, mais enregistré à {now:%d/%m %H:%M} UTC, après son expiration — à vérifier",
                message_en=f"“{mtype.label_en}” declared at {declared_at:%d/%m %H:%M} UTC, while the authorization was in "
                           f"force, but recorded at {now:%d/%m %H:%M} UTC, after it lapsed — to be checked",
            )
        if conflict_with is not None:
            _conflict(call, actor, role, milestone, conflict_with)
            return milestone
        _apply_effects(call, actor, milestone)
        return milestone

    milestone = with_refusal_log(call, actor, f"milestone:{type_code}", _do)
    if not milestone.is_conflict:
        _notify_milestone(call, actor, milestone)
    return milestone


def _stage_filter(stage):
    """Milestones of *stage*; those recorded before stages existed (empty stage) belong to the first one."""
    if stage is None or stage.order == 1:
        return Q(stage=stage) | Q(stage__isnull=True)
    return Q(stage=stage)


def _same_emitter(actor, milestone: Milestone) -> bool:
    """The actor speaks for the party that recorded *milestone* (same organisation, or the ship's master)."""
    from .rights import acts_for

    return acts_for(actor, milestone.emitter_role, milestone.emitter_org_id,
                    by_master=milestone.emitter_master_id is not None)


def _journal_milestone(call, actor, role, milestone: Milestone, conflict_with) -> None:
    mtype = milestone.type
    flags = []
    if milestone.deferred:
        flags.append(("saisie différée", "deferred entry"))
    if milestone.is_rectification:
        flags.append((f"rectification : {milestone.rectification_reason}", f"rectification: {milestone.rectification_reason}"))
    if conflict_with is not None:
        flags.append(("saisie concurrente", "competing entry"))
    cause_fr = f" — cause : {milestone.cause.label_fr}" if milestone.cause else ""
    cause_en = f" — cause: {milestone.cause.label_en}" if milestone.cause else ""
    visible = ["*", "PRE"] if role == "PRE" else ["*"]
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="milestone.recorded", obj=milestone,
        visible_roles=visible,
        summary_fr=f"{mtype.label_fr} — {milestone.declared_at:%d/%m/%Y %H:%M} UTC{cause_fr}"
        + "".join(f" [{fr}]" for fr, _en in flags),
        summary_en=f"{mtype.label_en} — {milestone.declared_at:%Y-%m-%d %H:%M} UTC{cause_en}"
        + "".join(f" [{en}]" for _fr, en in flags),
        payload={"type": mtype.code, "declared_at": milestone.declared_at, "recorded_at": milestone.recorded_at,
                 "device_recorded_at": milestone.device_recorded_at, "source": milestone.source,
                 "deferred": milestone.deferred, "seal": milestone.seal},
    )


def _apply_effects(call: PortCall, actor, milestone: Milestone) -> None:
    from . import stages as stage_svc

    mtype = milestone.type
    stage_svc.on_milestone(call, actor, milestone)
    if mtype.sets_anchor:
        field = {"ATA": "ata", "ATB": "atb", "T0": "t0", "T1": "t1", "ATD": "atd", "NOR": "nor_at"}[mtype.sets_anchor]
        # first berthing and first start of transfer keep their value over the stages; the end of transfer is the last
        later_stage = milestone.stage_id is not None and milestone.stage.order > 1
        if getattr(call, field) is None or milestone.is_rectification or (field == "t1" and later_stage):
            setattr(call, field, milestone.declared_at)
            call.save(update_fields=[field, "updated_at"])
            recompute_deadlines(call)
    if mtype.sets_status and not milestone.is_rectification:
        advance_from_milestone(call, mtype.sets_status, actor)
    if mtype.completes_tasks:
        complete_by_codes(call, mtype.completes_tasks, actor, evidence=f"milestone:{milestone.pk}")


def _conflict(call, actor, role, milestone: Milestone, first: Milestone) -> None:
    """Two entries of the same milestone: nothing is overwritten, a dispute is opened (EF-14.4, S6)."""
    from .disputes import open_dispute

    delta = abs((milestone.declared_at - first.declared_at).total_seconds()) / 60
    dispute = open_dispute(
        call, actor, target_kind="MILESTONE", target_id=first.pk, as_role=role, auto=True,
        subject=f"{milestone.type.label} — saisies concurrentes / competing entries",
        statement=(
            f"Saisie existante : {first.declared_at:%d/%m/%Y %H:%M} UTC par {first.emitter_label} ; "
            f"nouvelle saisie : {milestone.declared_at:%d/%m/%Y %H:%M} UTC par {milestone.emitter_label}"
            f"{' (saisie différée)' if milestone.deferred else ''} — écart {delta:.0f} min. "
            f"La plateforme ne tranche pas. / Existing entry {first.declared_at:%Y-%m-%d %H:%M} UTC, "
            f"new entry {milestone.declared_at:%Y-%m-%d %H:%M} UTC — the platform does not decide."
        ),
        counterpart_role=first.emitter_role,
    )
    Alert.objects.create(
        call=call, kind=AlertKind.CONFLICT, milestone=milestone, recipient_roles=["AGE", "CAP", role],
        message_fr=f"Conflit de saisie sur « {milestone.type.label_fr} » — contestation {dispute.reference} ouverte",
        message_en=f"Conflicting entries on “{milestone.type.label_en}” — dispute {dispute.reference} opened",
    )


def _notify_milestone(call, actor, milestone: Milestone) -> None:
    mtype = milestone.type
    if mtype.sets_anchor == "NOR" and not milestone.is_rectification:
        notify(call, ["*"], key=f"nor:{milestone.pk}",
               title_fr=f"{call.reference} : NOR remise le {milestone.declared_at:%d/%m %H:%M} UTC",
               title_en=f"{call.reference}: NOR tendered {milestone.declared_at:%d/%m %H:%M} UTC",
               url=call_url(call), realtime=True, exclude_user=actor.user)
        return
    if milestone.countersigner_roles:
        message = {"key": f"countersign:{milestone.pk}", "url": call_url(call) + "#jalons",
                   "title_fr": f"{call.reference} : « {mtype.label_fr} » à contresigner",
                   "title_en": f"{call.reference}: “{mtype.label_en}” to countersign"}
        others = [r for r in milestone.countersigner_roles if r not in SHORE_ROLES]
        if others:
            notify(call, others, **message)
        for shore_role in set(milestone.countersigner_roles) & set(SHORE_ROLES):
            shore = shore_org_id(call, shore_role)  # only the organisation that speaks for the shore side
            if shore is not None:
                notify(call, [shore_role], organizations=[shore], **message)


def record_system_milestone(call: PortCall, mtype: MilestoneType, actor, *, declared_at=None, note: str = "",
                            emitter_role: str = "") -> Milestone | None:
    """Milestones recorded by the platform as consequence of another act (green light, berth, joint signatures)."""
    from . import stages as stage_svc

    stage = stage_svc.current(call)
    if call.milestones.filter(_stage_filter(stage), type=mtype, is_conflict=False).exists() and not mtype.repeatable:
        return None
    now = timezone.now()
    role = emitter_role or (mtype.emitter_role if mtype.emitter_role not in (MilestoneType.SYSTEM, MilestoneType.ORIGIN)
                            else (sorted(actor.roles)[0] if actor.roles else "SYS"))
    milestone = Milestone(
        call=call, type=mtype, stage=stage, declared_at=declared_at or now, recorded_at=now, source=EntrySource.SYSTEM,
        emitter_role=role[:6], emitter_org=actor.org, emitter_user=actor.user if not actor.is_system else None,
        emitter_master=actor.master, emitter_label=actor.label, countersigner_roles=[], note=note,
    )
    milestone.seal = seal(_material(milestone))
    milestone.save()
    _journal_milestone(call, actor, role, milestone, None)
    _apply_effects(call, actor, milestone)
    return milestone


# ============================================================================ countersignature
def state_by_role(milestone: Milestone) -> dict[str, str]:
    states = {role: CountersignState.PENDING for role in milestone.countersigner_roles}
    for sig in milestone.signatures.all():
        states[sig.role] = sig.state
    return states


def overall_state(milestone: Milestone) -> str:
    states = state_by_role(milestone).values()
    if not states:
        return ""
    if CountersignState.CONTESTED in states:
        return CountersignState.CONTESTED
    if CountersignState.PENDING in states:
        return CountersignState.PENDING
    if CountersignState.TACIT in states:
        return CountersignState.TACIT
    return CountersignState.COUNTERSIGNED


@transaction.atomic
def countersign_milestone(milestone: Milestone, actor, *, contest: bool = False, comment: str = "",
                          as_role: str | None = None) -> MilestoneSignature:
    call = milestone.call
    ensure_open(call)
    mtype = milestone.type
    if contest:
        contesters = set(mtype.contester_roles or [])
        allowed = ({"AGE", "NAV", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM"} if "*" in contesters else contesters)
        allowed |= set(milestone.countersigner_roles)
        allowed.discard(milestone.emitter_role)
        if not comment.strip():
            raise RuleViolation(_("A contest states its grounds."))
    else:
        allowed = set(milestone.countersigner_roles)
    withheld = set()
    for shore_role in SHORE_ROLES:  # another terminal or provider of the call does not speak for the shore side
        if shore_role in allowed and not speaks_for_shore(actor, shore_role, call):
            allowed.discard(shore_role)
            withheld.add(shore_role)
    held = set(actor.roles)
    if as_role in withheld or (withheld & held and not allowed & held):
        raise PermissionRefused(_("Another organisation speaks for the shore side on this call: the agency or the "
                                  "harbour master designates it in the parties of the call."))
    role = actor.pick_role(allowed, as_role)
    current = state_by_role(milestone).get(role)
    if not contest and current == CountersignState.COUNTERSIGNED:
        raise RuleViolation(_("Your role has already countersigned this milestone."))
    if contest and current == CountersignState.CONTESTED:
        raise RuleViolation(_("Your role has already contested this milestone."))
    dispute = None
    if contest:
        from .disputes import open_dispute

        dispute = open_dispute(call, actor, target_kind="MILESTONE", target_id=milestone.pk, as_role=role,
                               subject=f"{mtype.label} — {milestone.declared_at:%d/%m/%Y %H:%M} UTC",
                               statement=comment, counterpart_role=milestone.emitter_role)
    now = timezone.now()
    state = CountersignState.CONTESTED if contest else CountersignState.COUNTERSIGNED
    sig = MilestoneSignature.objects.create(
        milestone=milestone, role=role, state=state, user=actor.user, master=actor.master, signer_label=actor.label,
        at=now, comment=comment, dispute=dispute,
        seal=seal({"milestone": milestone.pk, "milestone_seal": milestone.seal, "role": role, "state": state,
                   "at": now.isoformat(), "by": actor.label}),
    )
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="milestone.countersigned" if not contest else "milestone.contested",
        obj=milestone, visible_roles=["*"],
        summary_fr=f"« {mtype.label_fr} » {'contesté' if contest else 'contresigné'} par {role_label(role)}",
        summary_en=f"“{mtype.label_en}” {'contested' if contest else 'countersigned'} by {role}",
        payload={"state": state, "dispute": dispute.reference if dispute else None},
    )
    _complete_acknowledgement_tasks(milestone, actor)
    return sig


def _complete_acknowledgement_tasks(milestone: Milestone, actor) -> None:
    """Signature tasks tied to a milestone (e.g. M0:24 NOR acknowledged by TER and COM)."""
    states = state_by_role(milestone)
    for task in milestone.call.tasks.filter(status=TaskStatus.PENDING, nature="S"):
        if milestone.type.code in (task.milestone_codes or []) and task.joint:
            if all(states.get(r) == CountersignState.COUNTERSIGNED for r in task.all_roles):
                # completion is proven by the explicit countersignatures themselves
                system_complete(task, actor, evidence=f"milestone:{milestone.pk}", note="acknowledged", allow_joint=True)


def apply_tacit_countersignatures(now=None) -> int:
    """Qualified silence (EF-3.4, S4): after the port delay, missing countersignatures become TACIT.
    Never assimilated to an agreement; shown as such on every document produced."""
    now = now or timezone.now()
    created = 0
    candidates = (
        Milestone.objects.filter(recorded_at__gte=now - timedelta(days=60), call__status__in=[
            "DECLARED", "ACCEPTED", "PLANNED", "APPROACHING", "AT_BERTH", "IN_OPERATION", "OPS_COMPLETE", "DEPARTED",
        ])
        .exclude(countersigner_roles=[])
        .select_related("call", "call__port", "type")
        .prefetch_related("signatures")
    )
    for milestone in candidates:
        delay = timedelta(minutes=milestone.call.port.countersign_delay_minutes)
        if milestone.recorded_at + delay > now:
            continue
        signed = {s.role for s in milestone.signatures.all()}
        for role in milestone.countersigner_roles:
            if role in signed:
                continue
            with transaction.atomic():
                MilestoneSignature.objects.create(
                    milestone=milestone, role=role, state=CountersignState.TACIT, signer_label="FLUXAA",
                    at=now, comment="",
                    seal=seal({"milestone": milestone.pk, "role": role, "state": "TACIT", "at": now.isoformat()}),
                )
                journal.record(
                    port=milestone.call.port, call=milestone.call, actor=None, role="SYSTEM",
                    action="milestone.tacit", obj=milestone, visible_roles=["*"],
                    summary_fr=f"« {milestone.type.label_fr} » : contresignature tacite de {role_label(role)} "
                               f"(aucune réponse sous {delay.seconds // 60 + delay.days * 1440} min) — ce n'est pas un accord",
                    summary_en=f"“{milestone.type.label_en}”: tacit countersignature for {role} "
                               f"(no answer within the delay) — not an agreement",
                )
            created += 1
    return created


# ============================================================================ AIS corroboration (EF-3.6)
@transaction.atomic
def corroborate_ais(call: PortCall, type_code: str, ais_time, *, source_label: str = "AIS") -> dict:
    """Compare an AIS observation with the declared milestone. Divergence → alert, never a correction."""
    mtype = get_type(call, type_code)
    if not mtype.ais_corroboration:
        raise RuleViolation(_("This milestone is not corroborated by AIS."))
    milestone = call.milestones.filter(type=mtype, is_conflict=False).order_by("recorded_at").first()
    threshold = call.port.ais_divergence_minutes
    result = {"milestone": milestone.pk if milestone else None, "ais_time": ais_time.isoformat(), "diverges": False}
    if milestone is None:
        journal.record(port=call.port, call=call, actor=None, role="SYSTEM", action="ais.observed", object_kind="call",
                       visible_roles=["AGE", "CAP"],
                       summary_fr=f"AIS : « {mtype.label_fr} » observé à {ais_time:%d/%m %H:%M} UTC (non encore déclaré)",
                       summary_en=f"AIS: “{mtype.label_en}” observed at {ais_time:%Y-%m-%d %H:%M} UTC (not yet declared)",
                       payload={"type": type_code, "ais_time": ais_time})
        return result
    delta = abs((milestone.declared_at - ais_time).total_seconds()) / 60
    result["delta_minutes"] = round(delta, 1)
    if delta > threshold:
        result["diverges"] = True
        Alert.objects.create(
            call=call, kind=AlertKind.AIS, milestone=milestone, recipient_roles=["CAP", "AGE"],
            message_fr=f"Écart AIS de {delta:.0f} min sur « {mtype.label_fr} » (seuil {threshold} min) — aucune correction automatique",
            message_en=f"AIS divergence of {delta:.0f} min on “{mtype.label_en}” (threshold {threshold} min) — no automatic correction",
        )
        notify(call, ["CAP", "AGE"], key=f"ais:{milestone.pk}", title_fr=f"{call.reference} : écart AIS de {delta:.0f} min",
               title_en=f"{call.reference}: AIS divergence {delta:.0f} min", url=call_url(call))
    elif "CAP" in milestone.countersigner_roles and "CAP" not in {s.role for s in milestone.signatures.all()}:
        now = timezone.now()
        MilestoneSignature.objects.create(
            milestone=milestone, role="CAP", state=CountersignState.COUNTERSIGNED, signer_label=f"{source_label} (automatic)",
            at=now, comment=f"AIS {ais_time.isoformat()}",
            seal=seal({"milestone": milestone.pk, "role": "CAP", "state": "COUNTERSIGNED", "ais": ais_time.isoformat()}),
        )
    journal.record(port=call.port, call=call, actor=None, role="SYSTEM", action="ais.corroboration", obj=milestone,
                   visible_roles=["AGE", "CAP", "NAV"],
                   summary_fr=f"Corroboration AIS « {mtype.label_fr} » : écart {delta:.0f} min",
                   summary_en=f"AIS corroboration “{mtype.label_en}”: {delta:.0f} min difference",
                   payload=result)
    return result
