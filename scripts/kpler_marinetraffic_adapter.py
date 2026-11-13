#!/usr/bin/env python3
"""Adapter — Kpler / MarineTraffic → tableau AIS de FLUXAA Port (étude d'intégration, docs/INTEGRATIONS.md).

Lit des positions de navires telles que les rendent les services *Vessel Positions* de l'API MarineTraffic
(une société Kpler) — un fichier JSON déjà téléchargé, ou l'API elle-même avec la clé du contrat — et les
transmet à FLUXAA par le point d'accès que le tableau AIS offre déjà à tout fournisseur
(``POST /api/v1/ais/positions/``, compte d'intégration de portée ``ais``, docs/API.md). FLUXAA ne fait rien de
plus de ces positions que de ses autres sources AIS : elles corroborent les faits déclarés, informent ceux qui
regardent le port, et n'écrivent jamais un jalon (EF-3.6).

Le script ne dépend que de la bibliothèque standard. Il n'a pas été joué contre un compte Kpler : les noms
des champs et les échelles (vitesse et tirant d'eau en dixièmes dans les services historiques de MarineTraffic)
sont ceux de la documentation publique et se vérifient sur le contrat avant la mise en service ; les options
``--speed-scale`` et ``--draught-scale`` les ajustent sans toucher au code.

Exemples ::

    # 1. voir ce qui serait transmis, depuis un extrait enregistré (JSON : liste d'objets, ou {"data": [...]})
    python scripts/kpler_marinetraffic_adapter.py --from-file extrait-marinetraffic.json --dry-run

    # 2. transmettre à FLUXAA
    python scripts/kpler_marinetraffic_adapter.py --from-file extrait.json \
        --fluxaa https://port.example --token <jeton du compte d'intégration ais>

    # 3. interroger l'API MarineTraffic (zone prédéfinie du contrat, par exemple le port) puis transmettre
    MARINETRAFFIC_API_KEY=… python scripts/kpler_marinetraffic_adapter.py \
        --marinetraffic-url "https://services.marinetraffic.com/api/exportvessels/v:8/<clé>/protocol:jsono/msgtype:extended" \
        --fluxaa https://port.example --token <jeton>
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

# MarineTraffic → FLUXAA : plusieurs orthographes acceptées pour chaque donnée (services historiques en capitales,
# services récents en camelCase) ; la première trouvée l'emporte.
FIELDS = {
    "mmsi": ("MMSI", "mmsi"),
    "imo": ("IMO", "imo"),
    "lat": ("LAT", "lat", "latitude", "LATITUDE"),
    "lon": ("LON", "lon", "longitude", "LONGITUDE"),
    "speed": ("SPEED", "speed", "sog", "SOG"),
    "course": ("COURSE", "course", "cog", "COG"),
    "heading": ("HEADING", "heading", "trueHeading"),
    "status": ("STATUS", "status", "navStatus", "navigationalStatus"),
    "time": ("TIMESTAMP", "timestamp", "time", "positionReceived", "lastPositionUpdate"),
    "name": ("SHIPNAME", "shipname", "name", "SHIP_NAME"),
    "call_sign": ("CALLSIGN", "callsign", "callSign"),
    "ship_type": ("SHIPTYPE", "shiptype", "shipType", "TYPE"),
    "destination": ("DESTINATION", "destination"),
    "draught": ("DRAUGHT", "draught", "draft", "CURRENT_DRAUGHT"),
}


def pick(record: dict, key: str):
    for name in FIELDS[key]:
        if name in record and record[name] not in (None, ""):
            return record[name]
    return None


def _number(value):
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _when(value) -> str | None:
    """Horodatage MarineTraffic (UTC, « 2026-11-13T09:21:00 » ou epoch) → ISO 8601 UTC."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or str(value).isdigit():
        return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
    text = str(value).strip().replace(" ", "T")
    if not text.endswith("Z") and "+" not in text[10:]:
        text += "+00:00"
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def to_report(record: dict, *, speed_scale: float = 0.1, draught_scale: float = 0.1) -> dict | None:
    """Un enregistrement MarineTraffic → un rapport de position tel que FLUXAA l'attend
    (``{mmsi, lat, lon, observed_at, speed_kn?, course_deg?, heading_deg?, nav_status?, imo?, name?, …}``).
    Retourne None quand l'enregistrement n'a pas de MMSI ou pas de position."""
    mmsi = pick(record, "mmsi")
    lat, lon = _number(pick(record, "lat")), _number(pick(record, "lon"))
    if mmsi in (None, "") or lat is None or lon is None:
        return None
    report = {"mmsi": str(mmsi).strip(), "lat": round(lat, 6), "lon": round(lon, 6)}
    when = _when(pick(record, "time"))
    if when:
        report["observed_at"] = when
    speed = _number(pick(record, "speed"))
    if speed is not None:
        report["speed_kn"] = round(speed * speed_scale, 1)
    course = _number(pick(record, "course"))
    if course is not None:
        report["course_deg"] = round(course, 1)
    heading = _number(pick(record, "heading"))
    if heading is not None and 0 <= heading < 360:
        report["heading_deg"] = int(heading)
    status = _number(pick(record, "status"))
    if status is not None and 0 <= status <= 15:
        report["nav_status"] = int(status)
    for key in ("imo", "name", "call_sign", "destination"):
        value = pick(record, key)
        if value not in (None, ""):
            report[key] = str(value).strip()
    ship_type = _number(pick(record, "ship_type"))
    if ship_type is not None:
        report["ship_type"] = int(ship_type)
    draught = _number(pick(record, "draught"))
    if draught is not None:
        report["draught_m"] = round(draught * draught_scale, 1)
    return report


def records_from(payload) -> list[dict]:
    """La liste d'enregistrements, quelle que soit l'enveloppe (liste nue, {"data": [...]}, {"results": [...]})."""
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("data", "results", "vessels", "DATA"):
            if isinstance(payload.get(key), list):
                return [r for r in payload[key] if isinstance(r, dict)]
    return []


def fetch_json(url: str, headers: dict | None = None, timeout: int = 60):
    request = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 — URL donnée par l'exploitant
        return json.loads(response.read().decode("utf-8"))


def post_reports(base: str, token: str, reports: list[dict], timeout: int = 60) -> dict:
    """``POST /api/v1/ais/positions/`` — au plus 5000 rapports par appel (limite de FLUXAA)."""
    totals = {"stored": 0, "static": 0, "duplicates": 0, "rejected": 0}
    for start in range(0, len(reports), 5000):
        body = json.dumps({"reports": reports[start:start + 5000]}).encode("utf-8")
        request = urllib.request.Request(base.rstrip("/") + "/api/v1/ais/positions/", data=body, method="POST",
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            result = json.loads(response.read().decode("utf-8"))
        for key in totals:
            totals[key] += int(result.get(key, 0))
    return totals


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--from-file", help="extrait JSON enregistré (liste d'enregistrements, ou {\"data\": [...]})")
    source.add_argument("--marinetraffic-url", help="URL complète du service MarineTraffic (la clé y figure, ou MARINETRAFFIC_API_KEY)")
    parser.add_argument("--fluxaa", help="adresse de FLUXAA, par exemple https://port.example")
    parser.add_argument("--token", help="jeton du compte d'intégration de portée ais (ou FLUXAA_AIS_TOKEN)")
    parser.add_argument("--speed-scale", type=float, default=0.1, help="facteur appliqué à la vitesse (0.1 : dixièmes de nœud)")
    parser.add_argument("--draught-scale", type=float, default=0.1, help="facteur appliqué au tirant d'eau (0.1 : dixièmes de mètre)")
    parser.add_argument("--dry-run", action="store_true", help="afficher les rapports sans les transmettre")
    args = parser.parse_args(argv)

    if args.from_file:
        with open(args.from_file, encoding="utf-8") as handle:
            payload = json.load(handle)
    else:
        url = args.marinetraffic_url
        key = os.environ.get("MARINETRAFFIC_API_KEY", "")
        if key and key not in url:
            url = url.replace("<clé>", key).replace("<key>", key)
        try:
            payload = fetch_json(url)
        except (urllib.error.URLError, ValueError) as exc:
            print(f"MarineTraffic injoignable ou réponse illisible : {exc}", file=sys.stderr)
            return 2
    records = records_from(payload)
    reports = [r for r in (to_report(rec, speed_scale=args.speed_scale, draught_scale=args.draught_scale) for rec in records) if r]
    print(f"{len(records)} enregistrement(s) lu(s), {len(reports)} rapport(s) de position", file=sys.stderr)
    if args.dry_run or not reports:
        json.dump(reports, sys.stdout, ensure_ascii=False, indent=1)
        print()
        return 0
    token = args.token or os.environ.get("FLUXAA_AIS_TOKEN", "")
    if not args.fluxaa or not token:
        print("--fluxaa et --token (ou FLUXAA_AIS_TOKEN) sont requis pour transmettre ; --dry-run pour seulement voir", file=sys.stderr)
        return 2
    try:
        totals = post_reports(args.fluxaa, token, reports)
    except urllib.error.HTTPError as exc:
        print(f"FLUXAA a refusé : HTTP {exc.code} — {exc.read().decode('utf-8', 'replace')[:300]}", file=sys.stderr)
        return 1
    except urllib.error.URLError as exc:
        print(f"FLUXAA injoignable : {exc}", file=sys.stderr)
        return 1
    print(json.dumps(totals))
    return 0


if __name__ == "__main__":
    sys.exit(main())
