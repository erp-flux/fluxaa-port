"""Forms issued by the shipping agency: arrival notice, sanctions screening attestation, STS notification to the
coastal State, POAC designation, cargo declaration and outward manifest (FAL 2), ship's stores and crew's effects
(FAL 3 and 4), crew change list, bill of lading, final port account."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _m,
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


# ------------------------------------------------------------------------------------------------ arrival notice
def build_arrival_notice(call: PortCall) -> list[dict]:
    v = call.vessel
    stage = call.stages.order_by("order").first()
    return [
        fields(("Navire", "Vessel"), [
            F("Nom / numéro OMI", "Name / IMO number", _vessel(call), source="Vessel.name, Vessel.imo"), F("Pavillon / type", "Flag / type", " — ".join(filter(None, [v.flag, v.vessel_type])) or None, source="Vessel.flag, vessel_type"),
            F("Indicatif / MMSI", "Call sign / MMSI", v.call_sign or None, source="Vessel.call_sign"), F("Port en lourd (t)", "Deadweight (t)", str(v.dwt) if v.dwt else None, source="Vessel.dwt"),
            F("Longueur hors tout / largeur (m)", "Length overall / breadth (m)", f"{v.loa_m or '—'} / {v.beam_m or '—'}" if (v.loa_m or v.beam_m) else None, source="Vessel.loa_m, beam_m"),
            F("Tirant d'eau à l'arrivée AV / AR (m)", "Arrival draft fwd / aft (m)"), F("Armateur / gestionnaire", "Owner / manager", _parties(call, "COM"), source="CallParty COM actives"),
            F("Agent consignataire", "Shipping agent", str(call.agency), source="PortCall.agency"),
        ]),
        fields(("Escale", "Call"), [
            F("Référence", "Reference", call.reference, source="PortCall.reference"), F("Voyage", "Voyage", call.voyage_number or None, source="PortCall.voyage_number"),
            F("ETA limite du port", "ETA port limits", dt(call.eta), source="PortCall.eta"), F("ETB", "ETB", dt(call.etb), source="PortCall.etb"),
            F("ETD", "ETD", dt(call.etd), source="PortCall.etd"), F("Dernier port / prochain port", "Last port / next port", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, next_port"),
            F("Zone sollicitée / poste", "Area requested / berth", _where(call), source="PortCall.requested_berth_kind, berth"),
            F("Opérations", "Operations", ", ".join(stage.operations) if stage else ", ".join(call.template_codes), source="CallStage.operations"),
            F("Opération principale", "Main operation", _operation(call), source="PortCall.template_codes"),
            F("Produit / quantité", "Product / quantity", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity"),
            F("Terminal / réceptionnaire", "Terminal / receiver", _parties(call, "TER"), source="CallParty TER actives"), F("Inspecteur", "Surveyor", _parties(call, "INS"), source="CallParty INS actives"),
        ]),
        checklist(("Services et formalités sollicités", "Services and formalities requested"), [
            ("Pilotage, remorquage, lamanage à l'arrivée", "Pilot, tugs, mooring gang on arrival"), ("Libre pratique et formalités d'arrivée", "Free pratique and arrival formalities"),
            ("Soutage", "Bunkering"), ("Eau douce / provisions / relève d'équipage", "Fresh water / provisions / crew change"),
            ("Dépôt de déchets (notification préalable jointe)", "Waste delivery (advance notification attached)"), ("Travaux / immobilisation", "Repairs / immobilization"),
        ], columns=[("Oui", "Yes"), ("Non", "No")]),
        fields(("Pré-arrivée", "Pre-arrival"), [
            F("Jeu de données navire (Q88 / VPQ) transmis le", "Vessel dataset (Q88 / VPQ) sent on"), F("Certificats statutaires valides au départ prévu ☐", "Statutory certificates valid at planned departure ☐"),
            F("Contrôle des listes de sanctions (date, résultat)", "Sanctions screening (date, result)"), F("Dernière cargaison / état des citernes", "Last cargo / tank condition"),
            F("Marchandises dangereuses en colis à bord", "Packaged dangerous goods on board"), F("Observations", "Remarks", wide=True),
        ], note=("Avis d'arrivée transmis à la capitainerie, à l'autorité portuaire, aux services nautiques et au terminal au moins 72 h, puis 48 h et 24 h avant l'arrivée (ou dès le départ du port précédent si le voyage est plus court).",
                 "Arrival notice sent to the harbour master, the port authority, the marine services and the terminal at least 72 h, then 48 h and 24 h before arrival (or on departure from the previous port when the voyage is shorter).")),
    ]


_register(Form("ARRIVAL_NOTICE", "ARRIVAL_NOTICE", ("Avis d'arrivée (préavis 72 / 48 / 24 h)", "Arrival notice (72 / 48 / 24 h pre-arrival notification)"),
               ("Pratique portuaire — règlement d'exploitation du port ; Convention FAL (notification préalable)", "Port practice — port operating regulations; FAL Convention (advance notification)"),
               frozenset({"AGE"}), [("AGE", ("Agence maritime", "Shipping agency")), ("CAP", ("Capitainerie — reçu", "Harbour master — received"))],
               build_arrival_notice, family="AGE", answers=("M0:01", "M0:08"),
               purpose=("Le préavis d'arrivée de l'agence : navire, heures prévues, opérations, services et formalités sollicités.",
                        "The agency's pre-arrival notice: vessel, expected times, operations, services and formalities requested.")))


# ------------------------------------------------------------------------------------------------ sanctions screening
def build_sanctions(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit / origine / destination", "Product / origin / destination", f"{call.product or '—'} — {call.last_port or '—'} → {call.next_port or '—'}", source="PortCall.product, last_port, next_port")),
        table(("Parties et objets contrôlés", "Parties and items screened"),
              [("Objet du contrôle", "Item screened"), ("Nom / identifiant", "Name / identifier"), ("Résultat (aucune correspondance / correspondance / levée)", "Result (no match / match / cleared)"), ("Date", "Date")],
              [["Navire / Vessel", _vessel(call), None, None], ["Armateur et gestionnaire / Owner and manager", _parties(call, "COM"), None, None],
               ["Affréteur / Charterer", None, None, None], ["Expéditeur et réceptionnaire / Shipper and receiver", _parties(call, "TER"), None, None],
               ["Cargaison, origine, destination / Cargo, origin, destination", call.product or None, None, None],
               ["Banques et assureurs intervenants / Banks and insurers involved", None, None, None]], blank_rows=1,
              source="Vessel, CallParty COM et TER, PortCall.product"),
        fields(("Listes et outils consultés", "Lists and tools consulted"), [
            F("Listes de sanctions (ONU, UE, OFAC, OFSI, autres)", "Sanctions lists (UN, EU, OFAC, OFSI, others)", wide=True),
            F("Outil ou prestataire de filtrage, version", "Screening tool or provider, version"), F("Pavillon et historique de changement de nom / pavillon", "Flag and name / flag change history"),
            F("Signalements AIS (coupures, falsifications) examinés", "AIS reporting gaps and spoofing reviewed"), F("Conclusion", "Conclusion", wide=True),
        ]),
        text(("Attestation", "Attestation"), [
            ("L'agence atteste avoir effectué le contrôle ci-dessus à la date indiquée et n'avoir relevé aucune correspondance non levée ; toute correspondance est signalée à la capitainerie avant la déclaration de l'escale.",
             "The agency attests that it carried out the screening above on the stated date and found no uncleared match; any match is reported to the harbour master before the call is declared."),
        ], note=("Bonnes pratiques de conformité aux sanctions du transport maritime (OFAC Sanctions Advisory for the Maritime Industry, 2020 ; guides BIMCO / ICS) ; le contrôle se renouvelle avant chaque opération si les parties changent.",
                 "Maritime sanctions compliance good practice (OFAC Sanctions Advisory for the Maritime Industry, 2020; BIMCO / ICS guidance); the screening is renewed before each operation if the parties change.")),
    ]


_register(Form("SANCTIONS_CHECK", "SANCTIONS_CHECK", ("Attestation de contrôle des listes de sanctions", "Sanctions screening attestation"),
               ("OFAC Sanctions Advisory for the Maritime Industry (2020) ; guides BIMCO / ICS de conformité aux sanctions", "OFAC Sanctions Advisory for the Maritime Industry (2020); BIMCO / ICS sanctions compliance guidance"),
               frozenset({"AGE"}), [("AGE", ("Agence — responsable conformité", "Agency — compliance officer"))],
               build_sanctions, family="AGE", answers=("M0:05",),
               purpose=("L'attestation par laquelle l'agence confirme le contrôle des listes de sanctions du navire, de ses intérêts et de la cargaison.",
                        "The attestation by which the agency confirms the sanctions screening of the vessel, its interests and the cargo.")))


# ------------------------------------------------------------------------------------------------ STS notification, POAC
def build_sts_notification(call: PortCall) -> list[dict]:
    partner = call.linked_call
    return [
        fields(("Opération STS notifiée", "STS operation notified"), [
            F("Navire (ce dossier)", "Vessel (this file)", _vessel(call), source="Vessel.name, imo"), F("Pavillon / indicatif", "Flag / call sign", " / ".join(filter(None, [call.vessel.flag, call.vessel.call_sign])) or None, source="Vessel.flag, call_sign"),
            F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"), F("Pavillon / indicatif du partenaire", "Partner's flag / call sign", " / ".join(filter(None, [partner.vessel.flag, partner.vessel.call_sign])) if partner else None, source="linked_call.vessel"),
            F("Date et heure prévues de début", "Planned start date and time", dt(call.ets), source="PortCall.ets"), F("Durée prévue", "Planned duration"),
            F("Lieu (zone STS, position)", "Location (STS area, position)", _where(call), source="poste ou zone de l'étape"), F("Hydrocarbure (type) et quantité", "Oil (type) and quantity", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity"),
            F("Prestataire STS / POAC", "STS service provider / POAC", _party(call, "PRE"), source="CallParty PRE active"), F("Autorité notifiée (État côtier, capitainerie)", "Authority notified (coastal State, harbour master)", f"{call.port.name}", source="Port.name"),
        ]),
        checklist(("Confirmations", "Confirmations"), [
            ("Plan d'opérations STS approuvé par l'État du pavillon à bord (MARPOL annexe I, règle 41)", "STS operations plan approved by the flag State on board (MARPOL Annex I, regulation 41)"),
            ("Les deux navires sont des pétroliers de 150 jauge brute et plus au sens de la règle 40", "Both ships are oil tankers of 150 gross tonnage and above within the meaning of regulation 40"),
            ("Notification faite au moins 48 h avant l'opération (règle 42)", "Notification given at least 48 h before the operation (regulation 42)"),
            ("Les enregistrements de l'opération seront conservés à bord trois ans", "Records of the operation will be kept on board for three years"),
        ], columns=[("Oui", "Yes"), ("Non", "No")]),
        text(("Notification", "Notification"), [
            ("Conformément à la règle 42 de l'annexe I de MARPOL, l'agence notifie à l'État côtier, au nom du capitaine, l'opération de transbordement ci-dessus ; toute modification des éléments notifiés est communiquée sans délai.",
             "In accordance with regulation 42 of MARPOL Annex I, the agency notifies the coastal State, on behalf of the master, of the above transfer operation; any change to the notified particulars is communicated without delay."),
        ]),
    ]


_register(Form("STS_NOTIFICATION", "STS_NOTIFICATION", ("Notification d'opération STS à l'État côtier", "STS operation notification to the coastal State"),
               ("MARPOL annexe I, chapitre 8, règle 42 (notification 48 h) ; OCIMF Ship to Ship Transfer Guide", "MARPOL Annex I, chapter 8, regulation 42 (48 h notification); OCIMF Ship to Ship Transfer Guide"),
               frozenset({"AGE"}), [("AGE", ("Agence, pour le capitaine", "Agency, for the master")), ("CAP", ("Autorité — reçu", "Authority — received"))],
               build_sts_notification, family="AGE", templates=frozenset({"M3"}), needs_link=True, answers=("M3:3.01",),
               purpose=("La notification préalable (48 h) de l'opération STS à l'État côtier : navires, lieu, date, produit, quantité, POAC.",
                        "The 48 h prior notification of the STS operation to the coastal State: vessels, place, date, product, quantity, POAC.")))


def build_poac(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"),
                       F("Prestataire STS", "STS service provider", _party(call, "PRE"), source="CallParty PRE active")),
        fields(("Personne responsable de l'opération (POAC)", "Person in overall advisory control (POAC)"), [
            F("Nom et prénom", "Full name"), F("Employeur", "Employer"), F("Brevet de capitaine / qualification", "Master's licence / qualification"),
            F("Expérience STS (nombre d'opérations, types de navires)", "STS experience (number of operations, ship types)", wide=True),
            F("Formation STS suivie (organisme, date)", "STS training completed (body, date)"), F("Contact (VHF, téléphone)", "Contact (VHF, telephone)"),
        ]),
        text(("Mandat", "Mandate"), [
            ("L'agence, au nom des parties à l'opération, désigne la personne ci-dessus comme POAC de l'opération de transbordement. Le POAC conseille les deux capitaines sur l'approche, l'amarrage, le transfert et la séparation ; la responsabilité de la sécurité de chaque navire reste à son capitaine.",
             "The agency, on behalf of the parties to the operation, appoints the person above as POAC of the transfer operation. The POAC advises both masters on approach, mooring, transfer and unmooring; the safety of each ship remains the responsibility of its master."),
            ("Les justificatifs de qualification sont joints au dossier STS de l'escale.", "The qualification documents are attached to the STS file of the call."),
        ], note=("OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapitre 1.5 et 3 ; MARPOL annexe I, règle 41.",
                 "OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapters 1.5 and 3; MARPOL Annex I, regulation 41.")),
    ]


_register(Form("POAC_DESIGNATION", "STS_DOC", ("Désignation du POAC — mandat écrit", "POAC designation — written mandate"),
               ("OCIMF Ship to Ship Transfer Guide (2013) ; MARPOL annexe I, règle 41", "OCIMF Ship to Ship Transfer Guide (2013); MARPOL Annex I, regulation 41"),
               frozenset({"AGE"}), [("AGE", ("Agence", "Agency")), ("PRE", ("POAC — accepte le mandat", "POAC — accepts the mandate")), ("NAV", ("Capitaine", "Master"))],
               build_poac, family="AGE", templates=frozenset({"M3"}), needs_link=True, answers=("M3:3.04",),
               purpose=("Le mandat écrit désignant le POAC de l'opération STS, avec ses qualifications.", "The written mandate appointing the POAC of the STS operation, with the qualifications.")))


# ------------------------------------------------------------------------------------------------ FAL 2, 3, 4
def _fal_header(call: PortCall, arrival: bool | None = None) -> dict:
    v = call.vessel
    return fields(("Navire et escale", "Ship and call"), [
        F("Arrivée ☐ Départ ☐", "Arrival ☐ Departure ☐", "Arrivée / Arrival ☒" if arrival else ("Départ / Departure ☒" if arrival is False else None)),
        F("Nom et type du navire", "Name and type of ship", f"{v.name} — {v.vessel_type or '—'}", source="Vessel.name, vessel_type"),
        F("Numéro OMI", "IMO number", v.imo, source="Vessel.imo"), F("Indicatif", "Call sign", v.call_sign or None, source="Vessel.call_sign"),
        F("Pavillon", "Flag State of ship", v.flag or None, source="Vessel.flag"), F("Nom du capitaine", "Name of master"),
        F("Port d'arrivée / de départ", "Port of arrival / departure", call.port.name, source="Port.name"), F("Date d'arrivée / de départ", "Date of arrival / departure", dt(call.ata) or dt(call.eta), source="PortCall.ata, eta"),
        F("Dernier port / prochain port", "Last port / next port", " / ".join(filter(None, [call.last_port, call.next_port])) or None, source="PortCall.last_port, next_port"),
        F("Agent", "Agent", str(call.agency), source="PortCall.agency"),
    ])


def build_cargo_declaration(call: PortCall, outward: bool = False) -> list[dict]:
    load = _m(call, "TRANSFER_END")
    rows = [[None, call.product or None, f"{call.quantity} {call.quantity_unit}" if call.quantity else None,
             call.last_port if not outward else call.port.name, call.port.name if not outward else (call.next_port or None), None]]
    return [
        _fal_header(call, arrival=not outward),
        table(("Cargaison", "Cargo"),
              [("N° de connaissement", "B/L number"), ("Description des marchandises (produit, grade)", "Description of goods (product, grade)"),
               ("Quantité (masse / volume)", "Quantity (mass / volume)"), ("Port de chargement", "Port of loading"), ("Port de déchargement", "Port of discharge"), ("Marques, observations", "Marks, remarks")],
              rows, blank_rows=3, source="PortCall.product, quantity, last_port, next_port"),
        fields(("Compléments", "Additional particulars"), [
            F("Cargaison restant à bord (transit)", "Cargo remaining on board (in transit)"), F("Date de fin des opérations", "Date of completion of cargo operations", dt(load.declared_at) if load else None, source="jalon TRANSFER_END"),
            F("Déclaration douanière / manifeste n°", "Customs declaration / manifest number"), F("Régime douanier", "Customs procedure"),
        ], note=("Modèle de la déclaration de cargaison, formulaire FAL 2 de l'OMI (Convention FAL, annexe, section 2) ; vrac liquide : une ligne par produit et par connaissement.",
                 "Model of the cargo declaration, IMO FAL form 2 (FAL Convention, annex, section 2); liquid bulk: one line per product and per bill of lading.")),
        text(("Déclaration", "Declaration"), [("Le capitaine (ou l'agent autorisé) certifie l'exactitude de la présente déclaration.", "The master (or authorized agent) certifies this declaration to be correct.")]),
    ]


_register(Form("CARGO_DECLARATION", "CARGO_DECLARATION", ("Déclaration de cargaison (FAL 2) — arrivée", "Cargo declaration (FAL 2) — arrival"),
               ("Convention FAL de l'OMI, formulaire 2", "IMO FAL Convention, form 2"),
               frozenset({"AGE"}), [("AGE", ("Agent autorisé", "Authorized agent")), ("ADM", ("Douanes — visa", "Customs — endorsement"))],
               lambda call: build_cargo_declaration(call, outward=False), family="AGE", templates=frozenset({"M1"}), answers=("M1:1.18",),
               purpose=("La déclaration douanière de la cargaison déchargée (FAL 2), pré-remplie du produit et de la quantité de l'escale.",
                        "The customs declaration of the discharged cargo (FAL 2), pre-filled with the call's product and quantity.")))
_register(Form("EXPORT_MANIFEST", "EXPORT_MANIFEST", ("Manifeste et déclaration de cargaison (FAL 2) — départ", "Outward manifest and cargo declaration (FAL 2) — departure"),
               ("Convention FAL de l'OMI, formulaire 2 (départ)", "IMO FAL Convention, form 2 (departure)"),
               frozenset({"AGE"}), [("AGE", ("Agent autorisé", "Authorized agent")), ("ADM", ("Douanes — visa", "Customs — endorsement"))],
               lambda call: build_cargo_declaration(call, outward=True), family="AGE", templates=frozenset({"M2"}), answers=("M2:2.18",),
               purpose=("Le manifeste de sortie et la déclaration d'exportation de la cargaison chargée (FAL 2).", "The outward manifest and export declaration of the loaded cargo (FAL 2).")))


def build_stores(call: PortCall) -> list[dict]:
    return [
        _fal_header(call),
        table(("Provisions de bord (FAL 3)", "Ship's stores (FAL 3)"),
              [("Article", "Name of article"), ("Quantité", "Quantity"), ("Emplacement à bord", "Location on board"), ("Usage officiel", "Official use")],
              [["Spiritueux / Spirits", None, None, None], ["Vin, bière / Wine, beer", None, None, None], ["Tabac, cigarettes / Tobacco, cigarettes", None, None, None],
               ["Combustibles de soute (type, tonnes) / Bunker fuel (type, tonnes)", None, None, None], ["Lubrifiants / Lubricating oil", None, None, None],
               ["Armes, munitions / Arms, ammunition", None, None, None], ["Médicaments, stupéfiants / Medicines, narcotics", None, None, None],
               ["Provisions alimentaires / Provisions", None, None, None]], blank_rows=3),
        table(("Effets de l'équipage (FAL 4)", "Crew's effects (FAL 4)"),
              [("N°", "No."), ("Nom de famille, prénoms", "Family name, given names"), ("Fonction", "Rank or rating"), ("Effets soumis à droits ou à restriction", "Effects liable to duty or restriction"), ("Signature", "Signature")],
              [], blank_rows=8),
        text(("Déclaration", "Declaration"), [
            ("Le capitaine certifie que les provisions de bord et les effets déclarés ci-dessus sont exacts ; les provisions sous scellés sont tenues à la disposition des douanes.",
             "The master certifies that the ship's stores and effects declared above are correct; bonded stores are kept at the disposal of customs."),
        ], note=("Modèles des formulaires FAL 3 (provisions de bord) et FAL 4 (effets de l'équipage) de l'OMI.", "Models of IMO FAL forms 3 (ship's stores) and 4 (crew's effects).")),
    ]


_register(Form("FAL_STORES", "FAL_FORMS", ("Provisions de bord et effets de l'équipage (FAL 3 et 4)", "Ship's stores and crew's effects (FAL 3 and 4)"),
               ("Convention FAL de l'OMI, formulaires 3 et 4", "IMO FAL Convention, forms 3 and 4"),
               frozenset({"AGE", "NAV"}), [("NAV", ("Capitaine", "Master")), ("ADM", ("Douanes — visa", "Customs — endorsement"))],
               build_stores, family="AGE", answers=("M0:13", "M8:8.05"),
               purpose=("Les déclarations des provisions de bord et des effets de l'équipage (FAL 3 et 4) remises aux douanes.", "The ship's stores and crew's effects declarations (FAL 3 and 4) handed to customs.")))


# ------------------------------------------------------------------------------------------------ crew change list
def build_crew_change(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Date de relève prévue", "Planned crew change date"), F("Effectif minimal de sécurité (document n°)", "Minimum safe manning (document no.)")),
        table(("Embarquants", "Joiners"),
              [("Nom et prénoms", "Full name"), ("Fonction", "Rank"), ("Nationalité", "Nationality"), ("Passeport n° / validité", "Passport no. / validity"), ("Visa / lettre de garantie", "Visa / guarantee letter"),
               ("Brevet (STCW) n°", "Certificate (STCW) no."), ("Certificat médical valide ☐", "Valid medical certificate ☐"), ("Vol / arrivée", "Flight / arrival")], [], blank_rows=6),
        table(("Débarquants", "Leavers"),
              [("Nom et prénoms", "Full name"), ("Fonction", "Rank"), ("Nationalité", "Nationality"), ("Passeport n° / validité", "Passport no. / validity"), ("Visa / transit", "Visa / transit"),
               ("Vol / départ", "Flight / departure"), ("Rapatriement organisé par", "Repatriation arranged by")], [], blank_rows=6),
        fields(("Accompagnement", "Arrangements"), [
            F("Hébergement et transport", "Accommodation and transport"), F("Laissez-passer demandés (nombre)", "Passes requested (number)"),
            F("Agence de manning / armateur", "Manning agency / owner", _parties(call, "COM"), source="CallParty COM actives"), F("Observations", "Remarks", wide=True),
        ], note=("Documents contrôlés par l'immigration (passeports, visas), l'autorité maritime (brevets STCW, effectif minimal) et la santé (certificats médicaux) ; Convention FAL, section 3 (relèves d'équipage).",
                 "Documents checked by immigration (passports, visas), the maritime authority (STCW certificates, safe manning) and health (medical certificates); FAL Convention, section 3 (crew changes).")),
    ]


_register(Form("CREW_CHANGE_LIST", "CREW_DOC", ("Liste de relève d'équipage", "Crew change list"),
               ("Convention FAL de l'OMI (relèves d'équipage) ; Convention STCW ; pratique de l'immigration", "IMO FAL Convention (crew changes); STCW Convention; immigration practice"),
               frozenset({"AGE"}), [("AGE", ("Agence", "Agency")), ("NAV", ("Capitaine", "Master")), ("ADM", ("Immigration — visa", "Immigration — endorsement"))],
               build_crew_change, family="AGE", templates=frozenset({"M8"}), answers=("M8:8.01",),
               purpose=("La liste des embarquants et débarquants avec leurs documents, déposée pour la relève d'équipage.", "The list of joiners and leavers with their documents, filed for the crew change.")))


# ------------------------------------------------------------------------------------------------ bill of lading
def build_bill_of_lading(call: PortCall) -> list[dict]:
    bl = call.measurements.filter(kind="BL").order_by("-created_at").first()
    figure = None
    if bl is not None:
        values = bl.current_values()
        figure = ", ".join(f"{p}: {values[p].value} {bl.unit}" for p in ("SHORE", "SHIP", "SURVEYOR") if p in values) or None
    return [
        fields(("Parties", "Parties"), [
            F("Expéditeur (shipper)", "Shipper", wide=True), F("Destinataire (consignee) — à l'ordre de", "Consignee — to the order of", wide=True),
            F("Notifier (notify party)", "Notify party", wide=True), F("Armateur / transporteur", "Carrier", _parties(call, "COM"), source="CallParty COM actives"),
        ]),
        fields(("Navire et voyage", "Vessel and voyage"), [
            F("Navire", "Vessel", _vessel(call), source="Vessel.name, imo"), F("Pavillon", "Flag", call.vessel.flag or None, source="Vessel.flag"),
            F("Port de chargement", "Port of loading", call.port.name if "M2" in call.template_codes else (call.last_port or None), source="Port.name ou PortCall.last_port"),
            F("Port de déchargement", "Port of discharge", call.next_port if "M2" in call.template_codes else call.port.name, source="PortCall.next_port ou Port.name"),
            F("Date d'embarquement (shipped on board)", "Shipped on board date", dt(call.t1) or None, source="PortCall.t1 (fin de transfert)"), F("Voyage", "Voyage", call.voyage_number or None, source="PortCall.voyage_number"),
        ]),
        table(("Marchandises", "Goods"),
              [("Description (produit, grade, spécification)", "Description (product, grade, specification)"), ("Quantité (masse)", "Quantity (mass)"), ("Volume à 15 °C / 60 °F", "Volume at 15 °C / 60 °F"),
               ("Densité à 15 °C / API", "Density at 15 °C / API"), ("Température", "Temperature"), ("Base du chiffre (bord / terre / inspecteur)", "Basis of figure (ship / shore / surveyor)")],
              [[call.product or None, _quantity(call), None, None, None, figure]], blank_rows=1,
              source="PortCall.product, quantity ; Measurement BL (valeurs bord, terre, inspecteur)"),
        fields(("Conditions", "Terms"), [
            F("Fret (payé d'avance / à destination)", "Freight (prepaid / collect)"), F("Nombre d'originaux", "Number of originals"),
            F("Charte-partie de référence (date)", "Charter-party referred to (date)"), F("Clauses (poids inconnu, said to contain…)", "Clauses (weight unknown, said to contain…)", wide=True),
            F("Lieu et date d'émission", "Place and date of issue", call.port.name, source="Port.name"), F("Signé par (capitaine / agent pour le capitaine)", "Signed by (master / agent for the master)"),
        ], note=("Le connaissement est émis sur l'instruction documentaire écrite du mandant (tâche M2:2.16) et après accord sur la quantité : la plateforme refuse l'émission tant que le point d'arrêt BL_ISSUE n'est pas levé ; aucun rôle ne lève ce verrou.",
                 "The bill of lading is issued on the principal's written documentary instructions (task M2:2.16) and after agreement on the quantity: the platform refuses the issue until the BL_ISSUE hold point is cleared; no role lifts this lock.")),
    ]


_register(Form("BILL_OF_LADING", "BILL_OF_LADING", ("Connaissement — données d'émission", "Bill of lading — issuing data"),
               ("Pratique du commerce des hydrocarbures (connaissement de charte-partie, type CONGENBILL / BIMCO) ; Règles de La Haye-Visby", "Oil trade practice (charter-party bill of lading, CONGENBILL / BIMCO type); Hague-Visby Rules"),
               frozenset({"AGE"}), [("AGE", ("Agent, pour le capitaine", "Agent, for the master")), ("NAV", ("Capitaine", "Master"))],
               build_bill_of_lading, family="AGE", templates=frozenset({"M2"}), answers=("M2:2.17",),
               purpose=("Les données d'émission du connaissement, pré-remplies de la quantité convenue ; l'émission reste verrouillée par le point d'arrêt BL_ISSUE.",
                        "The issuing data of the bill of lading, pre-filled with the agreed quantity; the issue stays locked by the BL_ISSUE hold point.")))


# ------------------------------------------------------------------------------------------------ port account
def build_port_account(call: PortCall) -> list[dict]:
    items = ["Droits de port et redevances / Port dues and charges", "Pilotage / Pilotage", "Remorquage / Towage", "Lamanage / Mooring", "Redevance de poste / terminal / Berth and terminal charges",
             "Inspection et laboratoire / Survey and laboratory", "Déchets (réception) / Waste reception", "Eau douce, provisions / Fresh water, provisions",
             "Relève d'équipage, transports / Crew change, transport", "Soutes / Bunkers", "Formalités, douanes, immigration, santé / Formalities, customs, immigration, health",
             "Sûreté / Security", "Communications, divers / Communications, sundries", "Honoraires d'agence / Agency fee"]
    return [
        identification(call, F("Mandant (armateur / affréteur)", "Principal (owner / charterer)", _parties(call, "COM"), source="CallParty COM actives"),
                       F("Arrivée / départ", "Arrival / departure", f"{dt(call.ata) or '—'} → {dt(call.atd) or '—'}", source="PortCall.ata, atd")),
        table(("Relevé des prestations", "Statement of services"),
              [("Poste", "Item"), ("Prestataire / référence", "Provider / reference"), ("Base (durée, quantité)", "Basis (duration, quantity)"), ("Montant", "Amount"), ("Devise", "Currency"), ("Justificatif joint n°", "Supporting document no.")],
              [[item, None, None, None, None, None] for item in items], blank_rows=2),
        fields(("Totaux", "Totals"), [
            F("Total des débours", "Total disbursements"), F("Avance de fonds reçue", "Advance received"), F("Solde dû / à rembourser", "Balance due / refundable"),
            F("Coordonnées bancaires de l'agence", "Agency bank details", wide=True),
        ], note=("Compte d'escale final (FDA) établi sur les justificatifs des prestataires et les durées du registre ; chaque justificatif est déposé comme document de l'escale (confidentialité N3 : mandant, agence).",
                 "Final disbursement account (FDA) built on the providers' supporting documents and the registry's durations; each supporting document is filed as a document of the call (N3: principal, agency).")),
    ]


_register(Form("PORT_ACCOUNT", "PORT_ACCOUNT", ("Compte d'escale final (FDA)", "Final disbursement account (FDA)"),
               ("Pratique de l'agence maritime (FONASBA — Standard Disbursement Account)", "Shipping agency practice (FONASBA — Standard Disbursement Account)"),
               frozenset({"AGE"}), [("AGE", ("Agence", "Agency")), ("COM", ("Mandant — reçu", "Principal — received"))],
               build_port_account, family="AGE", answers=("M0:38",),
               purpose=("Le compte d'escale final transmis au mandant avec ses justificatifs.", "The final disbursement account sent to the principal with its supporting documents.")))
