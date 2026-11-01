"""The stages of a call are kept like the rest of the registry: never deleted."""
from django.db import migrations

from apps.core.dbguards import REFUSE_FUNCTION, drop_sql, no_delete_sql

NO_DELETE = ["registry_callstage"]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    statements = [REFUSE_FUNCTION]
    for table in NO_DELETE:
        statements += no_delete_sql(table)
    with schema_editor.connection.cursor() as cursor:
        for sql in statements:
            cursor.execute(sql)


def uninstall(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        for table in NO_DELETE:
            for sql in drop_sql(table):
                cursor.execute(sql)


class Migration(migrations.Migration):
    dependencies = [("registry", "0009_call_stages")]
    operations = [migrations.RunPython(install, uninstall)]
