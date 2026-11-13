# 7. API publique v1 — points d'accès et représentations
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Le schéma OpenAPI 3 complet est servi par `/api/schema/` (documentation navigable : `/api/docs/`). Authentification, erreurs, synchronisation hors ligne et webhooks : `docs/API.md`. Ci-dessous l'inventaire des opérations et des exemples de représentations JSON produits sur les données de démonstration.

## 7.1 Opérations

| Méthode | Chemin | Opération | Résumé |
|---|---|---|---|
| `POST` | `/api/v1/ais/` | `v1_ais_create` | AIS observation: {imo\|mmsi, event: ARRIVAL\|DEPARTED, time} |
| `GET` | `/api/v1/ais/positions/` | `v1_ais_positions_retrieve` | Latest position of every vessel heard in the port waters (24 h) |
| `POST` | `/api/v1/ais/positions/` | `v1_ais_positions_create` | AIS position reports: {reports: [{mmsi, lat, lon, observed_at?, speed_kn?, course_deg?, heading_deg?, nav_status?, imo?, name?, call_sign?, destination?, draught_m?}]} |
| `GET` | `/api/v1/board/` | `v1_board_retrieve` | Port call board: every declared call of the port (vessel, agency, area, state, times) — no operational data of other agencies' calls |
| `GET` | `/api/v1/board/occupation/` | `v1_board_occupation_retrieve` | Berth occupation plan of a period (?start=YYYY-MM-DD&end=YYYY-MM-DD): the calls per berth, as the terminals' sheets |
| `GET` | `/api/v1/calls/` | `calls_list` | Calls on which your organisation holds a role |
| `POST` | `/api/v1/calls/` | `v1_calls_create` | Create a call (shipping agency only) |
| `GET` | `/api/v1/calls/{reference}/` | `calls_retrieve` | Call detail as visible by you |
| `POST` | `/api/v1/calls/{reference}/actions/{action}/` | `v1_calls_actions_create` | Life-cycle action: declare \| estimates \| cancel \| close-request \| close \| archive \| statement-of-facts \| invite \| remind \| renew \| party-access \| green-light-withdraw \| documents-request |
| `GET` | `/api/v1/calls/{reference}/disputes/` | `v1_calls_disputes_retrieve` | Disputes |
| `POST` | `/api/v1/calls/{reference}/disputes/` | `disputes_create` | Open a dispute |
| `POST` | `/api/v1/calls/{reference}/disputes/{dispute_id}/{action}/` | `disputes_action` | respond \| close (agreed true/false) — no 'reject' exists |
| `GET` | `/api/v1/calls/{reference}/documents/` | `v1_calls_documents_retrieve` | Documents visible to you |
| `POST` | `/api/v1/calls/{reference}/documents/` | `v1_calls_documents_create` | Upload a document (multipart: file, type) |
| `GET` | `/api/v1/calls/{reference}/documents/{document_id}/download/` | `v1_calls_documents_download_retrieve` | Download a document (access is audited) |
| `POST` | `/api/v1/calls/{reference}/documents/{document_id}/sign/` | `v1_calls_documents_sign_create` | Sign a document (optional hand-drawn signature PNG) |
| `GET` | `/api/v1/calls/{reference}/export/` | `v1_calls_export_retrieve` | Export (zip, documented open format) — COM and DIR |
| `GET` | `/api/v1/calls/{reference}/field-bundle/` | `v1_calls_field_bundle_retrieve` | Everything the field app needs to work offline for this call |
| `GET` | `/api/v1/calls/{reference}/forms/` | `forms_list` | Standard forms you may generate on this call (one structure: header, body, signatures, seal) |
| `GET` | `/api/v1/calls/{reference}/forms/{code}/` | `forms_render` | The form rendered as a printable HTML page, pre-filled from the registry |
| `POST` | `/api/v1/calls/{reference}/forms/{code}/` | `forms_file` | Generate the form and file it in the call's documents (fingerprinted, under your role) |
| `GET` | `/api/v1/calls/{reference}/green-lights/` | `v1_calls_green_lights_retrieve` | The green-light panel of the call: each party's go-ahead, its state, who gave it, when |
| `GET` | `/api/v1/calls/{reference}/journal/` | `v1_calls_journal_retrieve` | Call journal (hash-chained), filtered by your roles |
| `GET` | `/api/v1/calls/{reference}/measurements/` | `v1_calls_measurements_retrieve` | Measurements (ship / shore / surveyor) with the tank readings you may read |
| `POST` | `/api/v1/calls/{reference}/measurements/` | `v1_calls_measurements_create` | Open a measurement |
| `GET` | `/api/v1/calls/{reference}/measurements/{measurement_id}/tanks/` | `v1_calls_measurements_tanks_retrieve` | Tank readings of a measurement: validated ones, and your own side's pending ones |
| `POST` | `/api/v1/calls/{reference}/measurements/{measurement_id}/tanks/` | `v1_calls_measurements_tanks_create` | Read a tank: the ship its cargo tanks, the terminal its shore tanks (awaits the surveyor's validation) |
| `POST` | `/api/v1/calls/{reference}/measurements/{measurement_id}/tanks/{reading_id}/review/` | `v1_calls_measurements_tanks_review_create` | Surveyor: validate (decision=validate) or reject (decision=reject, note) a tank reading |
| `POST` | `/api/v1/calls/{reference}/measurements/{measurement_id}/values/` | `v1_calls_measurements_values_create` | Add your party's value (single emitter) |
| `GET` | `/api/v1/calls/{reference}/milestones/` | `v1_calls_milestones_retrieve` | Milestones (contradictory timeline) |
| `POST` | `/api/v1/calls/{reference}/milestones/` | `v1_calls_milestones_create` | Record a milestone (single emitter; hold points apply) |
| `POST` | `/api/v1/calls/{reference}/milestones/{milestone_id}/countersign/` | `v1_calls_milestones_countersign_create` | Countersign or contest a milestone |
| `GET` | `/api/v1/calls/{reference}/pumping-log/` | `v1_calls_pumping_log_retrieve` | Pumping log: the readings of both sides, and their comparison reading by reading |
| `POST` | `/api/v1/calls/{reference}/pumping-log/` | `v1_calls_pumping_log_create` | Add a pumping-log reading of your side (manual or automatic feed) |
| `GET` | `/api/v1/calls/{reference}/pumping-sheets/` | `v1_calls_pumping_sheets_retrieve` | Pumping log sheets (ship and shore headers) |
| `POST` | `/api/v1/calls/{reference}/pumping-sheets/` | `v1_calls_pumping_sheets_create` | Open your side's pumping log sheet (tank, calibration, density, VCF, planned quantity…) |
| `POST` | `/api/v1/calls/{reference}/pumping-sheets/{sheet_id}/close/` | `v1_calls_pumping_sheets_close_create` | Complete your side's sheet: actual stop level, final volume |
| `GET` | `/api/v1/calls/{reference}/requests/` | `v1_calls_requests_retrieve` | Requests and authorizations visible to you |
| `POST` | `/api/v1/calls/{reference}/requests/` | `requests_create` | Create (and submit) a request |
| `POST` | `/api/v1/calls/{reference}/requests/{request_id}/{action}/` | `requests_action` | submit \| review \| decide (2FA: X-MFA-Code) \| schedule \| execute \| cancel |
| `GET` | `/api/v1/calls/{reference}/safety-checklist/` | `v1_calls_safety_checklist_retrieve` | The ship/shore safety checklist of the call, with every item and the answers of both sides |
| `POST` | `/api/v1/calls/{reference}/safety-checklist/` | `v1_calls_safety_checklist_open` | Open the checklist (ship or terminal); optional repeat_interval_h |
| `POST` | `/api/v1/calls/{reference}/safety-checklist/{action}/` | `v1_calls_safety_checklist_action` | answer (items: [{item_code, state, value, remark, repetition}]) \| sign (comment) \| cancel (reason) |
| `POST` | `/api/v1/calls/{reference}/secure-deposit/` | `v1_calls_secure_deposit_create` | Write-only N4 deposit (armed guards, escort…) — returns a receipt |
| `GET` | `/api/v1/calls/{reference}/stages/` | `stages_list` | Stages of the call (areas in sequence) |
| `POST` | `/api/v1/calls/{reference}/stages/` | `stages_create` | Plan the next stage (agency or harbour master): berth_kind, operations[], berth?, planned_from?, planned_to?, reason? |
| `POST` | `/api/v1/calls/{reference}/stages/{stage_id}/cancel/` | `stages_cancel` | Cancel a planned stage (reason) |
| `POST` | `/api/v1/calls/{reference}/sync/` | `v1_calls_sync_create` | Offline synchronisation batch (field app) |
| `GET` | `/api/v1/calls/{reference}/tasks/` | `v1_calls_tasks_retrieve` | Tasks visible to your roles (EF-5.7) |
| `POST` | `/api/v1/calls/{reference}/tasks/{task_id}/{action}/` | `v1_calls_tasks_create` | complete \| sign \| countersign \| not-applicable |
| `GET` | `/api/v1/calls/{reference}/threads/` | `v1_calls_threads_retrieve` | Correspondence threads of the call |
| `POST` | `/api/v1/calls/{reference}/threads/` | `v1_calls_threads_create` | Open a thread (always attached to the call) |
| `POST` | `/api/v1/calls/{reference}/threads/{thread_id}/messages/` | `v1_calls_threads_messages_create` | Post a message in a thread |
| `GET` | `/api/v1/dashboard/` | `v1_dashboard_retrieve` | Real-time board and indicators (no N4 object, in any form) |
| `GET` | `/api/v1/me/` | `v1_me_retrieve` | Current identity, organisation and roles |
| `GET` | `/api/v1/secure/items/` | `secure_items_list` | N4 items (security authority and harbour master only) |
| `GET` | `/api/v1/secure/items/{reference}/` | `secure_items_retrieve` | Read an N4 item (access logged nominatively) |
| `POST` | `/api/v1/secure/items/{reference}/` | `v1_secure_items_create` | Decide on an N4 item (SUR, 2FA) |
| `GET` | `/api/v1/verify/{code}/` | `v1_verify_retrieve` | Public verification of an authorization by its code |
| `POST` | `/api/v1/vessels/` | `v1_vessels_create` | Register a vessel (agency) |

## 7.2 Représentations JSON (exemples sur les données de démonstration)


### Escale — résumé (`call_summary`)

```json
{
  "reference": "TGLFW-2026-0001",
  "status": "IN_OPERATION",
  "status_label": "En opération",
  "vessel": {
    "name": "MT ATLANTIC DEMO",
    "imo": "9999993"
  },
  "operating_area": "JETTY",
  "berth": "LFW-APP",
  "eta": "2026-11-12T15:20:03.382244+00:00",
  "etb": "2026-11-12T23:20:03.382244+00:00",
  "etd": "2026-11-14T17:20:03.382244+00:00",
  "ata": "2026-11-12T16:20:03.382244+00:00",
  "atb": "2026-11-12T23:30:03.382244+00:00",
  "atd": null,
  "templates": [
    "M0",
    "M1"
  ],
  "cargo_kind": "LIQUID",
  "sts_role": null,
  "validity": {
    "days": 15,
    "valid_until": "2026-11-28T11:20:03.391178+00:00",
    "expired_at": null,
    "overrun": false,
    "renewed_from": null
  }
}
```

### Escale — détail (`call_detail`, vue agence)

```json
{
  "reference": "TGLFW-2026-0001",
  "status": "IN_OPERATION",
  "status_label": "En opération",
  "vessel": {
    "name": "MT ATLANTIC DEMO",
    "imo": "9999993"
  },
  "operating_area": "JETTY",
  "berth": "LFW-APP",
  "eta": "2026-11-12T15:20:03.382244+00:00",
  "etb": "2026-11-12T23:20:03.382244+00:00",
  "etd": "2026-11-14T17:20:03.382244+00:00",
  "ata": "2026-11-12T16:20:03.382244+00:00",
  "atb": "2026-11-12T23:30:03.382244+00:00",
  "atd": null,
  "templates": [
    "M0",
    "M1"
  ],
  "cargo_kind": "LIQUID",
  "sts_role": null,
  "validity": {
    "days": 15,
    "valid_until": "2026-11-28T11:20:03.391178+00:00",
    "expired_at": null,
    "overrun": false,
    "renewed_from": null
  },
  "port": {
    "code": "TGLFW",
    "name": "Lomé",
    "timezone": "Africa/Lome"
  },
  "agency": "Agence maritime (démo)",
  "voyage": "DEMO-01",
  "your_roles": [
    "AGE"
  ],
  "estimates": {
    "eta": "2026-11-12T15:20:03.382244+00:00",
    "etb": "2026-11-12T23:20:03.382244+00:00",
    "ets": null,
    "etc": null,
    "etd": "2026-11-14T17:20:03.382244+00:00"
  },
  "actuals": {
    "ata": "2026-11-12T16:20:03.382244+00:00",
    "nor_at": "2026-11-12T16:40:03.382244+00:00",
    "atb": "2026-11-12T23:30:03.382244+00:00",
    "t0": "2026-11-13T02:20:03.382244+00:00",
    "t1": null,
    "atd": null
  },
  "parties": [
    {
      "id": 1,
      "organization": "Agence maritime (démo)",
      "role": "AGE",
      "principal": true,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 2,
      "organization": "Autorité portuaire (démo)",
      "role": "DIR",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 3,
      "organization": "Autorité portuaire (démo)",
      "role": "APO",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 4,
      "organization": "Autorité portuaire (démo)",
      "role": "CAP",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 5,
      "organization": "Douanes, immigration et santé (démo)",
      "role": "ADM",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 6,
      "organization": "Sûreté portuaire et marine nationale (démo)",
      "role": "SUR",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 7,
      "organization": "Services nautiques (démo)",
      "role": "SVC",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 8,
      "organization": "Terminal pétrolier (démo)",
      "role": "TER",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 9,
      "organization": "Surveyor et laboratoire (démo)",
      "role": "INS",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 10,
      "organization": "Armateur / affréteur (démo)",
      "role": "COM",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 11,
      "organization": "Prestataire déchets (démo)",
      "role": "PRE",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 12,
      "organization": "Réceptionnaire / importateur (démo)",
      "role": "COM",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 13,
      "organization": "Correspondant P&I (démo)",
      "role": "INS",
      "principal": false,
      "access": "FULL",
      "scopes": []
    },
    {
      "id": 14,
      "organization": "Fournisseur d'eau douce (démo)",
      "role": "PRE",
      "principal": false,
      "access": "FULL",
      "scopes": []
    }
  ],
  "your_access": {
    "level": "FULL",
    "tabs": null,
    "principal_agent": true
  },
  "billing_basis": {
    "validity_days": 15,
    "valid_from": "2026-11-13T11:20:03.395734+00:00",
    "valid_until": "2026-11-28T11:20:03.391178+00:00",
    "arrived_at": "2026-11-12T16:20:03.382244+00:00",
    "departed_at": null,
    "closed_at": null,
    "expired_at": null,
    "hours_in_port": 19.3,
    "overrun_hours": null
  },
  "linked_call": null,
  "named_by": [
    {
      "reference": "TGLFW-2026-0017",
      "vessel": "MT LAGUNE DEMO",
      "agency": "Consignataire associé (démo)",
      "kind": "OUTER",
      "sts_role": null,
      "status": "DECLARED"
    }
  ],
  "stages": [
    {
      "order": 1,
      "berth_kind": "JETTY",
      "berth": "LFW-APP",
      "operations": [
        "M1"
      ],
      "status": "CURRENT",
      "atb": "2026-11-12T23:30:03.382244+00:00",
      "atd": null
    }
  ],
  "product": "Gasoil 10 ppm",
  "quantity": "32000.000",
  "quantity_unit": "MT",
  "operation_details": {
    "M1": {
      "inert_gas": "YES",
      "max_rate_m3h": 1200,
      "stripping_rob": "≤ 25 m³",
      "vapour_return": "NO",
      "manifold_connections": "2 × 12\" ANSI 150",
      "max_manifold_pressure_bar": 7
    }
  },
  "declared": [
    {
      "template": "M1",
      "name": "Déchargement (import)",
      "items": [
        {
          "label": "Débit maximal de déchargement (m³/h)",
          "value": "1 200"
        },
        {
          "label": "Pression maximale au collecteur (bar)",
          "value": "7"
        },
        {
          "label": "Collecteur : nombre et diamètre des raccords",
          "value": "2 × 12\" ANSI 150"
        },
        {
          "label": "Citernes inertées à l'arrivée",
          "value": "Oui"
        },
        {
          "label": "Retour de vapeurs demandé",
          "value": "Non"
        },
        {
          "label": "ROB attendu après assèchement",
          "value": "≤ 25 m³"
        }
      ]
    }
  ],
  "hold_points": {
    "GREEN_LIGHT": {
      "ready": true,
      "missing": []
    },
    "BERTH_ASSIGN": {
      "ready": true,
      "missing": []
    },
    "MOVEMENT_AUTH": {
      "ready": true,
      "missing": []
    },
    "START_TRANSFER": {
      "ready": true,
      "missing": []
    },
    "DEPARTURE_CLEARANCE": {
      "ready": false,
      "missing": [
        "M0:32",
        "M0:33"
      ]
    },
    "CLOSE": {
      "ready": false,
      "missing": [
        "M0:36"
      ]
    }
  }
}
```

### Tâche (`task_dict`)

```json
{
  "id": 1,
  "code": "M0:01",
  "title": "Créer l'escale et inviter les parties prenantes",
  "title_fr": "Créer l'escale et inviter les parties prenantes",
  "title_en": "Create the call and invite the stakeholders",
  "section": "Nomination et déclaration",
  "role": "AGE",
  "co_roles": [],
  "joint": false,
  "nature": "R",
  "blocking": true,
  "due_at": "2026-11-13T11:20:03.395734+00:00",
  "timing": "à la nomination",
  "status": "DONE",
  "alert_level": "NONE",
  "request_type": "",
  "milestones": [],
  "document_type": "",
  "continuous": false,
  "ad_hoc": false,
  "green_light": false,
  "requested_at_creation": false,
  "completed_at": "2026-11-13T11:20:03.465374+00:00",
  "completed_role": "AGE",
  "na_reason": "",
  "signed_roles": []
}
```

### Jalon (`milestone_dict`)

```json
{
  "id": 1,
  "type": "GREEN_LIGHT",
  "label": "Feu vert / escale acceptée",
  "declared_at": "2026-11-13T11:20:03.853006+00:00",
  "recorded_at": "2026-11-13T11:20:03.894999+00:00",
  "device_recorded_at": null,
  "deferred": false,
  "source": "SYSTEM",
  "emitter_role": "CAP",
  "emitter": "Officier de port TGLFW — Autorité portuaire (démo)",
  "cause": null,
  "cause_reason": "",
  "related_id": null,
  "rectification": false,
  "conflict": false,
  "countersigner_roles": [],
  "countersignatures": {},
  "countersignature_state": "",
  "client_uuid": null
}
```

### Demande (`request_dict`)

```json
{
  "id": 1,
  "reference": "TGLFW-2026-0001-R01",
  "type": "GREEN_LIGHT",
  "label": "Feu vert",
  "status": "APPROVED",
  "status_label": "Approuvée",
  "confidentiality": "N1",
  "requester_role": "AGE",
  "data": {},
  "submitted_at": "2026-11-13T11:20:03.581598+00:00",
  "due_at": "2026-11-13T23:20:03.581598+00:00",
  "decision": "APPROVED",
  "decision_role": "CAP",
  "decided_at": "2026-11-13T11:20:03.853006+00:00",
  "conditions": "",
  "decision_roles": [
    "CAP"
  ],
  "executor_role": "",
  "provider": null,
  "authorization": {
    "number": "AUT-TGLFW-2026-000002",
    "valid_from": "2026-11-13T11:20:03.853006+00:00",
    "valid_until": "2026-11-20T11:20:03.853006+00:00",
    "verification_code": "MGEQG8ABUR",
    "berth": null,
    "cancelled": false
  }
}
```

### Document (`document_dict`)

```json
{
  "id": 1,
  "type": "Q88",
  "type_label": "Q88 / VPQ, plans, particularités du collecteur",
  "title": "Q88 / VPQ, plans, particularités du collecteur",
  "version": 1,
  "status": "ISSUED",
  "confidentiality": "N2",
  "issuer_role": "AGE",
  "issuer": "Agent maritime TGLFW — Agence maritime (démo)",
  "issued_at": "2026-11-13T11:20:03.480620+00:00",
  "sha256": "1694e51d6b03cfba0e2b736cf7759364a7d7679d11417afc8a5cc713abaef106",
  "size": 975,
  "mime_type": "application/pdf",
  "required_signers": [],
  "signatures": [],
  "deferred": false,
  "download": "/api/v1/calls/TGLFW-2026-0001/documents/1/download/"
}
```

### Mesure (`measurement_dict`)

```json
{
  "id": 1,
  "kind": "BL",
  "unit": "MT",
  "product": "Gasoil 10 ppm",
  "tolerance_pct": "0.300",
  "values": {
    "SHIP": {
      "value": "32000.000",
      "by": "Capt. Demo — Capitaine (MT ATLANTIC DEMO)",
      "at": "2026-11-13T11:20:06.249111+00:00",
      "deferred": false
    },
    "SHORE": {
      "value": "32000.000",
      "by": "Opérateur terminal TGLFW — Terminal pétrolier (démo)",
      "at": "2026-11-13T11:20:06.271071+00:00",
      "deferred": false
    },
    "SURVEYOR": {
      "value": "32000.000",
      "by": "Expert surveyor TGLFW — Surveyor et laboratoire (démo)",
      "at": "2026-11-13T11:20:06.294236+00:00",
      "deferred": false
    }
  },
  "complete": true,
  "discrepancy": {
    "difference": "0.000",
    "percent": "0.000"
  },
  "differences": [
    {
      "a": "SHIP",
      "b": "SHORE",
      "difference": "0.000",
      "percent": "0.000",
      "exceeds": false
    },
    {
      "a": "SHIP",
      "b": "SURVEYOR",
      "difference": "0.000",
      "percent": "0.000",
      "exceeds": false
    },
    {
      "a": "SHORE",
      "b": "SURVEYOR",
      "difference": "0.000",
      "percent": "0.000",
      "exceeds": false
    }
  ],
  "exceeds_tolerance": false
}
```

### Contestation (`dispute_dict`)

```json
{
  "id": 1,
  "reference": "DSP-TGLFW-2026-00001",
  "subject": "Interruption — début — 13/11/2026 06:20 UTC",
  "target": "MILESTONE",
  "target_id": 19,
  "status": "ANSWERED",
  "opened_role": "NAV",
  "opened_by": "Capt. Demo — Capitaine (MT ATLANTIC DEMO)",
  "counterpart_role": "TER",
  "opened_at": "2026-11-13T11:20:06.199956+00:00",
  "closed_at": null,
  "automatic": false
}
```
