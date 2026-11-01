"""The assistant's traces are kept like the rest of the registry: runs append-only, reviews never deleted."""
from django.db import migrations

from apps.core.dbguards import REFUSE_FUNCTION, append_only_sql, drop_sql, no_delete_sql

APPEND_ONLY = ["ai_assistantrun"]
NO_DELETE = ["ai_extractionreview"]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    statements = [REFUSE_FUNCTION]
    for table in APPEND_ONLY:
        statements += append_only_sql(table)
    for table in NO_DELETE:
        statements += no_delete_sql(table)
    with schema_editor.connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in APPEND_ONLY + NO_DELETE:
            for sql in drop_sql(table):
                cursor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("ai", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
