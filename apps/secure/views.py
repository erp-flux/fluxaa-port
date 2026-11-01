"""Security space (N4): reserved to SUR and CAP; everyone else gets "not found" (S5)."""
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core import mfa
from apps.registry.services.errors import NotVisible, RegistryError, StrongAuthRequired

from . import services as n4


def _guard(request):
    if n4.n4_role(request.user, request.user.port) is None:
        raise Http404


@login_required
def index(request):
    _guard(request)
    try:
        items = n4.list_items(request.user, request.user.port, request=request)
    except NotVisible:
        raise Http404
    return render(request, "secure/index.html", {"items": items, "role": n4.n4_role(request.user)})


@login_required
def item(request, reference):
    _guard(request)
    port = request.user.port
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "decide":
                n4.decide(request.user, port, reference, decision=request.POST.get("decision", ""),
                          modalities=request.POST.get("modalities", ""), strong_auth=mfa.session_is_strong(request),
                          request=request)
                messages.success(request, _("Decision recorded in the security space."))
            elif action == "confirm":
                n4.confirm(request.user, port, reference, what=request.POST.get("what", ""), request=request)
                messages.success(request, _("Confirmation recorded."))
            elif action == "attach" and request.FILES.get("file"):
                n4.add_attachment(request.user, port, reference, request.FILES["file"], request=request)
                messages.success(request, _("Attachment encrypted and stored."))
        except StrongAuthRequired:
            return redirect(f"{reverse('core:mfa_verify')}?next={request.path}")
        except NotVisible:
            raise Http404
        except RegistryError as exc:
            messages.error(request, exc.message)
        return redirect(request.path)
    try:
        content = n4.read_item(request.user, port, reference, request=request)
    except NotVisible:
        raise Http404
    return render(request, "secure/item.html", content)


@login_required
def attachment(request, attachment_id):
    _guard(request)
    try:
        att, data = n4.read_attachment(request.user, request.user.port, attachment_id, request=request)
    except NotVisible:
        raise Http404
    response = HttpResponse(data, content_type=att.mime_type or "application/octet-stream")
    response["Content-Disposition"] = f'attachment; filename="{att.name}"'
    return response


@login_required
def access_log(request):
    _guard(request)
    try:
        entries = n4.access_log(request.user, request.user.port, request=request)
    except NotVisible:
        raise Http404
    return render(request, "secure/log.html", {"entries": entries})
