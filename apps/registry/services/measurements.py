"""Measurements and pumping log (EF-8): double declaration, discrepancy, the platform never decides."""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.numbers import parse_decimal

from ..models import (
    MEASUREMENT_PARTY_ROLE,
    Alert,
    AlertKind,
    EntrySource,
    Measurement,
    MeasurementParty,
    MeasurementValue,
    PumpingLogEntry,
)
from . import journal
from .calls import call_url
from .errors import PermissionRefused, RuleViolation, ensure_open
from .milestones import is_deferred
from .notifications import notify
from .rights import roles_with, speaks_for_shore

MEASUREMENT_ROLES = sorted(roles_with("V", "measurement"))


def _in(language: str, label) -> str:
    """A choice label rendered in *language*, for the bilingual journal summaries."""
    with translation.override(language):
        return str(label())


def _decimal(value, field: str):
    if value in (None, ""):
        return None
    try:
        return parse_decimal(value)
    except ValueError:
        raise RuleViolation(_("“%(f)s” must be a number.") % {"f": field})


@transaction.atomic
def create_measurement(call, actor, kind: str, *, unit: str = "MT", product: str = "") -> Measurement:
    ensure_open(call)
    role = actor.pick_role({"INS", "TER", "NAV"})
    if kind not in Measurement.Kind.values:
        raise RuleViolation(_("Unknown measurement kind."))
    m = Measurement.objects.create(call=call, kind=kind, unit=unit, product=product or call.product,
                                   tolerance_pct=call.port.quantity_tolerance_pct, created_role=role,
                                   created_by=actor.user)
    journal.record(port=call.port, call=call, actor=actor, role=role, action="measurement.created", obj=m,
                   visible_roles=MEASUREMENT_ROLES, summary_fr=f"Mesure ouverte : {_in('fr', m.get_kind_display)} ({unit})",
                   summary_en=f"Measurement opened: {_in('en', m.get_kind_display)} ({unit})")
    return m


def add_value(measurement: Measurement, actor, party: str, value, *, temperature=None, density=None,
              declared_at=None, note: str = "", source: str = EntrySource.ONLINE, device_recorded_at=None,
              client_uuid=None, supersedes: MeasurementValue | None = None) -> MeasurementValue:
    """Single emitter per value (rule 1): ship = NAV, shore = TER, surveyor = INS."""
    if client_uuid:
        existing = MeasurementValue.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    if party not in MeasurementParty.values:
        raise RuleViolation(_("Unknown party."))
    role = MEASUREMENT_PARTY_ROLE[party]
    if role not in actor.roles:
        raise PermissionRefused(_("This value is entered by its owner only (single emitter)."))
    call = measurement.call
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    amount = _decimal(value, "value")
    if amount is None or amount < 0:
        raise RuleViolation(_("A quantity is a positive number."))
    if supersedes is not None and (supersedes.measurement_id != measurement.pk or supersedes.party != party):
        raise RuleViolation(_("A correction concerns a value of the same party."))
    # the shore figure is the terminal's of the call (the organisation that speaks for the shore side), whoever types
    # first; the ship figure is the master's; surveyors — there may be one per interest — each enter their own
    if party == MeasurementParty.SHORE and not speaks_for_shore(actor, "TER", call):
        raise PermissionRefused(_("The shore figure is entered by the terminal that speaks for the shore side on "
                                  "this call."))
    now = timezone.now()
    with transaction.atomic():
        mv = MeasurementValue(
            measurement=measurement, party=party, value=amount, temperature_c=_decimal(temperature, "temperature"),
            density=_decimal(density, "density"), entered_role=role, user=actor.user, master=actor.master,
            entered_label=actor.label, declared_at=declared_at or now, entered_at=now,
            deferred=is_deferred(source, device_recorded_at, now, declared_at), source=source, supersedes=supersedes,
            note=note,
            client_uuid=client_uuid,
        )
        mv.seal = seal({"measurement": measurement.pk, "party": party, "value": str(amount), "role": role,
                        "by": actor.label, "at": now.isoformat(), "supersedes": supersedes.pk if supersedes else None})
        mv.save()
        journal.record(
            port=call.port, call=call, actor=actor, role=role, action="measurement.value", obj=measurement,
            visible_roles=MEASUREMENT_ROLES,
            summary_fr=f"{_in('fr', measurement.get_kind_display)} — valeur {_in('fr', lambda: MeasurementParty(party).label)} : "
                       f"{amount} {measurement.unit}"
            + (" (correction)" if supersedes else "") + (" [saisie différée]" if mv.deferred else ""),
            summary_en=f"{_in('en', measurement.get_kind_display)} — {_in('en', lambda: MeasurementParty(party).label)} value: "
                       f"{amount} {measurement.unit}"
            + (" (correction)" if supersedes else "") + (" [deferred entry]" if mv.deferred else ""),
            payload={"party": party, "value": amount, "seal": mv.seal},
        )
        if measurement.exceeds_tolerance():
            d = measurement.discrepancy()
            Alert.objects.create(
                call=call, kind=AlertKind.QUANTITY, measurement=measurement, recipient_roles=MEASUREMENT_ROLES,
                message_fr=f"Écart bord/terre {d['percent']:.3f} % (tolérance {measurement.tolerance_pct} %) — ouvrir une contestation si nécessaire ; la plateforme ne tranche pas",
                message_en=f"Ship/shore difference {d['percent']:.3f}% (tolerance {measurement.tolerance_pct}%) — open a dispute if needed; the platform does not decide",
            )
    if measurement.exceeds_tolerance():
        notify(call, ["NAV", "TER", "INS", "AGE", "COM"], key=f"quantity:{measurement.pk}:{mv.pk}",
               title_fr=f"{call.reference} : écart bord/terre hors tolérance", realtime=True,
               title_en=f"{call.reference}: ship/shore difference outside tolerance", url=call_url(call) + "#mesures")
    return mv


def add_pumping_entry(call, actor, *, declared_at, manifold_pressure_bar=None, flow_rate_m3h=None, temperature_c=None,
                      note: str = "", source: str = EntrySource.ONLINE, device_recorded_at=None, client_uuid=None,
                      device_id: str = "", automatic: bool = False) -> PumpingLogEntry:
    if client_uuid:
        existing = PumpingLogEntry.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    role = actor.pick_role({"TER", "NAV"})
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    now = timezone.now()
    with transaction.atomic():
        entry = PumpingLogEntry.objects.create(
            call=call, declared_at=declared_at, recorded_at=now, role=role, user=actor.user, master=actor.master,
            entered_label=actor.label, manifold_pressure_bar=_decimal(manifold_pressure_bar, "pressure"),
            flow_rate_m3h=_decimal(flow_rate_m3h, "rate"), temperature_c=_decimal(temperature_c, "temperature"),
            note=note, source="AUTOMATIC" if automatic else "MANUAL", device_id=device_id,
            deferred=is_deferred(source, device_recorded_at, now, declared_at), client_uuid=client_uuid,
        )
        journal.record(port=call.port, call=call, actor=actor, role=role, action="pumping.entry", obj=entry,
                       visible_roles=MEASUREMENT_ROLES,
                       summary_fr=f"Journal de pompage {declared_at:%H:%M} : {entry.manifold_pressure_bar or '—'} bar, {entry.flow_rate_m3h or '—'} m³/h, {entry.temperature_c or '—'} °C",
                       summary_en=f"Pumping log {declared_at:%H:%M}: {entry.manifold_pressure_bar or '—'} bar, {entry.flow_rate_m3h or '—'} m3/h, {entry.temperature_c or '—'} °C")
    return entry
