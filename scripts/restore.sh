#!/usr/bin/env bash
# FLUXAA Port — restauration d'une sauvegarde produite par scripts/backup.sh.
#
# Usage, depuis le dossier deploy/ de l'hôte :
#
#   Test de restauration trimestriel (CDC ENF-1) — NON DESTRUCTIF, le service reste en marche :
#     docker compose exec web /app/scripts/restore.sh --test /backups/fluxaa-AAAAMMJJ-HHMMSSZ
#   La sauvegarde est restaurée dans deux bases temporaires (<base>_restore_test) et un dossier
#   temporaire, entièrement vérifiée, puis tout est supprimé. Conserver la sortie du script comme
#   preuve du test (procès-verbal, voir docs/DEPLOIEMENT.md).
#
#   Restauration réelle (sinistre, changement de serveur) — REMPLACE les données actuelles :
#     docker compose stop web scheduler
#     docker compose run --rm web /app/scripts/restore.sh /backups/fluxaa-AAAAMMJJ-HHMMSSZ
#     docker compose up -d
#
# Étapes :
#   1. contrôle du manifeste SHA256SUMS et lisibilité des archives, AVANT toute modification ;
#   2. pour chaque base : suppression puis recréation de la base par le superutilisateur, puis
#      pg_restore avec le rôle propriétaire dans cette base vide ;
#   3. restauration des pièces déposées ;
#   4. vérification : chaînes de hachage (manage.py verify_journal) et empreinte SHA-256 de
#      chaque pièce référencée par la base restaurée.
#
# Pourquoi une base recréée vide plutôt que « pg_restore --clean » sur la base en place : les
# tables du registre portent des déclencheurs qui refusent DELETE et TRUNCATE (règle « aucune
# suppression », apps/core/dbguards.py) ; une base du registre ne se vide donc jamais table par
# table. On la supprime entière (DROP DATABASE, par le superutilisateur) et l'on restaure dans une
# base neuve, sans aucun objet résiduel. Les options --clean --if-exists sont conservées : elles
# sont sans effet sur une base vide.
#
# Le superutilisateur (POSTGRES_USER, « postgres » par défaut, mot de passe POSTGRES_PASSWORD)
# n'est utilisé que pour supprimer et créer les bases ; tout le contenu est restauré avec le rôle
# propriétaire (DATABASE_OWNER_URL, SECURE_DATABASE_OWNER_URL), comme à l'origine.
set -euo pipefail
umask 077

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
MEDIA_DIR="${DJANGO_MEDIA_ROOT:-$APP_DIR/media}"
SUPERUSER="${POSTGRES_USER:-postgres}"

log()  { printf '%s [restauration] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { printf '%s [restauration] ERREUR : %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Usage : restore.sh [--test] [--oui] <dossier de sauvegarde>

  --test   test de restauration NON DESTRUCTIF (trimestriel, CDC ENF-1) : restauration dans des
           bases et un dossier temporaires, vérification complète, puis suppression. Les données
           en service ne sont pas touchées ; l'application peut rester en marche.
  --oui    restauration réelle sans demande de confirmation (usage non interactif).

<dossier de sauvegarde> : chemin d'un dossier fluxaa-AAAAMMJJ-HHMMSSZ, ou son seul nom s'il se
trouve dans BACKUP_DIR (/backups par défaut).

Restauration réelle (remplace les données actuelles), depuis le dossier deploy/ :
  docker compose stop web scheduler
  docker compose run --rm web /app/scripts/restore.sh /backups/fluxaa-AAAAMMJJ-HHMMSSZ
  docker compose up -d
EOF
}

# ------------------------------------------------------------------------------------- arguments
MODE="reel"
ASSUME_YES=0
SOURCE=""
while (( $# > 0 )); do
  case "$1" in
    --test) MODE="test" ;;
    --oui) ASSUME_YES=1 ;;
    -h|--help) usage; exit 0 ;;
    -*) usage >&2; fail "option inconnue : $1" ;;
    *)
      [[ -z "$SOURCE" ]] || fail "un seul dossier de sauvegarde est attendu."
      SOURCE="$1"
      ;;
  esac
  shift
done
if [[ -z "$SOURCE" ]]; then
  usage >&2
  exit 2
fi
if [[ ! -d "$SOURCE" && -d "${BACKUP_DIR}/${SOURCE}" ]]; then
  SOURCE="${BACKUP_DIR}/${SOURCE}"
fi
[[ -d "$SOURCE" ]] || fail "dossier de sauvegarde introuvable : ${SOURCE}"
SOURCE="$(cd "$SOURCE" && pwd)"

for tool in psql pg_restore sha256sum tar python; do
  command -v "$tool" >/dev/null 2>&1 || fail "commande « ${tool} » introuvable."
done
for name in DATABASE_URL DATABASE_OWNER_URL SECURE_DATABASE_URL SECURE_DATABASE_OWNER_URL POSTGRES_PASSWORD; do
  [[ -n "${!name:-}" ]] \
    || fail "${name} n'est pas défini. Lancez le script dans un conteneur de l'application (voir l'en-tête du script)."
done

# ------------------------------------------------------------- 1. manifeste et archives (lecture seule)
log "Sauvegarde : ${SOURCE}"
for file in SHA256SUMS fluxaa.dump fluxaa_secure.dump media.tar.gz; do
  [[ -f "${SOURCE}/${file}" ]] || fail "fichier manquant dans la sauvegarde : ${file}"
done
for file in fluxaa.dump fluxaa_secure.dump media.tar.gz; do
  grep -Eq "^[0-9a-f]{64} [ *]${file}\$" "${SOURCE}/SHA256SUMS" \
    || fail "le manifeste SHA256SUMS ne couvre pas ${file} : sauvegarde incomplète."
done
log "Contrôle des empreintes SHA-256…"
( cd "$SOURCE" && sha256sum --check --strict --quiet SHA256SUMS ) \
  || fail "empreintes non conformes : sauvegarde altérée ou incomplète. Rien n'a été modifié."
log "Empreintes conformes."
for file in fluxaa.dump fluxaa_secure.dump; do
  pg_restore --list "${SOURCE}/${file}" >/dev/null || fail "archive illisible : ${file}"
done
tar --list --gzip --file "${SOURCE}/media.tar.gz" >/dev/null || fail "archive des pièces illisible : media.tar.gz"

# ------------------------------------------------------------------------------- connexions
# Décompose les URL en variables MAIN_* et SECURE_* (décodage fait par Python : un mot de passe
# contenant des caractères encodés reste correct).
parse_database_urls() {
  python - <<'PY'
import os
import shlex
from urllib.parse import parse_qs, unquote, urlparse


def parts(name):
    parsed = urlparse(os.environ.get(name, ""))
    query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
    return {
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": query.get("host") or unquote(parsed.hostname or ""),
        "PORT": str(parsed.port or 5432),
        "DB": unquote(parsed.path.lstrip("/")),
        "SSLMODE": query.get("sslmode", "prefer"),
    }


lines = []
for prefix, name in (("MAIN", "DATABASE_OWNER_URL"), ("SECURE", "SECURE_DATABASE_OWNER_URL")):
    for key, value in parts(name).items():
        lines.append(f"{prefix}_{key}={shlex.quote(value)}")
lines.append(f"MAIN_APP_ROLE={shlex.quote(parts('DATABASE_URL')['USER'])}")
lines.append(f"SECURE_APP_ROLE={shlex.quote(parts('SECURE_DATABASE_URL')['USER'])}")
print("\n".join(lines))
PY
}

# url_with_db <url> <base> : la même URL de connexion, vers une autre base.
url_with_db() {
  python - "$1" "$2" <<'PY'
import sys
from urllib.parse import quote, urlparse, urlunparse

parsed = urlparse(sys.argv[1])
print(urlunparse(parsed._replace(path="/" + quote(sys.argv[2]))))
PY
}

parsed_urls="$(parse_database_urls)" || fail "URL de base de données illisibles (voir deploy/.env)."
eval "$parsed_urls"
for name in MAIN_USER MAIN_DB MAIN_HOST SECURE_USER SECURE_DB SECURE_HOST MAIN_APP_ROLE SECURE_APP_ROLE; do
  [[ -n "${!name}" ]] || fail "URL de base de données incomplète (${name} vide) : vérifiez deploy/.env."
done
[[ "$MAIN_DB" != "$SECURE_DB" ]] || fail "la base principale et la base N4 portent le même nom (${MAIN_DB})."

# psql_super <MAIN|SECURE> <base> [options psql…] : superutilisateur, sur le serveur de la base.
psql_super() {
  local prefix="$1" database="$2"
  shift 2
  local host="${prefix}_HOST" port="${prefix}_PORT" sslmode="${prefix}_SSLMODE"
  PGPASSWORD="$POSTGRES_PASSWORD" PGSSLMODE="${!sslmode}" psql --no-psqlrc -v ON_ERROR_STOP=1 -q \
    --host "${!host}" --port "${!port}" --username "$SUPERUSER" --dbname "$database" "$@"
}

# recreate_database <MAIN|SECURE> <base> [<rôle d'exécution>] : base neuve et vide, propriété du
# rôle propriétaire, connexion réservée au rôle d'exécution (comme postgres-init/01-init.sh).
recreate_database() {
  local prefix="$1" database="$2" app_role="${3:-}"
  local owner="${prefix}_USER"
  psql_super "$prefix" postgres -v db="$database" -v owner="${!owner}" <<'SQL'
DROP DATABASE IF EXISTS :"db";
CREATE DATABASE :"db" OWNER :"owner" TEMPLATE template0;
REVOKE ALL ON DATABASE :"db" FROM PUBLIC;
SQL
  psql_super "$prefix" "$database" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SQL
  if [[ -n "$app_role" ]]; then
    psql_super "$prefix" "$database" -v db="$database" -v app="$app_role" <<'SQL'
GRANT CONNECT ON DATABASE :"db" TO :"app";
GRANT USAGE ON SCHEMA public TO :"app";
SQL
  fi
}

# restore_database <MAIN|SECURE> <archive> <base> : contenu restauré avec le rôle propriétaire.
restore_database() {
  local prefix="$1" archive="$2" database="$3"
  local host="${prefix}_HOST" port="${prefix}_PORT" user="${prefix}_USER" password="${prefix}_PASSWORD" \
        sslmode="${prefix}_SSLMODE"
  PGPASSWORD="${!password}" PGSSLMODE="${!sslmode}" pg_restore \
    --host "${!host}" --port "${!port}" --username "${!user}" --dbname "$database" \
    --clean --if-exists --single-transaction --exit-on-error "$archive"
}

# other_sessions <MAIN|SECURE> <base> : nombre de connexions d'autres clients à la base.
other_sessions() {
  psql_super "$1" postgres -At -v db="$2" <<'SQL'
SELECT count(*) FROM pg_stat_activity WHERE datname = :'db' AND pid <> pg_backend_pid();
SQL
}

drop_test_database() {
  psql_super "$1" postgres -v db="$2" <<'SQL'
DROP DATABASE IF EXISTS :"db" WITH (FORCE);
SQL
}

# ----------------------------------------------------------------------------------- cibles
if [[ "$MODE" == test ]]; then
  TARGET_MAIN_DB="${MAIN_DB}_restore_test"
  TARGET_SECURE_DB="${SECURE_DB}_restore_test"
  TARGET_MEDIA="$(mktemp -d "${TMPDIR:-/tmp}/fluxaa-restore-test.XXXXXX")"
else
  TARGET_MAIN_DB="$MAIN_DB"
  TARGET_SECURE_DB="$SECURE_DB"
  TARGET_MEDIA="$MEDIA_DIR"
fi

# STARTED : les bases cibles ont commencé d'être recréées ; RESTORED : restauration terminée.
STARTED=0
RESTORED=0
on_exit() {
  local status=$?
  trap - EXIT
  if [[ "$MODE" == test ]]; then
    log "Nettoyage : suppression des bases et du dossier temporaires…"
    if (( STARTED == 1 )); then
      drop_test_database MAIN "$TARGET_MAIN_DB" || true
      drop_test_database SECURE "$TARGET_SECURE_DB" || true
    fi
    rm -rf -- "$TARGET_MEDIA"
  elif (( status != 0 && STARTED == 1 && RESTORED == 0 )); then
    printf '%s [restauration] ATTENTION : restauration interrompue, les bases peuvent être incomplètes. ' \
      "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >&2
    printf 'Corrigez la cause puis relancez ce script (il recrée les bases) avant de redémarrer web et scheduler.\n' >&2
  fi
  exit "$status"
}
trap on_exit EXIT
trap 'exit 130' INT TERM

log "Connexion au serveur PostgreSQL (${SUPERUSER}@${MAIN_HOST}:${MAIN_PORT})…"
psql_super MAIN postgres -At -c "SELECT 1" >/dev/null \
  || fail "connexion superutilisateur impossible : vérifiez POSTGRES_PASSWORD et que le service db fonctionne."
if [[ "$SECURE_HOST:$SECURE_PORT" != "$MAIN_HOST:$MAIN_PORT" ]]; then
  psql_super SECURE postgres -At -c "SELECT 1" >/dev/null \
    || fail "connexion superutilisateur impossible au serveur de la base N4 (${SECURE_HOST}:${SECURE_PORT})."
fi

if [[ "$MODE" == reel ]]; then
  # Aucune autre session ne doit utiliser les bases : web et scheduler doivent être arrêtés.
  for pair in "MAIN:${TARGET_MAIN_DB}" "SECURE:${TARGET_SECURE_DB}"; do
    sessions="$(other_sessions "${pair%%:*}" "${pair#*:}")"
    if (( sessions > 0 )); then
      fail "${sessions} connexion(s) active(s) sur la base ${pair#*:}. Arrêtez d'abord le service : docker compose stop web scheduler, puis relancez avec docker compose run --rm web /app/scripts/restore.sh …"
    fi
  done
  if (( ASSUME_YES == 0 )); then
    [[ -t 0 ]] || fail "restauration réelle sans terminal : ajoutez --oui pour confirmer."
    printf '\nLa restauration REMPLACE le contenu des bases %s et %s par celui de la sauvegarde\n' \
      "$TARGET_MAIN_DB" "$TARGET_SECURE_DB"
    printf '%s.\nToute donnée enregistrée depuis cette sauvegarde sera perdue.\n' "$(basename "$SOURCE")"
    printf 'Tapez RESTAURER pour confirmer : '
    read -r answer || answer=""
    [[ "$answer" == "RESTAURER" ]] || fail "restauration annulée, rien n'a été modifié."
  fi
  log "Restauration RÉELLE vers ${TARGET_MAIN_DB}, ${TARGET_SECURE_DB} et ${TARGET_MEDIA}."
else
  log "TEST de restauration (non destructif) vers ${TARGET_MAIN_DB}, ${TARGET_SECURE_DB} et ${TARGET_MEDIA}."
fi

[[ -d "$TARGET_MEDIA" && -w "$TARGET_MEDIA" ]] \
  || fail "dossier des pièces absent ou inaccessible en écriture : ${TARGET_MEDIA}. Rien n'a été modifié."

# -------------------------------------------------------------------------- 2. bases de données
STARTED=1
if [[ "$MODE" == test ]]; then
  # Rôles d'exécution sans accès aux bases de test : seule la vérification s'y connecte.
  recreate_database MAIN "$TARGET_MAIN_DB"
  recreate_database SECURE "$TARGET_SECURE_DB"
else
  recreate_database MAIN "$TARGET_MAIN_DB" "$MAIN_APP_ROLE"
  recreate_database SECURE "$TARGET_SECURE_DB" "$SECURE_APP_ROLE"
fi
log "Restauration de la base principale (${TARGET_MAIN_DB})…"
restore_database MAIN "${SOURCE}/fluxaa.dump" "$TARGET_MAIN_DB"
log "Restauration de la base de sûreté N4 (${TARGET_SECURE_DB})…"
restore_database SECURE "${SOURCE}/fluxaa_secure.dump" "$TARGET_SECURE_DB"

# ------------------------------------------------------------------------------------ 3. pièces
log "Restauration des pièces déposées dans ${TARGET_MEDIA}…"
tar --extract --gzip --file "${SOURCE}/media.tar.gz" --directory "$TARGET_MEDIA" \
  --no-same-owner --no-overwrite-dir
if [[ "$MODE" == reel ]]; then
  log "Les fichiers présents dans ${TARGET_MEDIA} mais absents de la sauvegarde sont conservés (aucune suppression)."
fi
RESTORED=1

# ------------------------------------------------------------------------------ 4. vérifications
# Vérification avec le rôle propriétaire, sur les bases restaurées.
VERIFY_MAIN_URL="$(url_with_db "$DATABASE_OWNER_URL" "$TARGET_MAIN_DB")"
VERIFY_SECURE_URL="$(url_with_db "$SECURE_DATABASE_OWNER_URL" "$TARGET_SECURE_DB")"
run_on_restored() {
  env -u FLUXAA_MIGRATE DATABASE_URL="$VERIFY_MAIN_URL" SECURE_DATABASE_URL="$VERIFY_SECURE_URL" \
    DJANGO_MEDIA_ROOT="$TARGET_MEDIA" DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-fluxaa.settings}" "$@"
}

log "Vérification des chaînes de hachage (manage.py verify_journal)…"
journal_status=0
run_on_restored python manage.py verify_journal || journal_status=$?

log "Vérification des empreintes des pièces référencées…"
documents_status=0
run_on_restored python - <<'PY' || documents_status=$?
import hashlib
import sys
from pathlib import Path

import django

django.setup()

from django.conf import settings  # noqa: E402

from apps.registry.models import Document  # noqa: E402

root = Path(settings.MEDIA_ROOT)
total = missing = altered = 0
for name, expected in Document.objects.order_by("pk").values_list("file", "sha256").iterator():
    total += 1
    path = root / name
    if not path.is_file():
        missing += 1
        print(f"  manquante : {name}")
        continue
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected:
        altered += 1
        print(f"  empreinte différente : {name}")
print(f"Pièces : {total} vérifiée(s), {missing} manquante(s), {altered} altérée(s).")
sys.exit(1 if missing or altered else 0)
PY

# ------------------------------------------------------------------------------------- bilan
journal_result="conformes"
documents_result="conformes"
(( journal_status == 0 )) || journal_result="ÉCHEC (voir ci-dessus)"
(( documents_status == 0 )) || documents_result="ÉCHEC (voir ci-dessus)"
if (( journal_status == 0 && documents_status == 0 )); then
  verdict="RÉUSSI"
else
  verdict="ÉCHEC"
fi

cat <<EOF

================ FLUXAA Port — $( [[ "$MODE" == test ]] && echo "test de restauration" || echo "restauration" ) ================
Date (UTC)            : $(date -u +%Y-%m-%dT%H:%M:%SZ)
Sauvegarde            : ${SOURCE}
Empreintes (manifeste): conformes
Base principale       : restaurée dans ${TARGET_MAIN_DB}
Base de sûreté N4     : restaurée dans ${TARGET_SECURE_DB}
Pièces                : restaurées dans ${TARGET_MEDIA}
Chaînes de hachage    : ${journal_result}
Empreintes des pièces : ${documents_result}
RÉSULTAT              : ${verdict}
EOF

if [[ "$MODE" == reel && "$verdict" == "RÉUSSI" ]]; then
  cat <<'EOF'

Étape suivante, depuis le dossier deploy/ : docker compose up -d
(le démarrage du service web applique les migrations éventuelles et les droits des rôles).
EOF
elif [[ "$MODE" == reel ]]; then
  cat <<'EOF'

La sauvegarde restaurée ne passe pas les vérifications : ne redémarrez pas le service avant
analyse ; essayez une sauvegarde antérieure si nécessaire.
EOF
fi

[[ "$verdict" == "RÉUSSI" ]] || exit 1
