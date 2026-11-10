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
| `POST /api/v1/vessels/` | enregistrer un navire (agence) — `imo`, `name`, `flag`, `type`, `dwt`… |
| `GET /api/v1/calls/?active=1&status=…` | escales où votre organisation tient un rôle |
| `POST /api/v1/calls/` | créer une escale (agence) — voir l'exemple §4 |
| `GET C/` | détail de l'escale, filtré par vos droits |
| `POST C/actions/<action>/` | `declare`, `estimates` (révision des heures, avec `reason`), `cancel`, `close-request`, `close`, `archive`, `statement-of-facts`, `invite` (une partie de plus : `organization_id` et `role`, ou `name`, `role`, `kind`, `email`, `phone` pour une organisation nouvelle) |
| `GET C/tasks/` | vos tâches (AGE et CAP : toutes) |
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
| `GET C/measurements/` · `POST C/measurements/` | lire ; ouvrir une mesure (`kind`, `unit`) |
| `POST C/measurements/<id>/values/` | saisir **votre** valeur (`party` = `SHIP`, `SHORE` ou `SURVEYOR` selon votre rôle, `value`, `temperature_c`, `density`, `declared_at`) |
| `GET C/pumping-log/` · `POST C/pumping-log/` | journal de pompage |
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
  "product": "Gasoil 10 ppm", "quantity": "32000", "quantity_unit": "MT", "voyage": "V-112",
  "parties": [{"organization_id": 7, "role": "TER"}, {"organization_id": 9, "role": "INS"},
              {"name": "Sierra Petroleum Laboratory", "role": "INS", "kind": "LABORATORY", "email": "lab@spl.test", "phone": "+232 76 000 000"}]}'
# parties : liste ouverte — une organisation enregistrée (organization_id) ou une nouvelle (name, role, kind suggérée ou libre, email, phone)

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

Natures acceptées : `milestone`, `countersign` (`milestone_id`, `contest`, `comment`), `measurement_value` (`measurement_id`, `party`, `value`), `pumping` (`pressure_bar`, `rate_m3h`, `temperature_c`), `photo` (`data_url` en base64), `task_complete` et `task_sign` (`task_id`). Les entrées sont rejouées **dans l'ordre de `device_recorded_at`** ; chaque `client_uuid` n'est appliqué qu'une fois (renvoyer un lot est sans danger). Réponse : un résultat par entrée (`ok`, `conflict`, `error` avec le message), avec `deferred: true` pour les saisies arrivées après le seuil. Deux saisies du même jalon ne s'écrasent jamais : la seconde est conservée et une contestation est ouverte (EF-14.4).

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
