"""Rattrapage des documents que la plateforme dépose d'elle-même (FLX-CDC-002, EXG-F-05) sur une installation mise
à niveau depuis une version qui ne les déposait pas : l'acte écrit de chaque décision déjà prise, la notice de
disponibilité d'une NOR déjà remise, le time sheet d'un rapport des faits déjà produit.

Idempotente : un document déjà présent n'est jamais refait ; une escale close, archivée, annulée ou rejetée n'est pas
touchée (son dossier est figé). Chaque document rattrapé est déposé sous le rôle et l'organisation de l'auteur de
l'acte d'origine (le décideur, l'émetteur de la NOR, l'agence du rapport des faits) et journalisé comme tout document
généré ; un échec ne bloque pas les autres rattrapages. Exécutée au démarrage du conteneur « web » (entrypoint.sh).
"""
from django.core.management.base import BaseCommand

from apps.registry.models import CallStatus, DocumentStatus, Milestone, PortCall, RequestStatus, ServiceRequest
from apps.registry.services.context import Actor

FROZEN = (CallStatus.CLOSED, CallStatus.ARCHIVED, CallStatus.CANCELLED, CallStatus.REJECTED)
DECIDED = (RequestStatus.APPROVED, RequestStatus.APPROVED_WITH_CONDITIONS, RequestStatus.REFUSED)


def actor_of(call, *, role: str, user=None, org=None, master=None) -> Actor:
    if master is not None:
        return Actor(port=call.port, roles=frozenset({master.role}), master=master, org=master.organization, strong_auth=True)
    return Actor(port=call.port, roles=frozenset({role}), user=user, org=org or (user.organization if user else None),
                 strong_auth=True)


def generated_exists(call: PortCall, document_type: str, title: str) -> bool:
    return call.documents.filter(type__code=document_type, title=title, generated=True,
                                 status__in=[DocumentStatus.ISSUED, DocumentStatus.SIGNED]).exists()


class Command(BaseCommand):
    help = "Dépose les actes, notices de disponibilité et time sheets manquants des escales en cours (mise à niveau)."

    def add_arguments(self, parser):
        parser.add_argument("--port", help="Code du port (par défaut : tous)")
        parser.add_argument("--dry-run", action="store_true", help="N'écrit rien : liste ce qui serait déposé")

    def handle(self, *args, **options):
        from apps.registry.services.forms import FORMS, auto_issue
        from apps.registry.services.requests import file_decision_act

        calls = PortCall.objects.exclude(status__in=FROZEN).select_related("port", "vessel")
        if options["port"]:
            calls = calls.filter(port__code=options["port"])
        dry = options["dry_run"]
        filed, planned = 0, []

        def file(label, fn):
            nonlocal filed
            planned.append(label)
            if dry:
                return
            try:
                if fn() is not None:
                    filed += 1
                    self.stdout.write(f"  + {label}")
                else:
                    self.stdout.write(self.style.WARNING(f"  ! {label} : non déposé (voir le journal fluxaa.forms)"))
            except Exception as exc:  # noqa: BLE001 — a failure never blocks the other backfills
                self.stdout.write(self.style.WARNING(f"  ! {label} : {exc}"))

        for call in calls:
            # 1. the written act of every decision already taken
            for req in ServiceRequest.objects.filter(call=call, status__in=DECIDED).select_related("type", "decision_user", "decision_org"):
                form = FORMS.get(f"AUTH_{req.type.code}")
                if form is None or not req.decision_role:
                    continue
                title = f"{form.title[0]} / {form.title[1]} — {call.reference}"
                if generated_exists(call, form.document_type, title):
                    continue
                actor = actor_of(call, role=req.decision_role, user=req.decision_user, org=req.decision_org)
                file(f"{call.reference} acte {req.type.code} ({req.reference})", lambda r=req, a=actor: file_decision_act(r, a, r.decision_role))
            # 2. the notice of readiness of a NOR already tendered
            nor = Milestone.objects.filter(call=call, type__code="NOR_TENDERED", is_rectification=False).order_by("declared_at").last()
            form = FORMS.get("NOR")
            if nor is not None and form is not None:
                title = f"{form.title[0]} / {form.title[1]} — {call.reference}"
                if not generated_exists(call, form.document_type, title):
                    actor = actor_of(call, role=nor.emitter_role, user=nor.emitter_user, org=nor.emitter_org, master=nor.emitter_master)
                    file(f"{call.reference} notice de disponibilité", lambda c=call, a=actor, m=nor: auto_issue(c, a, "NOR", as_role=m.emitter_role, about=m))
            # 3. the time sheet of a statement of facts already produced
            sof = call.documents.filter(type__code="SOF", generated=True, status__in=[DocumentStatus.ISSUED, DocumentStatus.SIGNED]).order_by("-version").first()
            form = FORMS.get("TIME_SHEET")
            if sof is not None and form is not None:
                title = f"{form.title[0]} / {form.title[1]} — {call.reference}"
                if not generated_exists(call, form.document_type, title):
                    actor = actor_of(call, role="AGE", user=sof.issuer_user, org=sof.issuer_org, master=sof.issuer_master)
                    file(f"{call.reference} time sheet", lambda c=call, a=actor: auto_issue(c, a, "TIME_SHEET", as_role="AGE"))

        if dry:
            self.stdout.write("\n".join(f"  ~ {label}" for label in planned) or "  rien à rattraper")
            self.stdout.write(self.style.SUCCESS(f"{len(planned)} document(s) seraient déposés (--dry-run)."))
        else:
            self.stdout.write(self.style.SUCCESS(f"{filed} document(s) rattrapé(s) sur {len(planned)} manquant(s)."))
