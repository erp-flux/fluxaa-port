"""Forms issued by the authorities of the port — harbour master, port authority, customs / immigration / health,
security: the written act of every decision taken on a request (one "authorization" form per decided request
type, with the request as filed, the decision, its validity, conditions and public verification code), the
operating limits of a berth, the shore access list and the pre-arrival security information.

An authorization form prints the authorization object the registry produced when the request was approved
(EF-2.5): the paper and the registry carry the same number, validity and verification code, and anyone may check
the code at the public address printed on the form, without access to the call file. When no authorization of the
type exists yet, the form is issued blank, to be completed by hand — the registry entry remains the reference."""
from __future__ import annotations

from functools import partial

from django.conf import settings
from django.urls import reverse

from ...catalog import REQUEST_TYPES
from ...models import PortCall
from .core import (
    F,
    Form,
    _authorization,
    _party,
    _register,
    _request,
    _request_rows,
    _vessel,
    _where,
    dt,
    fields,
    identification,
    qr,
    table,
    text,
)

# ------------------------------------------------------------------------------------------------ decisions (acts)
# What each kind of authorization adds to the common structure: specific fields and the records kept on paper.
SPECIFICS: dict[str, dict] = {
    "VESSEL_ACCEPTANCE": {
        "title": ("Acceptation du navire", "Vessel acceptance"),
        "fields": [F("Rapport SIRE / CDI pris en compte (date)", "SIRE / CDI report considered (date)"),
                   F("Validité de l'acceptation", "Validity of the acceptance"),
                   F("Conditions d'exploitation imposées", "Operating conditions imposed", wide=True)],
    },
    "GREEN_LIGHT": {
        "title": ("Feu vert", "Green light"),
        "fields": [F("Données navire et certificats vérifiés par", "Vessel data and certificates checked by"),
                   F("Contrôle des listes de sanctions confirmé le", "Sanctions screening confirmed on")],
    },
    "BERTH": {
        "title": ("Attribution de poste et de créneau", "Berth and slot assignment"),
        "fields": [F("Poste ou zone attribué", "Berth or area assigned", source="Authorization.berth"),
                   F("Créneau attribué (de / à)", "Slot assigned (from / to)"),
                   F("Tirant d'eau maximal admis (m)", "Maximum draft admitted (m)"),
                   F("Conditions d'accostage", "Berthing conditions", wide=True)],
    },
    "MOVEMENT": {
        "title": ("Autorisation de mouvement", "Movement authorization"),
        "fields": [F("Mouvement (de / à)", "Movement (from / to)"), F("Heure autorisée", "Authorized time"),
                   F("Pilote", "Pilot"), F("Remorqueurs", "Tugs"), F("Lamaneurs", "Mooring gang"),
                   F("Conditions (visibilité, vent, marée)", "Conditions (visibility, wind, tide)", wide=True)],
    },
    "FREE_PRATIQUE": {
        "title": ("Libre pratique", "Free pratique"),
        "fields": [F("Déclaration maritime de santé reçue le", "Maritime declaration of health received on"),
                   F("Inspection sanitaire : non requise ☐ réalisée ☐", "Health inspection: not required ☐ carried out ☐"),
                   F("Certificat de contrôle sanitaire du navire (validité)", "Ship sanitation certificate (validity)"),
                   F("Mesures sanitaires prescrites", "Health measures prescribed", wide=True)],
        "note": ("Règlement sanitaire international (2005), articles 27 et 28 : la libre pratique est accordée sur la base de la déclaration maritime de santé, sauf inspection.",
                 "International Health Regulations (2005), articles 27 and 28: free pratique is granted on the maritime declaration of health unless an inspection is required."),
    },
    "CUSTOMS_IMMIGRATION": {
        "title": ("Formalités douanières et d'immigration — arrivée", "Customs and immigration formalities — arrival"),
        "fields": [F("Déclaration générale (FAL 1) reçue le", "General declaration (FAL 1) received on"),
                   F("Liste d'équipage (FAL 5) visée", "Crew list (FAL 5) endorsed"),
                   F("Provisions de bord (FAL 3) et effets (FAL 4) contrôlés", "Ship's stores (FAL 3) and crew's effects (FAL 4) checked"),
                   F("Laissez-passer à terre délivrés (nombre)", "Shore passes issued (number)")],
        "tables": [table(("Scellés relevés et apposés", "Seals removed and applied"),
                         [("Local / magasin", "Store / compartment"), ("N° de scellé", "Seal number"), ("Apposé ☐ / relevé ☐", "Applied ☐ / removed ☐"),
                          ("Heure", "Time"), ("Agent", "Officer")], [], blank_rows=5)],
    },
    "OUTWARD_FORMALITIES": {
        "title": ("Formalités de sortie", "Outward formalities"),
        "fields": [F("Prochain port", "Next port"), F("Déclaration de sortie n°", "Outward declaration no."),
                   F("Manifeste de sortie / cargaison déclarée", "Outward manifest / cargo declared"),
                   F("Scellés contrôlés à la sortie", "Seals checked on departure"),
                   F("Observations", "Remarks", wide=True)],
    },
    "DEPARTURE_CLEARANCE": {
        "title": ("Congé de départ", "Departure clearance"),
        "fields": [F("Formalités de sortie accomplies le", "Outward formalities completed on"),
                   F("Déchets remis — bordereau n°", "Waste delivered — receipt no."),
                   F("Redevances et frais portuaires", "Port dues and charges"),
                   F("Heure d'appareillage autorisée", "Authorized time of departure"),
                   F("Prochain port", "Next port"), F("Conditions", "Conditions", wide=True)],
    },
    "ANCHORAGE_POSITION": {
        "title": ("Position de mouillage", "Anchorage position"),
        "fields": [F("Zone de mouillage", "Anchorage area"), F("Position (latitude, longitude)", "Position (latitude, longitude)"),
                   F("Rayon d'évitage (m)", "Swinging radius (m)"), F("Veille VHF (canal)", "VHF watch (channel)"),
                   F("Durée autorisée", "Authorized duration"), F("Consignes", "Instructions", wide=True)],
    },
    "STS_ZONE": {
        "title": ("Autorisation de zone et de fenêtre STS", "STS area and window authorization"),
        "fields": [F("Zone STS", "STS area"), F("Fenêtre autorisée (de / à)", "Authorized window (from / to)"),
                   F("Navire partenaire", "Partner vessel"), F("Prestataire STS / POAC", "STS provider / POAC"),
                   F("Limites météo (vent, houle)", "Weather limits (wind, swell)"), F("Conditions", "Conditions", wide=True)],
    },
    "BUNKERING": {
        "title": ("Autorisation de soutage", "Bunkering authorization"),
        "fields": [F("Avitailleur", "Bunker supplier"), F("Moyen (barge, camion, pipeline)", "Means (barge, truck, pipeline)"),
                   F("Produit et quantité", "Product and quantity"),
                   F("Compatibilité avec l'opération cargaison en cours", "Compatibility with the cargo operation under way", wide=True),
                   F("Conditions", "Conditions", wide=True)],
    },
    "BALLAST_DISCHARGE": {
        "title": ("Rejet d'eaux de ballast", "Ballast water discharge"),
        "fields": [F("Volume autorisé (m³)", "Authorized volume (m³)"), F("Méthode de conformité (D-1 / D-2)", "Compliance method (D-1 / D-2)"),
                   F("Lieu de rejet", "Place of discharge"), F("Réception à terre imposée ☐", "Reception ashore required ☐"),
                   F("Conditions", "Conditions", wide=True)],
    },
    "GAS_FREEING": {
        "title": ("Nettoyage / dégazage à quai", "Tank cleaning / gas-freeing alongside"),
        "fields": [F("Citernes concernées", "Tanks concerned"), F("Méthode", "Method"), F("Période autorisée", "Authorized period"),
                   F("Effluents et vapeurs : destination", "Effluents and vapours: destination"),
                   F("Mesures imposées", "Measures imposed", wide=True)],
    },
    "HOT_WORK": {
        "title": ("Autorisation de travaux (point chaud)", "Hot work authorization"),
        "fields": [F("Lieu et nature des travaux", "Place and nature of the works"), F("Période autorisée", "Authorized period"),
                   F("Certificat de dégazage n° / validité", "Gas-free certificate no. / validity"),
                   F("Veille incendie et moyens imposés", "Fire watch and means imposed", wide=True),
                   F("Conditions", "Conditions", wide=True)],
    },
    "IMMOBILIZATION": {
        "title": ("Immobilisation des machines", "Immobilization of the machinery"),
        "fields": [F("Période d'immobilisation (de / à)", "Immobilization period (from / to)"),
                   F("Moyens compensatoires (remorqueur en attente, veille renforcée)", "Compensating means (tug on standby, reinforced watch)", wide=True),
                   F("Remise en service garantie le", "Guaranteed return to service on"), F("Conditions", "Conditions", wide=True)],
    },
    "CREW_CHANGE": {
        "title": ("Relève d'équipage et laissez-passer", "Crew change and shore passes"),
        "fields": [F("Documents contrôlés (passeports, visas, brevets, certificats médicaux)", "Documents checked (passports, visas, certificates, medical)", wide=True),
                   F("Effectif minimal de sécurité maintenu ☐", "Minimum safe manning maintained ☐")],
        "tables": [table(("Laissez-passer délivrés", "Passes issued"),
                         [("Nom", "Name"), ("Fonction", "Rank"), ("Passeport", "Passport"), ("Embarque ☐ / débarque ☐", "Joining ☐ / leaving ☐"),
                          ("N° de laissez-passer", "Pass number"), ("Validité", "Validity")], [], blank_rows=6)],
    },
    "DOUBLE_BANKING": {
        "title": ("Accostage à couple", "Double banking"),
        "fields": [F("Navire intérieur / navire extérieur", "Inner vessel / outer vessel"), F("Durée autorisée", "Authorized duration"),
                   F("États de chargement admis", "Loading conditions admitted"), F("Seuils météo", "Weather thresholds"),
                   F("Conditions", "Conditions", wide=True)],
    },
}


def build_authorization(call: PortCall, type_code: str, rtype: dict, about=None) -> list[dict]:
    """*about*: the request the act is issued for (the one just decided); otherwise the latest of its type."""
    if about is not None:
        req = about
        auth = getattr(req, "authorization", None) if req.decision in ("APPROVED", "APPROVED_COND") else None
        if auth is not None and auth.is_cancelled:
            auth = None
    else:
        auth = _authorization(call, type_code)
        req = auth.request if auth is not None else _request(call, type_code)
    spec = SPECIFICS.get(type_code, {})
    sections = [identification(call,
                               F("Navire partenaire", "Partner vessel", call.linked_call.vessel.name if call.linked_call_id else None, source="PortCall.linked_call") if type_code in ("STS_ZONE", "DOUBLE_BANKING") else F("Produit / quantité", "Product / quantity", f"{call.product or '—'} — {call.quantity or '—'} {call.quantity_unit}", source="PortCall.product, quantity, quantity_unit"))]
    request_fields = [
        F("Demande", "Request", req.reference if req else None, source="ServiceRequest.reference"),
        F("Demandeur", "Requester", f"{req.requester_org.name} ({req.requester_role})" if req else None, source="ServiceRequest.requester_org, requester_role"),
        F("Déposée le", "Submitted on", dt(req.submitted_at) if req else None, source="ServiceRequest.submitted_at"),
        F("Prestataire désigné", "Provider named", req.provider_org.name if req and req.provider_org_id else None, source="ServiceRequest.provider_org"),
        *_request_rows(req),
    ]
    sections.append(fields(("Demande telle que déposée", "Request as filed"), request_fields,
                           note=("Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision.",
                                 "The values above are those entered by the requester in the registry; the decision does not alter them.")))
    decision_fields = [
        F("Décision", "Decision", req.get_decision_display() if req and req.decision else None, source="ServiceRequest.decision"),
        F("Prise par", "Taken by", f"{req.decision_org.name} ({req.decision_role})" if req and req.decision_org_id else None, source="ServiceRequest.decision_org, decision_role"),
        F("Le", "On", dt(req.decided_at) if req else None, source="ServiceRequest.decided_at"),
        F("Numéro de l'autorisation", "Authorization number", auth.number if auth else None, source="Authorization.number"),
        F("Effective du", "Effective from", dt(auth.valid_from) if auth else None, source="Authorization.valid_from"),
        F("Expire le", "Expires on", dt(auth.valid_until) if auth else None, source="Authorization.valid_until"),
        F("Portée", "Scope", auth.scope if auth else None, wide=True, source="Authorization.scope"),
        F("Conditions", "Conditions", (auth.conditions if auth else (req.decision_conditions if req else None)) or None, wide=True, source="Authorization.conditions"),
    ]
    if rtype.get("assigns_berth"):
        decision_fields.insert(4, F("Poste attribué", "Berth assigned", f"{auth.berth.code} — {auth.berth.name_fr}" if auth and auth.berth_id else None, source="Authorization.berth"))
    sections.append(fields(("Décision", "Decision"), decision_fields))
    sections.append(fields(spec.get("title", ("Objet", "Subject")), spec.get("fields", []), note=spec.get("note")))
    sections.extend(spec.get("tables", []))
    if auth is not None:
        url = f"{settings.SITE_URL}{reverse('registry:verify_code', args=[auth.verification_code])}"
        sections.append(qr(("Vérification publique", "Public verification"), url,
                           (f"Code {auth.verification_code} — existence et validité vérifiables sans accès au dossier de l'escale.",
                            f"Code {auth.verification_code} — existence and validity verifiable without access to the call file.")))
    sections.append(text(("Mentions", "Notes"), [
        ("La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.",
         "This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester."),
        ("Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.",
         "A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides."),
    ]))
    return sections


def _signers(rtype: dict) -> list[tuple[str, tuple[str, str]]]:
    signers = [(role, ("Autorité — décision", "Authority — decision")) for role in rtype["decision_roles"]]
    signers.append(("AGE", ("Agence — réception", "Agency — receipt")))
    if rtype["code"] in ("MOVEMENT", "DEPARTURE_CLEARANCE", "ANCHORAGE_POSITION", "HOT_WORK", "IMMOBILIZATION", "GAS_FREEING", "BUNKERING", "BALLAST_DISCHARGE", "STS_ZONE", "DOUBLE_BANKING"):
        signers.append(("NAV", ("Capitaine — pris connaissance", "Master — acknowledged")))
    return signers


_MODULES = {"STS_ZONE": frozenset({"M3"}), "BUNKERING": frozenset({"M4"}), "BALLAST_DISCHARGE": frozenset({"M5"}),
            "GAS_FREEING": frozenset({"M6"}), "HOT_WORK": frozenset({"M7"}), "IMMOBILIZATION": frozenset({"M7"}),
            "CREW_CHANGE": frozenset({"M8"}), "DOUBLE_BANKING": frozenset({"M9"}), "ANCHORAGE_POSITION": frozenset({"MA3"})}
_ANSWERS = {"VESSEL_ACCEPTANCE": ("M0:07",), "GREEN_LIGHT": ("M0:09",), "BERTH": ("M0:10", "M0:11"), "MOVEMENT": ("M0:25",),
            "FREE_PRATIQUE": ("M0:21",), "CUSTOMS_IMMIGRATION": ("M0:22",), "OUTWARD_FORMALITIES": ("M0:33",),
            "DEPARTURE_CLEARANCE": ("M0:34",), "ANCHORAGE_POSITION": ("MA3:A3.01",), "STS_ZONE": ("M3:3.03",),
            "BUNKERING": ("M4:4.01",), "BALLAST_DISCHARGE": ("M5:5.04",), "GAS_FREEING": ("M6:6.04",), "HOT_WORK": ("M7:7.04",),
            "IMMOBILIZATION": ("M7:7.08",), "CREW_CHANGE": ("M8:8.02",), "DOUBLE_BANKING": ("M9:9.01",)}

for _rtype in REQUEST_TYPES:
    if not _rtype.get("decision_roles"):
        continue  # a service order (pilots, waste collection) is confirmed by its provider: see the service note
    _code = _rtype["code"]
    _family = "ADM" if "ADM" in _rtype["decision_roles"] else ("APO" if _rtype["decision_roles"] == ["APO"] else "CAP")
    _register(Form(
        f"AUTH_{_code}", "AUTHORIZATION",
        (f"Autorisation — {_rtype['label_fr']}", f"Authorization — {_rtype['label_en']}"),
        ("Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique",
         "Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code"),
        frozenset(_rtype["decision_roles"]), _signers(_rtype), partial(build_authorization, type_code=_code, rtype=_rtype),
        family=_family, templates=_MODULES.get(_code, frozenset()), needs_link=_code in ("STS_ZONE", "DOUBLE_BANKING"),
        answers=(f"REQ:{_code}", *_ANSWERS.get(_code, ())),
        purpose=(f"L'acte écrit de la décision « {_rtype['label_fr']} » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.",
                 f"The written act of the decision “{_rtype['label_en']}”: the request as filed, the decision, its validity, conditions and verification code."),
    ))


# ------------------------------------------------------------------------------------------------ berth limits
def build_berth_limits(call: PortCall) -> list[dict]:
    berth = call.berth
    return [
        identification(call, F("Terminal", "Terminal", _party(call, "TER"), source="CallParty TER active"),
                       F("Type de poste", "Kind of berth", berth.get_kind_display() if berth else call.get_requested_berth_kind_display(), source="Berth.kind")),
        fields(("Caractéristiques du poste", "Berth particulars"), [
            F("Longueur utile / tirant d'eau maximal (m)", "Usable length / maximum draft (m)"), F("Déplacement / DWT maximal (t)", "Maximum displacement / DWT (t)"),
            F("Longueur hors tout maximale / minimale (m)", "Maximum / minimum length overall (m)"), F("Hauteur du collecteur admise (m)", "Manifold height admitted (m)"),
            F("Défenses (type, énergie)", "Fenders (type, energy)"), F("Bras / flexibles (nombre, diamètre, enveloppe)", "Arms / hoses (number, diameter, envelope)"),
        ]),
        table(("Limites d'exploitation", "Operating limits"),
              [("Paramètre", "Parameter"), ("Accostage", "Berthing"), ("Séjour à quai", "Stay alongside"), ("Transfert", "Transfer"), ("Déhalage / appareillage", "Unberthing")],
              [["Vent (nd, direction)", None, None, None, None], ["Houle (m, période)", None, None, None, None], ["Courant (nd)", None, None, None, None],
               ["Visibilité (m)", None, None, None, None], ["Marée / hauteur d'eau (m)", None, None, None, None], ["Nuit ☐ autorisé ☐ interdit", None, None, None, None]],
              blank_rows=2,
              note=("Au-delà d'une limite, l'opération concernée est suspendue et la capitainerie en est informée ; les limites sont rappelées au navire avant l'accostage (liste de contrôle, partie 1).",
                    "Beyond a limit the operation concerned is suspended and the harbour master informed; the limits are recalled to the ship before berthing (checklist, part 1).")),
        fields(("Mesures et veille", "Measures and watch"), [
            F("Station météo de référence", "Reference weather station"), F("Fréquence de relevé pendant le séjour", "Reading interval during the stay"),
            F("Remorqueur en attente requis à partir de", "Tug on standby required from"), F("Moyens de largage d'urgence", "Emergency release means"),
            F("Publié le / valable jusqu'au", "Published on / valid until"),
        ]),
    ]


_register(Form("BERTH_LIMITS", "BERTH_LIMITS", ("Conditions limites d'exploitation du poste", "Berth operating limits"),
               ("Pratique portuaire — ISGOTT 6e édition (limites du poste), PIANC (critères d'accostage), règlement d'exploitation du port",
                "Port practice — ISGOTT 6th edition (berth limits), PIANC (berthing criteria), port operating regulations"),
               frozenset({"CAP", "TER"}), [("CAP", ("Capitainerie", "Harbour master")), ("TER", ("Terminal", "Terminal")), ("NAV", ("Capitaine — pris connaissance", "Master — acknowledged"))],
               build_berth_limits, family="CAP", answers=("M0:12", "M9:9.11"),
               purpose=("Les conditions limites (vent, houle, courant, visibilité, marée) publiées par la capitainerie pour le poste de l'escale.",
                        "The operating limits (wind, swell, current, visibility, tide) published by the harbour master for the berth of the call.")))


# ------------------------------------------------------------------------------------------------ security (SUR)
def build_access_list(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Terminal / installation portuaire", "Terminal / port facility", _party(call, "TER"), source="CallParty TER active"),
                       F("Période d'accès demandée (de / à)", "Access period requested (from / to)")),
        table(("Personnes", "Persons"),
              [("Nom et prénom", "Full name"), ("Organisation / fonction", "Organisation / capacity"), ("Pièce d'identité n°", "Identity document no."),
               ("Motif", "Purpose"), ("Date et heures", "Date and hours"), ("Autorisé ☐ / refusé ☐", "Granted ☐ / refused ☐")], [], blank_rows=8),
        table(("Véhicules et matériel", "Vehicles and equipment"),
              [("Immatriculation / type", "Registration / type"), ("Conducteur", "Driver"), ("Chargement", "Load"), ("Date et heures", "Date and hours"), ("Autorisé ☐ / refusé ☐", "Granted ☐ / refused ☐")],
              [], blank_rows=4),
        fields(("Décision de l'autorité de sûreté", "Security authority's decision"), [
            F("Niveau de sûreté en vigueur", "Security level in force"), F("Badges délivrés (numéros)", "Badges issued (numbers)"),
            F("Conditions (escorte, zones, horaires)", "Conditions (escort, areas, hours)", wide=True), F("Décision prise le / par", "Decision taken on / by"),
        ], note=("Code ISPS, partie A §16 et partie B §16.10–16.17 : contrôle de l'accès à l'installation portuaire ; la liste est conservée avec le dossier de l'escale et n'y figure aucune donnée du domaine sûreté N4.",
                 "ISPS Code, part A §16 and part B §16.10–16.17: access control to the port facility; the list is kept with the call file and holds no N4 security data.")),
    ]


_register(Form("ACCESS_LIST", "ACCESS_LIST", ("Demande et autorisation d'accès en zone portuaire", "Port area access request and authorization"),
               ("Code ISPS (contrôle d'accès à l'installation portuaire) ; règlement de sûreté du port", "ISPS Code (port facility access control); port security regulations"),
               frozenset({"AGE", "SUR"}), [("AGE", ("Agence — demande", "Agency — request")), ("SUR", ("Autorité de sûreté — décision", "Security authority — decision"))],
               build_access_list, family="SUR", templates=frozenset({"M8", "M7"}), answers=("M8:8.04",),
               purpose=("La liste nominative des personnes et véhicules dont l'accès à la zone portuaire est demandé par l'agence et accordé par la sûreté.",
                        "The nominative list of persons and vehicles whose access to the port area is requested by the agency and granted by security.")))


def build_pre_arrival_security(call: PortCall) -> list[dict]:
    v = call.vessel
    return [
        fields(("Navire", "Ship"), [
            F("Nom / numéro OMI", "Name / IMO number", _vessel(call), source="Vessel.name, Vessel.imo"), F("Pavillon / port d'immatriculation", "Flag / port of registry", v.flag or None, source="Vessel.flag"),
            F("Indicatif / MMSI", "Call sign / MMSI", v.call_sign or None, source="Vessel.call_sign"), F("Jauge brute", "Gross tonnage"),
            F("Compagnie (exploitant) et n° OMI de compagnie", "Company (operator) and company IMO number"), F("Agent de sûreté de la compagnie (CSO) — contact", "Company security officer (CSO) — contact"),
            F("Certificat international de sûreté (ISSC) : délivré par, validité", "International ship security certificate (ISSC): issued by, validity", wide=True),
            F("Port d'arrivée / poste", "Port of arrival / berth", f"{call.port.name} — {_where(call)}", source="Port.name, poste"), F("ETA", "ETA", dt(call.eta), source="PortCall.eta"),
            F("Niveau de sûreté actuel du navire", "Current security level of the ship"), F("Nombre de personnes à bord", "Number of persons on board"),
        ]),
        table(("Dix dernières escales (ordre chronologique)", "Last ten ports of call (chronological order)"),
              [("Port, pays", "Port, country"), ("Installation portuaire", "Port facility"), ("Arrivée", "Arrival"), ("Départ", "Departure"), ("Niveau de sûreté", "Security level"), ("Mesures spéciales ou additionnelles", "Special or additional measures")],
              [], blank_rows=10),
        table(("Opérations navire-navire pendant la période", "Ship-to-ship activities during the period"),
              [("Lieu", "Location"), ("Date", "Date"), ("Navire / unité", "Ship / unit"), ("Nature de l'opération", "Nature of activity"), ("Mesures de sûreté appliquées", "Security measures applied")],
              [], blank_rows=3),
        text(("Déclaration", "Declaration"), [
            ("Je certifie que les renseignements ci-dessus sont exacts et complets ; un plan de sûreté approuvé est en vigueur à bord et les procédures de sûreté ont été maintenues pendant la période indiquée.",
             "I certify that the above information is true and complete; an approved ship security plan is in force on board and security procedures were maintained throughout the stated period."),
        ], note=("Jeu de données normalisé de l'information de sûreté avant l'arrivée — SOLAS XI-2 règle 9.2.1 et circulaire OMI MSC.1/Circ.1305 ; formulaire FAL « pre-arrival security information ».",
                 "Standard data set of the pre-arrival security information — SOLAS XI-2 regulation 9.2.1 and IMO circular MSC.1/Circ.1305; FAL pre-arrival security information form.")),
    ]


_register(Form("PRE_ARRIVAL_SECURITY", "PRE_ARRIVAL_SECURITY", ("Information de sûreté avant l'arrivée", "Pre-arrival security information"),
               ("SOLAS XI-2 règle 9.2.1 ; circulaire OMI MSC.1/Circ.1305 ; Convention FAL (formulaire d'information de sûreté)",
                "SOLAS XI-2 regulation 9.2.1; IMO circular MSC.1/Circ.1305; FAL Convention (security information form)"),
               frozenset({"NAV", "AGE"}), [("NAV", ("Capitaine ou agent de sûreté du navire (SSO)", "Master or ship security officer (SSO)")), ("SUR", ("Autorité de sûreté — reçu", "Security authority — received"))],
               build_pre_arrival_security, family="SUR", answers=("M0:17",),
               purpose=("Les renseignements de sûreté que le navire communique avant l'arrivée : certificat ISSC, niveau de sûreté, dix dernières escales, opérations navire-navire.",
                        "The security information the ship provides before arrival: ISSC, security level, last ten ports of call, ship-to-ship activities.")))
