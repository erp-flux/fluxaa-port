"""The safety checklists completed on line, by kind of cargo (FLX-CDC-002 v1.4 EXG-Q-10, v1.5 EXG-R-08).

Three catalogues, one structure: liquid bulk follows the ISGOTT ship/shore safety checklist (``ssscl.py``); dry
bulk follows the ship/shore safety checklist of the IMO BLU Code (Code of Practice for the Safe Loading and
Unloading of Bulk Carriers, appendix 3); containers, general cargo, ro-ro and any other call follow the
platform's cargo operations safety checklist, drawn from the ILO code of practice *Safety and health in ports*
and the terminals' own practice. The items are worded by the platform; each names the side that answers it —
the ship, the terminal, or both — and whether it is repeated during the operations.

The list a new checklist is opened from is chosen by the call's kind of cargo; the items are copied into the
record so that a list signed under one version of the catalogue stays readable as it was signed.
"""
from __future__ import annotations

from . import ssscl

SHIP, SHORE, BOTH = ssscl.SHIP, ssscl.SHORE, ssscl.BOTH

# ------------------------------------------------------------------------------------------------ dry bulk (BLU)
# (code, part, side, kind, French, English, repetitive)
BLU_ITEMS: list[tuple[str, str, str, str, str, str, bool]] = [
    # part 1 — before the operations: ship
    ("1.1", "1", SHIP, "check", "Tirant d'eau et tirant d'air du navire compatibles avec le poste et la profondeur disponible",
     "Draft and air draft of the ship within the berth's depth and clearance", False),
    ("1.2", "1", SHIP, "check", "Amarres tenues et adaptées aux conditions locales ; surveillance prévue pendant l'opération",
     "Moorings holding and suited to the local conditions; watch planned during the operations", True),
    ("1.3", "1", SHIP, "check", "Plan de chargement ou de déchargement établi, calculé pour la stabilité et les contraintes, remis au terminal",
     "Loading or unloading plan prepared, checked for stability and stresses, handed to the terminal", False),
    ("1.4", "1", SHIP, "check", "Cales inspectées, prêtes et acceptées ; panneaux manœuvrables ; cales interdites identifiées",
     "Holds inspected, ready and accepted; hatch covers operable; holds not to be worked identified", False),
    ("1.5", "1", SHIP, "check", "Déballastage ou ballastage planifié au rythme de la cadence convenue ; pompes et vannes essayées",
     "Deballasting or ballasting planned at the agreed rate; pumps and valves tested", False),
    ("1.6", "1", SHIP, "check", "Déclaration de cargaison du chargeur reçue (Code IMSBC) : groupe, humidité, TML, dangers",
     "Shipper's cargo declaration received (IMSBC Code): group, moisture, TML, hazards", False),
    # part 2 — before the operations: terminal
    ("2.1", "2", SHORE, "check", "Profondeur au poste et dégagements des moyens de manutention vérifiés pour le navire annoncé",
     "Depth at the berth and clearances of the handling equipment checked for the vessel announced", False),
    ("2.2", "2", SHORE, "check", "Moyens de manutention (grues, bennes, trémies, bande, chargeur) contrôlés ; cadence annoncée réalisable",
     "Handling equipment (cranes, grabs, hoppers, belt, shiploader) checked; the announced rate is achievable", False),
    ("2.3", "2", SHORE, "check", "Aires ou magasins de réception, ou stock à charger, disponibles pour la quantité prévue",
     "Receiving areas or warehouses, or the stock to load, available for the planned quantity", False),
    ("2.4", "2", SHORE, "check", "Prévisions météo compatibles avec l'opération (vent, pluie pour les cargaisons sensibles, houle)",
     "Weather forecast compatible with the operations (wind, rain for sensitive cargoes, swell)", True),
    ("2.5", "2", SHORE, "check", "Personnel de permanence désigné et joignable ; moyens de communication navire-terminal essayés",
     "Duty personnel assigned and reachable; ship/terminal communication means tested", False),
    # part 3 — agreed between ship and terminal
    ("3.1", "3", BOTH, "value", "Séquence de chargement ou de déchargement convenue (cales, quantités par passe, cadence par étape)",
     "Agreed loading or unloading sequence (holds, quantities per pour, rate per step)", False),
    ("3.2", "3", BOTH, "value", "Cadence maximale et quantité par passe convenues ; signal et délai d'arrêt convenus",
     "Agreed maximum rate and quantity per pour; stop signal and stop time agreed", False),
    ("3.3", "3", BOTH, "value", "Moyens de communication convenus (canal VHF, téléphone) et langue de travail",
     "Agreed communication means (VHF channel, telephone) and working language", False),
    ("3.4", "3", BOTH, "check", "Procédure d'urgence convenue : arrêt des opérations, incendie, chute de personne, pollution, mauvais temps",
     "Agreed emergency procedure: stop of the operations, fire, man overboard, pollution, bad weather", False),
    ("3.5", "3", BOTH, "check", "Accès au navire sûr (passerelle, filet, éclairage) ; zones interdites pendant la manutention signalées",
     "Safe access to the ship (gangway, net, lighting); areas closed during handling marked", True),
    ("3.6", "3", BOTH, "check", "Nivellement (trimming) convenu ; moyens prévus ; limites de hauteur de chute de la cargaison",
     "Trimming agreed; means provided; limits to the drop height of the cargo", False),
    ("3.7", "3", BOTH, "check", "Pesée ou comptage convenus : bascule, bande, draft survey ; rapprochement des quantités par cale",
     "Weighing or counting agreed: weighbridge, belt scale, draft survey; reconciliation of the quantities per hold", False),
    # part 4 — repetitive checks during the operations
    ("4.1", "4", SHIP, "check", "Contraintes de coque et stabilité suivies à chaque étape ; déballastage conforme au plan",
     "Hull stresses and stability followed at every step; deballasting as planned", True),
    ("4.2", "4", SHORE, "check", "Cadence et séquence respectées ; changement de cale annoncé au navire avant exécution",
     "Rate and sequence respected; change of hold announced to the ship before it is made", True),
    ("4.3", "4", BOTH, "check", "Dommages au navire ou aux installations (chocs de benne, panneaux, hiloires) signalés aussitôt",
     "Damage to the ship or to the facilities (grab strikes, hatch covers, coamings) reported at once", True),
    ("4.4", "4", BOTH, "check", "Poussières, déversements et résidus maîtrisés ; cales et pont nettoyés avant fermeture",
     "Dust, spillages and residues under control; holds and deck cleaned before closing", True),
]

BLU_PARTS: list[tuple[str, str, str]] = [
    ("1", "Partie 1 — Navire : vérifications avant les opérations", "Part 1 — Ship: checks before the operations"),
    ("2", "Partie 2 — Terminal : vérifications avant les opérations", "Part 2 — Terminal: checks before the operations"),
    ("3", "Partie 3 — Navire et terminal : plan convenu et accords écrits", "Part 3 — Ship and terminal: agreed plan and written agreements"),
    ("4", "Partie 4 — Vérifications répétées pendant les opérations", "Part 4 — Repetitive checks during the operations"),
]

# ------------------------------------------------------------------------------- containers, general cargo, ro-ro
CARGO_ITEMS: list[tuple[str, str, str, str, str, str, bool]] = [
    # part A — ship
    ("A.1", "A", SHIP, "check", "Amarres tenues et surveillées ; passerelle ou coupée sûre, filet de sécurité, éclairage de nuit",
     "Moorings holding and watched; gangway or accommodation ladder safe, safety net, lighting at night", True),
    ("A.2", "A", SHIP, "check", "Plan de chargement ou de déchargement, stabilité et saisissage établis et remis au terminal",
     "Loading or discharge plan, stability and lashing prepared and handed to the terminal", False),
    ("A.3", "A", SHIP, "check", "Engins de levage du bord (grues, mâts de charge) certifiés, SWL affichée, essais récents",
     "Ship's lifting gear (cranes, derricks) certified, SWL marked, recent tests", False),
    ("A.4", "A", SHIP, "check", "Panneaux, rampes et portes manœuvrables ; cales, ponts et garages éclairés et ventilés",
     "Hatch covers, ramps and doors operable; holds, decks and garages lit and ventilated", False),
    ("A.5", "A", SHIP, "check", "Marchandises dangereuses déclarées, ségrégées et signalées ; fiches de données disponibles",
     "Dangerous goods declared, segregated and marked; safety data sheets available", False),
    # part B — terminal
    ("B.1", "B", SHORE, "check", "Moyens de manutention (portiques, grues mobiles, chariots, tracteurs) contrôlés ; SWL compatible avec les colis",
     "Handling equipment (gantries, mobile cranes, forklifts, tractors) checked; SWL compatible with the cargo", False),
    ("B.2", "B", SHORE, "check", "Aires de dépôt, de parc ou de transit disponibles et balisées ; circulation organisée",
     "Storage, parking or transit areas available and marked out; traffic organised", False),
    ("B.3", "B", SHORE, "check", "Équipes désignées, briefées, équipées (EPI) ; personnel d'encadrement joignable",
     "Gangs assigned, briefed and equipped (PPE); supervisors reachable", False),
    ("B.4", "B", SHORE, "check", "Prévisions météo compatibles (vent pour les portiques et les colis volumineux, pluie pour les cargaisons sensibles)",
     "Weather forecast compatible (wind for the gantries and bulky cargo, rain for sensitive cargoes)", True),
    ("B.5", "B", SHORE, "check", "Moyens incendie, premiers secours et accès des secours vérifiés ; alarme et point de rassemblement connus",
     "Firefighting means, first aid and emergency access checked; alarm and muster point known", False),
    # part C — agreed between ship and terminal
    ("C.1", "C", BOTH, "value", "Séquence des opérations convenue (cales ou baies, ponts, lots) et cadence prévue",
     "Agreed sequence of the operations (holds or bays, decks, lots) and planned rate", False),
    ("C.2", "C", BOTH, "value", "Moyens de communication convenus (VHF, téléphone), langue de travail, signaleurs désignés",
     "Agreed communication means (VHF, telephone), working language, signalmen designated", False),
    ("C.3", "C", BOTH, "check", "Procédure d'urgence convenue : arrêt des opérations, incendie, blessé, chute de colis, pollution",
     "Agreed emergency procedure: stop of the operations, fire, injury, dropped load, pollution", False),
    ("C.4", "C", BOTH, "check", "Zones de manutention interdites au personnel non concerné ; cheminements piétons séparés des engins",
     "Handling areas closed to unconcerned staff; pedestrian routes separated from the vehicles", True),
    ("C.5", "C", BOTH, "check", "Travaux à chaud, fumeurs, espaces clos : interdits ou sous permis pendant les opérations",
     "Hot work, smoking, enclosed spaces: forbidden or under permit during the operations", False),
    ("C.6", "C", BOTH, "check", "Pointage contradictoire convenu : qui compte, où, comment les réserves et dommages sont consignés",
     "Joint tally agreed: who counts, where, how remarks and damage are recorded", False),
    # part D — repetitive checks during the operations
    ("D.1", "D", SHIP, "check", "Stabilité et saisissage suivis ; ballast ajusté ; gîte et assiette maîtrisées",
     "Stability and lashing followed; ballast adjusted; list and trim under control", True),
    ("D.2", "D", SHORE, "check", "Cadence et séquence respectées ; incidents, dommages et conteneurs ou colis endommagés consignés",
     "Rate and sequence respected; incidents, damage and damaged containers or packages recorded", True),
    ("D.3", "D", BOTH, "check", "Accès, éclairage et amarres vérifiés à chaque relève d'équipe",
     "Access, lighting and moorings checked at every change of shift", True),
    ("D.4", "D", BOTH, "check", "Marchandises dangereuses et reefers surveillés (branchement, température, fuites)",
     "Dangerous goods and reefers monitored (connection, temperature, leaks)", True),
]

CARGO_PARTS: list[tuple[str, str, str]] = [
    ("A", "Partie A — Navire : vérifications avant les opérations", "Part A — Ship: checks before the operations"),
    ("B", "Partie B — Terminal : vérifications avant les opérations", "Part B — Terminal: checks before the operations"),
    ("C", "Partie C — Navire et terminal : accords de la réunion préopérationnelle", "Part C — Ship and terminal: agreements of the pre-operational meeting"),
    ("D", "Partie D — Vérifications répétées pendant les opérations", "Part D — Repetitive checks during the operations"),
]

STANDARDS = {
    "SSSCL": {"items": ssscl.ITEMS, "parts": ssscl.PARTS, "document": "SSSCL",
              "label": ("Liste de contrôle navire/terre (ISGOTT)", "Ship/shore safety checklist (ISGOTT)"),
              "basis": ("Structure de l'ISGOTT, 6e édition, chapitre 25", "Structure of ISGOTT, 6th edition, chapter 25")},
    "BLU": {"items": BLU_ITEMS, "parts": BLU_PARTS, "document": "BLU_CHECKLIST",
            "label": ("Liste de contrôle navire/terre — vrac sec (Code BLU)", "Ship/shore safety checklist — dry bulk (BLU Code)"),
            "basis": ("Code BLU de l'OMI (résolution A.862(20)), appendice 3", "IMO BLU Code (resolution A.862(20)), appendix 3")},
    "CARGO": {"items": CARGO_ITEMS, "parts": CARGO_PARTS, "document": "CARGO_SAFETY_CHECKLIST",
              "label": ("Liste de contrôle sécurité des opérations de manutention", "Cargo operations safety checklist"),
              "basis": ("Recueil de directives pratiques du BIT « Sécurité et santé dans les ports » ; pratique des terminaux",
                        "ILO code of practice “Safety and health in ports”; terminal practice")},
}
STANDARD_BY_CARGO = {"LIQUID": "SSSCL", "DRY": "BLU", "CONTAINER": "CARGO", "GENERAL": "CARGO", "RORO": "CARGO", "OTHER": "CARGO"}


def standard_for(cargo_kind: str) -> str:
    return STANDARD_BY_CARGO.get(cargo_kind or "LIQUID", "SSSCL")


def catalogue(standard: str = "SSSCL") -> list[dict]:
    """The items as stored in a new checklist (one dict per item)."""
    spec = STANDARDS.get(standard, STANDARDS["SSSCL"])
    return [{"code": code, "part": part, "side": side, "kind": kind, "fr": fr, "en": en, "repetitive": rep}
            for code, part, side, kind, fr, en, rep in spec["items"]]


def parts(standard: str = "SSSCL") -> list[tuple[str, str, str]]:
    return STANDARDS.get(standard, STANDARDS["SSSCL"])["parts"]


def part_label(standard: str, part: str) -> tuple[str, str]:
    return next(((fr, en) for code, fr, en in parts(standard) if code == part), (part, part))


def document_code(standard: str) -> str:
    return STANDARDS.get(standard, STANDARDS["SSSCL"])["document"]


def label(standard: str) -> tuple[str, str]:
    return STANDARDS.get(standard, STANDARDS["SSSCL"])["label"]


def basis(standard: str) -> tuple[str, str]:
    return STANDARDS.get(standard, STANDARDS["SSSCL"])["basis"]


sides_of = ssscl.sides_of
