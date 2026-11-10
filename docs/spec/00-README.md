# FLX-SPEC-003 — Dossier de spécifications détaillées de FLUXAA Port

**Version 1.2 — 10 novembre 2026 — FLUXAA (Lomé). Confidentiel.**

Ce dossier donne à une équipe de développement **tout ce qu'il faut pour développer, faire évoluer ou refaire le produit** : le modèle de données champ par champ, les énumérations et les cycles de vie, les rôles et la matrice des droits, les catalogues (gabarits de tâches, jalons, demandes, documents, causes), les règles métier numérotées, chaque écran avec ses champs et ses actions, chaque formulaire standard avec ses sources de préremplissage, l'API, les notifications, les exigences non fonctionnelles et les données de démonstration.

Il complète — sans les remplacer — le corpus FLUXAA : PRO-MAR-001 (procédure d'escale), FLX-SPEC-001 (spécification fonctionnelle), FLX-SPEC-002 (catalogue des gabarits), FLX-CDC-001 (cahier des charges initial) et FLX-CDC-002 (cahier des charges de reprise et de mise en service). Quand un chapitre de ce dossier et un document du corpus divergent, **le code livré fait foi** et l'écart est consigné dans `docs/ARCHITECTURE.md` §11 (arbitrages).

## Comment lire le dossier

| Chapitre | Contenu | Origine |
|---|---|---|
| [01-modele-de-donnees.md](01-modele-de-donnees.md) | Toutes les entités des cinq applications (`core`, `registry`, `ais`, `ai`, `secure`), chaque champ avec son type, ses règles et son libellé FR / EN, les contraintes, les garde-fous d'intégrité | **généré** du code |
| [02-enumerations-et-cycles.md](02-enumerations-et-cycles.md) | Toutes les énumérations (codes et libellés), le cycle de vie des escales et des demandes | **généré** |
| [03-roles-et-droits.md](03-roles-et-droits.md) | Les douze rôles, la matrice objets × rôles, les fonctions de visibilité | **généré** |
| [04-catalogues.md](04-catalogues.md) | Échéances relatives, gabarits et leurs tâches, points d'arrêt, types de jalons, types de demande et leurs formulaires, types de document, causes d'interruption, ports pilotes | **généré** |
| [05-regles-metier.md](05-regles-metier.md) | Les six règles d'or et les invariants que le code applique, les cycles de vie, les droits et la confidentialité, les points d'arrêt et verrous, avec la fonction et le test qui les portent | rédigé |
| [06-formulaires.md](06-formulaires.md) | La structure unique et chacun des soixante-seize formulaires standards (une famille par partie émettrice), champ par champ, avec sa source de préremplissage | **généré** |
| [07-api.md](07-api.md) | Inventaire des opérations de l'API v1 et exemples de représentations JSON | **généré** |
| [08-ecrans.md](08-ecrans.md) | Chaque écran : adresse, rôles, zones et composants, données, actions, états ; les captures sont dans le catalogue des écrans (`fluxaa-port-ecrans.pdf`) | rédigé |
| [09-routes-et-actions.md](09-routes-et-actions.md) | Inventaire des routes, des vues et des actions de l'écran d'escale avec leurs paramètres | **généré** |
| [10-notifications-et-alertes.md](10-notifications-et-alertes.md) | Mécanismes de notification, alertes et traitements périodiques, inventaire des émissions, courriels | rédigé |
| [11-exigences-non-fonctionnelles.md](11-exigences-non-fonctionnelles.md) | Architecture technique et pile livrée ; sécurité, performance, disponibilité, langues et temps, accessibilité, hors ligne, exploitation, qualité | rédigé |
| [12-donnees-de-reference-et-demonstration.md](12-donnees-de-reference-et-demonstration.md) | Causes d'interruption, ports pilotes, parties par défaut et postes, natures de parties (liste non exhaustive), actions du journal ; ce que `load_demo` crée | rédigé |
| [13-formulaires-de-saisie.md](13-formulaires-de-saisie.md) | Chaque formulaire de saisie de l'interface : champs, types, obligations, validations, valeurs par défaut, effets et messages de refus | rédigé |
| [14-parcours-plan-et-recette.md](14-parcours-plan-et-recette.md) | Le parcours d'une escale de bout en bout (qui agit, quel acte, quel effet), le plan de développement recommandé, la recette et le test de bout en bout par l'interface (`scripts/test_interface.py`) | rédigé |
| [15-glossaire.md](15-glossaire.md) | Les termes du produit et leur définition | rédigé |
| [16-referentiel-operations-portuaires.md](16-referentiel-operations-portuaires.md) | Le référentiel des opérations portuaires d'une escale pétrolière (annexe I de FLX-CDC-002) : zones et régimes, phases et heures de référence, demandes et points d'arrêt, documents par partie, pratiques par zone et par opération, traçabilité, responsabilités, indicateurs — chaque pratique avec son état : livré, paramétrage, à développer (EXG-M-01 à M-16) | rédigé (copie du cahier des charges) |

Les chapitres **générés** sont produits par `python manage.py generate_spec` à partir des modèles Django, du catalogue (`apps/registry/catalog.py`), des services (`apps/registry/services/`), des formulaires (`services/forms/`), des routes et du schéma OpenAPI. Ils sont la référence : une équipe qui modifie le code régénère le dossier (`generate_spec --check` en intégration continue refuse un dossier obsolète). Les chapitres rédigés sont tenus à jour à la main, à chaque livraison, comme le `CHANGELOG.md`.

## Conventions

* **Identifiants.** Les entités sont désignées par leur nom de classe (`PortCall`, `Milestone`), les champs par `Entité.champ`, les codes de catalogue entre apostrophes inversées (`M0:25`, `SHIFT_START`, `VESSEL_ACCEPTANCE`). Les règles métier sont les six règles d'or numérotées 1 à 6 (chapitre 05) et les invariants nommés qui les complètent ; les écrans et les tests les citent par leur numéro ou leur nom.
* **Langues.** L'interface est bilingue français / anglais ; le dossier est en français et donne les libellés anglais à côté des libellés français quand le code les porte (catalogues, formulaires, énumérations). La langue d'affichage est celle de la personne (profil), à défaut celle du port.
* **Temps.** Toute date est stockée en UTC et affichée dans le fuseau du port ; les formulaires imprimés et le rapport des faits sont en UTC, explicitement.
* **Rôles.** Les trois lettres des rôles (AGE, NAV, TER, CAP, APO, SVC, ADM, SUR, INS, COM, PRE, DIR) sont celles de FLX-SPEC-001 §4 ; elles sont partout : gabarits, droits, écrans, API.
* **Points d'arrêt et refus.** Un refus de la plateforme n'est jamais silencieux : il nomme la tâche manquante, son responsable et l'action attendue, et il est inscrit au journal de l'escale.

## Périmètre livré

La version 1.3.1 du code (10 novembre 2026) couvre : registre des escales (tâches, jalons, demandes et autorisations, points d'arrêt, documents, mesures, contestations, échanges, étapes), convocation et accès sans compte des parties, liste ouverte des parties, formulaires standards émis par chaque partie, sûreté N4, appli terrain hors ligne, tableau de bord, tableau AIS, statistiques, assistant du port, API, export de réversibilité, paramétrage sans code, pile Docker et lanceur Windows. Ce dossier décrit cette version ; ce qui reste à décider pour la mise en service (hébergement, horodatage qualifié, postes réels, causes validées, adresses des organisations, édition des listes de contrôle) est dans FLX-CDC-002, annexes B et C. Ce que le métier attend encore de la plateforme — contrôle des maxima du poste, plan d'occupation, registre des certificats, événements et urgences, temps de planche… — est au chapitre 16 et dans la section 6.11 du même cahier des charges.

## Autres documents à lire avec ce dossier

`README.md` (démarrage), `docs/ARCHITECTURE.md` (composants, invariants, journal chaîné, arbitrages), `docs/API.md` (authentification, erreurs, hors ligne, webhooks), `docs/FORMULAIRES.md` (usage des formulaires), `docs/GUIDE_UTILISATEUR.md` (parcours par rôle), `docs/PARAMETRAGE.md` (administration sans code), `docs/SECURITE.md`, `docs/DEPLOIEMENT.md`, `docs/FORMAT_EXPORT.md`, `docs/TRACABILITE_CDC.md`, `docs/COMPOSANTS.md`.
