"""AIS board (EF-3.6, ENF-8): the public position reports of the vessels in and around the port waters.

These records are telemetry, not acts of the registry: they are kept for ``Port.ais_retention_days`` and then
purged, and they never change a milestone — the corroboration of EF-3.6 only raises alerts.
"""
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import Port


class VesselStatic(models.Model):
    """What a vessel broadcasts about itself (AIS message 5 / 24): one row per MMSI and port, updated in place."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ais_statics")
    mmsi = models.CharField(max_length=9)
    imo = models.CharField(max_length=7, blank=True)
    name = models.CharField(max_length=120, blank=True)
    call_sign = models.CharField(max_length=20, blank=True)
    ship_type = models.PositiveSmallIntegerField(null=True, blank=True)
    destination = models.CharField(max_length=40, blank=True)
    draught_m = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    updated_at = models.DateTimeField()

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port", "mmsi"], name="uniq_ais_static_per_port")]
        verbose_name = _("AIS vessel data")
        verbose_name_plural = _("AIS vessel data")

    def __str__(self) -> str:
        return f"{self.name or self.mmsi} ({self.port.code})"


class VesselPosition(models.Model):
    """One position report (AIS message 1, 2, 3, 18, 19 or 27)."""

    port = models.ForeignKey(Port, on_delete=models.PROTECT, related_name="ais_positions")
    mmsi = models.CharField(max_length=9)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)
    speed_kn = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    course_deg = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    heading_deg = models.PositiveSmallIntegerField(null=True, blank=True)
    nav_status = models.PositiveSmallIntegerField(null=True, blank=True)
    observed_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    source = models.CharField(max_length=40)

    class Meta:
        indexes = [models.Index(fields=["port", "mmsi", "-observed_at"]), models.Index(fields=["port", "-observed_at"])]
        constraints = [models.UniqueConstraint(fields=["port", "mmsi", "observed_at"], name="uniq_ais_report")]
        verbose_name = _("AIS position")
        verbose_name_plural = _("AIS positions")

    def __str__(self) -> str:
        return f"{self.mmsi} @ {self.observed_at:%Y-%m-%d %H:%M}"
