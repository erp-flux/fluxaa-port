# 2. Énumérations, statuts et cycles de vie
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Valeurs stockées en base (code) et libellés affichés (FR / EN). Les graphes de transitions sont ceux que les services refusent de contourner (`_set_status`, `REQUEST_TRANSITIONS`).

## 2.1 Application `core`

### `Role (apps/core/roles.py)`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `AGE` | AGE | Agence maritime / Shipping agency |
| `NAV` | NAV | Navire / capitaine / Vessel / master |
| `TER` | TER | Terminal / dépôt / Terminal / depot |
| `CAP` | CAP | Capitainerie / Harbour master |
| `APO` | APO | Autorité portuaire / Port authority |
| `SVC` | SVC | Services nautiques / Marine services |
| `ADM` | ADM | Douanes, immigration, santé / Customs, immigration, health |
| `SUR` | SUR | Sûreté et base navale / Security & naval base |
| `INS` | INS | Inspecteur et laboratoire / Surveyor & laboratory |
| `COM` | COM | Armateur / affréteur / Owner / charterer |
| `PRE` | PRE | Prestataire / Service provider |
| `DIR` | DIR | Direction du port / Port management |

### `Language`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `fr` | FR | Français |
| `en` | EN | English |

### `Berth.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `JETTY` | JETTY | Quai / appontement / Quay / jetty |
| `ANCHORAGE` | ANCHORAGE | Rade (mouillage) / Anchorage (roads) |
| `SPM` | SPM | Bouée au large (SPM / CBM) / Offshore buoy (SPM / CBM) |
| `STS_AREA` | STS_AREA | Zone STS au large / Offshore STS area |

## 2.2 Application `registry`

### `Confidentiality`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `N1` | N1 | N1 — Escale (toutes les parties) / N1 — Call (all parties) |
| `N2` | N2 | N2 — Restreint / N2 — Restricted |
| `N3` | N3 | N3 — Bilatéral / N3 — Bilateral |
| `N4` | N4 | N4 — Sûreté / N4 — Security |

### `Nature`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `F` | F | Fournir un document / Provide a document |
| `R` | R | Saisir des données / Enter data |
| `D` | D | Décider / Decide |
| `C` | C | Confirmer l'exécution / Confirm execution |
| `S` | S | Signer / contresigner / Sign / countersign |

### `Criticality`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `B` | BLOCKING | Bloquante / Blocking |
| `N` | NORMAL | Normale / Normal |

### `Anchor`
Deadline anchors. Every deadline is relative: no absolute date can be stored (EF-5.3)

| Code | Nom | Libellé FR / EN |
|---|---|---|
| `` | NONE | Sur événement (sans échéance) / Event-driven (no deadline) |
| `NOM` | NOM | Nomination |
| `ETA` | ETA | ETA |
| `ETB` | ETB | ETB |
| `ATB` | ATB | ATB |
| `T0` | T0 | T0 |
| `T1` | T1 | T1 |
| `ATD` | ATD | ATD |
| `NOR` | NOR | NOR |

### `TemplateKind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `BASE` | BASE | Socle commun (M0) / Common base (M0) |
| `OPERATION` | OPERATION | Modèle d'opération (M1–M8) / Operation model (M1–M8) |
| `MODULE` | MODULE | Module complémentaire (M9, MA1–MA3) / Additional module (M9, MA1–MA3) |

### `CallStatus`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `DRAFT` | DRAFT | Brouillon / Draft |
| `DECLARED` | DECLARED | Déclarée / Declared |
| `ACCEPTED` | ACCEPTED | Acceptée / Accepted |
| `PLANNED` | PLANNED | Planifiée / Planned |
| `APPROACHING` | APPROACHING | En approche / en rade / Approaching / at anchorage |
| `AT_BERTH` | AT_BERTH | À quai / Alongside |
| `IN_OPERATION` | IN_OPERATION | En opération / In operation |
| `OPS_COMPLETE` | OPS_COMPLETE | Opérations terminées / Operations completed |
| `SHIFTING` | SHIFTING | Déhalage dans le port / Shifting within the port |
| `DEPARTED` | DEPARTED | Navire parti / Departed |
| `CLOSED` | CLOSED | Clôturée / Closed |
| `ARCHIVED` | ARCHIVED | Archivée / Archived |
| `REJECTED` | REJECTED | Refusée / Rejected |
| `CANCELLED` | CANCELLED | Annulée / Cancelled |

### `Transition`
Transitions that the platform refuses while blocking tasks are not done (EF-11)

| Code | Nom | Libellé FR / EN |
|---|---|---|
| `DECLARE` | DECLARE | Déclarer l'escale / Declare the call |
| `GREEN_LIGHT` | GREEN_LIGHT | Donner le feu vert / Grant the green light |
| `BERTH_ASSIGN` | BERTH_ASSIGN | Attribuer un poste / Assign a berth |
| `MOVEMENT_AUTH` | MOVEMENT_AUTH | Délivrer l'autorisation de mouvement / Issue the movement authorization |
| `PILOT_BOARDING` | PILOT_BOARDING | Enregistrer le pilote à bord (arrivée) / Record pilot on board (arrival) |
| `BERTHING` | BERTHING | Enregistrer l'accostage (amarres à terre, amarrage terminé, navires à couple) / Record the berthing (lines ashore, all fast, vessels alongside) |
| `START_TRANSFER` | START_TRANSFER | Démarrer le transfert / Start the transfer |
| `DOUBLE_BANKING` | DOUBLE_BANKING | Autoriser l'accostage à couple / Authorize double banking |
| `HOT_WORK` | HOT_WORK | Autoriser les travaux par point chaud / Authorize hot work |
| `BL_ISSUE` | BL_ISSUE | Émettre le connaissement / Issue the bill of lading |
| `DEPARTURE_CLEARANCE` | DEPARTURE_CLEARANCE | Délivrer l'autorisation de départ / Issue the departure clearance |
| `PILOT_BOARDING_DEP` | PILOT_BOARDING_DEP | Enregistrer le pilote à bord (départ) / Record pilot on board (departure) |
| `DEPARTURE` | DEPARTURE | Enregistrer l'appareillage (dernière amarre, navire appareillé) / Record the departure (last line, vessel departed) |
| `CLOSE` | CLOSE | Clôturer l'escale / Close the call |

### `TaskStatus`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `PENDING` | PENDING | À faire / To do |
| `DONE` | DONE | Faite / Done |
| `NA` | NOT_APPLICABLE | Sans objet / Not applicable |

### `AlertLevel`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `NONE` | NONE | Dans les délais / On time |
| `REMINDER` | REMINDER | Rappel / Reminder |
| `LATE` | LATE | En retard / Late |
| `ESCALATED` | ESCALATED | Escaladée / Escalated |

### `CountersignState`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `PENDING` | PENDING | En attente de contresignature / Awaiting countersignature |
| `COUNTERSIGNED` | COUNTERSIGNED | Contresigné / Countersigned |
| `CONTESTED` | CONTESTED | Contesté / Contested |
| `TACIT` | TACIT | Contresignature tacite / Tacit countersignature |

### `EntrySource`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `ONLINE` | ONLINE | Saisie en ligne / Online entry |
| `OFFLINE` | OFFLINE | Saisie hors ligne (synchronisée) / Offline entry (synchronised) |
| `PAPER` | PAPER | Procédure papier (ressaisie) / Paper fallback (re-entered) |
| `AIS` | AIS | AIS |
| `SYSTEM` | SYSTEM | Système / System |

### `RequestStatus`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `CREATED` | CREATED | Créée / Created |
| `SUBMITTED` | SUBMITTED | Soumise / Submitted |
| `UNDER_REVIEW` | UNDER_REVIEW | En instruction / Under review |
| `APPROVED` | APPROVED | Approuvée / Approved |
| `APPROVED_COND` | APPROVED_WITH_CONDITIONS | Approuvée sous conditions / Approved with conditions |
| `REFUSED` | REFUSED | Refusée / Refused |
| `INFO_REQUIRED` | INFO_REQUIRED | Complément d'information demandé / Further information required |
| `SCHEDULED` | SCHEDULED | Programmée / Scheduled |
| `EXECUTED` | EXECUTED | Exécutée / Executed |
| `CLOSED` | CLOSED | Clôturée / Closed |
| `CANCELLED` | CANCELLED | Annulée / Cancelled |
| `EXPIRED` | EXPIRED | Expirée / Expired |

### `DocumentStatus`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `DRAFT` | DRAFT | Brouillon / Draft |
| `ISSUED` | ISSUED | Émis / Issued |
| `SIGNED` | SIGNED | Signé / Signed |
| `CANCELLED` | CANCELLED | Annulée / Cancelled |
| `REPLACED` | REPLACED | Remplacé / Replaced |

### `DisputeStatus`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `OPEN` | OPEN | Ouverte / Open |
| `ANSWERED` | ANSWERED | Répondue / Answered |
| `CLOSED_AGREED` | CLOSED_AGREED | Close — accord / Closed — agreement |
| `CLOSED_NOT_AGREED` | CLOSED_NOT_AGREED | Close — sans accord / Closed — no agreement |

### `MeasurementParty`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `SHIP` | SHIP | Bord / Ship |
| `SHORE` | SHORE | Terre / Shore |
| `SURVEYOR` | SURVEYOR | Inspecteur / Surveyor |

### `AlertKind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `REMINDER` | REMINDER | Rappel / Reminder |
| `LATE` | LATE | Tâche en retard / Late task |
| `ESCALATION` | ESCALATION | Escalade / Escalation |
| `HOLD_POINT` | HOLD_POINT | Refus de point d'arrêt / Hold point refusal |
| `QUANTITY` | QUANTITY | Écart bord/terre / Ship/shore discrepancy |
| `AIS` | AIS | Écart AIS / AIS divergence |
| `TACIT` | COUNTERSIGN_TACIT | Contresignature tacite / Tacit countersignature |
| `CONFLICT` | CONFLICT | Conflit de synchronisation / Synchronisation conflict |
| `EXPIRY` | EXPIRY | Autorisation expirée / Authorization expired |
| `ASSISTANT` | ASSISTANT | Signalée depuis la revue assistée / Raised from the assistant review |

### `TemplateVersion.Status`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `DRAFT` | DRAFT | Brouillon / Draft |
| `PUBLISHED` | PUBLISHED | Publiée / Published |
| `RETIRED` | RETIRED | Retirée / Retired |

### `CallStage.Status`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `PLANNED` | PLANNED | Planifiée / Planned |
| `CURRENT` | CURRENT | En cours / Current |
| `DONE` | DONE | Faite / Done |
| `CANCELLED` | CANCELLED | Annulée / Cancelled |

### `MasterAccessLink.Channel`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `EMAIL` | EMAIL | E-mail |
| `QR` | QR | QR code remis / QR code handed over |
| `PRINT` | PRINT | Imprimé / Printed |
| `SMS` | SMS | SMS |
| `OTHER` | OTHER | Autre / Other |

### `TaskSignature.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `SIGNED` | SIGNED | Signé / Signed |
| `COUNTERSIGNED` | COUNTERSIGNED | Contresigné / Countersigned |
| `CONTESTED` | CONTESTED | Contesté / Contested |
| `TACIT` | TACIT | Contresignature tacite / Tacit countersignature |

### `AuthorizationEvent.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `CANCELLED` | CANCELLED | Annulée / Cancelled |
| `VERIFIED` | VERIFIED | Vérifiée (code public) / Verified (public code) |

### `Measurement.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `INITIAL` | INITIAL | Jaugeage initial / Initial gauging |
| `FINAL` | FINAL | Jaugeage final / Final gauging |
| `OBQ` | OBQ | Quantité à bord avant opération (OBQ) / On-board quantity (OBQ) |
| `ROB` | ROB | Reste à bord (ROB) / Remaining on board (ROB) |
| `BL` | BL | Chiffre du connaissement / Bill of lading figure |
| `OTHER` | OTHER | Autre / Other |

### `DisputeEntry.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `STATEMENT` | STATEMENT | Exposé / Statement |
| `RESPONSE` | RESPONSE | Réponse / Response |
| `CLOSURE` | CLOSURE | Clôture / Closure |

## 2.4 Application `ai`

### `AssistantRun.Feature`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `EXTRACT` | EXTRACT | Extraction depuis un document / Extraction from a document |
| `REVIEW` | REVIEW | Revue de cohérence de l'escale / Consistency review of the call |
| `SUMMARY` | SUMMARY | Résumé d'un échange / Summary of an exchange |
| `REMARKS` | REMARKS | Projet de remarques pour le rapport des faits / Draft remarks for the statement of facts |
| `BRIEF` | BRIEF | Point du port / Brief of the port |
| `QUESTION` | QUESTION | Question sur le registre du port / Question on the registry of the port |

### `AssistantRun.Status`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `OK` | OK | Terminée / Completed |
| `ERROR` | ERROR | Échouée / Failed |

### `ExtractionReview.Status`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `PROPOSED` | PROPOSED | En attente de validation / Awaiting validation |
| `APPLIED` | APPLIED | Validée / Validated |
| `DISMISSED` | DISMISSED | Écartée / Dismissed |

## 2.5 Application `secure`

### `SecureItem.Kind`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `ARMED_GUARDS` | ARMED_GUARDS | Gardes armés / Armed guards |
| `ESCORT` | ESCORT | Escorte navale / Naval escort |
| `SECURITY_PLAN` | SECURITY_PLAN | Plan / déclaration de sûreté / Security plan / declaration |
| `INCIDENT` | INCIDENT | Incident de sûreté / Security incident |
| `OTHER` | OTHER | Autre question de sûreté / Other security matter |

### `SecureItem.Status`
| Code | Nom | Libellé FR / EN |
|---|---|---|
| `SUBMITTED` | SUBMITTED | Soumise / Submitted |
| `UNDER_REVIEW` | UNDER_REVIEW | En instruction / Under review |
| `APPROVED` | APPROVED | Approuvée / Approved |
| `APPROVED_COND` | APPROVED_COND | Approuvée sous conditions / Approved with conditions |
| `REFUSED` | REFUSED | Refusée / Refused |
| `EXECUTED` | EXECUTED | Exécutée / Executed |
| `CLOSED` | CLOSED | Clôturée / Closed |

## 2.9 Cycle de vie d'une escale (`CALL_TRANSITIONS`)

| Depuis | Vers (autorisé) |
|---|---|
| `DRAFT` | `CANCELLED`, `DECLARED` |
| `DECLARED` | `ACCEPTED`, `CANCELLED`, `REJECTED` |
| `ACCEPTED` | `CANCELLED`, `PLANNED` |
| `PLANNED` | `APPROACHING`, `CANCELLED` |
| `APPROACHING` | `AT_BERTH`, `DEPARTED`, `IN_OPERATION` |
| `AT_BERTH` | `DEPARTED`, `IN_OPERATION`, `SHIFTING` |
| `IN_OPERATION` | `OPS_COMPLETE`, `SHIFTING` |
| `OPS_COMPLETE` | `DEPARTED`, `SHIFTING` |
| `SHIFTING` | `AT_BERTH`, `DEPARTED`, `IN_OPERATION` |
| `DEPARTED` | `CLOSED` |
| `CLOSED` | `ARCHIVED` |
| `ARCHIVED` | — (terminal) |
| `REJECTED` | — (terminal) |
| `CANCELLED` | — (terminal) |

Chaîne opérationnelle le long de laquelle un jalon fait avancer l'escale (`OPERATIONAL_CHAIN`) : `PLANNED` → `APPROACHING` → `AT_BERTH` → `IN_OPERATION` → `OPS_COMPLETE` → `DEPARTED`.

Statuts « actifs » (`ACTIVE_STATUSES`, escales en cours) : `DECLARED`, `ACCEPTED`, `PLANNED`, `APPROACHING`, `AT_BERTH`, `IN_OPERATION`, `OPS_COMPLETE`, `SHIFTING`.

## 2.10 Cycle de vie d'une demande (`REQUEST_TRANSITIONS`)

| Depuis | Vers (autorisé) |
|---|---|
| `CREATED` | `CANCELLED`, `SUBMITTED` |
| `SUBMITTED` | `APPROVED`, `APPROVED_COND`, `CANCELLED`, `EXECUTED`, `INFO_REQUIRED`, `REFUSED`, `SCHEDULED`, `UNDER_REVIEW` |
| `UNDER_REVIEW` | `APPROVED`, `APPROVED_COND`, `CANCELLED`, `INFO_REQUIRED`, `REFUSED` |
| `INFO_REQUIRED` | `CANCELLED`, `SUBMITTED` |
| `APPROVED` | `CLOSED`, `EXECUTED`, `EXPIRED`, `SCHEDULED` |
| `APPROVED_COND` | `CLOSED`, `EXECUTED`, `EXPIRED`, `SCHEDULED` |
| `SCHEDULED` | `CANCELLED`, `EXECUTED`, `EXPIRED` |
| `EXECUTED` | `CLOSED` |
| `REFUSED` | `CLOSED` |
| `CLOSED` | — (terminal) |
| `CANCELLED` | — (terminal) |
| `EXPIRED` | `CLOSED` |
