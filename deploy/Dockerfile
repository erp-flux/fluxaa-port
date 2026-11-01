# syntax=docker/dockerfile:1
# FLUXAA Port — image applicative, utilisée par les services « web » et « scheduler ».
# Construite depuis la racine du dépôt (deploy/docker-compose.yml : context « .. »,
# dockerfile « deploy/Dockerfile »). Les secrets ne sont jamais dans l'image : ils viennent de
# deploy/.env au démarrage (voir .dockerignore).
FROM python:3.12-slim

# Version majeure du client PostgreSQL (pg_dump, pg_restore, psql). Elle DOIT être celle du
# serveur (image postgres:16-alpine du service « db ») : pg_dump refuse de sauvegarder un serveur
# plus récent que lui, et une archive produite par un pg_dump plus récent n'est pas garantie
# restaurable sur un serveur plus ancien. Le paquet « postgresql-client » de Debian suit la version
# de la distribution (17 sous Debian 13) : on installe donc postgresql-client-${PG_MAJOR} depuis le
# dépôt officiel PostgreSQL (apt.postgresql.org). À modifier en même temps que l'image du serveur.
ARG PG_MAJOR=16

ENV DJANGO_SETTINGS_MODULE=fluxaa.settings \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Paquets système :
#   gettext           → msgfmt, nécessaire à « manage.py compilemessages » (traductions FR/EN) ;
#   postgresql-client → pg_dump / pg_restore / psql pour scripts/backup.sh et scripts/restore.sh.
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl; \
    install -d /usr/share/postgresql-common/pgdg; \
    curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
        https://www.postgresql.org/media/keys/ACCC4CF8.asc; \
    . /etc/os-release; \
    echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
        > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends gettext "postgresql-client-${PG_MAJOR}"; \
    apt-get purge -y --auto-remove curl; \
    rm -rf /var/lib/apt/lists/*

# Utilisateur d'exécution non privilégié, UID/GID fixes (10001). C'est ce propriétaire qu'il faut
# donner au dossier de sauvegardes de l'hôte monté sur /backups (voir docs/DEPLOIEMENT.md).
# Son dossier personnel (/home/fluxaa) est accessible en écriture : gunicorn y crée son socket
# de contrôle (~/.gunicorn/gunicorn.ctl).
RUN groupadd --system --gid 10001 fluxaa \
 && useradd --system --uid 10001 --gid fluxaa --create-home --home-dir /home/fluxaa \
        --shell /usr/sbin/nologin fluxaa

WORKDIR /app

# Dépendances Python d'abord : cette couche reste en cache tant que requirements.txt ne change pas.
COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY . /app

# Le code reste la propriété de root : le processus applicatif ne peut pas le modifier. Seuls sont
# accessibles en écriture à l'utilisateur fluxaa : les dossiers « locale » (compilemessages au
# démarrage), /app/staticfiles (collectstatic au démarrage), /app/media (volume des pièces
# déposées) et /backups (sauvegardes).
RUN set -eux; \
    mkdir -p /app/media /app/staticfiles /backups; \
    find /app -type d -name locale -prune -exec chown -R fluxaa:fluxaa {} +; \
    chown -R fluxaa:fluxaa /app/media /app/staticfiles /backups; \
    chmod 0755 /app/deploy/entrypoint.sh /app/scripts/backup.sh /app/scripts/restore.sh

USER fluxaa

EXPOSE 8000

ENTRYPOINT ["/app/deploy/entrypoint.sh"]
# Commande par défaut « web » : attente de la base, migrations (rôle propriétaire), droits du rôle
# d'exécution, traductions, fichiers statiques, catalogues de référence des ports, puis
#   gunicorn fluxaa.wsgi:application --bind 0.0.0.0:8000 --workers 3 --timeout 60
# (voir deploy/entrypoint.sh). « scheduler » lance la boucle des traitements périodiques ; toute
# autre commande est exécutée telle quelle (ex. : python manage.py shell).
CMD ["web"]
