#!/usr/bin/env bash
# FLUXAA Port — sauvegarde complète : base principale, base de sûreté N4, pièces déposées.
#
# À lancer dans le conteneur web, depuis le dossier deploy/ de l'hôte :
#   docker compose exec web /app/scripts/backup.sh
#   docker compose exec -T web /app/scripts/backup.sh      # depuis cron (sans terminal)
#
# Produit $BACKUP_DIR/fluxaa-AAAAMMJJ-HHMMSSZ/ (heure UTC) contenant :
#   fluxaa.dump         base principale, pg_dump au format « custom », lue avec le rôle propriétaire ;
#   fluxaa_secure.dump  base de sûreté N4, même format ; les contenus N4 y restent chiffrés ;
#   media.tar.gz        pièces déposées (volume « media ») ;
#   SHA256SUMS          empreintes SHA-256 des trois fichiers, contrôlées par scripts/restore.sh.
# Le dossier est d'abord écrit sous un nom temporaire (.fluxaa-….partial) et ne prend son nom
# définitif qu'une fois complet : un dossier fluxaa-… est toujours une sauvegarde entière.
# Les sauvegardes de plus de BACKUP_RETENTION_DAYS jours (30 par défaut) sont ensuite supprimées.
#
# Les clés ne sont PAS dans la sauvegarde : sans FLUXAA_N4_KEYS la base N4 restaurée est
# illisible, sans FLUXAA_SIGNING_KEY les sceaux ne sont plus vérifiables. Une copie protégée de
# deploy/.env doit être conservée à part (docs/DEPLOIEMENT.md, « Clés et secrets »).
#
# Variables : DATABASE_OWNER_URL et SECURE_DATABASE_OWNER_URL (obligatoires, issues de
# deploy/.env), BACKUP_DIR (défaut /backups), BACKUP_RETENTION_DAYS (défaut 30),
# DJANGO_MEDIA_ROOT (défaut : dossier media/ de l'application).
set -euo pipefail
umask 077

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-30}"
MEDIA_DIR="${DJANGO_MEDIA_ROOT:-$APP_DIR/media}"

log()  { printf '%s [sauvegarde] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { printf '%s [sauvegarde] ERREUR : %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; exit 1; }

# Forme acceptée par libpq (pg_dump) : postgres:// ou postgresql://.
libpq_url() { printf '%s' "${1/#pgsql:/postgresql:}"; }

# ------------------------------------------------------------------------------------ contrôles
[[ -n "${DATABASE_OWNER_URL:-}" ]] \
  || fail "DATABASE_OWNER_URL n'est pas défini. Lancez le script dans le conteneur web : docker compose exec web /app/scripts/backup.sh"
[[ -n "${SECURE_DATABASE_OWNER_URL:-}" ]] \
  || fail "SECURE_DATABASE_OWNER_URL n'est pas défini (voir deploy/.env.example)."
[[ "$RETENTION_DAYS" =~ ^[0-9]+$ ]] \
  || fail "BACKUP_RETENTION_DAYS doit être un nombre entier de jours (valeur actuelle : ${RETENTION_DAYS})."
RETENTION_DAYS=$((10#$RETENTION_DAYS))
(( RETENTION_DAYS >= 1 )) || fail "BACKUP_RETENTION_DAYS doit valoir au moins 1."
for tool in pg_dump pg_restore sha256sum tar; do
  command -v "$tool" >/dev/null 2>&1 || fail "commande « ${tool} » introuvable."
done
[[ -d "$BACKUP_DIR" ]] || fail "le dossier de sauvegarde ${BACKUP_DIR} n'existe pas."
[[ -w "$BACKUP_DIR" ]] \
  || fail "le dossier ${BACKUP_DIR} n'est pas accessible en écriture pour l'utilisateur $(id -un) (UID $(id -u)). Sur l'hôte : sudo chown 10001:10001 <dossier de sauvegarde>"
[[ -d "$MEDIA_DIR" ]] || fail "dossier des pièces introuvable : ${MEDIA_DIR}"

# Une seule sauvegarde à la fois (cron et lancement manuel simultanés).
if command -v flock >/dev/null 2>&1; then
  exec 9>"${BACKUP_DIR}/.backup.lock"
  flock -n 9 || fail "une autre sauvegarde est en cours (verrou ${BACKUP_DIR}/.backup.lock)."
fi

NAME="fluxaa-$(date -u +%Y%m%d-%H%M%SZ)"
FINAL="${BACKUP_DIR}/${NAME}"
WORK="${BACKUP_DIR}/.${NAME}.partial"
[[ ! -e "$FINAL" ]] || fail "${FINAL} existe déjà."
mkdir "$WORK"
# En cas d'échec, le dossier incomplet est supprimé ; après succès il a déjà été renommé.
trap 'rm -rf -- "$WORK"' EXIT

log "Début de la sauvegarde dans ${FINAL}"

# -------------------------------------------------------------------------------- bases de données
# Ordre : bases d'abord, pièces ensuite. Une pièce déposée entre les deux figure dans l'archive
# sans être référencée par la base (sans conséquence) ; l'inverse ne peut pas se produire.
dump_database() {  # dump_database <url> <fichier> <libellé>
  log "Sauvegarde de la base ${3}…"
  pg_dump --format=custom --file="$2" --dbname="$(libpq_url "$1")"
  pg_restore --list "$2" >/dev/null || fail "l'archive produite est illisible : $2"
}
dump_database "$DATABASE_OWNER_URL" "${WORK}/fluxaa.dump" "principale"
dump_database "$SECURE_DATABASE_OWNER_URL" "${WORK}/fluxaa_secure.dump" "de sûreté N4"

# ------------------------------------------------------------------------------------------ pièces
log "Archivage des pièces déposées (${MEDIA_DIR})…"
tar_status=0
tar --create --gzip --file "${WORK}/media.tar.gz" --directory "$MEDIA_DIR" . || tar_status=$?
if (( tar_status == 1 )); then
  # Code 1 de GNU tar : un fichier a changé pendant la lecture (dépôt en cours). L'archive est
  # utilisable ; le fichier concerné figurera dans la sauvegarde suivante.
  log "Avertissement : un fichier a changé pendant l'archivage ; archive conservée."
elif (( tar_status != 0 )); then
  fail "échec de l'archivage des pièces (tar, code ${tar_status})."
fi

# ---------------------------------------------------------------------------------------- manifeste
( cd "$WORK" && sha256sum fluxaa.dump fluxaa_secure.dump media.tar.gz > SHA256SUMS )
mv -- "$WORK" "$FINAL"
log "Sauvegarde terminée : ${FINAL}"
( cd "$FINAL" && du -h fluxaa.dump fluxaa_secure.dump media.tar.gz | sed 's/^/    /' )

# ---------------------------------------------------------------------------------------- rétention
log "Suppression des sauvegardes de plus de ${RETENTION_DAYS} jours dans ${BACKUP_DIR}…"
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name 'fluxaa-*' -mtime "+${RETENTION_DAYS}" \
  -print -exec rm -rf -- {} +
# Dossiers temporaires abandonnés par une sauvegarde interrompue (plus d'un jour).
find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -name '.fluxaa-*.partial' -mtime +0 \
  -exec rm -rf -- {} +

log "Terminé. Pensez à copier ${NAME} hors du serveur (voir docs/DEPLOIEMENT.md)."
