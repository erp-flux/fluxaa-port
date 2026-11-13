"""Version 1.5 — the catalogue changes applied to the ports already bootstrapped (the bootstrap at start-up creates
the new operation models, milestone types and document types; this migration does what the bootstrap never
does, because it never touches what a port holds):
* the common base M0 gets a new published version carrying the green lights of the naval base / security, the
  terminal and the principal (tasks 09b, 09c, 09d), the berth-safety line of the non-tanker calls (31b), the
  green-light flag of the harbour master's own line (09) and the liquid-bulk restriction of the tanker lines
  (29, 31) — the former version is retired, the calls created under it keep it (EF-5.8);
* the hold points receive the new requirements (naval base green light before the movement authorization and
  the berthing; terminal and principal green lights, berth safety and the cargo lines before the operations);
* the operation models of liquid bulk are marked as such (M1, M2, M3, M6, MA2), so that the other kinds of cargo
  are offered their own;
* the pending harbour master's green-light tasks of the existing calls are flagged as green lights.
"""
from django.db import migrations
from django.utils import timezone


def upgrade(apps, schema_editor):
    from apps.registry import catalog, catalog_cargo

    Port = apps.get_model("core", "Port")
    CallTemplate = apps.get_model("registry", "CallTemplate")
    TemplateVersion = apps.get_model("registry", "TemplateVersion")
    TemplateTask = apps.get_model("registry", "TemplateTask")
    HoldPoint = apps.get_model("registry", "HoldPoint")
    HoldPointRequirement = apps.get_model("registry", "HoldPointRequirement")
    Task = apps.get_model("registry", "Task")

    new_lines = {line[1]["number"]: line for line in catalog_cargo.GREEN_LIGHT_TASKS}
    copy_fields = ["number", "section_fr", "section_en", "title_fr", "title_en", "role", "co_roles", "joint", "nature",
                   "anchor", "offset_minutes", "timing_fr", "timing_en", "criticality", "confidentiality", "hold_basis",
                   "request_type_code", "request_side", "milestone_codes", "document_type_code", "auto_event",
                   "continuous", "per_vessel", "not_applicable_allowed", "berth_kinds", "green_light", "cargo_kinds"]
    for port in Port.objects.all():
        # liquid-bulk operation models
        for spec in catalog.TEMPLATES:
            if spec.get("cargo_kinds"):
                CallTemplate.objects.filter(port=port, code=spec["code"], cargo_kinds=[]).update(cargo_kinds=spec["cargo_kinds"])
        # a new version of the common base
        m0 = CallTemplate.objects.filter(port=port, code="M0").first()
        if m0 is None:
            continue
        current = m0.versions.filter(status="PUBLISHED").order_by("-number").first()
        if current is None:
            continue
        present = set(current.tasks.values_list("number", flat=True))
        if set(new_lines) <= present:
            continue
        version = TemplateVersion.objects.create(template=m0, number=current.number + 1, status="PUBLISHED",
                                                notes="FLX-CDC-002 v1.5 — feux verts (base navale, terminal, mandant), ligne 31b ; lignes 29 et 31 réservées au vrac liquide",
                                                published_at=timezone.now(), published_by=current.published_by)
        order = 0
        for tt in current.tasks.all().order_by("order", "number"):
            order += 1
            values = {f: getattr(tt, f) for f in copy_fields}
            if tt.number in catalog_cargo.GREEN_LIGHT_EXISTING:
                values["green_light"] = True
            if tt.number in catalog_cargo.LIQUID_ONLY_M0 and not values["cargo_kinds"]:
                values["cargo_kinds"] = ["LIQUID"]
            TemplateTask.objects.create(version=version, order=order, **values)
            # the new lines follow the harbour master's green light and the berth-safety line
            following = [n for n in ("09b", "09c", "09d") if tt.number == "09" and n not in present] + \
                        [n for n in ("31b",) if tt.number == "31" and n not in present]
            for number in following:
                section, spec_t = new_lines[number]
                anchor, offset, timing_fr, timing_en = catalog.TIMING[spec_t["timing"]]
                sec_fr, sec_en = catalog.SEC.get(section, ("", ""))
                order += 1
                TemplateTask.objects.create(
                    version=version, number=number, section_fr=sec_fr, section_en=sec_en, title_fr=spec_t["title_fr"],
                    title_en=spec_t["title_en"], role=spec_t["role"], co_roles=spec_t["co_roles"], joint=spec_t["joint"],
                    nature=spec_t["nature"], anchor=anchor, offset_minutes=offset, timing_fr=timing_fr, timing_en=timing_en,
                    criticality=spec_t["criticality"], confidentiality=spec_t["confidentiality"], hold_basis=spec_t["hold_basis"],
                    request_type_code=spec_t["request_type_code"], request_side=spec_t["request_side"],
                    milestone_codes=spec_t["milestone_codes"], document_type_code=spec_t["document_type_code"],
                    auto_event=spec_t["auto_event"], continuous=spec_t["continuous"], per_vessel=spec_t["per_vessel"],
                    not_applicable_allowed=spec_t["not_applicable_allowed"], berth_kinds=spec_t["berth_kinds"], order=order,
                    green_light=spec_t["green_light"], cargo_kinds=spec_t["cargo_kinds"],
                )
        current.status = "RETIRED"
        current.save(update_fields=["status"])
        # hold points
        for transition, refs in catalog_cargo.HOLD_POINT_ADDITIONS.items():
            hold_point = HoldPoint.objects.filter(port=port, transition=transition).first()
            if hold_point is None:
                continue
            for ref in refs:
                template_code, number = ref.split(":", 1)
                HoldPointRequirement.objects.get_or_create(hold_point=hold_point, template_code=template_code, task_number=number)
    # the harbour master's green light of the existing calls, on the panel
    Task.objects.filter(template_code="M0", number="09").update(green_light=True)


def downgrade(apps, schema_editor):
    """The new M0 version stays (a version is never deleted); the flags are cleared."""
    Task = apps.get_model("registry", "Task")
    Task.objects.filter(template_code="M0", number="09").update(green_light=False)


class Migration(migrations.Migration):
    dependencies = [("registry", "0016_generalisation_1_5"), ("core", "0007_generalisation_1_5")]
    operations = [migrations.RunPython(upgrade, downgrade)]
