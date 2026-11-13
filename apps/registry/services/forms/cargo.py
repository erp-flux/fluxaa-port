"""Forms of version 1.5: the cargo operations of every kind (dry bulk, containers, general cargo, ro-ro) and
the forms taken from the terminals' own practice — the pre-arrival exchange of information (ISGOTT 22.2), the
vetting grid of the vessel against the berth limits, the cargo handling plan.

Same frame as every other form (core.py): what the registry knows is pre-filled, the rest is completed and signed
on paper and comes back as a version of the document.
"""
from __future__ import annotations

from decimal import Decimal

from ...models import CargoKind, PortCall
from .core import (
    F,
    Form,
    _m,
    _mt,
    _operation,
    _party,
    _register,
    _vessel,
    _where,
    checklist,
    dt,
    fields,
    identification,
    table,
    text,
)

DRY = frozenset({"DRY"})
CONTAINER = frozenset({"CONTAINER"})
GENERAL = frozenset({"GENERAL", "RORO", "OTHER"})
NOT_LIQUID = frozenset({"DRY", "CONTAINER", "GENERAL", "RORO", "OTHER"})
EVERY = frozenset()


def _figure(call: PortCall, kind: str, party: str):
    for m in call.measurements.filter(kind=kind).order_by("-created_at"):
        value = m.current_values().get(party)
        if value is not None:
            return value.value, m.unit
    return None, None


def _cargo(call: PortCall) -> str:
    return call.product or (CargoKind(call.cargo_kind).label if call.cargo_kind else "")


def _qty(call: PortCall) -> str | None:
    return f"{call.quantity} {call.get_quantity_unit_display()}" if call.quantity else None


def _stage_ops(call: PortCall) -> str:
    return ", ".join(c for c in call.template_codes if c != "M0")


# ================================================================================ pre-arrival exchange (ISGOTT 22.2)
PAEC_ITEMS = [
    ("A", "Nom et indicatif d'appel du navire", "Name and call sign of the ship"),
    ("B", "Pays d'immatriculation", "Country of registration"),
    ("C", "Longueur hors tout, largeur et tirants d'eau à l'arrivée", "Overall length, beam and drafts on arrival"),
    ("D", "Heure estimée d'arrivée à la zone d'embarquement du pilote", "Estimated time of arrival at the pilot boarding area"),
    ("E", "Déplacement à l'arrivée ; si chargé, nature et quantité de la cargaison", "Displacement on arrival; if loaded, nature and quantity of the cargo"),
    ("F", "Tirant d'eau maximal attendu pendant et à la fin des opérations", "Maximum draft expected during and upon completion of the operations"),
    ("G", "Défauts de coque, de machine ou d'équipement pouvant affecter la sécurité ou retarder l'opération", "Any defects on hull, machinery or equipment that could affect safety or delay the operation"),
    ("H", "Système de gaz inerte : confirmation du bon fonctionnement et teneur en oxygène des citernes", "Inert gas system: confirmation of good working order and tank oxygen content"),
    ("I", "Besoin de nettoyage de citernes ou de dégazage", "Any requirement for tank cleaning and/or gas freeing"),
    ("J", "Collecteur : type, taille, nombre, hauteur, réductions", "Manifold: type, size, number, height, reducers"),
    ("K", "Flexibles du bord disponibles : nombre, taille, pression de service", "Ship's flexible hoses available: number, size, working pressure"),
    ("L", "Opérations de cargaison prévues : séquence, débit, pression, ballastage", "Proposed cargo operations: sequence, rate, pressure, ballasting"),
    ("M", "Quantité et nature des résidus, slops et eaux de lavage ; ballast sale", "Quantity and nature of slops, washings and dirty ballast"),
    ("N", "Soutes et provisions demandées : quantités, spécifications, livraison", "Bunkers and stores required: quantities, specifications, delivery"),
    ("O", "État de fonctionnement de la grue du navire", "Operational status of the vessel's crane"),
    ("P", "Niveau de sûreté ISPS du navire", "Present ship security level (ISPS)"),
    ("Q", "Hauteur du collecteur au-dessus de l'eau à l'arrivée et attendue", "Height of manifold above water on arrival and expected"),
    ("R", "Longueur minimale de muraille parallèle sur ballast", "Minimum parallel body length in ballast condition"),
    ("S", "Pied de pilote minimal", "Minimum under-keel clearance"),
    ("T", "Contact du capitaine : courriel, téléphone satellite", "Master's contact: e-mail, satellite phone"),
    ("U", "Informations du terminal au navire : poste, limites, services, règlement", "Terminal to ship: berth, limits, services, regulations"),
    ("V", "Informations du navire au terminal et au pilote", "Ship to terminal and/or pilot"),
    ("W", "Déficiences ou incompatibilités de l'équipement d'amarrage, du collecteur ou des moyens d'accès", "Deficiencies or incompatibilities in mooring equipment, manifold or means of access"),
    ("X", "État des amarres (réparations, âge) ; remorques de secours", "Condition of the mooring lines (repairs, age); emergency towing-off pennants"),
    ("Y", "Chaumards, bittes et points forts utilisables ; SWL", "Fairleads, bollards and strong points available; SWL"),
    ("Z", "Charge de service (SWL) des équipements de levage et d'amarrage", "Safe working load (SWL) of the lifting and mooring equipment"),
    ("AA", "Zones de la coque inadaptées aux défenses ou aux remorqueurs", "Areas of the ship's hull unsuited to fenders or tugs"),
    ("AB", "Particularités du poste (appontement, bouée, zone STS)", "Particulars of the berth (jetty, buoy, STS area)"),
]


def build_paec(call: PortCall) -> list[dict]:
    """ISGOTT 22.2: the information the ship gives the terminal 72 hours before arrival and the terminal gives
    the ship, point by point; the ETA confirmations at 72, 48, 36 and 24 hours; the documents expected after
    departure from the last port."""
    v = call.vessel
    known = {
        "A": f"{v.name} — {v.call_sign or '—'}", "B": v.flag or None,
        "C": f"LOA {v.loa_m or '—'} m — largeur / beam {v.beam_m or '—'} m — tirant d'eau / draft {v.draft_m or '—'} m",
        "D": dt(call.eta), "E": (f"{v.displacement_t} t — " if v.displacement_t else "") + (f"{_cargo(call)} {_qty(call) or ''}".strip() or "—"),
        "J": None, "O": f"SWL {v.crane_swl_t} t" if v.crane_swl_t else None, "P": None,
        "Q": f"{v.manifold_height_m} m" if v.manifold_height_m else None, "T": None,
        "U": f"{_where(call)} — {_party(call, 'TER') or '—'}",
    }
    rows = [[code, f"{fr} / {en}", known.get(code), None] for code, fr, en in PAEC_ITEMS]
    confirmations = [["72 h", dt(call.eta - _hours(72)) if call.eta else None, None, None],
                     ["48 h", dt(call.eta - _hours(48)) if call.eta else None, None, None],
                     ["36 h", dt(call.eta - _hours(36)) if call.eta else None, None, None],
                     ["24 h", dt(call.eta - _hours(24)) if call.eta else None, None, None]]
    docs = {d.type.code: d for d in call.documents.exclude(status="CANCELLED").select_related("type")}
    expected = [("BILL_OF_LADING", "Connaissement", "Bill of lading"), ("QUALITY_CERT", "Certificat de qualité", "Certificate of quality"),
                ("QQ_CERT", "Certificat de quantité", "Certificate of quantity"), ("OTHER", "Certificat d'origine", "Certificate of origin"),
                ("CARGO_MANIFEST", "Manifeste de cargaison", "Cargo manifest")]
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"),
                       F("Cargaison / quantité", "Cargo / quantity", f"{_cargo(call)} — {_qty(call) or '—'}", source="PortCall.product, quantity")),
        text(("Objet", "Purpose"), [
            ("Au moins 72 heures avant l'arrivée, ou dès le départ du dernier port, le navire communique au terminal les informations ci-dessous (ISGOTT 22.2) ; le terminal communique les siennes. L'ETA est confirmée à 72, 48, 36 et 24 heures de la station de pilotage.",
             "At least 72 hours before arrival, or after departure from the last port, the ship gives the terminal the information below (ISGOTT 22.2); the terminal gives its own. The ETA is confirmed 72, 48, 36 and 24 hours before the pilot station."),
        ]),
        table(("Informations échangées", "Information exchanged"),
              [("Réf.", "Ref."), ("Information", "Information"), ("Demandé au navire — réponse", "Requested from ship — answer"), ("Demandé au terminal — réponse", "Requested from shore — answer")],
              rows, source="Vessel (nom, indicatif, pavillon, LOA, largeur, tirant d'eau, déplacement, hauteur de collecteur, SWL grue), PortCall (ETA, produit, quantité, poste), CallParty TER"),
        table(("Confirmations de l'ETA", "ETA confirmations"),
              [("Préavis", "Notice"), ("Échéance (UTC)", "Due (UTC)"), ("ETA confirmée", "ETA confirmed"), ("Par / canal", "By / channel")],
              confirmations, source="PortCall.eta − 72 / 48 / 36 / 24 h"),
        table(("Documents attendus après le départ du dernier port", "Documents expected after departure from the last port"),
              [("Document", "Document"), ("Reçu", "Received"), ("Référence / version", "Reference / version")],
              [[f"{fr} / {en}", "oui / yes" if code in docs and code != "OTHER" else None,
                f"{docs[code].title} v{docs[code].version}" if code in docs and code != "OTHER" else None] for code, fr, en in expected],
              source="Document.type.code (BILL_OF_LADING, QUALITY_CERT, QQ_CERT, CARGO_MANIFEST)"),
    ]


def _hours(n: int):
    from datetime import timedelta

    return timedelta(hours=n)


# ================================================================================ vetting grid against the berth limits
def vetting_rows(call: PortCall) -> list[dict]:
    """Each limit of the berth beside the vessel's particular: Y (within), N (outside, compulsory), K (caution), Z
    (not assessed) — as the terminals' own grids read."""
    return vetting_rows_for(call.vessel, call.berth or call.requested_berth, call.eta)


def vetting_rows_for(v, berth, at=None) -> list[dict]:
    """The same grid for a vessel and a berth without a call yet: the announcement shows it to the agency before
    it asks for the berth (v1.6)."""
    age = (at.year - v.built_year) if v is not None and v.built_year and at else None
    rows = [
        ("1.21", "LOA maximale (m)", "Max LOA (m)", berth.max_loa_m if berth else None, v.loa_m, "le", True),
        ("5.2", "Tirant d'eau maximal au poste (m)", "Maximum draft permitted alongside (m)", berth.max_draft_m if berth else None, v.draft_m, "le", False),
        ("1.29", "Largeur maximale (m)", "Max beam (m)", berth.max_beam_m if berth else None, v.beam_m, "le", True),
        ("5.2", "Déplacement maximal (t)", "Max displacement (t)", berth.max_displacement_t if berth else None, v.displacement_t, "le", True),
        ("", "Port en lourd maximal (t)", "Max DWT (t)", berth.max_dwt if berth else None, v.dwt, "le", True),
        ("5.41", "Hauteur maximale du collecteur au-dessus de l'eau (m)", "Max manifold height to waterline (m)", berth.max_manifold_height_m if berth else None, v.manifold_height_m, "le", True),
        ("", "Tirant d'air maximal (m)", "Max air draft (m)", berth.max_air_draft_m if berth else None, v.air_draft_m, "le", True),
        ("1.4", "Âge maximal (ans)", "Max age (years)", berth.max_vessel_age_years if berth else None, age, "le", True),
        ("7.2", "SWL minimale de la grue (t)", "Min crane SWL (t)", berth.min_crane_swl_t if berth else None, v.crane_swl_t, "ge", False),
    ]
    result = []
    for ref, fr, en, limit, actual, op, compulsory in rows:
        if limit is None or actual is None:
            status = "Z"
        else:
            within = (Decimal(str(actual)) <= Decimal(str(limit))) if op == "le" else (Decimal(str(actual)) >= Decimal(str(limit)))
            status = "Y" if within else ("N" if compulsory else "K")
        result.append({"ref": ref, "fr": fr, "en": en, "limit": limit, "actual": actual, "status": status,
                       "rule": "obligatoire / compulsory" if compulsory else "vigilance / caution"})
    return result


def vetting_verdict(rows: list[dict]) -> tuple[str, str]:
    statuses = {r["status"] for r in rows}
    if "N" in statuses:
        return ("INAPTE — une limite obligatoire est dépassée", "UNSUITABLE — a compulsory limit is exceeded")
    if "K" in statuses:
        return ("APTE SOUS VIGILANCE", "SUITABLE WITH CAUTIONS")
    if statuses <= {"Z"}:
        return ("NON ÉVALUÉ — limites ou données manquantes", "NOT ASSESSED — limits or data missing")
    return ("APTE", "SUITABLE")


def build_vetting_checklist(call: PortCall) -> list[dict]:
    """The terminal's vetting grid: the berth limits (parametrised per berth) against the vessel's particulars,
    with the Y / N / K / Z reading of the terminals' own grids and the verdict; the documentary items (OCIMF
    inspection, certificates, dry dock, PSC, P&I, incidents, last cargoes) completed from the file or by hand."""
    v = call.vessel
    rows = vetting_rows(call)
    verdict = vetting_verdict(rows)
    berth = call.berth or call.requested_berth
    docs = {d.type.code: d for d in call.documents.exclude(status="CANCELLED").select_related("type")}
    req = call.requests.filter(type__code="VESSEL_ACCEPTANCE").order_by("-pk").first()
    return [
        identification(call, F("Poste / type", "Berth / type", f"{berth.code} — {berth.get_kind_display()}" if berth else _where(call), source="PortCall.berth ou requested_berth"),
                       F("Cargaison", "Cargo", _cargo(call), source="PortCall.product"), F("N° de vetting", "Vetting no.", req.reference if req else None, source="ServiceRequest VESSEL_ACCEPTANCE.reference"),
                       F("Type de navire", "Kind of vessel", f"{v.get_vessel_kind_display()}" + (f" — {v.vessel_type}" if v.vessel_type else ""), source="Vessel.vessel_kind, vessel_type"),
                       F("Année de construction", "Year built", str(v.built_year) if v.built_year else None, source="Vessel.built_year")),
        table(("Limites du poste et données du navire", "Berth limits and vessel data"),
              [("Q88", "Q88"), ("Critère", "Item"), ("Limite", "Limit"), ("Navire", "Vessel data"), ("Statut", "Status"), ("Règle", "Rule")],
              [[r["ref"] or None, f"{r['fr']} / {r['en']}", str(r["limit"]) if r["limit"] is not None else None, str(r["actual"]) if r["actual"] is not None else None,
                r["status"], r["rule"]] for r in rows],
              source="Berth.max_loa_m, max_draft_m, max_beam_m, max_displacement_t, max_dwt, max_manifold_height_m, max_air_draft_m, max_vessel_age_years, min_crane_swl_t ; Vessel.loa_m, draft_m, beam_m, displacement_t, dwt, manifold_height_m, air_draft_m, built_year, crane_swl_t",
              note=("Y : dans la limite · N : hors limite obligatoire · K : vigilance · Z : non évalué (limite ou donnée absente).", "Y: within the limit · N: outside a compulsory limit · K: caution · Z: not assessed (limit or data missing).")),
        checklist(("Éléments documentaires", "Documentary items"), [
            ("1.9 — Type de coque (double coque pour un pétrolier)", "1.9 — Hull type (double hull for a tanker)"),
            ("— Rapport d'inspection OCIMF SIRE / CDI disponible" + (f" — {docs['VETTING_REPORT'].title}" if "VETTING_REPORT" in docs else ""), "— OCIMF SIRE / CDI inspection report available"),
            ("2.0 — Certificats statutaires valides à la date de départ prévue" + (" — fournis / provided" if "CERTIFICATES" in docs else ""), "2.0 — Statutory certificates valid at the planned departure date"),
            ("1.16 — Dernière mise en cale sèche ≤ 5 ans (sinon dérogation de classe)", "1.16 — Last dry dock ≤ 5 years (otherwise class derogation)"),
            ("3.4 — Langue de communication : anglais", "3.4 — Communication language: English"),
            ("8.34 — Conformité MARPOL", "8.34 — Complies with MARPOL"),
            ("5.23 — Alarmes de niveau haut installées et essayées", "5.23 — High level alarms fitted and tested"),
            ("5.30 — Conformité aux recommandations OCIMF (collecteurs, amarrage)", "5.30 — Complies with the OCIMF recommendations (manifolds, mooring)"),
            ("8.9 — Assurance P&I pollution en vigueur" + (" — attestation fournie / certificate provided" if "INSURANCE" in docs else ""), "8.9 — P&I pollution liability in force"),
            ("8.12 — Dernier contrôle par l'État du port : date et lieu", "8.12 — Last port State control: date and place"),
            ("8.14 — Aucun événement de pollution, échouement, incident grave non déclaré", "8.14 — No undeclared pollution, grounding or serious incident"),
            ("8.15 — Trois dernières cargaisons compatibles" + (" — fournies / provided" if "LAST_CARGOES" in docs else ""), "8.15 — Last three cargoes compatible"),
            ("— Cadence de pompage historique acceptable", "— Historical pumping rate acceptable"),
            ("— Accepté par le mandant / l'armateur de l'installation", "— Accepted by the principal / terminal owner"),
            ("— Accepté par l'autorité portuaire", "— Accepted by the port authority"),
        ], columns=[("Conforme", "Compliant"), ("Observation", "Remark")]),
        fields(("Avis", "Verdict"), [
            F("Résultat de la grille", "Grid result", f"{verdict[0]} / {verdict[1]}", wide=True, source="calcul : statuts de la table des limites"),
            F("Décision d'acceptation (registre)", "Acceptance decision (registry)",
              f"{req.get_decision_display()} — {dt(req.decided_at)}" if req is not None and req.decision else None, source="ServiceRequest VESSEL_ACCEPTANCE.decision, decided_at"),
            F("Conditions", "Conditions", req.decision_conditions if req is not None and req.decision_conditions else None, wide=True, source="ServiceRequest.decision_conditions"),
            F("Commentaires et remarques", "Comments and remarks", wide=True),
        ]),
    ]


# ================================================================================ cargo handling plan (terminal)
def build_cargo_handling_plan(call: PortCall) -> list[dict]:
    """The terminal's cargo handling plan, in the structure of the terminals' own plans: general information,
    cargo operations per parcel (ship side) and per shore tank (shore side), line displacement, line-up and seals,
    measurement equipment comparison, terminal representatives and their duties, shore tank data before / after
    line displacement / after the operation, acknowledgements."""
    v = call.vessel
    from ..measurements import pumping_summary

    sheets = [s for side in ("SHIP", "SHORE") for s in pumping_summary(call)[side]["sheets"]]
    shore_sheets = [s for s in sheets if s.side == "SHORE"]
    ship_sheets = [s for s in sheets if s.side == "SHIP"]
    return [
        fields(("1 · Informations générales", "1 · General information"), [
            F("Navire", "Vessel", _vessel(call), source="Vessel"), F("Port / poste", "Port / berth", f"{call.port.name} — {_where(call)}", source="Port, PortCall.berth"),
            F("Cargaison", "Cargo", _cargo(call), source="PortCall.product"), F("Quantité (MT vac.)", "Quantity (MT vac)", _qty(call), source="PortCall.quantity"),
            F("Tirant d'eau à l'arrivée (m)", "Arrival draft (m)", str(v.draft_m) if v.draft_m else None, source="Vessel.draft_m"), F("Tirant d'eau au départ (m)", "Departure draft (m)"),
            F("Densité / température", "Density / temperature", f"{shore_sheets[0].density} / —" if shore_sheets and shore_sheets[0].density else None, source="PumpingLogSheet.density"),
            F("Agent", "Agent", str(call.agency), source="PortCall.agency"), F("Inspecteur", "Surveyor", _party(call, "INS"), source="CallParty INS"),
            F("Opération", "Operation", _operation(call), source="PortCall.template_codes"), F("Date du plan", "Date of the plan", dt(call.etb or call.eta), source="PortCall.etb"),
        ]),
        table(("2 · Opérations de cargaison — côté navire (par lot)", "2 · Cargo operations — ship side (per parcel)"),
              [("N°", "No."), ("Élément", "Item"), ("Lot 1", "Parcel 1"), ("Lot 2", "Parcel 2"), ("Lot 3", "Parcel 3")],
              [["1", "Quantité par lot (MT vac.) / Quantity per parcel", _qty(call), None, None],
               ["2", "Citernes du bord prévues / Ship tanks intended", ", ".join(s.tank for s in ship_sheets if s.tank) or None, None, None],
               ["3", "Citerne de démarrage / First cargo tank worked", ship_sheets[0].tank if ship_sheets and ship_sheets[0].tank else None, None, None],
               ["4", "Mode de dégagement des citernes (PV / IGS) / Tank venting method", None, None, None],
               ["5", "Arrêt navire-terre : qui donne l'ordre / Ship-shore stop", None, None, None]],
              source="PortCall.quantity, PumpingLogSheet (SHIP).tank"),
        table(("Déplacement de ligne", "Line displacement"),
              [("N°", "No."), ("Élément", "Item"), ("Lot 1", "Parcel 1"), ("Lot 2", "Parcel 2")],
              [["1", "Quantité (m³) / Quantity (CBM)", None, None], ["2", "Citerne du bord / Ship tank", None, None],
               ["3", "Bac à terre / Shore tank", None, None], ["4", "Arrêt navire-terre / Ship-shore stop", None, None]]),
        table(("Côté terre — bacs récepteurs ou émetteurs", "Shore side — receiving or delivering tanks"),
              [("Produit", "Product"), ("Quantité (MT vac.)", "Quantity (MT vac)"), ("Bac", "Tank"), ("Creux (mm)", "Ullage (mm)"), ("Densité / temp.", "Density / temp."),
               ("Bac de départ", "Starting tank"), ("Débit initial (m³/h)", "Start rate (m³/h)"), ("Débit max (m³/h)", "Max rate (m³/h)"), ("Pression max (bar)", "Max pressure (bar)")],
              [[s.product or _cargo(call), f"{s.planned_quantity_mt}" if s.planned_quantity_mt else None, s.tank or None,
                f"{s.start_level_mm:g}" if s.start_level_mm is not None else None, f"{s.density}" if s.density else None,
                s.tank if s is shore_sheets[0] else None, None, f"{s.expected_rate_m3h}" if s.expected_rate_m3h else None,
                f"{s.expected_pressure_bar}" if s.expected_pressure_bar else None] for s in shore_sheets] or [],
              blank_rows=3 if not shore_sheets else 1, source="PumpingLogSheet (SHORE) : tank, product, planned_quantity_mt, start_level_mm, density, expected_rate_m3h, expected_pressure_bar"),
        table(("3 · Alignement — scellés et vannes", "3 · Line-up — seals and valves"),
              [("N°", "No."), ("N° de scellé", "Seal number"), ("Emplacement de la vanne", "Valve location"), ("Ouverte", "Opened"), ("Fermée", "Closed"), ("Observations", "Comments")],
              [], blank_rows=12),
        table(("4 · Comparaison des équipements de mesure", "4 · Measurement equipment comparison"),
              [("Équipement", "Equipment"), ("N° de série", "Serial number"), ("Moyenne avant", "Average before"), ("Moyenne après", "Average after")],
              [["Thermomètre terre / Shore thermometer", None, None, None], ["Thermomètre inspecteur / Surveyor thermometer", None, None, None],
               ["Ruban terre / Shore tape", None, None, None], ["Ruban inspecteur / Surveyor tape", None, None, None]]),
        table(("5 · Représentants du terminal — permanences", "5 · Terminal representatives — duties"),
              [("N°", "No."), ("Nom", "Name"), ("Fonction", "Rank"), ("De (heure)", "From (time)"), ("À (heure)", "To (time)")],
              [], blank_rows=4),
        checklist(("Responsabilités des représentants du terminal", "Responsibilities of the terminal representatives"), [
            ("Vérifier que tous les points des listes de contrôle de sécurité sont en ordre", "Ensure all safety checklist items are in order"),
            ("Présence continue au parc à bacs, à l'appontement, au navire et au collecteur", "Continuous manning of tank farm, jetty, vessel and manifold"),
            ("Vigilance permanente contre tout déversement à terre, à bord, au collecteur, en mer", "Be always alert of any oil spill on shore, vessel, manifold, sea"),
            ("Lire et viser les consignes permanentes", "Read and acknowledge the standing instructions"),
            ("Amarres, passerelle, dalots, parc à bacs surveillés en permanence", "Moorings, gangway, scuppers, tank farm attended at all times"),
            ("Vannes, tuyauteries, manomètres, bacs en ordre", "Valves, pipelines, pressure gauges, tanks all in order"),
            ("Appeler le chef de quart terre en cas de doute", "Call the shore officer whenever in doubt"),
            ("Vérifier l'éclairage et les points d'accès de sûreté", "Check lights and security access points"),
            ("Rapprochement horaire des quantités et investigation de tout écart", "Hourly reconciliation and investigation of any discrepancy"),
            ("Communication maintenue entre toutes les parties ; rondes de sécurité continues", "Communications maintained between all parties; continuous safety patrols"),
        ], columns=[("Vu", "Seen"), ("Visa", "Initials")]),
        table(("6 · Données des bacs du parc", "6 · Tank farm tanks data"),
              [("Bac", "Shore tank"), ("Produit", "Product"), ("Avant — HLA", "Before — HLA"), ("Avant — ATG", "Before — ATG"), ("Avant — ruban", "Before — hand dip"),
               ("Après déplacement — ATG", "After line displacement — ATG"), ("Après opération — HLA", "After — HLA"), ("Après opération — ATG", "After — ATG"), ("Après opération — ruban", "After — hand dip")],
              [[s.tank or None, s.product or None, None, None, f"{s.start_level_mm:g}" if s.start_level_mm is not None else None, None, None, None,
                f"{s.actual_stop_level_mm:g}" if s.actual_stop_level_mm is not None else None] for s in shore_sheets] or [],
              blank_rows=4, source="PumpingLogSheet (SHORE).start_level_mm, actual_stop_level_mm"),
        fields(("7 · Commentaires, remarques, observations", "7 · Comments, remarks, observations"), [F("", "", wide=True)]),
    ]


# ================================================================================ dry bulk, general cargo, containers
def build_draft_survey(call: PortCall) -> list[dict]:
    """The draft survey report (UNECE code of uniform standards and procedures): the six drafts read, corrected
    and averaged, displacement from the hydrostatic tables, deductibles, net displacement, cargo by difference;
    the ship, shore and surveyor figures of the registry."""
    v = call.vessel
    rows = []
    for kind, fr, en in (("DRAFT_I", "Draft survey initial", "Initial draft survey"), ("DRAFT_F", "Draft survey final", "Final draft survey")):
        ship, unit = _figure(call, kind, "SHIP")
        shore, _u = _figure(call, kind, "SHORE")
        surveyor, _u = _figure(call, kind, "SURVEYOR")
        rows.append([f"{fr} / {en}", f"{ship} {unit}" if ship is not None else None, f"{shore} {unit}" if shore is not None else None,
                     f"{surveyor} {unit}" if surveyor is not None else None])
    drafts = [("Avant — bâbord / Fore — port", None, None), ("Avant — tribord / Fore — starboard", None, None), ("Milieu — bâbord / Mid — port", None, None),
              ("Milieu — tribord / Mid — starboard", None, None), ("Arrière — bâbord / Aft — port", None, None), ("Arrière — tribord / Aft — starboard", None, None),
              ("Moyenne corrigée (perpendiculaires, flèche) / Corrected mean (perpendiculars, hog-sag)", None, None), ("Densité de l'eau (kg/m³) / Water density", None, None)]
    deductibles = ["Ballast / Ballast water", "Eau douce / Fresh water", "Fuel / Fuel oil", "Gazole / Diesel oil", "Huile / Lube oil", "Constante / Constant", "Autres / Others"]
    return [
        identification(call, F("Cargaison", "Cargo", _cargo(call), source="PortCall.product"), F("Quantité déclarée", "Declared quantity", _qty(call), source="PortCall.quantity"),
                       F("Longueur entre perpendiculaires (m)", "Length between perpendiculars (m)"), F("Port en lourd (t)", "Deadweight (t)", str(v.dwt) if v.dwt else None, source="Vessel.dwt"),
                       F("Draft survey initial", "Initial draft survey", _mt(call, "DRAFT_SURVEY_INITIAL"), source="jalon DRAFT_SURVEY_INITIAL"),
                       F("Draft survey final", "Final draft survey", _mt(call, "DRAFT_SURVEY_FINAL"), source="jalon DRAFT_SURVEY_FINAL")),
        table(("Tirants d'eau lus", "Drafts read"), [("Lecture", "Reading"), ("Initial (m)", "Initial (m)"), ("Final (m)", "Final (m)")],
              [[label, a, b] for label, a, b in drafts]),
        table(("Déplacement et déductions", "Displacement and deductibles"),
              [("Élément", "Item"), ("Initial (t)", "Initial (t)"), ("Final (t)", "Final (t)")],
              [["Déplacement aux tables (corrigé assiette, gîte, densité) / Displacement from tables (trim, list, density corrected)", None, None],
               *[[d, None, None] for d in deductibles], ["Déplacement net / Net displacement", None, None]]),
        table(("Quantité de cargaison", "Cargo quantity"),
              [("Mesure", "Measurement"), ("Navire", "Ship"), ("Terre", "Shore"), ("Inspecteur", "Surveyor")], rows,
              source="Measurement DRAFT_I / DRAFT_F : valeurs SHIP, SHORE, SURVEYOR",
              note=("La quantité de cargaison est la différence des déplacements nets ; aucune des trois valeurs n'est la référence (EF-8.1).",
                    "The cargo quantity is the difference of the net displacements; none of the three figures is the reference (EF-8.1).")),
        fields(("Conditions et remarques", "Conditions and remarks"), [F("État de la mer, houle, visibilité des marques", "Sea state, swell, visibility of the marks", wide=True),
                                                                    F("Réserves", "Remarks", wide=True)]),
    ]


def build_cargo_manifest(call: PortCall) -> list[dict]:
    """The cargo manifest (IMO FAL form 2 structure): B/L, marks and numbers, number and kind of packages,
    description, gross weight, measurement, shipper, consignee, port of loading / discharge."""
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"),
                       F("Port de chargement / déchargement", "Port of loading / discharge", f"{call.last_port or '—'} → {call.port.name} → {call.next_port or '—'}", source="PortCall.last_port, next_port"),
                       F("Cargaison déclarée", "Declared cargo", f"{_cargo(call)} — {_qty(call) or '—'}", source="PortCall.product, quantity")),
        table(("Marchandises", "Cargo"),
              [("Connaissement", "B/L no."), ("Marques et numéros", "Marks and numbers"), ("Nombre et nature des colis / unités", "Number and kind of packages / units"),
               ("Description", "Description"), ("Poids brut (kg)", "Gross weight (kg)"), ("Volume (m³)", "Measurement (m³)"), ("Chargeur", "Shipper"), ("Destinataire", "Consignee"), ("Remarques", "Remarks")],
              [[None, None, None, _cargo(call) or None, None, None, _party(call, "COM"), None, None]], blank_rows=8,
              source="PortCall.product, CallParty COM"),
        fields(("Totaux", "Totals"), [F("Nombre total de colis / unités / conteneurs", "Total packages / units / containers"), F("Poids brut total (t)", "Total gross weight (t)", _qty(call) if call.quantity_unit == "MT" else None, source="PortCall.quantity (MT)"),
                                      F("Marchandises dangereuses (voir déclaration DG)", "Dangerous goods (see DG declaration)")]),
    ]


def build_stowage_plan(call: PortCall) -> list[dict]:
    """The stowage / loading or discharge plan agreed between ship and terminal: per hold, deck or bay, the cargo,
    the quantities, the sequence and the limits (BLU Code §3 for bulk, CSS Code for the others)."""
    kind = call.cargo_kind
    unit_rows = [["1", None, None, None, None, None, None], ["2", None, None, None, None, None, None], ["3", None, None, None, None, None, None],
                 ["4", None, None, None, None, None, None], ["5", None, None, None, None, None, None]]
    where = "Cale / Hold" if kind == "DRY" else ("Baie / Bay" if kind == "CONTAINER" else ("Pont / Deck" if kind == "RORO" else "Cale ou pont / Hold or deck"))
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"),
                       F("Cargaison / quantité", "Cargo / quantity", f"{_cargo(call)} — {_qty(call) or '—'}", source="PortCall.product, quantity"),
                       F("Tirant d'eau à l'arrivée / au départ (m)", "Draft arrival / departure (m)", f"{call.vessel.draft_m or '—'} / —", source="Vessel.draft_m")),
        table(("Plan par " + where.split(" / ")[0].lower(), "Plan per " + where.split(" / ")[1].lower()),
              [(where, where), ("Cargaison / lot", "Cargo / parcel"), ("Quantité prévue", "Planned quantity"), ("Séquence", "Sequence"), ("Cadence (t/h, mvts/h)", "Rate (t/h, moves/h)"),
               ("Ballastage / stabilité", "Ballast / stability"), ("Observations", "Remarks")],
              unit_rows, blank_rows=3),
        fields(("Contraintes et accords", "Limits and agreements"), [
            F("Contraintes de structure (moments, efforts tranchants, charge par cale ou par pont)", "Structural limits (bending, shear, load per hold or deck)", wide=True),
            F("Tirant d'eau et assiette visés à la fin", "Target draft and trim on completion"), F("Nivellement / saisissage", "Trimming / lashing"),
            F("Ordre d'arrêt et délai", "Stop order and stop time"), F("Communication (VHF, téléphone)", "Communication (VHF, telephone)"),
        ], note=(("Plan convenu entre le navire et le terminal avant les opérations (Code BLU §3 et appendice 2).", "Plan agreed between the ship and the terminal before the operations (BLU Code §3 and appendix 2).") if kind == "DRY"
                 else ("Plan d'arrimage conforme au manuel d'assujettissement de la cargaison (Code CSS) et aux calculs de stabilité du bord.", "Stowage plan per the cargo securing manual (CSS Code) and the ship's stability calculations."))),
    ]


def build_dg_declaration(call: PortCall) -> list[dict]:
    """The dangerous goods declaration (IMDG Code 5.4, IMO FAL form 7 structure)."""
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"), F("Niveau de sûreté", "Security level")),
        table(("Marchandises dangereuses", "Dangerous goods"),
              [("Position / conteneur", "Stowage position / container"), ("N° ONU", "UN number"), ("Désignation officielle", "Proper shipping name"),
               ("Classe / division", "Class / division"), ("Groupe d'emballage", "Packing group"), ("Risques subsidiaires", "Subsidiary risks"),
               ("Nombre et type de colis", "Number and kind of packages"), ("Masse / volume", "Mass / volume"), ("Point d'éclair", "Flashpoint"), ("Polluant marin", "Marine pollutant"), ("EmS", "EmS")],
              [], blank_rows=8),
        text(("Déclaration du chargeur", "Shipper's declaration"), [
            ("Je déclare que le contenu de cet envoi est décrit ci-dessus de façon complète et exacte par sa désignation officielle de transport, et qu'il est classé, emballé, marqué, étiqueté ou placardé et à tous égards en état d'être transporté conformément aux règlements internationaux et nationaux applicables.",
             "I hereby declare that the contents of this consignment are fully and accurately described above by the proper shipping name, and are classified, packaged, marked and labelled/placarded, and are in all respects in proper condition for transport according to the applicable international and national governmental regulations."),
        ]),
    ]


def build_hold_inspection(call: PortCall) -> list[dict]:
    """The hold / cargo inspection report before loading or discharging: cleanliness, dryness, watertightness,
    odour, residues, infestation, ladders and lighting per hold; the acceptance or the remarks."""
    accepted = _m(call, "HOLDS_ACCEPTED")
    return [
        identification(call, F("Cargaison prévue", "Intended cargo", _cargo(call), source="PortCall.product"),
                       F("Inspection", "Inspection", dt(accepted.declared_at) if accepted else None, source="jalon HOLDS_ACCEPTED"),
                       F("Inspecteur", "Surveyor", _party(call, "INS"), source="CallParty INS")),
        table(("Cales / espaces inspectés", "Holds / spaces inspected"),
              [("Cale", "Hold"), ("Propreté", "Cleanliness"), ("Sèche", "Dry"), ("Étanchéité des panneaux", "Hatch cover tightness"), ("Odeur / résidus", "Odour / residues"),
               ("Infestation", "Infestation"), ("Échelles / éclairage", "Ladders / lighting"), ("Acceptée", "Accepted"), ("Réserves", "Remarks")],
              [[str(n), None, None, None, None, None, None, None, None] for n in range(1, 6)], blank_rows=2),
        fields(("Conclusion", "Conclusion"), [F("Cales acceptées pour la cargaison prévue", "Holds accepted for the intended cargo", "oui / yes" if accepted else None, source="jalon HOLDS_ACCEPTED"),
                                              F("Cales refusées et travaux demandés", "Holds rejected and work required", wide=True)]),
    ]


def build_tally_sheet(call: PortCall) -> list[dict]:
    """The tally sheet and out-turn statement: per lot, hold or deck and shift, the units counted by the ship and
    by the shore, the differences, the damaged units; the out-turn against the manifest."""
    tally_ship, unit = _figure(call, "TALLY", "SHIP")
    tally_shore, _u = _figure(call, "TALLY", "SHORE")
    tally_ins, _u = _figure(call, "TALLY", "SURVEYOR")
    return [
        identification(call, F("Cargaison", "Cargo", _cargo(call), source="PortCall.product"), F("Quantité au manifeste", "Manifest quantity", _qty(call), source="PortCall.quantity"),
                       F("Début / fin des opérations", "Start / end of operations", f"{_mt(call, 'CARGO_OPS_START') or '—'} → {_mt(call, 'CARGO_OPS_END') or '—'}", source="jalons CARGO_OPS_START / END")),
        table(("Pointage", "Tally"),
              [("Date / équipe", "Date / shift"), ("Cale / pont / lot", "Hold / deck / lot"), ("Marques", "Marks"), ("Pointé navire", "Ship tally"), ("Pointé terre", "Shore tally"),
               ("Écart", "Difference"), ("Endommagés", "Damaged"), ("Observations", "Remarks")],
              [], blank_rows=10),
        table(("Constat de réception (out-turn)", "Out-turn statement"),
              [("Mesure", "Measurement"), ("Navire", "Ship"), ("Terre", "Shore"), ("Inspecteur", "Surveyor")],
              [[f"Total pointé / Total tallied ({unit or ''})", str(tally_ship) if tally_ship is not None else None, str(tally_shore) if tally_shore is not None else None,
                str(tally_ins) if tally_ins is not None else None], ["Manifeste / Manifest", _qty(call), _qty(call), None], ["Manquants / Short", None, None, None], ["Excédents / Over", None, None, None]],
              source="Measurement TALLY : valeurs SHIP, SHORE, SURVEYOR ; PortCall.quantity"),
    ]


def build_mates_receipt(call: PortCall) -> list[dict]:
    """The mate's receipt: the cargo received on board, with the master's remarks, before the bill of lading."""
    return [
        identification(call, F("Chargeur", "Shipper", _party(call, "COM"), source="CallParty COM"), F("Port de destination", "Port of destination", call.next_port or None, source="PortCall.next_port")),
        table(("Marchandises reçues à bord", "Cargo received on board"),
              [("Marques et numéros", "Marks and numbers"), ("Nombre et nature des colis", "Number and kind of packages"), ("Description", "Description"), ("Poids brut", "Gross weight"), ("Volume", "Measurement"), ("Cale / pont", "Hold / deck")],
              [[None, None, _cargo(call) or None, _qty(call), None, None]], blank_rows=5, source="PortCall.product, quantity"),
        fields(("Réserves du bord", "Master's remarks"), [F("État apparent de la marchandise et de l'emballage", "Apparent order and condition of the goods and packing", wide=True),
                                                           F("Reçu à bord le", "Received on board on", _mt(call, "CARGO_OPS_END"), source="jalon CARGO_OPS_END")]),
    ]


def build_outturn_report(call: PortCall) -> list[dict]:
    """The terminal's operation / out-turn report: moves or tonnages per shift, times, stoppages, incidents,
    damaged units, weighing record; the quantities of the registry."""
    from ..reports import interruptions

    stops = interruptions(call)
    scale, unit = _figure(call, "SCALE", "SHORE")
    tally, tunit = _figure(call, "TALLY", "SHORE")
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"), F("Cargaison / quantité", "Cargo / quantity", f"{_cargo(call)} — {_qty(call) or '—'}", source="PortCall.product, quantity"),
                       F("Début / fin des opérations", "Start / end of operations", f"{_mt(call, 'CARGO_OPS_START') or _mt(call, 'TRANSFER_START') or '—'} → {_mt(call, 'CARGO_OPS_END') or _mt(call, 'TRANSFER_END') or '—'}", source="jalons CARGO_OPS_START / END")),
        table(("Relevé par équipe", "Record per shift"),
              [("Date / équipe", "Date / shift"), ("Moyens (grues, portiques, bennes)", "Means (cranes, gantries, grabs)"), ("Cale / baie / lot", "Hold / bay / lot"), ("Quantité ou mouvements", "Quantity or moves"),
               ("Cadence", "Rate"), ("Arrêts (h)", "Stoppages (h)"), ("Incidents", "Incidents")],
              [], blank_rows=8),
        table(("Arrêts enregistrés", "Stoppages recorded"),
              [("Début", "From"), ("Fin", "To"), ("Cause", "Cause"), ("Imputable à", "Attributable to")],
              [[dt(r["start"].declared_at), dt(r["end"].declared_at) if r["end"] else None, r["cause"].label_fr if r["cause"] else None, r["attribution"] or None] for r in stops],
              source="reports.interruptions"),
        fields(("Quantités constatées", "Quantities established"), [
            F("Pesée à terre (bascule, bande)", "Shore weighing (weighbridge, belt scale)", f"{scale} {unit}" if scale is not None else None, source="Measurement SCALE (SHORE)"),
            F("Pointage terre", "Shore tally", f"{tally} {tunit}" if tally is not None else None, source="Measurement TALLY (SHORE)"),
            F("Unités ou conteneurs endommagés", "Damaged units or containers", wide=True), F("Observations", "Remarks", wide=True),
        ]),
    ]


def build_damage_report(call: PortCall) -> list[dict]:
    """The damage or shortage report: what, where, when, how, by whom seen, the reservation of rights."""
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes")),
        fields(("Constat", "Report"), [
            F("Date et heure du constat", "Date and time of the report"), F("Lieu (cale, pont, quai, aire)", "Place (hold, deck, quay, yard)"),
            F("Objet endommagé ou manquant (cargaison, navire, installation, engin)", "Damaged or missing item (cargo, vessel, facility, equipment)", wide=True),
            F("Description des dommages ou des manquants", "Description of the damage or shortage", wide=True),
            F("Circonstances et cause apparente", "Circumstances and apparent cause", wide=True),
            F("Témoins", "Witnesses"), F("Photos jointes (références)", "Photos attached (references)"),
            F("Mesures conservatoires prises", "Protective measures taken", wide=True),
        ]),
        text(("Réserve de droits", "Reservation of rights"), [
            ("Le présent constat est dressé contradictoirement sans reconnaissance de responsabilité ; chaque partie réserve ses droits.",
             "This report is drawn up jointly without admission of liability; each party reserves its rights."),
        ]),
    ]


def build_blu_agreement(call: PortCall) -> list[dict]:
    """The ship/terminal loading or unloading plan agreement of the BLU Code (appendix 2): the sequence, the
    rates, the deballasting, the stoppages, the communication, agreed and signed by both before the operations."""
    return [
        identification(call, F("Cargaison / quantité", "Cargo / quantity", f"{_cargo(call)} — {_qty(call) or '—'}", source="PortCall.product, quantity"),
                       F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER"), F("Opération", "Operation", _operation(call), source="PortCall.template_codes")),
        table(("Plan convenu — séquence par passe", "Agreed plan — sequence per pour"),
              [("Passe", "Pour"), ("Cale", "Hold"), ("Quantité (t)", "Quantity (t)"), ("Cadence (t/h)", "Rate (t/h)"), ("Déballastage / ballastage pendant", "Deballasting / ballasting during"),
               ("Durée estimée", "Estimated duration"), ("Observations", "Remarks")],
              [], blank_rows=8),
        fields(("Accords", "Agreements"), [
            F("Cadence maximale convenue (t/h)", "Agreed maximum rate (t/h)"), F("Quantité maximale par passe (t)", "Maximum quantity per pour (t)"),
            F("Signal et délai d'arrêt", "Stop signal and stop time"), F("Communication (canal VHF, téléphone)", "Communication (VHF channel, telephone)"),
            F("Nivellement et moyens", "Trimming and means"), F("Tirant d'eau et assiette finaux visés", "Target final draft and trim"),
            F("Conditions d'arrêt (météo, houle, dommages)", "Stop conditions (weather, swell, damage)", wide=True),
        ], note=("Le plan est convenu avant le début des opérations et modifié d'un commun accord ; le navire peut demander l'arrêt à tout moment (Code BLU §3 et §5).",
                 "The plan is agreed before the operations start and changed by mutual agreement; the ship may ask for a stop at any time (BLU Code §3 and §5).")),
    ]


def build_bay_plan(call: PortCall) -> list[dict]:
    """The container bay plan acknowledgement: the lists exchanged (discharge, loading, restow, DG, reefers, out of
    gauge), the EDI messages, the final plan as stowed."""
    return [
        identification(call, F("Mouvements prévus", "Planned moves", _qty(call) if call.quantity_unit in ("MOVES", "BOX", "TEU") else None, source="PortCall.quantity (MOVES / BOX / TEU)"),
                       F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER")),
        table(("Listes et messages échangés", "Lists and messages exchanged"),
              [("Liste / message", "List / message"), ("Référence", "Reference"), ("Reçu le", "Received on"), ("Conteneurs", "Containers"), ("TEU", "TEU"), ("Observations", "Remarks")],
              [["Liste de déchargement / Discharge list (COPRAR)", None, None, None, None, None], ["Plan de chargement prévisionnel / Provisional bay plan (BAPLIE)", None, None, None, None, None],
               ["Restow", None, None, None, None, None], ["Marchandises dangereuses / Dangerous goods", None, None, None, None, None],
               ["Reefers", None, None, None, None, None], ["Hors gabarit / Out of gauge", None, None, None, None, None], ["Plan final tel qu'arrimé / Final plan as stowed", None, None, None, None, None]]),
        fields(("Confirmation du bord", "Ship's confirmation"), [F("Stabilité et contraintes vérifiées", "Stability and stresses checked"), F("Saisissage vérifié", "Lashing checked"),
                                                                  F("Poids vérifiés (VGM)", "Verified gross masses (VGM)"), F("Observations", "Remarks", wide=True)]),
    ]


def build_cargo_info_imsbc(call: PortCall) -> list[dict]:
    """The shipper's cargo information of the IMSBC Code (section 4): the cargo, its group, the moisture content
    and the transportable moisture limit, the hazards, the certificates."""
    return [
        identification(call, F("Chargeur", "Shipper", _party(call, "COM"), source="CallParty COM"), F("Cargaison", "Cargo", _cargo(call), source="PortCall.product"), F("Quantité (t)", "Quantity (t)", _qty(call), source="PortCall.quantity")),
        fields(("Information sur la cargaison (Code IMSBC §4.2)", "Cargo information (IMSBC Code §4.2)"), [
            F("Nom d'expédition de la cargaison en vrac (BCSN)", "Bulk cargo shipping name (BCSN)", _cargo(call) or None, source="PortCall.product"),
            F("Groupe (A, B, C)", "Group (A, B, C)"), F("Classe OMI / risque", "IMO class / hazard"), F("Facteur d'arrimage (m³/t)", "Stowage factor (m³/t)"),
            F("Angle de repos", "Angle of repose"), F("Teneur en humidité (%)", "Moisture content (%)"), F("Limite d'humidité transportable (TML, %)", "Transportable moisture limit (TML, %)"),
            F("Date de l'essai d'humidité", "Date of the moisture test"), F("Date de l'essai de TML", "Date of the TML test"),
            F("Propriétés chimiques pertinentes", "Relevant chemical properties", wide=True), F("Certificats joints", "Certificates attached", wide=True),
        ], note=("L'échantillonnage et les essais suivent le Code IMSBC (section 8) ; pour une cargaison du groupe A, la teneur en humidité est inférieure à la TML.",
                 "Sampling and testing follow the IMSBC Code (section 8); for a group A cargo the moisture content is below the TML.")),
    ]


# ================================================================================ registrations
_register(Form("PAEC", "PAEC", ("Échange d'informations avant l'arrivée (PAEC)", "Pre-arrival exchange of information (PAEC)"),
               ("ISGOTT, 6e édition, 22.2 — échange d'informations navire / terminal avant l'arrivée", "ISGOTT, 6th edition, 22.2 — pre-arrival ship / terminal exchange of information"),
               frozenset({"NAV", "AGE", "TER"}), [("NAV", ("Capitaine", "Master")), ("TER", ("Terminal", "Terminal"))], build_paec,
               family="NAV", answers=("M0:02",), cargo_kinds=frozenset({"LIQUID"}),
               purpose=("Les informations que le navire et le terminal échangent 72 h avant l'arrivée, point par point, avec les confirmations d'ETA et les documents attendus.",
                        "The information the ship and the terminal exchange 72 h before arrival, point by point, with the ETA confirmations and the documents expected.")))
_register(Form("VETTING_CHECKLIST", "VETTING_CHECKLIST", ("Grille de vetting du navire", "Vessel vetting checklist"),
               ("Grilles de vetting des terminaux ; questionnaire OCIMF Q88 / VPQ ; limites du poste paramétrées", "Terminal vetting grids; OCIMF Q88 / VPQ questionnaire; parametrised berth limits"),
               frozenset({"TER", "CAP"}), [("TER", ("Terminal", "Terminal")), ("CAP", ("Capitainerie", "Harbour master"))], build_vetting_checklist,
               family="TER", answers=("M0:06", "REQ:VESSEL_ACCEPTANCE"),
               purpose=("La grille de vetting : chaque limite du poste au regard des données du navire, le statut Y / N / K / Z et l'avis, les éléments documentaires.",
                        "The vetting grid: every berth limit against the vessel's data, the Y / N / K / Z status and the verdict, the documentary items.")))
_register(Form("CARGO_HANDLING_PLAN", "CARGO_HANDLING_PLAN", ("Plan de manutention de la cargaison", "Cargo handling plan"),
               ("Plans de manutention des terminaux pétroliers ; ISGOTT, 6e édition (plan de transfert, alignement, scellés)", "Oil terminal cargo handling plans; ISGOTT, 6th edition (transfer plan, line-up, seals)"),
               frozenset({"TER"}), [("TER", ("Préparé par — terminal", "Prepared by — terminal")), ("NAV", ("Pris connaissance — navire", "Acknowledged — ship"))], build_cargo_handling_plan, landscape=True,
               family="TER", answers=("M1:1.03", "M2:2.03"), cargo_kinds=frozenset({"LIQUID"}),
               purpose=("Le plan de manutention du terminal : lots et citernes du bord, bacs à terre, déplacement de ligne, alignement et scellés, comparaison des instruments, permanences, données des bacs.",
                        "The terminal's cargo handling plan: parcels and ship tanks, shore tanks, line displacement, line-up and seals, instrument comparison, duties, tank data.")))
_register(Form("DRAFT_SURVEY", "DRAFT_SURVEY_REPORT", ("Rapport de draft survey", "Draft survey report"),
               ("Code de procédures uniformes pour les draft surveys (CEE-ONU) ; pratique des inspecteurs", "UNECE code of uniform standards and procedures for draught surveys; surveyors' practice"),
               frozenset({"INS"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Capitaine / chef officier", "Master / chief officer")), ("TER", ("Terminal", "Terminal"))], build_draft_survey,
               family="INS", templates=frozenset({"MB1", "MB2"}), answers=("MB1:B1.13", "MB2:B2.14"), cargo_kinds=DRY,
               purpose=("Le rapport de draft survey : tirants d'eau, déplacements, déductions, quantité par différence, avec les valeurs bord, terre et inspecteur.",
                        "The draft survey report: drafts, displacements, deductibles, quantity by difference, with the ship, shore and surveyor figures.")))
_register(Form("CARGO_MANIFEST", "CARGO_MANIFEST", ("Manifeste de cargaison", "Cargo manifest"),
               ("Convention FAL de l'OMI, formulaire 2 (déclaration de cargaison)", "IMO FAL Convention, form 2 (cargo declaration)"),
               frozenset({"AGE", "NAV"}), [("NAV", ("Capitaine ou agent autorisé", "Master or authorised agent"))], build_cargo_manifest,
               family="AGE", answers=("MB1:B1.01", "MC1:C1.03", "MG1:G1.01", "MR1:R1.01", "MX1:X1.01"), cargo_kinds=NOT_LIQUID,
               purpose=("Le manifeste de cargaison et ses listes : connaissements, marques, colis ou unités, poids, chargeur et destinataire.",
                        "The cargo manifest and its lists: bills of lading, marks, packages or units, weights, shipper and consignee.")))
_register(Form("STOWAGE_PLAN", "STOWAGE_PLAN", ("Plan d'arrimage / de chargement ou de déchargement", "Stowage / loading or discharge plan"),
               ("Code BLU §3 (vrac) ; Code CSS et manuel d'assujettissement (divers, roulier)", "BLU Code §3 (bulk); CSS Code and cargo securing manual (general cargo, ro-ro)"),
               frozenset({"NAV", "AGE"}), [("NAV", ("Capitaine / chef officier", "Master / chief officer")), ("TER", ("Terminal", "Terminal"))], build_stowage_plan,
               family="NAV", templates=frozenset({"MB1", "MB2", "MG1", "MR1"}), answers=("MB1:B1.02", "MB2:B2.03", "MG1:G1.03", "MR1:R1.02"), cargo_kinds=NOT_LIQUID,
               purpose=("Le plan par cale, baie ou pont : cargaison, quantités, séquence, cadence, ballastage, contraintes et accords.",
                        "The plan per hold, bay or deck: cargo, quantities, sequence, rate, ballast, limits and agreements.")))
_register(Form("DG_DECLARATION", "DG_DECLARATION", ("Déclaration de marchandises dangereuses", "Dangerous goods declaration"),
               ("Code IMDG, chapitre 5.4 ; Convention FAL, formulaire 7", "IMDG Code, chapter 5.4; FAL Convention, form 7"),
               frozenset({"AGE", "NAV"}), [("AGE", ("Chargeur / agent", "Shipper / agent")), ("NAV", ("Capitaine", "Master"))], build_dg_declaration,
               family="AGE", answers=("MC1:C1.02", "MG1:G1.02", "MX1:X1.02"), cargo_kinds=NOT_LIQUID,
               purpose=("La déclaration des marchandises dangereuses à bord : positions, n° ONU, classes, emballages, polluants marins.",
                        "The declaration of the dangerous goods on board: positions, UN numbers, classes, packagings, marine pollutants.")))
_register(Form("HOLD_INSPECTION", "HOLD_INSPECTION", ("Rapport d'inspection des cales / de la cargaison", "Hold / cargo inspection report"),
               ("Pratique des inspecteurs de cargaisons sèches ; Code BLU ; Code IMSBC", "Dry cargo surveyors' practice; BLU Code; IMSBC Code"),
               frozenset({"INS", "TER"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Capitaine", "Master")), ("TER", ("Terminal", "Terminal"))], build_hold_inspection,
               family="INS", templates=frozenset({"MB1", "MB2", "MG1", "MR1"}), answers=("MB1:B1.06", "MB2:B2.05", "MG1:G1.05", "MR1:R1.04"), cargo_kinds=NOT_LIQUID,
               purpose=("L'inspection des cales ou de la cargaison avant les opérations : propreté, étanchéité, réserves, acceptation.",
                        "The inspection of the holds or the cargo before the operations: cleanliness, tightness, remarks, acceptance.")))
_register(Form("TALLY_SHEET", "TALLY_SHEET", ("Feuille de pointage et constat de réception", "Tally sheet and out-turn statement"),
               ("Pratique du pointage contradictoire ; constat de réception (out-turn)", "Joint tally practice; out-turn statement"),
               frozenset({"TER", "INS"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship")), ("INS", ("Inspecteur", "Surveyor"))], build_tally_sheet,
               family="INS", templates=frozenset({"MG1", "MR1", "MC1"}), answers=("MG1:G1.07", "MG1:G1.10", "MR1:R1.06", "MR1:R1.09"), cargo_kinds=frozenset({"GENERAL", "RORO", "OTHER", "CONTAINER"}),
               purpose=("Le pointage des colis ou unités par le navire et par la terre, les écarts, les dommages, le constat de réception contre le manifeste.",
                        "The tally of the packages or units by the ship and by the shore, the differences, the damage, the out-turn against the manifest.")))
_register(Form("MATES_RECEIPT", "MATES_RECEIPT", ("Reçu de bord (mate's receipt)", "Mate's receipt"),
               ("Pratique maritime — reçu de bord, préalable au connaissement", "Maritime practice — mate's receipt before the bill of lading"),
               frozenset({"NAV"}), [("NAV", ("Chef officier / capitaine", "Chief officer / master")), ("AGE", ("Agent / chargeur", "Agent / shipper"))], build_mates_receipt,
               family="NAV", templates=frozenset({"MB2", "MG1"}), answers=("MB2:B2.15", "MG1:G1.11"), cargo_kinds=NOT_LIQUID,
               purpose=("Le reçu de bord de la cargaison chargée, avec les réserves du bord, avant l'émission du connaissement.",
                        "The receipt of the cargo loaded, with the ship's remarks, before the bill of lading is issued.")))
_register(Form("OUTTURN_REPORT", "OUTTURN_REPORT", ("Rapport d'opération du terminal (out-turn)", "Terminal operation report (out-turn)"),
               ("Rapports d'opération des terminaux ; pesées et pointages", "Terminal operation reports; weighings and tallies"),
               frozenset({"TER"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship"))], build_outturn_report,
               family="TER", templates=frozenset({"MB1", "MB2", "MC1", "MG1", "MR1", "MX1"}), answers=("MB1:B1.14", "MC1:C1.11", "MX1:X1.08"), cargo_kinds=NOT_LIQUID,
               purpose=("Le rapport d'opération du terminal : relevé par équipe, arrêts, quantités pesées ou pointées, unités endommagées.",
                        "The terminal's operation report: record per shift, stoppages, weighed or tallied quantities, damaged units.")))
_register(Form("CARGO_DAMAGE", "CARGO_DAMAGE_REPORT", ("Constat de dommages ou de manquants", "Damage or shortage report"),
               ("Usage maritime — constat contradictoire, réserve de droits", "Maritime practice — joint report, reservation of rights"),
               frozenset({"INS", "TER", "NAV", "AGE"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Navire", "Ship")), ("TER", ("Terminal", "Terminal"))], build_damage_report,
               family="INS", answers=("MB1:B1.15", "MC1:C1.12", "MG1:G1.12", "MR1:R1.10"),
               purpose=("Le constat contradictoire de dommages ou de manquants, avec réserve de droits.", "The joint damage or shortage report, with reservation of rights.")))
_register(Form("BLU_AGREEMENT", "BLU_AGREEMENT", ("Accord de chargement / déchargement navire-terminal (Code BLU)", "Ship/terminal loading / unloading agreement (BLU Code)"),
               ("Code BLU de l'OMI, §3 et appendice 2 — plan de chargement ou de déchargement", "IMO BLU Code, §3 and appendix 2 — loading or unloading plan"),
               frozenset({"TER", "NAV"}), [("NAV", ("Capitaine", "Master")), ("TER", ("Représentant du terminal", "Terminal representative"))], build_blu_agreement,
               family="TER", templates=frozenset({"MB1", "MB2"}), answers=("MB1:B1.07", "MB2:B2.07"), cargo_kinds=DRY,
               purpose=("Le plan de chargement ou de déchargement convenu entre le vraquier et le terminal : passes, cadences, déballastage, arrêts.",
                        "The loading or unloading plan agreed between the bulk carrier and the terminal: pours, rates, deballasting, stoppages.")))
_register(Form("BAY_PLAN", "BAY_PLAN", ("Plan de chargement conteneurs (bay plan)", "Container bay plan"),
               ("Pratique des terminaux à conteneurs — messages BAPLIE / COPRAR ; SOLAS VI (VGM)", "Container terminal practice — BAPLIE / COPRAR messages; SOLAS VI (VGM)"),
               frozenset({"AGE", "NAV"}), [("NAV", ("Capitaine / chef officier", "Master / chief officer")), ("TER", ("Planificateur du terminal", "Terminal planner"))], build_bay_plan,
               family="AGE", templates=frozenset({"MC1"}), answers=("MC1:C1.01", "MC1:C1.10"), cargo_kinds=CONTAINER,
               purpose=("Les listes et plans échangés pour les opérations conteneurs et le plan final tel qu'arrimé.",
                        "The lists and plans exchanged for the container operations and the final plan as stowed.")))
_register(Form("CARGO_INFO_IMSBC", "CARGO_INFO_IMSBC", ("Déclaration de cargaison du chargeur (Code IMSBC)", "Shipper's cargo declaration (IMSBC Code)"),
               ("Code IMSBC, section 4 — information sur la cargaison", "IMSBC Code, section 4 — cargo information"),
               frozenset({"AGE", "COM"}), [("COM", ("Chargeur", "Shipper")), ("NAV", ("Capitaine", "Master"))], build_cargo_info_imsbc,
               family="AGE", templates=frozenset({"MB2"}), answers=("MB2:B2.01",), cargo_kinds=DRY,
               purpose=("L'information du chargeur sur la cargaison en vrac : groupe, humidité, TML, risques, certificats.",
                        "The shipper's information on the bulk cargo: group, moisture, TML, hazards, certificates.")))
