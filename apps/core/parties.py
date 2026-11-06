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
    # owner, charterer, cargo interests
    ("SHIPOWNER", "COM", "Armateur / propriétaire", "Shipowner"),
    ("SHIP_MANAGER", "COM", "Gestionnaire technique / opérateur", "Ship manager / operator"),
    ("CHARTERER", "COM", "Affréteur", "Charterer"),
    ("RECEIVER", "COM", "Réceptionnaire / importateur", "Receiver / importer"),
    ("SHIPPER", "COM", "Expéditeur / exportateur", "Shipper / exporter"),
    ("TRADER", "COM", "Négociant (trader)", "Trader"),
    ("COLLATERAL_MANAGER", "COM", "Gestionnaire de garanties / banque (collateral management)", "Collateral manager / bank"),
    ("INSURER", "COM", "Assureur / club P&I", "Insurer / P&I club"),
    ("BROKER", "COM", "Courtier maritime", "Ship broker"),
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
