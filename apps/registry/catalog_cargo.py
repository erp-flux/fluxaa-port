"""Catalogue extension of version 1.5 (FLX-CDC-002 §6.13): the platform is open to every cargo and every vessel.

Operation templates for dry bulk, containers, general cargo, ro-ro and any other call; the milestones, document
types and hold-point requirements they need; the green lights of the common base (naval base, terminal,
principal) beside the harbour master's; the standard forms that come from the terminals' own practice (pre-arrival
exchange of information, vetting checklist against the berth limits, cargo handling plan).

Everything here is loaded by ``bootstrap_port`` like the rest of the catalogue; ports installed before 1.5
receive it through the data migration ``registry.0017``.
"""
from __future__ import annotations

QUAY = ["JETTY", "SPM"]
NOT_LIQUID = ["DRY", "CONTAINER", "GENERAL", "RORO", "OTHER"]


def _t(num, role, nature, timing, crit, fr, en, *, co=(), joint=False, conf="N2", req="", side="", ms=(), doc="",
       auto="", cont=False, na=True, kinds=(), basis="", per_vessel=False, green=False, cargo=()):
    return {
        "number": num, "role": role, "co_roles": list(co), "joint": joint, "nature": nature, "timing": timing,
        "criticality": crit, "confidentiality": conf, "title_fr": fr, "title_en": en, "request_type_code": req,
        "request_side": side, "milestone_codes": list(ms), "document_type_code": doc, "auto_event": auto,
        "continuous": cont, "not_applicable_allowed": na, "berth_kinds": list(kinds), "per_vessel": per_vessel,
        "hold_basis": basis or ("PRO-MAR-001 — point d'arrêt / hold point" if crit == "B" else ""),
        "green_light": green, "cargo_kinds": list(cargo),
    }


# --------------------------------------------------------------------------------------------
# Green lights of the common base (EXG-R-03): the harbour master's (M0:09, a decision on the GREEN_LIGHT
# request) is joined by the naval base's, the terminal's and the principal's — each a blocking confirmation of
# its role, withdrawable with a reason, shown on the call's green-light panel
# --------------------------------------------------------------------------------------------
GREEN_LIGHT_TASKS = [
    ("M0.1", _t("09b", "SUR", "C", "ETA-24h", "B",
                "Donner le feu vert de la base navale / sûreté à l'entrée du navire dans les eaux du port",
                "Give the naval base / security green light for the vessel's entry into the port waters",
                green=True, basis="Sûreté portuaire — contrôle d'accès des navires (ISPS, autorité navale)")),
    ("M0.1", _t("09c", "TER", "C", "ETB-6h", "B",
                "Donner le feu vert du terminal : bacs ou aires, lignes ou moyens de manutention et personnel prêts",
                "Give the terminal's green light: tanks or yards, lines or handling means and staff ready",
                green=True, kinds=QUAY, basis="PRO-MAR-001 — mise à disposition du terminal")),
    ("M0.1", _t("09d", "COM", "C", "ETB-6h", "B",
                "Donner le feu vert commercial : cargaison libérée, instruction d'opérer donnée au navire et au terminal",
                "Give the commercial green light: cargo released, instruction to operate given to the vessel and the terminal",
                green=True, basis="Charte-partie / contrat de vente — libération de la cargaison")),
    # berth safety of the non-tanker calls (the tanker's own line, M0:31, is liquid-only)
    ("M0.3", _t("31b", "TER", "C", "T0", "B",
                "Confirmer la mise en sécurité du poste : aires balisées, éclairage, moyens de levage contrôlés, moyens incendie, accès",
                "Confirm berth safety: areas marked out, lighting, lifting gear checked, firefighting means, access",
                kinds=QUAY, cargo=NOT_LIQUID, basis="Convention OIT n° 152 / Recueil BIT — sécurité et santé dans les ports")),
]
# the harbour master's green light and the tanker-only lines of the common base
GREEN_LIGHT_EXISTING = {"09"}
LIQUID_ONLY_M0 = {"29", "31"}

HOLD_POINT_ADDITIONS = {
    "MOVEMENT_AUTH": ["M0:09b"],
    "BERTHING": ["M0:09b"],
    "START_TRANSFER": ["M0:09c", "M0:09d", "M0:31b",
                       "MB1:B1.04", "MB1:B1.05", "MB1:B1.06", "MB1:B1.07",
                       "MB2:B2.05", "MB2:B2.06", "MB2:B2.07",
                       "MC1:C1.02", "MC1:C1.05",
                       "MG1:G1.03", "MG1:G1.05",
                       "MR1:R1.02", "MR1:R1.04",
                       "MX1:X1.03"],
    "BL_ISSUE": ["MB2:B2.16"],
}


# --------------------------------------------------------------------------------------------
# Operation templates (EXG-R-08) — in addition to M0, like M1 and M2
# --------------------------------------------------------------------------------------------
def _interruptions(num):
    return ("", _t(num, "ANY", "R", "NOW", "B", "Déclarer chaque interruption : début, fin et cause en liste fermée",
                   "Declare every interruption: start, end and cause from the closed list", cont=True,
                   basis="FLX-SPEC-001 §7 — événement 18"))


def _customs(num, fr="Déposer la déclaration douanière de cargaison", en="File the customs cargo declaration"):
    return ("", _t(num, "AGE", "F", "T1+24h", "B", fr, en, doc="CARGO_DECLARATION", basis="Code des douanes"))


def _protest(num):
    return ("", _t(num, "ANY", "F", "T1+24h", "N",
                   "Émettre une lettre de protêt si l'écart bord/terre ou les réserves l'exigent",
                   "Issue a letter of protest if the ship/shore difference or the remarks call for it", doc="PROTEST"))


def _damage(num):
    return ("", _t(num, "ANY", "F", "T1+24h", "N",
                   "Établir le constat de dommages ou de manquants s'il y a lieu (navire, cargaison, installations)",
                   "Establish the damage or shortage report if any (vessel, cargo, facilities)", doc="CARGO_DAMAGE_REPORT"))


TEMPLATES = [
    {
        "code": "MB1", "kind": "OPERATION", "order": 21, "berth_kinds": ["JETTY"], "cargo_kinds": ["DRY"],
        "name_fr": "Déchargement de vrac sec (import)", "name_en": "Dry bulk discharge (import)",
        "description_fr": "Minerais, céréales, clinker, engrais, charbon… En complément de M0 ; Code BLU, Code IMSBC, draft survey.",
        "description_en": "Minerals, grain, clinker, fertiliser, coal… In addition to M0; BLU Code, IMSBC Code, draft survey.",
        "tasks": [
            ("", _t("B1.01", "AGE", "F", "ETA-7j", "B", "Fournir le manifeste de cargaison et le connaissement",
                    "Provide the cargo manifest and the bill of lading", doc="CARGO_MANIFEST", basis="Convention FAL / Code des douanes")),
            ("", _t("B1.02", "NAV", "F", "ETB-24h", "B",
                    "Fournir le plan de déchargement : séquence des cales, déballastage, contraintes de structure, tirants d'eau",
                    "Provide the discharge plan: hold sequence, deballasting, structural limits, drafts", doc="STOWAGE_PLAN",
                    basis="Code BLU §3 — plan de déchargement convenu")),
            ("", _t("B1.03", "TER", "R", "ETB-12h", "B",
                    "Confirmer la capacité de réception : aire ou magasin, moyens de manutention (grues, bennes, trémies, bande), cadence",
                    "Confirm the receiving capacity: yard or warehouse, handling means (cranes, grabs, hoppers, belt), rate",
                    basis="Code BLU — plan convenu entre le navire et le terminal")),
            ("", _t("B1.04", "NAV", "R", "ETB-6h", "B",
                    "Confirmer l'état des cales : panneaux manœuvrables, éclairage, échelles, cargaison non déplacée, aération",
                    "Confirm the holds' condition: hatch covers operable, lighting, ladders, cargo not shifted, ventilation",
                    basis="Code BLU / Code IMSBC")),
            ("", _t("B1.05", "INS", "R", "T0", "B",
                    "Réaliser le draft survey initial : tirants d'eau, densité de l'eau, ballast, consommables",
                    "Perform the initial draft survey: drafts, water density, ballast, consumables", co=("NAV", "TER"),
                    ms=("DRAFT_SURVEY_INITIAL",), basis="UNECE — code de procédures uniformes pour les draft surveys")),
            ("", _t("B1.06", "INS", "R", "T0", "B",
                    "Inspecter les cales et accepter la cargaison à la vue : état, humidité, contamination, réserves",
                    "Inspect the holds and accept the cargo as seen: condition, moisture, contamination, remarks",
                    co=("NAV",), ms=("HOLDS_ACCEPTED",), basis="Pratique d'inspection des cargaisons sèches")),
            ("", _t("B1.07", "TER", "F", "T0", "B",
                    "Enregistrer l'accord de déchargement navire/terminal : séquence, cadence, déballastage, arrêts, communication",
                    "Record the ship/terminal unloading agreement: sequence, rate, deballasting, stoppages, communication",
                    doc="BLU_AGREEMENT", basis="Code BLU, appendice 2 — plan de chargement / déchargement")),
            ("", _t("B1.08", "TER", "R", "EVT", "B", "Enregistrer le début des opérations de déchargement",
                    "Record the start of the discharge operations", co=("NAV",), ms=("CARGO_OPS_START",),
                    basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("B1.09", "TER", "R", "CONT", "B",
                    "Tenir le relevé des quantités déchargées par cale et par équipe : tonnage pesé ou compté, cadence",
                    "Keep the record of the quantities discharged per hold and per shift: weighed or counted tonnage, rate",
                    co=("INS",), cont=True, basis="Code BLU — suivi du déchargement")),
            _interruptions("B1.10"),
            ("", _t("B1.11", "TER", "R", "EVT", "B", "Enregistrer la fin du déchargement et le nettoyage des cales et des aires",
                    "Record the end of the discharge and the cleaning of the holds and the areas", co=("NAV",),
                    ms=("CARGO_OPS_END",), basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("B1.12", "INS", "R", "T1+4h", "B", "Réaliser le draft survey final", "Perform the final draft survey",
                    co=("NAV", "TER"), ms=("DRAFT_SURVEY_FINAL",), basis="UNECE — draft survey final")),
            ("", _t("B1.13", "INS", "F", "T1+12h", "B", "Produire le rapport de draft survey et le constat de quantité déchargée",
                    "Issue the draft survey report and the discharged-quantity statement", doc="DRAFT_SURVEY_REPORT",
                    basis="UNECE — rapport de draft survey")),
            ("", _t("B1.14", "TER", "F", "T1+12h", "N", "Émettre le rapport de réception (out-turn) et le relevé des pesées à terre",
                    "Issue the out-turn report and the shore weighing record", doc="OUTTURN_REPORT")),
            _damage("B1.15"),
            _customs("B1.16"),
            _protest("B1.17"),
        ],
    },
    {
        "code": "MB2", "kind": "OPERATION", "order": 22, "berth_kinds": ["JETTY"], "cargo_kinds": ["DRY"],
        "name_fr": "Chargement de vrac sec (export)", "name_en": "Dry bulk loading (export)",
        "description_fr": "Minerais, clinker, céréales, engrais… En complément de M0 ; Code BLU, Code IMSBC (TML, humidité), draft survey.",
        "description_en": "Minerals, clinker, grain, fertiliser… In addition to M0; BLU Code, IMSBC Code (TML, moisture), draft survey.",
        "tasks": [
            ("", _t("B2.01", "AGE", "F", "ETA-7j", "B",
                    "Fournir la déclaration de cargaison du chargeur : nature, groupe IMSBC, teneur en humidité, TML, certificats",
                    "Provide the shipper's cargo declaration: nature, IMSBC group, moisture content, TML, certificates",
                    doc="CARGO_INFO_IMSBC", basis="Code IMSBC §4 — informations sur la cargaison")),
            ("", _t("B2.02", "AGE", "F", "ETA-7j", "B", "Fournir l'autorisation d'exportation et les documents du chargeur",
                    "Provide the export authorization and the shipper's documents", doc="EXPORT_AUTH",
                    basis="Réglementation des exportations")),
            ("", _t("B2.03", "NAV", "F", "ETB-24h", "B",
                    "Fournir le plan de chargement : séquence, déballastage, contraintes de structure, tirant d'eau final",
                    "Provide the loading plan: sequence, deballasting, structural limits, final draft", doc="STOWAGE_PLAN",
                    basis="Code BLU §3 — plan de chargement convenu")),
            ("", _t("B2.04", "TER", "R", "ETB-12h", "B",
                    "Confirmer le stock prêt, la chaîne de chargement (bande, chargeur, grues, bennes) et la cadence",
                    "Confirm the stock ready, the loading chain (belt, shiploader, cranes, grabs) and the rate",
                    basis="Code BLU — plan convenu")),
            ("", _t("B2.05", "INS", "R", "ETB-6h", "B",
                    "Inspecter les cales : propreté, sèches, étanches, prêtes à charger — certificat ou réserves",
                    "Inspect the holds: clean, dry, watertight, ready to load — certificate or remarks", co=("NAV", "TER"),
                    ms=("HOLDS_ACCEPTED",), basis="Pratique d'inspection des cales (hold inspection)")),
            ("", _t("B2.06", "INS", "R", "T0", "B", "Réaliser le draft survey initial", "Perform the initial draft survey",
                    co=("NAV", "TER"), ms=("DRAFT_SURVEY_INITIAL",), basis="UNECE — draft survey")),
            ("", _t("B2.07", "TER", "F", "T0", "B",
                    "Enregistrer l'accord de chargement navire/terminal : séquence, cadence, déballastage, arrêts, nivellement",
                    "Record the ship/terminal loading agreement: sequence, rate, deballasting, stoppages, trimming",
                    doc="BLU_AGREEMENT", basis="Code BLU, appendice 2")),
            ("", _t("B2.08", "TER", "R", "EVT", "B", "Enregistrer le début du chargement", "Record the start of loading",
                    co=("NAV",), ms=("CARGO_OPS_START",), basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("B2.09", "TER", "R", "CONT", "B",
                    "Tenir le relevé des quantités chargées par cale : bascule, bande, pesée, cadence",
                    "Keep the record of the quantities loaded per hold: weighbridge, belt scale, weighing, rate",
                    co=("INS",), cont=True, basis="Code BLU — suivi du chargement")),
            _interruptions("B2.10"),
            ("", _t("B2.11", "NAV", "R", "CONT", "N",
                    "Suivre le déballastage, la stabilité et les contraintes de coque pendant le chargement",
                    "Monitor deballasting, stability and hull stresses during loading", cont=True,
                    basis="Code BLU — surveillance pendant le chargement")),
            ("", _t("B2.12", "TER", "R", "EVT", "B", "Enregistrer la fin du chargement et le nivellement des cales",
                    "Record the end of loading and the trimming of the holds", co=("NAV",), ms=("CARGO_OPS_END",),
                    basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("B2.13", "INS", "R", "T1+4h", "B", "Réaliser le draft survey final et établir la quantité chargée",
                    "Perform the final draft survey and establish the loaded quantity", co=("NAV", "TER"),
                    ms=("DRAFT_SURVEY_FINAL",), basis="UNECE — draft survey final")),
            ("", _t("B2.14", "INS", "F", "T1+12h", "B", "Produire le rapport de draft survey", "Issue the draft survey report",
                    doc="DRAFT_SURVEY_REPORT", basis="UNECE — rapport de draft survey")),
            ("", _t("B2.15", "NAV", "F", "T1+12h", "B", "Émettre les reçus de bord (mate's receipts) avec les réserves éventuelles",
                    "Issue the mate's receipts with any remarks", doc="MATES_RECEIPT",
                    basis="Pratique maritime — reçu de bord avant connaissement")),
            ("", _t("B2.16", "COM", "F", "T1+12h", "B", "Transmettre l'instruction documentaire écrite pour le connaissement",
                    "Send the written documentary instructions for the bill of lading", doc="DOC_INSTRUCTIONS", conf="N3",
                    basis="FLX-SPEC-001 — verrou du connaissement")),
            ("", _t("B2.17", "AGE", "F", "T1+24h", "B", "Émettre le connaissement conformément aux reçus de bord et à l'instruction",
                    "Issue the bill of lading in accordance with the mate's receipts and the instructions",
                    doc="BILL_OF_LADING", basis="Règles de La Haye-Visby — connaissement")),
            _customs("B2.18", "Déposer le manifeste et la déclaration d'exportation", "File the export manifest and declaration"),
            _protest("B2.19"),
        ],
    },
    {
        "code": "MC1", "kind": "OPERATION", "order": 23, "berth_kinds": ["JETTY"], "cargo_kinds": ["CONTAINER"],
        "name_fr": "Opérations conteneurs (import, export, transbordement)", "name_en": "Container operations (import, export, transhipment)",
        "description_fr": "En complément de M0 ; plan de chargement (bay plan), marchandises dangereuses (Code IMDG), mouvements par équipe.",
        "description_en": "In addition to M0; bay plan, dangerous goods (IMDG Code), moves per shift.",
        "tasks": [
            ("", _t("C1.01", "AGE", "F", "ETA-48h", "B",
                    "Transmettre la liste de déchargement et le plan de chargement prévisionnel (bay plan, messages EDI)",
                    "Send the discharge list and the provisional loading plan (bay plan, EDI messages)", doc="BAY_PLAN",
                    basis="Pratique des terminaux à conteneurs — BAPLIE / COPRAR")),
            ("", _t("C1.02", "AGE", "F", "ETA-24h", "B",
                    "Déclarer les marchandises dangereuses : liste, classes IMDG, positions, ségrégation",
                    "Declare the dangerous goods: list, IMDG classes, positions, segregation", doc="DG_DECLARATION",
                    basis="Code IMDG chap. 5.4 — déclaration de marchandises dangereuses")),
            ("", _t("C1.03", "AGE", "F", "ETA-24h", "B",
                    "Fournir le manifeste de cargaison et les listes de conteneurs : import, export, transbordement, vides, reefers",
                    "Provide the cargo manifest and the container lists: import, export, transhipment, empties, reefers",
                    doc="CARGO_MANIFEST", basis="Convention FAL / Code des douanes")),
            ("", _t("C1.04", "TER", "R", "ETB-12h", "B",
                    "Confirmer l'allocation des portiques ou grues, des équipes, des aires et la cadence (mouvements par heure)",
                    "Confirm the allocation of the gantries or cranes, the gangs, the yard and the rate (moves per hour)",
                    basis="Pratique des terminaux à conteneurs — planification du navire")),
            ("", _t("C1.05", "NAV", "R", "ETB-6h", "B",
                    "Confirmer le plan de chargement final, la stabilité, le saisissage et les contraintes de pont",
                    "Confirm the final loading plan, stability, lashing and deck limits",
                    basis="SOLAS VI/5 et VII — manuel d'assujettissement de la cargaison")),
            ("", _t("C1.06", "TER", "R", "EVT", "B", "Enregistrer le début des opérations (premier mouvement)",
                    "Record the start of the operations (first move)", co=("NAV",), ms=("CARGO_OPS_START",),
                    basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("C1.07", "TER", "R", "CONT", "B",
                    "Tenir le relevé des mouvements par équipe : déchargés, chargés, reefers branchés, DG, hors gabarit, restow",
                    "Keep the record of the moves per shift: discharged, loaded, reefers plugged, DG, out-of-gauge, restows",
                    co=("NAV",), cont=True, basis="Pratique des terminaux — rapport d'opération")),
            _interruptions("C1.08"),
            ("", _t("C1.09", "TER", "R", "EVT", "B", "Enregistrer la fin des opérations (dernier mouvement) et la libération du poste",
                    "Record the end of the operations (last move) and the release of the berth", co=("NAV",),
                    ms=("CARGO_OPS_END",), basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("C1.10", "NAV", "F", "T1+2h", "B",
                    "Confirmer le plan de chargement final tel qu'arrimé et le saisissage vérifié",
                    "Confirm the final loading plan as stowed and the lashing checked", doc="BAY_PLAN",
                    basis="SOLAS VI — plan de chargement final")),
            ("", _t("C1.11", "TER", "F", "T1+12h", "B",
                    "Émettre le rapport d'opération du terminal : mouvements, temps, incidents, conteneurs endommagés (EIR)",
                    "Issue the terminal operation report: moves, times, incidents, damaged containers (EIR)", doc="OUTTURN_REPORT")),
            _damage("C1.12"),
            _customs("C1.13", "Déposer la déclaration douanière de cargaison (manifestes import et export)",
                     "File the customs cargo declaration (import and export manifests)"),
        ],
    },
    {
        "code": "MG1", "kind": "OPERATION", "order": 24, "berth_kinds": ["JETTY"], "cargo_kinds": ["GENERAL"],
        "name_fr": "Marchandises diverses, colis lourds et projets (import / export)", "name_en": "General cargo, breakbulk and project cargo (import / export)",
        "description_fr": "Sacs, palettes, colis, ferrailles, équipements, colis lourds… En complément de M0 ; pointage, réserves, reçus de bord.",
        "description_en": "Bags, pallets, packages, scrap, equipment, heavy lifts… In addition to M0; tally, remarks, mate's receipts.",
        "tasks": [
            ("", _t("G1.01", "AGE", "F", "ETA-48h", "B", "Fournir le manifeste de cargaison et la liste de colisage",
                    "Provide the cargo manifest and the packing list", doc="CARGO_MANIFEST", basis="Convention FAL / Code des douanes")),
            ("", _t("G1.02", "AGE", "F", "ETA-24h", "N", "Déclarer les marchandises dangereuses s'il y a lieu",
                    "Declare the dangerous goods if any", doc="DG_DECLARATION", basis="Code IMDG chap. 5.4")),
            ("", _t("G1.03", "NAV", "F", "ETB-24h", "B",
                    "Fournir le plan d'arrimage, la séquence de manutention et les contraintes : colis lourds, SWL des grues, calage",
                    "Provide the stowage plan, the handling sequence and the limits: heavy lifts, crane SWL, shoring",
                    doc="STOWAGE_PLAN", basis="Code CSS — assujettissement de la cargaison")),
            ("", _t("G1.04", "TER", "R", "ETB-12h", "B",
                    "Confirmer les moyens de manutention (grues, SWL, élingues, chariots), les aires et les équipes",
                    "Confirm the handling means (cranes, SWL, slings, forklifts), the areas and the gangs",
                    basis="Convention OIT n° 152 — manutention portuaire")),
            ("", _t("G1.05", "INS", "R", "T0", "B",
                    "Inspecter la cargaison avant manutention : état, marquage, emballage, réserves",
                    "Inspect the cargo before handling: condition, marking, packaging, remarks", co=("NAV", "TER"),
                    ms=("HOLDS_ACCEPTED",), basis="Pratique d'inspection des marchandises diverses")),
            ("", _t("G1.06", "TER", "R", "EVT", "B", "Enregistrer le début des opérations de manutention",
                    "Record the start of the cargo operations", co=("NAV",), ms=("CARGO_OPS_START",),
                    basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("G1.07", "TER", "R", "CONT", "B",
                    "Tenir le pointage (tally) des colis manutentionnés par cale, par équipe et par lot",
                    "Keep the tally of the packages handled per hold, per shift and per lot", co=("INS",), cont=True,
                    basis="Pratique — pointage contradictoire")),
            _interruptions("G1.08"),
            ("", _t("G1.09", "TER", "R", "EVT", "B", "Enregistrer la fin des opérations de manutention",
                    "Record the end of the cargo operations", co=("NAV",), ms=("CARGO_OPS_END",),
                    basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("G1.10", "INS", "F", "T1+12h", "B", "Produire le rapport de pointage et le constat de réception (out-turn)",
                    "Issue the tally report and the out-turn statement", doc="TALLY_SHEET",
                    basis="Pratique — rapport de pointage")),
            ("", _t("G1.11", "NAV", "F", "T1+12h", "N", "Émettre les reçus de bord (mate's receipts) — export",
                    "Issue the mate's receipts — export", doc="MATES_RECEIPT", basis="Pratique maritime — reçu de bord")),
            _damage("G1.12"),
            _customs("G1.13"),
            _protest("G1.14"),
        ],
    },
    {
        "code": "MR1", "kind": "OPERATION", "order": 25, "berth_kinds": ["JETTY"], "cargo_kinds": ["RORO"],
        "name_fr": "Roulier — véhicules et engins (ro-ro)", "name_en": "Ro-ro — vehicles and rolling equipment",
        "description_fr": "Véhicules neufs ou d'occasion, camions, engins, remorques… En complément de M0 ; plan de pont, pointage des unités, réserves.",
        "description_en": "New or used vehicles, trucks, machinery, trailers… In addition to M0; deck plan, tally of the units, remarks.",
        "tasks": [
            ("", _t("R1.01", "AGE", "F", "ETA-48h", "B",
                    "Fournir le manifeste et la liste des unités : châssis / VIN, type, poids, dimensions, destination",
                    "Provide the manifest and the list of units: chassis / VIN, type, weight, dimensions, destination",
                    doc="CARGO_MANIFEST", basis="Convention FAL / Code des douanes")),
            ("", _t("R1.02", "NAV", "F", "ETB-24h", "B",
                    "Fournir le plan de pont et la séquence de débarquement ou d'embarquement par rampe",
                    "Provide the deck plan and the discharge or loading sequence over the ramp", doc="STOWAGE_PLAN",
                    basis="Code CSS — saisissage des véhicules")),
            ("", _t("R1.03", "TER", "R", "ETB-12h", "B",
                    "Confirmer la rampe ou le linkspan, les aires de parc, les chauffeurs et la cadence",
                    "Confirm the ramp or linkspan, the parking areas, the drivers and the rate",
                    basis="Pratique des terminaux rouliers")),
            ("", _t("R1.04", "INS", "R", "T0", "B",
                    "Inspecter l'état des unités avant mouvement et consigner les réserves : dommages, clés, carburant, kilométrage",
                    "Inspect the units before moving them and record the remarks: damage, keys, fuel, mileage",
                    co=("NAV", "TER"), ms=("HOLDS_ACCEPTED",), basis="Pratique — inspection contradictoire des véhicules")),
            ("", _t("R1.05", "TER", "R", "EVT", "B", "Enregistrer le début des opérations", "Record the start of the operations",
                    co=("NAV",), ms=("CARGO_OPS_START",), basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("R1.06", "TER", "R", "CONT", "B",
                    "Tenir le pointage des unités par pont et par lot : débarquées, embarquées, en attente",
                    "Keep the tally of the units per deck and per lot: discharged, loaded, waiting", co=("INS",), cont=True,
                    basis="Pratique — pointage des unités")),
            _interruptions("R1.07"),
            ("", _t("R1.08", "TER", "R", "EVT", "B", "Enregistrer la fin des opérations", "Record the end of the operations",
                    co=("NAV",), ms=("CARGO_OPS_END",), basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("R1.09", "INS", "F", "T1+12h", "B", "Produire le rapport d'inspection et de pointage des unités (out-turn)",
                    "Issue the inspection and tally report of the units (out-turn)", doc="TALLY_SHEET",
                    basis="Pratique — rapport de pointage")),
            _damage("R1.10"),
            _customs("R1.11"),
            _protest("R1.12"),
        ],
    },
    {
        "code": "MX1", "kind": "OPERATION", "order": 26, "berth_kinds": [], "cargo_kinds": ["OTHER", "GENERAL", "DRY", "CONTAINER", "RORO", "LIQUID"],
        "name_fr": "Autre escale ou cargaison non listée", "name_en": "Any other call or cargo not listed",
        "description_fr": "Passagers, navire d'État, pêche, recherche, cargaison hors catalogue, escale sans manutention… Le gabarit décrit l'opération et en suit les temps ; tout ce qui ne s'applique pas est marqué sans objet.",
        "description_en": "Passengers, government vessel, fishing, research, cargo outside the catalogue, call without handling… The template describes the operation and follows its times; whatever does not apply is marked not applicable.",
        "tasks": [
            ("", _t("X1.01", "AGE", "F", "ETA-48h", "B",
                    "Décrire l'opération et fournir les documents de cargaison ou de séjour applicables : manifeste, listes, déclarations",
                    "Describe the operation and provide the applicable cargo or stay documents: manifest, lists, declarations",
                    doc="CARGO_MANIFEST", basis="Convention FAL — documents d'escale")),
            ("", _t("X1.02", "AGE", "F", "ETA-24h", "N", "Déclarer les marchandises dangereuses s'il y a lieu",
                    "Declare the dangerous goods if any", doc="DG_DECLARATION", basis="Code IMDG chap. 5.4")),
            ("", _t("X1.03", "TER", "R", "ETB-12h", "B", "Confirmer les moyens, les aires et le personnel pour l'opération décrite",
                    "Confirm the means, the areas and the staff for the operation described",
                    basis="PRO-MAR-001 — préparation de l'opération")),
            ("", _t("X1.04", "TER", "R", "EVT", "B", "Enregistrer le début de l'opération", "Record the start of the operation",
                    co=("NAV",), ms=("CARGO_OPS_START",), basis="PRO-MAR-001 — démarrage des opérations")),
            ("", _t("X1.05", "TER", "R", "CONT", "N", "Tenir le relevé de l'opération : quantités, unités, temps",
                    "Keep the record of the operation: quantities, units, times", cont=True)),
            _interruptions("X1.06"),
            ("", _t("X1.07", "TER", "R", "EVT", "B", "Enregistrer la fin de l'opération", "Record the end of the operation",
                    co=("NAV",), ms=("CARGO_OPS_END",), basis="PRO-MAR-001 — fin des opérations")),
            ("", _t("X1.08", "TER", "F", "T1+12h", "N", "Émettre le rapport d'opération", "Issue the operation report",
                    doc="OUTTURN_REPORT")),
            _customs("X1.09"),
        ],
    },
]


# --------------------------------------------------------------------------------------------
# Milestones of the cargo operations (the matrix numbers follow FLX-SPEC-001 §7)
# --------------------------------------------------------------------------------------------
def _mt(num, code, emitter, cs, ct, fr, en, **kw):
    return {"number": num, "code": code, "emitter_role": emitter, "countersigner_roles": list(cs),
            "contester_roles": list(ct), "label_fr": fr, "label_en": en, **kw}


MILESTONES = [
    _mt(14, "HOLDS_ACCEPTED", "INS", ["NAV", "TER"], ["COM"], "Cales / cargaison inspectées et acceptées",
        "Holds / cargo inspected and accepted",
        completes_tasks=["MB1:B1.06", "MB2:B2.05", "MG1:G1.05", "MR1:R1.04"]),
    _mt(14, "DRAFT_SURVEY_INITIAL", "INS", ["NAV", "TER"], ["COM"], "Draft survey initial terminé",
        "Initial draft survey completed", completes_tasks=["MB1:B1.05", "MB2:B2.06"]),
    _mt(16, "CARGO_OPS_START", "TER", ["NAV"], ["AGE", "COM"], "Début des opérations de manutention",
        "Start of cargo operations", hold_point="START_TRANSFER", sets_anchor="T0", sets_status="IN_OPERATION",
        completes_tasks=["MB1:B1.08", "MB2:B2.08", "MC1:C1.06", "MG1:G1.06", "MR1:R1.05", "MX1:X1.04"]),
    _mt(20, "CARGO_OPS_END", "TER", ["NAV"], ["AGE", "COM"], "Fin des opérations de manutention",
        "End of cargo operations", sets_anchor="T1", sets_status="OPS_COMPLETE",
        completes_tasks=["MB1:B1.11", "MB2:B2.12", "MC1:C1.09", "MG1:G1.09", "MR1:R1.08", "MX1:X1.07"]),
    _mt(23, "DRAFT_SURVEY_FINAL", "INS", ["NAV", "TER"], ["COM"], "Draft survey final terminé",
        "Final draft survey completed", completes_tasks=["MB1:B1.12", "MB2:B2.13"]),
]


# --------------------------------------------------------------------------------------------
# Document types of the cargo operations and of the forms taken from the terminals' practice
# --------------------------------------------------------------------------------------------
def _dt(code, fr, en, issuers, conf="N2", signers=(), audience=(), generated=False, bl=False, years=10, exact=False):
    return {"code": code, "label_fr": fr, "label_en": en, "issuer_roles": list(issuers), "default_confidentiality": conf,
            "signer_roles": list(signers), "audience_roles": list(audience), "generated": generated,
            "is_bill_of_lading": bl, "retention_years": years, "readers_exact": exact}


DOCUMENT_TYPES = [
    _dt("CARGO_MANIFEST", "Manifeste de cargaison et listes (colisage, conteneurs, unités)", "Cargo manifest and lists (packing, containers, units)",
        ["AGE", "NAV"], audience=["TER", "ADM", "CAP", "APO", "INS"]),
    _dt("STOWAGE_PLAN", "Plan d'arrimage / de chargement ou de déchargement (cales, ponts, séquence)", "Stowage / loading or discharge plan (holds, decks, sequence)",
        ["NAV", "AGE"], audience=["TER", "INS", "CAP"]),
    _dt("BAY_PLAN", "Plan de chargement conteneurs (bay plan, listes EDI)", "Container bay plan (EDI lists)",
        ["AGE", "NAV"], audience=["TER", "INS"]),
    _dt("DG_DECLARATION", "Déclaration de marchandises dangereuses (Code IMDG, FAL 7)", "Dangerous goods declaration (IMDG Code, FAL 7)",
        ["AGE", "NAV"], audience=["TER", "CAP", "APO", "SUR", "ADM", "SVC"]),
    _dt("CARGO_INFO_IMSBC", "Déclaration de cargaison du chargeur (Code IMSBC : groupe, humidité, TML)", "Shipper's cargo declaration (IMSBC Code: group, moisture, TML)",
        ["AGE", "COM"], audience=["NAV", "TER", "INS", "CAP"]),
    _dt("BLU_AGREEMENT", "Accord de chargement / déchargement navire-terminal (Code BLU)", "Ship/terminal loading / unloading agreement (BLU Code)",
        ["TER", "NAV"], signers=["NAV", "TER"], audience=["INS", "CAP"]),
    _dt("DRAFT_SURVEY_REPORT", "Rapport de draft survey", "Draft survey report", ["INS"], audience=["NAV", "TER", "COM"]),
    _dt("HOLD_INSPECTION", "Rapport d'inspection des cales / de la cargaison", "Hold / cargo inspection report",
        ["INS", "TER"], audience=["NAV", "TER", "COM"]),
    _dt("TALLY_SHEET", "Feuille de pointage et constat de réception (out-turn)", "Tally sheet and out-turn statement",
        ["TER", "INS"], signers=["NAV", "TER"], audience=["INS", "COM"]),
    _dt("MATES_RECEIPT", "Reçu de bord (mate's receipt)", "Mate's receipt", ["NAV"], audience=["AGE", "TER", "COM"]),
    _dt("OUTTURN_REPORT", "Rapport d'opération / de réception du terminal (out-turn, mouvements, pesées)", "Terminal operation / out-turn report (moves, weighings)",
        ["TER"], audience=["INS", "NAV", "COM"]),
    _dt("CARGO_DAMAGE_REPORT", "Constat de dommages ou de manquants", "Damage or shortage report",
        ["INS", "TER", "NAV", "AGE"], signers=["NAV", "TER"], audience=["INS", "COM", "CAP"]),
    _dt("BLU_CHECKLIST", "Liste de contrôle navire/terre — vrac sec (Code BLU)", "Ship/shore safety checklist — dry bulk (BLU Code)",
        ["TER", "NAV"], audience=["INS"]),
    _dt("CARGO_SAFETY_CHECKLIST", "Liste de contrôle sécurité des opérations de manutention (conteneurs, divers, roulier)", "Cargo operations safety checklist (containers, general cargo, ro-ro)",
        ["TER", "NAV"], audience=["INS"]),
    _dt("PAEC", "Échange d'informations avant l'arrivée navire-terminal (ISGOTT 22.2)", "Pre-arrival ship/terminal exchange of information (ISGOTT 22.2)",
        ["NAV", "AGE", "TER"], audience=["TER", "CAP", "SVC", "INS"], generated=True),
    _dt("VETTING_CHECKLIST", "Grille de vetting du navire au regard des limites du poste", "Vessel vetting checklist against the berth limits",
        ["TER", "CAP"], audience=["CAP", "APO", "COM"], generated=True),
    _dt("CARGO_HANDLING_PLAN", "Plan de manutention de la cargaison (terminal)", "Cargo handling plan (terminal)",
        ["TER"], signers=["NAV", "TER"], audience=["INS", "CAP"], generated=True),
    _dt("BERTH_OCCUPATION", "Plan d'occupation des postes / conférence de placement", "Berth occupation plan / placement conference",
        ["CAP", "APO"], conf="N1", generated=True),
]
