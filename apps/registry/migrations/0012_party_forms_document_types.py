"""Existing ports: the document types of the forms every party issues from the platform (v1.3).

New ports get them from the reference catalogue (bootstrap_ports); this migration adds the missing types to the
ports already installed without touching the types their administrator has already adjusted.
"""
from django.db import migrations

from apps.registry import catalog

NEW_CODES = ["AUTHORIZATION", "ARRIVAL_NOTICE", "SANCTIONS_CHECK", "ACCESS_LIST", "PRE_ARRIVAL_SECURITY", "INERT_GAS_DECLARATION",
             "HOT_WORK_PERMIT", "ENCLOSED_SPACE_PERMIT", "INCIDENT_REPORT", "MOVEMENT_ORDER", "SERVICE_NOTE", "BERTH_READINESS",
             "SHORE_TANK_REPORT", "SAMPLING_RECORD", "BUNKER_CHECKLIST", "LOI"]


def forwards(apps, schema_editor):
    if schema_editor.connection.alias != "default":
        return  # the registry lives in the main database only
    Port = apps.get_model("core", "Port")
    DocumentType = apps.get_model("registry", "DocumentType")
    by_code = {d["code"]: d for d in catalog.DOCUMENT_TYPES}
    order = {d["code"]: i for i, d in enumerate(catalog.DOCUMENT_TYPES, start=1)}
    for port in Port.objects.all():
        for code in NEW_CODES:
            values = {k: v for k, v in by_code[code].items() if k != "code"}
            values["order"] = order[code]
            DocumentType.objects.get_or_create(port=port, code=code, defaults=values)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_party_access_links"),
        ("registry", "0011_task_stage"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
