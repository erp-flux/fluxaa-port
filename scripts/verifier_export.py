#!/usr/bin/env python3
"""Vérifie, sans la plateforme, l'intégrité d'un export de réversibilité FLUXAA Port (EF-15, ENF-4.1).

Usage :
    python3 scripts/verifier_export.py export_TGLFW.zip [--key CLE_DE_SCELLEMENT]

Contrôles :
  1. chaque fichier listé dans manifest.json a l'empreinte SHA-256 annoncée ;
  2. le journal des événements et le journal des accès forment des chaînes continues : numéros
     consécutifs, chaque entrée porte l'empreinte de la précédente, et l'empreinte de chaque entrée
     se recalcule à l'identique à partir de son contenu ;
  3. avec --key (la clé FLUXAA_SIGNING_KEY du port), le sceau du manifeste et les jetons
     d'horodatage locaux sont aussi vérifiés.

Aucune dépendance hors bibliothèque standard Python 3.10+. Code de sortie 0 si tout est intègre.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
import zipfile

GENESIS = "0" * 64


def canonical_json(data) -> str:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def sha256_hex(data: bytes | str) -> str:
    return hashlib.sha256(data.encode("utf-8") if isinstance(data, str) else data).hexdigest()


def seal(data, key: str) -> str:
    return hmac.new(key.encode("utf-8"), canonical_json(data).encode("utf-8"), hashlib.sha256).hexdigest()


def check_chain(rows: list[dict], name: str, problems: list[str]) -> int:
    previous, expected = GENESIS, 1
    for row in sorted(rows, key=lambda r: r["material"]["seq"]):
        material = row["material"]
        seq = material["seq"]
        if seq != expected:
            problems.append(f"{name} : entrée manquante avant le nº {seq} (attendu {expected})")
            return expected - 1
        if material["prev_hash"] != previous:
            problems.append(f"{name} : nº {seq} ne pointe pas vers l'entrée précédente")
        if sha256_hex(canonical_json(material)) != row["hash"]:
            problems.append(f"{name} : le contenu de l'entrée nº {seq} a été modifié")
        previous, expected = row["hash"], expected + 1
    return expected - 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("archive")
    parser.add_argument("--key", help="clé de scellement (FLUXAA_SIGNING_KEY) pour vérifier sceaux et horodatages")
    args = parser.parse_args()
    problems: list[str] = []
    with zipfile.ZipFile(args.archive) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        for name, expected in manifest.get("files", {}).items():
            try:
                content = archive.read(name)
            except KeyError:
                problems.append(f"fichier annoncé mais absent : {name}")
                continue
            if sha256_hex(content) != expected:
                problems.append(f"empreinte différente : {name}")
        counts = {}
        for name in ("journal.json", "audit.json"):
            if name in archive.namelist():
                counts[name] = check_chain(json.loads(archive.read(name)), name, problems)
        if args.key:
            if manifest.get("seal") and seal(manifest["files"], args.key) != manifest["seal"]:
                problems.append("le sceau du manifeste ne correspond pas à la clé fournie")
            if "journal.json" in archive.namelist():
                for row in json.loads(archive.read("journal.json")):
                    if row.get("timestamp_provider") != "local":
                        continue
                    token = seal({"digest": row["hash"], "at": row["material"]["at"], "provider": "local"}, args.key)
                    if token != row.get("timestamp_token"):
                        problems.append(f"journal.json : horodatage invalide pour le nº {row['material']['seq']}")
    print(f"Archive : {args.archive} — format {manifest.get('format')} — port {manifest.get('port', '?')}")
    print(f"Fichiers contrôlés : {len(manifest.get('files', {}))}")
    for name, count in counts.items():
        print(f"{name} : {count} entrées chaînées")
    if problems:
        print("\nANOMALIES :")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("\nIntégrité vérifiée : aucune altération détectée.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
