"""Forms issued by the surveyor and the laboratory: sampling record, certificate of quantity, certificate of
quality (analysis report), tank cleanliness certificate, empty tanks / ROB certificate, gas-free certificate."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _mt,
    _operation,
    _party,
    _register,
    fields,
    identification,
    table,
    text,
)


def _measures(call: PortCall, kinds: tuple) -> list[list]:
    rows = []
    for m in call.measurements.filter(kind__in=kinds).order_by("created_at"):
        values = m.current_values()
        rows.append([m.get_kind_display(), m.product or call.product or "—", m.unit,
                     *[f"{values[p].value}" + (f" @ {values[p].temperature_c} °C" if values[p].temperature_c is not None else "") if p in values else None
                       for p in ("SHIP", "SHORE", "SURVEYOR")]])
    return rows


# ------------------------------------------------------------------------------------------------ sampling
def build_sampling(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit", "Product", call.product or None, source="PortCall.product"), F("Inspecteur", "Surveyor", _party(call, "INS"), source="CallParty INS active")),
        table(("Échantillons prélevés", "Samples drawn"),
              [("N°", "No."), ("Point (citerne, bac, ligne, collecteur)", "Point (tank, shore tank, line, manifold)"), ("Type (haut / milieu / bas / composite / continu)", "Type (upper / middle / lower / composite / running)"),
               ("Heure", "Time"), ("Volume / flacon", "Volume / container"), ("N° de scellé", "Seal number"), ("Destination (laboratoire, bord, terminal, rétention)", "Distribution (laboratory, ship, terminal, retained)")],
              [], blank_rows=12),
        fields(("Conditions de prélèvement", "Sampling conditions"), [
            F("Méthode (manuelle, automatique en ligne)", "Method (manual, automatic in-line)"), F("Appareillage (préleveur, bouteille, flacons)", "Equipment (sampler, bottle, containers)"),
            F("Température du produit (°C)", "Product temperature (°C)"), F("Témoins (bord, terminal)", "Witnesses (ship, terminal)"),
            F("Durée de conservation des échantillons de rétention", "Retention period of retained samples"), F("Observations", "Remarks", wide=True),
        ]),
        text(("Procès-verbal", "Record"), [
            ("Les échantillons ci-dessus ont été prélevés, scellés et étiquetés contradictoirement ; leur distribution est consignée. L'échantillon MARPOL du soutage, le cas échéant, fait l'objet du bordereau du fournisseur.",
             "The samples above were drawn, sealed and labelled jointly; their distribution is recorded. The MARPOL bunker sample, if any, is covered by the supplier's note."),
        ], note=("API MPMS chapitre 8.1 (échantillonnage manuel) et 8.2 (automatique) ; ISO 3170 / 3171 ; EI HM 23.", "API MPMS chapter 8.1 (manual sampling) and 8.2 (automatic); ISO 3170 / 3171; EI HM 23.")),
    ]


_register(Form("SAMPLING_RECORD", "SAMPLING_RECORD", ("Procès-verbal d'échantillonnage", "Sampling record"),
               ("API MPMS chapitre 8 ; ISO 3170 / 3171 ; EI HM 23", "API MPMS chapter 8; ISO 3170 / 3171; EI HM 23"),
               frozenset({"INS"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Navire — témoin", "Ship — witness")), ("TER", ("Terminal — témoin", "Terminal — witness"))],
               build_sampling, family="INS", templates=frozenset({"M1", "M2", "M3"}), needs_link=True, answers=("M1:1.07",),
               purpose=("Le procès-verbal des échantillons prélevés, scellés et distribués.", "The record of the samples drawn, sealed and distributed.")))


# ------------------------------------------------------------------------------------------------ quantity certificate
def build_quantity_cert(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit", "Product", call.product or None, source="PortCall.product"), F("Opération", "Operation", _operation(call), source="PortCall.template_codes")),
        table(("Quantités du registre", "Registry quantities"),
              [("Mesure", "Measurement"), ("Produit", "Product"), ("Unité", "Unit"), ("Bord", "Ship"), ("Terre", "Shore"), ("Inspecteur", "Surveyor")],
              _measures(call, ("INITIAL", "FINAL", "OBQ", "ROB", "BL")), blank_rows=1, source="Measurement et MeasurementValue (valeurs courantes par partie)"),
        fields(("Détermination de la quantité", "Quantity determination"), [
            F("Jaugeage initial bord (date, heure)", "Initial ship gauging (date, time)", _mt(call, "TRANSFER_START"), source="jalon TRANSFER_START"), F("Jaugeage final bord (date, heure)", "Final ship gauging (date, time)", _mt(call, "TRANSFER_END"), source="jalon TRANSFER_END"),
            F("Quantité bord (TCV / GSV / masse) avec VEF", "Ship figure (TCV / GSV / mass) with VEF"), F("Facteur d'expérience navire (VEF) appliqué", "Vessel experience factor (VEF) applied"),
            F("Quantité terre (bacs / compteurs)", "Shore figure (tanks / meters)"), F("Eau libre, sédiments, OBQ / ROB", "Free water, sediment, OBQ / ROB"),
            F("Densité à 15 °C / API et table de conversion", "Density at 15 °C / API and conversion table"), F("Quantité certifiée (unité)", "Certified quantity (unit)"),
            F("Écart bord/terre (quantité, %) et tolérance du port", "Ship/shore difference (quantity, %) and port tolerance"), F("Observations", "Remarks", wide=True),
        ]),
        text(("Certificat", "Certificate"), [
            ("L'inspecteur certifie que la quantité ci-dessus a été déterminée contradictoirement selon les méthodes indiquées ; la plateforme ne désigne pas de valeur de référence, chaque partie conservant sa propre mesure au registre.",
             "The surveyor certifies that the quantity above was determined jointly by the stated methods; the platform designates no reference value, each party keeping its own measurement in the registry."),
        ], note=("API MPMS chapitre 17.1 (inspection des cargaisons maritimes), 11 et 12 (calculs) ; EI HM 28 / HM 50 ; tables ASTM D1250.", "API MPMS chapter 17.1 (marine cargo inspection), 11 and 12 (calculations); EI HM 28 / HM 50; ASTM D1250 tables.")),
    ]


_register(Form("QUANTITY_CERT", "QQ_CERT", ("Certificat de quantité", "Certificate of quantity"),
               ("API MPMS chapitres 11, 12 et 17 ; EI HM 28 / 50 ; ASTM D1250", "API MPMS chapters 11, 12 and 17; EI HM 28 / 50; ASTM D1250"),
               frozenset({"INS"}), [("INS", ("Inspecteur", "Surveyor"))],
               build_quantity_cert, family="INS", templates=frozenset({"M1", "M2", "M3"}), needs_link=True, answers=("M1:1.08", "M1:1.16", "M2:2.15", "M3:3.14"),
               purpose=("Le certificat de quantité de l'inspecteur, établi sur les jaugeages bord et terre du registre.", "The surveyor's certificate of quantity, drawn up on the ship and shore gaugings of the registry.")))


# ------------------------------------------------------------------------------------------------ quality certificate
def build_quality_cert(call: PortCall) -> list[dict]:
    tests = [["Masse volumique à 15 °C (kg/m³) / Density at 15 °C", "ISO 12185 / ASTM D4052", None, None], ["Point d'éclair (°C) / Flash point", "ISO 2719 / ASTM D93", None, None],
             ["Teneur en soufre (mg/kg ou % m/m) / Sulphur content", "ISO 20846 / ASTM D4294", None, None], ["Teneur en eau (mg/kg ou % v/v) / Water content", "ISO 12937 / ASTM D6304", None, None],
             ["Sédiments / contamination (mg/kg) / Sediment / contamination", "ISO 12662 / ASTM D473", None, None], ["Couleur / aspect / Colour / appearance", "ASTM D1500 / visuel", None, None],
             ["Viscosité cinématique à 40 °C (mm²/s) / Kinematic viscosity at 40 °C", "ISO 3104 / ASTM D445", None, None], ["Distillation (°C) / Distillation", "ISO 3405 / ASTM D86", None, None],
             ["Indice de cétane ou d'octane / Cetane or octane number", "ISO 5165 / ASTM D613 — ISO 5164 / ASTM D2699", None, None], ["Autres (benzène, plomb, oxygénés, conductivité…) / Others", None, None, None]]
    return [
        identification(call, F("Produit / grade", "Product / grade", call.product or None, source="PortCall.product"), F("Laboratoire", "Laboratory", _party(call, "INS"), source="CallParty INS active")),
        fields(("Échantillon analysé", "Sample analysed"), [
            F("Échantillon n° / scellé n°", "Sample no. / seal no."), F("Point et date de prélèvement", "Sampling point and date"),
            F("Reçu au laboratoire le", "Received at the laboratory on"), F("Spécification de référence (norme, contrat)", "Reference specification (standard, contract)"),
        ]),
        table(("Résultats d'analyse", "Analysis results"),
              [("Caractéristique", "Property"), ("Méthode", "Method"), ("Spécification (min / max)", "Specification (min / max)"), ("Résultat", "Result")], tests, blank_rows=2),
        fields(("Conclusion", "Conclusion"), [
            F("Conforme à la spécification ☐ non conforme ☐ (caractéristiques hors spécification)", "On specification ☐ off specification ☐ (properties out of specification)", wide=True),
            F("Analyste / responsable du laboratoire", "Analyst / laboratory manager"), F("Date du rapport", "Date of report"),
        ], note=("Rapport d'essai selon ISO/IEC 17025 ; méthodes ISO / ASTM / EN citées par caractéristique ; les spécifications sont celles du contrat ou de la norme nationale du produit.",
                 "Test report under ISO/IEC 17025; ISO / ASTM / EN methods cited per property; specifications are those of the contract or of the national product standard.")),
    ]


_register(Form("QUALITY_CERT", "QUALITY_CERT", ("Certificat de qualité — rapport d'analyse", "Certificate of quality — analysis report"),
               ("ISO/IEC 17025 (rapport d'essai) ; méthodes ISO / ASTM / EN", "ISO/IEC 17025 (test report); ISO / ASTM / EN methods"),
               frozenset({"INS"}), [("INS", ("Laboratoire", "Laboratory"))],
               build_quality_cert, family="INS", templates=frozenset({"M1", "M2", "M3", "M4"}), needs_link=True, answers=("M1:1.16", "M2:2.07"),
               purpose=("Le rapport d'analyse du laboratoire et sa conclusion de conformité à la spécification.", "The laboratory's analysis report and its conclusion on conformity to the specification.")))


# ------------------------------------------------------------------------------------------------ cleanliness, empty tanks
def build_cleanliness_cert(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit à charger", "Product to be loaded", call.product or None, source="PortCall.product"), F("Inspection le (date, heure)", "Inspection on (date, time)")),
        table(("Inspection des citernes", "Tank inspection"),
              [("Citerne", "Tank"), ("Dernière cargaison", "Last cargo"), ("Méthode d'inspection (visuelle, wall-wash, mesure)", "Inspection method (visual, wall-wash, measurement)"), ("Résultat", "Result"), ("Acceptée ☐ refusée ☐", "Accepted ☐ rejected ☐"), ("Observations", "Remarks")],
              [], blank_rows=12),
        fields(("Lignes, pompes, collecteur", "Lines, pumps, manifold"), [
            F("Lignes et pompes inspectées / purgées", "Lines and pumps inspected / drained"), F("Collecteur et réducteurs", "Manifold and reducers"),
            F("Atmosphère des citernes lors de l'inspection (O₂, LEL)", "Tank atmosphere during inspection (O₂, LEL)"), F("Réserves", "Reservations", wide=True),
        ]),
        text(("Certificat", "Certificate"), [
            ("L'inspecteur certifie que les citernes ci-dessus ont été inspectées contradictoirement et jugées aptes à recevoir le produit indiqué, sous les réserves mentionnées. Le certificat ne couvre que l'état constaté à l'heure de l'inspection.",
             "The surveyor certifies that the tanks above were inspected jointly and found fit to receive the stated product, subject to the reservations noted. The certificate covers only the condition found at the time of inspection."),
        ], note=("Pratique de l'inspection des cargaisons (tank cleanliness / dry certificate) ; ISGOTT 6e édition, chapitre 22.4 ; normes de propreté du produit (contrat, terminal).",
                 "Cargo inspection practice (tank cleanliness / dry certificate); ISGOTT 6th edition, chapter 22.4; product cleanliness standards (contract, terminal).")),
    ]


_register(Form("CLEANLINESS_CERT", "CLEANLINESS_CERT", ("Certificat de propreté des citernes", "Tank cleanliness certificate"),
               ("Pratique de l'inspection des cargaisons ; ISGOTT 6e édition, chapitre 22.4", "Cargo inspection practice; ISGOTT 6th edition, chapter 22.4"),
               frozenset({"INS"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Chef de la cargaison", "Chief officer")), ("TER", ("Terminal", "Terminal"))],
               build_cleanliness_cert, family="INS", templates=frozenset({"M2"}), answers=("M2:2.04",),
               purpose=("Le certificat de propreté des citernes délivré après l'inspection contradictoire, avant chargement.", "The tank cleanliness certificate issued after the joint inspection, before loading.")))


def build_empty_tanks_cert(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Produit déchargé", "Product discharged", call.product or None, source="PortCall.product"), F("Fin du déchargement", "Completion of discharge", _mt(call, "TRANSFER_END"), source="jalon TRANSFER_END")),
        table(("Reste à bord par citerne (ROB)", "Remaining on board per tank (ROB)"),
              [("Citerne", "Tank"), ("Sondage (mm)", "Sounding (mm)"), ("Liquide (m³)", "Liquid (m³)"), ("Non liquide (m³)", "Non-liquid (m³)"), ("Pompable ☐ / non pompable ☐", "Pumpable ☐ / non-pumpable ☐"), ("Observations", "Remarks")],
              [], blank_rows=12),
        fields(("Totaux et conditions", "Totals and conditions"), [
            F("ROB total liquide / non liquide (m³)", "Total ROB liquid / non-liquid (m³)"), F("OBQ à l'arrivée (m³) pour comparaison", "OBQ on arrival (m³) for comparison"),
            F("Assiette et gîte lors du sondage", "Trim and list at sounding"), F("Lignes et pompes : vidangées ☐ — contenu estimé (m³)", "Lines and pumps: drained ☐ — estimated content (m³)"),
            F("Citernes vides au sens du contrat ☐ (seuil)", "Tanks empty within the meaning of the contract ☐ (threshold)"), F("Réserves (navire, terminal)", "Reservations (ship, terminal)", wide=True),
        ]),
        text(("Constat", "Statement"), [
            ("Le présent constat, établi contradictoirement, consigne les quantités restant à bord après déchargement ; il sert de base au calcul de la quantité livrée et à toute réclamation de ROB.",
             "This joint statement records the quantities remaining on board after discharge; it is the basis of the delivered quantity calculation and of any ROB claim."),
        ], note=("API MPMS chapitre 17.1 et 17.4 (OBQ / ROB) ; pratique de l'inspection des cargaisons (dry tank / empty tank certificate).", "API MPMS chapter 17.1 and 17.4 (OBQ / ROB); cargo inspection practice (dry tank / empty tank certificate).")),
    ]


_register(Form("EMPTY_TANKS_CERT", "EMPTY_TANKS_CERT", ("Certificat de citernes vides — constat de ROB", "Empty tanks certificate — ROB statement"),
               ("API MPMS chapitre 17.1 et 17.4 ; pratique de l'inspection des cargaisons", "API MPMS chapter 17.1 and 17.4; cargo inspection practice"),
               frozenset({"INS"}), [("INS", ("Inspecteur", "Surveyor")), ("NAV", ("Chef de la cargaison", "Chief officer")), ("TER", ("Terminal", "Terminal"))],
               build_empty_tanks_cert, family="INS", templates=frozenset({"M1", "M3"}), needs_link=True, answers=("M1:1.14",),
               purpose=("Le constat contradictoire des quantités restant à bord après déchargement.", "The joint statement of the quantities remaining on board after discharge.")))


# ------------------------------------------------------------------------------------------------ gas-free
def build_gas_free_cert(call: PortCall) -> list[dict]:
    return [
        identification(call, F("Objet : travaux par point chaud ☐ entrée en espace clos ☐ nettoyage ☐ réparation à quai ☐", "Purpose: hot work ☐ enclosed space entry ☐ cleaning ☐ repair alongside ☐"),
                       F("Certificat n° / validité (de / à)", "Certificate no. / validity (from / to)")),
        table(("Espaces contrôlés", "Spaces tested"),
              [("Espace", "Space"), ("Heure", "Time"), ("O₂ (% vol.)", "O₂ (% vol.)"), ("Hydrocarbures (% LEL)", "Hydrocarbons (% LEL)"), ("H₂S (ppm)", "H₂S (ppm)"), ("Benzène / autres toxiques (ppm)", "Benzene / other toxics (ppm)"), ("Conclusion", "Conclusion")],
              [], blank_rows=10),
        fields(("Conditions", "Conditions"), [
            F("Appareils de mesure (type, n° de série, étalonnage)", "Instruments (type, serial no., calibration)", wide=True), F("Ventilation à maintenir ☐ ; nouvelles mesures toutes les (h)", "Ventilation to be maintained ☐; new tests every (h)"),
            F("Espaces adjacents couverts par le certificat", "Adjacent spaces covered by the certificate", wide=True), F("Restrictions", "Restrictions", wide=True),
        ]),
        text(("Certificat", "Certificate"), [
            ("L'inspecteur (chimiste maritime) certifie que les espaces ci-dessus, aux heures indiquées, sont : sûrs pour l'entrée ☐ / sûrs pour les travaux par point chaud ☐ / non sûrs ☐, aux conditions mentionnées. Le certificat cesse de valoir à l'expiration indiquée ou dès que les conditions changent.",
             "The surveyor (marine chemist) certifies that the spaces above, at the stated times, are: safe for entry ☐ / safe for hot work ☐ / not safe ☐, on the conditions noted. The certificate lapses at the stated expiry or as soon as conditions change."),
        ], note=("ISGOTT 6e édition, chapitres 9 et 10 ; NFPA 306 (Standard for the Control of Gas Hazards on Vessels) ; résolution OMI A.1050(27).", "ISGOTT 6th edition, chapters 9 and 10; NFPA 306 (Standard for the Control of Gas Hazards on Vessels); IMO resolution A.1050(27).")),
    ]


_register(Form("GAS_FREE_CERT", "GAS_FREE_CERT", ("Certificat de dégazage", "Gas-free certificate"),
               ("ISGOTT 6e édition, chapitres 9–10 ; NFPA 306 ; résolution OMI A.1050(27)", "ISGOTT 6th edition, chapters 9–10; NFPA 306; IMO resolution A.1050(27)"),
               frozenset({"INS"}), [("INS", ("Inspecteur / chimiste maritime", "Surveyor / marine chemist")), ("NAV", ("Capitaine — reçu", "Master — received"))],
               build_gas_free_cert, family="INS", templates=frozenset({"M6", "M7"}), answers=("M6:6.05", "M7:7.05"),
               purpose=("Le certificat de dégazage des espaces contrôlés, avec sa durée de validité explicite.", "The gas-free certificate of the spaces tested, with its explicit period of validity.")))
