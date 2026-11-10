# 10. Temps, échéances, alertes et notifications

> Chapitre **rédigé** (FLX-SPEC-003, onglet principal, section 9), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.

## 10.1 Temps, échéances, alertes et notifications

**Ancres.** Toute échéance est relative à une ancre de l'escale (`Anchor`) : NOM (nomination = création), ETA, ETB, ATB, T0, T1, ATD, NOR ; le code de la tâche porte `anchor` + `offset_minutes` (par exemple `ETA-72h` = ETA − 4 320 min, `ATD+15j`). `PortCall.anchor_time(anchor)` rend l'heure réelle si elle existe, sinon l'estimée (ATA sinon ETA, ATB sinon ETB, T0 sinon ETS, T1 sinon ETC, ATD sinon ETD). Les tâches sans ancre (événement, continu, immédiat, selon charte-partie, quotidien, par phase, à la livraison) n'ont pas d'échéance. Les 48 libellés d'échéance livrés (`catalog.TIMING`) sont listés avec les tâches dans l'onglet *5. Catalogues*.

**Calcul et cascade (`compute_due`, `recompute_deadlines`).** `due_at = anchor_time + offset`. Quand une ancre change — révision des heures par l'agence (motif obligatoire), jalon qui pose une heure réelle, déhalage qui pose l'ETB de l'étape suivante — toutes les tâches `PENDING` de l'escale sont recalculées en une passe silencieuse : un niveau d'alerte qui **baisse** est retiré sans notification ; un niveau qui monte est notifié par le planificateur, groupé (jamais de rafale).

**Niveaux d'alerte d'une tâche (`alert_level_for`).**

| Niveau | Condition | Destinataires |
| --- | --- | --- |
| NONE | échéance lointaine, tâche faite, sans objet, continue ou sans échéance | — |
| REMINDER | `now ≥ due_at − Port.reminder_lead_hours` (24 h) | le rôle de la tâche (AGE pour `ANY`) |
| LATE | `now ≥ due_at`, tâche normale, retard < `Port.escalation_after_minutes` (240 min) | le rôle + AGE |
| ESCALATED | tâche **bloquante** en retard (immédiat), ou tâche normale en retard au-delà du seuil | le rôle + AGE + CAP ; SMS aux personnes avec téléphone et au téléphone officiel de l'organisation responsable |

Chaque montée de niveau crée une `Alert` (pièce du dossier, reprise au rapport des faits) et une entrée de journal `alert.emitted`, puis **une seule notification par destinataire et par passe** (`dedupe_key = alerts:<escale>:<horodatage>`), bloquante si l'une des alertes l'est.

**Autres alertes (`AlertKind`)** : `HOLD_POINT` (refus d'un point d'arrêt, bloquante), `QUANTITY` (écart bord/terre au-delà de `Port.quantity_tolerance_pct`, 0,300 %, avec proposition de contestation), `AIS` (écart entre une observation AIS et le registre au-delà de `Port.ais_divergence_minutes`, 30 min ; jamais une correction), `TACIT` (contresignature tacite posée), `CONFLICT` (saisies concurrentes à la synchronisation : les deux conservées, contestation ouverte), `EXPIRY` (autorisation expirée sans exécution), `ASSISTANT` (constat de la revue IA promu en alerte par une personne, sous son nom).

**Contresignature tacite (`apply_tacit_countersignatures`).** Pour chaque jalon d'une escale active enregistré depuis plus de `Port.countersign_delay_minutes` (120 min) et dont un contresignataire n'a ni contresigné ni contesté, le planificateur crée une signature `TACIT` scellée au nom de la plateforme, journalisée et notifiée à l'émetteur et au rôle silencieux. Elle n'est jamais assimilée à un accord : le rapport des faits, l'export et l'API la montrent comme telle.

**Notifications (`services/notifications.notify`).** Une notification est créée par destinataire (utilisateur actif tenant l'un des rôles visés sur l'escale, dans une organisation qui tient ce rôle), avec un titre FR et EN, une adresse de page et une clé de dédoublonnage (`dedupe_key`, unique par utilisateur : un événement ne notifie jamais deux fois). Canaux :

| Canal | Quand | Réglage |
| --- | --- | --- |
| Dans l'application (`/notifications/`, compteur dans l'en-tête) | toujours | — |
| Courriel immédiat | notification bloquante ou temps réel (points d'arrêt, escalades, décisions, convocations), ou utilisateur qui n'a pas choisi le résumé quotidien | `User.notify_digest_only` |
| Résumé quotidien par courriel | le reste, une fois par jour à `Port.digest_hour_local` (7 h, heure du port) | `send_daily_digests` |
| SMS | escalades seulement, aux personnes ayant un téléphone et au téléphone officiel de l'organisation | `FLUXAA_SMS_BACKEND` = `log` ou `webhook` (`FLUXAA_SMS_WEBHOOK_URL`, jeton) |
| Webhooks sortants | événements du registre vers un système tiers abonné (`WebhookSubscription`), livraison signée HMAC avec reprises (`WebhookDelivery`) | onglet *6. API* |
| Courriel de convocation | à la déclaration, lien d'accès à l'adresse de l'organisation sans compte ; sans adresse, entrée `party_link.unsent` | `Organization.email` |

**Planificateur (`run_scheduler`, boucle de 60 s, service `scheduler`).** Chaque passe exécute dans l'ordre, chacune dans sa transaction et sans bloquer les autres : contresignatures tacites, évaluation des alertes de toutes les escales actives, expiration des autorisations (statut `EXPIRED` + alerte), résumés quotidiens, livraison des webhooks (reprises, 100 par passe), purge des positions AIS plus anciennes que `Port.ais_retention_days`. Le résultat de chaque passe est journalisé dans les logs du service.

**Heure et fuseau.** Stockage UTC ; affichage dans `Port.timezone` avec le fuseau rappelé en tête de page ; saisie en heure du port ; horodatage double des jalons ; une saisie dont l'heure déclarée précède l'enregistrement de plus de `FLUXAA_LATE_ENTRY_SECONDS` (30 min) est marquée différée ; une saisie hors ligne porte en plus l'heure de l'appareil ; un écart appareil/serveur au-delà de `FLUXAA_DEFERRED_THRESHOLD_SECONDS` (120 s) est signalé. Les dates de l'API sont ISO 8601 avec décalage.
