"""Grant the runtime database roles exactly what they need — and no DELETE on the registry.

Run with the owner credentials (FLUXAA_MIGRATE=1). The runtime role used by the application
cannot delete or truncate any registry table, nor update an append-only one: even with the
application's credentials, a direct database access cannot erase the registry (CDC ENF-3.6).
"""
from __future__ import annotations

import os
from urllib.parse import unquote, urlparse

from django.apps import apps
from django.core.management.base import BaseCommand
from django.db import connections

from apps.core.guards import AppendOnlyModel

# Tables the runtime role may delete rows from (sessions, tokens, editable configuration)
DELETABLE = {
    "django_session", "authtoken_token", "registry_templatetask", "registry_holdpointrequirement",
    "registry_portdefaultparty", "core_user_groups", "core_user_user_permissions", "registry_webhooksubscription",
    # AIS telemetry: public broadcast data purged after the port's retention period, never acts of the registry
    "ais_vesselposition", "ais_vesselstatic",
}


def role_from_url(url: str | None) -> str:
    return unquote(urlparse(url).username or "") if url else ""


class Command(BaseCommand):
    help = "Apply PostgreSQL privileges for the runtime roles (main and N4 databases)."

    def handle(self, *args, **options):
        self._grant("default", role_from_url(os.environ.get("DATABASE_URL")), exclude_app="secure")
        self._grant("secure", role_from_url(os.environ.get("SECURE_DATABASE_URL")), only_app="secure")

    def _grant(self, alias: str, role: str, exclude_app: str | None = None, only_app: str | None = None):
        connection = connections[alias]
        if connection.vendor != "postgresql":
            self.stdout.write(f"[{alias}] not PostgreSQL — skipped")
            return
        owner = connection.settings_dict.get("USER")
        if not role or role == owner:
            self.stdout.write(self.style.WARNING(f"[{alias}] runtime role equals owner ({owner}) — no separation applied"))
            return
        append_only, deletable = [], []
        for model in apps.get_models():
            label = model._meta.app_label
            if only_app and label != only_app or exclude_app and label == exclude_app:
                continue
            table = model._meta.db_table
            if issubclass(model, AppendOnlyModel):
                append_only.append(table)
            if table in DELETABLE:
                deletable.append(table)
        quoted = connection.ops.quote_name
        with connection.cursor() as cur:
            cur.execute(f"GRANT USAGE ON SCHEMA public TO {quoted(role)}")
            cur.execute(f"GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {quoted(role)}")
            cur.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {quoted(role)}")
            cur.execute(f"REVOKE DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM {quoted(role)}")
            for table in append_only:
                cur.execute(f"REVOKE UPDATE ON {quoted(table)} FROM {quoted(role)}")
            for table in deletable:
                cur.execute(f"GRANT DELETE ON {quoted(table)} TO {quoted(role)}")
        self.stdout.write(self.style.SUCCESS(
            f"[{alias}] {role}: read/insert/update granted; no DELETE/TRUNCATE on the registry; "
            f"{len(append_only)} append-only tables without UPDATE; {len(deletable)} tables deletable"
        ))
