"""N4 security domain — stored in its own database, encrypted with its own keys (CDC EF-12.4).

Nothing here references the operational registry by foreign key: the call is identified by its
numeric id and reference only. The operational database therefore contains no trace of N4 objects,
not even their existence (acceptance scenario S5).
"""
from __future__ import annotations

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.core.guards import AppendOnlyModel, NoDeleteModel


class SecureItem(NoDeleteModel):
    class Kind(models.TextChoices):
        ARMED_GUARDS = "ARMED_GUARDS", _("Armed guards")
        ESCORT = "ESCORT", _("Naval escort")
        SECURITY_PLAN = "SECURITY_PLAN", _("Security plan / declaration")
        INCIDENT = "INCIDENT", _("Security incident")
        OTHER = "OTHER", _("Other security matter")

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", _("Submitted")
        UNDER_REVIEW = "UNDER_REVIEW", _("Under review")
        APPROVED = "APPROVED", _("Approved")
        APPROVED_COND = "APPROVED_COND", _("Approved with conditions")
        REFUSED = "REFUSED", _("Refused")
        EXECUTED = "EXECUTED", _("Executed")
        CLOSED = "CLOSED", _("Closed")

    reference = models.CharField(max_length=40, unique=True)
    port_code = models.CharField(max_length=10, db_index=True)
    call_id = models.BigIntegerField(db_index=True)
    call_reference = models.CharField(max_length=30)
    vessel_name = models.CharField(max_length=120)
    kind = models.CharField(max_length=14, choices=Kind.choices)
    status = models.CharField(max_length=14, choices=Status.choices, default=Status.SUBMITTED)
    submitted_by_id = models.BigIntegerField()
    submitted_by_label = models.CharField(max_length=200)
    submitted_role = models.CharField(max_length=3)
    submitted_org_label = models.CharField(max_length=200)
    submitted_at = models.DateTimeField(default=timezone.now)
    due_at = models.DateTimeField(null=True, blank=True)
    payload_enc = models.TextField(help_text="Fernet-encrypted JSON (N4 keys)")
    decision_enc = models.TextField(blank=True)
    decided_by_id = models.BigIntegerField(null=True, blank=True)
    decided_by_label = models.CharField(max_length=200, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    embarked_at = models.DateTimeField(null=True, blank=True)
    disembarked_at = models.DateTimeField(null=True, blank=True)
    anti_intrusion_confirmed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-submitted_at"]
        verbose_name = _("security record (N4)")
        verbose_name_plural = _("security records (N4)")

    def __str__(self) -> str:
        return self.reference


class SecureAttachment(AppendOnlyModel):
    item = models.ForeignKey(SecureItem, on_delete=models.PROTECT, related_name="attachments")
    name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64)
    data_enc = models.BinaryField(help_text="Encrypted content (N4 keys)")
    uploaded_by_id = models.BigIntegerField()
    uploaded_by_label = models.CharField(max_length=200)
    at = models.DateTimeField(default=timezone.now)


class SecureChainHead(models.Model):
    port_code = models.CharField(max_length=10, unique=True)
    last_seq = models.PositiveBigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, default="0" * 64)


class SecureSequence(models.Model):
    port_code = models.CharField(max_length=10)
    year = models.PositiveSmallIntegerField()
    last_value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["port_code", "year"], name="uniq_secure_sequence")]


class SecureAccessLog(AppendOnlyModel):
    """Nominative log of every access to N4 data, chained (EF-12.4)."""

    port_code = models.CharField(max_length=10, db_index=True)
    seq = models.PositiveBigIntegerField()
    item = models.ForeignKey(SecureItem, on_delete=models.PROTECT, null=True, blank=True, related_name="accesses")
    at = models.DateTimeField(default=timezone.now)
    user_id = models.BigIntegerField()
    user_label = models.CharField(max_length=200)
    role = models.CharField(max_length=3)
    action = models.CharField(max_length=20)
    detail = models.CharField(max_length=300, blank=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    notified = models.BooleanField(default=False)
    prev_hash = models.CharField(max_length=64)
    hash = models.CharField(max_length=64, unique=True)

    class Meta:
        ordering = ["-seq"]
        constraints = [models.UniqueConstraint(fields=["port_code", "seq"], name="uniq_secure_log_seq")]
