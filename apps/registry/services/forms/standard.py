"""The fourteen reference forms of the ship/shore interface, the formalities and the services: NOR, time sheet,
ISGOTT ship/shore safety checklist, pre-transfer agreement, ullage report, hose record, letter of protest, FAL
forms, declaration of security, maritime declaration of health, advance waste notification, STS checklists, pilot
card, bunker delivery note. Pre-filled from the registry, completed and signed on paper, filed back as versions."""
from __future__ import annotations

from decimal import Decimal

from ...models import PortCall
from ..reports import interruptions, time_sheet
from .core import F, Form, _m, _mt, _operation, _party, _register, _where, checklist, dt, fields, table, text


def build_nor(call: PortCall) -> list[dict]:
    arrival = _m(call, "ARRIVAL")
    nor = _m(call, "NOR_TENDERED")
    loading = any(code in call.template_codes for code in ("M2", "MB2"))
    op = _operation(call)
    op_fr, op_en = ("chargement", "loading") if loading else ("déchargement", "discharge")
    return [
        fields(("Navire et escale", "Vessel and call"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"),
            F("Pavillon", "Flag", call.vessel.flag or None, source="Vessel.flag"),
            F("Voyage", "Voyage", call.voyage_number or None, source="PortCall.voyage_number"),
            F("Port", "Port", f"{call.port.name} ({call.port.code})", source="Port.name, Port.code"),
            F("Poste / zone", "Berth / area", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
            F("Produit", "Product", call.product or None, source="PortCall.product"),
            F("Quantité nominée", "Nominated quantity", f"{call.quantity} {call.quantity_unit}" if call.quantity else None, source="PortCall.quantity, PortCall.quantity_unit"),
            F("Opération", "Operation", op, source="PortCall.template_codes (M2 = chargement, sinon déchargement)"),
        ]),
        fields(("Heures", "Times"), [
            F("Arrivée à la limite du port (ATA)", "Arrival at the port limit (ATA)", dt(arrival.declared_at) if arrival else dt(call.ata), source="jalon ARRIVAL.declared_at, sinon PortCall.ata"),
            F("Mouillage", "Anchored", _mt(call, "ANCHORED"), source="jalon ANCHORED.declared_at"),
            F("NOR remise le", "NOR tendered on", dt(nor.declared_at) if nor else dt(call.nor_at), source="jalon NOR_TENDERED.declared_at, sinon PortCall.nor_at"),
            F("Remise par", "Tendered by", nor.emitter_label if nor else None, source="jalon NOR_TENDERED.emitter_label"),
            F("Destinataires", "Addressed to", ", ".join(filter(None, [_party(call, "TER"), _party(call, "COM")])) or None, wide=True, source="CallParty TER et COM actives (Organization.name)"),
        ]),
        text(("Déclaration", "Statement"), [
            ("Je soussigné, capitaine du navire ci-dessus, vous informe que le navire est arrivé au port et se trouve, à tous égards, "
             "prêt à commencer les opérations de " + op_fr + " conformément aux termes de la charte-partie.",
             "I, the undersigned master of the above vessel, hereby give notice that the vessel has arrived at the port and is in "
             "all respects ready to commence " + op_en + " in accordance with the terms of the charter-party."),
            ("Le temps de planche court conformément à la charte-partie. Heure de réception et observations du destinataire ci-dessous.",
             "Laytime counts in accordance with the charter-party. Time of receipt and the recipient's remarks below."),
        ]),
        fields(("Accusé de réception", "Acknowledgement of receipt"), [
            F("Reçue le (date, heure)", "Received on (date, time)"),
            F("Acceptée / acceptée sous réserve", "Accepted / accepted under reserve"),
            F("Observations", "Remarks", wide=True),
        ]),
    ]


def _h(delta) -> str | None:
    """Hours and minutes of a duration, as the time sheets write them (h:mm)."""
    if delta is None:
        return None
    minutes = int(round(delta.total_seconds() / 60))
    return f"{minutes // 60}:{minutes % 60:02d}"


def _party_kind(call: PortCall, role: str, kinds: tuple[str, ...]) -> str | None:
    """The organisation holding *role* whose kind is one of *kinds* (the trader, the supercargo…), else none."""
    for party in call.parties.filter(role=role, revoked_at__isnull=True).select_related("organization"):
        if party.organization.kind in kinds:
            return party.organization.name
    return None


def _products(call: PortCall) -> list[str]:
    seen = []
    for name in [m.product for m in call.measurements.all()] + [call.product]:
        if name and name not in seen:
            seen.append(name)
    return seen[:3] or [""]


def _figure(call: PortCall, product: str, kind: str, party: str):
    for m in call.measurements.filter(kind=kind).order_by("-created_at"):
        if product and m.product and m.product != product:
            continue
        value = m.current_values().get(party)
        if value is not None:
            return value.value, m.unit
    return None, None


def build_time_sheet(call: PortCall) -> list[dict]:
    """The vessel time sheet of the demurrage analysis, in the structure of the terminal time sheets (FLX-CDC-002
    v1.4, EXG-Q-02): general information, standard activities from/to/elapsed, non-standard activities and
    stoppages with the delay counted and its attribution, quantities and performance per product, time summary,
    exclusions and remarks, four signatures. Every time comes from the contradictory registry."""
    sheet = time_sheet(call)
    nor = _m(call, "NOR_TENDERED")
    nor_received = None
    if nor is not None:
        received = nor.signatures.filter(role="TER", state="COUNTERSIGNED").order_by("at").first()
        nor_received = dt(received.at) if received else None
    arrival = _m(call, "ARRIVAL")
    products = _products(call)
    general = fields(("A · Informations générales", "A · General information"), [
        F("Navire", "Vessel", call.vessel.name, source="Vessel.name"), F("Pavillon", "Flag", call.vessel.flag or None, source="Vessel.flag"),
        F("Numéro OMI", "IMO number", call.vessel.imo, source="Vessel.imo"), F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind"),
        F("Fin de traversée (E.O.S.P.)", "E.O. sea passage", dt(arrival.declared_at) if arrival else dt(call.ata), source="jalon ARRIVAL.declared_at, sinon PortCall.ata"),
        F("NOR remise", "N.O.R. tendered", dt(nor.declared_at) if nor else dt(call.nor_at), source="jalon NOR_TENDERED.declared_at"),
        F("NOR reçue", "N.O.R. received", nor_received, source="contresignature TER du jalon NOR_TENDERED (MilestoneSignature.at)"),
        F("Négociant (trader)", "Trader", _party_kind(call, "COM", ("TRADER", "CHARTERER", "SHIPPER", "RECEIVER")) or _party(call, "COM"), source="CallParty COM (kind TRADER / CHARTERER / SHIPPER / RECEIVER)"),
        F("Agent", "Agent", str(call.agency), source="PortCall.agency"), F("Inspecteur", "Surveyor", _party(call, "INS"), source="CallParty INS active"),
        F("Subrécargue", "Supercargo", _party_kind(call, "COM", ("SUPERCARGO", "SUPERINTENDENT")), source="CallParty COM (kind SUPERCARGO / SUPERINTENDENT)"),
        F("Déplacement (t)", "Displacement (t)"), F("Tirant d'eau à l'arrivée (m)", "Draft — arrival (m)"), F("Tirant d'eau au départ (m)", "Draft — departure (m)"),
        F("Produit 1", "Product 1", products[0] or None, source="Measurement.product, sinon PortCall.product"),
        F("Produit 2", "Product 2", products[1] if len(products) > 1 else None, source="Measurement.product"),
        F("Produit 3", "Product 3", products[2] if len(products) > 2 else None, source="Measurement.product"),
        F("Opération", "Operation", _operation(call), source="PortCall.template_codes"),
        F("Port en lourd (t)", "Deadweight (t)", str(call.vessel.dwt) if call.vessel.dwt else None, source="Vessel.dwt"),
        F("Temps de pompage prévu (h)", "Planned pump time (h)", str(call.planned_pump_hours) if call.planned_pump_hours is not None else None, source="PortCall.planned_pump_hours"),
        F("Référence du lot", "Batch reference", call.batch_reference or None, source="PortCall.batch_reference"),
    ])
    activities = [
        ("Pilote à bord (arrivée)", "Pilot on board (arrival)", "PILOT_ON_BOARD_ARR", "FIRST_LINE"),
        ("Mouillage", "Anchored", "ANCHORED", "ANCHOR_AWEIGH"),
        ("Amarrage", "Mooring", "FIRST_LINE", "ALL_FAST"),
        ("Réunion de sécurité navire / terre", "Ship / shore safety meeting", "PRE_TRANSFER_MEETING", "SSSCL_SIGNED"),
        ("Raccordement des bras ou flexibles", "Arm or hose connection", "ESD_TEST", "HOSES_CONNECTED"),
        ("Chargement / déchargement / manutention", "Loading / unloading / cargo operations", ("TRANSFER_START", "STS_TRANSFER_START", "CARGO_OPS_START"), ("TRANSFER_END", "STS_TRANSFER_END", "CARGO_OPS_END")),
        ("Débranchement", "Disconnecting", "LINES_DRAINED", "HOSES_DISCONNECTED"),
        ("Documents à bord et signés", "Documents on board and signed", "DOCUMENTS_SIGNED", None),
        ("Pilote à bord (départ)", "Pilot on board (departure)", "PILOT_ON_BOARD_DEP", "LAST_LINE"),
        ("Désamarrage", "Unmooring", "LAST_LINE", "DEPARTED"),
    ]
    rows = []
    for n, (fr, en, start_codes, end_codes) in enumerate(activities, start=1):
        start_m = next((m for code in (start_codes if isinstance(start_codes, tuple) else (start_codes,)) if (m := _m(call, code))), None)
        end_m = next((m for code in (end_codes if isinstance(end_codes, tuple) else (end_codes,)) if (m := _m(call, code))), None) if end_codes else None
        elapsed = _h(end_m.declared_at - start_m.declared_at) if start_m and end_m and end_m.declared_at >= start_m.declared_at else None
        remarks = []
        for m in (start_m, end_m):
            if m is not None:
                states = ", ".join(f"{sg.role}: {sg.get_state_display()}" for sg in m.signatures.all())
                remarks.append(f"{m.type.code} {m.emitter_label}" + (f" — {states}" if states else ""))
        rows.append([str(n), dt(start_m.declared_at) if start_m else None, dt(end_m.declared_at) if end_m else None, elapsed,
                     f"{fr} / {en}", " ; ".join(remarks) or None])
    all_fast, last_line = _m(call, "ALL_FAST") or _m(call, "STS_ALONGSIDE"), _m(call, "LAST_LINE") or _m(call, "STS_SEPARATED")
    alongside = (last_line.declared_at - all_fast.declared_at) if all_fast and last_line else None
    rows.append(["", None, None, _h(alongside), "Temps total à quai / Total time alongside", "ALL_FAST → LAST_LINE"])
    stops = interruptions(call)
    attribution = {"SHIP": "navire / ship", "SHORE": "terre / shore", "THIRD": "tiers / third party", "WEATHER": "météo / weather"}
    stop_rows = []
    counted_total = Decimal("0")
    counted_shore = Decimal("0")
    for n, row in enumerate(stops, start=1):
        duration = (row["end"].declared_at - row["start"].declared_at) if row["end"] else None
        counted = _h(duration) if duration is not None and row["established"] else None
        if duration is not None and row["established"]:
            counted_total += Decimal(duration.total_seconds()) / Decimal("3600")
            if row["attribution"] == "SHORE":
                counted_shore += Decimal(duration.total_seconds()) / Decimal("3600")
        description = (f"{row['cause'].label_fr} / {row['cause'].label_en}" if row["cause"] else "—")
        if row["start"].cause_reason:
            description += f" — {row['start'].cause_reason}"
        description += f" ({row['start'].emitter_label}" + ("" if row["established"] else " ; contestée ou tacite / contested or tacit") + ")"
        stop_rows.append([str(n), dt(row["start"].declared_at), dt(row["end"].declared_at) if row["end"] else None, _h(duration),
                          counted, attribution.get(row["attribution"], row["attribution"] or "—"), description])
    stop_rows.append(["", None, None, None, f"{counted_total:.2f} h", "", "Total des retards comptés / Total delays counted — "
                      f"dont imputables à terre / of which attributable to shore : {counted_shore:.2f} h"])
    t0, t1 = call.t0, call.t1
    gross = (t1 - t0) if t0 and t1 else None
    net_h = (Decimal(gross.total_seconds()) / Decimal("3600") - counted_total) if gross is not None else None
    from ..measurements import pumping_summary

    pumping = pumping_summary(call)
    pressure = pumping["SHORE"]["average_pressure_bar"] or pumping["SHIP"]["average_pressure_bar"]
    perf_rows = []
    for product in products:
        bl, unit = _figure(call, product, "BL", "SHIP")
        if bl is None:
            bl, unit = _figure(call, product, "BL", "SHORE")
        ship, unit_s = _figure(call, product, "FINAL", "SHIP")
        shore, unit_t = _figure(call, product, "FINAL", "SHORE")
        quantity = shore if shore is not None else ship
        average = (quantity / net_h).quantize(Decimal("0.1")) if quantity is not None and net_h and net_h > 0 else None
        required = (quantity / call.planned_pump_hours).quantize(Decimal("0.1")) if quantity is not None and call.planned_pump_hours else None
        perf_rows.append([product or "—", f"{bl} {unit}" if bl is not None else None, f"{ship} {unit_s}" if ship is not None else None,
                          f"{shore} {unit_t}" if shore is not None else None,
                          f"{average} {unit_t or unit_s or ''}/h".strip() if average is not None else None,
                          f"{required} {unit_t or unit_s or ''}/h".strip() if required is not None else None,
                          f"{pressure} bar" if pressure is not None else None])
    return [
        general,
        table(("B · Activités standard", "B · Standard activities"),
              [("N°", "No."), ("Du", "From"), ("Au", "To"), ("Durée", "Elapsed"), ("Opération", "Operation"), ("Observations", "Comments / remarks")],
              rows, source="jalons du registre (declared_at, emitter_label) et contresignatures ; durée = au − du"),
        table(("C · Activités non standard et arrêts", "C · Non-standard activities and stoppages"),
              [("N°", "No."), ("Du", "From"), ("Au", "To"), ("Durée", "Elapsed"), ("Retard compté", "Delay counted"), ("Imputable à", "Attributable to"), ("Description", "Description")],
              stop_rows, blank_rows=2,
              source="reports.interruptions : jalons INTERRUPTION_START/END, InterruptionCause.attributable_to ; retard compté = durée des interruptions à cause établie contradictoirement",
              note=("Le retard compté est pré-rempli pour les interruptions dont la cause est établie contradictoirement ; une interruption contestée ou tacite est laissée à l'appréciation des signataires.",
                    "The delay counted is pre-filled for the stoppages whose cause is established contradictorily; a contested or tacit stoppage is left to the signatories.")),
        table(("D · Quantités et performance", "D · Quantities and performance"),
              [("Produit", "Product"), ("Quantité B/L", "B/L quantity"), ("Quantité bord", "Ship quantity"), ("Quantité terre", "Shore quantity"),
               ("Débit moyen", "Average rate"), ("Débit requis", "Required rate"), ("Pression moyenne", "Average pressure")],
              perf_rows, source="Measurement BL / FINAL (valeurs bord et terre), débit moyen = quantité terre ÷ temps net, débit requis = quantité ÷ temps de pompage prévu, pression = journal de pompage"),
        fields(("E · Récapitulatif des temps", "E · Time summary"), [
            F("Début de l'opération", "Operation started", dt(t0), source="PortCall.t0"), F("Fin de l'opération", "Operation completed", dt(t1), source="PortCall.t1"),
            F("Temps total à quai", "Total time alongside", _h(alongside), source="ALL_FAST → LAST_LINE"),
            F("Total des retards comptés", "Total delays counted", f"{counted_total:.2f} h", source="section C"),
            F("Temps net d'opération", "Total net operating time", f"{net_h:.2f} h" if net_h is not None else None, source="(T1 − T0) − retards comptés"),
            F("Temps de pompage prévu (h)", "Planned pump time (h)", str(call.planned_pump_hours) if call.planned_pump_hours is not None else None, source="PortCall.planned_pump_hours"),
            F("Attente en rade", "Waiting at anchorage", f"{sheet['waiting_h']:.2f} h" if sheet.get("waiting_h") is not None else None, source="reports.time_sheet : ATB − ATA"),
            F("Validité de l'annonce (facturation)", "Validity of the announcement (billing)",
              f"{call.validity_days} j — du {call.created_at:%d/%m/%Y} au {call.valid_until:%d/%m/%Y %H:%M} UTC" if call.valid_until else None,
              source="PortCall.validity_days, created_at, valid_until"),
            F("Dépassement de la validité (h)", "Overrun of the validity (h)", str(call.billing_basis()["overrun_hours"]) if call.billing_basis()["overrun_hours"] else None, source="PortCall.billing_basis()"),
            F("Temps de planche utilisé — selon charte-partie", "Laytime used — per charter-party"),
        ], note=("Le décompte du temps de planche et des surestaries suit la charte-partie et les BIMCO Laytime Definitions for Charter Parties 2013 ; la plateforme fournit les heures contradictoires, jamais le décompte.",
                 "Laytime and demurrage follow the charter-party and the BIMCO Laytime Definitions for Charter Parties 2013; the platform supplies the contradictory times, never the count.")),
        fields(("F · Exclusions, commentaires et remarques", "F · Exclusions, comments and remarks"), [
            F("Ce time sheet n'inclut pas", "This time sheet does not include", wide=True), F("Commentaires et remarques", "Comments and remarks", wide=True),
        ]),
    ]


def build_pumping_log(call: PortCall) -> list[dict]:
    """The pumping log of the call as the terminal logs print it (EXG-Q-01): one header per sheet (ship, shore),
    the hourly readings of both sides beside each other, the deviation in m³ and in %, the completion."""
    from ..measurements import compare_sides, pumping_summary

    sections = []
    summary = pumping_summary(call)
    for side, fr, en in (("SHORE", "Terre — bac récepteur / livreur", "Shore — receiving / delivering tank"), ("SHIP", "Bord — citernes", "Ship — cargo tanks")):
        for sheet in summary[side]["sheets"]:
            sections.append(fields((f"Feuille {fr}", f"Sheet {en}"), [
                F("Citerne / bac", "Tank", sheet.tank or None, source="PumpingLogSheet.tank"), F("Produit", "Product", sheet.product or None, source="PumpingLogSheet.product"),
                F("Niveau de départ (mm)", "Start dip (mm)", str(sheet.start_level_mm) if sheet.start_level_mm is not None else None, source="PumpingLogSheet.start_level_mm"),
                F("Niveau d'arrêt prévu (mm)", "Expected stop dip (mm)", str(sheet.expected_stop_level_mm) if sheet.expected_stop_level_mm is not None else None, source="PumpingLogSheet.expected_stop_level_mm"),
                F("Quantité par mètre (m³/m)", "Quantity per metre (m³/m)", str(sheet.m3_per_metre) if sheet.m3_per_metre is not None else None, source="PumpingLogSheet.m3_per_metre"),
                F("Densité (t/m³) / VCF", "Density (t/m³) / VCF", " / ".join(str(v) for v in (sheet.density, sheet.vcf) if v is not None) or None, source="PumpingLogSheet.density, vcf"),
                F("Tonnes par mètre", "Tons per metre", f"{sheet.tons_per_metre:.3f}" if sheet.tons_per_metre is not None else None, source="m³/m × densité × VCF"),
                F("Quantité prévue (m³ / t)", "Planned quantity (m³ / t)", " / ".join(str(v) for v in (sheet.planned_quantity_m3, sheet.planned_quantity_mt) if v is not None) or None, source="PumpingLogSheet.planned_quantity_m3, planned_quantity_mt"),
                F("Débit / pression attendus", "Expected rate / pressure", " / ".join(f"{v} {u}" for v, u in ((sheet.expected_rate_m3h, "m³/h"), (sheet.expected_pressure_bar, "bar")) if v is not None) or None, source="PumpingLogSheet.expected_rate_m3h, expected_pressure_bar"),
                F("Début / fin estimés", "Estimated start / completion", " → ".join(dt(v) for v in (sheet.estimated_start, sheet.estimated_completion) if v) or None, source="PumpingLogSheet.estimated_start, estimated_completion"),
                F("Niveau d'arrêt réel (mm) / volume final (m³)", "Actual stop dip (mm) / final volume (m³)", " / ".join(str(v) for v in (sheet.actual_stop_level_mm, sheet.final_volume_m3) if v is not None) or None, source="PumpingLogSheet.actual_stop_level_mm, final_volume_m3"),
                F("Ouverte par", "Opened by", sheet.opened_label, source="PumpingLogSheet.opened_label"),
            ]))
    rows = []
    for row in compare_sides(call):
        shore, ship = row["shore"], row["ship"]
        rows.append([
            f"{row['at']:%d/%m %H:%M}",
            str(shore.manifold_pressure_bar) if shore is not None and shore.manifold_pressure_bar is not None else None,
            str(shore.level_mm) if shore is not None and shore.level_mm is not None else None,
            str(shore.hourly_m3) if shore is not None and shore.hourly_m3 is not None else None,
            str(shore.cumulative_m3) if shore is not None and shore.cumulative_m3 is not None else None,
            str(shore.cumulative_mt) if shore is not None and shore.cumulative_mt is not None else None,
            str(shore.flow_rate_m3h) if shore is not None and shore.flow_rate_m3h is not None else None,
            str(ship.hourly_m3) if ship is not None and ship.hourly_m3 is not None else None,
            str(ship.cumulative_m3) if ship is not None and ship.cumulative_m3 is not None else None,
            str(row["hourly_deviation"]) if row["hourly_deviation"] is not None else None,
            (f"{row['hourly_pct']:+.3f} %" if row["hourly_pct"] is not None else None),
            (f"{row['cumulative_pct']:+.3f} %" if row["cumulative_pct"] is not None else None) + (" !" if row["exceeds"] else "") if row["cumulative_pct"] is not None or row["exceeds"] else None,
            " ; ".join(x.note for x in (shore, ship) if x is not None and x.note) or None,
        ])
    tolerance = call.port.quantity_tolerance_pct
    sections.append(table(("Relevés horaires — bord et terre", "Hourly readings — ship and shore"), [
        ("Heure", "Time"), ("Pression terre (bar)", "Shore pressure (bar)"), ("Niveau terre (mm)", "Shore dip (mm)"), ("Reçu / livré terre (m³)", "Shore moved (m³)"),
        ("Cumul terre (m³)", "Shore cumulated (m³)"), ("Cumul terre (t)", "Shore cumulated (t)"), ("Débit terre (m³/h)", "Shore rate (m³/h)"),
        ("Livré / reçu bord (m³)", "Ship moved (m³)"), ("Cumul bord (m³)", "Ship cumulated (m³)"), ("Écart (m³)", "Deviation (m³)"),
        ("Écart horaire (%)", "Hourly deviation (%)"), ("Écart cumulé (%)", "Cumulated deviation (%)"), ("Observations", "Remarks")],
        rows, blank_rows=2 if not rows else 0, source="PumpingLogEntry des deux côtés appariés par heure (measurements.compare_sides) ; écart = terre − bord",
        note=(f"Arrêter le transfert pour investigation si l'écart dépasse {tolerance} % (pratique des terminaux, tolérance du port) ; la plateforme signale, ne tranche pas.",
              f"Stop the transfer for investigation if the deviation exceeds {tolerance}% (terminal practice, the port's tolerance); the platform flags, never decides.")))
    sections.append(fields(("Totaux", "Totals"), [
        F("Cumul terre (m³ / t)", "Shore cumulated (m³ / t)", " / ".join(str(v) for v in (summary["SHORE"]["cumulative_m3"], summary["SHORE"]["cumulative_mt"]) if v is not None) or None, source="dernier relevé terre"),
        F("Cumul bord (m³ / t)", "Ship cumulated (m³ / t)", " / ".join(str(v) for v in (summary["SHIP"]["cumulative_m3"], summary["SHIP"]["cumulative_mt"]) if v is not None) or None, source="dernier relevé bord"),
        F("Pression moyenne terre / bord (bar)", "Average pressure shore / ship (bar)", " / ".join(str(v) for v in (summary["SHORE"]["average_pressure_bar"], summary["SHIP"]["average_pressure_bar"]) if v is not None) or None, source="moyenne des relevés"),
        F("Débit moyen terre / bord (m³/h)", "Average rate shore / ship (m³/h)", " / ".join(str(v) for v in (summary["SHORE"]["average_rate_m3h"], summary["SHIP"]["average_rate_m3h"]) if v is not None) or None, source="moyenne des relevés"),
    ]))
    return sections


MARK = {"YES": "✔", "NO": "✘", "NA": "n/a", "": "—"}


def build_ssscl(call: PortCall, standard: str = "SSSCL") -> list[dict]:
    """The safety checklist of the call — ISGOTT for liquid bulk, BLU Code for dry bulk, the cargo operations
    list for the others (v1.5) — pre-filled with the ticks, values and remarks of the on-line checklist of the
    call when there is one (EXG-Q-10), blank boxes otherwise."""
    from ... import checklists
    from ..checklist import current

    record = current(call)
    if record is not None and record.standard != standard:
        record = None  # a list of another standard (the call changed kind): blank boxes
    answers = record.current_answers() if record is not None else {}
    sections = [
        fields(("Identification", "Identification"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
            F("Produit", "Product", call.product or None, source="PortCall.product"), F("Opération", "Operation", _operation(call), source="PortCall.template_codes"),
            F("Date et heure d'arrivée au poste (ATB)", "Date and time of berthing (ATB)", dt(call.atb), source="PortCall.atb"),
            F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active (Organization.name)"),
            F("Liste de contrôle en ligne", "On-line checklist", (f"v{record.version} — {record.get_status_display()}" + (f", signée le {dt(record.signed_at)}" if record.signed_at else "")) if record else None, source="SafetyChecklist.version, status, signed_at"),
            F("Intervalle des vérifications répétées (h)", "Interval of the repetitive checks (h)", str(record.repeat_interval_h) if record and record.repeat_interval_h is not None else None, source="SafetyChecklist.repeat_interval_h"),
        ]),
    ]
    items = record.items if record is not None else checklists.catalogue(standard)
    columns = {"SHIP": [("Navire", "Ship")], "SHORE": [("Terre", "Shore")], "BOTH": [("Navire", "Ship"), ("Terre", "Shore")]}
    for part, fr, en in checklists.parts(standard):
        part_items = [i for i in items if i["part"] == part]
        if not part_items:
            continue
        if all(i["kind"] == "value" for i in part_items):
            sections.append(fields((fr, en), [
                F(i["fr"], i["en"], next((answers[(i["code"], s)].value for s in ("SHIP", "SHORE") if (i["code"], s) in answers and answers[(i["code"], s)].value), None),
                  wide=len(i["fr"]) > 40, source=f"SafetyCheckAnswer.value (point {i['code']})") for i in part_items]))
            continue
        side = part_items[0]["side"]
        rows = []
        for i in part_items:
            marks, remarks = [], []
            for s in checklists.sides_of(i):
                a = answers.get((i["code"], s))
                marks.append(MARK.get(a.state, "—") if a is not None and record is not None else "☐")
                if a is not None and a.remark:
                    remarks.append(f"{'navire' if s == 'SHIP' else 'terre'} : {a.remark}")
            label_fr = f"{i['code']} — {i['fr']}" + (" (R)" if i.get("repetitive") else "")
            rows.append({"fr": label_fr, "en": i["en"], "marks": marks, "remark": " ; ".join(remarks)})
        sections.append(checklist((fr, en), rows, columns=columns[side],
                                  note=(("(R) : point répété pendant les opérations à l'intervalle convenu", "(R): repeated during the operations at the agreed interval") if any(i.get("repetitive") for i in part_items) else None)))
    if record is not None:
        reps = list(record.answers.filter(repetition__gte=1).order_by("answered_at"))
        if reps:
            sections.append(table(("Vérifications répétées enregistrées", "Repetitive checks recorded"),
                                  [("Heure (UTC)", "Time (UTC)"), ("Point", "Item"), ("Côté", "Side"), ("Réponse", "Answer"), ("Par", "By"), ("Remarque", "Remark")],
                                  [[dt(a.answered_at), a.item_code, "navire / ship" if a.side == "SHIP" else "terre / shore", MARK.get(a.state, "—"), a.author_label, a.remark or None] for a in reps],
                                  source="SafetyCheckAnswer (repetition ≥ 1)"))
        signatures = list(record.signatures.order_by("signed_at"))
        if signatures:
            sections.append(table(("Signatures électroniques", "Electronic signatures"),
                                  [("Côté", "Side"), ("Signataire", "Signed by"), ("Heure (UTC)", "Time (UTC)"), ("Sceau", "Seal")],
                                  [["navire / ship" if sg.side == "SHIP" else "terre / shore", sg.signer_label, dt(sg.signed_at), sg.seal[:16] + "…"] for sg in signatures],
                                  source="SafetyChecklistSignature"))
    sections.append(text(("Déclaration", "Declaration"), [
        ("Nous, soussignés, avons vérifié ensemble, point par point, les éléments de cette liste, et nous nous sommes assurés que les réponses sont, à notre connaissance, exactes. Nous avons convenu de répéter les vérifications marquées (R) à l'intervalle indiqué.",
         "We, the undersigned, have checked the items of this list together, item by item, and have satisfied ourselves that the answers are, to the best of our knowledge, correct. We have agreed to repeat the checks marked (R) at the stated interval."),
    ], note=(f"Les parties suivent la structure de : {checklists.basis(standard)[0]} ; les points sont formulés par la plateforme, le terminal applique l'édition dont il dispose.",
             f"The parts follow the structure of: {checklists.basis(standard)[1]}; the items are worded by the platform, the terminal applies its own edition.")))
    return sections


def build_blu_checklist(call: PortCall) -> list[dict]:
    return build_ssscl(call, "BLU")


def build_cargo_checklist(call: PortCall) -> list[dict]:
    return build_ssscl(call, "CARGO")


def build_pre_transfer(call: PortCall) -> list[dict]:
    return [
        fields(("Réunion", "Meeting"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active (Organization.name)"),
            F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"), F("Date et heure", "Date and time"),
            F("Produit", "Product", call.product or None, source="PortCall.product"), F("Quantité", "Quantity", f"{call.quantity} {call.quantity_unit}" if call.quantity else None, source="PortCall.quantity, PortCall.quantity_unit"),
            F("Participants (nom, fonction)", "Attendees (name, capacity)", wide=True),
        ]),
        fields(("Paramètres de transfert convenus", "Agreed transfer parameters"), [
            F("Débit initial (m³/h)", "Initial rate (m³/h)"), F("Débit maximal (m³/h)", "Maximum rate (m³/h)"),
            F("Débit de fin / topping-off (m³/h)", "Topping-off rate (m³/h)"), F("Pression maximale au collecteur (bar)", "Maximum manifold pressure (bar)"),
            F("Température maximale (°C)", "Maximum temperature (°C)"), F("Nombre de lignes / bras", "Number of lines / arms"),
            F("Séquence des citernes bord", "Ship tank sequence", wide=True), F("Séquence des bacs terre", "Shore tank sequence", wide=True),
            F("Ballastage / déballastage simultané", "Simultaneous ballast operations"), F("Échantillonnage (points, moments)", "Sampling (points, times)"),
        ]),
        fields(("Communication et urgence", "Communication and emergency"), [
            F("Canal VHF principal / de secours", "Primary / backup VHF channel"), F("Signal d'arrêt d'urgence", "Emergency stop signal"),
            F("Temps de fermeture des vannes (s)", "Valve closure time (s)"), F("Procédure ESD testée à (heure)", "ESD tested at (time)", _mt(call, "ESD_TEST"), source="jalon ESD_TEST.declared_at"),
            F("Limites d'arrêt : vent (nd), houle (m), foudre, visibilité", "Stop limits: wind (kn), swell (m), lightning, visibility", wide=True),
            F("Personnes de permanence (navire / terminal)", "Persons on duty (ship / terminal)", wide=True),
        ]),
        text(("Accord", "Agreement"), [
            ("Les parties conviennent des paramètres ci-dessus. Toute modification en cours de transfert est convenue entre les responsables de permanence et consignée au registre (jalon ou échange).",
             "The parties agree on the parameters above. Any change during the transfer is agreed between the persons on duty and recorded in the registry (milestone or exchange)."),
        ]),
    ]


def build_ullage(call: PortCall) -> list[dict]:
    measures = []
    for m in call.measurements.all().order_by("created_at"):
        values = m.current_values()
        measures.append([m.get_kind_display(), m.product or call.product or "—", m.unit,
                         *[f"{values[p].value}" + (f" @ {values[p].temperature_c} °C" if values[p].temperature_c is not None else "")
                           + (f", d {values[p].density}" if values[p].density is not None else "") if p in values else None
                           for p in ("SHIP", "SHORE", "SURVEYOR")]])
    return [
        fields(("Jaugeage", "Gauging"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
            F("Produit", "Product", call.product or None, source="PortCall.product"), F("Nature", "Kind", "initial / initial ☐   final / final ☐   OBQ ☐   ROB ☐"),
            F("Date et heure du jaugeage", "Date and time of gauging"), F("Méthode (ruban UTI, radar, ATG…)", "Method (UTI tape, radar, ATG…)"),
            F("Tirant d'eau AV / AR (m)", "Draft fwd / aft (m)"), F("Gîte / assiette", "List / trim"),
            F("Inspecteur", "Surveyor", _party(call, "INS"), source="CallParty INS active (Organization.name)"), F("Facteur d'expérience navire (VEF)", "Vessel experience factor (VEF)"),
        ]),
        table(("Citernes", "Tanks"), [("Citerne", "Tank"), ("Creux / innage (m)", "Ullage / innage (m)"), ("Température (°C)", "Temperature (°C)"),
                                       ("Eau libre (m)", "Free water (m)"), ("Densité @15 °C / API", "Density @15 °C / API"),
                                       ("TOV (m³)", "TOV (m³)"), ("GOV (m³)", "GOV (m³)"), ("VCF", "VCF"), ("GSV (m³)", "GSV (m³)"),
                                       ("Masse (t)", "Weight (t)")], [], blank_rows=14,
              note=("Calculs selon API MPMS ch. 11 et 12 (tables ASTM D1250) ; totaux reportés dans la section des quantités.",
                    "Calculations under API MPMS ch. 11 and 12 (ASTM D1250 tables); totals carried to the quantities section.")),
        table(("Quantités enregistrées au registre", "Quantities recorded in the registry"),
              [("Mesure", "Measurement"), ("Produit", "Product"), ("Unité", "Unit"), ("Bord", "Ship"), ("Terre", "Shore"), ("Inspecteur", "Surveyor")],
              measures, blank_rows=1, source="Measurement (kind, product, unit) et MeasurementValue courante par partie (value, temperature_c, density)"),
        fields(("Totaux", "Totals"), [
            F("TOV total (m³)", "Total TOV (m³)"), F("Eau libre totale (m³)", "Total free water (m³)"), F("GSV total (m³ @15 °C)", "Total GSV (m³ @15 °C)"),
            F("Masse totale (t air)", "Total weight (t in air)"), F("Écart bord/terre (%)", "Ship/shore difference (%)"), F("Observations", "Remarks", wide=True),
        ]),
    ]


def build_hose_record(call: PortCall) -> list[dict]:
    rows = []
    con, dis = _m(call, "HOSES_CONNECTED"), _m(call, "HOSES_DISCONNECTED")
    rows.append(["1", None, None, None, dt(con.declared_at) if con else None, dt(dis.declared_at) if dis else None, None])
    return [
        fields(("Raccordement", "Connection"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
            F("Produit", "Product", call.product or None, source="PortCall.product"), F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active (Organization.name)"),
            F("Type : flexibles ☐ bras de chargement ☐", "Type: hoses ☐ loading arms ☐"), F("Réduction au collecteur", "Manifold reducer"),
        ]),
        table(("Lignes", "Lines"), [("N°", "No."), ("Identifiant flexible / bras", "Hose / arm id"), ("Diamètre (po)", "Size (in)"),
                                     ("Dernier essai de pression (date, bar)", "Last pressure test (date, bar)"), ("Connecté le", "Connected at"),
                                     ("Déconnecté le", "Disconnected at"), ("Vidangé / purgé", "Drained / purged")], rows, blank_rows=5,
              source="jalons HOSES_CONNECTED et HOSES_DISCONNECTED (declared_at) pour la ligne 1"),
        fields(("Contrôles", "Checks"), [
            F("Joints et boulonnage vérifiés", "Gaskets and bolting checked"), F("Mise à la masse / joint isolant", "Bonding / insulating flange"),
            F("Essai d'étanchéité en pression (bar, durée)", "Leak test under pressure (bar, duration)"), F("Supports et rayon de courbure conformes", "Supports and bend radius compliant"),
            F("Observations", "Remarks", wide=True),
        ]),
    ]


def build_protest(call: PortCall) -> list[dict]:
    return [
        fields(("Expéditeur et destinataire", "From and to"), [
            F("De (organisation, rôle, nom)", "From (organisation, role, name)", wide=True), F("À (organisation, rôle)", "To (organisation, role)", wide=True),
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Escale", "Call", call.reference, source="PortCall.reference"),
            F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"), F("Date", "Date"),
        ]),
        text(("Objet et faits", "Subject and facts"), [
            ("Objet : ______________________________________________", "Subject: ______________________________________________"),
            ("Je soussigné proteste par la présente contre les faits suivants, constatés lors de l'escale référencée, et me réserve, au nom de mes mandants, tous droits de recours pour les pertes, retards et dommages qui en résulteraient :",
             "I, the undersigned, hereby protest against the following facts, observed during the referenced call, and reserve, on behalf of my principals, all rights of recourse for any loss, delay or damage arising therefrom:"),
            ("Faits (dates, heures, références des jalons du registre) : ________________________________________________________________",
             "Facts (dates, times, references of the registry milestones): ________________________________________________________________"),
            ("La présente lettre ne constitue ni une reconnaissance de responsabilité ni une renonciation à un droit.",
             "This letter is neither an admission of liability nor a waiver of any right."),
        ]),
        fields(("Réception", "Receipt"), [F("Reçue le (date, heure)", "Received on (date, time)"), F("Par (nom, fonction)", "By (name, capacity)"),
                                           F("Observations du destinataire (« reçu sous réserve »…)", "Recipient's remarks (“received under protest”…)", wide=True)]),
    ]


def build_fal(call: PortCall) -> list[dict]:
    v = call.vessel
    return [
        fields(("FAL 1 — Déclaration générale", "FAL form 1 — General declaration"), [
            F("Nom et type du navire", "Name and type of ship", f"{v.name} — {v.vessel_type or '—'}", source="Vessel.name, Vessel.vessel_type"), F("Numéro OMI", "IMO number", v.imo, source="Vessel.imo"),
            F("Indicatif d'appel", "Call sign", v.call_sign or None, source="Vessel.call_sign"), F("Numéro du voyage", "Voyage number", call.voyage_number or None, source="PortCall.voyage_number"),
            F("Port d'arrivée / de départ", "Port of arrival / departure", f"{call.port.name} ({call.port.code})", source="Port.name, Port.code"),
            F("Date et heure d'arrivée / de départ", "Date and time of arrival / departure", dt(call.ata) or dt(call.eta), source="PortCall.ata, sinon PortCall.eta"),
            F("Pavillon", "Flag State of ship", v.flag or None, source="Vessel.flag"), F("Nom du capitaine", "Name of master"),
            F("Dernier port d'escale / prochain port", "Last port of call / next port of call", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, PortCall.next_port"),
            F("Certificat d'immatriculation (port, date, numéro)", "Certificate of registry (port, date, number)"),
            F("Jauge brute / nette", "Gross / net tonnage"), F("Position du navire dans le port", "Position of the ship in the port", _where(call), source="PortCall.berth ou zone de l'étape en cours"),
            F("Brève description du voyage", "Brief particulars of voyage", wide=True),
            F("Brève description de la cargaison", "Brief description of the cargo", f"{call.product} — {call.quantity} {call.quantity_unit}" if call.product else None, wide=True, source="PortCall.product, quantity, quantity_unit"),
            F("Nombre de membres d'équipage / passagers", "Number of crew / passengers"), F("Observations", "Remarks", wide=True),
            F("Agent du navire (nom, coordonnées)", "Ship's agent (name, contact details)", str(call.agency), wide=True, source="PortCall.agency (Organization.name)"),
        ], note=("Documents joints : FAL 2 déclaration de cargaison, FAL 3 provisions de bord, FAL 4 effets de l'équipage, FAL 5 liste d'équipage, FAL 6 liste des passagers, FAL 7 marchandises dangereuses, déclaration maritime de santé.",
                 "Attached documents: FAL 2 cargo declaration, FAL 3 ship's stores, FAL 4 crew's effects, FAL 5 crew list, FAL 6 passenger list, FAL 7 dangerous goods manifest, maritime declaration of health.")),
        table(("FAL 5 — Liste d'équipage", "FAL form 5 — Crew list"), [("N°", "No."), ("Nom de famille", "Family name"), ("Prénoms", "Given names"),
                                                                         ("Fonction", "Rank or rating"), ("Nationalité", "Nationality"),
                                                                         ("Date et lieu de naissance", "Date and place of birth"),
                                                                         ("Pièce d'identité (nature, numéro)", "Identity document (nature, number)")],
              [], blank_rows=12,
              note=("Les formulaires FAL sont déposés au guichet unique de l'État ; la plateforme les prépare et conserve la preuve du dépôt (document « preuve de dépôt FAL »), elle ne les transmet pas (règle d'or : aucune formalité FAL reproduite).",
                    "FAL forms are filed with the State's single window; the platform prepares them and keeps the proof of filing (document “proof of FAL filing”), it does not transmit them (golden rule: no FAL formality reproduced).")),
    ]


def build_dos(call: PortCall) -> list[dict]:
    v = call.vessel
    activities = [
        ("Exécution de toutes les tâches liées à la sûreté", "Ensuring the performance of all security duties"),
        ("Surveillance des zones d'accès restreint", "Monitoring restricted areas to ensure that only authorized personnel have access"),
        ("Contrôle de l'accès à l'installation portuaire", "Controlling access to the port facility"),
        ("Contrôle de l'accès au navire", "Controlling access to the ship"),
        ("Surveillance de l'installation portuaire, y compris les zones d'accostage et les abords du navire", "Monitoring of the port facility, including berthing areas and areas surrounding the ship"),
        ("Surveillance du navire, y compris les zones d'accostage et les abords du navire", "Monitoring of the ship, including berthing areas and areas surrounding the ship"),
        ("Manutention de la cargaison", "Handling of cargo"),
        ("Livraison des provisions de bord", "Delivery of ship's stores"),
        ("Manutention des bagages non accompagnés", "Handling unaccompanied baggage"),
        ("Contrôle de l'embarquement des personnes et de leurs effets", "Controlling the embarkation of persons and their effects"),
        ("Disponibilité des systèmes de communication de sûreté entre le navire et l'installation portuaire", "Ensuring that security communication is readily available between the ship and port facility"),
    ]
    return [
        fields(("Parties", "Parties"), [
            F("Nom du navire", "Name of ship", v.name, source="Vessel.name"), F("Port d'immatriculation", "Port of registry"), F("Numéro OMI", "IMO number", v.imo, source="Vessel.imo"),
            F("Installation portuaire", "Name of port facility", f"{call.port.name} — {_where(call)}", source="Port.name, poste ou zone de l'étape en cours"),
            F("Validité : du / au", "Valid from / to"), F("Activités couvertes", "Activities covered", call.product or None, source="PortCall.product"),
            F("Niveau de sûreté du navire", "Security level for the ship"), F("Niveau de sûreté de l'installation", "Security level for the port facility"),
        ]),
        checklist(("Responsabilités convenues (ISPS, partie B, appendice 1)", "Agreed responsibilities (ISPS Code, part B, appendix 1)"), activities,
                  columns=[("Installation", "Port facility"), ("Navire", "Ship")],
                  note=("Les signataires certifient que les mesures et dispositions de sûreté de l'installation portuaire et du navire pendant les activités spécifiées satisfont aux dispositions du chapitre XI-2 et de la partie A du Code ISPS, et seront appliquées conformément aux dispositions déjà prévues dans leur plan approuvé ou aux arrangements spécifiques convenus et annexés.",
                        "The signatories certify that security measures and arrangements for both the port facility and the ship during the specified activities meet the provisions of chapter XI-2 and part A of the ISPS Code that will be implemented in accordance with the provisions already stipulated in their approved plan or the specific arrangements agreed to and set out in the attached annex.")),
        fields(("Contacts de sûreté (24 h)", "Security contacts (24 h)"), [
            F("Agent de sûreté de l'installation (PFSO)", "Port facility security officer (PFSO)", wide=True),
            F("Agent de sûreté du navire (SSO)", "Ship security officer (SSO)", wide=True),
        ]),
    ]


def build_mdh(call: PortCall) -> list[dict]:
    v = call.vessel
    questions = [
        ("Une personne est-elle décédée à bord pendant le voyage, autrement que par accident ?", "Has any person died on board during the voyage otherwise than as a result of accident?"),
        ("Y a-t-il à bord, ou y a-t-il eu pendant le voyage international, un cas de maladie dont vous soupçonnez qu'elle est de nature infectieuse ?", "Is there on board or has there been during the international voyage any case of disease which you suspect to be of an infectious nature?"),
        ("Le nombre total de passagers malades pendant le voyage a-t-il été supérieur à la normale ?", "Has the total number of ill passengers during the voyage been greater than normal/expected?"),
        ("Y a-t-il actuellement des malades à bord ?", "Is there any ill person on board now?"),
        ("Un médecin a-t-il été consulté ?", "Was a medical practitioner consulted?"),
        ("Avez-vous connaissance d'une situation à bord susceptible d'entraîner une infection ou la propagation d'une maladie ?", "Are you aware of any condition on board which may lead to infection or spread of disease?"),
        ("Une mesure sanitaire (quarantaine, isolement, désinfection, décontamination) a-t-elle été appliquée à bord ?", "Has any sanitary measure (quarantine, isolation, disinfection or decontamination) been applied on board?"),
        ("Des passagers clandestins ont-ils été trouvés à bord ?", "Have any stowaways been found on board?"),
        ("Y a-t-il un animal malade à bord ?", "Is there a sick animal or pet on board?"),
    ]
    return [
        fields(("Navire", "Ship"), [
            F("Nom du navire", "Name of ship", v.name, source="Vessel.name"), F("Numéro OMI", "IMO number", v.imo, source="Vessel.imo"), F("Pavillon", "Flag", v.flag or None, source="Vessel.flag"),
            F("Port d'arrivée", "Port of arrival", call.port.name, source="Port.name"), F("Date", "Date", dt(call.ata) or dt(call.eta), source="PortCall.ata, sinon PortCall.eta"),
            F("Venant de / allant à", "From / to", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, PortCall.next_port"),
            F("Nom du capitaine", "Master's name"), F("Jauge brute", "Gross tonnage"),
            F("Certificat de contrôle sanitaire / d'exemption valide (lieu, date)", "Valid sanitation control / exemption certificate (place, date)", wide=True),
            F("Nombre de membres d'équipage / de passagers", "Number of crew / passengers"),
            F("Ports d'escale depuis le début du voyage, avec dates", "Ports of call since the start of the voyage, with dates", wide=True),
        ]),
        checklist(("Questions sanitaires (répondre oui ou non)", "Health questions (answer yes or no)"), questions,
                  columns=[("Oui", "Yes"), ("Non", "No")]),
        text(("Déclaration", "Declaration"), [
            ("Je déclare par la présente que les renseignements et réponses contenus dans cette déclaration de santé (y compris le tableau en annexe) sont, à ma connaissance, exacts et conformes à la vérité.",
             "I hereby declare that the particulars and answers to the questions given in this Declaration of Health (including the schedule) are true and correct to the best of my knowledge and belief."),
        ], note=("Modèle de l'annexe 8 du Règlement sanitaire international (2005) de l'OMS. En cas de réponse « oui », joindre le tableau des cas.",
                 "Model of annex 8 of the WHO International Health Regulations (2005). If any answer is “yes”, attach the schedule of cases.")),
    ]


def build_waste(call: PortCall) -> list[dict]:
    v = call.vessel
    categories = [
        ("Annexe I — eaux de cale huileuses", "Annex I — oily bilge water"), ("Annexe I — résidus d'hydrocarbures (boues)", "Annex I — oily residues (sludge)"),
        ("Annexe I — eaux de lavage de citernes huileuses", "Annex I — oily tank washings"), ("Annexe I — eau de ballast sale", "Annex I — dirty ballast water"),
        ("Annexe II — résidus et mélanges de substances liquides nocives", "Annex II — NLS residues and mixtures"),
        ("Annexe IV — eaux usées", "Annex IV — sewage"),
        ("Annexe V — plastiques", "Annex V — plastics"), ("Annexe V — déchets alimentaires", "Annex V — food wastes"),
        ("Annexe V — déchets domestiques", "Annex V — domestic wastes"), ("Annexe V — huile de cuisson", "Annex V — cooking oil"),
        ("Annexe V — cendres d'incinérateur", "Annex V — incinerator ashes"), ("Annexe V — déchets d'exploitation", "Annex V — operational wastes"),
        ("Annexe V — résidus de cargaison (HME / non HME)", "Annex V — cargo residues (HME / non-HME)"), ("Annexe V — déchets électroniques", "Annex V — e-waste"),
        ("Annexe VI — substances appauvrissant l'ozone", "Annex VI — ozone-depleting substances"), ("Annexe VI — résidus d'épuration des gaz", "Annex VI — exhaust gas cleaning residues"),
    ]
    return [
        fields(("Navire et escale", "Ship and call"), [
            F("Nom du navire", "Name of ship", v.name, source="Vessel.name"), F("Numéro OMI", "IMO number", v.imo, source="Vessel.imo"), F("Pavillon", "Flag State", v.flag or None, source="Vessel.flag"),
            F("Heure d'arrivée prévue", "Estimated time of arrival", dt(call.eta), source="PortCall.eta"), F("Heure de départ prévue", "Estimated time of departure", dt(call.etd), source="PortCall.etd"),
            F("Dernier port d'escale / prochain port", "Last port of call / next port", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, PortCall.next_port"),
            F("Dernier port et date de dépôt des déchets", "Last port and date of waste delivery"), F("Agent", "Agent", str(call.agency), source="PortCall.agency (Organization.name)"),
            F("Dépôt : tout ☐ une partie ☐ aucun ☐", "Delivering: all ☐ some ☐ none ☐"),
        ]),
        table(("Type et quantité de déchets", "Type and amount of waste"),
              [("Type", "Type"), ("À déposer (m³)", "To be delivered (m³)"), ("Capacité de stockage max. (m³)", "Max. storage capacity (m³)"),
               ("Quantité conservée à bord (m³)", "Amount retained on board (m³)"), ("Port de dépôt du reste", "Port of delivery of remaining waste"),
               ("Quantité estimée produite d'ici le prochain port (m³)", "Estimated amount generated before next port (m³)")],
              [[f"{fr} / {en}", None, None, None, None, None] for fr, en in categories],
              note=("Modèle de l'appendice 1 de la circulaire OMI MEPC.1/Circ.834/Rev.1 ; à transmettre au moins 24 h avant l'arrivée au prestataire et à l'autorité portuaire.",
                    "Model of appendix 1 of IMO circular MEPC.1/Circ.834/Rev.1; to be sent at least 24 h before arrival to the provider and the port authority.")),
        text(("Confirmation", "Confirmation"), [
            ("Je confirme que les renseignements ci-dessus sont exacts et qu'il existe à bord une capacité de stockage suffisante pour conserver tous les déchets produits entre la notification et le prochain port où ils seront déposés.",
             "I confirm that the above details are accurate and correct and that there is sufficient dedicated capacity on board to store all waste generated between notification and the next port at which waste will be delivered."),
        ]),
    ]


def build_sts(call: PortCall) -> list[dict]:
    partner = call.linked_call
    return [
        fields(("Opération STS", "STS operation"), [
            F("Navire (ce dossier)", "Vessel (this file)", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"),
            F("Navire partenaire", "Partner vessel", f"{partner.vessel.name} — IMO {partner.vessel.imo} ({partner.reference})" if partner else None, source="PortCall.linked_call → Vessel.name, imo, PortCall.reference"),
            F("Zone STS", "STS area", _where(call), source="PortCall.berth ou zone de l'étape en cours"), F("Produit / quantité", "Product / quantity", f"{call.product or '—'} — {call.quantity or '—'} {call.quantity_unit}", source="PortCall.product, quantity, quantity_unit"),
            F("Prestataire STS / POAC", "STS provider / POAC", _party(call, "PRE"), source="CallParty PRE active (Organization.name)"), F("Mouillage ou en route", "At anchor or under way"),
            F("Limites météo convenues (vent, houle)", "Agreed weather limits (wind, swell)"), F("Défenses et flexibles (type, certificats)", "Fenders and hoses (type, certificates)", wide=True),
        ]),
        checklist(("Liste 1 — Avant l'opération (compatibilité, plan, notifications)", "Checklist 1 — Before operations (compatibility, plan, notifications)"), [
            ("Compatibilité des navires vérifiée (dimensions, francs-bords, collecteurs, amarrage)", "Vessel compatibility verified (dimensions, freeboards, manifolds, mooring)"),
            ("Plan d'opération STS (JPO) établi, approuvé et à bord des deux navires", "STS operations plan (JPO) prepared, approved and on board both vessels"),
            ("Notification à l'État côtier et à la capitainerie faite dans les délais", "Coastal State and harbour master notified in time"),
            ("Zone, mouillage ou route convenus ; limites météo et critères d'abandon convenus", "Area, anchorage or route agreed; weather limits and abort criteria agreed"),
        ], columns=[("Navire", "Ship"), ("POAC", "POAC")]),
        checklist(("Liste 2 — Avant la mise à couple", "Checklist 2 — Before run-in and mooring"), [
            ("Défenses primaires et secondaires en place et gonflées ; remorques de secours prêtes", "Primary and secondary fenders rigged and inflated; emergency towing-off pennants ready"),
            ("Communication entre navires et avec le POAC établie et testée", "Ship-to-ship and POAC communication established and tested"),
            ("Équipages briefés ; postes d'amarrage armés ; éclairage de nuit prêt", "Crews briefed; mooring stations manned; night lighting ready"),
            ("Ballast et assiette adaptés ; francs-bords compatibles", "Ballast and trim suitable; freeboards compatible"),
        ], columns=[("Navire", "Ship"), ("POAC", "POAC")]),
        checklist(("Liste 3 — Avant le transfert", "Checklist 3 — Before cargo transfer"), [
            ("Flexibles raccordés, supportés, testés ; collecteurs étanches", "Hoses connected, supported, tested; manifolds tight"),
            ("Débits, pression, séquence des citernes et procédure d'arrêt d'urgence convenus", "Rates, pressure, tank sequence and emergency stop procedure agreed"),
            ("Veille et communication continues ; moyens antipollution prêts", "Continuous watch and communication; pollution response equipment ready"),
            ("Gaz inerte, dégagements de citernes et sources d'ignition contrôlés", "Inert gas, tank venting and ignition sources under control"),
        ], columns=[("Navire", "Ship"), ("POAC", "POAC")]),
        checklist(("Liste 5 — Après le transfert", "Checklist 5 — After transfer"), [
            ("Flexibles vidangés, purgés et déconnectés ; collecteurs obturés", "Hoses drained, purged and disconnected; manifolds blanked"),
            ("Quantités constatées et documents échangés", "Quantities agreed and documents exchanged"),
            ("Amarres larguées dans l'ordre convenu ; défenses récupérées", "Moorings released in the agreed order; fenders recovered"),
        ], columns=[("Navire", "Ship"), ("POAC", "POAC")],
            note=("Structure des listes de contrôle du Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF/ICS/CDI/SIGTTO, 2013) ; le prestataire STS applique l'édition sous licence dont il dispose.",
                  "Structure of the checklists of the Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF/ICS/CDI/SIGTTO, 2013); the STS provider applies its licensed edition.")),
    ]


def build_pilot_card(call: PortCall) -> list[dict]:
    v = call.vessel
    return [
        fields(("Navire", "Ship's particulars"), [
            F("Nom du navire", "Ship's name", v.name, source="Vessel.name"), F("Indicatif", "Call sign", v.call_sign or None, source="Vessel.call_sign"), F("Date", "Date", dt(call.ata) or dt(call.eta), source="PortCall.ata, sinon PortCall.eta"),
            F("Déplacement (t)", "Displacement (t)"), F("Port en lourd (t)", "Deadweight (t)", str(v.dwt) if v.dwt else None, source="Vessel.dwt"),
            F("Année de construction", "Year built", str(v.built_year) if v.built_year else None, source="Vessel.built_year"),
            F("Longueur hors tout (m)", "Length overall (m)", str(v.loa_m) if v.loa_m else None, source="Vessel.loa_m"), F("Largeur (m)", "Breadth (m)", str(v.beam_m) if v.beam_m else None, source="Vessel.beam_m"),
            F("Tirant d'eau AV / AR (m)", "Draft fwd / aft (m)"), F("Tirant d'air (m)", "Air draft (m)"),
            F("Type d'ancre ; chaîne (maillons)", "Anchor type; chain (shackles)"), F("Propulseur d'étrave / arrière (kW)", "Bow / stern thruster (kW)"),
        ]),
        table(("Propulsion et vitesses de manœuvre", "Propulsion and manoeuvring speeds"),
              [("Allure", "Order"), ("Tours/min", "RPM"), ("Vitesse chargé (nd)", "Speed loaded (kn)"), ("Vitesse lège (nd)", "Speed ballast (kn)")],
              [["Avant toute / Full ahead", None, None, None], ["Avant demi / Half ahead", None, None, None], ["Avant lente / Slow ahead", None, None, None],
               ["Avant très lente / Dead slow ahead", None, None, None], ["Arrière très lente / Dead slow astern", None, None, None],
               ["Arrière lente / Slow astern", None, None, None], ["Arrière demi / Half astern", None, None, None], ["Arrière toute / Full astern", None, None, None]]),
        fields(("Appareil à gouverner et équipements", "Steering and equipment"), [
            F("Type de machine ; puissance maximale (kW)", "Engine type; maximum power (kW)"), F("Hélice (pas fixe / variable, sens de rotation)", "Propeller (fixed / CPP, direction of rotation)"),
            F("Angle maximal de barre ; temps bâbord-tribord (s)", "Maximum rudder angle; hard-over to hard-over time (s)"), F("Délai machine : arrêt → arrière toute (s)", "Engine: stop to full astern (s)"),
            F("Équipements vérifiés : ancres, indicateur de barre, gyrocompas, radars, VHF, loch, écho-sondeur, AIS, corne", "Equipment checked: anchors, rudder indicator, gyro, radars, VHF, speed log, echo sounder, AIS, whistle", wide=True),
            F("Particularités de manœuvre", "Manoeuvring peculiarities", wide=True),
        ], note=("Modèle de la fiche pilote de l'annexe 2 de la résolution OMI A.960(23) ; l'échange d'informations capitaine-pilote se fait à l'embarquement.",
                 "Model of the pilot card of annex 2 to IMO resolution A.960(23); the master-pilot exchange takes place on boarding.")),
    ]


def build_bdn(call: PortCall) -> list[dict]:
    v = call.vessel
    return [
        fields(("Livraison de soutes", "Bunker delivery"), [
            F("Nom et numéro OMI du navire receveur", "Name and IMO number of receiving ship", f"{v.name} — IMO {v.imo}", source="Vessel.name, Vessel.imo"),
            F("Port", "Port", call.port.name, source="Port.name"), F("Date de début de la livraison", "Date of commencement of delivery"),
            F("Fournisseur (nom, adresse, téléphone)", "Supplier (name, address, telephone)", _party(call, "PRE"), wide=True, source="CallParty PRE active (Organization.name)"),
            F("Produit(s)", "Product name(s)"), F("Quantité (tonnes métriques)", "Quantity (metric tons)"),
            F("Masse volumique à 15 °C (kg/m³)", "Density at 15 °C (kg/m³)"), F("Teneur en soufre (% m/m)", "Sulphur content (% m/m)"),
            F("Échantillon MARPOL (numéro du scellé)", "MARPOL sample (seal number)"),
        ]),
        text(("Déclaration du fournisseur", "Supplier's declaration"), [
            ("Le fournisseur déclare que le fioul livré est conforme à la règle 18.3 de l'annexe VI de MARPOL et que sa teneur en soufre ne dépasse pas la limite applicable (règle 14.1 ou 14.4) ou, pour un navire équipé d'un système équivalent, la valeur indiquée ci-dessus.",
             "The supplier declares that the fuel oil supplied is in conformity with regulation 18.3 of MARPOL Annex VI and that its sulphur content does not exceed the applicable limit (regulation 14.1 or 14.4) or, for a ship fitted with an equivalent arrangement, the value stated above."),
        ], note=("Modèle de l'appendice V de l'annexe VI de MARPOL ; conservé à bord trois ans.",
                 "Model of appendix V to MARPOL Annex VI; kept on board for three years.")),
    ]




_register(Form("NOR", "NOR", ("Notice de disponibilité", "Notice of readiness"),
               ("Pratique des chartes-parties — BIMCO Laytime Definitions for Charter Parties 2013", "Charter-party practice — BIMCO Laytime Definitions for Charter Parties 2013"),
               frozenset({"AGE", "NAV"}), [("NAV", ("Capitaine", "Master")), ("TER", ("Terminal — réception", "Terminal — receipt")), ("COM", ("Affréteur / réceptionnaire", "Charterer / receiver"))],
               build_nor,
               family="NAV", answers=("M0:23",), purpose=("La notice de disponibilité remise par le capitaine aux destinataires de la charte-partie ; l'accusé de réception du terminal et de l'affréteur.", "The master's notice of readiness to the charter-party recipients; the terminal's and charterer's acknowledgement.")))
_register(Form("TIME_SHEET", "TIME_SHEET", ("Time sheet", "Time sheet"),
               ("Structure des time sheets des terminaux (analyse des surestaries) — BIMCO Laytime Definitions for Charter Parties 2013", "Structure of the terminal vessel time sheets (demurrage analysis) — BIMCO Laytime Definitions for Charter Parties 2013"),
               frozenset({"AGE", "TER", "NAV"}), [("NAV", ("Pour le navire", "For ship")), ("INS", ("Pour l'inspecteur", "For surveyor")), ("AGE", ("Pour l'agent", "For agent")), ("TER", ("Pour le terminal", "For shore"))],
               build_time_sheet, landscape=True,
               family="AGE", answers=("M0:37",), purpose=("Le time sheet de l'escale lu par toutes les parties : activités standard, arrêts et retards comptés, quantités et performance, récapitulatif des temps.", "The call's time sheet read by every party: standard activities, stoppages and delays counted, quantities and performance, time summary.")))
_register(Form("PUMPING_LOG", "PUMPING_LOG", ("Journal de pompage", "Pumping log"),
               ("Structure des journaux de pompage des terminaux ; ISGOTT, 6e édition (surveillance du transfert)", "Structure of the terminal pumping logs; ISGOTT, 6th edition (monitoring of the transfer)"),
               frozenset({"TER", "NAV"}), [("TER", ("Pour le terminal", "For shore")), ("NAV", ("Pour le navire", "For ship")), ("INS", ("Pour l'inspecteur", "For surveyor"))],
               build_pumping_log, landscape=True,
               family="TER", cargo_kinds=frozenset({"LIQUID"}), answers=("M1:1.11", "M2:2.11"), purpose=("Le journal de pompage tenu par le navire et par le terminal, relevé par relevé, avec l'écart terre − bord et le seuil d'arrêt pour investigation.", "The pumping log kept by the ship and by the terminal, reading by reading, with the shore − ship deviation and the stop-for-investigation threshold.")))
_register(Form("SSSCL", "SSSCL", ("Liste de contrôle navire / terre", "Ship/shore safety checklist"),
               ("Structure de l'ISGOTT, 6e édition (OCIMF / ICS / IAPH), chapitre 25", "Structure of ISGOTT, 6th edition (OCIMF / ICS / IAPH), chapter 25"),
               frozenset({"TER", "NAV"}), [("NAV", ("Pour le navire", "For the ship")), ("TER", ("Pour le terminal", "For the terminal"))], build_ssscl,
               family="TER", answers=("M0:28",), cargo_kinds=frozenset({"LIQUID"}),
               purpose=("La liste de contrôle navire/terre signée conjointement avant le transfert et répétée pendant.", "The ship/shore safety checklist signed jointly before the transfer and repeated during it.")))
_register(Form("BLU_CHECKLIST", "BLU_CHECKLIST", ("Liste de contrôle navire / terre — vrac sec", "Ship/shore safety checklist — dry bulk"),
               ("Code BLU de l'OMI (résolution A.862(20)), appendice 3 ; Code IMSBC", "IMO BLU Code (resolution A.862(20)), appendix 3; IMSBC Code"),
               frozenset({"TER", "NAV"}), [("NAV", ("Pour le navire", "For the ship")), ("TER", ("Pour le terminal", "For the terminal"))], build_blu_checklist,
               family="TER", answers=("M0:28",), cargo_kinds=frozenset({"DRY"}),
               purpose=("La liste de contrôle navire/terre du Code BLU, signée avant le chargement ou le déchargement d'un vraquier et répétée pendant.", "The BLU Code ship/shore safety checklist, signed before loading or unloading a bulk carrier and repeated during it.")))
_register(Form("CARGO_SAFETY_CHECKLIST", "CARGO_SAFETY_CHECKLIST", ("Liste de contrôle sécurité des opérations de manutention", "Cargo operations safety checklist"),
               ("Recueil de directives pratiques du BIT « Sécurité et santé dans les ports » ; pratique des terminaux à conteneurs, divers et rouliers", "ILO code of practice “Safety and health in ports”; container, general cargo and ro-ro terminal practice"),
               frozenset({"TER", "NAV"}), [("NAV", ("Pour le navire", "For the ship")), ("TER", ("Pour le terminal", "For the terminal"))], build_cargo_checklist,
               family="TER", answers=("M0:28",), cargo_kinds=frozenset({"CONTAINER", "GENERAL", "RORO", "OTHER"}),
               purpose=("La liste de contrôle de sécurité des opérations de manutention, signée par le navire et le terminal avant les opérations et répétée pendant.", "The cargo operations safety checklist, signed by the ship and the terminal before the operations and repeated during them.")))
_register(Form("PRE_TRANSFER", "PRE_TRANSFER_MINUTES", ("Accord de transfert — réunion pré-transfert", "Transfer agreement — pre-transfer meeting"),
               ("ISGOTT, 6e édition, réunion pré-transfert et accords écrits", "ISGOTT, 6th edition, pre-transfer meeting and written agreements"),
               frozenset({"TER", "NAV"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship")), ("INS", ("Inspecteur", "Surveyor"))], build_pre_transfer,
               family="TER", cargo_kinds=frozenset({"LIQUID"}), answers=("M0:27",), purpose=("Le compte rendu de la réunion pré-transfert : paramètres, communication, urgence, accord écrit.", "The minutes of the pre-transfer meeting: parameters, communication, emergency, written agreement.")))
_register(Form("ULLAGE", "ULLAGE_REPORT", ("Rapport de jaugeage", "Ullage / sounding report"),
               ("API MPMS chapitre 17.1 et 17.2 (inspection des cargaisons maritimes) ; EI HM 28 ; tables ASTM D1250", "API MPMS chapters 17.1 and 17.2 (marine cargo inspection); EI HM 28; ASTM D1250 tables"),
               frozenset({"INS", "NAV", "TER"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Officier de quart / chef de cargaison", "Chief officer")), ("TER", ("Terminal", "Terminal"))], build_ullage, landscape=True,
               family="INS", cargo_kinds=frozenset({"LIQUID"}), answers=("M1:1.05", "M1:1.15", "M2:2.05", "M2:2.14", "M3:3.14"), purpose=("Le relevé de jaugeage des citernes, avec les quantités bord, terre et inspecteur du registre.", "The tank gauging report, with the ship, shore and surveyor quantities of the registry.")))
_register(Form("HOSES", "HOSE_RECORD", ("Relevé de connexion et de déconnexion", "Hose / arm connection and disconnection record"),
               ("ISGOTT, 6e édition (flexibles et bras de chargement) ; OCIMF Guide to Manufacturing and Purchasing Hoses for Offshore Moorings", "ISGOTT, 6th edition (hoses and loading arms); OCIMF hose guidelines"),
               frozenset({"TER", "NAV"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship"))], build_hose_record,
               family="TER", cargo_kinds=frozenset({"LIQUID"}), answers=("M1:1.09", "M1:1.13", "MA2:A2.04"), purpose=("Le relevé des connexions et déconnexions des flexibles ou bras, avec les essais.", "The record of hose or arm connections and disconnections, with the tests.")))
_register(Form("PROTEST", "PROTEST", ("Lettre de protestation", "Letter of protest"),
               ("Usage maritime — réserve de droits, sans reconnaissance de responsabilité", "Maritime practice — reservation of rights without admission of liability"),
               frozenset({"AGE", "NAV", "TER", "INS", "PRE"}), [("AGE", ("Expéditeur", "Issuer")), ("TER", ("Destinataire — reçu", "Recipient — received"))], build_protest,
               family="AGE", answers=("M1:1.19", "M4:4.09", "MB1:B1.17", "MB2:B2.19", "MG1:G1.14", "MR1:R1.12"), purpose=("La lettre de protestation d'une partie, avec réserve de droits et accusé de réception.", "A party's letter of protest, with reservation of rights and acknowledgement.")))
_register(Form("FAL", "FAL_FORMS", ("Formulaires FAL — déclaration générale et liste d'équipage", "FAL forms — general declaration and crew list"),
               ("Convention FAL de l'OMI, formulaires 1 et 5 (modèles 2024)", "IMO FAL Convention, forms 1 and 5 (2024 models)"),
               frozenset({"AGE", "NAV"}), [("NAV", ("Capitaine ou agent autorisé", "Master or authorized agent"))], build_fal,
               family="AGE", answers=("M0:13",), purpose=("La déclaration générale et la liste d'équipage des formulaires FAL de l'OMI.", "The general declaration and crew list of the IMO FAL forms.")))
_register(Form("DOS", "SECURITY_DECLARATION", ("Déclaration de sûreté", "Declaration of security"),
               ("Code ISPS, partie B, appendice 1 (modèle de déclaration de sûreté)", "ISPS Code, part B, appendix 1 (model declaration of security)"),
               frozenset({"SUR", "NAV"}), [("SUR", ("Agent de sûreté de l'installation portuaire (PFSO)", "Port facility security officer (PFSO)")), ("NAV", ("Agent de sûreté du navire (SSO) / capitaine", "Ship security officer (SSO) / master"))],
               build_dos, confidentiality_note=("Niveaux de sûreté et arrangements à remplir à la main : ils ne sont pas enregistrés dans le registre de l'escale.",
                                                "Security levels and arrangements are completed by hand: they are not stored in the call's registry."),
               family="SUR", answers=("M0:30", "M9:9.09"), purpose=("La déclaration de sûreté entre le navire et l'installation portuaire (code ISPS).", "The declaration of security between the ship and the port facility (ISPS Code).")))
_register(Form("MDH", "MDH", ("Déclaration maritime de santé", "Maritime declaration of health"),
               ("Règlement sanitaire international (2005) de l'OMS, annexe 8", "WHO International Health Regulations (2005), annex 8"),
               frozenset({"NAV"}), [("NAV", ("Capitaine", "Master")), ("NAV", ("Médecin de bord (le cas échéant)", "Ship's surgeon (if any)"))], build_mdh,
               family="NAV", answers=("M0:14",), purpose=("La déclaration maritime de santé du capitaine à l'autorité sanitaire.", "The master's maritime declaration of health to the health authority.")))
_register(Form("WASTE", "WASTE_NOTIFICATION", ("Notification préalable de dépôt des déchets", "Advance notification form for waste delivery"),
               ("Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 1 (MARPOL, installations de réception portuaires)", "IMO circular MEPC.1/Circ.834/Rev.1, appendix 1 (MARPOL port reception facilities)"),
               frozenset({"NAV", "AGE"}), [("NAV", ("Capitaine", "Master")), ("PRE", ("Prestataire — reçu", "Provider — received"))], build_waste,
               family="NAV", answers=("M0:16", "M6:6.01"), purpose=("La notification préalable des déchets à déposer (MARPOL, installations de réception).", "The advance notification of waste to be delivered (MARPOL port reception facilities).")))
_register(Form("STS", "STS_CHECKLISTS", ("Listes de contrôle STS", "STS checklists"),
               ("Structure du Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF / ICS / CDI / SIGTTO, 2013)", "Structure of the Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF / ICS / CDI / SIGTTO, 2013)"),
               frozenset({"PRE", "NAV"}), [("PRE", ("POAC", "POAC")), ("NAV", ("Capitaine", "Master"))], build_sts,
               family="PRE", templates=frozenset({"M3"}), needs_link=True, answers=("M3:3.10",), purpose=("Les listes de contrôle de l'opération STS, avant l'opération, la mise à couple, le transfert et après.", "The STS checklists before the operation, run-in, transfer and after.")))
_register(Form("PILOT_CARD", "PILOT_CARD", ("Fiche pilote", "Pilot card"),
               ("Résolution OMI A.960(23), annexe 2", "IMO resolution A.960(23), annex 2"),
               frozenset({"NAV", "SVC"}), [("NAV", ("Capitaine", "Master")), ("SVC", ("Pilote", "Pilot"))], build_pilot_card,
               family="NAV", answers=("M0:18", "M0:26"), purpose=("La fiche pilote remise au pilote à l'embarquement (échange capitaine-pilote).", "The pilot card handed to the pilot on boarding (master-pilot exchange).")))
_register(Form("BDN", "BUNKER_DELIVERY_NOTE", ("Note de livraison de soutes", "Bunker delivery note"),
               ("MARPOL, annexe VI, appendice V", "MARPOL Annex VI, appendix V"),
               frozenset({"PRE"}), [("PRE", ("Représentant du fournisseur", "Supplier's representative")), ("NAV", ("Chef mécanicien", "Chief engineer"))], build_bdn,
               family="PRE", templates=frozenset({"M4"}), answers=("M4:4.08",), purpose=("La note de livraison de soutes du fournisseur (MARPOL annexe VI).", "The supplier's bunker delivery note (MARPOL Annex VI).")))
