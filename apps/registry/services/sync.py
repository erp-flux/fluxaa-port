"""Offline synchronisation (EF-14): entries captured in the field are replayed in chronological order.

Each entry carries a client UUID (idempotency), the declared time of the fact, and the time it was
captured on the device. The server adds its own time: the double timestamp is kept, and anything
received late is flagged "saisie différée". A conflict never overwrites: it opens a dispute.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime

from django.core.files.base import ContentFile
from django.utils.dateparse import parse_datetime
from django.utils.translation import gettext as _

from ..models import EntrySource, Measurement, Milestone, Task
from .documents import upload_document
from .errors import RegistryError, RuleViolation
from .measurements import add_pumping_entry, add_value
from .milestones import countersign_milestone, record_milestone
from .rights import milestone_visible
from .tasks import complete_task, sign_task

SUPPORTED = {"milestone", "countersign", "measurement_value", "pumping", "photo", "task_complete", "task_sign"}


def _when(value, field: str) -> datetime:
    parsed = parse_datetime(value) if isinstance(value, str) else value
    if parsed is None:
        raise RuleViolation(_("Invalid date for %(f)s.") % {"f": field})
    return parsed


def process_batch(call, actor, entries: list[dict]) -> list[dict]:
    """Replay a batch; returns one result per entry, in the order received."""
    ordered = sorted(enumerate(entries), key=lambda pair: str(pair[1].get("device_recorded_at") or ""))
    results: dict[int, dict] = {}
    for index, entry in ordered:
        kind = entry.get("kind")
        client_uuid = entry.get("client_uuid")
        result = {"client_uuid": client_uuid, "kind": kind}
        try:
            if kind not in SUPPORTED:
                raise RuleViolation(_("Unsupported entry kind."))
            uid = uuid.UUID(str(client_uuid)) if client_uuid else None
            device_time = _when(entry["device_recorded_at"], "device_recorded_at") if entry.get("device_recorded_at") else None
            if kind == "milestone":
                related = None
                if entry.get("related_client_uuid"):
                    related = Milestone.objects.filter(call=call, client_uuid=entry["related_client_uuid"]).first()
                elif entry.get("related_id"):
                    related = Milestone.objects.filter(call=call, pk=entry["related_id"]).first()
                obj = record_milestone(
                    call, actor, entry["type"], _when(entry["declared_at"], "declared_at"),
                    cause_code=entry.get("cause", ""), cause_reason=entry.get("cause_reason", ""),
                    note=entry.get("note", ""), related=related, source=EntrySource.OFFLINE,
                    device_recorded_at=device_time, client_uuid=uid, as_role=entry.get("role"),
                )
                result.update({"status": "conflict" if obj.is_conflict else "ok", "id": obj.pk, "deferred": obj.deferred})
            elif kind == "countersign":
                milestone = Milestone.objects.filter(call=call, pk=entry.get("milestone_id")).first()
                if milestone is None or not milestone_visible(actor, milestone):
                    raise RuleViolation(_("Unknown milestone."))
                sig = countersign_milestone(milestone, actor, contest=bool(entry.get("contest")),
                                            comment=entry.get("comment", ""), as_role=entry.get("role"))
                result.update({"status": "ok", "id": sig.pk})
            elif kind == "measurement_value":
                measurement = Measurement.objects.filter(call=call, pk=entry.get("measurement_id")).first()
                if measurement is None:
                    raise RuleViolation(_("Unknown measurement."))
                value = add_value(measurement, actor, entry["party"], entry["value"],
                                  temperature=entry.get("temperature_c"), density=entry.get("density"),
                                  declared_at=_when(entry.get("declared_at") or entry["device_recorded_at"], "declared_at"),
                                  note=entry.get("note", ""), source=EntrySource.OFFLINE, device_recorded_at=device_time,
                                  client_uuid=uid)
                result.update({"status": "ok", "id": value.pk, "deferred": value.deferred})
            elif kind == "pumping":
                row = add_pumping_entry(call, actor, declared_at=_when(entry["declared_at"], "declared_at"),
                                        manifold_pressure_bar=entry.get("pressure_bar"), flow_rate_m3h=entry.get("rate_m3h"),
                                        temperature_c=entry.get("temperature_c"), note=entry.get("note", ""),
                                        source=EntrySource.OFFLINE, device_recorded_at=device_time, client_uuid=uid,
                                        device_id=entry.get("device_id", ""))
                result.update({"status": "ok", "id": row.pk, "deferred": row.deferred})
            elif kind == "photo":
                raw = entry.get("data_url", "")
                if not raw.startswith("data:image/") or ";base64," not in raw:
                    raise RuleViolation(_("Invalid photo."))
                header, encoded = raw.split(";base64,", 1)
                ext = header.split("/")[-1].replace("jpeg", "jpg")[:4]
                content = ContentFile(base64.b64decode(encoded), name=f"photo_{(client_uuid or 'field')}.{ext}")
                content.content_type = header[5:]
                doc = upload_document(call, actor, entry.get("document_type", "PHOTO"), content,
                                      title=entry.get("title", "Photo"), client_uuid=uid, deferred=True,
                                      as_role=entry.get("role"))
                result.update({"status": "ok", "id": doc.pk})
            elif kind in ("task_complete", "task_sign"):
                task = Task.objects.filter(call=call, pk=entry.get("task_id")).first()
                if task is None:
                    raise RuleViolation(_("Unknown task."))
                if kind == "task_complete":
                    complete_task(task, actor, note=entry.get("note", ""), role=entry.get("role"))
                else:
                    sign_task(task, actor, role=entry.get("role"), comment=entry.get("note", ""))
                result.update({"status": "ok", "id": task.pk})
        except RegistryError as exc:
            result.update({"status": "refused", "code": exc.code, "message": exc.message, "details": exc.details})
        except (KeyError, ValueError) as exc:
            result.update({"status": "refused", "code": "invalid", "message": f"{type(exc).__name__}: {exc}"})
        results[index] = result
    return [results[i] for i in range(len(entries))]
