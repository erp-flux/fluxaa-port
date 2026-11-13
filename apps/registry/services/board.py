"""The port call board (FLX-CDC-002 v1.4 EXG-Q-04, v1.5 EXG-R-07): every call of the port that is declared and
not yet closed, for consultation by the agencies, the other parties of the port and the interested parties — laid
out as the port's own placement conference: alongside, in the roads, expected, departed; berth, vessel, call
number, agency, nature of the cargo and tonnage (when the port shows them), ETA, FAL forms and manifest filed,
arrival in the roads, ETB, ETD. Nothing else of another agency's call is shown: no parties, no tasks, no documents,
no measurements — and no way in: a call is opened only by the organisations that hold a role on it (EXG-Q-03).

The berth occupation plan reads the same calls per berth over a period, as the terminals' own occupation sheets:
vessel, operation, trader, product, quantity, ETA / ETB / ETD, and whether the operation is completed, ongoing
or expected.
"""
from __future__ import annotations

import csv
import io
from datetime import timedelta

from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from ..models import ACTIVE_STATUSES, CallStatus, CargoKind, PortCall
from .rights import call_queryset_for_user

GROUPS = (
    ("alongside", (CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.OPS_COMPLETE)),
    ("roads", (CallStatus.APPROACHING, CallStatus.SHIFTING)),
    ("expected", (CallStatus.DECLARED, CallStatus.ACCEPTED, CallStatus.PLANNED)),
    ("departed", (CallStatus.DEPARTED, CallStatus.CLOSED)),
)
FAL_TYPES = ("FAL_FORMS", "FAL_PROOF")
MANIFEST_TYPES = ("CARGO_MANIFEST", "EXPORT_MANIFEST", "BAY_PLAN")


def group_labels() -> dict[str, str]:
    return {"alongside": _("Alongside"), "roads": _("In the roads (arrived, at anchorage, shifting)"),
            "expected": _("Expected"), "departed": _("Departed (24 h)")}


def calls(port, now=None):
    """Declared calls of the port: the active ones, and those departed or closed within the last 24 hours."""
    now = now or timezone.now()
    since = now - timedelta(hours=24)
    return (PortCall.objects.filter(port=port)
            .filter(Q(status__in=ACTIVE_STATUSES) | Q(status__in=[CallStatus.DEPARTED, CallStatus.CLOSED], atd__gte=since))
            .select_related("vessel", "berth", "requested_berth", "agency", "linked_call", "linked_call__vessel").order_by("eta"))


def _area(call) -> tuple[str, object]:
    stage = call.stages.filter(status="CURRENT").select_related("berth").first()
    berth = call.berth or call.requested_berth or (stage.berth if stage is not None else None)
    area = berth.code if berth is not None else (stage.get_berth_kind_display() if stage is not None else call.get_requested_berth_kind_display())
    return area, berth


def _documents_filed(call) -> tuple[bool, bool]:
    codes = set(call.documents.exclude(status="CANCELLED").values_list("type__code", flat=True))
    return bool(codes & set(FAL_TYPES)), bool(codes & set(MANIFEST_TYPES))


# compact unit labels for the tables of the conference and the occupation plan (translated at render time)
UNIT_SHORT = {"MT": "MT", "M3": "m³", "BBL": "bbl", "TEU": gettext_lazy("TEU"), "BOX": gettext_lazy("boxes"),
              "MOVES": gettext_lazy("moves"), "UNIT": gettext_lazy("units"), "M3B": "m³", "PAX": gettext_lazy("pax")}


def quantity_label(call) -> str:
    if call.quantity is None:
        if call.planned_pump_hours:
            return f"{call.planned_pump_hours:g} h"
        return ""
    unit = UNIT_SHORT.get(call.quantity_unit, call.quantity_unit)
    value = f"{call.quantity:,.0f}".replace(",", " ") if call.quantity == call.quantity.to_integral() else f"{call.quantity:,.3f}".replace(",", " ")
    return f"{value} {unit}"


def rows(port, user, now=None) -> list[dict]:
    """One row per call with the board's fields only; `link` says whether the viewer may open the call."""
    mine = set(call_queryset_for_user(user).values_list("pk", flat=True)) if user is not None else set()
    show_cargo = port.board_shows_cargo
    result = []
    for call in calls(port, now):
        area, berth = _area(call)
        fal, manifest = _documents_filed(call)
        operations = [code for code in call.template_codes if code not in ("M0",)]
        result.append({
            "call": call, "link": call.pk in mine, "group": _group(call),
            "vessel": call.vessel.name, "imo": call.vessel.imo, "flag": call.vessel.flag,
            "vessel_kind": call.vessel.get_vessel_kind_display(),
            "agency": str(call.agency), "area": area, "berth_kind": call.get_requested_berth_kind_display(),
            "operations": operations, "status": call.get_status_display(), "status_code": call.status,
            "cargo_kind": CargoKind(call.cargo_kind).label if call.cargo_kind else "",
            "cargo": (call.product or CargoKind(call.cargo_kind).label) if show_cargo else "",
            "quantity": quantity_label(call) if show_cargo else "",
            "fal": fal, "manifest": manifest,
            "sts_partner": call.linked_call.vessel.name if call.is_sts and call.linked_call_id else "",
            "eta": call.eta, "etb": call.etb, "etd": call.etd, "ata": call.ata, "atb": call.atb, "atd": call.atd,
            "valid_until": call.valid_until,
        })
    return result


def _group(call) -> str:
    if call.status == CallStatus.APPROACHING and call.ata is None:
        return "expected"
    for key, statuses in GROUPS:
        if call.status in statuses:
            return key
    return "expected"


def grouped(port, user, now=None) -> list[tuple[str, str, list[dict]]]:
    labels = group_labels()
    all_rows = rows(port, user, now)
    return [(key, labels[key], [r for r in all_rows if r["group"] == key]) for key, _statuses in GROUPS]


def to_csv(port, user, now=None) -> str:
    """The placement conference as a CSV sheet (semicolon-separated, the spreadsheets of the region)."""
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Groupe / Group", "Poste / Berth", "Navire / Vessel", "IMO", "N° escale / Call", "Consignataire / Agent",
                     "Nature de la cargaison / Cargo", "Tonnage / Quantity", "ETA (UTC)", "FAL", "Manifeste / Manifest",
                     "Arrivée rade / Arrived (UTC)", "ETB / ATB (UTC)", "ETD / ATD (UTC)", "État / State"])
    for key, label, group_rows in grouped(port, user, now):
        for r in group_rows:
            writer.writerow([label, r["area"], r["vessel"], r["imo"], r["call"].reference, r["agency"], r["cargo"], r["quantity"],
                             _f(r["eta"]), "OUI/YES" if r["fal"] else "NON/NO", "OUI/YES" if r["manifest"] else "NON/NO",
                             _f(r["ata"]), _f(r["atb"] or r["etb"]), _f(r["atd"] or r["etd"]), r["status"]])
    return out.getvalue()


def _f(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


# ------------------------------------------------------------------------------------------ berth occupation plan
def occupation(port, user, start, end) -> list[dict]:
    """The berth occupation plan of a period: every call of the port whose stay overlaps the period, per berth or
    area, with the operation, the trader, the product and the quantity (when the port shows them), ETA / ETB / ETD
    and the state of the operation."""
    mine = set(call_queryset_for_user(user).values_list("pk", flat=True)) if user is not None else set()
    show_cargo = port.board_shows_cargo
    qs = (PortCall.objects.filter(port=port).exclude(status__in=[CallStatus.CANCELLED, CallStatus.REJECTED, CallStatus.EXPIRED, CallStatus.DRAFT])
          .filter(Q(eta__lte=end) & (Q(atd__gte=start) | Q(atd__isnull=True, etd__gte=start) | Q(atd__isnull=True, etd__isnull=True, eta__gte=start)))
          .select_related("vessel", "berth", "requested_berth", "agency").order_by("eta"))
    plan = []
    for call in qs:
        area, berth = _area(call)
        trader = call.parties.filter(role="COM", revoked_at__isnull=True).select_related("organization").first()
        if call.status in (CallStatus.DEPARTED, CallStatus.CLOSED, CallStatus.ARCHIVED):
            state = "completed"
        elif call.status in (CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.OPS_COMPLETE, CallStatus.SHIFTING, CallStatus.APPROACHING):
            state = "ongoing"
        else:
            state = "expected"
        operations = [code for code in call.template_codes if code != "M0"]
        plan.append({"call": call, "link": call.pk in mine, "area": area, "berth": berth, "vessel": call.vessel.name,
                     "agency": str(call.agency), "operations": operations, "trader": trader.organization.name if trader and show_cargo else "",
                     "cargo": (call.product or CargoKind(call.cargo_kind).label) if show_cargo else "",
                     "quantity": quantity_label(call) if show_cargo else "", "state": state,
                     "eta": call.ata or call.eta, "etb": call.atb or call.etb, "etd": call.atd or call.etd,
                     "actual_eta": call.ata is not None, "actual_etb": call.atb is not None, "actual_etd": call.atd is not None})
    plan.sort(key=lambda r: (r["area"], r["eta"]))
    return plan


def occupation_csv(port, user, start, end) -> str:
    out = io.StringIO()
    writer = csv.writer(out, delimiter=";")
    writer.writerow(["Poste / Berth", "N°", "Navire / Vessel", "Opération / Operation", "Consignataire / Agent", "Mandant / Trader",
                     "Produit / Product", "Quantité / Quantity", "ETA (UTC)", "ETB (UTC)", "ETD (UTC)", "État / State"])
    for r in occupation(port, user, start, end):
        writer.writerow([r["area"], r["call"].reference, r["vessel"], ", ".join(r["operations"]), r["agency"], r["trader"], r["cargo"],
                         r["quantity"], _f(r["eta"]), _f(r["etb"]), _f(r["etd"]), r["state"]])
    return out.getvalue()
