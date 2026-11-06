"""Print the catalogue of the standard forms (docs/FORMULAIRES.md §2) from the code, as Markdown, grouped by the
party that issues each form. Run from the project root:  python scripts/forms_catalogue.py [--fr|--en]"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fluxaa.settings")

import django  # noqa: E402

django.setup()

from apps.registry import catalog  # noqa: E402
from apps.registry.services import forms  # noqa: E402

lang = 1 if "--en" in sys.argv else 0
labels = {d["code"]: (d["label_fr"], d["label_en"]) for d in catalog.DOCUMENT_TYPES}


def offered(form) -> str:
    parts = []
    if form.templates:
        parts.append(", ".join(sorted(form.templates)))
    if form.needs_link:
        parts.append("escale reliée" if lang == 0 else "linked call")
    return " ou ".join(parts) if lang == 0 and parts else (" or ".join(parts) if parts else ("toutes" if lang == 0 else "all"))


head = ("| Code | Formulaire | Standard de référence | Émis par | Signé par | Répond à | Type de document | Escales |",
        "| Code | Form | Reference standard | Issued by | Signed by | Answers | Document type | Calls |")[lang]
print(head)
print("|---|---|---|---|---|---|---|---|")
for code, label, members in forms.grouped(list(forms.FORMS.values())):
    print(f"| **{code}** | **{label[lang]}** ({len(members)}) | | | | | | |")
    for f in members:
        signers = ", ".join(f"{role} ({lbl[lang]})" for role, lbl in f.signers)
        answers = ", ".join(f"`{a}`" for a in f.answers) or "—"
        print(f"| `{f.code}` | {f.title[lang]}" + (f" — {f.purpose[lang]}" if f.purpose else "") +
              f" | {f.standard[lang]} | {', '.join(sorted(f.roles))} | {signers} | {answers} | `{f.document_type}` {labels[f.document_type][lang]} | {offered(f)} |")
print()
print(f"{len(forms.FORMS)} formulaires" if lang == 0 else f"{len(forms.FORMS)} forms")
