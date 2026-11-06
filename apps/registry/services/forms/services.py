"""Forms issued by the marine services (pilots, tugs, mooring gang) and, for the service note, by any provider:
movement order and service delivery note."""
from __future__ import annotations

from ...models import PortCall
from .core import (
    F,
    Form,
    _mt,
    _party,
    _register,
    _request,
    _request_rows,
    _where,
    dt,
    fields,
    identification,
    table,
    text,
)


# ------------------------------------------------------------------------------------------------ movement order
def build_movement_order(call: PortCall) -> list[dict]:
    req = _request(call, "MARINE_SERVICES")
    auth = None
    for a in call.authorizations.filter(type_code="MOVEMENT").order_by("-signed_at"):
        if not a.is_cancelled:
            auth = a
            break
    return [
        identification(call, F("Autorisation de mouvement n° / validité", "Movement authorization no. / validity", f"{auth.number} — {dt(auth.valid_until)}" if auth else None, source="Authorization MOVEMENT"),
                       F("Demande de services n°", "Service request no.", req.reference if req else None, source="ServiceRequest MARINE_SERVICES")),
        fields(("Demande de services telle que déposée", "Service request as filed"), _request_rows(req) or [F("Services demandés", "Services requested", wide=True)]),
        fields(("Mouvement ordonné", "Movement ordered"), [
            F("Nature : entrée ☐ accostage ☐ déhalage ☐ sortie ☐", "Kind: inward ☐ berthing ☐ shifting ☐ outward ☐"), F("De / à", "From / to", _where(call), source="poste ou zone de l'étape"),
            F("Heure prévue d'embarquement du pilote", "Planned pilot boarding time"), F("Point d'embarquement du pilote", "Pilot boarding point"),
            F("Pilote désigné", "Pilot assigned"), F("Remorqueurs (noms, puissance, nombre)", "Tugs (names, bollard pull, number)"),
            F("Lamaneurs (équipe, vedette)", "Mooring gang (team, launch)"), F("Canal VHS de travail", "Working VHF channel"),
            F("Tirant d'eau annoncé AV / AR (m)", "Declared draft fwd / aft (m)"), F("Conditions (marée, courant, vent, visibilité)", "Conditions (tide, current, wind, visibility)", wide=True),
        ]),
        text(("Ordre", "Order"), [
            ("Les services nautiques confirment la réservation ci-dessus et ordonnent le mouvement aux conditions indiquées, sous couvert de l'autorisation de mouvement en vigueur. Le capitaine conserve la conduite et la responsabilité du navire ; le pilote le conseille.",
             "The marine services confirm the booking above and order the movement on the stated conditions, under the movement authorization in force. The master keeps the conduct and the responsibility of the ship; the pilot advises."),
        ], note=("Résolution OMI A.960(23) (pilotage) ; règlement des services nautiques du port.", "IMO resolution A.960(23) (pilotage); port marine services regulations.")),
    ]


_register(Form("MOVEMENT_ORDER", "MOVEMENT_ORDER", ("Ordre de mouvement — confirmation des services nautiques", "Movement order — marine services confirmation"),
               ("Résolution OMI A.960(23) ; règlement des services nautiques du port", "IMO resolution A.960(23); port marine services regulations"),
               frozenset({"SVC"}), [("SVC", ("Services nautiques", "Marine services")), ("NAV", ("Capitaine — reçu", "Master — received")), ("CAP", ("Capitainerie — informée", "Harbour master — informed"))],
               build_movement_order, family="SVC", answers=("REQ:MARINE_SERVICES", "M0:18"),
               purpose=("La confirmation des services nautiques réservés (pilote, remorqueurs, lamaneurs) et l'ordre de mouvement.", "The confirmation of the marine services booked (pilot, tugs, mooring gang) and the movement order.")))


# ------------------------------------------------------------------------------------------------ service note
def build_service_note(call: PortCall) -> list[dict]:
    times = [["Pilote à bord (arrivée) / Pilot on board (arrival)", _mt(call, "PILOT_ON_BOARD_ARR")], ["Première amarre / First line", _mt(call, "FIRST_LINE")],
             ["Amarrage terminé / All fast", _mt(call, "ALL_FAST")], ["Pilote à bord (départ) / Pilot on board (departure)", _mt(call, "PILOT_ON_BOARD_DEP")],
             ["Dernière amarre / Last line", _mt(call, "LAST_LINE")], ["Appareillé / Departed", _mt(call, "DEPARTED")]]
    return [
        identification(call, F("Prestataire", "Provider", _party(call, "SVC") or _party(call, "PRE"), source="CallParty SVC ou PRE active"), F("Commande / demande n°", "Order / request no.")),
        table(("Prestation", "Service"),
              [("Service", "Service"), ("Moyens (noms, nombre)", "Means (names, number)"), ("Début", "Start"), ("Fin", "End"), ("Durée / quantité", "Duration / quantity"), ("Observations", "Remarks")],
              [["Pilotage / Pilotage", None, None, None, None, None], ["Remorquage / Towage", None, None, None, None, None], ["Lamanage / Mooring", None, None, None, None, None],
               ["Vedette, transport / Launch, transport", None, None, None, None, None], ["Eau douce (m³, potabilité contrôlée ☐) / Fresh water (m³, potability checked ☐)", None, None, None, None, None],
               ["Provisions, pièces / Provisions, spares", None, None, None, None, None], ["Autre / Other", None, None, None, None, None]], blank_rows=2),
        table(("Heures du registre", "Registry times"), [("Événement", "Event"), ("Heure (UTC)", "Time (UTC)")], times, source="jalons PILOT_ON_BOARD_ARR, FIRST_LINE, ALL_FAST, PILOT_ON_BOARD_DEP, LAST_LINE, DEPARTED"),
        fields(("Constat", "Acknowledgement"), [
            F("Prestation exécutée conformément à la commande ☐ avec réserves ☐", "Service performed as ordered ☐ with reservations ☐"), F("Réserves (retard, attente, dommage)", "Reservations (delay, waiting, damage)", wide=True),
            F("Certificats joints (potabilité, étalonnage, agrément)", "Certificates attached (potability, calibration, licence)", wide=True), F("Représentant du prestataire (nom)", "Provider's representative (name)"),
        ], note=("Bon de prestation signé par le capitaine (ou l'agent) et le prestataire ; base de facturation du compte d'escale. Les heures de pilotage, d'amarrage et d'appareillage viennent du registre contradictoire.",
                 "Service note signed by the master (or the agent) and the provider; basis of the disbursement account. Pilotage, mooring and departure times come from the contradictory registry.")),
    ]


_register(Form("SERVICE_NOTE", "SERVICE_NOTE", ("Bon de prestation de service", "Service delivery note"),
               ("Pratique portuaire (bon de pilotage, de remorquage, de lamanage, de livraison) ; FONASBA (compte d'escale)", "Port practice (pilotage, towage, mooring, delivery vouchers); FONASBA (disbursement account)"),
               frozenset({"SVC", "PRE"}), [("SVC", ("Prestataire", "Provider")), ("NAV", ("Capitaine — reçu", "Master — received")), ("AGE", ("Agence — visa", "Agency — endorsement"))],
               build_service_note, family="SVC", answers=("REQ:MARINE_SERVICES", "REQ:WASTE_COLLECTION", "M8:8.06", "MA2:A2.03"),
               purpose=("Le bon de prestation signé par le capitaine pour chaque service rendu (pilotage, remorquage, lamanage, eau, provisions, vedette).",
                        "The service note signed by the master for each service rendered (pilotage, towage, mooring, water, provisions, launch).")))
