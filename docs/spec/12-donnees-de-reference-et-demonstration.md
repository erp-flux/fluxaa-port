# 12. Données de référence et de démonstration

> Chapitre **rédigé** (FLX-SPEC-003, onglet 5, sections 5.6 à 5.8), tenu à la main à chaque livraison ; sa source de vérité est le code livré (`apps/registry/catalog.py`, `apps/core/parties.py`, `apps/registry/management/commands/load_demo.py`).

## 12.1 Causes d'interruption, parties par défaut, postes et zones des ports pilotes

### Causes d'interruption

`INTERRUPTION_CAUSES` : imputation (`attributable_to` : SHIP navire, SHORE terre, THIRD tiers, WEATHER météo) portée au time sheet ; `requires_reason` impose un motif libre à la saisie du jalon d'interruption.

| Code | Imputation | Libellé FR | Libellé EN |
|---|---|---|---|
| `SHORE_TANK_SWITCH` | SHORE | Changement de bac à terre | Shore tank switch |
| `SHORE_ULLAGE` | SHORE | Creux insuffisant à terre | Insufficient shore ullage |
| `SHORE_PUMP` | SHORE | Panne de pompe ou de ligne à terre | Shore pump or line failure |
| `SHORE_POWER` | SHORE | Coupure électrique terminal | Terminal power failure |
| `SHORE_LAB` | SHORE | Attente d'analyse laboratoire terre | Waiting for shore laboratory |
| `SHIP_PUMP` | SHIP | Panne de pompe ou d'équipement bord | Ship pump or equipment failure |
| `SHIP_BALLAST` | SHIP | Ballastage / déballastage du navire | Ship ballasting / deballasting |
| `SHIP_INERT_GAS` | SHIP | Gaz inerte ou O₂ hors limites | Inert gas or O₂ out of limits |
| `SHIP_STRIPPING` | SHIP | Assèchement / changement de citerne bord | Stripping / ship tank change |
| `SHIP_REQUEST` | SHIP | Arrêt demandé par le bord | Stop requested by the ship |
| `SURVEYOR` | THIRD | Attente surveyor / jaugeage intermédiaire | Waiting for surveyor / intermediate gauging |
| `CUSTOMS` | THIRD | Blocage douanier | Customs hold |
| `AUTHORITY_ORDER` | THIRD | Ordre de la capitainerie | Harbour master's order |
| `SECURITY_ALERT` | THIRD | Alerte de sûreté | Security alert |
| `WEATHER_LIMITS` | WEATHER | Dépassement des limites météo (vent, houle, courant) | Weather limits exceeded (wind, swell, current) |
| `LIGHTNING` | WEATHER | Orage / risque de foudre | Thunderstorm / lightning risk |
| `OTHER` | — | Autre — motif obligatoire | Other — reason mandatory |

### Ports pilotes, parties par défaut et postes

`PORTS` : pour chaque port pilote, ses réglages, ses organisations par défaut (`PortDefaultParty`, invitées d'office) et ses postes (`Berth`, nature de zone, LOA et tirant d'eau maximaux, récupération des vapeurs). Depuis la 1.5 chaque port porte la **validité par défaut d'une annonce** (15 jours), sa **validité maximale** (90 jours) et le réglage *le tableau des escales montre la nature de la cargaison et le tonnage* (vrai) ; chaque poste peut porter ses **limites d'acceptation** (LOA, tirant d'eau, DWT, largeur, déplacement, hauteur du collecteur, pied de pilote, âge, SWL des grues, tirant d'air) et les **natures de cargaison** qu'il traite — l'amorçage les laisse vides : le port les renseigne, la grille de vetting les lit.


#### SLFNA — Freetown (SL, Africa/Freetown, langue en)

Cadre de la carte AIS : latitude 8.350000 à 8.580000, longitude -13.550000 à -13.120000.

| Code | Type | Nom FR | Nom EN | Latitude | Longitude | Rayon (m) |
|---|---|---|---|---|---|---|
| `KISSY-JETTY` | JETTY | Appontement pétrolier de Kissy | Kissy oil jetty | 8.480000 | -13.195000 | — |
| `FNA-ANCH` | ANCHORAGE | Rade de Freetown — mouillage pétroliers | Freetown roads — tanker anchorage | 8.500000 | -13.260000 | 1500 |
| `FNA-STS` | STS_AREA | Zone STS au large de Freetown | Freetown offshore STS area | 8.400000 | -13.450000 | 2500 |

#### TGLFW — Lomé (TG, Africa/Lome, langue fr)

Cadre de la carte AIS : latitude 5.950000 à 6.160000, longitude 1.180000 à 1.420000.

| Code | Type | Nom FR | Nom EN | Latitude | Longitude | Rayon (m) |
|---|---|---|---|---|---|---|
| `LFW-APP` | JETTY | Appontement pétrolier de Lomé | Lomé oil jetty | 6.128000 | 1.287000 | — |
| `LFW-RADE` | ANCHORAGE | Rade de Lomé — mouillage | Lomé roads — anchorage | 6.080000 | 1.300000 | 1500 |
| `LFW-STS` | STS_AREA | Zone STS au large de Lomé | Lomé offshore STS area | 6.000000 | 1.350000 | 2500 |

### Accès aux rapports (`ReportAccess`, `DEFAULT_REPORT_READERS`)

Créés à l'amorçage de chaque port, modifiables par l'administrateur (administration → *Accès aux rapports*), jamais écrasés par un nouvel amorçage :

| Code | Rapport | Rôles lecteurs par défaut |
| --- | --- | --- |
| `PUMPING_LOG` | journal de pompage (relevés bord et terre, écart) | NAV, TER, CAP, INS, COM, DIR, AGE |
| `MEASUREMENTS` | mesures et relevés de citernes validés | NAV, TER, CAP, INS, COM, DIR, AGE |
| `SAFETY_CHECKLIST` | liste de contrôle navire/terre (lecture ; les deux bords lisent toujours) | NAV, TER, CAP, APO, INS, AGE, SUR, DIR |
| `CALL_BOARD` | conférence de placement (tableau des escales du port) et plan d'occupation des postes | AGE, TER, CAP, APO, SVC, ADM, SUR, INS, COM, PRE, DIR |

### Points des listes de contrôle de sécurité (`apps/registry/ssscl.py`, `apps/registry/checklists.py`)

**ISGOTT (vrac liquide, `SSSCL`)** : quarante-cinq points en sept parties (1A navire avant l'arrivée · 1B terminal avant l'arrivée · 2 navire après l'amarrage · 3 terminal après l'amarrage · 4 navire et terminal avant le transfert · 5A accords écrits · 6 vérifications répétées), chacun avec le côté qui répond (navire, terre, les deux), sa nature (case à cocher ou valeur convenue) et sa répétition (R) ; copiés dans chaque liste ouverte. La liste complète est au chapitre 6 (formulaire `SSSCL`).

**Code BLU (vrac sec, `BLU_CHECKLIST`, 1.5)** : vingt-deux points en quatre parties — 1 avant l'arrivée (profondeur et limites du poste, plan de chargement ou de déchargement convenu, cadences, ballastage, trimming, cargaison IMSBC, contacts), 2 avant les opérations (cales prêtes, accès, engins et trémies, éclairage, communications, procédure d'arrêt d'urgence, pollution), 3 pendant (séquence respectée, contraintes de structure, draft survey, modifications convenues par écrit), 4 après (cales et ponts nettoyés, draft survey final, dommages constatés) — côté navire, terminal ou les deux ; répétés : séquence et contraintes.

**Opérations de manutention (conteneurs, divers, roulier, autre — `CARGO_SAFETY_CHECKLIST`, 1.5)** : vingt points en quatre parties — A accès et passerelle, B engins, grues et zones de travail, C arrimage, saisissage et marchandises dangereuses, D communications, arrêt d'urgence et météo — même mécanique de réponses, de signatures et de répétitions. Les deux catalogues sont au chapitre 6 (formulaires `BLU_CHECKLIST`, `CARGO_SAFETY_CHECKLIST`).

## 12.2 Natures de parties — liste non exhaustive (`PARTY_KINDS`)

Proposées à l'invitation d'une partie (*Inviter une partie*, onglet Parties) et à l'enregistrement d'une organisation depuis une escale ; une nature hors liste se saisit librement (`Organization.kind`, 80 caractères) et `kind_label` / `kind_role` la reconnaissent par son code ou son libellé FR / EN. Les natures sont groupées par rôle FLUXAA.

| Code | Rôle | Libellé FR | Libellé EN |
|---|---|---|---|
| `SHIPPING_AGENT` | AGE | Agence maritime / consignataire | Shipping agent |
| `PROTECTING_AGENT` | AGE | Agent protecteur (pour l'armateur) | Protecting agent (for the owner) |
| `VESSEL` | NAV | Navire / capitaine | Vessel / master |
| `LIGHTERING_VESSEL` | NAV | Navire allégeur / barge (STS) | Lightering vessel / barge (STS) |
| `OIL_TERMINAL` | TER | Terminal pétrolier | Oil terminal |
| `STORAGE_DEPOT` | TER | Dépôt de stockage | Storage depot |
| `REFINERY` | TER | Raffinerie | Refinery |
| `SPM_OPERATOR` | TER | Exploitant de bouée / monobouée (SPM) | SPM / buoy operator |
| `PIPELINE_OPERATOR` | TER | Exploitant de pipeline | Pipeline operator |
| `HARBOUR_MASTER` | CAP | Capitainerie | Harbour master's office |
| `VTS` | CAP | Centre de trafic maritime (VTS) | Vessel traffic service (VTS) |
| `PORT_AUTHORITY` | APO | Autorité portuaire | Port authority |
| `PORT_MANAGEMENT` | DIR | Direction du port | Port management |
| `PILOTAGE` | SVC | Station de pilotage | Pilotage |
| `TOWAGE` | SVC | Remorquage | Towage |
| `MOORING` | SVC | Lamanage / amarrage | Mooring / boatmen |
| `LAUNCH_SERVICE` | SVC | Vedettes / transbordement | Launch / boat service |
| `CUSTOMS` | ADM | Douanes | Customs |
| `IMMIGRATION` | ADM | Immigration / police aux frontières | Immigration / border police |
| `PORT_HEALTH` | ADM | Santé portuaire / quarantaine | Port health / quarantine |
| `MARITIME_AUTHORITY` | ADM | Autorité maritime (État du port / du pavillon) | Maritime authority (port / flag State) |
| `ENVIRONMENT_AUTHORITY` | ADM | Autorité environnementale | Environmental authority |
| `PORT_SECURITY` | SUR | Sûreté portuaire (PFSO) | Port facility security (PFSO) |
| `NAVY` | SUR | Marine nationale / base navale | Navy / naval base |
| `MARITIME_POLICE` | SUR | Gendarmerie / police maritime | Maritime police |
| `CARGO_SURVEYOR` | INS | Inspecteur de cargaison (quantité, qualité) | Cargo surveyor (quantity, quality) |
| `LABORATORY` | INS | Laboratoire d'analyses | Laboratory |
| `CLASS_SOCIETY` | INS | Société de classification | Classification society |
| `PANDI_SURVEYOR` | INS | Expert P&I / correspondant | P&I surveyor / correspondent |
| `VETTING_INSPECTOR` | INS | Inspecteur vetting (SIRE / CDI) | Vetting inspector (SIRE / CDI) |
| `MARINE_CHEMIST` | INS | Chimiste maritime (dégazage) | Marine chemist (gas-free) |
| `DRAFT_SURVEYOR` | INS | Expert maritime (draft survey, avaries) | Marine surveyor (draft survey, damage) |
| `SHIPOWNER` | COM | Armateur / propriétaire | Shipowner |
| `SHIP_MANAGER` | COM | Gestionnaire technique / opérateur | Ship manager / operator |
| `CHARTERER` | COM | Affréteur | Charterer |
| `RECEIVER` | COM | Réceptionnaire / importateur | Receiver / importer |
| `SHIPPER` | COM | Expéditeur / exportateur | Shipper / exporter |
| `TRADER` | COM | Négociant (trader) | Trader |
| `COLLATERAL_MANAGER` | COM | Gestionnaire de garanties / banque (collateral management) | Collateral manager / bank |
| `INSURER` | COM | Assureur / club P&I | Insurer / P&I club |
| `BROKER` | COM | Courtier maritime | Ship broker |
| `STS_PROVIDER` | PRE | Prestataire STS (POAC, mooring master) | STS service provider (POAC, mooring master) |
| `FENDER_HOSE_SUPPLIER` | PRE | Fournisseur de défenses et de flexibles | Fender and hose supplier |
| `BUNKER_SUPPLIER` | PRE | Avitailleur en soutes / barge de soutage | Bunker supplier / bunker barge |
| `WASTE_CONTRACTOR` | PRE | Collecteur de déchets / installation de réception (MARPOL) | Waste contractor / reception facility (MARPOL) |
| `TANK_CLEANING` | PRE | Nettoyage et dégazage de citernes | Tank cleaning and gas-freeing |
| `WATER_SUPPLIER` | PRE | Fournisseur d'eau douce | Fresh water supplier |
| `SHIP_CHANDLER` | PRE | Avitailleur (provisions, ship chandler) | Ship chandler |
| `CREW_AGENCY` | PRE | Agence de relève d'équipage / manning | Crew change / manning agency |
| `REPAIR_YARD` | PRE | Chantier / entreprise de réparation | Repair yard / contractor |
| `DIVING` | PRE | Plongée / travaux sous-marins | Diving / underwater services |
| `OIL_SPILL_RESPONSE` | PRE | Lutte antipollution (OSRO) | Oil spill response (OSRO) |
| `FIRE_SERVICE` | PRE | Service incendie / sécurité civile | Fire service / civil protection |
| `SECURITY_GUARDS` | PRE | Gardiennage (non armé) | Security guards (unarmed) |
| `TRANSPORT` | PRE | Transport (camions-citernes, logistique) | Transport (tank trucks, logistics) |
| `MEDICAL` | PRE | Services médicaux / évacuation | Medical services / evacuation |
| `TELECOM` | PRE | Télécommunications / connectivité | Telecommunications / connectivity |
| `OTHER` |  | Autre partie | Other party |

## 12.3 Actions du journal chaîné et du journal d'accès

Chaque écriture du registre est une `JournalEntry` chaînée (SHA-256 de l'entrée précédente, `seq` par port) avec `action`, acteur, rôle, objet, résumé FR / EN, charge utile et `visible_roles` ; les consultations vont au journal d'accès (`AuditEntry`). Codes d'action en vigueur :

| Domaine | Actions du journal chaîné |
|---|---|
| Escale | `call.created`, `call.declared`, `call.status` (de → vers), `call.estimates_revised`, `call.linked`, `call.stage_planned`, `call.stage_changed`, `call.stage_cancelled`, `call.closure_requested` |
| Parties et accès | `party.granted`, `party.revoked`, `party.shore_side`, `organization.created`, `master_link.issued`, `master_link.revoked`, `party_link.unsent`, `link.named` |
| Tâches | `task.completed`, `task.signed`, `task.countersigned`, `task.not_applicable`, `task.ad_hoc` |
| Jalons | `milestone.recorded`, `milestone.countersigned`, `milestone.tacit`, `ais.observed`, `ais.corroboration` |
| Demandes et autorisations | `request.created`, `request.submitted`, `request.under_review`, `request.decided`, `request.provider`, `request.scheduled`, `request.executed`, `request.cancelled`, `authorization.issued`, `authorization.cancelled`, `authorization.expired` |
| Documents | `document.issued`, `document.signed`, `document.fully_signed`, `document.cancelled`, `document.data_validated`, `vessel.updated` |
| Mesures | `measurement.created`, `measurement.value`, `pumping.entry` |
| Contestations et échanges | `dispute.opened`, `dispute.answered`, `dispute.closed`, `thread.created` |
| Points d'arrêt et alertes | `holdpoint.refused`, `alert.emitted`, `alert.raised` |
| Administration | `template.published`, `user.administered`, `mfa.changed`, `mfa.reset`, `api_token.created` |

| Journal d'accès (`AuditEntry`) | Événements |
|---|---|
| Consultations | `view` (dossier, rapport des faits, formulaire), `download` (document), `export` (escale), `export.port` (export du port) |
| Comptes et liens | `login`, `master.access`, `master.denied`, `assistant` (chaque exécution de l'assistant, avec l'inventaire transmis) |
| Espace sûreté (journal propre, base sûreté) | `CREATE`, `LIST`, `VIEW`, `DECIDE`, `CONFIRM`, `ATTACH`, `DOWNLOAD` |

Natures ajoutées en 1.6 avec les parties proposées par l'opération (`PARTIES_BY_OPERATION`) : `BULK_TERMINAL`, `CONTAINER_TERMINAL`, `GENERAL_CARGO_TERMINAL` (TER) ; `TALLY_COMPANY`, `BUNKER_SURVEYOR` (INS) ; `FREIGHT_FORWARDER` (COM) ; `STEVEDORE`, `LASHING`, `FUMIGATION`, `WEIGHBRIDGE` (PRE).

Natures ajoutées en 1.4 pour les parties du contrôle des pertes (rôle COM) : `SUPERINTENDENT` (superintendant, représentant de l'armateur ou de l'affréteur), `SUPERCARGO` (subrécargue), `LOSS_CONTROL` (contrôle des pertes de l'affréteur ou du négociant) ; le time sheet lit le *trader* et le *subrécargue* parmi les parties COM de ces natures.

## 12.4 Données de démonstration (`load_demo`)

`python manage.py load_demo --port <SLFNA|TGLFW> [--password …] [--domain demo.fluxaa.test] [--history 8] [--no-calls] [--refresh-ais]` charge, dans un port déjà amorcé par `bootstrap_ports`, un jeu fictif de formation ; chaque nom porte le suffixe « (démo) » / « (demo) » et **rien ne doit jamais être chargé sur un port en production** (rien ne s'efface). Le mot de passe est celui de l'appel (sinon aléatoire, affiché) ; les secrets TOTP des rôles décideurs (CAP, APO, ADM, SUR) et de la direction (DIR) sont affichés par la commande.

| Ce qui est créé | Détail |
|---|---|
| 19 organisations | autorité portuaire (CAP, APO, DIR), douanes-immigration-santé (ADM), sûreté et marine nationale (SUR), services nautiques (SVC), agence maritime (AGE), terminal pétrolier (TER), surveyor et laboratoire (INS), armateur / affréteur (COM), prestataire déchets et prestataire STS (PRE) ; et six organisations **sans compte**, enregistrées au port et invitées par l'agence quand l'escale les requiert : laboratoire indépendant (INS, convoqué par lien), avitailleur de soutes, fournisseur d'eau douce (PRE), correspondant P&I (INS), réceptionnaire / importateur (COM), remorquage et lamanage (SVC) ; chacune avec sa nature (`kind`) de la liste non exhaustive ; et depuis la 1.5 un **consignataire associé** (AGE, agence co-nominée) et un **terminal conteneurs et vrac** (TER, toutes cargaisons) |
| Parties par défaut | les quatre organisations d'autorité et de service (CAP, APO, DIR, ADM, SUR, SVC) sont `PortDefaultParty` : invitées d'office à chaque escale |
| 14 utilisateurs | un par rôle : `cap`, `apo`, `dir`, `adm`, `sur`, `svc`, `age`, `ter`, `ins`, `com`, `pre`, `sts`, et depuis la 1.5 `age2` (agence associée) et `ter2` (terminal conteneurs et vrac) — adresse `<login>.<port>@<domaine>` (ex. `age.tglfw@demo.fluxaa.test`), langue du port ; second facteur enrôlé pour les décideurs |
| 10 navires | MT ATLANTIC DEMO (OMI 9999993, Liberia, 45 000 t), MT GULF DEMO (9999981, Îles Marshall, 38 000 t), MT HARMATTAN DEMO (9999979, Panama, pétrolier brut 105 000 t), MT SAVANNAH DEMO (9999967, Malte, 50 000 t), et depuis la 1.5 MV CLINKER DEMO (9311012, vraquier gréé), MSC LOME DEMO (9074743, porte-conteneurs), GRANDE DEMO (9074755, roulier PCTC), MV SAHEL DEMO (9074767, cargo divers) — avec MMSI pour le tableau AIS et, depuis la 1.5, leurs caractéristiques (LOA, largeur, tirant d'eau, année, déplacement, collecteur, tirant d'air, grues) pour la grille de vetting ; les **postes du port de démonstration reçoivent des limites d'acceptation illustratives** (appontement : LOA 250 m, tirant d'eau 13 m, 80 000 t, 25 ans… ; zone STS ; rade) que l'administrateur remplace par les vraies ; et depuis la 1.6 MT LAGUNE DEMO (9999955, Togo, pétrolier côtier 6 500 t) et MT KARA DEMO (9999943, Liberia, 47 000 t), tous deux annoncés par le consignataire associé |
| Escale A | déchargement M1 à quai, **en opération** : ETA − 20 h, feu vert et poste accordés (actes déposés automatiquement), jalons jusqu'au début de transfert avec une interruption contestée, mesures bord / terre / inspecteur, documents, échanges, contestation ouverte par le capitaine |
| Escale B | chargement M2, **acceptée**, en attente de poste ; lien d'accès du capitaine émis, certificats déposés par le capitaine via son lien |
| Escales C et D | paire STS (M3) en zone offshore, **déclarées** et reliées (`link_kind` STS) — C **livre** la cargaison (`sts_role` DONOR, 90 000 t de brut), D en **reçoit** 60 000 t (RECEIVER) ; le laboratoire indépendant, sans compte, est convoqué par lien à la déclaration ; l'escale C a une **seconde étape** planifiée à quai (M1) |
| Feux verts (1.5) | sur l'escale A, les quatre feux verts sont donnés (capitainerie par sa décision, sûreté et base navale, terminal, mandant) ; sur B ceux de la base navale et du terminal ; les escales de l'historique les portent tous |
| Escale E (1.5) | **vrac sec** : MV CLINKER DEMO, déchargement de clinker (MB1, 38 242 t), **acceptée** après vetting du terminal conteneurs et vrac et feux verts de la capitainerie et de la base navale ; validité de 10 jours ; le **consignataire associé** y a un accès partiel (tâches, documents) ; documents attendus demandés à l'annonce : attestation d'assurance (catalogue) et certificat d'origine (liste ouverte) ; Q88, certificats et manifeste déposés |
| Escale F (1.5) | **conteneurs** : MSC LOME DEMO, opérations conteneurs (MC1, 1 501 mouvements), **déclarée** |
| Escale G (1.5) | **roulier** : GRANDE DEMO, 1 850 véhicules (MR1), **brouillon** |
| Escale H (1.5) | **marchandises diverses** : MV SAHEL DEMO, riz en sacs (MG1, 11 200 t), annoncée avec une validité de 3 jours échue avant l'arrivée → **obsolète** (`expire_call`) : l'agence la refait depuis l'aperçu |
| Escale I (1.6) | **accostage à couple, autre agence** : MT LAGUNE DEMO, annoncé par le **consignataire associé** à couple de MT ATLANTIC DEMO (escale A, première agence) pour un allègement au poste (M2 + M9, 5 000 t, 12 h, défenses du terminal) ; **déclarée** ; lien **à sens unique**, à confirmer ; demande d'accostage à couple déposée (préremplie depuis l'annonce) et **en attente de la capitainerie**, que le point d'arrêt refuse tant que manquent l'accord exprès du navire intérieur, l'analyse d'amarrage, la matrice SIMOPS et le plan de déhalage ; créée après l'historique (référence 0017) |
| Escale J (1.6) | **STS, navire-mère d'une autre agence** : MT KARA DEMO, second navire-fille annoncé par le consignataire associé, désigne MT HARMATTAN DEMO (escale C) depuis la conférence de placement et en reçoit 30 000 t ; rôle receveur pris d'office ; **déclarée** ; lien à confirmer par l'autorisation de zone et de fenêtre STS, **demandée et en attente** ; le dossier de C liste MT KARA DEMO sous *Autres navires désignant cette escale* (référence 0018) |
| Historique | `--history` escales closes réparties sur l'année écoulée (8 par défaut, pétroliers), rejouées par les mêmes services qu'une escale réelle — feux verts compris —, pour nourrir statistiques et indicateurs |
| Image AIS | positions des quatre navires autour des postes du port (quai, rade, zone STS) pour le tableau AIS ; `--refresh-ais` ne recharge que cette image |

Les ports pilotes eux-mêmes (réglages, postes, organisations par défaut) viennent de `bootstrap_ports` (`catalog.PORTS`, section 12.1) ; `load_demo` ne crée aucune donnée N4.
