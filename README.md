# FLUXAA Port

**Registre opérationnel des escales de navires pétroliers** — rade, bouées et zones STS au large, quais. Une plateforme web commune à toutes les parties d'une escale (agence maritime, capitaine, terminal, capitainerie, autorité portuaire, services nautiques, douanes-immigration-santé, sûreté, inspecteur indépendant, armateur ou affréteur, prestataires), placée sous la garde de l'autorité portuaire.

Pilote livré pour **Freetown (SLFNA)** et **Lomé (TGLFW)**, interface **français / anglais**. Le code met en œuvre le cahier des charges FLX-CDC-001 et le corpus qui le précède (PRO-MAR-001, FLX-SPEC-001, FLX-SPEC-002) ; la correspondance exigence par exigence est dans [docs/TRACABILITE_CDC.md](docs/TRACABILITE_CDC.md).

## Ce que fait la plateforme

* **L'agence crée l'escale ; la plateforme crée le travail de chacun.** Les tâches de toutes les parties sont instanciées depuis les gabarits du port (socle M0, opérations M1 à M8, modules M9 et MA1 à MA3), assignées à des rôles, avec des échéances relatives à l'ETA, l'ETB, l'ATB, T0, T1, l'ATD ou la NOR, recalculées en cascade.
* **Une chronologie contradictoire.** Chaque jalon a un seul émetteur ; les autres parties contresignent ou contestent ; le silence devient « contresignature tacite », jamais un accord. Double horodatage, saisie hors ligne, ressaisie de la procédure papier.
* **Ce que la plateforme refuse, et pourquoi.** Points d'arrêt : déclaration, feu vert, poste, mouvement, pilote, début de transfert, départ, clôture ; verrou du connaissement que personne ne peut lever. Chaque refus nomme la tâche manquante et son responsable, et reste au journal.
* **Un moteur unique de demandes et d'autorisations** : formulaires paramétrables, qui demande ne décide jamais, décision sous double authentification, autorisation à expiration obligatoire et code de vérification public.
* **Documents, mesures, contestations, échanges**, tous rattachés à l'escale : empreintes SHA-256, versions, signatures ; quantités bord / terre / inspecteur sans valeur de référence ; contestations jamais « rejetées » ; aucune messagerie libre.
* **Rien ne s'efface.** Ni par l'application, ni par l'administration, ni par un accès direct à la base : garde-fous applicatifs, déclencheurs PostgreSQL, rôle sans droit de suppression, journal chaîné vérifiable hors plateforme.
* **Sûreté (N4) à part** : base distincte, chiffrement par des clés propres, dépôt en écriture seule, accès nominatif journalisé.
* **Chaque partie convoquée dès la déclaration**, avec son propre accès : notification pour les comptes, **lien nominatif sans compte** (valable jusqu'à la clôture) pour un terminal, un inspecteur, un armateur, un prestataire ou un service nautique qui n'en a pas ; **accès capitaine** par lien ou code remis par l'agence ; toute partie dépose ses documents ; **appli terrain** installable qui fonctionne sans réseau sur l'appontement.
* **Une escale qui change de zone** — rade, zone STS, bouée, quai, et retour — se compose d'**étapes** successives, chacune avec son poste, ses opérations, ses tâches et ses jalons ; le déhalage est gardé par l'autorisation de mouvement.
* **Chaque partie émet ses documents depuis la plateforme, qui les archive** : soixante-seize formulaires standards (NOR, time sheet, liste de contrôle navire/terre ISGOTT, rapport de jaugeage API MPMS, FAL, déclaration de sûreté ISPS, déclaration maritime de santé, notification et bordereau des déchets MARPOL, eaux de ballast BWM, listes STS OCIMF, fiche pilote A.960, permis de travail et d'entrée, certificats de quantité, de qualité, de propreté et de dégazage, acte écrit de chaque décision du port avec son code de vérification, ordre de mouvement, bons de prestation, instruction documentaire, lettre de garantie…), une famille par rôle, générés depuis le registre dans **une structure unique**, à imprimer, signer et déposer — [docs/FORMULAIRES.md](docs/FORMULAIRES.md).
* **Une liste ouverte de parties** : l'agence invite autant d'organisations qu'il en faut — enregistrées dans le port ou nouvelles (nom, nature suggérée ou libre, courriel, téléphone) —, convoquées chacune avec son propre accès à la déclaration.
* **Tableau de bord** (plan des postes sur 72 h, sept indicateurs traçables), **API publique** documentée, **export de réversibilité** au format ouvert.
* **Assistance IA optionnelle** (désactivée par défaut) : extraction pré-remplie à valider, revue de cohérence, résumés, projet de remarques, et au niveau du port un **point du jour** et des **questions sur le registre** — jamais une décision, jamais une donnée N4.
* **Tableau AIS** : les navires entendus dessinés sur le plan des eaux du port (récepteur local, flux aisstream.io ou système tiers), rapprochés des escales ; les écarts avec le registre sont posés comme des questions, jamais corrigés.
* **Statistiques** du port sur une période libre, recalculées du registre et exportables : escales, tonnages, attentes, interruptions par cause, délais de décision, contestations, saisies, tâches dans les délais par rôle.

## Démarrer

### Pour essayer sur un PC Windows (démonstration locale, un double-clic)

1. Installez [Docker Desktop](https://www.docker.com/products/docker-desktop/) si ce n'est pas déjà fait (redémarrage possible), et ouvrez-le une première fois.
2. Double-cliquez sur **`DEMARRER.cmd`** (à la racine de ce dossier). Si Windows demande confirmation (« Voulez-vous exécuter ce fichier ? » ou « Windows a protégé votre ordinateur » → *Informations complémentaires* → *Exécuter quand même*), acceptez.
3. La première fois, comptez 5 à 15 minutes : le lanceur crée la configuration (`deploy/.env`, secrets générés), construit l'image, démarre les services, charge les données de démonstration de Lomé et de Freetown, fait reconnaître le certificat local par Windows (répondez *Oui*) et ouvre `https://localhost/`.

Les comptes et le mot de passe sont écrits dans **`COMPTES-DEMO.txt`**. Les rôles qui décident (capitainerie, autorité portuaire, douanes-santé, sûreté) et l'administrateur du port demandent un code à 6 chiffres : **`CODES-DEMO.cmd`** l'affiche. **`ARRETER.cmd`** arrête la plateforme en conservant les données ; **`REINITIALISER-DEMO.cmd`** efface tout pour repartir d'une installation neuve. Cette installation locale est réservée à la démonstration (certificat local, courriels non envoyés) ; une mise en service suit [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md).

### En production ou en préproduction (Docker)

```bash
cd deploy
cp .env.example .env        # puis renseigner les secrets (voir docs/DEPLOIEMENT.md §3)
docker compose up -d --build
```

Le guide complet — prérequis, secrets, premier compte, sauvegardes, **test de restauration trimestriel**, mises à jour — est dans [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md).

### En développement (sans Docker)

Prérequis : Python 3.12+, PostgreSQL 16 (les déclencheurs d'intégrité sont propres à PostgreSQL), gettext.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
createdb fluxaa_dev && createdb fluxaa_secure_dev
export DJANGO_DEBUG=1 \
       DATABASE_URL="postgres://postgres@localhost/fluxaa_dev" \
       SECURE_DATABASE_URL="postgres://postgres@localhost/fluxaa_secure_dev" \
       FLUXAA_N4_KEYS="$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')" \
       FLUXAA_SIGNING_KEY="dev-only"
python manage.py migrate && python manage.py migrate --database secure
python manage.py compilemessages
python manage.py bootstrap_ports
python manage.py load_demo --port TGLFW --password Demo-Fluxaa-2026   # données fictives
python manage.py runserver          # http://127.0.0.1:8000
python manage.py run_scheduler      # dans un second terminal : alertes, tacites, expirations
```

Comptes de démonstration : `<rôle>.<port>@demo.fluxaa.test` (par exemple `age.tglfw@…`, `cap.tglfw@…`, `ter.slfna@…`), mot de passe choisi à l'appel de `load_demo`. Les secrets TOTP des rôles décideurs (CAP, APO, ADM, SUR) et de l'utilisateur `dir`, administrateur fonctionnel du port, sont affichés par la commande. Accès capitaine : `/bord/`. **Ne jamais charger les données de démonstration sur un port en production** : elles ne pourraient plus être effacées.

## Tests

```bash
# un PostgreSQL 16 accessible suffit : les bases de test (test_…) sont créées puis supprimées par pytest
export DATABASE_URL="postgres://postgres@localhost/fluxaa" SECURE_DATABASE_URL="postgres://postgres@localhost/fluxaa_secure"
pytest
ruff check .        # contrôle du code (règles fixées dans ruff.toml)
```

La suite (113 tests) joue les **huit scénarios de recette S1 à S8** du cahier des charges, les invariants d'intégrité (refus de mise à jour et de suppression par la base, détection d'altération du journal), les droits par rôle et par organisation, le parcours web de chaque rôle, l'API, les accès par lien des parties sans compte, les escales à plusieurs étapes, les formulaires standards, le tableau AIS (ingestion, décodage NMEA, projection, écarts, visibilité), les statistiques, l'assistance IA (dont la preuve qu'aucune donnée N4 ne lui parvient), la vérification hors plateforme d'un export et, dans `tests/test_security.py`, chacune des attaques relevées par la revue de sécurité ([docs/SECURITE.md](docs/SECURITE.md)). S'y ajoute un test **par les écrans** avec un navigateur réel, `scripts/test_interface.py` (148 vérifications sur une installation neuve : une escale complète avec chaque rôle, puis chaque écran de chaque rôle — [docs/spec/14-parcours-plan-et-recette.md](docs/spec/14-parcours-plan-et-recette.md) §14.3).

## Organisation du code

```
apps/core       ports, organisations, utilisateurs, postes, double authentification, garde-fous d'écriture
apps/registry   escales, gabarits et tâches, jalons, demandes, documents, mesures, contestations,
                échanges, alertes, notifications, journal chaîné, exports, tableau de bord, appli terrain
apps/api        API publique v1
apps/secure     domaine sûreté N4 (base séparée)
apps/ai         assistance IA optionnelle (EF-17) : escale et port (point, questions)
apps/ais        tableau AIS : ingestion (NMEA, aisstream, API), plan des eaux du port, écarts
templates/      écrans (HTML + HTMX), rapport des faits imprimable
static/         feuille de style, scripts, appli terrain hors ligne (service worker)
locale/fr       traductions françaises
deploy/         Dockerfile, docker-compose, Caddy (HTTPS), initialisation PostgreSQL
scripts/        sauvegarde, restauration, vérification d'un export
tests/          tests automatisés (PostgreSQL)
docs/           documentation
```

## Documentation

| Document | Pour qui |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | équipe technique — composants, invariants, journal chaîné, arbitrages entre documents du corpus, points ouverts |
| [docs/DEPLOIEMENT.md](docs/DEPLOIEMENT.md) | exploitant — installation, secrets, sauvegardes, restauration, mises à jour |
| [docs/GUIDE_UTILISATEUR.md](docs/GUIDE_UTILISATEUR.md) | chaque rôle — ce qu'il voit, ce qu'il fait, ce qui sera refusé ; démonstration en dix minutes |
| [docs/PARAMETRAGE.md](docs/PARAMETRAGE.md) | administrateur fonctionnel du port — gabarits, types de demande, causes, seuils, sans code |
| [docs/API.md](docs/API.md) | intégrateurs — authentification, erreurs, points d'accès, synchronisation hors ligne, webhooks |
| [docs/FORMULAIRES.md](docs/FORMULAIRES.md) | toutes les parties — les soixante-seize formulaires standards par partie émettrice, leur structure unique, leur dépôt, leur API |
| [docs/FORMAT_EXPORT.md](docs/FORMAT_EXPORT.md) | port et auditeurs — format de réversibilité et vérification d'intégrité |
| [docs/spec/00-README.md](docs/spec/00-README.md) | équipe de développement — le dossier de spécifications détaillées FLX-SPEC-003 en seize chapitres : modèle de données, énumérations, droits, catalogues, règles métier, formulaires, API, écrans, routes, notifications, exigences non fonctionnelles, données de référence, formulaires de saisie, parcours et recette, glossaire, référentiel des opérations portuaires |
| [docs/TRACABILITE_CDC.md](docs/TRACABILITE_CDC.md) | maîtrise d'ouvrage — chaque exigence des cahiers des charges (FLX-CDC-001, FLX-CDC-002), son code et sa preuve ; ce qui reste à développer |
| [docs/SECURITE.md](docs/SECURITE.md) | équipe technique, auditeurs, test d'intrusion — garanties, vérifications réalisées, limites connues |
| [docs/COMPOSANTS.md](docs/COMPOSANTS.md) | juridique — composants libres et licences (CDC §9) |

## Avant la mise en service

Le code ne tranche pas ce qui relève d'une décision : horodatage qualifié et niveau de signature électronique (**point ouvert O04**), hébergement (O05), périmètre exact du pilote (O06), liste fermée des causes d'interruption négociée avec les parties, noms et limites réels des postes de Freetown et de Lomé, test d'intrusion. Voir [docs/ARCHITECTURE.md §12](docs/ARCHITECTURE.md).

## Propriété

Code source, documentation et éléments graphiques : propriété de FLUXAA (FLX-CDC-001 §9). Les composants libres utilisés et leurs licences sont déclarés dans [docs/COMPOSANTS.md](docs/COMPOSANTS.md) ; tous autorisent l'exploitation commerciale.
