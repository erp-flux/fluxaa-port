"""The twelve roles of FLX-SPEC-001 §4.

Rights are carried by a *role on a call* (rule 5), never by a person or an organisation as such.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _


class Role(models.TextChoices):
    AGE = "AGE", _("Shipping agency")
    NAV = "NAV", _("Vessel / master")
    TER = "TER", _("Terminal / depot")
    CAP = "CAP", _("Harbour master")
    APO = "APO", _("Port authority")
    SVC = "SVC", _("Marine services")
    ADM = "ADM", _("Customs, immigration, health")
    SUR = "SUR", _("Security & naval base")
    INS = "INS", _("Surveyor & laboratory")
    COM = "COM", _("Owner / charterer")
    PRE = "PRE", _("Service provider")
    DIR = "DIR", _("Port management")


ALL_ROLES: tuple[str, ...] = tuple(r.value for r in Role)

# Roles that see every task of a call (CDC EF-5.7)
OVERVIEW_ROLES = frozenset({"AGE", "CAP"})
# Roles that take decisions on requests (approve/refuse) — any decision needs strong authentication
DECISION_ROLES = frozenset({"CAP", "APO", "ADM", "SUR"})
# Read-only commercial interests: no data entry right (CDC EF-12.5)
READ_ONLY_ROLES = frozenset({"COM"})
# Roles allowed to export structured data (FLX-SPEC-001 §5, verb E)
EXPORT_ROLES = frozenset({"COM", "DIR"})
# Roles allowed to read the access audit trail (CDC ENF-3.4)
AUDIT_ROLES = frozenset({"CAP", "DIR", "SUR"})
# Roles with access to the N4 security domain (CDC EF-12.4)
N4_ROLES = frozenset({"SUR", "CAP"})
# Roles that never see the dashboard (FLX-SPEC-001 §5)
NO_DASHBOARD_ROLES = frozenset({"NAV"})

# Special pseudo-role used in templates for "the party at the origin" / "any party"
ANY_PARTY = "ANY"


def role_label(code: str) -> str:
    try:
        return str(Role(code).label)
    except ValueError:
        if code == ANY_PARTY:
            return str(_("Any party"))
        return code


def validate_roles(codes) -> list[str]:
    """Return the list of unknown role codes (empty when all are valid)."""
    return [c for c in (codes or []) if c not in ALL_ROLES]
