# Journal des versions

Chaque livraison est consignée ici (FLX-CDC-002 §8, méthode de travail) : version, date, ce qui change pour les
utilisateurs, ce qui change pour l'exploitant (migrations, variables, services), et les tests qui le couvrent.

## 1.3.1 — 10 novembre 2026

Révision de la version 1.3 après un test complet de bout en bout par l'interface (148 vérifications : tous les
écrans et toutes les actions de l'escale, avec chaque rôle, le capitaine par code et une partie par lien ;
`docs/spec/14-parcours-plan-et-recette.md` §14.3).

Pour les utilisateurs :

* **Annonce d'escale avec un navire nouveau** : l'annonce échouait (erreur serveur) quand le navire était saisi à la
  volée plutôt que choisi dans la liste ; corrigé, avec le même garde-fou sur tout identifiant vide ou non numérique
  envoyé par un formulaire (le registre répond « introuvable » ou ignore la valeur, jamais une erreur serveur).
* **Mise à niveau d'une installation existante** : les escales en cours d'une installation qui tournait avec la
  version 1.2 reçoivent au premier démarrage les documents que la 1.3 dépose d'elle-même (acte de chaque décision
  déjà prise, notice de disponibilité, time sheet). Sans cela, une installation mise à jour sans recharger ses données
  montrait des décisions sans acte dans l'onglet Documents.

Pour l'exploitant :

* `manage.py backfill_generated_documents` (idempotente, `--dry-run`, `--port`), exécutée par `entrypoint.sh` après
  les catalogues ; le lanceur Windows signale un changement de version et rappelle comment recharger des escales
  neuves (`docs/DEPLOIEMENT.md` §9.1). Aucune migration, aucune variable nouvelle.
* `generate_spec --check` ne signale plus comme obsolètes les chapitres 06 et 07 quand seuls les exemples tirés des
  données de démonstration ont bougé (codes de vérification, heures, empreintes, identifiants) : il ne refuse un
  dossier que si la structure décrite par le code a changé.
* Tests : 113 (`test_an_upgraded_installation_catches_up_the_documents_it_did_not_file_before`).

## 1.3 — 2 novembre 2026

Pour les utilisateurs :

* **Chaque partie émet ses documents depuis la plateforme, qui les archive.** Soixante-seize formulaires standards
  (quatorze en 1.2), groupés par partie émettrice sur la page *Formulaires* de l'escale et proposés selon les
  opérations de l'escale : l'**acte écrit de chaque décision** des autorités (feu vert, acceptation du navire,
  poste, mouvement, libre pratique, formalités d'arrivée et de sortie, congé de départ, mouillage, zone STS,
  soutage, rejet de ballast, dégazage, travaux, immobilisation, relève, accostage à couple — avec la demande telle
  que déposée, la validité, les conditions et le QR du code de vérification public) ; les conditions limites du
  poste ; pour l'agence : avis d'arrivée, attestation de contrôle des sanctions, notification STS à l'État côtier,
  mandat du POAC, déclarations FAL 2, 3 et 4, liste de relève d'équipage, données du connaissement (toujours
  derrière son verrou), compte d'escale ; pour le navire : eaux de ballast (BWRF), plans de déchargement et de
  chargement, trois dernières cargaisons, déclaration d'inertage, permis de travail par point chaud, permis
  d'entrée en espace clos, déclaration d'événement ; pour le terminal : synthèse du vetting, mise en sécurité du
  poste, relevé des bacs, bon de réception, inspection de la bouée, dossier d'accostage à couple ; pour la sûreté :
  liste d'accès, information de sûreté avant l'arrivée ; pour les services nautiques : ordre de mouvement, bon de
  prestation ; pour l'inspecteur : procès-verbal d'échantillonnage, certificats de quantité, de qualité, de
  propreté des citernes, de citernes vides, de dégazage ; pour l'armateur : recap de nomination, instruction
  documentaire, assurances, lettre de garantie ; pour les prestataires : bordereau de réception des déchets, liste
  de contrôle soutage, étude de compatibilité STS, attestation des défenses et flexibles, agrément de
  l'installation de réception, dossier des intervenants (`docs/FORMULAIRES.md`).
* **Les actes se déposent d'eux-mêmes.** L'acte écrit de chaque décision (approbation, approbation sous conditions
  ou refus — autorisation de départ, formalités, libre pratique, feu vert, poste, mouvement…) est généré et déposé
  dans les documents de l'escale au moment de la décision, sous le rôle décideur, avec la confidentialité et les
  lecteurs de la demande (le demandeur lit toujours l'acte de sa demande ; le motif d'un refus restreint n'y figure
  pas) ; la notice de disponibilité est déposée dès qu'elle est remise, le time sheet avec le rapport des faits.
  Une réémission manuelle reste possible ; une panne de génération ne bloque jamais l'acte. Le paramétrage du port
  expose désormais le cadre des eaux du port (limites, fond de carte, rétention) pour le tableau AIS.
* **Liste ouverte des parties à inviter.** À l'annonce comme dans l'onglet Parties (et par l'API), l'agence invite
  autant d'organisations qu'il en faut : enregistrées dans le port, ou nouvelles — nom, nature choisie dans une
  liste suggérée non exhaustive (pilotage, laboratoire, avitailleur, collecteur de déchets, correspondant P&I,
  réceptionnaire, chantier, plongée…) ou écrite librement, courriel, téléphone. Une nouvelle organisation est
  créée avec le rôle de l'invitation, journalisée, puis convoquée par lien à la déclaration.

Pour l'exploitant :

* Migrations : `core 0006` (nature de l'organisation), `registry 0012` (seize types de document des formulaires,
  ajoutés aux ports installés), `registry 0013` (lecteurs propres à un document, `Document.audience_roles`).
  Aucune variable nouvelle. Le paquet `apps/registry/services/forms/` remplace le
  module `forms.py` (même interface) ; `scripts/forms_catalogue.py` imprime le catalogue.
* Données de démonstration : natures des organisations ; un réceptionnaire, un correspondant P&I et un fournisseur
  d'eau douce sans compte sur chaque escale ; un avitailleur et une société de remorquage enregistrés.
* Tests : 112 (`tests/test_parties.py` ajouté, `tests/test_forms.py` étendu) ; chapitre 6 du dossier de
  spécifications régénéré (`generate_spec`).
* Documentation : le dossier de spécifications `docs/spec/` compte seize chapitres (05, 08, 10 à 16 rédigés ;
  01 à 04, 06, 07, 09 générés) ; le chapitre 16 reprend l'annexe I du cahier des charges FLX-CDC-002 v1.3 —
  le référentiel des opérations portuaires d'une escale pétrolière (rade et mouillage, pilotage et mouvements,
  quai, transfert, opérations annexes, STS, départ, événements ; demandes, documents, traçabilité) — et dit, pour
  chaque pratique, si elle est livrée, à paramétrer ou à développer ; `docs/TRACABILITE_CDC.md` trace les
  exigences EXG de FLX-CDC-002, dont les seize exigences nouvelles EXG-M-01 à M-16 (aucune livrée en 1.3).

## 1.2 — 28 octobre 2026

Pour les utilisateurs :

* **Convocation de chaque partie dès la déclaration**, avec son propre accès : notification pour les comptes ;
  pour une organisation sans compte (terminal, inspecteur, armateur, prestataire, services nautiques), un **lien
  d'accès nominatif** envoyé par courriel, valable jusqu'à la clôture de l'escale ; le titulaire donne son nom à la
  première ouverture ; l'agence ou la capitainerie émet ou révoque un lien à tout moment (onglet Parties). Un lien
  ne décide jamais.
* **Dépôt de documents par toute partie** (type « Autre document », types des formulaires standards).
* **Escales à plusieurs étapes** : rade, zone STS, bouée, quai, et retour ; planification de l'étape suivante par
  l'agence ou la capitainerie (tâches créées aussitôt), déhalage enregistré par les services nautiques sous
  autorisation de mouvement, jalons et tâches rattachés à leur étape, rapport des faits par étape.
* **Quatorze formulaires standards** générés du registre dans une structure unique (NOR, time sheet, liste de
  contrôle navire/terre ISGOTT, accord pré-transfert, rapport de jaugeage API MPMS, relevé flexibles, lettre de
  protestation, FAL 1 et 5, déclaration de sûreté ISPS, déclaration maritime de santé, notification des déchets
  MARPOL, listes STS OCIMF, fiche pilote A.960, note de soutes) : aperçu imprimable, dépôt dans l'escale comme
  document généré, aussi par lien et par API (`docs/FORMULAIRES.md`).

Pour l'exploitant :

* Migrations : `core 0005` (validité maximale des liens de partie), `registry 0008` à `0011` (liens de partie,
  étapes d'escale et leur garde-fou base de données, étape des tâches). Aucune variable nouvelle ; le courrier
  électronique (`EMAIL_*`) sert désormais aussi à la convocation des parties.
* Données de démonstration : un laboratoire sans compte convoqué par lien sur l'escale STS, une seconde étape à
  quai sur la même escale ; le lanceur Windows écrit le lien dans `COMPTES-DEMO.txt` (ligne `LIEN`).
* Tests : 104 (`tests/test_links.py`, `tests/test_stages.py`, `tests/test_forms.py` ajoutés).

## 1.1 — 25 octobre 2026

* Tableau AIS (`/carte/`, commande `ais_listen`, API de positions), statistiques du port (`/statistiques/`, export
  CSV), assistant du port (point du port, questions sur le registre, avec l'assistance IA). 95 tests.

## 1.0 — 25 octobre 2026

* Première livraison : registre des escales, tâches, jalons, demandes et autorisations, points d'arrêt,
  documents, mesures, contestations, échanges, sûreté N4, accès capitaine, appli terrain, tableau de bord, API,
  export de réversibilité, pile Docker, lanceur Windows.
