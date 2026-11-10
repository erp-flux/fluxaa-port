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

*Schéma : statuts d'une escale · 14 statuts, chemin nominal et sorties — dessiné dans FLX-SPEC-003 (onglet principal).*

| De | Vers | Déclenché par | Condition |
| --- | --- | --- | --- |
| DRAFT | DECLARED | AGE, *Déclarer l'escale* | point d'arrêt `DECLARE` (M0:02, 03, 05 faits) ; convoque les parties, crée la demande de feu vert |
| DRAFT, DECLARED, ACCEPTED, PLANNED | CANCELLED | AGE, *Annuler* (motif) | avant tout accostage |
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

`ACTIVE_STATUSES` (tableau de bord, liens de partie valides) = DECLARED … SHIFTING ; `is_terminal_state` = CLOSED, ARCHIVED, REJECTED, CANCELLED. Les ancres de l'escale gardent leur sens sur plusieurs étapes : ATA première arrivée, ATB premier accostage, T0 premier début de transfert, T1 dernière fin, ATD appareillage final ; chaque étape porte en plus ses propres `atb` et `atd`.

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
| `BERTH_ASSIGN` attribuer un poste | décision APO | M0:06, M0:07, M0:09 feu vert (CAP) |
| `MOVEMENT_AUTH` autorisation de mouvement | décision CAP | M0:21 libre pratique (ADM) · M0:22 formalités douanières et d'immigration (ADM) · M5:5.04 rejet des eaux de ballast (CAP, si M5) |
| `PILOT_BOARDING` pilote à bord (arrivée) | jalon SVC | M0:25 autorisation de mouvement (CAP) |
| `BERTHING` amarrage, à couple | jalons SVC / PRE | M0:25 · M3:3.03 zone et fenêtre STS (CAP, si M3) · MA2:A2.02 conditions de houle et courant (CAP, si bouée) |
| `START_TRANSFER` début du transfert | jalons TER / PRE | M0:27 réunion pré-transfert · M0:28 liste de contrôle navire/terre · M0:29 essai d'arrêt d'urgence · M0:31 mise en sécurité du poste (TER) ; selon l'opération : M1:1.04–1.07, M2:2.04–2.09, M3:3.01–3.11, M4:4.01–4.06 (détail dans l'onglet *5. Catalogues*, point d'arrêt `START_TRANSFER`) |
| `DOUBLE_BANKING` accostage à couple | décision | M9:9.02 accord du navire intérieur (NAV) · 9.04 analyse d'amarrage · 9.06 matrice des opérations simultanées · 9.08 plan de déhalage d'urgence (TER) |
| `HOT_WORK` travaux par point chaud | décision CAP | M7:7.04 autorisation (CAP) · 7.05 certificat de dégazage (INS) · 7.06 permis nominatif (NAV) |
| `BL_ISSUE` émission du connaissement | dépôt AGE | M2:2.16 instruction documentaire écrite (COM) + invariants ci-dessous |
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

**Message de refus (O).** Format, en français et en anglais, affiché dans un encadré dédié et renvoyé par l'API (`409 hold_point_refused`, `missing[]`, `reasons[]`) : « Refusé : « *transition* » n'est pas encore possible. Tâche manquante `M0:25` « *intitulé* » — responsable : *rôle* — action attendue : *nature*. » puis les motifs d'invariant. Le même texte est journalisé et devient une alerte bloquante adressée à CAP, AGE et au rôle qui a tenté l'acte.
