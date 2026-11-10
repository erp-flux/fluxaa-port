# 13. Formulaires de saisie

> Chapitre **rédigé** (FLX-SPEC-003, onglet 3), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.


Tous les formulaires par lesquels une personne écrit dans le registre : pour chacun, l'écran qui le porte, l'action serveur, les rôles autorisés, puis champ par champ le nom technique, le libellé français et anglais, le type, l'obligation, les valeurs ou la validation, la source ou la valeur par défaut, et enfin les effets (objets créés, journal, notifications) et les refus possibles.

## 13.1 Conventions des formulaires

| Convention | Règle |
| --- | --- |
| Transport | chaque formulaire est un `POST` avec jeton CSRF ; les actions d'escale vont à `/escales/<id>/action/<action>/` (`views.call_action`), les actions de compte à leur page, les actions de sûreté à `/surete/<réf>/` avec un champ `action` ; les mêmes actes existent dans l'API (`/api/v1/…`, onglet API) avec les mêmes champs en JSON |
| Retour | un champ caché `back` (`?tab=<onglet>#<ancre>` ou chemin absolu) dit où revenir ; sinon la fiche de l'escale ; une adresse externe est ignorée (`back_url`) ; modèle redirection-après-POST : un rechargement ne rejoue jamais l'acte |
| Validation | côté serveur, dans les services (`apps/registry/services/*`), jamais seulement dans le navigateur : l'attribut HTML `required` n'est qu'une aide ; les valeurs inconnues sont ignorées (`validate_form` d'une demande), les chaînes sont tronquées à la longueur du modèle |
| Dates et heures | saisies en `datetime-local` et interprétées dans le fuseau du port (`parse_local`) ; stockées en UTC ; une valeur illisible répond *Date et heure invalides* ; un jalon ne peut être déclaré dans le futur ; `data-default-now` préremplit l'heure courante |
| Nombres | quantités et relevés en `inputmode=decimal`, point ou virgule acceptés, une quantité est un nombre positif ; les montants de cargaison en 3 décimales, l'unité MT / m³ @15 °C / bbl @60 °F |
| Réponses du serveur (`web_action`) | succès → message vert et redirection vers `back` ; `PermissionRefused` ou `RuleViolation` → message rouge, rien n'est écrit ; `HoldPointRefused` → l'encadré de refus (transition tentée, tâches manquantes avec rôle et action attendue, raisons) et une écriture `holdpoint.refused` au journal ; `StrongAuthRequired` → avertissement et renvoi vers la vérification du second facteur avec retour automatique ; objet hors de portée → 404 (jamais 403, règle 4) |
| Idempotence | un acte ne s'applique qu'une fois : contresigner deux fois, signer deux fois, confirmer deux fois est refusé (*votre rôle a déjà …*) ; une tâche close ne se referme pas ; l'appli terrain et l'API portent un `client_uuid` par entrée pour que la synchronisation ne crée pas de doublon |
| Journal | tout acte qui écrit au registre produit une écriture chaînée `journal.record` (action, rôle, rôles lecteurs, résumé FR / EN, charge utile) ; les lectures sensibles produisent une écriture d'audit `journal.audit` (`view`, `download`, `export`, `login`…) ; les actions sont nommées `<objet>.<verbe>` (`call.created`, `milestone.countersigned`, `request.decided`…) et listées dans l'onglet Catalogues |
| Notifications | dérivées de l'acte, jamais saisies : chaque effet « notifie … » ci-dessous crée une `Notification` par personne concernée, envoyée aussitôt (bloquante ou escalade) ou au récapitulatif quotidien selon le compte ; les abonnements webhook reçoivent les actions du journal |
| Double authentification | exigée à la connexion pour CAP, APO, SUR (`FLUXAA_MFA_REQUIRED_ROLES`) et pour tout administrateur ; exigée à nouveau (*step-up*, `FLUXAA_MFA_STEPUP_SECONDS` = 8 h) pour : décider une demande, décider un dossier N4, créer un jeton d'API d'un rôle décideur, modifier le paramétrage ; dans l'API, l'en-tête `X-MFA-Code` tient lieu de step-up |
| Qui agit | le rôle vient de l'organisation de la personne sur l'escale (plusieurs rôles possibles) ; un titulaire de lien tient un seul rôle et agit en son nom (`link.named`) ; l'API peut préciser `role` quand la personne en tient plusieurs |
| Longueurs | nom d'organisation 200, nature 80, téléphone 40, nom de titulaire 160 (3 au moins), motif de non-application / annulation libre mais obligatoire, note de jalon 2 000, question à l'assistant 600, remarques du rapport des faits 4 000, fichier 25 Mo (`FLUXAA_MAX_UPLOAD_MB`), pièce N4 10 Mo |
| Escale close | aucune écriture après la clôture (*The call is closed*), sauf l'archivage ; les lectures restent |

## 13.2 Compte et accès

### Connexion — `POST /compte/connexion/` (`core.LoginView`)

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `username` | Courriel / E-mail | email | oui | identifiant du compte, insensible à la casse | — |
| `password` | Mot de passe / Password | password | oui | vérifié par Django (hachage Argon2 / PBKDF2 selon la configuration) | — |
| `next` | — | hidden | non | chemin de retour, seulement relatif au site (`_safe_next`) | page demandée, sinon `/` |

**Effets** : session ouverte (clé régénérée), écriture d'audit `login` ; un rôle décideur ou un administrateur est envoyé vers `/compte/mfa/verifier/` (ou `/compte/mfa/activer/` s'il n'a pas encore de second facteur) avant toute page. **Refus** : *Courriel ou mot de passe incorrect* (même message pour un compte inactif) ; *Trop de tentatives…* (HTTP 429) au-delà de 10 échecs du compte depuis l'adresse, 30 depuis l'adresse, 50 sur le compte, pendant 15 min (`throttle.LIMITS`).

### Second facteur — activation `POST /compte/mfa/activer/` et vérification `POST /compte/mfa/verifier/`

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `code` | Code à six chiffres / Six-digit code | text `inputmode=numeric` | oui | TOTP RFC 6238, 6 chiffres (espaces tolérés), fenêtre de tolérance d'un pas | application d'authentification |
| `current_code` | Code de l'application actuelle / Code of your current application | text | oui si remplacement | code de l'ancienne application (`mfa.verify_user`) | — |
| `next` | — | hidden | non | retour | `/` |

**Activation** : le secret en attente est généré en session (`mfa_pending_secret`) et montré en QR (`otpauth://`) et en clair ; au bon code, il est chiffré (`FLUXAA_SIGNING_KEY`) et enregistré, la session est marquée vérifiée (`mfa.mark_session`), écriture d'audit `mfa.enabled` ou `mfa.changed`, courriel à la personne (*une nouvelle application vient d'être enregistrée…*). **Vérification** : au bon code, session marquée vérifiée (`mfa_verified_at`, clé régénérée) et retour à `next`. **Refus** : *Le code n'est pas valide* ; 5 codes faux → *Trop de codes incorrects…* (429) pendant 15 min, le bon code compris ; un remplacement sans le code de l'ancienne application est refusé (un mot de passe seul ne suffit jamais à prendre le second facteur).

### Mon compte — `POST /compte/` (`core.profile`)

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `action` | — | hidden | oui | `digest` (préférence de notification), `token` (créer ou remplacer le jeton d'API), `revoke` (révoquer le jeton) | bouton pressé |
| `notify_digest_only` | Récapitulatif quotidien pour les tâches normales / Daily digest for normal tasks | checkbox | non | `on` ; les tâches bloquantes et les escalades partent toujours immédiatement | `User.notify_digest_only` |

**Effets** : `digest` enregistre la préférence ; `token` supprime l'ancien jeton, en crée un nouveau affiché une seule fois, écriture d'audit `api_token.created` ; `revoke` supprime le jeton. **Refus** : un rôle soumis au second facteur sans session forte est renvoyé vers la vérification avant de créer un jeton.

### Langue et déconnexion — `POST /compte/langue/`, `POST /compte/deconnexion/`

| Champ | Type | Valeurs |
| --- | --- | --- |
| `language` | hidden | `fr` ou `en` (boutons FR / EN de la barre) ; mémorisé sur le compte et en cookie |
| `next` | hidden | page courante |

**Effets** : la langue change pour la session et le compte ; la déconnexion ferme la session (POST seulement, jamais par lien).

### Accès par code — `POST /bord/` (`registry.master_entry`) ; par lien — `GET /bord/<jeton>/`

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `code` | Code d'accès / Access code | text, capitales, `XXXX-XXXX` | oui | 8 caractères de l'alphabet sans ambiguïté (`ABCDEFGHJKMNPQRSTUVWXYZ23456789`), tiret et casse ignorés ; comparé par empreinte (`code_hash`) à un `MasterAccessLink` non révoqué et non expiré | remis par l'agence (QR, impression, SMS…) |
| jeton (dans l'adresse) | — | 43 caractères `token_urlsafe(32)` | — | comparé par empreinte (`token_hash`) | courriel ou QR |

**Effets** : session de lien (`fluxaa_master_link_id`, clé régénérée), écriture d'audit `master.access` avec `last_used_at` ; redirection vers la fiche de l'escale, ou vers `/bord/nom/` si le lien n'a pas encore de titulaire nommé. **Refus** : *Ce code n'est pas valide, a expiré ou a été révoqué…* (écriture `master.denied`) ; 10 codes faux depuis une adresse → *Trop de tentatives…* (429) 15 min.

### Nom du titulaire — `POST /bord/nom/` (`registry.link_name`)

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `name` | Votre nom complet / Your full name | text | oui | 3 à 160 caractères, espaces réduits | — |

**Effets** : `MasterAccessLink.master_name` renseigné une fois pour toutes, écriture d'audit `link.named` ; tout acte du titulaire porte ensuite ce nom (signatures, contresignatures, dépôts). **Refus** : *Indiquez votre nom complet*. Un lien déjà nommé ne repasse pas par cette page.

### Quitter — `POST /bord/sortie/`

Sans champ. **Effets** : la session de lien est fermée, en-tête `Clear-Site-Data: "cache"` pour purger les données hors ligne de l'appli terrain ; retour à `/bord/?sortie=1`.

## 13.3 Escale : annonce, déclaration, heures, annulation, parties, accès, étapes, escale partenaire

### Annonce d'escale — `POST /escales/nouvelle/` (`views.call_create` → `calls.create_call`) — AGE

| Champ | Libellé FR / EN | Type | Obligatoire | Valeurs, validation | Source / défaut |
| --- | --- | --- | --- | --- | --- |
| `vessel` | Navire enregistré / Registered vessel | select | oui, sauf nouveau navire | `Vessel` du port | — |
| `new_imo` | IMO | text `[0-9]{7}` | si nouveau navire | 7 chiffres, unique dans le port | — |
| `new_name` | Nom / Name | text | si nouveau navire | mis en capitales | — |
| `new_flag`, `new_type`, `new_dwt` | Pavillon, Type, DWT / Flag, Type, DWT | text, text, number ≥ 0 | non | `Vessel.full_clean()` | — |
| `kind` | Zone d'opération / Operating area | radio | oui | `JETTY` quai / appontement, `ANCHORAGE` rade, `SPM` bouée au large, `STS_AREA` zone STS (`Berth.Kind`) | — |
| `requested_berth` | Poste ou zone demandé / Requested berth or area | select | non | `Berth` actif du port, de la nature `kind` | — |
| `operations` | Opérations / Operations | cases | au moins une en pratique | codes des gabarits actifs de nature OPERATION (M1…M8) | — |
| `modules` | Modules complémentaires / Additional modules | cases | non | gabarits de nature MODULE (M9, MA2, MA3…) ; MA2 ajouté d'office pour SPM, MA3 pour rade et zone STS | — |
| `linked_call` | Escale partenaire / Partner call | select | non | escale en cours de la même agence ; lien `STS` | — |
| `eta` | ETA | datetime-local | oui | heure du port | — |
| `etb`, `ets`, `etc`, `etd` | ETB, Début / Fin des opérations (est.), ETD | datetime-local | non | heure du port | — |
| `product` | Produit / Product | text | non | libre (ex. *Gasoil 10 ppm*) | — |
| `quantity`, `quantity_unit` | Quantité déclarée, Unité / Declared quantity, Unit | number (3 décimales), select | non | `MT`, `M3`, `BBL` | `MT` |
| `voyage`, `last_port`, `next_port` | Voyage, Dernier port, Prochain port | text | non | libres | — |
| `party_role[]` | Rôle / Role | select, une par ligne | — | `TER`, `INS`, `COM`, `PRE`, `SVC` (`AGENCY_INVITABLE_ROLES`) | trois lignes TER, INS, PRE |
| `party_org[]` | Organisation enregistrée / Registered organisation | select | — | id d'une `Organization` active du port portant le rôle, `new` = nouvelle, vide = ligne ignorée | — |
| `party_name[]` | Nouvelle organisation : nom / New organisation: name | text ≤ 200 | si `new` | ≥ 2 caractères après réduction des espaces ; un nom existant (sans casse) réutilise l'organisation si elle porte le rôle | — |
| `party_kind[]` | Nature (suggérée ou libre) / Kind | text ≤ 80, datalist `kinds-<rôle>` | non | `normalize_kind` : libellé FR ou EN connu → code `PARTY_KINDS`, sinon conservé | — |
| `party_email[]`, `party_phone[]` | Courriel, Téléphone / E-mail, Phone | email, text ≤ 40 | non | courriel en minuscules | — |
| `party_<ROLE>` | (anciens champs) | hidden | non | un id d'organisation par rôle, encore accepté | — |

**Effets** : `PortCall` en brouillon (`DRAFT`) avec la référence `<PORT>-<année>-<nnnn>`, les gabarits pris à leur version publiée (`CallTemplateUse`), l'étape 1 (`CallStage`), les parties (AGE, parties par défaut du port, parties nommées), toutes les tâches instanciées (`instantiate_tasks`), les organisations nouvelles créées (`organization.created`), le lien réciproque sur l'escale partenaire ; journal `call.created` ; les tâches `auto_event=call.created` sont closes par la plateforme ; message *Escale \<réf> créée en brouillon…*. **Refus** : *Seule une agence maritime peut créer une escale* ; *Choisissez un navire ou enregistrez-en un nouveau* ; *Ce navire n'est pas enregistré dans ce port* ; *Le poste demandé ne correspond pas à la zone d'opération* ; *L'escale partenaire appartient à un autre port* ; *Escale partenaire introuvable parmi vos escales…* ; *Nommez l'organisation que vous invitez* ; *… est enregistrée dans le port sans le rôle …* ; *… existe mais est inactive* ; combinaison de gabarits invalide (`_check_templates`).

### Déclarer l'escale — `declare` (`calls.declare_call`) — AGE

Sans champ (confirmation). **Préalables** (point d'arrêt `DECLARE`) : jeu de données du navire M0:02, certificats du capitaine M0:03, contrôle des sanctions M0:05 ; une escale STS ou à couple doit déjà être reliée. **Effets** : statut `DECLARED` ; création et soumission de la demande `GREEN_LIGHT` au nom de l'agence ; toutes les parties notifiées (`declared:<id>`) ; les demandes déposées pendant le brouillon atteignent leur autorité ; **convocation** : chaque partie TER / INS / COM / PRE / SVC sans compte reçoit un lien d'accès (`party_link.issued`, `auto`), envoyé à son courriel quand elle en a un. **Refus** : *Seule l'agence déclare l'escale* ; *Seule une escale en brouillon peut être déclarée* ; *STS et accostage à couple relient deux navires : indiquez l'escale partenaire…* ; refus de point d'arrêt avec les tâches manquantes.

### Réviser les heures — `estimates` (`calls.update_estimates`) — AGE (ETB : APO une fois le poste attribué)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `eta`, `etb`, `ets`, `etc`, `etd` | ETA, ETB, Début des opérations, Fin, ETD | datetime-local | ETA ne peut être vidée | heure du port ; un champ vide ne change rien (`ESTIMATE_FIELDS`) | valeurs courantes |
| `reason` | Motif / Reason | text | non | libre | — |

**Effets** : les estimations sont mises à jour, chaque échéance relative est recalculée en cascade (`recompute_deadlines`, sans notification à la baisse) ; journal `call.estimates_revised` ; parties notifiées. **Refus** : *L'escale est close* ; *ETA est obligatoire* ; *ETB est saisie par Autorité portuaire seulement (émetteur unique)* après attribution du poste.

### Annuler l'escale — `cancel` (`calls.cancel_call`) — AGE

| `reason` | Motif / Reason | text | oui | libre |
| --- | --- | --- | --- | --- |

**Effets** : statut `CANCELLED` (depuis brouillon, déclarée, acceptée ou planifiée seulement, `CALL_TRANSITIONS`) ; journal `call.status` avec le motif ; toutes les parties notifiées. **Refus** : *Seule l'agence peut annuler son escale* ; *Un motif est requis* ; transition interdite (*de … vers …*) au-delà de l'approche.

### Demander la clôture, clore, archiver — `close_request` (AGE), `close` (CAP), `archive` (CAP)

Sans champ. **`close_request`** (`confirm_closure`, tâche M0:39 côté agence) : après le départ seulement ; journal `call.closure_requested`, capitainerie notifiée. **`close`** (`close_call`, point d'arrêt `CLOSE`) : exige la demande de l'agence, aucune contestation ouverte, le rapport des faits signé, les mesures complètes et les tâches bloquantes de clôture ; statut `CLOSED`, plus aucune écriture ensuite. **`archive`** (`archive_call`) : `CLOSED` → `ARCHIVED`. **Refus** : *Seule l'agence confirme la demande de clôture* ; *L'escale ne peut être close qu'après le départ* ; *L'agence n'a pas encore demandé la clôture* ; *Seule la capitainerie clot une escale* ; refus de point d'arrêt (contestation ouverte, mesure incomplète, rapport non signé).

### Relier une escale partenaire — `link` (`calls.link_partner`) — AGE (ses escales), CAP (deux agences)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation |
| --- | --- | --- | --- | --- |
| `partner` | Référence de l'escale partenaire / Reference of the partner call | text | oui | référence (capitales) ou identifiant d'une escale du même port, différente de celle-ci ; introuvable → 404 |
| `link_kind` | Lien / Link | select | oui | `STS`, `OUTER` (ce navire à l'extérieur), `INNER` (à l'intérieur) ; le lien réciproque est posé sur l'autre escale (`RECIPROCAL_LINK`) |

**Effets** : `linked_call` et `link_kind` sur les deux escales, écriture au journal de chacune (`call.linked`). **Refus** : *L'escale partenaire est indiquée par l'agence* (ou par la capitainerie pour deux agences) ; *Choisissez une autre escale du même port* ; *Lien inconnu* ; escale close.

### Inviter une partie — `party_add` (`calls.register_organization` + `calls.add_party`) — AGE (TER, INS, COM, PRE, SVC), CAP (tout rôle)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation |
| --- | --- | --- | --- | --- |
| `role` | Rôle / Role | select | oui | rôles invitables par l'acteur |
| `organization` | Organisation enregistrée / Registered organisation | select | oui ou `new` | id d'une organisation active du port portant le rôle (`allowed_roles`), ou `new` |
| `party_name`, `party_kind`, `party_email`, `party_phone` | Nouvelle organisation : nom, nature, courriel, téléphone | text, text (datalist), email, text | nom si `new` | mêmes règles qu'à l'annonce |

**Effets** : organisation créée le cas échéant (`organization.created`) ; `CallParty` (réutilisé s'il existe déjà actif) ; journal `party.granted` ; si l'escale n'est plus en brouillon : notification *Vous êtes invité sur l'escale…* et convocation (lien d'accès émis pour une partie sans compte) ; les ordres de service en attente de prestataire lui sont attribués s'il est seul de son rôle (`assign_pending_providers`). **Refus** : *L'escale est close* ; *Cette organisation n'est pas active dans ce port* ; *… n'est pas habilitée au rôle …* ; *L'agence n'invite que les terminaux, inspecteurs, armateurs / affréteurs, prestataires et services nautiques* ; *Nommez l'organisation que vous invitez*.

### Désigner pour la terre, révoquer un rôle — `party_shore`, `party_revoke` — AGE, CAP

| Champ | Type | Obligatoire | Valeurs |
| --- | --- | --- | --- |
| `party_id` | hidden | oui | `CallParty` de l'escale |
| `reason` (révocation) | text | oui | libre |

**`party_shore`** (`designate_shore_side`) : la partie TER ou PRE désignée enregistre les jalons et le chiffre côté terre et contresigne pour la terre ; journal `party.shore_side`. **`party_revoke`** (`revoke_party`) : `revoked_at`, `revoke_reason` ; l'accès cesse aussitôt, les saisies restent ; les liens d'accès de l'organisation sur l'escale sont révoqués ; journal `party.revoked`. **Refus** : *L'agence ou la capitainerie désigne le côté terre* ; *Seul un terminal ou un prestataire actif de l'escale peut parler pour la terre* ; *Un motif est requis* ; *Ce rôle n'est pas actif sur l'escale* ; *Seule la capitainerie peut révoquer ce rôle* (partie par défaut du port, ou rôle non invitable par l'agence).

### Accès du capitaine — `master_link` (`calls.issue_master_link`) — AGE

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `master_name` | Nom du capitaine / Master's name | text | oui | la signature est nominative | — |
| `channel` | Remis par / Handed over by | select | oui | `EMAIL`, `QR`, `PRINT`, `SMS`, `OTHER` | `EMAIL` |
| `vessel_position` | Navire / Vessel | select | oui | `OWN` ce navire, `INNER` navire intérieur (accostage à couple) | `OWN` |
| `note` | Note de remise / Delivery note | text | non | libre | — |

**Effets** : `MasterAccessLink` rôle NAV (jeton et code stockés par empreinte), expiration = ETD + `master_link_grace_hours` du port, plafonnée à `master_link_max_days` ; lien, code et QR affichés **une seule fois** (session `fluxaa_new_master_link`) ; journal `master_link.issued` (AGE, CAP). **Refus** : *Le lien d'accès est émis par l'agence* ; *Le nom du capitaine est requis…* ; *L'escale est close* ; *L'expiration doit être dans le futur*.

### Accès d'une partie sans compte — `party_link` (`calls.issue_party_link`) — AGE, CAP

| Champ | Libellé | Type | Obligatoire | Valeurs |
| --- | --- | --- | --- | --- |
| `party_id` | Partie / Party | select | oui | `CallParty` actif de rôle TER, INS, COM, PRE ou SVC (`LINK_ROLES`) |
| `holder_name` | Nom du titulaire (facultatif : demandé au premier usage) / Holder's name | text ≤ 160 | non | vide → `/bord/nom/` au premier usage |
| `channel`, `note` | Remis par, Note | select, text | oui, non | comme ci-dessus |

**Effets** : lien de rôle `<rôle>` pour l'organisation, valable jusqu'à la clôture au plus tard `party_link_max_days` ; affiché une fois ; journal `party_link.issued` (AGE, CAP, le rôle). **Refus** : *Le lien d'accès d'une partie est émis par l'agence ou la capitainerie* ; *Ce rôle n'est pas actif sur l'escale* ; *Le rôle … décide ou conduit l'escale : il lui faut un compte, pas un lien* (CAP, APO, ADM, SUR, DIR).

### Révoquer un accès — `master_revoke`, `link_revoke` (`calls.revoke_master_link`) — AGE, CAP

| `link_id` | hidden | oui | `MasterAccessLink` de l'escale | `reason` facultatif (défaut —) |
| --- | --- | --- | --- | --- |

**Effets** : `revoked_at` ; la session du titulaire est refusée à sa prochaine requête ; journal `master_link.revoked`. **Refus** : *Seule l'agence ou la capitainerie peut révoquer cet accès*.

### Planifier ou annuler une étape — `stage_add`, `stage_cancel` (`stages.add_stage`, `stages.cancel_stage`) — AGE, CAP

| Champ | Libellé | Type | Obligatoire | Valeurs, validation |
| --- | --- | --- | --- | --- |
| `berth_kind` | Zone d'opération / Operating area | select | oui | `Berth.Kind` |
| `berth` | Poste / zone (facultatif, attribué par le port) | select | non | poste actif de la nature choisie |
| `operations` | Opérations à cette étape / Operations at this stage | cases | non | gabarits OPERATION actifs |
| `planned_from`, `planned_to` | Prévu du / au | datetime-local | non | fin après début |
| `reason` | Motif / Reason | text ≤ 300 | non (obligatoire pour annuler) | libre |
| `stage_id` (annulation) | hidden | oui | étape `PLANNED` de l'escale |  |

**Effets** : `CallStage` suivant (ordre n+1, `PLANNED`), ses tâches créées aussitôt pour toutes les parties (`instantiate_tasks`, lignes nouvelles seulement), journal `call.stage_planned`, parties notifiées ; l'annulation marque l'étape `CANCELLED` avec motif (jamais supprimée, ses tâches restent et peuvent être déclarées sans objet), journal `call.stage_cancelled`. **Refus** : *Les étapes d'une escale sont planifiées par l'agence ou la capitainerie* ; *L'escale est close ou le navire est parti* ; *Zone d'opération inconnue* ; *Le poste demandé ne correspond pas à la zone* ; *La fin de la fenêtre doit suivre son début* ; *Seule une étape planifiée peut être annulée* ; *Un motif est requis*.

## 13.4 Tâches et jalons

### Marquer une tâche faite ou décidée — `task_complete` (`tasks.complete_task`) — le rôle de la tâche (ou `ANY`)

| Champ | Libellé | Type | Obligatoire | Valeurs |
| --- | --- | --- | --- | --- |
| `task_id` | — | hidden | oui | tâche de l'escale visible du rôle |
| `note` | Note (facultatif) / Note (optional) | text | non | libre, gardée comme `completion_note` |

**Effets** : tâche `DONE` avec l'heure, le rôle et la personne (`completed_by`, nom du titulaire de lien le cas échéant) ; journal `task.completed` ; l'alerte en cours s'éteint ; un point d'arrêt qui l'attendait s'ouvre. **Refus** : *Cette tâche n'est pas affectée à votre rôle* ; *Cette tâche est déjà close* ; *L'escale est close* ; *Les armateurs et affréteurs n'ont pas de droit de saisie…* (COM fournit des documents) ; *Cette tâche exige la signature de chaque partie : utilisez « Signer »* ; *Cette tâche se réalise par sa demande (…)* ; *… par l'enregistrement de ses jalons* ; *… en fournissant le document attendu* — une tâche liée à un objet ne se clot que par cet objet.

### Signer une tâche conjointe — `task_sign` (`tasks.sign_task`) — chaque rôle signataire (rôle + cosignataires)

| `task_id` | hidden | oui | tâche `joint=True` | `note` : commentaire facultatif |
| --- | --- | --- | --- | --- |

**Effets** : `TaskSignature` (`SIGNED`, nominative) ; journal `task.signed` ; quand tous les rôles ont signé, la tâche passe `DONE` et le jalon système associé est enregistré (ex. liste de contrôle navire / terre signée). **Refus** : *Cette tâche est déjà close* ; *Votre rôle a déjà signé cette tâche* ; COM ne signe pas.

### Déclarer une tâche sans objet — `task_na` (`tasks.mark_not_applicable`) — rôles de `na_roles`

| `task_id` | hidden | oui |  | `reason` | Motif (obligatoire, tracé) / Reason | text | oui |
| --- | --- | --- | --- | --- | --- | --- | --- |

**Qui** : pour une décision, une demande ou une tâche attendue par un point d'arrêt, seul le rôle affecté (jamais un corôle ni le demandeur) ; pour une tâche conjointe, seule la capitainerie avec second facteur ; sinon le rôle, ses corôles et la capitainerie. **Effets** : statut `NA`, `na_reason`, journal `task.not_applicable`. **Refus** : *Un motif est requis* ; *Cette tâche est déjà close* ; *Cette tâche ne peut être déclarée sans objet* ; escale close.

### Contresigner ou contester une tâche — `task_countersign` (`tasks.countersign_task`) — corôle d'une tâche faite (API `POST …/tasks/<id>/countersign/`, non exposé dans la fiche)

| `task_id` | `contest` = `1` pour contester | `comment` (obligatoire pour une contestation) |
| --- | --- | --- |

**Effets** : `TaskSignature` `COUNTERSIGNED` ou `CONTESTED`, journal `task.countersigned`. **Refus** : *Les tâches conjointes se signent, ne se contresignent pas* ; *Seule une tâche faite peut être contresignée* ; *Votre rôle a déjà répondu*.

### Ajouter une tâche ad hoc — `task_adhoc` (`tasks.create_ad_hoc_task`) — AGE, CAP

| Champ | Libellé | Type | Obligatoire | Valeurs |
| --- | --- | --- | --- | --- |
| `title_fr`, `title_en` | Tâche (français), Tâche (anglais) | text | FR oui | libres |
| `role` | Rôle / Role | select | oui | AGE, NAV, TER, CAP, APO, SVC, ADM, SUR, INS, PRE |
| `anchor` | Ancrage / Anchor | select | non | vide, ETA, ETB, ATB, T0, T1, ATD |
| `offset_hours` | Décalage (heures, négatif = avant) / Offset | number | non | entier, converti en minutes |

**Effets** : tâche `template_code=""` marquée ad hoc, nature C, jamais bloquante, échéance calculée si l'ancrage est connu ; journal `task.ad_hoc` ; elle apparaît aussitôt dans les tâches du rôle et ses rappels suivent les règles ordinaires. **Refus** : *Ancrage inconnu*.

### Enregistrer un jalon — `milestone` (`milestones.record_milestone`) — rôle émetteur du type ; types d'origine : TER, NAV, PRE, SVC, CAP, INS, AGE

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `type` | Jalon / Milestone | select | oui | code d'un `MilestoneType` actif du port, émis par le rôle (jamais un type SYSTEM) | — |
| `declared_at` | Heure déclarée (heure du port) / Declared time | datetime-local | oui | pas dans le futur (tolérance 5 min) | maintenant |
| `cause` | Cause — pour une interruption / Cause | select | si `INTERRUPTION_START` | code d'une `InterruptionCause` active (liste fermée) | — |
| `cause_reason` | Motif (obligatoire pour « Autre ») / Reason | text | si la cause l'exige | libre | — |
| `related_id` | Interruption que ce jalon termine / Interruption that ends | select | si `INTERRUPTION_END` | arrêt ouvert de l'escale, enregistré par la même partie | — |
| `note` | Note | text ≤ 2 000 | non | libre | — |
| `paper` | Ressaisie depuis la procédure papier / Re-entry from the paper fallback | checkbox | non | `1` → source `PAPER`, marquée différée | `ONLINE` |
| (API) `rectifies_id`, `rectification_reason` | Rectifie le jalon, Motif | int, text | pour une rectification | même type, même émetteur, motif obligatoire | — |
| (API) `client_uuid`, `device_recorded_at`, `role`, `photo` | — | — | non | idempotence de la synchronisation, heure de l'appareil, rôle choisi, photo jointe | — |

**Effets** : `Milestone` scellé (`seal`) avec `declared_at`, `recorded_at`, source, `deferred` (synchronisé après le seuil ou déclaré plus de `FLUXAA_LATE_ENTRY_SECONDS` = 30 min avant son enregistrement) ; journal `milestone.recorded` (indicateurs *saisie différée*, *rectification*, *saisie concurrente*) ; contresignatures attendues créées pour les rôles du type, contresignataires notifiés ; effets du type : ancre de l'escale (`sets_anchor` ATA, NOR, ATB, T0, T1, ATD), avancement du statut (`sets_status` le long de la chaîne opérationnelle), tâches closes (`completes_tasks`), changement d'étape (`stages.on_milestone`) ; un type gardé par un point d'arrêt est évalué à l'heure déclarée — une autorisation en vigueur alors mais échue à l'enregistrement laisse passer le jalon marqué différé et crée une alerte à la capitainerie et à l'agence ; une **saisie concurrente** (même type, même étape, autre partie) ne remplace rien : le jalon est marqué `is_conflict` et une contestation est ouverte d'office (`auto`) entre les deux émetteurs. **Refus** : *L'escale est close* ; *Ce jalon est enregistré par la plateforme* ; *Une autre organisation parle pour la terre sur cette escale…* ; *Un jalon ne peut être déclaré dans le futur* ; *Une interruption exige une cause de la liste fermée* ; *La cause « … » exige un motif* ; *Indiquez l'interruption qui se termine* ; *Cette interruption est déjà close* ; *La fin ne peut précéder le début* ; *La fin d'une interruption est enregistrée par la partie qui en a enregistré le début* ; *« … » est enregistré par … seulement (émetteur unique)* ; refus de point d'arrêt (tâche manquante nommée, écriture `holdpoint.refused`).

### Contresigner ou contester un jalon — `countersign` (`milestones.countersign_milestone`) — rôles contresignataires et contestataires du type

| Champ | Libellé | Type | Obligatoire | Valeurs |
| --- | --- | --- | --- | --- |
| `milestone_id` | — | hidden | oui | jalon visible de l'escale |
| `contest` | — | hidden | non | `1` = contestation |
| `comment` | Motifs (obligatoire) / Grounds (mandatory) | textarea | si contestation | libre |

**Effets** : `MilestoneSignature` `COUNTERSIGNED` ou `CONTESTED`, nominative ; journal `milestone.countersigned` ; une contestation ouvre une `Dispute` rattachée au jalon avec l'émetteur pour contrepartie ; le silence au-delà de `countersign_delay_minutes` du port devient `TACIT` par le planificateur (`milestone.tacit`, jamais un accord). **Refus** : *Une contestation expose ses motifs* ; *Une autre organisation parle pour la terre…* ; *Votre rôle a déjà contresigné / contesté ce jalon* ; l'émetteur ne contresigne pas son propre jalon.

### Rectifier un jalon — API seulement (`POST …/milestones/` avec `rectifies_id`)

Un jalon ne se modifie pas : la rectification est un nouveau jalon du même type, par le même émetteur, avec un motif, lié à l'ancien (`is_rectification`) ; les deux restent visibles et figurent sur le rapport des faits ; les contresignataires sont sollicités à nouveau. **Refus** : *Une rectification concerne un jalon du même type* ; *Seul l'émetteur d'un jalon peut le rectifier* ; *Une rectification exige un motif*.

## 13.5 Demandes et décisions

### Nouvelle demande — `request_create` (`requests.create_request` puis `submit_request`) — rôles demandeurs du type

| Champ | Libellé | Type | Obligatoire | Valeurs, validation |
| --- | --- | --- | --- | --- |
| `type` | Type / Type | hidden (choisi par `?type=` dans la colonne latérale) | oui | code d'un `RequestType` actif du port dont `requester_roles` ∩ rôles de la personne |
| un champ par entrée de `form_schema` | `label_fr` / `label_en` du schéma | selon `type` : `text` (texte), `textarea`, `select` (options du schéma), `datetime` (datetime-local, heure du port), `number` / `integer`, `boolean` (case) | `required` du schéma | `validate_form` : obligatoires présents, nombres et dates valides, choix parmi les options ; les clés inconnues sont ignorées |
| `provider` | Prestataire qui exécute la prestation / Provider | select | si plusieurs organisations tiennent le rôle exécutant | `Organization` partie à l'escale avec `executor_role` ; un seul candidat → attribué d'office ; aucun → nommé plus tard |

**Effets** : `ServiceRequest` `<référence>-Rnn`, confidentialité du type, données validées, `CREATED` puis `SUBMITTED` (journal `request.created`, `request.submitted`) ; les autorités décideuses — ou, pour un ordre de service sans décideur, le prestataire — sont notifiées (`notify_submission`) ; sur un brouillon, la notification attend la déclaration ; la tâche liée au type (`request_type_code`, côté demandeur) est close par la soumission. **Refus** : type inconnu → 404 ; *Le champ « … » est obligatoire* ; *… doit être un nombre* ; *… doit être une date et une heure* ; *Choix invalide pour « … »* ; *Choisissez le prestataire parmi les organisations participant à l'escale* ; escale close.

Les types de demande livrés (feu vert, poste, mouvement, libre pratique, formalités, services nautiques, soutage, déballastage, dégazage, travaux à chaud, immobilisation, STS, accostage à couple, collecte des déchets, relève d'équipage…) et leurs schémas sont dans l'onglet *Catalogues* ; chaque type décidé a son acte écrit `AUTH_<TYPE>` dans l'onglet *Formulaires standards*.

### Prendre en instruction — `request_review` (`requests.take_under_review`) — rôles décideurs

`request_id` seulement. **Effets** : `SUBMITTED` → `UNDER_REVIEW`, journal `request.under_review`. **Refus** : *Le rôle demandeur ne peut instruire sa propre demande (règle 2)* ; transition interdite.

### Décider — `request_decide` (`requests.decide_request`) — rôles décideurs du type, session forte exigée

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `request_id` | — | hidden | oui | demande `SUBMITTED` ou `UNDER_REVIEW` visible | — |
| `decision` | Décision / Decision | select | oui | `APPROVED`, `APPROVED_COND`, `INFO_REQUIRED`, `REFUSED` | — |
| `berth` | Poste ou zone attribué / Berth or area assigned | select | si le type attribue un poste (`assigns_berth`) | poste actif de la nature de l'escale ou d'une étape planifiée | — |
| `valid_from` | Effet / Effective from | datetime-local | non | heure du port | maintenant |
| `valid_until` | Valide jusqu'au / Valid until | datetime-local | non | après `valid_from` | `valid_from` + `validity_hours` du type |
| `conditions` | Conditions | text | si `APPROVED_COND` | libre | — |
| `reason` | Motif (obligatoire pour un refus ou un complément) / Reason | textarea | si `REFUSED` ou `INFO_REQUIRED` | libre ; pour un contrôle d'acceptabilité ou un type à motif N3, le motif d'un refus n'est lisible que de l'agence, de l'armateur et du service instructeur et ne figure pas dans la charge utile du journal | — |

**Effets** : statut de la demande, `decision_role` / `decision_org` / `decision_user` / `decided_at`, journal `request.decided` ; en cas d'approbation : **`Authorization`** numérotée `AUT-<PORT>-<année>-<nnnnnn>`, scellée, avec `verification_code` public, validité, conditions, poste ; le poste attribué va à l'étape concernée (`stages.assign_berth`) et à l'escale ; statut d'escale avancé si le type le prévoit (`approval_status`, ex. feu vert → `ACCEPTED`, poste → `PLANNED`) ; jalon système enregistré si le type le prévoit (`approval_milestone`) ; tâches closes (`decision_completes`) ; un refus peut faire passer l'escale à `REJECTED` (`refusal_status`) ; **l'acte écrit de la décision** (`AUTH_<TYPE>`, approbation ou refus) est généré et déposé aussitôt dans les documents de l'escale sous le rôle décideur (`file_decision_act` → `forms.auto_issue`), avec la confidentialité de la demande et ses lecteurs (le demandeur lit toujours l'acte de sa demande), le code de vérification et son QR pour une approbation, jamais le motif d'un refus restreint ; demandeur, agence (et armateur pour un vetting) notifiés ; les points d'arrêt `GREEN_LIGHT` et `BERTH_ASSIGN` sont vérifiés avant d'approuver. **Refus** : `StrongAuthRequired` → renvoi vers le second facteur ; *Décision inconnue* ; *Le rôle ou la personne demandeur ne peut jamais décider sur sa propre demande (règle 2)* ; *Cette demande n'attend pas de décision* ; *Un refus ou une demande de complément expose son motif* ; *Une approbation sous conditions énonce les conditions* ; *L'expiration doit suivre la date d'effet* ; *Sélectionnez le poste ou la zone attribué* ; *Le poste attribué ne correspond pas à la zone d'opération de l'escale ni d'une étape planifiée* ; refus de point d'arrêt. Une défaillance de la génération de l'acte ne bloque jamais la décision : elle est journalisée côté serveur et l'autorité émet l'acte à la main depuis la page Formulaires.

### Confirmer la prestation — `request_schedule`, `request_execute` (`requests.schedule_request`, `execute_request`) — rôle exécutant (le prestataire désigné)

| Champ | Libellé | Type | Obligatoire | Valeurs | Défaut |
| --- | --- | --- | --- | --- | --- |
| `request_id` | — | hidden | oui | ordre de service visible | — |
| `scheduled_for` | Prévu pour / Scheduled for | datetime-local | oui (programmation) | heure du port | maintenant |
| `note` | Note | text | non (exécution) | libre | — |

**Effets** : `SCHEDULED` (journal `request.scheduled`) puis `EXECUTED` (`request.executed`, `executed_at`, `executed_by`) ; un ordre sans autorité décideuse se programme dès `SUBMITTED`, un ordre décidé seulement après approbation ; tâches closes par la programmation (`decision_completes`) et par l'exécution (`execution_completes`). **Refus** : *Cet ordre de service est exécuté par un autre prestataire* ; *Cette demande n'attend pas…* ; transition interdite.

### Nommer le prestataire — `request_provider` (`requests.assign_provider`) — la partie demandeuse

| `request_id` | hidden | oui |  | `provider` | Prestataire / Provider | select | oui | organisation candidate (`provider_candidates`) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |

**Effets** : `provider_org` ; le prestataire est notifié (`notify_submission`). **Refus** : *Cette demande n'est pas exécutée par un prestataire* ; *Seule la partie demandeuse nomme le prestataire* ; *Le prestataire de cet ordre ne peut plus être choisi* ; *Choisissez le prestataire parmi les organisations participant à l'escale*.

### Soumettre à nouveau, annuler — `request_submit`, `request_cancel` — la partie demandeuse

| `request_id` | hidden | oui |  | `reason` (annulation) | Motif | text | oui |
| --- | --- | --- | --- | --- | --- | --- | --- |

**Effets** : `INFO_REQUIRED` → `SUBMITTED` (journal `request.submitted`, autorité notifiée) ; `CREATED` / `SUBMITTED` / `INFO_REQUIRED` → `CANCELLED` (journal `request.cancelled`). **Refus** : *Seule la partie demandeuse soumet / annule la demande* ; *Un motif est requis* ; transition interdite (une demande décidée ne s'annule pas : l'autorité annule l'autorisation, `cancel_authorization`, motif obligatoire, journal `authorization.cancelled`).

### Expiration — planificateur (`requests.expire_authorizations`)

Sans formulaire : une autorisation échue passe la demande à `EXPIRED` (journal `authorization.expired`), demandeur et agence alertés ; l'état affiché (*valide*, *expirée*, *annulée*, *pas encore en vigueur*) est toujours recalculé à l'instant.

## 13.6 Documents, mesures et journal de pompage

### Déposer un document — `document_upload` (`documents.upload_document`) — rôles émetteurs du type (`DocumentType.issuer_roles`, sinon tout rôle ayant « C » sur document)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `task_id` | Pour la tâche / For the task | select | non | tâches `PENDING` de l'escale attendant un document (`document_type_code`) dont le rôle ou un co-rôle est tenu par la personne ; présélection par `?task=` depuis l'onglet Tâches | — |
| `type` | Type / Type | select | oui | `DocumentType` actif du port, non généré, dont `issuer_roles` ∩ rôles de la personne ; présélection par `?type=` ; une tâche désignée exige exactement le type qu'elle attend | — |
| `title` | Titre (facultatif) / Title | text | non | libre | libellé du type |
| `confidentiality` | Confidentialité | select | non | *défaut du type*, `N1` toutes parties, `N2` restreint, `N3` bilatéral ; `N4` jamais (espace sûreté) | `default_confidentiality` du type |
| `counterpart_role` | Contrepartie (N3) / Counterpart | select | si `N3` | AGE, NAV, TER, COM, INS, CAP ; à défaut, premier `audience_roles` du type | — |
| `file` | Fichier / File | file | oui | extensions `.pdf .png .jpg .jpeg .webp .heic .tif .tiff .doc .docx .xls .xlsx .csv .txt .eml .msg .html .xml .json .zip` ; taille ≤ `FLUXAA_MAX_UPLOAD_MB` (25 Mo) ; non vide ; type MIME reconnu sur les premiers octets pour PDF, PNG, JPEG, WebP (un fichier qui prétend l'être sans l'être est stocké en octets bruts, téléchargement seulement) | — |
| `previous_id` | *Nouvelle version* (bouton du document) | hidden | non | document `ISSUED` ou `SIGNED` de la même escale et du même type, non généré, dont la personne est l'émetteur | — |

**Effets** : `Document` en statut `ISSUED`, version 1 (ou version du précédent + 1, le précédent passant `REPLACED`), empreinte SHA-256, taille, type MIME, `issuer_role` / `issuer_org` / `issuer_user` ou `issuer_master`, `required_signers` = `signer_roles` du type, lecteurs N2 (`audience_roles` du type et du document), `retention_until` = aujourd'hui + `retention_years` du type ; journal `document.issued` (visible des lecteurs du document) ; la tâche désignée — ou l'unique tâche en attente de ce type pour le rôle émetteur — est close par le dépôt (`system_complete`, preuve `document:<id>`) ; si le type exige des signatures, la tâche attend la dernière signature et les signataires sont notifiés (clé `document:<id>:sign`). Un type `is_bill_of_lading` passe par le verrou `BL_ISSUE` (`holdpoints.check`) : refus `LockRefused` journalisé `holdpoint.refused`. Depuis l'application de terrain, le dépôt porte `client_uuid` (idempotent) et `deferred` (saisie différée). **Refus** : *Choisissez un fichier* ; *Type de document inconnu* ; *L'escale est close* ; *Ce document est généré depuis le registre, jamais déposé (EF-7.3)* ; *Les documents N4 sont déposés dans l'espace sûreté seulement* ; *Un document bilatéral (N3) nomme sa contrepartie* ; *Type de fichier non accepté (…)* ; *Fichier trop volumineux (max 25 Mo)* ; *Le fichier est vide* ; *La tâche … attend un autre document : …* ; *La tâche … n'est pas accomplie par la fourniture d'un document* ; *Cette tâche est déjà close* ; *Une nouvelle version concerne la même escale et le même type* ; *Seul un document émis ou signé peut être remplacé* ; *Seul l'émetteur publie une nouvelle version* ; refus du verrou du connaissement.

### Signer — `document_sign` (`documents.sign_document`) — rôles signataires requis qui n'ont pas encore signé

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `document_id` | — | hidden | oui | document `ISSUED` visible, dont `required_signers` contient un rôle de la personne non encore signé | — |
| `signature_image` | Signature manuscrite (facultative) / Hand-drawn signature | hidden (canvas `sigpad`, bouton *Effacer*) | non | data URL `data:image/png;base64,` de 400 000 caractères au plus | vide |

**Effets** : `DocumentSignature` (rôle, libellé du signataire, `signed_at`, `document_sha256` de la version exacte, image, sceau), journal `document.signed` ; quand tous les rôles requis ont signé : statut `SIGNED` (document figé : plus de nouvelle version), journal `document.fully_signed`, tâche liée close. **Refus** : *Seul un document émis en attente de signatures peut être signé* ; *Image de signature invalide* ; aucun rôle signataire en attente ; escale close.

### Annuler — `document_cancel` (`documents.cancel_document`) — l'émetteur (même organisation)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `document_id` | — | hidden | oui | document visible, `DRAFT`, `ISSUED` ou `SIGNED` | — |
| `reason` | Motif / Reason | text | oui | non vide | — |

**Effets** : statut `CANCELLED`, `cancel_reason`, journal `document.cancelled` ; le document reste lisible (jamais supprimé). **Refus** : *Seul l'émetteur annule un document* ; *Un motif est requis* ; *Ce document ne peut plus être annulé* ; escale close.

### Consulter, télécharger — `document_download` (`/escales/<id>/documents/<doc>/`) — lecteurs du document

Sans formulaire. Chaque consultation est inscrite au journal d'accès (`download`). Affichage dans le navigateur (`?inline=1`) pour les PDF et images reconnus sur leur contenu et pour les documents HTML générés par la plateforme (rapport des faits, formulaires), sous `Content-Security-Policy: sandbox` ; tout fichier envoyé par une partie est sinon servi en `application/octet-stream` (téléchargement), jamais rendu comme une page du site. Lecteurs : N1 toutes les parties, N2 superviseurs (`AGE`, `CAP`, `DIR`) + `COM` + émetteur + signataires + `audience_roles`, N3 émetteur et contrepartie ; un prestataire (`PRE`) ne lit que ses propres pièces N1.

### Ouvrir une mesure — `measurement_open` (`measurements.create_measurement`) — INS, TER, NAV

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `kind` | Nature / Kind | select | oui | `INITIAL` jaugeage initial, `FINAL` jaugeage final, `OBQ`, `ROB`, `BL` chiffre du connaissement, `OTHER` | `INITIAL` |
| `unit` | Unité / Unit | select | oui | `MT`, `M3` (m³ @15 °C), `BBL` (bbl @60 °F) | `MT` |

**Effets** : `Measurement` (produit = `PortCall.product`, `tolerance_pct` = `Port.quantity_tolerance_pct`, 0,300 % par défaut, figée à l'ouverture), journal `measurement.created` visible des rôles ayant « V » sur mesure. L'onglet est masqué aux autres rôles (*Les quantités ne sont pas visibles de votre rôle*). **Refus** : *Nature de mesure inconnue* ; escale close.

### Saisir ma valeur — `measurement_value` (`measurements.add_value`) — NAV pour le bord, TER pour la terre (l'organisation qui parle pour la terre), INS pour l'inspecteur — un émetteur par valeur (règle 1)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `measurement_id` | — | hidden | oui | mesure de l'escale | — |
| `party` | Partie / Party | select | oui | parmi `SHIP`, `SHORE`, `SURVEYOR` selon les rôles tenus (`SHIP` ↔ NAV, `SHORE` ↔ TER, `SURVEYOR` ↔ INS) | la première tenue |
| `value` | Quantité / Quantity | text `inputmode=decimal` | oui | nombre ≥ 0, virgule ou point décimal acceptés (`parse_decimal` refuse une valeur mêlant les deux) ; prérempli depuis le connaissement validé par l'assistant pour une mesure `BL` (`?prefill_bl=`, étiquette *prérempli — à vérifier*) | — |
| `temperature_c` | Température (°C) | text décimal | non | nombre | — |
| `density` | Densité / Density | text décimal | non | nombre | — |
| `note` (API, terrain) | Note | text | non | libre | — |

**Effets** : `MeasurementValue` scellée (sceau sur mesure, partie, valeur, rôle, auteur, heure, valeur corrigée), `declared_at` / `entered_at`, `deferred` si saisie différée (terrain : `source`, `device_recorded_at`, `client_uuid` idempotent) ; une nouvelle valeur de la même partie devient la valeur courante, la précédente reste au registre (`supersedes`) ; journal `measurement.value` ; les écarts bord/terre, bord/inspecteur, terre/inspecteur sont recalculés à l'affichage ; si |bord − terre| dépasse la tolérance : `Alert` de nature `QUANTITY` (*écart bord/terre x % (tolérance y %) — ouvrir une contestation si nécessaire ; la plateforme ne tranche pas*) et notification temps réel NAV, TER, INS, AGE, COM. La plateforme ne désigne jamais de valeur de référence ; une mesure sans valeur bord ou terre bloque la clôture (point d'arrêt `CLOSE`). **Refus** : *Partie inconnue* ; *Cette valeur est saisie par son titulaire seulement (émetteur unique)* ; *L'escale est close* ; *Une quantité est un nombre positif* ; *« … » doit être un nombre* ; *Une correction concerne une valeur de la même partie* ; *Le chiffre terre est saisi par le terminal qui parle pour la terre sur cette escale*.

### Journal de pompage — `pumping` (`measurements.add_pumping_entry`) — TER, NAV

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `declared_at` | Heure / Time | datetime-local (`data-default-now`) | non | heure du port | maintenant |
| `pressure_bar` | bar | text décimal | non | pression au collecteur | — |
| `rate_m3h` | m³/h | text décimal | non | débit | — |
| `temperature_c` | °C | text décimal | non | température | — |
| `note` (API) | Note | text | non | libre | — |
| `device_id`, `automatic` (API) | — | — | non | relevé instrumenté : source `AUTOMATIC`, identifiant de l'appareil ; `client_uuid` idempotent | — |

**Effets** : `PumpingLogEntry` (`recorded_at`, rôle, auteur, `deferred` si saisie différée), journal `pumping.entry` ; le tableau de l'onglet Mesures affiche la chaîne des relevés avec les mentions *automatique* et *différé*. **Refus** : *L'escale est close* ; *« … » doit être un nombre*.

## 13.7 Contestations, échanges, rapport des faits, formulaires standards et assistant

### Ouvrir une contestation — `dispute_open` (`disputes.open_dispute`) — tout rôle sauf DIR (`OPENING_ROLES`), escale non close

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `target_kind` | Concerne / Concerns | select (onglet Contestations) ou hidden (depuis l'objet contesté) | oui | `OTHER` *un autre sujet (heures, documents, prestations…)*, `MEASUREMENT` *les quantités — le connaissement reste verrouillé jusqu'à la clôture* ; depuis un objet : `MILESTONE`, `TASK`, `DOCUMENT`, `REQUEST` | `OTHER` |
| `target_id` | — | hidden | non | identifiant d'un objet de l'escale de la nature indiquée | — |
| `subject` | Objet / Subject | text | oui | non vide, 250 caractères ; prérempli depuis une mesure (*nature — produit*) | — |
| `counterpart_role` | Contrepartie / Counterpart | select | non | AGE, NAV, TER, INS, SVC, CAP, APO, PRE (depuis une mesure : NAV, TER, INS, AGE hors rôles tenus) ; si l'objet contesté a un auteur unique de ce rôle, la contestation lui est adressée (organisation ou capitaine) | — |
| `statement` | Exposé / Statement | textarea | oui | non vide | — |

**Effets** : `Dispute` `DSP-<PORT>-<année>-<nnnnn>` en statut `OPEN`, première entrée `STATEMENT`, journal `dispute.opened` (visible de tous : l'en-tête est public, l'exposé et les réponses sont bilatéraux — ouvreur, contrepartie, capitainerie), notification de la contrepartie, de l'agence et de la capitainerie ; une contestation `MEASUREMENT` non close ferme le verrou `BL_ISSUE` et toute contestation non close bloque la clôture de l'escale (point d'arrêt `CLOSE`). La plateforme ouvre elle-même une contestation (`auto_created`) sur une contresignature contestée d'un jalon ou d'une tâche et sur des saisies concurrentes. **Refus** : *Une contestation énonce son objet et ses motifs* ; *Sujet de contestation inconnu* ; *L'élément contesté n'appartient pas à cette escale* ; escale close.

### Répondre — `dispute_respond` (`disputes.respond`) — la contrepartie (ou, sans contrepartie nommée, tout rôle ouvreur autre que l'ouvreur) ; l'ouvreur dès qu'une réponse existe

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `dispute_id` | — | hidden | oui | contestation `OPEN` ou `ANSWERED` de l'escale | — |
| `text` | Réponse / Response | textarea | oui | non vide | — |

**Effets** : entrée `RESPONSE` ; `OPEN` → `ANSWERED` à la première réponse d'un autre rôle que l'ouvreur ; journal `dispute.answered` ; notification de l'ouvreur et de la contrepartie. **Refus** : *Cette contestation est close* ; *La réponse est vide* ; *Cette contestation est adressée à une autre partie* ; escale close.

### Clore — `dispute_close` (`disputes.close`) — l'ouvreur (même organisation) ou la capitainerie ; jamais arbitrée

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `dispute_id` | — | hidden | oui | contestation non close | — |
| `agreed` | avec accord / sans accord | radio `1` / `0` (ouvreur) ; hidden `0` (capitainerie : *constate que la contestation s'achève sans accord : un accord appartient aux parties*) | oui | — | — |
| `text` | Comment elle s'achève / How it ends | textarea | oui | non vide | — |

**Effets** : entrée `CLOSURE`, statut `CLOSED_AGREED` ou `CLOSED_NOT_AGREED`, `closed_at`, journal `dispute.closed` ; le verrou du connaissement et la clôture de l'escale ne sont plus retenus par elle. **Refus** : *Cette contestation est déjà close* ; *Indiquez comment la contestation s'achève* ; *La capitainerie ne constate qu'une clôture sans accord : un accord appartient aux parties* ; un autre titulaire du rôle ouvreur (autre organisation) ne peut pas la clore.

### Ouvrir un échange — `thread_create` (`correspondence.create_thread`) — tout rôle sauf DIR (`WRITERS`), escale non close

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `subject` | Objet / Subject | text | oui | non vide, 250 caractères | — |
| `participants` | Avec / With | cases à cocher, un rôle par case (tous les rôles sauf ceux de la personne) | oui sauf N1 | codes de `ALL_ROLES` ; le rôle de l'auteur est toujours participant | — |
| `confidentiality` | Confidentialité | select | oui | `N2` restreint aux participants, `N3` bilatéral (exactement une autre partie), `N1` toutes les parties de l'escale ; `N4` refusé | `N2` |
| `body` | Message | textarea | oui | non vide | — |

**Effets** : `Thread` (participants triés, `related_kind` / `related_id` lorsqu'il est ouvert depuis un objet par l'API) et premier `Message`, journal `thread.created` (visible de tous en N1, des participants sinon), notification des parties invitées. **Refus** : *Les sujets de sûreté vont dans l'espace sûreté* ; *Un échange bilatéral réunit exactement deux parties* ; *Choisissez au moins une autre partie* ; *Objet et message sont requis* ; escale close.

### Répondre dans un fil — `thread_post` (`correspondence.post_message`) — participants du fil

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `thread_id` | — | hidden | oui | fil visible de l'escale | — |
| `body` | Répondre… / Reply… | text | oui | non vide | — |
| `document` (API) | pièce jointe | identifiant | non | document de la même escale, lisible de l'auteur | — |

**Effets** : `Message` (`author_label`, `sent_at`), `last_message_at` du fil ; notification des parties invitées et, dans sa propre organisation seulement, de la partie créatrice. Les fils d'un rôle se lisent par tout titulaire du rôle dans l'organisation participante (`rights.thread_visible`). **Refus** : *Vous n'êtes pas participant de cet échange* ; *Le message est vide* ; *La pièce jointe appartient à une autre escale* ; escale close.

### Rapport des faits — `statement` (`reports.issue_statement_of_facts`) — AGE, escale `OPS_COMPLETE` ou `DEPARTED` (onglet Aperçu)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `remarks` | Remarques de l'agence (facultatives) / Agency remarks | textarea | non | libre ; prérempli par l'assistant après *Rédiger les remarques avec l'assistant* (étiquette *prérempli par l'assistant — relire avant de générer*) | vide |
| `remarks_assisted` | — | hidden `1` | non | présent quand le brouillon vient de l'assistant | — |

**Effets** : le rapport des faits est rendu depuis le registre seul (EF-7.3 : chronologie des jalons et contresignatures, interruptions et imputations, quantités, documents, contestations) par `reports.render_statement`, puis déposé comme document généré `SOF` (N1, signataires NAV et TER notifiés, version n + 1 si un rapport émis ou signé existe), rattaché à la tâche M0:36 ; les remarques sont imprimées sous le nom de l'agence avec la mention *rédigées par …* ou *projet préparé avec l'assistant IA, relu et validé par …* ; le **time sheet** (`TIME_SHEET`, M0:37) est déposé automatiquement dans la foulée (`forms.auto_issue`). Aperçu sans dépôt : `/escales/<id>/rapport-des-faits/` (journal d'accès `view`). **Refus** : *Le rapport des faits est produit par l'agence* ; *Le rapport des faits est produit après la fin des opérations*.

### Émettre un formulaire standard — `form_issue` (`forms.issue`) — rôles du formulaire (page Formulaires, `/escales/<id>/formulaires/`)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `code` | — | hidden (bouton *Émettre et déposer* de la ligne) | oui | code d'un des 76 formulaires offert à l'escale (`forms.offered`) et émis par un rôle de la personne | — |
| `as_role` (API) | — | — | non | quand la personne tient plusieurs rôles du formulaire | premier rôle tenu (ordre alphabétique) |

**Effets** : rendu HTML du formulaire prérempli (`forms.render`), déposé par `documents.upload_document` comme document généré du type du formulaire, nom `<référence>_<code>.html`, titre `<titre FR> / <titre EN> — <référence>`, numéro `CODE-RÉFÉRENCE-nn`, version n + 1 du document de même titre encore émis ou signé, confidentialité du type, signataires du type ; journal `document.issued`. L'aperçu (`/escales/<id>/formulaires/<code>/`) est libre et ne dépose rien. Le formulaire *Connaissement — données d'émission* passe par le verrou `BL_ISSUE`. Les dépôts automatiques (acte de chaque décision, NOR, time sheet) sont décrits en 4.2. **Refus** : *Formulaire inconnu* ; *Ce formulaire n'est pas généré par votre rôle* ; *Ce formulaire ne s'applique pas aux opérations de cette escale* ; refus du verrou du connaissement ; escale close.

### Assistant — actions `ai.*` — port dont `ai_assistance_enabled` est vrai ; jamais par un lien d'accès ; l'assistant propose, une personne valide

| Action | Adresse (POST) | Rôles | Entrées | Effets |
| --- | --- | --- | --- | --- |
| Lire avec l'assistant (`extract`) | `/escales/<id>/assistant/extraction/<doc>/` | selon le type lu : `Q88` AGE, NAV ; `CERTIFICATES` AGE, NAV, CAP, APO, ADM ; `BL` AGE, NAV, TER, INS | document `ISSUED` ou `SIGNED` lisible de la personne | `AssistantRun` (`EXTRACT`, journal d'accès `assistant` avec l'inventaire de ce qui a été transmis) et `ExtractionReview` `PROPOSED` ; rien n'est enregistré |
| Vérifier les valeurs lues (`extraction`) | `/escales/<id>/assistant/verification/<revue>/` | la personne autorisée à lire ce type | Q88 et BL : une ligne par champ — `keep` (case, clé) et `value_<clé>` (valeur corrigeable), avec la citation (`evidence`) et la valeur actuelle du navire ; certificats : `row` (index), `keep_<i>`, `name_<i>`, `number_<i>`, `expiry_<i>` (AAAA-MM-JJ) ; `decision=dismiss` écarte la proposition ; avertissement si le numéro OMI lu diffère de celui de l'escale | Q88 : fiche navire mise à jour sur les seuls champs applicables (pavillon, type, indicatif, MMSI, DWT, LOA, largeur, tirant d'eau, année, armateur, gestionnaire ; jamais le nom ni l'OMI), journal `vessel.updated` ; certificats et connaissement : journal `document.data_validated` sous le nom du validateur ; un connaissement validé préremplit la mesure `BL` (`mesures?prefill_bl=`) ; refus *Cette extraction a déjà été traitée*, *« … » n'est pas une valeur valide pour la fiche navire*, *Les dates d'expiration s'écrivent AAAA-MM-JJ*, *La quantité doit être un nombre*, escale close |
| Revue de l'escale (`review`) | `/escales/<id>/assistant/revue/` | AGE, CAP, APO, TER, INS | le registre tel que la personne le voit (`payloads.call_digest`) | constats affichés dans l'Aperçu (*question pour une personne*, références citées), complétés de constats déterministes ; rien n'est enregistré |
| Lever une alerte (`raise_alert`) | `/escales/<id>/assistant/revue/<run>/alerte/<i>/` | la personne qui a lancé la revue | index du constat | `Alert` sous son nom, journal `alert.raised` ; refus *Seule la personne qui a lancé la revue peut lever ses constats*, *Constat inconnu* |
| Résumer un échange (`summarize`) | `/escales/<id>/assistant/echange/<fil>/` | participants du fil | les messages du fil | résumé affiché avec la mention *résumé par l'assistant — à vérifier avec les messages* ; rien n'est enregistré |
| Rédiger les remarques (`remarks`) | `/escales/<id>/assistant/remarques/` | AGE | le registre de l'escale | brouillon des remarques prérempli dans le formulaire du rapport des faits, marqué `remarks_assisted` |
| Assistant du port (`port`) | `/assistant/` (GET : synthèse ; POST `question`) | DIR, CAP, APO | question de 600 caractères au plus sur les escales visibles | réponse citée par référence d'escale, jamais nominative ; refus *Écrivez la question*, *La question est trop longue (600 caractères au plus)* |

Règles communes : *L'assistance IA n'est pas activée pour ce port* et *L'assistant n'est pas disponible par un lien d'accès* ; l'assistant ne décide, ne corrige et ne signe jamais ; chaque exécution est journalisée (`AssistantRun` : fonctionnalité, modèle, inventaire des objets transmis, durée) ; les pièces N4 et les contenus invisibles de la personne ne sont jamais transmis ; une indisponibilité du service affiche *L'assistant n'a pas pu traiter cette demande* sans autre effet.

## 13.8 Sûreté N4 et administration du port

### Déposer une demande de sûreté — `secure_deposit` (`secure.deposit`) — AGE, NAV, SUR, CAP ; écriture seule (onglet Aperçu, escale non close)

| Champ | Libellé | Type | Obligatoire | Valeurs, validation | Défaut |
| --- | --- | --- | --- | --- | --- |
| `kind` | Nature / Kind | select | oui | `ARMED_GUARDS` gardes armés, `ESCORT` escorte navale, `SECURITY_PLAN` plan ou déclaration de sûreté, `INCIDENT` incident de sûreté, `OTHER` autre sujet de sûreté | `ARMED_GUARDS` |
| `guards` | Nombre de gardes / Number of guards | text `inputmode=numeric` | non | libre | — |
| `company` | Société / Company | text | non | libre | — |
| `embark` | Embarquement / Embarkation | datetime-local | non | heure du port | — |
| `disembark` | Débarquement / Disembarkation | datetime-local | non | heure du port | — |
| `escort` | Escorte (route, durée) / Escort | text | non | libre | — |
| `details` | Détails / Details | textarea | non | libre ; la demande doit avoir au moins un champ renseigné | — |

**Effets** : `SecureItem` dans la **base sûreté** (`SECURE_DATABASE_URL`), charge utile chiffrée avec `FLUXAA_N4_KEYS` (`secure.encrypt`), référence `N4-<PORT>-<année>-<nnnn>` affichée **une seule fois** comme reçu au déposant (*Conservez-le : cette demande n'apparaîtra nulle part ailleurs dans l'escale*), statut `SUBMITTED`, `due_at` = ETA − 24 h pour les gardes armés (A1.02), déposant (`submitted_role`, libellé, organisation), journal d'accès sûreté `CREATE`, courriel aux utilisateurs SUR du port (référence seule, jamais le contenu). Rien n'apparaît dans l'escale : aucune entrée de journal d'escale, aucune notification, aucune pièce dans l'onglet Documents, aucun export, aucun envoi à l'assistant. **Refus** : rôle non autorisé → *introuvable* ; *L'escale est close* ; *Nature de demande de sûreté inconnue* ; *La demande est vide*.

### Espace sûreté — `/surete/` (liste), `/surete/<référence>/` (dossier), `/surete/journal/` (journal d'accès), `/surete/piece/<id>/` (pièce) — SUR et CAP du port (`n4_role`), tout autre rôle voit *introuvable*

| Action | Formulaire (POST sur le dossier) | Qui | Entrées | Effets |
| --- | --- | --- | --- | --- |
| Lister, consulter | — | SUR, CAP | — | déchiffrement à l'affichage ; journal d'accès `LIST` (nombre de dossiers), `VIEW` (dossier) ; la liste montre référence, escale, nature, déposant, échéance, statut |
| Décider et fixer les modalités (`action=decide`) | `decision` select `APPROVED` / `APPROVED_COND` / `REFUSED` ; `modalities` textarea obligatoire (modalités ou motif) | SUR seulement ; **session forte** (second facteur récent, sinon renvoi vers `/compte/2fa/verifier/?next=`) ; dossier `SUBMITTED` ou `UNDER_REVIEW` | — | statut = décision, `SecureDecision` (décision, modalités, auteur, heure), journal d'accès `DECIDE` ; refus *Seule l'autorité de sûreté décide*, *Décision inconnue*, *Ce dossier n'attend pas de décision*, *Indiquez les modalités ou le motif* |
| Confirmer (`action=confirm`) | bouton `what` = `embarked` embarquement, `disembarked` débarquement, `anti_intrusion` mesures anti-intrusion (A1.03 / A1.04) | SUR | — | horodatage du champ correspondant, une seule fois ; le débarquement passe le dossier `EXECUTED` ; journal d'accès `CONFIRM` ; refus *Seule l'autorité de sûreté confirme*, *Confirmation inconnue*, *Déjà confirmé* |
| Joindre une pièce (`action=attach`) | `file` (fichier) | SUR, CAP | fichier ≤ 10 Mo | `SecureAttachment` chiffrée, journal d'accès `ATTACH` ; lecture d'une pièce journalisée `READ` ; refus *Fichier trop volumineux (10 Mo maximum dans l'espace sûreté)* |
| Journal d'accès | — | SUR, CAP | — | toutes les lectures et écritures de l'espace (qui, quand, quoi, adresse), chaîne vérifiable (`verify_chain`) |

Statuts d'un dossier : `SUBMITTED`, `UNDER_REVIEW`, `APPROVED`, `APPROVED_COND`, `REFUSED`, `EXECUTED`, `CLOSED`. Les champs `embarked_at`, `disembarked_at`, `anti_intrusion_confirmed_at` portent les confirmations. L'espace n'a ni recherche plein texte ni export : la confidentialité N4 prime sur la commodité (FLX-SPEC-002, EF-12).

### Administration du port — `/admin/` — administrateur du port (`is_port_admin`, limité à son port) ou superutilisateur

Les écrans de réglage n'ont pas de connexion propre : celle de la plateforme s'applique (limites d'essais, second facteur), puis l'administrateur revient à la page demandée. Toute modification d'un compte (rôles, activation, mot de passe, remise à zéro du second facteur) est inscrite au journal d'accès (`user.administered`, champs modifiés).

| Écran | Modèle | Champs (groupes) | Règles |
| --- | --- | --- | --- |
| Port | `Port` | identité : `code`, `name`, `country`, `timezone`, `default_language`, `is_active` · *Délais et seuils* : `countersign_delay_minutes`, `reminder_lead_hours`, `escalation_after_minutes`, `quantity_tolerance_pct`, `ais_divergence_minutes`, `digest_hour_local` · *Accès capitaine* : `master_link_grace_hours`, `master_link_max_days` · *Conservation et sûreté* : `retention_years`, `security_authority_email` · *Eaux du port — tableau AIS* : `map_lat_min` / `map_lat_max`, `map_lon_min` / `map_lon_max`, `map_image`, `ais_retention_days` · *Assistance IA (EF-17)* : `ai_assistance_enabled`, `ai_agreement_reference` | l'administrateur ne voit que son port ; sans cadre AIS le tableau est une liste |
| Organisations | `Organization` | `name`, `short_name`, `kind` (nature de partie, liste non exhaustive `PARTY_KINDS` + saisie libre), `allowed_roles`, `email`, `phone`, `is_active` | une organisation créée depuis une escale (*Inviter une partie*) apparaît ici (journal `organization.created`) |
| Utilisateurs | `User` | `email`, mot de passe, `full_name`, `organization`, `roles` (rôles que la personne peut exercer, dans ceux de son organisation), `language`, `phone` · *Administration* : `is_active`, `is_port_admin`, `is_integration`, `integration_scopes` · *Notifications et sécurité* : `notify_digest_only`, `mfa_enabled`, `last_login` (lecture) | décocher `mfa_enabled` efface l'enrôlement : la personne réenrôle une application à la prochaine connexion (téléphone perdu) ; un compte d'intégration reçoit un jeton API depuis son profil (journal `api_token.created`) |
| Postes | `Berth` | `code`, `name_fr`, `name_en`, `kind` (nature de zone), `max_loa_m`, `max_draft_m`, `has_vapour_recovery`, `is_active` | proposés à l'attribution de poste selon la nature de l'escale ou de l'étape |
| Gabarits | `CallTemplate`, `TemplateVersion`, `TemplateTask` | gabarit : `code`, `name_fr` / `name_en`, `kind`, `published`, `is_active` · version : `number`, `status` (`DRAFT` → `PUBLISHED`), `published_at`, `published_by`, `notes` · tâche (en ligne) : `number`, `order`, `section_fr` / `section_en`, `title_fr` / `title_en` ; *Qui et comment* : `role`, `nature` (C/F/S/D), `joint`, `co_roles` ; *Échéance (toujours relative)* : `anchor`, `offset_minutes`, `timing_fr` / `timing_en` ; *Criticité* : `criticality`, `confidentiality`, `hold_basis`, `not_applicable_allowed` ; *Accomplie par* : `request_type_code` / `request_side`, `milestone_codes`, `document_type_code`, `auto_event`, `continuous`, `per_vessel`, `berth_kinds` | les tâches ne se modifient que sur une version `DRAFT` ; la publication fige la version ; une escale garde les versions de ses tâches |
| Points d'arrêt | `HoldPoint`, `HoldPointRequirement` | `transition` (`GREEN_LIGHT`, `BERTH_ASSIGN`, `CLOSE`…), `description_fr` / `description_en`, exigences (`template_code`, `task_number`) | le verrou `BL_ISSUE` n'est pas configurable |
| Types de jalons | `MilestoneType` | `number`, `code`, `label_fr` / `label_en`, `emitter_role`, `hold_point`, `is_active` | les codes système utilisés par les règles ne se renomment pas |
| Types de demande | `RequestType` | `code`, libellés, `requester_roles`, `decider_roles`, `executor_role`, `confidentiality`, `form_schema`, `validity_hours`, `assigns_berth`, `approval_status`, `approval_milestone`, `refusal_status`, `decision_completes`, `execution_completes`, `is_active` | chaque type décidé a son acte `AUTH_<TYPE>` |
| Types de document | `DocumentType` | `code`, libellés, `issuer_roles`, `default_confidentiality`, `signer_roles`, `audience_roles`, `retention_years`, `is_active` ; `generated` et `is_bill_of_lading` en lecture seule | le verrou du connaissement ne se désactive pas |
| Causes d'interruption | `InterruptionCause` | `code`, libellés, `attributable_to` (`SHIP`, `SHORE`, `THIRD`, `WEATHER`), `requires_reason`, `order`, `is_active` | imputation du time sheet |
| Parties par défaut | `PortDefaultParty` | `organization`, `role` | invitées d'office à chaque escale (capitainerie, autorité portuaire, sûreté, administrations, services) |
| Navires | `Vessel` | `name`, `imo`, `flag`, `vessel_type`, `dwt`, dimensions, armateur, gestionnaire | créés aussi à l'annonce d'une escale |
| Abonnements webhook | `WebhookSubscription` | `name`, `url`, `actions` (vide = toutes les actions N1), `is_active`, `secret` (lecture) | publication signée des événements du journal (API) |

Les catalogues livrés pour chaque port (gabarits M0–M9, MA2 et MA3 — le module A1 de sûreté vit dans l'espace sûreté, jalons, demandes, documents, causes, points d'arrêt, parties) sont dans l'onglet *Catalogues* ; la commande `bootstrap_ports` les installe et `load_demo` charge le jeu de démonstration.
