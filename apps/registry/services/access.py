"""Resolve the call and the acting party for an incoming request (web or API)."""
from __future__ import annotations

from apps.core import mfa

from ..models import MasterAccessLink, PortCall
from .context import Actor, actor_for_call
from .errors import NotVisible
from .rights import draft_visible

MASTER_SESSION_KEY = "fluxaa_master_link_id"


def master_from_session(request) -> MasterAccessLink | None:
    link_id = request.session.get(MASTER_SESSION_KEY) if hasattr(request, "session") else None
    if not link_id:
        return None
    link = MasterAccessLink.objects.filter(pk=link_id).select_related("call", "call__port").first()
    if link is None or not link.is_valid():
        request.session.pop(MASTER_SESSION_KEY, None)
        return None
    return link


def find_call(reference_or_pk) -> PortCall:
    qs = PortCall.objects.select_related("port", "vessel", "berth", "agency", "requested_berth")
    call = qs.filter(reference=str(reference_or_pk)).first()
    if call is None and str(reference_or_pk).isdigit():
        call = qs.filter(pk=int(reference_or_pk)).first()
    if call is None:
        raise NotVisible()
    return call


def call_and_actor(request, reference_or_pk, *, master: MasterAccessLink | None = None) -> tuple[PortCall, Actor]:
    call = find_call(reference_or_pk)
    user = getattr(request, "user", None)
    master = master or getattr(user, "master", None) or (None if user is not None and user.is_authenticated else master_from_session(request))
    if master is not None:
        actor = actor_for_call(call, master=master)
    else:
        actor = actor_for_call(call, user=user, strong_auth=mfa.request_is_strong(request))
    if not draft_visible(actor, call):
        raise NotVisible()
    return call, actor
