"""Forms issued by the owner, charterer or receiver: nomination and charter-party recap, documentary instructions
for the bill of lading, insurance confirmation, letter of indemnity for delivery without bill of lading."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _operation,
    _parties,
    _partner,
    _party,
    _quantity,
    _register,
    _vessel,
    fields,
    identification,
    table,
    text,
)


# ------------------------------------------------------------------------------------------------ nomination / recap
def build_cp_recap(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Mandant (armateur / affréteur)", "Principal (owner / charterer)", _parties(call, "COM"), source="CallParty COM actives"),
                       F("Opération / quantité", "Operation / quantity", f"{_operation(call)} — {_quantity(call) or '—'}", source="PortCall.template_codes, quantity")),
        fields(("Charte-partie", "Charter-party"), [
            F("Type et date de la charte-partie (voyage, à temps)", "Type and date of the charter-party (voyage, time)"), F("Affréteur / armateur disposant", "Charterer / disponent owner"),
            F("Laycan (de / à)", "Laycan (from / to)"), F("Ports de chargement et de déchargement", "Loading and discharge ports"),
            F("Cargaison (produit, quantité, tolérance)", "Cargo (product, quantity, tolerance)", wide=True), F("Débit de pompage garanti / pression", "Guaranteed pumping rate / pressure"),
            F("Temps de planche (heures) ; NOR : délai et conditions", "Laytime (hours); NOR: notice time and conditions", wide=True), F("Surestaries (taux) / dispatch", "Demurrage (rate) / despatch"),
            F("Clauses d'escale (agents, frais, douane, heures exclues)", "Port-call clauses (agents, costs, customs, excepted periods)", wide=True),
        ]),
        fields(("Nomination", "Nomination"), [
            F("Navire nommé et accepté le", "Vessel nominated and accepted on"), F("Terminal / réceptionnaire", "Terminal / receiver", _parties(call, "TER"), source="CallParty TER actives"),
            F("Inspecteur désigné", "Surveyor appointed", _party(call, "INS"), source="CallParty INS active"), F("Agent nommé par", "Agent appointed by", str(call.agency), source="PortCall.agency"),
            F("Instructions particulières (échantillonnage, documents, scellés)", "Special instructions (sampling, documents, seals)", wide=True),
        ], note=("Extrait communiqué à l'agence pour l'escale ; les clauses non reproduites restent celles de la charte-partie signée (BIMCO / ASBATANKVOY / SHELLVOY ou autre formule).",
                 "Extract provided to the agency for the call; clauses not reproduced remain those of the signed charter-party (BIMCO / ASBATANKVOY / SHELLVOY or other form).")),
    ]


_register(Form("CP_RECAP", "CP_RECAP", ("Nomination et extrait de charte-partie", "Nomination and charter-party recap"),
               ("Pratique de l'affrètement pétrolier (ASBATANKVOY, SHELLVOY, BPVOY) ; BIMCO", "Tanker chartering practice (ASBATANKVOY, SHELLVOY, BPVOY); BIMCO"),
               frozenset({"COM"}), [("COM", ("Mandant", "Principal")), ("AGE", ("Agence — reçu", "Agency — received"))],
               build_cp_recap, family="COM", answers=("M0:04",),
               purpose=("L'extrait de recap ou de charte-partie et les clauses d'escale que le mandant communique à l'agence.", "The recap or charter-party extract and the port-call clauses the principal gives the agency.")))


# ------------------------------------------------------------------------------------------------ documentary instructions
def build_doc_instructions(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Mandant", "Principal", _parties(call, "COM"), source="CallParty COM actives"), F("Produit / quantité", "Product / quantity", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity")),
        fields(("Connaissement", "Bill of lading"), [
            F("Expéditeur (shipper)", "Shipper", wide=True), F("Destinataire (consignee) — à l'ordre de", "Consignee — to the order of", wide=True), F("Notifier", "Notify party", wide=True),
            F("Nombre d'originaux et de copies", "Number of originals and copies"), F("Base du chiffre : terre ☐ bord ☐ inspecteur ☐", "Basis of figure: shore ☐ ship ☐ surveyor ☐"),
            F("Description des marchandises (libellé exact)", "Description of goods (exact wording)", wide=True), F("Port de déchargement / destination", "Port of discharge / destination"),
            F("Mentions de fret ; clauses à insérer", "Freight terms; clauses to insert", wide=True), F("Remise des originaux à (personne, adresse)", "Originals to be delivered to (person, address)", wide=True),
        ]),
        fields(("Autres documents demandés", "Other documents requested"), [
            F("Certificats de quantité et de qualité (destinataires)", "Certificates of quantity and quality (recipients)"), F("Certificat d'origine, facture, liste de colisage", "Certificate of origin, invoice, packing list"),
            F("Reçu du capitaine (mate's receipt), time sheet, rapport des faits", "Mate's receipt, time sheet, statement of facts"), F("Lettre de protestation à émettre si", "Letter of protest to be issued if"),
        ]),
        text(("Instruction", "Instruction"), [
            ("Le mandant donne à l'agence l'instruction écrite d'émettre, pour le compte du capitaine, le connaissement selon les mentions ci-dessus. L'émission n'intervient qu'après accord sur la quantité ; toute divergence est signalée au mandant avant signature.",
             "The principal instructs the agency in writing to issue, for the master, the bill of lading with the particulars above. The issue takes place only after agreement on the quantity; any discrepancy is reported to the principal before signature."),
        ], note=("FLX-CDC-001 EF-7.4 — verrou du connaissement : l'instruction documentaire écrite (tâche M2:2.16) est l'une des conditions du point d'arrêt BL_ISSUE.",
                 "FLX-CDC-001 EF-7.4 — bill of lading lock: the written documentary instruction (task M2:2.16) is one of the conditions of the BL_ISSUE hold point.")),
    ]


_register(Form("DOC_INSTRUCTIONS", "DOC_INSTRUCTIONS", ("Instruction documentaire du mandant (connaissement)", "Principal's documentary instructions (bill of lading)"),
               ("Pratique du commerce des hydrocarbures ; Règles de La Haye-Visby", "Oil trade practice; Hague-Visby Rules"),
               frozenset({"COM"}), [("COM", ("Mandant", "Principal")), ("AGE", ("Agence — reçu", "Agency — received"))],
               build_doc_instructions, family="COM", templates=frozenset({"M2", "MB2"}), answers=("M2:2.16", "MB2:B2.16"),
               purpose=("L'instruction écrite du mandant pour l'émission du connaissement et des documents de cargaison.", "The principal's written instructions for the issue of the bill of lading and cargo documents.")))


# ------------------------------------------------------------------------------------------------ insurance
def build_insurance(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Navire partenaire", "Partner vessel", _partner(call), source="PortCall.linked_call"), F("Prestataire STS / terminal", "STS provider / terminal", _party(call, "PRE") or _party(call, "TER"), source="CallParty PRE ou TER")),
        table(("Couvertures", "Covers"),
              [("Assuré", "Insured"), ("Nature (P&I, corps et machines, RC prestataire, pollution)", "Kind (P&I, hull and machinery, provider's liability, pollution)"), ("Assureur / club", "Insurer / club"), ("Police / certificat n°", "Policy / certificate no."), ("Validité", "Validity"), ("Plafond", "Limit")],
              [[_vessel(call), "P&I / Hull & machinery", None, None, None, None], [_partner(call) or "Navire partenaire / Partner vessel", "P&I / Hull & machinery", None, None, None, None],
               [_party(call, "PRE") or "Prestataire / Provider", "RC prestataire / Provider's liability", None, None, None, None]], blank_rows=2,
              source="Vessel, PortCall.linked_call, CallParty PRE"),
        fields(("Confirmation", "Confirmation"), [
            F("Opération couverte : STS ☐ accostage à couple ☐ autre ☐", "Operation covered: STS ☐ double banking ☐ other ☐"), F("Clauses particulières (STS clause, knock-for-knock)", "Special clauses (STS clause, knock-for-knock)", wide=True),
            F("Certificat CLC / Bunkers / assurance pollution (n°, validité)", "CLC / Bunkers / pollution insurance certificate (no., validity)", wide=True), F("Confirmé par (nom, fonction)", "Confirmed by (name, capacity)"),
        ], note=("Les attestations des assureurs sont jointes au dossier ; la confirmation du mandant ne se substitue pas aux certificats d'assurance statutaires du navire (CLC 1992, Convention Bunkers 2001).",
                 "The insurers' certificates are attached to the file; the principal's confirmation does not replace the ship's statutory insurance certificates (CLC 1992, Bunkers Convention 2001).")),
    ]


_register(Form("INSURANCE", "INSURANCE", ("Confirmation des couvertures d'assurance", "Insurance cover confirmation"),
               ("Pratique du P&I et de l'assurance maritime ; OCIMF Ship to Ship Transfer Guide (assurances)", "P&I and marine insurance practice; OCIMF Ship to Ship Transfer Guide (insurance)"),
               frozenset({"COM"}), [("COM", ("Mandant", "Principal")), ("AGE", ("Agence — reçu", "Agency — received"))],
               build_insurance, family="COM", templates=frozenset({"M3", "M9"}), needs_link=True, answers=("M3:3.09", "M9:9.10"),
               purpose=("La confirmation des couvertures d'assurance des navires et du prestataire pour l'opération STS ou à couple.", "The confirmation of the insurance covers of the vessels and the provider for the STS or double banking operation.")))


# ------------------------------------------------------------------------------------------------ letter of indemnity
def build_loi(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Destinataire (armateur / capitaine)", "Addressee (owner / master)", wide=True), F("Date", "Date")),
        fields(("Cargaison et livraison demandée", "Cargo and delivery requested"), [
            F("Cargaison (produit, quantité)", "Cargo (product, quantity)", f"{call.product or '—'} — {_quantity(call) or '—'}", source="PortCall.product, quantity"),
            F("Connaissement(s) n° / date / port de chargement", "Bill(s) of lading no. / date / port of loading", wide=True), F("Livrer à (réceptionnaire)", "Deliver to (receiver)", _parties(call, "TER"), source="CallParty TER actives"),
            F("Lieu de livraison", "Place of delivery", f"{call.port.name}", source="Port.name"), F("Motif : originaux non parvenus ☐ port autre que celui du connaissement ☐", "Reason: originals not arrived ☐ port other than the B/L port ☐"),
        ]),
        text(("Engagement", "Undertaking"), [
            ("En contrepartie de la livraison de la cargaison sans présentation des connaissements originaux, le soussigné s'engage à indemniser l'armateur, le capitaine et leurs assureurs de toute responsabilité, perte, dommage ou dépense résultant de cette livraison, à fournir les fonds nécessaires à la défense de toute action, à procurer la mainlevée de toute saisie du navire et à remettre les originaux dès réception.",
             "In consideration of delivering the cargo without production of the original bills of lading, the undersigned undertakes to indemnify the owner, the master and their insurers against any liability, loss, damage or expense arising from such delivery, to provide funds for the defence of any claim, to secure the release of the vessel from any arrest and to surrender the originals as soon as received."),
            ("Le présent engagement est régi par le droit désigné au contrat et prend fin à la remise des originaux.", "This undertaking is governed by the law designated in the contract and ends on surrender of the originals."),
        ], note=("Structure des lettres de garantie types du Groupe international des clubs P&I (formules A / B, livraison sans connaissement, livraison dans un port autre) ; à signer par le mandant et, le cas échéant, contresigner par une banque.",
                 "Structure of the International Group of P&I Clubs standard letters of indemnity (forms A / B, delivery without bill of lading, delivery at another port); signed by the principal and, where required, countersigned by a bank.")),
    ]


_register(Form("LOI", "LOI", ("Lettre de garantie — livraison sans connaissement original", "Letter of indemnity — delivery without original bill of lading"),
               ("Formules types du Groupe international des clubs P&I (LOI A / B)", "International Group of P&I Clubs standard forms (LOI A / B)"),
               frozenset({"COM"}), [("COM", ("Mandant (réceptionnaire / affréteur)", "Principal (receiver / charterer)")), ("COM", ("Banque — contresignature (le cas échéant)", "Bank — countersignature (if required)")), ("AGE", ("Agence — reçu pour l'armateur", "Agency — received for the owner"))],
               build_loi, family="COM", templates=frozenset({"M1", "M3"}), needs_link=True,
               purpose=("La lettre de garantie remise à l'armateur pour une livraison sans présentation du connaissement original.", "The letter of indemnity given to the owner for delivery without production of the original bill of lading.")))
