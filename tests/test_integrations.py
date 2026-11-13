"""The adapters of docs/INTEGRATIONS.md: records of a maritime data provider (Kpler / MarineTraffic shape) become
the position reports the AIS board ingests, and nothing else — no milestone, no decision."""
from __future__ import annotations

import importlib.util
import pathlib

import pytest

from apps.ais import services as ais_svc

SPEC = importlib.util.spec_from_file_location("kpler_adapter", pathlib.Path(__file__).resolve().parent.parent / "scripts" / "kpler_marinetraffic_adapter.py")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)

SAMPLE = [
    # the legacy MarineTraffic shape (capitals, speed and draught in tenths, UTC timestamp)
    {"MMSI": "636019825", "IMO": "9999993", "SHIPNAME": "MT ATLANTIC DEMO", "LAT": "6.1234", "LON": "1.2987", "SPEED": "83",
     "COURSE": "271.5", "HEADING": "270", "STATUS": "0", "TIMESTAMP": "2026-11-13 09:21:00", "SHIPTYPE": "80",
     "DESTINATION": "LOME", "DRAUGHT": "112", "CALLSIGN": "D5AB2"},
    # a camelCase shape, epoch time, speed already in knots
    {"mmsi": 636019826, "lat": 6.10, "lon": 1.30, "sog": 0.0, "cog": 12.0, "navStatus": 5, "positionReceived": 1794568860, "name": "MT GULF DEMO"},
    # no position: ignored
    {"MMSI": "636019827", "SHIPNAME": "NO FIX"},
    # no mmsi: ignored
    {"LAT": "6.1", "LON": "1.3"},
]


def test_marinetraffic_records_become_fluxaa_position_reports():
    reports = [r for r in (adapter.to_report(rec) for rec in SAMPLE) if r]
    assert len(reports) == 2
    first = reports[0]
    assert first["mmsi"] == "636019825" and first["lat"] == 6.1234 and first["lon"] == 1.2987
    assert first["speed_kn"] == 8.3 and first["draught_m"] == 11.2 and first["heading_deg"] == 270 and first["nav_status"] == 0
    assert first["observed_at"].startswith("2026-11-13T09:21:00") and first["imo"] == "9999993" and first["ship_type"] == 80
    second = adapter.to_report(SAMPLE[1], speed_scale=1.0)
    assert second["speed_kn"] == 0.0 and second["nav_status"] == 5 and second["observed_at"].startswith("2026-11-13T")
    # the envelope of a provider response is understood
    assert adapter.records_from({"data": SAMPLE}) == SAMPLE and adapter.records_from(SAMPLE) == SAMPLE and adapter.records_from({"x": 1}) == []
    # what the adapter produces is what the AIS board accepts, as is
    for report in reports:
        stored = ais_svc.normalise(report)
        assert stored["mmsi"] == report["mmsi"] and "latitude" in stored


@pytest.mark.django_db
def test_the_adapter_output_is_ingested_by_the_ais_board(world):
    reports = [r for r in (adapter.to_report(rec) for rec in SAMPLE) if r]
    result = ais_svc.ingest(world.port, reports, source="test:kpler")
    assert result["stored"] == 2 and result["rejected"] == 0
    assert ais_svc.latest_reports(world.port).count() == 2
