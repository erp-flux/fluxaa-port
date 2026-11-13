"""Generate the developer specification dossier (docs/spec/*.md) from the code itself.

The dossier FLX-SPEC-003 has two kinds of chapters: the ones written by hand (screens, business rules,
notifications, non-functional requirements) and the ones GENERATED here from the code — data model,
enumerations and state machines, roles and rights, catalogues, standard forms, API, routes and actions. The
generated chapters are the reference: a developer who changes a model, a template or a form regenerates them
(`python manage.py generate_spec`) and the dossier never drifts from the product.

    python manage.py generate_spec            # writes docs/spec/*.md (generated chapters only)
    python manage.py generate_spec --check    # exits 1 when a generated chapter would change (CI)
"""
from __future__ import annotations

import ast
import inspect
import json
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import models
from django.urls import URLPattern, URLResolver, get_resolver
from django.utils import translation

GENERATED_NOTE = ("> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : "
                  "modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.\n")

APPS = ["core", "registry", "ais", "ai", "secure"]
APP_TITLES = {"core": "core — port, organisations, utilisateurs, postes",
              "registry": "registry — le registre des escales",
              "ais": "ais — tableau AIS",
              "ai": "ai — assistance IA (traces)",
              "secure": "secure — domaine sûreté N4 (base distincte)"}


# ------------------------------------------------------------------------------------------------ helpers
def md_escape(text) -> str:
    if text is None:
        return ""
    return str(text).replace("|", "\\|").replace("\n", " ").strip()


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for row in rows:
        out.append("| " + " | ".join(md_escape(c) for c in row) + " |")
    return "\n".join(out) + "\n"


def both(fr_getter, en_getter) -> str:
    """Return 'FR / EN' from two language-dependent getters."""
    with translation.override("fr"):
        fr = str(fr_getter())
    with translation.override("en"):
        en = str(en_getter())
    return fr if fr == en else f"{fr} / {en}"


def first_line(doc: str | None) -> str:
    if not doc:
        return ""
    return inspect.cleandoc(doc).split("\n\n")[0].replace("\n", " ").rstrip(".")


# ------------------------------------------------------------------------------------------------ 01 data model
_ENUMS: dict[frozenset, str] = {}


def enum_registry() -> dict[frozenset, str]:
    """Map the set of values of every TextChoices of the project to its name (for the field rules)."""
    if _ENUMS:
        return _ENUMS
    from apps.core.roles import Role

    _ENUMS[frozenset(Role.values)] = "Role"
    for app_label in APPS:
        module = apps.get_app_config(app_label).models_module
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, models.TextChoices) and obj is not models.TextChoices:
                _ENUMS.setdefault(frozenset(obj.values), name)
        for model in apps.get_app_config(app_label).get_models():
            for name, obj in vars(model).items():
                if inspect.isclass(obj) and issubclass(obj, models.TextChoices):
                    _ENUMS.setdefault(frozenset(obj.values), f"{model.__name__}.{name}")
    return _ENUMS


def field_type(f) -> str:
    kind = f.get_internal_type()
    if isinstance(f, models.ForeignKey):
        return f"FK → {f.related_model.__name__}"
    if isinstance(f, models.OneToOneField):
        return f"1–1 → {f.related_model.__name__}"
    if isinstance(f, models.ManyToManyField):
        return f"M–N → {f.related_model.__name__}"
    extra = ""
    if isinstance(f, models.CharField) and f.max_length:
        extra = f"({f.max_length})"
    elif isinstance(f, models.DecimalField):
        extra = f"({f.max_digits},{f.decimal_places})"
    return kind.replace("Field", "") + extra


def field_rules(f) -> str:
    rules = []
    if f.primary_key:
        return "clé primaire (auto)"
    if getattr(f, "auto_now_add", False):
        return "horodatage automatique à la création ; non modifiable"
    if getattr(f, "auto_now", False):
        return "horodatage automatique à chaque enregistrement"
    if f.unique:
        rules.append("unique")
    if getattr(f, "null", False):
        rules.append("nullable")
    if getattr(f, "blank", False) and not getattr(f, "null", False) and not isinstance(f, models.BooleanField):
        rules.append("peut être vide")
    if f.has_default() and not callable(f.default):
        rules.append(f"défaut `{f.default!r}`")
    elif f.has_default() and callable(f.default):
        rules.append(f"défaut `{getattr(f.default, '__name__', 'callable')}()`")
    if getattr(f, "editable", True) is False:
        rules.append("non modifiable")
    if getattr(f, "db_index", False) and not f.unique:
        rules.append("indexé")
    if f.choices:
        name = enum_registry().get(frozenset(v for v, _l in f.choices))
        if name:
            rules.append(f"énumération `{name}` (ch. 2)")
        else:
            values = ", ".join(f"`{v}`" for v, _l in f.choices[:12]) + (" …" if len(f.choices) > 12 else "")
            rules.append(f"valeurs : {values}")
    if isinstance(f, (models.ForeignKey, models.OneToOneField)):
        rules.append(f"on_delete `{f.remote_field.on_delete.__name__}`")
    return " ; ".join(rules)


def guard_kind(model) -> str:
    names = [c.__name__ for c in model.__mro__]
    if "AppendOnlyModel" in names:
        return "ajout seul (ni UPDATE ni DELETE en base)"
    if "NoDeleteModel" in names:
        return "sans suppression (UPDATE autorisé, DELETE refusé en base)"
    return "ordinaire"


def gen_data_model() -> str:
    out = ["# 1. Modèle de données\n", GENERATED_NOTE,
           "\nChaque entité est décrite par ses champs (type, règles), ses contraintes et son garde-fou d'intégrité. "
           "Les libellés sont donnés en français / anglais tels que l'interface les affiche. Les énumérations sont au "
           "chapitre 2, les règles d'écriture au chapitre 5.\n"]
    for app_label in APPS:
        config = apps.get_app_config(app_label)
        out.append(f"\n## 1.{APPS.index(app_label) + 1} Application `{APP_TITLES[app_label]}`\n")
        for model in config.get_models():
            if model._meta.proxy or model._meta.abstract:
                continue
            meta = model._meta
            out.append(f"\n### `{model.__name__}` — table `{meta.db_table}`\n")
            doc = first_line(model.__doc__)
            if doc and not doc.startswith(model.__name__ + "("):
                out.append(f"{doc}\n\n")
            out.append(f"Garde-fou : {guard_kind(model)}. Base : `{'secure' if app_label == 'secure' else 'default'}`.\n\n")
            rows = []
            for f in meta.get_fields():
                if not getattr(f, "concrete", False) or f.auto_created and not f.concrete:
                    continue
                if f.many_to_many and f.auto_created:
                    continue
                label = both(lambda f=f: getattr(f, "verbose_name", f.name), lambda f=f: getattr(f, "verbose_name", f.name))
                help_text = both(lambda f=f: getattr(f, "help_text", ""), lambda f=f: getattr(f, "help_text", ""))
                rows.append([f"`{f.name}`", field_type(f), label if label != f.name.replace("_", " ") else "", field_rules(f), help_text])
            out.append(md_table(["Champ", "Type", "Libellé FR / EN", "Règles", "Aide"], rows))
            constraints = []
            for c in meta.constraints:
                fields = ", ".join(getattr(c, "fields", []) or [])
                constraints.append(f"`{c.name}`" + (f" ({fields})" if fields else "") + (" — unicité" if c.__class__.__name__ == "UniqueConstraint" else ""))
            for ut in meta.unique_together:
                constraints.append("unicité (" + ", ".join(ut) + ")")
            for idx in meta.indexes:
                constraints.append("index (" + ", ".join(idx.fields) + ")")
            if meta.ordering:
                constraints.append("tri par défaut : " + ", ".join(meta.ordering))
            if constraints:
                out.append("\nContraintes et index : " + " ; ".join(constraints) + ".\n")
            props = []
            for name, member in vars(model).items():
                if isinstance(member, property) and member.fget and member.fget.__doc__:
                    props.append(f"`{name}` — {first_line(member.fget.__doc__)}")
                elif inspect.isfunction(member) and not name.startswith("_") and member.__doc__ and name not in ("save", "clean"):
                    props.append(f"`{name}()` — {first_line(member.__doc__)}")
            if props:
                out.append("\nPropriétés et méthodes documentées : " + " ; ".join(props) + ".\n")
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 02 enumerations
def gen_enums() -> str:
    from apps.registry import models as rm

    out = ["# 2. Énumérations, statuts et cycles de vie\n", GENERATED_NOTE,
           "\nValeurs stockées en base (code) et libellés affichés (FR / EN). Les graphes de transitions sont ceux que "
           "les services refusent de contourner (`_set_status`, `REQUEST_TRANSITIONS`).\n"]
    seen = set()
    for app_label in APPS:
        module = apps.get_app_config(app_label).models_module
        enums = []
        for name, obj in vars(module).items():
            if inspect.isclass(obj) and issubclass(obj, models.TextChoices) and obj is not models.TextChoices and obj not in seen:
                enums.append((name, obj))
                seen.add(obj)
        for model in apps.get_app_config(app_label).get_models():
            for name, obj in vars(model).items():
                if inspect.isclass(obj) and issubclass(obj, models.TextChoices) and obj not in seen:
                    enums.append((f"{model.__name__}.{name}", obj))
                    seen.add(obj)
        if app_label == "core":
            from apps.core.roles import Role

            enums.insert(0, ("Role (apps/core/roles.py)", Role))
            seen.add(Role)
        if not enums:
            continue
        out.append(f"\n## 2.{APPS.index(app_label) + 1} Application `{app_label}`\n")
        for name, enum in enums:
            out.append(f"\n### `{name}`\n")
            doc = first_line(enum.__doc__)
            if doc and "An enumeration" not in doc and not doc.startswith("str("):
                out.append(doc + "\n\n")
            rows = []
            for member in enum:
                rows.append([f"`{member.value}`", member.name, both(lambda m=member: m.label, lambda m=member: m.label)])
            out.append(md_table(["Code", "Nom", "Libellé FR / EN"], rows))
    out.append("\n## 2.9 Cycle de vie d'une escale (`CALL_TRANSITIONS`)\n\n")
    out.append(md_table(["Depuis", "Vers (autorisé)"], [[f"`{k}`", ", ".join(f"`{v}`" for v in sorted(vs)) or "— (terminal)"]
                                                        for k, vs in rm.CALL_TRANSITIONS.items()]))
    out.append("\nChaîne opérationnelle le long de laquelle un jalon fait avancer l'escale (`OPERATIONAL_CHAIN`) : "
               + " → ".join(f"`{s}`" for s in rm.OPERATIONAL_CHAIN) + ".\n\nStatuts « actifs » (`ACTIVE_STATUSES`, escales en cours) : "
               + ", ".join(f"`{s}`" for s in rm.ACTIVE_STATUSES) + ".\n")
    out.append("\n## 2.10 Cycle de vie d'une demande (`REQUEST_TRANSITIONS`)\n\n")
    out.append(md_table(["Depuis", "Vers (autorisé)"], [[f"`{k}`", ", ".join(f"`{v}`" for v in sorted(vs)) or "— (terminal)"]
                                                        for k, vs in rm.REQUEST_TRANSITIONS.items()]))
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 03 rights
def gen_rights() -> str:
    from apps.core import roles as R
    from apps.registry.services import rights

    out = ["# 3. Rôles et droits\n", GENERATED_NOTE,
           "\nLes droits viennent du **rôle d'une organisation sur l'escale** (`CallParty`), jamais d'une personne. "
           "La matrice ci-dessous (FLX-SPEC-001 §5) est appliquée côté serveur par `services/rights.py` ; l'interface "
           "n'ajoute aucun droit, elle masque ce qui est refusé. Verbes : C créer · V voir · S saisir/modifier · "
           "A approuver/décider · Cs contresigner · Ct contester · K clore · E exporter.\n"]
    out.append("\n## 3.1 Les douze rôles\n\n")
    out.append(md_table(["Code", "Libellé FR / EN", "Groupes"], [
        [f"`{r.value}`", both(lambda r=r: r.label, lambda r=r: r.label), ", ".join(g for g, members in [
            ("vue d'ensemble des tâches", R.OVERVIEW_ROLES), ("décideur (second facteur)", R.DECISION_ROLES),
            ("lecture seule commerciale", R.READ_ONLY_ROLES), ("export", R.EXPORT_ROLES), ("journal des accès", R.AUDIT_ROLES),
            ("domaine N4", R.N4_ROLES), ("sans tableau de bord", R.NO_DASHBOARD_ROLES)] if r.value in members)]
        for r in R.Role]))
    out.append(f"\nPseudo-rôle `{R.ANY_PARTY}` dans les gabarits : « la partie à l'origine / toute partie ».\n")
    out.append("\n## 3.2 Matrice objets × rôles (`rights.MATRIX`)\n\n")
    role_codes = list(R.ALL_ROLES)
    rows = []
    for kind, table in rights.MATRIX.items():
        rows.append([f"`{kind}`"] + ["".join(sorted(table.get(r, set()), key=lambda v: "CVSACsCtKE".find(v))) or "—" for r in role_codes])
    out.append(md_table(["Objet"] + role_codes, rows))
    out.append("\nSuperviseurs N2 (voient les objets « restreints » en plus de l'émetteur et des destinataires) : "
               + ", ".join(sorted(rights.N2_SUPERVISORS)) + ". Rôles du côté terre : " + ", ".join(rights.SHORE_ROLES) + ".\n")
    out.append("\n## 3.3 Règles de visibilité et d'attribution (fonctions de `services/rights.py`)\n\n")
    rows = []
    for name, fn in inspect.getmembers(rights, inspect.isfunction):
        if fn.__module__ != rights.__name__ or name.startswith("_"):
            continue
        rows.append([f"`{name}{inspect.signature(fn)}`", first_line(fn.__doc__) or "—"])
    out.append(md_table(["Fonction", "Règle"], rows))
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 04 catalogues
def gen_catalogues() -> str:
    from apps.registry import catalog as C

    out = ["# 4. Catalogues de référence\n", GENERATED_NOTE,
           "\nContenu chargé dans chaque port par `bootstrap_ports` (`apps/registry/catalog.py`), puis modifiable par "
           "l'administrateur fonctionnel sans code (gabarits versionnés, types, causes, points d'arrêt). Les codes sont "
           "stables : ils sont cités par les points d'arrêt, les demandes et les documents.\n"]
    # timing
    out.append("\n## 4.1 Échéances relatives (`TIMING`)\n\n")
    out.append(md_table(["Code", "Ancre", "Décalage (min)", "Libellé FR / EN"],
                        [[f"`{k}`", v[0] or "— (événement)", v[1], f"{v[2]} / {v[3]}"] for k, v in C.TIMING.items()]))
    out.append("\nAncres : NOM nomination (création de l'escale), ETA, ETB, ATB, T0, T1, NOR, ATD. Un décalage négatif "
               "précède l'ancre. Les échéances sont recalculées en cascade à chaque révision des heures.\n")
    # templates
    out.append("\n## 4.2 Gabarits d'escale et tâches (`TEMPLATES`)\n\n"
               "Natures : D décision · F fourniture (document) · S saisie (jalon ou mesure) · R réalisation · "
               "Cs contresignature ; criticité : B bloquante (point d'arrêt) · N normale. Les colonnes « demande », "
               "« jalons » et « document » relient la tâche à l'objet qui la fait automatiquement.\n")
    for tpl in C.TEMPLATES:
        kinds = ", ".join(tpl.get("berth_kinds") or []) or "toutes zones"
        out.append(f"\n### `{tpl['code']}` — {tpl['name_fr']} / {tpl['name_en']}\n\n")
        out.append(f"Nature : {tpl['kind']} · ordre {tpl['order']} · zones : {kinds}"
                   + (" · exige une escale reliée" if tpl.get("requires_linked_call") else "")
                   + (f" · {tpl['description_fr']}" if tpl.get("description_fr") else "") + "\n\n")
        rows = []
        for section_code, task in tpl["tasks"]:
            sec = C.SEC.get(section_code, (section_code, section_code))[0] if isinstance(section_code, str) else section_code
            timing = C.TIMING.get(task["timing"], (task["timing"], 0, task["timing"], ""))
            links = []
            if task.get("request_type_code"):
                links.append(f"demande `{task['request_type_code']}` ({task.get('request_side') or '—'})")
            if task.get("milestone_codes"):
                links.append("jalons " + ", ".join(f"`{m}`" for m in task["milestone_codes"]))
            if task.get("document_type_code"):
                links.append(f"document `{task['document_type_code']}`")
            if task.get("auto_event"):
                links.append(f"auto `{task['auto_event']}`")
            flags = []
            if task.get("joint"):
                flags.append("conjointe")
            if task.get("continuous"):
                flags.append("continue")
            if not task.get("not_applicable_allowed", True):
                flags.append("jamais sans objet")
            if task.get("per_vessel"):
                flags.append("par navire")
            if task.get("berth_kinds"):
                flags.append("zones " + "/".join(task["berth_kinds"]))
            rows.append([f"`{tpl['code']}:{task['number']}`", sec, task["role"] + (" + " + "/".join(task["co_roles"]) if task["co_roles"] else ""),
                         task["nature"], f"{timing[2]}", task["criticality"], task["confidentiality"],
                         f"{task['title_fr']} / {task['title_en']}", " ; ".join(links), ", ".join(flags), task.get("hold_basis", "")])
        out.append(md_table(["Tâche", "Section", "Rôle (+ co-rôles)", "Nat.", "Échéance", "Crit.", "Conf.", "Intitulé FR / EN",
                             "Objet lié", "Particularités", "Base"], rows))
    # hold points
    out.append("\n## 4.3 Points d'arrêt (`HOLD_POINTS`)\n\n"
               "Chaque transition est refusée tant qu'une des tâches requises est « à faire » ou que l'autorisation issue "
               "d'une tâche de décision n'est pas en vigueur à l'heure du fait. Les tâches d'une autre étape de l'escale "
               "ne gardent pas la transition. Invariants non paramétrables en plus : voir chapitre 5.\n\n")
    out.append(md_table(["Transition", "Tâches requises"], [[f"`{k}`", ", ".join(f"`{t}`" for t in v)] for k, v in C.HOLD_POINTS.items()]))
    # milestones
    out.append("\n## 4.4 Types de jalons (`MILESTONES`)\n\n")
    rows = []
    for m in C.MILESTONES:
        extras = []
        for key in ("sets_anchor", "sets_status", "hold_point", "completes_tasks", "interruption", "repeatable",
                    "ais_corroboration", "pair_with", "requires_cause", "berth_kinds", "shore_side"):
            if key in m and m[key]:
                extras.append(f"{key}={m[key]}")
        rows.append([m["number"], f"`{m['code']}`", m["emitter_role"], ", ".join(m["countersigner_roles"]) or "—",
                     ", ".join(m["contester_roles"]) or "—", f"{m['label_fr']} / {m['label_en']}", " ; ".join(extras)])
    out.append(md_table(["N°", "Code", "Émetteur", "Contresignataires", "Contestataires", "Libellé FR / EN", "Effets et options"], rows))
    # request types
    out.append("\n## 4.5 Types de demande (`REQUEST_TYPES`) et leurs formulaires\n\n")
    for r in C.REQUEST_TYPES:
        out.append(f"\n### `{r['code']}` — {r['label_fr']} / {r['label_en']}\n\n")
        attrs = [f"demandeurs : {', '.join(r.get('requester_roles') or []) or '—'}",
                 f"décideurs : {', '.join(r.get('decision_roles') or []) or '— (commande de service)'}",
                 f"exécutant : {r.get('executor_role') or '—'}", f"confidentialité : {r.get('confidentiality', 'N2')}"]
        for key in ("refusal_confidentiality", "validity_hours", "processing_minutes", "hold_point", "assigns_berth",
                    "is_vetting", "submit_completes", "decision_completes", "execution_completes", "approval_milestone",
                    "approval_status", "refusal_status", "expected_documents", "movement"):
            if key in r and r[key] not in (None, "", [], False):
                attrs.append(f"{key} : {r[key]}")
        out.append(" · ".join(attrs) + "\n\n")
        if r.get("description_fr"):
            out.append(f"{r['description_fr']} / {r.get('description_en', '')}\n\n")
        if r.get("form_schema"):
            rows = []
            for f in r["form_schema"]:
                opts = "; ".join(f"`{o['value']}` {o['label_fr']} / {o['label_en']}" for o in f.get("options", []))
                rows.append([f"`{f['key']}`", f["type"], "oui" if f.get("required") else "non", f"{f['label_fr']} / {f['label_en']}", opts])
            out.append(md_table(["Clé", "Type", "Obligatoire", "Libellé FR / EN", "Options"], rows))
        else:
            out.append("Sans champ de formulaire.\n")
    # document types
    out.append("\n## 4.6 Types de document (`DOCUMENT_TYPES`)\n\n")
    out.append(md_table(["Code", "Libellé FR / EN", "Émetteurs", "Conf.", "Signataires", "Lecteurs (N2)", "Généré", "B/L", "Conservation (ans)"],
                        [[f"`{d['code']}`", f"{d['label_fr']} / {d['label_en']}", ", ".join(d["issuer_roles"]), d["default_confidentiality"],
                          ", ".join(d["signer_roles"]) or "—", ", ".join(d["audience_roles"]) or "—", "oui" if d["generated"] else "",
                          "oui" if d["is_bill_of_lading"] else "", d["retention_years"]] for d in C.DOCUMENT_TYPES]))
    # causes
    out.append("\n## 4.7 Causes d'interruption (`CAUSES`, liste fermée)\n\n")
    out.append(md_table(["Code", "Imputation", "Libellé FR / EN"], [[f"`{c[0]}`", c[1] or "— (à préciser)", f"{c[2]} / {c[3]}"] for c in C.CAUSES]))
    # ports
    out.append("\n## 4.8 Ports pilotes et postes (`PORTS`)\n\n")
    for code, port in C.PORTS.items():
        out.append(f"\n### `{code}` — {port['name']} ({port['country']}, {port['timezone']}, langue {port['default_language']})\n\n")
        m = port["map"]
        out.append(f"Cadre de la carte AIS : lat {m['lat_min']} → {m['lat_max']}, lon {m['lon_min']} → {m['lon_max']} (indicatif, à valider par la capitainerie).\n\n")
        out.append(md_table(["Code", "Zone", "Nom FR / EN", "Latitude", "Longitude", "Rayon (m)"],
                            [[f"`{b[0]}`", b[1], f"{b[2]} / {b[3]}", b[4], b[5], b[6] or "—"] for b in port["berths"]]))
    if hasattr(C, "DEFAULT_PARTIES"):
        out.append("\n## 4.9 Parties par défaut\n\n" + md_table(["Rôle", "Règle"], [[k, v] for k, v in C.DEFAULT_PARTIES.items()]))
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 06 forms
def gen_forms() -> str:
    from apps.registry.models import PortCall
    from apps.registry.services import forms as F

    out = ["# 6. Formulaires standards — structure et champs\n", GENERATED_NOTE,
           f"\nLes {len(F.FORMS)} formulaires sont générés par le paquet `services/forms/` (un module par partie émettrice : "
           "`standard`, `authority`, `agency`, `ship`, `terminal`, `surveyor`, `services`, `provider`, `owner`) dans **une structure unique** "
           "(`templates/registry/reports/form.html`) : bandeau d'en-tête, corps en sections, bloc de signatures, pied "
           "scellé. Chaque partie émet depuis la plateforme les documents que l'escale lui demande (tâches « fournir un "
           "document » et décisions sur les demandes), et la plateforme les archive. Pour chaque champ : libellé FR / EN et "
           "**source** de préremplissage (champ du modèle, jalon ou calcul) ; un champ sans source est complété à la main sur "
           "le papier. Les listes de contrôle ont une case par colonne (partie) et une colonne « remarques » ; la section "
           "`qr` dessine le code de vérification publique d'une autorisation.\n"]
    out.append("\n## 6.1 Structure commune (toutes les feuilles)\n\n")
    out.append(md_table(["Zone", "Contenu", "Source"], [
        ["Bandeau", "Port (nom, code) · titre FR / EN · standard de référence · n° `CODE-RÉFÉRENCE-nn` · date et heure de génération (UTC)",
         "Port, Form.title, Form.standard, nombre de documents du type déjà déposés + 1, `timezone.now()`"],
        ["Méta", "Navire (nom, OMI, pavillon) · escale (référence, voyage) · zone ou poste (+ étape si l'escale en a plusieurs) · arrivée (ATA ou ETA)",
         "Vessel, PortCall, CallStage en cours, PortCall.ata / eta"],
        ["Corps", "Sections `fields` (champs), `table` (colonnes, lignes préremplies, lignes vierges), `checklist` (points, colonnes à cocher, remarques), `text` (paragraphes FR / EN) ; note facultative par section",
         "fonction `build_<code>(call)` du formulaire"],
        ["Signatures", "Une colonne par rôle signataire : libellé du standard FR / EN, rôle FLUXAA, « nom, date, heure »", "Form.signers"],
        ["Pied scellé", "Généré par (acteur) · dernière écriture du journal (n° et empreinte SHA-256) · nombre de signatures électroniques enregistrées · n° du formulaire",
         "JournalEntry (seq, hash), MilestoneSignature.count"],
        ["Impression", "A4 portrait (paysage pour le time sheet et le rapport de jaugeage), marges 10 mm, sections insécables", "Form.landscape"],
    ]))
    out.append("\n## 6.2 Catalogue par partie émettrice\n\n")

    def offered(f):
        parts = []
        if f.templates:
            parts.append("gabarit " + " ou ".join(sorted(f.templates)))
        if f.needs_link:
            parts.append("escale reliée")
        return " ou ".join(parts) or "toujours"

    rows = []
    for family, label, members in F.grouped(list(F.FORMS.values())):
        rows.append([f"**{family}**", f"**{label[0]}** ({len(members)})", "", "", "", "", "", ""])
        for f in members:
            rows.append([f"`{f.code}`", f"`{f.document_type}`", f"{f.title[0]} / {f.title[1]}" + (f" — {f.purpose[0]}" if f.purpose else ""),
                         f.standard[0], ", ".join(sorted(f.roles)), ", ".join(f"{role} ({fr})" for role, (fr, _en) in f.signers),
                         ", ".join(f"`{a}`" for a in f.answers) or "—", offered(f)])
    out.append(md_table(["Code", "Type de document", "Titre FR / EN — objet", "Standard", "Émis par", "Signé par", "Répond à", "Offert si"], rows))
    out.append("\n`REQ:<type>` = la décision sur ce type de demande ; `Mx:n` = la tâche du gabarit. Les actes d'autorisation "
               "(`AUTH_*`) sont engendrés par le catalogue des types de demande à rôles décideurs.\n")
    call = PortCall.objects.select_related("vessel", "port", "agency").order_by("id").first()
    if call is None:
        out.append("\n*(aucune escale en base : les sections n'ont pas pu être énumérées — charger les données de démonstration et régénérer)*\n")
        return "".join(out)
    for form in F.FORMS.values():
        out.append(f"\n## 6.{3 + list(F.FORMS).index(form.code)} `{form.code}` — {form.title[0]} / {form.title[1]}\n\n")
        out.append(f"Partie émettrice : {form.family} — {form.family_label[0]}. Standard : {form.standard[0]} / {form.standard[1]}. "
                   f"Rôles émetteurs : {', '.join(sorted(form.roles))}. Type de document : `{form.document_type}`. "
                   f"Répond à : {', '.join(f'`{a}`' for a in form.answers) or '—'}. Offert : {offered(form)}. "
                   f"Orientation : {'paysage' if form.landscape else 'portrait'}."
                   + (f" Objet : {form.purpose[0]}" if form.purpose else "")
                   + (f" Note : {form.confidentiality_note[0]}" if form.confidentiality_note else "") + "\n")
        for section in form.build(call):
            title = f"{section['title'][0]} / {section['title'][1]}"
            if section["kind"] == "fields":
                out.append(f"\n**Section (champs) — {title}**\n\n")
                out.append(md_table(["Champ FR / EN", "Source de préremplissage", "Largeur"], [
                    [f"{i['fr']} / {i['en']}", i.get("source") or "— (à compléter sur le papier)", "pleine" if i.get("wide") else "demi"]
                    for i in section["items"]]))
            elif section["kind"] == "table":
                out.append(f"\n**Section (tableau) — {title}**\n\n")
                out.append("Colonnes : " + " · ".join(f"{c[0]} / {c[1]}" for c in section["columns"]) + ".\n\n")
                out.append(f"Lignes préremplies : {section.get('source') or 'aucune'} ; lignes vierges ajoutées : {len(section['blank'])}.\n")
            elif section["kind"] == "checklist":
                out.append(f"\n**Section (liste de contrôle) — {title}**\n\n")
                out.append("Colonnes à cocher : " + " · ".join(f"{c[0]} / {c[1]}" for c in section["columns"]) + " ; colonne remarques.\n\n")
                out.append(md_table(["Point de contrôle FR / EN"], [[f"{i['fr']} / {i['en']}" if isinstance(i, dict) else f"{i[0]} / {i[1]}"]
                                                                      for i in section["items"]]))
            elif section["kind"] == "text":
                out.append(f"\n**Section (texte) — {title}**\n\n")
                for p in section["paragraphs"]:
                    out.append(f"> {p[0]}\n>\n> *{p[1]}*\n\n")
            elif section["kind"] == "qr":
                out.append(f"\n**Section (code de vérification) — {title}**\n\n")
                out.append(f"QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : {section['caption'][0]}\n")
            if section.get("note"):
                out.append(f"\nNote de section : {section['note'][0]} / {section['note'][1]}\n")
        out.append("\n**Signatures** : " + " · ".join(f"{role} — {fr} / {en}" for role, (fr, en) in form.signers) + "\n")
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 07 API
def gen_api() -> str:
    from drf_spectacular.generators import SchemaGenerator

    schema = SchemaGenerator().get_schema(request=None, public=True)
    out = ["# 7. API publique v1 — points d'accès et représentations\n", GENERATED_NOTE,
           "\nLe schéma OpenAPI 3 complet est servi par `/api/schema/` (documentation navigable : `/api/docs/`). "
           "Authentification, erreurs, synchronisation hors ligne et webhooks : `docs/API.md`. Ci-dessous l'inventaire "
           "des opérations et des exemples de représentations JSON produits sur les données de démonstration.\n"]
    out.append("\n## 7.1 Opérations\n\n")
    rows = []
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            if method not in ("get", "post", "put", "patch", "delete"):
                continue
            rows.append([f"`{method.upper()}`", f"`{path}`", f"`{op.get('operationId', '')}`", op.get("summary") or op.get("description", "")])
    out.append(md_table(["Méthode", "Chemin", "Opération", "Résumé"], rows))
    # examples
    try:
        from apps.api import representations as rep
        from apps.core.models import User
        from apps.registry.models import PortCall
        from apps.registry.services.context import actor_for_call

        call = PortCall.objects.select_related("vessel", "port").filter(status__in=["IN_OPERATION", "AT_BERTH", "OPS_COMPLETE"]).order_by("id").first() \
            or PortCall.objects.order_by("id").first()
        user = User.objects.filter(organization__port=call.port, roles__contains=["AGE"], is_active=True).first() if call else None
        if call and user:
            actor = actor_for_call(call, user=user)
            examples = [("Escale — résumé (`call_summary`)", rep.call_summary(call)), ("Escale — détail (`call_detail`, vue agence)", rep.call_detail(call, actor))]
            task = call.tasks.order_by("id").first()
            if task:
                examples.append(("Tâche (`task_dict`)", rep.task_dict(task)))
            ms = call.milestones.order_by("id").first()
            if ms:
                examples.append(("Jalon (`milestone_dict`)", rep.milestone_dict(ms)))
            req = call.requests.order_by("id").first()
            if req:
                examples.append(("Demande (`request_dict`)", rep.request_dict(req, actor)))
            doc = call.documents.order_by("id").first()
            if doc:
                examples.append(("Document (`document_dict`)", rep.document_dict(doc)))
            meas = call.measurements.order_by("id").first()
            if meas:
                examples.append(("Mesure (`measurement_dict`)", rep.measurement_dict(meas)))
            disp = call.disputes.order_by("id").first()
            if disp:
                examples.append(("Contestation (`dispute_dict`)", rep.dispute_dict(disp, actor)))
            entry = call.journal_entries.order_by("seq").first() if hasattr(call, "journal_entries") else None
            if entry:
                examples.append(("Entrée de journal (`journal_dict`)", rep.journal_dict(entry)))
            out.append("\n## 7.2 Représentations JSON (exemples sur les données de démonstration)\n\n")
            for title, payload in examples:
                out.append(f"\n### {title}\n\n```json\n{json.dumps(payload, ensure_ascii=False, indent=2, default=str)}\n```\n")
    except Exception as exc:  # the examples are a convenience: never block the generation
        out.append(f"\n*(exemples non générés : {exc})*\n")
    return "".join(out)


# ------------------------------------------------------------------------------------------------ 09 routes and actions
def iter_patterns(patterns, prefix=""):
    for p in patterns:
        if isinstance(p, URLResolver):
            yield from iter_patterns(p.url_patterns, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            view = p.callback
            name = (p.name or "")
            yield prefix + str(p.pattern), name, view


def view_name(view) -> str:
    cls = getattr(view, "view_class", None) or getattr(view, "cls", None)
    if cls is not None:
        return f"{cls.__module__}.{cls.__name__}"
    inner = view
    while hasattr(inner, "__wrapped__"):
        inner = inner.__wrapped__
    return f"{getattr(inner, '__module__', '?')}.{getattr(inner, '__name__', repr(inner))}"


def web_actions() -> list[list]:
    """Parse apps/registry/views.py: every `action == "x"` branch of call_action with the POST parameters it reads
    and the service it calls."""
    source = Path(settings.BASE_DIR, "apps", "registry", "views.py").read_text()
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "call_action")
    rows = []

    def branch_actions(test) -> list[str]:
        names = []
        for node in ast.walk(test):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.replace("_", "").isalnum():
                names.append(node.value)
        return names

    def walk_if(node):
        actions = branch_actions(node.test)
        params, services = [], []
        for sub in ast.walk(ast.Module(body=node.body, type_ignores=[])):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute):
                target = sub.func.value
                if isinstance(target, ast.Name) and target.id == "data" and sub.func.attr in ("get", "getlist") and sub.args:
                    arg = sub.args[0]
                    if isinstance(arg, ast.Constant):
                        params.append(arg.value + ("[]" if sub.func.attr == "getlist" else ""))
                if isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name) and target.value.id == "request" \
                        and target.attr == "FILES":
                    params.append("file (multipart)")
                if isinstance(target, ast.Name) and target.id.endswith(("_svc", "disputes", "correspondence", "reports", "n4", "mfa")):
                    services.append(f"{target.id}.{sub.func.attr}")
        if actions and not all(a in ("1", "on") for a in actions):
            rows.append([", ".join(f"`{a}`" for a in actions if a not in ("1", "on", "PAPER", "ONLINE", "EMAIL", "OWN", "STS", "OTHER", "N2", "MT")),
                         ", ".join(f"`{p}`" for p in dict.fromkeys(params)) or "—",
                         ", ".join(f"`{s}`" for s in dict.fromkeys(services)) or "—"])
        for sub in node.orelse:
            if isinstance(sub, ast.If):
                walk_if(sub)

    for node in fn.body:
        if isinstance(node, ast.If):
            walk_if(node)
    return rows


def doc_forms(pattern: str) -> list[str]:
    """The spellings under which chapter 8 may name a route: the raw pattern, the pattern with its converters
    written as the chapter writes them (`<int:pk>` → `<id>`, `<str:code>` → `<code>`) and the last segment."""
    if not pattern:
        return []
    simple = re.sub(r"<int:[a-z_]+>", "<id>", pattern)
    simple = re.sub(r"<str:([a-z_]+)>", r"<\1>", simple)
    forms = [f"`/{pattern}`", f"/{simple}"]
    parts = [s for s in simple.split("/") if s]
    if len(parts) >= 2:
        forms.append("…/" + "/".join(parts[-2:]) + "/")
    return forms


def gen_routes(screens_doc: Path) -> tuple[str, list[str]]:
    out = ["# 9. Routes, vues et actions (inventaire)\n", GENERATED_NOTE,
           "\nToutes les URL servies par la plateforme, la vue qui les traite et le chapitre d'écran qui les décrit "
           "(chapitre 8). Les actions sont les sous-chemins `POST /escales/<id>/action/<action>/` de l'écran d'escale, "
           "avec les paramètres lus et le service appelé.\n"]
    documented = screens_doc.read_text() if screens_doc.exists() else ""
    missing = []
    rows = []
    for pattern, name, view in iter_patterns(get_resolver().url_patterns):
        vn = view_name(view)
        if "django.contrib.admin" in vn or pattern.startswith("admin/") and "admin_login" not in vn:
            continue
        doc_ref = ""
        if pattern.startswith("api/"):
            doc_ref = "ch. 7 (API)"
        elif name and f"`{name}`" in documented or any(form in documented for form in doc_forms(pattern)):
            doc_ref = "oui"
        elif vn.split(".")[-1] in documented:
            doc_ref = "oui (vue)"
        else:
            doc_ref = "**non**"
            missing.append(pattern)
        rows.append([f"`/{pattern}`", f"`{name}`" if name else "—", f"`{vn.replace('apps.', '')}`", doc_ref])
    out.append("\n## 9.1 Routes web et API\n\n" + md_table(["Chemin", "Nom", "Vue", "Décrit au"], rows))
    out.append("\nL'administration (`/admin/…`) est l'interface de paramétrage Django : ses écrans sont décrits au "
               "chapitre 8 (§8.9) par modèle administré.\n")
    out.append("\n## 9.2 Actions de l'écran d'escale (`POST /escales/<id>/action/<action>/`)\n\n"
               "Chaque action lit `request.POST` (`back` facultatif : page de retour), passe par `web_action` (refus "
               "métier → message, point d'arrêt → encadré de refus, authentification forte manquante → page du second "
               "facteur) et par `account_or_master` (compte ou lien d'accès).\n\n")
    out.append(md_table(["Action", "Paramètres lus", "Service appelé"], web_actions()))
    out.append("\nL'action `estimates` lit aussi les heures estimées `eta`, `etb`, `ets`, `etc`, `etd` (`calls.ESTIMATE_FIELDS`) ; "
               "`request_create` lit chaque clé du `form_schema` du type de demande (cases à cocher → booléen, dates → ISO 8601).\n")
    return "".join(out), missing


# ------------------------------------------------------------------------------------------------ command

VOLATILE = [
    (re.compile(r"Code [A-Z0-9]{10}"), "Code XXXXXXXXXX"),
    (re.compile(r'"verification_code": "[A-Z0-9]{10}"'), '"verification_code": "XXXXXXXXXX"'),
    (re.compile(r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}"), "<date heure>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(\+00:00|Z)?"), "<horodatage>"),
    (re.compile(r"\b[0-9a-f]{64}\b"), "<sha256>"),
    (re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"), "<uuid>"),
    # durations counted up to "now" move with the clock, not with the code (billing basis of a call in progress)
    (re.compile(r'"(hours_in_port|overrun_hours|remaining_h|overrun_h)": -?\d+(\.\d+)?'), r'"\1": <heures>'),
]


def volatile(text: str) -> str:
    """The examples of chapters 06 and 07 are rendered from the demonstration data: verification codes, times, hashes
    and identifiers change at every `load_demo`. They are neutralised before comparing, so that `--check` only
    fails when the structure described by the code changed."""
    for pattern, replacement in VOLATILE:
        text = pattern.sub(replacement, text)
    return text


class Command(BaseCommand):
    help = "Generate the generated chapters of the developer specification dossier (docs/spec)."

    def add_arguments(self, parser):
        parser.add_argument("--out", default=str(Path(settings.BASE_DIR, "docs", "spec")))
        parser.add_argument("--check", action="store_true", help="Exit 1 when a generated chapter would change")

    def handle(self, *args, **options):
        out_dir = Path(options["out"])
        out_dir.mkdir(parents=True, exist_ok=True)
        chapters = {
            "01-modele-de-donnees.md": gen_data_model,
            "02-enumerations-et-cycles.md": gen_enums,
            "03-roles-et-droits.md": gen_rights,
            "04-catalogues.md": gen_catalogues,
            "06-formulaires.md": gen_forms,
            "07-api.md": gen_api,
        }
        changed = []
        with translation.override("fr"):
            for name, fn in chapters.items():
                content = fn()
                self._write(out_dir / name, content, changed, options["check"])
            routes, missing = gen_routes(out_dir / "08-ecrans.md")
            self._write(out_dir / "09-routes-et-actions.md", routes, changed, options["check"])
        for pattern in missing:
            self.stdout.write(self.style.WARNING(f"route non décrite au chapitre 8 : /{pattern}"))
        if options["check"] and changed:
            self.stderr.write(self.style.ERROR("chapitres générés obsolètes : " + ", ".join(changed)))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS(f"Spécifications générées dans {out_dir} ({len(chapters) + 1} chapitres)."))

    def _write(self, path: Path, content: str, changed: list, check: bool):
        current = path.read_text() if path.exists() else None
        if current is not None and volatile(current) == volatile(content):
            return  # only the examples taken from the demonstration data moved (codes, times, hashes): not a change
        changed.append(path.name)
        if not check:
            path.write_text(content)
