"""The ship/shore safety checklist completed on line (FLX-CDC-002 v1.4, EXG-Q-10).

The parts follow the structure of the ISGOTT (6th edition) ship/shore safety checklist: checks before arrival
(tanker, terminal), checks after mooring (tanker, terminal), the pre-transfer conference with its joint checks and
written agreements, and the repetitive checks during and after the transfer. The items are worded by the platform;
the terminal keeps applying its licensed edition for the full item lists. Each item names the side that answers
it — the ship, the terminal, or both — and whether it is repeated during the transfer ("R" items).

The list below is the catalogue a new checklist is opened from; the items are copied into the record so that a
checklist signed under one version of the catalogue stays readable as it was signed.
"""
from __future__ import annotations

SHIP, SHORE, BOTH = "SHIP", "SHORE", "BOTH"

# (code, part, side, kind, French, English, repetitive)
# kind: "check" (yes / no / n.a.) or "value" (an agreed figure or text written in by either side)
ITEMS: list[tuple[str, str, str, str, str, str, bool]] = [
    # ---------------------------------------------------------------- part 1A — tanker, before arrival
    ("1A.1", "1A", SHIP, "check", "Système de gaz inerte en service ; teneur en oxygène des citernes à cargaison inférieure à 8 % en volume",
     "Inert gas system in service; cargo tank oxygen content below 8% by volume", False),
    ("1A.2", "1A", SHIP, "check", "Pression positive des citernes maintenue ; dispositifs de pression / dépression et de dégagement vérifiés",
     "Positive tank pressure maintained; pressure/vacuum and venting devices checked", False),
    ("1A.3", "1A", SHIP, "check", "Plan de chargement ou de déchargement et de ballastage établi, à bord, et transmis au terminal",
     "Loading or discharge and ballast plan prepared, on board and sent to the terminal", False),
    ("1A.4", "1A", SHIP, "check", "Équipage informé des limites du poste (vent, houle, courant, tirant d'eau) et des conditions d'arrêt",
     "Crew briefed on the berth limits (wind, swell, current, draft) and on the stop conditions", False),
    ("1A.5", "1A", SHIP, "check", "Dispositifs d'amarrage, treuils et remorques de secours vérifiés et prêts",
     "Mooring equipment, winches and emergency towing-off pennants checked and ready", False),
    # ---------------------------------------------------------------- part 1B — terminal, before arrival
    ("1B.1", "1B", SHORE, "check", "Poste, défenses, bras ou flexibles, dispositifs d'accès et éclairage prêts et contrôlés",
     "Berth, fenders, arms or hoses, means of access and lighting ready and checked", False),
    ("1B.2", "1B", SHORE, "check", "Bacs, lignes et vannes alignés conformément au plan ; creux ou disponibilité du produit vérifiés",
     "Shore tanks, lines and valves lined up per plan; ullage or product availability checked", False),
    ("1B.3", "1B", SHORE, "check", "Prévisions météo et marée compatibles avec les limites du poste pendant la durée prévue de l'opération",
     "Weather and tide forecasts within the berth limits for the planned duration of the operation", False),
    ("1B.4", "1B", SHORE, "check", "Personnel de permanence désigné, informé, joignable ; moyens de communication essayés",
     "Duty personnel assigned, briefed and reachable; communication means tested", False),
    # ---------------------------------------------------------------- part 2 — tanker, after mooring
    ("2.1", "2", SHIP, "check", "Amarres tenues et surveillées ; treuils en frein ; remorques de secours en place aux deux extrémités",
     "Moorings tended and monitored; winches on brakes; emergency towing-off pennants rigged fore and aft", True),
    ("2.2", "2", SHIP, "check", "Moyen d'accès sûr, éclairé et surveillé ; filet de sécurité en place",
     "Safe, lit and watched means of access; safety net rigged", True),
    ("2.3", "2", SHIP, "check", "Dalots et évacuations obturés ; plateaux de rétention du collecteur vides et en place",
     "Scuppers and drains plugged; manifold drip trays empty and in place", True),
    ("2.4", "2", SHIP, "check", "Ouvertures de citernes fermées ; dégagement des citernes conforme au plan convenu",
     "Tank openings closed; tank venting as agreed in the plan", True),
    ("2.5", "2", SHIP, "check", "Portes et hublots des emménagements fermés ; ventilation en surpression ou conforme",
     "Accommodation doors and ports closed; ventilation on positive pressure or as required", True),
    ("2.6", "2", SHIP, "check", "Matériel incendie prêt et paré ; manches pressurisées et lances disposées au collecteur",
     "Fire-fighting equipment ready for immediate use; pressurised hoses and nozzles laid at the manifold", True),
    ("2.7", "2", SHIP, "check", "Moyens antipollution et plan d'urgence prêts ; sources d'ignition contrôlées, interdiction de fumer affichée",
     "Spill response equipment and emergency plan ready; ignition sources controlled, no-smoking notices posted", True),
    ("2.8", "2", SHIP, "check", "Pompes à cargaison, vannes du collecteur et système de mesure des citernes vérifiés ; collecteurs non utilisés obturés",
     "Cargo pumps, manifold valves and tank gauging system checked; unused manifolds blanked", False),
    ("2.9", "2", SHIP, "check", "Veille suffisante et effectif à bord pendant toute la durée de l'opération",
     "Adequate watch and crew on board throughout the operation", True),
    ("2.10", "2", SHIP, "check", "Moyens de propulsion, barre et machine disponibles pour un appareillage d'urgence selon l'accord",
     "Propulsion, steering and engines available for emergency departure as agreed", False),
    # ---------------------------------------------------------------- part 3 — terminal, after mooring
    ("3.1", "3", SHORE, "check", "Défenses en place et en bon état ; crochets à échappement et moyens d'amarrage du quai opérationnels",
     "Fenders in place and in good order; quick-release hooks and berth mooring means operational", False),
    ("3.2", "3", SHORE, "check", "Bras ou flexibles adaptés au collecteur, supportés, dans leur enveloppe de mouvement ; joints et boulonnage vérifiés",
     "Arms or hoses suited to the manifold, supported, within their operating envelope; gaskets and bolting checked", False),
    ("3.3", "3", SHORE, "check", "Joint isolant ou câble de mise à la masse conforme à la procédure convenue",
     "Insulating flange or bonding cable per the agreed procedure", False),
    ("3.4", "3", SHORE, "check", "Matériel incendie et antipollution du terminal prêt ; accès des secours dégagé",
     "Terminal fire-fighting and spill response equipment ready; emergency access clear", True),
    ("3.5", "3", SHORE, "check", "Dispositif d'arrêt d'urgence (ESD) du terminal armé ; temps de fermeture des vannes connu",
     "Terminal emergency shutdown (ESD) armed; valve closure time known", False),
    ("3.6", "3", SHORE, "check", "Accès au quai contrôlé ; sources d'ignition et véhicules non autorisés exclus de la zone",
     "Berth access controlled; ignition sources and unauthorised vehicles kept out of the area", True),
    ("3.7", "3", SHORE, "check", "Éclairage du poste et des cheminements suffisant pour l'opération de nuit",
     "Berth and walkway lighting sufficient for night operations", True),
    # ---------------------------------------------------------------- part 4 — joint pre-transfer checks
    ("4.1", "4", BOTH, "check", "Système de communication principal et de secours convenu et essayé ; langue de travail convenue",
     "Primary and backup communication system agreed and tested; working language agreed", True),
    ("4.2", "4", BOTH, "check", "Signaux et procédure d'arrêt d'urgence convenus ; essai d'arrêt d'urgence consigné",
     "Emergency stop signals and procedure agreed; emergency shutdown test recorded", False),
    ("4.3", "4", BOTH, "check", "Collecteurs, flexibles ou bras raccordés, étanches, et vérifiés sous pression avant le démarrage",
     "Manifolds, hoses or arms connected, tight and pressure-checked before starting", False),
    ("4.4", "4", BOTH, "check", "Alignement des vannes bord et terre vérifié de part et d'autre ; lignes non utilisées isolées",
     "Ship and shore valve line-up checked on both sides; unused lines isolated", False),
    ("4.5", "4", BOTH, "check", "Débits de démarrage, de régime et de fin, pression maximale et séquence de citernes convenus (partie 5A)",
     "Start, full and topping-off rates, maximum pressure and tank sequence agreed (part 5A)", False),
    ("4.6", "4", BOTH, "check", "Surveillance convenue des citernes et des bacs ; jaugeage et échantillonnage convenus avec l'inspecteur",
     "Agreed monitoring of tanks and shore tanks; gauging and sampling agreed with the surveyor", False),
    ("4.7", "4", BOTH, "check", "Conditions météo et limites d'interruption convenues ; procédure de déconnexion d'urgence connue des deux côtés",
     "Weather conditions and stop limits agreed; emergency disconnection procedure known on both sides", True),
    ("4.8", "4", BOTH, "check", "Personnes responsables de permanence désignées des deux côtés, noms et moyens de contact échangés",
     "Responsible persons on duty named on both sides, names and contact means exchanged", True),
    # ---------------------------------------------------------------- part 5A — written agreements of the conference
    ("5A.1", "5A", BOTH, "value", "Débit initial / maximal / de fin (m³/h)", "Initial / maximum / topping-off rate (m³/h)", False),
    ("5A.2", "5A", BOTH, "value", "Pression maximale au collecteur (bar)", "Maximum manifold pressure (bar)", False),
    ("5A.3", "5A", BOTH, "value", "Température maximale du produit (°C)", "Maximum product temperature (°C)", False),
    ("5A.4", "5A", BOTH, "value", "Temps de fermeture des vannes bord / terre (s)", "Ship / shore valve closure time (s)", False),
    ("5A.5", "5A", BOTH, "value", "Séquence des citernes et des bacs ; échantillonnage et jaugeage", "Tank and shore tank sequence; sampling and gauging", False),
    ("5A.6", "5A", BOTH, "value", "Limites d'interruption : vent (nd), houle (m), foudre, visibilité", "Stop limits: wind (kn), swell (m), lightning, visibility", False),
    ("5A.7", "5A", BOTH, "value", "Canal VHF principal / de secours ; langue", "Primary / backup VHF channel; language", False),
    ("5A.8", "5A", BOTH, "value", "Intervalle des vérifications répétées (h)", "Interval of the repetitive checks (h)", False),
    # ---------------------------------------------------------------- part 6 — repeated during and after the transfer
    ("6.1", "6", BOTH, "check", "Amarres, flexibles ou bras, pression au collecteur et débit vérifiés dans les limites convenues",
     "Moorings, hoses or arms, manifold pressure and rate checked within the agreed limits", True),
    ("6.2", "6", BOTH, "check", "Communication et veille maintenues des deux côtés ; conditions météo dans les limites",
     "Communication and watch maintained on both sides; weather within limits", True),
    ("6.3", "6", SHIP, "check", "Ballastage conforme au plan ; tirant d'eau, assiette, gîte et francs-bords surveillés",
     "Ballast per plan; draft, trim, list and freeboard monitored", True),
    ("6.4", "6", SHORE, "check", "Bacs et lignes à terre surveillés ; changement de bac annoncé au navire avant exécution",
     "Shore tanks and lines monitored; shore tank switch announced to the ship before it is made", True),
    ("6.5", "6", BOTH, "check", "Après transfert : lignes vidangées, collecteurs obturés, quantités constatées contradictoirement",
     "After transfer: lines drained, manifolds blanked, quantities agreed jointly", False),
]

PARTS: list[tuple[str, str, str]] = [
    ("1A", "Partie 1A — Navire : vérifications avant l'arrivée", "Part 1A — Tanker: checks pre-arrival"),
    ("1B", "Partie 1B — Terminal : vérifications avant l'arrivée", "Part 1B — Terminal: checks pre-arrival"),
    ("2", "Partie 2 — Navire : vérifications après l'amarrage", "Part 2 — Tanker: checks after mooring"),
    ("3", "Partie 3 — Terminal : vérifications après l'amarrage", "Part 3 — Terminal: checks after mooring"),
    ("4", "Partie 4 — Navire et terminal : vérifications avant le transfert", "Part 4 — Tanker and terminal: pre-transfer checks"),
    ("5A", "Partie 5A — Accords écrits de la réunion pré-transfert", "Part 5A — Written agreements of the pre-transfer conference"),
    ("6", "Partie 6 — Vérifications répétées pendant et après le transfert", "Part 6 — Repetitive checks during and after the transfer"),
]


def catalogue() -> list[dict]:
    """The items as stored in a new checklist (one dict per item)."""
    return [{"code": code, "part": part, "side": side, "kind": kind, "fr": fr, "en": en, "repetitive": rep}
            for code, part, side, kind, fr, en, rep in ITEMS]


def part_label(part: str) -> tuple[str, str]:
    return next(((fr, en) for code, fr, en in PARTS if code == part), (part, part))


def sides_of(item: dict) -> list[str]:
    """The side(s) that answer an item: both for a joint check or an agreement."""
    return ["SHIP", "SHORE"] if item["side"] == BOTH else [item["side"]]
