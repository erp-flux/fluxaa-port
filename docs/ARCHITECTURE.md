# Architecture de FLUXAA Port

Ce document décrit comment la plateforme est construite et pourquoi. Il complète le cahier des charges FLX-CDC-001 (§5, orientations d'architecture) et consigne les **arbitrages** faits là où les documents du corpus se contredisaient.

## 1. Vue d'ensemble

```
 Navigateurs (bureau, mobile)           Appli terrain (PWA hors ligne)        Systèmes tiers
        │  HTML + HTMX                          │  JSON /api/v1/…/sync              │  API v1, webhooks
        ▼                                       ▼                                   ▼
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │  Django 5.2 (gunicorn)                                                                   │
 │  apps.core      ports, organisations, utilisateurs, postes, 2FA, garde-fous d'écriture   │
 │  apps.registry  escales, tâches, jalons, demandes, documents, mesures, contestations,    │
 │                 échanges, alertes, journal chaîné, exports, tableau de bord              │
 │  apps.api       API publique v1 (DRF, schéma OpenAPI, Redoc)                             │
 │  apps.secure    domaine sûreté N4 (dépôt en écriture seule, chiffré)                     │
 │  apps.ai        assistance IA optionnelle (EF-17), jamais décisionnaire                   │
 └───────────────┬───────────────────────────────────────────────┬──────────────────────────┘
                 │ alias « default »                              │ alias « secure »
                 ▼                                                ▼
        PostgreSQL — registre opérationnel              PostgreSQL — domaine N4
        (déclencheurs append-only / no-delete,           (base distincte, clés distinctes,
         rôle d'exécution sans DELETE)                    même garde-fous)
                 ▲
                 │ toutes les minutes
        run_scheduler : rappels / retards / escalades, contresignatures tacites,
        expiration des autorisations, résumés quotidiens, webhooks
```

Le choix technique est volontairement sobre : un monolithe Django, deux bases PostgreSQL, du HTML rendu côté serveur enrichi d'HTMX, aucun framework JavaScript. Une équipe de maintenance réduite peut le reprendre ; l'intégrité ne dépend d'aucun composant exotique.

## 2. Les invariants et où ils sont tenus

| Invariant | Mécanisme |
|---|---|
| **Aucune suppression, aucune altération** (règle 3, EF-3.1, ENF-3.6) | Trois couches indépendantes : (1) modèles `AppendOnlyModel` / `NoDeleteModel` (`apps/core/guards.py`) qui lèvent une erreur ; (2) déclencheurs PostgreSQL `fluxaa_refuse()` installés par migration sur toutes les tables du registre, du domaine N4 et des traces de l'assistant (UPDATE, DELETE ou TRUNCATE refusés selon la nature de la table) ; (3) commande `apply_db_grants` : le rôle utilisé par l'application n'a pas le privilège `DELETE`. Un superutilisateur qui contournerait les déclencheurs serait détecté par la chaîne (§3). |
| **Journal opposable** (ENF-4.1) | Chaque acte produit une `JournalEntry` dont l'empreinte SHA-256 couvre le contenu et l'empreinte précédente (chaîne par port). Les consultations, téléchargements et exports alimentent une seconde chaîne (`AuditEntry`). `manage.py verify_journal` et `scripts/verifier_export.py` recalculent les deux. |
| **Émetteur unique** (règle 1) | Le type de jalon, la partie d'une mesure ou le rôle d'une tâche fixent qui saisit ; les autres contresignent ou contestent. |
| **Qui demande ne décide pas** (règle 2) | Contrôle par rôle **et** par personne dans `decide_request` ; un type de demande dont un rôle serait à la fois demandeur et décideur est refusé au paramétrage. |
| **Besoin d'en connaître** (règle 4) | `services/rights.py` porte la matrice FLX-SPEC-001 §5 et les quatre niveaux N1–N4 ; l'interface, l'API, les exports et l'assistant passent tous par les services, jamais par des requêtes directes. |
| **Droits par rôle sur l'escale** (règle 5) | `CallParty` (organisation × rôle × escale, dates, révocation) ∩ rôles que la personne peut exercer. |
| **Toute attente est une tâche** (règle 6) | Les gabarits instancient les tâches à la création ; les échéances sont relatives à des ancres (ETA, ETB, ATB, T0, T1, ATD, NOR) et recalculées en cascade. |
| **Authentification forte** (ENF-3.1) | Double authentification (TOTP) exigée dès la connexion pour CAP, APO et SUR (`FLUXAA_MFA_REQUIRED_ROLES`) et pour tout administrateur (paramétrage : vérification de moins de 8 h ; une seule page de connexion, tentatives limitées), sur les pages web (`MfaEnforcementMiddleware`) **comme** sur l'API appelée depuis le navigateur (`MfaSessionAuthentication`) : un mot de passe seul n'ouvre ni l'une ni l'autre. Toute décision la redemande (moins de 8 h, ou en-tête `X-MFA-Code` par l'API) ; un jeton d'API ne se crée qu'après vérification. |
| **Pages durcies** (ENF-3) | `Content-Security-Policy` sur chaque page HTML : scripts servis par la plateforme uniquement, aucun script en ligne ni tiers, aucun encadrement (`frame-ancestors 'none'`) ; en plus HSTS, `nosniff`, `Referrer-Policy`, cookies `Secure`. Un document HTML déposé est servi avec une politique qui interdit tout script. |

## 3. Le journal chaîné

```
empreinte(n) = SHA-256( JSON canonique de { seq, port, call, at, actor_*, action, object_*,
                                            visible_roles, summary_fr, summary_en, payload,
                                            prev_hash = empreinte(n-1) } )
jeton d'horodatage(n) = HMAC-SHA256(clé de scellement, { digest, at, provider })
```

* Le JSON canonique trie les clés, n'échappe pas l'Unicode et n'a pas d'espaces (`apps/core/crypto.py`).
* L'écriture verrouille la tête de chaîne du port (`ChainHead`, `SELECT … FOR UPDATE`) : deux écritures concurrentes ne peuvent pas produire deux successeurs.
* Un refus de point d'arrêt est journalisé **hors** de la transaction annulée (`with_refusal_log`) : la tentative reste au dossier même si l'action échoue (EF-11.3).
* L'horodatage est local (HMAC) en attendant l'arbitrage du **point ouvert O04** ; le fournisseur `rfc3161` est prévu dans `services/journal.py` et s'active par configuration, sans réécriture du journal.

## 4. Modèle de données (registre)

| Objet | Rôle | Garde-fou |
|---|---|---|
| `PortCall` | l'escale, son statut, ses ancres estimées et réelles | jamais supprimée, référence immuable |
| `CallParty` | organisation × rôle sur l'escale | jamais supprimée, révocable |
| `CallTemplate` → `TemplateVersion` → `TemplateTask` | catalogue FLX-SPEC-002, versionné | version publiée figée |
| `Task`, `TaskSignature` | tâches instanciées, signatures conjointes | tâche jamais supprimée, signatures append-only |
| `MilestoneType`, `Milestone`, `MilestoneSignature` | jalons à émetteur unique, contresignatures | append-only ; rectification = nouveau jalon lié |
| `RequestType`, `ServiceRequest`, `Authorization`, `AuthorizationEvent` | moteur unique de demandes ; autorisations scellées à code public | autorisation append-only, expiration obligatoire |
| `DocumentType`, `Document`, `DocumentSignature` | pièces versionnées et empreintes | contenu figé (déclencheur sur l'empreinte) |
| `Measurement`, `MeasurementValue` | quantités bord / terre / inspecteur | valeurs append-only, correction = nouvelle valeur liée |
| `TankReading`, `TankReadingReview` | relevés des citernes du navire (par le navire) et des bacs à terre (par le terminal) : niveau, température, eau libre, densité, TOV, GOV, VCF, GSV, poids ; validation ou rejet par l'inspecteur, visibles des autres parties une fois validés (1.4) | append-only (déclencheurs), correction = nouveau relevé lié au relevé rejeté |
| `PumpingLogSheet`, `PumpingLogEntry` | journal de pompage par bord : feuille (citerne, niveaux, m³/m, densité, VCF, quantité et débit prévus, heures estimées) et relevés horaires (niveau, volumes horaire et cumulé, tonnes, débit, pression, température) ; comparaison terre − bord calculée (`measurements.compare_sides`) | feuille jamais supprimée, relevés append-only |
| `SafetyChecklist`, `SafetyCheckAnswer`, `SafetyChecklistSignature` | liste de contrôle navire/terre en ligne : points copiés du référentiel `ssscl.py` à l'ouverture, réponses de chaque bord (répétitions comprises), une signature par bord ; signée des deux → tâche M0:28, jalon `SSSCL_SIGNED`, formulaire `SSSCL` déposé | liste jamais supprimée (annulable avec motif), réponses et signatures append-only |
| `ReportAccess` | qui lit chaque rapport tenu en ligne (journal de pompage, mesures validées, liste de contrôle, tableau des escales), réglé au paramétrage | jamais supprimé ; défauts du catalogue à défaut de ligne |
| `Dispute`, `DisputeEntry` | contestations (jamais « rejetées ») | append-only |
| `Thread`, `Message` | échanges rattachés à l'escale | append-only |
| `Alert`, `Notification` | alertes (pièces du dossier) et notifications dérivées | alerte append-only, unicité par destinataire et événement |
| `JournalEntry`, `AuditEntry`, `ChainHead` | les deux chaînes | append-only |
| `MasterAccessLink` | accès sans compte : du capitaine (jusqu'au départ) ou d'une partie convoquée à la déclaration — terminal, inspecteur, armateur, prestataire, service nautique — (jusqu'à la clôture) ; jeton et code hachés, titulaire nominatif, rôle et organisation portés par le lien | jamais supprimé, révocable ; un lien ne décide jamais (rôles CAP/APO/ADM/SUR/DIR/AGE refusés) |
| `CallStage` | étapes d'une escale qui change de zone (rade → STS → quai…) : zone, poste, opérations, fenêtre, accostage et départ de l'étape ; les jalons et les tâches d'une étape ultérieure y sont rattachés | jamais supprimée, annulable avec motif ; une seule étape en cours |

Les libellés métier (tâches, jalons, causes, types de demande et de document) sont des **données bilingues** (`*_fr`, `*_en`), pas des chaînes du code (ENF-7).

### 4.1 Généralisation (version 1.5)

* **Nature de cargaison et type de navire** — `PortCall.cargo_kind` (`CargoKind` : LIQUID, DRY, CONTAINER, GENERAL, RORO, OTHER), `Vessel.vessel_kind` (`VesselKind`), unités `QUANTITY_UNITS` filtrées par `UNITS_BY_CARGO`. `CallTemplate.cargo_kinds` et `TemplateTask.cargo_kinds` (JSON, vide = toutes) décident des gabarits offerts et des tâches du socle commun instanciées (`calls._check_templates`, `instantiate_tasks`). Le catalogue des autres cargaisons est dans `apps/registry/catalog_cargo.py` (gabarits MB1, MB2, MC1, MG1, MR1, MX1 ; feux verts 09b, 09c, 09d, 31b ; jalons ; types de document ; points d'arrêt) et fusionné dans `catalog.py` ; la migration `registry.0017_catalogue_1_5` publie une nouvelle version de M0 par port sans toucher aux escales en cours. Les listes de contrôle par nature sont dans `apps/registry/checklists.py` (BLU, CARGO ; ISGOTT reste dans `ssscl.py`) et `SafetyChecklist.standard` fige celle d'une liste ouverte. Les formulaires des autres cargaisons sont dans `services/forms/cargo.py` ; `Form.cargo_kinds` et `Form.templates` gouvernent l'offre (`forms.offered`).
* **Validité de l'annonce** — `PortCall.validity_days`, `valid_until`, `expired_at`, `renewed_from` ; `Port.default_validity_days`, `max_validity_days` ; `calls.validity_for`, `expire_call`, `renew_call` ; `scheduler.watch_validity` (rappels 72 h / 24 h, obsolescence des escales pas encore à quai — `EXPIRABLE_STATUSES` —, dépassement quotidien des escales à quai) ; `PortCall.billing_basis()` exposé par la fiche, le time sheet, l'API et l'export (`1.2`). Le statut `EXPIRED` est terminal.
* **Feux verts** — `TemplateTask.green_light` / `Task.green_light` ; les feux verts sont des tâches du socle commun gardant des points d'arrêt (`HoldPointRequirement`), donnés par `tasks.complete_task` (COM admis pour le sien) et retirés par `tasks.withdraw_green_light` (motif, journal, notification, réouverture de la tâche) ; `tasks.green_lights(call)` en donne l'état ; celui de la capitainerie reste la décision sur la demande `GREEN_LIGHT`.
* **Accès contrôlé** — `CallParty.access` (`FULL`, `PARTIAL`, `READ`) et `scopes` ; `rights.is_principal_agent`, `access_of`, `allowed_tabs`, `can_act_in`, `require_act` ; chaque action d'écran est rattachée à un onglet (`views.ACTION_SCOPES`) et chaque vue de sous-ressource de l'API porte son onglet (`CallAPIView.scope`) : hors accès, 404 en lecture et refus explicite en écriture ; `views._strip_acts` retire de l'écran tout acte qu'une partie ne peut pas faire. L'agent principal (`PortCall.agency`) seul déclare, révise, annule, clôture et refait l'annonce ; `AGENCY_INVITABLE_ROLES` comprend AGE pour les agences associées.
* **STS en deux escales** — `PortCall.sts_role` (`DONOR`, `RECEIVER`) ; `calls._create_sts_partner` crée l'escale du partenaire sous son agence, reliée (`linked_call`), l'agence annonçante inscrite comme agence associée ; `measurements.counterpart_entries` prend le journal bord du partenaire comme série « terre » de la comparaison.
* **Documents attendus** — `tasks.request_documents` crée des tâches F non bloquantes (`D<n>`, `requested_at_creation`, type `OTHER` pour un libellé libre) à l'annonce (`expected_documents`, `custom_documents`) ou depuis l'onglet Documents.
* **Conférence de placement et plan d'occupation** — `services/board.py` (`rows`, `grouped`, `to_csv`, `occupation`, `occupation_csv`), `Port.board_shows_cargo` ; pages `/escales/port/` et `/escales/port/occupation/`, API `board/` et `board/occupation/`.
* **Grille de vetting** — limites d'acceptation du poste (`Berth.max_*`, `min_*`) comparées aux caractéristiques du navire (`Vessel.displacement_t`, `manifold_height_m`, `air_draft_m`, `crane_swl_t`, `loa_m`, `beam_m`, `draft_m`, `built_year`, `dwt`) par `forms/cargo.vetting_rows` / `vetting_verdict`.

### 4.2 L'annonce s'adapte à l'opération (version 1.6)

* **Fiche d'intention par modèle** — `CallTemplate.intake_schema` (même grammaire que `RequestType.form_schema` ; catalogue `catalog.INTAKE`, installé par `bootstrap_ports` et par la migration `registry.0018` pour les ports existants) ; `PortCall.operation_details` garde les réponses par code de modèle ; `services/intake.py` (`templates_with_intake`, `parse_intake` / `parse_intake_mapping`, `declared`, `prefill_for_request`) les lit, les type, les montre et en préremplit les demandes — seulement depuis le modèle dont une tâche lève la demande, plus les faits du navire (`SHARED_KEYS`) et ce que l'escale dit elle-même (produit, quantité, poste, navire du lien) ; `requests.create_request` reçoit les valeurs préremplies telles que soumises, jamais à l'insu du demandeur. Les réponses suivent la règle du produit et de la quantité (`rights.can_see_full_call`) : ni l'aperçu, ni l'API, ni le préremplissage ne les donnent à un prestataire.
* **Accostage à couple à l'annonce** — `calls.create_call(db_partner=…)` : escale du port (toute agence vue sur la conférence, `_on_board`), navire enregistré ou nouveau (`_create_db_partner` crée l'escale sous son agence, l'agence annonçante en agence associée) ; lien réciproque entre escales de la même agence, **à sens unique** vers l'escale d'une autre agence jusqu'à l'autorisation d'accostage à couple de la capitainerie (`complete_reciprocal_link`, appelé par `requests.decide_request`) ; `_notify_partner_link` avertit l'agence, le capitaine et la capitainerie de l'autre escale.
* **Partenaire d'une autre agence, navire-mère** — un transbordement comme un accostage à couple peut désigner l'escale d'une autre agence vue sur la conférence (`_on_board`) : lien à sens unique, notification (`_notify_partner_link`), rôle STS inverse pris d'office (`_inverse_sts_role`, `_check_sts_roles`) ; `link_confirmed` (même agence, lien en retour, ou autorisation `STS_ZONE` / `DOUBLE_BANKING` approuvée) garde la lecture du journal du partenaire (`measurements.counterpart_entries`) ; `incoming_links` liste sur une escale celles qui la désignent — sans champ nouveau : un navire-mère garde un `linked_call`, ses navires-filles pointent vers lui.
* **Agence de l'autre navire, annonce tout ou rien** — `calls.partner_agency` : une agence du port, ou une agence nommée sur place (`register_organization`, rôle AGE, retrouvée par son nom si elle existe) ; `calls.agency_has_account` et `_tell_port_of_agency_without_account` avertissent les administrateurs fonctionnels du port (`notifications.notify_port_admins`, notification sans escale) quand l'escale créée relève d'une agence pour laquelle personne ne peut encore se connecter. L'annonce s'exécute en une transaction (`views._announce` sous `transaction.atomic`, `@transaction.atomic` sur `POST /api/v1/calls/`) : un refus n'enregistre rien en chemin et le formulaire revient tel que saisi.
* **Lecture avant la demande** — `calls.berth_occupation` (qui tient ou attend le poste sur la fenêtre), `forms/cargo.vetting_rows_for` (le navire contre les limites d'acceptation du poste, sans escale), servis par le fragment HTMX `views.berth_occupation` ; `apps/core/parties.PARTIES_BY_OPERATION` (les parties qu'appelle chaque modèle) proposé par l'annonce.
* **Partout ailleurs** — aperçu (*Déclaré à l'annonce*, *Accostage à couple*), API (`operation_details`, `declared`, `linked_call.reciprocal`, `double_banking` à la création), export `fluxaa-port-export/1.3` (`link_kind`, `operation_details`), reprise d'une annonce et partenaire STS / couple (réponses copiées).

## 5. Points d'arrêt

Depuis la 1.5, `MOVEMENT_AUTH` et `BERTHING` exigent le feu vert de la sûreté et de la base navale (M0:09b), `START_TRANSFER` ceux du terminal (M0:09c) et du mandant (M0:09d), et, pour les cargaisons autres que liquides, le poste prêt (M0:31b) et les tâches des gabarits MB1, MB2, MC1, MG1, MR1, MX1 ; `BL_ISSUE` exige MB2:B2.16 pour le vrac sec. Le retrait d'un feu vert referme le point d'arrêt sans autre mécanique : la tâche redevient à faire.

Deux sources, évaluées par `services/holdpoints.py` avant chaque transition gardée :

1. **paramétrables** (`HoldPoint` + `HoldPointRequirement`) : la liste des tâches qui doivent être faites — déclaration, feu vert, attribution de poste, autorisation de mouvement, pilote à bord (arrivée et départ), début de transfert, accostage à couple, travaux par point chaud, autorisation de départ, clôture ;
2. **codés et non paramétrables** : verrou du connaissement (EF-7.4 : instruction documentaire 2.16, accord sur la quantité, aucune contestation de quantité ni écart hors tolérance), acceptation de navire valide pour l'attribution de poste et le feu vert (PRO-MAR-001 §3.2.2.1), clôture impossible avec une contestation ouverte ou une mesure incomplète.

Un refus nomme chaque tâche manquante, son rôle responsable et l'action attendue ; il est journalisé (EF-11.2, EF-11.3) et l'écran l'affiche dans un encadré dédié.

## 6. Domaine sûreté N4

* Application `apps/secure`, **base de données distincte** (alias `secure`, routeur `fluxaa/db_router.py` qui interdit toute relation avec le registre).
* Dépôt en écriture seule depuis l'escale (agence, capitaine, sûreté, capitainerie) : le déposant reçoit un récépissé ; rien n'apparaît dans l'escale, son journal, le tableau de bord ou les exports.
* Contenu chiffré par des clés propres (`FLUXAA_N4_KEYS`, Fernet multi-clés pour la rotation).
* Accès réservé à SUR et CAP ; tout autre rôle reçoit un 404 qui ne révèle pas l'existence. Chaque accès est inscrit nominativement dans un journal chaîné propre au domaine ; un accès par un autre rôle que l'autorité de sûreté lui est notifié par courriel, sans détail.

## 7. Temps, langues, notifications

* Heures stockées en UTC, affichées dans le fuseau du port (`Port.timezone`), fuseau rappelé à l'écran. Les heures saisies dans un formulaire sont interprétées dans le fuseau du port.
* Interface entièrement bilingue (catalogue `locale/fr`, chaînes sources en anglais) ; la langue suit le profil, à défaut la langue du port (Lomé : français, Freetown : anglais).
* Les nombres saisis acceptent la virgule décimale (`apps/core/numbers.py`) ; une valeur ambiguë (« 32,046.310 ») est refusée plutôt qu'interprétée.
* Notifications **toujours dérivées** d'un acte ou d'une échéance ; une seule par destinataire et par événement (contrainte d'unicité) ; résumé quotidien par défaut ; temps réel réservé au bloquant et aux escalades ; SMS pour les seules escalades. Les saisies répétitives du contrôle des pertes (relevés de pompage, validations de citernes) sont notifiées par clés groupées — un bord et une fenêtre de six heures, une mesure et une heure — pour que l'équipe soit tenue informée sans être inondée ; un écart hors tolérance, un relevé rejeté, un point de la liste de contrôle à « non » et une relance partent en temps réel (`docs/spec/10-notifications-et-planificateur.md`).

## 8. Terrain et hors ligne

L'appli terrain (`/escales/<id>/terrain/`, application web progressive) charge un paquet de l'escale (`/api/v1/calls/<réf>/field-bundle/`), enregistre les saisies localement avec l'heure de l'appareil, puis les rejoue dans l'ordre chronologique (`/sync/`). Le serveur conserve les deux horodatages, marque « saisie différée » ce qui arrive après le seuil (`FLUXAA_DEFERRED_THRESHOLD_SECONDS`), et transforme toute saisie concurrente en contestation au lieu d'écraser (EF-14.4, S6). Le formulaire de jalon permet aussi la **ressaisie de la procédure papier de secours**, marquée différée (ENF-1).

## 9. API et intégrations

API REST v1 sous `/api/v1/`, schéma OpenAPI à `/api/schema/`, documentation à `/api/docs/` — détail dans [API.md](API.md). Les entrées N1 du journal peuvent être publiées vers le guichet unique ou le PCS par webhooks signés (HMAC) et rejoués en cas d'échec ; aucune formalité FAL n'est reproduite.

## 10. Assistance IA (EF-17)

`apps/ai` est désactivé par défaut. Il ne s'active que si l'exploitant de la plateforme a fourni la clé d'API **et** la référence de la clause contractuelle avec le fournisseur (`FLUXAA_AI_PROVIDER_AGREEMENT`), **et** que le port l'a activé avec la référence de son propre accord. Quatre usages :

| Usage | Ce que fait l'assistant | Ce que fait la personne |
|---|---|---|
| Extraction (Q88, certificats, connaissement) | propose des valeurs, citées du document | coche, corrige, valide ou écarte ; la fiche navire n'est mise à jour qu'à ce moment, sous son nom |
| Revue de cohérence | liste des constats, à partir de ce que le rôle voit | décide de signaler un constat comme alerte (sous son nom) |
| Résumé d'un échange | un résumé affiché au lecteur | rien n'est enregistré dans l'escale |
| Remarques du rapport des faits | un projet de texte | relit, modifie, génère le rapport, que le capitaine et le terminal signent |

Garanties vérifiées par les tests : aucun code de `apps/ai` n'importe le domaine N4 ni n'appelle une fonction de décision, de signature ou de clôture ; les personnes sont remplacées par leur rôle dans les données envoyées ; chaque requête laisse une trace append-only (`AssistantRun` : qui, quoi, empreinte des données envoyées, inventaire des objets) ; une panne du fournisseur n'affecte jamais le registre.

## 11. Arbitrages entre documents du corpus

La hiérarchie du CDC §0.2 a été appliquée (PRO-MAR-001 > FLX-SPEC-001 > FLX-SPEC-002 > CDC > maquettes).

| Sujet | Contradiction | Arbitrage retenu |
|---|---|---|
| Saisies du capitaine | EF-13.3 : le capitaine n'a « aucun droit de création d'objet, hors contestation » ; FLX-SPEC-001 §7 le désigne émetteur de jalons (mouillage, appareillage, passerelle…) et la procédure lui demande ses certificats | FLX-SPEC-001 prévaut : le capitaine enregistre **ses** jalons et fournit **les documents qui lui sont demandés** ; il ne crée ni demande ni échange |
| Contresignature de la NOR par l'affréteur | EF-12.5 : COM sans droit de saisie sur les événements ; §7 : COM contresigne la NOR | contresigner n'est pas saisir : COM contresigne ou conteste, ne crée aucun événement |
| Visibilité des contestations | chaque partie doit savoir qu'une contestation bloque la clôture ; les exposés sont bilatéraux | l'en-tête est visible des parties de l'escale ; les exposés ne le sont que des deux parties et de la capitainerie |
| Module MA1 (sûreté) | tâches de sûreté dans un gabarit d'escale vs cloisonnement N4 strict | MA1 est entièrement traité dans le domaine N4 (dépôt en écriture seule) ; aucune tâche N4 dans le registre |
| Rôle du superviseur STS (POAC) | absent de la liste des rôles | rattaché au rôle PRE (prestataire), qui ne voit que son service |
| Pilote à bord au départ | non listé comme point d'arrêt | ajouté (`PILOT_BOARDING_DEP`, tâche M0:34 — autorisation de départ délivrée) par cohérence avec l'arrivée |
| Tâches d'interface quai en rade ou en zone STS | M0 décrit l'accostage à quai pour toutes les escales | tâches M0:12, 18, 25–31, 35 limitées aux quais et bouées ; tâche 35b pour la rade et les zones STS |
| Statut « À quai / En opération » | un seul statut dans EF-1.2 | deux statuts (`AT_BERTH`, `IN_OPERATION`) : le tableau de bord et les indicateurs distinguent l'attente à quai du transfert |
| Complétude d'une mesure | EF-8.1 exige bord et terre, l'inspecteur « le cas échéant » | complète si bord **et** terre ; tous les écarts par paire sont affichés, la tolérance s'applique à l'écart bord/terre |
| Contestation « Répondue » et clôture | critère d'EF-4.3 : clôture refusée tant qu'une contestation est « Ouverte » ; EF-4.1 distingue « Répondue » | une réponse ne règle rien : la clôture de l'escale exige que chaque contestation soit **close** (avec ou sans accord). Aucun blocage définitif : la capitainerie peut toujours la clore sans accord |
| Verrou du connaissement et contestation de quantité | EF-7.4 exige « l'accord sur la quantité » | une contestation de quantité non close (ouverte ou répondue) maintient le verrou ; close avec ou sans accord, elle ne le maintient plus et reste au dossier (journal, rapport des faits, export) |
| Plusieurs prestataires sur une escale | EF-5.2 : une tâche est assignée à un rôle et toute personne titulaire du rôle peut la traiter ; FLX-SPEC-001 : PRE « ne voit que son service » | les tâches PRE restent assignées au rôle (EF-5.2) ; tout ce qui a un auteur — documents, demandes de service (le prestataire est désigné quand plusieurs participent), jalons, contestations — est cloisonné par organisation |
| Plusieurs terminaux, ou plusieurs prestataires en mer | FLX-SPEC-001 §7 : le côté terre (terminal à quai, opérateur en mer) émet ses jalons, son chiffre et contresigne ceux du bord ; le corpus ne prévoit pas qu'ils soient plusieurs | une seule organisation parle au nom du côté terre : d'office si elle est seule de son rôle, sinon celle que l'agence ou la capitainerie désigne (`CallParty.shore_side`, journalisé). Sans désignation, aucune ne le peut : la plateforme refuse plutôt que de laisser une organisation s'attribuer ce rôle |
| Alertes au rapport des faits | EF-6.4 : chaque alerte figure au rapport des faits ; les alertes sont adressées à des rôles | le rapport des faits les reprend toutes, comme l'exige EF-6.4 ; l'export d'une partie ne contient que les alertes qui lui sont adressées |
| Convocation des parties et accès sans compte | EF-13 ne prévoit d'accès sans compte que pour le capitaine ; le port demande que chaque acteur reçoive, dès la déclaration, son lien valable jusqu'à la clôture | le lien d'accès est généralisé aux rôles qui ne décident pas (TER, INS, COM, PRE, SVC), émis d'office à la déclaration pour une organisation sans compte, nominatif à la première ouverture, valable jusqu'à la clôture ; les rôles qui décident gardent un compte avec second facteur (ENF-3.1 inchangé) |
| Escale à plusieurs zones | le corpus décrit une zone par escale (EF-1.1 : zone demandée) ; les escales réelles passent de la rade au STS puis au quai | la zone devient celle de l'**étape en cours** (`CallStage`) ; les ancres de l'escale gardent leur sens (ATB = premier accostage, T0 = premier début, T1 = dernière fin, ATD = appareillage final) ; le déhalage est un jalon des services nautiques (`SHIFT_START`, statut `SHIFTING`) gardé par l'autorisation de mouvement et les tâches de l'étape suivante |
| Formulaires standards | EF-7.3 : le rapport des faits est généré depuis le registre ; les autres pièces sont déposées | les formulaires standards ([FORMULAIRES.md](FORMULAIRES.md)) — soixante-seize, une famille par partie émettrice — sont générés dans une structure unique, préremplis depuis le registre pour ce qu'il connaît, déposés comme documents générés de leur type ; chaque partie émet ainsi depuis la plateforme les documents que l'escale lui demande (dont l'acte écrit de chaque décision), et le papier signé revient comme version du même document |
| Parties de l'escale | FLX-SPEC-001 §4 : douze rôles ; l'agence invite terminal, inspecteur, armateur, prestataires | la liste des parties est **ouverte** : les rôles portent les droits, la **nature** d'une organisation (`Organization.kind`, suggestions non exhaustives de `apps/core/parties.py`) dit ce qu'elle est ; l'agence invite autant d'organisations qu'il en faut, enregistrées ou nouvelles, à l'annonce, dans l'onglet Parties ou par l'API (`calls.register_organization`, journalisé) |

## 12. Points ouverts qui conditionnent la mise en service

| Point | Effet dans le code |
|---|---|
| **O04** horodatage qualifié et niveau de signature | fournisseur local actif ; interface RFC 3161 prête ; signatures scellées et nominatives, niveau juridique à confirmer |
| **O05** hébergement | conteneurs prêts ([DEPLOIEMENT.md](DEPLOIEMENT.md)) ; localisation et exigences du port à arbitrer |
| **O06** périmètre exact du pilote | deux ports et le catalogue complet sont chargés ; un port peut désactiver des gabarits |
| Liste fermée des causes d'interruption | 17 causes proposées, à négocier avec les parties puis à ajuster dans le paramétrage |
| Seuils entre crochets du CDC | valeurs par défaut dans `Port` (délais, tolérance, seuils), modifiables sans code |
| Noms et limites des postes de Freetown et de Lomé | postes de démonstration à confirmer par chaque capitainerie |
| Test d'intrusion et notification d'incident (ENF-3.7, ENF-3.8) | à réaliser avant la mise en service ; garanties, vérifications déjà faites et limites connues : [SECURITE.md](SECURITE.md) |

## 13. Modules transverses : tableau AIS, statistiques, assistant du port

Trois modules ajoutés pour un déploiement dans plusieurs ports. Ils lisent le registre ; aucun n'y écrit un acte.

**Tableau AIS** (`apps/ais`). Deux tables hors registre : `VesselPosition` (une ligne par rapport de position, purgée après `Port.ais_retention_days`) et `VesselStatic` (dernières données statiques par MMSI). L'ingestion (`services.ingest`) normalise et déduplique ce que donnent trois sources : la commande `ais_listen` (trames NMEA d'un récepteur local sur UDP ou TCP, décodées par pyais ; ou le flux aisstream.io par websocket, cadré sur le rectangle du port), ou `POST /api/v1/ais/positions/` par un compte d'intégration de périmètre `ais`. La page `/carte/` projette le rectangle du port (`Port.map_*`, projection équirectangulaire corrigée du cosinus de la latitude) en SVG, dessine les postes et zones (`Berth.latitude/longitude/radius_m`) et la dernière position de chaque navire entendu en 24 h, rapprochée des escales par MMSI (`Vessel.mmsi`) ou IMO (données statiques). `services.discrepancies` compare déterministement l'image AIS et le registre (arrivée non enregistrée, sortie non enregistrée, silence, navire toujours amarré après appareillage) et affiche des **questions**, jamais une écriture : l'alerte de corroboration d'EF-3.6 (`corroborate_ais`) reste le seul effet d'une observation AIS, et seulement sur appel explicite. La visibilité de l'escale à côté d'un navire suit `rights.call_queryset_for_user`.

**Statistiques** (`apps/registry/services/stats.py`, `/statistiques/`). Calcul à la demande sur une période (mois d'ETA pour les escales, mois de l'événement pour décisions, contestations et signatures), à partir des mêmes fonctions que les indicateurs d'EF-10.2 (`reports.time_sheet`, `reports.interruptions`). Rien n'est stocké ; l'export CSV reprend chaque tableau ; chaque consultation est journalisée. Graphiques en SVG inline (`_bar_chart.html`, nombres non localisés).

**Contrôle des pertes, interface navire/terre et tableau des escales** (version 1.4, `apps/registry/services/measurements.py`, `checklist.py`, `board.py`, `preparation.py`). Quatre règles tiennent ces écrans. *Chaque bord saisit pour lui-même* : `rights.acts_for_side` reconnaît le navire par le compte ou le lien NAV, la terre par le terminal qui a saisi la feuille ou le relevé (ou, sans relevé, celui qui parle pour le côté terre) ; le journal de pompage et les relevés de citernes portent le bord, l'organisation et l'auteur. *L'inspecteur valide avant que les autres lisent* : `TankReadingReview` ; `rights.tank_reading_visible` ne montre un relevé en attente ou rejeté qu'à son bord et à l'inspecteur. *Le port décide qui lit* : `ReportAccess` par rapport et par port, consulté par `rights.can_read_report` à l'écran, dans l'API et dans l'export (`DEFAULT_REPORT_READERS` à défaut de ligne). *Rien d'une agence ne sort vers une autre* : `board.rows` ne livre que navire, agence, zone, opérations, état et heures, et un lien seulement aux organisations qui tiennent un rôle sur l'escale. La comparaison des relevés (`compare_sides`) apparie chaque relevé terre au relevé bord le plus proche dans une fenêtre de 45 minutes, calcule l'écart horaire et cumulé en m³ et en pour cent de la feuille terre et lève l'alerte `QUANTITY` (temps réel) au-delà de `Port.quantity_tolerance_pct` ; aucune des deux séries n'est une référence. La liste de contrôle copie à l'ouverture le référentiel `apps/registry/ssscl.py` dans `SafetyChecklist.items` (une liste signée garde les points tels qu'elle les a posés), n'accepte les réponses que du bord du point (`BOTH` : les deux), et la seconde signature enchaîne la tâche M0:28, le jalon `SSSCL_SIGNED` et le dépôt du formulaire `SSSCL` par `forms.auto_issue`. La préparation de la déclaration (`preparation.readiness`) relit le point d'arrêt `DECLARE`, nomme pour chaque tâche manquante l'organisation qui en répond et si elle a de quoi agir (comptes, lien), et offre la relance (`remind` : notification aux comptes, courriel au capitaine à l'adresse où son accès a été envoyé, journal `task.reminded`).

**Assistant du port** (`apps/ai`, `/assistant/`). Deux usages supplémentaires d'EF-17, `BRIEF` et `QUESTION`, avec `AssistantRun.call` vide : le condensé envoyé (`payloads.port_digest`) couvre les escales actives et appareillées depuis moins de 24 h que le demandeur peut ouvrir, les décisions en attente, les tâches en retard, les contestations, l'image AIS et ses écarts, les alertes des 24 h et les indicateurs sur 90 jours — des rôles, jamais une personne, jamais N4 (mêmes tests structurels que pour l'escale). Résultats personnels, conservés en session ; trace append-only avec empreinte et inventaire.
