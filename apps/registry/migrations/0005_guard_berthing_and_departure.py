"""Existing ports: guard the berthing and departure milestones by their own hold points.

Before this version, recording "first line", "all fast", "vessels alongside" (STS), "last line" or "departed" was not
guarded: skipping the pilot milestone bypassed the movement authorization and the departure clearance. New ports get
these settings from the reference catalogue (bootstrap_ports); this migration gives them to ports already installed,
without overriding a hold point that the port administrator has set on these milestones.
"""
from django.db import migrations

GUARDS = {
    "BERTHING": (["FIRST_LINE", "ALL_FAST", "STS_ALONGSIDE"], ["M0:25", "M3:3.03", "MA2:A2.02"]),
    "DEPARTURE": (["LAST_LINE", "DEPARTED"], ["M0:34"]),
}


def forwards(apps, schema_editor):
    if schema_editor.connection.alias != "default":
        return  # the registry lives in the main database only (the N4 database is migrated separately)
    Port = apps.get_model("core", "Port")
    MilestoneType = apps.get_model("registry", "MilestoneType")
    HoldPoint = apps.get_model("registry", "HoldPoint")
    HoldPointRequirement = apps.get_model("registry", "HoldPointRequirement")
    for port in Port.objects.all():
        for transition, (milestones, requirements) in GUARDS.items():
            MilestoneType.objects.filter(port=port, code__in=milestones, hold_point="").update(hold_point=transition)
            hold_point, created = HoldPoint.objects.get_or_create(port=port, transition=transition)
            if created:
                for reference in requirements:
                    template_code, number = reference.split(":", 1)
                    HoldPointRequirement.objects.get_or_create(hold_point=hold_point, template_code=template_code,
                                                               task_number=number)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_attempt_window"),
        ("registry", "0004_provider_and_movement_hold_points"),
    ]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
