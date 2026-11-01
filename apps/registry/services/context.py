"""Who is acting, and under which roles on *this* call.

Rights are computed from the roles on the call (CallParty) intersected with the roles the person
may exercise — never from the organisation alone (EF-12.1, rule 5). The master acts through an
account-less link limited to one call (EF-13).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.roles import role_label

from ..models import MasterAccessLink, PortCall
from .errors import NotVisible, PermissionRefused


@dataclass(frozen=True)
class Actor:
    port: object
    roles: frozenset = field(default_factory=frozenset)
    user: object | None = None
    master: MasterAccessLink | None = None
    org: object | None = None
    is_system: bool = False
    strong_auth: bool = False

    # ------------------------------------------------------------------ identity
    @property
    def label(self) -> str:
        if self.is_system:
            return "FLUXAA"
        if self.master is not None:
            if self.master.role == "NAV":
                master = _("Master")
                return f"{self.master.master_name} — {master} ({self.master.call.vessel.name})"
            name = self.master.master_name or _("(name not entered)")
            return f"{name} — {role_label(self.master.role)} ({self.org})"
        name = self.user.full_name or self.user.email
        org = f" — {self.org}" if self.org else ""
        return f"{name}{org}"

    @property
    def is_master(self) -> bool:
        """The ship's side, through the master's account-less link."""
        return self.master is not None and self.master.role == "NAV"

    @property
    def is_link(self) -> bool:
        """Account-less access of any kind (master or party): never a decision, never the assistant."""
        return self.master is not None

    def has(self, *roles: str) -> bool:
        return any(r in self.roles for r in roles)

    def pick_role(self, allowed, preferred: str | None = None) -> str:
        """Return the role under which the actor acts for an action allowed to *allowed* roles."""
        allowed = set(allowed)
        if preferred:
            if preferred in self.roles and preferred in allowed:
                return preferred
            raise PermissionRefused(
                _("You do not hold the role %(role)s on this call.") % {"role": role_label(preferred)}
            )
        for role in sorted(self.roles):
            if role in allowed:
                return role
        if not allowed:
            raise PermissionRefused(_("This action is not open to your role on this call."))
        raise PermissionRefused(
            _("This action is reserved to: %(roles)s.") % {"roles": ", ".join(role_label(r) for r in sorted(allowed))}
        )

    def with_strong_auth(self, value: bool = True) -> "Actor":
        return Actor(self.port, self.roles, self.user, self.master, self.org, self.is_system, value)

    # ------------------------------------------------------------------ persistence helpers
    def stamp(self) -> dict:
        """Common actor fields for records that keep a nominative trace."""
        return {
            "user": self.user if self.user is not None and not self.is_system else None,
            "master": self.master,
            "label": self.label,
        }


def system_actor(port) -> Actor:
    return Actor(port=port, roles=frozenset({"SYSTEM"}), is_system=True, strong_auth=True)


def roles_on_call(call: PortCall, user) -> frozenset:
    if user is None or not getattr(user, "is_authenticated", False) or not user.organization_id:
        return frozenset()
    now = timezone.now()
    party_roles = {
        p.role for p in call.parties.all()
        if p.organization_id == user.organization_id and p.is_active_at(now)
    }
    return frozenset(set(user.roles or []) & party_roles)


def actor_for_call(call: PortCall, *, user=None, master: MasterAccessLink | None = None, strong_auth: bool = False) -> Actor:
    """Resolve the actor for *call*; raise NotVisible when the person has no role on it."""
    if master is not None:
        if master.call_id != call.id or not master.is_valid():
            raise NotVisible()
        if master.role != "NAV":
            # a party's link: the organisation must still hold that role on the call (revoking the role ends the link)
            active = call.parties.filter(organization_id=master.organization_id, role=master.role, revoked_at__isnull=True)
            if master.organization_id is None or not active.exists():
                raise NotVisible()
        return Actor(port=call.port, roles=frozenset({master.role}), master=master, org=master.organization)
    if user is None or not getattr(user, "is_authenticated", False):
        raise NotVisible()
    if not user.organization_id or user.organization.port_id != call.port_id:
        raise NotVisible()
    roles = roles_on_call(call, user)
    if not roles:
        raise NotVisible()
    return Actor(port=call.port, roles=roles, user=user, org=user.organization, strong_auth=strong_auth)


def port_actor(user, *, strong_auth: bool = False) -> Actor:
    """Actor for port-level actions (creating a call, dashboard): roles the user may exercise."""
    if user is None or not user.is_authenticated or not user.organization_id:
        raise PermissionRefused(_("Your account is not attached to an organisation of a port."))
    return Actor(
        port=user.organization.port, roles=user.role_set, user=user, org=user.organization, strong_auth=strong_auth
    )
