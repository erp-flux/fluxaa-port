# Journal des versions

Chaque livraison est consignée ici (FLX-CDC-002 §8, méthode de travail) : version, date, ce qui change pour les
utilisateurs, ce qui change pour l'exploitant (migrations, variables, services), et les tests qui le couvrent.

## 1.6 — 13 novembre 2026

L'annonce s'adapte à l'opération (FLX-CDC-002 §6.13, EXG-R-11).

Pour les utilisateurs :

* **Questions propres à chaque modèle d'opération** sur le formulaire d'annonce : dévoilées par le coche du modèle, obligatoires seulement alors, typées (nombre à virgule accepté, date-heure du port), gardées sur l'escale par modèle (*Aperçu › Déclaré à l'annonce*), reprises à la reprise d'une annonce et copiées au partenaire d'un STS ou d'un accostage à couple ; seize fiches livrées (M1 à M9, MA3, MB1, MB2, MC1, MG1, MR1, MX1), adaptables par le port.
* **Demandes préremplies depuis l'annonce** (soutage, ballast, dégazage, travaux, immobilisation, relève, zone STS, accostage à couple, mouillage), signalées comme telles sur la ligne de la tâche et dans l'onglet Demandes — à vérifier avant transmission. **Chaque demande ne reprend que les réponses de son opération** (le modèle dont une tâche la lève) : une clé de même nom dans un autre modèle n'est pas reprise — le volume de ballast n'est pas un volume de déchets, la durée d'un accostage à couple n'est pas celle d'une immobilisation. La demande d'acceptation du navire s'ouvre avec le produit, la quantité et le poste de l'annonce, et les trois dernières cargaisons déclarées. Un nombre décimal déclaré (450,5 t) préremplit la demande en français comme en anglais.
* **Ce que l'agence déclare à l'annonce se lit comme le produit et la quantité** : par les parties qui lisent l'escale entière, pas par un prestataire — ni sur l'aperçu, ni par l'API, ni par le préremplissage ; il lit ce qui le concerne dans la demande qui lui est adressée. Les nombres déclarés s'écrivent dans la langue du lecteur (1 200 ; 450,5).
* **Accostage à couple nommé à l'annonce** (module M9) : position de ce navire (extérieur / intérieur) et l'autre navire — une escale du port de n'importe quelle agence (vue sur la conférence de placement), un navire enregistré ou nouveau dont l'escale est créée sous son agence ; lien réciproque entre escales de la même agence, à sens unique vers l'escale d'une autre agence jusqu'à l'autorisation d'accostage à couple de la capitainerie ; l'agence, le capitaine et la capitainerie de l'autre escale avertis aussitôt ; l'en-tête et l'aperçu montrent la configuration.
* **Transbordement avec le navire-mère d'une autre agence** : l'escale partenaire se choisit aussi parmi les escales des autres agences que la conférence de placement montre en rade ou en zone STS ; elle est **nommée, jamais ouverte** — son agence, son capitaine et la capitainerie avertis —, le rôle inverse (livre / reçoit) est pris d'office, le lien reste *à confirmer* jusqu'à l'autorisation de zone et de fenêtre STS, et rien du dossier désigné (journal de pompage) n'est lu avant ; une escale peut être désignée par plusieurs navires (*Autres navires désignant cette escale*) ; même règle pour l'action *Relier une escale partenaire*.
* **L'agence de l'autre navire n'est ni forcément celle qui annonce, ni forcément déjà enregistrée** : pour un navire sans escale encore (transbordement ou accostage à couple), *Son agence n'est pas dans la liste* la nomme (nom, e-mail ; API `agency_name`, `agency_email`, `agency_phone`) ; elle est enregistrée dans le port comme agence maritime — ou retrouvée par son nom —, l'escale de son navire est créée sous elle, **elle seule la déclare**, et les administrateurs du port sont avertis tant que personne ne peut se connecter pour elle ; l'agence annonçante y garde un accès d'agence associée. Une escale partenaire choisie, les champs *navire* et *agence* du bloc se grisent.
* **Une annonce refusée revient telle qu'elle a été saisie, et n'enregistre rien** : l'annonce s'exécute en une transaction (écran et API) — plus de navire nouveau ou d'organisation laissés en chemin par un refus, plus de formulaire à ressaisir. Un navire « nouveau » dont le port connaît déjà l'IMO est nommé, avec le renvoi à la liste des navires enregistrés. Par l'API, un enregistrement refusé par sa propre validation (e-mail d'une organisation nommée…) répond `400 validation_error`, champ par champ, au lieu d'une erreur serveur.
* **Avant de demander un poste** : qui le tient ou l'attend sur la fenêtre demandée ; **la compatibilité du navire avec les limites d'acceptation du poste** (✓ / ✗ / ! par ligne et l'avis) et un avertissement si le poste ne reçoit pas la nature de cargaison choisie.
* **Parties proposées par l'opération** : la liste des parties qu'appelle chaque modèle coché (terminal, inspecteur, réceptionnaire, prestataire STS, soutier, installation de réception, manutentionnaire, draft surveyor, société de pointage, fournisseur de défenses…), chacune ajoutée d'un bouton avec son rôle et sa nature ; dix natures de parties ajoutées au catalogue (terminaux de vrac, à conteneurs, divers / roulier ; manutentionnaire, saisissage, fumigation, pont-bascule ; société de pointage, inspecteur de soutage ; transitaire).
* Un choix de l'annonce repris dans un champ libre d'une demande s'y lit en clair (*Allègement ou complément de cargaison au poste*, *VLSFO 0,5 %*), plus par son code.
* Données de démonstration : deux escales du consignataire associé — **MT LAGUNE DEMO** à couple de MT ATLANTIC DEMO (demande d'accostage à couple en attente, tenue par le point d'arrêt) et **MT KARA DEMO**, second navire-fille du navire-mère MT HARMATTAN DEMO (autorisation de zone STS en attente) ; la paire STS partage désormais la cargaison (60 000 t et 30 000 t).
* API : `POST /api/v1/calls/` accepte `operation_details` et `double_banking`, et `linked_call` peut désigner l'escale d'une autre agence vue sur la conférence ; `GET` rend `operation_details`, `declared`, `linked_call` (`kind`, `reciprocal`, `confirmed`) et `named_by` (les escales qui désignent celle-ci) ; export `fluxaa-port-export/1.3` (`link_kind`, `operation_details`).
* **Étude d'intégration Kpler / MarineTraffic** (`docs/INTEGRATIONS.md`) : inventaire des points d'entrée et de sortie de la plateforme, revue des produits Kpler (positions AIS, arrivées attendues et ETA, escales observées, fiche navire et propriété, Risk & Compliance, Direct Access, Container Intelligence) et ce que chacun apporterait à une escale, trajectoire en cinq étapes ; **adaptateur livré** `scripts/kpler_marinetraffic_adapter.py` (positions MarineTraffic / Kpler AIS → tableau AIS de FLUXAA, essai à sec, tests).
* La relecture avant livraison a corrigé quatre défauts de la 1.6 elle-même — le préremplissage par simple coïncidence de clé entre modèles ; les réponses de l'annonce servies à un prestataire ; un nombre décimal prérempli vidé par le navigateur en français ; la mention *lien à confirmer…*, trop longue, qui élargissait la page de l'aperçu — et deux plus anciens, que le formulaire allongé rendait plus coûteux : l'annonce refusée qui perdait la saisie et pouvait laisser un navire ou une organisation enregistrés ; l'erreur serveur de l'API sur l'e-mail invalide d'une organisation nommée. Chacun est couvert par un test.
* Le test de bout en bout a montré que la capitainerie ne peut décider une demande déposée sur une escale encore en brouillon d'une autre agence (invisible pour elle jusqu'à la déclaration) : comportement voulu, le scénario déclare l'escale avant la décision.

Pour l'exploitant :

* Migration `registry.0018` (fiche d'intention des gabarits, réponses de l'annonce ; installation des fiches livrées sur les gabarits existants). Aucune variable nouvelle.
* Suite de tests rendue indépendante de l'ordre : chaque test commence dans la langue du port du monde de test (Freetown, anglais) — un test des feux verts ne passait que s'il suivait un test ayant laissé l'anglais actif ; il passe désormais seul comme dans la suite, et chaque fichier de tests a été rejoué isolément. La vérification des chapitres générés (`generate_spec --check`) ignore les durées qui avancent avec l'horloge (heures au port d'une escale en cours).
* Tests : 152 (`tests/test_announcement.py`, quatorze tests ; `tests/test_integrations.py`, deux tests) ; test par les écrans : 238 vérifications, second facteur imposé (section « 1.6 — L'annonce s'adapte à l'opération », scénario S14 de `docs/spec/14`).

## 1.5 — 12 novembre 2026

Généralisation de la plateforme : toutes les cargaisons, toutes les parties sous contrôle (FLX-CDC-002 §6.13, EXG-R-01 à R-10).

Pour les utilisateurs :

* **Chaque tâche se fait sur sa ligne** (*Tâches*) : le document à déposer, la demande à remplir, la décision à prendre, le jalon à enregistrer, la confirmation à donner, sans changer d'onglet.
* **Validité de l'annonce** : fixée en jours à l'annonce (défaut et plafond du port : 15 et 90 jours), rappelée 72 h puis 24 h avant l'échéance ; une escale pas encore à quai à l'échéance devient **obsolète** (lisible, plus modifiable) et l'agent principal **refait l'annonce** d'un bouton ; une escale à quai n'est jamais interrompue, son **dépassement** est compté. La validité, le temps au port et le dépassement forment la **base de facturation** (encart *Validité de l'annonce*, time sheet section E, API, export).
* **Quatre feux verts** sur le panneau de l'aperçu : capitainerie (sa décision), **sûreté et base navale** (avant le mouvement et l'amarrage), **terminal** et **mandant — armateur / affréteur** (avant le transfert) ; chacun donne le sien d'un bouton et peut le **retirer avec un motif** : toutes les parties sont informées, le point d'arrêt se referme.
* **Agent principal et accès contrôlé** : l'agence qui annonce donne à chaque partie invitée tout le dossier, une partie (les onglets choisis) ou la lecture seule, à l'annonce ou depuis *Parties* ; une **agence associée** peut être nommée pour une partie des opérations ; les onglets, les boutons et l'API suivent l'accès donné ; les autorités du port gardent tout.
* **Transbordement navire-navire en deux escales** : le navire qui livre et celui qui reçoit ont chacun leur escale, leur agence et leur équipe ; l'escale du partenaire est créée depuis l'annonce ; les deux journaux de pompage sont rapprochés relevé par relevé.
* **Documents attendus dès l'annonce** : les documents exigés par les gabarits sont listés ; l'agence ajoute ceux du catalogue qu'elle attend et tout autre document (liste ouverte, rôle, délai) — chacun devient une tâche de la partie qui l'émet ; *Documents › Documents attendus* pour en demander d'autres.
* **Toutes les cargaisons** : nature de la cargaison et type de navire à l'annonce ; gabarits **MB1** déchargement et **MB2** chargement de vrac sec, **MC1** conteneurs, **MG1** marchandises diverses et colis, **MR1** roulier, **MX1** toute autre escale (passagers, navire d'État, pêche, recherche, relâche) ; unités (EVP, boîtes, mouvements, unités, m³ en vrac, passagers) ; mesures draft survey, pesée à terre, pointage ; jalons de début et fin des opérations ; listes de contrôle du **Code BLU** et des **opérations de manutention** en ligne ; dix-sept formulaires de plus — PAEC (ISGOTT 22.2), grille de vetting, plan de manutention, manifeste, plan d'arrimage, bay plan, déclaration de marchandises dangereuses, déclaration IMSBC, accord BLU, draft survey, inspection des cales, pointage, reçu de bord, out-turn, constat de dommages, listes BLU et manutention (94 formulaires au total).
* **Conférence de placement** (ex-*Tableau du port*) : à quai, en rade, attendus, partis, avec la nature de la cargaison et le tonnage quand le port les montre, formulaires FAL et manifeste déposés ; téléchargement CSV ; **plan d'occupation des postes** sur une période (opération, mandant, produit, quantité, ETA / ETB / ETD, état), CSV aussi.
* **Grille de vetting** : chaque limite d'acceptation du poste comparée aux données du navire (Y / N / K / Z) et un avis.
* Une partie en lecture seule, ou dont l'accès partiel exclut un onglet, ne se voit proposer aucun bouton d'action ; le serveur refusait déjà, l'écran ne prétend plus le contraire.

Pour l'exploitant :

* Migrations `core.0007` (ports : validité par défaut et maximale, tableau avec cargaison ; postes : limites d'acceptation, natures de cargaison), `registry.0016` (escales, parties, tâches, navires, gabarits, mesures, listes de contrôle) et `registry.0017` (nouvelle version publiée du gabarit M0 par port, gabarits et catalogue cargo, points d'arrêt) — `docs/DEPLOIEMENT.md` §9.1 : les escales en cours gardent leur version de gabarit. Aucune variable nouvelle. Format d'export `fluxaa-port-export/1.2` (champs ajoutés seulement).
* Données de démonstration : un consignataire associé et un terminal conteneurs et vrac, les comptes `age2` et `ter2`, quatre navires (vraquier, porte-conteneurs, roulier, cargo divers) avec leurs caractéristiques, des limites d'acceptation illustratives sur les postes, les escales E (vrac sec, acceptée, agence associée en accès partiel), F (conteneurs), G (roulier), H (divers, obsolète à refaire), et les feux verts des escales A et B.
* Tests : 136 (`tests/test_generalisation.py`, onze tests) ; test par les écrans : 214 vérifications (`scripts/test_interface.py`, scénario S13 de `docs/spec/14`, second facteur imposé).

## 1.4 — 12 novembre 2026

Contrôle des pertes, interface navire/terre et préparation de la déclaration (FLX-CDC-002 §6.12, EXG-Q-01 à Q-10).

Pour les utilisateurs :

* **Journal de pompage tenu par le navire et par le terminal** (*Mesures › Journal de pompage — bord et terre*) : chaque bord ouvre sa feuille (citerne, niveau de départ et d'arrêt prévu, m³ par mètre, densité, VCF, quantité et débit prévus, heures estimées) et relève heure par heure ; la plateforme calcule les volumes horaires et cumulés, les tonnes et le débit, apparie les relevés des deux bords, affiche l'écart terre − bord horaire et cumulé et alerte en temps réel au-delà de la tolérance du port — « arrêter pour investigation ». Formulaire `PUMPING_LOG` généré. Lu par la capitainerie, l'inspecteur, l'armateur et l'affréteur (superintendant, trader, loss control), la direction et l'agence.
* **Time sheet** dans la structure des time sheets de terminal (informations générales, activités standard, arrêts et retards comptés ou imputés, quantités et performance par produit, récapitulatif des temps, exclusions), généré par l'agence, le terminal ou le navire, lu par toutes les parties ; heures de pompage prévues et référence de lot à l'annonce de l'escale.
* **Relevés de citernes** : les citernes du navire par le navire, les bacs à terre par le terminal (niveau, température, eau libre, densité, TOV, GOV, VCF, GSV, poids) ; **l'inspecteur valide ou rejette** avant que les autres parties ne les voient ; un relevé rejeté se corrige par un nouveau relevé, totaux validés par bord.
* **Certificat de qualité du laboratoire** lu par le terminal, l'armateur ou l'affréteur, le navire, l'inspecteur et le port seulement.
* **Accès aux rapports décidés au paramétrage** (*Paramétrage › Accès aux rapports*) : journal de pompage, mesures validées, liste de contrôle, tableau des escales ; case « lecteurs limités à la liste ci-dessus » sur un type de document.
* **Tableau des escales du port** (*Tableau du port*) : toutes les escales déclarées — attendues, en rade, à quai, parties depuis moins de 24 h — pour les agences, les parties du port et les parties intéressées, sans rien d'opérationnel : une agence ne voit jamais la cargaison, les quantités, les parties, les tâches ni les documents d'une escale d'une autre agence, et n'ouvre que les siennes.
* **Liste de contrôle navire/terre en ligne** (page *Liste de contrôle*) : les 45 points de l'ISGOTT par partie, cochés par le bord concerné (oui, non, sans objet, valeur, remarque), signature pour le navire et pour le terminal, points répétitifs re-cochés pendant le transfert ; la seconde signature fait la tâche M0:28, pose le jalon et dépose le formulaire `SSSCL` rempli ; un « non » est notifié aussitôt.
* **Avant la déclaration** (*Aperçu*) : ce qui manque, **qui en répond** (organisation, rôle, comptes ou lien), et les moyens de décanter — fournir le document (l'agence peut déposer les certificats au nom du capitaine), confirmer, remettre son accès au capitaine, **relancer** (notification aux comptes, courriel au capitaine, journal). Les refus de point d'arrêt nomment les responsables de la même façon. L'accès capitaine peut être envoyé par courriel, avec la liste de ce que le port attend de lui.
* **Toute action de ces écrans est notifiée à l'équipe** de l'escale, avec des clés groupées pour les saisies répétitives (une notification par bord et par tranche de six heures pour les relevés de pompage).

Pour l'exploitant :

* Migrations `registry.0014` (tables) et `registry.0015` (déclencheurs append-only et sans suppression, valeurs par défaut appliquées aux ports installés sans écraser leurs réglages). Aucune variable nouvelle. Export au format `fluxaa-port-export/1.1` (champs ajoutés seulement). Nouveaux points d'accès de l'API : `tanks/`, `tanks/<id>/review/`, `pumping-sheets/`, `pumping-sheets/<id>/close/`, `pumping-log/` (comparaison), `safety-checklist/`, `safety-checklist/<action>/`, `/api/v1/board/`, action `remind`. Données de démonstration : feuilles et relevés des deux bords, relevés de citernes, liste de contrôle signée sur MT ATLANTIC DEMO (`load_demo`).
* Tests : 125 (`tests/test_loss_control.py`, douze tests) ; test par les écrans : 174 vérifications (`scripts/test_interface.py`, scénario S12 de `docs/spec/14`).

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
