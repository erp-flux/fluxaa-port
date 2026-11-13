# FLUXAA Port — Guide de déploiement et d'exploitation

Ce guide s'adresse à l'administrateur système chargé d'installer et d'exploiter FLUXAA Port, le
registre opérationnel des escales de navires pétroliers, pour l'autorité portuaire de Freetown
(SLFNA) ou de Lomé (TGLFW). Il couvre l'installation, les comptes initiaux, les sauvegardes et le
test de restauration, les mises à jour, la sécurité des bases de données et des clés, la
supervision, le choix d'hébergement et le dépannage.

Sauf mention contraire, toutes les commandes `docker compose …` se lancent depuis le dossier
`deploy/` du dépôt (dans ce guide : `/srv/fluxaa-port/deploy`).

---

## 1. Architecture déployée

```
Internet ──► 80/443 ── caddy ──► web:8000 (Django + gunicorn) ──► db:5432 (PostgreSQL 16)
                                  scheduler (tâches périodiques) ──┘    ├─ base fluxaa         (registre)
                                                                        └─ base fluxaa_secure  (sûreté N4)
```

| Service     | Rôle                                                                                                                                                                                               |
|-------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `db`        | PostgreSQL 16. Deux bases : `fluxaa` (registre des escales) et `fluxaa_secure` (domaine de sûreté N4). Non exposé hors de Docker.                                                                   |
| `web`       | Application Django servie par gunicorn. À chaque démarrage : migrations, droits des rôles, traductions, fichiers statiques, catalogues de référence des ports.                                       |
| `scheduler` | Traitements périodiques toutes les 60 s : contre-signatures tacites, alertes et escalades, expiration des autorisations, résumés quotidiens, envoi des webhooks.                                    |
| `caddy`     | Frontal HTTPS : certificat Let's Encrypt obtenu et renouvelé automatiquement, en-têtes de sécurité, requêtes limitées à 30 Mo. Seul service publié (ports 80 et 443). Il remplace l'en-tête `X-Forwarded-For` reçu : l'application s'y fie pour l'adresse du client (journal d'accès, limitation des tentatives). Ne jamais publier le port 8000 de `web` sans ce frontal. |

Données persistantes :

| Emplacement                         | Contenu                                                            |
|-------------------------------------|--------------------------------------------------------------------|
| volume `fluxaa_pgdata`              | les deux bases PostgreSQL                                          |
| volume `fluxaa_media`               | pièces déposées (documents des escales)                            |
| volumes `fluxaa_caddy_data`, `fluxaa_caddy_config` | certificats et configuration de Caddy               |
| dossier de l'hôte `deploy/backups/` (ou `BACKUP_HOST_DIR`) | sauvegardes                                 |
| `deploy/.env`                       | configuration et **tous les secrets** (clés, mots de passe)        |

Fichiers du déploiement : `deploy/Dockerfile`, `deploy/entrypoint.sh`, `deploy/docker-compose.yml`,
`deploy/Caddyfile`, `deploy/postgres-init/01-init.sh`, `deploy/.env.example`,
`scripts/backup.sh`, `scripts/restore.sh`.

---

## 2. Prérequis

**Serveur**

- Linux 64 bits : serveur physique ou machine virtuelle (Ubuntu Server 22.04/24.04 LTS ou
  Debian 12/13 conviennent).
- À titre indicatif, pour un port : 2 vCPU, 4 Go de RAM, 50 Go de disque SSD. Le volume des pièces
  croît avec les documents déposés (25 Mo au plus par pièce). Prévoir un disque distinct, ou un
  montage réseau, pour les sauvegardes.
- Horloge synchronisée par NTP (`timedatectl` doit indiquer `System clock synchronized: yes`).
  L'horodatage du journal utilise l'horloge du serveur, et les codes de double authentification
  (TOTP) sont refusés si l'horloge dérive.
- Un compte d'administration nominatif avec `sudo`, accès SSH par clé.

**Logiciels**

- Docker Engine et le plugin Docker Compose v2 (commande `docker compose`, version 2.20 ou
  ultérieure). L'ancien `docker-compose` (v1) n'est pas pris en charge. Installation :
  <https://docs.docker.com/engine/install/>. Contrôle : `docker compose version`.
- Git.

**Réseau**

- Un nom de domaine (ex. `fluxaa.port-exemple.sl`) avec un enregistrement DNS **A** (et **AAAA**
  si le serveur a une adresse IPv6) pointant vers l'adresse IP publique du serveur.
- Ports entrants ouverts depuis Internet : **80/tcp** (validation Let's Encrypt et redirection
  vers HTTPS) et **443/tcp** ; **443/udp** en option (HTTP/3). Aucun autre port n'est publié.
  Si le serveur est derrière un routeur NAT, rediriger 80 et 443 vers lui.
- Sorties nécessaires : Let's Encrypt (`acme-v02.api.letsencrypt.org`) ; pendant la construction
  de l'image, Docker Hub, PyPI, `deb.debian.org` et `apt.postgresql.org` ; en fonctionnement, le
  serveur SMTP, la passerelle SMS et, si le module IA est activé, l'API d'Anthropic.

Note sur le pare-feu : Docker publie les ports 80 et 443 en écrivant directement ses règles
iptables, que `ufw` ne filtre pas. Ce n'est pas gênant ici (seuls 80 et 443 sont publiés et
doivent être ouverts) ; restreindre en revanche l'accès SSH avec `ufw` ou le pare-feu du
fournisseur.

---

## 3. Installation pas à pas

### 3.1 Récupérer le code

```bash
sudo git clone <URL du dépôt FLUXAA Port> /srv/fluxaa-port
cd /srv/fluxaa-port/deploy
```

### 3.2 Créer le fichier de configuration

```bash
cp .env.example .env
chmod 600 .env
```

`deploy/.env` contient tous les secrets de l'installation. Il n'est jamais versionné (`.gitignore`)
ni copié dans l'image (`.dockerignore`).

### 3.3 Générer les secrets

Chaque commande affiche une valeur à coller dans `.env`. Générer une valeur **distincte** pour
chaque variable.

| Variable(s)                                                                                       | Commande                                                                                  |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------|
| `DJANGO_SECRET_KEY`, puis `FLUXAA_SIGNING_KEY`                                                    | `python3 -c "import secrets; print(secrets.token_urlsafe(50))"`                           |
| `FLUXAA_N4_KEYS`                                                                                  | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |
| `POSTGRES_PASSWORD`, `FLUXAA_OWNER_PASSWORD`, `FLUXAA_APP_PASSWORD`, `FLUXAA_SECURE_APP_PASSWORD` | `python3 -c "import secrets; print(secrets.token_hex(24))"`                               |

- Si le module Python `cryptography` n'est pas installé sur la machine, cette commande produit une
  clé Fernet équivalente : `python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"`.
- Sans Python sur l'hôte : `docker run --rm python:3.12-slim python -c "…"`.
- Les mots de passe sont en hexadécimal pour pouvoir figurer tels quels dans les URL de connexion.
  Ne jamais utiliser le caractère `$` dans une valeur de `.env`.

### 3.4 Renseigner `.env`

Le fichier `.env.example` documente chaque variable. Points à vérifier :

1. **Domaine** : `DOMAIN`, `DJANGO_ALLOWED_HOSTS` (doit contenir `DOMAIN`),
   `DJANGO_CSRF_TRUSTED_ORIGINS` (`https://` + `DOMAIN`), `FLUXAA_SITE_URL` (`https://` + `DOMAIN`).
2. **Mots de passe PostgreSQL** : les quatre variables `*_PASSWORD`, puis le **même** mot de passe
   recopié dans chacune des quatre URL (`MOT_DE_PASSE_APP` → valeur de `FLUXAA_APP_PASSWORD`, etc.).
   Le conteneur `web` refuse de démarrer si une URL ne correspond pas à son mot de passe.
3. **Clés** : `DJANGO_SECRET_KEY`, `FLUXAA_SIGNING_KEY`, `FLUXAA_N4_KEYS` (section 11).
4. **Courrier électronique** : `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`,
   `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`. Les notifications et escalades en dépendent, ainsi que la
   **convocation des parties sans compte** à la déclaration de chaque escale : le lien d'accès part à l'adresse
   de courriel de l'organisation (fiche de l'organisation, paramétrage du port). Sans adresse, la convocation
   est consignée au journal (`party_link.unsent`) et l'agence remet le lien par un autre canal (onglet Parties).
5. **SMS** (escalades) : `FLUXAA_SMS_BACKEND=webhook` et la passerelle, ou `console` en attendant.
6. Laisser `FLUXAA_MFA_ENFORCED=1` et `FLUXAA_AI_ENABLED=0` sauf décision contraire du port.

Les mots de passe PostgreSQL ne sont lus qu'au **premier** démarrage de la base, pour créer les
rôles. Les changer ensuite dans `.env` ne suffit pas : voir 10.4.

### 3.5 Préparer le dossier de sauvegarde

Le conteneur s'exécute sous l'utilisateur `fluxaa` (UID/GID 10001), qui doit pouvoir écrire dans
le dossier de sauvegarde de l'hôte :

```bash
mkdir -p backups
sudo chown 10001:10001 backups
sudo chmod 700 backups
```

Pour placer les sauvegardes sur un autre disque, indiquer son chemin absolu dans
`BACKUP_HOST_DIR` (ex. `/mnt/sauvegardes/fluxaa`) et appliquer les mêmes commandes à ce dossier.

### 3.6 Construire et démarrer

```bash
docker compose up -d --build
```

Au premier démarrage :

1. `db` initialise PostgreSQL et exécute `postgres-init/01-init.sh` : création des bases
   `fluxaa` et `fluxaa_secure` et des rôles `fluxaa_owner`, `fluxaa_app`, `fluxaa_secure_app`.
2. `web` contrôle la configuration, attend la base, applique les migrations des deux bases avec
   le rôle propriétaire, attribue les droits des rôles d'exécution (`apply_db_grants`), compile
   les traductions, collecte les fichiers statiques, charge les catalogues de référence des ports
   (`bootstrap_ports`, SLFNA et TGLFW), puis lance gunicorn.
3. `scheduler` démarre lorsque `web` est déclaré en bonne santé.
4. `caddy` obtient le certificat HTTPS du domaine (quelques secondes à quelques minutes).

La commande rend la main lorsque `web` est en bonne santé (jusqu'à 3 minutes au premier démarrage).

### 3.7 Vérifier

```bash
docker compose ps                         # db et web : « healthy » ; scheduler et caddy : « running »
docker compose logs --tail=50 web         # lignes « [entrypoint] … » puis démarrage de gunicorn
docker compose logs --tail=50 caddy       # « certificate obtained successfully »
curl -fsS https://<DOMAIN>/healthz        # {"status": "ok"}
```

Ouvrir ensuite `https://<DOMAIN>/` dans un navigateur : la page de connexion s'affiche.

### 3.8 Mettre les secrets en lieu sûr

Avant toute mise en service, conserver une copie de `deploy/.env` **hors du serveur** (section
7.6). Sans elle, une sauvegarde ne peut pas être exploitée.

---

## 4. Premier compte : opérateur de plateforme

```bash
docker compose exec web python manage.py createsuperuser
```

La commande demande l'adresse e-mail (identifiant de connexion), le nom complet et le mot de passe
(12 caractères au moins).

Ce compte « opérateur de plateforme » a accès au paramétrage de tous les ports
(`https://<DOMAIN>/admin/`). Il sert à créer les organisations et les administrateurs fonctionnels
des ports, pas au travail courant. Comme tout compte qui administre d'autres comptes, il doit
enregistrer une application d'authentification (TOTP) à sa première connexion : quiconque peut
réinitialiser le second facteur d'une autre personne doit en détenir un. Le paramétrage exige une
vérification de moins de 8 heures. Lui donner un mot de passe long, propre à une personne nommée, et
le réserver aux opérations de paramétrage. La page de connexion est la même pour tous
(`/compte/connexion/`, tentatives limitées) : `/admin/login/` y renvoie.

Mot de passe perdu : `docker compose exec web python manage.py changepassword <adresse e-mail>`.
Téléphone perdu : `docker compose exec web python manage.py reset_mfa <adresse e-mail> --reason "…"`
(la personne est prévenue par courriel et enregistre une nouvelle application à sa connexion
suivante ; la réinitialisation est inscrite au journal des accès quand le compte appartient à un
port).

---

## 5. Administrateur fonctionnel du port

Les ports SLFNA (Freetown) et TGLFW (Lomé) et leurs catalogues de référence (modèles d'escale,
jalons, types de demandes et de documents, causes d'interruption, points d'arrêt) sont créés
automatiquement au démarrage. L'opérateur de plateforme crée ensuite l'administrateur fonctionnel
du port, depuis `https://<DOMAIN>/admin/` :

1. **Ports** : ouvrir le port concerné et vérifier le fuseau horaire, la langue par défaut, les
   délais et seuils, et renseigner l'**e-mail de l'autorité de sûreté** (destinataire des
   notifications nominatives d'accès aux données N4).
2. **Organisations → Ajouter** : le port, le nom de l'organisation (ex. l'autorité portuaire), les
   « rôles que cette organisation peut tenir » (ex. CAP, APO, DIR), l'e-mail et le téléphone
   utilisés pour les escalades.
3. **Utilisateurs → Ajouter** : adresse e-mail, nom complet, organisation, « rôles que
   l'utilisateur peut exercer » (parmi ceux de l'organisation ; DIR pour un responsable de la
   direction du port, par exemple), langue, mot de passe. Enregistrer, puis dans la fiche cocher
   **« administrateur fonctionnel du port »** et enregistrer de nouveau. Cet utilisateur accède
   alors au paramétrage, limité à son seul port.
4. Transmettre l'adresse de connexion à l'intéressé. Administrateur fonctionnel — ou titulaire des
   rôles CAP, APO ou SUR —, il enrôle une application d'authentification (TOTP) à sa première
   connexion.

Téléphone perdu d'un utilisateur : l'administrateur fonctionnel décoche « double authentification
activée » dans sa fiche ; la personne est prévenue par courriel et enregistre une nouvelle application
à sa connexion suivante. Toute modification d'un compte par un administrateur (rôles, activation, mot
de passe, second facteur) est inscrite au journal des accès et signalée par courriel à la personne.

L'administrateur fonctionnel crée ensuite les organisations et utilisateurs de son port, désigne
les **parties par défaut** (organisation tenant par défaut les rôles CAP, APO, ADM, SUR, SVC sur
chaque escale) et fait évoluer les modèles et listes de référence, sans livraison de code.

Le paramétrage ne permet de supprimer que les parties par défaut et les tâches d'une version de
modèle encore en brouillon. Un port, une organisation ou un utilisateur qui ne sert plus se
**désactive** (case « actif »).

---

## 6. Données de démonstration (facultatif)

```bash
docker compose exec web python manage.py load_demo --port SLFNA
docker compose exec web python manage.py load_demo --port TGLFW
```

La commande crée des organisations fictives (suffixées « (démo) »), un utilisateur par rôle
(`<rôle>.<port>@demo.fluxaa.test`, ex. `age.slfna@demo.fluxaa.test`) et quatre escales à des
stades différents (un déchargement en cours, un chargement accepté, une paire STS déclarée). Elle affiche le mot de passe commun et les secrets TOTP des rôles décideurs, à
ajouter dans une application d'authentification. L'utilisateur `dir` est administrateur
fonctionnel du port. Options : `--password <mot de passe>`, `--domain <domaine des adresses>`,
`--no-calls` (sans escales), `--history N` (N escales closes sur l'année écoulée, 8 par défaut, pour les
statistiques), `--refresh-ais` (réémet seulement l'image AIS de démonstration : le tableau AIS ne montre que
les positions des 24 dernières heures ; le lanceur Windows le fait à chaque démarrage).

**Ne jamais charger ces données sur une installation de production** : en application de la règle
« aucune suppression », elles ne pourront plus être effacées. Réserver la démonstration et la
formation à une installation distincte.

### 6.1 Installation locale de démonstration sur un poste Windows

Pour une démonstration ou une formation sur un simple PC, sans serveur ni nom de domaine, le dépôt
contient des lanceurs à double-cliquer (racine du dossier), qui s'appuient sur Docker Desktop :

| Fichier | Effet |
|---|---|
| `DEMARRER.cmd` | Première fois : crée `deploy/.env` (`DOMAIN=localhost`, secrets générés, courriels écrits dans le journal, `DJANGO_HSTS_SECONDS=0`), construit l'image, démarre les services avec `docker-compose.local.yml` (frontal `Caddyfile.local` : certificat de l'autorité locale de Caddy, sans en-tête HSTS), charge les données de démonstration des deux ports, fait reconnaître le certificat local par Windows (magasin de l'utilisateur, confirmation demandée), écrit `COMPTES-DEMO.txt` (comptes, clés TOTP, et la ligne `LIEN` : l'accès sans compte du laboratoire indépendant convoqué sur l'escale STS de démonstration) et ouvre `https://localhost/`. Si les ports 443/80 sont occupés, il publie 8443/8080 (`deploy/docker-compose.ports.yml`). Les fois suivantes : démarrage et ouverture du navigateur. |
| `CODES-DEMO.cmd` | Affiche les codes TOTP courants des comptes de démonstration qui décident, à partir des clés de `COMPTES-DEMO.txt` (remplace une application d'authentification, pour la démonstration seulement). |
| `ARRETER.cmd` | `docker compose down` : les volumes (bases, documents) sont conservés. |
| `REINITIALISER-DEMO.cmd` | Après confirmation (taper `EFFACER`) : `docker compose down --volumes`, puis suppression de `deploy/.env`, de `docker-compose.ports.yml` et de `COMPTES-DEMO.txt`. |

Ces lanceurs refusent d'agir sur une configuration dont `DOMAIN` n'est pas `localhost`. L'équivalent
en ligne de commande, sur tout système : `docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build`
depuis `deploy/`, avec un `.env` dont `DOMAIN=localhost`. `COMPTES-DEMO.txt` et `deploy/.env` contiennent
des secrets ; ils sont exclus de l'image et du dépôt. Une installation locale n'est pas une
préproduction : le test d'intrusion et les vérifications de la section 3.7 se font sur la pile réelle.

---

## 7. Sauvegardes

### 7.1 Contenu

`scripts/backup.sh` crée un dossier `fluxaa-AAAAMMJJ-HHMMSSZ` (heure UTC) :

| Fichier              | Contenu                                                                                     |
|----------------------|---------------------------------------------------------------------------------------------|
| `fluxaa.dump`        | base principale (`pg_dump`, format « custom »), lue avec le rôle propriétaire               |
| `fluxaa_secure.dump` | base N4 ; demandes, décisions et pièces N4 y restent chiffrées par `FLUXAA_N4_KEYS`          |
| `media.tar.gz`       | pièces déposées                                                                             |
| `SHA256SUMS`         | empreintes des trois fichiers, contrôlées avant toute restauration                          |

Le dossier n'apparaît sous ce nom qu'une fois complet. Les sauvegardes de plus de
`BACKUP_RETENTION_DAYS` jours (30 par défaut) sont supprimées après chaque sauvegarde réussie.

La base principale est en clair dans la sauvegarde, et les métadonnées N4 (références, navires,
nature et statut des demandes, dates) aussi. Les sauvegardes sont donc aussi sensibles que le
serveur lui-même.

### 7.2 Sauvegarde manuelle

```bash
docker compose exec web /app/scripts/backup.sh
```

La sauvegarde se fait à chaud, sans interrompre le service.

### 7.3 Sauvegarde quotidienne (cron de l'hôte)

`sudo crontab -e`, puis :

```cron
15 2 * * * cd /srv/fluxaa-port/deploy && docker compose exec -T web /app/scripts/backup.sh >> /var/log/fluxaa-backup.log 2>&1
```

`-T` est indispensable sous cron (pas de terminal). Contrôler régulièrement
`/var/log/fluxaa-backup.log` (section 12).

### 7.4 Copie hors du serveur

Une sauvegarde restée sur le serveur ne protège ni d'une panne de disque, ni d'un incendie, ni
d'une compromission. Copier chaque jour la dernière sauvegarde vers un autre site, par exemple :

```bash
rsync -a --chmod=D700,F600 /srv/fluxaa-port/deploy/backups/ sauvegarde@serveur-distant:/sauvegardes/fluxaa/
```

Pour un support amovible ou un stockage externe, chiffrer la copie :

```bash
tar -C /srv/fluxaa-port/deploy/backups -cf - fluxaa-AAAAMMJJ-HHMMSSZ \
  | gpg --symmetric --cipher-algo AES256 -o fluxaa-AAAAMMJJ-HHMMSSZ.tar.gpg
```

La rétention de 30 jours ne s'applique qu'aux copies locales ; la politique de conservation des
copies hors site relève du port (la durée de conservation réglementaire des données du registre
est paramétrée par port, 10 ans par défaut).

### 7.5 Ce que la sauvegarde ne contient pas

- Les **clés et mots de passe** (`deploy/.env`), volontairement : voir 7.6.
- Les certificats HTTPS : Caddy les obtient de nouveau automatiquement.
- L'image Docker : elle se reconstruit depuis le dépôt.

### 7.6 Clés et secrets

Conserver au moins deux copies de `deploy/.env`, séparées des sauvegardes de données, par exemple
dans le gestionnaire de secrets de l'autorité portuaire et sur un support chiffré déposé au coffre
du responsable de la sûreté. Mettre ces copies à jour à chaque rotation de clé N4.

Sans `FLUXAA_N4_KEYS`, la base N4 restaurée est illisible. Sans `FLUXAA_SIGNING_KEY`, les sceaux
(signatures, jalons, autorisations, horodatages, exports) ne sont plus vérifiables et tous les
utilisateurs doivent réenrôler leur double authentification.

---

## 8. Test de restauration trimestriel (CDC ENF-1)

Le cahier des charges impose un test de restauration **chaque trimestre**. Le mode `--test` de
`scripts/restore.sh` le réalise sans toucher aux données en service, l'application restant en
marche.

### 8.1 Procédure

Choisir une sauvegarde récente, de préférence la copie hors site rapatriée dans le dossier de
sauvegarde, puis, en heure creuse :

```bash
ls backups/
docker compose exec -T web /app/scripts/restore.sh --test /backups/fluxaa-AAAAMMJJ-HHMMSSZ \
  2>&1 | tee ~/pv-restauration-$(date +%Y%m%d).txt
```

Le script :

1. contrôle les empreintes `SHA256SUMS` et la lisibilité des archives ;
2. restaure les deux bases dans des bases temporaires `fluxaa_restore_test` et
   `fluxaa_secure_restore_test`, recréées vides, et les pièces dans un dossier temporaire ;
3. recalcule les chaînes de hachage du journal, de l'audit des accès et du journal d'accès N4
   (`manage.py verify_journal`) ;
4. recalcule l'empreinte SHA-256 de chaque pièce référencée par la base restaurée ;
5. supprime les bases et le dossier temporaires, et affiche le bilan (`RÉSULTAT : RÉUSSI` ou
   `ÉCHEC`). Le code de sortie est 0 en cas de réussite.

### 8.2 Procès-verbal

Archiver le fichier `pv-restauration-AAAAMMJJ.txt` avec : date, sauvegarde testée, nom de
l'opérateur, résultat, anomalies et actions correctives. En cas d'`ÉCHEC`, ne pas attendre le
trimestre suivant : identifier la cause (sauvegarde incomplète, pièce manquante, chaîne rompue) et
traiter (section 14).

Une fois par an, il est recommandé de faire en plus une restauration complète sur une **machine
distincte**, à partir de la copie hors site et de la copie de secours de `.env` (8.4). Ce test
vérifie aussi que les clés conservées hors du serveur sont les bonnes.

### 8.3 Restauration réelle (sinistre, retour arrière)

La restauration réelle **remplace** le contenu des deux bases : tout ce qui a été enregistré depuis
la sauvegarde est perdu. Les pièces présentes sur le disque mais absentes de la sauvegarde sont
conservées.

```bash
docker compose stop web scheduler
docker compose run --rm web /app/scripts/restore.sh /backups/fluxaa-AAAAMMJJ-HHMMSSZ
#   → taper RESTAURER pour confirmer (ou ajouter --oui en mode non interactif)
docker compose up -d
```

Les tables du registre refusent `DELETE` et `TRUNCATE` (déclencheurs « aucune suppression »). Le
script ne vide donc jamais une base table par table : il la supprime entière et la recrée vide en
superutilisateur, puis y restaure la sauvegarde avec le rôle propriétaire. Il refuse de démarrer
tant qu'une session (service `web` ou `scheduler`) est connectée à une base cible. Au redémarrage,
`web` applique les migrations éventuelles et les droits des rôles.

Si la vérification finale échoue, ne pas redémarrer le service avant analyse ; essayer une
sauvegarde antérieure.

### 8.4 Reconstruction sur un nouveau serveur

1. Installer le serveur (sections 2 et 3.1), puis copier dans `deploy/` le fichier `.env`
   **d'origine** (mêmes clés et mêmes mots de passe).
2. Préparer le dossier de sauvegarde (3.5) et y copier le dossier `fluxaa-…` à restaurer (vérifier
   son propriétaire : `sudo chown -R 10001:10001 backups`).
3. Construire l'image et démarrer la base : `docker compose build`, puis `docker compose up -d db`.
4. Restaurer : `docker compose run --rm web /app/scripts/restore.sh --oui /backups/fluxaa-…`.
5. Démarrer : `docker compose up -d`, puis faire pointer le DNS vers le nouveau serveur.

---

## 9. Mises à jour

### 9.1 Mise à jour de l'application

```bash
cd /srv/fluxaa-port/deploy
docker compose exec -T web /app/scripts/backup.sh      # sauvegarde préalable, obligatoire
cd .. && git pull && cd deploy
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 web
```

Les migrations, les droits des rôles, les traductions, les fichiers statiques et les catalogues de
référence sont appliqués automatiquement au démarrage de `web`. Le chargement des catalogues ne
remplace jamais ce que l'administrateur du port a modifié.

Le démarrage exécute aussi `manage.py backfill_generated_documents` : sur une installation qui
tournait avec une version qui ne déposait pas d'elle-même les documents générés (1.2 et avant), les
escales en cours reçoivent, une seule fois, l'acte écrit de chaque décision déjà prise, la notice de
disponibilité d'une NOR déjà remise et le time sheet d'un rapport des faits déjà produit — sous le
rôle et l'organisation de l'auteur de l'acte d'origine, journalisés comme tout document généré. Les
escales closes, archivées, annulées ou rejetées ne sont pas touchées (leur dossier est figé). La
commande est idempotente ; `--dry-run` liste ce qu'elle déposerait, `--port <code>` la limite à un
port. Un échec sur un document n'empêche ni les autres rattrapages ni le démarrage (message
`ATTENTION` dans les journaux de `web`).

Mise à niveau vers la **version 1.4** : deux migrations (`registry.0014`, `registry.0015`) créent les tables du contrôle des pertes et de la liste de contrôle (relevés de citernes et leurs validations, feuilles du journal de pompage, listes de contrôle, réponses et signatures, accès aux rapports), posent leurs déclencheurs (append-only, aucune suppression) et appliquent aux ports déjà installés les valeurs du catalogue qu'ils tiennent encore : lecteurs par défaut des rapports, lecteurs limités du certificat de qualité, time sheet émis par le terminal et le navire, type `PUMPING_LOG`, co-rôle agence sur la tâche M0:03 des escales non encore déclarées. Ce que l'administrateur du port a modifié est conservé. Aucune variable d'environnement nouvelle ; les droits des rôles de base couvrent les nouvelles tables (`apply_db_grants`, exécuté au démarrage). Les escales en cours gardent leur journal de pompage : les relevés antérieurs restent lisibles, sans feuille ni bord ; les nouvelles feuilles s'ouvrent depuis l'onglet Mesures.

Mise à niveau vers la **version 1.5** : trois migrations. `core.0007` ajoute aux ports la validité par défaut et maximale des annonces et le réglage du tableau des escales, et aux postes leurs limites d'acceptation et leurs natures de cargaison (vides : le port les renseigne). `registry.0016` ajoute la nature de cargaison et le rôle STS de l'escale, sa validité (`validity_days`, `valid_until`, `expired_at`, `renewed_from`), le statut `EXPIRED`, l'accès des parties (`access`, `scopes`), les feux verts et les documents demandés sur les tâches, le type et les caractéristiques des navires, les natures de cargaison des gabarits et de leurs tâches, les nouvelles natures de mesure et le référentiel des listes de contrôle. `registry.0017` **publie pour chaque port une nouvelle version du gabarit M0** (tâches 09b, 09c, 09d, 31b ; 09 marquée feu vert ; 29 et 31 réservées au vrac liquide), ajoute les gabarits MB1, MB2, MC1, MG1, MR1, MX1, les jalons, les 18 types de document et les points d'arrêt du catalogue cargo, et marque feu vert les tâches M0:09 des escales en cours. **Les escales en cours gardent leur version de gabarit** : elles n'ont ni validité (l'encart le dit : *Aucune validité n'a été fixée pour cette annonce*), ni feux verts de la base navale, du terminal ou du mandant — les points d'arrêt ne les leur demandent pas, puisque la tâche n'existe pas sur l'escale ; leurs parties ont toutes l'accès complet ; leur nature de cargaison est *vrac liquide*. Les escales annoncées après la mise à niveau portent tout. L'administrateur vérifie après démarrage, dans *Paramétrage › Ports*, la validité par défaut (15 jours) et maximale (90 jours) et, dans *Postes / zones*, renseigne les limites d'acceptation que la grille de vetting lira.

Mise à niveau vers la **version 1.6** : une migration, `registry.0018`, qui ajoute la fiche d'intention des gabarits (`CallTemplate.intake_schema`) et les réponses de l'annonce (`PortCall.operation_details`), puis **installe la fiche livrée sur les gabarits de chaque port qui n'en ont pas** (M1 à M9, MA3, MB1, MB2, MC1, MG1, MR1, MX1) ; un port qui a déjà adapté une fiche la garde. Aucune variable nouvelle ; les escales en cours ne changent pas (leurs réponses sont vides, l'aperçu ne montre pas de bloc *Déclaré à l'annonce*).

Installation locale de démonstration (`DEMARRER.cmd`) : les données de démonstration existantes
sont conservées et mises à niveau de la même façon ; le lanceur signale le changement de version
(`deploy\windows\version-installee.txt`) et rappelle que `REINITIALISER-DEMO.cmd` puis
`DEMARRER.cmd` rechargent des escales neuves, qui montrent toutes les nouveautés.

Retour arrière : les migrations de base de données ne s'annulent pas automatiquement. Revenir à la
version précédente du code (`git checkout <version>`) **et** restaurer la sauvegarde prise juste
avant la mise à jour (8.3).

### 9.2 Mises à jour de sécurité des images

Une fois par mois, ou à la publication d'un correctif :

```bash
docker compose pull db caddy           # correctifs PostgreSQL 16.x et Caddy 2.x
docker compose build --pull            # image applicative reconstruite sur la dernière python:3.12-slim
docker compose up -d
```

### 9.3 Changement de version majeure de PostgreSQL

Le passage de PostgreSQL 16 à une version majeure supérieure n'est **pas** automatique : les
fichiers de données ne sont pas compatibles d'une version majeure à l'autre. Procédure, à répéter
d'abord sur une machine de test :

1. sauvegarde (7.2) puis test de cette sauvegarde (8.1) ;
2. `docker compose down` ;
3. dans `docker-compose.yml`, changer l'image `postgres:16-alpine` ; dans `deploy/Dockerfile`,
   changer `ARG PG_MAJOR=16` pour la même version (le client `pg_dump`/`pg_restore` doit avoir la
   version majeure du serveur) ;
4. mettre de côté l'ancien volume au lieu de le supprimer :
   `docker volume create fluxaa_pgdata_pg16`, puis copier son contenu
   (`docker run --rm -v fluxaa_pgdata:/src -v fluxaa_pgdata_pg16:/dst alpine cp -a /src/. /dst/`),
   puis `docker volume rm fluxaa_pgdata` ;
5. `docker compose build`, `docker compose up -d db` (la nouvelle base est initialisée et les rôles
   créés), puis restauration réelle (8.4, étapes 4 et 5).

---

## 10. Rôles de base de données et règle « aucune suppression »

### 10.1 Les rôles

| Rôle                | Base(s)                     | Droits                                                                                                                                                                        | Utilisé par                                                    |
|---------------------|-----------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------|
| `postgres`          | toutes                      | superutilisateur                                                                                                                                                              | initialisation (01-init.sh), restauration                      |
| `fluxaa_owner`      | `fluxaa`, `fluxaa_secure`   | propriétaire des bases et de toutes les tables                                                                                                                                | migrations et droits au démarrage de `web`, sauvegardes        |
| `fluxaa_app`        | `fluxaa` seulement          | `SELECT`, `INSERT`, `UPDATE` ; aucun `DELETE` ni `TRUNCATE` sur le registre ; pas d'`UPDATE` sur les tables en ajout seul ; `DELETE` limité aux sessions, jetons d'API et quelques tables de paramétrage | service `web` et `scheduler`, en permanence                    |
| `fluxaa_secure_app` | `fluxaa_secure` seulement   | mêmes principes sur la base N4                                                                                                                                                | service `web` et `scheduler`, pour le domaine N4               |

Le droit de connexion est retiré à `PUBLIC` sur les deux bases : `fluxaa_app` ne peut pas se
connecter à `fluxaa_secure`, ni `fluxaa_secure_app` à `fluxaa`.

### 10.2 Pourquoi deux rôles par base

Le registre est une preuve : un enregistrement ne se supprime pas, il se rectifie par un nouvel
enregistrement (CDC ENF-3.6). Deux protections indépendantes l'imposent :

1. **Les droits** : le rôle avec lequel l'application tourne n'a aucun droit de suppression. Une
   faille applicative, une injection SQL ou une fuite des identifiants d'exécution ne permet donc
   pas d'effacer le registre. Les droits sont recalculés à chaque démarrage de `web`
   (`manage.py apply_db_grants`).
2. **Les déclencheurs** : sur les tables du registre, des déclencheurs PostgreSQL refusent
   `DELETE` et `TRUNCATE` (et `UPDATE` sur les tables en ajout seul : journal, signatures, mesures,
   messages…), y compris pour le propriétaire. Toute altération faite en dehors de l'application
   rompt en outre les chaînes de hachage, ce que détecte `verify_journal`.

Le propriétaire pourrait retirer ces déclencheurs : ses identifiants ne servent donc qu'au
démarrage (migrations, droits) et aux sauvegardes. Le point d'entrée les retire de l'environnement
des processus `gunicorn` et `scheduler` avant de les lancer. Ils restent lisibles dans
`deploy/.env` par quiconque est administrateur de l'hôte : l'accès au serveur doit donc être
limité à des comptes nominatifs.

### 10.3 Vérifier les protections

```bash
# Droits du rôle d'exécution sur une table du registre :
docker compose exec db psql -U postgres -d fluxaa -c '\dp registry_portcall'
# Suppression tentée avec le rôle d'exécution → « permission denied for table registry_portcall » :
docker compose exec db psql -U postgres -d fluxaa -c 'SET ROLE fluxaa_app; DELETE FROM registry_portcall;'
# Suppression tentée par le propriétaire → « FLUXAA registry: DELETE on registry_portcall is forbidden »
# (dès que la table contient au moins une escale) :
docker compose exec db psql -U postgres -d fluxaa -c 'SET ROLE fluxaa_owner; DELETE FROM registry_portcall;'
# Relevés du contrôle des pertes (1.4) : modification refusée par le déclencheur, même par le propriétaire
docker compose exec db psql -U postgres -d fluxaa -c 'SET ROLE fluxaa_owner; UPDATE registry_tankreading SET level_mm = 0;'
# Intégrité des chaînes de hachage :
docker compose exec web python manage.py verify_journal
```

### 10.4 Changer un mot de passe de base de données

Le script d'initialisation ne s'exécute qu'une fois. Pour changer, par exemple, le mot de passe
de `fluxaa_app` :

```bash
docker compose exec db psql -U postgres -c '\password fluxaa_app'   # saisie masquée
```

puis reporter le nouveau mot de passe dans `FLUXAA_APP_PASSWORD` **et** dans `DATABASE_URL`, et
appliquer : `docker compose up -d` (les conteneurs `web` et `scheduler` sont recréés avec la
nouvelle configuration). Même principe pour `fluxaa_owner` (deux URL), `fluxaa_secure_app` et
`postgres`. Mettre à jour la copie de secours de `.env`.

---

## 11. Base de sûreté N4 et clés

### 11.1 Séparation du domaine N4

Les données de sûreté (gardes armés, escortes, plans et incidents de sûreté) sont séparées du
registre à trois niveaux :

- une **base distincte** (`fluxaa_secure`), sans aucun lien avec la base principale ;
- un **rôle d'exécution distinct** (`fluxaa_secure_app`) : une fuite des identifiants de la base
  principale n'ouvre pas le domaine de sûreté ;
- des **clés de chiffrement distinctes** (`FLUXAA_N4_KEYS`, Fernet) : le contenu des demandes, les
  décisions et les pièces jointes N4 sont chiffrés dans la base. Les métadonnées (référence, escale,
  navire, nature, statut, dates, auteurs) ne le sont pas.

Chaque accès aux données N4 est inscrit nominativement dans un journal chaîné, et les accès par un
rôle autre que SUR sont notifiés à l'autorité de sûreté du port. Les données N4 ne sont jamais
exportées, affichées sur un tableau de bord ni transmises au module IA.

### 11.2 Rotation des clés N4

`FLUXAA_N4_KEYS` est une liste séparée par des virgules, la plus récente en premier : la première
clé chiffre les nouvelles données, toutes les clés de la liste déchiffrent.

1. Générer une nouvelle clé (3.3).
2. La placer **en tête** de la liste, en conservant les anciennes après elle :
   `FLUXAA_N4_KEYS=<nouvelle clé>,<clé précédente>`
3. Appliquer : `docker compose up -d`.
4. Vérifier qu'un utilisateur SUR consulte un dossier N4 ancien et en crée un nouveau.
5. Mettre à jour les copies de secours de `.env` (7.6).

**Ne jamais retirer une ancienne clé** : les données chiffrées avec elle resteraient illisibles,
et les pièces jointes N4, en ajout seul, ne peuvent pas être rechiffrées. La rotation protège les
données futures ; en cas de compromission d'une clé, les données déjà chiffrées avec elle doivent
être considérées comme exposées.

Faire une rotation en cas de soupçon de compromission, au départ d'une personne ayant eu accès aux
clés, ou selon la périodicité fixée par la politique de sûreté du port.

### 11.3 Autres clés

| Clé                  | Peut-elle changer ?                                                                                                                                                     |
|----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `DJANGO_SECRET_KEY`  | Oui. Tous les utilisateurs sont déconnectés ; les liens de réinitialisation de mot de passe en cours deviennent invalides.                                               |
| `FLUXAA_SIGNING_KEY` | **Non.** Elle scelle signatures, jalons, autorisations, horodatages et exports, et chiffre les secrets de double authentification. La changer rend les sceaux existants invérifiables et oblige chaque utilisateur à réenrôler son application TOTP. |
| `FLUXAA_N4_KEYS`     | Par ajout en tête uniquement (11.2).                                                                                                                                      |

---

## 12. Supervision

### 12.1 Point de santé `/healthz`

`https://<DOMAIN>/healthz` répond `200 {"status": "ok"}` lorsque l'application atteint la base
principale, `503 {"status": "error"}` sinon. Il est accessible sans authentification et ne divulgue
rien d'autre. Le configurer dans l'outil de supervision du port (contrôle toutes les 1 à 5 minutes,
alerte après deux échecs) :

```bash
curl -fsS --max-time 10 https://<DOMAIN>/healthz
```

Le même point sert au contrôle de santé Docker du conteneur `web`.

### 12.2 État des conteneurs et journaux

```bash
docker compose ps                          # état et santé de chaque service
docker compose logs -f web                 # application (erreurs Django, gunicorn)
docker compose logs -f scheduler           # une ligne « scheduler tick: {…} » par minute
docker compose logs -f caddy               # certificats, erreurs de proxy
docker compose logs -f db                  # PostgreSQL
```

Points d'attention : `Scheduler step … failed` (une étape périodique échoue), `Traceback` dans
`web`, erreurs de certificat dans `caddy`, `FATAL` dans `db`, `attempt limit reached` dans `web`
(série de mots de passe, de codes de double authentification ou de codes capitaine erronés : les
tentatives sont suspendues quinze minutes pour ce compte ou cette adresse ; une répétition signale
une tentative d'intrusion). Les journaux Docker sont plafonnés à
5 × 10 Mo par conteneur. Aucun journal d'accès HTTP n'est tenu : certaines adresses contiennent un
jeton d'accès (liens capitaine `/bord/…`).

### 12.3 Contrôles réguliers

| Fréquence      | Contrôle                                                                                                                                           |
|----------------|----------------------------------------------------------------------------------------------------------------------------------------------------|
| continu        | `/healthz` (12.1)                                                                                                                                  |
| quotidien      | sauvegarde de moins de 24 h : `find /srv/fluxaa-port/deploy/backups -maxdepth 1 -name 'fluxaa-*' -mtime -1 \| grep -q . \|\| echo ALERTE` ; copie hors site faite |
| quotidien      | espace disque : `df -h` et `docker system df -v` (alerte à 80 %)                                                                                  |
| hebdomadaire   | intégrité du registre : `docker compose exec -T web python manage.py verify_journal` (code de sortie non nul = alerte, section 14)                |
| mensuel        | mises à jour de sécurité des images (9.2)                                                                                                          |
| trimestriel    | test de restauration et procès-verbal (section 8)                                                                                                  |
| annuel         | restauration complète sur une machine distincte avec la copie de secours des clés (8.2)                                                            |

---

## 13. Hébergement en Sierra Leone et au Togo

Le lieu d'hébergement des données est une **décision du port** (point ouvert O05 du cahier des
charges). La pile technique est identique dans tous les cas : rien dans ce déploiement ne dépend
d'un fournisseur.

### 13.1 Sur site, à l'autorité portuaire

- **Avantages** : données sur le territoire national et sous le contrôle direct du port ; accès
  local maintenu en cas de coupure des liaisons internationales.
- **Exigences** : salle technique climatisée et à accès contrôlé ; onduleur et groupe électrogène ;
  si possible deux accès Internet d'opérateurs différents ; adresse IP publique fixe ; pare-feu
  laissant passer 80 et 443 ; compétences d'administration disponibles ; copie des sauvegardes sur
  un **autre site**.
- Les agences maritimes, terminaux, capitaines, armateurs et affréteurs, souvent à l'extérieur du
  port voire à l'étranger, accèdent au registre par Internet : le serveur doit être joignable depuis
  Internet. Une installation accessible seulement depuis le réseau interne limite l'usage
  multipartite du registre.

**Sans accès entrant depuis Internet** (intranet), Let's Encrypt ne peut pas délivrer de
certificat. Deux possibilités :

- certificat de l'infrastructure de clés du port ou de l'État : ajouter au service `caddy` le
  volume `- ./certs:/certs:ro`, puis dans le bloc du site du `Caddyfile` :
  `tls /certs/fullchain.pem /certs/privkey.pem` ;
- autorité interne de Caddy : ajouter `tls internal` dans le bloc du site, puis installer sur les
  postes clients le certificat racine obtenu par
  `docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./fluxaa-racine.crt`.

### 13.2 Machine virtuelle chez un fournisseur cloud

- **Avantages** : disponibilité électrique et réseau, bande passante, instantanés de disque,
  mise en service rapide.
- **Points de vigilance** : localisation des données hors du territoire national (cadre juridique
  à examiner par le port) ; dépendance aux liaisons internationales, y compris pour les utilisateurs
  locaux ; maîtrise des accès administrateur du fournisseur. Choisir la région la plus proche
  disponible et vérifier la latence depuis le port.
- Répartiteur de charge du fournisseur placé devant le serveur : en mode TCP (transmission sans
  déchiffrement), aucune modification n'est nécessaire. S'il termine lui-même le TLS et transmet
  en HTTP, adapter le `Caddyfile` : adresse du site en `http://{$DOMAIN}` (sinon Caddy redirige
  vers HTTPS) et adresse du répartiteur déclarée dans les options globales, pour que l'en-tête
  `X-Forwarded-Proto: https` qu'il envoie soit conservé (sinon boucle de redirection) :

  ```
  {
  	servers {
  		trusted_proxies static <plage d'adresses du répartiteur>
  	}
  }
  ```

### 13.3 Solutions mixtes

- Production sur site et copies chiffrées des sauvegardes chez un fournisseur (ou dans un autre
  bâtiment public) ;
- production chez un fournisseur et copie des sauvegardes conservée au port, qui garde ainsi une
  copie souveraine et exploitable de ses données (avec la copie de secours des clés, 7.6).

### 13.4 Une plateforme ou une instance par pays

La plateforme est multi-port : Freetown et Lomé peuvent partager une même installation, leurs
données restant cloisonnées. Si la décision O05 impose une instance par pays, déployer une pile
par pays et limiter le catalogue chargé au démarrage : `FLUXAA_BOOTSTRAP_PORTS=SLFNA` ou
`FLUXAA_BOOTSTRAP_PORTS=TGLFW` dans `.env`.

### 13.5 Éléments à trancher pour O05

Lieu de stockage des données et des sauvegardes ; administrateur de l'infrastructure ; détenteur
des clés N4 et des copies de secours ; cadre juridique applicable (protection des données
personnelles, sûreté portuaire, archives) ; activation ou non du module IA, dont les textes sont
alors envoyés à l'API d'Anthropic (activation : `FLUXAA_AI_ENABLED=1`, `ANTHROPIC_API_KEY` et
`FLUXAA_AI_PROVIDER_AGREEMENT` dans `.env`, puis, port par port et par l'exploitant seulement, la case
« assistance IA activée » et la référence de l'accord du port — voir [PARAMETRAGE.md](PARAMETRAGE.md) §10) ;
réversibilité. Pour la réversibilité, l'export complet d'un
port s'obtient par :

```bash
docker compose exec web python manage.py export_port SLFNA /backups/export-SLFNA-$(date +%Y%m%d).zip
```

Le port peut en vérifier l'intégrité sans la plateforme, avec le seul Python standard :
`python3 scripts/verifier_export.py export-SLFNA-AAAAMMJJ.zip --key "<FLUXAA_SIGNING_KEY>"`
(format et méthode : [FORMAT_EXPORT.md](FORMAT_EXPORT.md)).

---

## 14. Dépannage

| Symptôme | Cause probable et remède |
|---|---|
| `docker compose up` : `required variable … is missing a value` | Variable obligatoire vide dans `.env`. La renseigner. |
| `web` s'arrête avec `[entrypoint] ERREUR de configuration : …` | Le message indique la variable en cause (clé manquante, clé N4 invalide, mot de passe d'une URL différent de la variable `*_PASSWORD`, rôle propriétaire utilisé à l'exécution, `DJANGO_DEBUG` activé). Corriger `.env`, puis `docker compose up -d`. |
| `web` : `base de données injoignable après 60 s` | Voir `docker compose logs db`. `password authentication failed` : les mots de passe de `.env` ont été modifiés après la première initialisation. Remettre les anciens, ou changer le mot de passe du rôle (10.4). |
| `role "fluxaa_app" does not exist` ou `database "fluxaa" does not exist` | Le volume `fluxaa_pgdata` existait déjà : le script d'initialisation ne s'exécute que sur un volume vide. Sur une installation **neuve et sans données** seulement : `docker compose down`, `docker volume rm fluxaa_pgdata`, `docker compose up -d`. Cette commande détruit la base. |
| `dependency failed to start: container fluxaa-web-1 is unhealthy` | `web` ne répond pas sur `/healthz`. Lire `docker compose logs web`. Vérifier que `DOMAIN` figure dans `DJANGO_ALLOWED_HOSTS`. Un premier démarrage très lent (migrations) se termine par un nouveau `docker compose up -d`. |
| Pas de certificat HTTPS (`caddy` : `challenge failed`, `timeout`) | Le DNS ne pointe pas vers le serveur (`dig +short <DOMAIN>`), ou le port 80 n'est pas joignable depuis Internet (pare-feu, NAT). Après plusieurs échecs, Let's Encrypt limite temporairement les demandes : corriger, puis attendre. Sans accès entrant : 13.1. |
| `502 Bad Gateway` | `web` arrêté ou en cours de démarrage : `docker compose ps`, `docker compose logs web`. |
| `400 Bad Request` | L'adresse utilisée n'est pas dans `DJANGO_ALLOWED_HOSTS`. |
| `403` « échec de la vérification CSRF » à la connexion | `DJANGO_CSRF_TRUSTED_ORIGINS` doit valoir `https://<DOMAIN>`. |
| Boucle de redirection | Un équipement placé devant Caddy termine le TLS : voir 13.2 (site en `http://`, `trusted_proxies`). |
| `413 Request Entity Too Large` | Requête de plus de 30 Mo (limite du `Caddyfile`). Les pièces sont limitées par `FLUXAA_MAX_UPLOAD_MB`. |
| `permission denied for table …` dans les journaux de `web` | Migration appliquée à la main sans attribution des droits. `docker compose restart web` (les droits sont recalculés au démarrage). |
| Les e-mails ne partent pas | Lire `docker compose logs web scheduler`. Tester : `docker compose exec web python manage.py sendtestemail <adresse>`. Vérifier `EMAIL_*` et que l'expéditeur est autorisé par le serveur SMTP. |
| Codes de double authentification refusés | Horloge du serveur (`timedatectl`) ou du téléphone décalée. Téléphone perdu : dans le paramétrage, fiche de l'utilisateur, décocher « double authentification activée » ; l'utilisateur réenrôle une application à sa prochaine connexion. |
| Sauvegarde : `n'est pas accessible en écriture` | `sudo chown 10001:10001` sur le dossier de sauvegarde (3.5). |
| Sauvegarde : `server version mismatch` | `ARG PG_MAJOR` du `Dockerfile` différent de la version du serveur (9.3). Aligner, puis `docker compose build`. |
| Restauration refusée : `connexion(s) active(s)` | Arrêter d'abord le service : `docker compose stop web scheduler`, puis utiliser `docker compose run --rm web …` (8.3). |
| `verify_journal` signale `BROKEN` | Le registre a été modifié en dehors de l'application. Ne rien corriger. Préserver les traces : sauvegarde immédiate, copie des journaux (`docker compose logs > …`). Identifier la dernière sauvegarde saine avec `restore.sh --test`. Alerter la direction du port et le responsable de la sûreté. |
| Mot de passe d'un administrateur perdu | `docker compose exec web python manage.py changepassword <adresse e-mail>`. |

---

## 15. Sources AIS (facultatif)

Le **tableau AIS** (`/carte/`) montre, sur un plan des eaux du port, la dernière position de chaque
navire entendu au cours des 24 dernières heures, avec l'escale qui lui correspond. Il ne fonctionne
qu'avec une source de positions ; sans source, la page reste une liste vide et rien d'autre ne change.
Les positions AIS sont des données diffusées publiquement par les navires : elles **informent et
corroborent** (alerte en cas d'écart avec un jalon, jamais de correction), elles ne sont jamais un acte
du registre et sont purgées après la durée fixée par le port (paramètre « positions AIS conservées »,
30 jours par défaut).

### 15.1 Préalable : le cadre de la carte

Dans le paramétrage du port (PARAMETRAGE.md §1 et §3), l'administrateur saisit les quatre limites
du cadre (latitudes sud et nord, longitudes ouest et est), la position de chaque poste ou zone
(latitude, longitude, rayon pour une zone) et, s'il le souhaite, un extrait de carte couvrant
exactement ce cadre (PNG ou JPEG dont le port détient les droits). Les ports pilotes sont livrés avec
un cadre et des positions **indicatives, à confirmer par la capitainerie**.

### 15.2 Trois façons d'alimenter le tableau

| Source | Commande ou point d'accès | Quand |
|---|---|---|
| **Récepteur local** (antenne VHF et logiciel AIS-catcher, rtl_ais, un transpondeur de la capitainerie…) qui émet des trames NMEA | `manage.py ais_listen --port TGLFW --udp 0.0.0.0:10110` ou `--tcp <hôte>:<port>` | la capitainerie dispose d'un récepteur ; aucune dépendance extérieure, aucun abonnement |
| **Flux aisstream.io** (positions mondiales, clé gratuite pour un usage modéré) | `manage.py ais_listen --port TGLFW --aisstream` avec `FLUXAA_AISSTREAM_KEY` | pas de récepteur ; nécessite un accès Internet sortant permanent du serveur |
| **Système tiers** (VTS, fournisseur commercial, PCS) qui pousse des positions | `POST /api/v1/ais/positions/` avec un compte d'intégration de périmètre `ais` (API.md §3) | le port a déjà un système qui reçoit l'AIS |

Un seul service par port suffit ; plusieurs sources peuvent coexister (les doublons sont ignorés).

### 15.3 Avec Docker Compose

Le service `ais` est défini dans `docker-compose.yml` sous le **profil `ais`** : il ne démarre que
sur demande.

```bash
# flux aisstream.io (clé dans .env : FLUXAA_AISSTREAM_KEY, port dans AIS_PORT)
docker compose --profile ais up -d ais

# récepteur local sur UDP 10110 : modifier la ligne « command » du service ais, par exemple
#   command: ["ais", "TGLFW", "--udp", "0.0.0.0:10110", "--batch-seconds", "5"]
# puis orienter le récepteur vers l'adresse du serveur, port UDP 10110.
```

Le service écrit les positions par lots toutes les cinq secondes, se reconnecte seul après une
coupure, ignore toute trame illisible et journalise un compte par lot (`docker compose logs ais`).
Les positions ne transitent jamais par le rôle propriétaire de la base : le service utilise le rôle
d'exécution comme `web` et `scheduler`.

### 15.4 Vérifier

* `docker compose logs --tail 20 ais` : une ligne `ais TGLFW: {'stored': …}` par lot.
* Page `/carte/` : les navires entendus apparaissent dans le cadre ; « 0 navire entendu » après dix
  minutes signale une source muette (antenne, pare-feu UDP, clé aisstream).
* Dans le paramétrage : **Positions AIS** et **Données navire AIS** (lecture seule).

### 15.5 Ce que l'AIS ne fait pas

Il ne crée, ne modifie et ne contresigne aucun jalon : l'arrivée et l'appareillage restent déclarés par
le capitaine. Un écart entre l'image AIS et le registre (navire entendu amarré alors qu'aucune arrivée
n'est enregistrée, navire parti alors que l'escale est « en opération »…) est affiché sur le tableau
comme une **question** pour la capitainerie et l'agence, et l'observation d'un fait corroborable produit
au plus une alerte (EF-3.6). Les positions sont visibles de toutes les parties du port ; l'escale
affichée à côté d'un navire n'est nommée qu'aux parties qui peuvent l'ouvrir.
