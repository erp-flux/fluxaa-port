from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView

from apps.core.views import admin_login, healthz

admin.site.site_header = "FLUXAA Port — paramétrage"
admin.site.site_title = "FLUXAA Port"
admin.site.index_title = "Paramétrage du port / Port settings"

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("admin/login/", admin_login),  # one sign-in page for everyone: attempt limits and second factor
    path("admin/", admin.site.urls),
    path("api/v1/", include("apps.api.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularRedocView.as_view(url_name="schema"), name="api-docs"),
    path("surete/", include("apps.secure.urls")),
    path("", include("apps.core.urls")),
    path("", include("apps.ai.urls")),
    path("", include("apps.ais.urls")),
    path("", include("apps.registry.urls")),
]
