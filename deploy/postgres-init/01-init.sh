#!/usr/bin/env bash
# FLUXAA Port — initialisation de PostgreSQL.
#
# Exécuté UNE SEULE FOIS par l'image postgres, au premier démarrage (volume « pgdata » vide), en
# tant que superutilisateur « postgres ». Les démarrages suivants ne le relancent pas : changer
# ensuite un mot de passe dans deploy/.env ne modifie pas le rôle correspondant (voir
# docs/DEPLOIEMENT.md, « Changer un mot de passe de base de données »).
#
# Crée :
#   * la base principale « fluxaa » (registre opérationnel des escales) ;
#   * la base de sûreté « fluxaa_secure » (domaine N4 : gardes armés, escortes, incidents) ;
#   * trois rôles :
#       fluxaa_owner       propriétaire des deux bases et de toutes les tables. Utilisé seulement
#                          pour les migrations, l'attribution des droits (FLUXAA_MIGRATE=1) et les
#                          sauvegardes. Jamais par le service web ni par le planificateur ;
#       fluxaa_app         rôle d'exécution de la base principale. Il ne possède AUCUNE table :
#                          ses droits (SELECT, INSERT, UPDATE ; DELETE seulement sur quelques tables
#                          techniques) lui sont donnés par « manage.py apply_db_grants » après chaque
#                          migration. Règle « aucune suppression » : ni DELETE ni TRUNCATE sur le
#                          registre (CDC ENF-3.6) ;
#       fluxaa_secure_app  rôle d'exécution de la base N4, et d'elle seule. La base N4 utilise un
#                          rôle distinct pour qu'une fuite des identifiants de la base principale
#                          n'ouvre pas le domaine de sûreté (CDC EF-12.4).
#
# Le droit CONNECT est retiré à PUBLIC sur les deux bases : fluxaa_app ne peut pas se connecter à
# fluxaa_secure, ni fluxaa_secure_app à fluxaa.
#
# Mots de passe : variables FLUXAA_OWNER_PASSWORD, FLUXAA_APP_PASSWORD et
# FLUXAA_SECURE_APP_PASSWORD, transmises au service « db » par deploy/docker-compose.yml. Elles
# sont passées à psql comme variables (:'…') : aucun problème de guillemets ni d'injection.
#
# Le corps s'exécute dans un sous-shell : le script fonctionne qu'il soit exécuté (bit x) ou lu
# par l'entrypoint de l'image postgres (fichier non exécutable), sans modifier les options de ce
# dernier.
(
  set -euo pipefail

  for name in FLUXAA_OWNER_PASSWORD FLUXAA_APP_PASSWORD FLUXAA_SECURE_APP_PASSWORD; do
    if [[ -z "${!name:-}" ]]; then
      echo "[01-init] ERREUR : la variable ${name} est vide ; renseignez-la dans deploy/.env." >&2
      exit 1
    fi
  done

  echo "[01-init] Création des rôles fluxaa_owner, fluxaa_app, fluxaa_secure_app et des bases fluxaa, fluxaa_secure…"

  psql --no-psqlrc -v ON_ERROR_STOP=1 \
    --username "${POSTGRES_USER:-postgres}" --dbname "${POSTGRES_DB:-postgres}" \
    -v owner_password="$FLUXAA_OWNER_PASSWORD" \
    -v app_password="$FLUXAA_APP_PASSWORD" \
    -v secure_app_password="$FLUXAA_SECURE_APP_PASSWORD" <<'SQL'
-- Rôles : connexion autorisée, aucun attribut d'administration.
CREATE ROLE fluxaa_owner      LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'owner_password';
CREATE ROLE fluxaa_app        LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
CREATE ROLE fluxaa_secure_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'secure_app_password';

-- Les deux bases appartiennent au propriétaire : c'est lui qui exécute les migrations, donc
-- lui qui possède les tables. Les rôles d'exécution ne possèdent rien.
CREATE DATABASE fluxaa        OWNER fluxaa_owner;
CREATE DATABASE fluxaa_secure OWNER fluxaa_owner;

-- Connexion : chaque rôle d'exécution n'accède qu'à sa propre base.
REVOKE ALL ON DATABASE fluxaa        FROM PUBLIC;
REVOKE ALL ON DATABASE fluxaa_secure FROM PUBLIC;
GRANT CONNECT ON DATABASE fluxaa        TO fluxaa_app;
GRANT CONNECT ON DATABASE fluxaa_secure TO fluxaa_secure_app;

-- Schéma public : personne d'autre que le propriétaire ne peut y créer d'objet.
\connect fluxaa
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO fluxaa_app;

\connect fluxaa_secure
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO fluxaa_secure_app;
SQL

  echo "[01-init] Initialisation terminée."
)
