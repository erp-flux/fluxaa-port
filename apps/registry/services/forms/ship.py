"""Forms issued by the vessel: ballast water reporting form, discharge / loading plan, last three cargoes,
inert gas declaration, hot work permit, enclosed space entry permit, declaration of an event on board."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _operation,
    _parties,
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


# ------------------------------------------------------------------------------------------------ ballast water
def build_ballast(call: PortCall) -> list[dict]:
    v = call.vessel
    return [
        fields(("Navire", "Vessel information"), [
            F("Nom / numéro OMI", "Name / IMO number", _vessel(call), source="Vessel.name, imo"), F("Pavillon", "Flag", v.flag or None, source="Vessel.flag"),
            F("Armateur / gestionnaire", "Owner / manager", _parties(call, "COM"), source="CallParty COM actives"), F("Type", "Type", v.vessel_type or None, source="Vessel.vessel_type"),
            F("Jauge brute / port en lourd (t)", "Gross tonnage / deadweight (t)", str(v.dwt) if v.dwt else None, source="Vessel.dwt"), F("Agent", "Agent", str(call.agency), source="PortCall.agency"),
            F("Port d'arrivée / date", "Arrival port / date", f"{call.port.name} — {dt(call.ata) or dt(call.eta)}", source="Port.name, PortCall.ata/eta"), F("Dernier port / prochain port", "Last port / next port", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, next_port"),
            F("Capacité totale de ballast (m³)", "Total ballast water capacity (m³)"), F("Volume total de ballast à bord (m³)", "Total ballast water on board (m³)"),
            F("Nombre de citernes de ballast", "Total number of ballast tanks"), F("Citernes à rejeter dans le port (nombre)", "Tanks to be discharged in port (number)"),
        ]),
        fields(("Gestion des eaux de ballast", "Ballast water management"), [
            F("Plan de gestion des eaux de ballast à bord ☐ appliqué ☐", "Ballast water management plan on board ☐ implemented ☐"),
            F("Méthode de conformité : D-1 échange ☐ D-2 système de traitement ☐ autre ☐", "Compliance method: D-1 exchange ☐ D-2 treatment system ☐ other ☐"),
            F("Système de traitement (type, approbation) — état : opérationnel ☐ en dérogation ☐", "Treatment system (type, approval) — status: operational ☐ under exemption ☐", wide=True),
            F("Certificat international de gestion des eaux de ballast (validité)", "International ballast water management certificate (validity)"),
            F("Registre des eaux de ballast à jour ☐", "Ballast water record book up to date ☐"),
        ]),
        table(("Historique des eaux de ballast par citerne", "Ballast water history per tank"),
              [("Citerne / cale", "Tank / hold"), ("Origine : date, port ou position, volume (m³), temp. (°C)", "Source: date, port or position, volume (m³), temp. (°C)"),
               ("Échange / traitement : date, position, volume (m³), méthode", "Exchange / treatment: date, position, volume (m³), method"),
               ("Rejet prévu : date, port ou position, volume (m³)", "Intended discharge: date, port or position, volume (m³)"), ("Nature (séparé, propre, souillé)", "Nature (segregated, clean, dirty)")],
              [], blank_rows=8),
        text(("Déclaration", "Declaration"), [
            ("Le responsable de la gestion des eaux de ballast certifie que les renseignements ci-dessus sont exacts et que le registre des eaux de ballast en fait foi.",
             "The responsible officer certifies that the above information is correct and that the ballast water record book bears it out."),
        ], note=("Modèle du Ballast Water Reporting Form (résolution OMI A.868(20), appendice 2) adapté à la Convention BWM 2004 (règles B-4, D-1, D-2) ; à transmettre avant l'arrivée.",
                 "Model of the Ballast Water Reporting Form (IMO resolution A.868(20), appendix 2) adapted to the BWM Convention 2004 (regulations B-4, D-1, D-2); to be sent before arrival.")),
    ]


_register(Form("BALLAST_NOTIFICATION", "BALLAST_NOTIFICATION", ("Notification des eaux de ballast (BWRF)", "Ballast water reporting form (BWRF)"),
               ("Convention BWM 2004 ; résolution OMI A.868(20), appendice 2 (Ballast Water Reporting Form)", "BWM Convention 2004; IMO resolution A.868(20), appendix 2 (Ballast Water Reporting Form)"),
               frozenset({"NAV"}), [("NAV", ("Officier responsable des eaux de ballast", "Responsible ballast water officer")), ("CAP", ("Autorité — reçu", "Authority — received"))],
               build_ballast, family="NAV", answers=("M0:15", "M5:5.02", "M5:5.03"),
               purpose=("La notification des eaux de ballast à bord : volumes, origine, méthode de conformité, rejets prévus.", "The ballast water report: volumes on board, origin, compliance method, intended discharges.")))


# ------------------------------------------------------------------------------------------------ cargo plans
def build_cargo_plan(call: PortCall, loading: bool) -> list[dict]:
    op = ("chargement", "loading") if loading else ("déchargement", "discharge")
    return [
        identification(call, F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active"),
                       F("Produit / quantité nominée", "Product / nominated quantity", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity")),
        fields(("Paramètres du plan", "Plan parameters"), [
            F("Débit initial / maximal / de fin (m³/h)", "Initial / maximum / topping-off rate (m³/h)"), F("Pression maximale au collecteur (bar)", "Maximum manifold pressure (bar)"),
            F("Nombre de lignes et de pompes", "Number of lines and pumps"), F("Température du produit (°C) / densité", "Product temperature (°C) / density"),
            F("Tirant d'eau et assiette : début / fin (m)", "Draft and trim: start / end (m)"), F("Stabilité (GM) et contraintes de structure (SF, BM) vérifiées ☐", "Stability (GM) and structural limits (SF, BM) checked ☐"),
            F("Gaz inerte : O₂ (%) et pression des citernes", "Inert gas: O₂ (%) and tank pressure"), F("Durée prévue (h)", "Planned duration (h)"),
        ]),
        table((f"Séquence de {op[0]} des citernes", f"Tank {op[1]} sequence"),
              [("Ordre", "Order"), ("Citerne", "Tank"), ("Produit", "Product"), ("Quantité (m³ / t)", "Quantity (m³ / t)"), ("Creux final (m)", "Final ullage (m)"), ("Débit (m³/h)", "Rate (m³/h)"), ("Début / fin prévus", "Planned start / end"), ("Observations", "Remarks")],
              [], blank_rows=10),
        table(("Séquence de ballastage / déballastage simultané", "Simultaneous ballasting / deballasting sequence"),
              [("Ordre", "Order"), ("Citerne de ballast", "Ballast tank"), ("Opération", "Operation"), ("Volume (m³)", "Volume (m³)"), ("Début / fin", "Start / end"), ("Observations", "Remarks")],
              [], blank_rows=5),
        text(("Accord", "Agreement"), [
            ("Le plan est établi par le chef de la cargaison sous l'autorité du capitaine et discuté avec le terminal à la réunion pré-transfert ; toute modification en cours d'opération est convenue entre les responsables de permanence et consignée.",
             "The plan is prepared by the chief officer under the master's authority and discussed with the terminal at the pre-transfer meeting; any change during the operation is agreed between the persons on duty and recorded."),
        ], note=("ISGOTT, 6e édition, chapitre 22 (plans de chargement et de déchargement) et 25 (réunion pré-transfert).", "ISGOTT, 6th edition, chapter 22 (loading and discharge plans) and 25 (pre-transfer meeting).")),
    ]


_register(Form("DISCHARGE_PLAN", "DISCHARGE_PLAN", ("Plan de déchargement et de ballastage", "Discharge and ballast plan"),
               ("ISGOTT, 6e édition, chapitre 22", "ISGOTT, 6th edition, chapter 22"),
               frozenset({"NAV"}), [("NAV", ("Chef de la cargaison / capitaine", "Chief officer / master")), ("TER", ("Terminal — accord", "Terminal — agreed"))],
               lambda call: build_cargo_plan(call, loading=False), family="NAV", templates=frozenset({"M1"}), answers=("M1:1.02",),
               purpose=("Le plan de déchargement et de ballastage remis au terminal avant la réunion pré-transfert.", "The discharge and ballast plan handed to the terminal before the pre-transfer meeting.")))
_register(Form("LOADING_PLAN", "LOADING_PLAN", ("Plan de chargement", "Loading plan"),
               ("ISGOTT, 6e édition, chapitre 22", "ISGOTT, 6th edition, chapter 22"),
               frozenset({"NAV"}), [("NAV", ("Chef de la cargaison / capitaine", "Chief officer / master")), ("TER", ("Terminal — accord", "Terminal — agreed"))],
               lambda call: build_cargo_plan(call, loading=True), family="NAV", templates=frozenset({"M2"}), answers=("M2:2.03",),
               purpose=("Le plan de chargement : séquence, stabilité, contraintes de structure, tirant d'eau.", "The loading plan: sequence, stability, structural limits, draft.")))


# ------------------------------------------------------------------------------------------------ last cargoes
def build_last_cargoes(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit à charger", "Product to be loaded", call.product or None, source="PortCall.product"), F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active")),
        table(("Trois dernières cargaisons par citerne", "Last three cargoes per tank"),
              [("Citerne", "Tank"), ("Dernière cargaison (produit, port, date)", "Last cargo (product, port, date)"), ("Avant-dernière", "Second last"), ("Antépénultième", "Third last"),
               ("Nettoyage effectué (méthode, date)", "Cleaning carried out (method, date)"), ("État : inerté ☐ dégazé ☐", "Condition: inerted ☐ gas-free ☐")],
              [], blank_rows=12),
        fields(("Lignes et pompes", "Lines and pumps"), [
            F("Dernier produit dans les lignes et pompes", "Last product in lines and pumps"), F("Lignes purgées / rincées (méthode)", "Lines drained / flushed (method)"),
            F("Revêtement des citernes", "Tank coating"), F("Ségrégation prévue pour la cargaison", "Segregation planned for the cargo"),
        ]),
        text(("Déclaration", "Declaration"), [
            ("Le capitaine déclare que les citernes désignées pour le chargement ont contenu les cargaisons ci-dessus et sont dans l'état indiqué ; l'inspection contradictoire des citernes et le certificat de propreté restent du ressort de l'inspecteur.",
             "The master declares that the tanks nominated for loading carried the cargoes above and are in the stated condition; the joint tank inspection and the cleanliness certificate remain the surveyor's."),
        ], note=("Exigence usuelle des terminaux et du vetting (questionnaire Q88 § cargo history ; ISGOTT ch. 22.4) : compatibilité du produit avec les cargaisons précédentes et le revêtement.",
                 "Usual terminal and vetting requirement (Q88 cargo history; ISGOTT ch. 22.4): compatibility of the product with the previous cargoes and the coating.")),
    ]


_register(Form("LAST_CARGOES", "LAST_CARGOES", ("Déclaration des trois dernières cargaisons", "Last three cargoes declaration"),
               ("Pratique des terminaux et du vetting (Q88, ISGOTT ch. 22.4)", "Terminal and vetting practice (Q88, ISGOTT ch. 22.4)"),
               frozenset({"NAV"}), [("NAV", ("Capitaine", "Master")), ("TER", ("Terminal — reçu", "Terminal — received"))],
               build_last_cargoes, family="NAV", templates=frozenset({"M2"}), answers=("M2:2.02",),
               purpose=("La déclaration des trois dernières cargaisons par citerne et du nettoyage effectué, avant chargement.", "The declaration of the last three cargoes per tank and of the cleaning done, before loading.")))


# ------------------------------------------------------------------------------------------------ inert gas
def build_inert_gas(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Opération", "Operation", _operation(call), source="PortCall.template_codes"), F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active")),
        fields(("Système de gaz inerte", "Inert gas system"), [
            F("Type (gaz de combustion, générateur, azote)", "Type (flue gas, generator, nitrogen)"), F("En service ☐ hors service ☐ — depuis", "Operational ☐ out of service ☐ — since"),
            F("Teneur en O₂ du gaz délivré (%)", "O₂ content of the gas delivered (%)"), F("Pression de dégagement / dépression (mbar)", "P/V valve setting (mbar)"),
            F("Analyseurs d'oxygène étalonnés le", "Oxygen analysers calibrated on"), F("Heure du relevé", "Time of readings"),
        ]),
        table(("Relevé par citerne", "Readings per tank"),
              [("Citerne", "Tank"), ("O₂ (%)", "O₂ (%)"), ("Pression (mbar)", "Pressure (mbar)"), ("Teneur en hydrocarbures (% LEL / vol.)", "Hydrocarbon content (% LEL / vol.)"), ("Inertée ☐", "Inerted ☐"), ("Observations", "Remarks")],
              [], blank_rows=12),
        text(("Déclaration", "Declaration"), [
            ("Le capitaine déclare que les citernes à cargaison sont inertées, que leur teneur en oxygène ne dépasse pas 8 % en volume et qu'une pression positive est maintenue ; en cas d'indisponibilité du système, aucune opération cargaison n'est entreprise sans l'accord écrit du terminal et de la capitainerie.",
             "The master declares that the cargo tanks are inerted, that their oxygen content does not exceed 8 % by volume and that a positive pressure is maintained; should the system be unavailable, no cargo operation is undertaken without the written agreement of the terminal and the harbour master."),
        ], note=("SOLAS II-2 règle 16.3 et FSS code ch. 15 (gaz inerte) ; ISGOTT 6e édition, chapitre 7 et liste de contrôle navire/terre, partie 1A.",
                 "SOLAS II-2 regulation 16.3 and FSS Code ch. 15 (inert gas); ISGOTT 6th edition, chapter 7 and ship/shore safety checklist, part 1A.")),
    ]


_register(Form("INERT_GAS_DECLARATION", "INERT_GAS_DECLARATION", ("Déclaration d'inertage et de teneur en oxygène", "Inert gas and oxygen content declaration"),
               ("SOLAS II-2 règle 16.3 ; code FSS chapitre 15 ; ISGOTT 6e édition, chapitre 7", "SOLAS II-2 regulation 16.3; FSS Code chapter 15; ISGOTT 6th edition, chapter 7"),
               frozenset({"NAV"}), [("NAV", ("Chef de la cargaison / capitaine", "Chief officer / master")), ("TER", ("Terminal — reçu", "Terminal — received"))],
               build_inert_gas, family="NAV", templates=frozenset({"M1", "M2", "M3"}), needs_link=True, answers=("M1:1.04", "M2:2.06"),
               purpose=("La déclaration de l'état du gaz inerte et de la teneur en oxygène des citernes avant le transfert.", "The declaration of the inert gas status and tank oxygen content before the transfer.")))


# ------------------------------------------------------------------------------------------------ permits
def build_hot_work_permit(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Autorisation de la capitainerie n°", "Harbour master's authorization no.", source="Authorization HOT_WORK"), F("Terminal informé", "Terminal informed", _party(call, "TER"), source="CallParty TER active")),
        fields(("Travaux", "Work"), [
            F("Lieu exact (espace, pont, compartiment)", "Exact location (space, deck, compartment)", wide=True), F("Nature des travaux et outillage", "Nature of the work and tools", wide=True),
            F("Personnes autorisées (noms, fonctions)", "Persons authorized (names, capacities)", wide=True), F("Entreprise extérieure", "Outside contractor", _party(call, "PRE"), source="CallParty PRE active"),
            F("Validité du permis : de / à (12 h maximum)", "Permit validity: from / to (12 h maximum)"), F("Certificat de dégazage n° / validité", "Gas-free certificate no. / validity"),
        ]),
        checklist(("Précautions", "Precautions"), [
            ("Espace et espaces adjacents dégazés ; atmosphère contrôlée : O₂ 20,9 %, hydrocarbures < 1 % LEL, toxiques dans les limites", "Space and adjacent spaces gas-free; atmosphere tested: O₂ 20.9 %, hydrocarbons < 1 % LEL, toxics within limits"),
            ("Citernes et lignes adjacentes isolées, obturées ou inertées ; résidus enlevés", "Adjacent tanks and lines isolated, blanked or inerted; residues removed"),
            ("Aucune opération cargaison, ballast, soutage ou dégazage simultanée", "No simultaneous cargo, ballast, bunkering or gas-freeing operation"),
            ("Veille incendie désignée, extincteurs et manche en pression sur place ; pendant les travaux et 60 min après", "Fire watch designated, extinguishers and charged hose at hand; during the work and 60 min after"),
            ("Équipement de travail contrôlé (câbles, bouteilles, détendeurs) ; mise à la terre", "Work equipment checked (cables, cylinders, regulators); earthing"),
            ("Communication avec la passerelle / salle de contrôle ; arrêt immédiat sur alarme", "Communication with the bridge / control room; immediate stop on alarm"),
        ], columns=[("Fait", "Done"), ("S.O.", "N/A")]),
        table(("Mesures d'atmosphère répétées", "Repeated atmosphere tests"),
              [("Heure", "Time"), ("Lieu", "Location"), ("O₂ (%)", "O₂ (%)"), ("LEL (%)", "LEL (%)"), ("H₂S / CO (ppm)", "H₂S / CO (ppm)"), ("Testé par", "Tested by")], [], blank_rows=4),
        text(("Permis", "Permit"), [
            ("Le capitaine délivre le présent permis, nominatif et limité dans le temps, aux conditions ci-dessus ; il est suspendu dès qu'une condition cesse d'être remplie. Il est délivré après l'autorisation écrite de la capitainerie et porté à la connaissance du terminal.",
             "The master issues this permit, nominative and time-limited, on the conditions above; it is suspended as soon as a condition ceases to be met. It is issued after the harbour master's written authorization and brought to the terminal's attention."),
        ], note=("ISGOTT 6e édition, chapitre 9 (travaux par point chaud) et modèle de permis ; code IGS/ISM de la compagnie.", "ISGOTT 6th edition, chapter 9 (hot work) and model permit; the company's safety management system.")),
    ]


_register(Form("HOT_WORK_PERMIT", "HOT_WORK_PERMIT", ("Permis de travail par point chaud", "Hot work permit"),
               ("ISGOTT 6e édition, chapitre 9 (modèle de permis de travail par point chaud)", "ISGOTT 6th edition, chapter 9 (model hot work permit)"),
               frozenset({"NAV"}), [("NAV", ("Capitaine — délivre", "Master — issues")), ("NAV", ("Responsable des travaux", "Person in charge of the work")), ("TER", ("Terminal — informé", "Terminal — informed"))],
               build_hot_work_permit, family="NAV", templates=frozenset({"M7"}), answers=("M7:7.06",),
               purpose=("Le permis nominatif et limité dans le temps délivré par le capitaine pour les travaux par point chaud.", "The nominative, time-limited permit issued by the master for hot work.")))


def build_enclosed_space_permit(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Terminal informé", "Terminal informed", _party(call, "TER"), source="CallParty TER active"), F("Permis n° / validité (de / à)", "Permit no. / validity (from / to)")),
        fields(("Espace et travaux", "Space and work"), [
            F("Espace à visiter", "Space to be entered"), F("Motif de l'entrée", "Reason for entry"),
            F("Personnes autorisées à entrer", "Persons authorized to enter", wide=True), F("Surveillant à l'extérieur", "Attendant outside"),
            F("Équipement de sauvetage prêt (ARI, harnais, treuil)", "Rescue equipment ready (SCBA, harness, hoist)", wide=True),
        ]),
        checklist(("Préparation", "Preparation"), [
            ("Espace ventilé, isolé (vannes, lignes, électricité) et éclairé", "Space ventilated, isolated (valves, lines, electricity) and lit"),
            ("Atmosphère mesurée à plusieurs niveaux : O₂ 20,9 %, hydrocarbures < 1 % LEL, toxiques dans les limites", "Atmosphere tested at several levels: O₂ 20.9 %, hydrocarbons < 1 % LEL, toxics within limits"),
            ("Ventilation continue et mesures répétées convenues ; détecteur personnel porté", "Continuous ventilation and repeat tests agreed; personal detector worn"),
            ("Communication convenue (radio, signaux) ; passerelle informée", "Communication agreed (radio, signals); bridge informed"),
        ], columns=[("Fait", "Done"), ("S.O.", "N/A")]),
        table(("Mesures d'atmosphère", "Atmosphere tests"),
              [("Heure", "Time"), ("Niveau", "Level"), ("O₂ (%)", "O₂ (%)"), ("LEL (%)", "LEL (%)"), ("H₂S / CO / autre (ppm)", "H₂S / CO / other (ppm)"), ("Testé par", "Tested by")], [], blank_rows=4),
        text(("Permis", "Permit"), [
            ("Le capitaine autorise l'entrée aux conditions ci-dessus ; le permis est nominatif, limité dans le temps et annulé dès qu'une condition change. Personne n'entre pour secourir sans équipement respiratoire.",
             "The master authorizes the entry on the conditions above; the permit is nominative, time-limited and cancelled as soon as a condition changes. No one enters to rescue without breathing apparatus."),
        ], note=("Résolution OMI A.1050(27) — recommandations révisées sur l'entrée dans les espaces clos à bord ; ISGOTT 6e édition, chapitre 10.",
                 "IMO resolution A.1050(27) — revised recommendations for entering enclosed spaces aboard ships; ISGOTT 6th edition, chapter 10.")),
    ]


_register(Form("ENCLOSED_SPACE_PERMIT", "ENCLOSED_SPACE_PERMIT", ("Permis d'entrée en espace clos", "Enclosed space entry permit"),
               ("Résolution OMI A.1050(27) ; ISGOTT 6e édition, chapitre 10", "IMO resolution A.1050(27); ISGOTT 6th edition, chapter 10"),
               frozenset({"NAV"}), [("NAV", ("Capitaine — délivre", "Master — issues")), ("NAV", ("Responsable de l'entrée", "Person in charge of the entry"))],
               build_enclosed_space_permit, family="NAV", templates=frozenset({"M6", "M7"}), answers=("M6:6.06",),
               purpose=("Le permis nominatif et limité dans le temps délivré par le capitaine pour l'entrée dans un espace clos.", "The nominative, time-limited permit issued by the master for entry into an enclosed space.")))


# ------------------------------------------------------------------------------------------------ event on board
def build_incident(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Déclaré par (nom, fonction)", "Declared by (name, capacity)"), F("Date et heure de l'événement", "Date and time of the event")),
        fields(("Événement", "Event"), [
            F("Nature : blessé grave ☐ décès ☐ passager clandestin ☐ pollution ☐ incendie ☐ avarie ☐ autre ☐", "Nature: serious injury ☐ death ☐ stowaway ☐ pollution ☐ fire ☐ damage ☐ other ☐", wide=True),
            F("Lieu (à bord, à quai, en rade)", "Place (on board, alongside, in the roads)", _where(call), source="poste ou zone de l'étape"), F("Personnes concernées (nombre, nationalité)", "Persons involved (number, nationality)"),
            F("Circonstances", "Circumstances", wide=True), F("Mesures prises à bord", "Measures taken on board", wide=True),
            F("Secours et autorités alertés (heure)", "Rescue services and authorities alerted (time)", wide=True), F("Conséquences sur l'opération", "Consequences for the operation"),
        ]),
        fields(("Suites", "Follow-up"), [
            F("Rapport de mer / déclaration d'accident déposé ☐ (référence)", "Sea protest / accident report filed ☐ (reference)"), F("Assureur / P&I informé ☐", "Insurer / P&I informed ☐"),
            F("Enquête demandée par", "Investigation requested by"), F("Pièces jointes (photos, témoignages)", "Attachments (photos, statements)"),
        ], note=("La déclaration est faite sans délai à la capitainerie, qui la transmet aux services compétents (santé, police, environnement) ; elle ne préjuge pas des responsabilités.",
                 "The declaration is made without delay to the harbour master, who passes it to the competent services (health, police, environment); it prejudges no liability.")),
    ]


_register(Form("INCIDENT_REPORT", "INCIDENT_REPORT", ("Déclaration d'événement à bord ou au poste", "Declaration of an event on board or at the berth"),
               ("Pratique portuaire (déclaration d'événement de mer) ; code IGS ; Convention FAL (passagers clandestins)", "Port practice (declaration of a marine event); ISM Code; FAL Convention (stowaways)"),
               frozenset({"NAV", "AGE", "TER", "SVC", "INS", "PRE"}), [("NAV", ("Capitaine ou déclarant", "Master or declarant")), ("CAP", ("Capitainerie — reçu", "Harbour master — received"))],
               build_incident, family="NAV", answers=("M8:8.07",),
               purpose=("La déclaration à la capitainerie de tout événement particulier : blessé, décès, passager clandestin, pollution, avarie.", "The declaration to the harbour master of any special event: injury, death, stowaway, pollution, damage.")))
