from django.conf import settings


def fluxaa(request):
    user = getattr(request, "user", None)
    context = {"PORT": getattr(request, "port", None), "SITE_URL": settings.SITE_URL, "AI_ENABLED": settings.FLUXAA_AI_ENABLED}
    if user is not None and not user.is_authenticated and getattr(request, "session", None) is not None \
            and request.session.get("fluxaa_master_link_id"):
        from apps.registry.services.access import master_from_session

        context["LINK"] = master_from_session(request)
    if user is not None and user.is_authenticated:
        context["USER_ROLES"] = sorted(user.role_set)
        context["UNREAD_NOTIFICATIONS"] = user.notifications.filter(read_at__isnull=True).count()
        context["IS_SECURITY"] = bool(set(user.roles or []) & {"SUR", "CAP"})
        context["IS_STATISTICS"] = bool(set(user.roles or []) & {"DIR", "APO", "CAP"}) or user.is_port_admin or user.is_superuser
        port = getattr(user, "port", None)
        context["IS_ASSISTANT"] = bool(set(user.roles or []) & {"DIR", "APO", "CAP"}) and bool(
            port is not None and settings.FLUXAA_AI_ENABLED and port.ai_assistance_enabled and (port.ai_agreement_reference or "").strip())
    return context
