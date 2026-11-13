"""Version 1.6 — the announcement adapts to the operation (FLX-CDC-002 v1.6, EXG-R-11):
* each operation model carries the questions the announcement asks when it is chosen (``intake_schema``, the
  grammar of the request forms); the ports already bootstrapped receive the catalogue's questions for every model
  that has none yet — a port that wrote its own keeps them;
* the call keeps the answers (``operation_details``), shown on its overview, exported and used to pre-fill the
  requests the model's tasks raise.
"""
from django.db import migrations, models


def install_intake(apps, schema_editor):
    from apps.registry import catalog

    CallTemplate = apps.get_model("registry", "CallTemplate")
    for template in CallTemplate.objects.all():
        if not template.intake_schema and catalog.INTAKE.get(template.code):
            template.intake_schema = catalog.INTAKE[template.code]
            template.save(update_fields=["intake_schema"])


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0017_catalogue_1_5"),
    ]

    operations = [
        migrations.AddField(
            model_name="calltemplate",
            name="intake_schema",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='List of {"key", "label_fr", "label_en", "type", "required", "options", "help_fr", "help_en"} — the same grammar as the form of a request type; a key shared with the form of a request raised by this model\'s tasks pre-fills that request.',
                verbose_name="questions asked at the announcement",
            ),
        ),
        migrations.AddField(
            model_name="portcall",
            name="operation_details",
            field=models.JSONField(
                blank=True,
                default=dict,
                verbose_name="information declared for each operation",
            ),
        ),
        migrations.RunPython(install_intake, migrations.RunPython.noop),
    ]
