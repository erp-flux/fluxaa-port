# 5. Règles métier

> Chapitre **rédigé** (FLX-SPEC-003, onglet principal, sections 4, 6, 7 et 8), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.

Les règles que le code applique, avec la fonction et le test qui les portent : règles d'or et invariants, cycles de vie, droits et confidentialité, points d'arrêt et verrous. Les énumérations et la matrice des droits sont générées dans les chapitres 02 et 03.

## 5.1 Règles d'or et invariants

Six règles d'or (FLX-CDC-001 §0.3) gouvernent toute fonctionnalité ; elles ne sont jamais contournables par un écran, un paramétrage ni un administrateur, et toute évolution qui les toucherait est soumise à FLUXAA avant développement. Chacune est tenue à un endroit précis du code, que la colonne *Mise en œuvre* nomme pour qu'une réécriture la place au même niveau : dans les services, jamais dans les vues.

| N° | Règle | Ce que cela impose | Mise en œuvre livrée |
| --- | --- | --- | --- |
| 1 | **Émetteur unique** : un fait n'est saisi que par le rôle qui en répond ; les autres contresignent ou contestent | chaque type de jalon porte son émetteur, ses contresignataires et ses contestataires ; chaque valeur de mesure porte sa partie (bord = NAV, terre = TER, inspecteur = INS) ; chaque tâche porte son rôle ; une fin d'interruption revient à la partie qui en a saisi le début ; côté terre unique et désigné quand plusieurs terminaux ou prestataires participent | `MilestoneType.emitter_role`, `services/milestones.record_milestone`, `services/measurements.add_value`, `CallParty.shore_side`, `rights.shore_org_id` |
| 2 | **Qui demande ne décide jamais** | contrôle par rôle et par personne à la décision ; un type de demande dont un rôle serait à la fois demandeur et décideur est refusé au paramétrage ; toute décision exige un second facteur récent | `services/requests.decide_request`, `RequestType.clean()`, `StrongAuthRequired` |
| 3 | **Aucune suppression, administrateur compris** | modèles en ajout seul ou sans suppression ; déclencheurs PostgreSQL `fluxaa_refuse()` sur les tables du registre, du domaine N4 et des traces IA ; rôle d'exécution sans privilège `DELETE` ; une erreur se corrige par un nouvel enregistrement lié (rectification, nouvelle valeur, nouvelle version) ; une escale close est figée | `apps/core/guards.py` (`AppendOnlyModel`, `NoDeleteModel`), migrations `*_database_guards`, `apply_db_grants`, déclencheur `fluxaa_document_frozen` |
| 4 | **Besoin d'en connaître** : quatre niveaux N1 (escale), N2 (restreint, défaut), N3 (bilatéral), N4 (sûreté, base distincte) | tout accès passe par les services de droits, jamais par une requête directe ; un objet invisible n'existe pas (404), son existence n'est jamais révélée ; le domaine N4 est une autre base, chiffrée, en écriture seule pour les déposants | `services/rights.py` (matrice §7), `apps/secure` |
| 5 | **Les droits viennent du rôle de l'organisation sur l'escale**, datés et révocables | `CallParty` (organisation × rôle × escale, `valid_from`, `revoked_at`) ∩ rôles que la personne peut exercer ; ce qui a un auteur est cloisonné par organisation ; un lien sans compte porte un rôle et une organisation | `services/context.actor_for_call`, `rights.acts_for` |
| 6 | **Toute attente est une tâche** assignée, datée, relancée | les gabarits instancient les tâches à la création et à chaque étape ; les échéances sont relatives à une ancre et recalculées en cascade ; rappel, retard, escalade par le planificateur ; aucune messagerie libre | `services/calls.instantiate_tasks`, `recompute_deadlines`, `services/alerts.py` |

**Invariants complémentaires** que le code tient et qu'une réécriture doit reproduire :

| Invariant | Mise en œuvre attendue |
| --- | --- |
| Journal opposable | chaque acte produit une entrée de journal dont l'empreinte SHA-256 couvre son contenu et l'empreinte précédente (chaîne par port, `ChainHead`) ; les consultations, téléchargements et exports alimentent une seconde chaîne (`AuditEntry`) ; une commande recalcule les deux chaînes, un script autonome vérifie un export sans la plateforme |
| Double horodatage | un jalon porte l'heure déclarée (`declared_at`) et l'heure d'enregistrement (`recorded_at`), plus l'heure de l'appareil hors ligne ; déclaré plus de `FLUXAA_LATE_ENTRY_SECONDS` (1 800 s) avant son enregistrement, il est marqué « saisie différée » ; le point d'arrêt est évalué à l'heure déclarée |
| Silence qualifié | passé `Port.countersign_delay_minutes` (120), un jalon non contresigné reçoit une contresignature **tacite**, mentionnée comme telle partout (rapport des faits, export) ; ce n'est pas un accord |
| Contestation jamais rejetée | une contestation se répond et se clot (avec ou sans accord) par les parties ; la capitainerie peut la clore sans accord, jamais la trancher ; non close, elle bloque la clôture et, pour une quantité, le connaissement |
| Autorisation à expiration | toute autorisation porte `valid_from`, `valid_until` (obligatoire, refus en `clean()` et `save()`) et un code de vérification public ; un point d'arrêt regarde l'autorisation **en vigueur à l'heure du fait**, pas le drapeau de la tâche |
| Rien n'est absolu dans les échéances | une tâche ne stocke jamais de date absolue d'échéance saisie : `anchor` + `offset_minutes`, `due_at` étant recalculé |
| Fichier déposé jamais page du site | type reconnu par le contenu (PDF, images) ; tout autre fichier servi en octets bruts sous politique `sandbox` ; `Content-Security-Policy` stricte sur chaque page |
| Un seul moteur de règles | web, API, appli terrain et synchronisation appellent les mêmes fonctions de service ; aucune règle n'est implémentée dans un gabarit HTML ou en JavaScript seulement |
| Zéro personne dans les chiffres | statistiques, indicateurs et pilotage sont calculés par rôle, jamais par personne ; l'assistant IA ne reçoit que des rôles |

## 5.2 Cycles de vie et états

Chaque objet du registre a un graphe d'états fermé ; une transition hors du graphe est refusée par le service, jamais par l'écran seul. Les tables ci-dessous sont normatives : les codes sont ceux de l'API et de l'export.

### 5.2.1 Escale (`PortCall.status`)

*Schéma : statuts d'une escale · 15 statuts (dont **Obsolète** depuis la 1.5), chemin nominal et sorties — dessiné dans FLX-SPEC-003 (onglet principal).*

| De | Vers | Déclenché par | Condition |
| --- | --- | --- | --- |
| DRAFT | DECLARED | AGE, *Déclarer l'escale* | point d'arrêt `DECLARE` (M0:02, 03, 05 faits) ; convoque les parties, crée la demande de feu vert |
| DRAFT, DECLARED, ACCEPTED, PLANNED | CANCELLED | AGE (agent principal), *Annuler* (motif) | avant tout accostage |
| DRAFT, DECLARED, ACCEPTED, PLANNED, APPROACHING | EXPIRED (obsolète) | la plateforme, `scheduler.watch_validity` (1.5) | la validité de l'annonce (`valid_until`) est échue sans que le navire soit à quai ; `expired_at` posé ; parties notifiées ; une escale à quai n'est jamais rendue obsolète — son **dépassement** est compté |
| EXPIRED, CANCELLED, REJECTED | → nouvelle escale DRAFT (`renewed_from`) | AGE (agent principal), *Refaire l'annonce* (`renew_call`, 1.5) | une seule reprise active par escale ; même navire, zone, opérations, modules, cargaison, parties et accès ; même validité en jours, comptée depuis la reprise |
| DECLARED | ACCEPTED / REJECTED | décision CAP sur `GREEN_LIGHT` | approbation → jalon `GREEN_LIGHT` ; refus → motif N3 |
| ACCEPTED | PLANNED | décision APO sur `BERTH` | point d'arrêt `BERTH_ASSIGN` ; poste affecté à l'étape |
| PLANNED | APPROACHING | jalon `ARRIVAL` (NAV) | pose ATA |
| APPROACHING | AT\_BERTH | jalon `ALL_FAST` (SVC) ou `STS_ALONGSIDE` (PRE) | point d'arrêt `BERTHING` ; pose ATB |
| AT\_BERTH | IN\_OPERATION | jalon `TRANSFER_START` (TER) ou `STS_TRANSFER_START` (PRE) | point d'arrêt `START_TRANSFER` ; pose T0 |
| IN\_OPERATION | OPS\_COMPLETE | jalon `TRANSFER_END` / `STS_TRANSFER_END` | pose T1 (la dernière fin l'emporte) |
| AT\_BERTH, IN\_OPERATION, OPS\_COMPLETE | SHIFTING | jalon `SHIFT_START` (SVC) | étape suivante planifiée, autorisation de mouvement en vigueur, tâches bloquantes de l'étape suivante faites |
| SHIFTING | AT\_BERTH, IN\_OPERATION | jalons d'accostage ou de transfert de l'étape suivante | idem |
| APPROACHING, AT\_BERTH, OPS\_COMPLETE, SHIFTING | DEPARTED | jalon `DEPARTED` (SVC) | point d'arrêt `DEPARTURE` ; pose ATD ; le lien capitaine expire après `master_link_grace_hours` |
| DEPARTED | CLOSED | CAP, *Clôturer* (après *Demander la clôture* par AGE) | point d'arrêt `CLOSE` ; contestations closes, mesures complètes, rapport des faits signé ; éteint les liens |
| CLOSED | ARCHIVED | CAP ou DIR, *Archiver* | escale figée (toute écriture refusée) |

`ACTIVE_STATUSES` (tableau de bord, liens de partie valides) = DECLARED … SHIFTING ; `is_terminal_state` = CLOSED, ARCHIVED, REJECTED, CANCELLED, EXPIRED ; `EXPIRABLE_STATUSES` = DRAFT, DECLARED, ACCEPTED, PLANNED, APPROACHING. Les ancres de l'escale gardent leur sens sur plusieurs étapes : ATA première arrivée, ATB premier accostage, T0 premier début de transfert, T1 dernière fin, ATD appareillage final ; chaque étape porte en plus ses propres `atb` et `atd`.

### 5.2.2 Étape d'escale (`CallStage.status`)

| État | Sens | Entrée | Sortie |
| --- | --- | --- | --- |
| CURRENT | l'étape où le navire est ou va | première étape à la création ; étape suivante au `SHIFT_START` | DONE au `SHIFT_START` suivant |
| PLANNED | étape à venir | *Planifier l'étape suivante* (AGE, CAP) : tâches des nouvelles opérations créées, lignes spécifiques à la zone des gabarits déjà présents ajoutées | CURRENT au déhalage ; CANCELLED avec motif |
| DONE | étape quittée (`atd` posé) | `SHIFT_START` | — |
| CANCELLED | étape abandonnée, jamais supprimée | *Annuler l'étape* (motif) ; ses tâches restent et peuvent être déclarées sans objet | — |

Une seule étape est CURRENT ; un poste attribué (`BERTH`) va à la première étape PLANNED de cette zone, sinon à l'étape courante et à l'escale ; un jalon porte l'étape courante ; un point d'arrêt ignore les tâches rattachées à une autre étape.

### 5.2.3 Demande et autorisation (`ServiceRequest.status`, `Authorization`)

| De | Vers | Par | Règle |
| --- | --- | --- | --- |
| CREATED | SUBMITTED | demandeur, *Soumettre* (ou création avec `submit`) | pièces attendues du type jointes ; le type nomme ses rôles demandeurs |
| SUBMITTED | UNDER\_REVIEW | décideur, *Prendre en instruction* | — |
| SUBMITTED, UNDER\_REVIEW | APPROVED / APPROVED\_COND / REFUSED / INFO\_REQUIRED | décideur (second facteur) | jamais le demandeur, ni par rôle ni par personne ; motif obligatoire pour refus, conditions, complément ; approbation → `Authorization` (validité obligatoire, code public), jalon d'approbation, tâches terminées, statut d'escale si le type le dit |
| INFO\_REQUIRED | SUBMITTED | demandeur | après complément |
| SUBMITTED (commande sans décideur), APPROVED, APPROVED\_COND | SCHEDULED | exécutant (SVC, PRE), *Programmer* | heure programmée |
| SCHEDULED, APPROVED, APPROVED\_COND, SUBMITTED (commande) | EXECUTED | exécutant, *Confirmer l'exécution* | termine la tâche d'exécution |
| EXECUTED, REFUSED, EXPIRED, APPROVED\* | CLOSED | système ou décideur | — |
| APPROVED\*, SCHEDULED | EXPIRED | planificateur (`expire_authorizations`) | `valid_until` dépassé sans exécution ; alerte `EXPIRY` |
| CREATED … SCHEDULED | CANCELLED | demandeur ou décideur (motif) | — |

Une autorisation est en ajout seul : elle ne se modifie pas, elle s'annule (`AuthorizationEvent` CANCELLED, motif) ou expire ; sa vérification publique (`/verifier/<code>/`) est journalisée (VERIFIED). `is_valid(at)` = `valid_from ≤ at < valid_until` et non annulée.

### 5.2.4 Tâche (`Task.status`, `alert_level`)

| État | Par | Règle |
| --- | --- | --- |
| PENDING → DONE | titulaire du rôle (ou co-rôle), *Réaliser* / *Fournir* ; ou le système quand le jalon, le document ou la décision attendu arrive | une tâche conjointe (`joint`) exige la signature de chaque rôle (`TaskSignature`) ; une tâche de décision (`request_side = decide`) n'est jamais faite à la main : seule la décision la termine |
| PENDING → NA (sans objet) | le rôle responsable, motif obligatoire | refusé pour une tâche `not_applicable_allowed = false`, pour une tâche de décision attendue par un point d'arrêt si l'acteur n'en répond pas |
| alert\_level NONE → REMINDER → LATE → ESCALATED | planificateur | voir section 9 ; redescend sans bruit quand l'échéance s'éloigne |

### 5.2.5 Jalon et contresignature (`Milestone`, `MilestoneSignature.state`)

Un jalon n'a pas de statut : il existe, horodaté deux fois, et porte des drapeaux : `deferred` (saisie différée), `is_conflict` (saisie concurrente détectée à la synchronisation : conservée, contestation ouverte), `is_rectification` + `rectifies` (nouveau jalon lié à celui qu'il corrige, motif obligatoire, même organisation émettrice), `source` (ONLINE, OFFLINE, PAPER, AIS, SYSTEM). Chaque contresignataire attendu a une ligne `MilestoneSignature` : PENDING → COUNTERSIGNED (contresigne) ou CONTESTED (conteste : ouvre une contestation) ; PENDING → TACIT par le planificateur passé le délai du port.

### 5.2.6 Document (`Document.status`)

| De | Vers | Par | Règle |
| --- | --- | --- | --- |
| — | ISSUED | émetteur (rôle émetteur du type), dépôt ou génération | empreinte SHA-256, type reconnu par le contenu, confidentialité du type, contrepartie obligatoire en N3 |
| ISSUED | SIGNED | chaque signataire requis (rôles du type) | la dernière signature fige le document ; une signature porte l'empreinte exacte de la version |
| ISSUED, SIGNED | REPLACED | émetteur, *Nouvelle version* | nouvelle ligne `version + 1` avec `previous` ; l'ancienne reste lisible |
| ISSUED | CANCELLED | émetteur (organisation émettrice seulement), motif | jamais un document signé |

Le connaissement (`is_bill_of_lading`) n'est émis que si le verrou `BL_ISSUE` est levé (section 8).

**Dépôt automatique des actes.** Certains documents ne dépendent pas d'un clic : la plateforme les génère et les dépose elle-même comme documents générés, sous le rôle de l'auteur de l'acte (`forms.auto_issue`) — l'**acte écrit de chaque décision** (`AUTH_<TYPE>`, approbation, approbation sous conditions ou refus ; confidentialité et lecteurs de la demande, `Document.audience_roles` ; code de vérification et QR pour une approbation ; jamais le motif d'un refus restreint), la **notice de disponibilité** à la remise du jalon `NOR_TENDERED`, le **time sheet** avec le rapport des faits. Une génération qui échoue est journalisée côté serveur et ne bloque jamais l'acte : la partie émet alors le formulaire à la main depuis la page Formulaires. Tout document ainsi déposé est visible dès l'acte dans l'onglet Documents de ses lecteurs (onglet *4. Formulaires standards*, § 4.2).

### 5.2.7 Contestation (`Dispute.status`)

OPEN (ouverte par une partie sur un jalon, une tâche, une mesure, un document, une demande ou autre, avec contrepartie) → ANSWERED (la contrepartie répond ; une réponse ne règle rien) → CLOSED\_AGREED (l'organisation qui l'a ouverte la clot par accord) ou CLOSED\_NOT\_AGREED (l'une des parties ou la capitainerie la clot sans accord). Il n'existe pas de « rejet ». OPEN et ANSWERED bloquent la clôture de l'escale ; une contestation de mesure OPEN ou ANSWERED maintient le verrou du connaissement.

### 5.2.8 Lien d'accès sans compte (`MasterAccessLink`)

Émis (jeton et code hachés, affichés une seule fois ; `auto_issued` quand la plateforme convoque à la déclaration) → nommé (`master_name` à l'émission ou à la première ouverture ; tant qu'il est vide, le lien n'ouvre que la page *Votre nom*) → éteint par révocation (`revoked_at`, motif ; aussi quand le rôle de la partie est révoqué), par expiration (`expires_at` ; capitaine : départ + délai de grâce, au plus `master_link_max_days` ; partie : clôture de l'escale, au plus `party_link_max_days`) ou par la fin de l'escale. Un lien ne porte jamais un rôle décideur.

## 5.3 Droits, confidentialité, cloisonnement

Les droits sont calculés côté serveur pour un **acteur** = une personne (ou un lien sans compte) × les rôles que son organisation tient sur l'escale × les rôles qu'elle peut exercer, avec deux drapeaux : `strong_auth` (second facteur récent) et `is_link` / `is_master` (accès sans compte). Trois couches s'appliquent dans l'ordre : la matrice objet × rôle (ce que le rôle peut faire), la confidentialité de l'objet (qui le voit), le cloisonnement par organisation (qui agit sur un objet qui a un auteur).

### 5.3.1 Matrice objet × rôle (FLX-SPEC-001 §5, `rights.MATRIX`)

Verbes : **C** créer · **V** voir · **S** saisir ou modifier · **A** approuver ou décider · **Cs** contresigner · **Ct** contester · **K** clore · **E** exporter.

| Objet | AGE | NAV | TER | CAP | APO | SVC | ADM | SUR | INS | COM | PRE | DIR |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Escale | C S K V | V | V | A K V | S V | V | V | V | V | V E | V | V E |
| Navire | C S V | V Ct | V | A V | V | V | V | V | V | V | — | V |
| Partie | C V | V | V | A V | V | V | V | V | V | V | V | V |
| Demande | C S V | V Ct | C S V | A V | A V | V | A V | A V | — | V | C S V | V |
| Autorisation | V | V | V | C A V | C A V | V | C A V | C A V | — | V | V | V E |
| Jalon | S Cs V | Cs Ct V | S Cs V | V Ct | V | S V | S V | S V | S Cs V | V Ct | S | V E |
| Mesure | V | S Cs V | S Cs V | V | — | — | — | — | S Cs V | V Ct | — | V E |
| Contestation | C V | C V | C V | V A | V | V | V | V | C V | C V | V | V E |
| Document | C S V | C Cs V | C S V | V A | V | V | C A V | C V | C S V | V | C | V E |
| Échange | C V | C V | C V | C V | C V | C V | C V | C V | C V | C V | C V | V |
| Poste | V | — | V | A V | C S A V | S V | — | — | — | — | — | V |
| Tableau de bord | V | — | V | V | V | V | V | V | V | V | V | V E |
| Journal des accès | — | — | — | V | — | — | — | V | — | — | — | V E |

La matrice est nécessaire, pas suffisante : le type de jalon, de document ou de demande restreint encore qui émet, et les règles ci-dessous s'ajoutent.

### 5.3.2 Confidentialité (`Confidentiality`)

| Niveau | Sens | Qui voit |
| --- | --- | --- |
| N1 | de l'escale | toutes les parties de l'escale ayant le verbe V sur l'objet |
| N2 (défaut) | restreint | l'émetteur, les destinataires du type (`audience_roles`, signataires requis), les superviseurs `N2_SUPERVISORS` = {AGE, CAP, DIR}, et COM pour les documents |
| N3 | bilatéral | l'émetteur et la contrepartie nommée (`counterpart_role`), plus la capitainerie pour les exposés d'une contestation ; motif de refus d'un vetting : AGE, COM et le service qui a décidé |
| N4 | sûreté | personne dans le registre : base distincte, dépôt en écriture seule par AGE et NAV, lecture par SUR et CAP, chaque accès journalisé et signalé à l'autorité de sûreté ; un N4 ne se dépose jamais comme document du registre |

Règles de visibilité par objet (telles que codées) : une **tâche** est vue par son rôle et ses co-rôles, par AGE et CAP (toutes), par toute partie sauf un prestataire quand elle est `ANY` ; un **jalon** est vu de tous sauf d'un prestataire, qui ne voit que les siens et ceux qu'il contresigne comme côté terre ; une **demande** est vue selon sa confidentialité, de son demandeur, de ses décideurs et de son exécutant, jamais de l'inspecteur ; un prestataire ne voit que les demandes qu'il a faites et les commandes qui lui sont confiées ; un **document** est vu de son organisation émettrice, puis selon N1/N2/N3 ; un prestataire ne voit que ses propres documents ; une **contestation** montre son en-tête à toute partie et ses exposés aux deux parties et à CAP ; un **fil d'échange** est vu de son organisation créatrice et des rôles invités (N1 : toute partie sauf prestataire non invité ; DIR voit les N2) ; une **alerte** est vue des rôles destinataires, CAP et DIR ; les **mesures** sont vues des rôles ayant V (NAV, TER, INS, AGE, CAP, COM, DIR) ; le **brouillon** d'escale n'est vu que de l'agence et du capitaine.

### 5.3.3 Cloisonnement par organisation (`rights.acts_for`)

Plusieurs organisations peuvent tenir le même rôle sur une escale (deux prestataires, deux inspecteurs, armateur et affréteur). Tout ce qui a un auteur — document, demande, fil, chiffre de mesure, contestation, rectification de jalon, fin d'interruption — n'est lu, remplacé, annulé ou clos que par **l'organisation qui l'a émis**, qu'elle ait agi par un compte ou par son lien sans compte ; le navire est une seule partie, tout lien capitaine valide parle pour lui. Côté terre (TER à quai, PRE en mer), une seule organisation enregistre les jalons, le chiffre terre et contresigne au nom de la terre : celle que l'agence ou la capitainerie a désignée (`CallParty.shore_side`), ou la seule à tenir le rôle ; à plusieurs sans désignation, aucune (refus explicite). Une commande de service nomme son prestataire quand plusieurs participent.

### 5.3.4 Second facteur et accès sans compte

| Situation | Règle |
| --- | --- |
| Connexion de CAP, APO, SUR, et de tout administrateur du port | mot de passe puis code TOTP, dès la connexion (`FLUXAA_MFA_REQUIRED_ROLES`) ; sans second facteur, ni les pages ni l'API ne s'ouvrent |
| Toute décision, clôture, révocation, acte d'administration | second facteur de moins de `FLUXAA_MFA_STEPUP_SECONDS` (8 h) : redemandé sinon ; par l'API, en-tête `X-MFA-Code` |
| Remplacement de l'application d'authentification | exige un code de l'ancienne ; téléphone perdu : réinitialisation par l'administrateur, journalisée, personne prévenue par courriel |
| Tentatives | limitées par compte et par adresse (mot de passe, TOTP, code d'accès) ; suspension jusqu'à quinze minutes ; une seule page de connexion, l'administration comprise |
| Lien ou code sans compte | rôles NAV, TER, INS, COM, PRE, SVC seulement ; portée une escale ; nom complet exigé ; jamais `strong_auth` ; ni tableau de bord, ni assistant, ni export, ni espace sûreté ; l'API l'accepte avec `Authorization: Master <jeton>` |
| Comptes d'intégration | jeton d'API créé après second facteur, un seul actif par personne, révocable ; un compte de périmètre `ais` ne peut qu'écrire des observations et des positions AIS |

## 5.4 Points d'arrêt et verrous

Un point d'arrêt (`HoldPoint`, EF-11) est une transition que la plateforme **refuse** tant que les tâches qu'il requiert ne sont pas faites ou que son invariant n'est pas satisfait. Le refus est explicite : il nomme chaque tâche manquante, son responsable et l'action attendue, est écrit au journal (`holdpoint.refused`, lisible par la capitainerie et l'agence) et produit une alerte bloquante. Les tâches requises sont paramétrables par port (`HoldPointRequirement`) ; les invariants de la seconde table ne le sont pas.

**Algorithme (`services/holdpoints.evaluate`)** — pour une transition `T` d'une escale, à l'heure `at` de l'acte (l'heure déclarée d'un jalon, pas l'heure de saisie) et pour une étape de référence (l'étape courante, ou l'étape suivante pour un déhalage) :

1. prendre les exigences du point d'arrêt du port pour `T` : couples (gabarit, numéro de tâche) ;
2. pour chaque tâche de l'escale qui correspond et qui n'est pas rattachée à une autre étape : si elle est `PENDING`, elle manque ; si c'est une tâche de **décision** (`request_side = decide`) faite, vérifier que l'autorisation qu'elle a produite est **en vigueur à `at`** (ni expirée, ni pas encore valable, ni annulée), sinon motif de refus ;
3. ajouter les invariants non paramétrables de `T` ;
4. aucune tâche manquante et aucun motif → autorisé ; sinon lever `HoldPointRefused` (ou `LockRefused` pour le connaissement) avec la liste bilingue des manques.

Une tâche déclarée « sans objet » par le rôle qui en répond ne manque plus ; une tâche de décision attendue par un point d'arrêt ne peut être déclarée sans objet que par son décideur.

### 5.4.1 Transitions gardées et tâches requises (paramétrage livré)

| Transition | Déclenchée par | Tâches requises (gabarit:n° — rôle) |
| --- | --- | --- |
| `DECLARE` déclarer l'escale | AGE | M0:02 jeu de données navire (AGE) · M0:03 certificats statutaires et d'assurance (NAV) · M0:05 contrôle des sanctions (AGE) |
| `GREEN_LIGHT` accorder le feu vert | décision CAP | M0:06 demande de vetting (TER) · M0:07 décision de vetting (CAP) |
| `BERTH_ASSIGN` attribuer un poste | décision APO | M0:06, M0:07, M0:09 feu vert de la capitainerie (CAP) |
| `MOVEMENT_AUTH` autorisation de mouvement | décision CAP | M0:21 libre pratique (ADM) · M0:22 formalités douanières et d'immigration (ADM) · **M0:09b feu vert de la sûreté et de la base navale (SUR, 1.5)** · M5:5.04 rejet des eaux de ballast (CAP, si M5) |
| `PILOT_BOARDING` pilote à bord (arrivée) | jalon SVC | M0:25 autorisation de mouvement (CAP) |
| `BERTHING` amarrage, à couple | jalons SVC / PRE | M0:25 · **M0:09b (SUR, 1.5)** · M3:3.03 zone et fenêtre STS (CAP, si M3) · MA2:A2.02 conditions de houle et courant (CAP, si bouée) |
| `START_TRANSFER` début du transfert / des opérations | jalons TER / PRE (`TRANSFER_START`, `STS_TRANSFER_START`, et `CARGO_OPS_START` pour les autres cargaisons, 1.5) | M0:27 réunion pré-transfert · M0:28 liste de contrôle de sécurité (ISGOTT, BLU ou manutention selon la cargaison) · M0:29 essai d'arrêt d'urgence (vrac liquide) · M0:31 mise en sécurité du poste (TER, vrac liquide) · **M0:09c feu vert du terminal (TER, quai) · M0:09d feu vert du mandant (COM) · M0:31b poste prêt — manutention (TER, quai, hors liquide) (1.5)** ; selon l'opération : M1:1.04–1.07, M2:2.04–2.09, M3:3.01–3.11, M4:4.01–4.06, et depuis la 1.5 MB1:B1.04–B1.07 (cales acceptées, plan BLU convenu, draft survey initial, engins), MB2:B2.05–B2.07, MC1:C1.02 / C1.05, MG1:G1.03 / G1.05, MR1:R1.02 / R1.04, MX1:X1.03 (détail dans l'onglet *5. Catalogues*, point d'arrêt `START_TRANSFER`) |
| `DOUBLE_BANKING` accostage à couple | décision | M9:9.02 accord du navire intérieur (NAV) · 9.04 analyse d'amarrage · 9.06 matrice des opérations simultanées · 9.08 plan de déhalage d'urgence (TER) |
| `HOT_WORK` travaux par point chaud | décision CAP | M7:7.04 autorisation (CAP) · 7.05 certificat de dégazage (INS) · 7.06 permis nominatif (NAV) |
| `BL_ISSUE` émission du connaissement | dépôt AGE | M2:2.16 instruction documentaire écrite (COM) · MB2:B2.16 (vrac sec, 1.5) + invariants ci-dessous |
| `DEPARTURE_CLEARANCE` congé de départ | décision CAP | M0:32 déchets remis (PRE) · M0:33 formalités de sortie (ADM) · M7:7.12 certificats mis à jour (NAV, si M7) |
| `PILOT_BOARDING_DEP` pilote à bord (départ) | jalon SVC | M0:34 congé de départ (CAP) |
| `DEPARTURE` dernière amarre, appareillage | jalons SVC | M0:34 |
| `CLOSE` clôture | CAP | M0:36 rapport des faits produit et signé (AGE) + invariants |
| déhalage `SHIFT_START` | jalon SVC | étape suivante planifiée ; autorisation de mouvement en vigueur à l'heure du fait ; tâches bloquantes de l'étape suivante (celles du point d'arrêt `PILOT_BOARDING` évalué sur cette étape) |

### 5.4.2 Invariants non paramétrables

| Verrou | Règle | Qui pourrait le lever |
| --- | --- | --- |
| Connaissement | impossible sans l'instruction documentaire écrite du mandant (M2:2.16 faite), sans accord sur la quantité (certificat de quantité M2:2.15 fait), avec une contestation de mesure non close (OPEN ou ANSWERED) ou un écart bord/terre final hors tolérance | personne — ni rôle, ni paramétrage, ni administrateur |
| Poste et feu vert | impossibles sans une acceptation de navire (vetting) valide et non expirée quand l'escale en a demandé une | personne |
| Clôture | impossible tant qu'une contestation n'est pas close (une réponse ne suffit pas) ou qu'une mesure est incomplète (valeur bord ou terre absente) | la capitainerie peut clore une contestation sans accord, jamais la trancher |
| Autorisation périmée | une tâche de décision faite n'ouvre un point d'arrêt que si son autorisation est en vigueur à l'heure du fait | une nouvelle demande décidée |
| Décision sans objet | une tâche de décision ne se fait pas à la main et ne se déclare sans objet que par son décideur | — |
| Escale close | aucune écriture sur une escale CLOSED ou ARCHIVED (document généré compris) | — |

**Message de refus (O).** Format, en français et en anglais, affiché dans un encadré dédié et renvoyé par l'API (`409 hold_point_refused`, `missing[]`, `reasons[]`) : « Refusé : « *transition* » n'est pas encore possible. Tâche manquante `M0:25` « *intitulé* » — responsable : *rôle* — action attendue : *nature*. » puis les motifs d'invariant. Le même texte est journalisé et devient une alerte bloquante adressée à CAP, AGE et au rôle qui a tenté l'acte. Depuis la 1.4, l'encadré nomme pour chaque tâche manquante **qui en répond** (les organisations tenant le rôle, avec leur moyen d'agir : compte, lien d'accès, ou rien) et offre à qui le regarde ses propres moyens d'agir (fournir le document, confirmer, relancer la partie, remettre son accès au capitaine) — §5.5.6.

## 5.5 Contrôle des pertes et interface navire/terre (version 1.4, FLX-CDC-002 §6.12)

### 5.5.1 Journal de pompage tenu par les deux bords (`measurements.open_pumping_sheet`, `add_pumping_entry`, `compare_sides`)

| Règle | Détail |
| --- | --- |
| Deux feuilles | le navire (capitaine par son lien, ou compte NAV) ouvre la feuille **bord** (`PumpingLogSheet.side = SHIP`), le terminal qui parle au nom du côté terre la feuille **terre** ; une feuille porte la citerne ou le bac, le produit, le niveau de départ et d'arrêt prévu, le barème (m³ par mètre), la densité, le VCF, la quantité prévue (m³ et t — t = m³ × d × VCF quand elle n'est pas saisie), le débit et la pression attendus, les heures estimées ; plusieurs feuilles par côté (changement de bac) ; la feuille est **terminée** par son côté (niveau d'arrêt réel, volume final = dernier cumul si absent) et n'accepte plus de relevé |
| Un relevé | heure déclarée, pression au collecteur, débit, température, **niveau (mm)**, **quantité transférée depuis le relevé précédent (m³)**, **cumul (m³)**, cumul (t), remarque ; ce que la partie ne saisit pas est **calculé depuis la feuille** et figé dans le relevé (append-only) : transféré = |niveau − niveau précédent (ou de départ)| / 1000 × barème ; cumul = cumul précédent + transféré ; tonnes = cumul × d × VCF ; débit = transféré ÷ heures écoulées. Un relevé sans feuille désignée rejoint la feuille ouverte du côté (appli terrain) ; émetteur unique : NAV pour le bord, TER parlant pour la terre ; COM, INS et les autres lisent |
| Appariement | un relevé terre et un relevé bord déclarés à moins de **45 minutes** l'un de l'autre forment une ligne (`compare_sides`, `PAIRING_WINDOW`) ; écart = **terre − bord**, horaire (sur le transféré) et cumulé (sur le cumul), en m³ et en % du chiffre bord ; aucun chiffre n'est la référence |
| Seuil d'arrêt | quand l'écart horaire **ou** cumulé dépasse `Port.quantity_tolerance_pct` (0,300 %, la règle des journaux de pompage des terminaux « arrêter le déchargement pour investigation si l'écart dépasse 0,3 % »), une alerte `QUANTITY` est créée (pièce du dossier, rapport des faits) et notifiée **en temps réel** aux lecteurs du journal ; la plateforme signale et ne tranche pas, n'arrête rien |
| Lecteurs | décidés au paramétrage (`ReportAccess PUMPING_LOG`, défaut NAV, TER, CAP, INS, COM, DIR, AGE) ; le journal imprimé (`PUMPING_LOG`, formulaire généré, émis par TER ou NAV) suit les lecteurs de son type de document |

### 5.5.2 Relevés par citerne validés par l'inspecteur (`add_tank_reading`, `review_tank_reading`, `rights.tank_reading_visible`)

| Règle | Détail |
| --- | --- |
| Qui relève | les citernes à cargaison du navire : le navire ; les bacs du terminal : le terminal qui parle pour la terre ; nul autre (COM, INS, AGE : refus) ; une mesure (`Measurement`) porte les relevés de ses deux côtés en plus des totaux déclarés |
| Un relevé | citerne, creux ou innage (mm), température, eau libre, densité à 15 °C, TOV, GOV, VCF, GSV, masse ; GSV = GOV × VCF et masse = GSV × densité sont calculés quand ils ne sont pas saisis (API MPMS ch. 12) ; au moins une valeur ; scellé, append-only ; une **correction** est un nouveau relevé qui remplace le précédent (`supersedes`) |
| Validation | seul l'inspecteur (INS) **valide** ou **rejette** (motif obligatoire) le dernier relevé d'une citerne, une seule fois (`TankReadingReview`, append-only ; le dernier examen fait l'état : PENDING, VALIDATED, REJECTED) ; un relevé remplacé ne s'examine plus |
| Visibilité | un relevé en attente ou rejeté n'est vu que par **son côté** (le navire ; le terminal qui l'a saisi) et par l'inspecteur ; un relevé **validé** est vu par les lecteurs des mesures (`ReportAccess MEASUREMENTS`) ; l'export et l'API suivent la même règle ; l'écran montre par côté le total des citernes validées face au chiffre déclaré du côté, et le nombre de relevés en attente ou rejetés |
| Notifications | relevé saisi → l'inspecteur (temps réel, une fois par mesure, côté et heure) ; validé → les lecteurs (une fois par mesure, côté et heure) ; rejeté → le côté et l'agence (temps réel : le capitaine n'a pas de compte, l'agence relaie) |

### 5.5.3 Lecteurs décidés au paramétrage (`ReportAccess`, `rights.report_readers`, `DocumentType.readers_exact`)

| Rapport | Qui lit (défaut) | Où se règle |
| --- | --- | --- |
| Journal de pompage (`PUMPING_LOG`) | NAV, TER, CAP, INS, COM, DIR, AGE | administration → *Accès aux rapports* |
| Mesures et relevés validés (`MEASUREMENTS`) | NAV, TER, CAP, INS, COM, DIR, AGE | idem (remplace la colonne V de la matrice `measurement`) |
| Liste de contrôle navire/terre (`SAFETY_CHECKLIST`) | NAV, TER, CAP, APO, INS, AGE, SUR, DIR ; les deux bords lisent toujours | idem |
| Tableau des escales du port (`CALL_BOARD`) | tous les rôles sauf NAV | idem |
| Time sheet (`TIME_SHEET`) | **toutes les parties** (N1) ; émis par AGE, TER ou NAV | type de document |
| Certificat de qualité (`QUALITY_CERT`) | TER, COM (trader, superintendant, contrôle des pertes), NAV, INS (émetteur), CAP, APO, DIR — **pas l'agence** : `readers_exact` retire la règle N2 qui ajoute AGE, CAP, DIR et COM | type de document (*lecteurs limités à la liste*) |

`bootstrap_ports` crée les lignes manquantes avec ces défauts et ne touche jamais au réglage du port ; la migration `0015` applique les nouveaux défauts aux ports déjà installés **seulement** s'ils tiennent encore l'ancienne valeur du catalogue.

### 5.5.4 Cloisonnement entre agences et tableau des escales du port (`board`)

Les informations opérationnelles d'une escale (parties, tâches, demandes, documents, mesures, journal de pompage, liste de contrôle, échanges, journal, export, API) ne sont accessibles qu'aux organisations qui y tiennent un rôle actif (`rights.call_queryset_for_user`, `actor_for_call`) : une autre agence répond *introuvable* (404) sur chaque page et chaque route API de l'escale, ne reçoit aucune notification, ne voit pas la référence dans ses listes. Le **tableau des escales du port** (`/escales/port/`, `GET /api/v1/board/`) montre à tout compte du port autorisé (`CALL_BOARD`) chaque escale déclarée et non close (actives ; parties ou closes depuis moins de 24 h à l'ATD) avec les seuls champs d'un tableau de port : navire (nom, OMI, pavillon), agence, zone ou poste, gabarits d'opération (codes), état, ETA/ATA, ETB/ATB, ETD/ATD ; jamais le produit, la quantité, les parties ou un lien : la référence et le lien n'apparaissent que pour les organisations qui tiennent un rôle sur l'escale (*consultation seule* sinon).

### 5.5.5 Liste de contrôle navire/terre en ligne (`services/checklist`, `SafetyChecklist`)

| Règle | Détail |
| --- | --- |
| Ouverture | le navire ou le terminal parlant pour la terre ouvre la liste (une seule ouverte à la fois ; versions successives) ; les points du catalogue (`apps/registry/ssscl.py`, structure de l'ISGOTT 6e éd. : 1A, 1B, 2, 3, 4, 5A accords, 6 vérifications répétées — 45 points, formulés par la plateforme) sont **copiés dans l'enregistrement** : une liste signée reste lisible telle que signée ; intervalle des vérifications répétées saisi à l'ouverture ou convenu au point 5A.8 |
| Réponses | chaque côté coche ses points (oui / non / sans objet), les points communs demandent les deux ; un « non » exige une remarque et notifie l'autre bord, l'agence et la capitainerie en temps réel ; les accords (5A) sont écrits par l'un ou l'autre côté ; chaque réponse est un enregistrement scellé et nominatif (append-only), la dernière réponse par point et par côté fait l'état |
| Signature | un côté signe quand tous ses points sont « oui » ou « sans objet » et que les accords sont écrits ; la signature signe aussi la **tâche conjointe M0:28** pour son rôle ; la seconde signature clôt la liste (`SIGNED`), termine M0:28, ce qui enregistre le jalon système `SSSCL_SIGNED` (point d'arrêt du début de transfert) et dépose le formulaire `SSSCL` pré-rempli des coches (document généré, lié à la liste) |
| Après signature | seules les vérifications répétées (points R) se cochent à nouveau, numérotées (`repetition` 1, 2…), jusqu'à la clôture de l'escale ; la prochaine échéance = dernière répétition (ou signature) + intervalle |
| Annulation | l'agence ou la capitainerie annule une liste ouverte (motif) ; une liste signée ne s'annule pas |
| Lecture | les deux bords toujours ; les autres rôles selon `SAFETY_CHECKLIST` ; le capitaine la renseigne depuis son téléphone (page `/escales/<id>/liste-de-controle/`, sans menu) |

### 5.5.6 Préparation de la déclaration (`services/preparation`)

| Règle | Détail |
| --- | --- |
| Ce qui manque, qui en répond | `preparation.readiness` : pour chaque tâche que le point d'arrêt `DECLARE` attend (M0:02 jeu de données navire — AGE ; M0:03 certificats — NAV, **co-rôle AGE** depuis la 1.4 ; M0:05 sanctions — AGE), les organisations tenant le rôle ou un co-rôle, avec leur moyen d'agir (comptes, lien d'accès, accès capitaine valide) et l'action qui la termine (document à fournir, demande, jalon, confirmation) ; affiché dans l'aperçu (*Avant la déclaration*, brouillon, AGE et CAP) et dans l'encadré de refus |
| Les certificats par l'agence | l'agence dépose les certificats statutaires pour le compte du capitaine (type `CERTIFICATES`, émetteurs NAV et AGE) et la tâche M0:03 se termine (co-rôle) ; l'acte est journalisé sous le rôle AGE |
| Accès capitaine par courriel | `issue_master_link(send_to=…)` : le lien et le code sont envoyés au capitaine avec la **liste de ce que le port attend de lui** (tâches NAV en attente, avec leurs échéances) ; journal `master_link.sent` ; le lien et le code restent affichés une fois à l'agence |
| Relance | l'agence ou la capitainerie relance une tâche en attente (`remind`) : notification temps réel aux comptes du rôle (jamais au rôle de l'émetteur de la relance) ; pour le navire, courriel à l'adresse de l'accès capitaine — refus explicite s'il n'a pas d'accès valide ou si l'accès a été remis sans adresse ; journal `task.reminded` ; dernière relance affichée |
| À la création | les autres comptes de l'agence sont notifiés de ce que la déclaration attend (le créateur le lit à l'écran) |

## 5.6 Généralisation de la plateforme (version 1.5, FLX-CDC-002 §6.13)

### 5.6.1 Validité d'une annonce et reprise (`calls.validity_for`, `expire_call`, `renew_call`, `scheduler.watch_validity`)

| Règle | Détail |
| --- | --- |
| Fixée à l'annonce | chaque escale porte une validité en jours (`PortCall.validity_days`, obligatoire à l'annonce ; défaut `Port.default_validity_days` = 15, plafond `Port.max_validity_days` = 90 ; entier entre 1 et le plafond) et la date qu'elle fixe (`valid_until` = création + validité) ; l'API la reçoit (`validity_days`) ou prend le défaut |
| Rappels | le planificateur (`watch_validity`, toutes les minutes avec les autres surveillances) notifie l'agence et la capitainerie **72 h puis 24 h** avant l'échéance (`VALIDITY_REMINDERS_H`), une fois chacun (le rappel de 24 h en temps réel) |
| Obsolescence | à l'échéance, une escale **pas encore à quai** (DRAFT, DECLARED, ACCEPTED, PLANNED, APPROACHING) passe **Obsolète** (`EXPIRED`, `expired_at`), ses liens d'accès s'éteignent, l'agence, la capitainerie et l'autorité portuaire sont notifiées en temps réel ; elle reste lisible et exportable, aucune écriture n'y est plus acceptée ; une escale **à quai ou au-delà n'est jamais interrompue** : son dépassement (`validity_overrun`, heures au-delà de `valid_until`) est signalé chaque jour et compté |
| Reprise | l'agent principal refait l'annonce (`renew_call`) : nouvelle escale en brouillon, même navire, zone, opérations, modules, cargaison, quantité, voyage, parties et accès, même validité en jours comptée depuis la reprise, `renewed_from` ; une seule reprise non terminée par escale ; l'ancienne pointe vers la nouvelle |
| Facturation | la validité annoncée, le temps passé au port et le dépassement sont la base de facturation de l'escale : `PortCall.billing_basis()` (validité, du / au, arrivée, départ, clôture, obsolescence, heures au port, heures de dépassement) est exposée dans la fiche (*Validité de l'annonce*), le time sheet (section E) et l'API (`billing_basis`) ; la plateforme ne facture pas, elle donne les chiffres |

### 5.6.2 Feux verts de chaque partie (`tasks.green_lights`, `complete_task`, `withdraw_green_light`)

| Règle | Détail |
| --- | --- |
| Quatre feux | des tâches du socle commun portent `green_light` : **M0:09** capitainerie (donné par la décision sur la demande *Feu vert*), **M0:09b** sûreté et base navale (SUR, ETA − 24 h), **M0:09c** terminal (TER, ETB − 6 h, escales à quai), **M0:09d** mandant — armateur / affréteur (COM, ETB − 6 h) ; un port en ajoute ou en retire dans le gabarit M0 (case *feu vert* d'une tâche de version brouillon) |
| Ce qu'ils gardent | M0:09b est requis par `MOVEMENT_AUTH` (autorisation de mouvement) et `BERTHING` (amarrage) ; M0:09c et M0:09d par `START_TRANSFER` (début du transfert ou des opérations) ; un refus de point d'arrêt les nomme comme toute tâche manquante |
| Donner | la partie qui tient le rôle le donne depuis le panneau de l'aperçu ou sa ligne de tâche (`task_complete`, note facultative ; COM y est admis bien qu'il ne fasse aucune autre tâche de confirmation) ; l'acte est journalisé et notifié en temps réel à AGE, CAP, NAV, TER |
| Retirer | la partie qui l'a donné, ou la capitainerie, le **retire avec un motif obligatoire** (`withdraw_green_light`) : la tâche redevient à faire avec la mention *retiré par \<rôle> : \<motif>*, les points d'arrêt qu'elle garde se referment aussitôt, toutes les parties concernées sont notifiées (*FEU VERT RETIRÉ par … — motif*) ; le feu vert de la capitainerie, lié à une autorisation, se retire par l'annulation de l'autorisation |
| État | `green_lights(call)` donne pour chaque feu : *donné* (par qui, quand), *attendu* (échéance), *refusé* (décision de refus sur la demande), *sans objet* (tâche non applicable) ; même lecture dans l'API (`GET …/green-lights/`) |

### 5.6.3 Accès contrôlé au dossier et agences associées (`CallParty.access`, `rights.access_of`, `can_act_in`, `require_act`, `calls.set_party_access`)

| Règle | Détail |
| --- | --- |
| Agent principal | l'agence qui annonce l'escale (`PortCall.agency`) est l'**agent principal** : elle seule déclare, révise les heures, annule, confirme la clôture et refait l'annonce ; elle donne à chaque partie qu'elle invite l'accès au dossier |
| Trois niveaux | `FULL` : tous les onglets de son rôle, agit dans son rôle ; `PARTIAL` : les onglets listés (`scopes` parmi aperçu, parties, tâches, demandes, jalons, documents, mesures, contestations, échanges, journal), agit dans ces onglets seulement ; `READ` : tous les onglets de son rôle, **aucun acte** ; l'agent principal, les parties par défaut du port et les parties invitées par la capitainerie gardent l'accès complet — une tentative de le restreindre est refusée |
| Qui fixe | à l'annonce (ligne de partie, accès prédéfini), à l'invitation et à tout moment depuis l'onglet Parties (`party_access`) par l'agent principal ou la capitainerie ; journal `party.access`, partie notifiée |
| Application | écran : les onglets hors accès ne sont pas offerts, un onglet demandé hors accès ramène au premier permis ; une partie sans droit d'agir ne voit aucun bouton d'action (`_strip_acts`) ; chaque action POST est rattachée à un onglet (`ACTION_SCOPES`) et `rights.require_act` la refuse hors accès avec un refus explicite (*Votre accès à cette escale est en lecture seule…* / *… ne couvre pas cette partie du dossier (tâches) : l'agent principal le donne*) ; API : les vues de sous-ressources portent leur onglet (`CallAPIView.scope`) — 404 hors accès en lecture, refus en écriture ; `your_access` dans la représentation de l'escale |
| Agences associées | une opération peut nommer **plusieurs agences** : l'agent principal invite une autre agence du port avec le rôle AGE (`AGENCY_INVITABLE_ROLES` comprend AGE) et l'accès voulu ; l'agence associée voit l'escale dans sa liste, agit dans son accès, et n'est jamais agent principal ; une agence associée n'invite pas |
| Rôles tenus à plusieurs | toute partie dont le rôle est tenu par plusieurs organisations (deux terminaux, deux inspecteurs…) reçoit son propre accès ; la désignation *parle pour la terre* reste celle de la 1.3 |

### 5.6.4 Transbordement navire-navire : deux escales, deux équipes (`calls._create_sts_partner`, `measurements.counterpart_entries`)

| Règle | Détail |
| --- | --- |
| Deux escales | un STS implique le navire qui **livre** et celui qui **reçoit** (`PortCall.sts_role` : DONOR / RECEIVER) ; chacun a **sa propre escale**, son agence, ses parties, ses tâches et ses mesures ; les deux sont reliées (`linked_call`, rôles inverses) |
| Création | à l'annonce, l'agence nomme son rôle et le partenaire : une escale déjà annoncée (la sienne), un navire enregistré ou un navire nouveau ; dans les deux derniers cas la plateforme **crée l'escale du partenaire** aussitôt — sous l'agence nommée (une agence du port) ou la sienne — avec la zone STS, le gabarit M3 et le module MA3, le rôle inverse, la même cargaison et la même validité ; l'agence qui annonce y est inscrite comme **agence associée** (accès complet) pour suivre l'opération ; l'API fait de même (`sts_partner`) |
| Journaux rapprochés | sur une escale STS, la « terre » du journal de pompage est le journal **bord du partenaire** : `compare_sides` apparie les relevés des deux navires (fenêtre de 45 min), l'écart affiché et exporté est *partenaire − bord* ; les feuilles, relevés et validations restent ceux de chaque escale |
| Invariant | un navire ne peut être son propre partenaire ; l'agence du partenaire doit être une agence du port ; l'un livre, l'autre reçoit |

### 5.6.5 Documents attendus dès l'annonce (`tasks.request_documents`, `Task.requested_at_creation`)

| Règle | Détail |
| --- | --- |
| Obligatoires | les documents que les gabarits exigent (tâches de nature F) sont instanciés comme avant et bloquent ce qu'ils bloquent ; l'annonce les liste, par opération cochée, pour information |
| Ajoutés | l'agence ajoute à l'annonce les documents **facultatifs du catalogue** (`expected_documents`, tout type non généré actif) et **tout autre document** de la liste ouverte (`custom_documents` : libellé, rôle émetteur, heures avant l'ETA) ; après l'annonce, l'agence ou la capitainerie en demande d'autres depuis l'onglet Documents (`documents_request`) |
| Ce qu'ils deviennent | chaque document demandé devient une **tâche non bloquante** de nature F de la partie qui l'émet (numéro `D1`, `D2`…, type de document du catalogue ou `OTHER` pour un libellé libre, échéance relative à l'ETA, `requested_at_creation`), notifiée à la partie, visible dans *Documents attendus* ; la fournir termine la tâche ; la liste n'est jamais close |

### 5.6.6 Toutes les cargaisons (`CargoKind`, `CallTemplate.cargo_kinds`, `TemplateTask.cargo_kinds`, `checklists`, `forms`)

| Règle | Détail |
| --- | --- |
| Nature de cargaison | chaque escale porte une nature (`PortCall.cargo_kind` : vrac liquide, vrac sec, conteneurs, marchandises diverses, roulier, autre) et chaque navire un type (`Vessel.vessel_kind`) ; la nature choisit les **gabarits** offerts (`CallTemplate.cargo_kinds` ; M1, M2, M3, M6, MA2 : liquide ; MB1, MB2 : vrac sec ; MC1 : conteneurs ; MG1 : divers ; MR1 : roulier ; MX1 : toute escale ; M4, M5, M7, M8, M9, MA3 : toutes), les **tâches du socle commun** qui s'appliquent (`TemplateTask.cargo_kinds` : M0:29 et M0:31 réservées au liquide, M0:31b au quai hors liquide), les **unités** (`UNITS_BY_CARGO`), les **natures de mesure** (draft survey, pesée, pointage), la **liste de contrôle** (`checklists.standard_for` : SSSCL, BLU, CARGO) et les **formulaires** (`Form.cargo_kinds`, `Form.templates`) |
| Gabarits livrés | MB1 déchargement de vrac sec (17 tâches : manifeste et plan de déchargement, cales acceptées, plan BLU convenu, draft survey initial et final, engins et trémies, cadence, nettoyage, out-turn…), MB2 chargement de vrac sec (19 : déclaration IMSBC, humidité et TML, cales inspectées, séquence de chargement, trimming, instruction documentaire, connaissement…), MC1 opérations conteneurs (13 : bay plan, liste des mouvements, EDI, reefers, DG, pointage, EIR…), MG1 marchandises diverses et colis (14 : plan d'arrimage, assujettissement, pointage, reçus de bord, constats), MR1 roulier (12 : liste des véhicules, rampe, saisissage, pointage, dommages), MX1 autre escale — passagers, navire d'État, pêche, recherche, relâche (9 : objet, autorisations, services, sûreté) ; jalons `HOLDS_ACCEPTED`, `DRAFT_SURVEY_INITIAL`, `CARGO_OPS_START` (point d'arrêt `START_TRANSFER`, pose T0), `CARGO_OPS_END` (pose T1), `DRAFT_SURVEY_FINAL` ; 18 types de document (manifeste, plan d'arrimage, bay plan, déclaration DG, déclaration IMSBC, accord BLU, draft survey, inspection des cales, pointage, reçu de bord, out-turn, constat de dommages, liste BLU, liste manutention, PAEC, grille de vetting, plan de manutention, plan d'occupation) |
| Listes de contrôle | vrac liquide : ISGOTT (45 points, 7 parties) ; vrac sec : **Code BLU** (22 points : avant l'arrivée, avant les opérations, pendant, après ; navire / terminal / commun) ; conteneurs, divers, roulier, autre : **opérations de manutention** (20 points : accès et passerelle, engins et grues, arrimage et marchandises dangereuses, communications et urgence) ; même mécanique (ouverture, réponses des deux bords, signatures, répétitions, formulaire déposé) |
| Formulaires | quinze formulaires ajoutés (PAEC et plan de manutention pour le liquide ; grille de vetting ; manifeste, plan d'arrimage, bay plan, déclaration DG, déclaration IMSBC, accord BLU, draft survey, inspection des cales, pointage, reçu de bord, out-turn, constat de dommages) ; le time sheet s'adapte (opération, jalons `CARGO_OPS_*`, validité et dépassement en section E) ; les formulaires liquides (journal de pompage, pré-transfert, ullage, flexibles, SSSCL) ne sont offerts qu'au vrac liquide |
| Migration | `0017_catalogue_1_5` publie pour chaque port une nouvelle version de M0 (tâches 09b, 09c, 09d, 31b ; 09 marquée feu vert ; 29 et 31 réservées au liquide), ajoute les gabarits, jalons, types de document et points d'arrêt du catalogue cargo ; les escales en cours gardent leur version de gabarit, leurs tâches M0:09 existantes sont marquées feu vert |

## 5.7 L'annonce s'adapte à l'opération (version 1.6, FLX-CDC-002 §6.13, EXG-R-11)

### 5.7.1 Questions propres à chaque modèle d'opération (`CallTemplate.intake_schema`, `PortCall.operation_details`, `services/intake`)

| Règle | Détail |
| --- | --- |
| Fiche d'intention d'un modèle | chaque modèle d'opération ou module porte les **questions que le port pose à l'annonce quand il est choisi** (`intake_schema`, même grammaire que `RequestType.form_schema` : `key`, `label_fr/en`, `type` text / textarea / number / integer / datetime / boolean / select, `required`, `options`, `help_fr/en`) ; le catalogue livre les fiches de M1 à M9, MA3, MB1, MB2, MC1, MG1, MR1 et MX1 (`catalog.INTAKE`) ; le port les adapte dans l'administration (ajout, retrait, caractère obligatoire) |
| Formulaire adaptatif | l'annonce affiche le bloc de chaque modèle **au moment où il est coché** (`fieldset[data-intake]`, script `app.js`) ; une question obligatoire ne lie que tant que son bloc est visible (`data-required` → `required`) ; côté serveur `intake.parse_intake` ne lit que les modèles choisis, type chaque réponse (nombre à virgule ou espace accepté, entier, date-heure du port, option de la liste, case à cocher) et refuse une question obligatoire sans réponse (*M4 — Quantité totale (t) est obligatoire pour cette opération*) ; le formulaire revient rempli |
| Conservation | les réponses sont gardées sur l'escale par code de modèle (`operation_details` : `{"M4": {"grade": "VLSFO", "quantity_mt": 450}}`), inscrites au journal `call.created`, montrées sur l'aperçu (*Déclaré à l'annonce*, `intake.declared`), reprises à la reprise d'une annonce (`renew_call`), copiées au partenaire d'un STS (M3) et d'un accostage à couple (M9), servies par l'API (`operation_details`, `declared`) et par l'export (format 1.3). **Lecture** : comme le produit et la quantité, ces réponses (soutier, grade et quantité soutés, trois dernières cargaisons, manutentionnaire…) ne sont montrées qu'à ceux qui lisent l'escale entière (`rights.can_see_full_call`) — un prestataire nommé sur l'escale ne les lit ni sur l'aperçu ni par l'API ; il lit ce qui le concerne dans la demande qui lui est adressée |
| Préremplissage des demandes | une demande ne commence qu'avec ce dont le registre répond (`intake.prefill_for_request`) : **(1)** les réponses aux questions **du modèle dont une tâche lève cette demande**, pour les clés que la fiche et le formulaire partagent — `BUNKERING` ← M4 (grade, quantité, soutier, accord du terminal), `BALLAST_DISCHARGE` ← M5 (volume, méthode), `GAS_FREEING` ← M6 (méthode), `HOT_WORK` et `IMMOBILIZATION` ← M7 (travaux ; durée, remise en service), `CREW_CHANGE` ← M8 (relevants, débarquants), `STS_ZONE` ← M3 (fenêtre, POAC), `DOUBLE_BANKING` ← M9 (objet, durée), `ANCHORAGE_POSITION` ← MA3 (arrivée en rade) ; **une clé partagée par hasard avec un autre modèle n'est pas reprise** (le volume de ballast n'est pas un volume de déchets, la durée d'un accostage à couple n'est pas celle d'une immobilisation, la fenêtre d'un transbordement n'est pas le créneau d'un poste) ; **(2)** les faits du navire déclarés une fois, quel que soit le modèle qui les a demandés (`intake.SHARED_KEYS` : `last_cargoes`, les trois dernières cargaisons → `VESSEL_ACCEPTANCE`) ; **(3)** ce que l'escale dit elle-même (`product`, `quantity`, `requested_berth` → `VESSEL_ACCEPTANCE`) et le navire de son lien (`partner_vessel` d'un STS, `inner_vessel` d'un accostage à couple). Un choix repris dans un champ libre s'y lit en clair, plus par son code. La demande, sur l'onglet Demandes comme sur la ligne de sa tâche, porte la mention *prérempli depuis l'annonce — à vérifier avant d'envoyer* ; rien n'est prérempli pour qui ne lit pas l'escale entière |
| Occupation du poste | quand l'agence choisit un poste et une fenêtre (ETA / ETB / ETD), un fragment HTMX (`/escales/nouvelle/occupation/`, `calls.berth_occupation`) lui montre **qui tient ou attend ce poste sur la fenêtre** (escales actives dont le poste attribué ou demandé est celui-là et dont la fenêtre — ATB/ETB/ETA à ATD/ETD, 36 h par défaut — chevauche) et lui propose un autre poste, d'autres heures ou un accostage à couple ; à la création, le même chevauchement vaut un avertissement si M9 n'est pas choisi |

| Parties proposées par l'opération | chaque modèle porte les **parties qu'il appelle habituellement** (`apps/core/parties.PARTIES_BY_OPERATION` : M1 terminal pétrolier, inspecteur de cargaison, réceptionnaire, laboratoire ; M3 prestataire STS (POAC, défenses, flexibles), inspecteur, affréteur ; M4 soutier, inspecteur de soutage ; M6 installation de réception, nettoyage de citernes ; M7 entreprise de réparation, classification, plongée ; M8 agence de relève, avitailleur, eau douce, médical ; M9 fournisseur de défenses ; MB1 / MB2 terminal de vrac, manutentionnaire, draft surveyor, réceptionnaire ou chargeur, pont-bascule ; MC1 terminal à conteneurs, manutentionnaire, transitaire ; MG1 / MR1 terminal, manutentionnaire, société de pointage, réceptionnaire). L'annonce les liste **au moment où le modèle est coché** (`[data-party-hints]`), chacune avec son rôle et la raison de sa présence ; un bouton **ajoute la ligne de partie** avec le rôle et la nature préremplis (`app.js`, `addRow`). Suggestion issue de la pratique portuaire, jamais une obligation : la liste des parties reste ouverte, et les natures `BULK_TERMINAL`, `CONTAINER_TERMINAL`, `GENERAL_CARGO_TERMINAL`, `STEVEDORE`, `LASHING`, `FUMIGATION`, `WEIGHBRIDGE`, `TALLY_COMPANY`, `BUNKER_SURVEYOR`, `FREIGHT_FORWARDER` complètent le catalogue des natures de parties |
| Compatibilité navire / poste à l'annonce | le même fragment lit, dès qu'un poste est demandé et qu'un navire est choisi (ou qu'un DWT est saisi pour un navire nouveau), les **limites d'acceptation du poste contre les caractéristiques du navire** (`forms/cargo.vetting_rows_for`, mêmes lignes que la grille de vetting : LOA, tirant d'eau, largeur, déplacement, port en lourd, collecteur, tirant d'air, âge, SWL) et l'avis (`vetting_verdict`) ; seules les lignes évaluables s'affichent (✓ dans la limite, ✗ limite obligatoire dépassée, ! vigilance) ; un poste dont les natures de cargaison reçues (`Berth.cargo_kinds`) excluent la nature choisie est signalé. Lecture indicative avant la demande de poste : la grille complète du terminal reste le formulaire `VETTING_CHECKLIST` émis sur l'escale |

### 5.7.2 Accostage à couple nommé à l'annonce (`calls.create_call(db_partner=…)`, `_create_db_partner`, `_on_board`, `complete_reciprocal_link`)

| Règle | Détail |
| --- | --- |
| Bloc de l'annonce | cocher le module **M9** révèle le bloc *Accostage à couple* : la **position** de ce navire — `OUTER` vient à couple du navire à quai, `INNER` est à quai et reçoit l'autre —, puis **l'autre navire** : une **escale du port** (`db_partner_call`, toute agence : les escales déclarées ou plus avancées, non terminées, à quai ou attendues à quai, telles que la conférence de placement les montre — `_double_banking_candidates`, lecteurs `CALL_BOARD`), un **navire enregistré** sans escale (`db_partner_vessel`) ou un **navire nouveau** (`db_imo`, `db_name`…), et pour ces deux derniers l'**agence de l'autre navire** (`db_partner_agency`, vide = la mienne) ; sans autre navire, l'annonce avec M9 est refusée |
| Même agence | l'escale désignée appartient à l'agence (ou l'acteur est la capitainerie) : les deux escales sont liées **dans les deux sens** aussitôt (`link_kind` OUTER / INNER réciproques, journal `call.linked` des deux côtés) |
| Autre agence | l'escale désignée appartient à une autre agence : le lien est posé **à sens unique** sur l'escale annoncée (`linked_call`, `link_kind`), l'aperçu porte *lien à confirmer par l'autorisation d'accostage à couple de la capitainerie* ; l'**agence du navire intérieur, son capitaine et la capitainerie sont avertis aussitôt** (`_notify_partner_link`, clé `double_banking:<annoncée>:<désignée>`) ; la **décision favorable de la capitainerie sur la demande `DOUBLE_BANKING`** (point d'arrêt `DOUBLE_BANKING` : accord exprès du navire intérieur 9.02, analyse d'amarrage 9.04, matrice SIMOPS 9.06, plan de déhalage 9.08) rend le lien **réciproque** (`requests.decide_request` → `complete_reciprocal_link`, journal sur l'escale intérieure) ; la capitainerie peut aussi lier les deux escales elle-même (`link`) |
| Navire sans escale | l'autre navire reçoit **sa propre escale** dans le même acte (`_create_db_partner`) : même zone, mêmes heures, mêmes opérations et le module M9, position inverse, sous son agence si elle est nommée (l'agence annonçante y est **agence associée**), avec les réponses M9 de l'annonce ; l'agence nommée est avertie (`double_banking:<partenaire>:nominated`) |
| Agence que le port ne connaît pas encore | l'agence de l'autre navire — d'un accostage à couple comme d'un transbordement — n'est **ni forcément celle qui annonce, ni forcément déjà enregistrée** : *Son agence n'est pas dans la liste* la nomme (nom, e-mail ; API `agency_name`, `agency_email`, `agency_phone`) ; `calls.partner_agency` l'**enregistre dans le port** avec le seul rôle AGE et la nature *agence maritime / consignataire* (`register_organization`, journal `organization.created`), ou la **retrouve par son nom** — jamais de doublon ; l'escale de l'autre navire est créée sous elle. **Elle seule déclare cette escale** (agent principal) : tant que personne ne peut se connecter pour elle (`calls.agency_has_account`), les **administrateurs fonctionnels du port sont avertis** (`agency_without_account:<organisation>:<escale>`, lien vers sa fiche) et l'agent annonçant le lit sur l'escale créée ; il y garde son accès d'agence associée |
| Annonce refusée | l'annonce s'exécute en **une transaction** (`views._announce` sous `transaction.atomic`, API `POST /calls/` de même) : un refus — règle du registre, question obligatoire sans réponse, IMO déjà pris, e-mail invalide — **n'enregistre rien en chemin** (ni navire nouveau, ni organisation nouvelle, ni escale du partenaire, ni notification) et **le formulaire revient tel qu'il a été saisi**, le motif en tête |
| Garde-fous | l'autre navire est un autre navire ; une seule escale partenaire à la fois (STS ou accostage) ; la position est OUTER ou INNER ; l'agence du navire partenaire est une agence du port ; une escale non visible sur la conférence (brouillon, close) ne peut être désignée par une autre agence (*Escale partenaire introuvable parmi vos escales : la capitainerie lie les escales de deux agences*) |
| Affichage | l'en-tête de l'escale dit *À couple de X (accostage à couple)* ou *Reçoit X à couple* ; l'aperçu porte le bloc *Accostage à couple* (position, autre navire, agence, lien confirmé ou à confirmer) ; les deux dossiers se montrent l'un l'autre une fois le lien réciproque |

### 5.7.3 Transbordement : le partenaire d'une autre agence, le navire-mère (`calls.create_call(linked_call=…)`, `link_partner`, `link_confirmed`, `incoming_links`)

| Règle | Détail |
| --- | --- |
| Trois façons de nommer le partenaire | à l'annonce d'un transbordement (modèle M3 ou zone STS), le bloc *les deux navires* propose : **une escale de l'agence** (`Mes escales`), **une escale d'une autre agence** que la conférence de placement montre en rade ou en zone STS (`views._sts_candidates` : escales actives non brouillon, zone `STS_AREA` / `ANCHORAGE` ou rôle STS renseigné), ou **un navire sans escale** (enregistré ou nouveau) dont l'escale est créée sous son agence (1.5, `_create_sts_partner`) — une agence du port, ou une agence que le port ne connaît pas encore, nommée sur place (§5.7.2, *Agence que le port ne connaît pas encore*). Une escale choisie, les champs *navire* et *agence* du bloc se désactivent : elle a déjà les siens |
| Escale d'une autre agence : nommée, jamais ouverte | l'escale annoncée porte le lien (`linked_call`, `link_kind` STS) ; l'escale désignée n'est pas modifiée ; son **agence, son capitaine et la capitainerie sont avertis aussitôt** (`_notify_partner_link`, clé `sts_link:<annoncée>:<désignée>`) ; l'agence annonçante ne reçoit **aucun accès** au dossier désigné (en-tête sans lien, `404` à l'adresse du dossier) |
| Côtés du transfert | un navire livre, l'autre reçoit : si le rôle de l'escale annoncée est laissé vide, elle prend **l'inverse de celui de l'escale désignée** (`_inverse_sts_role`) ; deux escales du même côté ne se lient pas (*Un navire livre la cargaison et l'autre la reçoit*, `_check_sts_roles`) |
| Lien confirmé (`link_confirmed`) | le lien vaut pour les deux dossiers quand les deux escales sont de la **même agence**, quand l'escale désignée **pointe en retour**, ou quand la capitainerie a **autorisé la configuration** de l'escale annoncée (demande `STS_ZONE` approuvée pour un transbordement, `DOUBLE_BANKING` pour un accostage à couple) ; l'autorisation rend en outre le lien réciproque si l'escale désignée n'a pas encore de partenaire (`complete_reciprocal_link`, qui lui donne le rôle inverse si elle n'en a pas) |
| Rien n'est lu par un lien non confirmé | tant que le lien n'est pas confirmé, le journal de pompage du partenaire **n'est pas rapproché** sur le dossier annoncé (`measurements.counterpart_entries` rend une série vide) et l'aperçu porte *lien à confirmer par l'autorisation de zone et de fenêtre STS de la capitainerie* |
| Navire-mère et navires-filles | une escale peut être désignée par **plusieurs** escales (un navire-mère en zone STS, des navires-filles d'agences différentes ; un navire à quai et plusieurs navires annoncés à couple) : `incoming_links` les liste sur son aperçu (*Autres navires désignant cette escale* : navire, référence, agence, rôle ou position, état, ETA) — jamais un brouillon d'une autre agence, ni une escale annulée, rejetée ou obsolète ; le navire-mère garde un seul `linked_call` (son premier partenaire) ; chaque navire-fille rapproche **son** journal de celui du navire-mère sur son propre dossier |
| Déclaration | l'obligation de nommer le partenaire avant de déclarer (modèles `requires_linked_call`) est satisfaite aussi quand une autre escale déclarée désigne déjà celle-ci |
| Lien après l'annonce | l'action *Relier une escale partenaire* de l'aperçu suit la même règle : escale de l'agence → lien réciproque ; escale d'une autre agence vue sur la conférence → lien à sens unique et notification ; sinon *introuvable* |
| Limite connue | sur le dossier du navire-mère, le rapprochement des journaux de pompage se fait avec son premier partenaire seulement ; celui des autres navires-filles se lit sur leurs dossiers (la capitainerie et l'inspecteur invité sur chacun les voient tous) |
