from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AiConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ai"
    label = "ai"
    verbose_name = _("AI assistance")
