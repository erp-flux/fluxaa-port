# 14. Parcours d'une escale, plan de développement et recette

> Chapitre **rédigé** (FLX-SPEC-003, onglet principal, sections 3 et 11), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.

## 14.1 Parcours d'une escale de bout en bout

*Schéma : parcours d'une escale · 12 étapes, 10 points d'arrêt — dessiné dans FLX-SPEC-003 (onglet principal).*

L'escale est créée par l'agence et avance par les actes des parties ; chaque acte est une tâche faite, un jalon enregistré ou une demande décidée, et les transitions sensibles sont refusées tant que les tâches bloquantes ne sont pas faites. Le tableau donne, étape par étape, qui agit, par quoi, et ce que la plateforme en fait.

| Étape | Qui | Acte dans la plateforme | Effet |
| --- | --- | --- | --- |
| Annonce | AGE | formulaire *Annoncer une escale* : navire, zone, opérations, modules, heures, cargaison, parties | `PortCall` en `DRAFT`, référence attribuée, première étape créée, tâches instanciées depuis les gabarits publiés, échéances calculées ; visible de l'agence et du capitaine seulement |
| Déclaration | AGE | *Déclarer l'escale* après Q88 (M0:02), certificats (M0:03), sanctions (M0:05) | point d'arrêt `DECLARE` ; statut `DECLARED` ; chaque partie notifiée et convoquée (lien sans compte pour une organisation sans compte) ; demande de feu vert créée |
| Vetting et feu vert | TER demande, CAP et APO décident ; CAP décide le feu vert | demandes `VESSEL_ACCEPTANCE` puis `GREEN_LIGHT` | autorisations à validité ; jalon `GREEN_LIGHT` ; statut `ACCEPTED` ou `REJECTED` (motif N3) |
| Poste et créneau | AGE demande, APO décide | demande `BERTH` (fenêtre, tirant d'eau) | point d'arrêt `BERTH_ASSIGN` (acceptation valide exigée) ; poste affecté à l'étape ; statut `PLANNED` ; jalon `BERTH_ASSIGNED` |
| Arrivée, rade, NOR | NAV, AGE | jalons `ARRIVAL`, `ANCHORED`, `NOR_TENDERED` | ATA et NOR posés, statut `APPROACHING`, échéances recalculées ; TER et COM contresignent la NOR |
| Libre pratique, formalités | AGE demande, ADM décide | demandes `FREE_PRATIQUE`, `CUSTOMS_IMMIGRATION` | autorisations ; jalons correspondants ; tâches M0:21, M0:22 terminées |
| Mouvement et pilote | AGE demande, CAP décide ; SVC exécute | demande `MOVEMENT` (arrivée, déhalage, départ) ; jalons `PILOT_ON_BOARD_ARR`, `FIRST_LINE` | points d'arrêt `MOVEMENT_AUTH`, `PILOT_BOARDING` : autorisation en vigueur à l'heure du fait |
| Accostage | SVC (quai, bouée) ou PRE (STS) | `ALL_FAST` ou `STS_ALONGSIDE` | point d'arrêt `BERTHING` ; ATB de l'escale (premier accostage) et de l'étape ; statut `AT_BERTH` |
| Interface navire/terre | TER, NAV, INS | tâches conjointes (réunion pré-transfert, liste de contrôle), jalon `ESD_TEST`, `HOSES_CONNECTED`, jaugeage initial | préparation du point d'arrêt `START_TRANSFER` |
| Transfert | TER (ou PRE en mer), NAV, INS | `TRANSFER_START` … interruptions avec cause … `TRANSFER_END` ; journal de pompage ; mesures | statut `IN_OPERATION` puis `OPS_COMPLETE` ; T0, T1 ; tolérance bord/terre ; alertes |
| Documents finals | INS, AGE, COM | jaugeage final, certificats, instruction documentaire, connaissement, rapport des faits signé | verrou `BL_ISSUE` (instruction écrite + quantité agréée, aucune contestation ouverte) |
| Départ | AGE demande, CAP et ADM décident ; SVC, NAV | `DEPARTURE_CLEARANCE`, formalités de sortie, `PILOT_ON_BOARD_DEP`, `LAST_LINE`, `DEPARTED` | points d'arrêt `DEPARTURE_CLEARANCE`, `PILOT_BOARDING_DEP`, `DEPARTURE` ; ATD ; statut `DEPARTED` ; lien capitaine expire |
| Clôture | AGE demande, CAP clôt | *Demander la clôture*, *Clôturer* | point d'arrêt `CLOSE` : rapport des faits signé, aucune contestation non close, aucune mesure incomplète ; statut `CLOSED`, puis `ARCHIVED` ; tous les liens d'accès éteints |

Une escale qui change de zone (allègement en zone STS puis déchargement à quai, par exemple) répète les étapes *mouvement → accostage → transfert* pour chaque étape planifiée : le déhalage (`SHIFT_START`, statut `SHIFTING`) joue le rôle d'un départ intermédiaire, gardé par l'autorisation de mouvement et par les tâches bloquantes de l'étape suivante (section 6).

## 14.2 Plan de développement recommandé et recette

**Ordre de construction.** Le produit se construit de l'intérieur vers l'extérieur : d'abord les données et leurs garde-fous, puis les services et leurs tests, enfin les écrans et l'API, qui ne font qu'appeler. Chaque incrément est livrable et testable seul.

| Incrément | Contenu | Onglets de référence | Fini quand |
| --- | --- | --- | --- |
| 1. Socle | ports, organisations, utilisateurs, rôles, postes ; authentification, TOTP, limitation ; modèles du registre avec migrations et déclencheurs ; journal chaîné ; chargement des catalogues (`bootstrap_ports`) | 1, 5 | `verify_journal` vert ; `test_database_refuses_update_and_delete` ; catalogues chargés pour SLFNA et TGLFW |
| 2. Escale et tâches | création, déclaration, parties, étapes ; instanciation des tâches par gabarit, zone et étape ; ancres, échéances, cascade ; tâches faites, conjointes, sans objet | 1, 5, 3 (§3, §4) | S1 (escale nominale), S3 (révision des heures sans rafale) |
| 3. Jalons et points d'arrêt | types de jalons, émetteur unique, contresignature, contestation, tacite, rectification, double horodatage ; points d'arrêt et invariants ; alertes | 5, main §6 à §9 | S2 (refus puis autorisation), S4 (tacite) |
| 4. Demandes et autorisations | types paramétrés, formulaires `form_schema`, instruction, décision sous second facteur, autorisations scellées à expiration, code public, commandes de service, prestataire nommé | 5 (§3), 3 (§5) | S7 (refus de vetting), `test_hold_points_require_an_authorization_in_force` |
| 5. Documents, mesures, contestations, échanges | types de documents, dépôt, versions, signatures, verrou du connaissement ; mesures bord/terre/inspecteur, tolérance, journal de pompage ; contestations ; fils d'échange | 1, 3 (§6, §7) | S8 (verrou du connaissement), `test_disputes_never_rejected_and_block_closure` |
| 6. Interface web | gabarit de page, tableau de bord, liste, annonce, fiche d'escale et ses dix onglets, notifications, compte, administration | 2, 3 | `test_pages_render_for_every_role`, parcours des 24 comptes |
| 7. Accès sans compte et terrain | lien capitaine, liens des parties (convocation à la déclaration), page *Votre nom*, appli terrain hors ligne et synchronisation | 2 (§2, §7), 6 (§3) | S6 (conflit hors ligne), `tests/test_links.py` |
| 8. API et intégrations | points d'accès, schéma OpenAPI, jetons, webhooks, export de réversibilité et vérificateur | 6 | `test_api_flow_and_n4_existence_not_disclosed`, `test_port_export_is_verifiable_offline_and_tampering_is_detected` |
| 9. Rapports et formulaires standards | rapport des faits, time sheet, statistiques, indicateurs, les quatorze formulaires dans la structure unique | 4 | `tests/test_forms.py`, `tests/test_stats.py` |
| 10. Domaine N4 | base distincte, dépôt, décision, pièces chiffrées, journal des accès, notification à l'autorité | 1 (§11) | S5 (cloisonnement N4) |
| 11. Modules optionnels | tableau AIS (ingestion, projection, écarts), assistant IA (extraction, revue, résumés, point du port), SMS | 1 (§12), 2 (§9) | `tests/test_ais.py`, `tests/test_ai.py` |
| 12. Exploitation | Docker Compose, sauvegardes et restauration, lanceur de démonstration, données de démonstration (`load_demo`), documentation | — | installation neuve et mise à jour en place sur la pile ; restauration testée |

**Définition du fini (O)** pour tout incrément : les règles sont dans les services et couvertes par un test ; aucune écriture directe depuis une vue ; chaque acte journalisé avec résumé FR et EN ; chaque chaîne visible traduite ; `ruff check`, `makemigrations --check`, `spectacular --validate --fail-on-warn`, `check --deploy` sans constat ; la ligne de traçabilité de chaque exigence mise à jour ; la documentation utilisateur du rôle concerné mise à jour.

**Scénarios de recette.** Les huit scénarios de FLX-CDC-001 sont automatisés et rejoués à chaque livraison ; la recette humaine les rejoue sur les données de démonstration (`docs/GUIDE_UTILISATEUR.md`, démonstration en dix minutes).

| Scénario | Ce qui est vérifié | Test |
| --- | --- | --- |
| S1 escale nominale de déchargement | de l'annonce à la clôture, chaque tâche, jalon, demande et document à sa place ; rapport des faits signé | `test_s1_nominal_discharge_call` |
| S2 point d'arrêt refusé puis levé | pilote à bord refusé sans autorisation de mouvement, message nommant la tâche et le responsable, journal, puis acceptation | `test_s2_hold_point_refusal_then_allowed` |
| S3 révision de l'ETA | toutes les échéances suivent, aucune rafale de notifications, retards retirés en silence | `test_s3_eta_revision_cascade_without_burst` |
| S4 contresignature tacite | silence passé le délai → tacite, mentionnée au rapport des faits, jamais un accord | `test_s4_tacit_countersignature` |
| S5 cloisonnement N4 | un dépôt de sûreté n'apparaît nulle part dans le registre, l'export ni l'API ; accès SUR journalisé | `test_s5_n4_partitioning` |
| S6 saisie hors ligne concurrente | deux saisies du même fait → les deux conservées, conflit signalé, contestation ouverte, saisie différée marquée | `test_s6_offline_conflict_creates_dispute` |
| S7 refus de vetting | motif en N3 visible de l'agence et de l'armateur seulement, aucun poste attribuable | `test_s7_vetting_refusal` |
| S8 verrou du connaissement | sans instruction écrite, sans quantité agréée ou avec contestation de mesure : refus que personne ne lève | `test_s8_bill_of_lading_lock` |
| S9 accès sans compte (1.2) | convocation à la déclaration, nom exigé, saisie nominative, jamais une décision, extinction à la clôture | `tests/test_links.py` (4 tests) |
| S10 escale à deux étapes (1.2) | allègement STS puis quai : planification, déhalage gardé, accostage suivant sans conflit, ancres cohérentes, rapport par étape | `test_offshore_then_quay_in_one_call` |
| S11 formulaires standards (1.2) | structure unique, préremplissage, offre par rôle et opération, dépôt comme document, par lien et par API | `tests/test_forms.py` (4 tests) |

S'y ajoutent les tests d'intégrité (`test_database_refuses_update_and_delete`, `test_journal_chain_detects_tampering`, `test_port_export_is_verifiable_offline_and_tampering_is_detected`), de droits (`test_only_agency_creates_and_rights_on_call`, `test_two_providers_on_one_call_stay_apart`, `test_rival_agency_neither_sees_nor_links_another_agencys_call`…), de sécurité (`tests/test_security.py` : politique de contenu, second facteur, tentatives, jetons, fichiers déposés) et des modules optionnels.

## 14.3 Test de bout en bout par l'interface

En plus de la suite `pytest` (services, vues avec le client de test, API), le dépôt livre un test qui passe **par les
écrans** avec un navigateur réel (Chromium piloté par Playwright) : `scripts/test_interface.py`. Il se joue sur une
installation neuve — bases vides, `load_demo` des deux ports, second facteur imposé (`FLUXAA_MFA_ENFORCED=1`, comme
l'installation de démonstration Windows et la production) — et consigne chaque vérification avec son attendu, son
observé, son résultat et une capture (`results.json`, dossier `shots/`).

```bash
python scripts/test_interface.py --base https://localhost --password Demo-Fluxaa-2026 \
    --secrets deploy/windows/load_demo-TGLFW.log deploy/windows/load_demo-SLFNA.log \
    --mail-log <journal du conteneur web> --out /tmp/test-interface
```

Ce qu'il rejoue, dans l'ordre, avec les comptes de démonstration de Lomé (et l'agence de Freetown pour l'anglais) :

| Partie | Vérifications |
| --- | --- |
| Accès | connexion sans second facteur (agence), avec code TOTP (capitainerie), code faux refusé, limite de tentatives |
| Escale de bout en bout (111 vérifications) | annonce avec un navire nouveau, un poste demandé, l'opération M1 et trois parties dont une organisation créée à la volée ; invitation d'organisations enregistrées ; accès du capitaine (code) et lien d'une partie ; tâches de la déclaration (sanctions, Q88, certificats déposés par le capitaine) ; déclaration ; vetting demandé par le terminal et décidé par la capitainerie **→ acte déposé** ; feu vert **→ acte** et vérification publique de son code ; poste attribué par l'autorité portuaire **→ acte** ; services nautiques commandés, confirmés, exécutés ; libre pratique et formalités par les administrations (second facteur demandé au moment de décider) **→ actes** ; arrivée et NOR **→ notice de disponibilité déposée**, contresignée par le terminal ; autorisation de mouvement **→ acte** ; pilote à bord, première amarre, all fast, passerelle **→ À quai** ; **point d'arrêt** : début de transfert refusé tant que la réunion, la liste de contrôle et l'essai ESD manquent ; signatures conjointes terminal / capitaine, ESD, tâches M1, documents de l'agence et du capitaine, raccordement ; transfert, débit de régime, journal de pompage, interruption avec cause de la liste fermée et sa fin, **contestation d'un jalon par le capitaine**, topping-off, fin, vidange, débranchement ; mesure bord / terre / inspecteur et écart ; réponse et clôture de la contestation, contestation libre ; fil d'échange et réponse ; bon de réception déposé et signé ; page Formulaires de chaque partie et émission (avis d'arrivée, SSSCL, certificat de quantité, ordre de mouvement, bordereau de déchets), actes visibles comme déposés chez la capitainerie, formulaires de l'armateur ; partie sans compte par son lien (nom, consultation, dépôt, tableau de bord refusé) ; étape suivante planifiée puis annulée ; déchets ; formalités de sortie **→ acte** ; **congé de départ → acte lu par l'agence** ; appareillage **→ Navire parti** ; rapport des faits **→ SOF et time sheet déposés**, signés par le capitaine et le terminal ; clôture demandée, contestation close par la capitainerie, clôture, archivage ; export de l'escale vérifié hors plateforme |
| Sûreté N4 | dépôt confidentiel par l'agence, liste, décision, confirmation d'embarquement, journal des accès ; l'agence n'atteint pas l'espace (introuvable) ; rien n'apparaît dans le journal de l'escale |
| Sécurité | aucun bouton de décision pour l'agence ; une décision forcée (POST direct) est refusée ; jeton d'API faux refusé |
| API | jeton créé depuis Mon compte ; `me`, `calls`, `forms`, émission d'un formulaire, `sync` (saisie hors ligne), `journal`, documentation interactive |
| Freetown | tableau de bord, formulaires et actes des escales de démonstration en anglais |
| Parcours des écrans | pour chacun des onze rôles à compte : pages communes, chaque escale visible (dix onglets, appli terrain, formulaires et quatre aperçus), rapport des faits et export quand ils sont offerts, pages propres (administration pour la direction, espace sûreté, AIS, statistiques, pilotage) — aucune erreur serveur, aucune page introuvable ; le capitaine par code (dix onglets, formulaires, tableau de bord refusé) ; les pages publiques |

Résultat de la révision 1.3.1 (10 novembre 2026) : 148 vérifications, 148 passées. Le test a révélé l'erreur serveur
de l'annonce avec un navire nouveau, corrigée ; et il a conduit au rattrapage des documents générés à la mise à niveau
d'une installation existante (`backfill_generated_documents`). Le rapport détaillé, écran par écran, est livré avec
le produit (`fluxaa-port-rapport-de-test.pdf`). Le test crée une escale `MT TEST E2E …` et des documents sur les
escales de démonstration 0001 et 0002 : il se joue sur une installation de test, jamais en production.
