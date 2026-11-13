# Guide de paramétrage — administrateur fonctionnel du port

Tout ce qui suit se fait **sans livraison de code** (EF-16), dans l'écran **Paramétrage** (`/admin/`), accessible aux utilisateurs marqués « administrateur fonctionnel du port ». Chaque administrateur ne voit et ne modifie que **son** port. L'exploitant de la plateforme (superutilisateur) gère en plus la création des ports et l'activation de l'assistance IA.

Aucun écran de paramétrage ne permet de supprimer un enregistrement du registre, ni de modifier une escale, un jalon, un document ou une décision : ces objets ne se touchent que par l'application, où les droits s'appliquent.

> **Règle de prudence.** Un gabarit publié est figé ; une escale garde la version de gabarit en vigueur à sa création. On peut donc modifier les gabarits pendant que des escales sont en cours sans rien changer à celles-ci.

---

## 1. Seuils et délais du port

**Paramétrage › Ports › (votre port)**

| Paramètre | Défaut | Effet |
|---|---|---|
| Délai de contresignature | 120 min | passé ce délai, un jalon non contresigné devient « contresignature tacite » (EF-3.4) — jamais un accord |
| Délai de rappel | 24 h | rappel adressé au rôle assigné avant l'échéance |
| Escalade après retard | 240 min | une tâche normale en retard au-delà de ce seuil est escaladée ; une tâche bloquante en retard l'est immédiatement |
| Tolérance bord/terre | 0,300 % | au-delà, alerte de quantité et proposition de contestation (EF-8.2) ; depuis la 1.4, le même seuil s'applique à l'écart terre − bord du **journal de pompage**, horaire et cumulé : alerte en temps réel « arrêter pour investigation » aux lecteurs du journal |
| Seuil d'écart AIS | 30 min | au-delà, alerte (jamais de correction) |
| Heure du résumé quotidien | 7 h (heure locale) | envoi du résumé des notifications non urgentes |
| Validité du lien capitaine après le départ | 24 h | |
| Validité maximale du lien capitaine | 30 jours | |
| Validité maximale des liens des parties sans compte | 90 jours | lien d'un terminal, inspecteur, armateur, prestataire ou service nautique, émis à la déclaration : valable jusqu'à la clôture de l'escale, au plus ce nombre de jours |
| Validité par défaut d'une annonce | 15 jours | proposée à l'agence à l'annonce (1.5) ; elle la raccourcit ou l'allonge dans la limite du maximum ; conservée pour la facturation |
| Validité maximale d'une annonce | 90 jours | au-delà, l'annonce est refusée ; un séjour plus long fait l'objet d'une nouvelle annonce |
| Le tableau des escales montre la nature de la cargaison et le tonnage | coché | la conférence de placement et le plan d'occupation montrent le produit ou la nature de la cargaison et le tonnage, comme le tableau d'un port ; décoché, ils ne montrent que le navire, le consignataire, le poste, les opérations, l'état et les heures |
| Conservation | 10 ans | durée de conservation probante (PRO-MAR-001 §6.1) |
| E-mail de l'autorité de sûreté | — | reçoit les notifications d'accès aux dossiers N4 (sans détail) |

Le fuseau horaire et la langue par défaut se règlent ici aussi ; le code du port, le pays et l'activation de l'assistance IA sont réservés à l'exploitant.

**Carte des eaux du port (tableau AIS)** — les quatre limites du cadre (latitude sud et nord, longitude ouest et est), un fond de carte facultatif (PNG ou JPEG couvrant exactement ce cadre, dont le port détient les droits), et la durée de conservation des positions AIS (30 jours par défaut ; ce sont des données diffusées publiquement, pas des actes du registre). Sans cadre, le tableau AIS reste une liste. Sources de positions : DEPLOIEMENT.md §15.

## 2. Organisations, utilisateurs, rôles

**Organisations** — pour chacune, cochez les **rôles qu'elle peut tenir** (AGE, TER, INS, COM, PRE, SVC, ADM, SUR, CAP, APO, DIR). Une organisation peut en tenir plusieurs (l'autorité portuaire : CAP, APO, DIR). Sa **nature** dit ce qu'elle est dans les mots du port : une liste **non exhaustive** de natures est suggérée (`apps/core/parties.py` : agence, agent protecteur, terminal, dépôt, raffinerie, exploitant de bouée, pipeline, capitainerie, VTS, autorité portuaire, pilotage, remorquage, lamanage, vedettes, douanes, immigration, santé portuaire, autorité maritime, autorité environnementale, sûreté portuaire, marine nationale, gendarmerie maritime, inspecteur de cargaison, laboratoire, société de classification, expert P&I, inspecteur vetting, chimiste maritime, expert maritime, armateur, gestionnaire technique, affréteur, réceptionnaire, expéditeur, négociant, gestionnaire de garanties / banque, assureur, courtier, prestataire STS, fournisseur de défenses et flexibles, avitailleur, collecteur de déchets, nettoyage de citernes, eau douce, ship chandler, agence de relève, chantier, plongée, lutte antipollution, service incendie, gardiennage, transport, services médicaux, télécommunications…) et toute autre nature peut être écrite librement. Seul le rôle porte les droits ; la nature sert à reconnaître la partie (liste des parties, formulaires, exports).

**Liste ouverte des parties d'une escale.** L'agence (ou la capitainerie) invite sur une escale autant d'organisations qu'il en faut, dans les rôles TER, INS, COM, PRE et SVC (tous les rôles pour la capitainerie) : une organisation déjà enregistrée, ou une **nouvelle organisation** nommée à l'annonce ou dans l'onglet *Parties* avec sa nature, son courriel et son téléphone. Celle-ci est créée dans le port avec le seul rôle de l'invitation, active, et enregistrée au journal du port (`organization.created`) ; vous la complétez ou la corrigez ici (autres rôles, adresse, désactivation). Une organisation inactive, ou enregistrée sans le rôle demandé, n'est pas réinvitée sous un autre rôle depuis une escale : l'administrateur tranche. Une partie sans compte est convoquée par lien à la déclaration (à son adresse, ou par QR/impression).

**Utilisateurs** — rattachés à une organisation, avec les rôles qu'ils peuvent exercer. Les droits réels sur une escale sont l'intersection de ces rôles et des rôles que **l'organisation tient sur l'escale** : une personne n'a jamais de droit « par elle-même » (règle 5).

* La double authentification est imposée à la première connexion pour CAP, APO et SUR et pour tout administrateur (vous compris), et redemandée pour toute décision ; le paramétrage exige une vérification de moins de 8 heures.
* **Téléphone perdu** : décochez « double authentification activée » dans la fiche de la personne ; elle enregistrera une nouvelle application à sa prochaine connexion. Toute modification d'un compte (rôles, activation, mot de passe, second facteur) est inscrite au journal des accès et signalée par courriel à la personne.
* « Résumé quotidien pour les tâches normales » réduit le bruit ; les tâches bloquantes et les escalades restent en temps réel.
* « Compte d'intégration technique » et ses périmètres : réservés à l'exploitant, pour les systèmes tiers qui utilisent l'API.

**Parties par défaut** — les organisations invitées automatiquement sur toute escale du port (capitainerie, autorité portuaire, douanes-immigration-santé, sûreté, services nautiques). L'agence invite les autres (terminal, inspecteur, armateur ou affréteur, prestataires).

**Plusieurs organisations pour un même rôle sur une escale** (deux prestataires, l'armateur et l'affréteur, deux sociétés de remorquage…) : chacune ne lit, ne remplace, n'annule ou ne clôt que ce qu'elle a elle-même émis (documents, demandes, échanges, chiffres de mesure, contestations) ; une commande de service désigne l'organisation qui la réalise. Quand deux terminaux, ou plusieurs prestataires en mer, participent à une escale, l'agence ou la capitainerie désigne dans les *Parties* celui qui parle au nom du côté terre (jalons et chiffre terre, contresignature au nom de la terre) ; sans désignation, aucun ne le peut. Une commande passée avant l'arrivée de tout prestataire revient à celui qui rejoint l'escale s'il est seul de son métier ; à défaut, l'agence le désigne depuis l'onglet *Demandes*. Les tâches restent assignées au rôle (EF-5.2).

## 3. Postes et zones

**Postes / zones** — code, nom bilingue, type (`Quai / appontement`, `Rade`, `Bouée au large SPM/CBM`, `Zone STS au large`), **limites d'acceptation** (1.5 : longueur hors tout, tirant d'eau, port en lourd, largeur, déplacement, hauteur du collecteur au-dessus de l'eau, pied de pilote minimal, âge maximal du navire, SWL minimale des grues, tirant d'air maximal — chaque limite renseignée est comparée à la donnée du navire par la **grille de vetting** du formulaire `VETTING_CHECKLIST` ; une limite vide n'est pas évaluée), **conditions d'exploitation** (limites météo, par exemple `{"wind_kn": 25, "swell_m": 2.0}`, récupération des vapeurs, **natures de cargaison traitées** — vide = toutes, `["LIQUID"]` pour un appontement pétrolier, `["CONTAINER", "RORO"]` pour un terminal à conteneurs). Le type de poste choisit les tâches applicables (voir §4, « uniquement pour ces zones »). Les données de démonstration donnent aux postes des limites illustratives ; un port réel les remplace par les siennes.

**Lues à l'annonce** (1.6) — les limites d'acceptation et les natures de cargaison reçues sont comparées au navire dès que l'agence demande le poste (bloc de compatibilité du formulaire d'annonce) ; un poste sans limites renseignées n'évalue rien et le dit.

**Position sur le tableau AIS** — latitude et longitude du centre du poste ou de la zone, et rayon (m) pour une zone de mouillage ou STS. Un poste sans position n'est pas dessiné. Les positions livrées pour les ports pilotes sont indicatives (note « à confirmer ») : la capitainerie les corrige depuis sa carte.

## 4. Gabarits d'escale et tâches

**Gabarits d'escale** — M0 (socle commun), M1 à M8 (modèles d'opération du vrac liquide), MB1 et MB2 (déchargement et chargement de vrac sec), MC1 (conteneurs), MG1 (marchandises diverses et colis), MR1 (roulier), MX1 (toute autre escale : passagers, navire d'État, pêche, recherche, relâche), M9 et MA1 à MA3 (modules). Chaque gabarit porte ses **natures de cargaison** (1.5 ; vide = toutes) : l'annonce ne propose que les gabarits de la nature choisie. Un gabarit inactif n'est plus proposé à la création des escales.

**Fiche d'intention d'un gabarit** (1.6) — champ *Questions posées à l'annonce* (`intake_schema`) du gabarit, même grammaire que le formulaire d'un type de demande (§5 : `key`, `label_fr`, `label_en`, `type` text / textarea / number / integer / datetime / boolean / select, `required`, `options`, `help_fr`, `help_en`). Les fiches livrées (M1 à M9, MA3, MB1, MB2, MC1, MG1, MR1, MX1) s'installent à la création du port et à la mise à niveau 1.6 sur les gabarits qui n'en ont pas ; un port les adapte librement — une clé commune à la fiche d'un modèle et au formulaire d'une demande **que lèvent les tâches de ce modèle** préremplit cette demande (`grade`, `quantity_mt` de M4 → `BUNKERING` ; `volume_m3`, `method` de M5 → `BALLAST_DISCHARGE` ; `purpose`, `duration_h` de M9 → `DOUBLE_BANKING`…). La même clé dans la fiche d'un autre modèle n'est pas reprise : pour préremplir une demande depuis une fiche, donnez à la question la clé du champ **et** rattachez la demande à une tâche du modèle (`request_type` de la tâche du gabarit). Seule exception, les faits du navire déclarés une fois (`last_cargoes`), repris quel que soit le modèle. Les **parties qu'appelle chaque modèle** (proposées à l'annonce) et les **natures de parties** sont des catalogues du code (`apps/core/parties.py`), suggestions jamais limitatives.

Pour modifier un gabarit :

1. Sélectionnez-le dans la liste, action **« Créer une version brouillon »** : la version publiée est copiée.
2. Ouvrez **Versions de gabarit › (le brouillon)** et modifiez, ajoutez ou supprimez des tâches.
3. Revenez à la liste des versions, sélectionnez le brouillon, action **« Publier »**. La plateforme vérifie les règles ci-dessous et refuse la publication en expliquant pourquoi.

Champs d'une tâche :

| Champ | Règle |
|---|---|
| Numéro, ordre, section (FR/EN), tâche (FR/EN) | les deux langues sont saisies ici, pas dans le code (ENF-7) |
| Rôle responsable, nature, signature conjointe, rôles cosignataires | la tâche est assignée à un **rôle**, jamais à une personne ; une tâche conjointe n'est faite que lorsque chaque rôle a signé |
| Point d'ancrage + décalage, libellé de l'échéance | **toujours relatif** à ETA, ETB, ATB, T0, T1, ATD ou NOR (EF-5.3) ; une échéance absolue est refusée ; 60 jours au plus |
| Criticité, confidentialité, fondement du caractère bloquant | une tâche **bloquante** doit citer son fondement (point d'arrêt de la PRO-MAR-001 ou obligation réglementaire) |
| Peut être déclarée sans objet | si coché, « Sans objet » est proposé, avec motif obligatoire et tracé |
| Réalisée par… (repliable) | la tâche se ferme seule quand survient l'acte correspondant : dépôt ou décision d'une demande (`type de demande lié`), enregistrement de jalons, fourniture d'un type de document, événement de la plateforme (escale créée, déclarée) |
| Tâche continue | reste ouverte jusqu'à la fin du transfert (journal de pompage, interruptions) |
| Une par navire (×2) | pour STS et accostage à couple |
| Uniquement pour ces zones | vide = toutes ; par exemple `["JETTY", "SPM"]` pour les tâches d'interface navire/terre |
| Seulement pour ces natures de cargaison | vide = toutes ; `["LIQUID"]` pour une ligne du socle commun réservée aux pétroliers (M0:29 essai d'arrêt d'urgence, M0:31 mise en sécurité du poste), `["DRY", "CONTAINER", "GENERAL", "RORO", "OTHER"]` pour M0:31b (poste prêt — manutention) (1.5) |
| Feu vert | la tâche est un **feu vert** (1.5) : elle apparaît sur le panneau des feux verts de l'aperçu de l'escale, sa partie la donne d'un bouton et peut la **retirer avec un motif** ; les points d'arrêt qui l'exigent se referment aussitôt. Le socle commun livre quatre feux verts — M0:09 capitainerie (par sa décision), M0:09b sûreté et base navale, M0:09c terminal (quai), M0:09d mandant (armateur / affréteur) ; un port en ajoute (par exemple un feu vert de l'autorité portuaire ou du laboratoire) ou en retire dans une version brouillon de M0 |

Une tâche N4 ne peut pas figurer dans un gabarit : les questions de sûreté vont dans l'espace sûreté.

## 5. Types de demande et leurs formulaires

**Types de demande** — chaque type est un formulaire paramétrable (EF-2.2) :

| Champ | Règle |
|---|---|
| Rôles demandeurs / autorités décisionnaires | un rôle ne peut jamais être les deux (règle 2) — la plateforme refuse l'enregistrement |
| Rôle exécutant | pour les prestations (pilotage, remorquage…) : pas de décision, une programmation puis une exécution |
| Confidentialité, confidentialité du motif de refus | N1 à N3 (N4 : espace sûreté) |
| Champs du formulaire | liste JSON, voir ci-dessous |
| Délai d'instruction, validité par défaut de l'autorisation | une autorisation porte **toujours** une date d'expiration |
| Acceptation du navire (vetting), décision gardée par | effet de point d'arrêt sur l'attribution de poste et le feu vert |
| Tâches réalisées par le dépôt / la décision / l'exécution | codes `GABARIT:NUMÉRO`, par exemple `["M0:06"]` |
| Jalon enregistré à l'approbation, statut de l'escale à l'approbation / au refus | par exemple le feu vert fait passer l'escale à « Acceptée » |
| La décision attribue un poste | le décideur choisit le poste dans la liste des postes compatibles |

Format des champs du formulaire :

```json
[
  {"key": "window_from", "label_fr": "Créneau souhaité — début", "label_en": "Requested window — from",
   "type": "datetime", "required": true},
  {"key": "arrival_draft", "label_fr": "Tirant d'eau à l'arrivée (m)", "label_en": "Arrival draft (m)",
   "type": "number", "required": true},
  {"key": "movement", "label_fr": "Mouvement", "label_en": "Movement", "type": "select", "required": true,
   "options": [{"value": "ARRIVAL", "label_fr": "Entrée / accostage", "label_en": "Arrival / berthing"},
               {"value": "SHIFT", "label_fr": "Déhalage", "label_en": "Shifting"}]}
]
```

Types disponibles : `text`, `textarea`, `number`, `integer`, `datetime` (saisi en heure du port, conservé en UTC), `date`, `select`, `boolean`. Les nombres acceptent la virgule décimale.

## 6. Types de document

Rôles émetteurs, signataires requis, lecteurs supplémentaires (N2), confidentialité par défaut, durée de conservation, et depuis la 1.4 la case **« lecteurs limités à la liste ci-dessus »** (§6.1). Un document avec signataires n'est réputé fait qu'une fois toutes les signatures obtenues. Les cases « généré à partir du registre » (rapport des faits, time sheet) et « connaissement (verrouillé) » ne sont **pas modifiables** : le verrou du connaissement ne peut pas être levé par paramétrage (EF-7.4).

Les **formulaires standards** ([FORMULAIRES.md](FORMULAIRES.md)) — quatre-vingt-quatorze formulaires, émis par chaque partie — s'appuient sur les types de document : les rôles émetteurs, la confidentialité et les signataires que vous réglez ici s'appliquent au formulaire déposé ; un formulaire n'est proposé qu'aux rôles émetteurs de son type. Seize types livrés en 1.3 leur sont propres : `AUTHORIZATION` (acte d'autorisation, **généré seulement**, N1, émis par CAP, APO, ADM), `ARRIVAL_NOTICE`, `SANCTIONS_CHECK`, `ACCESS_LIST`, `PRE_ARRIVAL_SECURITY`, `INERT_GAS_DECLARATION`, `HOT_WORK_PERMIT`, `ENCLOSED_SPACE_PERMIT`, `INCIDENT_REPORT`, `MOVEMENT_ORDER`, `SERVICE_NOTE`, `BERTH_READINESS`, `SHORE_TANK_REPORT`, `SAMPLING_RECORD`, `BUNKER_CHECKLIST`, `LOI` ; les autres formulaires reprennent les types existants (`QQ_CERT`, `WASTE_RECEIPT`, `STS_DOC`, `VETTING_REPORT`, `CP_RECAP`…). Un port installé avant la 1.3 reçoit les nouveaux types par la migration de données `registry.0012` (ou `bootstrap_ports --refresh`) ; la 1.4 ajoute `PUMPING_LOG` (journal de pompage, **généré seulement**, émis par TER et NAV, lu par les parties du contrôle des pertes), ouvre le `TIME_SHEET` à l'émission par le terminal et le navire (lecture N1 par toutes les parties) et limite les lecteurs du `QUALITY_CERT` (migration `registry.0015`). Le contenu des formulaires (sections, points de contrôle) suit les standards de l'industrie et ne se modifie pas à l'écran. Le type `OTHER` (« Autre document ») permet à toute partie de déposer une pièce qui n'entre dans aucun type.

### 6.1 Lecteurs d'un type de document

Un document **N2** (restreint) est lu par son émetteur, par les signataires requis et par les **lecteurs** du type ; s'y ajoutent, par défaut, les rôles de coordination — agence, capitainerie, direction — et l'armateur ou affréteur. La case **« lecteurs limités à la liste ci-dessus »** (`readers_exact`) retire ces rôles implicites : le document n'est alors lu que par les rôles nommés. Elle est cochée pour le **certificat de qualité du laboratoire** (`QUALITY_CERT`, lecteurs navire, terminal, armateur / affréteur, capitainerie, autorité portuaire, direction : l'agence ne le lit pas, EXG-Q-06). Un prestataire ne lit jamais un document qu'il n'a pas émis. Le dépôt d'un document notifie ses lecteurs (ses signataires sont notifiés « à signer »).

### 6.2 Accès aux rapports et tableaux en ligne

**Paramétrage › Accès aux rapports** (`ReportAccess`, EXG-Q-08) — pour chaque rapport tenu en ligne, les rôles qui le lisent. Les rôles qui **saisissent** (le navire et le terminal pour le journal de pompage et les relevés de citernes, l'inspecteur pour la validation) le font quel que soit ce réglage ; le réglage dit qui **lit**. Les valeurs livrées :

| Rapport | Lecteurs par défaut | Ce qui est lu |
|---|---|---|
| `PUMPING_LOG` Journal de pompage | NAV, TER, CAP, INS, COM, DIR, AGE | les feuilles et relevés des deux bords, la comparaison relevé par relevé, les écarts et alertes, le formulaire `PUMPING_LOG` |
| `MEASUREMENTS` Mesures et relevés de citernes validés | NAV, TER, CAP, INS, COM, DIR, AGE | les quantités bord / terre / inspecteur, les totaux de citernes **validés par l'inspecteur** ; un relevé en attente ou rejeté n'est vu que par son bord et par l'inspecteur |
| `SAFETY_CHECKLIST` Liste de contrôle navire/terre | NAV, TER, CAP, APO, INS, AGE, SUR, DIR | la page *Liste de contrôle* : réponses, répétitions, signatures |
| `CALL_BOARD` Conférence de placement et plan d'occupation des postes | AGE, TER, CAP, APO, SVC, ADM, SUR, INS, COM, PRE, DIR | navire, consignataire, poste ou zone, opérations, état, heures estimées et réelles, formulaires FAL et manifeste déposés de chaque escale déclarée ; la nature de la cargaison et le tonnage **si le port le décide** (§1, coché par défaut) — jamais les parties, les tâches, les demandes, les documents ni les mesures d'une autre agence |

Les lignes ne se suppriment pas (une ligne sans rôle ferme le rapport à tous, hors les rôles qui le saisissent) ; chaque modification reste dans l'historique de la fiche (bouton *Historique* de l'administration). Un rôle retiré ici ne voit plus le rapport à l'écran, dans l'API ni dans l'export. Les rôles qui n'apparaissent dans aucune ligne (services nautiques et douanes pour le journal de pompage, par exemple) ne lisent ni l'onglet ni le formulaire correspondant. Ce réglage ne touche pas aux documents déposés, qui suivent §6.

### 6.3 Documents attendus à l'annonce (1.5)

Les documents que les gabarits exigent sont des tâches bloquantes ou non selon le gabarit (§4). L'agence y ajoute, à l'annonce ou depuis l'onglet *Documents*, les **documents facultatifs du catalogue** (tout type de document actif non généré) et **tout autre document** d'une liste ouverte (libellé, rôle qui le fournit, délai avant l'ETA) : chacun devient une tâche non bloquante de la partie qui l'émet, notifiée. Pour qu'un document figure dans la liste proposée, il suffit qu'il existe comme type de document actif ; pour qu'il soit **exigé** de toute escale d'une nature, on l'ajoute comme tâche de nature F au gabarit concerné.

### 6.4 Accès des parties au dossier (1.5)

Ce n'est pas un paramétrage : l'**agent principal** (l'agence qui a annoncé l'escale) ou la capitainerie donne à chaque partie invitée, à l'annonce ou depuis l'onglet *Parties*, un accès **complet** (tous les onglets de son rôle, agit dans son rôle), **partiel** (les onglets listés, y agit) ou en **lecture seule** (aucun acte). Les parties par défaut du port (§2) et l'agent principal gardent toujours leur accès complet. Une **agence associée** (une autre agence du port, invitée avec le rôle AGE pour une partie des opérations) agit dans l'accès reçu et n'est jamais agent principal.

## 7. Causes d'interruption

Liste **fermée** (EF-3.5) : code, libellé bilingue, imputation (terre, bord, tiers, météo), « motif obligatoire » (pour « Autre »), ordre d'affichage. Une cause désactivée n'est plus proposée mais reste valable pour les jalons déjà enregistrés. La liste livrée (17 causes) est une proposition à négocier avec les parties avant la recette.

## 8. Points d'arrêt et types de jalons

**Points d'arrêt** — pour chaque transition gardée (déclaration, feu vert, attribution de poste, autorisation de mouvement, pilote à bord à l'arrivée et au départ, début du transfert ou des opérations, accostage à couple, travaux par point chaud, autorisation de départ, clôture), la liste des tâches exigées. Depuis la 1.5, l'autorisation de mouvement et l'amarrage exigent le feu vert de la sûreté et de la base navale (M0:09b) ; le début du transfert exige ceux du terminal (M0:09c) et du mandant (M0:09d), et pour les cargaisons autres que liquides le poste prêt (M0:31b) et les tâches des gabarits MB1, MB2, MC1, MG1, MR1, MX1 (cales acceptées, plan BLU convenu, draft survey initial, engins, bay plan…) ; retirer un feu vert de la liste d'un point d'arrêt est une décision de procédure. Ajouter une exigence durcit le contrôle ; aucun utilisateur ne peut la contourner (EF-11.4). Les contrôles réglementaires codés (verrou du connaissement, acceptation de navire valide, clôture sans contestation ouverte ni mesure incomplète) ne figurent pas ici parce qu'ils ne se désactivent pas.

**Types de jalons** — émetteur unique, contresignataires, rôles pouvant contester (`["*"]` = toutes les parties), corroboration AIS, cause obligatoire, ancre fixée (ATA, ATB, T0…), statut d'escale atteint, tâches réalisées, proposition dans l'appli terrain. Changer l'émetteur d'un jalon est une décision de procédure : à faire valider par la capitainerie.

## 9. Échanges avec les systèmes tiers

**Abonnements webhook** — URL du système destinataire (guichet unique, PCS…), actions publiées (vide = toutes). Seules les entrées visibles par toutes les parties (N1) sont publiées, signées par HMAC (`X-Fluxaa-Signature`) avec le secret affiché, et rejouées en cas d'échec.

**Fournisseurs de données maritimes** (1.6) — le tableau AIS reçoit les positions de tout fournisseur par `POST /api/v1/ais/positions/` (compte d'intégration de portée `ais`) ; l'adaptateur `scripts/kpler_marinetraffic_adapter.py` y transmet celles de MarineTraffic / Kpler AIS ; l'étude `docs/INTEGRATIONS.md` dit ce que les autres produits Kpler apporteraient et à quelles conditions.

## 10. Assistance IA (EF-17)

Activable **par l'exploitant seulement**, port par port, une fois l'accord écrit du port obtenu (sa référence est saisie dans « référence de l'accord du port »). L'administrateur du port consulte en lecture les **requêtes à l'assistant** (qui, quand, quoi, empreinte des données envoyées) et les **extractions en attente de validation**. L'activation ouvre aussi, pour la direction, l'autorité et la capitainerie, l'**assistant du port** (`/assistant/`) : point du port et questions sur le registre, tracés de la même façon (requêtes sans escale).

## 11. Pilotage du paramétrage

La page **Pilotage** (`/pilotage/`, administrateur du port et direction) indique, sur 30 à 365 jours : les alertes par gabarit et par nature, le nombre de notifications reçues par personne et par escale (cible EF-6 : moins de 15), les retards et le délai moyen de saisie des jalons par rôle (EF-6.5, ENF-8). C'est l'outil pour décider d'allonger un délai, de rendre une tâche normale ou de revoir un seuil — il juge le paramétrage, pas les personnes.

La page **Statistiques** (`/statistiques/`, direction, autorité, capitainerie, administrateur du port) complète le pilotage sur une période libre : escales, tonnages, attentes et durées par mois, répartition par modèle d'opération, zone, produit et poste, interruptions par cause et imputation, délais de décision par type de demande, contestations et contresignatures, saisies par source, tâches dans les délais par rôle ; export CSV du même contenu. Rien n'y est stocké : chaque chiffre est recalculé du registre.

## 12. Démonstration de recette EF-16 (15 minutes, sans assistance technique)

1. **Ajouter un type de demande** : *Types de demande › Ajouter* — code `BUNKER_SURVEY`, libellés FR/EN, demandeur `AGE`, décideur `CAP`, confidentialité N2, champs `[{"key": "grade", "label_fr": "Grade", "label_en": "Grade", "type": "text", "required": true}]`, validité 24 h. Enregistrer. Sur une escale, l'agence le voit dans « Nouvelle demande », la capitainerie le décide.
2. **Ajouter une tâche à un gabarit** : *Gabarits d'escale* › cocher M1 › action « Créer une version brouillon » › ouvrir le brouillon › ajouter une tâche (rôle TER, nature « Confirmer l'exécution », ancre ETB, décalage −720 min, normale) › publier. La prochaine escale M1 la contient ; les escales en cours ne changent pas.
3. **Ajouter une cause d'interruption** : *Causes d'interruption › Ajouter* — code `JETTY_INSPECTION`, libellés FR/EN, imputation « Terre ». Elle apparaît immédiatement dans le formulaire de jalon et dans l'appli terrain.

## 13. Commandes d'exploitation utiles

| Commande | Usage |
|---|---|
| `python manage.py bootstrap_ports [--port TGLFW] [--refresh]` | charge le catalogue de référence (idempotent) ; `--refresh` réaligne les libellés des listes de référence, **jamais** les gabarits publiés |
| `python manage.py export_port TGLFW export.zip` | export de réversibilité complet, vérifiable avec `scripts/verifier_export.py` |
| `python manage.py verify_journal` | recalcule les chaînes du journal et de l'audit de chaque port |
| `python manage.py load_demo --port TGLFW [--history 8] [--refresh-ais]` | **démonstration et formation uniquement** — jamais sur un port en production ; `--history N` rejoue N escales closes sur l'année écoulée pour nourrir les statistiques (0 = aucune) ; `--refresh-ais` réémet seulement l'image AIS de démonstration (positions des 24 dernières heures) |
| `python manage.py ais_listen --port TGLFW --udp 0.0.0.0:10110` (ou `--tcp hôte:port`, `--aisstream`) | alimente le tableau AIS depuis un récepteur ou un flux — DEPLOIEMENT.md §15 |
