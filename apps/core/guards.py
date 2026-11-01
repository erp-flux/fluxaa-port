"""Write guards for registry records (FLX-SPEC-001 rule 3 — "Aucune suppression").

Two levels of protection are applied, both demonstrable in tests:
  1. at the ORM level (this module) — no code path, admin included, can update an append-only
     record or delete any registry record;
  2. at the database level — PostgreSQL triggers installed by migrations refuse UPDATE/DELETE/
     TRUNCATE whatever the client (see apps/registry/migrations/0002_database_guards.py), and the
     runtime database role has no DELETE privilege (see apps/core/management/commands/apply_db_grants.py).
"""
from django.db import models


class ImmutableRecordError(Exception):
    """Raised when code tries to alter or delete a protected registry record."""


class NoDeleteQuerySet(models.QuerySet):
    def delete(self):  # noqa: D401
        raise ImmutableRecordError(f"Deleting {self.model.__name__} records is forbidden.")

    delete.queryset_only = True


class AppendOnlyQuerySet(NoDeleteQuerySet):
    def update(self, **kwargs):
        raise ImmutableRecordError(f"{self.model.__name__} is append-only: updates are forbidden.")

    def bulk_update(self, objs, fields, batch_size=None):
        raise ImmutableRecordError(f"{self.model.__name__} is append-only: updates are forbidden.")

    def update_or_create(self, *args, **kwargs):
        raise ImmutableRecordError(f"{self.model.__name__} is append-only: updates are forbidden.")


class NoDeleteModel(models.Model):
    """Records that may change state but never disappear (calls, tasks, requests, documents…)."""

    objects = NoDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError(f"Deleting {type(self).__name__} records is forbidden.")


class AppendOnlyModel(models.Model):
    """Records that are written once and never modified (journal, milestones, signatures…)."""

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ImmutableRecordError(f"{type(self).__name__} is append-only: updates are forbidden.")
        kwargs.pop("update_fields", None)
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ImmutableRecordError(f"Deleting {type(self).__name__} records is forbidden.")
