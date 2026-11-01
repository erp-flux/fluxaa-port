"""NMEA 0183 AIS sentences (!AIVDM / !AIVDO) → reports for ``services.ingest``.

Decoding relies on pyais (MIT). Message types used: 1, 2, 3, 18, 19, 27 (positions), 5 and 24 (static data).
Anything else is ignored. Values that AIS marks "not available" (heading 511, course 360, speed 102.3,
latitude 91, longitude 181) are dropped, never stored as if they were measurements.
"""
from __future__ import annotations

from datetime import datetime

from django.utils import timezone

POSITION_TYPES = {1, 2, 3, 18, 19, 27}
STATIC_TYPES = {5, 24}


def _enum_value(value):
    return getattr(value, "value", value)


def report_from_message(message, *, observed_at: datetime | None = None) -> dict | None:
    """A decoded pyais message → one report dict, or None when the message carries nothing we store."""
    msg_type = int(_enum_value(getattr(message, "msg_type", 0)) or 0)
    mmsi = str(getattr(message, "mmsi", "") or "")
    if not mmsi:
        return None
    report = {"mmsi": mmsi, "observed_at": observed_at or timezone.now()}
    if msg_type in POSITION_TYPES:
        lat, lon = getattr(message, "lat", None), getattr(message, "lon", None)
        if lat is None or lon is None or abs(lat) > 90 or abs(lon) > 180:
            return None
        report.update({"lat": lat, "lon": lon})
        speed = getattr(message, "speed", None)
        course = getattr(message, "course", None)
        heading = getattr(message, "heading", None)
        status = getattr(message, "status", None)
        report["speed_kn"] = speed if speed is not None and speed < 102.3 else None
        report["course_deg"] = course if course is not None and course < 360 else None
        report["heading_deg"] = heading if heading is not None and heading < 360 else None
        status = _enum_value(status)
        report["nav_status"] = int(status) if status is not None and 0 <= int(status) <= 15 else None
        if msg_type == 19:
            report["name"] = (getattr(message, "shipname", "") or "").strip("@ ")
            report["ship_type"] = _enum_value(getattr(message, "ship_type", None))
        return report
    if msg_type in STATIC_TYPES:
        name = (getattr(message, "shipname", "") or "").strip("@ ")
        call_sign = (getattr(message, "callsign", "") or "").strip("@ ")
        imo = getattr(message, "imo", None)
        if name:
            report["name"] = name
        if call_sign:
            report["call_sign"] = call_sign
        if imo:
            report["imo"] = str(imo)
        if getattr(message, "ship_type", None) is not None:
            report["ship_type"] = _enum_value(message.ship_type)
        if msg_type == 5:
            report["destination"] = (getattr(message, "destination", "") or "").strip("@ ")
            report["draught_m"] = getattr(message, "draught", None)
        return report if len(report) > 2 else None
    return None


def decode_sentences(sentences: list[bytes | str], *, observed_at: datetime | None = None) -> list[dict]:
    """Decode complete sentences (single-fragment, or the fragments of one message given together)."""
    from pyais import decode

    raw = [s.encode() if isinstance(s, str) else s for s in sentences]
    raw = [s.strip() for s in raw if s.strip().startswith((b"!AIVDM", b"!AIVDO"))]
    reports = []
    for sentence in raw:
        try:
            message = decode(sentence)
        except Exception:  # noqa: BLE001 — a corrupt sentence never stops the stream
            continue
        report = report_from_message(message, observed_at=observed_at)
        if report is not None:
            reports.append(report)
    return reports
