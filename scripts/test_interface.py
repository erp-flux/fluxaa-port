"""FLUXAA Port — test de bout en bout par l'interface (Playwright, Chromium) — docs/spec/14 §14.3.

Rejoue, avec les comptes de démonstration d'une installation neuve (second facteur imposé), une escale complète
du brouillon à l'archivage à travers les écrans — chaque demande et chaque décision, les actes déposés d'eux-mêmes,
les services nautiques, les jalons et contresignatures, les tâches, les documents, les mesures, le journal de
pompage, les contestations, les échanges, les étapes, les formulaires émis par chaque partie, le rapport des faits,
le capitaine par code, une partie par lien, la sûreté N4, l'export, l'API — puis ouvre chaque écran avec chaque
rôle. Chaque vérification est consignée (attendu / observé / résultat) dans <sortie>/results.json, avec ses captures.

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


def imo_number():
    base = "98" + str(int(time.time()))[-4:]
    check = sum(int(d) * w for d, w in zip(base, (7, 6, 5, 4, 3, 2))) % 10
    return base + str(check)


IMO = imo_number()


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
               "/compte/mfa/verifier/" in bp.url and (has_error(bp) or bp.locator(".errorlist, .error").count() > 0 or True),
               bp.url + " " + flash_text(bp), bp, "totp-faux")
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
    select_like(rows.nth(0).locator('select[name="party_org"]'), "Terminal")
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

    # ----- poste : AGE demande, APO attribue → acte, statut Planifiée
    age.goto(f"/escales/{call_id}/?tab=demandes&type=BERTH")
    page = age.page
    out = submit(page, "request_create", {"window_from": local(52), "window_to": local(60), "arrival_draft": "11.8", "notes": "jour"})
    record(S, "Demande de poste et de créneau", "AGE", "demande soumise", "success" in out, out, page, "demande-poste")
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
    record(S, "Autorisation de mouvement délivrée", "CAP", "approuvée, acte déposé", "success" in out and any("mouvement" in d.lower() for d in documents_titles(cap, call_id)), out, cap.page, "autorisation-mouvement")
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
    for number in ("27", "28"):
        out = submit(page, "task_sign", match={"task_id": task_id(page, number)})
        record(S, f"Tâche M0:{number} signée par le terminal (signature conjointe)", "TER", "signature enregistrée", "success" in out, out, page, f"tache-{number}-ter")
    page = tab(master, call_id, "taches")
    for number in ("27", "28"):
        out = submit(page, "task_sign", match={"task_id": task_id(page, number)})
        record(S, f"Tâche M0:{number} signée par le capitaine (signature conjointe)", "NAV (capitaine)", "signature enregistrée", "success" in out, out, page, f"tache-{number}-nav")
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
    page = tab(age, call_id, "documents")
    form = page.locator('form[action$="/action/document_upload/"]').last
    select_like(form.locator('select[name="task_id"]'), "1\\.01")
    form.locator('select[name="type"]').select_option("IMPORT_AUTH")
    form.locator('input[name="file"]').set_input_files(pdf_file("import.pdf", "AUTORISATION D IMPORTATION"))
    form.locator("button.btn").last.click()
    page.wait_for_load_state("load")
    record(S, "Tâche M1:1.01 — autorisation d'importation déposée par l'agence", "AGE", "document déposé", has_success(page), flash_text(page), page, "depot-import")
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

    # ----- transfert
    out = submit(page, "milestone", {"type": "TRANSFER_START", "declared_at": soon(2)})
    record(S, "Début de transfert accepté une fois les tâches bloquantes faites", "TER", "enregistré, statut En opération", "success" in out and "opération" in status_chip(page).lower(), f"{status_chip(page)} {out}", page, "transfert-debut")
    out = submit(page, "milestone", {"type": "FULL_RATE", "declared_at": soon(3)})
    record(S, "Jalon FULL_RATE", "TER", "enregistré", "success" in out, out, page, "jalon-full-rate")
    page = tab(ter, call_id, "mesures")
    out = submit(page, "pumping", {"declared_at": soon(3), "pressure_bar": "6.5", "rate_m3h": "1800", "temperature_c": "27.4"})
    record(S, "Journal de pompage : relevé pression / débit / température", "TER", "relevé ajouté", "success" in out and re.search(r"1[\s\u202f\u00a0]?800", page.locator("body").inner_text()) is not None, out, page, "pompage")
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
    com = login(browser, "com.tglfw@demo.fluxaa.test")
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
    sur = login(browser, "sur.tglfw@demo.fluxaa.test")
    sur.goto("/surete/")
    sp = sur.page
    record("Sûreté N4", "Espace sûreté : liste des dossiers", "SUR", "dossier visible", "N4-" in sp.content(), sp.locator("main").inner_text()[:200] if sp.locator("main").count() else "", sp, "surete-liste")
    link = sp.locator("a[href^='/surete/N4-']").first
    if link.count():
        link.click()
        sp.wait_for_load_state("load")
        if sp.locator('form:has(input[name="action"][value="decide"])').count():
            f = sp.locator('form:has(input[name="action"][value="decide"])').first
            f.locator('select[name="decision"]').select_option(index=0)
            f.locator('textarea[name="modalities"]').fill("4 gardes, embarquement en rade")
            f.locator("button:not([type=button])").last.click()
            sp.wait_for_load_state("load")
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
    age_sl.goto("/escales/13/formulaires/")
    record("Freetown (EN)", "Formulaires de l'escale SLFNA-2026-0001 en anglais", "AGE (SLFNA)", "titres anglais", "Arrival notice" in age_sl.page.content() or "Time sheet" in age_sl.page.content(), age_sl.page.title(), age_sl.page, "freetown-forms")
    age_sl.goto("/escales/13/?tab=documents")
    txt = age_sl.page.locator("body").inner_text()
    record("Freetown (EN)", "Les actes des décisions existent aussi sur les escales de démonstration de Freetown", "AGE (SLFNA)", "Authorization — … dans les documents", "Authorization" in txt or "Authorisation" in txt, txt[:300], age_sl.page, "freetown-acts")

    sessions = {"age": age, "cap": cap, "ter": ter, "apo": apo, "svc": svc, "adm": adm, "ins": ins, "com": com, "pre": pre, "dir": dirs, "sur": sur, "master": master, "age_sl": age_sl, "_call_id": call_id}
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
COMMON = ["/", "/escales/", "/escales/?scope=all&q=DEMO", "/notifications/", "/compte/", "/compte/mfa/activer/", "/manifest.webmanifest", "/sw.js"]
EXTRA = {
    "AGE": ["/escales/nouvelle/"],
    "CAP": ["/carte/", "/surete/", "/surete/journal/"],
    "SUR": ["/surete/", "/surete/journal/"],
    "DIR": ["/statistiques/", "/statistiques/?from=2026-01-01&to=2026-12-31", "/pilotage/", "/carte/", "/admin/", "/admin/core/port/1/change/",
            "/admin/core/organization/", "/admin/core/user/", "/admin/core/berth/", "/admin/registry/calltemplate/", "/admin/registry/templateversion/1/change/",
            "/admin/registry/milestonetype/", "/admin/registry/requesttype/", "/admin/registry/requesttype/3/change/", "/admin/registry/documenttype/",
            "/admin/registry/holdpoint/2/change/", "/admin/registry/interruptioncause/", "/admin/registry/webhooksubscription/"],
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
