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

**Autres alertes (`AlertKind`)** : `HOLD_POINT` (refus d'un point d'arrêt, bloquante), `QUANTITY` (écart bord/terre d'une mesure au-delà de `Port.quantity_tolerance_pct`, 0,300 %, avec proposition de contestation ; depuis la 1.4 aussi l'écart terre − bord, horaire ou cumulé, d'une ligne du journal de pompage : « arrêter pour investigation »), `AIS` (écart entre une observation AIS et le registre au-delà de `Port.ais_divergence_minutes`, 30 min ; jamais une correction), `TACIT` (contresignature tacite posée), `CONFLICT` (saisies concurrentes à la synchronisation : les deux conservées, contestation ouverte), `EXPIRY` (autorisation expirée sans exécution), `ASSISTANT` (constat de la revue IA promu en alerte par une personne, sous son nom).

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

**Notifications du contrôle des pertes et de l'interface navire/terre (1.4, EXG-Q-07).** Toute action de ces écrans est notifiée à l'équipe, avec les règles anti-bruit : une notification par événement et par destinataire, et des clés groupées là où les saisies sont répétitives.

| Événement | Destinataires | Clé (`dedupe_key`) | Temps réel |
| --- | --- | --- | --- |
| Feuille de journal de pompage ouverte | lecteurs `PUMPING_LOG` | `pumping-sheet:<feuille>` | non |
| Relevés de pompage en cours | lecteurs `PUMPING_LOG`, **une fois par côté et par fenêtre de six heures** | `pumping:<escale>:<côté>:<jour><fenêtre>` | non |
| Écart terre − bord hors tolérance | lecteurs `PUMPING_LOG` | `pumping-dev:<escale>:<relevé>` | **oui** |
| Valeur d'une mesure saisie | lecteurs `MEASUREMENTS` | `quantity:<mesure>:<valeur>` | non (oui si hors tolérance) |
| Relevés de citernes à valider | INS, une fois par mesure, côté et heure | `tank:<mesure>:<côté>:<heure>` | oui |
| Relevés validés | lecteurs `MEASUREMENTS`, une fois par mesure, côté et heure | `tank:<mesure>:<côté>:validated:<heure>` | non |
| Relevé rejeté | le côté (organisation) et l'agence | `tank:<relevé>:rejected` | oui |
| Document déposé (tout type) | les lecteurs du document, signataires exclus (déjà notifiés *à signer*) | `document:<id>:issued` | non |
| Liste de contrôle ouverte / point répondu « non » / signée par un bord / signée par les deux | l'autre bord et AGE / l'autre bord, AGE, CAP / l'autre bord et AGE / NAV, TER, AGE, CAP, INS | `checklist:<id>:opened`, `…:<point>:<côté>:no:<minute>`, `…:signed:<côté>`, `…:signed` | oui |
| Escale créée en brouillon | les autres comptes AGE de l'agence | `draft:<escale>` | non |
| Relance d'une tâche | les comptes des rôles de la tâche (hors rôle du relanceur) ; courriel au capitaine | `remind:<tâche>:<minute>` | oui |

**Notifications de la généralisation (1.5, EXG-R).** Mêmes règles anti-bruit ; les destinataires d'une escale sont ses parties tenant les rôles visés.

| Événement | Destinataires | Clé (`dedupe_key`) | Temps réel |
| --- | --- | --- | --- |
| Validité de l'annonce : 72 h puis 24 h avant l'échéance (`scheduler.watch_validity`) | AGE, CAP | `validity:<escale>:72h`, `…:24h` | le rappel de 24 h |
| Annonce obsolète (`calls.expire_call`) | AGE, CAP, APO | `expired:<escale>` | oui |
| Validité dépassée par une escale à quai (une fois par jour) | AGE, CAP, APO | `validity:<escale>:overrun:<jour>` | non |
| Feu vert donné (`tasks.complete_task`) | AGE, CAP, NAV, TER (hors l'auteur) | `green:<tâche>:given:<minute>` | oui |
| Feu vert retiré, avec le motif (`tasks.withdraw_green_light`) | AGE, CAP, NAV, TER, APO (hors l'auteur) | `green:<tâche>:withdrawn:<minute>` | oui |
| Accès d'une partie fixé (`calls.set_party_access`) | la partie (son organisation) | `party:<partie>:access:<minute>` | non |
| Escale du navire partenaire créée pour un STS (`calls._create_sts_partner`) | l'agence du partenaire | `sts:<escale>:nominated` | oui |
| Documents demandés à l'annonce ou depuis (`tasks.request_documents`) | les rôles émetteurs des documents demandés | `documents:<escale>:requested:<minute>` | non |

**Notifications de l'annonce adaptée (1.6, EXG-R-11).** Un accostage à couple engage un navire qui n'a rien demandé : il est averti dès l'annonce, par son dossier.

| Événement | Destinataires | Clé (`dedupe_key`) | Temps réel |
| --- | --- | --- | --- |
| Accostage à couple annoncé contre une escale du port (`calls._notify_partner_link`) — sur **l'escale de l'autre navire** : l'agence, le capitaine et la capitainerie ; lien réciproque (même agence) ou à confirmer par l'autorisation de la capitainerie (autre agence) | AGE, CAP, NAV de l'escale partenaire (hors l'auteur) | `double_banking:<escale>:<partenaire>` | oui |
| Escale créée pour l'autre navire d'un accostage à couple, sous son agence (`calls._create_db_partner`) | l'agence nommée | `double_banking:<partenaire>:nominated` | oui |
| Escale de l'autre navire (STS ou accostage à couple) créée sous une agence **pour laquelle personne ne peut encore se connecter** — nommée à l'annonce, ou enregistrée sans utilisateur actif (`calls._tell_port_of_agency_without_account`, `notifications.notify_port_admins`) : *« … n'a pas encore de compte : … l'a désignée comme agence de … — ouvrez ses comptes, elle seule déclare l'escale de son navire »*, lien vers la fiche de l'organisation ; notification **du port**, sans escale (`Notification.call` vide : un brouillon n'est connu que de son agence) | les administrateurs fonctionnels du port (`User.is_port_admin`) | `agency_without_account:<organisation>:<escale>` | oui |
| Transbordement annoncé avec une escale d'une autre agence (`calls._notify_partner_link`) — sur **l'escale désignée** (le navire-mère) : le lien attend l'autorisation de zone et de fenêtre STS | AGE, CAP, NAV de l'escale désignée (hors l'auteur) | `sts_link:<escale>:<désignée>` | oui |


**Planificateur (`run_scheduler`, boucle de 60 s, service `scheduler`).** Chaque passe exécute dans l'ordre, chacune dans sa transaction et sans bloquer les autres : contresignatures tacites, évaluation des alertes de toutes les escales actives, expiration des autorisations (statut `EXPIRED` + alerte), **surveillance de la validité des annonces** (`watch_validity`, 1.5 : rappels à 72 h et 24 h, passage à *Obsolète* d'une escale pas encore à quai, signalement quotidien du dépassement d'une escale à quai), résumés quotidiens, livraison des webhooks (reprises, 100 par passe), purge des positions AIS plus anciennes que `Port.ais_retention_days`. Le résultat de chaque passe est journalisé dans les logs du service.

**Heure et fuseau.** Stockage UTC ; affichage dans `Port.timezone` avec le fuseau rappelé en tête de page ; saisie en heure du port ; horodatage double des jalons ; une saisie dont l'heure déclarée précède l'enregistrement de plus de `FLUXAA_LATE_ENTRY_SECONDS` (30 min) est marquée différée ; une saisie hors ligne porte en plus l'heure de l'appareil ; un écart appareil/serveur au-delà de `FLUXAA_DEFERRED_THRESHOLD_SECONDS` (120 s) est signalé. Les dates de l'API sont ISO 8601 avec décalage.
