"""Forms issued by the terminal or depot: vetting request summary, berth readiness attestation, shore tank
measurement report, terminal receipt, SPM inspection report, double banking study and emergency unberthing plan."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _mt,
    _operation,
    _parties,
    _partner,
    _party,
    _quantity,
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


# ------------------------------------------------------------------------------------------------ vetting request
def build_vetting_request(call: PortCall) -> list[dict]:
    v = call.vessel
    req = call.requests.filter(type__code="VESSEL_ACCEPTANCE").order_by("-created_at").first()
    data = (req.data if req else {}) or {}
    return [
        fields(("Navire proposé", "Vessel proposed"), [
            F("Nom / numéro OMI", "Name / IMO number", _vessel(call), source="Vessel.name, imo"), F("Pavillon / type / année", "Flag / type / year", " — ".join(filter(None, [v.flag, v.vessel_type, str(v.built_year) if v.built_year else ""])) or None, source="Vessel.flag, vessel_type, built_year"),
            F("Port en lourd (t) / LOA (m) / largeur (m)", "Deadweight (t) / LOA (m) / beam (m)", f"{v.dwt or '—'} / {v.loa_m or '—'} / {v.beam_m or '—'}", source="Vessel.dwt, loa_m, beam_m"),
            F("Armateur / gestionnaire", "Owner / manager", _parties(call, "COM"), source="CallParty COM actives"), F("Société de classification / classe", "Classification society / class"),
            F("Produit / quantité", "Product / quantity", f"{data.get('product') or call.product or '—'} — {data.get('quantity') or _quantity(call) or '—'}", source="ServiceRequest.data, PortCall"),
            F("Poste sollicité", "Requested berth", data.get("requested_berth") or _where(call), source="ServiceRequest.data[requested_berth]"),
        ]),
        fields(("Éléments du vetting", "Vetting elements"), [
            F("Rapport SIRE 2.0 / CDI — date, inspecteur, observations ouvertes", "SIRE 2.0 / CDI report — date, inspector, open observations", data.get("inspection") or None, wide=True, source="ServiceRequest.data[inspection]"),
            F("Historique PSC (détentions, déficiences) — 36 mois", "PSC history (detentions, deficiencies) — 36 months", data.get("psc_history") or None, wide=True, source="ServiceRequest.data[psc_history]"),
            F("Trois dernières cargaisons", "Last three cargoes", data.get("last_cargoes") or None, wide=True, source="ServiceRequest.data[last_cargoes]"),
            F("Incidents, avaries, pollution — 5 ans", "Incidents, casualties, pollution — 5 years", wide=True), F("Âge, changements de pavillon ou de gestionnaire", "Age, flag or manager changes"),
            F("Compatibilité avec le poste (dimensions, collecteur, défenses, tirant d'eau)", "Compatibility with the berth (dimensions, manifold, fenders, draft)", wide=True),
            F("Résultat du vetting interne et conditions proposées", "Internal vetting result and proposed conditions", data.get("vetting_result") or None, wide=True, source="ServiceRequest.data[vetting_result]"),
        ]),
        text(("Demande", "Request"), [
            ("Le terminal demande à l'autorité portuaire l'acceptation du navire ci-dessus pour l'opération indiquée, au vu de son vetting interne dont le résultat est joint ; aucun poste n'est attribué à un navire non accepté.",
             "The terminal requests the port authority to accept the vessel above for the stated operation, on the basis of its internal vetting whose result is attached; no berth is assigned to a vessel not accepted."),
        ], note=("OCIMF SIRE 2.0 / CDI ; Tanker Management and Self Assessment (TMSA) ; politique de vetting du terminal.", "OCIMF SIRE 2.0 / CDI; Tanker Management and Self Assessment (TMSA); the terminal's vetting policy.")),
    ]


_register(Form("VETTING_REQUEST", "VETTING_REPORT", ("Demande d'acceptation du navire — synthèse du vetting", "Vessel acceptance request — vetting summary"),
               ("OCIMF SIRE 2.0 / CDI ; TMSA ; politique de vetting du terminal", "OCIMF SIRE 2.0 / CDI; TMSA; the terminal's vetting policy"),
               frozenset({"TER"}), [("TER", ("Terminal — responsable vetting", "Terminal — vetting officer")), ("CAP", ("Autorité — reçu", "Authority — received"))],
               build_vetting_request, family="TER", answers=("M0:06",),
               purpose=("La synthèse du vetting interne du terminal jointe à la demande d'acceptation du navire.", "The summary of the terminal's internal vetting attached to the vessel acceptance request.")))


# ------------------------------------------------------------------------------------------------ berth readiness
def build_berth_readiness(call: PortCall) -> list[dict]:
    return [
        identification(call, F("ETB / ATB", "ETB / ATB", dt(call.atb) or dt(call.etb), source="PortCall.atb, etb"), F("Opération", "Operation", _operation(call), source="PortCall.template_codes")),
        checklist(("Poste", "Berth"), [
            ("Poste libre, dégagé, éclairé ; défenses contrôlées", "Berth free, clear, lit; fenders checked"),
            ("Bras ou flexibles disponibles, contrôlés, à l'essai en date ; réducteurs adaptés au collecteur", "Arms or hoses available, checked, tests in date; reducers fitted to the manifold"),
            ("Bacs, lignes et vannes alignés ; creux disponible ou produit prêt", "Tanks, lines and valves lined up; ullage available or product ready"),
            ("Dalots et plateaux de rétention du quai obturés / vidés", "Quay scuppers and drip trays plugged / emptied"),
            ("Kit antipollution, barrage flottant et moyens de récupération disponibles", "Spill kit, boom and recovery means available"),
            ("Moyens incendie du poste prêts (lances, mousse, canons, hydrants en pression)", "Berth fire-fighting means ready (hoses, foam, monitors, hydrants charged)"),
            ("Dispositif d'arrêt d'urgence (ESD) armé et testé", "Emergency shutdown (ESD) armed and tested"),
            ("Accès et passerelle, éclairage, zone de sûreté et contrôle d'accès en place", "Access and gangway, lighting, security zone and access control in place"),
            ("Communication avec le navire convenue (VHF, téléphone) ; personnel de permanence désigné", "Communication with the ship agreed (VHF, telephone); duty personnel assigned"),
            ("Prévisions météo et marée compatibles avec les limites du poste", "Weather and tide forecasts within the berth limits"),
        ], columns=[("Fait", "Done"), ("S.O.", "N/A")]),
        fields(("Attestation", "Attestation"), [
            F("Poste mis en sécurité le (date, heure)", "Berth made safe on (date, time)"), F("Responsable du poste", "Berth supervisor"),
            F("Réserves", "Reservations", wide=True),
        ], note=("ISGOTT 6e édition, chapitre 15 et 16 (préparation du poste) et liste de contrôle navire/terre, partie 1B et 3 ; règlement d'exploitation du terminal.",
                 "ISGOTT 6th edition, chapters 15 and 16 (berth preparation) and ship/shore safety checklist, parts 1B and 3; terminal operating regulations.")),
    ]


_register(Form("BERTH_READINESS", "BERTH_READINESS", ("Attestation de mise en sécurité du poste", "Berth readiness and safety attestation"),
               ("ISGOTT 6e édition, chapitres 15–16 ; règlement d'exploitation du terminal", "ISGOTT 6th edition, chapters 15–16; terminal operating regulations"),
               frozenset({"TER"}), [("TER", ("Responsable du poste", "Berth supervisor")), ("CAP", ("Capitainerie — informée", "Harbour master — informed"))],
               build_berth_readiness, family="TER", answers=("M0:31", "M1:1.03"),
               purpose=("L'attestation du terminal que le poste est prêt et mis en sécurité avant l'accostage.", "The terminal's attestation that the berth is ready and made safe before berthing.")))


# ------------------------------------------------------------------------------------------------ shore tanks
def build_shore_tank_report(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit", "Product", call.product or None, source="PortCall.product"), F("Opération", "Operation", _operation(call), source="PortCall.template_codes")),
        fields(("Relevé", "Measurement"), [
            F("Nature : avant transfert ☐ après transfert ☐", "Kind: before transfer ☐ after transfer ☐"), F("Date et heure", "Date and time"),
            F("Méthode : jaugeage manuel ☐ ATG ☐ compteurs ☐", "Method: manual gauging ☐ ATG ☐ meters ☐"), F("Tables de bac (date d'étalonnage)", "Tank tables (calibration date)"),
            F("Inspecteur présent", "Surveyor present", _party(call, "INS"), source="CallParty INS active"), F("Opérateur terminal", "Terminal operator"),
        ]),
        table(("Bacs", "Tanks"),
              [("Bac", "Tank"), ("Niveau (mm)", "Level (mm)"), ("Eau libre (mm)", "Free water (mm)"), ("Temp. (°C)", "Temp. (°C)"), ("Densité à 15 °C", "Density at 15 °C"), ("Volume brut (m³)", "Gross volume (m³)"), ("VCF", "VCF"), ("Volume à 15 °C (m³)", "Volume at 15 °C (m³)"), ("Masse (t)", "Mass (t)")],
              [], blank_rows=8),
        table(("Compteurs (le cas échéant)", "Meters (if any)"),
              [("Compteur", "Meter"), ("Index début", "Opening reading"), ("Index fin", "Closing reading"), ("Facteur", "Meter factor"), ("Volume (m³)", "Volume (m³)"), ("Étalonnage (date)", "Calibration (date)")], [], blank_rows=3),
        fields(("Totaux", "Totals"), [
            F("Total bacs à 15 °C (m³) / masse (t)", "Total tanks at 15 °C (m³) / mass (t)"), F("Lignes : pleines ☐ vides ☐ — volume (m³)", "Lines: full ☐ empty ☐ — volume (m³)"),
            F("Quantité terre retenue (unité)", "Shore figure retained (unit)"), F("Observations", "Remarks", wide=True),
        ], note=("API MPMS chapitres 3 (jaugeage), 7 (température), 12 (calculs) ; EI HM ; tables ASTM D1250. La quantité terre est saisie dans le registre (onglet Mesures) et comparée à la quantité bord.",
                 "API MPMS chapters 3 (gauging), 7 (temperature), 12 (calculations); EI HM; ASTM D1250 tables. The shore figure is entered in the registry (Quantities tab) and compared with the ship figure.")),
    ]


_register(Form("SHORE_TANK_REPORT", "SHORE_TANK_REPORT", ("Relevé des bacs et compteurs à terre", "Shore tank and meter measurement report"),
               ("API MPMS chapitres 3, 7 et 12 ; EI HM ; ASTM D1250", "API MPMS chapters 3, 7 and 12; EI HM; ASTM D1250"),
               frozenset({"TER"}), [("TER", ("Terminal", "Terminal")), ("INS", ("Inspecteur — témoin", "Surveyor — witness"))],
               build_shore_tank_report, family="TER", templates=frozenset({"M1", "M2"}), answers=("M1:1.06", "M2:2.08"),
               purpose=("Le relevé des bacs récepteurs ou expéditeurs et des compteurs, avant et après le transfert.", "The reading of the receiving or shipping tanks and the meters, before and after the transfer.")))


# ------------------------------------------------------------------------------------------------ terminal receipt
def build_terminal_receipt(call: PortCall) -> list[dict]:
    rows = []
    for m in call.measurements.filter(kind__in=["INITIAL", "FINAL", "BL"]).order_by("created_at"):
        values = m.current_values()
        rows.append([m.get_kind_display(), m.product or call.product or "—", m.unit,
                     *[f"{values[p].value}" if p in values else None for p in ("SHIP", "SHORE", "SURVEYOR")]])
    return [
        identification(call, F("Produit / quantité nominée", "Product / nominated quantity", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity"),
                       F("Début / fin du transfert", "Transfer start / end", f"{_mt(call, 'TRANSFER_START') or '—'} → {_mt(call, 'TRANSFER_END') or '—'}", source="jalons TRANSFER_START, TRANSFER_END")),
        table(("Quantités du registre", "Registry quantities"),
              [("Mesure", "Measurement"), ("Produit", "Product"), ("Unité", "Unit"), ("Bord", "Ship"), ("Terre", "Shore"), ("Inspecteur", "Surveyor")], rows, blank_rows=1,
              source="Measurement et MeasurementValue (valeurs courantes par partie)"),
        fields(("Réception", "Receipt"), [
            F("Quantité reçue dans les bacs (unité, base de calcul)", "Quantity received into tanks (unit, basis)"), F("Bacs récepteurs", "Receiving tanks"),
            F("Température moyenne (°C) / densité à 15 °C", "Average temperature (°C) / density at 15 °C"), F("Eau libre et sédiments (BS&W)", "Free water and sediment (BS&W)"),
            F("Écart bord/terre (quantité, %)", "Ship/shore difference (quantity, %)"), F("Dans la tolérance ☐ hors tolérance — lettre de protestation ☐", "Within tolerance ☐ outside tolerance — letter of protest ☐"),
            F("Observations", "Remarks", wide=True),
        ]),
        text(("Bon de réception", "Receipt"), [
            ("Le terminal certifie avoir reçu du navire ci-dessus la quantité indiquée, relevée contradictoirement en présence de l'inspecteur ; le présent bon ne vaut pas accord sur les quantités qui font l'objet d'une contestation ouverte.",
             "The terminal certifies that it received from the vessel above the stated quantity, measured jointly in the presence of the surveyor; this receipt is no agreement on quantities under an open dispute."),
        ]),
    ]


_register(Form("TERMINAL_RECEIPT", "TERMINAL_RECEIPT", ("Bon de réception du terminal", "Terminal receipt"),
               ("Pratique des terminaux (outturn / discharge certificate) ; API MPMS chapitre 17", "Terminal practice (outturn / discharge certificate); API MPMS chapter 17"),
               frozenset({"TER"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Capitaine", "Master")), ("INS", ("Inspecteur", "Surveyor"))],
               build_terminal_receipt, family="TER", templates=frozenset({"M1"}), answers=("M1:1.17",),
               purpose=("Le bon par lequel le terminal reconnaît la quantité reçue dans ses bacs.", "The receipt by which the terminal acknowledges the quantity received into its tanks.")))


# ------------------------------------------------------------------------------------------------ SPM inspection
def build_spm_inspection(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Bouée / poste", "Buoy / berth", _where(call), source="PortCall.berth"), F("Dernière inspection complète (date, organisme)", "Last full inspection (date, body)")),
        table(("Inspection avant l'escale", "Pre-call inspection"),
              [("Élément", "Item"), ("Contrôle effectué (méthode, date)", "Check carried out (method, date)"), ("État : conforme ☐ réserve ☐", "Condition: compliant ☐ reservation ☐"), ("Observations", "Remarks")],
              [["Corps de bouée, flottabilité, feux et signalisation / Buoy body, buoyancy, lights and marks", None, None, None],
               ["Système d'amarrage : aussières, manilles, chaînes, bouées de soutien / Mooring system: hawsers, shackles, chains, support buoys", None, None, None],
               ["Ancrage et lignes d'ancre / Anchor legs", None, None, None],
               ["Flexibles flottants : état, pression d'essai, dates / Floating hoses: condition, test pressure, dates", None, None, None],
               ["Flexibles sous-marins et PLEM / Subsea hoses and PLEM", None, None, None],
               ["Vannes, raccords, coupleur de rupture / Valves, couplings, breakaway coupling", None, None, None],
               ["Tourelle / table de rotation, joint tournant / Turntable and swivel", None, None, None],
               ["Moyens d'assistance : remorqueurs, vedettes, équipe d'amarrage / Assistance means: tugs, launches, mooring crew", None, None, None]],
              blank_rows=2),
        fields(("Conclusion", "Conclusion"), [
            F("Bouée apte à recevoir le navire ☐ sous réserve ☐ inapte ☐", "Buoy fit to receive the vessel ☐ with reservations ☐ unfit ☐"), F("Limites d'exploitation rappelées (houle, vent, courant)", "Operating limits recalled (swell, wind, current)"),
            F("Inspecté par (nom, fonction)", "Inspected by (name, capacity)"), F("Date et heure", "Date and time"),
        ], note=("OCIMF — Single Point Mooring Maintenance and Operations Guide (SMOG) et Guide to Purchasing, Manufacturing and Testing of Loading and Discharge Hoses for Offshore Moorings (GMPHOM).",
                 "OCIMF — Single Point Mooring Maintenance and Operations Guide (SMOG) and Guide to Purchasing, Manufacturing and Testing of Loading and Discharge Hoses for Offshore Moorings (GMPHOM).")),
    ]


_register(Form("SPM_INSPECTION", "SPM_DOC", ("Rapport d'inspection de la bouée (SPM)", "SPM buoy inspection report"),
               ("OCIMF SMOG ; OCIMF GMPHOM (flexibles)", "OCIMF SMOG; OCIMF GMPHOM (hoses)"),
               frozenset({"TER"}), [("TER", ("Exploitant de la bouée", "Buoy operator")), ("CAP", ("Capitainerie — reçu", "Harbour master — received"))],
               build_spm_inspection, family="TER", templates=frozenset({"MA2"}), answers=("MA2:A2.01",),
               purpose=("Le rapport d'inspection de la bouée, des flexibles et du système d'amarrage avant l'escale.", "The inspection report of the buoy, hoses and mooring system before the call.")))


# ------------------------------------------------------------------------------------------------ double banking study
def build_double_banking_study(call: PortCall) -> list[dict]:
    partner = call.linked_call
    pv = partner.vessel if partner else None
    return [
        identification(call, F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"),
                       F("Configuration : ce navire intérieur ☐ extérieur ☐", "Configuration: this vessel inner ☐ outer ☐", {"INNER": "intérieur / inner", "OUTER": "extérieur / outer"}.get(call.link_kind), source="PortCall.link_kind")),
        table(("Compatibilité des deux navires", "Compatibility of the two vessels"),
              [("Caractéristique", "Particular"), ("Ce navire", "This vessel"), ("Navire partenaire", "Partner vessel"), ("Compatible ☐ / réserve", "Compatible ☐ / reservation")],
              [["LOA / largeur (m) / LOA / beam (m)", f"{call.vessel.loa_m or '—'} / {call.vessel.beam_m or '—'}", f"{pv.loa_m or '—'} / {pv.beam_m or '—'}" if pv else None, None],
               ["Port en lourd (t) / Deadweight (t)", str(call.vessel.dwt) if call.vessel.dwt else None, str(pv.dwt) if pv and pv.dwt else None, None],
               ["Franc-bord et différence prévue / Freeboard and expected difference", None, None, None],
               ["Tirant d'eau arrivée / départ / Draft arrival / departure", None, None, None],
               ["Position et hauteur du collecteur / Manifold position and height", None, None, None],
               ["Points d'amarrage, treuils, aussières / Mooring points, winches, lines", None, None, None],
               ["Dispositif d'amarrage du système combiné / Mooring arrangement of the combined system", None, None, None]],
              blank_rows=1, source="Vessel (ce navire et partenaire) : loa_m, beam_m, dwt"),
        fields(("Analyse d'amarrage du système combiné", "Mooring analysis of the combined system"), [
            F("Conditions extrêmes retenues (vent, houle, courant)", "Extreme conditions considered (wind, swell, current)", wide=True), F("Charges maximales dans les amarres et les défenses", "Maximum loads in lines and fenders"),
            F("Méthode / logiciel et référence de l'étude", "Method / software and study reference"), F("Seuils météo de la configuration (plus restrictifs)", "Weather thresholds of the configuration (more restrictive)"),
        ]),
        table(("Matrice des opérations simultanées", "Simultaneous operations matrix"),
              [("Opération", "Operation"), ("Navire intérieur", "Inner vessel"), ("Navire extérieur", "Outer vessel"), ("Autorisée ☐ / interdite ☐ / conditions", "Allowed ☐ / prohibited ☐ / conditions")],
              [["Transfert cargaison / Cargo transfer", None, None, None], ["Ballastage / Ballast", None, None, None], ["Soutage / Bunkering", None, None, None],
               ["Travaux, dégazage / Repairs, gas-freeing", None, None, None], ["Relève, avitaillement / Crew change, stores", None, None, None]], blank_rows=1),
        fields(("Plan de déhalage d'urgence", "Emergency unberthing plan"), [
            F("Scénarios déclencheurs", "Triggering scenarios", wide=True), F("Moyens (remorqueurs, pilote, lamaneurs) et délais de mise en œuvre", "Means (tugs, pilot, mooring gang) and lead times", wide=True),
            F("Responsabilités nominatives (terminal, navires, capitainerie)", "Named responsibilities (terminal, vessels, harbour master)", wide=True), F("Ordre de largage et séquence", "Release order and sequence", wide=True),
            F("Plan d'accès, de coupée et d'évacuation des deux équipages", "Access, gangway and evacuation plan of both crews", wide=True),
        ], note=("OCIMF Mooring Equipment Guidelines (MEG4) ; OCIMF Ship to Ship Transfer Guide (amarrage à couple) ; ISGOTT 6e édition, chapitre 23.",
                 "OCIMF Mooring Equipment Guidelines (MEG4); OCIMF Ship to Ship Transfer Guide (alongside mooring); ISGOTT 6th edition, chapter 23.")),
    ]


_register(Form("DOUBLE_BANKING_STUDY", "DOUBLE_BANKING_DOC", ("Dossier d'accostage à couple — compatibilité, amarrage, déhalage d'urgence", "Double banking file — compatibility, mooring, emergency unberthing"),
               ("OCIMF MEG4 ; OCIMF Ship to Ship Transfer Guide ; ISGOTT 6e édition, chapitre 23", "OCIMF MEG4; OCIMF Ship to Ship Transfer Guide; ISGOTT 6th edition, chapter 23"),
               frozenset({"TER"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Capitaine — ce navire", "Master — this vessel")), ("NAV", ("Capitaine — navire partenaire", "Master — partner vessel")), ("CAP", ("Capitainerie", "Harbour master"))],
               build_double_banking_study, family="TER", templates=frozenset({"M9"}), needs_link=True, answers=("M9:9.03", "M9:9.04", "M9:9.06", "M9:9.08"),
               purpose=("L'étude de compatibilité, l'analyse d'amarrage, la matrice des opérations simultanées et le plan de déhalage d'urgence de l'accostage à couple.",
                        "The compatibility study, mooring analysis, simultaneous operations matrix and emergency unberthing plan of the double banking.")))
