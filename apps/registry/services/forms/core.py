"""Standard forms of a call — every kind of cargo since 1.5 —, generated from the registry in ONE structure (docs/FORMULAIRES.md).

Every form shares the same frame: a header (port, call, vessel, berth or stage, dates, form number), a body made
of sections (fields, tables, checklists, text, a verification QR code), a signature block (one column per signing
role) and a sealed footer (generation time, journal sequence and hash of the registry at that moment). What the
registry knows is pre-filled; what it does not know is left blank for the people who complete and sign the paper.
A form filed into the call becomes a generated document (hash, versions, signatures) like the statement of facts.

Every party issues, from the platform, the documents the call asks of it — the tasks "provide a document" of the
templates and the decisions on the requests addressed to it — and the platform keeps them in the call's archive.
The forms are grouped by the party that issues them (``Form.family``): agency, vessel, terminal, harbour master,
port authority, customs / immigration / health, security, marine services, surveyor / laboratory, owner /
charterer, providers. Structures follow the industry references named on each form — ISGOTT (6th edition) for
the ship/shore interface, the OCIMF Ship to Ship Transfer Guide for STS, IMO FAL forms and the ISPS Code, the WHO
Maritime Declaration of Health (IHR 2005), MARPOL (advance waste notification, waste delivery receipt, bunker
delivery note), the BWM Convention (ballast water reporting form), API MPMS chapter 17 / EI HM for quantity, BIMCO
laytime definitions for the NOR and the time sheet, IMO resolution A.960 for the pilot card. Checklists reproduce
the parts and the kind of checks of those references in the platform's own words: the port keeps using its
licensed editions for the full item lists.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from django.core.files.base import ContentFile
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.core.roles import role_label

from ...models import JournalEntry, MilestoneSignature, PortCall
from ..errors import PermissionRefused, RuleViolation

# ------------------------------------------------------------------------------------------------ building blocks
Pair = tuple[str, str]  # (French, English)


def F(fr: str, en: str, value=None, *, wide: bool = False, source: str = "") -> dict:
    """A labelled field: pre-filled when *value* is known, a blank line otherwise. *source* names, for the
    specification, where the value comes from (model field, milestone code, computation); empty = completed
    by hand on the printed form."""
    return {"fr": fr, "en": en, "value": value, "wide": wide, "source": source}


def fields(title: Pair, items: list[dict], *, note: Pair | None = None) -> dict:
    return {"kind": "fields", "title": title, "items": items, "note": note}


def table(title: Pair, columns: list[Pair], rows: list[list], *, blank_rows: int = 0, note: Pair | None = None,
          source: str = "") -> dict:
    return {"kind": "table", "title": title, "columns": columns, "rows": rows, "blank": range(blank_rows), "note": note,
            "source": source}


def checklist(title: Pair, items: list[Pair], *, columns: list[Pair] | None = None, note: Pair | None = None) -> dict:
    return {"kind": "checklist", "title": title, "items": items,
            "columns": columns or [("Navire", "Ship"), ("Terre", "Shore")], "note": note}


def text(title: Pair, paragraphs: list[Pair], *, note: Pair | None = None) -> dict:
    return {"kind": "text", "title": title, "paragraphs": paragraphs, "note": note}


def qr(title: Pair, url: str, caption: Pair, *, note: Pair | None = None) -> dict:
    """A QR code of a public verification address (authorizations): drawn at rendering time."""
    return {"kind": "qr", "title": title, "url": url, "caption": caption, "note": note}


def dt(value) -> str | None:
    return f"{value:%d/%m/%Y %H:%M} UTC" if value else None


def d(value) -> str | None:
    return f"{value:%d/%m/%Y}" if value else None


def _m(call: PortCall, code: str):
    return call.milestones.filter(type__code=code, is_conflict=False).order_by("declared_at").first()


def _mt(call: PortCall, code: str) -> str | None:
    m = _m(call, code)
    return dt(m.declared_at) if m else None


def _stage(call: PortCall):
    return call.stages.filter(status="CURRENT").select_related("berth").first() or call.stages.select_related("berth").order_by("order").first()


def _where(call: PortCall) -> str:
    stage = _stage(call)
    if call.berth_id:
        return f"{call.berth.code} — {call.berth.name_fr}"
    if stage is not None:
        return stage.get_berth_kind_display()
    return call.get_requested_berth_kind_display()


def _party(call: PortCall, role: str) -> str | None:
    party = call.parties.filter(role=role, revoked_at__isnull=True).select_related("organization").first()
    return party.organization.name if party else None


def _parties(call: PortCall, role: str) -> str | None:
    names = [p.organization.name for p in call.parties.filter(role=role, revoked_at__isnull=True).select_related("organization")]
    return ", ".join(names) or None


def _vessel(call: PortCall) -> str:
    return f"{call.vessel.name} — IMO {call.vessel.imo}"


def _quantity(call: PortCall) -> str | None:
    return f"{call.quantity} {call.quantity_unit}" if call.quantity else None


OPERATION_LABELS = {
    "M1": "déchargement / discharge", "M2": "chargement / loading", "M3": "transbordement STS / STS transfer",
    "M4": "soutage / bunkering", "MB1": "déchargement de vrac sec / dry bulk discharge", "MB2": "chargement de vrac sec / dry bulk loading",
    "MC1": "opérations conteneurs / container operations", "MG1": "marchandises diverses / general cargo",
    "MR1": "roulier / ro-ro", "MX1": "autre opération / other operation",
}


def _operation(call: PortCall) -> str:
    """The operation of the call, named after its templates (every kind of cargo since 1.5)."""
    codes = call.template_codes
    for code, label in OPERATION_LABELS.items():
        if code in codes:
            return label
    return "escale / call"


def _partner(call: PortCall) -> str | None:
    partner = call.linked_call
    return f"{partner.vessel.name} — IMO {partner.vessel.imo} ({partner.reference})" if partner else None


def _request(call: PortCall, type_code: str):
    """The most recent request of this type on the call (decided first)."""
    qs = call.requests.filter(type__code=type_code).select_related("type", "requester_org", "provider_org")
    return qs.exclude(decided_at=None).order_by("-decided_at").first() or qs.order_by("-created_at").first()


def _authorization(call: PortCall, type_code: str):
    """The latest authorization of this type on the call, cancelled ones excluded."""
    for auth in call.authorizations.filter(type_code=type_code).select_related("request", "berth").order_by("-signed_at"):
        if not auth.is_cancelled:
            return auth
    return None


def _request_rows(req) -> list[dict]:
    """The request's form values as pre-filled fields, labelled after its type's schema."""
    from ...templatetags.fluxaa import request_fields  # labelled and formatted like the screen

    if req is None:
        return []
    return [F(label, label, value, wide=len(str(value)) > 60, source=f"ServiceRequest.data[{key}]")
            for (label, value), key in zip(request_fields(req), _request_keys(req))]


def _request_keys(req) -> list[str]:
    schema = [f for f in (req.type.form_schema or []) if isinstance(f, dict) and f.get("key")]
    data = req.data or {}
    keys = [f["key"] for f in schema if f["key"] in data]
    return keys + [k for k in data if k not in keys]


def identification(call: PortCall, *extra: dict) -> dict:
    """The identification block most forms open with."""
    return fields(("Navire et escale", "Vessel and call"), [
        F("Navire", "Vessel", _vessel(call), source="Vessel.name, Vessel.imo"),
        F("Pavillon / type", "Flag / type", " — ".join(filter(None, [call.vessel.flag, call.vessel.vessel_type])) or None, source="Vessel.flag, Vessel.vessel_type"),
        F("Escale / voyage", "Call / voyage", f"{call.reference}" + (f" — voy. {call.voyage_number}" if call.voyage_number else ""), source="PortCall.reference, PortCall.voyage_number"),
        F("Port", "Port", f"{call.port.name} ({call.port.code})", source="Port.name, Port.code"),
        F("Poste / zone", "Berth / area", _where(call), source="PortCall.berth ou CallStage.berth_kind de l'étape en cours"),
        F("Agence", "Agency", str(call.agency), source="PortCall.agency (Organization.name)"),
        *extra,
    ])


# ------------------------------------------------------------------------------------------------ the forms
FAMILIES: list[tuple[str, Pair]] = [
    ("AGE", ("Agence maritime", "Shipping agency")), ("NAV", ("Navire / capitaine", "Vessel / master")),
    ("TER", ("Terminal / dépôt", "Terminal / depot")), ("CAP", ("Capitainerie", "Harbour master")),
    ("APO", ("Autorité portuaire", "Port authority")), ("ADM", ("Douanes, immigration, santé", "Customs, immigration, health")),
    ("SUR", ("Sûreté", "Security")), ("SVC", ("Services nautiques", "Marine services")),
    ("INS", ("Inspecteur et laboratoire", "Surveyor and laboratory")), ("COM", ("Armateur / affréteur", "Owner / charterer")),
    ("PRE", ("Prestataires", "Service providers")),
]


@dataclass
class Form:
    code: str
    document_type: str
    title: Pair
    standard: Pair
    roles: frozenset  # roles that may generate and file the form
    signers: list[tuple[str, Pair]]
    build: Callable[[PortCall], list[dict]]
    intro: Pair | None = None
    landscape: bool = False
    confidentiality_note: Pair | None = None
    extra: dict = field(default_factory=dict)
    family: str = ""  # the party that issues the form (grouping on the screen and in the specification)
    templates: frozenset = frozenset()  # offered only when one of these templates is on the call (empty = always)
    needs_link: bool = False  # also offered when the call has a partner call (STS, double banking)
    answers: tuple = ()  # task references ("M0:12") or request types ("REQ:BERTH") this form answers
    purpose: Pair | None = None  # one line: what the form is for (catalogue, specification)
    cargo_kinds: frozenset = frozenset()  # offered only for these kinds of cargo (empty = every kind) — v1.5

    @property
    def family_label(self) -> Pair:
        return dict(FAMILIES).get(self.family, (self.family, self.family))


FORMS: dict[str, Form] = {}


def _register(form: Form) -> Form:
    if not form.family:
        form.family = sorted(form.roles)[0]
    FORMS[form.code] = form
    return form


# ------------------------------------------------------------------------------------------------ rendering, filing
def offered(call: PortCall, form: Form) -> bool:
    """Does this call call for the form (its kind of cargo, its operations and modules), whoever asks?"""
    if form.cargo_kinds and (call.cargo_kind or "LIQUID") not in form.cargo_kinds:
        return False
    if not form.templates and not form.needs_link:
        return True
    codes = set(call.template_codes)
    if form.templates and codes & form.templates:
        return True
    return bool(form.needs_link and call.linked_call_id)


def available(call: PortCall, actor) -> list[Form]:
    """The forms this actor may generate on this call (its roles, the call's operations)."""
    return [form for form in FORMS.values() if set(actor.roles) & form.roles and offered(call, form)]


def for_call(call: PortCall) -> list[Form]:
    """Every form the call calls for, whatever the role (the catalogue screen)."""
    return [form for form in FORMS.values() if offered(call, form)]


def grouped(forms: list[Form]) -> list[tuple[str, Pair, list[Form]]]:
    """Forms by issuing party, in the order of FAMILIES."""
    groups = []
    for code, label in FAMILIES:
        members = [f for f in forms if f.family == code]
        if members:
            groups.append((code, label, members))
    return groups


def context(call: PortCall, code: str, actor=None, *, about=None) -> dict:
    """The rendering context of a form. *about* is the object the form is issued for when the registry holds
    several of its kind on the call (the request just decided, the milestone just recorded): a builder that
    accepts it draws on that one instead of the latest."""
    from apps.core import mfa  # QR drawing (SVG) shared with the second factor and the access links

    form = FORMS.get(code)
    if form is None:
        raise RuleViolation(_("Unknown form."))
    last = JournalEntry.objects.filter(call=call).order_by("-seq").first()
    number = call.documents.filter(type__code=form.document_type, title__startswith=form.title[0]).count() + 1
    stage = _stage(call)
    sections = _build(form, call, about)
    for s in sections:
        if s["kind"] == "qr":
            s["image"] = mfa.svg_data_uri(mfa.qr_svg(s["url"]))
    return {
        "form": form, "call": call, "vessel": call.vessel, "port": call.port, "stage": stage, "where": _where(call),
        "arrival": (f"ATA {dt(call.ata)}" if call.ata else f"ETA {dt(call.eta)}"), "multi_stage": call.stages.count() > 1,
        "sections": sections, "generated_at": timezone.now(),
        "registry_seq": last.seq if last else 0, "registry_hash": last.hash if last else "",
        "number": f"{form.code}-{call.reference}-{number:02d}",
        "signers": [(role, role_label(role), fr, en) for role, (fr, en) in form.signers],
        "generated_by": actor.label if actor is not None else "",
        "signature_count": MilestoneSignature.objects.filter(milestone__call=call).count(),
    }


def _build(form: Form, call: PortCall, about) -> list[dict]:
    import inspect

    if about is not None and "about" in inspect.signature(form.build).parameters:
        return form.build(call, about=about)
    return form.build(call)


def render(call: PortCall, code: str, actor=None, *, about=None) -> str:
    return render_to_string("registry/reports/form.html", context(call, code, actor, about=about))


def issue(call: PortCall, actor, code: str, *, as_role: str | None = None, confidentiality: str = "",
          counterpart_role: str = "", audience_roles: list[str] | None = None, about=None):
    """File the form into the call as a generated document (hash, version, signatures), under the actor's role
    (*as_role* when the actor holds several of the form's roles). A later issue of the same form becomes the next
    version of the same document; the earlier one stays readable."""
    from ..documents import upload_document

    form = FORMS.get(code)
    if form is None:
        raise RuleViolation(_("Unknown form."))
    roles = set(actor.roles) & form.roles
    if not roles:
        raise PermissionRefused(_("This form is not generated by your role."))
    if not offered(call, form):
        raise RuleViolation(_("This form does not apply to the operations of this call."))
    html = render(call, code, actor, about=about)
    content = ContentFile(html.encode("utf-8"), name=f"{call.reference}_{form.code.lower()}.html")
    content.content_type = "text/html"
    title = f"{form.title[0]} / {form.title[1]} — {call.reference}"
    previous = call.documents.filter(type__code=form.document_type, title=title, generated=True,
                                     status__in=["ISSUED", "SIGNED"]).first()
    role = as_role if as_role in roles else sorted(roles)[0]
    return upload_document(call, actor, form.document_type, content, title=title, generated=True, previous=previous,
                           as_role=role, confidentiality=confidentiality, counterpart_role=counterpart_role,
                           audience_roles=audience_roles)


def auto_issue(call: PortCall, actor, code: str, **kwargs):
    """File a form as the consequence of another act of the same party — the written act of a decision, the
    notice of readiness once tendered, the safety checklist once signed by both sides, the time sheet with the
    statement of facts. The act itself is never blocked by its paperwork: a form that cannot be generated is
    logged and left to be issued by hand from the forms page."""
    import logging

    from django.db import transaction

    try:
        with transaction.atomic():
            return issue(call, actor, code, **kwargs)
    except Exception:  # noqa: BLE001 — see the docstring
        logging.getLogger("fluxaa.forms").exception("form %s could not be filed automatically on %s", code, call.reference)
        return None
