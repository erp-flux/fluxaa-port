"""Route the N4 security domain to its own database (CDC EF-12.4, architecture orientation 3).

The separation is structural: N4 models live in the ``secure`` app, migrate only on the
``secure`` alias, and may never hold a relation to an object of the operational registry.
When both aliases point to the exact same physical database (single-DB deployments), all
migrations and relations operate on that single database.
"""
from django.conf import settings

SECURE_APPS = {"secure"}


def _is_single_db() -> bool:
    databases = getattr(settings, "DATABASES", {})
    default_db = databases.get("default", {})
    secure_db = databases.get("secure", {})
    return bool(
        default_db
        and secure_db
        and default_db.get("NAME") == secure_db.get("NAME")
        and default_db.get("HOST") == secure_db.get("HOST")
    )


class DomainRouter:
    @staticmethod
    def _alias(model) -> str:
        return "secure" if model._meta.app_label in SECURE_APPS else "default"

    def db_for_read(self, model, **hints):
        return self._alias(model)

    def db_for_write(self, model, **hints):
        return self._alias(model)

    def allow_relation(self, obj1, obj2, **hints):
        if _is_single_db():
            return True
        return (obj1._meta.app_label in SECURE_APPS) == (obj2._meta.app_label in SECURE_APPS)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if _is_single_db():
            return db == "default"
        if app_label in SECURE_APPS:
            return db == "secure"
        return db == "default"
