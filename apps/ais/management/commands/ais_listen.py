"""Feed the AIS board of a port from a receiver or a stream provider (docs/DEPLOIEMENT.md §15).

    manage.py ais_listen --port TGLFW --udp 0.0.0.0:10110        # NMEA sentences from a local receiver (AIS-catcher, rtl_ais…)
    manage.py ais_listen --port TGLFW --tcp 192.168.1.20:5000    # NMEA sentences from a TCP server
    manage.py ais_listen --port TGLFW --aisstream                # aisstream.io, key in FLUXAA_AISSTREAM_KEY, box of the port

Reports are written in batches every few seconds. The command runs until it is stopped and reconnects on
error; a corrupt sentence or message is skipped, never fatal.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.ais import nmea, services
from apps.core.models import Port

log = logging.getLogger("fluxaa.ais")
AISSTREAM_URL = "wss://stream.aisstream.io/v0/stream"


def _host_port(value: str) -> tuple[str, int]:
    host, _sep, port = value.rpartition(":")
    if not host or not port.isdigit():
        raise CommandError(f"expected host:port, got {value!r}")
    return host, int(port)


class Command(BaseCommand):
    help = "Listen to an AIS source and store its position reports for one port."

    def add_arguments(self, parser):
        parser.add_argument("--port", required=True, help="UN/LOCODE of the port (SLFNA, TGLFW…)")
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument("--udp", metavar="HOST:PORT", help="receive NMEA sentences on this UDP address")
        source.add_argument("--tcp", metavar="HOST:PORT", help="connect to a TCP server of NMEA sentences")
        source.add_argument("--aisstream", action="store_true", help="subscribe to aisstream.io for the port's box")
        parser.add_argument("--batch-seconds", type=int, default=5, help="write the buffered reports every N seconds")
        parser.add_argument("--max-seconds", type=int, default=0, help="stop after N seconds (tests); 0 = forever")

    def handle(self, *args, **options):
        port = Port.objects.filter(code=options["port"]).first()
        if port is None:
            raise CommandError(f"Unknown port {options['port']}")
        self.port = port
        self.batch_seconds = max(1, options["batch_seconds"])
        self.deadline = time.monotonic() + options["max_seconds"] if options["max_seconds"] else None
        self.buffer: list[dict] = []
        self.last_flush = time.monotonic()
        if options["udp"]:
            self._udp(*_host_port(options["udp"]))
        elif options["tcp"]:
            self._tcp(*_host_port(options["tcp"]))
        else:
            if not port.has_map:
                raise CommandError("aisstream needs the port's map box (PARAMETRAGE.md §2) to subscribe to an area.")
            key = os.environ.get("FLUXAA_AISSTREAM_KEY", "")
            if not key:
                raise CommandError("FLUXAA_AISSTREAM_KEY is not set.")
            asyncio.run(self._aisstream(key))
        self._flush(force=True)

    # ------------------------------------------------------------------------------------------ buffering
    def _add(self, reports: list[dict]) -> None:
        self.buffer.extend(reports)
        self._flush()

    def _flush(self, force: bool = False) -> None:
        if not self.buffer or (not force and time.monotonic() - self.last_flush < self.batch_seconds):
            return
        close_old_connections()
        counts = services.ingest(self.port, self.buffer, source=self.source)
        log.info("ais %s: %s", self.port.code, counts)
        self.buffer = []
        self.last_flush = time.monotonic()

    def _expired(self) -> bool:
        return self.deadline is not None and time.monotonic() >= self.deadline

    # ------------------------------------------------------------------------------------------- NMEA
    def _udp(self, host: str, udp_port: int) -> None:
        self.source = "nmea-udp"
        from pyais.stream import UDPReceiver

        self.stdout.write(f"Listening for NMEA on udp://{host}:{udp_port} → {self.port.code}")
        with UDPReceiver(host, udp_port) as stream:
            stream._fobj.settimeout(1)  # pyais keeps the socket private; the timeout lets the batch flush when quiet
            while not self._expired():
                try:
                    for message in self._messages(stream):
                        report = nmea.report_from_message(message)
                        if report:
                            self._add([report])
                        if self._expired():
                            break
                except (socket.timeout, TimeoutError):
                    self._flush()
                    continue

    def _tcp(self, host: str, tcp_port: int) -> None:
        self.source = "nmea-tcp"
        from pyais.stream import TCPConnection

        while not self._expired():
            try:
                self.stdout.write(f"Connecting to tcp://{host}:{tcp_port} → {self.port.code}")
                with TCPConnection(host, tcp_port) as stream:
                    for message in self._messages(stream):
                        report = nmea.report_from_message(message)
                        if report:
                            self._add([report])
                        if self._expired():
                            return
            except OSError as exc:
                log.warning("ais tcp %s: %s — retrying in 10 s", self.port.code, exc)
                self._flush(force=True)
                time.sleep(10)

    @staticmethod
    def _messages(stream):
        """pyais yields NMEA fragments; ``decode`` assembles multipart messages."""
        for sentence in stream:
            try:
                yield sentence.decode()
            except Exception:  # noqa: BLE001 — corrupt or unsupported sentence
                continue

    # --------------------------------------------------------------------------------------- aisstream
    async def _aisstream(self, key: str) -> None:
        import websockets

        self.source = "aisstream"
        box = [[[float(self.port.map_lat_min), float(self.port.map_lon_min)],
                [float(self.port.map_lat_max), float(self.port.map_lon_max)]]]
        subscription = json.dumps({"APIKey": key, "BoundingBoxes": box,
                                   "FilterMessageTypes": ["PositionReport", "ShipStaticData"]})
        while not self._expired():
            try:
                async with websockets.connect(AISSTREAM_URL) as socket_:
                    await socket_.send(subscription)
                    self.stdout.write(f"Subscribed to aisstream for {self.port.code} {box}")
                    async for frame in socket_:
                        report = self.aisstream_report(json.loads(frame))
                        if report:
                            self._add([report])
                        if self._expired():
                            return
            except Exception as exc:  # noqa: BLE001 — network hiccup: reconnect
                log.warning("aisstream %s: %s — reconnecting in 10 s", self.port.code, exc)
                self._flush(force=True)
                await asyncio.sleep(10)

    @staticmethod
    def aisstream_report(frame: dict) -> dict | None:
        """One aisstream.io frame → one report (format of https://aisstream.io/documentation)."""
        meta = frame.get("MetaData") or {}
        kind = frame.get("MessageType")
        body = (frame.get("Message") or {}).get(kind) or {}
        mmsi = meta.get("MMSI")
        if not mmsi:
            return None
        observed = parse_datetime(str(meta.get("time_utc", "")).replace(" UTC", "").split(".")[0] + "+00:00")
        report = {"mmsi": str(mmsi), "observed_at": observed or timezone.now(),
                  "name": (meta.get("ShipName") or "").strip()}
        if kind == "PositionReport":
            report.update({"lat": meta.get("latitude"), "lon": meta.get("longitude"), "speed_kn": body.get("Sog"),
                           "course_deg": body.get("Cog"), "heading_deg": body.get("TrueHeading"),
                           "nav_status": body.get("NavigationalStatus")})
            if report["heading_deg"] == 511:
                report["heading_deg"] = None
        elif kind == "ShipStaticData":
            report.update({"imo": body.get("ImoNumber") or "", "call_sign": (body.get("CallSign") or "").strip(),
                           "destination": (body.get("Destination") or "").strip(),
                           "draught_m": body.get("MaximumStaticDraught"), "ship_type": body.get("Type")})
        else:
            return None
        return report
