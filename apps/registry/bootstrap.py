"""Load the reference catalogue into a port (idempotent).

Re-running never overwrites what the port's administrator has changed: templates already published
are kept, and reference rows are only created when missing (use ``refresh=True`` to realign labels).
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.core.models import Berth, Port

from . import catalog
from .models import (
    CallTemplate,
    DocumentType,
    HoldPoint,
    HoldPointRequirement,
    InterruptionCause,
    MilestoneType,
    RequestType,
    TemplateTask,
    TemplateVersion,
)


def _upsert(model, lookup: dict, values: dict, refresh: bool):
    obj = model.objects.filter(**lookup).first()
    if obj is None:
        return model.objects.create(**lookup, **values), True
    if refresh:
        for key, value in values.items():
            setattr(obj, key, value)
        obj.save()
    return obj, False


@transaction.atomic
def bootstrap_port(code: str, *, refresh: bool = False, user=None) -> dict:
    spec = catalog.PORTS.get(code)
    if spec is None:
        raise ValueError(f"Unknown port {code}; known: {', '.join(catalog.PORTS)}")
    port, _ = Port.objects.get_or_create(
        code=code, defaults={"name": spec["name"], "country": spec["country"], "timezone": spec["timezone"],
                             "default_language": spec["default_language"]},
    )
    counts = {"berths": 0, "templates": 0, "tasks": 0, "milestone_types": 0, "request_types": 0,
              "document_types": 0, "causes": 0, "hold_points": 0}
    box = spec.get("map") or {}
    if box and port.map_lat_min is None and port.map_lon_min is None:  # never over the administrator's own box
        port.map_lat_min, port.map_lat_max = box["lat_min"], box["lat_max"]
        port.map_lon_min, port.map_lon_max = box["lon_min"], box["lon_max"]
        port.save(update_fields=["map_lat_min", "map_lat_max", "map_lon_min", "map_lon_max"])
    for berth_code, kind, fr, en, lat, lon, radius in spec["berths"]:
        berth, created = _upsert(Berth, {"port": port, "code": berth_code},
                                 {"kind": kind, "name_fr": fr, "name_en": en, "latitude": lat, "longitude": lon,
                                  "radius_m": radius,
                                  "notes": "Nom, limites et position à confirmer par la capitainerie / to be confirmed by the harbour master"},
                                 refresh)
        if not created and berth.latitude is None and berth.longitude is None and lat is not None:
            berth.latitude, berth.longitude, berth.radius_m = lat, lon, radius
            berth.save(update_fields=["latitude", "longitude", "radius_m"])
        counts["berths"] += int(created)

    for spec_t in catalog.TEMPLATES:
        template, _ = _upsert(CallTemplate, {"port": port, "code": spec_t["code"]}, {
            "kind": spec_t["kind"], "name_fr": spec_t["name_fr"], "name_en": spec_t["name_en"],
            "description_fr": spec_t.get("description_fr", ""), "description_en": spec_t.get("description_en", ""),
            "berth_kinds": spec_t.get("berth_kinds", []), "requires_linked_call": spec_t.get("requires_linked_call", False),
            "never_alone": spec_t.get("never_alone", False), "order": spec_t["order"],
        }, refresh)
        if template.versions.exists():
            continue
        version = TemplateVersion.objects.create(template=template, number=1, notes="FLX-SPEC-002 v1.0")
        for order, (section, task) in enumerate(spec_t["tasks"], start=1):
            anchor, offset, timing_fr, timing_en = catalog.TIMING[task["timing"]]
            sec_fr, sec_en = catalog.SEC.get(section, ("", ""))
            TemplateTask.objects.create(
                version=version, number=task["number"], section_fr=sec_fr, section_en=sec_en,
                title_fr=task["title_fr"], title_en=task["title_en"], role=task["role"], co_roles=task["co_roles"],
                joint=task["joint"], nature=task["nature"], anchor=anchor, offset_minutes=offset, timing_fr=timing_fr,
                timing_en=timing_en, criticality=task["criticality"], confidentiality=task["confidentiality"],
                hold_basis=task["hold_basis"], request_type_code=task["request_type_code"],
                request_side=task["request_side"], milestone_codes=task["milestone_codes"],
                document_type_code=task["document_type_code"], auto_event=task["auto_event"],
                continuous=task["continuous"], per_vessel=task["per_vessel"],
                not_applicable_allowed=task["not_applicable_allowed"], berth_kinds=task["berth_kinds"], order=order,
            )
            counts["tasks"] += 1
        version.status = TemplateVersion.Status.PUBLISHED
        version.published_at = timezone.now()
        version.published_by = user
        version.save()
        counts["templates"] += 1

    for order, m in enumerate(catalog.MILESTONES, start=1):
        values = {k: v for k, v in m.items() if k != "code"}
        values["order"] = order
        _obj, created = _upsert(MilestoneType, {"port": port, "code": m["code"]}, values, refresh)
        counts["milestone_types"] += int(created)

    for order, r in enumerate(catalog.REQUEST_TYPES, start=1):
        values = {k: v for k, v in r.items() if k != "code"}
        values["order"] = order
        _obj, created = _upsert(RequestType, {"port": port, "code": r["code"]}, values, refresh)
        counts["request_types"] += int(created)

    for order, d in enumerate(catalog.DOCUMENT_TYPES, start=1):
        values = {k: v for k, v in d.items() if k != "code"}
        values["order"] = order
        _obj, created = _upsert(DocumentType, {"port": port, "code": d["code"]}, values, refresh)
        counts["document_types"] += int(created)

    for order, (cause_code, attribution, fr, en) in enumerate(catalog.CAUSES, start=1):
        _obj, created = _upsert(InterruptionCause, {"port": port, "code": cause_code}, {
            "attributable_to": attribution, "label_fr": fr, "label_en": en, "requires_reason": cause_code == "OTHER",
            "order": order,
        }, refresh)
        counts["causes"] += int(created)

    for transition, requirements in catalog.HOLD_POINTS.items():
        hold_point, created = HoldPoint.objects.get_or_create(port=port, transition=transition)
        if created or refresh:
            for ref in requirements:
                template_code, number = ref.split(":", 1)
                HoldPointRequirement.objects.get_or_create(hold_point=hold_point, template_code=template_code,
                                                           task_number=number)
        counts["hold_points"] += int(created)
    return {"port": port.code, **counts}
