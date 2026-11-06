"""Route the N4 security domain to its own database (CDC EF-12.4, architecture orientation 3).

The separation is structural: N4 models live in the ``secure`` app, migrate only on the
``secure`` alias, and may never hold a relation to an object of the operational registry.
"""

SECURE_APPS = {"secure"}


class DomainRouter:
    @staticmethod
    def _alias(model) -> str:
        return "secure" if model._meta.app_label in SECURE_APPS else "default"

    def db_for_read(self, model, **hints):
        return self._alias(model)

    def db_for_write(self, model, **hints):
        return self._alias(model)

    def allow_relation(self, obj1, obj2, **hints):
        return (obj1._meta.app_label in SECURE_APPS) == (obj2._meta.app_label in SECURE_APPS)

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label in SECURE_APPS:
            return db == "secure"
        return db == "default"
