"""Install the PostgreSQL triggers that make the registry append-only / undeletable."""
from django.db import migrations

from apps.core.dbguards import REFUSE_FUNCTION, append_only_sql, drop_sql, no_delete_sql

APPEND_ONLY = [
    "registry_journalentry", "registry_auditentry", "registry_milestone", "registry_milestonesignature",
    "registry_tasksignature", "registry_disputeentry", "registry_authorization", "registry_authorizationevent",
    "registry_documentsignature", "registry_measurementvalue", "registry_pumpinglogentry", "registry_message",
    "registry_alert",
]
NO_DELETE = [
    "registry_portcall", "registry_callparty", "registry_masteraccesslink", "registry_task",
    "registry_servicerequest", "registry_document", "registry_measurement", "registry_dispute",
    "registry_thread", "registry_notification", "registry_calltemplateuse", "registry_templateversion",
    "registry_vessel",
]
EXTRA = [
    'DROP TRIGGER IF EXISTS fluxaa_reference_immutable ON "registry_portcall";',
    'CREATE TRIGGER fluxaa_reference_immutable BEFORE UPDATE OF reference ON "registry_portcall" '
    "FOR EACH ROW WHEN (OLD.reference IS DISTINCT FROM NEW.reference) EXECUTE FUNCTION fluxaa_refuse();",
    'DROP TRIGGER IF EXISTS fluxaa_document_frozen ON "registry_document";',
    'CREATE TRIGGER fluxaa_document_frozen BEFORE UPDATE ON "registry_document" '
    "FOR EACH ROW WHEN (OLD.sha256 IS DISTINCT FROM NEW.sha256 OR OLD.file IS DISTINCT FROM NEW.file) "
    "EXECUTE FUNCTION fluxaa_refuse();",
]


def install(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    statements = [REFUSE_FUNCTION]
    for table in APPEND_ONLY:
        statements += append_only_sql(table)
    for table in NO_DELETE:
        statements += no_delete_sql(table)
    statements += EXTRA
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
        cursor.execute('DROP TRIGGER IF EXISTS fluxaa_reference_immutable ON "registry_portcall";')
        cursor.execute('DROP TRIGGER IF EXISTS fluxaa_document_frozen ON "registry_document";')


class Migration(migrations.Migration):
    dependencies = [("registry", "0001_initial")]
    operations = [migrations.RunPython(install, uninstall)]
