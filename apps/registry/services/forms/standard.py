"""The fourteen reference forms of the ship/shore interface, the formalities and the services: NOR, time sheet,
ISGOTT ship/shore safety checklist, pre-transfer agreement, ullage report, hose record, letter of protest, FAL
forms, declaration of security, maritime declaration of health, advance waste notification, STS checklists, pilot
card, bunker delivery note. Pre-filled from the registry, completed and signed on paper, filed back as versions."""
from __future__ import annotations

from ...models import PortCall
from ..reports import interruptions, time_sheet
from .core import F, Form, _m, _mt, _party, _register, _where, checklist, dt, fields, table, text


def build_nor(call: PortCall) -> list[dict]:
    arrival = _m(call, "ARRIVAL")
    nor = _m(call, "NOR_TENDERED")
    loading = "M2" in call.template_codes
    op = "chargement / loading" if loading else "déchargement / discharge"
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


def build_time_sheet(call: PortCall) -> list[dict]:
    sheet = time_sheet(call)
    rows = []
    for code, fr, en in (("ARRIVAL", "Arrivée limite du port", "Arrival at port limit"), ("NOR_TENDERED", "NOR remise", "NOR tendered"),
                         ("ANCHORED", "Mouillage", "Anchored"), ("ANCHOR_AWEIGH", "Appareillage du mouillage", "Anchor aweigh"),
                         ("PILOT_ON_BOARD_ARR", "Pilote à bord", "Pilot on board"), ("FIRST_LINE", "Première amarre", "First line"),
                         ("ALL_FAST", "Amarrage terminé (all fast)", "All fast"), ("STS_ALONGSIDE", "STS — à couple", "STS — alongside"),
                         ("HOSES_CONNECTED", "Flexibles connectés", "Hoses connected"), ("TRANSFER_START", "Début du transfert", "Commenced cargo"),
                         ("STS_TRANSFER_START", "Début du transfert STS", "STS transfer commenced"), ("TRANSFER_END", "Fin du transfert", "Completed cargo"),
                         ("STS_TRANSFER_END", "Fin du transfert STS", "STS transfer completed"), ("HOSES_DISCONNECTED", "Flexibles déconnectés", "Hoses disconnected"),
                         ("DOCUMENTS_SIGNED", "Documents signés", "Documents signed"), ("LAST_LINE", "Dernière amarre", "Last line"),
                         ("DEPARTED", "Appareillé", "Departed")):
        for m in call.milestones.filter(type__code=code, is_conflict=False).order_by("declared_at"):
            rows.append([f"{fr} / {en}", dt(m.declared_at), m.emitter_label, ", ".join(
                f"{s.role}: {s.get_state_display()}" for s in m.signatures.all()) or "—"])
    stops = [[(row["cause"].label_fr + " / " + row["cause"].label_en) if row["cause"] else "—",
              dt(row["start"].declared_at), dt(row["end"].declared_at) if row["end"] else None,
              f"{row['duration_h']:.2f}" if row["duration_h"] is not None else None,
              row["attribution"] or "—", "établie / established" if row["established"] else "contestée ou tacite / contested or tacit"]
             for row in interruptions(call)]
    return [
        fields(("Escale", "Call"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Voyage", "Voyage", call.voyage_number or None, source="PortCall.voyage_number"),
            F("Port / poste", "Port / berth", f"{call.port.name} — {_where(call)}", source="Port.name, poste ou zone de l'étape en cours"), F("Produit", "Product", call.product or None, source="PortCall.product"),
            F("Quantité déclarée", "Declared quantity", f"{call.quantity} {call.quantity_unit}" if call.quantity else None, source="PortCall.quantity, PortCall.quantity_unit"),
            F("Agence", "Agency", str(call.agency), source="PortCall.agency (Organization.name)"),
        ]),
        table(("Chronologie", "Chronology"), [("Événement", "Event"), ("Heure (UTC)", "Time (UTC)"), ("Émetteur", "Recorded by"),
                                              ("Contresignatures", "Countersignatures")], rows, blank_rows=2,
              source="Milestone (types de la chronologie, declared_at, emitter_label) et MilestoneSignature (role, state)"),
        table(("Interruptions", "Stoppages"), [("Cause", "Cause"), ("Début", "From"), ("Fin", "To"), ("Durée (h)", "Duration (h)"),
                                               ("Imputation", "Attribution"), ("État", "State")], stops, blank_rows=1,
              source="reports.interruptions : jalons INTERRUPTION_START/END, InterruptionCause, contresignatures"),
        fields(("Totaux", "Totals"), [
            F("Attente en rade (h)", "Waiting at anchorage (h)", f"{sheet['waiting_h']:.2f}" if sheet.get("waiting_h") is not None else None, source="reports.time_sheet : ATB − ATA"),
            F("Durée brute de transfert (h)", "Gross transfer time (h)", f"{sheet['transfer_gross_h']:.2f}" if sheet.get("transfer_gross_h") is not None else None, source="reports.time_sheet : T1 − T0"),
            F("Temps morts (h)", "Stoppages (h)", f"{sheet['stops_h']:.2f}" if sheet.get("stops_h") is not None else None, source="reports.time_sheet : somme des interruptions"),
            F("Durée nette de transfert (h)", "Net transfer time (h)", f"{sheet['transfer_net_h']:.2f}" if sheet.get("transfer_net_h") is not None else None, source="reports.time_sheet : brut − temps morts"),
            F("Temps de planche utilisé (h) — selon charte-partie", "Laytime used (h) — per charter-party"),
            F("Surestaries / dispatch", "Demurrage / despatch"),
        ], note=("Les heures viennent du registre contradictoire ; le décompte du temps de planche suit la charte-partie et les BIMCO Laytime Definitions for Charter Parties 2013.",
                 "Times come from the contradictory registry; laytime is computed under the charter-party and the BIMCO Laytime Definitions for Charter Parties 2013.")),
    ]


def build_ssscl(call: PortCall) -> list[dict]:
    ship, shore, both = [("Navire", "Ship")], [("Terre", "Shore")], [("Navire", "Ship"), ("Terre", "Shore")]
    return [
        fields(("Identification", "Identification"), [
            F("Navire", "Vessel", f"{call.vessel.name} — IMO {call.vessel.imo}", source="Vessel.name, Vessel.imo"), F("Poste", "Berth", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
            F("Produit", "Product", call.product or None, source="PortCall.product"), F("Opération", "Operation", "chargement / loading" if "M2" in call.template_codes else "déchargement / discharge", source="PortCall.template_codes"),
            F("Date et heure d'arrivée au poste (ATB)", "Date and time of berthing (ATB)", dt(call.atb), source="PortCall.atb"),
            F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active (Organization.name)"),
        ]),
        checklist(("Partie 1A — Navire : vérifications avant l'arrivée", "Part 1A — Tanker: checks pre-arrival"), [
            ("Système de gaz inerte en service, teneur en O₂ des citernes dans les limites", "Inert gas system operational, tank O₂ within limits"),
            ("Dispositifs de pression/dépression et dégagement des citernes vérifiés", "Pressure/vacuum devices and tank venting checked"),
            ("Plan de chargement ou de déchargement et de ballastage établi et à bord", "Loading/discharge and ballast plan prepared and on board"),
            ("Équipage informé des limites du poste (vent, houle, courant, tirant d'eau)", "Crew briefed on the berth limits (wind, swell, current, draft)"),
        ], columns=ship),
        checklist(("Partie 1B — Terminal : vérifications avant l'arrivée", "Part 1B — Terminal: checks pre-arrival"), [
            ("Poste, défenses, bras ou flexibles et moyens d'accès prêts et contrôlés", "Berth, fenders, arms or hoses and means of access ready and checked"),
            ("Bacs, lignes et vannes alignés conformément au plan ; capacité disponible", "Shore tanks, lines and valves lined up per plan; capacity available"),
            ("Prévisions météo et marée compatibles avec les limites du poste", "Weather and tide forecasts within the berth limits"),
            ("Personnel de permanence désigné et informé", "Duty personnel assigned and briefed"),
        ], columns=shore),
        checklist(("Partie 2 — Navire : vérifications après l'amarrage", "Part 2 — Tanker: checks after mooring"), [
            ("Amarres tenues et surveillées ; remorque de secours prête", "Moorings tended; emergency towing-off pennants ready"),
            ("Moyens d'accès sûrs ; dalots fermés ; plateaux de rétention vidés", "Safe means of access; scuppers plugged; drip trays empty"),
            ("Ouvertures de citernes fermées ; dégagement conforme au plan", "Tank openings closed; venting per plan"),
            ("Matériel incendie et antipollution prêt ; sources d'ignition contrôlées", "Fire-fighting and spill response equipment ready; ignition sources controlled"),
        ], columns=ship),
        checklist(("Partie 3 — Terminal : vérifications après l'amarrage", "Part 3 — Terminal: checks after mooring"), [
            ("Défenses en place ; accès et éclairage conformes", "Fenders in place; access and lighting compliant"),
            ("Bras ou flexibles adaptés au collecteur, supportés, dans leur enveloppe de mouvement", "Arms or hoses suited to the manifold, supported, within their operating envelope"),
            ("Matériel incendie et antipollution du terminal prêt", "Terminal fire-fighting and spill response equipment ready"),
            ("Dispositif d'arrêt d'urgence (ESD) du terminal armé", "Terminal emergency shutdown (ESD) armed"),
        ], columns=shore),
        checklist(("Partie 4 — Navire et terminal : vérifications avant le transfert", "Part 4 — Tanker and terminal: pre-transfer checks"), [
            ("Système de communication convenu et testé ; signaux d'arrêt d'urgence convenus", "Agreed communication system tested; emergency stop signals agreed"),
            ("Procédure d'arrêt d'urgence convenue, essai consigné", "Emergency shutdown procedure agreed and tested"),
            ("Collecteurs, flexibles ou bras raccordés et étanches ; joints isolants / mise à la masse conformes", "Manifolds, hoses or arms connected and tight; insulating flange / bonding compliant"),
            ("Alignement des vannes bord et terre vérifié ; gaz inerte et pression des citernes surveillés", "Ship and shore valve line-up checked; inert gas and tank pressure monitored"),
            ("Effectif suffisant et veille assurée des deux côtés pendant tout le transfert", "Sufficient personnel and watch on both sides throughout the transfer"),
            ("Interdiction de fumer, portes et hublots fermés, appareils électriques portatifs contrôlés", "Smoking prohibited, doors and ports closed, portable electrical equipment controlled"),
        ], columns=both),
        fields(("Partie 5A — Accords avant le transfert", "Part 5A — Pre-transfer agreements"), [
            F("Débit initial / maximal / de fin (m³/h)", "Initial / maximum / topping-off rate (m³/h)"),
            F("Pression maximale au collecteur (bar)", "Maximum manifold pressure (bar)"),
            F("Température maximale (°C)", "Maximum temperature (°C)"), F("Temps de fermeture des vannes (s)", "Valve closure time (s)"),
            F("Séquence des citernes et des bacs ; échantillonnage et jaugeage", "Tank and shore tank sequence; sampling and gauging", wide=True),
            F("Limites d'interruption (vent, houle, foudre, visibilité)", "Stop limits (wind, swell, lightning, visibility)", wide=True),
            F("Canal VHF principal / de secours ; langue", "Primary / backup VHF channel; language"),
            F("Intervalle des vérifications répétées (h)", "Interval of repetitive checks (h)"),
        ]),
        checklist(("Partie 6 — Vérifications répétées pendant et après le transfert", "Part 6 — Repetitive checks during and after transfer"), [
            ("Amarres, flexibles ou bras, pression et débit vérifiés", "Moorings, hoses/arms, pressure and rate checked"),
            ("Communication et veille maintenues ; conditions météo dans les limites", "Communication and watch maintained; weather within limits"),
            ("Ballastage conforme au plan ; tirant d'eau, assiette et francs-bords surveillés", "Ballast per plan; draft, trim and freeboard monitored"),
            ("Après transfert : lignes vidangées, collecteurs obturés, quantités constatées", "After transfer: lines drained, manifolds blanked, quantities agreed"),
        ], columns=[("Heure", "Time"), ("Navire", "Ship"), ("Terre", "Shore")]),
        text(("Déclaration", "Declaration"), [
            ("Nous, soussignés, avons vérifié ensemble, point par point, les éléments de cette liste, et nous nous sommes assurés que les réponses sont, à notre connaissance, exactes. Nous avons convenu de répéter les vérifications de la partie 6 à l'intervalle indiqué.",
             "We, the undersigned, have checked the items of this list together, item by item, and have satisfied ourselves that the answers are, to the best of our knowledge, correct. We have agreed to repeat the part 6 checks at the stated interval."),
        ], note=("Les parties suivent la structure de la liste de contrôle navire/terre de l'ISGOTT, 6e édition ; les points sont formulés par la plateforme, le terminal applique l'édition sous licence dont il dispose.",
                 "The parts follow the structure of the ISGOTT 6th edition ship/shore safety checklist; the items are worded by the platform, the terminal applies its licensed edition.")),
    ]


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
               ("Chronologie du registre — BIMCO Laytime Definitions for Charter Parties 2013", "Registry chronology — BIMCO Laytime Definitions for Charter Parties 2013"),
               frozenset({"AGE"}), [("AGE", ("Agence", "Agency")), ("NAV", ("Capitaine", "Master")), ("TER", ("Terminal", "Terminal"))], build_time_sheet, landscape=True,
               family="AGE", answers=("M0:37",), purpose=("La chronologie contradictoire de l'escale et ses interruptions, base du décompte du temps de planche.", "The contradictory chronology of the call and its stoppages, the basis of the laytime count.")))
_register(Form("SSSCL", "SSSCL", ("Liste de contrôle navire / terre", "Ship/shore safety checklist"),
               ("Structure de l'ISGOTT, 6e édition (OCIMF / ICS / IAPH), chapitre 25", "Structure of ISGOTT, 6th edition (OCIMF / ICS / IAPH), chapter 25"),
               frozenset({"TER", "NAV"}), [("NAV", ("Pour le navire", "For the ship")), ("TER", ("Pour le terminal", "For the terminal"))], build_ssscl,
               family="TER", answers=("M0:28",), purpose=("La liste de contrôle navire/terre signée conjointement avant le transfert et répétée pendant.", "The ship/shore safety checklist signed jointly before the transfer and repeated during it.")))
_register(Form("PRE_TRANSFER", "PRE_TRANSFER_MINUTES", ("Accord de transfert — réunion pré-transfert", "Transfer agreement — pre-transfer meeting"),
               ("ISGOTT, 6e édition, réunion pré-transfert et accords écrits", "ISGOTT, 6th edition, pre-transfer meeting and written agreements"),
               frozenset({"TER", "NAV"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship")), ("INS", ("Inspecteur", "Surveyor"))], build_pre_transfer,
               family="TER", answers=("M0:27",), purpose=("Le compte rendu de la réunion pré-transfert : paramètres, communication, urgence, accord écrit.", "The minutes of the pre-transfer meeting: parameters, communication, emergency, written agreement.")))
_register(Form("ULLAGE", "ULLAGE_REPORT", ("Rapport de jaugeage", "Ullage / sounding report"),
               ("API MPMS chapitre 17.1 et 17.2 (inspection des cargaisons maritimes) ; EI HM 28 ; tables ASTM D1250", "API MPMS chapters 17.1 and 17.2 (marine cargo inspection); EI HM 28; ASTM D1250 tables"),
               frozenset({"INS", "NAV", "TER"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Officier de quart / chef de cargaison", "Chief officer")), ("TER", ("Terminal", "Terminal"))], build_ullage, landscape=True,
               family="INS", answers=("M1:1.05", "M1:1.15", "M2:2.05", "M2:2.14", "M3:3.14"), purpose=("Le relevé de jaugeage des citernes, avec les quantités bord, terre et inspecteur du registre.", "The tank gauging report, with the ship, shore and surveyor quantities of the registry.")))
_register(Form("HOSES", "HOSE_RECORD", ("Relevé de connexion et de déconnexion", "Hose / arm connection and disconnection record"),
               ("ISGOTT, 6e édition (flexibles et bras de chargement) ; OCIMF Guide to Manufacturing and Purchasing Hoses for Offshore Moorings", "ISGOTT, 6th edition (hoses and loading arms); OCIMF hose guidelines"),
               frozenset({"TER", "NAV"}), [("TER", ("Terminal", "Terminal")), ("NAV", ("Navire", "Ship"))], build_hose_record,
               family="TER", answers=("M1:1.09", "M1:1.13", "MA2:A2.04"), purpose=("Le relevé des connexions et déconnexions des flexibles ou bras, avec les essais.", "The record of hose or arm connections and disconnections, with the tests.")))
_register(Form("PROTEST", "PROTEST", ("Lettre de protestation", "Letter of protest"),
               ("Usage maritime — réserve de droits, sans reconnaissance de responsabilité", "Maritime practice — reservation of rights without admission of liability"),
               frozenset({"AGE", "NAV", "TER", "INS", "PRE"}), [("AGE", ("Expéditeur", "Issuer")), ("TER", ("Destinataire — reçu", "Recipient — received"))], build_protest,
               family="AGE", answers=("M1:1.19", "M4:4.09"), purpose=("La lettre de protestation d'une partie, avec réserve de droits et accusé de réception.", "A party's letter of protest, with reservation of rights and acknowledgement.")))
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
