"""Notifications (EF-6, EF-18): derived from an object or a deadline, never typed by hand.

Anti-noise rules:
  * one notification per event and per recipient (unique dedupe key);
  * real time only for blocking tasks and escalations; daily digest otherwise (user preference);
  * nobody can mute a blocking alert;
  * SMS for escalations only;
  * several alerts produced by the same evaluation for the same call are grouped per recipient.
"""
from __future__ import annotations

import json
import logging
import urllib.request

from django.conf import settings
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils import timezone, translation

from apps.core.models import User

from ..models import CallParty, Notification

log = logging.getLogger(__name__)


def users_for_roles(call, roles, *, exclude_user=None, organizations=None):
    """Active users holding one of *roles* on *call* (role exercised by the user AND held by the org), optionally
    within some organisations only. A draft call is known to its agency alone: nobody else is told about it."""
    now = timezone.now()
    roles = set(roles)
    if "*" in roles:
        roles = {"AGE", "TER", "CAP", "APO", "SVC", "ADM", "SUR", "INS", "COM", "DIR"}  # providers: own service only
    if call.status == "DRAFT":
        roles &= {"AGE"}
    parties = [p for p in CallParty.objects.filter(call=call, role__in=roles, revoked_at__isnull=True) if p.is_active_at(now)]
    if organizations is not None:
        parties = [p for p in parties if p.organization_id in set(organizations)]
    by_org: dict[int, set[str]] = {}
    for party in parties:
        by_org.setdefault(party.organization_id, set()).add(party.role)
    users = []
    for user in User.objects.filter(organization_id__in=by_org.keys(), is_active=True, is_integration=False):
        if set(user.roles or []) & by_org[user.organization_id]:
            if exclude_user is not None and user.pk == exclude_user.pk:
                continue
            users.append(user)
    return users


def notify(call, roles, *, key: str, title_fr: str, title_en: str, url: str = "", realtime: bool = False,
           blocking: bool = False, alert=None, exclude_user=None, sms: bool = False, organizations=None) -> int:
    """Create one notification per recipient for the event *key*. Returns the number created."""
    created = 0
    for user in users_for_roles(call, roles, exclude_user=exclude_user, organizations=organizations):
        try:
            with transaction.atomic():
                note = Notification.objects.create(
                    user=user, call=call, alert=alert, dedupe_key=key[:160], title_fr=title_fr[:300],
                    title_en=title_en[:300], url=url, realtime=realtime or blocking, blocking=blocking,
                )
        except IntegrityError:
            continue  # already notified for this event (anti-noise)
        created += 1
        if blocking or realtime or not user.notify_digest_only:
            _send_email_now(note)
        if sms and user.phone:
            send_sms(user.phone, note.title_en if (user.language or "fr") == "en" else note.title_fr)
            note.sms_sent_at = timezone.now()
            note.save(update_fields=["sms_sent_at"])
    return created


def notify_port_admins(port, *, key: str, title_fr: str, title_en: str, url: str = "") -> int:
    """A notification that concerns the port rather than one call — an organisation to complete, accounts to open:
    one per functional administrator of the port (``User.is_port_admin``), once per event *key*."""
    created = 0
    for user in User.objects.filter(organization__port=port, is_port_admin=True, is_active=True, is_integration=False):
        try:
            with transaction.atomic():
                note = Notification.objects.create(user=user, call=None, dedupe_key=key[:160], title_fr=title_fr[:300],
                                                   title_en=title_en[:300], url=url, realtime=True)
        except IntegrityError:
            continue  # already told
        created += 1
        _send_email_now(note)
    return created


def _send_email_now(note: Notification) -> None:
    user = note.user
    lang = user.language or (user.port.default_language if user.port else "fr")
    title = note.title_en if lang == "en" else note.title_fr
    link = f"{settings.SITE_URL}{note.url}" if note.url else settings.SITE_URL
    try:
        send_mail(f"[FLUXAA Port] {title}", f"{title}\n\n{link}\n", settings.DEFAULT_FROM_EMAIL, [user.email],
                  fail_silently=False)
        note.email_sent_at = timezone.now()
        note.save(update_fields=["email_sent_at"])
    except Exception as exc:  # pragma: no cover - depends on SMTP
        log.warning("E-mail notification to %s failed: %s", user.email, exc)


def send_sms(phone: str, text: str) -> bool:
    backend = settings.FLUXAA_SMS_BACKEND
    if backend == "disabled":
        return False
    if backend == "console":
        log.info("SMS to %s: %s", phone, text)
        return True
    if backend == "webhook" and settings.FLUXAA_SMS_WEBHOOK_URL:
        body = json.dumps({"to": phone, "text": text[:300]}).encode("utf-8")
        req = urllib.request.Request(
            settings.FLUXAA_SMS_WEBHOOK_URL, data=body, method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {settings.FLUXAA_SMS_WEBHOOK_TOKEN}"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                return True
        except Exception as exc:  # pragma: no cover
            log.warning("SMS gateway error: %s", exc)
    return False


def send_daily_digests(now=None) -> int:
    """One e-mail per user summarising the notifications not yet sent by e-mail."""
    now = now or timezone.now()
    pending = Notification.objects.filter(email_sent_at__isnull=True, digest_sent_at__isnull=True).select_related("user")
    by_user: dict[int, list[Notification]] = {}
    for note in pending:
        by_user.setdefault(note.user_id, []).append(note)
    sent = 0
    for notes in by_user.values():
        user = notes[0].user
        port = user.port
        if port is not None:
            import zoneinfo

            local = now.astimezone(zoneinfo.ZoneInfo(port.timezone))
            if local.hour != port.digest_hour_local:
                continue
        lang = user.language or (port.default_language if port else "fr")
        with translation.override(lang):
            lines = [f"- {n.title_en if lang == 'en' else n.title_fr} — {settings.SITE_URL}{n.url}" for n in notes]
            subject = "[FLUXAA Port] Daily summary" if lang == "en" else "[FLUXAA Port] Résumé quotidien"
        try:
            send_mail(subject, "\n".join(lines), settings.DEFAULT_FROM_EMAIL, [user.email])
        except Exception as exc:  # pragma: no cover
            log.warning("Digest to %s failed: %s", user.email, exc)
            continue
        Notification.objects.filter(pk__in=[n.pk for n in notes]).update(digest_sent_at=now)
        sent += 1
    return sent
