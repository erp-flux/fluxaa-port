"""The AIS board: a page for every signed-in party of the port, refreshed by HTMX every minute."""
from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.registry.services import journal, rights
from apps.registry.services.documents import content_type

from . import services


def _port(request):
    port = getattr(request.user, "port", None)
    if port is None:
        raise Http404
    return port


@login_required
@require_GET
def board(request):
    port = _port(request)
    data = services.board(port, visible_calls=rights.call_queryset_for_user(request.user))
    fragment = request.headers.get("HX-Request") == "true"
    if not fragment:
        journal.audit(port=port, user=request.user, action="view", object_kind="ais_board", request=request)
    template = "ais/_board.html" if fragment else "ais/board.html"
    return render(request, template, {"data": data, "max_age_hours": services.MAX_AGE_HOURS})


@login_required
@require_GET
def background(request):
    """The chart excerpt behind the board, served as an image only if it really is one."""
    port = _port(request)
    if not port.map_image:
        raise Http404
    handle = port.map_image.open("rb")
    head = handle.read(16)
    handle.seek(0)
    kind = content_type(head, "")
    if kind not in ("image/png", "image/jpeg", "image/webp"):
        raise Http404
    response = FileResponse(handle, content_type=kind)
    response["Cache-Control"] = "private, max-age=3600"
    return response
