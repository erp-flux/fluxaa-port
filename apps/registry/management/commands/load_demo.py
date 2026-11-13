"""Demonstration / training data: fictitious organisations, one user per role, and three calls at
different stages. Never run it on a production tenant: every name is suffixed "(démo)" / "(demo)"."""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone, translation

from apps.core import mfa
from apps.core.models import Organization, Port, User
from apps.registry.bootstrap import bootstrap_port
from apps.registry.models import Notification, PortDefaultParty, RequestStatus, Vessel
from apps.registry.services import calls as call_svc
from apps.registry.services import milestones as ms_svc
from apps.registry.services import requests as req_svc
from apps.registry.services import tasks as task_svc
from apps.registry.services.context import actor_for_call, system_actor

ORGS = [
    # key, FR name, EN name, roles, default party roles, kind (apps.core.parties — a suggestion list, not a closed one)
    ("authority", "Autorité portuaire (démo)", "Port Authority (demo)", ["CAP", "APO", "DIR"], ["CAP", "APO", "DIR"], "PORT_AUTHORITY"),
    ("adm", "Douanes, immigration et santé (démo)", "Customs, Immigration and Health (demo)", ["ADM"], ["ADM"], "CUSTOMS"),
    ("security", "Sûreté portuaire et marine nationale (démo)", "Port Security and Navy (demo)", ["SUR"], ["SUR"], "PORT_SECURITY"),
    ("marine", "Services nautiques (démo)", "Marine Services (demo)", ["SVC"], ["SVC"], "PILOTAGE"),
    ("agency", "Agence maritime (démo)", "Shipping Agency (demo)", ["AGE"], [], "SHIPPING_AGENT"),
    ("agency2", "Consignataire associé (démo)", "Associate Shipping Agent (demo)", ["AGE"], [], "SHIPPING_AGENT"),  # co-nominated agency (1.5)
    ("terminal", "Terminal pétrolier (démo)", "Oil Terminal (demo)", ["TER"], [], "OIL_TERMINAL"),
    ("cargo_terminal", "Terminal conteneurs et vrac (démo)", "Container and Bulk Terminal (demo)", ["TER"], [], "TERMINAL"),  # every cargo (1.5)
    ("surveyor", "Surveyor et laboratoire (démo)", "Surveyor & Laboratory (demo)", ["INS"], [], "CARGO_SURVEYOR"),
    ("owner", "Armateur / affréteur (démo)", "Owner / Charterer (demo)", ["COM"], [], "CHARTERER"),
    ("waste", "Prestataire déchets (démo)", "Waste Contractor (demo)", ["PRE"], [], "WASTE_CONTRACTOR"),
    ("sts", "Prestataire STS (démo)", "STS Provider (demo)", ["PRE"], [], "STS_PROVIDER"),
    ("lab", "Laboratoire indépendant (démo)", "Independent Laboratory (demo)", ["INS"], [], "LABORATORY"),  # no account: convened by link
    # parties without an account, registered in the port and invited by the agency when the call needs them
    ("bunkers", "Avitailleur de soutes (démo)", "Bunker Supplier (demo)", ["PRE"], [], "BUNKER_SUPPLIER"),
    ("water", "Fournisseur d'eau douce (démo)", "Fresh Water Supplier (demo)", ["PRE"], [], "WATER_SUPPLIER"),
    ("pandi", "Correspondant P&I (démo)", "P&I Correspondent (demo)", ["INS"], [], "PANDI_SURVEYOR"),
    ("receiver", "Réceptionnaire / importateur (démo)", "Receiver / Importer (demo)", ["COM"], [], "RECEIVER"),
    ("tugs", "Remorquage et lamanage (démo)", "Towage and Mooring (demo)", ["SVC"], [], "TOWAGE"),
]
USERS = [
    # login, organisation, roles, FR label, EN label
    ("cap", "authority", ["CAP"], "Officier de port", "Harbour master officer"),
    ("apo", "authority", ["APO"], "Planificateur des postes", "Berth planner"),
    ("dir", "authority", ["DIR"], "Direction du port", "Port management"),
    ("adm", "adm", ["ADM"], "Agent douanes-santé", "Customs and health officer"),
    ("sur", "security", ["SUR"], "Officier de sûreté", "Security officer"),
    ("svc", "marine", ["SVC"], "Pilote", "Pilot"),
    ("age", "agency", ["AGE"], "Agent maritime", "Ship agent"),
    ("age2", "agency2", ["AGE"], "Agent maritime associé", "Associate ship agent"),
    ("ter", "terminal", ["TER"], "Opérateur terminal", "Terminal operator"),
    ("ter2", "cargo_terminal", ["TER"], "Chef d'exploitation terminal", "Terminal operations manager"),
    ("ins", "surveyor", ["INS"], "Expert surveyor", "Surveyor"),
    ("com", "owner", ["COM"], "Opérations affréteur", "Charterer operations"),
    ("pre", "waste", ["PRE"], "Prestataire déchets", "Waste contractor"),
    ("sts", "sts", ["PRE"], "Superviseur STS (POAC)", "STS superintendent (POAC)"),
]
VESSELS = [("9999993", "MT ATLANTIC DEMO", "Liberia", "Product tanker", 45000, "636099993", "TANKER_PRODUCT"),
           ("9999981", "MT GULF DEMO", "Marshall Islands", "Product tanker", 38000, "538099981", "TANKER_PRODUCT"),
           ("9999979", "MT HARMATTAN DEMO", "Panama", "Crude tanker", 105000, "352099979", "TANKER_CRUDE"),
           ("9999967", "MT SAVANNAH DEMO", "Malta", "Product tanker", 50000, "229099967", "TANKER_PRODUCT"),
           # every kind of cargo since 1.5: a bulk carrier, a container ship, a car carrier, a general cargo ship
           ("9311012", "MV CLINKER DEMO", "Panama", "Geared bulk carrier", 56000, "352311012", "BULK"),
           ("9074743", "MSC LOME DEMO", "Liberia", "Container ship", 90000, "636074743", "CONTAINER"),
           ("9074755", "GRANDE DEMO", "Italy", "Pure car and truck carrier", 30000, "247074755", "RORO"),
           ("9074767", "MV SAHEL DEMO", "Togo", "General cargo", 12000, "671074767", "GENERAL"),
           # the other vessel belongs to another agency (1.6): a coastal tanker announced alongside the vessel at the
           # jetty, a second daughter vessel coming to the mother vessel at the STS area
           ("9999955", "MT LAGUNE DEMO", "Togo", "Coastal product tanker", 6500, "671099955", "TANKER_PRODUCT"),
           ("9999943", "MT KARA DEMO", "Liberia", "Product tanker", 47000, "636099943", "TANKER_PRODUCT")]
# Particulars of the demo vessels, for the vetting grid (1.5): LOA, beam, summer draft, year built, displacement,
# manifold height above the waterline, air draft, crane SWL — illustrative figures
PARTICULARS = {
    "9999993": (183.0, 32.2, 12.2, 2012, 58000, 14.5, 44.0, None),
    "9999981": (176.0, 31.0, 11.6, 2009, 49000, 13.8, 42.0, None),
    "9999979": (244.0, 42.0, 15.0, 2006, 125000, 18.5, 52.0, None),
    "9999967": (183.0, 32.2, 12.8, 2015, 63000, 15.0, 45.0, None),
    "9311012": (190.0, 32.3, 12.9, 2011, 68000, None, 46.0, 30.0),
    "9074743": (300.0, 48.2, 14.5, 2014, 125000, None, 60.0, None),
    "9074755": (199.9, 32.3, 9.5, 2010, 38000, None, 48.0, None),
    "9074767": (120.0, 20.0, 7.4, 1998, 15000, None, 32.0, 25.0),
    "9999955": (105.0, 16.8, 6.6, 2014, 9200, 6.0, 28.0, None),
    "9999943": (183.0, 32.2, 12.4, 2013, 60000, 14.6, 44.5, None),
}
# Acceptance limits of the demo berths (1.5): illustrative figures, read by the vetting grid against the vessel's data —
# a port enters its own in the settings (berths)
BERTH_LIMITS = {  # kind → (max LOA, max draft, max DWT, max beam, max displacement, max manifold height, min UKC, max age, min crane SWL, max air draft)
    "JETTY": (250.0, 13.0, 80000, 45.0, 110000, 19.0, 1.0, 25, None, None),
    "STS_AREA": (340.0, 22.0, 320000, 60.0, 360000, None, 2.0, 25, None, None),
    "ANCHORAGE": (None, 18.0, None, None, None, None, 1.5, None, None, None),
}
# Demo AIS picture: where each vessel is heard, relative to the berths of the port (offsets in degrees)
DEMO_POSITIONS = [  # imo, berth code, dlat, dlon, speed, course, heading, nav status
    ("9999993", "JETTY", 0.0, 0.0, 0.0, 0.0, 95, 5),
    ("9999981", "ANCHORAGE", 0.004, -0.006, 0.1, 0.0, 180, 1),
    ("9999979", "STS_AREA", 0.0, 0.0, 0.0, 0.0, 270, 5),
    ("9999967", "STS_AREA", 0.0015, 0.001, 0.0, 0.0, 270, 5),
]


def demo_pdf(title: str, lines: list[str]) -> bytes:
    """A one-page PDF, valid and readable, clearly marked as demonstration material."""
    def esc(text: str) -> str:
        return text.encode("latin-1", "replace").decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    rows = [f"BT /F1 18 Tf 56 780 Td ({esc(title)}) Tj ET", "BT /F1 10 Tf 56 760 Td (FLUXAA Port - document de demonstration / demonstration document) Tj ET"]
    y = 730
    for line in lines:
        rows.append(f"BT /F1 11 Tf 56 {y} Td ({esc(line)}) Tj ET")
        y -= 16
    stream = "\n".join(rows).encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + body + b"\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%EOF\n".encode()
    return bytes(out)


def demo_file(name: str, title: str, lines: list[str]):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, demo_pdf(title, lines), content_type="application/pdf")


class Command(BaseCommand):
    help = "Load fictitious demonstration data in a port (organisations, users per role, three calls)."

    def add_arguments(self, parser):
        parser.add_argument("--port", required=True, help="SLFNA or TGLFW")
        parser.add_argument("--password", help="Password for every demo user (default: random, printed)")
        parser.add_argument("--domain", default="demo.fluxaa.test")
        parser.add_argument("--no-calls", action="store_true")
        parser.add_argument("--history", type=int, default=8,
                            help="closed calls spread over the past year, for the statistics (0 = none)")
        parser.add_argument("--refresh-ais", action="store_true",
                            help="only re-emit the demo AIS positions (the board shows the last 24 h); nothing else is touched")

    @transaction.atomic
    def handle(self, *args, **options):
        # The demonstration replays calls already under way: their milestones are entered now for times in the
        # past. They are not late entries of a real call, so the late-entry mark is not raised for them (entries
        # made offline in the field app still are, as everywhere else).
        settings.FLUXAA_LATE_ENTRY_SECONDS = 10**9
        code = options["port"]
        if options["refresh_ais"]:
            port = Port.objects.filter(code=code).first()
            if port is None:
                raise CommandError(f"Unknown port {code}")
            vessels = list(Vessel.objects.filter(port=port, imo__in=[imo for imo, *_ in VESSELS]))
            if not vessels:
                raise CommandError(f"No demo vessel in {code}: load the demo first.")
            self._positions(port, vessels)
            self.stdout.write(self.style.SUCCESS(f"Demo AIS picture refreshed in {port}."))
            return
        bootstrap_port(code)
        port = Port.objects.get(code=code)
        english = port.default_language == "en"
        password = options["password"] or secrets.token_urlsafe(10)
        orgs = {}
        for key, fr, en, roles, defaults, kind in ORGS:
            org, _ = Organization.objects.get_or_create(port=port, name=en if english else fr,
                                                        defaults={"allowed_roles": roles, "email": f"{key}@{options['domain']}", "kind": kind})
            if org.kind != kind:
                org.kind = kind
                org.save(update_fields=["kind"])
            orgs[key] = org
            for role in defaults:
                PortDefaultParty.objects.get_or_create(port=port, organization=org, role=role)
        lines = []
        for login, org_key, roles, label_fr, label_en in USERS:
            email = f"{login}.{code.lower()}@{options['domain']}"
            user = User.objects.filter(email=email).first()
            if user is None:
                label = label_en if english else label_fr
                user = User.objects.create_user(email=email, password=password, full_name=f"{label} {code}",
                                                organization=orgs[org_key], roles=roles,
                                                is_port_admin=login == "dir")
            secret = ""
            if set(roles) & {"CAP", "APO", "SUR", "ADM"} or user.requires_mfa_login:  # deciders and the port admin
                if not user.mfa_enabled:
                    secret = mfa.new_secret()
                    user.set_mfa_secret(secret)
                    user.mfa_enabled = True
                    user.save(update_fields=["mfa_secret_encrypted", "mfa_enabled"])
                else:
                    secret = user.get_mfa_secret()
            lines.append(f"  {','.join(roles):<4} {email:<38} {('TOTP ' + secret) if secret else ''}")
        vessels = []
        for imo, name, flag, vtype, dwt, mmsi, kind in VESSELS:
            vessel, _ = Vessel.objects.get_or_create(port=port, imo=imo, defaults={"name": name, "flag": flag,
                                                                                "vessel_type": vtype, "dwt": dwt,
                                                                                "mmsi": mmsi, "vessel_kind": kind})
            if not vessel.mmsi:
                vessel.mmsi = mmsi
                vessel.save(update_fields=["mmsi"])
            if imo in PARTICULARS and vessel.loa_m is None:
                (vessel.loa_m, vessel.beam_m, vessel.draft_m, vessel.built_year, vessel.displacement_t,
                 vessel.manifold_height_m, vessel.air_draft_m, vessel.crane_swl_t) = PARTICULARS[imo]
                vessel.save(update_fields=["loa_m", "beam_m", "draft_m", "built_year", "displacement_t",
                                           "manifold_height_m", "air_draft_m", "crane_swl_t"])
            vessels.append(vessel)
        for berth in port.berths.all():
            limits = BERTH_LIMITS.get(berth.kind)
            if limits and berth.max_draft_m is None:
                (berth.max_loa_m, berth.max_draft_m, berth.max_dwt, berth.max_beam_m, berth.max_displacement_t,
                 berth.max_manifold_height_m, berth.min_ukc_m, berth.max_vessel_age_years, berth.min_crane_swl_t,
                 berth.max_air_draft_m) = limits
                berth.save()
        self._positions(port, vessels)
        if not options["no_calls"]:
            with translation.override(port.default_language or "fr"):
                self._calls(port, orgs, vessels)
                if options["history"]:
                    self._history(port, orgs, vessels, options["history"])
                self._other_agencies(port, orgs, vessels)  # after the history: the calls above keep their numbers
        self.stdout.write(self.style.SUCCESS(f"Demo data loaded in {port}."))
        self.stdout.write(f"Password for every demo user: {password}")
        self.stdout.write("Users (TOTP secrets to add in an authenticator app — deciding roles and port administrator):")
        for line in lines:
            self.stdout.write(line)
        self.stdout.write("The 'dir' user is the port's functional administrator (settings).")
        access = getattr(self, "party_access", None)
        if access:
            ref, org, token, code = access
            self.stdout.write(f"Access without account (party link) — {org}, surveyor on {ref}: "
                              f"{settings.SITE_URL}/bord/{token}/  or code {code} on {settings.SITE_URL}/bord/")

    def _positions(self, port, vessels):
        """A handful of AIS reports so that the board shows something: the demo vessels around the berths, and one
        tanker in transit that has no call in the port."""
        from apps.ais.services import ingest

        now = timezone.now()
        by_kind = {}
        for berth in port.berths.filter(latitude__isnull=False).order_by("code"):
            by_kind.setdefault(berth.kind, berth)
        reports = []
        for imo, kind, dlat, dlon, speed, course, heading, status in DEMO_POSITIONS:
            berth = by_kind.get(kind)
            vessel = next((v for v in vessels if v.imo == imo), None)
            if berth is None or vessel is None:
                continue
            reports.append({"mmsi": vessel.mmsi, "imo": vessel.imo, "name": vessel.name, "observed_at": now - timedelta(minutes=3),
                            "lat": float(berth.latitude) + dlat, "lon": float(berth.longitude) + dlon,
                            "speed_kn": speed, "course_deg": course, "heading_deg": heading, "nav_status": status,
                            "destination": port.code})
        anchorage = by_kind.get("ANCHORAGE") or by_kind.get("JETTY")
        if anchorage is not None:
            reports.append({"mmsi": "999000001", "name": "MT TRANSIT DEMO", "observed_at": now - timedelta(minutes=8),
                            "lat": float(anchorage.latitude) - 0.03, "lon": float(anchorage.longitude) + 0.05,
                            "speed_kn": 11.5, "course_deg": 250.0, "heading_deg": 252, "nav_status": 0,
                            "destination": "LAGOS"})
        ingest(port, reports, source="demo")

    def _calls(self, port, orgs, vessels):
        def L(en: str, fr: str) -> str:  # demo content in the port's language
            return en if port.default_language == "en" else fr

        agency_user = User.objects.filter(organization=orgs["agency"]).first()
        if agency_user is None:
            raise CommandError("Demo agency user missing.")
        now = timezone.now()
        jetty = port.berths.filter(kind="JETTY").first()
        parties = [(orgs["terminal"], "TER"), (orgs["surveyor"], "INS"), (orgs["owner"], "COM"), (orgs["waste"], "PRE"),
                   # the list of the parties is open: a receiver, a P&I correspondent and a water supplier without accounts
                   (orgs["receiver"], "COM"), (orgs["pandi"], "INS"), (orgs["water"], "PRE")]

        def actor(call, key):
            user = User.objects.filter(organization=orgs[key]).first() if key not in ("cap", "apo", "dir") else (
                User.objects.filter(organization=orgs["authority"], roles__contains=[key.upper()]).first()
            )
            return actor_for_call(call, user=user, strong_auth=True)

        def done(call, codes):
            from apps.registry.services.tasks import system_complete

            sys = system_actor(port)
            for code in codes:
                tpl, number = code.split(":")
                for t in call.tasks.filter(template_code=tpl, number=number, status="PENDING"):
                    system_complete(t, sys, evidence="demo", note="demo data", allow_joint=True)

        # Call A — discharge at the jetty, in operation
        a = call_svc.create_call(agency_user, vessel=vessels[0], eta=now - timedelta(hours=20), requested_berth_kind="JETTY",
                                 operations=["M1"], parties=parties, etb=now - timedelta(hours=12),
                                 etd=now + timedelta(hours=30), product="Gasoil 10 ppm", quantity=32000, voyage_number="DEMO-01",
                                 planned_pump_hours="27.5", batch_reference="LFW-GO-2026-11",
                                 # what the announcement asked for the discharge (v1.6)
                                 operation_details={"M1": {"max_rate_m3h": 1200, "max_manifold_pressure_bar": 7, "manifold_connections": "2 × 12\" ANSI 150",
                                                           "inert_gas": "YES", "vapour_return": "NO", "stripping_rob": "≤ 25 m³"}})
        from apps.registry.services.documents import upload_document

        upload_document(a, actor(a, "agency"), "Q88", demo_file("q88-atlantic-demo.pdf", "Q88 - MT ATLANTIC DEMO", [
            "IMO 9999993 - Liberia - Product tanker - DWT 45 000", "Manifold: 4 x 12 in ANSI 150, centre manifold",
            "Max. discharge rate: 1 400 m3/h - max. manifold pressure 10 bar"]))
        link, _token, _code = call_svc.issue_master_link(a, actor(a, "agency"), master_name="Capt. Demo")
        nav = actor_for_call(a, master=link)
        upload_document(a, nav, "CERTIFICATES", demo_file("certificates-atlantic-demo.pdf", "Certificates - MT ATLANTIC DEMO", [
            "IOPP, SOLAS safety construction / equipment / radio, ISSC, CLC and bunker CLC blue cards",
            "All valid beyond the planned departure date"]))
        upload_document(a, actor(a, "agency"), "IMPORT_AUTH", demo_file("import-authorisation.pdf", "Import authorisation", [
            "Gasoil 10 ppm - 32 000 MT - consignee: Oil Terminal (demo)"]))
        done(a, ["M0:05"])
        call_svc.declare_call(a, actor(a, "agency"))
        vet = req_svc.create_request(a, actor(a, "terminal"), "VESSEL_ACCEPTANCE", {
            "product": "Gasoil", "inspection": L("SIRE 2.0 — no open observation", "SIRE 2.0 — aucune observation ouverte"),
            "last_cargoes": "ULSD / ULSD / Jet A-1", "vetting_result": L("Accepted", "Accepté")})
        req_svc.decide_request(vet, actor(a, "cap"), RequestStatus.APPROVED, valid_until=now + timedelta(days=30))
        req_svc.decide_request(a.requests.get(type__code="GREEN_LIGHT"), actor(a, "cap"), RequestStatus.APPROVED)
        # the other green lights of the call (1.5): the naval base, the terminal and the principal give theirs
        for number, key, note in (("09b", "security", L("Vessel cleared on the watch list", "Navire contrôlé sur la liste de veille")),
                                  ("09c", "terminal", L("Tanks and lines ready", "Bacs et lignes prêts")),
                                  ("09d", "owner", L("Cargo released, instruction to discharge given", "Cargaison libérée, instruction de décharger donnée"))):
            task_svc.complete_task(a.tasks.get(template_code="M0", number=number), actor(a, key), note=note)
        berth = req_svc.create_request(a, actor(a, "agency"), "BERTH", {"window_from": (now - timedelta(hours=12)).isoformat(),
                                                                          "arrival_draft": 11.4})
        req_svc.decide_request(berth, actor(a, "apo"), RequestStatus.APPROVED, berth=jetty, valid_from=now - timedelta(hours=12),
                               valid_until=now + timedelta(hours=48))
        for code, data in (("FREE_PRATIQUE", {"crew": 23}), ("CUSTOMS_IMMIGRATION", {"crew_list": True})):
            req = req_svc.create_request(a, actor(a, "agency"), code, data)
            req_svc.decide_request(req, actor(a, "adm"), RequestStatus.APPROVED)
        mov = req_svc.create_request(a, actor(a, "agency"), "MOVEMENT", {"movement": "ARRIVAL",
                                                                          "requested_time": (now - timedelta(hours=13)).isoformat()})
        req_svc.decide_request(mov, actor(a, "cap"), RequestStatus.APPROVED, valid_from=now - timedelta(hours=14))
        ms_svc.record_milestone(a, nav, "ARRIVAL", now - timedelta(hours=19))
        ms_svc.record_milestone(a, actor(a, "agency"), "NOR_TENDERED", now - timedelta(hours=18, minutes=40))
        ms_svc.record_milestone(a, nav, "ANCHORED", now - timedelta(hours=18, minutes=30))
        ms_svc.record_milestone(a, nav, "ANCHOR_AWEIGH", now - timedelta(hours=13, minutes=20))
        svc = actor(a, "marine")
        ms_svc.record_milestone(a, svc, "PILOT_ON_BOARD_ARR", now - timedelta(hours=13))
        ms_svc.record_milestone(a, svc, "FIRST_LINE", now - timedelta(hours=12, minutes=10))
        ms_svc.record_milestone(a, svc, "ALL_FAST", now - timedelta(hours=11, minutes=50))
        ms_svc.record_milestone(a, nav, "GANGWAY", now - timedelta(hours=11, minutes=40))
        ter = actor(a, "terminal")
        t = a.tasks.get(template_code="M0", number="27")
        task_svc.sign_task(t, ter)
        task_svc.sign_task(t, nav)
        # the ship/shore safety checklist completed on line by both sides, then signed (task M0:28, 1.4)
        from apps.registry.services import checklist as cl_svc

        checklist = cl_svc.open_checklist(a, ter, repeat_interval_h="4")
        agreements = {"5A.1": "600 / 1 200 / 300 m³/h", "5A.2": "7 bar", "5A.3": "40 °C", "5A.4": "30 s / 45 s",
                      "5A.5": L("Ship 1P→6S; shore T-11 then T-12; sampling at manifold, gauging by surveyor",
                                "Bord 1P→6S ; terre T-11 puis T-12 ; échantillonnage au collecteur, jaugeage par l'inspecteur"),
                      "5A.6": L("Wind 25 kn, swell 1.5 m, lightning within 5 nm, visibility 1 nm", "Vent 25 nd, houle 1,5 m, foudre à moins de 5 nm, visibilité 1 nm"),
                      "5A.7": L("VHF 12 / 16; English", "VHF 12 / 16 ; anglais"), "5A.8": "4"}
        for item in checklist.items:
            for who, side in ((nav, "SHIP"), (ter, "SHORE")):
                if side not in (["SHIP", "SHORE"] if item["side"] == "BOTH" else [item["side"]]):
                    continue
                if item["kind"] == "value":
                    if side == "SHORE":
                        cl_svc.answer(checklist, who, item_code=item["code"], value=agreements.get(item["code"], "—"))
                else:
                    cl_svc.answer(checklist, who, item_code=item["code"], state="NA" if item["code"] == "2.10" and side == "SHIP" else "YES",
                                  remark=L("engine on 2 h notice as agreed", "machine à 2 h de préavis comme convenu") if item["code"] == "2.10" and side == "SHIP" else "")
        cl_svc.sign(checklist, nav)
        cl_svc.sign(checklist, ter)
        ms_svc.record_milestone(a, ter, "ESD_TEST", now - timedelta(hours=10, minutes=30))
        done(a, ["M0:31", "M1:1.04", "M1:1.06", "M1:1.07"])
        ms_svc.record_milestone(a, actor(a, "surveyor"), "INITIAL_GAUGING", now - timedelta(hours=10))
        ms_svc.record_milestone(a, ter, "HOSES_CONNECTED", now - timedelta(hours=9, minutes=30))
        ms_svc.record_milestone(a, ter, "TRANSFER_START", now - timedelta(hours=9))
        ms_svc.record_milestone(a, ter, "FULL_RATE", now - timedelta(hours=8, minutes=30))
        stop = ms_svc.record_milestone(a, ter, "INTERRUPTION_START", now - timedelta(hours=5), cause_code="SHORE_TANK_SWITCH")
        ms_svc.record_milestone(a, ter, "INTERRUPTION_END", now - timedelta(hours=4, minutes=20), related=stop)
        from apps.registry.services.measurements import (
            add_pumping_entry,
            add_tank_reading,
            add_value,
            create_measurement,
            open_pumping_sheet,
            review_tank_reading,
        )

        # the pumping log of both sides (1.4): the terminal's sheet for its receiving tank, the ship's for its tanks;
        # hourly readings paired by the platform, one hour outside the 0.3 % tolerance (the alert of the terminal logs)
        shore_sheet = open_pumping_sheet(a, ter, tank="T-12", start_level_mm="1325", expected_stop_level_mm="19800",
                                         m3_per_metre="1684", density="0.8412", vcf="0.9824", planned_quantity_m3="32046",
                                         expected_rate_m3h="1200", expected_pressure_bar="6.5",
                                         estimated_start=now - timedelta(hours=9), estimated_completion=now + timedelta(hours=18))
        ship_sheet = open_pumping_sheet(a, nav, tank="1P–6S", density="0.8412", vcf="0.9824", planned_quantity_m3="32046",
                                        expected_rate_m3h="1200")
        shore_levels = [(8, 2420, 6.2), (7, 3110, 6.3), (6, 3805, 6.4), (5, 4180, 6.0), (4, 4515, 6.1), (3, 5230, 6.1), (2, 5925, 6.1), (1, 6625, 6.0)]
        ship_moved = [(8, "1844"), (7, "1162"), (6, "1170"), (5, "631"), (4, "564"), (3, "1198"), (2, "1171"), (1, "1178")]
        for (hours, level, pressure), (_h, moved) in zip(shore_levels, ship_moved):
            add_pumping_entry(a, ter, declared_at=now - timedelta(hours=hours), sheet=shore_sheet, level_mm=str(level),
                              manifold_pressure_bar=pressure, temperature_c=31,
                              note=L("start of discharge", "début du déchargement") if hours == 8 else (L("tank switch T-11 → T-12", "changement de bac T-11 → T-12") if hours == 5 else ""))
            add_pumping_entry(a, nav, declared_at=now - timedelta(hours=hours, minutes=5), sheet=ship_sheet, hourly_m3=moved,
                              manifold_pressure_bar=pressure + 0.4, temperature_c=30)
        # countersignatures: most milestones agreed, the interruption contested by the master
        cap = actor(a, "cap")
        signs = {"ARRIVAL": [cap], "NOR_TENDERED": [ter], "PILOT_ON_BOARD_ARR": [nav], "ALL_FAST": [nav, ter],
                 "ESD_TEST": [nav], "INITIAL_GAUGING": [nav, ter], "HOSES_CONNECTED": [nav], "TRANSFER_START": [nav],
                 "FULL_RATE": [nav]}
        for milestone in a.milestones.filter(type__code__in=list(signs)):
            for who in signs[milestone.type.code]:
                if milestone.emitter_role not in who.roles:
                    ms_svc.countersign_milestone(milestone, who)
        ms_svc.countersign_milestone(stop, nav, contest=True, comment=L(
            "Stop announced for 20 minutes at the pre-transfer meeting; the ship was kept waiting 40 minutes "
            "with cargo pumps idling. Time to be counted against the terminal.",
            "Arrêt annoncé pour 20 minutes à la réunion pré-transfert ; le navire a attendu 40 minutes pompes "
            "cargaison au ralenti. Temps à imputer au terminal."))
        from apps.registry.services import disputes as dispute_svc

        dispute = a.disputes.filter(status="OPEN").first()
        if dispute is not None:
            dispute_svc.respond(dispute, ter, L(
                "Tank switch took longer because of a valve check on shore tank T-12; "
                "the delay is recorded, attribution to be settled in the time sheet.",
                "Le changement de bac a pris plus de temps à cause d'une vérification de vanne sur le bac T-12 ; "
                "le retard est consigné, son imputation sera réglée dans le time sheet."))
        # quantities: bill of lading figure and initial gauging, entered by their own emitters
        bl = create_measurement(a, actor(a, "surveyor"), "BL")
        add_value(bl, nav, "SHIP", "32000.000")
        add_value(bl, ter, "SHORE", "32000.000")
        add_value(bl, actor(a, "surveyor"), "SURVEYOR", "32000.000")
        initial = create_measurement(a, actor(a, "surveyor"), "INITIAL")
        add_value(initial, nav, "SHIP", "32046.310", temperature="29.5", density="0.8412")
        add_value(initial, actor(a, "surveyor"), "SURVEYOR", "32039.870", temperature="29.4", density="0.8410")
        # tank by tank (1.4): the ship reads its cargo tanks, the terminal its shore tank; the surveyor validates — one
        # reading is left pending, one was rejected and corrected
        ins = actor(a, "surveyor")
        tanks = {"1P": ("412", "5342.1", "0.98241"), "1S": ("418", "5338.4", "0.98241"), "2P": ("405", "5410.0", "0.98238"),
                 "2S": ("409", "5401.6", "0.98238"), "3P": ("455", "5280.3", "0.98235"), "3S": ("452", "5274.2", "0.98235")}
        for tank, (ullage, gov, vcf) in tanks.items():
            reading = add_tank_reading(initial, nav, tank=tank, level_mm=ullage, temperature_c="29.5", gov_m3=gov, vcf=vcf,
                                       density="0.8412", declared_at=now - timedelta(hours=10, minutes=20))
            if tank == "2P":
                review_tank_reading(reading, ins, validate=False, note=L("temperature inconsistent with the adjacent tanks — re-read",
                                                                          "température incohérente avec les citernes voisines — à relire"))
                add_tank_reading(initial, nav, tank=tank, level_mm=ullage, temperature_c="29.6", gov_m3=gov, vcf=vcf, density="0.8412",
                                 declared_at=now - timedelta(hours=9, minutes=50), supersedes=reading,
                                 note=L("re-read with the surveyor", "relu avec l'inspecteur"))
            elif tank != "3S":
                review_tank_reading(reading, ins, validate=True)
        shore = add_tank_reading(initial, ter, tank="T-12", level_mm="1325", temperature_c="30.1", gov_m3="2231.3", vcf="0.98230",
                                 density="0.8412", declared_at=now - timedelta(hours=10, minutes=10))
        review_tank_reading(shore, ins, validate=True)
        # correspondence attached to the call
        from apps.registry.services.correspondence import create_thread, post_message

        thread = create_thread(a, ter, subject=L("Shore tank switch - rate reduction", "Changement de bac - réduction de débit"),
                               participant_roles=["NAV", "AGE", "INS"],
                               body=L("Switching from T-11 to T-12 around 16:00. Please reduce to 600 m3/h at 15:50 "
                                      "and stand by for our call on channel 12.",
                                      "Passage du bac T-11 au T-12 vers 16:00. Merci de réduire à 600 m3/h à 15:50 "
                                      "et de rester à l'écoute sur le canal 12."))
        post_message(thread, nav, L("Noted. Rate will be reduced at 15:50, ship standing by on channel 12.",
                                    "Bien noté. Débit réduit à 15:50, le navire reste à l'écoute sur le canal 12."))
        # a confidential security filing (N4): goes to the security space only, nothing in the call
        from apps.secure import services as secure_svc

        secure_svc.deposit(a, actor(a, "agency"), kind="ARMED_GUARDS", payload={
            "guards": "3", "company": "Demo Maritime Security Ltd", "embark": (now - timedelta(hours=20)).isoformat(),
            "disembark": (now + timedelta(hours=31)).isoformat(), "escort": "",
            "details": L("Weapons sealed in the ship's armoury while alongside; certificates sent to the security officer.",
                         "Armes scellées dans l'armurerie du bord pendant le séjour à quai ; certificats transmis à "
                         "l'officier de sûreté.")})

        # Call B — loading, accepted, waiting for its berth
        b = call_svc.create_call(agency_user, vessel=vessels[1], eta=now + timedelta(hours=26), requested_berth_kind="JETTY",
                                 operations=["M2"], parties=parties, etb=now + timedelta(hours=34),
                                 etd=now + timedelta(hours=60), product="Jet A-1", quantity=18000, voyage_number="DEMO-02",
                                 operation_details={"M2": {"max_rate_m3h": 900, "tank_condition": "LAST_CARGO", "last_cargoes": "Jet A-1, Jet A-1, gasoil",
                                                           "inert_gas": "YES", "bl_quantity_basis": "SHORE"}})
        upload_document(b, actor(b, "agency"), "Q88", demo_file("q88-gulf-demo.pdf", "Q88 - MT GULF DEMO", [
            "IMO 9999981 - Marshall Islands - Product tanker - DWT 38 000"]))
        link_b, _token, _code = call_svc.issue_master_link(b, actor(b, "agency"), master_name="Capt. Demo")
        upload_document(b, actor_for_call(b, master=link_b), "CERTIFICATES", demo_file(
            "certificates-gulf-demo.pdf", "Certificates - MT GULF DEMO", ["All valid beyond the planned departure date"]))
        done(b, ["M0:05"])
        call_svc.declare_call(b, actor(b, "agency"))
        vet = req_svc.create_request(b, actor(b, "terminal"), "VESSEL_ACCEPTANCE", {
            "product": "Jet A-1", "inspection": L("SIRE 2.0 — 2 observations closed", "SIRE 2.0 — 2 observations levées"),
            "last_cargoes": "Jet A-1 / Gasoline / Jet A-1",
            "vetting_result": L("Accepted with conditions", "Accepté sous conditions")})
        req_svc.decide_request(vet, actor(b, "cap"), RequestStatus.APPROVED_WITH_CONDITIONS,
                               conditions=L("Daylight berthing only", "Accostage de jour uniquement"), valid_until=now + timedelta(days=30))
        req_svc.decide_request(b.requests.get(type__code="GREEN_LIGHT"), actor(b, "cap"), RequestStatus.APPROVED)
        task_svc.complete_task(b.tasks.get(template_code="M0", number="09b"), actor(b, "security"))
        task_svc.complete_task(b.tasks.get(template_code="M0", number="09c"), actor(b, "terminal"))  # the principal's is awaited
        req_svc.create_request(b, actor(b, "agency"), "BERTH", {"window_from": (now + timedelta(hours=34)).isoformat(),
                                                                 "arrival_draft": 9.8})

        # Calls C and D — STS pair in the offshore area, declared; the laboratory has no account and is convened
        # by a link at the declaration (Parties tab); the lightering call then goes to the quay (second stage)
        sts_parties = [(orgs["sts"], "PRE"), (orgs["surveyor"], "INS"), (orgs["lab"], "INS"), (orgs["owner"], "COM"),
                       (orgs["terminal"], "TER")]
        c = call_svc.create_call(agency_user, vessel=vessels[2], eta=now + timedelta(days=3), requested_berth_kind="STS_AREA",
                                 operations=["M3"], parties=sts_parties, etd=now + timedelta(days=5),
                                 product="Crude oil", quantity=90000, voyage_number="DEMO-03", sts_role="DONOR",
                                 operation_details={"M3": {"window_from": (now + timedelta(days=3, hours=6)).isoformat(),
                                                           "window_to": (now + timedelta(days=4, hours=18)).isoformat(),
                                                           "poac": "Capt. K. Mensah — STS Services Demo", "equipment_by": "PROVIDER",
                                                           "transfer_mode": "ANCHOR", "compatibility_done": "YES"}})
        d = call_svc.create_call(agency_user, vessel=vessels[3], eta=now + timedelta(days=3, hours=4),
                                 requested_berth_kind="STS_AREA", operations=["M3"], parties=sts_parties,
                                 etd=now + timedelta(days=5), product="Crude oil", quantity=60000, voyage_number="DEMO-04",
                                 linked_call=c, link_kind="STS", sts_role="RECEIVER")
        for call in (c, d):
            call.refresh_from_db()
            done(call, ["M0:02", "M0:03", "M0:05"])
            call_svc.declare_call(call, actor(call, "agency"))
        from apps.registry.services import stages as stage_svc

        stage_svc.add_stage(c, actor(c, "agency"), berth_kind="JETTY", operations=["M1"],
                            planned_from=now + timedelta(days=4, hours=12), planned_to=now + timedelta(days=5),
                            reason="Déchargement du reliquat à quai après l'allègement"
                            if port.default_language != "en" else "Discharge of the remainder at the quay after lightering")
        lab_party = c.parties.get(organization=orgs["lab"], role="INS")
        _link, token, code = call_svc.issue_party_link(c, actor(c, "agency"), party=lab_party, holder_name="", channel="QR",
                                                      note="demo")
        self.party_access = (c.reference, orgs["lab"].name, token, code)
        self.named_calls = (a, c)
        self._other_cargoes(port, orgs, vessels, agency_user, now, actor, done, L)

    def _other_agencies(self, port, orgs, vessels):
        """Version 1.6 — the other vessel of a double banking or of a ship-to-ship transfer is not always the same
        agency's. The associate agent announces a coastal tanker alongside the vessel discharging at the jetty
        (lightering at the berth), and a second daughter vessel coming to the mother vessel at the STS area. Both
        name a call of the first agency from the port's board: the links wait for the harbour master, whose
        decisions are pending — the double banking is held by its hold point until the inner vessel consents."""
        from apps.registry.models import RequestType
        from apps.registry.services import intake as intake_svc
        from apps.registry.services.tasks import system_complete

        named = getattr(self, "named_calls", None)
        user2 = User.objects.filter(organization=orgs["agency2"]).first()
        if named is None or user2 is None or len(vessels) < 10:
            return
        a, c = named
        english = port.default_language == "en"
        now = timezone.now()
        sys = system_actor(port)

        def declare(call):
            for number in ("02", "03", "05"):
                for t in call.tasks.filter(template_code="M0", number=number, status="PENDING"):
                    system_complete(t, sys, evidence="demo", note="demo data", allow_joint=True)
            call_svc.declare_call(call, actor_for_call(call, user=user2, strong_auth=True))

        # I — double banking: the coastal tanker comes alongside the vessel at the jetty to load part of her cargo
        a.refresh_from_db()
        i = call_svc.create_call(
            user2, vessel=vessels[8], eta=now + timedelta(hours=6), requested_berth_kind="JETTY", operations=["M2"],
            modules=["M9"], requested_berth=a.berth or a.requested_berth, etb=now + timedelta(hours=8),
            etd=now + timedelta(hours=22), product="Gasoil 10 ppm", quantity=5000, voyage_number="DEMO-17", validity_days=7,
            planned_pump_hours=10, parties=[(orgs["terminal"], "TER"), (orgs["surveyor"], "INS")],
            db_partner={"call": a, "position": "OUTER"},
            operation_details={
                "M9": {"purpose": "LIGHTERING", "duration_h": 12, "fenders_by": "TERMINAL",
                       "loading_condition": ("Outer vessel in ballast alongside, loaded 5,000 t at separation; inner vessel discharging, draught 11.2 m to 9.8 m"
                                             if english else
                                             "Navire extérieur sur lest à l'accostage, chargé 5 000 t à la séparation ; navire intérieur en déchargement, tirant d'eau 11,2 m à 9,8 m")},
                "M2": {"max_rate_m3h": 500, "max_manifold_pressure_bar": 6, "manifold_connections": "2 × 8\" ANSI 150",
                       "tank_condition": "LAST_CARGO", "last_cargoes": "Gasoil / Gasoil / Jet A-1", "inert_gas": "NO"},
            })
        declare(i)
        rtype = RequestType.objects.filter(port=port, code="DOUBLE_BANKING", is_active=True).first()
        if rtype is not None:
            data = {k: str(v) for k, v in intake_svc.prefill_for_request(i, rtype).items() if v not in (None, "")}
            req_svc.create_request(i, actor_for_call(i, user=user2, strong_auth=True), "DOUBLE_BANKING", data)

        # J — a second daughter vessel, of the associate agent, names the mother vessel at the STS area
        c.refresh_from_db()
        window_from, window_to = now + timedelta(days=4, hours=20), now + timedelta(days=5, hours=20)
        j = call_svc.create_call(
            user2, vessel=vessels[9], eta=now + timedelta(days=4, hours=12), requested_berth_kind="STS_AREA", operations=["M3"],
            etd=now + timedelta(days=6), product="Crude oil", quantity=30000, voyage_number="DEMO-18", validity_days=12,
            parties=[(orgs["sts"], "PRE"), (orgs["surveyor"], "INS")], linked_call=c, link_kind="STS",
            operation_details={"M3": {"window_from": window_from.isoformat(), "window_to": window_to.isoformat(),
                                      "poac": "Capt. K. Mensah — STS Services Demo", "equipment_by": "PROVIDER",
                                      "transfer_mode": "ANCHOR", "compatibility_done": "TBC"}})
        declare(j)
        rtype = RequestType.objects.filter(port=port, code="STS_ZONE", is_active=True).first()
        if rtype is not None:
            data = {k: str(v) for k, v in intake_svc.prefill_for_request(j, rtype).items() if v not in (None, "")}
            req_svc.create_request(j, actor_for_call(j, user=user2, strong_auth=True), "STS_ZONE", data)

    def _other_cargoes(self, port, orgs, vessels, agency_user, now, actor, done, L):
        """Version 1.5 — the port is open to every cargo: a bulk carrier of clinker with a co-nominated agency given a
        partial access, a container ship, a car carrier expected, and a general-cargo announcement that ran out
        of validity and must be announced again."""
        cargo_parties = [(orgs["cargo_terminal"], "TER"), (orgs["surveyor"], "INS"), (orgs["receiver"], "COM")]
        # E — dry bulk discharge of clinker, declared and accepted; the associate agent follows the tasks and the
        # documents only (EXG-R-04); the shipper's documents are asked for at the announcement (EXG-R-06)
        e = call_svc.create_call(agency_user, vessel=vessels[4], eta=now + timedelta(hours=40), requested_berth_kind="JETTY",
                                 operations=["MB1"], parties=cargo_parties + [(orgs["agency2"], "AGE", "PARTIAL", ["taches", "documents"])],
                                 etb=now + timedelta(hours=48), etd=now + timedelta(days=5), product="Clinker", quantity=38242,
                                 quantity_unit="MT", voyage_number="DEMO-05", cargo_kind="DRY", validity_days=10,
                                 expected_documents=["INSURANCE"],
                                 custom_documents=[{"label": L("Certificate of origin", "Certificat d'origine"), "role": "COM", "hours_before_eta": 48}],
                                 operation_details={"MB1": {"holds": 5, "geared": "YES", "imsbc_group": "C", "discharge_rate_tpd": 8000,
                                                            "stevedore": L("Lomé Stevedoring Demo", "Manutention de Lomé (démo)"), "dust_or_odour": "YES"}})
        from apps.registry.services.documents import upload_document

        upload_document(e, actor(e, "agency"), "Q88", demo_file("particulars-clinker-demo.pdf", "Ship's particulars - MV CLINKER DEMO", [
            "IMO 9311012 - Panama - Geared bulk carrier, 4 cranes x 30 t - DWT 56 000 - 5 holds"]))
        link_e, _t, _c = call_svc.issue_master_link(e, actor(e, "agency"), master_name="Capt. Bulk Demo")
        upload_document(e, actor_for_call(e, master=link_e), "CERTIFICATES", demo_file(
            "certificates-clinker-demo.pdf", "Certificates - MV CLINKER DEMO", ["All valid beyond the planned departure date"]))
        upload_document(e, actor(e, "agency"), "CARGO_MANIFEST", demo_file("manifest-clinker-demo.pdf", "Cargo manifest - MV CLINKER DEMO", [
            "Clinker in bulk - 38 242 MT - 5 holds - consignee: Receiver / Importer (demo)"]))
        done(e, ["M0:05"])
        call_svc.declare_call(e, actor(e, "agency"))
        vet = req_svc.create_request(e, actor(e, "cargo_terminal"), "VESSEL_ACCEPTANCE", {
            "product": "Clinker", "inspection": L("Class survey in date, PSC Lomé 2026 — no deficiency", "Visite de classe à jour, PSC Lomé 2026 — aucune déficience"),
            "last_cargoes": "Clinker / Gypsum / Coal", "vetting_result": L("Accepted", "Accepté")})
        req_svc.decide_request(vet, actor(e, "cap"), RequestStatus.APPROVED, valid_until=now + timedelta(days=30))
        req_svc.decide_request(e.requests.get(type__code="GREEN_LIGHT"), actor(e, "cap"), RequestStatus.APPROVED)
        task_svc.complete_task(e.tasks.get(template_code="M0", number="09b"), actor(e, "security"))
        # F — container ship, expected: moves, bay plan and dangerous goods asked of the agent
        f = call_svc.create_call(agency_user, vessel=vessels[5], eta=now + timedelta(days=2), requested_berth_kind="JETTY",
                                 operations=["MC1"], parties=[(orgs["cargo_terminal"], "TER"), (orgs["surveyor"], "INS")],
                                 etb=now + timedelta(days=2, hours=3), etd=now + timedelta(days=3), product="Tcs/Tcs",
                                 quantity=1501, quantity_unit="MOVES", voyage_number="DEMO-06", cargo_kind="CONTAINER",
                                 planned_pump_hours="24",
                                 operation_details={"MC1": {"moves_discharge": 820, "moves_load": 640, "restows": 41, "reefers": 36, "dg_units": 12,
                                                            "oog_units": 3, "gearless": "YES"}})
        upload_document(f, actor(f, "agency"), "Q88", demo_file("particulars-msc-demo.pdf", "Ship's particulars - MSC LOME DEMO", [
            "IMO 9074743 - Liberia - Container ship 8 000 TEU - DWT 90 000"]))
        link_f, _t, _c = call_svc.issue_master_link(f, actor(f, "agency"), master_name="Capt. Box Demo")
        upload_document(f, actor_for_call(f, master=link_f), "CERTIFICATES", demo_file(
            "certificates-msc-demo.pdf", "Certificates - MSC LOME DEMO", ["All valid beyond the planned departure date"]))
        done(f, ["M0:05"])
        call_svc.declare_call(f, actor(f, "agency"))
        # G — car carrier expected in a week, still a draft: the agent is told what the declaration waits for
        call_svc.create_call(agency_user, vessel=vessels[6], eta=now + timedelta(days=7), requested_berth_kind="JETTY",
                             operations=["MR1"], parties=[(orgs["cargo_terminal"], "TER"), (orgs["surveyor"], "INS")],
                             etd=now + timedelta(days=8), product=L("Vehicles", "Véhicules"), quantity=1850, quantity_unit="UNIT",
                             voyage_number="DEMO-07", cargo_kind="RORO",
                             operation_details={"MR1": {"units": 1850, "high_heavy": 120, "ramp": "STERN", "ramp_load_t": 150, "vehicle_customs": "YES"}})
        # H — a general-cargo announcement whose validity ran out before the vessel came: obsolete, to be announced again
        h = call_svc.create_call(agency_user, vessel=vessels[7], eta=now - timedelta(days=2), requested_berth_kind="JETTY",
                                 operations=["MG1"], parties=[(orgs["cargo_terminal"], "TER")], etd=now - timedelta(days=1),
                                 product=L("Bagged rice", "Riz en sacs"), quantity=11200, quantity_unit="MT", voyage_number="DEMO-08",
                                 cargo_kind="GENERAL", validity_days=3)
        done(h, ["M0:02", "M0:03", "M0:05"])
        call_svc.declare_call(h, actor(h, "agency"))
        type(h).objects.filter(pk=h.pk).update(valid_until=now - timedelta(hours=6))
        h.refresh_from_db()
        call_svc.expire_call(h)

    # ------------------------------------------------------------------------------------ past calls
    def _history(self, port, orgs, vessels, count: int):
        """Closed calls spread over the past year, replayed through the same services as a real call, so that the
        statistics page and the indicators have something to show. Decision and entry delays are plausible, not
        real: nothing here is a measurement of anyone."""
        import random

        from apps.registry.services.tasks import system_complete

        rnd = random.Random(2026)
        now = timezone.now()
        agency_user = User.objects.filter(organization=orgs["agency"]).first()
        jetty = port.berths.filter(kind="JETTY").first()
        parties = [(orgs["terminal"], "TER"), (orgs["surveyor"], "INS"), (orgs["owner"], "COM")]
        sys = system_actor(port)

        def actor(call, key):
            user = User.objects.filter(organization=orgs[key]).first() if key not in ("cap", "apo", "dir") else (
                User.objects.filter(organization=orgs["authority"], roles__contains=[key.upper()]).first()
            )
            return actor_for_call(call, user=user, strong_auth=True)

        def done(call, codes):
            for code in codes:
                tpl, number = code.split(":")
                for t in call.tasks.filter(template_code=tpl, number=number, status="PENDING"):
                    system_complete(t, sys, evidence="demo", note="demo history", allow_joint=True)

        products = [("M1", "Gasoil 10 ppm", 30000), ("M2", "Jet A-1", 17000), ("M1", "Essence 95", 24000),
                    ("M1", "Gasoil 10 ppm", 36000), ("M2", "Fuel-oil", 21000), ("M1", "Jet A-1", 19000)]
        causes = ["SHORE_TANK_SWITCH", "SHIP_BALLAST", "WEATHER_LIMITS", "SHORE_PUMP", "SHIP_STRIPPING", "SURVEYOR"]
        for i in range(count):
            op, product, quantity = products[i % len(products)]
            # the history replays calls of the four tankers of the first agency (the two vessels of the associate
            # agent, added in 1.6, have no past in the port)
            tankers = [v for v in vessels[:8] if v.vessel_kind.startswith("TANKER")] or vessels
            vessel = tankers[i % len(tankers)]
            eta = now - timedelta(days=int(365 * (i + 0.5) / count) + rnd.randint(0, 6), hours=rnd.randint(0, 23))
            waiting = timedelta(hours=rnd.choice([3, 5, 8, 14, 22, 31]))
            transfer = timedelta(hours=rnd.choice([16, 20, 24, 30, 36]))
            t_arr = eta + timedelta(minutes=rnd.randint(-90, 120))
            t_fast = t_arr + waiting
            t_start = t_fast + timedelta(hours=3)
            t_end = t_start + transfer
            t_dep = t_end + timedelta(hours=rnd.choice([4, 6, 9]))
            # hold points check authorizations at the time of the act they guard; a replayed past call needs its
            # authorizations in force both at the past milestones and today, when the replay decides them
            window = dict(valid_from=eta - timedelta(days=2), valid_until=now + timedelta(days=30))
            call = call_svc.create_call(agency_user, vessel=vessel, eta=eta, requested_berth_kind="JETTY", operations=[op],
                                        parties=parties, etb=t_fast, etd=t_dep, product=product, quantity=quantity,
                                        voyage_number=f"DEMO-H{i + 1:02d}")
            done(call, ["M0:02", "M0:03", "M0:05", "M0:09b", "M0:09c", "M0:09d"])  # the green lights of 1.5 given in the replay
            call_svc.declare_call(call, actor(call, "agency"))
            link, _token, _code = call_svc.issue_master_link(call, actor(call, "agency"), master_name="Capt. Demo",
                                                             expires_at=now + timedelta(days=1))
            nav = actor_for_call(call, master=link)
            vet = req_svc.create_request(call, actor(call, "terminal"), "VESSEL_ACCEPTANCE", {
                "product": product, "inspection": "SIRE 2.0", "last_cargoes": product, "vetting_result": "OK"})
            req_svc.decide_request(vet, actor(call, "cap"), RequestStatus.APPROVED, **window)
            req_svc.decide_request(call.requests.get(type__code="GREEN_LIGHT"), actor(call, "cap"), RequestStatus.APPROVED, **window)
            berth_req = req_svc.create_request(call, actor(call, "agency"), "BERTH", {"window_from": t_fast.isoformat(),
                                                                                       "arrival_draft": 10.5})
            req_svc.decide_request(berth_req, actor(call, "apo"), RequestStatus.APPROVED, berth=jetty, **window)
            for code, data in (("FREE_PRATIQUE", {"crew": 22}), ("CUSTOMS_IMMIGRATION", {"crew_list": True})):
                req = req_svc.create_request(call, actor(call, "agency"), code, data)
                req_svc.decide_request(req, actor(call, "adm"), RequestStatus.APPROVED, **window)
            mov = req_svc.create_request(call, actor(call, "agency"), "MOVEMENT", {"movement": "ARRIVAL",
                                                                                     "requested_time": t_fast.isoformat()})
            req_svc.decide_request(mov, actor(call, "cap"), RequestStatus.APPROVED, **window)
            ter, svc, ins, cap = actor(call, "terminal"), actor(call, "marine"), actor(call, "surveyor"), actor(call, "cap")
            ms_svc.record_milestone(call, nav, "ARRIVAL", t_arr)
            ms_svc.record_milestone(call, actor(call, "agency"), "NOR_TENDERED", t_arr + timedelta(minutes=20))
            if waiting > timedelta(hours=4):
                ms_svc.record_milestone(call, nav, "ANCHORED", t_arr + timedelta(minutes=40))
                ms_svc.record_milestone(call, nav, "ANCHOR_AWEIGH", t_fast - timedelta(hours=2))
            done(call, ["M0:25"])
            ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_ARR", t_fast - timedelta(hours=1, minutes=30))
            ms_svc.record_milestone(call, svc, "FIRST_LINE", t_fast - timedelta(minutes=25))
            ms_svc.record_milestone(call, svc, "ALL_FAST", t_fast)
            ms_svc.record_milestone(call, nav, "GANGWAY", t_fast + timedelta(minutes=10))
            done(call, [f"M0:{n}" for n in ("27", "28", "29", "31")] + [f"M1:1.0{n}" for n in (4, 5, 6, 7)]
                 + [f"M2:2.0{n}" for n in (4, 5, 6, 7, 8, 9)])
            ms_svc.record_milestone(call, ter, "ESD_TEST", t_fast + timedelta(hours=1))
            ms_svc.record_milestone(call, ins, "INITIAL_GAUGING", t_fast + timedelta(hours=1, minutes=30))
            ms_svc.record_milestone(call, ter, "HOSES_CONNECTED", t_fast + timedelta(hours=2, minutes=20))
            ms_svc.record_milestone(call, ter, "TRANSFER_START", t_start)
            ms_svc.record_milestone(call, ter, "FULL_RATE", t_start + timedelta(minutes=35))
            for k in range(rnd.choice([0, 1, 1, 2])):
                at = t_start + timedelta(hours=4 + 7 * k + rnd.randint(0, 2))
                cause = causes[(i + k) % len(causes)]
                who = ter if cause.startswith(("SHORE", "SURVEYOR", "WEATHER")) else nav
                stop = ms_svc.record_milestone(call, who, "INTERRUPTION_START", at, cause_code=cause)
                ms_svc.record_milestone(call, who, "INTERRUPTION_END", at + timedelta(minutes=rnd.choice([25, 40, 70, 110])),
                                        related=stop)
                other = nav if who is ter else ter
                contest = (i + k) % 3 == 1
                ms_svc.countersign_milestone(stop, other, contest=contest,
                                             comment="demo history: duration disputed" if contest else "")
            ms_svc.record_milestone(call, nav, "TOPPING_OFF", t_end - timedelta(hours=1))
            ms_svc.record_milestone(call, ter, "TRANSFER_END", t_end)
            ms_svc.record_milestone(call, ter, "LINES_DRAINED", t_end + timedelta(minutes=45))
            ms_svc.record_milestone(call, ter, "HOSES_DISCONNECTED", t_end + timedelta(hours=1, minutes=10))
            ms_svc.record_milestone(call, ins, "FINAL_GAUGING", t_end + timedelta(hours=1, minutes=40))
            for milestone in call.milestones.filter(type__code__in=["ARRIVAL", "ALL_FAST", "TRANSFER_START", "TRANSFER_END"]):
                for who in (cap, nav, ter):
                    if milestone.emitter_role not in who.roles and set(milestone.type.countersigner_roles) & set(who.roles):
                        ms_svc.countersign_milestone(milestone, who)
            for dispute in call.disputes.filter(status__in=("OPEN", "ANSWERED")):
                from apps.registry.services import disputes as dispute_svc

                opener = nav if dispute.opened_role == "NAV" else ter
                if i % 2 == 0:  # settled by the parties themselves
                    dispute_svc.close(dispute, opener, agreed=True, text="demo history: settled in the time sheet")
                else:  # recorded by the harbour master as closed without agreement
                    dispute_svc.close(dispute, cap, agreed=False, text="demo history: no agreement, noted in the statement of facts")
            done(call, ["M0:32", "M7:7.12"])
            outward = req_svc.create_request(call, actor(call, "agency"), "OUTWARD_FORMALITIES", {})
            req_svc.decide_request(outward, actor(call, "adm"), RequestStatus.APPROVED, **window)
            clearance = req_svc.create_request(call, actor(call, "agency"), "DEPARTURE_CLEARANCE",
                                               {"requested_time": t_dep.isoformat()})
            req_svc.decide_request(clearance, cap, RequestStatus.APPROVED, **window)
            ms_svc.record_milestone(call, svc, "PILOT_ON_BOARD_DEP", t_dep - timedelta(minutes=50))
            ms_svc.record_milestone(call, svc, "LAST_LINE", t_dep - timedelta(minutes=10))
            ms_svc.record_milestone(call, nav, "DEPARTED", t_dep)
            done(call, ["M0:36"])
            call_svc.confirm_closure(call, actor(call, "agency"))
            call_svc.close_call(call, cap)
            # plausible delays between submission and decision, and between deadline and completion, for the
            # statistics: demo data, not a record of anyone
            for req in call.requests.filter(decided_at__isnull=False):
                hours = rnd.choice([0.5, 1, 2, 3, 5, 8, 14, 26])
                call.requests.filter(pk=req.pk).update(submitted_at=req.decided_at - timedelta(hours=hours))
            for task in call.tasks.filter(status="DONE", due_at__isnull=False):
                margin = timedelta(minutes=rnd.randint(20, 540))
                late = rnd.random() < 0.12
                call.tasks.filter(pk=task.pk).update(completed_at=task.due_at + margin if late else task.due_at - margin)
            # a closed call of last year does not leave unread notifications in the demo inboxes
            Notification.objects.filter(call=call, read_at__isnull=True).update(read_at=now)
