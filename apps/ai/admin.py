"""Read-only view of the assistant's traces for the port administrator (EF-17 audit)."""
from django.contrib import admin

from apps.core.admin import PortScopedAdmin

from .models import AssistantRun, ExtractionReview


class ReadOnlyPortAdmin(PortScopedAdmin):
    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(AssistantRun)
class AssistantRunAdmin(ReadOnlyPortAdmin):
    list_display = ("created_at", "call", "feature", "requested_role", "requested_by", "model", "status", "duration_ms")
    list_filter = ("feature", "status")
    search_fields = ("call__reference", "input_digest")
    readonly_fields = ("port", "call", "feature", "requested_by", "requested_role", "model", "input_digest",
                       "input_inventory", "output", "status", "error", "duration_ms", "created_at")


@admin.register(ExtractionReview)
class ExtractionReviewAdmin(ReadOnlyPortAdmin):
    port_field = "call__port"
    list_display = ("created_at", "call", "kind", "status", "validated_label", "validated_at")
    list_filter = ("kind", "status")
    readonly_fields = ("run", "call", "document", "kind", "proposed", "status", "validated", "validated_by",
                       "validated_label", "validated_at", "created_at")
