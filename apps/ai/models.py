"""Traces of the AI assistance (CDC EF-17).

Every request sent to the AI provider leaves an append-only ``AssistantRun``: who asked, on which
call, which feature, the SHA-256 of the exact payload sent and an inventory of the objects it was
built from — never their content twice. An extraction never writes into the registry: it creates an
``ExtractionReview`` that a person validates or dismisses, field by field.
"""
from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.guards import AppendOnlyModel, NoDeleteModel


class AssistantRun(AppendOnlyModel):
    class Feature(models.TextChoices):
        EXTRACT = "EXTRACT", _("Extraction from a document")
        REVIEW = "REVIEW", _("Consistency review of the call")
        SUMMARY = "SUMMARY", _("Summary of an exchange")
        REMARKS = "REMARKS", _("Draft remarks for the statement of facts")
        BRIEF = "BRIEF", _("Brief of the port")
        QUESTION = "QUESTION", _("Question on the registry of the port")

    class Status(models.TextChoices):
        OK = "OK", _("Completed")
        ERROR = "ERROR", _("Failed")

    port = models.ForeignKey("core.Port", on_delete=models.PROTECT, related_name="+")
    call = models.ForeignKey("registry.PortCall", on_delete=models.PROTECT, related_name="assistant_runs",
                             null=True, blank=True, help_text=_("Empty for the port-level features (brief, question)."))
    feature = models.CharField(max_length=8, choices=Feature.choices)
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    requested_role = models.CharField(max_length=3)
    model = models.CharField(max_length=80)
    input_digest = models.CharField(_("fingerprint of the data sent (SHA-256)"), max_length=64)
    input_inventory = models.JSONField(_("objects the request was built from"), default=list)
    output = models.JSONField(default=dict)
    status = models.CharField(max_length=5, choices=Status.choices)
    error = models.CharField(max_length=300, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("assistant run")
        verbose_name_plural = _("assistant runs")

    def __str__(self) -> str:
        return f"{self.call or self.port} — {self.get_feature_display()} ({self.created_at:%Y-%m-%d %H:%M})"


class ExtractionReview(NoDeleteModel):
    """Values proposed by the assistant: shown as "pre-filled" and saved only after a person validates them."""

    class Status(models.TextChoices):
        PROPOSED = "PROPOSED", _("Awaiting validation")
        APPLIED = "APPLIED", _("Validated")
        DISMISSED = "DISMISSED", _("Dismissed")

    run = models.OneToOneField(AssistantRun, on_delete=models.PROTECT, related_name="review")
    call = models.ForeignKey("registry.PortCall", on_delete=models.PROTECT, related_name="extraction_reviews")
    document = models.ForeignKey("registry.Document", on_delete=models.PROTECT, related_name="extraction_reviews")
    kind = models.CharField(max_length=20)
    proposed = models.JSONField(default=dict)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.PROPOSED)
    validated = models.JSONField(null=True, blank=True)
    validated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
                                     related_name="+")
    validated_label = models.CharField(max_length=200, blank=True)
    validated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("extraction awaiting validation")
        verbose_name_plural = _("extractions awaiting validation")

    def save(self, *args, **kwargs):
        if not self._state.adding and self.pk:
            original = ExtractionReview.objects.filter(pk=self.pk).values("status", "proposed").first()
            if original and (original["status"] != self.Status.PROPOSED or original["proposed"] != self.proposed):
                from apps.core.guards import ImmutableRecordError

                raise ImmutableRecordError("A validated or dismissed extraction is frozen.")
        super().save(*args, **kwargs)
