"""Periodic processing, run every minute by the `scheduler` service (manage.py run_scheduler)."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.request
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from ..models import WebhookDelivery
from .alerts import evaluate_all
from .milestones import apply_tacit_countersignatures
from .notifications import send_daily_digests
from .requests import expire_authorizations

log = logging.getLogger(__name__)


def deliver_webhooks(now=None, limit: int = 100) -> int:
    """Publish N1 journal events to third-party systems (single window / PCS), signed with HMAC."""
    now = now or timezone.now()
    sent = 0
    pending = (WebhookDelivery.objects.filter(status="PENDING", next_attempt_at__lte=now)
               .select_related("subscription", "entry", "entry__call", "entry__call__vessel")[:limit])
    for delivery in pending:
        entry = delivery.entry
        body = json.dumps({
            "event": entry.action, "seq": entry.seq, "at": entry.at.isoformat(), "hash": entry.hash,
            "call": entry.call.reference if entry.call_id else None,
            "vessel": {"imo": entry.call.vessel.imo, "name": entry.call.vessel.name} if entry.call_id else None,
            "summary": {"fr": entry.summary_fr, "en": entry.summary_en},
        }, ensure_ascii=False).encode("utf-8")
        signature = hmac.new(delivery.subscription.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        req = urllib.request.Request(delivery.subscription.url, data=body, method="POST", headers={
            "Content-Type": "application/json", "X-Fluxaa-Signature": f"sha256={signature}",
            "X-Fluxaa-Event": entry.action,
        })
        delivery.attempts += 1
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if 200 <= resp.status < 300:
                    delivery.status = "SENT"
                    delivery.sent_at = timezone.now()
                    sent += 1
                else:
                    raise RuntimeError(f"HTTP {resp.status}")
        except Exception as exc:  # retries with back-off, then FAILED after 8 attempts
            delivery.last_error = str(exc)[:300]
            delivery.next_attempt_at = now + timedelta(minutes=2 ** min(delivery.attempts, 8))
            if delivery.attempts >= 8:
                delivery.status = "FAILED"
        delivery.save()
    return sent


def _purge_ais_positions(now) -> int:
    """AIS reports past the port's retention (telemetry, not registry acts): once an hour is enough."""
    if now.minute >= 5:
        return 0
    from apps.ais.services import purge

    return purge(now)


def tick(now=None) -> dict:
    now = now or timezone.now()
    summary = {}
    for name, func in (
        ("tacit", apply_tacit_countersignatures),
        ("alerts", evaluate_all),
        ("expired", expire_authorizations),
        ("digests", send_daily_digests),
        ("webhooks", deliver_webhooks),
        ("ais_purge", _purge_ais_positions),
    ):
        try:
            with transaction.atomic():
                summary[name] = func(now)
        except Exception as exc:  # one failing step never blocks the others
            log.exception("Scheduler step %s failed", name)
            summary[name] = f"error: {exc}"
    return summary
