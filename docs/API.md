# API publique v1

L'API est la surface d'intégration de la plateforme (CDC, orientation d'architecture 5) : systèmes des terminaux et des agences, guichet unique, fournisseur AIS, appli terrain. Elle applique **exactement** les mêmes règles que l'interface, parce que les deux appellent les mêmes services : droits par rôle sur l'escale, points d'arrêt, émetteur unique, séparation demande/décision, cloisonnement N4.

* Base : `https://<hôte>/api/v1/`
* Schéma OpenAPI 3 : `/api/schema/` — documentation navigable : `/api/docs/`
* JSON en UTF-8 ; dates ISO 8601 avec fuseau (`2026-10-24T09:30:00+00:00`) ; les escales sont désignées par leur **référence** (`TGLFW-2026-0001`).

## 1. Authentification

| Qui | En-tête | Obtention |
|---|---|---|
| Utilisateur ou compte d'intégration | `Authorization: Bearer <jeton>` | page **Mon compte › Jeton d'API** (après double authentification pour les rôles qui l'exigent) ; un seul jeton actif par personne, révocable |
| Capitaine (sans compte) | `Authorization: Master <jeton du lien>` | jeton du lien remis par l'agence (EF-13) ; portée limitée à son escale, expire après le départ |
| Partie sans compte (terminal, inspecteur, armateur, prestataire, service nautique) | `Authorization: Master <jeton du lien>` | jeton du lien envoyé à la déclaration ou émis par l'agence ; portée limitée à son escale, jusqu'à la clôture ; refusé (`403`) tant que le titulaire n'a pas donné son nom sur `/bord/nom/` ; jamais de décision |
| Navigateur | cookie de session + jeton CSRF | utilisé par l'appli terrain ; pour CAP, APO et SUR, la session ne vaut qu'après la double authentification (sinon `403 strong_auth_required`) |

**Décisions** (approuver, refuser, clôturer…) : une double authentification récente est exigée. Par l'API, joignez le code TOTP courant :

```
X-MFA-Code: 492817
```

Sans lui, la réponse est `403` avec le code `strong_auth_required`.

Limites : 2 000 requêtes par heure et par utilisateur (réglable par `API_THROTTLE_USER`), 60 par minute pour la vérification publique d'autorisation.

## 2. Erreurs

Toutes les erreurs métier ont la même forme :

```json
{"code": "hold_point_refused",
 "message": "Refus : « Enregistrer le pilote à bord (arrivée) » n'est pas encore possible. …",
 "details": {"transition": "PILOT_BOARDING_ARR",
             "missing_tasks": [{"task": "M0:25", "title_fr": "…", "title_en": "…", "role": "CAP",
                                "co_roles": [], "nature": "D"}],
             "reasons": []}}
```

| HTTP | `code` | Sens |
|---|---|---|
| 404 | `not_found` | l'objet n'existe pas **pour vous** — y compris un objet N4 ou une escale où votre organisation n'a pas de rôle : l'existence n'est jamais révélée |
| 400 | `validation_error` | un enregistrement refusé par sa propre validation (e-mail d'une organisation nommée, numéro IMO…) : `details` le dit champ par champ ; à la création d'une escale, rien n'est enregistré en chemin (1.6 — c'était une erreur serveur) |
| 403 | `permission_refused` | votre rôle sur l'escale ne permet pas l'action |
| 403 | `strong_auth_required` | décision sans double authentification récente |
| 409 | `rule_violation` | règle du registre : émetteur unique, règle 2, cycle de vie, motif manquant… |
| 409 | `hold_point_refused` | point d'arrêt : `details.missing_tasks` nomme chaque tâche manquante, son rôle et l'action attendue |
| 409 | `lock_refused` | verrou du connaissement : aucun rôle ne peut le lever |
| 409 | `immutable` | tentative de modifier un enregistrement figé |

Les messages suivent la langue du compte (français ou anglais).

## 3. Points d'accès

`C` = `/api/v1/calls/<référence>`

| Méthode et chemin | Objet |
|---|---|
| `GET /api/v1/me/` | identité, organisation, rôles |
| `POST /api/v1/vessels/` | enregistrer un navire (agence) — `imo`, `name`, `flag`, `kind` (type de navire : `TANKER_PRODUCT`, `BULK`, `CONTAINER`, `RORO`, `GENERAL`… ; 1.5), `type`, `dwt`, `loa_m`, `beam_m`, `draft_m`, `built_year`, `displacement_t`, `manifold_height_m`, `air_draft_m`, `crane_swl_t`… |
| `GET /api/v1/calls/?active=1&status=…` | escales où votre organisation tient un rôle |
| `POST /api/v1/calls/` | créer une escale (agence) — voir l'exemple §4 ; depuis la 1.4 aussi `planned_pump_hours` et `batch_reference` (time sheet) ; depuis la 1.5 `cargo_kind` (`LIQUID`, `DRY`, `CONTAINER`, `GENERAL`, `RORO`, `OTHER` — choisit les gabarits, unités, mesures et listes de contrôle), `validity_days` (validité de l'annonce, défaut et plafond du port), `sts_role` (`DONOR` ou `RECEIVER`) et `sts_partner` (`{"vessel_imo", "agency_id"?, "role"?}` : l'escale du navire partenaire est créée sous son agence, la vôtre y est agence associée), `expected_documents[]` (codes de types de document du catalogue) et `custom_documents[]` (`{"label", "role", "hours_before_eta"}`), et pour chaque partie `access` (`FULL`, `PARTIAL`, `READ`) et `scopes[]` (onglets d'un accès partiel : `apercu`, `parties`, `taches`, `demandes`, `jalons`, `documents`, `mesures`, `contestations`, `echanges`, `journal`) | ; depuis la 1.6 `operation_details` (`{"<modèle>": {"<clé>": valeur}}` : les réponses aux questions de chaque modèle choisi — `GET /api/v1/calls/` ne les demande pas, `POST` les valide comme l'écran, une question obligatoire manquante est refusée) et `double_banking` (`{"position": "OUTER"|"INNER", "call_reference"}` pour une escale du port — toute agence vue sur la conférence —, ou `{"position", "vessel_imo", "agency_id"?}` pour un navire sans escale : son escale est créée sous son agence) ; dans `sts_partner` comme dans `double_banking`, l'agence de l'autre navire est une agence du port (`agency_id`) **ou une agence que le port ne connaît pas encore** (`agency_name`, et `agency_email`, `agency_phone` facultatifs) : elle est enregistrée avec le rôle d'agence — ou retrouvée par son nom —, les administrateurs du port sont avertis tant qu'elle n'a pas de compte, et elle seule déclare l'escale de son navire ; ni l'un ni l'autre : la vôtre. La création est **une transaction** : un refus (`400`, `409`) n'enregistre rien en chemin |
| `GET C/` | détail de l'escale, filtré par vos droits ; depuis la 1.5 `cargo_kind`, `sts_role`, `validity` (`days`, `valid_until`, `remaining_h`, `overrun_h`, `expired_at`, `renewed_from`), `billing_basis`, `parties[].access` / `scopes` / `principal`, et `your_access` (`level`, `scopes`, `principal_agent`) | ; depuis la 1.6 `operation_details` (brut) et `declared` (`[{template, name, items: [{label, value}]}]`, libellé dans la langue du compte) — rendus, comme `product` et `quantity`, à ceux qui lisent l'escale entière : absents de la réponse faite à un prestataire —, `linked_call` (`{reference, vessel, kind: STS|INNER|OUTER, reciprocal, confirmed}` — `confirmed` vrai quand les deux escales sont de la même agence, que l'autre pointe en retour, ou que la capitainerie a autorisé la zone STS ou l'accostage à couple ; `reciprocal` vrai quand l'autre escale pointe en retour) et `named_by` (`[{reference, vessel, agency, kind, sts_role, status}]` : les escales qui désignent celle-ci — navires-filles d'un navire-mère, navire annoncé à couple) |
| `POST C/actions/<action>/` | `declare`, `estimates` (révision des heures, avec `reason`), `cancel`, `close-request`, `close`, `archive`, `statement-of-facts`, `invite` (une partie de plus : `organization_id` et `role`, ou `name`, `role`, `kind`, `email`, `phone` pour une organisation nouvelle), `remind` (`task_id` : l'agence ou la capitainerie relance la partie d'une tâche en attente — notification en temps réel à ses comptes, courriel au capitaine ; réponse `reached`) ; depuis la 1.5 `renew` (refaire une annonce obsolète, annulée ou rejetée : `201` avec la nouvelle escale), `party-access` (`party_id`, `access`, `scopes[]` — agent principal ou capitainerie), `green-light-withdraw` (`task_id`, `reason`), `documents-request` (`expected_documents[]`, `custom_documents[]` : `201` avec les tâches créées) ; `invite` accepte aussi `access` et `scopes[]` |
| `GET C/tasks/` | vos tâches (AGE et CAP : toutes) ; depuis la 1.5 chaque tâche porte `green_light` et `requested_at_creation` |
| `GET C/green-lights/` | les feux verts de l'escale (1.5) : `results[]` — `task` (code, intitulés, rôle, échéance), `state` (`GIVEN`, `PENDING`, `REFUSED`, `NA`), `by`, `at`, `request` (la demande dont la décision vaut feu vert, pour la capitainerie), `withdrawable` (vous pouvez le retirer) ; un feu vert se donne par `POST C/tasks/<id>/complete/` |
| `POST C/tasks/<id>/<action>/` | `complete`, `sign`, `countersign`, `not-applicable` (avec `reason`) |
| `GET C/milestones/` · `POST C/milestones/` | lire ; enregistrer un jalon — `type`, `declared_at`, `cause`, `cause_reason`, `note`, `related_id` (fin d'interruption), `rectifies_id` + `rectification_reason`, `paper` (ressaisie de la procédure papier), `client_uuid` (idempotence) |
| `POST C/milestones/<id>/countersign/` | contresigner ; avec `"contest": true` et `comment`, contester (ouvre une contestation) |
| `GET C/requests/` · `POST C/requests/` | lire ; créer une demande — `type`, `data` (champs du formulaire du type), `submit`, `provider` (identifiant de l'organisation prestataire, obligatoire pour un service exécuté par un prestataire quand plusieurs participent à l'escale) |
| `POST C/requests/<id>/<action>/` | `submit`, `review`, `decide` (`decision` = `APPROVED`, `APPROVED_COND`, `REFUSED`, `INFO_REQUIRED`, `reason`, `conditions`, `valid_from`, `valid_until`, `berth`), `schedule` (`scheduled_for`), `execute`, `cancel` |
| `GET C/documents/` · `POST C/documents/` | lire ; fournir un document (multipart : `type`, `file`, `title`, `confidentiality`, `counterpart_role`, `task_id`, `previous_id`) |
| `GET C/documents/<id>/download/` | télécharger (consultation journalisée) |
| `POST C/documents/<id>/sign/` | signer cette version |
| `GET C/forms/` | formulaires que vos rôles émettent sur l'escale, par partie émettrice (`code`, `document_type`, `family` et libellés, `title_*`, `standard_*`, `purpose_*`, `answers` = tâches et demandes traitées, `templates` requis, `needs_link`, `signers`, `landscape`) — [FORMULAIRES.md](FORMULAIRES.md) |
| `GET C/forms/<code>/` · `POST C/forms/<code>/` | la page imprimable préremplie (HTML) ; générer et déposer le formulaire comme document de son type (`201`, document créé) |
| `GET C/stages/` · `POST C/stages/` | étapes de l'escale (zones successives) ; planifier la suivante (agence, capitainerie) — `berth_kind`, `operations[]`, `berth`, `planned_from`, `planned_to`, `reason` ; les tâches des nouvelles opérations sont créées aussitôt |
| `POST C/stages/<id>/cancel/` | annuler une étape planifiée (`reason`) — jamais supprimée |
| `GET C/measurements/` · `POST C/measurements/` | lire ; ouvrir une mesure (`kind` : `INITIAL`, `FINAL`, et depuis la 1.5 `DRAFT_I`, `DRAFT_F` draft survey, `SCALE` pesée à terre, `TALLY` pointage ; `unit` parmi `MT`, `M3`, `BBL`, `TEU`, `BOX`, `MOVES`, `UNIT`, `M3B`, `PAX`) |
| `POST C/measurements/<id>/values/` | saisir **votre** valeur (`party` = `SHIP`, `SHORE` ou `SURVEYOR` selon votre rôle, `value`, `temperature_c`, `density`, `declared_at`) |
| `GET C/measurements/<id>/tanks/` · `POST C/measurements/<id>/tanks/` | relevés de citernes que vous pouvez lire (validés ; les vôtres en attente) ; saisir un relevé de **votre** bord — `side` (`SHIP` ou `SHORE`, déduit de votre rôle), `tank`, `level_mm`, `temperature_c`, `free_water_mm`, `density`, `tov_m3`, `gov_m3`, `vcf`, `gsv_m3`, `weight_mt`, `declared_at`, `note`, `supersedes` (correction d'un relevé rejeté), `client_uuid` |
| `POST C/measurements/<id>/tanks/<relevé>/review/` | l'inspecteur valide ou rejette — `decision` = `validate` ou `reject`, `note` (obligatoire pour un rejet) ; un relevé validé devient visible des lecteurs des mesures |
| `GET C/pumping-sheets/` · `POST C/pumping-sheets/` | feuilles du journal de pompage ; ouvrir la feuille de **votre** bord — `side`, `tank`, `product`, `start_level_mm`, `expected_stop_level_mm`, `m3_per_metre`, `density`, `vcf`, `planned_quantity_m3`, `planned_quantity_mt`, `expected_rate_m3h`, `expected_pressure_bar`, `estimated_start`, `estimated_completion`, `note` |
| `POST C/pumping-sheets/<id>/close/` | terminer la feuille — `actual_stop_level_mm`, `final_volume_m3`, `note` |
| `GET C/pumping-log/` · `POST C/pumping-log/` | journal de pompage des deux bords (`results`) et sa **comparaison** relevé par relevé (`comparison` : `at`, `shore`, `ship`, `hourly_deviation_m3`, `hourly_pct`, `cumulative_deviation_m3`, `cumulative_pct`, `exceeds_tolerance`), lecteurs fixés au paramétrage ; saisir un relevé de votre bord — `declared_at`, `sheet_id` (à défaut, la feuille ouverte de votre bord), `tank`, `level_mm`, `hourly_m3`, `cumulative_m3` (calculés depuis la feuille s'ils manquent), `pressure_bar`, `rate_m3h`, `temperature_c`, `note`, `device_id`, `automatic` |
| `GET C/safety-checklist/` · `POST C/safety-checklist/` | la liste de contrôle de sécurité en ligne — ISGOTT, Code BLU ou opérations de manutention selon la nature de la cargaison (`standard`, 1.5) (`checklist` : points par partie avec l'état de chaque bord, répétitions, signatures, progression ; `versions`) ; ouvrir une liste (navire ou terminal) — `repeat_interval_h` |
| `POST C/safety-checklist/<action>/` | `answer` (`items[]` : `item_code`, `state` = `YES`, `NO` ou `NA`, `value`, `remark`, `repetition`), `sign` (`comment` ; la seconde signature fait M0:28, pose le jalon `SSSCL_SIGNED` et dépose le formulaire `SSSCL`), `cancel` (`reason`, capitainerie ou agence) |
| `GET C/disputes/` · `POST C/disputes/` | contestations ; ouvrir (`subject`, `statement`, `counterpart_role`, `target_kind` = `MILESTONE`, `TASK`, `MEASUREMENT`, `DOCUMENT`, `REQUEST` ou `OTHER`, `target_id` d'un objet de cette escale) ; une contestation `MEASUREMENT` non close maintient le verrou du connaissement |
| `POST C/disputes/<id>/<action>/` | `respond` (`text`), `close` (`agreed`, `text`) — il n'existe pas de « rejet » |
| `GET C/threads/` · `POST C/threads/` | échanges de l'escale ; ouvrir un fil (`subject`, `participants`, `confidentiality`, `body`) |
| `POST C/threads/<id>/messages/` | répondre |
| `GET C/journal/` | entrées du journal visibles par vous |
| `GET C/export/` | export de l'escale (COM, DIR) — [FORMAT_EXPORT.md](FORMAT_EXPORT.md) |
| `GET C/field-bundle/` | paquet hors ligne de l'appli terrain (tâches, jalons proposés, causes) |
| `POST C/sync/` | rejeu des saisies hors ligne (§5) |
| `POST C/secure-deposit/` | dépôt confidentiel dans l'espace sûreté (écriture seule ; renvoie un récépissé) |
| `GET /api/v1/dashboard/` | données du tableau de bord (rôles autorisés) |
| `GET /api/v1/board/` | conférence de placement — tableau des escales du port (lecteurs fixés au paramétrage) : `vessel`, `imo`, `flag`, `vessel_kind`, `reference`, `agency`, `area`, `operations`, `status`, `group` (`expected`, `roads`, `alongside`, `departed`), heures estimées et réelles, `cargo` et `quantity` (nuls quand le port ne les montre pas ; `shows_cargo` en tête), `fal_filed`, `manifest_filed`, `sts_partner`, `valid_until`, `party` (votre organisation tient un rôle : l'escale s'ouvre) — rien d'opérationnel sur l'escale d'une autre agence |
| `GET /api/v1/board/occupation/?start=&end=` | plan d'occupation des postes sur la période (1.5) : `results[]` — `area`, `reference`, `vessel`, `operations`, `agency`, `trader`, `cargo`, `quantity`, `eta`, `etb`, `etd`, `state` (`completed`, `ongoing`, `expected`), `party` |
| `POST /api/v1/ais/` | observation AIS d'un fait corroborable — compte d'intégration de périmètre `ais` : `{"imo": "9999993", "event": "ARRIVAL", "time": "…"}` ; un écart produit une alerte, jamais une correction |
| `POST /api/v1/ais/positions/` | positions pour le tableau AIS — compte d'intégration de périmètre `ais` : `{"reports": [{"mmsi": "636099993", "lat": 6.128, "lon": 1.287, "observed_at": "…", "speed_kn": 0.1, "course_deg": 95, "heading_deg": 95, "nav_status": 5, "imo": "9999993", "name": "…", "destination": "…", "draught_m": 11.2}]}` (5 000 rapports au plus par appel ; réponse : `stored`, `static`, `duplicates`, `rejected`) |
| `GET /api/v1/ais/positions/` | dernière position de chaque navire entendu (24 h), avec l'escale correspondante si vous pouvez l'ouvrir, le cadre de la carte et les écarts constatés entre l'image AIS et le registre (`discrepancies`) |
| `GET /api/v1/verify/<code>/` | vérification publique d'une autorisation (sans compte) |
| `GET /api/v1/secure/items/` · `GET/POST /api/v1/secure/items/<référence>/` | espace sûreté (SUR, CAP) ; 404 pour tout autre rôle |

## 4. Exemple : de la création au premier jalon

```bash
H='Authorization: Bearer 6f1c…'
curl -s -X POST https://port.example/api/v1/calls/ -H "$H" -H 'Content-Type: application/json' -d '{
  "vessel_imo": "9999993", "operating_area": "JETTY", "operations": ["M1"],
  "eta": "2026-11-02T06:00:00+00:00", "etb": "2026-11-02T14:00:00+00:00", "etd": "2026-11-04T06:00:00+00:00",
  "cargo_kind": "LIQUID", "product": "Gasoil 10 ppm", "quantity": "32000", "quantity_unit": "MT", "voyage": "V-112",
  "validity_days": 15,
  "expected_documents": ["INSURANCE"], "custom_documents": [{"label": "Certificat d'origine", "role": "COM", "hours_before_eta": 24}],
  "parties": [{"organization_id": 7, "role": "TER"}, {"organization_id": 9, "role": "INS", "access": "PARTIAL", "scopes": ["mesures", "documents"]},
              {"organization_id": 12, "role": "AGE", "access": "PARTIAL", "scopes": ["taches", "documents"]},
              {"name": "Sierra Petroleum Laboratory", "role": "INS", "kind": "LABORATORY", "email": "lab@spl.test", "phone": "+232 76 000 000"}]}'
# parties : liste ouverte — une organisation enregistrée (organization_id) ou une nouvelle (name, role, kind suggérée ou libre, email, phone) ;
# access / scopes (1.5) : ce que l'agent principal donne à chaque partie ; une seconde agence (role AGE) est une agence associée
# vrac sec, conteneurs, roulier… : "cargo_kind": "DRY", "operations": ["MB1"], "quantity_unit": "MT" — ou "CONTAINER", ["MC1"], "MOVES"
# transbordement navire-navire : "operating_area": "STS_AREA", "operations": ["M3"], "sts_role": "DONOR",
#   "sts_partner": {"vessel_imo": "9999967", "agency_id": 12, "role": "RECEIVER"}  → l'escale du partenaire est créée sous l'agence 12
#   ou "linked_call": "TGLFW-2026-0003"  → le partenaire a déjà son escale : la vôtre (lien réciproque) ou celle d'une autre agence vue sur la
#   conférence de placement (1.6 : lien à sens unique, rôle inverse pris d'office, confirmé par l'autorisation STS_ZONE de la capitainerie)
# l'annonce s'adapte à l'opération (1.6) : les réponses aux questions de chaque modèle, et l'accostage à couple
#   "operation_details": {"M1": {"max_rate_m3h": 1200, "max_manifold_pressure_bar": 7}, "M4": {"grade": "VLSFO", "quantity_mt": 450, "delivery_mode": "BARGE"}},
#   "modules": ["M9"], "double_banking": {"position": "OUTER", "call_reference": "TGLFW-2026-0001"}   → à couple du navire à quai (escale de toute agence)
#   ou "double_banking": {"position": "OUTER", "vessel_imo": "9074731", "agency_id": 12}            → l'autre navire reçoit son escale sous l'agence 12

curl -s -X POST https://port.example/api/v1/calls/TGLFW-2026-0005/actions/declare/ -H "$H"
# → 409 hold_point_refused tant que M0:02, M0:03 et M0:05 ne sont pas faites ; le refus est journalisé
```

## 5. Saisie hors ligne : `POST C/sync/`

```json
{"entries": [
  {"kind": "milestone", "client_uuid": "4f5f3c7e-2b9e-4c1d-9f1e-1b2c3d4e5f60",
   "type": "INTERRUPTION_START", "cause": "SHORE_PUMP",
   "declared_at": "2026-10-24T10:05:00+00:00", "device_recorded_at": "2026-10-24T10:06:12+00:00"},
  {"kind": "measurement_value", "client_uuid": "…", "measurement_id": 3, "party": "SHORE", "value": "31950,250",
   "device_recorded_at": "…"}
]}
```

Natures acceptées : `milestone`, `countersign` (`milestone_id`, `contest`, `comment`), `measurement_value` (`measurement_id`, `party`, `value`), `pumping` (`pressure_bar`, `rate_m3h`, `temperature_c`, et depuis la 1.4 `sheet_id`, `tank`, `level_mm`, `hourly_m3`, `cumulative_m3` — le bord est celui de votre rôle), `photo` (`data_url` en base64), `task_complete` et `task_sign` (`task_id`). Les entrées sont rejouées **dans l'ordre de `device_recorded_at`** ; chaque `client_uuid` n'est appliqué qu'une fois (renvoyer un lot est sans danger). Réponse : un résultat par entrée (`ok`, `conflict`, `error` avec le message), avec `deferred: true` pour les saisies arrivées après le seuil. Deux saisies du même jalon ne s'écrasent jamais : la seconde est conservée et une contestation est ouverte (EF-14.4).

## 6. Webhooks sortants

Pour chaque abonnement du port, les entrées du journal visibles par toutes les parties sont envoyées en `POST` :

```
Content-Type: application/json
X-Fluxaa-Event: milestone.recorded
X-Fluxaa-Signature: sha256=<HMAC-SHA256 du corps avec le secret de l'abonnement>
```

```json
{"event": "milestone.recorded", "seq": 412, "at": "…", "hash": "…", "call": "TGLFW-2026-0001",
 "vessel": {"imo": "9999993", "name": "MT ATLANTIC DEMO"}, "summary": {"fr": "…", "en": "…"}}
```

Vérifiez la signature avant tout traitement. En cas d'échec, l'envoi est retenté avec un délai croissant (2, 4, 8… minutes), puis marqué en échec après 8 tentatives.
