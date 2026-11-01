"""Business exceptions raised by the registry services.

Every refusal carries an explicit, bilingual message (EF-11.2: never a generic message).
Views translate them into HTTP responses: NotVisible -> 404 (existence not disclosed),
PermissionRefused -> 403, HoldPointRefused / LockRefused / RuleViolation -> 409.
"""
from __future__ import annotations

from django.utils.translation import gettext as _


class RegistryError(Exception):
    http_status = 400
    code = "registry_error"

    def __init__(self, message: str = "", *, details: dict | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        return self.message


class NotVisible(RegistryError):
    """The object does not exist *for this actor*. Never reveals existence (EF-12, S5)."""

    http_status = 404
    code = "not_found"

    def __init__(self, message: str = ""):
        super().__init__(message or _("Not found."))


class PermissionRefused(RegistryError):
    http_status = 403
    code = "permission_refused"


class StrongAuthRequired(PermissionRefused):
    code = "strong_auth_required"

    def __init__(self, message: str = ""):
        super().__init__(message or _("This decision requires a recent two-factor authentication."))


class RuleViolation(RegistryError):
    """A business rule of the registry refuses the action (rule 1, rule 2, life-cycle graph…)."""

    http_status = 409
    code = "rule_violation"


class HoldPointRefused(RegistryError):
    """A hold point refuses the transition (EF-11). Lists missing tasks, responsible roles and expected actions."""

    http_status = 409
    code = "hold_point_refused"

    def __init__(self, transition: str, missing: list[dict], reasons: list[str] | None = None, message: str = ""):
        self.transition = transition
        self.missing = missing
        self.reasons = reasons or []
        super().__init__(message, details={"transition": transition, "missing_tasks": missing, "reasons": self.reasons})


class LockRefused(HoldPointRefused):
    """A non-configurable lock (bill of lading, EF-7.4). No role, administrator included, can lift it."""

    code = "lock_refused"


def ensure_open(call) -> None:
    """A closed, archived, rejected or cancelled call is frozen: nothing more is signed, cancelled or decided on it."""
    if call.is_terminal_state:
        raise RuleViolation(_("The call is closed."))


def ensure_not_closed(call) -> None:
    """Closed or archived: frozen. A cancelled or rejected call can still see its open disputes answered and closed —
    they would otherwise stay open for ever."""
    if call.status in ("CLOSED", "ARCHIVED"):
        raise RuleViolation(_("The call is closed."))
