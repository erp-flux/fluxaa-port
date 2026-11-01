from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ApiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.api"
    label = "api"
    verbose_name = _("Public API")

    def ready(self):
        from . import schema  # noqa: F401 — registers the OpenAPI authentication extensions
