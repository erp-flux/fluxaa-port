# 8. Écrans — catalogue des écrans

> Chapitre **rédigé** (FLX-SPEC-003, onglet 2), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.


Chaque écran de la plateforme : adresse, rôles qui l'ouvrent, objectif, zones et composants, données affichées, actions offertes, états particuliers, et sa capture sur les données de démonstration. Les écrans sont décrits tels que livrés ; une réécriture conserve les adresses, les rôles et les actions, la mise en forme restant libre dans les limites des conventions d'interface.

## 8.1 Conventions d'interface

Toutes les pages suivent le même gabarit (`templates/base.html`) et la même feuille de style (`static/css/fluxaa.css`, 1 feuille, aucune bibliothèque CSS) ; l'interactivité tient en deux scripts auto-hébergés (`static/js/app.js`, HTMX 2.0.11) sous une politique de sécurité de contenu sans script en ligne. Les écrans sont rendus côté serveur (Django) ; HTMX rafraîchit seulement le tableau de bord (toutes les 60 s) et le tableau AIS.

| Convention | Règle |
| --- | --- |
| Gabarit de page | Barre supérieure (marque, menu principal, badge du port avec son fuseau, chips des rôles de la personne, commutateur FR / EN, cloche des notifications avec compteur, nom de la personne → *Mon compte*, déconnexion), zone `main` à largeur maximale 1 320 px, pied de page (fuseau du port, heures stockées en UTC). Lien d'évitement vers le contenu. |
| Menu principal | *Tableau de bord* (tous sauf un compte NAV seul), *Escales*, *Tableau AIS*, *Statistiques* (DIR, APO, CAP), *Assistant* (si l'assistance est activée pour le port et le rôle), *Espace sûreté* (SUR, CAP), *Pilotage* (DIR, administrateur), *Paramétrage* (administrateur du port, superutilisateur) → administration Django. L'entrée courante porte `aria-current="page"`. |
| Titulaire d'un lien | Pas de menu ; la barre montre le nom du titulaire, son organisation, son rôle et *Quitter* ; seules les pages de son escale sont accessibles. |
| Messages | Les messages Django (`flash success / error / warning`) sous la barre ; un **refus de point d'arrêt** s'affiche dans l'encadré dédié `_refusal.html` (transition refusée, tâches manquantes avec responsable et action attendue, raisons) et reste inscrit au journal. |
| Confirmation | Les actes irréversibles (décisions, clôtures, annulations, dépôt sûreté) portent `data-confirm` : une boîte de confirmation native avant l'envoi. |
| Formulaires d'action | Chaque action est un formulaire `POST` vers `/escales/<id>/action/<action>/` avec jeton CSRF, un champ caché `back` (retour à l'onglet et à l'ancre), replié dans un `<details class="action">` quand il demande une saisie. Sans JavaScript, tout fonctionne (boutons `<noscript>` pour les listes à soumission automatique). |
| Chips | `chip status st-<STATUT>` pour l'état de l'escale ; `chip done / pending / hold / late / reminder / escalated / contested / tacit / na / deferred / blocking` pour les états ; `role` pour un code de rôle (info-bulle = libellé) ; `code` pour un code de catalogue (monospace) ; `conf` pour le niveau N1…N3. |
| Tableaux | `table.grid` dans `div.tablewrap` (défilement horizontal sur petit écran) ; lignes de section `tr.section-row` ; colonnes numériques en `num` (monospace). |
| Heures | Affichées `jj/mm HH:MM` dans le fuseau du port (`<time>`), suffixe *est.* pour une estimation ; saisies en `datetime-local` interprétées dans le fuseau du port ; `data-default-now` préremplit à l'heure courante. |
| Langue | FR par défaut (langue du compte, sinon cookie, sinon langue du port) ; chaque libellé passe par `{% trans %}` ; les libellés de catalogue sont stockés en FR et EN (`label_fr` / `label_en`) et choisis par `pick()`. |
| États vides | Un paragraphe `p.empty` nomme ce qui manque et, quand c'est possible, l'action à faire (« Aucune escale. Annoncez la première… »). |
| Erreurs | 403 / 404 : pages Django standard ; un objet invisible pour le rôle répond 404, jamais 403 (son existence n'est pas révélée, règle 4). Une règle métier violée revient en message d'erreur sur la page d'origine. |
| Accessibilité | Libellés explicites (`label for`), `aria-label` sur les commandes sans texte, `role="table"` sur le plan des postes, `sr-only` pour les barres, contraste AA, cibles tactiles ≥ 44 px dans l'appli terrain, tout utilisable au clavier. |
| Impression | Les formulaires standards et le rapport des faits ont leur propre gabarit A4 (`reports/`), sans barre ni menu. |
| Téléphone | Les pages sont fluides jusqu'à 390 px ; **limite connue** : les tableaux larges de la fiche d'escale (points d'arrêt, tâches) débordent en largeur sous 640 px (défilement horizontal du `tablewrap`) ; l'écran prévu pour le téléphone est l'**appli terrain**. Cible 1.4 : lignes empilées sous 600 px. |

### Inventaire des écrans

| Écran | Adresse | Qui | Section |
| --- | --- | --- | --- |
| Connexion, second facteur (vérification, activation), mon compte | `/compte/connexion/`, `/compte/mfa/verifier/`, `/compte/mfa/activer/`, `/compte/` | comptes | 8.2 |
| Accès par code, lien d'accès, nom du titulaire | `/bord/`, `/bord/<jeton>/`, `/bord/nom/` | capitaine et parties sans compte | 8.2 |
| Tableau de bord | `/` | tous sauf NAV seul | 8.3 |
| Liste des escales, annonce d'escale | `/escales/`, `/escales/nouvelle/` | tous ; AGE | 8.3 |
| Fiche d'escale : en-tête, frise, onglets | `/escales/<id>/?tab=<onglet>` | parties de l'escale | 8.4 – 8.6 |
| Formulaires de l'escale, aperçu d'un formulaire, rapport des faits | `/escales/<id>/formulaires/`, `…/formulaires/<code>/`, `…/rapport-des-faits/` | parties | 8.7 |
| Appli terrain | `/escales/<id>/terrain/` | parties qui saisissent | 8.7 |
| Espace sûreté, dépôt, journal des accès | `/surete/`, `/surete/<réf>/`, `/surete/journal/` | SUR, CAP | 8.8 |
| Notifications | `/notifications/` | comptes | 8.8 |
| Vérification publique | `/verifier/`, `/verifier/<code>/` | public | 8.8 |
| Tableau AIS | `/carte/` | comptes du port | 8.9 |
| Statistiques, assistant du port, pilotage | `/statistiques/`, `/assistant/`, `/pilotage/` | DIR, APO, CAP ; administrateur | 8.9 |
| Administration et paramétrage | `/admin/…` | administrateur du port | 8.10 |
| Export d'escale (archive zip), téléchargement d'un document | `/escales/<id>/export/`, `/escales/<id>/documents/<id>/` | COM, DIR ; lecteurs | fichiers, pas d'écran |
| Routes utilitaires (sans écran propre) | `/compte/deconnexion/` (déconnexion), `/compte/langue/` (changement de langue, `POST lang`), `/bord/<token>/` (entrée par le lien d'accès, puis `/bord/nom/`), `/bord/sortie/` (fin de session du lien), `/admin/login/` (renvoi vers la connexion de la plateforme), `/surete/piece/<id>/` (pièce chiffrée de l'espace sûreté, SUR et CAP), `/escales/<id>/assistant/verification/<id>/` (vérification des valeurs lues par l'assistant, onglet Documents), `/healthz` (état de l'instance pour la supervision, sans authentification) | selon la route | 8.2, 8.5, 8.8 |

## 8.2 Accès : connexion, second facteur, mon compte, accès sans compte

### Connexion — `/compte/connexion/`

|  |  |
| --- | --- |
| Accès | public (page d'entrée de tout compte) |
| Objet | ouvrir une session par courriel et mot de passe ; renvoyer vers la page demandée (`next`) |
| Composants | `loginbox` : titre, phrase d'accroche, formulaire (`username` courriel, `password`), lien *Capitaine d'un navire ? Entrez le code d'accès*, lien *Vérifier une autorisation* |
| Règles | 10 échecs d'un compte depuis une adresse, 30 depuis une adresse, 50 sur un compte → blocage 15 min (`AttemptWindow`, message *Trop de tentatives*) ; un rôle décideur (`FLUXAA_MFA_REQUIRED_ROLES`) est envoyé vers l'activation ou la vérification du second facteur avant toute page ; chaque connexion est inscrite au journal des accès (`login`) |
| États | erreur d'identifiants ; blocage temporaire ; compte inactif = même message qu'un mauvais mot de passe |

*Capture d'écran : Connexion — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Second facteur — vérification `/compte/mfa/verifier/` et activation `/compte/mfa/activer/`

|  |  |
| --- | --- |
| Accès | compte connecté ; la vérification est exigée à la connexion des rôles décideurs puis à chaque décision si la dernière vérification date de plus de 8 h (`FLUXAA_MFA_STEPUP_SECONDS`) |
| Objet | prouver la possession de l'application d'authentification (TOTP, RFC 6238) |
| Activation | QR code à scanner, clé en clair pour saisie manuelle, code à six chiffres ; remplacement d'une application : code de l'ancienne **et** de la nouvelle ; téléphone perdu → réinitialisation par l'administrateur (`reset_mfa`, journalisée, courriel à la personne) |
| Vérification | un champ `code` ; après succès, la session est marquée vérifiée (`mfa_verified_at`) et renvoyée vers `next` |
| Règles | 5 codes faux → 15 min ; secret chiffré (`FLUXAA_SIGNING_KEY`) ; les changements sont journalisés (`mfa.enabled`, `mfa.changed`, `mfa.reset`) et notifiés par courriel |

*Capture d'écran : Second facteur — vérification — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Second facteur — activation — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Mon compte — `/compte/`

|  |  |
| --- | --- |
| Accès | tout compte |
| Objet | voir ses rôles, régler ses notifications, activer le second facteur, gérer son jeton d'API |
| Composants | quatre sections : *Rôles* (chips, rappel de la règle 5), *Notifications* (case *Récapitulatif quotidien pour les tâches normales* — les tâches bloquantes et les escalades partent toujours immédiatement), *Double authentification* (état, bouton *Activer*), *Jeton d'API* (créer / remplacer / révoquer ; affiché une seule fois) |
| Actions | `POST /compte/` avec `action` = `digest`, `token`, `revoke` ; la création d'un jeton est journalisée (`api_token.created`) |

*Capture d'écran : Mon compte — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Accès par code — `/bord/` ; par lien — `/bord/<jeton>/` ; nom du titulaire — `/bord/nom/`

|  |  |
| --- | --- |
| Accès | public ; le code (8 caractères, alphabet sans ambiguïté) ou le jeton (43 caractères) vient d'un `MasterAccessLink` valide (non révoqué, non expiré) |
| Objet | ouvrir, sans compte, **une seule escale** : le capitaine (rôle NAV, jusqu'au départ) ou une partie convoquée (TER, INS, COM, PRE, SVC, jusqu'à la clôture) |
| Parcours | `/bord/` : champ `code` (saisie en capitales, format `XXXX-XXXX`) → session de lien → fiche de l'escale. `/bord/<jeton>/` : même chose depuis le lien reçu par courriel ou QR. Si le lien n'a pas encore de titulaire nommé, `/bord/nom/` demande le **nom complet** (3 à 160 caractères) avant toute autre page : tout ce que le titulaire saisit est nominatif (`link.named`) |
| Règles | 10 codes faux par adresse → blocage 15 min (`master-ip`) ; chaque accès réussi ou refusé est inscrit au journal des accès (`master.access`, `master.denied`) ; la session de lien ne donne ni tableau de bord, ni autre escale, ni pièce N4 ; *Quitter* ferme la session et purge les données hors ligne |

*Capture d'écran : Accès par code (téléphone) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Nom du titulaire d'un lien (téléphone) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Ce que voit le titulaire d'un lien

Le capitaine voit la fiche de son escale avec les onglets Aperçu, Tâches, Jalons, Demandes, Documents, Échanges (pas Mesures ni Journal ni Parties), ses tâches NAV, les formulaires de sa famille, l'appli terrain ; une partie convoquée voit la même fiche avec les droits de son rôle et le cloisonnement de son organisation.

*Capture d'écran : Escale vue par le capitaine (téléphone) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Jalons vus par le capitaine (téléphone) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Escale vue par un laboratoire convoqué par lien — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.3 Tableau de bord, liste des escales, annonce d'escale

### Tableau de bord — `/`

|  |  |
| --- | --- |
| Accès | tout compte d'un port sauf un compte NAV seul (matrice `dashboard`, verbe V ; DIR tient aussi E) ; un compte sans ce droit est renvoyé vers la liste des escales |
| Objet | la situation du port d'un coup d'œil : qui est attendu, en rade, à quai, parti ; l'occupation des postes sur 72 h ; les sept indicateurs ; les prochaines tâches de ses rôles |
| Périmètre | seulement les escales où l'organisation de la personne tient un rôle actif (`rights.call_queryset_for_user`) : la capitainerie, l'autorité et la direction voient tout le port parce qu'elles sont parties par défaut de chaque escale ; une agence ne voit que les siennes ; les brouillons n'apparaissent pas (l'agence en voit le nombre) |
| Composants | en-tête (*Escales de navires pétroliers*, nom du port, boutons *Annoncer une escale* pour AGE et *Toutes les escales*) ; **Plan des postes — 72 heures** (`build_plan`) : une ligne par poste ou zone actif du port (nature puis code) et une ligne *Pas encore attribué* ; fenêtre de −12 h à +60 h graduée toutes les 12 h, trait vertical à l'heure courante ; une barre par escale de ETB/ATB à ETD/ATD (de ETA/ATA pour une rade ou une zone STS ; 36 h par défaut sans fin connue) : pleine = réel, contour = estimé, verte = transfert en cours, ▲ = tâche escaladée ; un navire attendu à quai mais mouillé en rade est aussi dessiné en pointillé sur la première ligne de rade ; info-bulle = navire et statut, clic = fiche ; **Indicateurs — 90 derniers jours** (`reports.indicators`) : sept tuiles — attente moyenne en rade (h), occupation moyenne du poste (h), durée nette moyenne de transfert (h), part des temps morts à cause établie contradictoirement (%), tâches bloquantes faites à l'heure (%), délai moyen de décision des autorités (h), contestations ouvertes — info-bulle = escales sources ; **quatre colonnes** : *Attendus* (déclarée, acceptée, planifiée), *En rade / en approche / en déhalage*, *À quai / en opération* (à quai, en opération, opérations terminées), *Partis (24 h)*, chacune avec compteur, navire → fiche, référence, zone et poste, chip de statut, chip *Escaladée*, dernier temps connu (ETA, ATA, ATB ou ATD) ; **Vos prochaines tâches** : les 12 tâches en attente les plus proches, avec échéance, pour les rôles de la personne (échéance, escale → onglet Tâches, code et intitulé, rôle, chips d'alerte et *Bloquante*) ; lien *n escales en brouillon non déclarées* pour l'agence |
| Comportement | la zone `#board` est rechargée par HTMX toutes les 60 s (`hx-get` sur `/` ; avec l'en-tête `HX-Request` la vue répond le corps seul, `_dashboard_body.html`) ; sans JavaScript la page reste exacte à son chargement |
| Règles | les dossiers de sûreté ne sont jamais comptés ; chaque chiffre est recalculé à la demande à partir du registre (aucune table d'agrégats) ; une escale partie quitte les colonnes 24 h après son ATD |
| Variantes | direction (B01) et capitainerie (B02) : tout le port ; agence (B03) : ses escales, le bouton d'annonce et le compteur de brouillons |

*Capture d'écran : Tableau de bord — direction — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Tableau de bord — capitainerie — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Tableau de bord — agence — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Liste des escales — `/escales/`

|  |  |
| --- | --- |
| Accès | tout compte (menu *Escales*) ; page d'arrivée d'un compte sans tableau de bord |
| Objet | retrouver une escale par référence, navire ou IMO ; consulter les archives |
| Composants | en-tête (*Escales*, « Escales sur lesquelles votre organisation tient un rôle », bouton *Annoncer une escale* si AGE) ; formulaire de recherche en GET : champ `q` (navire, IMO ou référence, recherche « contient » sans distinction de casse), sélecteur `scope` (*Escales en cours* = brouillons, statuts actifs et escales parties ; *Toutes, archives incluses* = closes et annulées comprises), bouton *Filtrer* ; tableau `grid` : Référence (lien, monospace), Navire et IMO, Zone d'opération et poste attribué, ETA / ATA, ETD / ATD (suffixe *est.* pour une estimation), Statut (chip) ; tri par ETA décroissante, 300 lignes au plus |
| Règles | les brouillons ne sont montrés qu'à l'agence ; aucune escale d'une autre organisation n'est listée ni retrouvable par la recherche (règle 4) |
| États | vide : « Aucune escale. Annoncez la première… » pour l'agence, « Aucune escale n'implique votre organisation pour le moment » pour les autres |

*Capture d'écran : Liste des escales — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Liste des escales — recherche dans les archives — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Annonce d'escale — `/escales/nouvelle/`

|  |  |
| --- | --- |
| Accès | AGE seulement ; un autre rôle reçoit le message *Seule une agence maritime peut créer une escale* et revient à la liste |
| Objet | créer l'escale en brouillon avec ses gabarits, ses heures estimées, sa cargaison et ses parties ; les tâches de toutes les parties sont instanciées aussitôt (`services.calls.create_call`), les parties sont notifiées à la déclaration |
| Composants | cinq groupes de champs. **Navire** : liste des navires du port (`vessel`) ou repli *Enregistrer un nouveau navire* (`new_imo` 7 chiffres, `new_name` mis en capitales, `new_flag`, `new_type`, `new_dwt`). **Où et quoi** : zone d'opération (boutons radio `kind` : quai / appontement, rade, bouée au large SPM / CBM, zone STS au large), poste ou zone demandé (`requested_berth`, facultatif, de la nature choisie), opérations (cases `operations` : gabarits M1…M8 actifs du port, info-bulle = description), modules complémentaires (`modules` : M9, MA2, MA3…), escale partenaire (`linked_call` parmi les escales en cours de l'agence, pour un STS ou un accostage à couple). **Heures** (fuseau du port) : ETA obligatoire, ETB, début et fin estimés des opérations (`ets`, `etc`), ETD. **Cargaison et voyage** : produit, quantité déclarée, unité (MT, m³ @15 °C, bbl @60 °F), voyage, dernier port, prochain port. **Parties que vous invitez** : la liste ouverte (`_party_rows.html`, module `parties` de `app.js`) — une ligne par partie : rôle (`party_role` : TER, INS, COM, PRE, SVC), organisation enregistrée (`party_org`, options filtrées sur le rôle choisi, avec sa nature et ses rôles) ou *— nouvelle organisation —* qui dévoile le nom (`party_name`), la nature (`party_kind`, liste de suggestions `kinds-<rôle>` tirée de `PARTY_KINDS`, saisie libre acceptée), le courriel et le téléphone ; *+ Ajouter une partie* clone la dernière ligne, ✕ la retire (la dernière ligne est vidée, jamais supprimée) ; trois lignes vides (TER, INS, PRE) par défaut ; sans JavaScript, toutes les colonnes restent visibles et saisissables |
| Actions | *Créer l'escale en brouillon* (POST) → message « Escale \<réf> créée en brouillon : renseignez les données du navire, puis déclarez-la » et redirection vers la fiche ; *Annuler* → liste |
| Règles | référence `<PORT>-<année>-<numéro sur 4 chiffres>` (compteur annuel du port) ; le module MA2 est ajouté de lui-même pour une bouée, MA3 pour une rade ou une zone STS ; les gabarits sont pris à leur version publiée et la combinaison zone / opérations / modules est contrôlée (`_check_templates`) ; l'étape 1 de l'escale est créée avec la zone et les opérations demandées ; parties automatiques : l'agence (AGE) puis les parties par défaut du port (capitainerie, autorité portuaire, douanes-immigration-santé, sûreté, services nautiques…) ; une organisation nouvelle est créée dans le port avec le seul rôle donné, sa nature normalisée (`normalize_kind` : un libellé connu en FR ou EN devient son code, un libellé libre est conservé tel quel), son courriel en minuscules, et l'acte `organization.created` est inscrit au journal du port (visible CAP, APO, DIR, AGE) ; un nom déjà enregistré (sans distinction de casse) est réutilisé s'il porte le rôle, refusé sinon (*… est enregistrée dans le port sans le rôle … : demandez à l'administrateur du port*), refusé aussi s'il est inactif ; une ligne *nouvelle organisation* sans nom est refusée (*Nommez l'organisation que vous invitez*) ; une ligne sans organisation ni nom est ignorée ; l'agence n'invite que TER, INS, COM, PRE et SVC — une autorité nouvelle est invitée par la capitainerie depuis l'onglet Parties ; une partie sans compte reçoit son propre accès par courriel à la déclaration (lien à remettre par QR ou impression si elle n'a pas de courriel) |
| États | toute erreur revient sur le formulaire avec les valeurs saisies : navire absent (*Choisissez un navire ou enregistrez-en un nouveau*), poste incompatible avec la zone, escale partenaire d'une autre agence (*la capitainerie relie les escales de deux agences*), organisation sans nom ou sans le rôle |

*Capture d'écran : Annonce d'escale — un terminal enregistré, un laboratoire et un avitailleur nouveaux — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.4 Fiche d'escale : en-tête, frise de passage, onglets Aperçu et Tâches

### La fiche — `/escales/<id>/?tab=<onglet>`

|  |  |
| --- | --- |
| Accès | un compte dont l'organisation tient un rôle actif sur l'escale, ou le titulaire d'un lien de cette escale (`account_or_master`) ; toute autre personne reçoit 404 ; un brouillon n'est visible que de l'agence et du capitaine |
| Objet | la page unique de l'escale : tout ce qui la concerne, pour chaque partie selon ses droits ; chaque ouverture d'onglet est inscrite au journal des accès (`view`, détail = onglet) |
| En-tête (`callhead`) | référence et numéro de voyage ; nom du navire ; IMO, pavillon, type, agence, poste attribué (code et nom) ou zone demandée ; produit et quantité (vue complète seulement) ; chip de statut ; codes des gabarits appliqués ; lien *Partenaire : \<navire>* quand l'escale est reliée ; boutons *Appli terrain*, *Rapport des faits* (vue complète), *Formulaires*, *Export* (COM, DIR) |
| Frise de passage (`build_strip`) | de l'arrivée (ATA ou ETA) au départ (ATD, ETD, sinon T1 + 6 h, sinon arrivée + 48 h) ; segments *attente* (ATA → ATB), *à quai* (ATB → T0 et T1 → ATD), *transfert* (T0 → T1), *interruption* (hachuré, un segment par arrêt déclaré avec sa cause), *à venir* ; repères ATA, NOR, ATB, T0, T1, ATD (ou leur estimation, suffixe *est.*) espacés d'au moins 7 % ; trait *maintenant* ; légende ; masquée pour un prestataire seul |
| Ancrages (`dl.anchors`) | six repères : Arrivée / ETA, NOR, Amarré / ETB, T0, T1, Départ / ETD — une estimation est grisée, un temps manquant vaut — |
| Onglets | Aperçu, Tâches (compteur des tâches en attente), Jalons, Demandes, Documents, Mesures, Contestations (compteur des contestations ouvertes), Échanges, Journal, Parties ; un prestataire seul (PRE) ne voit que Aperçu, Tâches, Jalons, Demandes, Documents, Échanges (`can_see_full_call`) ; le capitaine et une partie convoquée par lien ont les mêmes onglets que leur rôle ; l'onglet courant porte `aria-current` ; un onglet inconnu ramène à Aperçu |
| Refus | un refus de point d'arrêt rencontré par une action s'affiche en tête de la fiche (`_refusal.html`) après la redirection, une seule fois (`pop_refusal`) |
| Assistance | quand l'assistance EF-17 est activée pour le port et le rôle, `apps.ai.views.tab_context` ajoute à l'onglet des propositions marquées comme telles (revue assistée, remarques préremplies) — jamais une écriture au registre |

### Onglet Aperçu — `?tab=apercu`

|  |  |
| --- | --- |
| Colonne principale | **Ce que la plateforme refusera — et pourquoi** (vue complète) : huit transitions — Déclaration, Feu vert, Attribution du poste, Autorisation de mouvement, Accostage, Début du transfert, Autorisation de départ, Clôture — évaluées à l'instant par `holdpoints.evaluate` : chip *Ouverte* ou *Bloqué* avec la liste des tâches bloquantes manquantes (code, intitulé, rôle responsable) et des raisons (autorisation expirée, contestation ouverte, mesure incomplète…) ; **Revue assistée** (si activée) : bouton *Revoir l'escale avec l'assistant*, constats de règles et constats de l'assistant avec gravité, bouton *Signaler comme alerte* (confirmation) ; **Vos tâches ouvertes sur cette escale** : jusqu'à 8 tâches en attente des rôles de la personne (code, intitulé, nature, délai, échéance, chips d'alerte et *Bloquante*), lien *Toutes vos tâches* → onglet Tâches filtré ; **Notice of readiness** quand elle a été remise : date, émetteur, état par rôle (contresignée, en attente, contestée, tacite) ; **Étapes de l'escale** (vue complète) : une ligne par étape (ordre, zone et poste, opérations, fenêtre prévue, amarré, quitté, état *courante* / *planifiée* / *faite* / *annulée* avec motif) |
| Colonne latérale | **Agence** (AGE) : *Déclarer l'escale* (brouillon ; confirmation ; exige M0:02, M0:03, M0:05), *Réviser les heures* (ETA, ETB, début et fin des opérations, ETD, motif → échéances recalculées), *Produire le rapport des faits* (opérations terminées ou navire parti ; remarques de l'agence, préremplissage par l'assistant signalé par une étiquette et un champ `remarks_assisted`), *Demander la clôture* (navire parti), *Annuler l'escale* (brouillon à planifiée ; motif ; confirmation), *Relier une escale partenaire* (référence, lien STS / extérieur / intérieur) ; **Capitainerie** (CAP) : *Clore l'escale* (navire parti ; refusé tant qu'une contestation est ouverte ou que le rapport des faits n'est pas signé), *Archiver* (escale close) ; **Parties** (vue complète) : une ligne par organisation avec ses chips de rôle ; **Dépôt confidentiel de sûreté** (AGE, NAV, SUR, CAP, escale non close) : nature (gardes armés, escorte, plan de sûreté, incident, autre), nombre de gardes, société, embarquement, débarquement, escorte, détails → espace sûreté chiffré, rien dans la fiche ni le journal |
| Actions (`POST /escales/<id>/action/…`) | `declare`, `estimates`, `statement`, `close_request`, `cancel`, `link`, `close`, `archive`, `stage_add`, `stage_cancel`, `secure_deposit` ; assistance : `ai:review`, `ai:raise_alert`, `ai:remarks` |
| Règles | *Planifier l'étape suivante* (AGE, CAP ; escale ni close ni partie) crée aussitôt les tâches des nouvelles opérations pour toutes les parties ; quitter l'étape courante est un déhalage enregistré par les services nautiques sous autorisation de mouvement en vigueur ; une étape planifiée s'annule avec motif |
| Variantes | téléphone (C02) : colonnes empilées, frise et ancrages conservés ; anglais, port de Freetown (C03) : mêmes écrans, libellés EN, fuseau et références SLFNA ; plusieurs étapes (C06) ; escale déclarée (C07) ; escale close (C08) ; escale acceptée puis planifiée (C09) |

*Capture d'écran : Aperçu — escale en opération, vue de l'agence — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — téléphone — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — en anglais, port de Freetown — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — escale en plusieurs étapes — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — escale déclarée — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — escale close — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Aperçu — escale acceptée et planifiée — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Tâches — `?tab=taches` et `?tab=taches&mine=1`

|  |  |
| --- | --- |
| Objet | la liste de contrôle vivante de l'escale : chaque tâche instanciée des gabarits, par gabarit, avec son rôle, son échéance, son état et l'action qui la fait avancer |
| Visibilité (`rights.visible_tasks`) | l'agence et la capitainerie voient toutes les tâches ; un autre rôle voit les tâches de ses rôles, celles qu'il cosigne et les tâches *ANY* ; un prestataire seul ne voit que les siennes ; lien *Seulement mes tâches* / *Toutes les tâches que je peux voir* |
| Composants | un tableau par gabarit (ligne de section = code du gabarit, *Ad hoc* pour les tâches ajoutées) : # (numéro M0:12), tâche (intitulé, section, motif de non-application, note d'exécution), rôle (chip, cosignataires, *signature conjointe — signé : …*), échéance (heure et règle de délai, ex. *ETA − 24 h*), état (chip *À faire* / *Faite* / *Non applicable* + alerte *Bientôt due* / *En retard* / *Escaladée* + *Bloquante*), action |
| Actions | selon la nature de la tâche et le rôle : *Par sa demande* → onglet Demandes avec le type présélectionné ; *Enregistrer le jalon* → onglet Jalons ; *Fournir le document* → onglet Documents avec tâche et type présélectionnés ; *Signer* (`task_sign`, signature conjointe, un rôle à la fois) ; *Marquer faite* ou *Décider* (`task_complete`, note facultative ; natures C, R, D sans demande, jalon ni document liés ; jamais pour COM) ; *Non applicable* (`task_na`, motif obligatoire et tracé, rôles autorisés par `na_roles`, escale non close) ; *Ajouter une tâche ad hoc* (AGE, CAP ; `task_adhoc` : intitulés FR et EN, rôle, ancrage ETA/ETB/ATB/T0/T1/ATD et décalage en heures ; explicitement marquée, jamais bloquante) |
| Règles | les tâches sont affectées à des rôles, jamais à des personnes ; une tâche bloquante ne peut venir que des gabarits du port ; une tâche liée à une demande, un jalon ou un document n'est close que par cet objet (le bouton renvoie vers lui) ; chaque signature, exécution ou non-application est un acte du journal |
| Variantes | capitainerie (C04) : toutes les tâches ; terminal (C05) : ses tâches et celles qu'il cosigne, formulaires d'action dépliés |

*Capture d'écran : Tâches — vue de la capitainerie — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Tâches — vue du terminal, formulaires d'action dépliés — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.5 Onglets Jalons, Demandes et Documents

### Onglet Jalons — `?tab=jalons`

|  |  |
| --- | --- |
| Objet | la chronologie contradictoire de l'escale : un émetteur par jalon, les autres parties contresignent ou contestent ; le silence devient une contresignature tacite après le délai du port, jamais un accord |
| Visibilité (`rights.visible_milestones`) | toutes les parties voient tous les jalons ; un prestataire seul ne voit que les siens et, s'il parle pour la terre, ceux qu'il doit contresigner |
| Colonne principale | tableau : heure déclarée (et heure système `sys.` d'enregistrement), jalon (libellé du type, cause et motif d'une interruption, note, chips *saisie différée*, *rectification*, *saisie concurrente — contestation ouverte*, *enregistré par la plateforme*), émetteur (nom, organisation, rôle), contresignatures (une chip par rôle attendu : *contresigné* / *en attente* / *contesté* / *tacite*), actions |
| Actions | *Contresigner* (`countersign`, pour un rôle attendu dont l'état est *en attente*) ; *Contester* (`countersign` avec `contest=1`, motif obligatoire ; rôles contestataires du type ou `*`, jamais l'émetteur) ; **Enregistrer un jalon** (colonne latérale, `milestone`) : type (les types actifs du port que le rôle émet ; les jalons d'origine ATA/NOR/ATB… pour les rôles d'origine sauf COM ; un type gardé par un point d'arrêt porte `data-hold`), heure déclarée (heure du port, préremplie à maintenant), cause d'interruption (liste fermée du port ; le motif libre devient obligatoire pour *Autre*), interruption que ce jalon termine (quand des arrêts sont ouverts), note, case *Ressaisie depuis la procédure papier* (marquée différée) ; bouton *Ouvrir l'appli terrain* |
| Règles | un terminal ou un prestataire qui ne parle pas pour la terre ne contresigne ni ne conteste en son nom (`speaks_for_shore`) ; un jalon gardé par un point d'arrêt est refusé avec la tâche manquante nommée et le refus reste au journal ; deux heures déclarées par deux parties pour le même jalon = saisie concurrente et contestation ouverte d'office ; un jalon ne se corrige pas : une rectification est un nouveau jalon lié à l'ancien |

*Capture d'écran : Jalons — vue du terminal — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Demandes — `?tab=demandes` et `?tab=demandes&type=<code>`

|  |  |
| --- | --- |
| Objet | les demandes et autorisations de l'escale : le rôle demandeur ne décide jamais ; chaque approbation produit une autorisation avec une validité et un code de vérification public |
| Visibilité (`rights.visible_requests`) | selon la confidentialité de la demande : N1 = toutes les parties sauf INS et PRE ; N2 = AGE, CAP, DIR ; N3 = personne d'autre — plus, toujours, le demandeur, les rôles décideurs et l'exécutant du type ; une demande de contrôle d'acceptabilité (vetting) est aussi visible de l'armateur ; INS n'a aucun droit sur les demandes ; un prestataire ne voit que ses demandes et les ordres de service qu'il exécute |
| Colonne principale | une carte par demande : type, référence, niveau de confidentialité, demandeur et date de soumission, rôles qui décident, rôle qui exécute et prestataire désigné ; chip d'état (*Créée*, *Soumise*, *En instruction*, *Complément demandé*, *Approuvée*, *Approuvée sous conditions*, *Refusée*, *Planifiée*, *Exécutée*, *Annulée*, *Expirée*) ; les champs saisis (`dl.facts`, selon le schéma du type) ; la décision (rôle, date, conditions, motif — le motif d'un refus de vetting n'est montré qu'à l'agence, à l'armateur et au service instructeur) ; l'autorisation (numéro, état calculé à l'affichage *valide* / *expirée* / *annulée* / *pas encore en vigueur*, valide jusqu'au, poste, code de vérification → `/verifier/<code>/`) |
| Actions | *Décider* (`request_decide`, rôles décideurs du type, jamais le demandeur ; confirmation *Cette décision engage le port* ; décision Approuver / Approuver sous conditions / Demander un complément / Refuser ; poste ou zone attribué pour un type qui attribue un poste ; effet et validité (défaut = heures de validité du type) ; conditions ; motif obligatoire pour un refus ou un complément ; **second facteur exigé** : sans session forte, le lien le dit et la décision est renvoyée vers la vérification) ; *Prendre en instruction* (`request_review`) ; *Confirmer la prestation* (`request_schedule` : heure prévue ; `request_execute` : réalisée) pour le rôle exécutant ; *Nommer le prestataire* (`request_provider`, demandeur, quand plusieurs prestataires tiennent le rôle) ; *Soumettre à nouveau* (`request_submit`, après un complément) ; *Annuler* (`request_cancel`, motif) ; **Nouvelle demande** (colonne latérale) : liste des types que le rôle peut demander (`data-autosubmit`, bouton *Choisir* sans JavaScript) puis le formulaire du type (`request_create`) généré de son `form_schema` — champs texte, zone de texte, liste, date-heure, nombre, case à cocher, obligatoires marqués \* — et le prestataire à désigner quand plusieurs tiennent le rôle |
| Règles | une tâche liée à une demande se clos par la décision ; l'autorisation est l'acte écrit : numéro, validité, conditions, code public ; une autorisation expirée ne vaut plus pour les points d'arrêt (ex. accostage sous autorisation de mouvement échue) ; chaque décision est journalisée avec son rôle et sa session vérifiée |
| Variantes | décideur (D02) : formulaires de décision ; demandeur (D03) : ses demandes, annulation et nouvelle demande ; formulaire d'un type (D04) : `?type=BERTH`, demande de poste |

*Capture d'écran : Demandes — vue du décideur (capitainerie) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Demandes — vue du demandeur (agence) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Demandes — formulaire d'un type de demande — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Documents — `?tab=documents`

|  |  |
| --- | --- |
| Objet | les pièces de l'escale : fournies par les parties ou émises par la plateforme (formulaires standards) ; chaque fichier a son empreinte SHA-256 ; un document signé est figé — un changement crée une nouvelle version, l'ancienne reste lisible |
| Visibilité (`rights.visible_documents`) | l'émetteur voit toujours sa pièce ; N1 = tout rôle lecteur de documents ; N2 = AGE, CAP, DIR, COM, les signataires requis et l'audience du type ; N3 = l'émetteur et le rôle contrepartie ; un prestataire seul ne voit que ce qu'il a émis |
| Colonne principale | tableau : document (titre → ouverture en ligne, version `vN`, niveau, type, nom du fichier d'origine, empreinte abrégée avec l'empreinte complète en info-bulle, chip *saisie différée*), émetteur (nom, organisation, rôle, date), état (*Émis*, *Signé*, *Remplacé*, *Annulé*), signatures (✓ signataire et rôle ; *requis : …*), actions |
| Actions | *Télécharger* (`/escales/<id>/documents/<id>/`, journalisé) ; *Signer* (`document_sign`, rôle signataire requis non encore signé ; signature manuscrite facultative sur `canvas.sigpad`, attachée à l'empreinte exacte de la version) ; *Nouvelle version* (`document_upload` avec `previous_id`, émetteur seulement, pièce non générée, escale non close) ; *Lire avec l'assistant* / *Vérifier les valeurs lues* (assistance EF-17, pièces extractibles : proposition de valeurs, rien n'est enregistré sans validation) ; **Formulaires standards** (colonne latérale) : les formulaires offerts à la partie pour cette escale (aperçu) et *Tous les formulaires de l'escale* ; **Fournir un document** (`document_upload`) : tâche liée (ses tâches documentaires en attente, présélectionnée par `?task=`), type (les types non générés que le rôle émet, présélectionné par `?type=`), titre facultatif, confidentialité (défaut du type, N1, N2, N3) et contrepartie N3, fichier |
| Règles | le connaissement ne peut être émis avant les instructions documentaires écrites du donneur d'ordre et une quantité convenue — aucun rôle ne lève ce verrou (`BL_ISSUE`) ; fournir la pièce d'une tâche documentaire clot la tâche ; une pièce générée par la plateforme n'est pas remplaçable par un fichier : on la réémet depuis son formulaire (nouvelle version) ; **dépôt automatique** : la plateforme dépose elle-même, sous le rôle de l'auteur de l'acte, l'acte écrit de chaque décision (autorisation, approbation sous conditions, refus — feu vert, poste, mouvement, libre pratique, formalités, autorisation de départ…) avec la confidentialité et les lecteurs de la demande, la notice de disponibilité dès qu'elle est remise (`NOR_TENDERED`) et le time sheet avec le rapport des faits (`forms.auto_issue`) ; les autres formulaires sont émis par leur partie depuis la page Formulaires |

*Capture d'écran : Documents — vue de l'agence : les actes des décisions et la NOR, déposés par la plateforme — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.6 Onglets Mesures, Contestations, Échanges, Journal et Parties

### Onglet Mesures — `?tab=mesures`

|  |  |
| --- | --- |
| Objet | les quantités bord, terre et inspecteur de chaque mesure, et le relevé de pompage ; la plateforme calcule les écarts et ne désigne jamais une valeur de référence |
| Visibilité | matrice `measurement`, verbe V : AGE, NAV, TER, CAP, INS, COM, DIR ; les autres rôles voient *Les quantités ne sont pas visibles pour votre rôle* |
| Colonne principale | **Quantités — bord, terre, inspecteur** : une carte par mesure (nature : jaugeage initial, jaugeage final, OBQ, ROB, chiffre du connaissement, autre ; produit, unité, tolérance %) avec un tableau Bord / Terre / Inspecteur (valeur, température, densité, saisi par) et la colonne Écarts (chaque paire, écart absolu et %, chip *dans la tolérance* / *hors tolérance* pour bord − terre ; chip *valeur bord ou terre manquante — bloque la clôture*) ; **Relevé de pompage** : heure, pression manifold (bar), débit (m³/h), température, saisi par (rôle ; chips *automatique*, *différé*) |
| Actions | *Saisir ma valeur* (`measurement_value` : partie — bord pour NAV, terre pour TER, inspecteur pour INS — quantité, °C, densité ; préremplissage du chiffre du connaissement par l'assistant signalé et marqué) ; *Contester cette quantité* (`dispute_open` ciblé MEASUREMENT : contrepartie, exposé — le connaissement reste verrouillé tant que la contestation n'est pas close) ; **Ouvrir une mesure** (INS, TER, NAV ; `measurement_open` : nature, unité) ; **Ajouter un relevé de pompage** (TER, NAV ; `pumping` : heure, bar, m³/h, °C) |
| Règles | chaque partie saisit son propre chiffre, une nouvelle saisie de la même partie remplace la précédente en gardant l'historique ; une mesure sans valeur bord ou terre bloque la clôture ; l'écart bord − terre est comparé à la tolérance du port |

*Capture d'écran : Mesures — vue de l'inspecteur — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Contestations — `?tab=contestations`

|  |  |
| --- | --- |
| Objet | les contestations de l'escale : elles n'arrêtent jamais l'opération et la plateforme ne tranche jamais ; les parties répondent et closent, avec ou sans accord ; une contestation ouverte empêche la clôture de l'escale |
| Visibilité | l'en-tête (objet, référence, ouvreur, contrepartie, état) pour tout rôle lecteur de contestations ; les exposés sont bilatéraux (N3) : les deux parties et la capitainerie ; un prestataire ne voit que les siennes |
| Colonne principale | une carte par contestation : objet, référence, ouverte par (rôle), contrepartie, date, mention *ouverte par la plateforme (saisies concurrentes)* ; chip *Ouverte* / *Répondue* / *Close* ; fil des écritures (nature, auteur, rôle, heure, texte) ou la mention de confidentialité |
| Actions | *Répondre* (`dispute_respond`, contrepartie, ou ouvreur quand elle est répondue) ; *Clore* (`dispute_close` : l'ouvreur choisit *avec accord* / *sans accord* ; la capitainerie n'enregistre qu'une fin sans accord — un accord appartient aux parties ; texte obligatoire) ; **Ouvrir une contestation** (colonne latérale, rôles ouvreurs, escale non close ; `dispute_open` : porte sur *un autre sujet* ou *les quantités* (connaissement verrouillé), objet, contrepartie, exposé) — pour un jalon, le bouton *Contester* de la chronologie rattache la contestation au jalon |
| Règles | cibles possibles : jalon, tâche, mesure, document, demande, autre ; une contestation sur les quantités maintient le verrou du connaissement ; chaque écriture est journalisée |

*Capture d'écran : Contestations — vue du terminal — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Échanges — `?tab=echanges`

|  |  |
| --- | --- |
| Objet | la correspondance de l'escale : chaque échange est rattaché à l'escale et, si possible, à un objet ; il n'y a pas de messagerie libre |
| Visibilité (`rights.thread_visible`) | le côté créateur (son organisation) et les rôles invités ; N1 = toutes les parties sauf un prestataire non invité ; N2 = participants et direction ; N3 = les deux parties |
| Colonne principale | une carte par fil : objet, niveau, chips des rôles participants, résumé de l'assistant (marqué *à vérifier contre les messages*) quand il a été demandé, fil des messages (auteur, rôle, heure, texte), champ de réponse |
| Actions | *Envoyer* une réponse (`thread_post`, rôles rédacteurs, escale non close) ; **Nouvel échange** (`thread_create` : objet, rôles destinataires (cases), confidentialité N2 par défaut / N3 bilatéral / N1 toutes les parties, message) ; *Résumer avec l'assistant* (`ai:summarize`) |
| Règles | un fil N3 n'admet qu'une autre partie ; les messages sont horodatés et immuables ; l'ouverture d'un fil et chaque message sont des actes du journal visibles des seuls participants |

*Capture d'écran : Échanges — vue de l'agence — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Journal — `?tab=journal`

|  |  |
| --- | --- |
| Objet | la preuve : chaque acte, refus et alerte de l'escale, dans l'ordre, chacun portant l'empreinte du précédent (chaînage SHA-256) |
| Visibilité (`journal.entry_visible`) | chaque entrée porte ses rôles lecteurs ; un prestataire ne lit que ce que son organisation a fait et les ordres de service qu'il exécute ; les entrées d'un échange ou d'un document suivent la visibilité de l'objet |
| Composants | chip *Chaîne intacte — n entrées vérifiées* ou *Chaîne rompue à l'entrée s* (CAP, DIR ; `journal.verify_chain` sur tout le port) ; tableau : #, heure (à la seconde), qui (nom et rôle), quoi (résumé dans la langue de la page ; chip *refusé* pour un refus de point d'arrêt), empreinte abrégée (complète en info-bulle) ; 400 dernières entrées ; **Audit des accès** (CAP, DIR, SUR ; `AuditEntry`, 200 dernières) : qui a consulté, téléchargé ou exporté quoi |
| Règles | aucune action sur cet onglet : le journal est en ajout seul ; une entrée n'est jamais modifiée ni supprimée, la rupture serait détectée ; les dossiers de sûreté n'y apparaissent jamais |

*Capture d'écran : Journal — vue de la capitainerie — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Onglet Parties — `?tab=parties`

|  |  |
| --- | --- |
| Objet | les rôles tenus sur l'escale — datés, révocables — et les accès sans compte (capitaine, parties convoquées) |
| Visibilité | toute partie de l'escale (vue complète) ; la gestion (inviter, révoquer, désigner, émettre un accès) est réservée à l'agence et à la capitainerie |
| Colonne principale | **Rôles sur cette escale** : tableau organisation (mention *(partie par défaut du port)*, nature de l'organisation), rôle (code et libellé ; chip *parle pour la terre* ; bouton *Désigner pour la terre* quand plusieurs organisations tiennent le même rôle TER ou PRE), depuis, état (*active* / *révoquée* avec heure et motif), action *Révoquer* (motif obligatoire) ; **Inviter une partie** (escale non close) : le même composant que l'annonce, à une ligne — rôle (l'agence : TER, INS, COM, PRE, SVC ; la capitainerie : tous les rôles), organisation enregistrée (filtrée sur le rôle) ou *— nouvelle organisation —* avec nom, nature (suggestions du rôle, saisie libre), courriel, téléphone ; bouton *Inviter* |
| Colonne latérale (AGE, CAP) | **Accès du capitaine** : le capitaine n'a pas de compte ; l'agence émet un lien ou un code limité à l'escale, valide jusqu'au départ (`master_link` : nom du capitaine, remis par courriel / QR / impression / SMS / autre, navire concerné (ce navire, navire intérieur en accostage à couple), note de remise) ; après émission, lien, code et QR sont **affichés une seule fois** (`fluxaa_new_master_link` en session) ; liste des liens (nom, canal, expiration, dernier usage, *Révoquer* / *révoqué* / *expiré*) ; **Accès des parties sans compte** : à la déclaration chaque partie sans compte reçoit son lien par courriel, valide jusqu'à la clôture, le titulaire donne son nom au premier usage ; émission manuelle (`party_link` : partie TER / INS / COM / PRE / SVC, nom du titulaire facultatif, canal) ; liste des liens (organisation, rôle, titulaire ou *nom demandé au premier usage*, *émis à la déclaration → adresse* ou canal, échéance, dernier usage, *Révoquer*) |
| Actions | `party_add`, `party_revoke`, `party_shore`, `master_link`, `master_revoke`, `party_link`, `link_revoke` |
| Règles | l'agence ne révoque que les parties qu'elle a invitées (jamais une partie par défaut du port), la capitainerie révoque toute partie ; révoquer un rôle retire l'accès aussitôt et conserve tout ce que l'organisation a saisi ; les rôles décideurs gardent toujours un compte avec second facteur — aucun lien n'est émis pour CAP, APO, ADM, SUR ; une organisation nouvelle est créée selon les mêmes règles qu'à l'annonce (`register_organization`) et reçoit aussitôt son lien si l'escale est déclarée |
| Variantes | parties d'une escale en opération (E05, formulaire d'invitation déplié sur *nouvelle organisation*) ; convocations d'une escale en plusieurs étapes avec liens émis à la déclaration (E06) |

*Capture d'écran : Parties — rôles, invitation d'une nouvelle organisation — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Parties — convocations et liens émis à la déclaration — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.7 Formulaires standards, rapport des faits, appli terrain

### Formulaires de l'escale — `/escales/<id>/formulaires/`

|  |  |
| --- | --- |
| Accès | toute partie de l'escale, compte ou lien (bouton *Formulaires* de l'en-tête ; onglet Documents) ; chaque ouverture est inscrite au journal des accès (`view`, `forms`) |
| Objet | chaque partie émet d'ici les documents que l'escale lui demande — les tâches « fournir un document » et les décisions sur les demandes qui lui sont adressées — dans une structure unique ; ce que le registre sait est prérempli, le reste est complété et signé sur le papier puis déposé comme version du même document |
| Catalogue | 76 formulaires (`services/forms/`) en onze familles, dans l'ordre d'émission : AGE agence maritime (13), NAV navire / capitaine (12), TER terminal / dépôt (9), CAP capitainerie (13, dont 12 des 17 actes d'autorisation partagés avec APO et ADM), APO autorité portuaire (1), ADM douanes, immigration, santé (4), SUR sûreté (3), SVC services nautiques (2), INS inspecteur et laboratoire (7), COM armateur / affréteur (4), PRE prestataires (8) ; le détail par formulaire est dans l'onglet *Formulaires standards* |
| Composants | en-tête de l'escale (référence → fiche, navire, statut, bouton *Documents*) ; **n formulaires que vous pouvez émettre sur cette escale** (`form_svc.available` : rôles de la personne ∩ rôles du formulaire, et formulaire offert par les gabarits de l'escale — `offered()` : sans condition, ou si l'escale porte l'un des gabarits du formulaire, ou si elle est reliée) ; tableau par famille (ligne de section = rôle émetteur) : formulaire (titre FR et EN, code, objet), *Répond à* (les tâches `M0:12` et demandes `REQ:<TYPE>` qu'il satisfait), standard de référence, signé par (rôles et qualités), déposé (version, état, date et émetteur du document généré → ouverture en ligne), actions ; **n formulaires émis par les autres parties de l'escale** : par famille, titre et standard — reçus comme documents de l'escale |
| Actions | *Aperçu / imprimer* → `/escales/<id>/formulaires/<code>/` (page A4 autonome, journalisée `form:<code>`) ; *Émettre et déposer* (`form_issue` : génère le formulaire depuis le registre et le dépose dans les documents de l'escale, empreinté, sous le rôle de la personne ; une émission suivante du même formulaire devient la version suivante du même document) |
| Règles | un formulaire n'est généré que par les rôles qui l'émettent et seulement si l'escale l'appelle (STS, soutage, travaux… ne sont pas offerts à une escale qui ne les comporte pas) ; le document déposé est généré (`generated=True`), porte son SHA-256, sa version et les signatures électroniques des rôles nommés ; le papier complété et signé est déposé comme nouvelle version ; le connaissement reste derrière son verrou (`BL_ISSUE`) même depuis cette page |
| Variantes | agence (F01), capitainerie (F01b), inspecteur (F01c) : chacun voit sa famille et celles des autres |

*Capture d'écran : Formulaires — vue de l'agence — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Formulaires — vue de la capitainerie, actes déposés — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Formulaires — vue de l'inspecteur — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Un formulaire — `/escales/<id>/formulaires/<code>/`

|  |  |
| --- | --- |
| Accès | les rôles émetteurs du formulaire, sur une escale qui l'appelle ; sinon 404 |
| Structure unique (`reports/form.html`) | 1. **bandeau d'en-tête** identique sur tous : port, titre FR / EN, standard de référence, numéro `<CODE>-<référence>-<nn>` et heure de génération UTC ; métadonnées navire / IMO / pavillon, escale et voyage, zone ou poste (et étape), arrivée ATA ou ETA ; introduction du formulaire ; 2. **corps** : sections du standard, de cinq natures — `fields` (champs préremplis ou à compléter, larges ou non), `table` (colonnes bilingues, lignes du registre puis lignes vierges), `checklist` (points de contrôle ISGOTT avec une case ☐ par colonne et remarques), `text` (paragraphes bilingues), `qr` (QR code SVG et adresse, pour la vérification publique d'un acte) ; note de section ; note de confidentialité ; 3. **signatures** : une colonne par rôle signataire (qualité, rôle, nom / date / heure) ; 4. **pied scellé** : généré depuis le registre par …, dernière écriture du journal n° et son empreinte, nombre de signatures électroniques enregistrées, numéro du formulaire |
| Mise en page | page autonome sans barre ni menu, A4 portrait (paysage pour le time sheet et les tableaux larges), styles d'impression (`@page`, coupures évitées dans les lignes et les signatures), heures en UTC |
| Exemples | liste de contrôle navire / terre `SSSCL` (ISGOTT 6e éd., chap. 25 ; NAV et TER ; répond à M0:28) — F02 ; time sheet `TIME_SHEET` (chronologie du registre, BIMCO ; AGE ; signé AGE, NAV, TER ; M0:37 ; paysage) — F03 ; notice de disponibilité `NOR` (AGE, NAV ; signée NAV, TER, COM ; M0:23) — F04, et la même sur une escale planifiée, vierge là où le registre ne sait pas encore — F05 ; acte d'autorisation *Feu vert* `AUTH_GREEN_LIGHT` (CAP ; répond à `REQ:GREEN_LIGHT` et M0:09 ; décision, conditions, validité, QR de vérification) — F08 ; certificat de quantité `QUANTITY_CERT` (API MPMS 11, 12, 17 ; INS ; offert pour M1, M2, M3) — F09 ; bordereau de réception des déchets `WASTE_RECEIPT` (MEPC.1/Circ.834, app. 3 ; PRE, signé PRE et NAV ; `REQ:WASTE_COLLECTION`, M0:32…) — F10 ; notification des eaux de ballast `BALLAST_NOTIFICATION` (BWM 2004, A.868(20) ; NAV ; M0:15, M5:5.02, M5:5.03), émise par le capitaine depuis son lien — F11 ; ordre de mouvement `MOVEMENT_ORDER` (A.960(23) ; SVC ; `REQ:MARINE_SERVICES`, M0:18) — F12 ; acte *Formalités douanières et d'immigration* `AUTH_CUSTOMS_IMMIGRATION` (ADM ; `REQ:CUSTOMS_IMMIGRATION`, M0:22) — F13 |

*Capture d'écran : Liste de contrôle navire / terre (ISGOTT) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Time sheet — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Notice de disponibilité — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Notice de disponibilité — escale planifiée, champs vierges — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Acte d'autorisation — feu vert, avec QR de vérification — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Certificat de quantité — inspecteur — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Bordereau de réception des déchets — prestataire — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Notification des eaux de ballast — émise par le capitaine — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Ordre de mouvement — services nautiques — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Acte d'autorisation — formalités douanières et d'immigration — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Rapport des faits — `/escales/<id>/rapport-des-faits/`

|  |  |
| --- | --- |
| Accès | toute partie en vue complète (pas un prestataire seul) ; journalisé (`view`, `statement`) |
| Objet | l'aperçu, à tout moment, du rapport des faits consolidé tel que la plateforme le générera (`reports.render_statement`) ; les faits viennent du registre seul |
| Sections | en-tête (navire, escale, port) ; Parties ; Étapes de l'escale ; Chronologie contradictoire (chaque jalon avec l'état de chaque contresignature, les saisies différées et tacites comptées) ; Interruptions (cause, imputation, durée) ; Time sheet (temps par imputation) ; Alertes émises (toutes, EF-6.4) ; Contestations ouvertes ; Remarques de l'agence (sous son nom, avec la mention *rédigées avec l'assistant* le cas échéant) ; Intégrité (dernière écriture du journal et son empreinte) |
| Émission | depuis l'Aperçu, *Produire le rapport des faits* (`statement`, AGE, après la fin des opérations) le dépose comme document `SOF` généré (tâche M0:36) ; le capitaine et le terminal le signent dans l'onglet Documents ; la clôture exige le rapport signé |

*Capture d'écran : Rapport des faits — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Appli terrain — `/escales/<id>/terrain/`

|  |  |
| --- | --- |
| Accès | toute partie de l'escale, compte ou lien (bouton *Appli terrain* ; onglet Jalons) ; les données viennent de l'API `GET /api/v1/calls/<réf>/field-bundle/` et repartent par `POST …/sync/` |
| Objet | saisir sur la jetée, sans connexion : jalons, contresignatures et contestations, relevé de pompage ; installable (manifeste `/manifest.webmanifest`, service worker `/sw.js`) ; cibles tactiles ≥ 44 px, boutons *big* |
| Composants | en-tête (référence, statut, navire, rôles, *Retour à l'escale*) ; barre d'état (chips *connecté* / *hors ligne*, *données enregistrées du …*, entrées en attente, entrées refusées ; bouton *Synchroniser maintenant* ; dernière synchronisation ; résultat) ; navigation Jalons / À contresigner / Relevé de pompage / Mes tâches / Sur cet appareil ; **Enregistrer un jalon** : interruptions ouvertes, grille des types que le rôle émet, formulaire (heure déclarée avec bouton *Maintenant*, cause et motif, interruption que ce jalon termine, note, photo par la caméra) ; **À contresigner** : chaque jalon en attente avec *Contresigner* (confirmation) ou *Contester* (motif obligatoire) ; **Relevé de pompage** (TER, NAV) ; **Mes tâches** (lecture seule, par échéance) ; **Entrées sur cet appareil** : la file locale avec l'heure du fait et l'heure d'enregistrement, et les résultats des dernières synchronisations |
| Règles | chaque entrée garde l'heure déclarée du fait et l'heure de sauvegarde sur l'appareil ; le registre ajoute la sienne à la réception et marque *saisie différée* les arrivées tardives ; une saisie concurrente n'écrase jamais l'autre — le registre ouvre une contestation ; une escale close refuse toute entrée ; *Quitter* (session de lien) purge les données hors ligne ; sans JavaScript, la page le dit et renvoie à la fiche |

*Capture d'écran : Appli terrain (téléphone) — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.8 Espace sûreté, notifications, vérification publique d'une autorisation

### Espace sûreté — `/surete/`, un dossier `/surete/<référence>/`, journal des accès `/surete/journal/`

|  |  |
| --- | --- |
| Accès | SUR et CAP du port (`n4_role`) ; tout autre compte reçoit 404 partout (règle S5 : l'existence de l'espace n'est pas révélée) ; menu *Espace sûreté* |
| Objet | gardes armés, escortes, plans de sûreté et incidents (N4) : stockés à part, dans la base `secure`, chiffrés avec leurs propres clés, jamais sur un tableau de bord ni dans un export ; chaque accès est journalisé nominativement |
| Liste (`secure/index.html`) | tableau des dossiers du port : référence `N4-<PORT>-<année>-<nnnn>` → dossier, nature (gardes armés, escorte navale, plan / déclaration de sûreté, incident, autre), escale, navire, dépôt, décision due, statut (*Soumis*, *En instruction*, *Approuvé*, *Approuvé sous conditions*, *Refusé*, *Exécuté*, *Clos*) ; bouton *Journal des accès* ; la consultation de la liste est elle-même journalisée (`LIST`) |
| Dossier (`secure/item.html`) | en-tête (nature, référence, navire, escale, déposé par et rôle, date, statut) ; **Demande** : les champs déchiffrés à la lecture (nombre de gardes, société, embarquement, débarquement, escorte, détails…) ; **Décision** (décision, modalités, par qui, quand) ; **Pièces jointes** (nom, SHA-256, téléchargement déchiffré) et ajout *Ajouter (chiffré)* ; colonne latérale pour SUR : **Décider et fixer les modalités** (dossier soumis ou en instruction ; Approuvé / Approuvé sous conditions / Refusé ; modalités ou motif obligatoires ; confirmation ; **session forte exigée** — sinon renvoi vers la vérification du second facteur) ; **Confirmations** : Embarquement, Débarquement (passe le dossier à *Exécuté*), Mesures anti-intrusion — chacune une fois |
| Journal des accès (`secure/log.html`) | #, heure, personne, rôle, action (`LIST`, `VIEW`, `DECIDE`, `CONFIRM`, `ATTACH`, `DOWNLOAD`…), dossier, *notifié* ; chaîné : une altération serait détectée ; un accès par un rôle autre que SUR (la capitainerie) est notifié à l'autorité de sûreté |
| Règles | le dépôt se fait depuis la fiche d'escale (*Dépôt confidentiel de sûreté*, AGE / NAV / SUR / CAP) et ne laisse aucune trace dans l'escale, son journal ni ses exports ; seule l'autorité de sûreté décide et confirme, la capitainerie lit ; les clés N4 (`FLUXAA_N4_KEYS`) sont distinctes de la clé de signature ; aucune API n'expose ces dossiers hors du dépôt (`POST …/secure-deposit/`) |

*Capture d'écran : Espace sûreté — liste des dossiers — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Dossier de sûreté — décision et confirmations — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Journal des accès de l'espace sûreté — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Notifications — `/notifications/`

|  |  |
| --- | --- |
| Accès | tout compte (cloche de la barre, compteur des non lues) |
| Objet | les notifications de la personne : toujours dérivées d'un acte ou d'une échéance d'une escale, jamais saisies à la main |
| Composants | liste des 200 dernières : titre (en gras tant que non lue) → lien vers l'objet, date, mentions *envoyée par courriel* / *SMS*, chip *Bloquante* ; bouton *Tout marquer comme lu* (POST) |
| Règles | les tâches bloquantes et les escalades partent toujours immédiatement, les tâches normales suivent le réglage *Récapitulatif quotidien* du compte ; les canaux (courriel, SMS, webhook) sont configurés par port ; rien de l'espace sûreté n'y transite sauf l'avis d'accès à l'autorité de sûreté |

*Capture d'écran : Notifications — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Vérification publique d'une autorisation — `/verifier/` et `/verifier/<code>/`

|  |  |
| --- | --- |
| Accès | public, sans compte (lien de la page de connexion, QR code imprimé sur chaque acte d'autorisation) |
| Objet | vérifier qu'une autorisation émise par le port existe et est en vigueur, sans accès au dossier de l'escale (EF-2.5) |
| Composants | champ *Code de vérification* (monospace, mis en capitales) et bouton *Vérifier* (GET) ; résultat : chip *En vigueur* / *Annulée* / *Pas en vigueur* ; autorisation (numéro), type, port, navire et IMO, émise par (libellé du rôle), validité de → à (UTC) ; sinon *Aucune autorisation ne correspond à ce code* |
| Règles | le code (`verification_code`) est propre à chaque autorisation, l'état est calculé à l'instant (`is_valid(now)`, annulation) ; rien d'autre de l'escale n'est révélé (ni cargaison, ni parties, ni demandes) ; le sceau (`seal`) de l'acte est tronqué à 16 caractères dans la réponse ; la page est aussi servie par l'API publique `GET /api/v1/verify/<code>/` |

*Capture d'écran : Vérification publique — saisie du code — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Vérification publique — résultat — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.9 Tableau AIS, statistiques, assistant du port, pilotage du paramétrage

### Tableau AIS — `/carte/`

|  |  |
| --- | --- |
| Accès | tout compte du port (menu *Tableau AIS*) ; l'ouverture est journalisée (`view`, `ais_board`) ; rafraîchi par HTMX toutes les 60 s (`/carte/` avec `HX-Request` renvoie le fragment `_board.html`) |
| Objet | les positions diffusées par les navires eux-mêmes, reçues sur les 24 dernières heures (`MAX_AGE_HOURS`) : elles informent, corroborent l'arrivée et le départ déclarés (une alerte, jamais une correction) et ne remplacent jamais un jalon saisi par son émetteur |
| Composants | en-tête (port, *n navires entendus*, heure, *n dans les eaux du port*, *n avec une escale*) ; **carte** (SVG `viewBox` dans la boîte des eaux du port : fond = extrait de carte du port s'il est configuré (`/carte/fond/`, PNG / JPEG / WebP vérifiés par leur contenu), carrés = postes, cercles = rades et zones STS, triangle orienté par navire avec son nom, classé ▲ à quai / en opération, △ attendu / en approche, ▽ parti, ◇ sans escale dans ce port ; légende et limites de la boîte) — sans boîte configurée, le tableau n'est qu'une liste et le dit ; **écarts entre l'image AIS et le registre** (`discrepancies`) : navire entendu dans les eaux du port sans arrivée enregistrée, navire entendu hors des eaux alors que l'escale est à quai, aucune position depuis plus de 6 h (`SILENT_HOURS`) pour une escale en cours, navire encore amarré plus d'une heure après le départ enregistré — chacun avec le lien de l'escale ; **tableau** : navire (MMSI, IMO), escale (référence et statut, ou *navire connu, pas d'escale en cours*), position en degrés et minutes décimales (chip *hors de la boîte*), vitesse / route, statut AIS, destination, dernier rapport et âge en minutes |
| Règles | un écart est une question pour la capitainerie et l'agence : le registre garde ce que ses émetteurs ont déclaré et eux seuls le rectifient ; un rapport de moins de 120 min (`FRESH_MINUTES`) décrit le présent ; seules les escales visibles de la personne sont rapprochées ; les positions viennent d'un récepteur ou d'un flux configuré (guide de déploiement §15), jamais saisies à la main |

*Capture d'écran : Tableau AIS — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Statistiques — `/statistiques/`

|  |  |
| --- | --- |
| Accès | DIR, APO, CAP, administrateur du port, superutilisateur (menu *Statistiques*) ; un superutilisateur d'une instance nationale choisit le port (`?port=CODE`) ; chaque consultation et chaque export sont journalisés (`view` / `export`, `statistics`, période) |
| Objet | les statistiques du port sur une période (EF-10.2 étendu) : chaque chiffre est recalculé à l'ouverture depuis le registre, rien n'est stocké ni ajusté ; les mois sont ceux de l'ETA pour les escales, de l'événement pour les décisions, contestations et signatures ; les brouillons ne comptent pas |
| Période | `from` / `to` (dates ; défaut : les 365 derniers jours) ; bouton *Afficher* ; bouton *CSV* (`?format=csv` : les mêmes tableaux, fichier `fluxaa-<PORT>-statistiques-<période>.csv`) |
| Sections | **tuiles** : escales de la période, terminées, annulées ou rejetées, tonnes déclarées (MT seulement), attente en rade moyenne et médiane, durée nette de transfert, séjour au port, délai de décision (et nombre) ; **Escales et quantités par mois** : quatre graphiques en barres SVG (`_bar_chart.html`, sans bibliothèque) — escales, tonnes, attente, transfert — et le tableau mensuel replié ; **Ce que le port a traité** : par modèle d'opération, par zone demandée, par produit, par poste (escales, heures à quai, taux d'occupation pour les quais et appontements) ; **Interruptions et temps morts** : nombre, heures, part à cause établie contradictoirement, par cause et imputation, par imputation ; **Décisions des autorités** : par type de demande et rôle décideur, décisions, refus, sous conditions, moyenne / médiane / plus long (h) ; **Contestations et contresignatures** : ouvertes, encore ouvertes, closes avec / sans accord, ouvertes automatiquement, jours pour clore ; réponses de contresignature, contresignées, tacites (%), contestées (%), par sujet ; **Saisies, documents et alertes** : jalons, saisies tardives, documents, alertes, jalons par source, alertes par nature ; **Tâches faites à l'heure, par rôle** (faites, à l'heure, bloquantes, bloquantes à l'heure) |
| Règles | une direction, une autorité ou une capitainerie ne compte que les escales qui lui sont visibles ; les délais décrivent le flux des demandes, pas une personne ; une interruption contestée garde sa cause déclarée jusqu'à la clôture de la contestation ; les dossiers de sûreté ne sont jamais comptés |

*Capture d'écran : Statistiques — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Assistant du port — `/assistant/`

|  |  |
| --- | --- |
| Accès | DIR, CAP, APO (`PORT_ROLES`) d'un port où l'assistance EF-17 est activée (`client.enabled_for`) ; sinon 404 ; menu *Assistant* ; chaque ouverture est journalisée (`view`, `assistant_port`) |
| Objet | un point de situation à la demande et des questions sur le registre, rédigés en clair ; l'assistant lit le registre comme la personne le voit, cite les escales, dit quand le registre ne montre pas quelque chose et n'approuve, ne signe, ne clot ni ne corrige jamais rien |
| Composants | **Point du port** : bouton *Préparer le point* / *Actualiser le point* (`action=brief`) ; texte daté (« écrit à … depuis le registre à cet instant ») ; **Interroger le registre** : question (600 caractères au plus, `QUESTION_MAX_CHARS`), bouton *Demander* (`action=ask`), réponse datée ; **Ce qui a été donné à l'assistant** (replié) : l'inventaire des objets fournis (rôles seulement, jamais une personne ; rien du domaine de sûreté) |
| Règles | réponses depuis les escales que la personne peut ouvrir, le tableau AIS et les indicateurs des 90 derniers jours ; rien n'est enregistré dans une escale ; chaque requête est tracée (`AssistantRun` : empreinte des données envoyées, inventaire, modèle) ; les résultats sont personnels et gardés en session seulement ; une indisponibilité du service revient en message d'erreur, jamais en page vide |

*Capture d'écran : Assistant du port — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Pilotage du paramétrage (calibrage) — `/pilotage/`

|  |  |
| --- | --- |
| Accès | administrateur du port et direction (DIR) ; menu *Pilotage* ; journalisé (`view`, `calibration`) |
| Objet | dire à l'administrateur quels gabarits, délais et seuils produisent du bruit ou des retards — les chiffres jugent le paramétrage, jamais les personnes (EF-6.5, ENF-8) |
| Composants | sélecteur de période `days` = 30 / 90 / 180 / 365 jours (`data-autosubmit`, bouton sans JavaScript) ; **Notifications reçues par personne et par escale** : moyenne, maximum, paires personne-escale au-dessus de 15 (cible EF-6), tâches escaladées ; **Alertes par gabarit d'escale** : escales, alertes, alertes par escale, par nature ; **Échéances et saisies par rôle** : tâches dues, en retard (%), retard moyen (h), jalons saisis, délai moyen de saisie (min, entre l'heure déclarée et l'enregistrement — ressaisies hors ligne et papier comprises) |
| Règles | seules les escales déclarées de la période comptent ; aucune action sur la page : le réglage se fait dans l'administration (gabarits, types de jalons, points d'arrêt, délais du port) |

*Capture d'écran : Pilotage du paramétrage — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

## 8.10 Administration et paramétrage — `/admin/…`

### Principes

|  |  |
| --- | --- |
| Accès | administrateur du port (`is_port_admin`) et superutilisateur ; menu *Paramétrage* ; toute autre personne reçoit la page de connexion de l'administration |
| Outil | l'administration Django, en-tête *FLUXAA Port — paramétrage*, index *Paramétrage du port / Port settings* ; deux blocs : **Organisation du port** (`core` : ports, organisations, utilisateurs, postes / zones) et **Registre des escales** (`registry` : abonnements webhook, causes d'interruption, gabarits d'escale, navires, parties par défaut, points d'arrêt, types de demande, types de document, types de jalon, versions de gabarit) |
| Cloisonnement (`PortScopedAdmin`) | chaque liste et chaque formulaire sont restreints au port de l'administrateur ; les listes déroulantes vers un autre objet ne proposent que ceux du port ; le superutilisateur voit tout |
| Second facteur | lire est permis avec un mot de passe ; **ajouter ou modifier exige une vérification récente du second facteur** (`_recent_second_factor`, ENF-3.1) — sinon le formulaire est en lecture seule |
| Suppression | **jamais** : aucun objet de paramétrage ne se supprime (`has_delete_permission` = faux) ; on désactive (`is_active`) ; une version de gabarit publiée est figée |
| Traçabilité | chaque création ou modification d'un compte est journalisée (`user.administered`, journal des accès) et notifiée par courriel à la personne avec les champs changés ; les autres modifications restent dans l'historique de l'administration Django (`LogEntry`) |

*Capture d'écran : Administration — accueil — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Port — `/admin/core/port/<id>/change/`

|  |  |
| --- | --- |
| Champs | identité (code, nom, pays, fuseau, langue par défaut, actif — code, pays et actif en lecture seule pour l'administrateur du port) ; **Délais et seuils** : délai de contresignature (min ; passé ce délai un jalon non contresigné vaut contresignature tacite, EF-3.4), délai de rappel (h), escalade après retard (min ; une tâche bloquante en retard l'est immédiatement), tolérance bord / terre (%), seuil d'écart AIS (min), heure du résumé quotidien ; **Accès capitaine** : validité du lien après le départ (h), validité maximale (jours) ; **Conservation et sûreté** : conservation (années), courriel de l'autorité de sûreté (reçoit les notifications d'accès N4) ; **Eaux du port — tableau AIS** : les quatre limites du cadre (degrés décimaux), fond de carte facultatif (PNG ou JPEG couvrant exactement le cadre), positions AIS conservées (jours) ; **Assistance IA (EF-17)** : activée, référence de l'accord du port — réservées au superutilisateur (décision de gouvernance de l'opérateur) |
| Règles | un port ne se crée que par le superutilisateur (`bootstrap_ports`) ; l'administrateur du port ne voit que le sien |

*Capture d'écran : Administration — paramètres du port — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Organisations — `/admin/core/organization/`

|  |  |
| --- | --- |
| Liste | nom, nom court, nature, rôles, courriel, téléphone, actif ; filtres actif et nature ; recherche sur le nom, le nom court et la nature |
| Formulaire | port, nom, nom court, **nature de partie** (champ libre avec la liste de suggestions `PARTY_KINDS`, non exhaustive ; un libellé connu est normalisé en son code), **rôles que l'organisation peut tenir** (cases), courriel, téléphone, actif |
| Règles | une organisation invitée à la volée depuis une annonce ou un onglet Parties arrive ici avec son seul rôle : l'administrateur la complète (autres rôles, coordonnées) ; désactiver une organisation empêche toute nouvelle invitation sans toucher aux escales passées |

*Capture d'écran : Administration — organisations — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Utilisateurs — `/admin/core/user/<id>/change/`

|  |  |
| --- | --- |
| Liste | nom, courriel, organisation, rôles, second facteur, administrateur du port, actif ; filtres actif / administrateur / second facteur / intégration |
| Formulaire | courriel (identifiant), mot de passe, nom complet, organisation (du port), rôles (cases, limités aux rôles que l'organisation peut tenir — règle 5), langue, téléphone ; **Administration** : actif, administrateur du port, compte d'intégration et périmètres (superutilisateur seulement) ; **Notifications et sécurité** : résumé quotidien seulement, second facteur activé, dernière connexion (lecture seule) |
| Règles | le second facteur ne s'active que par la personne elle-même depuis *Mon compte* (l'administrateur ne peut que le **réinitialiser** en décochant la case : secret effacé, acte journalisé, courriel à la personne) ; aucune suppression : on désactive ; chaque modification est journalisée et notifiée |

*Capture d'écran : Administration — utilisateur — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Postes et zones — `/admin/core/berth/`

|  |  |
| --- | --- |
| Liste | code, nom FR, nom EN, nature (quai / appontement, rade, bouée SPM / CBM, zone STS), LOA maximale, tirant d'eau maximal, récupération des vapeurs, actif ; filtres nature et actif |
| Formulaire | port, code, noms FR / EN, nature, limites (LOA maximale, tirant d'eau maximal, DWT maximal, limites météo), récupération des vapeurs, position (latitude, longitude, rayon en m pour une rade ou une zone) pour le tableau AIS, notes, actif |
| Règles | la nature d'un poste doit correspondre à la zone d'opération demandée ; les limites alimentent le formulaire *Limites du poste* et le contrôle d'acceptabilité |

*Capture d'écran : Administration — postes et zones — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Gabarits d'escale et versions — `/admin/registry/calltemplate/`, `/admin/registry/templateversion/<id>/change/`

|  |  |
| --- | --- |
| Gabarits | liste : code (M0, M1…M9, MA2, MA3), noms, nature (module / opération), version publiée, actif ; versions en ligne (numéro, état, publication, notes, lien) ; action *Créer une version brouillon (copie de la version publiée) à modifier* |
| Version de gabarit | gabarit, numéro, état (brouillon / publiée / retirée), publication, publiée par (lecture seule), notes ; **tâches du gabarit** en ligne, modifiables seulement en brouillon : numéro et ordre, section FR / EN, intitulés FR / EN ; *Qui et comment* : rôle, nature (F fournir, R renseigner, D décider, C confirmer, S signer), signature conjointe, rôles cosignataires ; *Échéance (toujours relative)* : ancrage (ETA, ETB, ATB, T0, T1, ATD…) et décalage en minutes, libellés de délai ; *Criticité* : criticité (bloquante / normale), confidentialité, fondement du blocage, non-application permise ; *Complétée par* (replié) : code de type de demande et côté, codes de jalons, code de type de document, événement automatique, continue, par navire, natures de poste ; action *Publier la version brouillon sélectionnée (les nouvelles escales l'utiliseront)* |
| Règles | une version publiée ne se modifie plus : on crée un brouillon, on le modifie, on le publie ; les escales en cours gardent la version qu'elles ont prise (`CallTemplateUse`) ; la publication est refusée si la version est incohérente (`publish_version` : codes de tâches uniques, rôles valides, références aux types existants) ; une tâche bloquante ne peut venir que d'ici |

*Capture d'écran : Administration — gabarits d'escale — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Administration — version de gabarit et ses tâches — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Types de jalons — `/admin/registry/milestonetype/`

|  |  |
| --- | --- |
| Liste | numéro, code, libellés FR / EN, rôle émetteur (ou *origine* pour ATA, NOR, ATB… saisis par les rôles d'origine ; *système* pour les jalons enregistrés par la plateforme), point d'arrêt, actif ; filtres actif et émetteur |
| Formulaire | port, numéro, code, libellés, émetteur, **contresignataires** (cases), rôles contestataires (`*` = tous), saisie terrain permise, point d'arrêt gardant le jalon, ancre d'escale alimentée (ATA, ATB, T0, T1, ATD…), ordre, actif |

*Capture d'écran : Administration — types de jalons — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Types de demandes — `/admin/registry/requesttype/`, `/admin/registry/requesttype/<id>/change/`

|  |  |
| --- | --- |
| Liste | code, libellés, rôles demandeurs, autorités décideuses, confidentialité, actif ; filtres actif et confidentialité |
| Formulaire | port, code, libellés et descriptions FR / EN, **rôles demandeurs** et **autorités décideuses** (cases — un rôle ne peut être les deux), rôle exécutant (ordre de service), confidentialité de la demande et du motif de refus, contrôle d'acceptabilité (vetting), attribue un poste, heures de validité de l'autorisation, **schéma du formulaire** (`form_schema`, JSON : clé, type texte / zone de texte / liste / date-heure / nombre / case, libellés FR / EN, obligatoire, options), ordre, actif |
| Règles | le schéma génère le formulaire de l'onglet Demandes et les champs du formulaire *Réponse à une demande* ; chaque type décidé a son acte d'autorisation (`AUTH_<CODE>`) dans le catalogue des formulaires ; INS n'est jamais demandeur ni décideur |

*Capture d'écran : Administration — types de demandes — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

*Capture d'écran : Administration — un type de demande et son schéma — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Types de documents — `/admin/registry/documenttype/`

|  |  |
| --- | --- |
| Liste | code, libellés, confidentialité par défaut, généré, connaissement, actif ; filtres actif et confidentialité |
| Formulaire | port, code, libellés, confidentialité par défaut (N1 / N2 / N3), **rôles émetteurs**, **signataires requis**, **lecteurs supplémentaires (N2)** (cases), conservation, ordre, actif ; *généré* et *connaissement* en lecture seule |
| Règles | le verrou du connaissement ne se paramètre pas (`is_bill_of_lading` figé) ; un type généré ne reçoit pas de fichier libre : ses pièces viennent des formulaires ; les rôles émetteurs d'un type doivent couvrir les rôles des formulaires qui le produisent (test automatique) |

*Capture d'écran : Administration — types de documents — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Points d'arrêt — `/admin/registry/holdpoint/<id>/change/`

|  |  |
| --- | --- |
| Liste | transition, tâches requises |
| Formulaire | port, transition (déclarer, feu vert, attribuer un poste, autorisation de mouvement, pilote à bord, accostage, début du transfert, accostage à couple, travaux à chaud, émission du connaissement, autorisation de départ, clôture…), **exigences** en ligne : gabarit et numéro de tâche bloquante requis (une ligne par tâche) |
| Règles | une transition par port ; l'évaluation (`holdpoints.evaluate`) nomme la tâche manquante et son rôle à chaque refus ; les règles non paramétrables (contestation ouverte, mesure incomplète, rapport des faits non signé, verrou du connaissement) s'ajoutent toujours |

*Capture d'écran : Administration — point d'arrêt — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Causes d'interruption — `/admin/registry/interruptioncause/`

|  |  |
| --- | --- |
| Liste | code, libellés, imputable à (navire, terre, tiers / externe, météo, ou aucune imputation), motif obligatoire, actif, ordre ; filtres imputation et actif |
| Règles | liste fermée proposée à la saisie d'une interruption (fiche et appli terrain) ; l'imputation alimente le time sheet et les statistiques de temps morts ; *Autre* exige un motif |

*Capture d'écran : Administration — causes d'interruption — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Abonnements webhook — `/admin/registry/webhooksubscription/`

|  |  |
| --- | --- |
| Liste | nom, adresse, actif, créé le |
| Formulaire | port, nom, adresse HTTPS, événements souscrits, actif ; **secret** généré et affiché en lecture seule (signature HMAC des livraisons, en-tête `X-Fluxaa-Signature`) |
| Règles | chaque livraison est tentée avec reprise ; le contenu suit le format de l'onglet API ; rien du domaine de sûreté n'est jamais livré |

*Capture d'écran : Administration — abonnements webhook — voir le catalogue des écrans (`fluxaa-port-ecrans.pdf`) ou l'onglet 2 de FLX-SPEC-003.*

### Autres écrans d'administration

Navires (`/admin/registry/vessel/` : nom, IMO, pavillon, type, DWT — complétés aussi à l'annonce), Parties par défaut (`/admin/registry/portdefaultparty/` : organisation et rôle invités automatiquement sur chaque escale — capitainerie, autorité, douanes-immigration-santé, sûreté, services nautiques ; jamais supprimées, désactivées par l'organisation), et, pour le superutilisateur, les ports et les comptes d'intégration.
