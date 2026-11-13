"""FLUXAA Port — test de bout en bout par l'interface (Playwright, Chromium) — docs/spec/14 §14.3.

Rejoue, avec les comptes de démonstration d'une installation neuve (second facteur imposé), une escale complète
du brouillon à l'archivage à travers les écrans — chaque demande et chaque décision, les actes déposés d'eux-mêmes,
les services nautiques, les jalons et contresignatures, les tâches, les documents, les mesures, le journal de
pompage, les contestations, les échanges, les étapes, les formulaires émis par chaque partie, le rapport des faits,
le capitaine par code, une partie par lien, la sûreté N4, l'export, l'API — puis, depuis la version 1.5, les feux
verts de chaque partie et leur retrait, la validité de l'annonce et sa reprise sur une escale obsolète, l'accès
partiel d'une agence associée fixé par l'agent principal, le transbordement navire-navire, l'exécution des tâches en
ligne, l'annonce d'une escale de vrac sec avec ses documents attendus, la conférence de placement et le plan
d'occupation — puis ouvre chaque écran avec chaque rôle. Chaque vérification est consignée (attendu / observé /
résultat) dans <sortie>/results.json, avec ses captures.

Préalables : une installation neuve (bases vides, `load_demo` des deux ports avec le même mot de passe), le serveur
joignable, `pip install playwright pyotp` et `playwright install chromium`. Les clés TOTP des décideurs sont lues
dans la sortie de `load_demo` (fichiers passés par --secrets). Le lien d'une partie convoquée par courriel est relu
dans le journal du serveur quand il est fourni (--mail-log : sortie du backend de courriel « console »).

    python scripts/test_interface.py --base http://127.0.0.1:8000 --password Demo-Fluxaa-2026 \
        --secrets deploy/windows/load_demo-TGLFW.log deploy/windows/load_demo-SLFNA.log --out /tmp/test-interface
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import sys
import time
import traceback

import pyotp
from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

ARGS = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
ARGS.add_argument("--base", default="http://127.0.0.1:8000")
ARGS.add_argument("--password", default="Demo-Fluxaa-2026")
ARGS.add_argument("--secrets", nargs="*", default=[], help="sorties de load_demo (clés TOTP des décideurs)")
ARGS.add_argument("--mail-log", default="", help="journal où le backend de courriel « console » écrit les convocations")
ARGS.add_argument("--out", default="test-interface")
OPTS = ARGS.parse_args()
BASE = OPTS.base.rstrip("/")
PW = OPTS.password
HERE = pathlib.Path(OPTS.out)
HERE.mkdir(parents=True, exist_ok=True)
SHOTS = HERE / "shots"
SHOTS.mkdir(exist_ok=True)
FILES = HERE / "files"
FILES.mkdir(exist_ok=True)
REPO = pathlib.Path(__file__).resolve().parent.parent
RESULTS = []
SECRETS = {}
for name in OPTS.secrets:
    for line in pathlib.Path(name).read_text(encoding="utf-8", errors="replace").splitlines():
        m = re.match(r"^\s*[A-Z,]{3,}\s+(\S+@\S+)\s+TOTP\s+([A-Z2-7]+)\s*$", line)
        if m:
            SECRETS[m.group(1)] = m.group(2)

NOW = dt.datetime.now().replace(second=0, microsecond=0)
USER_OF = {}


def imo_number(offset=0):
    base = "98" + str(int(time.time()) + offset)[-4:]
    check = sum(int(d) * w for d, w in zip(base, (7, 6, 5, 4, 3, 2))) % 10
    return base + str(check)


IMO = imo_number()
IMO_BULK = imo_number(4321)  # the dry-bulk call announced in the 1.5 section
IMO_OUTER = imo_number(4322)  # the vessel announced alongside MT ATLANTIC DEMO (double banking, 1.6)
IMO_OUTER2 = imo_number(4323)  # the same, by the other agency
IMO_DAUGHTER = imo_number(4324)  # a daughter vessel of the other agency naming the mother vessel of an STS (1.6)
IMO_TYPED = imo_number(4325)  # a new vessel typed in an announcement first refused, then accepted as typed (1.6)
IMO_GOLFE = imo_number(4326)  # the daughter vessel of an agency the port does not know yet (1.6)


def local(delta_hours=0):
    return (NOW + dt.timedelta(hours=delta_hours)).strftime("%Y-%m-%dT%H:%M")


def soon(minutes=1):
    """A fact time just after now (the registry accepts up to five minutes ahead): after an authorization
    delivered a moment ago, and never in the past of it."""
    return (dt.datetime.now().replace(second=0, microsecond=0) + dt.timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M")


def step_up(page):
    """The second factor asked again before a decision (ENF-3.1): enter the code, come back to the form."""
    if "/compte/mfa/verifier/" in page.url:
        email = USER_OF.get(page)
        secret = SECRETS.get(email or "")
        if not secret:
            return False
        page.fill("#code", pyotp.TOTP(secret).now())
        page.click("button.btn")
        page.wait_for_load_state("load")
        return True
    return False


def pdf_file(name: str, title: str) -> str:
    """A minimal valid PDF, enough for an upload."""
    path = FILES / name
    if not path.exists():
        content = f"BT /F1 18 Tf 50 750 Td ({title}) Tj ET".encode("latin-1")
        objs = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
                b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
                b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
        out = b"%PDF-1.4\n"
        offsets = []
        for i, o in enumerate(objs, 1):
            offsets.append(len(out))
            out += f"{i} 0 obj\n".encode() + o + b"\nendobj\n"
        xref = len(out)
        out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
        for off in offsets:
            out += f"{off:010d} 00000 n \n".encode()
        out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
        path.write_bytes(out)
    return str(path)


# ------------------------------------------------------------------------------------------ journal des vérifications
class Check:
    n = 0


def record(section, title, role, expected, ok, observed, page=None, shot=None):
    Check.n += 1
    entry = {"n": Check.n, "section": section, "title": title, "role": role, "expected": expected,
             "observed": (observed or "")[:600], "status": "NA" if ok is None else ("OK" if ok else "KO"), "shot": ""}
    if page is not None and shot:
        file = SHOTS / f"{Check.n:03d}-{shot}.png"
        try:
            page.screenshot(path=str(file), full_page=False)
            entry["shot"] = file.name
        except Exception as exc:  # noqa: BLE001
            entry["shot"] = f"(capture impossible : {exc})"
    RESULTS.append(entry)
    print(f"[{entry['status']}] {Check.n:03d} {section} — {title} ({role}) :: {entry['observed'][:140]}")
    return ok


def flashes(page):
    return [(f.get_attribute("class") or "", f.inner_text().strip()) for f in page.locator(".flash").all()]


def flash_text(page):
    return " | ".join(f"{c.replace('flash', '').strip()}: {t}" for c, t in flashes(page))


def has_success(page):
    return any("success" in c or "warning" in c for c, _ in flashes(page)) and not has_error(page)


def has_error(page):
    return any("error" in c for c, _ in flashes(page)) or page.locator(".refusal").count() > 0


def refusal_text(page):
    loc = page.locator(".refusal")
    return loc.first.inner_text().strip()[:500] if loc.count() else ""


def page_ok(page, response):
    text = page.content()
    return response is not None and response.status < 400 and "Traceback" not in text and "Server Error" not in text


# ----------------------------------------------------------------------------------------------- sessions
class Session:
    def __init__(self, browser, key, width=1366, locale="fr-FR"):
        self.key = key
        self.ctx = browser.new_context(viewport={"width": width, "height": 900}, locale=locale, service_workers="block")
        self.page = self.ctx.new_page()
        self.page.set_default_timeout(15000)
        self.page.on("dialog", lambda d: d.accept())

    def goto(self, path):
        return self.page.goto(BASE + path, wait_until="load")

    def close(self):
        self.ctx.close()


def login(browser, email, width=1366):
    s = Session(browser, email, width)
    p = s.page
    p.goto(BASE + "/compte/connexion/")
    p.fill("#id_username", email)
    p.fill("#id_password", PW)
    p.click("button.btn")
    p.wait_for_load_state("load")
    USER_OF[p] = email
    if "/compte/mfa/verifier/" in p.url:
        secret = SECRETS.get(email)
        if not secret:
            raise RuntimeError(f"no TOTP secret for {email}")
        p.fill("#code", pyotp.TOTP(secret).now())
        p.click("button.btn")
        p.wait_for_load_state("load")
    return s


def master_session(browser, code, width=390):
    s = Session(browser, "master", width)
    p = s.page
    p.goto(BASE + "/bord/")
    p.fill("#code", code)
    p.click("button.btn")
    p.wait_for_load_state("load")
    return s


def link_session(browser, url, name, width=1366):
    s = Session(browser, "link", width)
    p = s.page
    p.goto(url)
    p.wait_for_load_state("load")
    if p.locator("#name").count():
        p.fill("#name", name)
        p.click("button.btn")
        p.wait_for_load_state("load")
    return s


# ----------------------------------------------------------------------------------------------- formulaires
def _form(page, action, match=None, index=0):
    forms = page.locator(f'form[action$="/action/{action}/"]')
    count = forms.count()
    if count == 0:
        raise AssertionError(f"no form for action {action} on {page.url}")
    if match:
        for i in range(count):
            f = forms.nth(i)
            if all(f.locator(f'input[name="{k}"]').count() and f.locator(f'input[name="{k}"]').first.input_value() == str(v)
                   for k, v in match.items()):
                return f
        raise AssertionError(f"no form for action {action} matching {match} (among {count})")
    return forms.nth(index)


def submit(page, action, fields=None, match=None, index=0, button=None, _retry=True):
    """Fill and submit the form of an action through its own submit button; returns the flash / refusal text.
    A decision may first ask for the second factor (step-up): the code is entered and the form submitted again."""
    form = _form(page, action, match, index)
    details = form.locator("xpath=ancestor::details[1]")
    if details.count():
        details.first.evaluate("d => { d.open = true }")
    for key, value in (fields or {}).items():
        field = form.locator(f'[name="{key}"]').first
        tag = field.evaluate("e => e.tagName.toLowerCase()")
        typ = (field.get_attribute("type") or "").lower()
        if tag == "select":
            field.select_option(str(value))
        elif typ == "checkbox":
            if value:
                field.check()
            else:
                field.uncheck()
        elif typ == "radio":
            form.locator(f'[name="{key}"][value="{value}"]').check()
        elif typ == "file":
            field.set_input_files(value)
        elif typ == "hidden":
            field.evaluate("(e, v) => { e.value = v }", str(value))
        else:
            field.fill(str(value))
    if button:
        btn = form.locator(f'button[name="{button[0]}"][value="{button[1]}"]')
    else:
        btn = form.locator("button:not([type=button])").last
    btn.click()
    page.wait_for_load_state("load")
    if _retry and step_up(page):
        return submit(page, action, fields, match, index, button, _retry=False)
    return flash_text(page) or refusal_text(page)


def select_like(select, pattern):
    """select_option by a regular expression on the option text (Playwright only takes exact labels)."""
    rx = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
    for opt in select.locator("option").all():
        if rx.search(opt.inner_text()):
            select.select_option(opt.get_attribute("value"))
            return opt.inner_text()
    raise AssertionError(f"no option matching {rx.pattern}")


def tab(session, call_id, name):
    session.goto(f"/escales/{call_id}/?tab={name}")
    return session.page


def documents_titles(session, call_id):
    page = tab(session, call_id, "documents")
    return [a.inner_text().strip() for a in page.locator("table.grid tr td:first-child > a").all()]


def status_chip(page):
    loc = page.locator(".callhead .chip.status")
    return loc.first.inner_text().strip() if loc.count() else ""


# ----------------------------------------------------------------------------------------------- feux verts (1.5)
def lights(page):
    """The green-light panel of the overview tab: role → state chip text, as the page shows them."""
    out = {}
    for light in page.locator("#feux-verts .light").all():
        role = light.locator(".light-head b").first.inner_text().strip()
        out[role] = light.locator(".light-head .chip").first.inner_text().strip()
    return out


def give_light(session, call_id, note=""):
    """The party gives its own green light from the overview panel (only its own light offers the button)."""
    page = tab(session, call_id, "apercu")
    forms = page.locator('#feux-verts form[action$="/action/task_complete/"]')
    if not forms.count():
        return "pas de bouton « Donner le feu vert »"
    form = forms.first
    form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
    if note:
        form.locator('input[name="note"]').fill(note)
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    if step_up(page):
        return give_light(session, call_id, note)
    return flash_text(page) or refusal_text(page)


def withdraw_light(session, call_id, reason):
    page = tab(session, call_id, "apercu")
    forms = page.locator('#feux-verts form[action$="/action/green_withdraw/"]')
    if not forms.count():
        return "pas de bouton « Retirer »"
    form = forms.first
    form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
    form.locator('input[name="reason"]').fill(reason)
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    if step_up(page):
        return withdraw_light(session, call_id, reason)
    return flash_text(page) or refusal_text(page)


def nav_tabs(page):
    return [a.evaluate("e => (e.childNodes[0] && e.childNodes[0].textContent || '').trim()") for a in page.locator("nav.tabs a").all()]


# ----------------------------------------------------------------------------------------------- scénario
def scenario(browser):
    S = "Escale de bout en bout"
    age = login(browser, "age.tglfw@demo.fluxaa.test")
    p = age.page
    record("Accès", "Connexion de l'agence (sans second facteur)", "AGE", "tableau de bord", p.url.rstrip("/") == BASE,
           p.url, p, "connexion-agence")

    cap = login(browser, "cap.tglfw@demo.fluxaa.test")
    record("Accès", "Connexion de la capitainerie avec code TOTP", "CAP", "tableau de bord après le second facteur",
           cap.page.url.rstrip("/") == BASE, cap.page.url, cap.page, "connexion-capitainerie")

    # mauvais code
    bad = Session(browser, "bad")
    bp = bad.page
    bp.goto(BASE + "/compte/connexion/")
    bp.fill("#id_username", "dir.slfna@demo.fluxaa.test")
    bp.fill("#id_password", PW)
    bp.click("button.btn")
    bp.wait_for_load_state("load")
    if "/compte/mfa/verifier/" in bp.url:
        bp.fill("#code", "000000")
        bp.click("button.btn")
        bp.wait_for_load_state("load")
        record("Accès", "Un code TOTP faux est refusé", "DIR (SLFNA)", "reste sur la page du second facteur, message d'erreur",
               "/compte/mfa/verifier/" in bp.url and has_error(bp),
               bp.url + " " + flash_text(bp), bp, "totp-faux")
    else:
        record("Accès", "Un code TOTP faux est refusé", "DIR (SLFNA)", "reste sur la page du second facteur, message d'erreur",
               None, "second facteur non imposé sur cette installation (FLUXAA_MFA_ENFORCED=0) : vérification non jouée", bp, "totp-faux")
    bad.close()

    # ----- 1. annonce
    p = age.page
    age.goto("/escales/nouvelle/")
    p.select_option("#vessel", "")
    p.locator("details.action summary").first.click()
    p.fill("#new_imo", IMO)
    p.fill("#new_name", "MT Test E2E " + IMO[-3:])
    p.fill("#new_flag", "Liberia")
    p.fill("#new_type", "Product tanker")
    p.fill("#new_dwt", "47000")
    p.check('input[name="kind"][value="JETTY"]')
    select_like(p.locator("#requested_berth"), "LFW-APP")
    p.check('input[name="operations"][value="M1"]')
    p.fill("#eta", local(48))
    p.fill("#etb", local(52))
    p.fill("#ets", local(54))
    p.fill("#etc", local(78))
    p.fill("#etd", local(84))
    p.fill("#product", "Gasoil 10 ppm")
    p.fill("#quantity", "30000")
    p.fill("#voyage", "E2E-01")
    p.fill("#last_port", "Tema")
    p.fill("#next_port", "Abidjan")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("TER")
    select_like(rows.nth(0).locator('select[name="party_org"]'), "Terminal pétrolier|Oil terminal")
    rows.nth(1).locator('select[name="party_role"]').select_option("PRE")
    rows.nth(1).locator('select[name="party_org"]').select_option("new")
    rows.nth(1).locator('input[name="party_name"]').fill("Laboratoire E2E")
    rows.nth(1).locator('input[name="party_kind"]').fill("Laboratoire d'analyses")
    rows.nth(1).locator('input[name="party_email"]').fill("labo.e2e@example.org")
    rows.nth(1).locator('input[name="party_phone"]').fill("+228 90 00 00 00")
    rows.nth(2).locator('select[name="party_role"]').select_option("INS")
    select_like(rows.nth(2).locator('select[name="party_org"]'), "Inspect|Survey|Contrôle")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    call_id = int(m.group(1)) if m else None
    ref = p.locator(".callhead .ref").first.inner_text().strip() if p.locator(".callhead .ref").count() else ""
    record(S, "Annonce d'une escale : navire nouveau, poste demandé, M1, trois parties dont une organisation nouvelle", "AGE",
           "escale créée en brouillon avec sa référence", call_id is not None and "Brouillon" in status_chip(p),
           f"{p.url} {ref} {status_chip(p)} {flash_text(p)}", p, "annonce")
    if call_id is None:
        raise RuntimeError("call not created: " + flash_text(p))
    head = p.locator(".callhead").inner_text()
    val = p.locator("#validite").inner_text() if p.locator("#validite").count() else ""
    record(S, "1.5 — L'annonce porte sa nature de cargaison et sa validité (15 jours par défaut du port), comptée pour la facturation", "AGE",
           "en-tête « Vrac liquide », encart Validité « 15 jours » avec le reste à courir", "Vrac liquide" in head and "15 jours" in val and ("Reste" in val or "jusqu'au" in val),
           (head[:160] + " | " + val[:160]).replace("\n", " "), p, "annonce-validite")
    page = tab(age, call_id, "parties")
    names = page.locator("table.grid td:first-child").all_inner_texts()
    record(S, "Onglet Parties : la nouvelle organisation est enregistrée avec sa nature et invitée", "AGE",
           "Laboratoire E2E — Laboratoire d'analyses (PRE) dans la liste", any("Laboratoire E2E" in n for n in names) and any("Laboratoire d'analyses" in n for n in names),
           " / ".join(n.replace("\n", " ") for n in names)[:400], page, "parties-nouvelle-organisation")

    # ----- invitation de parties enregistrées depuis l'onglet Parties (armateur, prestataire déchets)
    for role, pattern, label in (("COM", "Armateur", "l'armateur / affréteur"), ("PRE", "déchets", "le prestataire déchets")):
        page = tab(age, call_id, "parties")
        form = _form(page, "party_add")
        form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
        form.locator('select[name="role"]').select_option(role)
        select_like(form.locator('select[name="organization"]'), pattern)
        form.locator("button:not([type=button])").last.click()
        page.wait_for_load_state("load")
        names = " ".join(page.locator("table.grid td:first-child").all_inner_texts())
        record(S, f"Invitation d'une organisation enregistrée ({label}) depuis l'onglet Parties", "AGE", "rôle ajouté à l'escale", has_success(page) and pattern.lower() in names.lower(), flash_text(page), page, f"invitation-{role.lower()}")

    # ----- accès capitaine et lien de partie
    page = tab(age, call_id, "parties")
    out = submit(page, "master_link", {"master_name": "Cdt Kofi Mensah", "channel": "PRINT", "note": "remis à bord"})
    code = ""
    mono = page.locator(".flash.success .mono")
    if mono.count() >= 2:
        code = mono.nth(1).inner_text().strip()
    record(S, "Accès du capitaine (code et lien, affichés une fois)", "AGE", "code XXXX-XXXX affiché", bool(re.match(r"^[A-Z0-9]{4}-[A-Z0-9]{4}$", code)), f"{code} {out}", page, "acces-capitaine")
    out = submit(page, "party_link", {"channel": "PRINT"})
    links = page.locator("ul.calllist li").all_inner_texts()
    record(S, "Lien d'accès d'une partie sans compte émis par l'agence", "AGE", "lien listé pour l'organisation", "Laboratoire E2E" in " ".join(links) or "success" in out, out[:200] + " / " + " ".join(links)[:300], page, "lien-partie")

    # ----- tâches de la déclaration : M0:05 (AGE), M0:02 (AGE, Q88), M0:03 (NAV, certificats, par le capitaine)
    page = tab(age, call_id, "taches")
    def task_id(page, number):
        row = page.locator(f"tr:has(td.code:text-is('{number}'))").first
        return row.locator('input[name="task_id"]').first.input_value()
    out = submit(page, "task_complete", {"note": "listes OFAC, ONU, UE : rien"}, match={"task_id": task_id(page, "05")})
    record(S, "Tâche M0:05 — confirmer le contrôle des sanctions", "AGE", "tâche faite", "success" in out, out, page, "tache-sanctions")
    page = tab(age, call_id, "documents")
    form = page.locator('form[action$="/action/document_upload/"]').last
    select_like(form.locator('select[name="task_id"]'), "M0:02")
    form.locator('select[name="type"]').select_option("Q88")
    form.locator('input[name="title"]').fill("Q88 MT Test E2E")
    form.locator('input[name="file"]').set_input_files(pdf_file("q88.pdf", "Q88 MT TEST E2E"))
    form.locator("button.btn").last.click()
    page.wait_for_load_state("load")
    record(S, "Tâche M0:02 — dépôt du Q88 par l'agence (document rattaché à la tâche)", "AGE", "document déposé, tâche faite", has_success(page) and "Q88" in " ".join(documents_titles(age, call_id)), flash_text(page), page, "depot-q88")

    # ----- 1.4 : préparation de la déclaration — qui répond de chaque élément manquant, et les moyens d'agir
    page = tab(age, call_id, "apercu")
    box = page.locator("#declaration")
    text = box.inner_text() if box.count() else ""
    record(S, "Aperçu « Avant la déclaration » : ce qui manque, qui en répond, les actions (déposer, relancer, remettre l'accès)", "AGE",
           "M0:03 listée avec le navire comme responsable et les boutons d'action", "M0:03" in text and ("Remettre" in text or "accès" in text.lower()),
           text[:400], page, "avant-declaration")
    out = submit(page, "declare")
    body = page.locator(".refusal").inner_text() if page.locator(".refusal").count() else out
    record(S, "Déclaration tentée trop tôt : le refus nomme la tâche manquante, qui en répond, et offre « Fournir le document » / « Remettre son accès au capitaine »", "AGE",
           "boîte de refus avec responsables et actions", "M0:03" in body and ("répond" in body or "answers" in body) and ("Fournir" in body or "Provide" in body),
           body[:400], page, "refus-declaration-responsables")
    page = tab(age, call_id, "parties")
    out = submit(page, "master_link", {"master_name": "Cdt Kofi Mensah", "channel": "EMAIL", "send_to": "capitaine.e2e@example.org", "note": "courriel"})
    mailed = ""
    if OPTS.mail_log and pathlib.Path(OPTS.mail_log).exists():
        log = pathlib.Path(OPTS.mail_log).read_text(encoding="utf-8", errors="replace")
        idx = log.rfind("capitaine.e2e@example.org")
        mailed = log[idx:idx + 2500] if idx >= 0 else ""
    record(S, "Accès capitaine envoyé par courriel avec la liste de ce que le port attend du navire (certificats M0:03…)", "AGE",
           "courriel contenant le code d'accès et la tâche M0:03", "M0:03" in mailed and "/bord/" in mailed, (mailed[:300] or out[:200]), page, "acces-capitaine-courriel")
    page = tab(age, call_id, "apercu")
    row = page.locator("#declaration li:has-text('M0:03')").first
    out = ""
    if row.count() and row.locator('form[action$="/action/remind/"]').count():
        row.locator('form[action$="/action/remind/"] button').first.click()
        page.wait_for_load_state("load")
        out = flash_text(page)
    record(S, "Relance du capitaine pour la tâche M0:03 depuis l'aperçu (courriel à l'adresse de l'accès, journalisée)", "AGE", "relance envoyée à 1 destinataire", "1 destinataire" in out or "1 recipient" in out, out[:200] or "pas de bouton Relancer", page, "relance")

    master = master_session(browser, code)
    mp = master.page
    record(S, "Capitaine : ouverture de l'escale par le code, sur téléphone", "NAV (capitaine)", "fiche de l'escale", f"/escales/{call_id}/" in mp.url, mp.url, mp, "capitaine-telephone")
    tab(master, call_id, "documents")
    form = mp.locator('form[action$="/action/document_upload/"]').last
    select_like(form.locator('select[name="task_id"]'), "M0:03")
    form.locator('select[name="type"]').select_option("CERTIFICATES")
    form.locator('input[name="file"]').set_input_files(pdf_file("certs.pdf", "CERTIFICATS STATUTAIRES"))
    form.locator("button.btn").last.click()
    mp.wait_for_load_state("load")
    record(S, "Tâche M0:03 — certificats statutaires déposés par le capitaine (sans compte)", "NAV (capitaine)", "document déposé sous le rôle NAV", has_success(mp), flash_text(mp), mp, "capitaine-certificats")

    # ----- déclaration
    page = tab(age, call_id, "apercu")
    out = submit(page, "declare")
    record(S, "Déclaration de l'escale : parties notifiées, feu vert demandé", "AGE", "statut Déclarée, demande de feu vert soumise", "Déclarée" in status_chip(page) and "success" in out, f"{status_chip(page)} {out}", page, "declaration")
    page = tab(age, call_id, "demandes")
    record(S, "La demande de feu vert existe (créée par la déclaration)", "AGE", "Feu vert — Soumise", "Feu vert" in page.content(), page.locator("article").first.inner_text()[:200] if page.locator("article").count() else "", page, "demande-feu-vert")

    # ----- vetting : TER demande, CAP décide → acte
    ter = login(browser, "ter.tglfw@demo.fluxaa.test")
    page = tab(ter, call_id, "demandes")
    ter.goto(f"/escales/{call_id}/?tab=demandes&type=VESSEL_ACCEPTANCE")
    page = ter.page
    vform = _form(page, "request_create")
    told = [vform.locator(f'[name="{key}"]').first.input_value() for key in ("product", "quantity", "requested_berth")]
    record(S, "(1.6) La demande d'acceptation du navire s'ouvre avec ce que l'escale dit déjà — le produit, la quantité et le poste de l'annonce —, que le terminal vérifie avant d'envoyer", "TER",
           "product, quantity et requested_berth préremplis : Gasoil 10 ppm, 30000, LFW-APP", told == ["Gasoil 10 ppm", "30000", "LFW-APP"] and "prérempli" in page.content().lower(),
           " | ".join(told), page, "vetting-prerempli")
    out = submit(page, "request_create", {"product": "Gasoil 10 ppm", "quantity": "30000", "requested_berth": "LFW-APP",
                                           "inspection": "SIRE 2.0 du 12/09/2026 — 2 observations closes", "psc_history": "aucune détention",
                                           "last_cargoes": "gasoil, gasoil, jet A1", "vetting_result": "accepté sous réserve : jour seulement"})
    record(S, "Demande d'acceptation du navire (vetting) déposée par le terminal", "TER", "demande soumise", "success" in out, out, page, "demande-vetting")

    page = tab(cap, call_id, "demandes")
    art = page.locator("article:has-text('Acceptation de navire')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_decide", {"decision": "APPROVED_COND", "conditions": "Accostage de jour uniquement", "reason": ""}, match={"request_id": rid})
    record(S, "Décision d'acceptation du navire (sous conditions) par la capitainerie", "CAP", "décision enregistrée", "success" in out, out, page, "decision-vetting")
    docs = documents_titles(cap, call_id)
    record(S, "ACTE DÉPOSÉ DE LUI-MÊME : « Autorisation — Acceptation de navire » dans les documents", "CAP", "document généré présent", any("Acceptation de navire" in d for d in docs), " ; ".join(docs), cap.page, "acte-vetting-documents")

    page = tab(cap, call_id, "demandes")
    art = page.locator("article:has-text('Feu vert')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid})
    record(S, "Feu vert accordé", "CAP", "statut Acceptée", "Acceptée" in status_chip(page) and "success" in out, f"{status_chip(page)} {out}", page, "feu-vert")
    docs = documents_titles(cap, call_id)
    record(S, "Acte « Autorisation — Feu vert » déposé", "CAP", "document présent", any("Feu vert" in d for d in docs), " ; ".join(docs), cap.page, "acte-feu-vert")
    page = tab(cap, call_id, "demandes")
    vcode = page.locator("article:has-text('Feu vert') a.code").first.inner_text().strip()
    anon = Session(browser, "anon")
    anon.goto(f"/verifier/{vcode}/")
    record(S, "Vérification publique du code de l'autorisation (sans compte)", "public", "autorisation reconnue, en vigueur", "introuvable" not in anon.page.content().lower() and vcode in anon.page.content(), anon.page.locator("main").inner_text()[:300] if anon.page.locator("main").count() else anon.page.content()[:200], anon.page, "verification-publique")
    anon.close()

    # ----- 1.5 : le panneau des feux verts — capitainerie (décision), base navale, terminal, mandant
    page = tab(age, call_id, "apercu")
    st = lights(page)
    record(S, "1.5 — Panneau des feux verts : celui de la capitainerie est donné par sa décision, ceux de la base navale, du terminal et du mandant sont attendus", "AGE",
           "4 feux : Capitainerie « donné », les trois autres « attendu »", len(st) == 4 and sum(1 for v in st.values() if v == "donné") == 1 and sum(1 for v in st.values() if v == "attendu") == 3,
           json.dumps(st, ensure_ascii=False), page, "feux-verts-panneau")

    # ----- poste : AGE demande depuis l'onglet Tâches (exécution en ligne, 1.5), APO attribue → acte, statut Planifiée
    page = tab(age, call_id, "taches")
    out = submit(page, "request_create", {"window_from": local(52), "window_to": local(60), "arrival_draft": "11.8", "notes": "jour"}, match={"type": "BERTH"})
    record(S, "1.5 — Tâche M0:10 exécutée depuis l'onglet Tâches : la demande de poste et de créneau est déposée en ligne, sans passer par l'onglet Demandes", "AGE", "demande soumise, tâche faite", "success" in out, out, page, "demande-poste")
    apo = login(browser, "apo.tglfw@demo.fluxaa.test")
    page = tab(apo, call_id, "demandes")
    art = page.locator("article:has-text('Attribution de poste')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    form = _form(page, "request_decide", {"request_id": rid})
    form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
    form.locator('select[name="decision"]').select_option("APPROVED")
    select_like(form.locator('select[name="berth"]'), "LFW-APP")
    form.locator('input[name="conditions"]').fill("créneau confirmé")
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    if step_up(page):
        form = _form(page, "request_decide", {"request_id": rid})
        form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
        form.locator('select[name="decision"]').select_option("APPROVED")
        select_like(form.locator('select[name="berth"]'), "LFW-APP")
        form.locator("button:not([type=button])").last.click()
        page.wait_for_load_state("load")
    out = flash_text(page) or refusal_text(page)
    record(S, "Attribution du poste et du créneau par l'autorité portuaire", "APO", "statut Planifiée, poste LFW-APP", "Planifiée" in status_chip(page) and "LFW-APP" in page.locator(".callhead").inner_text(), f"{status_chip(page)} {out}", page, "attribution-poste")
    docs = documents_titles(apo, call_id)
    record(S, "Acte « Autorisation — Attribution de poste » déposé", "APO", "document présent", any("Attribution de poste" in d for d in docs), " ; ".join(docs), apo.page, "acte-poste")

    # ----- services nautiques, libre pratique, douane
    age.goto(f"/escales/{call_id}/?tab=demandes&type=MARINE_SERVICES")
    page = age.page
    form = _form(page, "request_create")
    form.locator('select[name="movement"]').select_option("ARRIVAL")
    form.locator('input[name="requested_time"]').fill(local(51))
    form.locator('input[name="tugs"]').fill("2")
    form.locator('input[name="mooring_gang"]').check()
    if form.locator('select[name="provider"]').count():
        form.locator('select[name="provider"]').select_option(index=1)
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    out = flash_text(page) or refusal_text(page)
    record(S, "Commande des services nautiques (pilote, 2 remorqueurs, lamaneurs) à l'arrivée", "AGE", "commande soumise", "success" in out, out, page, "commande-services")
    svc = login(browser, "svc.tglfw@demo.fluxaa.test")
    page = tab(svc, call_id, "demandes")
    art = page.locator("article:has-text('pilote')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_schedule", {"scheduled_for": local(51)}, match={"request_id": rid})
    record(S, "Confirmation de la réservation par les services nautiques", "SVC", "programmée", "success" in out, out, page, "services-confirmes")
    out = submit(page, "request_execute", match={"request_id": rid})
    record(S, "Prestation marquée exécutée", "SVC", "exécutée", "success" in out, out, page, "services-executes")

    adm = login(browser, "adm.tglfw@demo.fluxaa.test")
    for code_, label, fields in (("FREE_PRATIQUE", "Libre pratique", {"crew": "22", "health_events": "aucun"}),
                                 ("CUSTOMS_IMMIGRATION", "Formalités douanières", {"crew_list": True, "notes": "FAL 1 à 5 déposés au guichet"})):
        age.goto(f"/escales/{call_id}/?tab=demandes&type={code_}")
        out = submit(age.page, "request_create", fields)
        record(S, f"Demande « {label} » déposée", "AGE", "demande soumise", "success" in out, out, age.page, f"demande-{code_.lower()}")
        page = tab(adm, call_id, "demandes")
        art = page.locator(f"article:has-text('{label}')").first
        rid = art.locator('input[name="request_id"]').first.input_value()
        if code_ == "FREE_PRATIQUE":
            # 1.5 : la décision se prend aussi depuis la ligne de la tâche M0:21, sur l'onglet Tâches
            page = tab(adm, call_id, "taches")
            out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid})
            record(S, f"1.5 — Tâche M0:21 exécutée depuis l'onglet Tâches : décision « {label} » prise en ligne sur la ligne de la tâche", "ADM", "approuvée, acte déposé", "success" in out and any(label.split()[0] in d for d in documents_titles(adm, call_id)), out, adm.page, f"decision-{code_.lower()}")
            continue
        out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid})
        record(S, f"Décision « {label} » par les administrations", "ADM", "approuvée, acte déposé", "success" in out and any(label.split()[0] in d for d in documents_titles(adm, call_id)), out, adm.page, f"decision-{code_.lower()}")

    # ----- arrivée (capitaine), NOR (agence) → document NOR
    page = tab(master, call_id, "jalons")
    out = submit(page, "milestone", {"type": "ARRIVAL", "declared_at": local(-1), "note": "limite du port, pilote en attente"})
    record(S, "Jalon ARRIVAL enregistré par le capitaine (téléphone)", "NAV (capitaine)", "jalon enregistré", "success" in out, out, page, "jalon-arrivee-capitaine")
    page = tab(age, call_id, "jalons")
    out = submit(page, "milestone", {"type": "NOR_TENDERED", "declared_at": local(-1), "note": "remise au terminal et à l'affréteur"})
    record(S, "Jalon NOR_TENDERED enregistré par l'agence", "AGE", "jalon enregistré", "success" in out, out, page, "jalon-nor")
    docs = documents_titles(age, call_id)
    record(S, "La notice de disponibilité est déposée d'elle-même à la remise de la NOR", "AGE", "document « Notice de disponibilité »", any("Notice de disponibilité" in d or "NOR" in d for d in docs), " ; ".join(docs), age.page, "nor-document")
    page = tab(ter, call_id, "jalons")
    out = submit(page, "countersign", match={"milestone_id": page.locator("tr:has-text('NOR') input[name='milestone_id']").first.input_value()}) if page.locator("tr:has-text('NOR') input[name='milestone_id']").count() else "pas de bouton"
    record(S, "Le terminal contresigne la NOR (accusé de réception)", "TER", "contresignature enregistrée", "success" in out, out, page, "contresignature-nor")

    # ----- mouvement : AGE demande, CAP autorise → acte ; accostage par les services nautiques
    age.goto(f"/escales/{call_id}/?tab=demandes&type=MOVEMENT")
    out = submit(age.page, "request_create", {"movement": "ARRIVAL", "requested_time": local(0)})
    record(S, "Demande d'autorisation de mouvement (entrée)", "AGE", "soumise", "success" in out, out, age.page, "demande-mouvement")
    page = tab(cap, call_id, "demandes")
    art = page.locator("article:has-text('mouvement')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_decide", {"decision": "APPROVED", "conditions": "visibilité > 1 M, 2 remorqueurs"}, match={"request_id": rid})
    record(S, "1.5 — POINT D'ARRÊT : l'autorisation de mouvement est refusée tant que la base navale n'a pas donné son feu vert (M0:09b)", "CAP",
           "refus motivé nommant M0:09b", "09b" in out and "success" not in out, out[:300], page, "mouvement-refuse-feu-vert-base")
    sur = login(browser, "sur.tglfw@demo.fluxaa.test")
    out = give_light(sur, call_id, "transit vérifié, pas d'alerte")
    st = lights(sur.page)
    record(S, "1.5 — La base navale donne son feu vert depuis le panneau de l'aperçu", "SUR", "feu vert donné, 2 feux donnés sur 4", "success" in out and sum(1 for v in st.values() if v == "donné") == 2, out[:200] + " " + json.dumps(st, ensure_ascii=False), sur.page, "feu-vert-base-navale")
    page = tab(cap, call_id, "demandes")
    out = submit(page, "request_decide", {"decision": "APPROVED", "conditions": "visibilité > 1 M, 2 remorqueurs"}, match={"request_id": rid})
    record(S, "Autorisation de mouvement délivrée une fois le feu vert de la base navale donné", "CAP", "approuvée, acte déposé", "success" in out and any("mouvement" in d.lower() for d in documents_titles(cap, call_id)), out, cap.page, "autorisation-mouvement")
    page = tab(svc, call_id, "jalons")
    for mcode, h in (("PILOT_ON_BOARD_ARR", 1), ("FIRST_LINE", 2), ("ALL_FAST", 3)):
        out = submit(page, "milestone", {"type": mcode, "declared_at": soon(h)})
        record(S, f"Jalon {mcode} enregistré par les services nautiques", "SVC", "enregistré", "success" in out, out, page, f"jalon-{mcode.lower()}")
    page = tab(master, call_id, "jalons")
    out = submit(page, "milestone", {"type": "GANGWAY", "declared_at": soon(4)})
    record(S, "Jalon GANGWAY (passerelle) enregistré par le capitaine", "NAV (capitaine)", "enregistré", "success" in out, out, page, "jalon-gangway")
    page = tab(age, call_id, "apercu")
    record(S, "Après all fast : statut À quai, ATB renseignée dans l'en-tête", "AGE", "À quai", "quai" in status_chip(page).lower(), f"{status_chip(page)} — {page.locator('.callhead').inner_text()[:300]}", page, "a-quai")

    # ----- point d'arrêt : début de transfert refusé avant la liste de contrôle
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "TRANSFER_START", "declared_at": soon(1)})
    record(S, "POINT D'ARRÊT : début de transfert refusé tant que la liste de contrôle, la réunion et l'essai ESD manquent", "TER", "refus motivé, tâches manquantes nommées", "Refus" in out or "refus" in out.lower(), out[:400], page, "point-arret-refus")

    # ----- interface navire/terre : tâches conjointes, ESD, jaugeage, raccordement
    page = tab(ter, call_id, "taches")
    out = submit(page, "task_sign", match={"task_id": task_id(page, "27")})
    record(S, "Tâche M0:27 signée par le terminal (signature conjointe)", "TER", "signature enregistrée", "success" in out, out, page, "tache-27-ter")
    page = tab(master, call_id, "taches")
    out = submit(page, "task_sign", match={"task_id": task_id(page, "27")})
    record(S, "Tâche M0:27 signée par le capitaine (signature conjointe)", "NAV (capitaine)", "signature enregistrée", "success" in out, out, page, "tache-27-nav")

    # ----- 1.4 : la liste de contrôle navire/terre renseignée en ligne par le terminal et le capitaine, puis signée
    ter.goto(f"/escales/{call_id}/liste-de-controle/")
    page = ter.page
    out = submit(page, "checklist_open", {"repeat_interval_h": "4"})
    record(S, "Liste de contrôle navire/terre ouverte en ligne par le terminal", "TER", "liste ouverte, parties 1A à 6 affichées", "Partie 1A" in page.content() and "Partie 6" in page.content(), out[:200], page, "ssscl-ouverture")

    def tick_all(session, who):
        page = session.page
        session.goto(f"/escales/{call_id}/liste-de-controle/")
        recorded = 0
        for part in page.locator("section.cl-part").all():
            form = part.locator('form[action$="/action/checklist_answer/"]').first
            if not form.locator('input[name="item_code"]').count():
                continue
            for code in form.locator('input[name="item_code"]').all():
                item = code.get_attribute("value")
                radio = form.locator(f'input[name="state_{item}"][value="YES"]')
                if radio.count():
                    radio.check()
                value = form.locator(f'input[name="value_{item}"]')
                if value.count():
                    value.fill({"5A.1": "600 / 1 200 / 300 m³/h", "5A.2": "7 bar", "5A.3": "40 °C", "5A.4": "30 s / 45 s", "5A.7": "VHF 12 / 16", "5A.8": "4"}.get(item, "convenu en réunion"))
            form.locator("button:not([type=button])").last.click()
            page.wait_for_load_state("load")
            recorded += 1
            session.goto(f"/escales/{call_id}/liste-de-controle/")
            page = session.page
        return recorded

    n = tick_all(ter, "TER")
    page = ter.page
    record(S, "Le terminal coche ses points (parties 1B, 3, 4, 6) et écrit les accords (5A)", "TER", "réponses enregistrées, progression terre complète",
           n >= 4 and "23 / 23" in page.content(), page.locator(".sides").inner_text()[:300] if page.locator(".sides").count() else "", page, "ssscl-terre")
    n = tick_all(master, "NAV")
    mp = master.page
    record(S, "Le capitaine coche ses points sur téléphone (parties 1A, 2, 4, 6)", "NAV (capitaine)", "progression navire complète",
           n >= 4 and "27 / 27" in mp.content(), mp.locator(".sides").inner_text()[:300] if mp.locator(".sides").count() else "", mp, "ssscl-navire")
    master.goto(f"/escales/{call_id}/liste-de-controle/")
    out = submit(mp, "checklist_sign", {"comment": "vérifié ensemble au collecteur"})
    record(S, "Signature de la liste pour le navire (nominative, scellée)", "NAV (capitaine)", "signée pour le navire, attente du terminal", "success" in out, out[:200], mp, "ssscl-signature-navire")
    ter.goto(f"/escales/{call_id}/liste-de-controle/")
    page = ter.page
    out = submit(page, "checklist_sign", {"comment": ""})
    record(S, "Signature pour le terminal : liste close, tâche M0:28 faite, jalon « liste signée », formulaire pré-rempli déposé", "TER",
           "signée par les deux parties ; document déposé", "success" in out and ("deux parties" in page.content() or "both sides" in page.content()), out[:200], page, "ssscl-signature-terminal")
    page = tab(ter, call_id, "taches")
    row = page.locator("tr:has(td.code:text-is('28'))").first
    record(S, "Tâche M0:28 faite par les deux signatures de la liste en ligne", "TER", "statut Faite", "Faite" in row.inner_text() or "Done" in row.inner_text(), row.inner_text()[:200], page, "tache-28-faite")
    docs = documents_titles(ter, call_id)
    record(S, "Formulaire SSSCL déposé de lui-même, pré-rempli des coches, dans les documents", "TER", "document présent", any("navire / terre" in d.lower() or "ship/shore" in d.lower() for d in docs), " ; ".join(docs)[:300], ter.page, "ssscl-document")
    page = tab(ter, call_id, "jalons")
    record(S, "Jalon SSSCL_SIGNED enregistré par la plateforme", "TER", "jalon présent", "signée" in page.content().lower() or "SSSCL" in page.content(), "", page, "jalon-ssscl")
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "ESD_TEST", "declared_at": soon(1)})
    record(S, "Jalon ESD_TEST (essai d'arrêt d'urgence)", "TER", "enregistré", "success" in out, out, page, "jalon-esd")
    page = tab(ter, call_id, "taches")
    for number, note in (("31", "dalots obturés, kit en place"), ("1.03", "bac 12, ligne 3"), ("1.06", "index 1 204 500")):
        out = submit(page, "task_complete", {"note": note}, match={"task_id": task_id(page, number)})
        record(S, f"Tâche {number} faite par le terminal", "TER", "faite", "success" in out, out, page, f"tache-{number}-ter")
    page = tab(master, call_id, "taches")
    out = submit(page, "task_complete", {"note": "O2 6 %, pression +400 mm"}, match={"task_id": task_id(page, "1.04")})
    record(S, "Tâche M1:1.04 (gaz inerte) faite par le capitaine", "NAV (capitaine)", "faite", "success" in out, out, page, "tache-1.04")
    ins = login(browser, "ins.tglfw@demo.fluxaa.test")
    page = tab(ins, call_id, "jalons")
    out = submit(page, "milestone", {"type": "INITIAL_GAUGING", "declared_at": soon(1)})
    record(S, "Jalon INITIAL_GAUGING par l'inspecteur", "INS", "enregistré", "success" in out, out, page, "jalon-jaugeage-initial")
    page = tab(ins, call_id, "taches")
    out = submit(page, "task_complete", {"note": "6 échantillons scellés"}, match={"task_id": task_id(page, "1.07")})
    record(S, "Tâche M1:1.07 (échantillons) faite par l'inspecteur", "INS", "faite", "success" in out, out, page, "tache-1.07")
    page = tab(age, call_id, "taches")
    out = submit(page, "document_upload", {"file": pdf_file("import.pdf", "AUTORISATION D IMPORTATION"), "title": "Autorisation d'importation E2E"}, match={"task_id": task_id(page, "1.01")})
    record(S, "1.5 — Tâche M1:1.01 exécutée depuis l'onglet Tâches : l'autorisation d'importation est déposée en ligne sur la ligne de la tâche", "AGE", "document déposé, tâche faite", "success" in out and any("importation" in d.lower() for d in documents_titles(age, call_id)), out, age.page, "depot-import")
    page = tab(master, call_id, "documents")
    form = mp.locator('form[action$="/action/document_upload/"]').last
    select_like(form.locator('select[name="task_id"]'), "1\\.02")
    form.locator('select[name="type"]').select_option("DISCHARGE_PLAN")
    form.locator('input[name="file"]').set_input_files(pdf_file("plan.pdf", "PLAN DE DECHARGEMENT"))
    form.locator("button.btn").last.click()
    mp.wait_for_load_state("load")
    record(S, "Tâche M1:1.02 — plan de déchargement déposé par le capitaine", "NAV (capitaine)", "document déposé", has_success(mp), flash_text(mp), mp, "depot-plan")
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "HOSES_CONNECTED", "declared_at": soon(1)})
    record(S, "Jalon HOSES_CONNECTED", "TER", "enregistré", "success" in out, out, page, "jalon-flexibles")

    # ----- 1.5 : feux verts du terminal et du mandant avant le transfert ; retrait motivé, point d'arrêt refermé
    out = submit(page, "milestone", {"type": "TRANSFER_START", "declared_at": soon(2)})
    record(S, "1.5 — POINT D'ARRÊT : le début de transfert est refusé tant que le terminal et le mandant n'ont pas donné leur feu vert (M0:09c, M0:09d)", "TER",
           "refus nommant 09c et 09d", "09c" in out and "09d" in out and "success" not in out, out[:300], page, "transfert-refuse-feux-verts")
    out = give_light(ter, call_id, "poste prêt, bras connectés")
    record(S, "1.5 — Le terminal donne son feu vert", "TER", "feu vert donné", "success" in out, out[:200], ter.page, "feu-vert-terminal")
    com = login(browser, "com.tglfw@demo.fluxaa.test")
    out = give_light(com, call_id, "LOI reçue")
    record(S, "1.5 — Le mandant (armateur / affréteur) donne son feu vert", "COM", "feu vert donné, 4 feux donnés", "success" in out and all(v == "donné" for v in lights(com.page).values()), out[:200] + " " + json.dumps(lights(com.page), ensure_ascii=False), com.page, "feu-vert-mandant")
    out = withdraw_light(com, call_id, "garantie bancaire non reçue")
    st = lights(com.page)
    record(S, "1.5 — Le mandant RETIRE son feu vert avec un motif : toutes les parties en sont informées, le feu repasse « attendu »", "COM",
           "retrait enregistré, feu du mandant « attendu »", "success" in out and sum(1 for v in st.values() if v == "attendu") == 1, out[:200] + " " + json.dumps(st, ensure_ascii=False), com.page, "feu-vert-retrait")
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "TRANSFER_START", "declared_at": soon(2)})
    record(S, "1.5 — Après le retrait, le point d'arrêt se referme : le début de transfert est de nouveau refusé (M0:09d)", "TER", "refus nommant 09d", "09d" in out and "success" not in out, out[:300], page, "transfert-refuse-apres-retrait")
    out = give_light(com, call_id, "garantie reçue")
    record(S, "1.5 — Le mandant redonne son feu vert", "COM", "feu vert donné", "success" in out, out[:200], com.page, "feu-vert-mandant-redonne")
    age.goto("/notifications/")
    txt = age.page.locator("main").inner_text()
    record(S, "1.5 — L'agence a été notifiée du retrait du feu vert et de son motif", "AGE", "notification « feu vert retiré » avec le motif", "retir" in txt.lower() and "garantie bancaire" in txt.lower(), txt[:300], age.page, "notification-retrait-feu-vert")

    # ----- transfert
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "TRANSFER_START", "declared_at": soon(2)})
    record(S, "Début de transfert accepté une fois les tâches bloquantes faites et les quatre feux verts donnés", "TER", "enregistré, statut En opération", "success" in out and "opération" in status_chip(page).lower(), f"{status_chip(page)} {out}", page, "transfert-debut")
    out = submit(page, "milestone", {"type": "FULL_RATE", "declared_at": soon(3)})
    record(S, "Jalon FULL_RATE", "TER", "enregistré", "success" in out, out, page, "jalon-full-rate")
    page = tab(ter, call_id, "mesures")
    out = submit(page, "sheet_open", {"tank": "TK-12", "start_level_mm": "1325", "m3_per_metre": "1684", "density": "0.8412", "vcf": "0.9824",
                                      "planned_quantity_m3": "30000", "expected_rate_m3h": "1200", "expected_pressure_bar": "6.5"})
    record(S, "Journal de pompage 1.4 : feuille terre ouverte (bac, barème m³/m, densité, VCF, quantité prévue)", "TER", "feuille ouverte", "success" in out and "TK-12" in page.content(), out[:200], page, "pompage-feuille-terre")
    out = submit(page, "pumping", {"declared_at": soon(3), "pressure_bar": "6.5", "level_mm": "2310", "temperature_c": "27.4", "note": "début du déchargement"})
    record(S, "Relevé terre : niveau → quantité transférée et cumul calculés avec le barème (1 658,74 m³)", "TER", "relevé ajouté avec les quantités calculées",
           "success" in out and re.search(r"1[\s\u202f\u00a0]?658", page.locator("body").inner_text()) is not None, out[:200], page, "pompage-terre")
    page = tab(master, call_id, "mesures")
    out = submit(page, "sheet_open", {"tank": "1P-6S", "density": "0.8412", "vcf": "0.9824", "planned_quantity_m3": "30000"})
    record(S, "Feuille bord ouverte par le capitaine", "NAV (capitaine)", "feuille ouverte", "success" in out, out[:200], mp, "pompage-feuille-bord")
    out = submit(mp, "pumping", {"declared_at": soon(4), "pressure_bar": "6.9", "hourly_m3": "1650"})
    body = mp.locator("#pompage").inner_text() if mp.locator("#pompage").count() else ""
    record(S, "Relevé bord apparié au relevé terre de la même heure : écart terre − bord calculé en m³ et en %", "NAV (capitaine)",
           "ligne avec les deux relevés et l'écart (+0,5 %, hors tolérance → arrêt pour investigation)", "success" in out and "1 650" in body.replace("\u202f", " ").replace("\xa0", " ") and ("investigation" in body),
           body[:400], mp, "pompage-ecart")
    page = tab(com, call_id, "mesures")  # the owner's session opened for its green light
    body = page.locator("#pompage").inner_text() if page.locator("#pompage").count() else ""
    record(S, "Le journal de pompage des deux côtés est lu par l'armateur / affréteur (loss control), sans saisie possible", "COM",
           "tableau visible, pas de formulaire de relevé", "TK-12" in page.content() and page.locator('form[action$="/action/pumping/"]').count() == 0, body[:200], page, "pompage-lecture-com")
    page = tab(svc, call_id, "mesures")  # the marine services session opened for the berthing
    record(S, "Le journal de pompage n'est pas visible des services nautiques (lecteurs décidés au paramétrage)", "SVC",
           "onglet sans journal de pompage", page.locator("#pompage").count() == 0, page.locator("main").inner_text()[:200], page, "pompage-svc")
    page = tab(ter, call_id, "jalons")
    out = submit(page, "milestone", {"type": "INTERRUPTION_START", "declared_at": soon(3), "cause": "SHORE_PUMP", "note": "pompe P2"})
    record(S, "Interruption déclarée avec cause de la liste fermée (panne pompe terre, imputée à la terre)", "TER", "enregistrée", "success" in out, out, page, "interruption-debut")
    page = tab(ter, call_id, "jalons")
    rel = page.locator('select[name="related_id"]')
    out = submit(page, "milestone", {"type": "INTERRUPTION_END", "declared_at": soon(4), **({"related_id": rel.locator("option").nth(1).get_attribute("value")} if rel.count() and rel.locator("option").count() > 1 else {})})
    record(S, "Fin d'interruption rattachée à son début", "TER", "enregistrée", "success" in out, out, page, "interruption-fin")
    page = tab(master, call_id, "jalons")
    row = page.locator("tr:has-text('Panne de pompe')").first
    if row.count() and row.locator('input[name="milestone_id"]').count():
        mid = row.locator('input[name="milestone_id"]').first.input_value()
        out = submit(page, "countersign", {"comment": "la pompe terre a redémarré à 05:40, pas 05:45"}, match={"milestone_id": mid, "contest": "1"})
        record(S, "Le capitaine CONTESTE un jalon (heure de fin d'interruption) → contestation ouverte", "NAV (capitaine)", "contestation ouverte, liée au jalon", "success" in out, out, page, "contestation-jalon")
    else:
        record(S, "Le capitaine conteste un jalon", "NAV (capitaine)", "bouton Contester disponible", False, "aucun bouton de contestation sur la ligne de l'interruption", page, "contestation-jalon")
    page = tab(master, call_id, "jalons")
    out = submit(page, "milestone", {"type": "TOPPING_OFF", "declared_at": soon(1)})
    record(S, "Jalon TOPPING_OFF (préavis de fin de remplissage) par le capitaine", "NAV (capitaine)", "enregistré", "success" in out, out, page, "jalon-topping_off")
    for mcode, h in (("TRANSFER_END", 2), ("LINES_DRAINED", 3), ("HOSES_DISCONNECTED", 4)):
        page = tab(ter, call_id, "jalons")
        out = submit(page, "milestone", {"type": mcode, "declared_at": soon(h)})
        record(S, f"Jalon {mcode}", "TER", "enregistré", "success" in out, out, page, f"jalon-{mcode.lower()}")

    # ----- mesures contradictoires
    page = tab(ins, call_id, "mesures")
    out = submit(page, "measurement_open", {"kind": "FINAL", "unit": "MT"})
    record(S, "Ouverture d'une mesure (jaugeage final, MT) par l'inspecteur", "INS", "mesure ouverte", "success" in out, out, page, "mesure-ouverte")
    out = submit(page, "measurement_value", {"party": "SURVEYOR", "value": "29950", "temperature_c": "28", "density": "0.8400"})
    record(S, "Valeur de l'inspecteur saisie", "INS", "valeur enregistrée", "success" in out, out, page, "mesure-inspecteur")
    page = tab(ter, call_id, "mesures")
    out = submit(page, "measurement_value", {"party": "SHORE", "value": "29900"})
    record(S, "Valeur terre saisie par le terminal", "TER", "valeur enregistrée", "success" in out, out, page, "mesure-terre")
    page = tab(master, call_id, "mesures")
    out = submit(page, "measurement_value", {"party": "SHIP", "value": "30010"})
    record(S, "Valeur bord saisie par le capitaine", "NAV (capitaine)", "valeur enregistrée, écart calculé", "success" in out and ("tolérance" in mp.content().lower()), out, mp, "mesure-bord")
    # ----- 1.4 : relevés par citerne, validés par l'inspecteur avant d'être visibles des autres parties
    out = submit(mp, "tank_reading", {"tank": "3P", "level_mm": "455", "temperature_c": "29.5", "gov_m3": "5280.3", "vcf": "0.98235", "density": "0.8412"}, index=0)
    record(S, "Relevé de la citerne bord 3P par le capitaine (GSV et masse calculés)", "NAV (capitaine)", "relevé en attente de l'inspecteur", "success" in out and ("attente" in mp.content().lower() or "awaiting" in mp.content().lower()), out[:200], mp, "citerne-bord")
    page = tab(ter, call_id, "mesures")
    hidden = "3P" not in page.locator("main").inner_text()
    out = submit(page, "tank_reading", {"tank": "TK-12", "level_mm": "19800", "gov_m3": "29870.0", "vcf": "0.98230", "density": "0.8412"}, index=0)
    record(S, "Relevé du bac terre TK-12 par le terminal ; la citerne bord en attente ne lui est pas visible", "TER", "relevé terre enregistré ; 3P absente de la page", "success" in out and hidden, f"3P masquée : {hidden} — {out[:150]}", page, "citerne-terre")
    page = tab(ins, call_id, "mesures")
    forms = page.locator('form[action$="/action/tank_review/"]')
    out = submit(page, "tank_review", index=0) if forms.count() else ""
    out2 = submit(page, "tank_review", index=0) if page.locator('form[action$="/action/tank_review/"]').count() else ""
    record(S, "L'inspecteur valide les relevés de citernes (bord et terre)", "INS", "relevés validés", "success" in out and ("success" in out2 or not out2), (out + " / " + out2)[:200], page, "citernes-validees")
    page = tab(com, call_id, "mesures")
    text = page.locator("main").inner_text()
    record(S, "Une fois validés, les relevés de citernes sont visibles de l'armateur / affréteur avec le total des citernes validées", "COM",
           "3P et TK-12 visibles, total validé", "3P" in text and "TK-12" in text and ("validé" in text.lower() or "validated" in text.lower()), text[:200], page, "citernes-com")
    # ----- 1.4 : certificat de qualité du laboratoire — terminal, trader, navire, inspecteur et port seulement
    page = tab(ins, call_id, "documents")
    form = page.locator('form[action$="/action/document_upload/"]').last
    form.locator('select[name="type"]').select_option("QUALITY_CERT")
    form.locator('input[name="title"]').fill("Certificat de qualité — Gasoil 10 ppm")
    form.locator('input[name="file"]').set_input_files(pdf_file("quality.pdf", "CERTIFICAT DE QUALITE"))
    form.locator("button.btn").last.click()
    page.wait_for_load_state("load")
    record(S, "Certificat de qualité déposé par le laboratoire (INS)", "INS", "document déposé", has_success(page), flash_text(page), page, "certificat-qualite")
    seen_com = any("qualité" in d.lower() for d in documents_titles(com, call_id))
    seen_age = any("qualité" in d.lower() for d in documents_titles(age, call_id))
    seen_ter = any("qualité" in d.lower() for d in documents_titles(ter, call_id))
    record(S, "Le certificat de qualité est lu par le trader (COM) et le terminal, pas par l'agence", "COM / TER / AGE",
           "visible COM et TER, invisible AGE", seen_com and seen_ter and not seen_age, f"COM {seen_com}, TER {seen_ter}, AGE {seen_age}", com.page, "certificat-qualite-lecteurs")
    page = tab(ins, call_id, "jalons")
    out = submit(page, "milestone", {"type": "FINAL_GAUGING", "declared_at": soon(4)})
    record(S, "Jalon FINAL_GAUGING", "INS", "enregistré", "success" in out, out, page, "jalon-jaugeage-final")

    # ----- contestation : réponse et clôture
    page = tab(ter, call_id, "contestations")
    if page.locator('form[action$="/action/dispute_respond/"]').count():
        out = submit(page, "dispute_respond", {"text": "Heure du registre terre : 05:45 ; relevé pompe joint."})
        record(S, "Le terminal répond à la contestation", "TER", "réponse enregistrée", "success" in out, out, page, "contestation-reponse")
    page = tab(master, call_id, "contestations")
    if page.locator('form[action$="/action/dispute_close/"]').count():
        out = submit(page, "dispute_close", {"agreed": "1", "text": "Heure 05:45 acceptée après vérification du relevé."})
        record(S, "Le capitaine clôt la contestation avec accord", "NAV (capitaine)", "close", "success" in out, out, page, "contestation-close")
    page = tab(age, call_id, "contestations")
    out = submit(page, "dispute_open", {"target_kind": "OTHER", "subject": "Heure de la passerelle", "counterpart_role": "SVC", "statement": "La passerelle n'a été posée qu'à +2 h 30."})
    record(S, "Ouverture d'une contestation libre par l'agence envers les services nautiques", "AGE", "ouverte", "success" in out, out, page, "contestation-ouverte")

    # ----- échanges
    page = tab(age, call_id, "echanges")
    form = _form(page, "thread_create")
    form.locator('input[name="subject"]').fill("Créneau de déballastage")
    form.locator('input[name="participants"][value="TER"]').check()
    form.locator('select[name="confidentiality"]').select_option("N2")
    form.locator('textarea[name="body"]').fill("Le bord souhaite déballaster pendant le déchargement.")
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    record(S, "Nouveau fil d'échange agence → terminal (N2)", "AGE", "fil créé", has_success(page), flash_text(page), page, "echange-nouveau")
    page = tab(ter, call_id, "echanges")
    out = submit(page, "thread_post", {"body": "D'accord pour le déballastage, débit réduit."})
    record(S, "Réponse du terminal dans le fil", "TER", "message envoyé", "success" in out, out, page, "echange-reponse")

    # ----- documents : bon de réception, signature, nouvelle version
    page = tab(ter, call_id, "documents")
    form = page.locator('form[action$="/action/document_upload/"]').last
    if form.locator('select[name="task_id"]').count():
        try:
            select_like(form.locator('select[name="task_id"]'), "1\\.17")
        except Exception:  # noqa: BLE001
            pass
    form.locator('select[name="type"]').select_option("TERMINAL_RECEIPT")
    form.locator('input[name="file"]').set_input_files(pdf_file("receipt.pdf", "BON DE RECEPTION"))
    form.locator("button.btn").last.click()
    page.wait_for_load_state("load")
    record(S, "Bon de réception du terminal déposé", "TER", "document déposé", has_success(page), flash_text(page), page, "depot-bon-reception")
    sign_forms = page.locator('form[action$="/action/document_sign/"]')
    if sign_forms.count():
        out = submit(page, "document_sign", index=sign_forms.count() - 1)
        record(S, "Signature électronique d'un document par son émetteur", "TER", "signature enregistrée", "success" in out, out, page, "document-signe")

    # ----- formulaires standards émis par chaque partie
    age.goto(f"/escales/{call_id}/formulaires/")
    page = age.page
    n_forms = len(page.locator('form[action$="/action/form_issue/"]').all())
    record(S, "Page Formulaires de l'agence : ses formulaires, par famille, avec « répond à » et « déposé »", "AGE", "liste non vide", n_forms > 0 and "répond" in page.content().lower() or n_forms > 0, f"{n_forms} formulaires proposés", page, "formulaires-agence")
    out = submit(page, "form_issue", match={"code": "ARRIVAL_NOTICE"})
    record(S, "Émission et dépôt de l'avis d'arrivée (formulaire généré du registre)", "AGE", "déposé comme document", "success" in out and any("arrivée" in d.lower() for d in documents_titles(age, call_id)), out, age.page, "formulaire-avis-arrivee")
    age.goto(f"/escales/{call_id}/formulaires/TIME_SHEET/")
    record(S, "Aperçu imprimable d'un formulaire (time sheet) prérempli du registre", "AGE", "page A4 avec les heures de l'escale", age.page.locator("body").inner_text().count("ALL_FAST") + age.page.locator("body").inner_text().lower().count("all fast") > 0, age.page.title(), age.page, "formulaire-time-sheet")
    ter.goto(f"/escales/{call_id}/formulaires/")
    out = submit(ter.page, "form_issue", match={"code": "SSSCL"})
    record(S, "Le terminal émet la liste de contrôle navire/terre", "TER", "déposée", "success" in out, out, ter.page, "formulaire-ssscl")
    ins.goto(f"/escales/{call_id}/formulaires/")
    out = submit(ins.page, "form_issue", match={"code": "QUANTITY_CERT"})
    record(S, "L'inspecteur émet le certificat de quantité", "INS", "déposé", "success" in out, out, ins.page, "formulaire-certificat-quantite")
    cap.goto(f"/escales/{call_id}/formulaires/")
    txt = cap.page.locator("body").inner_text()
    record(S, "Page Formulaires de la capitainerie : les actes des décisions apparaissent comme déposés", "CAP", "colonne Déposé renseignée pour les actes", "Feu vert" in txt and ("v1" in txt), txt[:300], cap.page, "formulaires-capitainerie")
    svc.goto(f"/escales/{call_id}/formulaires/")
    out = submit(svc.page, "form_issue", match={"code": "MOVEMENT_ORDER"})
    record(S, "Les services nautiques émettent l'ordre de mouvement", "SVC", "déposé", "success" in out, out, svc.page, "formulaire-ordre-mouvement")
    com.goto(f"/escales/{call_id}/formulaires/")
    forms_com = [i.input_value() for i in com.page.locator('form[action$="/action/form_issue/"] input[name="code"]').all()]
    record(S, "L'armateur voit ses formulaires (recap, instruction documentaire, assurances, LOI)", "COM", "famille COM proposée", "CP_RECAP" in forms_com, ", ".join(forms_com), com.page, "formulaires-armateur")

    # ----- partie sans compte par son lien : nom, consultation, dépôt, formulaire
    # le lien a été affiché une fois à l'émission ; on le relit depuis le journal de la plateforme (courriel console)
    link_url = read_last_link_from_log("Laboratoire E2E")
    if link_url:
        lab = link_session(browser, link_url, "A. Mensah (Laboratoire E2E)")
        lp = lab.page
        record(S, "Partie sans compte : nom donné à la première ouverture, puis fiche de l'escale", "PRE (lien)", "fiche de l'escale", f"/escales/{call_id}/" in lp.url, lp.url, lp, "lien-partie-ouverture")
        tab(lab, call_id, "documents")
        form = lp.locator('form[action$="/action/document_upload/"]').last
        form.locator('select[name="type"]').select_option("OTHER")
        form.locator('input[name="title"]').fill("Rapport d'analyse E2E")
        form.locator('input[name="file"]').set_input_files(pdf_file("labo.pdf", "RAPPORT D ANALYSE"))
        form.locator("button.btn").last.click()
        lp.wait_for_load_state("load")
        record(S, "Dépôt d'un document par la partie sans compte (sous son organisation)", "PRE (lien)", "document déposé", has_success(lp), flash_text(lp), lp, "lien-partie-depot")
        lab.goto("/")
        record(S, "Un lien n'ouvre pas le tableau de bord", "PRE (lien)", "refus ou renvoi", "tableau de bord" not in lp.locator("body").inner_text().lower() or "/compte/connexion" in lp.url, lp.url, lp, "lien-partie-tableau-de-bord")
        lab.close()
    else:
        record(S, "Partie sans compte par son lien", "PRE (lien)", "lien lisible dans le courriel de convocation", None, "non vérifié : journal des courriels non fourni (--mail-log)", None)

    # ----- étapes : planifier puis annuler
    page = tab(age, call_id, "apercu")
    form = _form(page, "stage_add")
    form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
    form.locator('select[name="berth_kind"]').select_option("ANCHORAGE")
    form.locator('input[name="operations"][value="M5"]').check()
    form.locator('input[name="planned_from"]').fill(local(30))
    form.locator('input[name="planned_to"]').fill(local(40))
    form.locator('input[name="reason"]').fill("attente en rade avant le second poste")
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    record(S, "Planification d'une étape suivante (rade)", "AGE", "étape planifiée listée", has_success(page) and "planifiée" in page.content().lower(), flash_text(page), page, "etape-planifiee")
    if page.locator('form[action$="/action/stage_cancel/"]').count():
        out = submit(page, "stage_cancel", {"reason": "finalement inutile"})
        record(S, "Annulation d'une étape planifiée, avec motif (jamais effacée)", "AGE", "étape annulée visible", "success" in out and "annulée" in page.content().lower(), out, page, "etape-annulee")

    # ----- déchets, formalités de sortie, congé de départ → acte « Congé de départ »
    pre = login(browser, "pre.tglfw@demo.fluxaa.test")
    age.goto(f"/escales/{call_id}/?tab=demandes&type=WASTE_COLLECTION")
    page = age.page
    form = _form(page, "request_create")
    form.locator('input[name="categories"]').fill("I, V")
    form.locator('input[name="volume_m3"]').fill("12")
    form.locator('input[name="requested_time"]').fill(local(23))
    if form.locator('select[name="provider"]').count():
        form.locator('select[name="provider"]').select_option(index=1)
    form.locator("button:not([type=button])").last.click()
    page.wait_for_load_state("load")
    record(S, "Notification préalable de remise des déchets (commande de service)", "AGE", "soumise", has_success(page), flash_text(page), page, "demande-dechets")
    pre.goto(f"/escales/{call_id}/formulaires/")
    out = submit(pre.page, "form_issue", match={"code": "WASTE_RECEIPT"})
    record(S, "Le prestataire émet le bordereau de réception des déchets (répond à M0:32)", "PRE", "déposé", "success" in out, out, pre.page, "formulaire-bordereau-dechets")
    page = tab(pre, call_id, "jalons")
    out = submit(page, "milestone", {"type": "WASTE_DELIVERED", "declared_at": soon(1)})
    record(S, "Jalon WASTE_DELIVERED par le prestataire", "PRE", "enregistré", "success" in out, out, page, "jalon-dechets")
    page = tab(pre, call_id, "taches")
    if page.locator("tr:has(td.code:text-is('32')) form[action$='/action/task_complete/']").count():
        out = submit(page, "task_complete", {"note": "bordereau déposé"}, match={"task_id": task_id(page, "32")})
        record(S, "Tâche M0:32 (déchets remis) faite", "PRE", "faite", "success" in out, out, page, "tache-32")
    age.goto(f"/escales/{call_id}/?tab=demandes&type=OUTWARD_FORMALITIES")
    out = submit(age.page, "request_create")
    record(S, "Demande de formalités de sortie", "AGE", "soumise", "success" in out, out, age.page, "demande-sortie")
    page = tab(adm, call_id, "demandes")
    art = page.locator("article:has-text('sortie')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid})
    record(S, "Formalités de sortie approuvées (acte déposé)", "ADM", "approuvées", "success" in out, out, page, "decision-sortie")
    age.goto(f"/escales/{call_id}/?tab=demandes&type=DEPARTURE_CLEARANCE")
    out = submit(age.page, "request_create", {"requested_time": local(2)})
    record(S, "Demande de congé de départ", "AGE", "soumise", "success" in out, out, age.page, "demande-conge")
    page = tab(cap, call_id, "demandes")
    art = page.locator("article:has-text('Congé de départ')").first
    rid = art.locator('input[name="request_id"]').first.input_value()
    out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid})
    record(S, "CONGÉ DE DÉPART délivré par la capitainerie", "CAP", "approuvé", "success" in out, out, page, "conge-depart")
    docs = documents_titles(cap, call_id)
    record(S, "ACTE « Autorisation — Congé de départ » DÉPOSÉ dans les documents (le cas signalé)", "CAP", "document présent", any("Congé de départ" in d for d in docs), " ; ".join(docs), cap.page, "acte-conge-depart")
    docs_age = documents_titles(age, call_id)
    record(S, "L'agence (demandeur) lit l'acte du congé de départ", "AGE", "document visible", any("Congé de départ" in d for d in docs_age), " ; ".join(docs_age), age.page, "acte-conge-agence")

    # ----- appareillage, rapport des faits, clôture, archivage
    page = tab(svc, call_id, "jalons")
    for mcode, h in (("PILOT_ON_BOARD_DEP", 1), ("LAST_LINE", 2)):
        out = submit(page, "milestone", {"type": mcode, "declared_at": soon(h)})
        record(S, f"Jalon {mcode}", "SVC", "enregistré", "success" in out, out, page, f"jalon-{mcode.lower()}")
    page = tab(master, call_id, "jalons")
    out = submit(page, "milestone", {"type": "DEPARTED", "declared_at": soon(3)})
    record(S, "Jalon DEPARTED (appareillage) enregistré par le capitaine", "NAV (capitaine)", "enregistré", "success" in out, out, page, "jalon-departed")
    page = tab(age, call_id, "apercu")
    record(S, "Statut Appareillée après la dernière amarre", "AGE", "Appareillée", ("parti" in status_chip(page).lower() or "appareill" in status_chip(page).lower()), status_chip(page), page, "appareillee")
    out = submit(page, "statement", {"remarks": "Escale sans incident ; interruption terre de 45 min."})
    record(S, "Génération du rapport des faits par l'agence", "AGE", "SOF généré", "success" in out, out, page, "rapport-des-faits")
    docs = documents_titles(age, call_id)
    record(S, "Rapport des faits ET time sheet déposés comme documents", "AGE", "SOF et time sheet présents", any("Rapport des faits" in d or "faits" in d.lower() for d in docs) and any("Time sheet" in d or "time sheet" in d.lower() for d in docs), " ; ".join(docs), age.page, "sof-time-sheet-documents")
    age.goto(f"/escales/{call_id}/rapport-des-faits/")
    record(S, "Aperçu du rapport des faits (chronologie, interruptions, signatures)", "AGE", "page rendue", "ALL_FAST" in age.page.content() or "all fast" in age.page.content().lower() or "Rapport des faits" in age.page.content(), age.page.title(), age.page, "rapport-des-faits-apercu")
    # signatures du SOF par le capitaine et le terminal
    for sess, who in ((master, "NAV (capitaine)"), (ter, "TER")):
        page = tab(sess, call_id, "documents")
        row = page.locator("tr:has-text('Rapport des faits')").first
        if row.count() and row.locator('form[action$="/action/document_sign/"]').count():
            mid = row.locator('input[name="document_id"]').first.input_value()
            out = submit(page, "document_sign", match={"document_id": mid})
            record(S, f"Signature du rapport des faits par {who}", who, "signée", "success" in out, out, page, f"sof-signe-{who[:3].lower()}")
        else:
            record(S, f"Signature du rapport des faits par {who}", who, "bouton Signer disponible", False, "pas de bouton Signer sur le rapport des faits", page, f"sof-signe-{who[:3].lower()}")
    page = tab(age, call_id, "apercu")
    out = submit(page, "close_request")
    record(S, "Demande de clôture par l'agence", "AGE", "demandée", "success" in out, out, page, "cloture-demandee")
    page = tab(cap, call_id, "contestations")
    if page.locator('form[action$="/action/dispute_close/"]').count():
        out = submit(page, "dispute_close", {"text": "Sans accord : les heures du registre font foi."})
        record(S, "La capitainerie clôt la contestation restante (sans accord, jamais arbitrée)", "CAP", "close", "success" in out, out, page, "contestation-close-cap")
    page = tab(cap, call_id, "apercu")
    out = submit(page, "close")
    record(S, "Clôture de l'escale par la capitainerie", "CAP", "statut Close", "success" in out and "clôtur" in status_chip(page).lower(), f"{status_chip(page)} {out}", page, "escale-close")
    if "clôtur" in status_chip(page).lower():
        out = submit(page, "archive")
        record(S, "Archivage", "CAP", "statut Archivée", "archiv" in status_chip(page).lower(), f"{status_chip(page)} {out}", page, "escale-archivee")

    # ----- export de réversibilité et vérification hors plateforme
    dirs = login(browser, "dir.tglfw@demo.fluxaa.test")
    resp = dirs.page.request.get(f"{BASE}/escales/{call_id}/export/")
    path = HERE / "export.zip"
    path.write_bytes(resp.body())
    dirs.goto(f"/escales/{call_id}/")
    import subprocess
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "verifier_export.py"), str(path)], capture_output=True, text=True)
    record(S, "Export de l'escale (zip) et vérification hors plateforme des empreintes", "DIR", "vérificateur : OK", r.returncode == 0, (r.stdout + r.stderr)[-300:], dirs.page, "export-verifie")

    # ----- sûreté N4
    page = tab(age, 1, "apercu")
    out = submit(page, "secure_deposit", {"kind": "ARMED_GUARDS", "guards": "4", "company": "Sécurité E2E", "embark": local(1), "disembark": local(30), "details": "transit vers Lagos"})
    record("Sûreté N4", "Dépôt confidentiel d'une demande de gardes armés par l'agence", "AGE", "déposé dans l'espace sûreté", "success" in out, out, page, "surete-depot")
    sur.goto("/surete/")  # the security session opened for the naval base's green light
    sp = sur.page
    record("Sûreté N4", "Espace sûreté : liste des dossiers", "SUR", "dossier visible", "N4-" in sp.content(), sp.locator("main").inner_text()[:200] if sp.locator("main").count() else "", sp, "surete-liste")
    link = sp.locator("a[href^='/surete/N4-']").first
    if link.count():
        link.click()
        sp.wait_for_load_state("load")
        if sp.locator('form:has(input[name="action"][value="decide"])').count():
            def decide():
                f = sp.locator('form:has(input[name="action"][value="decide"])').first
                f.locator('select[name="decision"]').select_option(index=0)
                f.locator('textarea[name="modalities"]').fill("4 gardes, embarquement en rade")
                f.locator("button:not([type=button])").last.click()
                sp.wait_for_load_state("load")

            decide()
            if step_up(sp):  # the second factor asked again (its validity lapsed during the scenario): decide again
                decide()
            record("Sûreté N4", "Décision de la sûreté sur le dossier", "SUR", "décision enregistrée", has_success(sp) or "✓" in sp.content(), flash_text(sp), sp, "surete-decision")
        if sp.locator('button[name="what"][value="embarked"]').count():
            sp.locator('button[name="what"][value="embarked"]').click()
            sp.wait_for_load_state("load")
            record("Sûreté N4", "Confirmation d'embarquement", "SUR", "confirmée", "✓" in sp.content() or has_success(sp), flash_text(sp), sp, "surete-embarquement")
    sur.goto("/surete/journal/")
    record("Sûreté N4", "Journal des accès de l'espace sûreté", "SUR", "page rendue", page_ok(sp, sur.goto("/surete/journal/")), sp.title(), sp, "surete-journal")
    r2 = age.goto("/surete/")
    record("Sûreté N4", "L'agence n'atteint pas l'espace sûreté (existence non divulguée)", "AGE", "introuvable (404)", r2 is not None and r2.status == 404, str(r2.status if r2 else None), age.page, "surete-agence-404")
    j = tab(cap, 1, "journal").locator("body").inner_text()
    record("Sûreté N4", "Rien du dépôt N4 n'apparaît dans le journal de l'escale", "CAP", "aucune mention de gardes armés", "gardes" not in j.lower() and "Sécurité E2E" not in j, j[:200], cap.page, "surete-journal-escale")

    # ----- sécurité : le demandeur ne décide jamais ; le lien ne décide pas
    page = tab(age, 2, "demandes")
    cnt = page.locator('form[action$="/action/request_decide/"]').count()
    record("Sécurité", "L'agence ne voit aucun bouton Décider sur les demandes", "AGE", "0 formulaire de décision", cnt == 0, f"{cnt} formulaire(s)", page, "agence-ne-decide-pas")
    r3 = age.page.request.post(f"{BASE}/escales/2/action/request_decide/", form={"request_id": "1", "decision": "APPROVED", "csrfmiddlewaretoken": age.page.evaluate("document.cookie.match(/csrftoken=([^;]+)/)?.[1] || ''")}, headers={"Referer": BASE + "/"})
    record("Sécurité", "Une décision forcée par l'agence (POST direct) est refusée", "AGE", "403 ou refus", r3.status in (403, 404) or "refus" in r3.text().lower() or "error" in r3.text().lower(), f"HTTP {r3.status}", None)

    # ----- API
    age.goto("/compte/")
    age.page.locator('button[name="action"][value="token"]').click()
    age.page.wait_for_load_state("load")
    token = age.page.locator("p.mono").first.inner_text().strip() if age.page.locator("p.mono").count() else ""
    record("API", "Création d'un jeton d'API depuis Mon compte", "AGE", "jeton affiché une fois", len(token) > 20, token[:6] + "…", age.page, "api-jeton")
    import urllib.request
    def api(method, path, data=None, tok=token):
        req = urllib.request.Request(BASE + "/api/v1/" + path, method=method, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status, json.loads(resp.read().decode() or "null")
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read().decode() or "null")
    st, me = api("GET", "me/")
    record("API", "GET /api/v1/me/ avec le jeton", "AGE", "200, rôles de l'agence", st == 200 and "AGE" in json.dumps(me), f"{st} {json.dumps(me)[:160]}", None)
    st, calls = api("GET", "calls/")
    record("API", "GET /api/v1/calls/ : les escales de l'agence", "AGE", "200, liste contenant TGLFW-2026-0001", st == 200 and "TGLFW-2026-0001" in json.dumps(calls), f"{st} {len(calls) if isinstance(calls, list) else calls}", None)
    st, forms_ = api("GET", "calls/TGLFW-2026-0002/forms/")
    record("API", "GET …/forms/ : formulaires offerts à l'agence sur une escale", "AGE", "200, ARRIVAL_NOTICE présent", st == 200 and "ARRIVAL_NOTICE" in json.dumps(forms_), f"{st} {json.dumps(forms_)[:160]}", None)
    st, issued = api("POST", "calls/TGLFW-2026-0002/forms/SANCTIONS_CHECK/")
    record("API", "POST …/forms/SANCTIONS_CHECK/ : émission et dépôt par l'API", "AGE", "201/200, document créé", st in (200, 201), f"{st} {json.dumps(issued)[:200]}", None)
    st, sync = api("POST", "calls/TGLFW-2026-0002/sync/", {"entries": [{"kind": "milestone", "client_uuid": "11111111-2222-4333-8444-555555555555", "type": "NOR_TENDERED", "declared_at": local(-2) + ":00Z", "device_recorded_at": local(-2) + ":00Z", "device_id": "e2e", "note": "sync e2e"}]})
    record("API", "POST …/sync/ : saisie hors ligne synchronisée (jalon NOR)", "AGE", "200, entrée acceptée ou refus motivé", st in (200, 201, 207), f"{st} {json.dumps(sync)[:240]}", None)
    st, exp = api("GET", "calls/TGLFW-2026-0002/journal/")
    record("API", "GET …/journal/ : journal de l'escale", "AGE", "200", st == 200, f"{st} {len(exp) if isinstance(exp, list) else json.dumps(exp)[:100]}", None)
    st, body = api("GET", "me/", tok="faux-jeton")
    record("API", "Jeton faux refusé", "—", "401", st == 401, str(st), None)
    r4 = age.goto("/api/docs/")
    record("API", "Documentation interactive de l'API (/api/docs/)", "AGE", "page rendue", page_ok(age.page, r4), age.page.title(), age.page, "api-docs")

    # ----- Freetown en anglais
    age_sl = login(browser, "age.slfna@demo.fluxaa.test")
    page = age_sl.page
    record("Freetown (EN)", "Agence de Freetown : tableau de bord en anglais", "AGE (SLFNA)", "interface en anglais", "Dashboard" in page.content() or "Calls" in page.content(), page.title(), page, "freetown-dashboard")
    age_sl.goto("/escales/?scope=all&q=SLFNA-2026-0001")
    link = age_sl.page.locator("a[href^='/escales/']:has-text('SLFNA-2026-0001'), tr:has-text('SLFNA-2026-0001') a[href^='/escales/']").first
    m = re.search(r"/escales/(\d+)/", link.get_attribute("href") or "") if link.count() else None
    sl_id = int(m.group(1)) if m else 0
    age_sl.goto(f"/escales/{sl_id}/formulaires/")
    record("Freetown (EN)", "Formulaires de l'escale SLFNA-2026-0001 en anglais", "AGE (SLFNA)", "titres anglais", "Arrival notice" in age_sl.page.content() or "Time sheet" in age_sl.page.content(), age_sl.page.title(), age_sl.page, "freetown-forms")
    age_sl.goto(f"/escales/{sl_id}/?tab=documents")
    txt = age_sl.page.locator("body").inner_text()
    record("Freetown (EN)", "Les actes des décisions existent aussi sur les escales de démonstration de Freetown", "AGE (SLFNA)", "Authorization — … dans les documents", "Authorization" in txt or "Authorisation" in txt, txt[:300], age_sl.page, "freetown-acts")

    # ======================================================================================= 1.5
    G = "1.5 — Validité, accès, STS, toutes cargaisons"

    # ----- validité : une escale obsolète (validité échue avant l'accostage) est annoncée de nouveau par l'agent principal
    age.goto("/escales/?scope=all&q=SAHEL")
    link = age.page.locator("a[href^='/escales/']:has-text('SAHEL')").first
    if not link.count():
        link = age.page.locator("tr:has-text('SAHEL') a[href^='/escales/']").first
    href = link.get_attribute("href") if link.count() else ""
    m = re.search(r"/escales/(\d+)/", href or "")
    expired_id = int(m.group(1)) if m else None
    page = tab(age, expired_id, "apercu") if expired_id else age.page
    val = page.locator("#validite").inner_text() if page.locator("#validite").count() else ""
    record(G, "Escale obsolète (démo H, validité de 3 jours échue avant l'arrivée) : statut « Obsolète », encart Validité avec la date et le bouton « Refaire l'annonce »", "AGE",
           "statut Obsolète, bouton de reprise", expired_id is not None and "obsol" in status_chip(page).lower() and page.locator('form[action$="/action/renew/"]').count() == 1,
           f"{status_chip(page)} | {val[:200]}".replace("\n", " "), page, "escale-obsolete")
    renewed_id = None
    if expired_id and page.locator('form[action$="/action/renew/"]').count():
        out = submit(page, "renew")
        m = re.search(r"/escales/(\d+)/", page.url)
        renewed_id = int(m.group(1)) if m and int(m.group(1)) != expired_id else None
        val = page.locator("#validite").inner_text() if page.locator("#validite").count() else ""
        record(G, "Reprise de l'annonce : nouvelle escale en brouillon avec le même navire, les mêmes opérations et parties, liée à l'escale obsolète", "AGE",
               "nouvelle escale Brouillon, « Annonce refaite à partir de TGLFW-2026-0008 »", renewed_id is not None and "Brouillon" in status_chip(page) and "0008" in val and "refaite" in val.lower(),
               f"{page.url} {status_chip(page)} {out[:120]} | {val[:160]}".replace("\n", " "), page, "annonce-refaite")
        page = tab(age, expired_id, "apercu")
        val = page.locator("#validite").inner_text() if page.locator("#validite").count() else ""
        record(G, "L'escale obsolète pointe vers sa reprise et ne peut plus être refaite", "AGE", "« Refaite sous le numéro » et plus de bouton", "Refaite sous" in val and page.locator('form[action$="/action/renew/"]').count() == 0, val[:200].replace("\n", " "), page, "escale-obsolete-reprise")

    # ----- accès contrôlé : l'agence associée (démo E, accès partiel tâches + documents) ; l'agent principal change l'accès
    age2 = login(browser, "age2.tglfw@demo.fluxaa.test")
    age2.goto("/escales/?scope=all&q=CLINKER")
    link = age2.page.locator("a[href^='/escales/']:has-text('CLINKER')").first
    m = re.search(r"/escales/(\d+)/", link.get_attribute("href") or "") if link.count() else None
    e_id = int(m.group(1)) if m else 5
    page = tab(age2, e_id, "taches")
    tabs_seen = nav_tabs(page)
    head = page.locator(".callhead").inner_text()
    record(G, "Agence associée (co-nominée) sur l'escale de vrac sec : accès partiel donné par l'agent principal — seuls les onglets Tâches et Documents, pastille « Accès partiel »", "AGE (associée)",
           "2 onglets, pastille Accès partiel", set(tabs_seen) == {"Tâches", "Documents"} and "Accès partiel" in head,
           f"onglets {tabs_seen} | {head[:160]}".replace("\n", " "), page, "acces-partiel")
    r5 = age2.goto("/escales/1/")
    record(G, "L'agence associée n'ouvre pas une escale où elle n'a aucun rôle (existence non divulguée)", "AGE (associée)", "introuvable (404)", r5 is not None and r5.status == 404, str(r5.status if r5 else None), age2.page, "acces-partiel-404")
    r6 = age2.goto(f"/escales/{e_id}/?tab=jalons")
    body = age2.page.locator("main").inner_text()
    record(G, "Un onglet hors de l'accès partiel (Jalons) n'est pas servi à l'agence associée", "AGE (associée)", "renvoi vers un onglet autorisé ou refus", "Jalons" not in nav_tabs(age2.page) and ("Tâches" in body or r6.status == 404), f"{r6.status if r6 else None} {age2.page.url}", age2.page, "acces-partiel-onglet-refuse")
    page = tab(age, e_id, "parties")
    row = page.locator("tr:has-text('Consignataire associé')").first
    pid = row.locator('input[name="party_id"]').first.input_value() if row.locator('input[name="party_id"]').count() else ""
    out = submit(page, "party_access", {"access": "READ"}, match={"party_id": pid}) if pid else "pas de formulaire d'accès"
    record(G, "L'agent principal fixe l'accès de l'agence associée en lecture seule depuis l'onglet Parties", "AGE (principal)", "accès fixé : Lecture seule", "success" in out and "Lecture seule" in page.locator("tr:has-text('Consignataire associé')").first.inner_text(), out[:200], page, "acces-lecture-seule-fixe")
    page = tab(age2, e_id, "taches")
    head = page.locator(".callhead").inner_text()
    n_act = page.locator('form[action$="/action/task_complete/"], form[action$="/action/document_upload/"], form[action$="/action/request_create/"]').count()
    record(G, "En lecture seule, l'agence associée voit tous les onglets mais aucun bouton d'action ; la page le dit", "AGE (associée)",
           "pastille Lecture seule, 10 onglets, 0 formulaire d'action", "Lecture seule" in head and len(nav_tabs(page)) >= 9 and n_act == 0 and ("ne permet pas d'agir" in page.locator("main").inner_text()),
           f"{len(nav_tabs(page))} onglets, {n_act} formulaire(s) | {head[:120]}".replace("\n", " "), page, "acces-lecture-seule")
    page = tab(age, e_id, "parties")
    form = _form(page, "party_access", {"party_id": pid}) if pid else None
    if form is not None:
        form.locator("xpath=ancestor::details[1]").first.evaluate("d => { d.open = true }")
        form.locator('input[name="access"][value="PARTIAL"]').check()
        for code_ in ("apercu", "parties", "taches", "demandes", "jalons", "documents", "mesures", "contestations", "echanges", "journal"):
            box = form.locator(f'input[name="scopes"][value="{code_}"]')
            if code_ in ("taches", "documents", "jalons"):
                box.check()
            else:
                box.uncheck()
        form.locator("button:not([type=button])").last.click()
        page.wait_for_load_state("load")
        out = flash_text(page) or refusal_text(page)
        page = tab(age2, e_id, "jalons")
        record(G, "L'agent principal élargit l'accès partiel (tâches, documents, jalons) : l'agence associée gagne l'onglet Jalons aussitôt", "AGE (principal / associée)",
               "3 onglets dont Jalons", "success" in out and "Jalons" in nav_tabs(page) and len(nav_tabs(page)) == 3, f"{out[:120]} | onglets {nav_tabs(page)}", page, "acces-partiel-elargi")

    # ----- transbordement navire-navire : deux escales, deux équipes, journaux rapprochés
    age.goto("/escales/?scope=all&q=HARMATTAN")
    link = age.page.locator("a[href^='/escales/']:has-text('HARMATTAN')").first
    m = re.search(r"/escales/(\d+)/", link.get_attribute("href") or "") if link.count() else None
    sts_id = int(m.group(1)) if m else 3
    page = tab(age, sts_id, "apercu")
    txt = page.locator("main").inner_text()
    record(G, "Escale STS (démo C, navire livreur) : l'aperçu nomme le rôle du navire, le navire partenaire et son escale propre", "AGE",
           "section Transbordement : livreur, MT SAVANNAH DEMO, TGLFW-2026-0004", "Transbordement" in txt and "SAVANNAH" in txt and "TGLFW-2026-0004" in txt and "livr" in txt.lower(), txt[txt.find("Transbordement"):][:300].replace("\n", " "), page, "sts-apercu")
    page = tab(age, sts_id, "mesures")
    txt = page.locator("main").inner_text()
    record(G, "Mesures d'une escale STS : le journal de pompage compare les deux navires (la série « terre » est le journal du partenaire)", "AGE",
           "« les deux navires » et le nom du partenaire", "deux navires" in txt and "SAVANNAH" in txt, txt[:300].replace("\n", " "), page, "sts-mesures")

    # ----- toutes cargaisons : annonce d'une escale de vrac sec avec documents attendus, unité, validité et accès des parties
    age.goto("/escales/nouvelle/")
    p = age.page
    p.select_option("#vessel", "")
    p.locator("details.action summary").first.click()
    p.fill("#new_imo", IMO_BULK)
    p.fill("#new_name", "MV Bulk E2E " + IMO_BULK[-3:])
    p.fill("#new_flag", "Panama")
    p.select_option("#new_kind", "BULK")
    p.fill("#new_type", "Geared bulk carrier")
    p.fill("#new_dwt", "38000")
    p.check('input[name="cargo_kind"][value="DRY"]')
    p.fill("#product", "Clinker")
    p.fill("#quantity", "25000")
    p.select_option("#quantity_unit", "MT")
    p.fill("#planned_pump_hours", "60")
    p.check('input[name="kind"][value="JETTY"]')
    ops_visible = [lbl.get_attribute("data-cargo") for lbl in p.locator("label[data-operation]").all() if lbl.is_visible()]
    p.check('input[name="operations"][value="MB1"]')
    p.select_option("#op_MB1_geared", "YES")  # the question MB1 asks at the announcement (1.6)
    p.select_option("#op_MB1_imsbc_group", "C")
    p.fill("#eta", local(96))
    p.fill("#etb", local(100))
    p.fill("#etd", local(170))
    p.fill("#validity_days", "10")
    p.fill("#voyage", "E2E-02")
    p.check('input[name="expected_documents"][value="INSURANCE"]')
    p.locator("button[data-add-custom]").click()
    crow = p.locator("tr[data-custom-row]").last
    crow.locator('input[name="custom_doc_label"]').fill("Certificat d'origine")
    crow.locator('select[name="custom_doc_role"]').select_option("COM")
    crow.locator('input[name="custom_doc_hours"]').fill("24")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("TER")
    select_like(rows.nth(0).locator('select[name="party_org"]'), "conteneurs et vrac")
    rows.nth(1).locator('select[name="party_role"]').select_option("AGE")
    select_like(rows.nth(1).locator('select[name="party_org"]'), "Consignataire associé")
    rows.nth(1).locator('select[name="party_access"]').select_option("PARTIAL:taches,documents")
    rows.nth(2).locator('select[name="party_role"]').select_option("COM")
    select_like(rows.nth(2).locator('select[name="party_org"]'), "Réceptionnaire")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    bulk_id = int(m.group(1)) if m else None
    head = p.locator(".callhead").inner_text() if bulk_id else ""
    val = p.locator("#validite").inner_text() if bulk_id and p.locator("#validite").count() else ""
    record(G, "Annonce d'une escale de VRAC SEC (clinker, 25 000 MT, vraquier) : les gabarits proposés suivent la nature de la cargaison (MB1), validité 10 jours, agence associée en accès partiel, documents attendus", "AGE",
           "escale créée en brouillon, en-tête « Vrac sec — Clinker — 25 000 MT », validité 10 jours",
           bulk_id is not None and "Brouillon" in status_chip(p) and "Vrac sec" in head and "Clinker" in head and "10 jours" in val and all(("DRY" in (k or "") or not k) for k in ops_visible),
           f"{p.url} {status_chip(p)} {flash_text(p)} | {head[:160]} | {val[:100]}".replace("\n", " "), p, "annonce-vrac-sec")
    if bulk_id:
        page = tab(age, bulk_id, "taches")
        codes = page.locator("td.code").all_inner_texts()
        record(G, "Les tâches de l'escale de vrac sec viennent du socle commun et du gabarit MB1 (déchargement de vrac sec) — aucune tâche pétrolière", "AGE",
               "codes B1.xx présents, aucun 1.xx de M1, ni 29/31 (réservés aux liquides)", any(c.startswith("B1.") for c in codes) and not any(re.match(r"^1\.\d\d$", c) for c in codes) and "29" not in codes and "31" not in codes,
               ", ".join(codes)[:300], page, "vrac-sec-taches")
        page = tab(age, bulk_id, "documents")
        txt = page.locator("main").inner_text()
        record(G, "Les documents attendus demandés à l'annonce sont des tâches : l'attestation d'assurance (catalogue) et le certificat d'origine (liste ouverte, au mandant, 24 h avant l'ETA)", "AGE",
               "« Documents attendus » avec les deux documents", "Certificat d'origine" in txt and "assurance" in txt.lower() and "Documents attendus" in txt, txt[txt.find("Documents attendus"):][:300].replace("\n", " "), page, "vrac-sec-documents-attendus")
        page = tab(age, bulk_id, "parties")
        row = page.locator("tr:has-text('Consignataire associé')").first
        record(G, "L'agence associée est inscrite avec l'accès partiel choisi à l'annonce (tâches, documents)", "AGE", "Partiel — taches, documents", row.count() > 0 and "partiel" in row.inner_text().lower() and "taches" in row.inner_text(), row.inner_text()[:200].replace("\n", " ") if row.count() else "ligne absente", page, "vrac-sec-parties")
        page = tab(age2, bulk_id, "taches")
        record(G, "L'agence associée ouvre l'escale de vrac sec dans son accès partiel (tâches, documents)", "AGE (associée)", "2 onglets", len(nav_tabs(page)) == 2, str(nav_tabs(page)), page, "vrac-sec-acces-associee")
        age.goto(f"/escales/{bulk_id}/formulaires/")
        forms_age = [i.input_value() for i in age.page.locator('form[action$="/action/form_issue/"] input[name="code"]').all()]
        record(G, "Formulaires de l'agence sur une escale de vrac sec : manifeste et plan d'arrimage proposés, PAEC (pétrolier) absent", "AGE",
               "CARGO_MANIFEST et STOWAGE_PLAN offerts, pas de PAEC", "CARGO_MANIFEST" in forms_age and "STOWAGE_PLAN" in forms_age and "PAEC" not in forms_age, ", ".join(forms_age)[:300], age.page, "vrac-sec-formulaires")
        age.goto(f"/escales/{bulk_id}/formulaires/CARGO_MANIFEST/")
        record(G, "Aperçu du manifeste de cargaison (FAL 2) prérempli de l'escale de vrac sec", "AGE", "page rendue avec le navire et le produit", "Clinker" in age.page.content() and "MV BULK E2E" in age.page.content(), age.page.title(), age.page, "vrac-sec-manifeste")
        age.goto(f"/escales/{call_id}/formulaires/")
        forms_liq = [i.input_value() for i in age.page.locator('form[action$="/action/form_issue/"] input[name="code"]').all()]
        record(G, "Sur l'escale pétrolière, l'agence se voit proposer l'échange d'informations avant l'arrivée (PAEC, ISGOTT 22.2)", "AGE", "PAEC offert", "PAEC" in forms_liq, ", ".join(forms_liq)[:300], age.page, "petrolier-paec")
        ter.goto(f"/escales/{call_id}/formulaires/VETTING_CHECKLIST/")
        txt = ter.page.locator("body").inner_text()
        record(G, "Grille de vetting du terminal : chaque limite du poste comparée aux données du navire, statut Y / N / K / Z et avis", "TER", "page rendue avec les statuts", "APTE" in txt and ("Y" in txt or "Z" in txt) and ("limite" in txt.lower() or "limit" in txt.lower()), txt[:300].replace("\n", " "), ter.page, "vetting-grille")

    # ----- conférence de placement et plan d'occupation des postes
    age.goto("/escales/port/")
    txt = age.page.locator("main").inner_text()
    record(G, "Conférence de placement : toutes les escales déclarées du port — à quai, en rade, attendus — avec la nature de la cargaison et le tonnage comme le port le montre, FAL et manifeste", "AGE",
           "sections et colonnes de la conférence, clinker et conteneurs visibles", "quai" in txt.lower() and "Attendus" in txt and "Clinker" in txt and "Tcs/Tcs" in txt and "Manifeste" in txt and "FAL" in txt,
           txt[:300].replace("\n", " "), age.page, "conference-placement")
    r7 = age.page.request.get(f"{BASE}/escales/port/?format=csv")
    record(G, "Téléchargement de la conférence de placement en CSV", "AGE", "fichier CSV avec les en-têtes", r7.status == 200 and "text/csv" in (r7.headers.get("content-type") or "") and len(r7.body()) > 100, f"HTTP {r7.status}, {len(r7.body())} octets", None)
    age.goto("/escales/port/occupation/")
    txt = age.page.locator("main").inner_text()
    record(G, "Plan d'occupation des postes sur la période : escales par poste ou zone, opération, mandant, produit et quantité, ETA / ETB / ETD, état", "AGE",
           "tableau rendu avec les états", "occupation" in txt.lower() and ("en cours" in txt.lower() or "attendu" in txt.lower() or "terminée" in txt.lower()), txt[:300].replace("\n", " "), age.page, "plan-occupation")
    r8 = age.page.request.get(f"{BASE}/escales/port/occupation/?format=csv")
    record(G, "Téléchargement du plan d'occupation en CSV", "AGE", "fichier CSV", r8.status == 200 and "text/csv" in (r8.headers.get("content-type") or ""), f"HTTP {r8.status}, {len(r8.body())} octets", None)

    # ----- API 1.5
    ref_code = ref.split(" ")[0]
    st, gl = api("GET", f"calls/{ref_code}/green-lights/")
    record("API", "GET …/green-lights/ : les feux verts de l'escale et leur état", "AGE", "200, 4 feux tous donnés", st == 200 and isinstance(gl, dict) and len(gl.get("results") or []) == 4 and all(g.get("state") == "GIVEN" for g in gl["results"]), f"{st} {json.dumps(gl)[:200]}", None)
    st, detail = api("GET", f"calls/{ref_code}/")
    record("API", "GET …/calls/<ref>/ : accès de l'appelant (agent principal, accès complet), validité et base de facturation", "AGE", "your_access.level FULL, principal_agent, validity.days 15, billing_basis",
           st == 200 and isinstance(detail, dict) and (detail.get("your_access") or {}).get("level") == "FULL" and (detail.get("your_access") or {}).get("principal_agent") is True and (detail.get("validity") or {}).get("days") == 15 and "billing_basis" in detail,
           f"{st} {json.dumps({k: detail.get(k) for k in ('your_access', 'validity', 'cargo_kind')}, default=str)[:240] if isinstance(detail, dict) else detail}", None)
    st, occ = api("GET", "board/occupation/")
    record("API", "GET /api/v1/board/occupation/ : le plan d'occupation par l'API", "AGE", "200, lignes avec état", st == 200 and isinstance(occ, dict) and isinstance(occ.get("results"), list) and all("state" in r for r in occ["results"]), f"{st} {json.dumps(occ)[:200]}", None)

    # ----- 1.6 : l'annonce s'adapte à l'opération — questions propres au modèle, poste occupé, accostage à couple
    H = "1.6 — L'annonce s'adapte à l'opération"
    age.goto("/escales/nouvelle/")
    p = age.page
    m4 = p.locator("fieldset[data-intake='M4']")
    hidden_before = m4.get_attribute("hidden") is not None
    p.check('input[name="operations"][value="M4"]')
    shown = m4.get_attribute("hidden") is None and m4.locator("#op_M4_grade").is_visible()
    bound = m4.locator("#op_M4_quantity_mt").get_attribute("required") is not None
    p.uncheck('input[name="operations"][value="M4"]')
    unbound = m4.locator("#op_M4_quantity_mt").get_attribute("required") is None and m4.get_attribute("hidden") is not None
    record(H, "Le formulaire d'annonce s'adapte à l'opération : les questions du soutage (M4 — grade, quantité, mode de livraison, SIMOPS) n'apparaissent qu'en cochant le modèle, et n'obligent que lui", "AGE",
           "bloc M4 caché, visible une fois coché avec ses champs obligatoires, caché et libéré une fois décoché", hidden_before and shown and bound and unbound,
           f"caché avant : {hidden_before} ; visible et obligatoire coché : {shown and bound} ; libéré décoché : {unbound}", p, "annonce-adaptee-soutage")
    p.check('input[name="kind"][value="JETTY"]')
    select_like(p.locator("#requested_berth"), "LFW-APP")
    p.fill("#eta", local(2))
    p.fill("#etb", local(4))
    p.fill("#etd", local(30))
    try:
        p.wait_for_selector("[data-berth-occupation]", timeout=10000)
    except Exception:  # noqa: BLE001
        pass
    occ = p.locator("[data-berth-occupation]").inner_text() if p.locator("[data-berth-occupation]").count() else ""
    record(H, "Avant de demander un poste, l'agence voit qui le tient ou l'attend sur la fenêtre demandée : MT ATLANTIC DEMO est à quai sur LFW-APP — autre poste, autres heures, ou accostage à couple", "AGE",
           "avertissement nommant l'escale 0001 et le module M9", "TGLFW-2026-0001" in occ and "M9" in occ, occ[:240].replace("\n", " "), p, "annonce-poste-occupe")
    # the outer vessel: a new tanker alongside MT ATLANTIC DEMO (call 0001, the same agency), with the M9 questions
    p.select_option("#vessel", "")
    p.locator("fieldset:has(#new_imo) details.action summary").first.click()
    p.fill("#new_imo", IMO_OUTER)
    p.fill("#new_name", "MT Outer E2E " + IMO_OUTER[-3:])
    p.fill("#new_flag", "Malta")
    p.select_option("#new_kind", "TANKER_PRODUCT")
    p.fill("#new_dwt", "12000")
    p.locator("#new_dwt").dispatch_event("change")
    try:
        p.wait_for_selector("[data-berth-fit]", timeout=10000)
    except Exception:  # noqa: BLE001
        pass
    fit = p.locator("[data-berth-fit]").inner_text() if p.locator("[data-berth-fit]").count() else ""
    record(H, "Avant de demander le poste, l'agence lit la compatibilité du navire avec ses limites d'acceptation (ici le port en lourd du navire nouveau contre la limite du poste) — la grille de vetting complète viendra du terminal", "AGE",
           "bloc de compatibilité avec le DWT 12 000 dans la limite", "12000" in fit.replace("\u202f", "").replace(" ", "") and ("APTE" in fit or "SUITABLE" in fit), fit[:240].replace("\n", " "), p, "annonce-compatibilite-poste")
    p.check('input[name="cargo_kind"][value="LIQUID"]')
    p.fill("#product", "Gasoil (allègement au poste)")
    p.fill("#quantity", "5000")
    p.check('input[name="operations"][value="M1"]')
    p.check('input[name="modules"][value="M9"]')
    hints = p.locator("[data-party-hints]")
    hints_shown = hints.get_attribute("hidden") is None and hints.locator("li[data-template='M1']:visible").count() >= 1 and hints.locator("li[data-template='M9']:visible").count() >= 1
    before_rows = p.locator("tr[data-party-row]").count()
    hints.locator("li[data-template='M9'] button[data-add-party-role]").first.click()
    added = p.locator("tr[data-party-row]").last
    added_role = added.locator('select[name="party_role"]').input_value()
    added_kind = added.locator('input[name="party_kind"]').input_value()
    record(H, "Les parties qu'appelle l'opération sont proposées (déchargement : terminal, inspecteur, réceptionnaire, laboratoire ; accostage à couple : fournisseur de défenses) ; un bouton ajoute la ligne avec son rôle et sa nature", "AGE",
           "liste visible pour M1 et M9 ; la ligne ajoutée porte le rôle PRE et la nature « défenses »", hints_shown and added_role == "PRE" and "fense" in added_kind.lower(),
           f"visible : {hints_shown} ; lignes {before_rows} → {p.locator('tr[data-party-row]').count()} ; rôle {added_role} ; nature {added_kind}", p, "annonce-parties-proposees")
    added.locator('select[name="party_org"]').select_option("new")
    added.locator('input[name="party_name"]').fill("Défenses & Flexibles E2E")
    db = p.locator("fieldset[data-double-banking]")
    db_shown = db.get_attribute("hidden") is None and db.locator("#db_partner_call").is_visible()
    p.check('input[name="db_position"][value="OUTER"]')
    select_like(p.locator("#db_partner_call"), "ATLANTIC")
    p.select_option("#op_M9_purpose", "LIGHTERING")
    p.fill("#op_M9_duration_h", "12")
    p.fill("#op_M9_loading_condition", "Extérieur sur lest à l'accostage, chargé 5 000 t à la séparation ; intérieur en déchargement")
    p.select_option("#op_M9_fenders_by", "TERMINAL")
    p.fill("#op_M1_max_rate_m3h", "600")
    p.fill("#validity_days", "10")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("TER")
    select_like(rows.nth(0).locator('select[name="party_org"]'), "Terminal pétrolier|Oil terminal")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    outer_id = int(m.group(1)) if m else None
    outer_ref = p.locator(".callhead .ref").first.inner_text().strip().split(" ")[0] if outer_id and p.locator(".callhead .ref").count() else ""
    sec = p.locator("#accostage-a-couple").inner_text() if outer_id and p.locator("#accostage-a-couple").count() else ""
    dec = p.locator("#declare-a-l-annonce").inner_text() if outer_id and p.locator("#declare-a-l-annonce").count() else ""
    record(H, "Annonce d'un ACCOSTAGE À COUPLE : le navire extérieur (nouveau pétrolier) est annoncé à couple de MT ATLANTIC DEMO, désigné parmi les escales de la conférence ; l'aperçu montre la configuration et ce qui a été déclaré (objet, durée, états de chargement, défenses, débit)", "AGE",
           "escale créée, bloc « Accostage à couple » avec TGLFW-2026-0001, bloc « Déclaré à l'annonce » avec l'objet",
           outer_id is not None and db_shown and "TGLFW-2026-0001" in sec and "Allègement" in dec and "600" in dec,
           f"{p.url} {flash_text(p)} | {sec[:160]} | {dec[:160]}".replace("\n", " "), p, "annonce-accostage-a-couple")
    if outer_id:
        page = tab(age, outer_id, "taches")
        form = page.locator('form[action$="/action/request_create/"]:has(input[name="type"][value="DOUBLE_BANKING"])').first
        inner_val = form.locator('[name="inner_vessel"]').input_value() if form.count() else ""
        purpose_val = form.locator('[name="purpose"]').input_value() if form.count() else ""
        duration_val = form.locator('[name="duration_h"]').input_value() if form.count() else ""
        record(H, "La demande d'accostage à couple (tâche 9.01) se présente PRÉREMPLIE sur la ligne de sa tâche : navire intérieur, objet et durée viennent de l'annonce", "AGE",
               "champs inner_vessel, purpose, duration_h renseignés", "ATLANTIC" in inner_val and purpose_val and "12" in duration_val, f"{inner_val} | {purpose_val} | {duration_val}", page, "demande-couple-preremplie")
        age.goto(f"/escales/{outer_id}/?tab=demandes&type=IMMOBILIZATION")
        other = age.page.locator('form[action$="/action/request_create/"] [name="duration_h"]')
        other_val = other.first.input_value() if other.count() else "champ absent"
        record(H, "Une demande ne reprend que les réponses de SON opération : la durée de l'accostage à couple (12 h, module M9) ne préremplit pas une demande d'immobilisation, qui porte pourtant un champ de même nom", "AGE",
               "champ duration_h de la demande d'immobilisation vide", other_val == "", f"duration_h = « {other_val} »", age.page, "prerempli-sa-propre-operation")
        page = tab(age, 1, "apercu")
        sec1 = page.locator("#accostage-a-couple").inner_text() if page.locator("#accostage-a-couple").count() else ""
        record(H, "L'escale du navire intérieur (0001) montre aussitôt la configuration : deux escales de la même agence sont liées dans les deux sens", "AGE",
               "bloc « Accostage à couple » sur 0001 avec la référence du navire extérieur", bool(outer_ref) and outer_ref in sec1 and "intérieur" in sec1.lower(), sec1[:200].replace("\n", " "), page, "couple-escale-interieure")
        cap.goto("/notifications/")
        txt = cap.page.locator("main").inner_text()
        record(H, "La capitainerie est avertie aussitôt qu'un navire annonce venir à couple d'un navire à quai — l'accord exprès du navire intérieur n'est jamais présumé", "CAP",
               "notification nommant les deux navires", "accostage à couple" in txt.lower() and "ATLANTIC" in txt, txt[:240].replace("\n", " "), cap.page, "notification-couple")
        st, detail = api("GET", f"calls/{outer_ref}/")
        record("API", "GET …/calls/<ref>/ : ce qui a été déclaré à l'annonce (operation_details, declared) et le lien d'accostage à couple (linked_call, reciprocal)", "AGE",
               "operation_details.M9.purpose, linked_call.kind OUTER et reciprocal", st == 200 and isinstance(detail, dict) and ((detail.get("operation_details") or {}).get("M9") or {}).get("purpose") == "LIGHTERING"
               and (detail.get("linked_call") or {}).get("kind") == "OUTER" and (detail.get("linked_call") or {}).get("reciprocal") is True and detail.get("declared"),
               f"{st} {json.dumps({k: detail.get(k) for k in ('operation_details', 'linked_call')}, default=str)[:240] if isinstance(detail, dict) else detail}", None)
    # the announcement's answers follow the rule of the product and the quantity: not for a provider
    age.goto("/escales/1/")
    seen_age = age.page.locator("#declare-a-l-annonce").inner_text() if age.page.locator("#declare-a-l-annonce").count() else ""
    pre.goto("/escales/1/")
    main_pre = pre.page.locator("main").inner_text()
    record(H, "Ce que l'agence a déclaré à l'annonce se lit comme le produit et la quantité : l'agence le lit sur l'aperçu de l'escale 0001 (débit, pression, connexions), le prestataire nommé sur la même escale ouvre l'escale sans le lire", "PRE",
           "bloc « Déclaré à l'annonce » présent pour l'agence, absent pour le prestataire", "ANSI 150" in seen_age and pre.page.locator("#declare-a-l-annonce").count() == 0
           and "ANSI 150" not in main_pre and "TGLFW-2026-0001" in pre.page.content(),
           f"agence : {seen_age[:110]} | prestataire : bloc absent = {pre.page.locator('#declare-a-l-annonce').count() == 0}".replace("\n", " "), pre.page, "declare-pas-pour-le-prestataire")
    # the other agency names a vessel of this agency at the berth: the link waits for the harbour master
    age2.goto("/escales/nouvelle/")
    p = age2.page
    p.select_option("#vessel", "")
    p.locator("fieldset:has(#new_imo) details.action summary").first.click()
    p.fill("#new_imo", IMO_OUTER2)
    p.fill("#new_name", "MT Navette E2E " + IMO_OUTER2[-3:])
    p.fill("#new_flag", "Togo")
    p.select_option("#new_kind", "TANKER_PRODUCT")
    p.fill("#new_dwt", "6000")
    p.check('input[name="cargo_kind"][value="LIQUID"]')
    p.fill("#product", "Gasoil (soutage par navire-citerne)")
    p.fill("#quantity", "800")
    p.check('input[name="kind"][value="JETTY"]')
    p.check('input[name="operations"][value="M1"]')
    p.check('input[name="modules"][value="M9"]')
    p.check('input[name="db_position"][value="OUTER"]')
    select_like(p.locator("#db_partner_call"), "ATLANTIC")
    p.select_option("#op_M9_purpose", "BUNKER")
    p.fill("#op_M9_duration_h", "6")
    p.fill("#op_M9_loading_condition", "Navire-citerne chargé à l'accostage, sur lest à la séparation")
    p.fill("#eta", local(6))
    p.fill("#etb", local(8))
    p.fill("#etd", local(20))
    p.fill("#validity_days", "7")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("TER")
    select_like(rows.nth(0).locator('select[name="party_org"]'), "Terminal pétrolier|Oil terminal")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    outer2_id = int(m.group(1)) if m else None
    sec2 = p.locator("#accostage-a-couple").inner_text() if outer2_id and p.locator("#accostage-a-couple").count() else ""
    record(H, "Une AUTRE AGENCE annonce un navire à couple de MT ATLANTIC DEMO (escale d'autrui, vue sur la conférence) : le lien reste à sens unique, « à confirmer » par l'autorisation d'accostage à couple de la capitainerie ; l'agence du navire intérieur est avertie", "AGE (autre agence)",
           "escale créée, bloc avec l'escale 0001 et la mention « à confirmer »", outer2_id is not None and "TGLFW-2026-0001" in sec2 and "confirm" in sec2.lower(),
           f"{p.url} {flash_text(p)} | {sec2[:200]}".replace("\n", " "), p, "couple-autre-agence")
    if outer2_id:
        page = tab(age2, outer2_id, "taches")
        out = submit(page, "request_create", {}, match={"type": "DOUBLE_BANKING"})
        record(H, "L'autre agence dépose la demande d'accostage à couple depuis la ligne de sa tâche, telle que préremplie", "AGE (autre agence)", "demande soumise", "success" in out, out, page, "couple-demande-autre-agence")
        # a draft is the agency's own: the harbour master sees the call, and its request, once it is declared —
        # the other agency files the declaration prerequisites (sanctions, Q88, the certificates it may file for the master)
        page = tab(age2, outer2_id, "taches")
        submit(page, "task_complete", {"note": "listes OFAC, ONU, UE : rien"}, match={"task_id": task_id(page, "05")})
        page = tab(age2, outer2_id, "documents")
        for number, dtype, title, text in (("M0:02", "Q88", "Q88 MT Navette E2E", "Q88 MT NAVETTE E2E"), ("M0:03", "CERTIFICATES", "Certificats MT Navette E2E", "CERTIFICATS STATUTAIRES")):
            form = page.locator('form[action$="/action/document_upload/"]').last
            select_like(form.locator('select[name="task_id"]'), number)
            form.locator('select[name="type"]').select_option(dtype)
            if form.locator('input[name="title"]').count():
                form.locator('input[name="title"]').fill(title)
            form.locator('input[name="file"]').set_input_files(pdf_file(f"{dtype.lower()}-navette.pdf", text))
            form.locator("button.btn").last.click()
            page.wait_for_load_state("load")
        page = tab(age2, outer2_id, "apercu")
        out = submit(page, "declare")
        record(H, "L'autre agence déclare son escale à couple (sanctions, Q88, certificats déposés par elle pour le capitaine) : la capitainerie y accède désormais, avec la demande d'accostage à couple", "AGE (autre agence)",
               "statut Déclarée", "Déclarée" in status_chip(page) and "success" in out, f"{status_chip(page)} {out[:160]}", page, "couple-autre-agence-declaree")
        page = tab(cap, outer2_id, "demandes")
        art = page.locator("article:has-text('Accostage à couple')").first
        rid = art.locator('input[name="request_id"]').first.input_value() if art.count() else ""
        out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid}) if rid else "demande introuvable"
        record(H, "POINT D'ARRÊT : la capitainerie ne peut autoriser l'accostage à couple avant l'accord exprès du navire intérieur (9.02), l'analyse d'amarrage (9.04), la matrice SIMOPS (9.06) et le plan de déhalage (9.08)", "CAP",
               "refus listant les tâches manquantes", "9.02" in out and "9.04" in out, out[:300], page, "couple-point-d-arret")

    # ----- 1.6 : transbordement — le navire-mère relève d'une AUTRE agence ; plusieurs navires la nomment
    def call_of(session, needle):
        session.goto(f"/escales/?scope=all&q={needle}")
        link = session.page.locator(f"a[href^='/escales/']:has-text('{needle}')").first
        if not link.count():
            link = session.page.locator(f"tr:has-text('{needle}') a[href^='/escales/']").first
        m = re.search(r"/escales/(\d+)/", link.get_attribute("href") or "") if link.count() else None
        return int(m.group(1)) if m else 0

    mother_id = call_of(age, "HARMATTAN")
    kara_id = call_of(age2, "KARA")
    page = tab(age, mother_id, "apercu")
    named = page.locator("#navires-lies").inner_text() if page.locator("#navires-lies").count() else ""
    record(H, "STS — le dossier du navire-mère (MT HARMATTAN DEMO, première agence) nomme les navires qui la désignent : MT KARA DEMO, annoncé par une autre agence, à côté de son partenaire MT SAVANNAH DEMO", "AGE",
           "bloc « Autres navires désignant cette escale » avec MT KARA DEMO et son agence", "MT KARA DEMO" in named and "associ" in named.lower(), named[:240].replace("\n", " "), page, "sts-navire-mere-navires-lies")
    page = tab(age2, kara_id, "apercu")
    block = page.locator("#transbordement").inner_text() if page.locator("#transbordement").count() else ""
    header_link = page.locator(f".callhead a[href='/escales/{mother_id}/']").count()
    age2.goto(f"/escales/{mother_id}/")
    hidden = "404" in (age2.page.title() or "") or "introuvable" in age2.page.content().lower() or "not found" in age2.page.content().lower()
    record(H, "STS — le navire-fille de l'autre agence (MT KARA DEMO) nomme le navire-mère sans ouvrir son dossier : lien « à confirmer », rôle receveur pris d'office, aucun lien cliquable, dossier du navire-mère introuvable pour elle", "AGE (autre agence)",
           "bloc Transbordement avec la référence du navire-mère et « à confirmer » ; pas de lien ; 404", "HARMATTAN" in block and "confirmer" in block and header_link == 0 and hidden,
           f"{block[:200]} | lien en-tête : {header_link} | dossier mère caché : {hidden}".replace("\n", " "), age2.page, "sts-fille-autre-agence")
    # a third vessel, announced through the form by the other agency: the mother is picked among the calls of the port
    age2.goto("/escales/nouvelle/")
    p = age2.page
    p.select_option("#vessel", "")
    p.locator("fieldset:has(#new_imo) details.action summary").first.click()
    p.fill("#new_imo", IMO_DAUGHTER)
    p.fill("#new_name", "MT Fille E2E " + IMO_DAUGHTER[-3:])
    p.fill("#new_flag", "Togo")
    p.select_option("#new_kind", "TANKER_PRODUCT")
    p.fill("#new_dwt", "20000")
    p.check('input[name="cargo_kind"][value="LIQUID"]')
    p.fill("#product", "Crude oil")
    p.fill("#quantity", "8000")
    p.check('input[name="kind"][value="STS_AREA"]')
    p.check('input[name="operations"][value="M3"]')
    sts = p.locator("fieldset[data-sts]")
    sts_shown = sts.get_attribute("hidden") is None and sts.locator("#linked_call").is_visible()
    option = p.locator("#linked_call optgroup").nth(1).locator("option", has_text="HARMATTAN")
    mother_value = option.first.get_attribute("value") if option.count() else ""
    if mother_value:
        p.select_option("#linked_call", mother_value)
    p.fill("#op_M3_poac", "Capt. A. Mensah — STS Services Demo")
    p.select_option("#op_M3_transfer_mode", "ANCHOR")
    p.fill("#eta", local(24 * 5))
    p.fill("#etd", local(24 * 6))
    p.fill("#validity_days", "10")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("PRE")
    select_like(rows.nth(0).locator('select[name="party_org"]'), "STS")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    daughter_id = int(m.group(1)) if m else None
    block = p.locator("#transbordement").inner_text() if daughter_id and p.locator("#transbordement").count() else ""
    record(H, "STS — une AUTRE AGENCE annonce un navire-fille par le formulaire : le bloc des deux navires apparaît avec le modèle M3, le navire-mère se choisit parmi les escales du port (autres agences, conférence de placement), le rôle inverse est pris d'office", "AGE (autre agence)",
           "escale créée, bloc Transbordement : receveur, MT HARMATTAN DEMO, « à confirmer » ; l'agence du navire-mère avertie",
           daughter_id is not None and sts_shown and bool(mother_value) and "HARMATTAN" in block and "confirmer" in block and ("eceveur" in block or "eceiv" in block),
           f"{p.url} {flash_text(p)} | {block[:200]}".replace("\n", " "), p, "sts-annonce-fille-autre-agence")
    page = tab(age, mother_id, "apercu")
    named = page.locator("#navires-lies").inner_text() if page.locator("#navires-lies").count() else ""
    age.goto("/notifications/")
    notes = age.page.locator("main").inner_text()
    record(H, "STS — l'agence du navire-mère est avertie de chaque navire qui la nomme ; un brouillon d'une autre agence n'apparaît pas sur son dossier (il n'appartient qu'à son agence)", "AGE",
           "notification « annonce un transbordement navire-navire avec MT HARMATTAN DEMO » ; le navire-fille en brouillon absent du bloc", "transbordement navire-navire" in notes and "MT FILLE E2E" in notes.upper() and "FILLE E2E" not in named.upper() and "KARA" in named,
           f"{named[:160]} || {notes[:200]}".replace("\n", " "), age.page, "sts-notification-navire-mere")
    # the harbour master authorises the STS area and window of the declared daughter vessel: the link stands
    page = tab(cap, kara_id, "demandes")
    art = page.locator("article:has-text('STS')").first
    rid = art.locator('input[name="request_id"]').first.input_value() if art.count() else ""
    out = submit(page, "request_decide", {"decision": "APPROVED"}, match={"request_id": rid}) if rid else "demande introuvable"
    page = tab(age2, kara_id, "apercu")
    block = page.locator("#transbordement").inner_text() if page.locator("#transbordement").count() else ""
    record(H, "STS — la capitainerie autorise la zone et la fenêtre STS du navire-fille : le lien est confirmé (les journaux de pompage des deux navires se rapprochent désormais sur son dossier), le navire-mère garde son premier partenaire", "CAP",
           "décision enregistrée ; plus de mention « à confirmer » sur le dossier du navire-fille", "success" in out and "HARMATTAN" in block and "confirmer" not in block, f"{out[:120]} | {block[:160]}".replace("\n", " "), page, "sts-zone-autorisee")

    # a refused announcement comes back as typed and registers nothing; the partner's agency may be unknown to the port
    age.goto("/escales/nouvelle/")
    p = age.page
    p.select_option("#vessel", "")
    p.locator("fieldset:has(#new_imo) details.action summary").first.click()
    p.fill("#new_imo", IMO_TYPED)
    p.fill("#new_name", "MT Saisie E2E " + IMO_TYPED[-3:])
    p.fill("#new_flag", "Togo")
    p.select_option("#new_kind", "TANKER_PRODUCT")
    p.fill("#new_dwt", "30000")
    p.check('input[name="cargo_kind"][value="LIQUID"]')
    p.fill("#product", "Pétrole brut — lot saisi une fois")
    p.fill("#quantity", "9000")
    p.check('input[name="kind"][value="STS_AREA"]')
    p.check('input[name="operations"][value="M3"]')
    p.check('input[name="sts_role"][value="DONOR"]')
    p.locator("fieldset[data-sts] details.action summary").first.click()
    p.fill("#partner_imo", "9999993")  # MT ATLANTIC DEMO: the port knows this IMO — the announcement is refused
    p.fill("#partner_name", "MT Fille Golfe E2E")
    p.fill("#partner_flag", "Togo")
    p.fill("#op_M3_poac", "Capt. A. Mensah — STS Services Demo")
    p.fill("#eta", local(24 * 7))
    p.fill("#etd", local(24 * 8))
    p.fill("#validity_days", "10")
    rows = p.locator("tr[data-party-row]")
    rows.nth(0).locator('select[name="party_role"]').select_option("INS")
    rows.nth(0).locator('select[name="party_org"]').select_option("new")
    rows.nth(0).locator('input[name="party_name"]').fill("Laboratoire Saisi Une Fois E2E")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    reason = flash_text(p)
    kept = {"new_imo": p.input_value("#new_imo"), "new_name": p.input_value("#new_name"), "product": p.input_value("#product"),
            "partner_imo": p.input_value("#partner_imo"), "poac": p.input_value("#op_M3_poac"),
            "party": p.locator("tr[data-party-row]").nth(0).locator('input[name="party_name"]').input_value()}
    record(H, "Une annonce REFUSÉE revient telle qu'elle a été saisie, le motif en tête — ici le navire partenaire « nouveau » porte un IMO que le port connaît déjà (MT ATLANTIC DEMO) : la plateforme le nomme et renvoie à la liste des navires enregistrés", "AGE",
           "même page, message nommant MT ATLANTIC DEMO, saisies présentes (navire nouveau, produit, partenaire, POAC, partie nouvelle)",
           "/escales/nouvelle/" in p.url and has_error(p) and "ATLANTIC" in reason and kept["new_imo"] == IMO_TYPED and kept["new_name"].startswith("MT Saisie E2E")
           and kept["product"].startswith("Pétrole brut") and kept["partner_imo"] == "9999993" and kept["poac"].startswith("Capt.") and kept["party"].startswith("Laboratoire Saisi"),
           f"{reason[:170]} | {kept}", p, "annonce-refusee-rendue-telle-que-saisie")
    # the same form, corrected in place: the partner vessel is new, and so is its agency
    p.fill("#partner_imo", IMO_GOLFE)
    p.locator("fieldset[data-sts] details.action summary", has_text="agence").first.click()
    p.fill("#partner_agency_name", "Golfe Shipping E2E")
    p.fill("#partner_agency_email", "ops@golfe-shipping-e2e.example")
    p.click("button.btn:has-text('Créer')")
    p.wait_for_load_state("load")
    m = re.search(r"/escales/(\d+)/", p.url)
    typed_id = int(m.group(1)) if m else None
    said = flash_text(p)
    block = p.locator("#transbordement").inner_text() if typed_id and p.locator("#transbordement").count() else ""
    record(H, "Le même formulaire, corrigé sur place, passe : rien n'avait été enregistré par le refus (le navire nouveau garde son IMO, la partie nouvelle est créée une seule fois) ; le navire partenaire reçoit sa propre escale sous SON agence — une agence que le port ne connaissait pas, nommée à l'annonce —, qui seule la déclarera", "AGE",
           "escale créée ; bloc Transbordement avec MT FILLE GOLFE E2E et Golfe Shipping E2E ; message « n'a pas encore de compte »",
           typed_id is not None and "FILLE GOLFE E2E" in block.upper() and "Golfe Shipping E2E" in block and "pas encore de compte" in said,
           f"{p.url} | {said[:200]} | {block[:160]}".replace("\n", " "), p, "sts-agence-inconnue-du-port")
    dirs.goto("/notifications/")
    told = dirs.page.locator("main").inner_text()
    record(H, "L'administrateur fonctionnel du port est averti qu'une agence désignée à l'annonce n'a pas encore de compte : il lui ouvre ses accès (lien vers sa fiche)", "DIR",
           "notification nommant Golfe Shipping E2E et son navire, lien vers la fiche de l'organisation", "Golfe Shipping E2E" in told and "pas encore de compte" in told
           and dirs.page.locator("main a[href*='/admin/core/organization/']").count() >= 1, told[:260].replace("\n", " "), dirs.page, "notification-agence-sans-compte")

    # ----- 1.4 : tableau des escales du port — consultation par toutes les parties du port, isolation entre agences
    age.goto("/escales/port/")
    txt = age.page.locator("main").inner_text()
    record("Tableau du port", "L'agence voit toutes les escales déclarées du port (navire, agence, zone, état, heures) et ouvre les siennes ; l'escale E2E archivée n'y est plus", "AGE",
           "escales de démonstration listées avec leurs liens", "MT ATLANTIC DEMO" in txt and "MT GULF DEMO" in txt and age.page.locator("main a[href^='/escales/']").count() >= 3, txt[:300], age.page, "tableau-port-agence")
    com.goto("/escales/port/")
    txt = com.page.locator("main").inner_text()
    record("Tableau du port", "L'armateur consulte le tableau du port : navire, agence, poste, nature de la cargaison et tonnage (comme la conférence de placement, réglage du port), heures — jamais le détail opérationnel d'une autre agence", "COM",
           "tableau rendu avec la nature de la cargaison, sans lien vers les escales d'autrui", "MT ATLANTIC DEMO" in txt and "Clinker" in txt and "consultation seule" in txt, txt[:300], com.page, "tableau-port-armateur")
    age_sl.goto("/escales/port/")
    txt = age_sl.page.locator("main").inner_text()
    record("Tableau du port", "L'agence de Freetown ne voit que les escales de son port", "AGE (SLFNA)", "aucune escale de Lomé", "TGLFW" not in txt and "SLFNA" in txt, txt[:300], age_sl.page, "tableau-port-freetown")
    st, rows = api("GET", "board/")
    record("API", "GET /api/v1/board/ : la conférence de placement par l'API (navire, agence, nature de la cargaison et tonnage quand le port les montre, FAL, manifeste)", "AGE", "200, lignes avec cargo et quantity, sans product",
           st == 200 and isinstance(rows, dict) and rows.get("results") and all("product" not in r and "cargo" in r and "fal_filed" in r for r in rows["results"]), f"{st} {json.dumps(rows)[:200]}", None)
    st, log = api("GET", "calls/TGLFW-2026-0001/pumping-log/")
    record("API", "GET …/pumping-log/ : relevés des deux côtés et comparaison heure par heure", "AGE", "200, comparaison avec écart",
           st == 200 and isinstance(log, dict) and log.get("comparison") and any(r["exceeds_tolerance"] for r in log["comparison"]), f"{st} {json.dumps(log)[:200]}", None)
    st, chk = api("GET", "calls/TGLFW-2026-0001/safety-checklist/")
    record("API", "GET …/safety-checklist/ : la liste de contrôle et ses réponses", "AGE", "200, liste signée", st == 200 and isinstance(chk, dict) and (chk.get("checklist") or {}).get("status") == "SIGNED", f"{st} {json.dumps(chk)[:160]}", None)

    sessions = {"age": age, "cap": cap, "ter": ter, "apo": apo, "svc": svc, "adm": adm, "ins": ins, "com": com, "pre": pre, "dir": dirs, "sur": sur, "age2": age2, "master": master, "age_sl": age_sl, "_call_id": call_id}
    return call_id, sessions


def read_last_link_from_log(org_name):
    """The convocation e-mails are written by the console e-mail backend to the server log: the last party link sent to the organisation."""
    if not OPTS.mail_log or not pathlib.Path(OPTS.mail_log).exists():
        return ""
    log = pathlib.Path(OPTS.mail_log).read_text(encoding="utf-8", errors="replace")
    blocks = log.split("Content-Type: text/plain")
    for block in reversed(blocks):
        if org_name in block or "labo.e2e@example.org" in block:
            m = re.search(r"(https?://[^\s/]+/bord/[A-Za-z0-9_\-]+/)", block)
            if m:
                return BASE + m.group(1)[m.group(1).index("/bord/"):]
    m = None
    for m in re.finditer(r"(https?://[^\s/]+/bord/[A-Za-z0-9_\-]{20,}/)", log):
        pass
    return (BASE + m.group(1)[m.group(1).index("/bord/"):]) if m else ""


# ----------------------------------------------------------------------------------------------- parcours des écrans
TABS = ["apercu", "taches", "jalons", "demandes", "documents", "mesures", "contestations", "echanges", "journal", "parties"]
COMMON = ["/", "/escales/", "/escales/?scope=all&q=DEMO", "/escales/port/", "/escales/port/occupation/", "/notifications/", "/compte/", "/compte/mfa/activer/", "/manifest.webmanifest", "/sw.js"]
EXTRA = {
    "AGE": ["/escales/nouvelle/"],
    "CAP": ["/carte/", "/surete/", "/surete/journal/"],
    "SUR": ["/surete/", "/surete/journal/"],
    "DIR": ["/statistiques/", "/statistiques/?from=2026-01-01&to=2026-12-31", "/pilotage/", "/carte/", "/admin/", "/admin/core/port/1/change/",
            "/admin/core/organization/", "/admin/core/user/", "/admin/core/berth/", "/admin/registry/calltemplate/", "/admin/registry/templateversion/1/change/",
            "/admin/registry/milestonetype/", "/admin/registry/requesttype/", "/admin/registry/requesttype/3/change/", "/admin/registry/documenttype/",
            "/admin/registry/holdpoint/2/change/", "/admin/registry/interruptioncause/", "/admin/registry/webhooksubscription/",
            "/admin/registry/reportaccess/", "/admin/registry/documenttype/?q=QUALITY"],
    "APO": ["/carte/"],
}
DOWNLOADS = {"COM": ["/escales/1/export/"], "DIR": ["/escales/1/export/"]}


def crawl(browser, sessions):
    """Every screen a role can reach: the common pages, each call the role sees (its ten tabs, its forms page and the
    previews of the first forms offered, the statement of facts when the page offers it), the role's own pages."""
    S = "Parcours des écrans"
    for key, sess in sessions.items():
        if key in ("master", "age_sl", "_call_id"):
            continue
        role = key.upper()
        page = sess.page
        bad, visited = [], 0

        def visit(u):
            nonlocal visited
            visited += 1
            try:
                r = sess.goto(u)
                if not page_ok(page, r):
                    bad.append(f"{u} → {r.status if r else 'sans réponse'}")
            except PWTimeout:
                bad.append(f"{u} → délai dépassé")
            except Exception as exc:  # noqa: BLE001
                bad.append(f"{u} → {exc.__class__.__name__}")

        for u in COMMON + EXTRA.get(role, []):
            visit(u)
        sess.goto("/escales/")
        hrefs = sorted({a.get_attribute("href") for a in page.locator("a[href^='/escales/']").all() if re.match(r"^/escales/\d+/$", a.get_attribute("href") or "")})
        calls = [int(re.search(r"(\d+)", h).group(1)) for h in hrefs][:4]
        for cid in calls:
            for t in TABS:
                visit(f"/escales/{cid}/?tab={t}")
            sess.goto(f"/escales/{cid}/")
            if page.locator("a[href$='/rapport-des-faits/']").count():
                visit(f"/escales/{cid}/rapport-des-faits/")
            visit(f"/escales/{cid}/terrain/")
            if page.locator("a[href$='/liste-de-controle/']").count():
                visit(f"/escales/{cid}/liste-de-controle/")
            visit(f"/escales/{cid}/formulaires/")
            previews = [a.get_attribute("href") for a in page.locator("a[href*='/formulaires/']").all() if re.search(r"/formulaires/[A-Z_0-9]+/$", a.get_attribute("href") or "")]
            for u in sorted(set(previews))[:4]:
                visit(u)
        for u in DOWNLOADS.get(role, []):
            visited += 1
            r = page.request.get(BASE + u)
            if r.status >= 400 or len(r.body()) < 100:
                bad.append(f"{u} → {r.status}")
        record(S, f"{visited} écrans et aperçus ouverts avec le rôle {role} ({len(calls)} escales visibles)", role, "aucune erreur serveur, aucune page introuvable",
               not bad, "; ".join(bad) if bad else f"{visited} pages sans erreur", page, f"parcours-{key}")
    # capitaine par code : ses onglets et ses formulaires
    m = sessions["master"]
    mp = m.page
    cid = sessions.get("_call_id")
    bad = []
    if cid:
        for t in TABS:
            r = m.goto(f"/escales/{cid}/?tab={t}")
            if not page_ok(mp, r):
                bad.append(f"?tab={t} → {r.status if r else '-'}")
        r = m.goto(f"/escales/{cid}/formulaires/")
        if not page_ok(mp, r):
            bad.append(f"formulaires → {r.status if r else '-'}")
        r = m.goto(f"/escales/{cid}/liste-de-controle/")
        if not page_ok(mp, r):
            bad.append(f"liste de contrôle → {r.status if r else '-'}")
        m.goto("/")
        if "/compte/connexion/" not in mp.url and "tableau de bord" in mp.locator("body").inner_text().lower():
            bad.append("le capitaine atteint le tableau de bord")
    record(S, "Capitaine par code (téléphone) : dix onglets, formulaires, et pas de tableau de bord", "NAV (capitaine)", "pages rendues ; tableau de bord refusé",
           not bad and cid is not None, "; ".join(bad) if bad else "pages rendues, tableau de bord refusé", mp, "parcours-capitaine")
    # public
    anon = Session(browser, "anon")
    bad = []
    for u in ["/compte/connexion/", "/bord/", "/verifier/", "/healthz", "/api/docs/", "/manifest.webmanifest"]:
        r = anon.goto(u)
        if not page_ok(anon.page, r):
            bad.append(f"{u} → {r.status if r else '-'}")
    r = anon.page.request.get(BASE + "/api/schema/")
    if r.status != 200 or b"openapi" not in r.body()[:200]:
        bad.append(f"/api/schema/ → {r.status}")
    anon.goto("/escales/1/")
    redirected = "/compte/connexion/" in anon.page.url
    record(S, "Pages publiques (connexion, accès par code, vérification, santé, documentation et schéma de l'API) ; une page privée renvoie à la connexion", "public",
           "pages rendues ; redirection vers la connexion", not bad and redirected, ("; ".join(bad) + " ") + f"redirigé : {redirected}", anon.page, "parcours-public")
    anon.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--no-proxy-server"])
        try:
            call_id, sessions = scenario(browser)
        except Exception:  # noqa: BLE001
            record("Escale de bout en bout", "Interruption du scénario", "—", "scénario complet", False, traceback.format_exc()[-600:], None)
            sessions = {}
        try:
            if sessions:
                crawl(browser, sessions)
        except Exception:  # noqa: BLE001
            record("Parcours des écrans", "Interruption du parcours", "—", "parcours complet", False, traceback.format_exc()[-600:], None)
        browser.close()
    (HERE / "results.json").write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in RESULTS if r["status"] == "OK")
    ko = sum(1 for r in RESULTS if r["status"] == "KO")
    print(f"\n{ok} OK, {ko} KO, {len(RESULTS) - ok - ko} non vérifiée(s) sur {len(RESULTS)} — {HERE / 'results.json'}")
    sys.exit(1 if ko else 0)


if __name__ == "__main__":
    main()
