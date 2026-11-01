from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SecureConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.secure"
    label = "secure"
    verbose_name = _("Security domain (N4)")
