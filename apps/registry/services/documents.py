"""Documents (EF-7): fingerprint, versions, signatures, the bill-of-lading lock, generated documents."""
from __future__ import annotations

import hashlib
import mimetypes
from datetime import date

from django.conf import settings
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.crypto import seal
from apps.core.roles import ANY_PARTY, role_label

from ..models import (
    Confidentiality,
    Document,
    DocumentSignature,
    DocumentStatus,
    DocumentType,
    Nature,
    TaskStatus,
    Transition,
)
from . import holdpoints, journal
from .calls import call_url, with_refusal_log
from .errors import PermissionRefused, RuleViolation, ensure_open
from .notifications import notify
from .rights import N2_SUPERVISORS, is_document_issuer, roles_with
from .tasks import system_complete

ALLOWED_EXTENSIONS = {
    ".pdf", ".png", ".jpg", ".jpeg", ".webp", ".heic", ".tif", ".tiff", ".doc", ".docx", ".xls", ".xlsx", ".csv",
    ".txt", ".eml", ".msg", ".html", ".xml", ".json", ".zip",
}


def visibility_roles(doc: Document) -> list[str]:
    if doc.confidentiality == Confidentiality.N1:
        return ["*"] + ([doc.issuer_role] if doc.issuer_role == "PRE" else [])
    if doc.confidentiality == Confidentiality.N3:
        return sorted({doc.issuer_role, doc.counterpart_role} - {""})
    return sorted(set(N2_SUPERVISORS) | {"COM", doc.issuer_role, *(doc.required_signers or []),
                                         *(doc.type.audience_roles or [])})


# Types a browser may display inline; recognised from the content itself, never from what the sender declares.
SNIFFED_TYPES = ("application/pdf", "image/png", "image/jpeg", "image/webp")


def content_type(data: bytes, declared: str) -> str:
    """The type stored for a file: recognised from its first bytes for the types shown inline; any other file
    keeps its declared type, except that a file claiming to be one of those types without being one is stored as
    plain bytes (it will only ever be downloaded)."""
    if b"%PDF-" in data[:1024]:
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    declared = (declared or "").split(";")[0].strip().lower()
    if not declared or declared in SNIFFED_TYPES:
        return "application/octet-stream"
    return declared


def _read(uploaded) -> tuple[bytes, str, str]:
    name = getattr(uploaded, "name", "document")
    if hasattr(uploaded, "chunks"):
        data = b"".join(uploaded.chunks())
    elif isinstance(uploaded, (bytes, bytearray)):
        data = bytes(uploaded)
    else:
        data = uploaded.read()
    declared = getattr(uploaded, "content_type", "") or mimetypes.guess_type(name)[0] or ""
    return data, name, content_type(data, declared)


def upload_document(call, actor, type_code: str, uploaded, *, title: str = "", confidentiality: str = "",
                    counterpart_role: str = "", task=None, previous: Document | None = None, client_uuid=None,
                    deferred: bool = False, as_role: str | None = None, generated: bool = False,
                    filename: str = "") -> Document:
    if client_uuid:
        existing = Document.objects.filter(client_uuid=client_uuid).first()
        if existing is not None:
            return existing
    dtype = DocumentType.objects.filter(port=call.port, code=type_code, is_active=True).first()
    if dtype is None:
        raise RuleViolation(_("Unknown document type: %(code)s") % {"code": type_code})
    if call.is_terminal_state and not generated:
        raise RuleViolation(_("The call is closed."))
    if dtype.generated and not generated:
        raise RuleViolation(_("This document is generated from the registry, never uploaded (EF-7.3)."))
    if actor.is_system:
        role = "SYS"
    else:
        # the document type alone names its issuers (single emitter): a task never widens them
        allowed = set(dtype.issuer_roles or []) or roles_with("C", "document")
        if task is not None and task.role != ANY_PARTY:
            allowed &= {task.role, *task.co_roles}
        role = actor.pick_role(allowed, as_role)
    if task is not None:
        _check_task(call, task, dtype)
    level = confidentiality or dtype.default_confidentiality
    if level == Confidentiality.N3 and not counterpart_role and dtype.audience_roles:
        counterpart_role = dtype.audience_roles[0]
    if level == Confidentiality.N4:
        raise RuleViolation(_("N4 documents are filed in the security space only."))
    if level == Confidentiality.N3 and not counterpart_role:
        raise RuleViolation(_("A bilateral (N3) document names its counterpart."))
    data, name, mime = _read(uploaded)
    name = filename or name
    ext = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise RuleViolation(_("File type not accepted (%(ext)s).") % {"ext": ext or "?"})
    if len(data) > settings.FLUXAA_MAX_UPLOAD_MB * 1024 * 1024:
        raise RuleViolation(_("File too large (max %(mb)s MB).") % {"mb": settings.FLUXAA_MAX_UPLOAD_MB})
    if not data:
        raise RuleViolation(_("The file is empty."))
    if previous is not None:
        if previous.call_id != call.id or previous.type_id != dtype.id:
            raise RuleViolation(_("A new version concerns the same call and document type."))
        if previous.status not in (DocumentStatus.ISSUED, DocumentStatus.SIGNED):
            raise RuleViolation(_("Only an issued or signed document can be replaced."))
        if not is_document_issuer(actor, previous):
            raise PermissionRefused(_("Only the issuer publishes a new version."))

    def _do() -> Document:
        if dtype.is_bill_of_lading:
            holdpoints.check(call, Transition.BL_ISSUE)  # non-configurable lock (EF-7.4, S8)
        digest = hashlib.sha256(data).hexdigest()
        now = timezone.now()
        doc = Document(
            call=call, type=dtype, title=title or dtype.label, version=(previous.version + 1) if previous else 1,
            previous=previous, status=DocumentStatus.ISSUED, confidentiality=level, counterpart_role=counterpart_role,
            issuer_role=role, issuer_org=actor.org, issuer_user=actor.user if not actor.is_system else None,
            issuer_master=actor.master, issuer_label=actor.label, original_name=name[:255], mime_type=mime[:120],
            size=len(data), sha256=digest, required_signers=list(dtype.signer_roles or []), generated=generated,
            retention_until=date(now.year + dtype.retention_years, now.month, min(now.day, 28)),
            task=task, deferred=deferred, client_uuid=client_uuid, issued_at=now,
        )
        doc.file.save(name, ContentFile(data), save=False)
        doc.save()
        if previous is not None:
            previous.status = DocumentStatus.REPLACED
            previous.save(update_fields=["status"])
        journal.record(
            port=call.port, call=call, actor=actor, role=role, action="document.issued", obj=doc,
            visible_roles=visibility_roles(doc),
            summary_fr=f"Document émis : {doc.title_in('fr')} (v{doc.version}) — SHA-256 {digest[:12]}…"
            + (" [saisie différée]" if deferred else ""),
            summary_en=f"Document issued: {doc.title_in('en')} (v{doc.version}) — SHA-256 {digest[:12]}…"
            + (" [deferred entry]" if deferred else ""),
            payload={"type": dtype.code, "sha256": digest, "version": doc.version, "size": len(data)},
        )
        _complete_document_tasks(call, actor, doc, task)
        return doc

    doc = with_refusal_log(call, actor, f"document:{type_code}", _do)
    if doc.required_signers:
        notify(call, doc.required_signers, key=f"document:{doc.pk}:sign", title_fr=f"{call.reference} : {doc.title_in('fr')} à signer",
               title_en=f"{call.reference}: {doc.title_in('en')} to sign", url=call_url(call) + "#documents")
    return doc


def _check_task(call, task, dtype) -> None:
    """A document completes a task only if it is the document that task expects (EF-5): never a decision, a
    signature, a request, a milestone or a document of another type."""
    if task.call_id != call.id:
        raise RuleViolation(_("This task belongs to another call."))
    if task.status != TaskStatus.PENDING:
        raise RuleViolation(_("This task is already closed."))
    if task.document_type_code:
        if task.document_type_code != dtype.code:
            expected = DocumentType.objects.filter(port=call.port, code=task.document_type_code).first()
            raise RuleViolation(_("Task %(task)s expects another document: %(type)s.")
                                % {"task": task.code, "type": expected.label if expected else task.document_type_code})
    elif not (task.is_ad_hoc and task.nature == Nature.F):
        raise RuleViolation(_("Task %(task)s is not completed by providing a document.") % {"task": task.code})


def _complete_document_tasks(call, actor, doc: Document, task) -> None:
    if doc.required_signers:
        return  # tasks are completed when every required signature is obtained
    if task is not None:
        targets = [task]
    else:
        candidates = [t for t in call.tasks.filter(document_type_code=doc.type.code, status=TaskStatus.PENDING)
                      if t.role == doc.issuer_role or doc.issuer_role in (t.co_roles or [])]
        # several tasks expect this type: the issuer designates the task explicitly
        targets = candidates if len(candidates) == 1 else []
    for t in targets:
        if t.status == TaskStatus.PENDING and (actor.is_system or t.role == ANY_PARTY
                                               or doc.issuer_role in {t.role, *t.co_roles}):
            system_complete(t, actor, evidence=f"document:{doc.pk}", role=doc.issuer_role if doc.issuer_role != "SYS" else "")


@transaction.atomic
def sign_document(doc: Document, actor, *, signature_image: str = "", as_role: str | None = None) -> DocumentSignature:
    ensure_open(doc.call)
    if doc.status not in (DocumentStatus.ISSUED,):
        raise RuleViolation(_("Only an issued document awaiting signatures can be signed."))
    already = set(doc.signatures.values_list("role", flat=True))
    pending = [r for r in doc.required_signers if r not in already]
    role = actor.pick_role(pending, as_role)
    if signature_image and (not signature_image.startswith("data:image/png;base64,") or len(signature_image) > 400_000):
        raise RuleViolation(_("Invalid signature image."))
    now = timezone.now()
    sig = DocumentSignature.objects.create(
        document=doc, role=role, user=actor.user, master=actor.master, signer_label=actor.label, signed_at=now,
        document_sha256=doc.sha256, signature_image=signature_image,
        seal=seal({"document": doc.pk, "sha256": doc.sha256, "role": role, "by": actor.label, "at": now.isoformat()}),
    )
    journal.record(port=doc.call.port, call=doc.call, actor=actor, role=role, action="document.signed", obj=doc,
                   visible_roles=visibility_roles(doc),
                   summary_fr=f"{doc.title_in('fr')} signé par {actor.label} ({role_label(role)})",
                   summary_en=f"{doc.title_in('en')} signed by {actor.label} ({role})")
    if set(doc.required_signers) <= (already | {role}):
        doc.status = DocumentStatus.SIGNED
        doc.save(update_fields=["status"])
        journal.record(port=doc.call.port, call=doc.call, actor=actor, role=role, action="document.fully_signed", obj=doc,
                       visible_roles=visibility_roles(doc), summary_fr=f"{doc.title_in('fr')} : toutes les signatures obtenues — figé",
                       summary_en=f"{doc.title_in('en')}: all signatures obtained — frozen")
        if doc.task_id:
            targets = [doc.task]
        else:
            candidates = list(doc.call.tasks.filter(document_type_code=doc.type.code, status=TaskStatus.PENDING))
            targets = candidates if len(candidates) == 1 else []
        for t in targets:
            if t is not None and t.status == TaskStatus.PENDING:
                system_complete(t, actor, evidence=f"document:{doc.pk}", role=doc.issuer_role)
    return sig


@transaction.atomic
def cancel_document(doc: Document, actor, reason: str) -> Document:
    ensure_open(doc.call)
    if not is_document_issuer(actor, doc):
        raise PermissionRefused(_("Only the issuer cancels a document."))
    if not reason.strip():
        raise RuleViolation(_("A reason is required."))
    if doc.status not in (DocumentStatus.ISSUED, DocumentStatus.SIGNED, DocumentStatus.DRAFT):
        raise RuleViolation(_("This document can no longer be cancelled."))
    doc.status = DocumentStatus.CANCELLED
    doc.cancel_reason = reason
    doc.save(update_fields=["status", "cancel_reason"])
    journal.record(port=doc.call.port, call=doc.call, actor=actor, role=doc.issuer_role, action="document.cancelled",
                   obj=doc, visible_roles=visibility_roles(doc), summary_fr=f"{doc.title_in('fr')} annulé — {reason}",
                   summary_en=f"{doc.title_in('en')} cancelled — {reason}")
    return doc
