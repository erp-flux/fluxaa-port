"""Measurements and pumping log (EF-8; FLX-CDC-002 v1.4 EXG-Q-01, EXG-Q-05): double declaration, discrepancy, the
platform never decides.

* Quantities: each party enters its own figure (ship = master, shore = the terminal that speaks for the shore
  side, surveyor = the inspector); the platform computes the differences and the tolerance.
* Tank readings: the ship's cargo tanks are read by the ship, the terminal's shore tanks by the terminal; a
  reading is shown to the other parties only once the surveyor has validated it; the surveyor may reject it with
  a reason, and the side enters a corrected reading.
* Pumping log: the ship keeps its sheet, the terminal its own (tank, calibration, density, VCF, planned quantity,
  expected rate and pressure); each reading carries the level, the quantity moved since the previous reading and
  the cumulated quantity, computed from the sheet when the party does not enter them; the two sides are compared
  reading by reading and the port's tolerance (0.3 % by default) raises the alert of the terminal pumping logs:
  "stop for investigation if the deviation exceeds 0.3 %".
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

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
    PumpingLogSheet,
    TankReading,
    TankReadingReview,
)
from . import journal
from .calls import call_url
from .errors import PermissionRefused, RuleViolation, ensure_open
from .milestones import is_deferred
from .notifications import notify
from .rights import acts_for_side, report_readers, speaks_for_shore, tank_reading_visible

SIDE_ROLE = {"SHIP": "NAV", "SHORE": "TER"}
PAIRING_WINDOW = timedelta(minutes=45)  # a ship reading and a shore reading taken within this window are compared


def readers(port, code: str = "MEASUREMENTS") -> list[str]:
    """The roles that read the measurements or the pumping log of this port (parametrage)."""
    return sorted(report_readers(port, code))


def _in(language: str, label) -> str:
    """A choice label rendered in *language*, for the bilingual journal summaries."""
    with translation.override(language):
        return str(label())


def _decimal(value, field: str):
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return parse_decimal(value)
    except ValueError:
        raise RuleViolation(_("“%(f)s” must be a number.") % {"f": field})


def _side_of(actor, side: str | None, call) -> tuple[str, str]:
    """(side, role): the master enters the ship's records, the terminal that speaks for the shore the shore's."""
    if side not in (None, "", "SHIP", "SHORE"):
        raise RuleViolation(_("Unknown side."))
    if side in (None, ""):
        side = "SHIP" if "NAV" in actor.roles else "SHORE"
    role = SIDE_ROLE[side]
    if role not in actor.roles:
        raise PermissionRefused(_("The ship's records are entered by the ship, the shore's by the terminal."))
    if side == "SHORE" and not speaks_for_shore(actor, "TER", call):
        raise PermissionRefused(_("The shore records are entered by the terminal that speaks for the shore side on "
                                  "this call."))
    return side, role


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
                   visible_roles=readers(call.port), summary_fr=f"Mesure ouverte : {_in('fr', m.get_kind_display)} ({unit})",
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
    visible = readers(call.port)
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
            visible_roles=visible,
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
                call=call, kind=AlertKind.QUANTITY, measurement=measurement, recipient_roles=visible,
                message_fr=f"Écart bord/terre {d['percent']:.3f} % (tolérance {measurement.tolerance_pct} %) — ouvrir une contestation si nécessaire ; la plateforme ne tranche pas",
                message_en=f"Ship/shore difference {d['percent']:.3f}% (tolerance {measurement.tolerance_pct}%) — open a dispute if needed; the platform does not decide",
            )
    if measurement.exceeds_tolerance():
        notify(call, visible, key=f"quantity:{measurement.pk}:{mv.pk}",
               title_fr=f"{call.reference} : écart bord/terre hors tolérance", realtime=True,
               title_en=f"{call.reference}: ship/shore difference outside tolerance", url=call_url(call) + "#mesures")
    else:
        notify(call, visible, key=f"quantity:{measurement.pk}:{mv.pk}", exclude_user=actor.user,
               title_fr=f"{call.reference} : {_in('fr', measurement.get_kind_display)} — valeur {_in('fr', lambda: MeasurementParty(party).label).lower()} saisie ({amount} {measurement.unit})",
               title_en=f"{call.reference}: {_in('en', measurement.get_kind_display)} — {_in('en', lambda: MeasurementParty(party).label).lower()} value entered ({amount} {measurement.unit})",
               url=call_url(call) + "#mesures")
    return mv


# ============================================================================ tank readings (EXG-Q-05)
TANK_FIELDS = ("level_mm", "temperature_c", "free_water_mm", "density", "tov_m3", "gov_m3", "vcf", "gsv_m3", "weight_mt")


def add_tank_reading(measurement: Measurement, actor, *, side: str | None = None, tank: str, declared_at=None,
                     note: str = "", supersedes: TankReading | None = None, client_uuid=None, **figures) -> TankReading:
    """A tank of the ship, read by the ship; a shore tank, read by the terminal. The GSV and the weight are computed
    from the GOV, the VCF and the density when the party does not enter them (API MPMS ch. 12). The reading waits
    for the surveyor's validation before the other parties see it."""
    if client_uuid:
        existing = TankReading.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    call = measurement.call
    ensure_open(call)
    side, role = _side_of(actor, side, call)
    tank = " ".join((tank or "").split())[:40]
    if not tank:
        raise RuleViolation(_("Name the tank."))
    values = {name: _decimal(figures.get(name), name) for name in TANK_FIELDS}
    if all(v is None for v in values.values()):
        raise RuleViolation(_("Enter at least one figure for the tank."))
    if values["gsv_m3"] is None and values["gov_m3"] is not None and values["vcf"] is not None:
        values["gsv_m3"] = (values["gov_m3"] * values["vcf"]).quantize(Decimal("0.001"))
    if values["weight_mt"] is None and values["gsv_m3"] is not None and values["density"] is not None:
        values["weight_mt"] = (values["gsv_m3"] * values["density"]).quantize(Decimal("0.001"))
    if supersedes is not None and (supersedes.measurement_id != measurement.pk or supersedes.side != side):
        raise RuleViolation(_("A correction concerns a reading of the same side."))
    now = timezone.now()
    with transaction.atomic():
        reading = TankReading(measurement=measurement, side=side, tank=tank, entered_role=role, entered_org=actor.org,
                              user=actor.user, master=actor.master, entered_label=actor.label, declared_at=declared_at or now,
                              entered_at=now, supersedes=supersedes, note=note[:300], client_uuid=client_uuid, **values)
        reading.seal = seal({"measurement": measurement.pk, "side": side, "tank": tank, "by": actor.label,
                             "at": now.isoformat(), **{k: str(v) for k, v in values.items() if v is not None}})
        reading.save()
        journal.record(
            port=call.port, call=call, actor=actor, role=role, action="tank.reading", obj=reading,
            visible_roles=sorted({role, "INS"}),
            summary_fr=f"{_in('fr', measurement.get_kind_display)} — relevé {'citerne bord' if side == 'SHIP' else 'bac terre'} {tank} : "
                       f"{reading.quantity if reading.quantity is not None else '—'} — en attente de validation par l'inspecteur"
            + (" (correction)" if supersedes else ""),
            summary_en=f"{_in('en', measurement.get_kind_display)} — {'ship tank' if side == 'SHIP' else 'shore tank'} {tank} reading: "
                       f"{reading.quantity if reading.quantity is not None else '—'} — awaiting the surveyor's validation"
            + (" (correction)" if supersedes else ""),
            payload={"side": side, "tank": tank, **{k: v for k, v in values.items() if v is not None}, "seal": reading.seal},
        )
    # the surveyor is asked to validate: one notification per measurement, side and hour (anti-noise)
    notify(call, ["INS"], key=f"tank:{measurement.pk}:{side}:{now:%Y%m%d%H}", realtime=True,
           title_fr=f"{call.reference} : relevés de {'citernes bord' if side == 'SHIP' else 'bacs terre'} à valider ({_in('fr', measurement.get_kind_display)})",
           title_en=f"{call.reference}: {'ship tank' if side == 'SHIP' else 'shore tank'} readings to validate ({_in('en', measurement.get_kind_display)})",
           url=call_url(call) + "#mesures")
    return reading


def current_readings(measurement: Measurement, side: str | None = None) -> list[TankReading]:
    """The latest reading per tank and side (a superseded reading is left out)."""
    superseded = set(TankReading.objects.filter(measurement=measurement, supersedes__isnull=False)
                     .values_list("supersedes_id", flat=True))
    qs = measurement.tank_readings.select_related("entered_org").prefetch_related("reviews").order_by("entered_at", "id")
    if side:
        qs = qs.filter(side=side)
    latest: dict[tuple[str, str], TankReading] = {}
    for reading in qs:
        if reading.pk in superseded:
            continue
        latest[(reading.side, reading.tank)] = reading
    return list(latest.values())


def visible_readings(measurement: Measurement, actor) -> list[TankReading]:
    return [r for r in current_readings(measurement) if tank_reading_visible(actor, r)]


def tank_totals(measurement: Measurement, actor) -> dict[str, dict]:
    """Per side: the tanks visible to the actor, the sum of the validated figures, the pending and rejected
    counts — the side's declared total is compared with its validated tanks on the screen."""
    totals = {"SHIP": {"validated": Decimal("0"), "count": 0, "pending": 0, "rejected": 0, "readings": []},
              "SHORE": {"validated": Decimal("0"), "count": 0, "pending": 0, "rejected": 0, "readings": []}}
    for reading in current_readings(measurement):
        row = totals[reading.side]
        state = reading.state
        if state == TankReadingReview.State.PENDING:
            row["pending"] += 1
        elif state == TankReadingReview.State.REJECTED:
            row["rejected"] += 1
        if not tank_reading_visible(actor, reading):
            continue
        row["readings"].append(reading)
        if state == TankReadingReview.State.VALIDATED and reading.quantity is not None:
            row["validated"] += reading.quantity
            row["count"] += 1
    return totals


def review_tank_reading(reading: TankReading, actor, *, validate: bool, note: str = "") -> TankReadingReview:
    """The surveyor validates a reading — it becomes visible to every reader of the measurements — or rejects it
    with a reason: the side that entered it is told and enters a corrected reading."""
    call = reading.measurement.call
    ensure_open(call)
    if "INS" not in actor.roles:
        raise PermissionRefused(_("Tank readings are validated by the surveyor."))
    if reading.state != TankReadingReview.State.PENDING:
        raise RuleViolation(_("This reading has already been reviewed."))
    if reading not in current_readings(reading.measurement, reading.side):
        raise RuleViolation(_("This reading has been corrected: review the latest reading of the tank."))
    note = (note or "").strip()
    if not validate and not note:
        raise RuleViolation(_("A rejection states its reason."))
    now = timezone.now()
    state = TankReadingReview.State.VALIDATED if validate else TankReadingReview.State.REJECTED
    measurement = reading.measurement
    with transaction.atomic():
        review = TankReadingReview(reading=reading, state=state, role="INS", user=actor.user, master=actor.master,
                                   reviewer_label=actor.label, reviewed_at=now, note=note[:300])
        review.seal = seal({"reading": reading.pk, "state": state, "by": actor.label, "at": now.isoformat(), "note": note})
        review.save()
        where = "citerne bord" if reading.side == "SHIP" else "bac terre"
        where_en = "ship tank" if reading.side == "SHIP" else "shore tank"
        journal.record(
            port=call.port, call=call, actor=actor, role="INS", action="tank.validated" if validate else "tank.rejected",
            obj=reading, visible_roles=readers(call.port) if validate else sorted({reading.entered_role, "INS"}),
            summary_fr=f"{_in('fr', measurement.get_kind_display)} — relevé {where} {reading.tank} "
                       + (f"validé par l'inspecteur : {reading.quantity if reading.quantity is not None else '—'}" if validate else f"rejeté par l'inspecteur — {note}"),
            summary_en=f"{_in('en', measurement.get_kind_display)} — {where_en} {reading.tank} reading "
                       + (f"validated by the surveyor: {reading.quantity if reading.quantity is not None else '—'}" if validate else f"rejected by the surveyor — {note}"),
            payload={"state": state, "note": note, "seal": review.seal},
        )
    if validate:
        notify(call, readers(call.port), key=f"tank:{measurement.pk}:{reading.side}:validated:{now:%Y%m%d%H}", exclude_user=actor.user,
               title_fr=f"{call.reference} : relevés de {where}s validés par l'inspecteur ({_in('fr', measurement.get_kind_display)}) — visibles par les parties",
               title_en=f"{call.reference}: {where_en} readings validated by the surveyor ({_in('en', measurement.get_kind_display)}) — visible to the parties",
               url=call_url(call) + "#mesures")
    else:
        # the ship has no account: the agency, which coordinates the call, relays to the master
        notify(call, sorted({reading.entered_role, "AGE"}), key=f"tank:{reading.pk}:rejected", realtime=True,
               organizations=[reading.entered_org_id, call.agency_id] if reading.entered_org_id else None,
               title_fr=f"{call.reference} : relevé {where} {reading.tank} rejeté par l'inspecteur — {note}",
               title_en=f"{call.reference}: {where_en} {reading.tank} reading rejected by the surveyor — {note}",
               url=call_url(call) + "#mesures")
    return review


# ============================================================================ pumping log (EXG-Q-01)
SHEET_FIELDS = ("start_level_mm", "expected_stop_level_mm", "m3_per_metre", "density", "vcf", "planned_quantity_m3",
                "planned_quantity_mt", "expected_rate_m3h", "expected_pressure_bar")


def open_pumping_sheet(call, actor, *, side: str | None = None, tank: str = "", product: str = "", estimated_start=None,
                       estimated_completion=None, note: str = "", **figures) -> PumpingLogSheet:
    """The header of a side's pumping log: the ship opens the ship's (its tanks), the terminal the shore's (its
    tank), with the calibration, the density, the VCF and the planned quantity the readings are computed with."""
    ensure_open(call)
    side, role = _side_of(actor, side, call)
    values = {name: _decimal(figures.get(name), name) for name in SHEET_FIELDS}
    if values["planned_quantity_mt"] is None and values["planned_quantity_m3"] is not None and values["density"] is not None:
        values["planned_quantity_mt"] = (values["planned_quantity_m3"] * values["density"]
                                         * (values["vcf"] if values["vcf"] is not None else Decimal("1"))).quantize(Decimal("0.001"))
    tank = " ".join((tank or "").split())[:40]
    with transaction.atomic():
        sheet = PumpingLogSheet.objects.create(
            call=call, side=side, tank=tank, product=(product or call.product)[:120], estimated_start=estimated_start,
            estimated_completion=estimated_completion, opened_role=role, opened_org=actor.org, opened_by=actor.user,
            opened_master=actor.master, opened_label=actor.label, note=note[:300], **values,
        )
        journal.record(
            port=call.port, call=call, actor=actor, role=role, action="pumping.sheet", obj=sheet,
            visible_roles=readers(call.port, "PUMPING_LOG"),
            summary_fr=f"Journal de pompage {'bord' if side == 'SHIP' else 'terre'} ouvert"
                       + (f" — {tank}" if tank else "") + (f", {values['planned_quantity_m3']} m³ prévus" if values["planned_quantity_m3"] is not None else ""),
            summary_en=f"{'Ship' if side == 'SHIP' else 'Shore'} pumping log opened"
                       + (f" — {tank}" if tank else "") + (f", {values['planned_quantity_m3']} m³ planned" if values["planned_quantity_m3"] is not None else ""),
            payload={"side": side, "tank": tank, **{k: v for k, v in values.items() if v is not None}},
        )
    notify(call, readers(call.port, "PUMPING_LOG"), key=f"pumping-sheet:{sheet.pk}", exclude_user=actor.user,
           title_fr=f"{call.reference} : journal de pompage {'bord' if side == 'SHIP' else 'terre'} ouvert" + (f" ({tank})" if tank else ""),
           title_en=f"{call.reference}: {'ship' if side == 'SHIP' else 'shore'} pumping log opened" + (f" ({tank})" if tank else ""),
           url=call_url(call) + "#pompage")
    return sheet


def close_pumping_sheet(sheet: PumpingLogSheet, actor, *, actual_stop_level_mm=None, final_volume_m3=None,
                        note: str = "") -> PumpingLogSheet:
    """The side that keeps the sheet records the completion: actual stop level and final volume."""
    call = sheet.call
    ensure_open(call)
    side, role = _side_of(actor, sheet.side, call)
    if sheet.closed_at is not None:
        raise RuleViolation(_("This sheet is already completed."))
    sheet.actual_stop_level_mm = _decimal(actual_stop_level_mm, "actual_stop_level_mm")
    sheet.final_volume_m3 = _decimal(final_volume_m3, "final_volume_m3")
    if sheet.final_volume_m3 is None:
        last = sheet.entries.order_by("-declared_at", "-id").first()
        if last is not None and last.cumulative_m3 is not None:
            sheet.final_volume_m3 = last.cumulative_m3
    sheet.closed_at = timezone.now()
    if note:
        sheet.note = (sheet.note + " — " + note)[:300] if sheet.note else note[:300]
    sheet.save(update_fields=["actual_stop_level_mm", "final_volume_m3", "closed_at", "note"])
    journal.record(port=call.port, call=call, actor=actor, role=role, action="pumping.sheet_closed", obj=sheet,
                   visible_roles=readers(call.port, "PUMPING_LOG"),
                   summary_fr=f"Journal de pompage {'bord' if side == 'SHIP' else 'terre'} terminé — volume final {sheet.final_volume_m3 if sheet.final_volume_m3 is not None else '—'} m³",
                   summary_en=f"{'Ship' if side == 'SHIP' else 'Shore'} pumping log completed — final volume {sheet.final_volume_m3 if sheet.final_volume_m3 is not None else '—'} m³")
    return sheet


def _previous(sheet: PumpingLogSheet | None, call, side: str, declared_at) -> PumpingLogEntry | None:
    qs = sheet.entries if sheet is not None else call.pumping_log.filter(sheet__isnull=True, role=SIDE_ROLE[side])
    return qs.filter(declared_at__lte=declared_at).order_by("-declared_at", "-id").first()


def add_pumping_entry(call, actor, *, declared_at, sheet: PumpingLogSheet | None = None, tank: str = "", level_mm=None,
                      hourly_m3=None, cumulative_m3=None, manifold_pressure_bar=None, flow_rate_m3h=None,
                      temperature_c=None, note: str = "", source: str = EntrySource.ONLINE, device_recorded_at=None,
                      client_uuid=None, device_id: str = "", automatic: bool = False) -> PumpingLogEntry:
    """One reading of a side. What is not entered is computed from the sheet and the previous reading: the quantity
    moved since the previous reading from the level and the calibration, the cumulated quantity, the tonnes, the
    average rate since the previous reading. The other side's reading of the same hour is then compared."""
    if client_uuid:
        existing = PumpingLogEntry.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))
    if sheet is not None and sheet.call_id != call.pk:
        raise RuleViolation(_("This sheet belongs to another call."))
    side, role = _side_of(actor, sheet.side if sheet is not None else None, call)
    if sheet is None:  # the side's open sheet, when it has one (readings from the field app name no sheet)
        sheet = call.pumping_sheets.filter(side=side, closed_at__isnull=True).order_by("-opened_at").first()
    if sheet is not None and sheet.closed_at is not None:
        raise RuleViolation(_("This sheet is completed: open a new one for a further tank."))
    now = timezone.now()
    level = _decimal(level_mm, "level_mm")
    hourly = _decimal(hourly_m3, "hourly_m3")
    cumulative = _decimal(cumulative_m3, "cumulative_m3")
    pressure = _decimal(manifold_pressure_bar, "pressure")
    rate = _decimal(flow_rate_m3h, "rate")
    temperature = _decimal(temperature_c, "temperature")
    previous = _previous(sheet, call, side, declared_at)
    if sheet is not None and level is not None and hourly is None and sheet.m3_per_metre is not None:
        reference = previous.level_mm if previous is not None and previous.level_mm is not None else sheet.start_level_mm
        if reference is not None:
            hourly = (abs(level - reference) / Decimal("1000") * sheet.m3_per_metre).quantize(Decimal("0.001"))
    if cumulative is None and hourly is not None:
        base = previous.cumulative_m3 if previous is not None and previous.cumulative_m3 is not None else Decimal("0")
        cumulative = (base + hourly).quantize(Decimal("0.001"))
    if hourly is None and cumulative is not None and previous is not None and previous.cumulative_m3 is not None:
        hourly = (cumulative - previous.cumulative_m3).quantize(Decimal("0.001"))
    if rate is None and hourly is not None and previous is not None:
        hours = Decimal((declared_at - previous.declared_at).total_seconds()) / Decimal("3600")
        if hours > 0:
            rate = (hourly / hours).quantize(Decimal("0.01"))
    tonnes = sheet.tons(cumulative) if sheet is not None else None
    with transaction.atomic():
        entry = PumpingLogEntry.objects.create(
            call=call, sheet=sheet, declared_at=declared_at, recorded_at=now, role=role, user=actor.user, master=actor.master,
            entered_label=actor.label, tank=(tank or (sheet.tank if sheet is not None else ""))[:40],
            manifold_pressure_bar=pressure, flow_rate_m3h=rate, temperature_c=temperature, level_mm=level, hourly_m3=hourly,
            cumulative_m3=cumulative, cumulative_mt=tonnes.quantize(Decimal("0.001")) if tonnes is not None else None,
            note=note[:300], source="AUTOMATIC" if automatic else "MANUAL", device_id=device_id,
            deferred=is_deferred(source, device_recorded_at, now, declared_at), client_uuid=client_uuid,
        )
        journal.record(port=call.port, call=call, actor=actor, role=role, action="pumping.entry", obj=entry,
                       visible_roles=readers(call.port, "PUMPING_LOG"),
                       summary_fr=f"Journal de pompage {'bord' if side == 'SHIP' else 'terre'} {declared_at:%H:%M} : "
                                  f"{entry.manifold_pressure_bar if entry.manifold_pressure_bar is not None else '—'} bar, "
                                  f"{entry.flow_rate_m3h if entry.flow_rate_m3h is not None else '—'} m³/h, "
                                  f"{entry.temperature_c if entry.temperature_c is not None else '—'} °C"
                                  + (f", niveau {level} mm" if level is not None else "")
                                  + (f", cumul {cumulative} m³" if cumulative is not None else ""),
                       summary_en=f"{'Ship' if side == 'SHIP' else 'Shore'} pumping log {declared_at:%H:%M}: "
                                  f"{entry.manifold_pressure_bar if entry.manifold_pressure_bar is not None else '—'} bar, "
                                  f"{entry.flow_rate_m3h if entry.flow_rate_m3h is not None else '—'} m3/h, "
                                  f"{entry.temperature_c if entry.temperature_c is not None else '—'} °C"
                                  + (f", level {level} mm" if level is not None else "")
                                  + (f", cumulated {cumulative} m³" if cumulative is not None else ""),
                       payload={"side": side, "sheet": sheet.pk if sheet is not None else None})
    # anti-noise (EF-6): the readers are told once per side and six-hour window that readings are coming in; a
    # deviation outside tolerance is told at once, reading by reading (below)
    notify(call, readers(call.port, "PUMPING_LOG"), key=f"pumping:{call.pk}:{side}:{declared_at:%Y%m%d}{declared_at.hour // 6}",
           exclude_user=actor.user,
           title_fr=f"{call.reference} : relevés de pompage {'bord' if side == 'SHIP' else 'terre'} en cours (dernier {declared_at:%H:%M}"
                    + (f", cumul {cumulative} m³" if cumulative is not None else "") + ")",
           title_en=f"{call.reference}: {'ship' if side == 'SHIP' else 'shore'} pumping readings coming in (latest {declared_at:%H:%M}"
                    + (f", cumulated {cumulative} m³" if cumulative is not None else "") + ")",
           url=call_url(call) + "#pompage")
    _check_deviation(call, entry, actor)
    return entry


def _pct(difference, reference):
    if reference in (None, 0):
        return None
    return (difference / reference * 100).quantize(Decimal("0.001"))


def counterpart_entries(call):
    """The other side of the transfer. Alongside a terminal: the shore readings of the call. In a ship-to-ship
    transfer (v1.5, EXG-R-05) each vessel keeps its own log on its own call: the counterpart is the partner
    vessel's ship log, read through the link between the two calls."""
    entries = list(call.pumping_log.select_related("sheet").order_by("declared_at", "id"))
    shore = [e for e in entries if e.side == "SHORE"]
    if not shore and call.is_sts and call.linked_call_id:
        from .calls import link_confirmed

        if link_confirmed(call):  # a partner of another agency only named so far shows nothing of its log (v1.6)
            shore = [e for e in call.linked_call.pumping_log.select_related("sheet").order_by("declared_at", "id") if e.side == "SHIP"]
    return [e for e in entries if e.side == "SHIP"], shore


def counterpart_label(call) -> tuple[str, str]:
    """How the other side is named on the screens and the forms: the shore, or the partner vessel of an STS."""
    if call.is_sts and call.linked_call_id:
        return (f"navire partenaire ({call.linked_call.vessel.name})", f"partner vessel ({call.linked_call.vessel.name})")
    return ("terre", "shore")


def compare_sides(call) -> list[dict]:
    """The pumping log read as the terminal logs read it: each shore reading beside the ship reading of the same
    hour (within the pairing window), the quantity moved by each side, the deviation in m³ and in %, the cumulated
    quantities and their deviation. Neither side's figure is the reference: the deviation is signed shore − ship.
    In an STS transfer the "shore" series is the partner vessel's own log."""
    ship, shore = counterpart_entries(call)
    used: set[int] = set()
    rows = []

    def nearest(candidates, when):
        best, best_delta = None, None
        for c in candidates:
            if c.pk in used:
                continue
            delta = abs(c.declared_at - when)
            if delta <= PAIRING_WINDOW and (best_delta is None or delta < best_delta):
                best, best_delta = c, delta
        return best

    tolerance = call.port.quantity_tolerance_pct
    for s in shore:
        partner = nearest(ship, s.declared_at)
        if partner is not None:
            used.add(partner.pk)
        rows.append(_row(s, partner, tolerance))
    for e in ship:
        if e.pk not in used:
            rows.append(_row(None, e, tolerance))
    rows.sort(key=lambda r: r["at"])
    return rows


def _row(shore, ship, tolerance) -> dict:
    at = (shore or ship).declared_at
    hourly_dev = cum_dev = hourly_pct = cum_pct = None
    if shore is not None and ship is not None:
        if shore.hourly_m3 is not None and ship.hourly_m3 is not None:
            hourly_dev = shore.hourly_m3 - ship.hourly_m3
            hourly_pct = _pct(hourly_dev, ship.hourly_m3)
        if shore.cumulative_m3 is not None and ship.cumulative_m3 is not None:
            cum_dev = shore.cumulative_m3 - ship.cumulative_m3
            cum_pct = _pct(cum_dev, ship.cumulative_m3)
    exceeds = any(p is not None and abs(p) > tolerance for p in (hourly_pct, cum_pct))
    return {"at": at, "shore": shore, "ship": ship, "hourly_deviation": hourly_dev, "hourly_pct": hourly_pct,
            "cumulative_deviation": cum_dev, "cumulative_pct": cum_pct, "exceeds": exceeds}


def _check_deviation(call, entry: PumpingLogEntry, actor) -> None:
    """The rule of the terminal pumping logs: stop for investigation when the deviation between what the ship
    delivered and what the shore received exceeds the tolerance. The alert is a piece of the file; the readers of
    the pumping log are told at once; the platform does not stop the transfer itself and does not decide."""
    row = next((r for r in compare_sides(call) if (r["shore"] is not None and r["shore"].pk == entry.pk)
                or (r["ship"] is not None and r["ship"].pk == entry.pk)), None)
    if row is None or not row["exceeds"] or row["shore"] is None or row["ship"] is None:
        return
    tolerance = call.port.quantity_tolerance_pct
    pct = row["cumulative_pct"] if row["cumulative_pct"] is not None and abs(row["cumulative_pct"]) > tolerance else row["hourly_pct"]
    which_fr = "cumulé" if pct is row["cumulative_pct"] else "horaire"
    which_en = "cumulated" if pct is row["cumulative_pct"] else "hourly"
    visible = readers(call.port, "PUMPING_LOG")
    Alert.objects.create(
        call=call, kind=AlertKind.QUANTITY, recipient_roles=visible,
        message_fr=f"Journal de pompage {entry.declared_at:%H:%M} : écart {which_fr} terre − bord {pct:+.3f} % (tolérance {tolerance} %) — arrêter pour investigation selon la pratique des terminaux ; la plateforme ne tranche pas",
        message_en=f"Pumping log {entry.declared_at:%H:%M}: {which_en} shore − ship deviation {pct:+.3f}% (tolerance {tolerance}%) — stop for investigation as the terminal practice requires; the platform does not decide",
    )
    notify(call, visible, key=f"pumping-dev:{call.pk}:{entry.pk}", realtime=True,
           title_fr=f"{call.reference} : écart de pompage terre − bord {pct:+.3f} % à {entry.declared_at:%H:%M} — hors tolérance, arrêt pour investigation",
           title_en=f"{call.reference}: shore − ship pumping deviation {pct:+.3f}% at {entry.declared_at:%H:%M} — outside tolerance, stop for investigation",
           url=call_url(call) + "#pompage")


def pumping_summary(call) -> dict:
    """Per side: the sheets, the latest reading, the cumulated quantity, the average rate and pressure."""
    summary = {}
    ship_entries, shore_entries = counterpart_entries(call)
    for side in ("SHIP", "SHORE"):
        entries = ship_entries if side == "SHIP" else shore_entries
        pressures = [e.manifold_pressure_bar for e in entries if e.manifold_pressure_bar is not None]
        rates = [e.flow_rate_m3h for e in entries if e.flow_rate_m3h is not None]
        last = entries[-1] if entries else None
        sheets_call = call.linked_call if (side == "SHORE" and shore_entries and shore_entries[0].call_id != call.pk) else call
        sheets_side = "SHIP" if sheets_call.pk != call.pk else side
        summary[side] = {
            "sheets": list(sheets_call.pumping_sheets.filter(side=sheets_side).order_by("opened_at")),
            "count": len(entries), "last": last,
            "cumulative_m3": last.cumulative_m3 if last is not None else None,
            "cumulative_mt": last.cumulative_mt if last is not None else None,
            "average_pressure_bar": (sum(pressures) / len(pressures)).quantize(Decimal("0.01")) if pressures else None,
            "average_rate_m3h": (sum(rates) / len(rates)).quantize(Decimal("0.01")) if rates else None,
        }
    return summary


def can_keep_log(actor, call) -> bool:
    """The master and the terminal that speaks for the shore keep the pumping log."""
    return acts_for_side(actor, "SHIP") or ("TER" in actor.roles and speaks_for_shore(actor, "TER", call))
