# Format d'export et de réversibilité — `fluxaa-port-export/1.0`

Livrable contractuel (EF-15.3). Ce document suffit à relire, recharger ou vérifier un export **sans la plateforme**. Le format est ouvert : une archive ZIP, des fichiers JSON en UTF-8 et les pièces jointes dans leur format d'origine.

## 1. Deux exports

| Export | Qui | Comment | Contenu |
|---|---|---|---|
| **Escale** | armateur/affréteur (COM) et direction du port (DIR), conformément à FLX-SPEC-001 §5 | bouton « Exporter » de l'escale, ou `GET /api/v1/calls/<référence>/export/` | ce que **le rôle de l'exportateur** peut voir de cette escale |
| **Port (réversibilité)** | administrateur fonctionnel du port, exploitant | `python manage.py export_port <CODE> <fichier.zip>` | toutes les escales du port, les deux chaînes complètes (journal et accès), les traces de l'assistant |

Dans les deux cas, **rien du domaine sûreté N4** : il est dans une autre base, chiffrée avec d'autres clés, et ne peut pas être exporté par ces voies (EF-10.3, EF-12.4). Les **motifs de refus de vetting** sont retirés de tout export (critère d'acceptation EF-2.6). Chaque export est inscrit au journal des accès.

## 2. Structure de l'archive

Export d'escale :

```
call.json                 contenu de l'escale (§3)
documents/<id>_<nom>      pièces jointes visibles, octet pour octet
manifest.json             inventaire signé (§4)
```

Export de port :

```
calls/<référence>/call.json
calls/<référence>/documents/<id>_<nom>
journal.json              chaîne complète du journal du port (§5)
audit.json                chaîne complète du journal des accès (§5)
assistant.json            requêtes à l'assistant IA et validations (§6)
manifest.json
```

## 3. `call.json`

Dates et heures : ISO 8601 avec fuseau, en UTC. Montants et quantités : chaînes décimales (aucune perte d'arrondi). Rôles : codes FLX-SPEC-001 (`AGE`, `NAV`, `TER`, `CAP`, `APO`, `SVC`, `ADM`, `SUR`, `INS`, `COM`, `PRE`, `DIR`).

| Clé | Contenu |
|---|---|
| `reference`, `status` | référence immuable `PORT-AAAA-SÉQ`, statut du cycle de vie |
| `port` | `code`, `name`, `timezone` |
| `vessel` | `imo`, `name`, `flag`, `type`, `dwt` |
| `voyage`, `agency`, `operating_area`, `berth`, `product`, `quantity`, `quantity_unit` | |
| `templates` | gabarits et **versions** instanciés à la création (`[{code, version}]`) |
| `estimates` | `eta`, `etb`, `ets`, `etc`, `etd` |
| `actuals` | `ata`, `nor_at`, `atb`, `t0`, `t1`, `atd` |
| `parties` | `organization`, `role`, `valid_from`, `valid_until`, `revoked_at` |
| `milestones` | `id`, `type`, `declared_at` (heure déclarée), `recorded_at` (heure système), `device_recorded_at` (hors ligne), `deferred`, `source` (`ONLINE`, `OFFLINE`, `PAPER`, `AIS`, `SYSTEM`), `emitter_role`, `emitter`, `cause`, `cause_reason`, `related` (fin d'interruption → début), `rectification`, `conflict`, `seal`, `countersignatures` (`{rôle: état}`), `countersignature_state` |
| `tasks` | `code`, `title_fr`, `title_en`, `role`, `nature`, `criticality`, `due_at`, `status`, `completed_at`, `completed_role`, `na_reason` |
| `requests` | `reference`, `type`, `status`, `requester_role`, `data` (champs du formulaire), `submitted_at`, `decision`, `decision_role`, `decided_at`, `conditions`, `reason` (absent pour le vetting), `authorization` (`number`, `valid_from`, `valid_until`, `seal`, `verification_code`, `cancelled`) |
| `documents` | `id`, `type`, `title`, `version`, `status`, `confidentiality`, `issuer_role`, `issuer`, `issued_at`, `sha256`, `file` (chemin dans l'archive), `signatures` (`role`, `signer`, `at`, `seal`, `document_sha256`) |
| `measurements` | `kind`, `unit`, `tolerance_pct`, `values` (toutes, corrections comprises : `party`, `value`, `role`, `by`, `declared_at`, `entered_at`, `deferred`, `supersedes`, `seal`), `complete`, `differences` (`between`, `difference`, `percent`, `outside_tolerance` pour la paire bord/terre) |
| `pumping_log` | `declared_at`, `recorded_at`, `role`, `pressure_bar`, `rate_m3h`, `temperature_c`, `source`, `deferred` |
| `disputes` | `reference`, `subject`, `target`, `status`, `opened_role`, `counterpart_role`, `opened_at`, `closed_at`, `automatic` et, si l'exportateur est partie ou capitainerie, `entries` (`kind`, `role`, `by`, `text`, `at`, `seal`) |
| `alerts` | `kind`, `emitted_at`, `message_fr`, `message_en`, `blocking` |
| `journal` | entrées visibles par l'exportateur : `seq`, `at`, `action`, `role`, `actor`, `summary_fr`, `summary_en`, `hash`, `prev_hash`, `timestamp_provider` |

Toutes les valeurs successives sont présentes : une rectification, une correction de mesure ou une nouvelle version de document **s'ajoutent** à l'original, qui reste dans l'export.

## 4. `manifest.json`

```json
{
  "format": "fluxaa-port-export/1.0",
  "scope": "port",
  "port": "TGLFW",
  "generated_at": "2026-10-24T21:40:12.031+00:00",
  "files": {"calls/TGLFW-2026-0001/call.json": "<sha256>", "journal.json": "<sha256>", "…": "…"},
  "seal": "<HMAC-SHA256 de files>"
}
```

* `files` donne l'empreinte SHA-256 de **chaque** fichier de l'archive.
* `seal` = HMAC-SHA256, avec la clé de scellement du port (`FLUXAA_SIGNING_KEY`), du JSON canonique de `files`. Il prouve que l'inventaire a été produit par la plateforme ; il se vérifie avec la clé, que l'exploitant remet au port avec l'export de fin de contrat.
* L'export d'escale ajoute `exported_by`, `exported_roles` et `call`.

## 5. Chaînes `journal.json` et `audit.json`

Chaque ligne contient le **matériau exact** qui a été haché :

```json
{"material": {"seq": 41, "port": 2, "call": 5, "at": "2026-10-24T09:30:00+00:00",
              "actor_role": "SVC", "actor_user": 17, "actor_master": null, "actor_org": 14,
              "actor_label": "Pilote TGLFW — Services nautiques", "action": "milestone.recorded",
              "object_kind": "milestone", "object_id": 88, "visible_roles": ["*"],
              "summary_fr": "…", "summary_en": "…", "payload": {…}, "prev_hash": "<empreinte n-1>"},
 "hash": "<empreinte n>", "call_reference": "TGLFW-2026-0001",
 "timestamp_provider": "local", "timestamp_token": "<HMAC>"}
```

Règles de vérification :

1. **JSON canonique** : clés triées, séparateurs `,` et `:` sans espace, Unicode non échappé (`json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`).
2. `hash = SHA-256(JSON canonique de material)` — aucune clé n'est nécessaire.
3. Les numéros `seq` se suivent à partir de 1 ; `material.prev_hash` est le `hash` de l'entrée précédente ; celui de la première vaut 64 zéros.
4. Horodatage `local` : `timestamp_token = HMAC-SHA256(clé, JSON canonique de {"digest": hash, "at": material.at, "provider": "local"})`. Avec un horodatage qualifié (point ouvert O04), `timestamp_provider` vaudra `rfc3161` et le jeton sera une réponse RFC 3161 vérifiable auprès de l'autorité d'horodatage.

`audit.json` suit la même règle avec le matériau `{seq, port, call, at, user, master, actor_label, action, object_kind, object_id, detail, ip, prev_hash}`.

La chaîne est **par port** : les entrées de plusieurs escales s'y succèdent. L'export d'escale ne contient que les entrées visibles par l'exportateur, sans le matériau complet ; seul l'export de port permet de recalculer toute la chaîne.

## 6. `assistant.json`

`runs` : chaque requête à l'assistant IA (`feature` : `EXTRACT`, `REVIEW`, `SUMMARY`, `REMARKS`), avec l'empreinte SHA-256 des données envoyées (`input_digest`), l'inventaire des objets dont elles proviennent (`input_inventory`, par exemple `["document:12"]`), le statut et la réponse. `extractions` : les valeurs proposées, la décision (`APPLIED` ou `DISMISSED`), ce qui a été validé et par qui. Aucune donnée N4 n'y figure : l'assistant n'en reçoit jamais.

## 7. Sceaux des actes

Les champs `seal` des jalons, contresignatures, valeurs de mesure, entrées de contestation, signatures de documents et autorisations sont des HMAC-SHA256 du JSON canonique de l'acte, calculés à l'enregistrement avec la clé de scellement. Les pièces jointes se vérifient par leur `sha256` (et `document_sha256` dans chaque signature : la signature porte sur cette version exacte).

## 8. Vérifier un export

```bash
python3 scripts/verifier_export.py export_TGLFW.zip                 # empreintes et chaînes
python3 scripts/verifier_export.py export_TGLFW.zip --key "$CLE"     # + sceau du manifeste et horodatages
```

Le script n'utilise que la bibliothèque standard de Python ; il signale tout fichier modifié, toute entrée altérée, retirée ou insérée. Le test `tests/test_export.py` en démontre le fonctionnement, y compris la détection d'une entrée réécrite.

## 9. Évolution du format

Les versions `1.x` n'ajoutent que des champs : un lecteur écrit pour `1.0` lit les suivantes en ignorant ce qu'il ne connaît pas. Un changement incompatible passerait à `2.0`, documenté ici avec un convertisseur.
