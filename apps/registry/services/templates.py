"""Template versioning (EF-5.8): the port administrator edits a draft, then publishes it.
A call keeps forever the versions in force at its creation."""
from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from ..models import TemplateTask, TemplateVersion
from . import journal


@transaction.atomic
def new_draft_version(template, user) -> TemplateVersion:
    if template.versions.filter(status=TemplateVersion.Status.DRAFT).exists():
        return template.versions.get(status=TemplateVersion.Status.DRAFT)
    source = template.published_version
    number = (template.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
    draft = TemplateVersion.objects.create(template=template, number=number, notes="")
    if source is not None:
        for task in source.tasks.all():
            task.pk = None
            task.id = None
            task._state.adding = True
            task.version = draft
            task.save()
    return draft


@transaction.atomic
def publish_version(version: TemplateVersion, user) -> TemplateVersion:
    if version.status != TemplateVersion.Status.DRAFT:
        raise ValidationError("Only a draft version can be published.")
    errors = []
    for task in version.tasks.all():
        try:
            task.full_clean(exclude=["version"])
            TemplateTask.clean(task)
        except ValidationError as exc:
            errors.append(f"{task.number}: {'; '.join(exc.messages)}")
    if errors:
        raise ValidationError(errors)
    version.template.versions.filter(status=TemplateVersion.Status.PUBLISHED).update(status=TemplateVersion.Status.RETIRED)
    version.status = TemplateVersion.Status.PUBLISHED
    version.published_at = timezone.now()
    version.published_by = user
    version.save(update_fields=["status", "published_at", "published_by"])
    journal.record(
        port=version.template.port, call=None, actor=None, role="ADMIN", action="template.published", obj=version,
        visible_roles=["CAP", "DIR", "APO"],
        summary_fr=f"Modèle {version.template.code} v{version.number} publié par {user}",
        summary_en=f"Template {version.template.code} v{version.number} published by {user}",
        payload={"template": version.template.code, "version": version.number, "tasks": version.tasks.count()},
    )
    return version
