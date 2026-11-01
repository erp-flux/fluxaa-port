"""EF-15 / ENF-4.1 — the reversibility export can be verified without the platform."""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest
from django.conf import settings

from apps.registry.services import calls as call_svc
from apps.registry.services.exports import export_port

from .conftest import act, force_done, make_call

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verifier_export.py"


def verify(path, *extra):
    return subprocess.run([sys.executable, str(SCRIPT), str(path), *extra], capture_output=True, text=True)


@pytest.mark.django_db
def test_port_export_is_verifiable_offline_and_tampering_is_detected(world, tmp_path):
    call = make_call(world)
    force_done(call, ["M0:02", "M0:03", "M0:05"])
    call_svc.declare_call(call, act(world, call, "AGE"))
    archive = tmp_path / "export.zip"
    archive.write_bytes(export_port(world.port, None))
    result = verify(archive, "--key", settings.FLUXAA_SIGNING_KEY)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "aucune altération" in result.stdout

    # rewrite one past journal entry, as someone editing the archive would
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "journal.json":
                rows = json.loads(data)
                rows[0]["material"]["summary_en"] = "Nothing happened."
                data = json.dumps(rows).encode()
            dst.writestr(item, data)
    result = verify(tampered)
    assert result.returncode == 1
    assert "journal.json" in result.stdout and "modifié" in result.stdout

    # a wrong key cannot validate the manifest seal
    assert verify(archive, "--key", "not-the-key").returncode == 1
