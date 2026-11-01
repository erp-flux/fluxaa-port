from django.contrib import admin

from apps.core.admin import PortScopedAdmin

from .models import VesselPosition, VesselStatic


@admin.register(VesselStatic)
class VesselStaticAdmin(PortScopedAdmin):
    list_display = ("mmsi", "name", "imo", "call_sign", "destination", "updated_at", "port")
    search_fields = ("mmsi", "name", "imo", "call_sign")
    readonly_fields = ("port", "mmsi", "imo", "name", "call_sign", "ship_type", "destination", "draught_m", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(VesselPosition)
class VesselPositionAdmin(PortScopedAdmin):
    list_display = ("mmsi", "observed_at", "latitude", "longitude", "speed_kn", "course_deg", "nav_status", "source", "port")
    search_fields = ("mmsi",)
    list_filter = ("source",)
    readonly_fields = [f.name for f in VesselPosition._meta.fields]

    def has_add_permission(self, request):
        return False
