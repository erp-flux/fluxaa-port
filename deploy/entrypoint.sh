#!/usr/bin/env bash
# FLUXAA Port — point d'entrée des conteneurs « web » et « scheduler ».
#
#   web [options gunicorn…]   (défaut) attente de la base ; migrations des deux bases avec le rôle
#                             PROPRIÉTAIRE ; droits des rôles d'exécution ; traductions ; fichiers
#                             statiques ; catalogues de référence des ports ; puis gunicorn. Les
#                             options placées après « web » sont transmises à gunicorn
#                             (ex. : « web --workers 5 »).
#   scheduler                 attente de la base, puis boucle des traitements périodiques (60 s).
#   ais <port> <source…>      écoute d'une source AIS pour un port (facultatif, DEPLOIEMENT.md §15).
#   toute autre commande      exécutée telle quelle (ex. : python manage.py shell,
#                             /app/scripts/backup.sh).
#
# Juste avant de lancer gunicorn ou le planificateur, les identifiants du propriétaire et du
# superutilisateur PostgreSQL sont retirés de l'environnement du processus : le service tourne
# uniquement avec les rôles d'exécution, qui n'ont aucun droit de suppression sur le registre.
# (Les commandes lancées par « docker compose exec/run » reçoivent, elles, l'environnement complet
# de deploy/.env : c'est ainsi que les sauvegardes utilisent le rôle propriétaire.)
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

log() { printf '[entrypoint] %s\n' "$*" >&2; }

# --------------------------------------------------------------------------------------------
# Contrôle de la configuration : messages clairs plutôt qu'une trace Python au premier usage.
# --------------------------------------------------------------------------------------------
check_config() {
  python - "$1" <<'PY'
import os
import sys
from urllib.parse import unquote, urlparse

mode = sys.argv[1]
errors = []


def env(name):
    return os.environ.get(name, "").strip()


def credentials(url):
    parsed = urlparse(url)
    return unquote(parsed.username or ""), unquote(parsed.password or "")


required = ["DJANGO_SECRET_KEY", "FLUXAA_SIGNING_KEY", "FLUXAA_N4_KEYS", "DATABASE_URL", "SECURE_DATABASE_URL"]
if mode == "web":
    required += ["DATABASE_OWNER_URL", "SECURE_DATABASE_OWNER_URL"]
for name in required:
    if not env(name):
        errors.append(f"{name} n'est pas défini (voir deploy/.env.example).")

# Les mots de passe des URL doivent être ceux avec lesquels les rôles ont été créés.
for url_var, password_var in (("DATABASE_URL", "FLUXAA_APP_PASSWORD"),
                              ("DATABASE_OWNER_URL", "FLUXAA_OWNER_PASSWORD"),
                              ("SECURE_DATABASE_URL", "FLUXAA_SECURE_APP_PASSWORD"),
                              ("SECURE_DATABASE_OWNER_URL", "FLUXAA_OWNER_PASSWORD")):
    if env(url_var) and env(password_var) and credentials(env(url_var))[1] != env(password_var):
        errors.append(f"le mot de passe contenu dans {url_var} ne correspond pas à {password_var}.")

# Séparation des rôles : le service ne doit jamais tourner avec le rôle propriétaire, et le
# domaine N4 a son propre rôle d'exécution.
app_role = credentials(env("DATABASE_URL"))[0]
secure_role = credentials(env("SECURE_DATABASE_URL"))[0]
owner_roles = {credentials(env(v))[0] for v in ("DATABASE_OWNER_URL", "SECURE_DATABASE_OWNER_URL") if env(v)}
if app_role and app_role in owner_roles:
    errors.append("DATABASE_URL utilise le rôle propriétaire : indiquez le rôle d'exécution (fluxaa_app).")
if secure_role and (secure_role in owner_roles or secure_role == app_role):
    errors.append("SECURE_DATABASE_URL doit utiliser un rôle distinct (fluxaa_secure_app).")

keys = [k.strip() for k in env("FLUXAA_N4_KEYS").split(",") if k.strip()]
if keys:
    from cryptography.fernet import Fernet

    for number, key in enumerate(keys, start=1):
        try:
            Fernet(key.encode("ascii"))
        except Exception:
            errors.append(f"FLUXAA_N4_KEYS : la clé n° {number} n'est pas une clé Fernet valide.")

if env("DJANGO_DEBUG").lower() in {"1", "true", "yes", "on"}:
    errors.append("DJANGO_DEBUG est activé : interdit sur une installation de production.")

for message in errors:
    print(f"[entrypoint] ERREUR de configuration : {message}", file=sys.stderr)
sys.exit(1 if errors else 0)
PY
}

# --------------------------------------------------------------------------------------------
# Attente de la base de données (60 s au plus), avec le rôle d'exécution de DATABASE_URL.
# --------------------------------------------------------------------------------------------
wait_for_db() {
  log "Attente de la base de données…"
  python - <<'PY'
import os
import sys
import time

import psycopg

url = os.environ.get("DATABASE_URL", "")
if not url.startswith(("postgres://", "postgresql://", "pgsql://")):
    print("[entrypoint] DATABASE_URL n'est pas une URL PostgreSQL : attente ignorée.", file=sys.stderr)
    sys.exit(0)
url = "postgresql://" + url.split("://", 1)[1]
deadline = time.monotonic() + 60
last_error = None
while time.monotonic() < deadline:
    try:
        with psycopg.connect(url, connect_timeout=5) as connection:
            connection.execute("SELECT 1")
        sys.exit(0)
    except psycopg.Error as exc:
        last_error = exc
        time.sleep(2)
print(f"[entrypoint] ERREUR : base de données injoignable après 60 s : {last_error}", file=sys.stderr)
print("[entrypoint] Vérifiez « docker compose logs db », puis que les mots de passe de deploy/.env sont "
      "ceux utilisés lors de la création des rôles (deploy/postgres-init/01-init.sh, premier démarrage).",
      file=sys.stderr)
sys.exit(1)
PY
}

# Retire de l'environnement les secrets inutiles au service une fois les migrations faites.
drop_privileged_credentials() {
  unset DATABASE_OWNER_URL SECURE_DATABASE_OWNER_URL POSTGRES_PASSWORD \
        FLUXAA_OWNER_PASSWORD FLUXAA_APP_PASSWORD FLUXAA_SECURE_APP_PASSWORD
}

prepare_web() {
  check_config web
  wait_for_db

  log "Migrations de la base principale (rôle propriétaire)…"
  FLUXAA_MIGRATE=1 python manage.py migrate --noinput
  log "Migrations de la base de sûreté N4 (rôle propriétaire)…"
  FLUXAA_MIGRATE=1 python manage.py migrate --database secure --noinput

  log "Droits des rôles d'exécution (aucune suppression sur le registre)…"
  FLUXAA_MIGRATE=1 python manage.py apply_db_grants

  log "Compilation des traductions…"
  python manage.py compilemessages --ignore=.venv --ignore=media --ignore=staticfiles

  log "Collecte des fichiers statiques…"
  python manage.py collectstatic --noinput

  # Catalogues de référence (idempotent : ne remplace jamais ce que l'administrateur du port a
  # modifié). Par défaut tous les ports connus (SLFNA Freetown, TGLFW Lomé) ; FLUXAA_BOOTSTRAP_PORTS
  # permet de n'en charger qu'une partie (instance nationale), ex. : FLUXAA_BOOTSTRAP_PORTS=TGLFW.
  local codes=() args=() code
  IFS=', ' read -r -a codes <<< "${FLUXAA_BOOTSTRAP_PORTS:-}"
  for code in ${codes[@]+"${codes[@]}"}; do
    if [[ -n "$code" ]]; then
      args+=(--port "$code")
    fi
  done
  log "Catalogues de référence des ports…"
  python manage.py bootstrap_ports ${args[@]+"${args[@]}"}

  # Mise à niveau depuis une version qui ne déposait pas d'elle-même les actes des décisions, la notice de
  # disponibilité et le time sheet (1.2 et avant) : les documents manquants des escales en cours sont déposés, une
  # fois, sous leur auteur d'origine. Idempotent ; un échec n'empêche pas le démarrage.
  log "Documents générés des escales en cours (rattrapage après mise à niveau)…"
  python manage.py backfill_generated_documents || log "ATTENTION : rattrapage incomplet, voir ci-dessus (le service démarre quand même)."
}

command="${1:-web}"
case "$command" in
  web)
    if [[ $# -gt 0 ]]; then
      shift
    fi
    prepare_web
    drop_privileged_credentials
    log "Démarrage de gunicorn sur 0.0.0.0:8000…"
    # gthread : un client lent (téléversement ou téléchargement d'un document sur une liaison
    # mobile) n'immobilise qu'un fil d'exécution et n'est pas coupé par --timeout, qui ne surveille
    # que la vivacité du processus. --forwarded-allow-ips "*" : seul Caddy atteint le port 8000
    # (non publié sur l'hôte), ses en-têtes X-Forwarded-* sont donc pris en compte.
    exec gunicorn fluxaa.wsgi:application \
      --bind 0.0.0.0:8000 \
      --workers 3 \
      --timeout 60 \
      --worker-class gthread \
      --threads 4 \
      --worker-tmp-dir /dev/shm \
      --forwarded-allow-ips "*" \
      "$@"
    ;;
  scheduler)
    check_config scheduler
    wait_for_db
    drop_privileged_credentials
    log "Démarrage du planificateur (intervalle 60 s)…"
    exec python manage.py run_scheduler --interval 60
    ;;
  ais)
    # Écoute d'une source AIS pour un port : « ais <code port> --udp 0.0.0.0:10110 », « --tcp hôte:port »
    # ou « --aisstream » (clé FLUXAA_AISSTREAM_KEY). Voir DEPLOIEMENT.md §15.
    shift
    check_config scheduler
    wait_for_db
    drop_privileged_credentials
    log "Démarrage de l'écoute AIS…"
    exec python manage.py ais_listen --port "$@"
    ;;
  *)
    exec "$@"
    ;;
esac
