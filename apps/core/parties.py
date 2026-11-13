"""The parties of a tanker call — an open, non-exhaustive catalogue.

A call brings together far more organisations than the twelve roles name: pilots, tugs, boatmen, a laboratory,
a bunker barge, a waste contractor, a P&I correspondent, a classification surveyor… The *role* an organisation
holds on a call carries its rights (FLX-SPEC-001 §4); its *kind* says what it is in the port's own words. The
list below suggests the usual kinds, grouped by the role they normally hold; it is a help for the people who
invite the parties, never a closed list: any other kind can be typed, and the port administrator may add kinds
of his own. Nothing in the platform depends on a kind — only on the role.
"""
from __future__ import annotations

# (kind code, default role, French label, English label)
PARTY_KINDS: list[tuple[str, str, str, str]] = [
    # shipping agency
    ("SHIPPING_AGENT", "AGE", "Agence maritime / consignataire", "Shipping agent"),
    ("PROTECTING_AGENT", "AGE", "Agent protecteur (pour l'armateur)", "Protecting agent (for the owner)"),
    # vessel
    ("VESSEL", "NAV", "Navire / capitaine", "Vessel / master"),
    ("LIGHTERING_VESSEL", "NAV", "Navire allégeur / barge (STS)", "Lightering vessel / barge (STS)"),
    # terminal / depot
    ("OIL_TERMINAL", "TER", "Terminal pétrolier", "Oil terminal"),
    ("STORAGE_DEPOT", "TER", "Dépôt de stockage", "Storage depot"),
    ("REFINERY", "TER", "Raffinerie", "Refinery"),
    ("SPM_OPERATOR", "TER", "Exploitant de bouée / monobouée (SPM)", "SPM / buoy operator"),
    ("PIPELINE_OPERATOR", "TER", "Exploitant de pipeline", "Pipeline operator"),
    ("BULK_TERMINAL", "TER", "Terminal / quai de vrac sec", "Dry bulk terminal"),
    ("CONTAINER_TERMINAL", "TER", "Terminal à conteneurs", "Container terminal"),
    ("GENERAL_CARGO_TERMINAL", "TER", "Terminal de marchandises diverses / roulier", "General cargo / ro-ro terminal"),
    # harbour master, port authority, management
    ("HARBOUR_MASTER", "CAP", "Capitainerie", "Harbour master's office"),
    ("VTS", "CAP", "Centre de trafic maritime (VTS)", "Vessel traffic service (VTS)"),
    ("PORT_AUTHORITY", "APO", "Autorité portuaire", "Port authority"),
    ("PORT_MANAGEMENT", "DIR", "Direction du port", "Port management"),
    # marine services
    ("PILOTAGE", "SVC", "Station de pilotage", "Pilotage"),
    ("TOWAGE", "SVC", "Remorquage", "Towage"),
    ("MOORING", "SVC", "Lamanage / amarrage", "Mooring / boatmen"),
    ("LAUNCH_SERVICE", "SVC", "Vedettes / transbordement", "Launch / boat service"),
    # customs, immigration, health, maritime authority
    ("CUSTOMS", "ADM", "Douanes", "Customs"),
    ("IMMIGRATION", "ADM", "Immigration / police aux frontières", "Immigration / border police"),
    ("PORT_HEALTH", "ADM", "Santé portuaire / quarantaine", "Port health / quarantine"),
    ("MARITIME_AUTHORITY", "ADM", "Autorité maritime (État du port / du pavillon)", "Maritime authority (port / flag State)"),
    ("ENVIRONMENT_AUTHORITY", "ADM", "Autorité environnementale", "Environmental authority"),
    # security
    ("PORT_SECURITY", "SUR", "Sûreté portuaire (PFSO)", "Port facility security (PFSO)"),
    ("NAVY", "SUR", "Marine nationale / base navale", "Navy / naval base"),
    ("MARITIME_POLICE", "SUR", "Gendarmerie / police maritime", "Maritime police"),
    # surveyors and laboratories
    ("CARGO_SURVEYOR", "INS", "Inspecteur de cargaison (quantité, qualité)", "Cargo surveyor (quantity, quality)"),
    ("LABORATORY", "INS", "Laboratoire d'analyses", "Laboratory"),
    ("CLASS_SOCIETY", "INS", "Société de classification", "Classification society"),
    ("PANDI_SURVEYOR", "INS", "Expert P&I / correspondant", "P&I surveyor / correspondent"),
    ("VETTING_INSPECTOR", "INS", "Inspecteur vetting (SIRE / CDI)", "Vetting inspector (SIRE / CDI)"),
    ("MARINE_CHEMIST", "INS", "Chimiste maritime (dégazage)", "Marine chemist (gas-free)"),
    ("DRAFT_SURVEYOR", "INS", "Expert maritime (draft survey, avaries)", "Marine surveyor (draft survey, damage)"),
    ("TALLY_COMPANY", "INS", "Société de pointage (tally)", "Tally company"),
    ("BUNKER_SURVEYOR", "INS", "Inspecteur de soutage (bunker survey)", "Bunker surveyor"),
    # owner, charterer, cargo interests
    ("SHIPOWNER", "COM", "Armateur / propriétaire", "Shipowner"),
    ("SHIP_MANAGER", "COM", "Gestionnaire technique / opérateur", "Ship manager / operator"),
    ("CHARTERER", "COM", "Affréteur", "Charterer"),
    ("RECEIVER", "COM", "Réceptionnaire / importateur", "Receiver / importer"),
    ("SHIPPER", "COM", "Expéditeur / exportateur", "Shipper / exporter"),
    ("TRADER", "COM", "Négociant (trader)", "Trader"),
    ("SUPERINTENDENT", "COM", "Superintendant (représentant de l'armateur ou de l'affréteur)", "Superintendent (owner's or charterer's representative)"),
    ("SUPERCARGO", "COM", "Subrécargue (supercargo)", "Supercargo"),
    ("LOSS_CONTROL", "COM", "Contrôle des pertes (loss control) de l'affréteur ou du négociant", "Charterer's or trader's loss control"),
    ("COLLATERAL_MANAGER", "COM", "Gestionnaire de garanties / banque (collateral management)", "Collateral manager / bank"),
    ("INSURER", "COM", "Assureur / club P&I", "Insurer / P&I club"),
    ("BROKER", "COM", "Courtier maritime", "Ship broker"),
    ("FREIGHT_FORWARDER", "COM", "Transitaire / commissionnaire de transport", "Freight forwarder"),
    # service providers
    ("STS_PROVIDER", "PRE", "Prestataire STS (POAC, mooring master)", "STS service provider (POAC, mooring master)"),
    ("FENDER_HOSE_SUPPLIER", "PRE", "Fournisseur de défenses et de flexibles", "Fender and hose supplier"),
    ("BUNKER_SUPPLIER", "PRE", "Avitailleur en soutes / barge de soutage", "Bunker supplier / bunker barge"),
    ("WASTE_CONTRACTOR", "PRE", "Collecteur de déchets / installation de réception (MARPOL)", "Waste contractor / reception facility (MARPOL)"),
    ("TANK_CLEANING", "PRE", "Nettoyage et dégazage de citernes", "Tank cleaning and gas-freeing"),
    ("WATER_SUPPLIER", "PRE", "Fournisseur d'eau douce", "Fresh water supplier"),
    ("SHIP_CHANDLER", "PRE", "Avitailleur (provisions, ship chandler)", "Ship chandler"),
    ("CREW_AGENCY", "PRE", "Agence de relève d'équipage / manning", "Crew change / manning agency"),
    ("REPAIR_YARD", "PRE", "Chantier / entreprise de réparation", "Repair yard / contractor"),
    ("DIVING", "PRE", "Plongée / travaux sous-marins", "Diving / underwater services"),
    ("OIL_SPILL_RESPONSE", "PRE", "Lutte antipollution (OSRO)", "Oil spill response (OSRO)"),
    ("FIRE_SERVICE", "PRE", "Service incendie / sécurité civile", "Fire service / civil protection"),
    ("SECURITY_GUARDS", "PRE", "Gardiennage (non armé)", "Security guards (unarmed)"),
    ("TRANSPORT", "PRE", "Transport (camions-citernes, logistique)", "Transport (tank trucks, logistics)"),
    ("STEVEDORE", "PRE", "Entreprise de manutention (stevedore)", "Stevedoring company"),
    ("LASHING", "PRE", "Saisissage / arrimage", "Lashing / securing"),
    ("FUMIGATION", "PRE", "Fumigation / traitement phytosanitaire", "Fumigation / phytosanitary treatment"),
    ("WEIGHBRIDGE", "PRE", "Pesée à terre (pont-bascule)", "Weighbridge"),
    ("MEDICAL", "PRE", "Services médicaux / évacuation", "Medical services / evacuation"),
    ("TELECOM", "PRE", "Télécommunications / connectivité", "Telecommunications / connectivity"),
    ("OTHER", "", "Autre partie", "Other party"),
]


def kinds_for_role(role: str) -> list[tuple[str, str, str]]:
    """(code, fr, en) of the kinds usually holding *role* — a suggestion list, never a restriction."""
    return [(code, fr, en) for code, r, fr, en in PARTY_KINDS if r == role]


def kind_label(code_or_text: str, lang: str = "fr") -> str:
    for code, _r, fr, en in PARTY_KINDS:
        if code == code_or_text:
            return en if lang == "en" else fr
    return code_or_text


def normalize_kind(text: str) -> str:
    """A kind typed by a person: a known code, or a known French / English label, becomes the code (so that it is
    displayed in both languages); anything else is kept as typed — the list is not exhaustive."""
    value = " ".join((text or "").split())
    if not value:
        return ""
    folded = value.casefold()
    for code, _r, fr, en in PARTY_KINDS:
        if folded == code.casefold() or folded in _alternatives(fr) or folded in _alternatives(en):
            return code
    return value[:80]


def _alternatives(label: str) -> set[str]:
    """The label and each of its parts: "Bunker supplier / bunker barge" answers to "bunker supplier"."""
    parts = {label}
    for sep in (" / ", " (", ", "):
        for part in list(parts):
            parts.update(p.strip(" )") for p in part.split(sep))
    return {p.casefold() for p in parts if p}


def default_role(kind: str) -> str:
    for code, role, _fr, _en in PARTY_KINDS:
        if code == kind:
            return role
    return ""


# --------------------------------------------------------------------------------------------
# The parties an operation usually brings to the call (FLX-CDC-002 v1.6, EXG-R-11): when the agency ticks a model
# on the announcement, the form lists these beside the parties block, each with a button that adds the row with
# its role and kind — a suggestion drawn from port practice, never a requirement; the open list stays open.
# (template code → [(kind code, French reason, English reason)]; the role is the kind's default role)
# --------------------------------------------------------------------------------------------
PARTIES_BY_OPERATION: dict[str, list[tuple[str, str, str]]] = {
    "M1": [("OIL_TERMINAL", "reçoit la cargaison, tient le journal de pompage côté terre", "receives the cargo, keeps the shore pumping log"),
           ("CARGO_SURVEYOR", "jaugeages, échantillons, certificat de quantité", "ullages, samples, quantity certificate"),
           ("RECEIVER", "destinataire de la cargaison, lecteur du time sheet", "consignee of the cargo, reads the time sheet"),
           ("LABORATORY", "analyses de qualité avant et après transfert", "quality analyses before and after the transfer")],
    "M2": [("OIL_TERMINAL", "expédie la cargaison, tient le journal de pompage côté terre", "ships the cargo, keeps the shore pumping log"),
           ("CARGO_SURVEYOR", "jaugeages, échantillons, certificat de quantité", "ullages, samples, quantity certificate"),
           ("SHIPPER", "chargeur / exportateur, instruction documentaire", "shipper / exporter, documentary instruction"),
           ("LABORATORY", "certificat de qualité du lot chargé", "quality certificate of the parcel loaded")],
    "M3": [("STS_PROVIDER", "fournit le POAC, les défenses et les flexibles ; tenu de la liste de contrôle STS", "provides the POAC, fenders and hoses; keeps the STS checklist"),
           ("CARGO_SURVEYOR", "mesures contradictoires sur les deux navires", "joint measurements on both vessels"),
           ("CHARTERER", "affréteur ou négociant qui ordonne le transbordement", "charterer or trader ordering the transfer")],
    "M4": [("BUNKER_SUPPLIER", "soutier : licence, certification de la barge, BDN", "bunker supplier: licence, barge certification, BDN"),
           ("BUNKER_SURVEYOR", "contrôle des quantités livrées (optionnel)", "checks the quantities delivered (optional)")],
    "M5": [("LABORATORY", "analyse des eaux de ballast si l'autorité l'exige (optionnel)", "ballast water analysis when the authority requires it (optional)")],
    "M6": [("WASTE_CONTRACTOR", "installation de réception des déchets et des slops (MARPOL)", "reception facility for waste and slops (MARPOL)"),
           ("TANK_CLEANING", "nettoyage et dégazage des citernes, chimiste maritime", "tank cleaning and gas-freeing, marine chemist")],
    "M7": [("REPAIR_YARD", "entreprise de réparation, permis de travaux", "repair contractor, works permit"),
           ("CLASS_SOCIETY", "présence de la classification si les travaux la concernent", "class attendance when the works concern it"),
           ("DIVING", "travaux sous-marins, inspection de la coque (optionnel)", "underwater works, hull inspection (optional)")],
    "M8": [("CREW_AGENCY", "relève d'équipage : visas, transport, hébergement", "crew change: visas, transport, accommodation"),
           ("SHIP_CHANDLER", "avitaillement en vivres et pièces", "provisions and spares"),
           ("WATER_SUPPLIER", "eau douce (optionnel)", "fresh water (optional)"),
           ("MEDICAL", "consultation ou évacuation médicale (optionnel)", "medical consultation or evacuation (optional)")],
    "M9": [("FENDER_HOSE_SUPPLIER", "défenses et certificats, si ni le terminal ni le navire extérieur ne les fournissent", "fenders and certificates, when neither the terminal nor the outer vessel supplies them")],
    "MB1": [("BULK_TERMINAL", "quai, aires de stockage, cadence de déchargement", "quay, storage areas, discharge rate"),
            ("STEVEDORE", "manutention : grues, grappins, trémies, équipes", "stevedoring: cranes, grabs, hoppers, gangs"),
            ("DRAFT_SURVEYOR", "draft survey initial et final, inspection des cales", "initial and final draft survey, hold inspection"),
            ("RECEIVER", "réceptionnaire, destinataire du constat de quantité", "receiver, addressee of the quantity statement"),
            ("WEIGHBRIDGE", "pesée à terre si le port compte en pesées (optionnel)", "shore weighing when the port counts by weighbridge (optional)")],
    "MB2": [("BULK_TERMINAL", "quai, stocks à charger, cadence de chargement", "quay, stock to load, loading rate"),
            ("STEVEDORE", "manutention : chargeur, nivellement des cales", "stevedoring: loader, trimming of the holds"),
            ("DRAFT_SURVEYOR", "draft survey, acceptation des cales", "draft survey, hold acceptance"),
            ("SHIPPER", "chargeur / exportateur : déclaration IMSBC, instruction documentaire", "shipper / exporter: IMSBC declaration, documentary instruction")],
    "MC1": [("CONTAINER_TERMINAL", "terminal : bay plan, moyens, plan de travail", "terminal: bay plan, means, work plan"),
            ("STEVEDORE", "manutention et saisissage si le terminal ne les assure pas", "stevedoring and lashing when the terminal does not provide them"),
            ("FREIGHT_FORWARDER", "transitaire des conteneurs import / export (optionnel)", "forwarder of the import / export containers (optional)")],
    "MG1": [("GENERAL_CARGO_TERMINAL", "quai et aires, moyens de levage", "quay and areas, lifting gear"),
            ("STEVEDORE", "manutention, colis lourds, saisissage", "stevedoring, heavy lifts, lashing"),
            ("TALLY_COMPANY", "pointage contradictoire, constat de réception", "joint tally, out-turn report"),
            ("RECEIVER", "réceptionnaire ou chargeur des colis", "receiver or shipper of the packages")],
    "MR1": [("GENERAL_CARGO_TERMINAL", "terminal roulier : rampe, aires de parcage", "ro-ro terminal: ramp, parking areas"),
            ("STEVEDORE", "conducteurs, saisissage des unités", "drivers, securing of the units"),
            ("TALLY_COMPANY", "pointage et constat de dommages des unités", "tally and damage report of the units"),
            ("RECEIVER", "réceptionnaire des véhicules", "receiver of the vehicles")],
    "MX1": [("STEVEDORE", "manutention si l'escale en comporte (optionnel)", "stevedoring when the call needs it (optional)")],
}


def parties_for_operation(code: str, lang: str = "fr") -> list[dict]:
    """The parties the model usually calls for, with their default role and labels — for the announcement."""
    out = []
    for kind, why_fr, why_en in PARTIES_BY_OPERATION.get(code, []):
        out.append({"kind": kind, "role": default_role(kind), "label": kind_label(kind, lang),
                    "why": why_en if lang == "en" else why_fr})
    return out
