"""AIS board: ingestion of position reports, latest picture of the port waters, purge.

Sources (all optional, chosen by the port — docs/DEPLOIEMENT.md §15): a local receiver sending NMEA sentences
(``manage.py ais_listen --udp``), a stream provider (``--aisstream``), or any system posting JSON reports to
``POST /api/v1/ais/positions/`` with an integration account of scope ``ais``.

The board never writes a milestone: positions corroborate declared facts (EF-3.6) and inform the people who
watch the port; the registry stays contradictory and human.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.formats import number_format
from django.utils.translation import gettext_lazy as _

from apps.core.models import Berth, Port
from apps.registry.models import ACTIVE_STATUSES, CallStatus, PortCall, Vessel

from .models import VesselPosition, VesselStatic

NAV_STATUS = {
    0: _("Under way using engine"), 1: _("At anchor"), 2: _("Not under command"), 3: _("Restricted manoeuvrability"),
    4: _("Constrained by her draught"), 5: _("Moored"), 6: _("Aground"), 7: _("Engaged in fishing"),
    8: _("Under way sailing"), 11: _("Towing astern"), 12: _("Pushing ahead"), 14: _("AIS-SART"), 15: _("Undefined"),
}
MAX_AGE_HOURS = 24  # a vessel silent for longer leaves the board (it stays in the history until the purge)
BOARD_WIDTH = 1000  # SVG units; the height follows the box so that distances keep their proportions


class ReportError(ValueError):
    """A report that cannot be stored (missing MMSI, position out of range…)."""


# ------------------------------------------------------------------------------------------- parsing helpers
def _decimal(value, digits: int):
    if value in (None, ""):
        return None
    try:
        return round(Decimal(str(value)), digits)
    except (InvalidOperation, ValueError):
        return None


def _when(value) -> datetime:
    if value in (None, ""):
        return timezone.now()
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = parse_datetime(str(value))
        if parsed is None:
            raise ReportError(f"invalid time: {value!r}")
    if timezone.is_naive(parsed):
        parsed = timezone.make_aware(parsed, timezone.utc)
    return parsed


def normalise(report: dict) -> dict:
    """A report as any source gives it → the fields stored. Position fields are required unless the report is
    static-only (``imo``, ``name``… without ``lat``/``lon``)."""
    mmsi = str(report.get("mmsi") or "").strip()
    if not mmsi.isdigit() or not 7 <= len(mmsi) <= 9:
        raise ReportError("mmsi must be 7 to 9 digits")
    out = {"mmsi": mmsi, "observed_at": _when(report.get("observed_at") or report.get("time"))}
    lat, lon = report.get("lat", report.get("latitude")), report.get("lon", report.get("longitude"))
    if lat not in (None, "") or lon not in (None, ""):
        lat, lon = _decimal(lat, 6), _decimal(lon, 6)
        if lat is None or lon is None or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            raise ReportError("latitude/longitude out of range")
        speed = _decimal(report.get("speed_kn", report.get("sog")), 1)
        course = _decimal(report.get("course_deg", report.get("cog")), 1)
        heading = report.get("heading_deg", report.get("heading"))
        status = report.get("nav_status", report.get("status"))
        out.update({
            "latitude": lat, "longitude": lon,
            "speed_kn": speed if speed is not None and 0 <= speed <= 102 else None,
            "course_deg": course if course is not None and 0 <= course < 360 else None,
            "heading_deg": int(heading) if heading not in (None, "") and 0 <= int(heading) < 360 else None,
            "nav_status": int(status) if status not in (None, "") and 0 <= int(status) <= 15 else None,
        })
    static = {}
    for key, length in (("imo", 7), ("name", 120), ("call_sign", 20), ("destination", 40)):
        value = report.get(key)
        if value not in (None, ""):
            static[key] = str(value).strip()[:length]
    if static.get("imo") and not static["imo"].isdigit():
        static.pop("imo")
    if report.get("ship_type") not in (None, ""):
        static["ship_type"] = int(report["ship_type"])
    draught = _decimal(report.get("draught_m", report.get("draught")), 1)
    if draught is not None and 0 < draught < 30:
        static["draught_m"] = draught
    out["static"] = static
    return out


# -------------------------------------------------------------------------------------------- ingestion
def ingest(port: Port, reports: list[dict], *, source: str) -> dict:
    """Store what each report carries; a report already stored (same vessel, same time) is ignored.
    Returns the counts; malformed reports are counted, never raised, so a stream never stops on one bad line."""
    stored = statics = rejected = duplicates = 0
    for raw in reports:
        try:
            report = normalise(raw)
        except (ReportError, TypeError, ValueError):
            rejected += 1
            continue
        if report["static"]:
            with transaction.atomic():
                row, created = VesselStatic.objects.select_for_update().get_or_create(
                    port=port, mmsi=report["mmsi"], defaults={**report["static"], "updated_at": report["observed_at"]})
                if not created and report["observed_at"] >= row.updated_at:
                    for key, value in report["static"].items():
                        setattr(row, key, value)
                    row.updated_at = report["observed_at"]
                    row.save()
            statics += 1
        if "latitude" in report:
            try:
                with transaction.atomic():
                    VesselPosition.objects.create(
                        port=port, mmsi=report["mmsi"], latitude=report["latitude"], longitude=report["longitude"],
                        speed_kn=report["speed_kn"], course_deg=report["course_deg"], heading_deg=report["heading_deg"],
                        nav_status=report["nav_status"], observed_at=report["observed_at"], source=source[:40])
                stored += 1
            except IntegrityError:
                duplicates += 1
    return {"stored": stored, "static": statics, "duplicates": duplicates, "rejected": rejected}


def purge(now=None) -> int:
    """Drop the reports older than each port's retention (scheduler, once a day is plenty)."""
    now = now or timezone.now()
    deleted = 0
    for port in Port.objects.all():
        limit = now - timedelta(days=port.ais_retention_days)
        count, _detail = VesselPosition.objects.filter(port=port, observed_at__lt=limit).delete()
        deleted += count
    return deleted


# ------------------------------------------------------------------------------------------------ board
def _box(port: Port) -> dict | None:
    if not port.has_map:
        return None
    lat_min, lat_max = float(port.map_lat_min), float(port.map_lat_max)
    lon_min, lon_max = float(port.map_lon_min), float(port.map_lon_max)
    stretch = math.cos(math.radians((lat_min + lat_max) / 2)) or 1e-6  # a degree of longitude shrinks with latitude
    height = BOARD_WIDTH * (lat_max - lat_min) / ((lon_max - lon_min) * stretch)
    height = max(240.0, min(height, 1600.0))
    return {"lat_min": lat_min, "lat_max": lat_max, "lon_min": lon_min, "lon_max": lon_max,
            "width": BOARD_WIDTH, "height": round(height, 1),
            "metres_per_unit": (lon_max - lon_min) * stretch * 111_320 / BOARD_WIDTH}


def project(box: dict, lat: float, lon: float) -> tuple[float, float, bool]:
    """Board coordinates of a point; the flag says whether it lies inside the box."""
    x = (lon - box["lon_min"]) / (box["lon_max"] - box["lon_min"]) * box["width"]
    y = (box["lat_max"] - lat) / (box["lat_max"] - box["lat_min"]) * box["height"]
    inside = 0 <= x <= box["width"] and 0 <= y <= box["height"]
    return round(x, 1), round(y, 1), inside


def _call_class(call: PortCall | None) -> str:
    if call is None:
        return "none"
    if call.status in (CallStatus.AT_BERTH, CallStatus.IN_OPERATION, CallStatus.OPS_COMPLETE, CallStatus.SHIFTING):
        return "operation"
    if call.status == CallStatus.DEPARTED:
        return "departed"
    return "expected"


def latest_reports(port: Port, *, now=None):
    now = now or timezone.now()
    since = now - timedelta(hours=MAX_AGE_HOURS)
    return (VesselPosition.objects.filter(port=port, observed_at__gte=since)
            .order_by("mmsi", "-observed_at").distinct("mmsi"))


def board(port: Port, *, visible_calls=None, now=None) -> dict:
    """Everything the board shows: the box, the berths and areas, one entry per vessel heard in the last 24 h.
    *visible_calls* restricts the call shown next to a vessel to those the viewer may open."""
    now = now or timezone.now()
    box = _box(port)
    reports = list(latest_reports(port, now=now))
    statics = {s.mmsi: s for s in VesselStatic.objects.filter(port=port, mmsi__in=[r.mmsi for r in reports])}
    mmsis = {r.mmsi for r in reports}
    imos = {s.imo for s in statics.values() if s.imo}
    vessels = {}
    for vessel in Vessel.objects.filter(port=port).filter(mmsi__in=mmsis) | Vessel.objects.filter(port=port, imo__in=imos):
        if vessel.mmsi in mmsis:
            vessels[vessel.mmsi] = vessel
        else:
            for mmsi, static in statics.items():
                if static.imo == vessel.imo:
                    vessels.setdefault(mmsi, vessel)
    calls = {}
    if vessels:
        call_qs = PortCall.objects.filter(port=port, vessel__in=list(vessels.values()))
        call_qs = call_qs.filter(status__in=ACTIVE_STATUSES) | call_qs.filter(status=CallStatus.DEPARTED,
                                                                                 atd__gte=now - timedelta(hours=24))
        if visible_calls is not None:
            call_qs = call_qs.filter(pk__in=visible_calls.values("pk"))
        for call in call_qs.order_by("-eta").select_related("vessel", "berth"):
            calls.setdefault(call.vessel_id, call)
    entries = []
    for report in reports:
        static = statics.get(report.mmsi)
        vessel = vessels.get(report.mmsi)
        call = calls.get(vessel.pk) if vessel else None
        entry = {
            "mmsi": report.mmsi, "name": (vessel.name if vessel else "") or (static.name if static else "") or report.mmsi,
            "imo": (vessel.imo if vessel else "") or (static.imo if static else ""),
            "vessel": vessel, "call": call, "klass": _call_class(call),
            "lat": float(report.latitude), "lon": float(report.longitude), "speed_kn": report.speed_kn,
            "course_deg": report.course_deg, "heading_deg": report.heading_deg, "nav_status": report.nav_status,
            "nav_status_label": NAV_STATUS.get(report.nav_status, ""), "observed_at": report.observed_at,
            "age_minutes": int((now - report.observed_at).total_seconds() // 60),
            "destination": static.destination if static else "", "draught_m": static.draught_m if static else None,
            "rotation": report.heading_deg if report.heading_deg is not None else (
                float(report.course_deg) if report.course_deg is not None else 0),
        }
        entry["position_text"] = position_text(entry["lat"], entry["lon"])
        if box is not None:
            entry["x"], entry["y"], entry["inside"] = project(box, entry["lat"], entry["lon"])
        entries.append(entry)
    entries.sort(key=lambda e: ({"operation": 0, "expected": 1, "departed": 2, "none": 3}[e["klass"]], e["name"]))
    berths = []
    for berth in Berth.objects.filter(port=port, is_active=True).order_by("kind", "code"):
        if box is None or berth.latitude is None or berth.longitude is None:
            continue
        x, y, inside = project(box, float(berth.latitude), float(berth.longitude))
        if inside:
            radius = (berth.radius_m or 0) / box["metres_per_unit"] if berth.radius_m else 0
            berths.append({"berth": berth, "x": x, "y": y, "r": round(max(radius, 0), 1),
                           "label_y": round(y - max(radius, 7) - 6, 1)})
    if box is not None:
        _place_labels([e for e in entries if e.get("inside")])
    data = {"port": port, "box": box, "berths": berths, "vessels": entries, "generated_at": now,
            "on_board": sum(1 for e in entries if e.get("inside")),
            "with_call": sum(1 for e in entries if e["call"] is not None)}
    data["discrepancies"] = discrepancies(data)
    return data


FRESH_MINUTES = 120   # a report younger than this describes the present
SILENT_HOURS = 6      # a vessel of a call in progress unheard for longer is worth a look
MOORED_KN = 1.0       # below this speed a vessel is not under way


def discrepancies(data: dict) -> list[dict]:
    """Where the AIS picture and the registry disagree. Each line is a question for the harbour master and
    the agency, never a correction: the registry says what its emitters declared (EF-3.6)."""
    found = []
    box = data["box"]
    for entry in data["vessels"]:
        call = entry["call"]
        if call is None:
            continue
        fresh = entry["age_minutes"] <= FRESH_MINUTES
        speed = float(entry["speed_kn"]) if entry["speed_kn"] is not None else None
        slow = speed is None or speed < MOORED_KN
        inside = entry.get("inside") if box is not None else None
        klass = entry["klass"]
        status = call.get_status_display()
        if klass == "expected" and inside and fresh and call.ata is None:
            found.append({"kind": "arrived_undeclared", "call": call, "vessel": entry["name"],
                          "text": _("%(v)s is heard in the port waters (%(s)s kn) while call %(r)s has no arrival recorded.")
                          % {"v": entry["name"], "s": "—" if speed is None else number_format(speed, 1), "r": call.reference}})
        elif klass == "operation" and inside is False and fresh:
            found.append({"kind": "left_undeclared", "call": call, "vessel": entry["name"],
                          "text": _("%(v)s is heard outside the port waters while call %(r)s is “%(st)s”.")
                          % {"v": entry["name"], "r": call.reference, "st": status}})
        elif klass == "operation" and entry["age_minutes"] >= SILENT_HOURS * 60:
            found.append({"kind": "silent", "call": call, "vessel": entry["name"],
                          "text": _("No position from %(v)s for %(h)d h while call %(r)s is “%(st)s”.")
                          % {"v": entry["name"], "h": entry["age_minutes"] // 60, "r": call.reference, "st": status}})
        elif klass == "departed" and inside and fresh and slow and call.atd is not None:
            hours = (data["generated_at"] - call.atd).total_seconds() / 3600
            if hours >= 1:
                found.append({"kind": "still_here", "call": call, "vessel": entry["name"],
                              "text": _("%(v)s is still heard moored in the port waters %(h).0f h after the departure recorded on call %(r)s.")
                              % {"v": entry["name"], "h": hours, "r": call.reference}})
    return found


def position_text(lat: float, lon: float) -> str:
    """Degrees and decimal minutes, as read on the bridge: 06°07.68' N 001°17.22' E."""
    def part(value: float, pos: str, neg: str, width: int) -> str:
        hemisphere = pos if value >= 0 else neg
        value = abs(value)
        degrees = int(value)
        minutes = (value - degrees) * 60
        if minutes >= 59.995:
            degrees, minutes = degrees + 1, 0.0
        return f"{degrees:0{width}d}°{minutes:05.2f}' {hemisphere}"

    return f"{part(lat, 'N', 'S', 2)} {part(lon, 'E', 'W', 3)}"


LABEL_HEIGHT = 15.0
LABEL_CHAR = 7.2  # average advance of the 13 px label font, in board units


def _place_labels(entries: list[dict]) -> None:
    """Vessels moored side by side would print their names on top of each other: the label of a vessel whose
    name box overlaps an already placed one is pushed below it (the mark itself never moves)."""
    placed: list[tuple[float, float, float, float]] = []
    for entry in sorted(entries, key=lambda e: (e["y"], e["x"])):
        width = max(len(entry["name"]), 3) * LABEL_CHAR
        x0, dy = entry["x"] + 11, 4.0
        for _attempt in range(6):
            y0 = entry["y"] + dy - 12
            box = (x0, y0, x0 + width, y0 + LABEL_HEIGHT)
            if not any(box[0] < p[2] and box[2] > p[0] and box[1] < p[3] and box[3] > p[1] for p in placed):
                break
            dy += LABEL_HEIGHT
        placed.append(box)
        entry["label_dy"] = round(dy, 1)


def positions_json(data: dict) -> dict:
    """The board for the API: no model instances, ISO times, call references only."""
    return {
        "port": data["port"].code, "generated_at": data["generated_at"].isoformat(),
        "box": data["box"],
        "vessels": [{
            "mmsi": e["mmsi"], "imo": e["imo"], "name": e["name"], "lat": e["lat"], "lon": e["lon"],
            "speed_kn": float(e["speed_kn"]) if e["speed_kn"] is not None else None,
            "course_deg": float(e["course_deg"]) if e["course_deg"] is not None else None,
            "heading_deg": e["heading_deg"], "nav_status": e["nav_status"], "observed_at": e["observed_at"].isoformat(),
            "call": e["call"].reference if e["call"] else None, "call_status": e["call"].status if e["call"] else None,
            "inside": e.get("inside"),
        } for e in data["vessels"]],
        "discrepancies": [{"kind": d["kind"], "call": d["call"].reference, "vessel": d["vessel"], "text": str(d["text"])}
                          for d in data["discrepancies"]],
    }
