"""Stages of a call: a tanker may operate in several areas of the port during one call — lightering at an STS
area then discharging at the quay, loading at a buoy then topping up alongside, waiting at anchorage before
and after. Each stage keeps its own berth, operations, berthing and leaving times and milestones.

Rules: the first stage is born with the call; the agency or the harbour master plans the next ones (the tasks
of the new operations are instantiated at once, so that every party sees its work); leaving a stage is a
milestone (SHIFT_START, recorded by the marine services) that needs a movement authorization in force, like
the pilot's boarding; the berthing at the next stage uses the ordinary milestones, scoped to that stage. The
call-level anchors keep their meaning: ATB is the first berthing, T0 the first start of transfer, T1 the last
end of transfer, ATD the final departure.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.models import Berth

from ..models import CallStage, CallStatus, CallTemplate, CallTemplateUse, PortCall, TemplateKind
from . import journal
from .context import Actor
from .errors import PermissionRefused, RuleViolation
from .notifications import notify

AUTO_MODULES = (("MA2", {Berth.Kind.SPM}), ("MA3", {Berth.Kind.ANCHORAGE, Berth.Kind.STS_AREA}))
STAGE_KINDS = {k for k, _l in Berth.Kind.choices}


def current(call: PortCall) -> CallStage | None:
    return call.stages.filter(status=CallStage.Status.CURRENT).order_by("-order").first()


def next_planned(call: PortCall) -> CallStage | None:
    return call.stages.filter(status=CallStage.Status.PLANNED).order_by("order").first()


def ensure_initial(call: PortCall, *, user=None) -> CallStage:
    """The first stage, born with the call (also used to backfill calls created before stages existed)."""
    stage = current(call) or call.stages.order_by("order").first()
    if stage is not None:
        return stage
    operations = [c for c in call.template_codes if c != "M0"]
    return CallStage.objects.create(
        call=call, order=1, berth_kind=call.requested_berth_kind, berth=call.berth, operations=operations,
        planned_from=call.etb, planned_to=call.etd, atb=call.atb, atd=call.atd if call.atd else None,
        status=CallStage.Status.DONE if call.atd else CallStage.Status.CURRENT, created_by=user or call.created_by,
    )


def _templates_for(port, berth_kind: str, operations: list[str]) -> tuple[list[str], list]:
    """Operation templates (plus the modules that come with the area) applicable to *berth_kind*."""
    from .calls import _published_versions

    codes = list(dict.fromkeys(operations))
    if not codes:
        raise RuleViolation(_("Select at least one operation model for the stage."))
    templates = {t.code: t for t in CallTemplate.objects.filter(port=port, code__in=codes, is_active=True)}
    for code in codes:
        tpl = templates.get(code)
        if tpl is None or tpl.kind != TemplateKind.OPERATION:
            raise RuleViolation(_("%(code)s is not an operation model.") % {"code": code})
        if tpl.berth_kinds and berth_kind not in tpl.berth_kinds:
            raise RuleViolation(_("Template %(code)s does not apply to this operating area.") % {"code": code})
    for auto_code, kinds in AUTO_MODULES:
        if berth_kind in kinds and auto_code not in codes and CallTemplate.objects.filter(
            port=port, code=auto_code, is_active=True
        ).exists():
            codes.append(auto_code)
    return codes, _published_versions(port, codes)


@transaction.atomic
def add_stage(call: PortCall, actor: Actor, *, berth_kind: str, operations: list[str], berth: Berth | None = None,
              planned_from=None, planned_to=None, reason: str = "") -> CallStage:
    """Plan the next stage of the call: its area, its operations (tasks instantiated now), its window."""
    from .calls import instantiate_tasks

    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("The stages of a call are planned by the agency or the harbour master."))
    if call.is_terminal_state or call.status == CallStatus.DEPARTED:
        raise RuleViolation(_("The call is closed or the vessel has departed: no further stage."))
    if berth_kind not in STAGE_KINDS:
        raise RuleViolation(_("Unknown operating area."))
    if berth is not None and (berth.port_id != call.port_id or berth.kind != berth_kind):
        raise RuleViolation(_("The requested berth does not match the operating area."))
    if planned_from and planned_to and planned_to <= planned_from:
        raise RuleViolation(_("The end of the window must follow its start."))
    ensure_initial(call)
    codes, versions = _templates_for(call.port, berth_kind, list(operations))
    used = set(call.template_codes)
    new_versions = [v for v in versions if v.template.code not in used]
    order = (call.stages.order_by("-order").values_list("order", flat=True).first() or 0) + 1
    stage = CallStage.objects.create(
        call=call, order=order, berth_kind=berth_kind, berth=berth, operations=codes, planned_from=planned_from,
        planned_to=planned_to, status=CallStage.Status.PLANNED, reason=reason[:300], created_by=actor.user,
    )
    for version in new_versions:
        CallTemplateUse.objects.create(call=call, template_version=version)
    created = instantiate_tasks(call, new_versions, berth_kind=berth_kind, stage=stage) if new_versions else []
    # templates the call already holds (the common base, a reused operation): the lines specific to the new area
    reused = [use.template_version for use in call.template_uses.select_related("template_version__template")
              if use.template_version.template.code in used]
    created += instantiate_tasks(call, reused, berth_kind=berth_kind, stage=stage, only_new=True)
    role = "AGE" if "AGE" in actor.roles else "CAP"
    where = berth.code if berth else stage.get_berth_kind_display()
    journal.record(
        port=call.port, call=call, actor=actor, role=role, action="call.stage_planned", obj=stage,
        summary_fr=f"Étape {order} planifiée : {where} — modèles {', '.join(codes)} ({len(created)} tâches ajoutées)"
        + (f" — {reason}" if reason else ""),
        summary_en=f"Stage {order} planned: {where} — templates {', '.join(codes)} ({len(created)} tasks added)"
        + (f" — {reason}" if reason else ""),
        payload={"stage": order, "berth_kind": berth_kind, "berth": berth.code if berth else None, "templates": codes,
                 "planned_from": planned_from, "planned_to": planned_to, "tasks": len(created)},
    )
    if call.status != CallStatus.DRAFT:
        from .calls import call_url

        notify(call, ["*"], key=f"stage:{stage.pk}",
               title_fr=f"{call.reference} : étape {order} planifiée — {where} ({', '.join(codes)})",
               title_en=f"{call.reference}: stage {order} planned — {where} ({', '.join(codes)})", url=call_url(call))
    return stage


def cancel_stage(call: PortCall, actor: Actor, stage: CallStage, reason: str) -> CallStage:
    """A planned stage is cancelled, never deleted; its tasks stay and may be marked not applicable."""
    if "AGE" not in actor.roles and "CAP" not in actor.roles:
        raise PermissionRefused(_("The stages of a call are planned by the agency or the harbour master."))
    if stage.call_id != call.id or stage.status != CallStage.Status.PLANNED:
        raise RuleViolation(_("Only a planned stage can be cancelled."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    stage.status = CallStage.Status.CANCELLED
    stage.cancelled_at = timezone.now()
    stage.cancel_reason = reason[:300]
    stage.save(update_fields=["status", "cancelled_at", "cancel_reason"])
    journal.record(port=call.port, call=call, actor=actor, action="call.stage_cancelled", obj=stage,
                   summary_fr=f"Étape {stage.order} annulée — {reason}", summary_en=f"Stage {stage.order} cancelled — {reason}")
    return stage


def assign_berth(call: PortCall, berth: Berth) -> CallStage | None:
    """A berth assignment goes to the stage it is meant for: the next planned stage of that kind when there is
    one (the vessel is still elsewhere), otherwise the current stage (and the call itself)."""
    planned = call.stages.filter(status=CallStage.Status.PLANNED, berth_kind=berth.kind).order_by("order").first()
    if planned is not None:
        planned.berth = berth
        planned.save(update_fields=["berth"])
        return planned
    stage = current(call)
    if stage is not None and stage.berth_id != berth.pk:
        stage.berth = berth
        stage.save(update_fields=["berth"])
    return stage


def check_shift_possible(call: PortCall) -> CallStage:
    stage = next_planned(call)
    if stage is None:
        raise RuleViolation(_("No next stage is planned for this call: the agency or the harbour master plans it first "
                              "(overview, « Stages of the call »)."))
    return stage


def on_milestone(call: PortCall, actor: Actor, milestone) -> None:
    """Effects of a milestone on the stages: leaving the current one, berthing at the next one."""
    code = milestone.type.code
    if milestone.is_conflict or milestone.is_rectification:
        return
    if code == "SHIFT_START":
        leaving = current(call)
        nxt = check_shift_possible(call)
        if leaving is not None:
            leaving.status = CallStage.Status.DONE
            leaving.atd = milestone.declared_at
            leaving.save(update_fields=["status", "atd"])
        nxt.status = CallStage.Status.CURRENT
        nxt.save(update_fields=["status"])
        call.berth = nxt.berth
        call.requested_berth_kind = nxt.berth_kind
        if nxt.planned_from:
            call.etb = nxt.planned_from
        call.save(update_fields=["berth", "requested_berth_kind", "etb", "updated_at"])
        from .calls import recompute_deadlines

        recompute_deadlines(call)
        journal.record(
            port=call.port, call=call, actor=actor, action="call.stage_changed", obj=nxt,
            summary_fr=f"Étape {nxt.order} en cours : {nxt.label} (étape {leaving.order if leaving else '—'} terminée)",
            summary_en=f"Stage {nxt.order} under way: {nxt.label} (stage {leaving.order if leaving else '—'} done)",
            payload={"from": leaving.order if leaving else None, "to": nxt.order, "at": milestone.declared_at},
        )
    elif milestone.type.sets_anchor == "ATB":
        stage = current(call)
        if stage is not None and stage.atb is None:
            stage.atb = milestone.declared_at
            stage.save(update_fields=["atb"])


def summary(call: PortCall) -> list[dict]:
    rows = []
    for stage in call.stages.select_related("berth").order_by("order"):
        rows.append({"order": stage.order, "berth_kind": stage.berth_kind, "area": stage.get_berth_kind_display(),
                     "berth": stage.berth.code if stage.berth_id else None, "operations": stage.operations,
                     "planned_from": stage.planned_from, "planned_to": stage.planned_to, "atb": stage.atb,
                     "atd": stage.atd, "status": stage.status, "reason": stage.reason})
    return rows
