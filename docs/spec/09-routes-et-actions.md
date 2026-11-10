# 9. Routes, vues et actions (inventaire)
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Toutes les URL servies par la plateforme, la vue qui les traite et le chapitre d'écran qui les décrit (chapitre 8). Les actions sont les sous-chemins `POST /escales/<id>/action/<action>/` de l'écran d'escale, avec les paramètres lus et le service appelé.

## 9.1 Routes web et API

| Chemin | Nom | Vue | Décrit au |
|---|---|---|---|
| `/healthz` | `healthz` | `core.views.healthz` | oui |
| `/admin/login/` | — | `core.views.admin_login` | oui |
| `/api/v1/me/` | `me` | `api.views.MeView` | ch. 7 (API) |
| `/api/v1/vessels/` | `vessels` | `api.views.VesselView` | ch. 7 (API) |
| `/api/v1/calls/` | `calls` | `api.views.CallListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/` | `call` | `api.views.CallDetailView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/actions/<str:action>/` | `call-action` | `api.views.CallActionView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/tasks/` | `tasks` | `api.views.TaskListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/tasks/<int:task_id>/<str:action>/` | `task-action` | `api.views.TaskActionView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/milestones/` | `milestones` | `api.views.MilestoneListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/milestones/<int:milestone_id>/countersign/` | `countersign` | `api.views.MilestoneCountersignView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/requests/` | `requests` | `api.views.RequestListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/requests/<int:request_id>/<str:action>/` | `request-action` | `api.views.RequestActionView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/stages/` | `stages` | `api.views.StageListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/stages/<int:stage_id>/cancel/` | `stage-cancel` | `api.views.StageCancelView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/forms/` | `forms` | `api.views.FormListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/forms/<str:code>/` | `form` | `api.views.FormView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/documents/` | `documents` | `api.views.DocumentListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/documents/<int:document_id>/download/` | `document-download` | `api.views.DocumentDownloadView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/documents/<int:document_id>/sign/` | `document-sign` | `api.views.DocumentSignView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/measurements/` | `measurements` | `api.views.MeasurementListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/measurements/<int:measurement_id>/values/` | `measurement-values` | `api.views.MeasurementValueView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/pumping-log/` | `pumping-log` | `api.views.PumpingLogView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/disputes/` | `disputes` | `api.views.DisputeListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/disputes/<int:dispute_id>/<str:action>/` | `dispute-action` | `api.views.DisputeActionView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/threads/` | `threads` | `api.views.ThreadListView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/threads/<int:thread_id>/messages/` | `thread-messages` | `api.views.ThreadMessageView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/journal/` | `journal` | `api.views.JournalView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/export/` | `export` | `api.views.ExportView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/sync/` | `sync` | `api.views.SyncView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/field-bundle/` | `field-bundle` | `api.views.FieldBundleView` | ch. 7 (API) |
| `/api/v1/calls/<str:reference>/secure-deposit/` | `secure-deposit` | `api.views.SecureDepositView` | ch. 7 (API) |
| `/api/v1/dashboard/` | `dashboard` | `api.views.DashboardView` | ch. 7 (API) |
| `/api/v1/ais/` | `ais` | `api.views.AisView` | ch. 7 (API) |
| `/api/v1/ais/positions/` | `ais_positions` | `api.views.AisPositionsView` | ch. 7 (API) |
| `/api/v1/verify/<str:code>/` | `verify` | `api.views.VerifyView` | ch. 7 (API) |
| `/api/v1/secure/items/` | `secure-items` | `api.views.SecureItemListView` | ch. 7 (API) |
| `/api/v1/secure/items/<str:reference>/` | `secure-item` | `api.views.SecureItemView` | ch. 7 (API) |
| `/api/schema/` | `schema` | `drf_spectacular.views.SpectacularAPIView` | ch. 7 (API) |
| `/api/docs/` | `api-docs` | `drf_spectacular.views.SpectacularRedocView` | ch. 7 (API) |
| `/surete/` | `index` | `secure.views.index` | oui |
| `/surete/journal/` | `log` | `secure.views.access_log` | oui |
| `/surete/piece/<int:attachment_id>/` | `attachment` | `secure.views.attachment` | oui |
| `/surete/<str:reference>/` | `item` | `secure.views.item` | oui (vue) |
| `/compte/connexion/` | `login` | `core.views.LoginView` | oui |
| `/compte/deconnexion/` | `logout` | `core.views.logout_view` | oui |
| `/compte/langue/` | `language` | `core.views.language` | oui |
| `/compte/mfa/activer/` | `mfa_setup` | `core.views.mfa_setup` | oui |
| `/compte/mfa/verifier/` | `mfa_verify` | `core.views.mfa_verify` | oui |
| `/compte/` | `profile` | `core.views.profile` | oui |
| `/assistant/` | `port` | `ai.views.port` | oui |
| `/escales/<int:pk>/assistant/extraction/<int:doc_id>/` | `extract` | `ai.views.extract` | oui (vue) |
| `/escales/<int:pk>/assistant/verification/<int:review_id>/` | `extraction` | `ai.views.extraction` | oui |
| `/escales/<int:pk>/assistant/revue/` | `review` | `ai.views.review` | oui (vue) |
| `/escales/<int:pk>/assistant/revue/<int:run_id>/alerte/<int:index>/` | `raise_alert` | `ai.views.raise_alert` | oui (vue) |
| `/escales/<int:pk>/assistant/echange/<int:thread_id>/` | `summarize` | `ai.views.summarize` | oui (vue) |
| `/escales/<int:pk>/assistant/remarques/` | `remarks` | `ai.views.remarks` | oui (vue) |
| `/carte/` | `board` | `ais.views.board` | oui |
| `/carte/fond/` | `background` | `ais.views.background` | oui |
| `/` | `dashboard` | `registry.views.dashboard` | oui |
| `/escales/` | `call_list` | `registry.views.call_list` | oui |
| `/escales/nouvelle/` | `call_create` | `registry.views.call_create` | oui |
| `/escales/<int:pk>/` | `call_detail` | `registry.views.call_detail` | oui |
| `/escales/<int:pk>/action/<str:action>/` | `call_action` | `registry.views.call_action` | oui |
| `/escales/<int:pk>/documents/<int:doc_id>/` | `document_download` | `registry.views.document_download` | oui |
| `/escales/<int:pk>/export/` | `export_call` | `registry.views.export_call` | oui |
| `/escales/<int:pk>/rapport-des-faits/` | `statement_preview` | `registry.views.statement_preview` | oui |
| `/escales/<int:pk>/formulaires/` | `form_list` | `registry.views.form_list` | oui |
| `/escales/<int:pk>/formulaires/<str:code>/` | `form_preview` | `registry.views.form_preview` | oui |
| `/escales/<int:pk>/terrain/` | `field_app` | `registry.views.field_app` | oui |
| `/notifications/` | `notifications` | `registry.views.notifications` | oui |
| `/pilotage/` | `calibration` | `registry.views.calibration` | oui |
| `/statistiques/` | `statistics` | `registry.views.statistics` | oui |
| `/bord/` | `master_entry` | `registry.views.master_entry` | oui |
| `/bord/sortie/` | `master_logout` | `registry.views.master_logout` | oui |
| `/bord/nom/` | `link_name` | `registry.views.link_name` | oui |
| `/bord/<str:token>/` | `master_token` | `registry.views.master_token` | oui |
| `/verifier/` | `verify` | `registry.views.verify` | oui |
| `/verifier/<str:code>/` | `verify_code` | `registry.views.verify` | oui |
| `/manifest.webmanifest` | `manifest` | `registry.views.manifest` | oui |
| `/sw.js` | `service_worker` | `registry.views.service_worker` | oui |

L'administration (`/admin/…`) est l'interface de paramétrage Django : ses écrans sont décrits au chapitre 8 (§8.9) par modèle administré.

## 9.2 Actions de l'écran d'escale (`POST /escales/<id>/action/<action>/`)

Chaque action lit `request.POST` (`back` facultatif : page de retour), passe par `web_action` (refus métier → message, point d'arrêt → encadré de refus, authentification forte manquante → page du second facteur) et par `account_or_master` (compte ou lien d'accès).

| Action | Paramètres lus | Service appelé |
|---|---|---|
| `declare` | — | `call_svc.declare_call` |
| `estimates` | `reason` | `call_svc.update_estimates` |
| `cancel` | `reason` | `call_svc.cancel_call` |
| `stage_add` | `berth`, `berth_kind`, `operations[]`, `reason`, `planned_from`, `planned_to` | `stage_svc.add_stage` |
| `stage_cancel` | `reason`, `stage_id` | `stage_svc.cancel_stage` |
| `close_request` | — | `call_svc.confirm_closure` |
| `close` | — | `call_svc.close_call` |
| `archive` | — | `call_svc.archive_call` |
| `link` | `link_kind`, `partner` | `call_svc.link_partner` |
| `party_add` | `role`, `organization`, `party_name`, `party_kind`, `party_email`, `party_phone` | `call_svc.add_party`, `call_svc.register_organization` |
| `party_shore` | `party_id` | `call_svc.designate_shore_side` |
| `party_revoke` | `reason`, `party_id` | `call_svc.revoke_party` |
| `master_link` | `master_name`, `channel`, `note`, `vessel_position` | `call_svc.issue_master_link`, `mfa.svg_data_uri`, `mfa.qr_svg` |
| `party_link` | `holder_name`, `channel`, `note`, `party_id` | `call_svc.issue_party_link`, `mfa.svg_data_uri`, `mfa.qr_svg` |
| `master_revoke`, `link_revoke` | `reason`, `link_id` | `call_svc.revoke_master_link` |
| `task_complete` | `note` | `task_svc.complete_task` |
| `task_sign` | `note` | `task_svc.sign_task` |
| `task_na` | `reason` | `task_svc.mark_not_applicable` |
| `task_countersign` | `comment`, `contest` | `task_svc.countersign_task` |
| `task_adhoc` | `title_fr`, `title_en`, `role`, `anchor`, `offset_hours` | `task_svc.create_ad_hoc_task` |
| `milestone` | `related_id`, `type`, `cause`, `cause_reason`, `note`, `declared_at`, `paper` | `ms_svc.record_milestone` |
| `countersign` | `comment`, `contest` | `ms_svc.countersign_milestone` |
| `request_create` | `provider`, `type` | `req_svc.create_request` |
| `request_provider` | `provider` | `req_svc.assign_provider` |
| `request_review`, `request_decide`, `request_schedule`, `request_execute`, `request_cancel`, `request_submit` | `berth`, `decision`, `reason`, `conditions`, `valid_from`, `valid_until`, `scheduled_for`, `note` | `req_svc.take_under_review`, `req_svc.decide_request`, `req_svc.schedule_request`, `req_svc.execute_request`, `req_svc.cancel_request`, `req_svc.submit_request` |
| `document_upload` | `file (multipart)`, `task_id`, `previous_id`, `type`, `title`, `confidentiality`, `counterpart_role` | `doc_svc.upload_document` |
| `document_sign` | `signature_image` | `doc_svc.sign_document` |
| `document_cancel` | `reason` | `doc_svc.cancel_document` |
| `statement` | `remarks`, `remarks_assisted` | `reports.issue_statement_of_facts` |
| `form_issue` | `code` | `form_svc.issue` |
| `measurement_open` | `kind`, `unit` | `meas_svc.create_measurement` |
| `measurement_value` | `party`, `value`, `temperature_c`, `density`, `note` | `meas_svc.add_value` |
| `pumping` | `pressure_bar`, `rate_m3h`, `temperature_c`, `note`, `declared_at` | `meas_svc.add_pumping_entry` |
| `dispute_open` | `target_kind`, `subject`, `statement`, `counterpart_role`, `target_id` | `disputes.open_dispute` |
| `dispute_respond` | `text`, `dispute_id` | `disputes.respond` |
| `dispute_close` | `text`, `agreed`, `dispute_id` | `disputes.close` |
| `thread_create` | `subject`, `participants[]`, `body`, `confidentiality` | `correspondence.create_thread` |
| `thread_post` | `body`, `thread_id` | `correspondence.post_message` |
| `secure_deposit` | `kind`, `guards`, `company`, `embark`, `disembark`, `escort`, `details` | `n4.deposit` |

L'action `estimates` lit aussi les heures estimées `eta`, `etb`, `ets`, `etc`, `etd` (`calls.ESTIMATE_FIELDS`) ; `request_create` lit chaque clé du `form_schema` du type de demande (cases à cocher → booléen, dates → ISO 8601).
