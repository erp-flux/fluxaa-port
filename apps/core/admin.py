"""Settings screens for the port's functional administrator (EF-16) and the platform operator.

A port administrator sees and edits only the configuration of their own port. Business records
(calls, milestones, documents…) are deliberately absent from these screens: they are reached
through the application, where rights and confidentiality levels apply.
"""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserChangeForm
from django.utils.translation import gettext_lazy as _

from .models import Berth, Organization, Port, User
from .parties import PARTY_KINDS, normalize_kind
from .roles import Role


def _recent_second_factor(request) -> bool:
    """Changing settings or accounts requires a recent second-factor check (ENF-3.1), not just a password."""
    from django.conf import settings

    from . import mfa

    return not settings.FLUXAA_MFA_ENFORCED or mfa.session_is_strong(request)


class PortScopedAdmin(admin.ModelAdmin):
    """Restricts every list and form to the administrator's port."""

    port_field = "port"

    def _port(self, request):
        return request.user.port if not request.user.is_superuser else None

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        port = self._port(request)
        return qs if port is None else qs.filter(**{self.port_field: port})

    def _allowed(self, request):
        return request.user.is_active and (request.user.is_superuser or getattr(request.user, "is_port_admin", False))

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self._allowed(request) and _recent_second_factor(request)

    def has_change_permission(self, request, obj=None):
        return self._allowed(request) and _recent_second_factor(request)

    def has_delete_permission(self, request, obj=None):
        return False

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        port = self._port(request)
        if port is not None:
            if db_field.name == "port":
                kwargs["queryset"] = Port.objects.filter(pk=port.pk)
                kwargs["initial"] = port.pk
            elif hasattr(db_field.related_model, "port"):
                kwargs["queryset"] = db_field.related_model.objects.filter(port=port)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


def _changed_fields(message) -> str:
    """The fields named in an admin change message ([{"changed": {"fields": [...]}}]), for the person's e-mail."""
    import json

    try:
        items = json.loads(message) if isinstance(message, str) else message
        fields = [field for item in items or [] for field in item.get("changed", {}).get("fields", [])]
    except (TypeError, ValueError, AttributeError):
        fields = []
    return ", ".join(str(f) for f in fields) or str(_("settings"))


class RolesField(forms.MultipleChoiceField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("choices", Role.choices)
        kwargs.setdefault("widget", forms.CheckboxSelectMultiple)
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)


@admin.register(Port)
class PortAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "country", "timezone", "default_language", "is_active")
    fieldsets = (
        (None, {"fields": ("code", "name", "country", "timezone", "default_language", "is_active")}),
        (_("Delays and thresholds"), {"fields": ("countersign_delay_minutes", "reminder_lead_hours",
                                                 "escalation_after_minutes", "quantity_tolerance_pct",
                                                 "ais_divergence_minutes", "digest_hour_local")}),
        (_("Master access"), {"fields": ("master_link_grace_hours", "master_link_max_days")}),
        (_("Announcements and call board (v1.5)"), {"fields": ("default_validity_days", "max_validity_days", "board_shows_cargo")}),
        (_("Retention and security"), {"fields": ("retention_years", "security_authority_email")}),
        (_("Port waters — AIS board"), {
            "description": _("The box drawn on the AIS board (the four limits, decimal degrees) and, if wished, a chart "
                             "excerpt covering exactly that box. Without the box the board is a list."),
            "fields": (("map_lat_min", "map_lat_max"), ("map_lon_min", "map_lon_max"), "map_image", "ais_retention_days"),
        }),
        (_("AI assistance (EF-17)"), {"fields": ("ai_assistance_enabled", "ai_agreement_reference")}),
    )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs if request.user.is_superuser else qs.filter(pk=getattr(request.user.port, "pk", None))

    def get_readonly_fields(self, request, obj=None):
        # sending call data to an AI provider is a governance decision of the platform operator
        return () if request.user.is_superuser else ("code", "country", "is_active", "ai_assistance_enabled",
                                                      "ai_agreement_reference")

    def has_module_permission(self, request):
        return request.user.is_superuser or getattr(request.user, "is_port_admin", False)

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request) and _recent_second_factor(request)

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return False


class OrganizationForm(forms.ModelForm):
    allowed_roles = RolesField(label=_("roles this organisation may hold"))
    kind = forms.CharField(label=_("kind of party"), required=False, max_length=80,
                           help_text=_("Suggested kinds (non-exhaustive): %(kinds)s — or any other wording.") % {
                               "kinds": ", ".join(fr for _code, _role, fr, _en in PARTY_KINDS)},
                           widget=forms.TextInput(attrs={"list": "party-kinds", "style": "width:28em"}))

    class Meta:
        model = Organization
        fields = "__all__"

    def clean_kind(self):
        return normalize_kind(self.cleaned_data.get("kind", ""))


@admin.register(Organization)
class OrganizationAdmin(PortScopedAdmin):
    form = OrganizationForm
    list_display = ("name", "short_name", "kind_display", "roles_display", "email", "phone", "is_active")
    list_filter = ("is_active", "kind")
    search_fields = ("name", "short_name", "email", "kind")

    @admin.display(description=_("roles"))
    def roles_display(self, obj):
        return ", ".join(obj.allowed_roles or [])

    @admin.display(description=_("kind of party"), ordering="kind")
    def kind_display(self, obj):
        return obj.kind_label


class UserForm(UserChangeForm):
    """The password is shown as a read-only hash with a link to the password form (never as an editable field)."""

    roles = RolesField(label=_("roles the user may exercise"))

    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
        field_classes = {}


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    form = UserForm
    add_form = UserForm
    ordering = ("full_name",)
    list_display = ("full_name", "email", "organization", "roles_display", "mfa_enabled", "is_port_admin", "is_active")
    list_filter = ("is_active", "is_port_admin", "mfa_enabled", "is_integration")
    search_fields = ("full_name", "email")
    fieldsets = (
        (None, {"fields": ("email", "password", "full_name", "organization", "roles", "language", "phone")}),
        (_("Administration"), {"fields": ("is_active", "is_port_admin", "is_integration", "integration_scopes")}),
        (_("Notifications and security"), {"fields": ("notify_digest_only", "mfa_enabled", "last_login")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "full_name", "organization", "roles", "language",
                                                              "password1", "password2")}),)
    readonly_fields = ("last_login",)

    @admin.display(description=_("roles"))
    def roles_display(self, obj):
        return ", ".join(obj.roles or [])

    def get_form(self, request, obj=None, **kwargs):
        if obj is None:
            from django.contrib.auth.forms import UserCreationForm

            class CreationForm(UserCreationForm):
                roles = RolesField(label=_("roles the user may exercise"))

                class Meta:
                    model = User
                    fields = ("email", "full_name", "organization", "roles", "language")

            kwargs["form"] = CreationForm
        return super().get_form(request, obj, **kwargs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if request.user.is_superuser:
            return qs
        return qs.filter(organization__port=request.user.port, is_superuser=False)

    def save_model(self, request, obj, form, change):
        if change:  # the notice goes to the address on record before the change, never only to a new one
            request._fluxaa_previous_email = User.objects.filter(pk=obj.pk).values_list("email", flat=True).first()
        if change and "mfa_enabled" in form.changed_data and not obj.mfa_enabled:
            # reset after a lost phone: the person registers a new application at the next sign-in
            obj.mfa_secret_encrypted = ""
        if obj.mfa_enabled and not obj.mfa_secret_encrypted:
            obj.mfa_enabled = False
            messages.warning(request, _("Two-factor authentication is activated by the person, from their own "
                                        "phone, at sign-in; it has been left inactive."))
        super().save_model(request, obj, form, change)

    def _trace(self, request, obj, message, *, created: bool = False):
        # administrative changes to an account (roles, activation, password, second-factor reset) join the
        # port's access journal, where they cannot be erased (ENF-3.4) — and the person is told by e-mail
        port = obj.port or getattr(request.user, "port", None)
        if port is not None:
            from apps.registry.services import journal

            journal.audit(port=port, user=request.user, action="user.administered", obj=obj,
                          detail=str(message)[:500], request=request)
        previous = getattr(request, "_fluxaa_previous_email", None) or obj.email
        recipients = sorted({address for address in (previous, obj.email) if address})
        if not created and recipients and obj.pk != request.user.pk:
            from django.conf import settings
            from django.core.mail import send_mail
            from django.utils import translation

            with translation.override(obj.language or "fr"):
                subject = str(_("[FLUXAA Port] Your account was changed by an administrator"))
                body = str(_("%(admin)s has changed your account (%(email)s): %(changes)s. If you did not expect "
                             "it, contact your port administrator.")) % {
                    "admin": request.user.get_full_name() or request.user.email, "email": previous,
                    "changes": _changed_fields(message)}
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, recipients, fail_silently=True)

    def log_addition(self, request, obj, message):
        entry = super().log_addition(request, obj, message)
        self._trace(request, obj, message, created=True)
        return entry

    def log_change(self, request, obj, message):
        entry = super().log_change(request, obj, message)
        self._trace(request, obj, message)
        return entry

    def get_readonly_fields(self, request, obj=None):
        base = list(super().get_readonly_fields(request, obj))
        if not request.user.is_superuser:
            base += ["is_integration", "integration_scopes"]
        return base

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "organization" and not request.user.is_superuser:
            kwargs["queryset"] = Organization.objects.filter(port=request.user.port)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def _allowed(self, request):
        return request.user.is_active and (request.user.is_superuser or getattr(request.user, "is_port_admin", False))

    def has_module_permission(self, request):
        return self._allowed(request)

    def has_view_permission(self, request, obj=None):
        return self._allowed(request)

    def has_add_permission(self, request):
        return self._allowed(request) and _recent_second_factor(request)

    def has_change_permission(self, request, obj=None):
        return (self._allowed(request) and _recent_second_factor(request)
                and (obj is None or request.user.is_superuser or not obj.is_superuser))

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Berth)
class BerthAdmin(PortScopedAdmin):
    list_display = ("code", "name_fr", "name_en", "kind", "max_loa_m", "max_draft_m", "max_dwt", "cargo_kinds", "has_vapour_recovery", "is_active")
    list_filter = ("kind", "is_active")
    fieldsets = (
        (None, {"fields": ("code", ("name_fr", "name_en"), "kind", "cargo_kinds", "is_active", "notes")}),
        (_("Acceptance limits — compared with the vessel's particulars by the vetting grid (v1.5)"), {
            "fields": (("max_loa_m", "max_beam_m", "max_draft_m"), ("max_dwt", "max_displacement_t"),
                       ("max_manifold_height_m", "max_air_draft_m", "min_ukc_m"), ("max_vessel_age_years", "min_crane_swl_t"))}),
        (_("Operating conditions"), {"fields": ("weather_limits", "has_vapour_recovery")}),
        (_("Position on the AIS board"), {"fields": (("latitude", "longitude"), "radius_m")}),
    )
