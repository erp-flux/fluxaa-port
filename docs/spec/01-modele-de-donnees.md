# 1. Modèle de données
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Chaque entité est décrite par ses champs (type, règles), ses contraintes et son garde-fou d'intégrité. Les libellés sont donnés en français / anglais tels que l'interface les affiche. Les énumérations sont au chapitre 2, les règles d'écriture au chapitre 5.

## 1.1 Application `core — port, organisations, utilisateurs, postes`

### `Port` — table `core_port`
A tenant: one port authority and its waters (quays, anchorage, offshore areas)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `code` | Char(10) | UN/LOCODE | unique | p. ex. SLFNA, TGLFW / e.g. SLFNA, TGLFW |
| `name` | Char(120) | nom / name |  |  |
| `country` | Char(2) | pays (ISO 3166) / country (ISO 3166) |  |  |
| `timezone` | Char(64) | fuseau horaire / time zone | défaut `'UTC'` |  |
| `default_language` | Char(2) | langue par défaut / default language | défaut `'fr'` ; énumération `Language` (ch. 2) |  |
| `countersign_delay_minutes` | PositiveInteger | délai de contresignature (minutes) / countersignature delay (minutes) | défaut `120` | Passé ce délai, un jalon non contresigné vaut contresignature tacite (EF-3.4). / After this delay an unsigned milestone becomes a tacit countersignature (EF-3.4). |
| `reminder_lead_hours` | PositiveInteger | délai de rappel (heures) / reminder lead time (hours) | défaut `24` |  |
| `escalation_after_minutes` | PositiveInteger | escalade après retard (minutes) / escalation after lateness (minutes) | défaut `240` | Une tâche normale en retard au-delà de ce seuil est escaladée ; une tâche bloquante en retard l'est immédiatement. / A normal task late beyond this threshold is escalated; a late blocking task is escalated at once. |
| `quantity_tolerance_pct` | Decimal(5,3) | tolérance bord/terre (%) / ship/shore tolerance (%) | défaut `Decimal('0.300')` |  |
| `ais_divergence_minutes` | PositiveInteger | seuil d'écart AIS (minutes) / AIS divergence threshold (minutes) | défaut `30` |  |
| `master_link_grace_hours` | PositiveInteger | validité du lien capitaine après le départ (heures) / master link validity after departure (hours) | défaut `24` |  |
| `master_link_max_days` | PositiveInteger | validité maximale du lien capitaine (jours) / master link maximum validity (days) | défaut `30` |  |
| `party_link_max_days` | PositiveInteger | validité maximale des liens d'accès des parties (jours) / party access link maximum validity (days) | défaut `90` | Accès sans compte d'un terminal, d'un inspecteur, d'un armateur, d'un prestataire ou d'un service nautique : valable jusqu'à la clôture de l'escale, au plus ce nombre de jours. / Account-less access of a terminal, surveyor, owner, provider or marine service: valid until the closure of the call, at most this many days. |
| `retention_years` | PositiveInteger | conservation (années) / retention (years) | défaut `10` |  |
| `digest_hour_local` | PositiveSmallInteger | heure du résumé quotidien (heure locale) / daily digest hour (local) | défaut `7` |  |
| `security_authority_email` | Char(254) | e-mail de l'autorité de sûreté / security authority e-mail | peut être vide | Reçoit les notifications nominatives d'accès aux dossiers N4 (EF-12.4). / Receives the nominative notifications of access to N4 records (EF-12.4). |
| `ai_assistance_enabled` | Boolean | assistance IA activée / AI assistance enabled | défaut `False` | EF-17 : extraction, projet de remarques, revue de cohérence et résumés — jamais une décision. Exige l'accord écrit du port ci-dessous et la clause contractuelle de la plateforme avec le fournisseur. / EF-17: extraction, draft remarks, consistency review and summaries — never a decision. Requires the port's written agreement below and the platform's provider agreement. |
| `ai_agreement_reference` | Char(200) | référence de l'accord du port pour l'assistance IA / reference of the port's agreement for AI assistance | peut être vide | Clause contractuelle autorisant la transmission des données d'escale au fournisseur d'IA (EF-17). / Contractual clause authorising the transfer of call data to the AI provider (EF-17). |
| `map_lat_min` | Decimal(9,6) | carte — latitude sud / map — southern latitude | nullable |  |
| `map_lat_max` | Decimal(9,6) | carte — latitude nord / map — northern latitude | nullable |  |
| `map_lon_min` | Decimal(9,6) | carte — longitude ouest / map — western longitude | nullable |  |
| `map_lon_max` | Decimal(9,6) | carte — longitude est / map — eastern longitude | nullable |  |
| `map_image` | File | fond de carte / map background | peut être vide | Extrait de carte ou d'image satellite facultatif couvrant exactement le cadre ci-dessus (PNG ou JPEG) ; le port doit détenir les droits de le publier. / Optional chart or satellite excerpt covering exactly the box above (PNG or JPEG); the port must hold the rights to publish it. |
| `ais_retention_days` | PositiveInteger | positions AIS conservées (jours) / AIS positions kept (days) | défaut `30` | Les positions plus anciennes sont purgées ; ce sont des données diffusées publiquement, pas des actes du registre. / Position reports older than this are purged; they are public broadcast data, not registry acts. |
| `is_active` | Boolean | actif / active | défaut `True` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : tri par défaut : name.

Propriétés et méthodes documentées : `has_map` — The AIS board draws the port waters only once the box is configured (PARAMETRAGE.md §2).

### `Organization` — table `core_organization`
An organisation active in a port. It may hold several roles (e.g. port authority: CAP, APO, DIR)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `name` | Char(200) | nom / name |  |  |
| `short_name` | Char(40) | nom court / short name | peut être vide |  |
| `kind` | Char(80) | nature de la partie / kind of party | peut être vide | Ce qu'est l'organisation (pilotage, laboratoire, avitailleur…) : un code de la liste suggérée ou tout autre libellé. C'est le rôle, non la nature, qui porte les droits. / What the organisation is (pilotage, laboratory, bunker supplier…): a code of the suggested list or any other wording. The role, not the kind, carries the rights. |
| `allowed_roles` | JSON | rôles que cette organisation peut tenir / roles this organisation may hold | peut être vide ; défaut `list()` |  |
| `email` | Char(254) | e-mail | peut être vide |  |
| `phone` | Char(40) | téléphone (escalades) / phone (escalations) | peut être vide |  |
| `is_active` | Boolean | actif / active | défaut `True` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : `uniq_org_name_per_port` (port, name) — unicité ; tri par défaut : name.

### `User` — table `core_user`
A named person (or a technical integration account) belonging to one organisation

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `password` | Char(128) | mot de passe / password |  |  |
| `last_login` | DateTime | dernière connexion / last login | nullable |  |
| `is_superuser` | Boolean | statut super-utilisateur / superuser status | défaut `False` | Précise que l’utilisateur possède toutes les permissions sans les assigner explicitement. / Designates that this user has all permissions without explicitly assigning them. |
| `is_staff` | Boolean | statut équipe / staff status | défaut `False` | Précise si l’utilisateur peut se connecter à ce site d'administration. / Designates whether the user can log into this admin site. |
| `is_active` | Boolean | actif / active | défaut `True` | Précise si l’utilisateur doit être considéré comme actif. Décochez ceci plutôt que de supprimer le compte. / Designates whether this user should be treated as active. Unselect this instead of deleting accounts. |
| `date_joined` | DateTime | date d’inscription / date joined | défaut `now()` |  |
| `email` | Char(254) | e-mail | unique |  |
| `full_name` | Char(200) | nom complet / full name |  |  |
| `organization` | FK → Organization | organisation | nullable ; indexé ; on_delete `PROTECT` |  |
| `roles` | JSON | rôles que l'utilisateur peut exercer / roles the user may exercise | peut être vide ; défaut `list()` |  |
| `language` | Char(2) | langue / language | peut être vide ; énumération `Language` (ch. 2) |  |
| `phone` | Char(40) | téléphone mobile / mobile phone | peut être vide |  |
| `is_port_admin` | Boolean | administrateur fonctionnel du port / functional administrator of the port | défaut `False` | Peut modifier les gabarits, les types de demande, les listes de référence et les seuils de son port (EF-16). / May edit templates, request types, reference lists and thresholds of their port (EF-16). |
| `is_integration` | Boolean | compte d'intégration technique / technical integration account | défaut `False` |  |
| `integration_scopes` | JSON | périmètres d'intégration / integration scopes | peut être vide ; défaut `list()` |  |
| `mfa_secret_encrypted` | Text |  | peut être vide ; non modifiable |  |
| `mfa_enabled` | Boolean | double authentification activée / two-factor authentication enabled | défaut `False` |  |
| `notify_digest_only` | Boolean | résumé quotidien pour les tâches normales / daily digest for normal tasks | défaut `True` | Les tâches bloquantes et les escalades sont toujours notifiées en temps réel et ne peuvent pas être désactivées (EF-6.3). / Blocking tasks and escalations are always notified in real time and cannot be muted (EF-6.3). |
| `groups` | M–N → Group | groupes / groups | peut être vide | Les groupes dont fait partie cet utilisateur. Celui-ci obtient tous les droits de tous les groupes auxquels il appartient. / The groups this user belongs to. A user will get all permissions granted to each of their groups. |
| `user_permissions` | M–N → Permission | permissions de l’utilisateur / user permissions | peut être vide | Permissions spécifiques à cet utilisateur. / Specific permissions for this user. |

Contraintes et index : tri par défaut : full_name.

Propriétés et méthodes documentées : `requires_mfa_login` — Deciding roles (ENF-3.1) — and anyone who administers accounts or settings: whoever can reset another person's second factor must hold one.

### `Berth` — table `core_berth`
A resource of the port where a tanker operates: quay/jetty, anchorage, offshore buoy, STS area

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(30) |  |  |  |
| `name_fr` | Char(150) | nom (français) / name (French) |  |  |
| `name_en` | Char(150) | nom (anglais) / name (English) |  |  |
| `kind` | Char(12) | type | énumération `Berth.Kind` (ch. 2) |  |
| `max_loa_m` | Decimal(6,1) | longueur hors tout max. (m) / max LOA (m) | nullable |  |
| `max_draft_m` | Decimal(5,2) | tirant d'eau max. (m) / max draft (m) | nullable |  |
| `max_dwt` | PositiveInteger | port en lourd max. / max DWT | nullable |  |
| `weather_limits` | JSON | limites météo / weather limits | peut être vide ; défaut `dict()` | p. ex. {"wind_kn": 25, "swell_m": 2.0, "current_kn": 2.5, "visibility_nm": 1} / e.g. {"wind_kn": 25, "swell_m": 2.0, "current_kn": 2.5, "visibility_nm": 1} |
| `has_vapour_recovery` | Boolean | récupération des vapeurs / vapour recovery system | défaut `False` |  |
| `latitude` | Decimal(9,6) |  | nullable | Centre du poste ou de la zone, dessiné sur le tableau AIS. / Centre of the berth or area, drawn on the AIS board. |
| `longitude` | Decimal(9,6) |  | nullable |  |
| `radius_m` | PositiveInteger | rayon (m) / radius (m) | nullable | Étendue d'une zone de mouillage ou STS autour de son centre. / Extent of an anchorage or STS area around its centre. |
| `notes` | Text |  | peut être vide |  |
| `is_active` | Boolean | actif / active | défaut `True` |  |

Contraintes et index : `uniq_berth_code_per_port` (port, code) — unicité ; tri par défaut : port, kind, code.

### `AttemptWindow` — table `core_attemptwindow`
Failed attempts at a guessable secret (password, two-factor code, master access code) in the current window, per hashed key (apps.core.throttle). Technical table: no personal data is stored in clear

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `key` | Char(64) |  | unique |  |
| `started_at` | DateTime |  |  |  |
| `failures` | PositiveInteger |  | défaut `0` |  |

## 1.2 Application `registry — le registre des escales`

### `Vessel` — table `registry_vessel`
Vessel particulars ("fiche navire"), per port. Created and maintained by the agency

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `imo` | Char(7) | numéro OMI / IMO number |  |  |
| `name` | Char(120) | nom / name |  |  |
| `flag` | Char(60) | pavillon / flag | peut être vide |  |
| `vessel_type` | Char(60) | type | peut être vide | Brut, produits, chimiquier, GPL… / Crude, product, chemical, LPG… |
| `call_sign` | Char(20) | indicatif d'appel / call sign | peut être vide |  |
| `mmsi` | Char(9) | MMSI | peut être vide |  |
| `dwt` | PositiveInteger | port en lourd / DWT | nullable |  |
| `loa_m` | Decimal(6,2) | longueur hors tout (m) / LOA (m) | nullable |  |
| `beam_m` | Decimal(5,2) | largeur (m) / beam (m) | nullable |  |
| `draft_m` | Decimal(5,2) | tirant d'eau d'été (m) / summer draft (m) | nullable |  |
| `built_year` | PositiveSmallInteger | année de construction / year built | nullable |  |
| `owner_name` | Char(160) | propriétaire inscrit / registered owner | peut être vide |  |
| `manager_name` | Char(160) | gestionnaire / exploitant / manager / operator | peut être vide |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `updated_at` | DateTime |  | horodatage automatique à chaque enregistrement |  |

Contraintes et index : `uniq_vessel_imo_per_port` (port, imo) — unicité ; tri par défaut : name.

### `CallSequence` — table `registry_callsequence`
Gap-free yearly counters: calls [PORT]-[YYYY]-[SEQ] (EF-1.1), authorizations, disputes

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(4) |  | défaut `'CALL'` |  |
| `year` | PositiveSmallInteger |  |  |  |
| `last_value` | PositiveInteger |  | défaut `0` |  |

Contraintes et index : `uniq_call_sequence` (port, kind, year) — unicité.

### `CallTemplate` — table `registry_calltemplate`
A call model (M0…M9, MA1…MA3). Owned by the port authority; the engine is shared

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(10) |  |  |  |
| `kind` | Char(10) | nature / kind | énumération `TemplateKind` (ch. 2) |  |
| `name_fr` | Char(150) | nom (français) / name (French) |  |  |
| `name_en` | Char(150) | nom (anglais) / name (English) |  |  |
| `description_fr` | Text | description (français) / description (French) | peut être vide |  |
| `description_en` | Text | description (anglais) / description (English) | peut être vide |  |
| `berth_kinds` | JSON | types de poste concernés / applicable berth types | peut être vide ; défaut `list()` | Vide = tous les types. / Empty = all types. |
| `requires_linked_call` | Boolean | relie deux escales / links two calls | défaut `False` | Le STS et l'accostage à couple associent deux navires. / STS and double banking connect two vessels. |
| `never_alone` | Boolean | ne peut pas être utilisé seul / cannot be used alone | défaut `False` | M9 se greffe sur une opération. / M9 grafts onto an operation. |
| `is_active` | Boolean | actif / active | défaut `True` |  |
| `order` | PositiveSmallInteger |  | défaut `0` |  |

Contraintes et index : `uniq_template_code_per_port` (port, code) — unicité ; tri par défaut : port, order, code.

### `TemplateVersion` — table `registry_templateversion`
A frozen version of a template. A call keeps the version in force at its creation (EF-5.8)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `template` | FK → CallTemplate |  | indexé ; on_delete `PROTECT` |  |
| `number` | PositiveInteger | version |  |  |
| `status` | Char(10) | statut / status | défaut `TemplateVersion.Status.DRAFT` ; énumération `TemplateVersion.Status` (ch. 2) |  |
| `notes` | Text | notes de modification / change notes | peut être vide |  |
| `published_at` | DateTime |  | nullable |  |
| `published_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : `uniq_template_version` (template, number) — unicité ; tri par défaut : template, -number.

### `TemplateTask` — table `registry_templatetask`
A line of a call template (FLX-SPEC-002): who does what, by when, and whether it blocks

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `version` | FK → TemplateVersion |  | indexé ; on_delete `PROTECT` |  |
| `number` | Char(10) | numéro / number |  | p. ex. 01, 1.05, A1.02 / e.g. 01, 1.05, A1.02 |
| `section_fr` | Char(150) | section (français) / section (French) | peut être vide |  |
| `section_en` | Char(150) | section (anglais) / section (English) | peut être vide |  |
| `title_fr` | Char(400) | tâche (français) / task (French) |  |  |
| `title_en` | Char(400) | tâche (anglais) / task (English) |  |  |
| `role` | Char(3) | rôle responsable / assigned role | valeurs : `AGE`, `NAV`, `TER`, `CAP`, `APO`, `SVC`, `ADM`, `SUR`, `INS`, `COM`, `PRE`, `DIR` … |  |
| `co_roles` | JSON | rôles cosignataires / co-signing roles | peut être vide ; défaut `list()` | Rôles qui signent ou contresignent la tâche, p. ex. ["NAV", "TER"]. / Roles that sign or countersign the task, e.g. ["NAV", "TER"]. |
| `joint` | Boolean | signature conjointe requise / joint signature required | défaut `False` | La tâche n'est faite que lorsque le rôle responsable et chaque rôle cosignataire ont signé. / The task is done only when the assigned role and every co-signing role have signed. |
| `nature` | Char(1) |  | énumération `Nature` (ch. 2) |  |
| `anchor` | Char(3) | point d'ancrage de l'échéance / deadline anchor | peut être vide ; énumération `Anchor` (ch. 2) |  |
| `offset_minutes` | Integer | décalage par rapport à l'ancrage (minutes) / offset from anchor (minutes) | défaut `0` |  |
| `timing_fr` | Char(60) | libellé de l'échéance (français) / deadline label (French) | peut être vide |  |
| `timing_en` | Char(60) | libellé de l'échéance (anglais) / deadline label (English) | peut être vide |  |
| `criticality` | Char(1) | criticité / criticality | énumération `Criticality` (ch. 2) |  |
| `confidentiality` | Char(2) | confidentialité / confidentiality | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `hold_basis` | Char(200) | fondement du caractère bloquant / basis of the blocking character | peut être vide | Point d'arrêt de la PRO-MAR-001 ou obligation réglementaire. Obligatoire pour une tâche bloquante. / Hold point of PRO-MAR-001 or regulatory obligation. Required for a blocking task. |
| `request_type_code` | Char(40) | type de demande lié / linked request type | peut être vide |  |
| `request_side` | Char(8) | côté de la demande / request side | peut être vide ; valeurs : `submit`, `decide` |  |
| `milestone_codes` | JSON | jalons qui réalisent la tâche / milestones that complete the task | peut être vide ; défaut `list()` |  |
| `document_type_code` | Char(40) | type de document attendu / expected document type | peut être vide |  |
| `auto_event` | Char(30) | réalisée par un événement de la plateforme / completed by platform event | peut être vide ; valeurs : `call.created`, `call.declared` |  |
| `continuous` | Boolean | tâche continue / continuous task | défaut `False` | Reste ouverte jusqu'à T1 (journal de pompage, interruptions). / Kept open until T1 (pumping log, interruptions). |
| `per_vessel` | Boolean | une par navire (×2) / one per vessel (×2) | défaut `False` |  |
| `not_applicable_allowed` | Boolean | peut être déclarée sans objet / may be marked not applicable | défaut `True` |  |
| `berth_kinds` | JSON | uniquement pour ces zones d'opération / only for these operating areas | peut être vide ; défaut `list()` | Opération × type de poste : vide = toutes les zones ; p. ex. ["JETTY", "SPM"] pour les tâches d'interface navire/terre. / Operation × berth type: empty = every area; e.g. ["JETTY", "SPM"] for ship/shore interface tasks. |
| `order` | PositiveInteger |  | défaut `0` |  |

Contraintes et index : `uniq_task_number_per_version` (version, number) — unicité ; tri par défaut : version, order, number.

### `HoldPoint` — table `registry_holdpoint`
A guarded transition and the blocking template tasks it requires (EF-11)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `transition` | Char(24) |  | énumération `Transition` (ch. 2) |  |
| `description_fr` | Char(300) | description (français) / description (French) | peut être vide |  |
| `description_en` | Char(300) | description (anglais) / description (English) | peut être vide |  |

Contraintes et index : `uniq_hold_point` (port, transition) — unicité.

### `HoldPointRequirement` — table `registry_holdpointrequirement`
Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `hold_point` | FK → HoldPoint |  | indexé ; on_delete `CASCADE` |  |
| `template_code` | Char(10) | gabarit / template |  |  |
| `task_number` | Char(10) | numéro de tâche / task number |  |  |

Contraintes et index : `uniq_hold_requirement` (hold_point, template_code, task_number) — unicité ; tri par défaut : template_code, task_number.

### `InterruptionCause` — table `registry_interruptioncause`
Closed list of interruption causes, negotiated with the parties (EF-3.5)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(30) |  |  |  |
| `label_fr` | Char(200) | libellé (français) / label (French) |  |  |
| `label_en` | Char(200) | libellé (anglais) / label (English) |  |  |
| `attributable_to` | Char(10) | imputable à / attributable to | peut être vide ; valeurs : `SHIP`, `SHORE`, `THIRD`, `WEATHER` |  |
| `requires_reason` | Boolean | motif obligatoire (« Autre ») / reason mandatory ("Other") | défaut `False` |  |
| `is_active` | Boolean | actif / active | défaut `True` |  |
| `order` | PositiveSmallInteger |  | défaut `0` |  |

Contraintes et index : `uniq_cause_code_per_port` (port, code) — unicité ; tri par défaut : port, order, code.

### `MilestoneType` — table `registry_milestonetype`
An event of FLX-SPEC-001 §7: single emitter, countersigners, contesters

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(30) |  |  |  |
| `number` | PositiveSmallInteger | numéro dans la matrice / matrix number | défaut `0` |  |
| `label_fr` | Char(200) | libellé (français) / label (French) |  |  |
| `label_en` | Char(200) | libellé (anglais) / label (English) |  |  |
| `emitter_role` | Char(6) | émetteur unique / single emitter | valeurs : `AGE`, `NAV`, `TER`, `CAP`, `APO`, `SVC`, `ADM`, `SUR`, `INS`, `COM`, `PRE`, `DIR` … |  |
| `countersigner_roles` | JSON | contresignataires / countersigners | peut être vide ; défaut `list()` |  |
| `contester_roles` | JSON | peuvent contester / may contest | peut être vide ; défaut `list()` | ["*"] = toutes les parties / ["*"] = every party |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N1` ; énumération `Confidentiality` (ch. 2) |  |
| `ais_corroboration` | Boolean | corroboration AIS / AIS corroboration | défaut `False` |  |
| `requires_cause` | Boolean | cause de la liste fermée obligatoire / cause from the closed list required | défaut `False` |  |
| `closes_type` | Char(30) | clôt l'intervalle ouvert par / closes the interval opened by | peut être vide |  |
| `repeatable` | Boolean | peut survenir plusieurs fois / may occur several times | défaut `False` |  |
| `hold_point` | Char(24) | gardé par un point d'arrêt / guarded by hold point | peut être vide ; énumération `Transition` (ch. 2) |  |
| `sets_anchor` | Char(4) | fixe l'heure réelle / sets the actual time | peut être vide ; valeurs : `ATA`, `ATB`, `T0`, `T1`, `ATD`, `NOR` |  |
| `sets_status` | Char(14) | fait passer l'escale à / moves the call to | peut être vide ; énumération `CallStatus` (ch. 2) |  |
| `completes_tasks` | JSON | réalise les tâches de gabarit / completes template tasks | peut être vide ; défaut `list()` | p. ex. ["M1:1.09"] / e.g. ["M1:1.09"] |
| `auto_from_task` | Char(16) | enregistré automatiquement quand cette tâche est faite / recorded automatically when this task is done | peut être vide | p. ex. "M0:28" / e.g. "M0:28" |
| `field_entry` | Boolean | proposé dans l'appli terrain / offered in the field app | défaut `True` |  |
| `is_active` | Boolean |  | défaut `True` |  |
| `order` | PositiveSmallInteger |  | défaut `0` |  |

Contraintes et index : `uniq_milestone_type_per_port` (port, code) — unicité ; tri par défaut : port, order, number.

### `RequestType` — table `registry_requesttype`
A configurable request/authorization type (EF-2.2): no development per type

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(40) |  |  |  |
| `label_fr` | Char(200) | libellé (français) / label (French) |  |  |
| `label_en` | Char(200) | libellé (anglais) / label (English) |  |  |
| `description_fr` | Text |  | peut être vide |  |
| `description_en` | Text |  | peut être vide |  |
| `requester_roles` | JSON | rôles demandeurs / requesting roles | défaut `list()` |  |
| `decision_roles` | JSON | autorités décisionnaires / deciding authorities | défaut `list()` |  |
| `executor_role` | Char(3) | rôle exécutant / executing role | peut être vide ; énumération `Role` (ch. 2) |  |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `refusal_confidentiality` | Char(2) | confidentialité du motif de refus / confidentiality of the refusal reason | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `form_schema` | JSON | champs du formulaire / form fields | peut être vide ; défaut `list()` | Liste de {"key", "label_fr", "label_en", "type", "required", "options"}. / List of {"key", "label_fr", "label_en", "type", "required", "options"}. |
| `expected_documents` | JSON | types de document attendus / expected document types | peut être vide ; défaut `list()` |  |
| `processing_minutes` | PositiveInteger | délai d'instruction (minutes) / processing time (minutes) | défaut `240` |  |
| `validity_hours` | PositiveInteger | validité par défaut de l'autorisation (heures) / default validity of the authorization (hours) | défaut `72` | Une autorisation porte toujours une date d'expiration (EF-2.5). / An authorization always carries an expiry date (EF-2.5). |
| `is_vetting` | Boolean | acceptation du navire (vetting) / vessel acceptance (vetting) | défaut `False` |  |
| `hold_point` | Char(24) | décision gardée par / decision guarded by | peut être vide ; énumération `Transition` (ch. 2) |  |
| `submit_completes` | JSON | le dépôt réalise les tâches / submission completes tasks | peut être vide ; défaut `list()` |  |
| `decision_completes` | JSON | la décision réalise les tâches / decision completes tasks | peut être vide ; défaut `list()` |  |
| `execution_completes` | JSON | l'exécution réalise les tâches / execution completes tasks | peut être vide ; défaut `list()` |  |
| `approval_milestone` | Char(30) | jalon enregistré à l'approbation / milestone recorded on approval | peut être vide |  |
| `approval_status` | Char(14) | statut de l'escale à l'approbation / call status on approval | peut être vide ; énumération `CallStatus` (ch. 2) |  |
| `refusal_status` | Char(14) | statut de l'escale au refus / call status on refusal | peut être vide ; énumération `CallStatus` (ch. 2) |  |
| `assigns_berth` | Boolean | la décision attribue un poste / the decision assigns a berth | défaut `False` |  |
| `is_active` | Boolean |  | défaut `True` |  |
| `order` | PositiveSmallInteger |  | défaut `0` |  |

Contraintes et index : `uniq_request_type_per_port` (port, code) — unicité ; tri par défaut : port, order, code.

### `DocumentType` — table `registry_documenttype`
Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `code` | Char(40) |  |  |  |
| `label_fr` | Char(200) | libellé (français) / label (French) |  |  |
| `label_en` | Char(200) | libellé (anglais) / label (English) |  |  |
| `default_confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `issuer_roles` | JSON | rôles émetteurs / issuing roles | peut être vide ; défaut `list()` |  |
| `signer_roles` | JSON | signataires requis / required signatories | peut être vide ; défaut `list()` |  |
| `audience_roles` | JSON | lecteurs supplémentaires (N2) / additional readers (N2) | peut être vide ; défaut `list()` |  |
| `retention_years` | PositiveSmallInteger | conservation (années) / retention (years) | défaut `10` |  |
| `generated` | Boolean | généré à partir du registre / generated from the registry | défaut `False` |  |
| `is_bill_of_lading` | Boolean | connaissement (verrouillé) / bill of lading (locked) | défaut `False` |  |
| `is_active` | Boolean |  | défaut `True` |  |
| `order` | PositiveSmallInteger |  | défaut `0` |  |

Contraintes et index : `uniq_doc_type_per_port` (port, code) — unicité ; tri par défaut : port, order, code.

### `PortDefaultParty` — table `registry_portdefaultparty`
Organisations automatically invited on every call of the port (authorities, nautical services…)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `organization` | FK → Organization |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  | énumération `Role` (ch. 2) |  |

Contraintes et index : `uniq_default_party` (port, organization, role) — unicité.

### `PortCall` — table `registry_portcall`
A tanker call ("escale"). Created by the agency only (EF-1.1); reference immutable

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `reference` | Char(30) | référence / reference | unique ; non modifiable |  |
| `vessel` | FK → Vessel |  | indexé ; on_delete `PROTECT` |  |
| `voyage_number` | Char(40) | numéro de voyage / voyage number | peut être vide |  |
| `agency` | FK → Organization | agence / agency | indexé ; on_delete `PROTECT` |  |
| `status` | Char(14) | statut / status | défaut `CallStatus.DRAFT` ; énumération `CallStatus` (ch. 2) |  |
| `requested_berth_kind` | Char(12) | zone d'opération / operating area | énumération `Berth.Kind` (ch. 2) |  |
| `requested_berth` | FK → Berth |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `berth` | FK → Berth |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `product` | Char(120) | produit / product | peut être vide |  |
| `quantity` | Decimal(14,3) | quantité déclarée / declared quantity | nullable |  |
| `quantity_unit` | Char(8) | unité / unit | défaut `'MT'` ; valeurs : `MT`, `M3`, `BBL` |  |
| `last_port` | Char(80) | dernier port / last port | peut être vide |  |
| `next_port` | Char(80) | prochain port / next port | peut être vide |  |
| `eta` | DateTime | ETA |  |  |
| `etb` | DateTime | ETB | nullable |  |
| `ets` | DateTime | début des opérations estimé / estimated start of operations | nullable |  |
| `etc` | DateTime | fin des opérations estimée / estimated completion | nullable |  |
| `etd` | DateTime | ETD | nullable |  |
| `ata` | DateTime | arrivée réelle / actual arrival | nullable ; non modifiable |  |
| `atb` | DateTime | amarré (all fast) / all fast | nullable ; non modifiable |  |
| `t0` | DateTime | début du transfert / start of transfer | nullable ; non modifiable |  |
| `t1` | DateTime | fin du transfert / end of transfer | nullable ; non modifiable |  |
| `atd` | DateTime | départ réel / actual departure | nullable ; non modifiable |  |
| `nor_at` | DateTime | NOR remise / NOR tendered | nullable ; non modifiable |  |
| `linked_call` | FK → PortCall |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `link_kind` | Char(12) |  | peut être vide ; valeurs : `STS`, `INNER`, `OUTER` |  |
| `created_by` | FK → User |  | indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `declared_at` | DateTime |  | nullable |  |
| `closed_at` | DateTime |  | nullable |  |
| `updated_at` | DateTime |  | horodatage automatique à chaque enregistrement |  |

Contraintes et index : index (port, status) ; index (port, eta) ; tri par défaut : -eta.

Propriétés et méthodes documentées : `anchor_time()` — Actual time when known, otherwise the best estimate.

### `CallStage` — table `registry_callstage`
One operating area of a call, in sequence: a call may go from the roads or an STS area to the quay, from a buoy to the quay, from the quay back to an anchorage… Each stage has its own berth, its own operations (templates added when the stage is planned), its own berthing and leaving times. The first stage is created with the call; the agency or the harbour master plans the next ones; a movement authorization in force is needed to leave a stage (SHIFT_START) and to berth at the next one

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `order` | PositiveSmallInteger | ordre / order |  |  |
| `berth_kind` | Char(12) | zone d'opération / operating area | énumération `Berth.Kind` (ch. 2) |  |
| `berth` | FK → Berth | poste / zone / berth / area | nullable ; indexé ; on_delete `PROTECT` |  |
| `operations` | JSON | modèles d'opération de cette étape / operation templates of this stage | peut être vide ; défaut `list()` |  |
| `planned_from` | DateTime | prévue du / planned from | nullable |  |
| `planned_to` | DateTime | prévue au / planned to | nullable |  |
| `atb` | DateTime | amarré / à couple à cette étape / all fast / alongside at this stage | nullable |  |
| `atd` | DateTime | étape quittée le / left this stage | nullable |  |
| `status` | Char(9) |  | défaut `CallStage.Status.PLANNED` ; énumération `CallStage.Status` (ch. 2) |  |
| `reason` | Char(300) | motif / reason | peut être vide |  |
| `created_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | défaut `now()` |  |
| `cancelled_at` | DateTime |  | nullable |  |
| `cancel_reason` | Char(300) |  | peut être vide |  |

Contraintes et index : `uniq_call_stage_order` (call, order) — unicité ; tri par défaut : call, order.

### `CallTemplateUse` — table `registry_calltemplateuse`
Which template versions a call instantiated — kept forever for interpretability

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `template_version` | FK → TemplateVersion |  | indexé ; on_delete `PROTECT` |  |

Contraintes et index : `uniq_call_template` (call, template_version) — unicité.

### `CallParty` — table `registry_callparty`
Role on a call (EF-12.1): dated and revocable; revocation never purges history

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `organization` | FK → Organization |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  | énumération `Role` (ch. 2) |  |
| `valid_from` | DateTime |  | défaut `now()` |  |
| `valid_until` | DateTime |  | nullable |  |
| `revoked_at` | DateTime |  | nullable |  |
| `revoked_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `revoke_reason` | Char(300) |  | peut être vide |  |
| `granted_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `is_default` | Boolean |  | défaut `False` |  |
| `shore_side` | Boolean |  | défaut `False` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : `uniq_active_call_party` (call, organization, role) — unicité ; index (organization, role).

### `MasterAccessLink` — table `registry_masteraccesslink`
Account-less access to one call (EF-13): the master's, or a party's (terminal, surveyor, owner, provider, marine service) that has no account. Limited validity, revocable, traced; never a deciding role

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `master_name` | Char(160) | nom du titulaire / holder's name | peut être vide | Nominatif : saisi à l'émission, ou par le titulaire à la première utilisation. / Nominative: entered at issuance, or by the holder at first use. |
| `role` | Char(3) | rôle exercé / role exercised | défaut `'NAV'` |  |
| `organization` | FK → Organization | organisation de la partie / party organisation | nullable ; indexé ; on_delete `PROTECT` |  |
| `auto_issued` | Boolean | émis par la plateforme à la déclaration / issued by the platform at the declaration | défaut `False` |  |
| `sent_to` | Char(254) | envoyé à / sent to | peut être vide |  |
| `vessel_position` | Char(6) |  | défaut `'OWN'` ; valeurs : `OWN`, `INNER` |  |
| `token_hash` | Char(64) |  | unique ; non modifiable |  |
| `code_hash` | Char(64) |  | unique ; non modifiable |  |
| `issued_by` | FK → User |  | indexé ; on_delete `PROTECT` |  |
| `issued_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `delivery_channel` | Char(6) |  | défaut `MasterAccessLink.Channel.EMAIL` ; énumération `MasterAccessLink.Channel` (ch. 2) |  |
| `delivery_note` | Char(300) |  | peut être vide |  |
| `expires_at` | DateTime |  |  |  |
| `revoked_at` | DateTime |  | nullable |  |
| `revoked_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `revoke_reason` | Char(300) |  | peut être vide |  |
| `last_used_at` | DateTime |  | nullable |  |

Contraintes et index : tri par défaut : -issued_at.

Propriétés et méthodes documentées : `is_valid()` — The master's link ends shortly after departure (the ship leaves); a party's link lasts until the closure of the call, within its own expiry.

### `Task` — table `registry_task`
A task instantiated from a template version, assigned to a role — never to a person (EF-5.2)

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `stage` | FK → CallStage |  | nullable ; indexé ; on_delete `PROTECT` | Vide pour les tâches de l'escale dans son ensemble (socle commun et première étape) ; renseigné pour les tâches ajoutées avec une étape ultérieure. / Empty for the tasks of the call as a whole (common base and first stage); set for the tasks added with a later stage. |
| `template_task` | FK → TemplateTask |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `template_code` | Char(10) |  | peut être vide |  |
| `number` | Char(10) |  |  |  |
| `section_fr` | Char(150) |  | peut être vide |  |
| `section_en` | Char(150) |  | peut être vide |  |
| `title_fr` | Char(400) |  |  |  |
| `title_en` | Char(400) |  |  |  |
| `role` | Char(3) |  |  |  |
| `co_roles` | JSON |  | peut être vide ; défaut `list()` |  |
| `joint` | Boolean |  | défaut `False` |  |
| `nature` | Char(1) |  | énumération `Nature` (ch. 2) |  |
| `criticality` | Char(1) |  | énumération `Criticality` (ch. 2) |  |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `anchor` | Char(3) |  | peut être vide ; énumération `Anchor` (ch. 2) |  |
| `offset_minutes` | Integer |  | défaut `0` |  |
| `timing_fr` | Char(60) |  | peut être vide |  |
| `timing_en` | Char(60) |  | peut être vide |  |
| `request_type_code` | Char(40) |  | peut être vide |  |
| `request_side` | Char(8) |  | peut être vide |  |
| `milestone_codes` | JSON |  | peut être vide ; défaut `list()` |  |
| `document_type_code` | Char(40) |  | peut être vide |  |
| `auto_event` | Char(30) |  | peut être vide |  |
| `continuous` | Boolean |  | défaut `False` |  |
| `not_applicable_allowed` | Boolean |  | défaut `True` |  |
| `is_ad_hoc` | Boolean | tâche ad hoc / ad hoc task | défaut `False` |  |
| `order` | PositiveInteger |  | défaut `0` |  |
| `due_at` | DateTime |  | nullable |  |
| `status` | Char(8) |  | défaut `TaskStatus.PENDING` ; énumération `TaskStatus` (ch. 2) |  |
| `alert_level` | Char(10) |  | défaut `AlertLevel.NONE` ; énumération `AlertLevel` (ch. 2) |  |
| `completed_at` | DateTime |  | nullable |  |
| `completed_role` | Char(3) |  | peut être vide |  |
| `completed_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `completed_by_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `completion_note` | Text |  | peut être vide |  |
| `na_reason` | Text |  | peut être vide |  |
| `evidence` | Char(60) |  | peut être vide | kind:id of the object proving completion |
| `created_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : index (call, role) ; index (status, due_at) ; tri par défaut : call, order, number.

### `TaskSignature` — table `registry_tasksignature`
Signature / countersignature / contest on a task (joint tasks, co-signed entries)

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `task` | FK → Task |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  |  |  |
| `kind` | Char(14) |  | énumération `TaskSignature.Kind` (ch. 2) |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `signer_label` | Char(200) |  |  |  |
| `signed_at` | DateTime |  | défaut `now()` |  |
| `comment` | Text |  | peut être vide |  |
| `seal` | Char(64) |  |  |  |

Contraintes et index : tri par défaut : signed_at.

### `Milestone` — table `registry_milestone`
A dated fact with a single emitter (EF-3). Corrections are new, linked records

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `type` | FK → MilestoneType |  | indexé ; on_delete `PROTECT` |  |
| `stage` | FK → CallStage |  | nullable ; indexé ; on_delete `PROTECT` | L'étape de l'escale à laquelle le jalon appartient (une escale peut accoster plusieurs fois). / The stage of the call the milestone belongs to (a call may berth several times). |
| `declared_at` | DateTime | heure déclarée / declared time |  |  |
| `recorded_at` | DateTime | heure système / system time | défaut `now()` |  |
| `device_recorded_at` | DateTime | heure saisie sur l'appareil / time captured on the device | nullable |  |
| `deferred` | Boolean | saisie différée / deferred entry | défaut `False` |  |
| `source` | Char(8) |  | défaut `EntrySource.ONLINE` ; énumération `EntrySource` (ch. 2) |  |
| `emitter_role` | Char(6) |  |  |  |
| `emitter_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `emitter_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `emitter_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `emitter_label` | Char(200) |  |  |  |
| `countersigner_roles` | JSON |  | peut être vide ; défaut `list()` |  |
| `cause` | FK → InterruptionCause |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `cause_reason` | Char(300) |  | peut être vide |  |
| `related` | FK → Milestone |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `is_rectification` | Boolean |  | défaut `False` |  |
| `rectification_reason` | Char(300) |  | peut être vide |  |
| `is_conflict` | Boolean | saisie concurrente / competing entry | défaut `False` |  |
| `note` | Text |  | peut être vide |  |
| `payload` | JSON |  | peut être vide ; défaut `dict()` |  |
| `client_uuid` | UUID |  | unique ; nullable |  |
| `seal` | Char(64) |  |  |  |

Contraintes et index : index (call, type) ; tri par défaut : declared_at, recorded_at.

### `MilestoneSignature` — table `registry_milestonesignature`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `milestone` | FK → Milestone |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  |  |  |
| `state` | Char(14) |  | énumération `CountersignState` (ch. 2) |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `signer_label` | Char(200) |  |  |  |
| `at` | DateTime |  | défaut `now()` |  |
| `comment` | Text |  | peut être vide |  |
| `dispute` | FK → Dispute |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `seal` | Char(64) |  |  |  |

Contraintes et index : tri par défaut : at.

### `ServiceRequest` — table `registry_servicerequest`
Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `type` | FK → RequestType |  | indexé ; on_delete `PROTECT` |  |
| `reference` | Char(40) |  | unique |  |
| `status` | Char(14) |  | défaut `RequestStatus.CREATED` ; énumération `RequestStatus` (ch. 2) |  |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `requester_role` | Char(3) |  |  |  |
| `requester_org` | FK → Organization |  | indexé ; on_delete `PROTECT` |  |
| `requester_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `provider_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `data` | JSON |  | peut être vide ; défaut `dict()` |  |
| `submitted_at` | DateTime |  | nullable |  |
| `due_at` | DateTime |  | nullable |  |
| `decision` | Char(14) |  | peut être vide ; énumération `RequestStatus` (ch. 2) |  |
| `decision_role` | Char(3) |  | peut être vide |  |
| `decision_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `decision_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `decided_at` | DateTime |  | nullable |  |
| `decision_reason` | Text |  | peut être vide |  |
| `decision_conditions` | Text |  | peut être vide |  |
| `scheduled_for` | DateTime |  | nullable |  |
| `executed_at` | DateTime |  | nullable |  |
| `executed_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `updated_at` | DateTime |  | horodatage automatique à chaque enregistrement |  |

Contraintes et index : index (call, status) ; tri par défaut : -created_at.

### `Authorization` — table `registry_authorization`
Distinct object produced by an approval (EF-2.5). Always carries an expiry date

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `request` | FK → ServiceRequest |  | unique ; on_delete `PROTECT` |  |
| `number` | Char(40) |  | unique |  |
| `type_code` | Char(40) |  |  |  |
| `issuer_role` | Char(3) |  |  |  |
| `issuer_org` | FK → Organization |  | indexé ; on_delete `PROTECT` |  |
| `issuer_user` | FK → User |  | indexé ; on_delete `PROTECT` |  |
| `issuer_label` | Char(200) |  |  |  |
| `scope` | Text |  |  |  |
| `conditions` | Text |  | peut être vide |  |
| `valid_from` | DateTime |  |  |  |
| `valid_until` | DateTime |  |  |  |
| `signed_at` | DateTime |  | défaut `now()` |  |
| `seal` | Char(64) |  |  |  |
| `verification_code` | Char(12) |  | unique |  |
| `berth` | FK → Berth |  | nullable ; indexé ; on_delete `PROTECT` |  |

Contraintes et index : tri par défaut : -signed_at.

### `AuthorizationEvent` — table `registry_authorizationevent`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `authorization` | FK → Authorization |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(10) |  | énumération `AuthorizationEvent.Kind` (ch. 2) |  |
| `at` | DateTime |  | défaut `now()` |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `reason` | Char(300) |  | peut être vide |  |

### `Document` — table `registry_document`
A document of the call (EF-7). Signed = frozen; a change creates a new version

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `type` | FK → DocumentType |  | indexé ; on_delete `PROTECT` |  |
| `title` | Char(250) | titre / title |  |  |
| `version` | PositiveInteger |  | défaut `1` |  |
| `previous` | FK → Document |  | unique ; nullable ; on_delete `PROTECT` |  |
| `status` | Char(10) |  | défaut `DocumentStatus.ISSUED` ; énumération `DocumentStatus` (ch. 2) |  |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `counterpart_role` | Char(3) | contrepartie (N3) / counterpart (N3) | peut être vide |  |
| `audience_roles` | JSON | lecteurs de ce document (N2) / readers of this document (N2) | peut être vide ; défaut `list()` |  |
| `issuer_role` | Char(3) |  |  |  |
| `issuer_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `issuer_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `issuer_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `issuer_label` | Char(200) |  |  |  |
| `file` | File |  |  |  |
| `original_name` | Char(255) |  |  |  |
| `mime_type` | Char(120) |  | peut être vide |  |
| `size` | PositiveBigInteger |  | défaut `0` |  |
| `sha256` | Char(64) | empreinte (SHA-256) / fingerprint (SHA-256) |  |  |
| `required_signers` | JSON |  | peut être vide ; défaut `list()` |  |
| `generated` | Boolean |  | défaut `False` |  |
| `retention_until` | Date |  | nullable |  |
| `task` | FK → Task |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `deferred` | Boolean |  | défaut `False` |  |
| `client_uuid` | UUID |  | unique ; nullable |  |
| `cancel_reason` | Char(300) |  | peut être vide |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `issued_at` | DateTime |  | nullable |  |

Contraintes et index : index (call, type) ; tri par défaut : -created_at.

Propriétés et méthodes documentées : `display_title` — The issuer's title, or the type label in the reader's language when no title was given.

### `DocumentSignature` — table `registry_documentsignature`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `document` | FK → Document |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  |  |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `signer_label` | Char(200) |  |  |  |
| `signed_at` | DateTime |  | défaut `now()` |  |
| `document_sha256` | Char(64) |  |  |  |
| `signature_image` | Text |  | peut être vide | Hand-drawn signature (PNG data URL), optional |
| `seal` | Char(64) |  |  |  |

Contraintes et index : tri par défaut : signed_at.

### `Measurement` — table `registry_measurement`
A quantity measured by ship, shore and surveyor (EF-8.1). The platform never picks a reference

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(8) |  | énumération `Measurement.Kind` (ch. 2) |  |
| `product` | Char(120) |  | peut être vide |  |
| `unit` | Char(8) |  | défaut `'MT'` ; valeurs : `MT`, `M3`, `BBL` |  |
| `tolerance_pct` | Decimal(5,3) |  | défaut `Decimal('0.300')` |  |
| `created_role` | Char(3) |  |  |  |
| `created_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

Contraintes et index : tri par défaut : created_at.

Propriétés et méthodes documentées : `differences()` — Every pair of declared figures, compared both ways round: no figure is ever the reference ; `discrepancy()` — The ship/shore difference of EF-8.1 — the one that carries the tolerance (EF-8.2) ; `is_complete` — EF-8.1: a quantity carries a ship value and a shore value (the surveyor's when there is one).

### `MeasurementValue` — table `registry_measurementvalue`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `measurement` | FK → Measurement |  | indexé ; on_delete `PROTECT` |  |
| `party` | Char(8) |  | énumération `MeasurementParty` (ch. 2) |  |
| `value` | Decimal(16,3) |  |  |  |
| `temperature_c` | Decimal(6,2) |  | nullable |  |
| `density` | Decimal(7,4) |  | nullable |  |
| `entered_role` | Char(3) |  |  |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `entered_label` | Char(200) |  |  |  |
| `declared_at` | DateTime |  | défaut `now()` |  |
| `entered_at` | DateTime |  | défaut `now()` |  |
| `deferred` | Boolean |  | défaut `False` |  |
| `source` | Char(8) |  | défaut `EntrySource.ONLINE` ; énumération `EntrySource` (ch. 2) |  |
| `supersedes` | FK → MeasurementValue |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `note` | Char(300) |  | peut être vide |  |
| `client_uuid` | UUID |  | unique ; nullable |  |
| `seal` | Char(64) |  |  |  |

Contraintes et index : tri par défaut : entered_at.

### `PumpingLogEntry` — table `registry_pumpinglogentry`
Manual in V1; the same table accepts an automatic feed in V2 without schema change (EF-8.3)

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `declared_at` | DateTime |  |  |  |
| `recorded_at` | DateTime |  | défaut `now()` |  |
| `role` | Char(3) |  |  |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `entered_label` | Char(200) |  |  |  |
| `manifold_pressure_bar` | Decimal(7,2) |  | nullable |  |
| `flow_rate_m3h` | Decimal(9,2) |  | nullable |  |
| `temperature_c` | Decimal(6,2) |  | nullable |  |
| `note` | Char(300) |  | peut être vide |  |
| `source` | Char(10) |  | défaut `'MANUAL'` ; valeurs : `MANUAL`, `AUTOMATIC` |  |
| `device_id` | Char(80) |  | peut être vide |  |
| `deferred` | Boolean |  | défaut `False` |  |
| `client_uuid` | UUID |  | unique ; nullable |  |

Contraintes et index : tri par défaut : declared_at.

### `Dispute` — table `registry_dispute`
First-class contest (EF-4). Never blocks the operation; the platform never arbitrates

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `reference` | Char(40) |  | unique |  |
| `subject` | Char(250) | objet / subject |  |  |
| `target_kind` | Char(14) |  | valeurs : `MILESTONE`, `MEASUREMENT`, `AUTHORIZATION`, `DOCUMENT`, `TASK`, `OTHER` |  |
| `target_id` | PositiveBigInteger |  | nullable |  |
| `status` | Char(18) |  | défaut `DisputeStatus.OPEN` ; énumération `DisputeStatus` (ch. 2) |  |
| `opened_role` | Char(3) |  |  |  |
| `opened_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `opened_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `opened_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `opened_label` | Char(200) |  |  |  |
| `counterpart_role` | Char(3) |  | peut être vide |  |
| `counterpart_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `counterpart_master` | Boolean |  | défaut `False` |  |
| `auto_created` | Boolean |  | défaut `False` | Created by the platform on a synchronisation conflict |
| `opened_at` | DateTime |  | défaut `now()` |  |
| `closed_at` | DateTime |  | nullable |  |

Contraintes et index : tri par défaut : -opened_at.

### `DisputeEntry` — table `registry_disputeentry`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `dispute` | FK → Dispute |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(10) |  | énumération `DisputeEntry.Kind` (ch. 2) |  |
| `role` | Char(3) |  |  |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `author_label` | Char(200) |  |  |  |
| `text` | Text |  |  |  |
| `at` | DateTime |  | défaut `now()` |  |
| `seal` | Char(64) |  |  |  |

Contraintes et index : tri par défaut : at.

### `Thread` — table `registry_thread`
Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `subject` | Char(250) | objet / subject |  |  |
| `confidentiality` | Char(2) |  | défaut `Confidentiality.N2` ; énumération `Confidentiality` (ch. 2) |  |
| `participant_roles` | JSON | rôles participants / participating roles | défaut `list()` |  |
| `related_kind` | Char(14) |  | peut être vide |  |
| `related_id` | PositiveBigInteger |  | nullable |  |
| `created_role` | Char(3) |  |  |  |
| `created_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `last_message_at` | DateTime |  | nullable |  |

Contraintes et index : tri par défaut : -last_message_at, -created_at.

### `Message` — table `registry_message`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `thread` | FK → Thread |  | indexé ; on_delete `PROTECT` |  |
| `role` | Char(3) |  |  |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `author_label` | Char(200) |  |  |  |
| `body` | Text |  |  |  |
| `document` | FK → Document |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `sent_at` | DateTime |  | défaut `now()` |  |

Contraintes et index : tri par défaut : sent_at.

### `Alert` — table `registry_alert`
Every alert emitted is a piece of the file (EF-6.4): time-stamped, kept, on the statement of facts

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(10) |  | énumération `AlertKind` (ch. 2) |  |
| `task` | FK → Task |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `milestone` | FK → Milestone |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `measurement` | FK → Measurement |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `blocking` | Boolean |  | défaut `False` |  |
| `recipient_roles` | JSON |  | défaut `list()` |  |
| `message_fr` | Char(500) |  |  |  |
| `message_en` | Char(500) |  |  |  |
| `emitted_at` | DateTime |  | défaut `now()` |  |
| `template_code` | Char(10) |  | peut être vide |  |

Contraintes et index : tri par défaut : -emitted_at.

### `Notification` — table `registry_notification`
Per-user notification. Always derived from an object or a deadline (EF-18.2)

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `user` | FK → User |  | indexé ; on_delete `PROTECT` |  |
| `call` | FK → PortCall |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `alert` | FK → Alert |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `dedupe_key` | Char(160) |  |  |  |
| `title_fr` | Char(300) |  |  |  |
| `title_en` | Char(300) |  |  |  |
| `url` | Char(300) |  | peut être vide |  |
| `realtime` | Boolean |  | défaut `False` |  |
| `blocking` | Boolean |  | défaut `False` |  |
| `created_at` | DateTime |  | défaut `now()` |  |
| `read_at` | DateTime |  | nullable |  |
| `email_sent_at` | DateTime |  | nullable |  |
| `sms_sent_at` | DateTime |  | nullable |  |
| `digest_sent_at` | DateTime |  | nullable |  |

Contraintes et index : `uniq_notification_per_event` (user, dedupe_key) — unicité ; tri par défaut : -created_at.

### `ChainHead` — table `registry_chainhead`
Head of a hash chain. Row-locked during appends so that the chain stays linear

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `chain` | Char(10) |  | valeurs : `journal`, `audit` |  |
| `last_seq` | PositiveBigInteger |  | défaut `0` |  |
| `last_hash` | Char(64) |  | défaut `'0000000000000000000000000000000000000000000000000000000000000000'` |  |

Contraintes et index : `uniq_chain_head` (port, chain) — unicité.

### `JournalEntry` — table `registry_journalentry`
The call journal: every act, refusal and alert, chained cryptographically (ENF-4.1)

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `call` | FK → PortCall |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `seq` | PositiveBigInteger |  |  |  |
| `at` | DateTime |  | défaut `now()` |  |
| `actor_role` | Char(6) |  | peut être vide |  |
| `actor_user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `actor_master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `actor_org` | FK → Organization |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `actor_label` | Char(200) |  |  |  |
| `action` | Char(60) |  |  |  |
| `object_kind` | Char(30) |  | peut être vide |  |
| `object_id` | PositiveBigInteger |  | nullable |  |
| `visible_roles` | JSON |  | défaut `list()` | Roles that may read this entry; ['*'] = every party |
| `summary_fr` | Char(500) |  |  |  |
| `summary_en` | Char(500) |  |  |  |
| `payload` | JSON |  | peut être vide ; défaut `dict()` |  |
| `prev_hash` | Char(64) |  |  |  |
| `hash` | Char(64) |  | unique |  |
| `timestamp_provider` | Char(20) |  | défaut `'local'` |  |
| `timestamp_token` | Text |  | peut être vide |  |

Contraintes et index : `uniq_journal_seq` (port, seq) — unicité ; index (call, seq) ; index (action) ; tri par défaut : seq.

### `AuditEntry` — table `registry_auditentry`
Who saw, entered, approved, exported what and when (ENF-3.4). Chained like the journal

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `call` | FK → PortCall |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `seq` | PositiveBigInteger |  |  |  |
| `at` | DateTime |  | défaut `now()` |  |
| `user` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `master` | FK → MasterAccessLink |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `actor_label` | Char(200) |  |  |  |
| `action` | Char(40) |  |  |  |
| `object_kind` | Char(30) |  | peut être vide |  |
| `object_id` | PositiveBigInteger |  | nullable |  |
| `detail` | Char(300) |  | peut être vide |  |
| `ip` | GenericIPAddress |  | nullable |  |
| `user_agent` | Char(300) |  | peut être vide |  |
| `prev_hash` | Char(64) |  |  |  |
| `hash` | Char(64) |  | unique |  |

Contraintes et index : index (port, seq) ; index (call, at) ; tri par défaut : seq.

### `WebhookSubscription` — table `registry_webhooksubscription`
Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `name` | Char(120) |  |  |  |
| `url` | Char(400) |  |  |  |
| `secret` | Char(128) |  | défaut `_new_token()` |  |
| `actions` | JSON |  | peut être vide ; défaut `list()` | Journal actions to publish; empty = all N1 actions |
| `is_active` | Boolean |  | défaut `True` |  |
| `created_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |

### `WebhookDelivery` — table `registry_webhookdelivery`
Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `subscription` | FK → WebhookSubscription |  | indexé ; on_delete `PROTECT` |  |
| `entry` | FK → JournalEntry |  | indexé ; on_delete `PROTECT` |  |
| `status` | Char(8) |  | défaut `'PENDING'` ; valeurs : `PENDING`, `SENT`, `FAILED` |  |
| `attempts` | PositiveSmallInteger |  | défaut `0` |  |
| `next_attempt_at` | DateTime |  | défaut `now()` |  |
| `last_error` | Char(300) |  | peut être vide |  |
| `sent_at` | DateTime |  | nullable |  |

Contraintes et index : index (status, next_attempt_at).

## 1.3 Application `ais — tableau AIS`

### `VesselStatic` — table `ais_vesselstatic`
What a vessel broadcasts about itself (AIS message 5 / 24): one row per MMSI and port, updated in place

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `mmsi` | Char(9) |  |  |  |
| `imo` | Char(7) |  | peut être vide |  |
| `name` | Char(120) |  | peut être vide |  |
| `call_sign` | Char(20) |  | peut être vide |  |
| `ship_type` | PositiveSmallInteger |  | nullable |  |
| `destination` | Char(40) |  | peut être vide |  |
| `draught_m` | Decimal(4,1) |  | nullable |  |
| `updated_at` | DateTime |  |  |  |

Contraintes et index : `uniq_ais_static_per_port` (port, mmsi) — unicité.

### `VesselPosition` — table `ais_vesselposition`
One position report (AIS message 1, 2, 3, 18, 19 or 27)

Garde-fou : ordinaire. Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `mmsi` | Char(9) |  |  |  |
| `latitude` | Decimal(9,6) |  |  |  |
| `longitude` | Decimal(9,6) |  |  |  |
| `speed_kn` | Decimal(5,1) |  | nullable |  |
| `course_deg` | Decimal(5,1) |  | nullable |  |
| `heading_deg` | PositiveSmallInteger |  | nullable |  |
| `nav_status` | PositiveSmallInteger |  | nullable |  |
| `observed_at` | DateTime |  |  |  |
| `received_at` | DateTime |  | horodatage automatique à la création ; non modifiable |  |
| `source` | Char(40) |  |  |  |

Contraintes et index : `uniq_ais_report` (port, mmsi, observed_at) — unicité ; index (port, mmsi, -observed_at) ; index (port, -observed_at).

## 1.4 Application `ai — assistance IA (traces)`

### `AssistantRun` — table `ai_assistantrun`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port` | FK → Port |  | indexé ; on_delete `PROTECT` |  |
| `call` | FK → PortCall |  | nullable ; indexé ; on_delete `PROTECT` | Vide pour les fonctions au niveau du port (point, question). / Empty for the port-level features (brief, question). |
| `feature` | Char(8) |  | énumération `AssistantRun.Feature` (ch. 2) |  |
| `requested_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `requested_role` | Char(3) |  |  |  |
| `model` | Char(80) |  |  |  |
| `input_digest` | Char(64) | empreinte des données envoyées (SHA-256) / fingerprint of the data sent (SHA-256) |  |  |
| `input_inventory` | JSON | objets à partir desquels la requête a été construite / objects the request was built from | défaut `list()` |  |
| `output` | JSON |  | défaut `dict()` |  |
| `status` | Char(5) |  | énumération `AssistantRun.Status` (ch. 2) |  |
| `error` | Char(300) |  | peut être vide |  |
| `duration_ms` | PositiveInteger |  | défaut `0` |  |
| `created_at` | DateTime |  | défaut `now()` |  |

Contraintes et index : tri par défaut : -created_at.

### `ExtractionReview` — table `ai_extractionreview`
Values proposed by the assistant: shown as "pre-filled" and saved only after a person validates them

Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `default`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `run` | FK → AssistantRun |  | unique ; on_delete `PROTECT` |  |
| `call` | FK → PortCall |  | indexé ; on_delete `PROTECT` |  |
| `document` | FK → Document |  | indexé ; on_delete `PROTECT` |  |
| `kind` | Char(20) |  |  |  |
| `proposed` | JSON |  | défaut `dict()` |  |
| `status` | Char(9) |  | défaut `ExtractionReview.Status.PROPOSED` ; énumération `ExtractionReview.Status` (ch. 2) |  |
| `validated` | JSON |  | nullable |  |
| `validated_by` | FK → User |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `validated_label` | Char(200) |  | peut être vide |  |
| `validated_at` | DateTime |  | nullable |  |
| `created_at` | DateTime |  | défaut `now()` |  |

Contraintes et index : tri par défaut : -created_at.

## 1.5 Application `secure — domaine sûreté N4 (base distincte)`

### `SecureItem` — table `secure_secureitem`
Garde-fou : sans suppression (UPDATE autorisé, DELETE refusé en base). Base : `secure`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `reference` | Char(40) |  | unique |  |
| `port_code` | Char(10) |  | indexé |  |
| `call_id` | BigInteger |  | indexé |  |
| `call_reference` | Char(30) |  |  |  |
| `vessel_name` | Char(120) |  |  |  |
| `kind` | Char(14) |  | énumération `SecureItem.Kind` (ch. 2) |  |
| `status` | Char(14) |  | défaut `SecureItem.Status.SUBMITTED` ; énumération `SecureItem.Status` (ch. 2) |  |
| `submitted_by_id` | BigInteger |  |  |  |
| `submitted_by_label` | Char(200) |  |  |  |
| `submitted_role` | Char(3) |  |  |  |
| `submitted_org_label` | Char(200) |  |  |  |
| `submitted_at` | DateTime |  | défaut `now()` |  |
| `due_at` | DateTime |  | nullable |  |
| `payload_enc` | Text |  |  | Fernet-encrypted JSON (N4 keys) |
| `decision_enc` | Text |  | peut être vide |  |
| `decided_by_id` | BigInteger |  | nullable |  |
| `decided_by_label` | Char(200) |  | peut être vide |  |
| `decided_at` | DateTime |  | nullable |  |
| `embarked_at` | DateTime |  | nullable |  |
| `disembarked_at` | DateTime |  | nullable |  |
| `anti_intrusion_confirmed_at` | DateTime |  | nullable |  |
| `updated_at` | DateTime |  | horodatage automatique à chaque enregistrement |  |

Contraintes et index : tri par défaut : -submitted_at.

### `SecureAttachment` — table `secure_secureattachment`
Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `secure`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `item` | FK → SecureItem |  | indexé ; on_delete `PROTECT` |  |
| `name` | Char(255) |  |  |  |
| `mime_type` | Char(120) |  | peut être vide |  |
| `size` | PositiveBigInteger |  | défaut `0` |  |
| `sha256` | Char(64) |  |  |  |
| `data_enc` | Binary |  | non modifiable | Encrypted content (N4 keys) |
| `uploaded_by_id` | BigInteger |  |  |  |
| `uploaded_by_label` | Char(200) |  |  |  |
| `at` | DateTime |  | défaut `now()` |  |

### `SecureChainHead` — table `secure_securechainhead`
Garde-fou : ordinaire. Base : `secure`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port_code` | Char(10) |  | unique |  |
| `last_seq` | PositiveBigInteger |  | défaut `0` |  |
| `last_hash` | Char(64) |  | défaut `'0000000000000000000000000000000000000000000000000000000000000000'` |  |

### `SecureSequence` — table `secure_securesequence`
Garde-fou : ordinaire. Base : `secure`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port_code` | Char(10) |  |  |  |
| `year` | PositiveSmallInteger |  |  |  |
| `last_value` | PositiveInteger |  | défaut `0` |  |

Contraintes et index : `uniq_secure_sequence` (port_code, year) — unicité.

### `SecureAccessLog` — table `secure_secureaccesslog`
Nominative log of every access to N4 data, chained (EF-12.4)

Garde-fou : ajout seul (ni UPDATE ni DELETE en base). Base : `secure`.

| Champ | Type | Libellé FR / EN | Règles | Aide |
|---|---|---|---|---|
| `id` | BigAuto | ID | clé primaire (auto) |  |
| `port_code` | Char(10) |  | indexé |  |
| `seq` | PositiveBigInteger |  |  |  |
| `item` | FK → SecureItem |  | nullable ; indexé ; on_delete `PROTECT` |  |
| `at` | DateTime |  | défaut `now()` |  |
| `user_id` | BigInteger |  |  |  |
| `user_label` | Char(200) |  |  |  |
| `role` | Char(3) |  |  |  |
| `action` | Char(20) |  |  |  |
| `detail` | Char(300) |  | peut être vide |  |
| `ip` | GenericIPAddress |  | nullable |  |
| `notified` | Boolean |  | défaut `False` |  |
| `prev_hash` | Char(64) |  |  |  |
| `hash` | Char(64) |  | unique |  |

Contraintes et index : `uniq_secure_log_seq` (port_code, seq) — unicité ; tri par défaut : -seq.
