"""Settings of the port's call templates and reference lists — no code delivery needed (EF-16)."""
from __future__ import annotations

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from apps.core.admin import PortScopedAdmin, RolesField

from .models import (
    CallTemplate,
    DocumentType,
    HoldPoint,
    HoldPointRequirement,
    InterruptionCause,
    MilestoneType,
    PortDefaultParty,
    RequestType,
    TemplateTask,
    TemplateVersion,
    Vessel,
    WebhookSubscription,
)
from .services.templates import new_draft_version, publish_version


class TemplateVersionInline(admin.TabularInline):
    model = TemplateVersion
    extra = 0
    fields = ("number", "status", "published_at", "notes")
    readonly_fields = ("number", "status", "published_at", "notes")
    show_change_link = True
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(CallTemplate)
class CallTemplateAdmin(PortScopedAdmin):
    list_display = ("code", "name_fr", "name_en", "kind", "published", "is_active")
    list_filter = ("kind", "is_active")
    inlines = [TemplateVersionInline]
    actions = ["create_draft"]

    @admin.display(description=_("published version"))
    def published(self, obj):
        version = obj.published_version
        return f"v{version.number}" if version else "—"

    @admin.action(description=_("Create a draft version (copy of the published one) to edit"), permissions=["change"])
    def create_draft(self, request, queryset):
        for template in queryset:
            draft = new_draft_version(template, request.user)
            self.message_user(request, _("Draft v%(n)s of %(code)s ready to edit.") % {"n": draft.number, "code": template.code})


class TemplateTaskForm(forms.ModelForm):
    co_roles = RolesField(label=_("co-signing roles"))

    class Meta:
        model = TemplateTask
        fields = "__all__"


class TemplateTaskInline(admin.StackedInline):
    model = TemplateTask
    form = TemplateTaskForm
    extra = 0
    fieldsets = (
        (None, {"fields": (("number", "order"), ("section_fr", "section_en"), "title_fr", "title_en")}),
        (_("Who and how"), {"fields": (("role", "nature", "joint"), "co_roles")}),
        (_("Deadline (always relative)"), {"fields": (("anchor", "offset_minutes"), ("timing_fr", "timing_en"))}),
        (_("Criticality"), {"fields": (("criticality", "confidentiality"), "hold_basis", "not_applicable_allowed")}),
        (_("Completed by"), {"classes": ("collapse",), "fields": (("request_type_code", "request_side"), "milestone_codes",
                                                                  "document_type_code", "auto_event", "continuous",
                                                                  "per_vessel", "berth_kinds")}),
    )

    def _editable(self, obj):
        return obj is not None and obj.status == TemplateVersion.Status.DRAFT

    def has_add_permission(self, request, obj=None):
        return self._editable(obj)

    def has_change_permission(self, request, obj=None):
        return self._editable(obj)

    def has_delete_permission(self, request, obj=None):
        return self._editable(obj)


@admin.register(TemplateVersion)
class TemplateVersionAdmin(PortScopedAdmin):
    port_field = "template__port"
    list_display = ("template", "number", "status", "published_at")
    list_filter = ("status", "template__code")
    readonly_fields = ("template", "number", "status", "published_at", "published_by")
    fields = ("template", "number", "status", "published_at", "published_by", "notes")
    inlines = [TemplateTaskInline]
    actions = ["publish"]

    def has_add_permission(self, request):
        return False

    @admin.action(description=_("Publish the selected draft version (new calls will use it)"), permissions=["change"])
    def publish(self, request, queryset):
        for version in queryset:
            try:
                publish_version(version, request.user)
                self.message_user(request, _("%(v)s published.") % {"v": version})
            except ValidationError as exc:
                self.message_user(request, _("%(v)s not published: %(e)s") % {"v": version, "e": "; ".join(exc.messages)},
                                  level=messages.ERROR)


class HoldPointRequirementInline(admin.TabularInline):
    model = HoldPointRequirement
    extra = 1


@admin.register(HoldPoint)
class HoldPointAdmin(PortScopedAdmin):
    list_display = ("transition", "requirements_display")
    inlines = [HoldPointRequirementInline]

    @admin.display(description=_("required tasks"))
    def requirements_display(self, obj):
        return ", ".join(str(r) for r in obj.requirements.all())


class MilestoneTypeForm(forms.ModelForm):
    countersigner_roles = RolesField(label=_("countersigners"))

    class Meta:
        model = MilestoneType
        fields = "__all__"


@admin.register(MilestoneType)
class MilestoneTypeAdmin(PortScopedAdmin):
    form = MilestoneTypeForm
    list_display = ("number", "code", "label_fr", "label_en", "emitter_role", "hold_point", "is_active")
    list_filter = ("is_active", "emitter_role")
    ordering = ("order",)


class RequestTypeForm(forms.ModelForm):
    requester_roles = RolesField(label=_("requesting roles"))
    decision_roles = RolesField(label=_("deciding authorities"))

    class Meta:
        model = RequestType
        fields = "__all__"


@admin.register(RequestType)
class RequestTypeAdmin(PortScopedAdmin):
    form = RequestTypeForm
    list_display = ("code", "label_fr", "label_en", "requesters", "deciders", "confidentiality", "is_active")
    list_filter = ("is_active", "confidentiality")

    @admin.display(description=_("requesting roles"))
    def requesters(self, obj):
        return ", ".join(obj.requester_roles)

    @admin.display(description=_("deciding authorities"))
    def deciders(self, obj):
        return ", ".join(obj.decision_roles) or "—"


class DocumentTypeForm(forms.ModelForm):
    issuer_roles = RolesField(label=_("issuing roles"))
    signer_roles = RolesField(label=_("required signatories"))
    audience_roles = RolesField(label=_("additional readers (N2)"))

    class Meta:
        model = DocumentType
        fields = "__all__"


@admin.register(DocumentType)
class DocumentTypeAdmin(PortScopedAdmin):
    form = DocumentTypeForm
    list_display = ("code", "label_fr", "label_en", "default_confidentiality", "generated", "is_bill_of_lading", "is_active")
    list_filter = ("is_active", "default_confidentiality")

    def get_readonly_fields(self, request, obj=None):
        return ("is_bill_of_lading", "generated")  # the bill-of-lading lock cannot be configured away


@admin.register(InterruptionCause)
class InterruptionCauseAdmin(PortScopedAdmin):
    list_display = ("code", "label_fr", "label_en", "attributable_to", "requires_reason", "is_active", "order")
    list_editable = ("order",)
    list_filter = ("attributable_to", "is_active")


@admin.register(PortDefaultParty)
class PortDefaultPartyAdmin(PortScopedAdmin):
    list_display = ("organization", "role")

    def has_delete_permission(self, request, obj=None):
        return self._allowed(request)


@admin.register(Vessel)
class VesselAdmin(PortScopedAdmin):
    list_display = ("name", "imo", "flag", "vessel_type", "dwt")
    search_fields = ("name", "imo")


@admin.register(WebhookSubscription)
class WebhookSubscriptionAdmin(PortScopedAdmin):
    list_display = ("name", "url", "is_active", "created_at")
    readonly_fields = ("secret",)
