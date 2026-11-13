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

from ..models import ACTIVE_STATUSES, EXPIRABLE_STATUSES, CallStatus, PortCall, WebhookDelivery
from .alerts import evaluate_all
from .milestones import apply_tacit_countersignatures
from .notifications import notify, send_daily_digests
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


# Reminders of the validity of an announcement (FLX-CDC-002 v1.5, EXG-R-02): before it runs out, then every day
# it is overrun by a call already alongside (the overrun is counted for billing)
VALIDITY_REMINDERS_H = (72, 24)


def watch_validity(now=None) -> dict:
    """Every call announced for a period: reminded to the agency and the harbour master 72 h and 24 h before the
    period runs out; made obsolete when it runs out before the vessel is alongside; signalled daily when it is
    overrun by a vessel already alongside or working."""
    from .calls import call_url, expire_call

    now = now or timezone.now()
    reminded = expired = overrun = 0
    calls = PortCall.objects.filter(valid_until__isnull=False, status__in=[CallStatus.DRAFT, *ACTIVE_STATUSES]) \
        .select_related("vessel", "port")
    for call in calls:
        left = call.valid_until - now
        if left.total_seconds() <= 0:
            if call.status in EXPIRABLE_STATUSES:
                expired += int(expire_call(call))
            else:
                # alongside or working past the validity: never cut off, signalled once a day
                reminded_key = f"validity:{call.pk}:overrun:{now:%Y%m%d}"
                if notify(call, ["AGE", "CAP", "APO"], key=reminded_key, url=call_url(call),
                          title_fr=f"{call.reference} ({call.vessel.name}) : validité de l'annonce dépassée depuis le "
                                   f"{call.valid_until:%d/%m %H:%M} UTC — le dépassement est compté ; l'agence régularise l'annonce",
                          title_en=f"{call.reference} ({call.vessel.name}): validity of the announcement overrun since "
                                   f"{call.valid_until:%Y-%m-%d %H:%M} UTC — the overrun is counted; the agency regularises the announcement"):
                    overrun += 1
            continue
        hours_left = left.total_seconds() / 3600
        for hours in sorted(VALIDITY_REMINDERS_H):  # the nearest deadline first: one reminder per threshold
            if hours_left <= hours:
                if notify(call, ["AGE", "CAP"], key=f"validity:{call.pk}:{hours}h", url=call_url(call), realtime=hours == 24,
                          title_fr=f"{call.reference} ({call.vessel.name}) : l'annonce expire le {call.valid_until:%d/%m %H:%M} UTC "
                                   f"(dans {int(hours_left)} h) — clôturer l'escale, ou la refaire après l'échéance",
                          title_en=f"{call.reference} ({call.vessel.name}): the announcement expires on {call.valid_until:%Y-%m-%d %H:%M} UTC "
                                   f"(in {int(hours_left)} h) — close the call, or announce it again after the deadline"):
                    reminded += 1
                break
    return {"reminded": reminded, "expired": expired, "overrun": overrun}


def tick(now=None) -> dict:
    now = now or timezone.now()
    summary = {}
    for name, func in (
        ("tacit", apply_tacit_countersignatures),
        ("alerts", evaluate_all),
        ("expired", expire_authorizations),
        ("validity", watch_validity),
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
