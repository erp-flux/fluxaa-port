"""Forms issued by the service providers: waste delivery receipt (MARPOL), bunkering safety checklist, STS
compatibility study, STS equipment (fenders and hoses) attestation, reception facility attestation, outside
contractors' file."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _partner,
    _party,
    _register,
    _vessel,
    checklist,
    fields,
    identification,
    table,
    text,
)


# ------------------------------------------------------------------------------------------------ waste receipt
def build_waste_receipt(call: PortCall) -> list[dict]:
    categories = [("Annexe I — eaux de cale huileuses", "Annex I — oily bilge water"), ("Annexe I — résidus d'hydrocarbures (boues)", "Annex I — oily residues (sludge)"),
                  ("Annexe I — eaux de lavage de citernes", "Annex I — tank washings"), ("Annexe I — eau de ballast sale", "Annex I — dirty ballast water"),
                  ("Annexe II — résidus de substances liquides nocives", "Annex II — NLS residues"), ("Annexe IV — eaux usées", "Annex IV — sewage"),
                  ("Annexe V — plastiques", "Annex V — plastics"), ("Annexe V — déchets alimentaires", "Annex V — food wastes"), ("Annexe V — déchets domestiques", "Annex V — domestic wastes"),
                  ("Annexe V — huile de cuisson", "Annex V — cooking oil"), ("Annexe V — cendres d'incinérateur", "Annex V — incinerator ashes"), ("Annexe V — déchets d'exploitation", "Annex V — operational wastes"),
                  ("Annexe V — résidus de cargaison", "Annex V — cargo residues"), ("Annexe V — déchets électroniques", "Annex V — e-waste"), ("Annexe VI — résidus d'épuration des gaz", "Annex VI — exhaust gas cleaning residues")]
    return [
        fields(("Installation de réception", "Reception facility"), [
            F("Nom et adresse de l'installation / du prestataire", "Name and address of the facility / provider", _party(call, "PRE"), wide=True, source="CallParty PRE active"),
            F("Agrément (numéro, autorité, validité)", "Licence (number, authority, validity)"), F("Moyen de collecte (camion, barge, conteneur)", "Collection means (truck, barge, container)"),
            F("Port", "Port", call.port.name, source="Port.name"), F("Date et heure de la réception", "Date and time of delivery"),
        ]),
        fields(("Navire", "Ship"), [
            F("Nom / numéro OMI", "Name / IMO number", _vessel(call), source="Vessel.name, imo"), F("Pavillon", "Flag State", call.vessel.flag or None, source="Vessel.flag"),
            F("Jauge brute", "Gross tonnage"), F("Armateur / exploitant", "Owner / operator"), F("Agent", "Agent", str(call.agency), source="PortCall.agency"),
            F("Notification préalable n° / date", "Advance notification no. / date"),
        ]),
        table(("Déchets reçus", "Waste delivered"),
              [("Type", "Type"), ("Quantité reçue (m³)", "Amount delivered (m³)"), ("Observations (conteneurs, teneur en eau…)", "Remarks (containers, water content…)")],
              [[f"{fr} / {en}", None, None] for fr, en in categories], blank_rows=1),
        text(("Attestation", "Attestation"), [
            ("L'installation de réception atteste avoir reçu du navire ci-dessus les quantités indiquées, qui seront traitées conformément à la réglementation applicable ; le capitaine en reporte la remise aux registres MARPOL du bord.",
             "The reception facility attests that it received from the ship above the stated amounts, which will be handled in accordance with the applicable regulations; the master records the delivery in the ship's MARPOL record books."),
        ], note=("Modèle du bordereau de réception des déchets, appendice 3 de la circulaire OMI MEPC.1/Circ.834/Rev.1 (installations de réception portuaires).",
                 "Model of the waste delivery receipt, appendix 3 of IMO circular MEPC.1/Circ.834/Rev.1 (port reception facilities).")),
    ]


_register(Form("WASTE_RECEIPT", "WASTE_RECEIPT", ("Bordereau de réception des déchets", "Waste delivery receipt"),
               ("Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 3 (MARPOL)", "IMO circular MEPC.1/Circ.834/Rev.1, appendix 3 (MARPOL)"),
               frozenset({"PRE"}), [("PRE", ("Installation de réception", "Reception facility")), ("NAV", ("Capitaine", "Master"))],
               build_waste_receipt, family="PRE", answers=("REQ:WASTE_COLLECTION", "M0:32", "M5:5.07", "M6:6.07"),
               purpose=("Le bordereau par lequel l'installation de réception atteste les déchets reçus du navire.", "The receipt by which the reception facility attests the waste received from the ship.")))


# ------------------------------------------------------------------------------------------------ bunkering checklist
def build_bunker_checklist(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Avitailleur / moyen (barge, camion)", "Supplier / means (barge, truck)", _party(call, "PRE"), source="CallParty PRE active"),
                       F("Autorisation de soutage n°", "Bunkering authorization no.", source="Authorization BUNKERING")),
        fields(("Commande", "Order"), [
            F("Produit (grade) / quantité commandée (t)", "Product (grade) / quantity ordered (t)"), F("Teneur en soufre max. (% m/m) / viscosité / point d'éclair", "Max. sulphur (% m/m) / viscosity / flash point"),
            F("Débit maximal convenu (m³/h) / pression maximale (bar)", "Agreed maximum rate (m³/h) / maximum pressure (bar)"), F("Citernes receveuses et séquence", "Receiving tanks and sequence"),
            F("Agrément du soutier (n°, validité) / certification du moyen", "Bunker supplier licence (no., validity) / barge certification", wide=True), F("Système de comptage : scellés et vérification métrologique (date)", "Metering system: seals and metrological verification (date)", wide=True),
        ]),
        checklist(("Avant le soutage", "Before bunkering"), [
            ("Communication établie (VHF, signaux) ; procédure d'arrêt d'urgence convenue", "Communication established (VHF, signals); emergency stop procedure agreed"),
            ("Amarrage de la barge sûr ; défenses en place ; flexible supporté, certifié, à l'essai en date", "Barge safely moored; fenders in place; hose supported, certified, test in date"),
            ("Dalots obturés ; plateaux de rétention vides ; kit antipollution prêt des deux côtés", "Scuppers plugged; drip trays empty; spill kit ready on both sides"),
            ("Jaugeage initial contradictoire effectué ; compteurs relevés", "Joint initial gauging done; meters read"),
            ("Compatibilité avec l'opération cargaison en cours confirmée ; interdiction de fumer, sources d'ignition contrôlées", "Compatibility with the cargo operation under way confirmed; no smoking, ignition sources controlled"),
            ("Veille continue désignée (navire et avitailleur) ; manche incendie en pression", "Continuous watch designated (ship and supplier); fire hose charged"),
        ], columns=[("Navire", "Ship"), ("Avitailleur", "Supplier")]),
        checklist(("Pendant et après", "During and after"), [
            ("Débit et pression dans les limites ; niveaux des citernes surveillés ; topping-off annoncé", "Rate and pressure within limits; tank levels monitored; topping-off announced"),
            ("Échantillon MARPOL prélevé en continu au point de réception, scellé et signé", "MARPOL sample drawn continuously at the receiving point, sealed and signed"),
            ("Jaugeage final contradictoire ; flexible purgé et déconnecté ; note de livraison signée", "Joint final gauging; hose drained and disconnected; delivery note signed"),
        ], columns=[("Navire", "Ship"), ("Avitailleur", "Supplier")],
            note=("ISGOTT 6e édition, chapitre 25.5 (liste de contrôle soutage) ; IMO MEPC.1/Circ.875/Add.1 (bonnes pratiques d'achat et de livraison de fioul) ; ISO 13739.",
                  "ISGOTT 6th edition, chapter 25.5 (bunkering checklist); IMO MEPC.1/Circ.875/Add.1 (fuel oil purchase and delivery good practice); ISO 13739.")),
    ]


_register(Form("BUNKER_CHECKLIST", "BUNKER_CHECKLIST", ("Liste de contrôle sécurité soutage", "Bunkering safety checklist"),
               ("ISGOTT 6e édition, chapitre 25.5 ; ISO 13739 ; MEPC.1/Circ.875/Add.1", "ISGOTT 6th edition, chapter 25.5; ISO 13739; MEPC.1/Circ.875/Add.1"),
               frozenset({"PRE", "NAV"}), [("PRE", ("Avitailleur", "Supplier")), ("NAV", ("Chef mécanicien", "Chief engineer"))],
               build_bunker_checklist, family="PRE", templates=frozenset({"M4"}), answers=("M4:4.03", "M4:4.04", "M4:4.05"),
               purpose=("La liste de contrôle signée conjointement avant le soutage, avec l'agrément de l'avitailleur et les scellés du comptage.", "The checklist signed jointly before bunkering, with the supplier's licence and the metering seals.")))


# ------------------------------------------------------------------------------------------------ STS compatibility, equipment
def build_sts_compatibility(call: PortCall) -> list[dict]:
    partner = call.linked_call
    pv = partner.vessel if partner else None
    v = call.vessel
    return [
        identification(call, F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"), F("Prestataire STS / POAC", "STS provider / POAC", _party(call, "PRE"), source="CallParty PRE active")),
        table(("Caractéristiques comparées", "Compared particulars"),
              [("Caractéristique", "Particular"), ("Ce navire", "This vessel"), ("Navire partenaire", "Partner vessel"), ("Compatible ☐ / mesure", "Compatible ☐ / measure")],
              [["LOA / largeur (m) / LOA / beam (m)", f"{v.loa_m or '—'} / {v.beam_m or '—'}", f"{pv.loa_m or '—'} / {pv.beam_m or '—'}" if pv else None, None],
               ["Port en lourd (t) / Deadweight (t)", str(v.dwt) if v.dwt else None, str(pv.dwt) if pv and pv.dwt else None, None],
               ["Francs-bords au début et à la fin / Freeboards at start and end", None, None, None],
               ["Hauteur et position du collecteur ; réducteurs / Manifold height and position; reducers", None, None, None],
               ["Points de défenses et zones parallèles de coque / Fender contact points and parallel body", None, None, None],
               ["Treuils, chaumards, bollards ; plan d'amarrage / Winches, fairleads, bitts; mooring plan", None, None, None],
               ["Dispositifs de dégagement d'urgence / Emergency release arrangements", None, None, None]], blank_rows=1,
              source="Vessel (ce navire et partenaire) : loa_m, beam_m, dwt"),
        fields(("Plan d'opération", "Operations plan"), [
            F("Zone, mouillage ou en route ; navire manœuvrant / navire constant", "Area, at anchor or under way; manoeuvring / constant heading ship"), F("Limites météo et critères d'abandon", "Weather limits and abort criteria"),
            F("Défenses : type, taille, nombre, pression, certificats", "Fenders: type, size, number, pressure, certificates", wide=True), F("Flexibles : nombre, diamètre, longueur, pression d'essai, continuité, coupleur de rupture", "Hoses: number, diameter, length, test pressure, continuity, breakaway coupling", wide=True),
            F("Débits, pression, séquence ; communications", "Rates, pressure, sequence; communications"), F("Conclusion : compatibles ☐ sous conditions ☐ incompatibles ☐", "Conclusion: compatible ☐ with conditions ☐ incompatible ☐"),
        ], note=("OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapitres 2 (compatibilité), 4 (défenses), 5 (flexibles) et 6 (amarrage).",
                 "OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapters 2 (compatibility), 4 (fenders), 5 (hoses) and 6 (mooring).")),
    ]


_register(Form("STS_COMPATIBILITY", "STS_DOC", ("Étude de compatibilité STS des deux navires", "STS compatibility study of the two vessels"),
               ("OCIMF Ship to Ship Transfer Guide (2013), chapitres 2, 4, 5 et 6", "OCIMF Ship to Ship Transfer Guide (2013), chapters 2, 4, 5 and 6"),
               frozenset({"PRE"}), [("PRE", ("Prestataire STS / POAC", "STS provider / POAC")), ("NAV", ("Capitaine — ce navire", "Master — this vessel")), ("NAV", ("Capitaine — navire partenaire", "Master — partner vessel"))],
               build_sts_compatibility, family="PRE", templates=frozenset({"M3"}), needs_link=True, answers=("M3:3.05", "M3:3.11"),
               purpose=("L'étude de compatibilité des deux navires et le plan d'opération du prestataire STS.", "The STS provider's compatibility study of the two vessels and operations plan.")))


def build_sts_equipment(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"), F("Prestataire STS", "STS provider", _party(call, "PRE"), source="CallParty PRE active")),
        table(("Défenses primaires et secondaires", "Primary and secondary fenders"),
              [("Défense (n°, type)", "Fender (no., type)"), ("Dimensions / énergie", "Size / energy"), ("Pression de service (bar)", "Working pressure (bar)"), ("Certificat (n°, organisme, date)", "Certificate (no., body, date)"), ("Dernier essai / inspection", "Last test / inspection"), ("Vérification physique ☐", "Physical check ☐")],
              [], blank_rows=6),
        table(("Flexibles de transfert", "Transfer hoses"),
              [("Flexible (n°)", "Hose (no.)"), ("Diamètre / longueur", "Diameter / length"), ("Pression d'essai (bar) / date", "Test pressure (bar) / date"), ("Continuité électrique (date)", "Electrical continuity (date)"), ("Certificat (n°)", "Certificate (no.)"), ("Coupleur de rupture ☐", "Breakaway coupling ☐")],
              [], blank_rows=6),
        fields(("Autres équipements", "Other equipment"), [
            F("Aussières, manilles, bouées de défense", "Hawsers, shackles, fender buoys"), F("Vedettes, remorqueurs d'assistance", "Launches, assisting tugs"),
            F("Moyens antipollution déployables", "Deployable pollution response means"), F("Vérifié par (nom, date)", "Checked by (name, date)"),
        ], note=("OCIMF Ship to Ship Transfer Guide (2013), chapitres 4 et 5 ; ISO 17357 (défenses pneumatiques) ; OCIMF GMPHOM 2009 (flexibles).", "OCIMF Ship to Ship Transfer Guide (2013), chapters 4 and 5; ISO 17357 (pneumatic fenders); OCIMF GMPHOM 2009 (hoses).")),
    ]


_register(Form("STS_EQUIPMENT", "STS_DOC", ("Attestation des défenses et flexibles STS", "STS fenders and hoses attestation"),
               ("OCIMF Ship to Ship Transfer Guide (2013) ; ISO 17357 ; OCIMF GMPHOM 2009", "OCIMF Ship to Ship Transfer Guide (2013); ISO 17357; OCIMF GMPHOM 2009"),
               frozenset({"PRE"}), [("PRE", ("Prestataire STS", "STS provider")), ("NAV", ("Capitaine — reçu", "Master — received"))],
               build_sts_equipment, family="PRE", templates=frozenset({"M3", "M9"}), needs_link=True, answers=("M3:3.07", "M3:3.08", "M9:9.05"),
               purpose=("L'attestation des certificats et essais des défenses et des flexibles mis en œuvre.", "The attestation of the certificates and tests of the fenders and hoses used.")))


# ------------------------------------------------------------------------------------------------ reception facility, contractors
def build_reception_facility(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Installation / prestataire", "Facility / provider", _party(call, "PRE"), source="CallParty PRE active"), F("Opération demandée", "Operation requested")),
        fields(("Agrément et capacité", "Licence and capacity"), [
            F("Agrément (numéro, autorité, validité)", "Licence (number, authority, validity)"), F("Types de déchets ou de résidus acceptés", "Kinds of waste or residues accepted", wide=True),
            F("Capacité disponible aux dates de l'escale (m³)", "Capacity available on the call dates (m³)"), F("Moyens (barge, camions, bacs de réception, traitement)", "Means (barge, trucks, reception tanks, treatment)", wide=True),
            F("Délai de mise à disposition", "Lead time"), F("Conditions (horaires, accès, tarif de référence)", "Conditions (hours, access, reference tariff)", wide=True),
        ]),
        text(("Attestation", "Attestation"), [
            ("Le prestataire atteste disposer de l'agrément et de la capacité ci-dessus pour recevoir les déchets, résidus ou effluents de l'escale, et s'engage à délivrer un bordereau de réception pour chaque remise.",
             "The provider attests that it holds the licence and the capacity above to receive the call's waste, residues or effluents, and undertakes to issue a receipt for each delivery."),
        ], note=("MARPOL (installations de réception adéquates) ; circulaire OMI MEPC.1/Circ.834/Rev.1 ; agrément de l'autorité environnementale.", "MARPOL (adequate reception facilities); IMO circular MEPC.1/Circ.834/Rev.1; environmental authority licence.")),
    ]


_register(Form("RECEPTION_FACILITY", "CLEANING_DOC", ("Attestation d'agrément et de capacité de l'installation de réception", "Reception facility licence and capacity attestation"),
               ("MARPOL ; circulaire OMI MEPC.1/Circ.834/Rev.1", "MARPOL; IMO circular MEPC.1/Circ.834/Rev.1"),
               frozenset({"PRE"}), [("PRE", ("Installation de réception", "Reception facility")), ("AGE", ("Agence — reçu", "Agency — received"))],
               build_reception_facility, family="PRE", templates=frozenset({"M5", "M6"}), answers=("M6:6.02",),
               purpose=("L'attestation d'agrément et de capacité disponible de l'installation de réception pour l'escale.", "The reception facility's attestation of licence and available capacity for the call.")))


def build_works_crew(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Entreprise intervenante", "Contractor", _party(call, "PRE"), source="CallParty PRE active"), F("Travaux (nature, lieu, période)", "Works (nature, place, period)", wide=True)),
        table(("Intervenants", "Personnel"),
              [("Nom et prénom", "Full name"), ("Fonction", "Capacity"), ("Qualification / habilitation (n°, validité)", "Qualification / authorization (no., validity)"), ("Formation sécurité (ISGOTT, espace clos, point chaud)", "Safety training (ISGOTT, enclosed space, hot work)"), ("Pièce d'identité", "Identity document")],
              [], blank_rows=8),
        fields(("Entreprise", "Company"), [
            F("Assurance responsabilité civile (assureur, police, validité)", "Liability insurance (insurer, policy, validity)", wide=True), F("Certifications (ISO 9001 / 45001, agrément chantier)", "Certifications (ISO 9001 / 45001, yard licence)"),
            F("Matériel apporté à bord (liste, contrôles)", "Equipment brought on board (list, checks)", wide=True), F("Responsable des travaux à bord (contact)", "Person in charge of the works on board (contact)"),
        ], note=("Pièces exigées avant les travaux à bord ou à quai : qualification des intervenants, certificats, assurances ; le permis de travail reste délivré par le capitaine.",
                 "Documents required before works on board or at the quay: personnel qualifications, certificates, insurance; the work permit remains issued by the master.")),
    ]


_register(Form("WORKS_CREW", "WORKS_DOC", ("Dossier des intervenants extérieurs — qualifications, certificats, assurances", "Outside contractors' file — qualifications, certificates, insurance"),
               ("Code IGS ; ISGOTT 6e édition, chapitre 9 ; règlement du port (entreprises extérieures)", "ISM Code; ISGOTT 6th edition, chapter 9; port regulations (outside contractors)"),
               frozenset({"PRE"}), [("PRE", ("Entreprise intervenante", "Contractor")), ("NAV", ("Capitaine — reçu", "Master — received"))],
               build_works_crew, family="PRE", templates=frozenset({"M7"}), answers=("M7:7.02",),
               purpose=("Le dossier des intervenants extérieurs : qualifications, certificats et assurances avant les travaux.", "The outside contractors' file: qualifications, certificates and insurance before the works.")))
