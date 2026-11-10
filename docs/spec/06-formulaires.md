# 6. Formulaires standards — structure et champs
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Les 76 formulaires sont générés par le paquet `services/forms/` (un module par partie émettrice : `standard`, `authority`, `agency`, `ship`, `terminal`, `surveyor`, `services`, `provider`, `owner`) dans **une structure unique** (`templates/registry/reports/form.html`) : bandeau d'en-tête, corps en sections, bloc de signatures, pied scellé. Chaque partie émet depuis la plateforme les documents que l'escale lui demande (tâches « fournir un document » et décisions sur les demandes), et la plateforme les archive. Pour chaque champ : libellé FR / EN et **source** de préremplissage (champ du modèle, jalon ou calcul) ; un champ sans source est complété à la main sur le papier. Les listes de contrôle ont une case par colonne (partie) et une colonne « remarques » ; la section `qr` dessine le code de vérification publique d'une autorisation.

## 6.1 Structure commune (toutes les feuilles)

| Zone | Contenu | Source |
|---|---|---|
| Bandeau | Port (nom, code) · titre FR / EN · standard de référence · n° `CODE-RÉFÉRENCE-nn` · date et heure de génération (UTC) | Port, Form.title, Form.standard, nombre de documents du type déjà déposés + 1, `timezone.now()` |
| Méta | Navire (nom, OMI, pavillon) · escale (référence, voyage) · zone ou poste (+ étape si l'escale en a plusieurs) · arrivée (ATA ou ETA) | Vessel, PortCall, CallStage en cours, PortCall.ata / eta |
| Corps | Sections `fields` (champs), `table` (colonnes, lignes préremplies, lignes vierges), `checklist` (points, colonnes à cocher, remarques), `text` (paragraphes FR / EN) ; note facultative par section | fonction `build_<code>(call)` du formulaire |
| Signatures | Une colonne par rôle signataire : libellé du standard FR / EN, rôle FLUXAA, « nom, date, heure » | Form.signers |
| Pied scellé | Généré par (acteur) · dernière écriture du journal (n° et empreinte SHA-256) · nombre de signatures électroniques enregistrées · n° du formulaire | JournalEntry (seq, hash), MilestoneSignature.count |
| Impression | A4 portrait (paysage pour le time sheet et le rapport de jaugeage), marges 10 mm, sections insécables | Form.landscape |

## 6.2 Catalogue par partie émettrice

| Code | Type de document | Titre FR / EN — objet | Standard | Émis par | Signé par | Répond à | Offert si |
|---|---|---|---|---|---|---|---|
| **AGE** | **Agence maritime** (13) |  |  |  |  |  |  |
| `TIME_SHEET` | `TIME_SHEET` | Time sheet / Time sheet — La chronologie contradictoire de l'escale et ses interruptions, base du décompte du temps de planche. | Chronologie du registre — BIMCO Laytime Definitions for Charter Parties 2013 | AGE | AGE (Agence), NAV (Capitaine), TER (Terminal) | `M0:37` | toujours |
| `PROTEST` | `PROTEST` | Lettre de protestation / Letter of protest — La lettre de protestation d'une partie, avec réserve de droits et accusé de réception. | Usage maritime — réserve de droits, sans reconnaissance de responsabilité | AGE, INS, NAV, PRE, TER | AGE (Expéditeur), TER (Destinataire — reçu) | `M1:1.19`, `M4:4.09` | toujours |
| `FAL` | `FAL_FORMS` | Formulaires FAL — déclaration générale et liste d'équipage / FAL forms — general declaration and crew list — La déclaration générale et la liste d'équipage des formulaires FAL de l'OMI. | Convention FAL de l'OMI, formulaires 1 et 5 (modèles 2024) | AGE, NAV | NAV (Capitaine ou agent autorisé) | `M0:13` | toujours |
| `ARRIVAL_NOTICE` | `ARRIVAL_NOTICE` | Avis d'arrivée (préavis 72 / 48 / 24 h) / Arrival notice (72 / 48 / 24 h pre-arrival notification) — Le préavis d'arrivée de l'agence : navire, heures prévues, opérations, services et formalités sollicités. | Pratique portuaire — règlement d'exploitation du port ; Convention FAL (notification préalable) | AGE | AGE (Agence maritime), CAP (Capitainerie — reçu) | `M0:01`, `M0:08` | toujours |
| `SANCTIONS_CHECK` | `SANCTIONS_CHECK` | Attestation de contrôle des listes de sanctions / Sanctions screening attestation — L'attestation par laquelle l'agence confirme le contrôle des listes de sanctions du navire, de ses intérêts et de la cargaison. | OFAC Sanctions Advisory for the Maritime Industry (2020) ; guides BIMCO / ICS de conformité aux sanctions | AGE | AGE (Agence — responsable conformité) | `M0:05` | toujours |
| `STS_NOTIFICATION` | `STS_NOTIFICATION` | Notification d'opération STS à l'État côtier / STS operation notification to the coastal State — La notification préalable (48 h) de l'opération STS à l'État côtier : navires, lieu, date, produit, quantité, POAC. | MARPOL annexe I, chapitre 8, règle 42 (notification 48 h) ; OCIMF Ship to Ship Transfer Guide | AGE | AGE (Agence, pour le capitaine), CAP (Autorité — reçu) | `M3:3.01` | gabarit M3 ou escale reliée |
| `POAC_DESIGNATION` | `STS_DOC` | Désignation du POAC — mandat écrit / POAC designation — written mandate — Le mandat écrit désignant le POAC de l'opération STS, avec ses qualifications. | OCIMF Ship to Ship Transfer Guide (2013) ; MARPOL annexe I, règle 41 | AGE | AGE (Agence), PRE (POAC — accepte le mandat), NAV (Capitaine) | `M3:3.04` | gabarit M3 ou escale reliée |
| `CARGO_DECLARATION` | `CARGO_DECLARATION` | Déclaration de cargaison (FAL 2) — arrivée / Cargo declaration (FAL 2) — arrival — La déclaration douanière de la cargaison déchargée (FAL 2), pré-remplie du produit et de la quantité de l'escale. | Convention FAL de l'OMI, formulaire 2 | AGE | AGE (Agent autorisé), ADM (Douanes — visa) | `M1:1.18` | gabarit M1 |
| `EXPORT_MANIFEST` | `EXPORT_MANIFEST` | Manifeste et déclaration de cargaison (FAL 2) — départ / Outward manifest and cargo declaration (FAL 2) — departure — Le manifeste de sortie et la déclaration d'exportation de la cargaison chargée (FAL 2). | Convention FAL de l'OMI, formulaire 2 (départ) | AGE | AGE (Agent autorisé), ADM (Douanes — visa) | `M2:2.18` | gabarit M2 |
| `FAL_STORES` | `FAL_FORMS` | Provisions de bord et effets de l'équipage (FAL 3 et 4) / Ship's stores and crew's effects (FAL 3 and 4) — Les déclarations des provisions de bord et des effets de l'équipage (FAL 3 et 4) remises aux douanes. | Convention FAL de l'OMI, formulaires 3 et 4 | AGE, NAV | NAV (Capitaine), ADM (Douanes — visa) | `M0:13`, `M8:8.05` | toujours |
| `CREW_CHANGE_LIST` | `CREW_DOC` | Liste de relève d'équipage / Crew change list — La liste des embarquants et débarquants avec leurs documents, déposée pour la relève d'équipage. | Convention FAL de l'OMI (relèves d'équipage) ; Convention STCW ; pratique de l'immigration | AGE | AGE (Agence), NAV (Capitaine), ADM (Immigration — visa) | `M8:8.01` | gabarit M8 |
| `BILL_OF_LADING` | `BILL_OF_LADING` | Connaissement — données d'émission / Bill of lading — issuing data — Les données d'émission du connaissement, pré-remplies de la quantité convenue ; l'émission reste verrouillée par le point d'arrêt BL_ISSUE. | Pratique du commerce des hydrocarbures (connaissement de charte-partie, type CONGENBILL / BIMCO) ; Règles de La Haye-Visby | AGE | AGE (Agent, pour le capitaine), NAV (Capitaine) | `M2:2.17` | gabarit M2 |
| `PORT_ACCOUNT` | `PORT_ACCOUNT` | Compte d'escale final (FDA) / Final disbursement account (FDA) — Le compte d'escale final transmis au mandant avec ses justificatifs. | Pratique de l'agence maritime (FONASBA — Standard Disbursement Account) | AGE | AGE (Agence), COM (Mandant — reçu) | `M0:38` | toujours |
| **NAV** | **Navire / capitaine** (12) |  |  |  |  |  |  |
| `NOR` | `NOR` | Notice de disponibilité / Notice of readiness — La notice de disponibilité remise par le capitaine aux destinataires de la charte-partie ; l'accusé de réception du terminal et de l'affréteur. | Pratique des chartes-parties — BIMCO Laytime Definitions for Charter Parties 2013 | AGE, NAV | NAV (Capitaine), TER (Terminal — réception), COM (Affréteur / réceptionnaire) | `M0:23` | toujours |
| `MDH` | `MDH` | Déclaration maritime de santé / Maritime declaration of health — La déclaration maritime de santé du capitaine à l'autorité sanitaire. | Règlement sanitaire international (2005) de l'OMS, annexe 8 | NAV | NAV (Capitaine), NAV (Médecin de bord (le cas échéant)) | `M0:14` | toujours |
| `WASTE` | `WASTE_NOTIFICATION` | Notification préalable de dépôt des déchets / Advance notification form for waste delivery — La notification préalable des déchets à déposer (MARPOL, installations de réception). | Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 1 (MARPOL, installations de réception portuaires) | AGE, NAV | NAV (Capitaine), PRE (Prestataire — reçu) | `M0:16`, `M6:6.01` | toujours |
| `PILOT_CARD` | `PILOT_CARD` | Fiche pilote / Pilot card — La fiche pilote remise au pilote à l'embarquement (échange capitaine-pilote). | Résolution OMI A.960(23), annexe 2 | NAV, SVC | NAV (Capitaine), SVC (Pilote) | `M0:18`, `M0:26` | toujours |
| `BALLAST_NOTIFICATION` | `BALLAST_NOTIFICATION` | Notification des eaux de ballast (BWRF) / Ballast water reporting form (BWRF) — La notification des eaux de ballast à bord : volumes, origine, méthode de conformité, rejets prévus. | Convention BWM 2004 ; résolution OMI A.868(20), appendice 2 (Ballast Water Reporting Form) | NAV | NAV (Officier responsable des eaux de ballast), CAP (Autorité — reçu) | `M0:15`, `M5:5.02`, `M5:5.03` | toujours |
| `DISCHARGE_PLAN` | `DISCHARGE_PLAN` | Plan de déchargement et de ballastage / Discharge and ballast plan — Le plan de déchargement et de ballastage remis au terminal avant la réunion pré-transfert. | ISGOTT, 6e édition, chapitre 22 | NAV | NAV (Chef de la cargaison / capitaine), TER (Terminal — accord) | `M1:1.02` | gabarit M1 |
| `LOADING_PLAN` | `LOADING_PLAN` | Plan de chargement / Loading plan — Le plan de chargement : séquence, stabilité, contraintes de structure, tirant d'eau. | ISGOTT, 6e édition, chapitre 22 | NAV | NAV (Chef de la cargaison / capitaine), TER (Terminal — accord) | `M2:2.03` | gabarit M2 |
| `LAST_CARGOES` | `LAST_CARGOES` | Déclaration des trois dernières cargaisons / Last three cargoes declaration — La déclaration des trois dernières cargaisons par citerne et du nettoyage effectué, avant chargement. | Pratique des terminaux et du vetting (Q88, ISGOTT ch. 22.4) | NAV | NAV (Capitaine), TER (Terminal — reçu) | `M2:2.02` | gabarit M2 |
| `INERT_GAS_DECLARATION` | `INERT_GAS_DECLARATION` | Déclaration d'inertage et de teneur en oxygène / Inert gas and oxygen content declaration — La déclaration de l'état du gaz inerte et de la teneur en oxygène des citernes avant le transfert. | SOLAS II-2 règle 16.3 ; code FSS chapitre 15 ; ISGOTT 6e édition, chapitre 7 | NAV | NAV (Chef de la cargaison / capitaine), TER (Terminal — reçu) | `M1:1.04`, `M2:2.06` | gabarit M1 ou M2 ou M3 ou escale reliée |
| `HOT_WORK_PERMIT` | `HOT_WORK_PERMIT` | Permis de travail par point chaud / Hot work permit — Le permis nominatif et limité dans le temps délivré par le capitaine pour les travaux par point chaud. | ISGOTT 6e édition, chapitre 9 (modèle de permis de travail par point chaud) | NAV | NAV (Capitaine — délivre), NAV (Responsable des travaux), TER (Terminal — informé) | `M7:7.06` | gabarit M7 |
| `ENCLOSED_SPACE_PERMIT` | `ENCLOSED_SPACE_PERMIT` | Permis d'entrée en espace clos / Enclosed space entry permit — Le permis nominatif et limité dans le temps délivré par le capitaine pour l'entrée dans un espace clos. | Résolution OMI A.1050(27) ; ISGOTT 6e édition, chapitre 10 | NAV | NAV (Capitaine — délivre), NAV (Responsable de l'entrée) | `M6:6.06` | gabarit M6 ou M7 |
| `INCIDENT_REPORT` | `INCIDENT_REPORT` | Déclaration d'événement à bord ou au poste / Declaration of an event on board or at the berth — La déclaration à la capitainerie de tout événement particulier : blessé, décès, passager clandestin, pollution, avarie. | Pratique portuaire (déclaration d'événement de mer) ; code IGS ; Convention FAL (passagers clandestins) | AGE, INS, NAV, PRE, SVC, TER | NAV (Capitaine ou déclarant), CAP (Capitainerie — reçu) | `M8:8.07` | toujours |
| **TER** | **Terminal / dépôt** (9) |  |  |  |  |  |  |
| `SSSCL` | `SSSCL` | Liste de contrôle navire / terre / Ship/shore safety checklist — La liste de contrôle navire/terre signée conjointement avant le transfert et répétée pendant. | Structure de l'ISGOTT, 6e édition (OCIMF / ICS / IAPH), chapitre 25 | NAV, TER | NAV (Pour le navire), TER (Pour le terminal) | `M0:28` | toujours |
| `PRE_TRANSFER` | `PRE_TRANSFER_MINUTES` | Accord de transfert — réunion pré-transfert / Transfer agreement — pre-transfer meeting — Le compte rendu de la réunion pré-transfert : paramètres, communication, urgence, accord écrit. | ISGOTT, 6e édition, réunion pré-transfert et accords écrits | NAV, TER | TER (Terminal), NAV (Navire), INS (Inspecteur) | `M0:27` | toujours |
| `HOSES` | `HOSE_RECORD` | Relevé de connexion et de déconnexion / Hose / arm connection and disconnection record — Le relevé des connexions et déconnexions des flexibles ou bras, avec les essais. | ISGOTT, 6e édition (flexibles et bras de chargement) ; OCIMF Guide to Manufacturing and Purchasing Hoses for Offshore Moorings | NAV, TER | TER (Terminal), NAV (Navire) | `M1:1.09`, `M1:1.13`, `MA2:A2.04` | toujours |
| `VETTING_REQUEST` | `VETTING_REPORT` | Demande d'acceptation du navire — synthèse du vetting / Vessel acceptance request — vetting summary — La synthèse du vetting interne du terminal jointe à la demande d'acceptation du navire. | OCIMF SIRE 2.0 / CDI ; TMSA ; politique de vetting du terminal | TER | TER (Terminal — responsable vetting), CAP (Autorité — reçu) | `M0:06` | toujours |
| `BERTH_READINESS` | `BERTH_READINESS` | Attestation de mise en sécurité du poste / Berth readiness and safety attestation — L'attestation du terminal que le poste est prêt et mis en sécurité avant l'accostage. | ISGOTT 6e édition, chapitres 15–16 ; règlement d'exploitation du terminal | TER | TER (Responsable du poste), CAP (Capitainerie — informée) | `M0:31`, `M1:1.03` | toujours |
| `SHORE_TANK_REPORT` | `SHORE_TANK_REPORT` | Relevé des bacs et compteurs à terre / Shore tank and meter measurement report — Le relevé des bacs récepteurs ou expéditeurs et des compteurs, avant et après le transfert. | API MPMS chapitres 3, 7 et 12 ; EI HM ; ASTM D1250 | TER | TER (Terminal), INS (Inspecteur — témoin) | `M1:1.06`, `M2:2.08` | gabarit M1 ou M2 |
| `TERMINAL_RECEIPT` | `TERMINAL_RECEIPT` | Bon de réception du terminal / Terminal receipt — Le bon par lequel le terminal reconnaît la quantité reçue dans ses bacs. | Pratique des terminaux (outturn / discharge certificate) ; API MPMS chapitre 17 | TER | TER (Terminal), NAV (Capitaine), INS (Inspecteur) | `M1:1.17` | gabarit M1 |
| `SPM_INSPECTION` | `SPM_DOC` | Rapport d'inspection de la bouée (SPM) / SPM buoy inspection report — Le rapport d'inspection de la bouée, des flexibles et du système d'amarrage avant l'escale. | OCIMF SMOG ; OCIMF GMPHOM (flexibles) | TER | TER (Exploitant de la bouée), CAP (Capitainerie — reçu) | `MA2:A2.01` | gabarit MA2 |
| `DOUBLE_BANKING_STUDY` | `DOUBLE_BANKING_DOC` | Dossier d'accostage à couple — compatibilité, amarrage, déhalage d'urgence / Double banking file — compatibility, mooring, emergency unberthing — L'étude de compatibilité, l'analyse d'amarrage, la matrice des opérations simultanées et le plan de déhalage d'urgence de l'accostage à couple. | OCIMF MEG4 ; OCIMF Ship to Ship Transfer Guide ; ISGOTT 6e édition, chapitre 23 | TER | TER (Terminal), NAV (Capitaine — ce navire), NAV (Capitaine — navire partenaire), CAP (Capitainerie) | `M9:9.03`, `M9:9.04`, `M9:9.06`, `M9:9.08` | gabarit M9 ou escale reliée |
| **CAP** | **Capitainerie** (13) |  |  |  |  |  |  |
| `AUTH_VESSEL_ACCEPTANCE` | `AUTHORIZATION` | Autorisation — Acceptation de navire (vetting) / Authorization — Vessel acceptance (vetting) — L'acte écrit de la décision « Acceptation de navire (vetting) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | APO, CAP | CAP (Autorité — décision), APO (Autorité — décision), AGE (Agence — réception) | `REQ:VESSEL_ACCEPTANCE`, `M0:07` | toujours |
| `AUTH_GREEN_LIGHT` | `AUTHORIZATION` | Autorisation — Feu vert / Authorization — Green light — L'acte écrit de la décision « Feu vert » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception) | `REQ:GREEN_LIGHT`, `M0:09` | toujours |
| `AUTH_MOVEMENT` | `AUTHORIZATION` | Autorisation — Autorisation de mouvement / Authorization — Movement authorization — L'acte écrit de la décision « Autorisation de mouvement » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:MOVEMENT`, `M0:25` | toujours |
| `AUTH_DEPARTURE_CLEARANCE` | `AUTHORIZATION` | Autorisation — Congé de départ / Authorization — Departure clearance — L'acte écrit de la décision « Congé de départ » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:DEPARTURE_CLEARANCE`, `M0:34` | toujours |
| `AUTH_ANCHORAGE_POSITION` | `AUTHORIZATION` | Autorisation — Position de mouillage / Authorization — Anchorage position — L'acte écrit de la décision « Position de mouillage » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:ANCHORAGE_POSITION`, `MA3:A3.01` | gabarit MA3 |
| `AUTH_STS_ZONE` | `AUTHORIZATION` | Autorisation — Autorisation de zone et de fenêtre STS / Authorization — STS area and window authorization — L'acte écrit de la décision « Autorisation de zone et de fenêtre STS » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:STS_ZONE`, `M3:3.03` | gabarit M3 ou escale reliée |
| `AUTH_BUNKERING` | `AUTHORIZATION` | Autorisation — Autorisation de soutage / Authorization — Bunkering authorization — L'acte écrit de la décision « Autorisation de soutage » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:BUNKERING`, `M4:4.01` | gabarit M4 |
| `AUTH_BALLAST_DISCHARGE` | `AUTHORIZATION` | Autorisation — Rejet d'eaux de ballast / Authorization — Ballast water discharge — L'acte écrit de la décision « Rejet d'eaux de ballast » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | APO, CAP | CAP (Autorité — décision), APO (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:BALLAST_DISCHARGE`, `M5:5.04` | gabarit M5 |
| `AUTH_GAS_FREEING` | `AUTHORIZATION` | Autorisation — Nettoyage / dégazage à quai / Authorization — Cleaning / gas-freeing alongside — L'acte écrit de la décision « Nettoyage / dégazage à quai » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:GAS_FREEING`, `M6:6.04` | gabarit M6 |
| `AUTH_HOT_WORK` | `AUTHORIZATION` | Autorisation — Autorisation de travaux (point chaud) / Authorization — Works authorization (hot work) — L'acte écrit de la décision « Autorisation de travaux (point chaud) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:HOT_WORK`, `M7:7.04` | gabarit M7 |
| `AUTH_IMMOBILIZATION` | `AUTHORIZATION` | Autorisation — Immobilisation des machines / Authorization — Engine immobilisation — L'acte écrit de la décision « Immobilisation des machines » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:IMMOBILIZATION`, `M7:7.08` | gabarit M7 |
| `AUTH_DOUBLE_BANKING` | `AUTHORIZATION` | Autorisation — Accostage à couple / Authorization — Double banking — L'acte écrit de la décision « Accostage à couple » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | CAP | CAP (Autorité — décision), AGE (Agence — réception), NAV (Capitaine — pris connaissance) | `REQ:DOUBLE_BANKING`, `M9:9.01` | gabarit M9 ou escale reliée |
| `BERTH_LIMITS` | `BERTH_LIMITS` | Conditions limites d'exploitation du poste / Berth operating limits — Les conditions limites (vent, houle, courant, visibilité, marée) publiées par la capitainerie pour le poste de l'escale. | Pratique portuaire — ISGOTT 6e édition (limites du poste), PIANC (critères d'accostage), règlement d'exploitation du port | CAP, TER | CAP (Capitainerie), TER (Terminal), NAV (Capitaine — pris connaissance) | `M0:12`, `M9:9.11` | toujours |
| **APO** | **Autorité portuaire** (1) |  |  |  |  |  |  |
| `AUTH_BERTH` | `AUTHORIZATION` | Autorisation — Attribution de poste et de créneau (autorisation d'accostage) / Authorization — Berth and slot assignment (berthing authorization) — L'acte écrit de la décision « Attribution de poste et de créneau (autorisation d'accostage) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | APO | APO (Autorité — décision), AGE (Agence — réception) | `REQ:BERTH`, `M0:10`, `M0:11` | toujours |
| **ADM** | **Douanes, immigration, santé** (4) |  |  |  |  |  |  |
| `AUTH_FREE_PRATIQUE` | `AUTHORIZATION` | Autorisation — Libre pratique / Authorization — Free pratique — L'acte écrit de la décision « Libre pratique » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | ADM | ADM (Autorité — décision), AGE (Agence — réception) | `REQ:FREE_PRATIQUE`, `M0:21` | toujours |
| `AUTH_CUSTOMS_IMMIGRATION` | `AUTHORIZATION` | Autorisation — Formalités douanières et d'immigration (arrivée) / Authorization — Customs and immigration formalities (arrival) — L'acte écrit de la décision « Formalités douanières et d'immigration (arrivée) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | ADM | ADM (Autorité — décision), AGE (Agence — réception) | `REQ:CUSTOMS_IMMIGRATION`, `M0:22` | toujours |
| `AUTH_OUTWARD_FORMALITIES` | `AUTHORIZATION` | Autorisation — Formalités de sortie / Authorization — Outward formalities — L'acte écrit de la décision « Formalités de sortie » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | ADM | ADM (Autorité — décision), AGE (Agence — réception) | `REQ:OUTWARD_FORMALITIES`, `M0:33` | toujours |
| `AUTH_CREW_CHANGE` | `AUTHORIZATION` | Autorisation — Relève d'équipage et laissez-passer / Authorization — Crew change and passes — L'acte écrit de la décision « Relève d'équipage et laissez-passer » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification. | Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique | ADM | ADM (Autorité — décision), AGE (Agence — réception) | `REQ:CREW_CHANGE`, `M8:8.02` | gabarit M8 |
| **SUR** | **Sûreté** (3) |  |  |  |  |  |  |
| `DOS` | `SECURITY_DECLARATION` | Déclaration de sûreté / Declaration of security — La déclaration de sûreté entre le navire et l'installation portuaire (code ISPS). | Code ISPS, partie B, appendice 1 (modèle de déclaration de sûreté) | NAV, SUR | SUR (Agent de sûreté de l'installation portuaire (PFSO)), NAV (Agent de sûreté du navire (SSO) / capitaine) | `M0:30`, `M9:9.09` | toujours |
| `ACCESS_LIST` | `ACCESS_LIST` | Demande et autorisation d'accès en zone portuaire / Port area access request and authorization — La liste nominative des personnes et véhicules dont l'accès à la zone portuaire est demandé par l'agence et accordé par la sûreté. | Code ISPS (contrôle d'accès à l'installation portuaire) ; règlement de sûreté du port | AGE, SUR | AGE (Agence — demande), SUR (Autorité de sûreté — décision) | `M8:8.04` | gabarit M7 ou M8 |
| `PRE_ARRIVAL_SECURITY` | `PRE_ARRIVAL_SECURITY` | Information de sûreté avant l'arrivée / Pre-arrival security information — Les renseignements de sûreté que le navire communique avant l'arrivée : certificat ISSC, niveau de sûreté, dix dernières escales, opérations navire-navire. | SOLAS XI-2 règle 9.2.1 ; circulaire OMI MSC.1/Circ.1305 ; Convention FAL (formulaire d'information de sûreté) | AGE, NAV | NAV (Capitaine ou agent de sûreté du navire (SSO)), SUR (Autorité de sûreté — reçu) | `M0:17` | toujours |
| **SVC** | **Services nautiques** (2) |  |  |  |  |  |  |
| `MOVEMENT_ORDER` | `MOVEMENT_ORDER` | Ordre de mouvement — confirmation des services nautiques / Movement order — marine services confirmation — La confirmation des services nautiques réservés (pilote, remorqueurs, lamaneurs) et l'ordre de mouvement. | Résolution OMI A.960(23) ; règlement des services nautiques du port | SVC | SVC (Services nautiques), NAV (Capitaine — reçu), CAP (Capitainerie — informée) | `REQ:MARINE_SERVICES`, `M0:18` | toujours |
| `SERVICE_NOTE` | `SERVICE_NOTE` | Bon de prestation de service / Service delivery note — Le bon de prestation signé par le capitaine pour chaque service rendu (pilotage, remorquage, lamanage, eau, provisions, vedette). | Pratique portuaire (bon de pilotage, de remorquage, de lamanage, de livraison) ; FONASBA (compte d'escale) | PRE, SVC | SVC (Prestataire), NAV (Capitaine — reçu), AGE (Agence — visa) | `REQ:MARINE_SERVICES`, `REQ:WASTE_COLLECTION`, `M8:8.06`, `MA2:A2.03` | toujours |
| **INS** | **Inspecteur et laboratoire** (7) |  |  |  |  |  |  |
| `ULLAGE` | `ULLAGE_REPORT` | Rapport de jaugeage / Ullage / sounding report — Le relevé de jaugeage des citernes, avec les quantités bord, terre et inspecteur du registre. | API MPMS chapitre 17.1 et 17.2 (inspection des cargaisons maritimes) ; EI HM 28 ; tables ASTM D1250 | INS, NAV, TER | INS (Inspecteur), NAV (Officier de quart / chef de cargaison), TER (Terminal) | `M1:1.05`, `M1:1.15`, `M2:2.05`, `M2:2.14`, `M3:3.14` | toujours |
| `SAMPLING_RECORD` | `SAMPLING_RECORD` | Procès-verbal d'échantillonnage / Sampling record — Le procès-verbal des échantillons prélevés, scellés et distribués. | API MPMS chapitre 8 ; ISO 3170 / 3171 ; EI HM 23 | INS | INS (Inspecteur), NAV (Navire — témoin), TER (Terminal — témoin) | `M1:1.07` | gabarit M1 ou M2 ou M3 ou escale reliée |
| `QUANTITY_CERT` | `QQ_CERT` | Certificat de quantité / Certificate of quantity — Le certificat de quantité de l'inspecteur, établi sur les jaugeages bord et terre du registre. | API MPMS chapitres 11, 12 et 17 ; EI HM 28 / 50 ; ASTM D1250 | INS | INS (Inspecteur) | `M1:1.08`, `M1:1.16`, `M2:2.15`, `M3:3.14` | gabarit M1 ou M2 ou M3 ou escale reliée |
| `QUALITY_CERT` | `QUALITY_CERT` | Certificat de qualité — rapport d'analyse / Certificate of quality — analysis report — Le rapport d'analyse du laboratoire et sa conclusion de conformité à la spécification. | ISO/IEC 17025 (rapport d'essai) ; méthodes ISO / ASTM / EN | INS | INS (Laboratoire) | `M1:1.16`, `M2:2.07` | gabarit M1 ou M2 ou M3 ou M4 ou escale reliée |
| `CLEANLINESS_CERT` | `CLEANLINESS_CERT` | Certificat de propreté des citernes / Tank cleanliness certificate — Le certificat de propreté des citernes délivré après l'inspection contradictoire, avant chargement. | Pratique de l'inspection des cargaisons ; ISGOTT 6e édition, chapitre 22.4 | INS | INS (Inspecteur), NAV (Chef de la cargaison), TER (Terminal) | `M2:2.04` | gabarit M2 |
| `EMPTY_TANKS_CERT` | `EMPTY_TANKS_CERT` | Certificat de citernes vides — constat de ROB / Empty tanks certificate — ROB statement — Le constat contradictoire des quantités restant à bord après déchargement. | API MPMS chapitre 17.1 et 17.4 ; pratique de l'inspection des cargaisons | INS | INS (Inspecteur), NAV (Chef de la cargaison), TER (Terminal) | `M1:1.14` | gabarit M1 ou M3 ou escale reliée |
| `GAS_FREE_CERT` | `GAS_FREE_CERT` | Certificat de dégazage / Gas-free certificate — Le certificat de dégazage des espaces contrôlés, avec sa durée de validité explicite. | ISGOTT 6e édition, chapitres 9–10 ; NFPA 306 ; résolution OMI A.1050(27) | INS | INS (Inspecteur / chimiste maritime), NAV (Capitaine — reçu) | `M6:6.05`, `M7:7.05` | gabarit M6 ou M7 |
| **COM** | **Armateur / affréteur** (4) |  |  |  |  |  |  |
| `CP_RECAP` | `CP_RECAP` | Nomination et extrait de charte-partie / Nomination and charter-party recap — L'extrait de recap ou de charte-partie et les clauses d'escale que le mandant communique à l'agence. | Pratique de l'affrètement pétrolier (ASBATANKVOY, SHELLVOY, BPVOY) ; BIMCO | COM | COM (Mandant), AGE (Agence — reçu) | `M0:04` | toujours |
| `DOC_INSTRUCTIONS` | `DOC_INSTRUCTIONS` | Instruction documentaire du mandant (connaissement) / Principal's documentary instructions (bill of lading) — L'instruction écrite du mandant pour l'émission du connaissement et des documents de cargaison. | Pratique du commerce des hydrocarbures ; Règles de La Haye-Visby | COM | COM (Mandant), AGE (Agence — reçu) | `M2:2.16` | gabarit M2 |
| `INSURANCE` | `INSURANCE` | Confirmation des couvertures d'assurance / Insurance cover confirmation — La confirmation des couvertures d'assurance des navires et du prestataire pour l'opération STS ou à couple. | Pratique du P&I et de l'assurance maritime ; OCIMF Ship to Ship Transfer Guide (assurances) | COM | COM (Mandant), AGE (Agence — reçu) | `M3:3.09`, `M9:9.10` | gabarit M3 ou M9 ou escale reliée |
| `LOI` | `LOI` | Lettre de garantie — livraison sans connaissement original / Letter of indemnity — delivery without original bill of lading — La lettre de garantie remise à l'armateur pour une livraison sans présentation du connaissement original. | Formules types du Groupe international des clubs P&I (LOI A / B) | COM | COM (Mandant (réceptionnaire / affréteur)), COM (Banque — contresignature (le cas échéant)), AGE (Agence — reçu pour l'armateur) | — | gabarit M1 ou M3 ou escale reliée |
| **PRE** | **Prestataires** (8) |  |  |  |  |  |  |
| `STS` | `STS_CHECKLISTS` | Listes de contrôle STS / STS checklists — Les listes de contrôle de l'opération STS, avant l'opération, la mise à couple, le transfert et après. | Structure du Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF / ICS / CDI / SIGTTO, 2013) | NAV, PRE | PRE (POAC), NAV (Capitaine) | `M3:3.10` | gabarit M3 ou escale reliée |
| `BDN` | `BUNKER_DELIVERY_NOTE` | Note de livraison de soutes / Bunker delivery note — La note de livraison de soutes du fournisseur (MARPOL annexe VI). | MARPOL, annexe VI, appendice V | PRE | PRE (Représentant du fournisseur), NAV (Chef mécanicien) | `M4:4.08` | gabarit M4 |
| `WASTE_RECEIPT` | `WASTE_RECEIPT` | Bordereau de réception des déchets / Waste delivery receipt — Le bordereau par lequel l'installation de réception atteste les déchets reçus du navire. | Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 3 (MARPOL) | PRE | PRE (Installation de réception), NAV (Capitaine) | `REQ:WASTE_COLLECTION`, `M0:32`, `M5:5.07`, `M6:6.07` | toujours |
| `BUNKER_CHECKLIST` | `BUNKER_CHECKLIST` | Liste de contrôle sécurité soutage / Bunkering safety checklist — La liste de contrôle signée conjointement avant le soutage, avec l'agrément de l'avitailleur et les scellés du comptage. | ISGOTT 6e édition, chapitre 25.5 ; ISO 13739 ; MEPC.1/Circ.875/Add.1 | NAV, PRE | PRE (Avitailleur), NAV (Chef mécanicien) | `M4:4.03`, `M4:4.04`, `M4:4.05` | gabarit M4 |
| `STS_COMPATIBILITY` | `STS_DOC` | Étude de compatibilité STS des deux navires / STS compatibility study of the two vessels — L'étude de compatibilité des deux navires et le plan d'opération du prestataire STS. | OCIMF Ship to Ship Transfer Guide (2013), chapitres 2, 4, 5 et 6 | PRE | PRE (Prestataire STS / POAC), NAV (Capitaine — ce navire), NAV (Capitaine — navire partenaire) | `M3:3.05`, `M3:3.11` | gabarit M3 ou escale reliée |
| `STS_EQUIPMENT` | `STS_DOC` | Attestation des défenses et flexibles STS / STS fenders and hoses attestation — L'attestation des certificats et essais des défenses et des flexibles mis en œuvre. | OCIMF Ship to Ship Transfer Guide (2013) ; ISO 17357 ; OCIMF GMPHOM 2009 | PRE | PRE (Prestataire STS), NAV (Capitaine — reçu) | `M3:3.07`, `M3:3.08`, `M9:9.05` | gabarit M3 ou M9 ou escale reliée |
| `RECEPTION_FACILITY` | `CLEANING_DOC` | Attestation d'agrément et de capacité de l'installation de réception / Reception facility licence and capacity attestation — L'attestation d'agrément et de capacité disponible de l'installation de réception pour l'escale. | MARPOL ; circulaire OMI MEPC.1/Circ.834/Rev.1 | PRE | PRE (Installation de réception), AGE (Agence — reçu) | `M6:6.02` | gabarit M5 ou M6 |
| `WORKS_CREW` | `WORKS_DOC` | Dossier des intervenants extérieurs — qualifications, certificats, assurances / Outside contractors' file — qualifications, certificates, insurance — Le dossier des intervenants extérieurs : qualifications, certificats et assurances avant les travaux. | Code IGS ; ISGOTT 6e édition, chapitre 9 ; règlement du port (entreprises extérieures) | PRE | PRE (Entreprise intervenante), NAV (Capitaine — reçu) | `M7:7.02` | gabarit M7 |

`REQ:<type>` = la décision sur ce type de demande ; `Mx:n` = la tâche du gabarit. Les actes d'autorisation (`AUTH_*`) sont engendrés par le catalogue des types de demande à rôles décideurs.

## 6.3 `NOR` — Notice de disponibilité / Notice of readiness

Partie émettrice : NAV — Navire / capitaine. Standard : Pratique des chartes-parties — BIMCO Laytime Definitions for Charter Parties 2013 / Charter-party practice — BIMCO Laytime Definitions for Charter Parties 2013. Rôles émetteurs : AGE, NAV. Type de document : `NOR`. Répond à : `M0:23`. Offert : toujours. Orientation : portrait. Objet : La notice de disponibilité remise par le capitaine aux destinataires de la charte-partie ; l'accusé de réception du terminal et de l'affréteur.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / Flag | Vessel.flag | demi |
| Voyage / Voyage | PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Produit / Product | PortCall.product | demi |
| Quantité nominée / Nominated quantity | PortCall.quantity, PortCall.quantity_unit | demi |
| Opération / Operation | PortCall.template_codes (M2 = chargement, sinon déchargement) | demi |

**Section (champs) — Heures / Times**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Arrivée à la limite du port (ATA) / Arrival at the port limit (ATA) | jalon ARRIVAL.declared_at, sinon PortCall.ata | demi |
| Mouillage / Anchored | jalon ANCHORED.declared_at | demi |
| NOR remise le / NOR tendered on | jalon NOR_TENDERED.declared_at, sinon PortCall.nor_at | demi |
| Remise par / Tendered by | jalon NOR_TENDERED.emitter_label | demi |
| Destinataires / Addressed to | CallParty TER et COM actives (Organization.name) | pleine |

**Section (texte) — Déclaration / Statement**

> Je soussigné, capitaine du navire ci-dessus, vous informe que le navire est arrivé au port et se trouve, à tous égards, prêt à commencer les opérations de déchargement conformément aux termes de la charte-partie.
>
> *I, the undersigned master of the above vessel, hereby give notice that the vessel has arrived at the port and is in all respects ready to commence discharge in accordance with the terms of the charter-party.*

> Le temps de planche court conformément à la charte-partie. Heure de réception et observations du destinataire ci-dessous.
>
> *Laytime counts in accordance with the charter-party. Time of receipt and the recipient's remarks below.*


**Section (champs) — Accusé de réception / Acknowledgement of receipt**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Reçue le (date, heure) / Received on (date, time) | — (à compléter sur le papier) | demi |
| Acceptée / acceptée sous réserve / Accepted / accepted under reserve | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Signatures** : NAV — Capitaine / Master · TER — Terminal — réception / Terminal — receipt · COM — Affréteur / réceptionnaire / Charterer / receiver

## 6.4 `TIME_SHEET` — Time sheet / Time sheet

Partie émettrice : AGE — Agence maritime. Standard : Chronologie du registre — BIMCO Laytime Definitions for Charter Parties 2013 / Registry chronology — BIMCO Laytime Definitions for Charter Parties 2013. Rôles émetteurs : AGE. Type de document : `TIME_SHEET`. Répond à : `M0:37`. Offert : toujours. Orientation : paysage. Objet : La chronologie contradictoire de l'escale et ses interruptions, base du décompte du temps de planche.

**Section (champs) — Escale / Call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Voyage / Voyage | PortCall.voyage_number | demi |
| Port / poste / Port / berth | Port.name, poste ou zone de l'étape en cours | demi |
| Produit / Product | PortCall.product | demi |
| Quantité déclarée / Declared quantity | PortCall.quantity, PortCall.quantity_unit | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |

**Section (tableau) — Chronologie / Chronology**

Colonnes : Événement / Event · Heure (UTC) / Time (UTC) · Émetteur / Recorded by · Contresignatures / Countersignatures.

Lignes préremplies : Milestone (types de la chronologie, declared_at, emitter_label) et MilestoneSignature (role, state) ; lignes vierges ajoutées : 2.

**Section (tableau) — Interruptions / Stoppages**

Colonnes : Cause / Cause · Début / From · Fin / To · Durée (h) / Duration (h) · Imputation / Attribution · État / State.

Lignes préremplies : reports.interruptions : jalons INTERRUPTION_START/END, InterruptionCause, contresignatures ; lignes vierges ajoutées : 1.

**Section (champs) — Totaux / Totals**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Attente en rade (h) / Waiting at anchorage (h) | reports.time_sheet : ATB − ATA | demi |
| Durée brute de transfert (h) / Gross transfer time (h) | reports.time_sheet : T1 − T0 | demi |
| Temps morts (h) / Stoppages (h) | reports.time_sheet : somme des interruptions | demi |
| Durée nette de transfert (h) / Net transfer time (h) | reports.time_sheet : brut − temps morts | demi |
| Temps de planche utilisé (h) — selon charte-partie / Laytime used (h) — per charter-party | — (à compléter sur le papier) | demi |
| Surestaries / dispatch / Demurrage / despatch | — (à compléter sur le papier) | demi |

Note de section : Les heures viennent du registre contradictoire ; le décompte du temps de planche suit la charte-partie et les BIMCO Laytime Definitions for Charter Parties 2013. / Times come from the contradictory registry; laytime is computed under the charter-party and the BIMCO Laytime Definitions for Charter Parties 2013.

**Signatures** : AGE — Agence / Agency · NAV — Capitaine / Master · TER — Terminal / Terminal

## 6.5 `SSSCL` — Liste de contrôle navire / terre / Ship/shore safety checklist

Partie émettrice : TER — Terminal / dépôt. Standard : Structure de l'ISGOTT, 6e édition (OCIMF / ICS / IAPH), chapitre 25 / Structure of ISGOTT, 6th edition (OCIMF / ICS / IAPH), chapter 25. Rôles émetteurs : NAV, TER. Type de document : `SSSCL`. Répond à : `M0:28`. Offert : toujours. Orientation : portrait. Objet : La liste de contrôle navire/terre signée conjointement avant le transfert et répétée pendant.

**Section (champs) — Identification / Identification**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Poste / Berth | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Produit / Product | PortCall.product | demi |
| Opération / Operation | PortCall.template_codes | demi |
| Date et heure d'arrivée au poste (ATB) / Date and time of berthing (ATB) | PortCall.atb | demi |
| Terminal / Terminal | CallParty TER active (Organization.name) | demi |

**Section (liste de contrôle) — Partie 1A — Navire : vérifications avant l'arrivée / Part 1A — Tanker: checks pre-arrival**

Colonnes à cocher : Navire / Ship ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Système de gaz inerte en service, teneur en O₂ des citernes dans les limites / Inert gas system operational, tank O₂ within limits |
| Dispositifs de pression/dépression et dégagement des citernes vérifiés / Pressure/vacuum devices and tank venting checked |
| Plan de chargement ou de déchargement et de ballastage établi et à bord / Loading/discharge and ballast plan prepared and on board |
| Équipage informé des limites du poste (vent, houle, courant, tirant d'eau) / Crew briefed on the berth limits (wind, swell, current, draft) |

**Section (liste de contrôle) — Partie 1B — Terminal : vérifications avant l'arrivée / Part 1B — Terminal: checks pre-arrival**

Colonnes à cocher : Terre / Shore ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Poste, défenses, bras ou flexibles et moyens d'accès prêts et contrôlés / Berth, fenders, arms or hoses and means of access ready and checked |
| Bacs, lignes et vannes alignés conformément au plan ; capacité disponible / Shore tanks, lines and valves lined up per plan; capacity available |
| Prévisions météo et marée compatibles avec les limites du poste / Weather and tide forecasts within the berth limits |
| Personnel de permanence désigné et informé / Duty personnel assigned and briefed |

**Section (liste de contrôle) — Partie 2 — Navire : vérifications après l'amarrage / Part 2 — Tanker: checks after mooring**

Colonnes à cocher : Navire / Ship ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Amarres tenues et surveillées ; remorque de secours prête / Moorings tended; emergency towing-off pennants ready |
| Moyens d'accès sûrs ; dalots fermés ; plateaux de rétention vidés / Safe means of access; scuppers plugged; drip trays empty |
| Ouvertures de citernes fermées ; dégagement conforme au plan / Tank openings closed; venting per plan |
| Matériel incendie et antipollution prêt ; sources d'ignition contrôlées / Fire-fighting and spill response equipment ready; ignition sources controlled |

**Section (liste de contrôle) — Partie 3 — Terminal : vérifications après l'amarrage / Part 3 — Terminal: checks after mooring**

Colonnes à cocher : Terre / Shore ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Défenses en place ; accès et éclairage conformes / Fenders in place; access and lighting compliant |
| Bras ou flexibles adaptés au collecteur, supportés, dans leur enveloppe de mouvement / Arms or hoses suited to the manifold, supported, within their operating envelope |
| Matériel incendie et antipollution du terminal prêt / Terminal fire-fighting and spill response equipment ready |
| Dispositif d'arrêt d'urgence (ESD) du terminal armé / Terminal emergency shutdown (ESD) armed |

**Section (liste de contrôle) — Partie 4 — Navire et terminal : vérifications avant le transfert / Part 4 — Tanker and terminal: pre-transfer checks**

Colonnes à cocher : Navire / Ship · Terre / Shore ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Système de communication convenu et testé ; signaux d'arrêt d'urgence convenus / Agreed communication system tested; emergency stop signals agreed |
| Procédure d'arrêt d'urgence convenue, essai consigné / Emergency shutdown procedure agreed and tested |
| Collecteurs, flexibles ou bras raccordés et étanches ; joints isolants / mise à la masse conformes / Manifolds, hoses or arms connected and tight; insulating flange / bonding compliant |
| Alignement des vannes bord et terre vérifié ; gaz inerte et pression des citernes surveillés / Ship and shore valve line-up checked; inert gas and tank pressure monitored |
| Effectif suffisant et veille assurée des deux côtés pendant tout le transfert / Sufficient personnel and watch on both sides throughout the transfer |
| Interdiction de fumer, portes et hublots fermés, appareils électriques portatifs contrôlés / Smoking prohibited, doors and ports closed, portable electrical equipment controlled |

**Section (champs) — Partie 5A — Accords avant le transfert / Part 5A — Pre-transfer agreements**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Débit initial / maximal / de fin (m³/h) / Initial / maximum / topping-off rate (m³/h) | — (à compléter sur le papier) | demi |
| Pression maximale au collecteur (bar) / Maximum manifold pressure (bar) | — (à compléter sur le papier) | demi |
| Température maximale (°C) / Maximum temperature (°C) | — (à compléter sur le papier) | demi |
| Temps de fermeture des vannes (s) / Valve closure time (s) | — (à compléter sur le papier) | demi |
| Séquence des citernes et des bacs ; échantillonnage et jaugeage / Tank and shore tank sequence; sampling and gauging | — (à compléter sur le papier) | pleine |
| Limites d'interruption (vent, houle, foudre, visibilité) / Stop limits (wind, swell, lightning, visibility) | — (à compléter sur le papier) | pleine |
| Canal VHF principal / de secours ; langue / Primary / backup VHF channel; language | — (à compléter sur le papier) | demi |
| Intervalle des vérifications répétées (h) / Interval of repetitive checks (h) | — (à compléter sur le papier) | demi |

**Section (liste de contrôle) — Partie 6 — Vérifications répétées pendant et après le transfert / Part 6 — Repetitive checks during and after transfer**

Colonnes à cocher : Heure / Time · Navire / Ship · Terre / Shore ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Amarres, flexibles ou bras, pression et débit vérifiés / Moorings, hoses/arms, pressure and rate checked |
| Communication et veille maintenues ; conditions météo dans les limites / Communication and watch maintained; weather within limits |
| Ballastage conforme au plan ; tirant d'eau, assiette et francs-bords surveillés / Ballast per plan; draft, trim and freeboard monitored |
| Après transfert : lignes vidangées, collecteurs obturés, quantités constatées / After transfer: lines drained, manifolds blanked, quantities agreed |

**Section (texte) — Déclaration / Declaration**

> Nous, soussignés, avons vérifié ensemble, point par point, les éléments de cette liste, et nous nous sommes assurés que les réponses sont, à notre connaissance, exactes. Nous avons convenu de répéter les vérifications de la partie 6 à l'intervalle indiqué.
>
> *We, the undersigned, have checked the items of this list together, item by item, and have satisfied ourselves that the answers are, to the best of our knowledge, correct. We have agreed to repeat the part 6 checks at the stated interval.*


Note de section : Les parties suivent la structure de la liste de contrôle navire/terre de l'ISGOTT, 6e édition ; les points sont formulés par la plateforme, le terminal applique l'édition sous licence dont il dispose. / The parts follow the structure of the ISGOTT 6th edition ship/shore safety checklist; the items are worded by the platform, the terminal applies its licensed edition.

**Signatures** : NAV — Pour le navire / For the ship · TER — Pour le terminal / For the terminal

## 6.6 `PRE_TRANSFER` — Accord de transfert — réunion pré-transfert / Transfer agreement — pre-transfer meeting

Partie émettrice : TER — Terminal / dépôt. Standard : ISGOTT, 6e édition, réunion pré-transfert et accords écrits / ISGOTT, 6th edition, pre-transfer meeting and written agreements. Rôles émetteurs : NAV, TER. Type de document : `PRE_TRANSFER_MINUTES`. Répond à : `M0:27`. Offert : toujours. Orientation : portrait. Objet : Le compte rendu de la réunion pré-transfert : paramètres, communication, urgence, accord écrit.

**Section (champs) — Réunion / Meeting**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Terminal / Terminal | CallParty TER active (Organization.name) | demi |
| Poste / Berth | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Date et heure / Date and time | — (à compléter sur le papier) | demi |
| Produit / Product | PortCall.product | demi |
| Quantité / Quantity | PortCall.quantity, PortCall.quantity_unit | demi |
| Participants (nom, fonction) / Attendees (name, capacity) | — (à compléter sur le papier) | pleine |

**Section (champs) — Paramètres de transfert convenus / Agreed transfer parameters**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Débit initial (m³/h) / Initial rate (m³/h) | — (à compléter sur le papier) | demi |
| Débit maximal (m³/h) / Maximum rate (m³/h) | — (à compléter sur le papier) | demi |
| Débit de fin / topping-off (m³/h) / Topping-off rate (m³/h) | — (à compléter sur le papier) | demi |
| Pression maximale au collecteur (bar) / Maximum manifold pressure (bar) | — (à compléter sur le papier) | demi |
| Température maximale (°C) / Maximum temperature (°C) | — (à compléter sur le papier) | demi |
| Nombre de lignes / bras / Number of lines / arms | — (à compléter sur le papier) | demi |
| Séquence des citernes bord / Ship tank sequence | — (à compléter sur le papier) | pleine |
| Séquence des bacs terre / Shore tank sequence | — (à compléter sur le papier) | pleine |
| Ballastage / déballastage simultané / Simultaneous ballast operations | — (à compléter sur le papier) | demi |
| Échantillonnage (points, moments) / Sampling (points, times) | — (à compléter sur le papier) | demi |

**Section (champs) — Communication et urgence / Communication and emergency**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Canal VHF principal / de secours / Primary / backup VHF channel | — (à compléter sur le papier) | demi |
| Signal d'arrêt d'urgence / Emergency stop signal | — (à compléter sur le papier) | demi |
| Temps de fermeture des vannes (s) / Valve closure time (s) | — (à compléter sur le papier) | demi |
| Procédure ESD testée à (heure) / ESD tested at (time) | jalon ESD_TEST.declared_at | demi |
| Limites d'arrêt : vent (nd), houle (m), foudre, visibilité / Stop limits: wind (kn), swell (m), lightning, visibility | — (à compléter sur le papier) | pleine |
| Personnes de permanence (navire / terminal) / Persons on duty (ship / terminal) | — (à compléter sur le papier) | pleine |

**Section (texte) — Accord / Agreement**

> Les parties conviennent des paramètres ci-dessus. Toute modification en cours de transfert est convenue entre les responsables de permanence et consignée au registre (jalon ou échange).
>
> *The parties agree on the parameters above. Any change during the transfer is agreed between the persons on duty and recorded in the registry (milestone or exchange).*


**Signatures** : TER — Terminal / Terminal · NAV — Navire / Ship · INS — Inspecteur / Surveyor

## 6.7 `ULLAGE` — Rapport de jaugeage / Ullage / sounding report

Partie émettrice : INS — Inspecteur et laboratoire. Standard : API MPMS chapitre 17.1 et 17.2 (inspection des cargaisons maritimes) ; EI HM 28 ; tables ASTM D1250 / API MPMS chapters 17.1 and 17.2 (marine cargo inspection); EI HM 28; ASTM D1250 tables. Rôles émetteurs : INS, NAV, TER. Type de document : `ULLAGE_REPORT`. Répond à : `M1:1.05`, `M1:1.15`, `M2:2.05`, `M2:2.14`, `M3:3.14`. Offert : toujours. Orientation : paysage. Objet : Le relevé de jaugeage des citernes, avec les quantités bord, terre et inspecteur du registre.

**Section (champs) — Jaugeage / Gauging**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Poste / Berth | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Produit / Product | PortCall.product | demi |
| Nature / Kind | — (à compléter sur le papier) | demi |
| Date et heure du jaugeage / Date and time of gauging | — (à compléter sur le papier) | demi |
| Méthode (ruban UTI, radar, ATG…) / Method (UTI tape, radar, ATG…) | — (à compléter sur le papier) | demi |
| Tirant d'eau AV / AR (m) / Draft fwd / aft (m) | — (à compléter sur le papier) | demi |
| Gîte / assiette / List / trim | — (à compléter sur le papier) | demi |
| Inspecteur / Surveyor | CallParty INS active (Organization.name) | demi |
| Facteur d'expérience navire (VEF) / Vessel experience factor (VEF) | — (à compléter sur le papier) | demi |

**Section (tableau) — Citernes / Tanks**

Colonnes : Citerne / Tank · Creux / innage (m) / Ullage / innage (m) · Température (°C) / Temperature (°C) · Eau libre (m) / Free water (m) · Densité @15 °C / API / Density @15 °C / API · TOV (m³) / TOV (m³) · GOV (m³) / GOV (m³) · VCF / VCF · GSV (m³) / GSV (m³) · Masse (t) / Weight (t).

Lignes préremplies : aucune ; lignes vierges ajoutées : 14.

Note de section : Calculs selon API MPMS ch. 11 et 12 (tables ASTM D1250) ; totaux reportés dans la section des quantités. / Calculations under API MPMS ch. 11 and 12 (ASTM D1250 tables); totals carried to the quantities section.

**Section (tableau) — Quantités enregistrées au registre / Quantities recorded in the registry**

Colonnes : Mesure / Measurement · Produit / Product · Unité / Unit · Bord / Ship · Terre / Shore · Inspecteur / Surveyor.

Lignes préremplies : Measurement (kind, product, unit) et MeasurementValue courante par partie (value, temperature_c, density) ; lignes vierges ajoutées : 1.

**Section (champs) — Totaux / Totals**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| TOV total (m³) / Total TOV (m³) | — (à compléter sur le papier) | demi |
| Eau libre totale (m³) / Total free water (m³) | — (à compléter sur le papier) | demi |
| GSV total (m³ @15 °C) / Total GSV (m³ @15 °C) | — (à compléter sur le papier) | demi |
| Masse totale (t air) / Total weight (t in air) | — (à compléter sur le papier) | demi |
| Écart bord/terre (%) / Ship/shore difference (%) | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Signatures** : INS — Inspecteur / Surveyor · NAV — Officier de quart / chef de cargaison / Chief officer · TER — Terminal / Terminal

## 6.8 `HOSES` — Relevé de connexion et de déconnexion / Hose / arm connection and disconnection record

Partie émettrice : TER — Terminal / dépôt. Standard : ISGOTT, 6e édition (flexibles et bras de chargement) ; OCIMF Guide to Manufacturing and Purchasing Hoses for Offshore Moorings / ISGOTT, 6th edition (hoses and loading arms); OCIMF hose guidelines. Rôles émetteurs : NAV, TER. Type de document : `HOSE_RECORD`. Répond à : `M1:1.09`, `M1:1.13`, `MA2:A2.04`. Offert : toujours. Orientation : portrait. Objet : Le relevé des connexions et déconnexions des flexibles ou bras, avec les essais.

**Section (champs) — Raccordement / Connection**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Poste / Berth | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Produit / Product | PortCall.product | demi |
| Terminal / Terminal | CallParty TER active (Organization.name) | demi |
| Type : flexibles ☐ bras de chargement ☐ / Type: hoses ☐ loading arms ☐ | — (à compléter sur le papier) | demi |
| Réduction au collecteur / Manifold reducer | — (à compléter sur le papier) | demi |

**Section (tableau) — Lignes / Lines**

Colonnes : N° / No. · Identifiant flexible / bras / Hose / arm id · Diamètre (po) / Size (in) · Dernier essai de pression (date, bar) / Last pressure test (date, bar) · Connecté le / Connected at · Déconnecté le / Disconnected at · Vidangé / purgé / Drained / purged.

Lignes préremplies : jalons HOSES_CONNECTED et HOSES_DISCONNECTED (declared_at) pour la ligne 1 ; lignes vierges ajoutées : 5.

**Section (champs) — Contrôles / Checks**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Joints et boulonnage vérifiés / Gaskets and bolting checked | — (à compléter sur le papier) | demi |
| Mise à la masse / joint isolant / Bonding / insulating flange | — (à compléter sur le papier) | demi |
| Essai d'étanchéité en pression (bar, durée) / Leak test under pressure (bar, duration) | — (à compléter sur le papier) | demi |
| Supports et rayon de courbure conformes / Supports and bend radius compliant | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Signatures** : TER — Terminal / Terminal · NAV — Navire / Ship

## 6.9 `PROTEST` — Lettre de protestation / Letter of protest

Partie émettrice : AGE — Agence maritime. Standard : Usage maritime — réserve de droits, sans reconnaissance de responsabilité / Maritime practice — reservation of rights without admission of liability. Rôles émetteurs : AGE, INS, NAV, PRE, TER. Type de document : `PROTEST`. Répond à : `M1:1.19`, `M4:4.09`. Offert : toujours. Orientation : portrait. Objet : La lettre de protestation d'une partie, avec réserve de droits et accusé de réception.

**Section (champs) — Expéditeur et destinataire / From and to**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| De (organisation, rôle, nom) / From (organisation, role, name) | — (à compléter sur le papier) | pleine |
| À (organisation, rôle) / To (organisation, role) | — (à compléter sur le papier) | pleine |
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Escale / Call | PortCall.reference | demi |
| Poste / Berth | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Date / Date | — (à compléter sur le papier) | demi |

**Section (texte) — Objet et faits / Subject and facts**

> Objet : ______________________________________________
>
> *Subject: ______________________________________________*

> Je soussigné proteste par la présente contre les faits suivants, constatés lors de l'escale référencée, et me réserve, au nom de mes mandants, tous droits de recours pour les pertes, retards et dommages qui en résulteraient :
>
> *I, the undersigned, hereby protest against the following facts, observed during the referenced call, and reserve, on behalf of my principals, all rights of recourse for any loss, delay or damage arising therefrom:*

> Faits (dates, heures, références des jalons du registre) : ________________________________________________________________
>
> *Facts (dates, times, references of the registry milestones): ________________________________________________________________*

> La présente lettre ne constitue ni une reconnaissance de responsabilité ni une renonciation à un droit.
>
> *This letter is neither an admission of liability nor a waiver of any right.*


**Section (champs) — Réception / Receipt**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Reçue le (date, heure) / Received on (date, time) | — (à compléter sur le papier) | demi |
| Par (nom, fonction) / By (name, capacity) | — (à compléter sur le papier) | demi |
| Observations du destinataire (« reçu sous réserve »…) / Recipient's remarks (“received under protest”…) | — (à compléter sur le papier) | pleine |

**Signatures** : AGE — Expéditeur / Issuer · TER — Destinataire — reçu / Recipient — received

## 6.10 `FAL` — Formulaires FAL — déclaration générale et liste d'équipage / FAL forms — general declaration and crew list

Partie émettrice : AGE — Agence maritime. Standard : Convention FAL de l'OMI, formulaires 1 et 5 (modèles 2024) / IMO FAL Convention, forms 1 and 5 (2024 models). Rôles émetteurs : AGE, NAV. Type de document : `FAL_FORMS`. Répond à : `M0:13`. Offert : toujours. Orientation : portrait. Objet : La déclaration générale et la liste d'équipage des formulaires FAL de l'OMI.

**Section (champs) — FAL 1 — Déclaration générale / FAL form 1 — General declaration**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom et type du navire / Name and type of ship | Vessel.name, Vessel.vessel_type | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Indicatif d'appel / Call sign | Vessel.call_sign | demi |
| Numéro du voyage / Voyage number | PortCall.voyage_number | demi |
| Port d'arrivée / de départ / Port of arrival / departure | Port.name, Port.code | demi |
| Date et heure d'arrivée / de départ / Date and time of arrival / departure | PortCall.ata, sinon PortCall.eta | demi |
| Pavillon / Flag State of ship | Vessel.flag | demi |
| Nom du capitaine / Name of master | — (à compléter sur le papier) | demi |
| Dernier port d'escale / prochain port / Last port of call / next port of call | PortCall.last_port, PortCall.next_port | demi |
| Certificat d'immatriculation (port, date, numéro) / Certificate of registry (port, date, number) | — (à compléter sur le papier) | demi |
| Jauge brute / nette / Gross / net tonnage | — (à compléter sur le papier) | demi |
| Position du navire dans le port / Position of the ship in the port | PortCall.berth ou zone de l'étape en cours | demi |
| Brève description du voyage / Brief particulars of voyage | — (à compléter sur le papier) | pleine |
| Brève description de la cargaison / Brief description of the cargo | PortCall.product, quantity, quantity_unit | pleine |
| Nombre de membres d'équipage / passagers / Number of crew / passengers | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |
| Agent du navire (nom, coordonnées) / Ship's agent (name, contact details) | PortCall.agency (Organization.name) | pleine |

Note de section : Documents joints : FAL 2 déclaration de cargaison, FAL 3 provisions de bord, FAL 4 effets de l'équipage, FAL 5 liste d'équipage, FAL 6 liste des passagers, FAL 7 marchandises dangereuses, déclaration maritime de santé. / Attached documents: FAL 2 cargo declaration, FAL 3 ship's stores, FAL 4 crew's effects, FAL 5 crew list, FAL 6 passenger list, FAL 7 dangerous goods manifest, maritime declaration of health.

**Section (tableau) — FAL 5 — Liste d'équipage / FAL form 5 — Crew list**

Colonnes : N° / No. · Nom de famille / Family name · Prénoms / Given names · Fonction / Rank or rating · Nationalité / Nationality · Date et lieu de naissance / Date and place of birth · Pièce d'identité (nature, numéro) / Identity document (nature, number).

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

Note de section : Les formulaires FAL sont déposés au guichet unique de l'État ; la plateforme les prépare et conserve la preuve du dépôt (document « preuve de dépôt FAL »), elle ne les transmet pas (règle d'or : aucune formalité FAL reproduite). / FAL forms are filed with the State's single window; the platform prepares them and keeps the proof of filing (document “proof of FAL filing”), it does not transmit them (golden rule: no FAL formality reproduced).

**Signatures** : NAV — Capitaine ou agent autorisé / Master or authorized agent

## 6.11 `DOS` — Déclaration de sûreté / Declaration of security

Partie émettrice : SUR — Sûreté. Standard : Code ISPS, partie B, appendice 1 (modèle de déclaration de sûreté) / ISPS Code, part B, appendix 1 (model declaration of security). Rôles émetteurs : NAV, SUR. Type de document : `SECURITY_DECLARATION`. Répond à : `M0:30`, `M9:9.09`. Offert : toujours. Orientation : portrait. Objet : La déclaration de sûreté entre le navire et l'installation portuaire (code ISPS). Note : Niveaux de sûreté et arrangements à remplir à la main : ils ne sont pas enregistrés dans le registre de l'escale.

**Section (champs) — Parties / Parties**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom du navire / Name of ship | Vessel.name | demi |
| Port d'immatriculation / Port of registry | — (à compléter sur le papier) | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Installation portuaire / Name of port facility | Port.name, poste ou zone de l'étape en cours | demi |
| Validité : du / au / Valid from / to | — (à compléter sur le papier) | demi |
| Activités couvertes / Activities covered | PortCall.product | demi |
| Niveau de sûreté du navire / Security level for the ship | — (à compléter sur le papier) | demi |
| Niveau de sûreté de l'installation / Security level for the port facility | — (à compléter sur le papier) | demi |

**Section (liste de contrôle) — Responsabilités convenues (ISPS, partie B, appendice 1) / Agreed responsibilities (ISPS Code, part B, appendix 1)**

Colonnes à cocher : Installation / Port facility · Navire / Ship ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Exécution de toutes les tâches liées à la sûreté / Ensuring the performance of all security duties |
| Surveillance des zones d'accès restreint / Monitoring restricted areas to ensure that only authorized personnel have access |
| Contrôle de l'accès à l'installation portuaire / Controlling access to the port facility |
| Contrôle de l'accès au navire / Controlling access to the ship |
| Surveillance de l'installation portuaire, y compris les zones d'accostage et les abords du navire / Monitoring of the port facility, including berthing areas and areas surrounding the ship |
| Surveillance du navire, y compris les zones d'accostage et les abords du navire / Monitoring of the ship, including berthing areas and areas surrounding the ship |
| Manutention de la cargaison / Handling of cargo |
| Livraison des provisions de bord / Delivery of ship's stores |
| Manutention des bagages non accompagnés / Handling unaccompanied baggage |
| Contrôle de l'embarquement des personnes et de leurs effets / Controlling the embarkation of persons and their effects |
| Disponibilité des systèmes de communication de sûreté entre le navire et l'installation portuaire / Ensuring that security communication is readily available between the ship and port facility |

Note de section : Les signataires certifient que les mesures et dispositions de sûreté de l'installation portuaire et du navire pendant les activités spécifiées satisfont aux dispositions du chapitre XI-2 et de la partie A du Code ISPS, et seront appliquées conformément aux dispositions déjà prévues dans leur plan approuvé ou aux arrangements spécifiques convenus et annexés. / The signatories certify that security measures and arrangements for both the port facility and the ship during the specified activities meet the provisions of chapter XI-2 and part A of the ISPS Code that will be implemented in accordance with the provisions already stipulated in their approved plan or the specific arrangements agreed to and set out in the attached annex.

**Section (champs) — Contacts de sûreté (24 h) / Security contacts (24 h)**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Agent de sûreté de l'installation (PFSO) / Port facility security officer (PFSO) | — (à compléter sur le papier) | pleine |
| Agent de sûreté du navire (SSO) / Ship security officer (SSO) | — (à compléter sur le papier) | pleine |

**Signatures** : SUR — Agent de sûreté de l'installation portuaire (PFSO) / Port facility security officer (PFSO) · NAV — Agent de sûreté du navire (SSO) / capitaine / Ship security officer (SSO) / master

## 6.12 `MDH` — Déclaration maritime de santé / Maritime declaration of health

Partie émettrice : NAV — Navire / capitaine. Standard : Règlement sanitaire international (2005) de l'OMS, annexe 8 / WHO International Health Regulations (2005), annex 8. Rôles émetteurs : NAV. Type de document : `MDH`. Répond à : `M0:14`. Offert : toujours. Orientation : portrait. Objet : La déclaration maritime de santé du capitaine à l'autorité sanitaire.

**Section (champs) — Navire / Ship**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom du navire / Name of ship | Vessel.name | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Pavillon / Flag | Vessel.flag | demi |
| Port d'arrivée / Port of arrival | Port.name | demi |
| Date / Date | PortCall.ata, sinon PortCall.eta | demi |
| Venant de / allant à / From / to | PortCall.last_port, PortCall.next_port | demi |
| Nom du capitaine / Master's name | — (à compléter sur le papier) | demi |
| Jauge brute / Gross tonnage | — (à compléter sur le papier) | demi |
| Certificat de contrôle sanitaire / d'exemption valide (lieu, date) / Valid sanitation control / exemption certificate (place, date) | — (à compléter sur le papier) | pleine |
| Nombre de membres d'équipage / de passagers / Number of crew / passengers | — (à compléter sur le papier) | demi |
| Ports d'escale depuis le début du voyage, avec dates / Ports of call since the start of the voyage, with dates | — (à compléter sur le papier) | pleine |

**Section (liste de contrôle) — Questions sanitaires (répondre oui ou non) / Health questions (answer yes or no)**

Colonnes à cocher : Oui / Yes · Non / No ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Une personne est-elle décédée à bord pendant le voyage, autrement que par accident ? / Has any person died on board during the voyage otherwise than as a result of accident? |
| Y a-t-il à bord, ou y a-t-il eu pendant le voyage international, un cas de maladie dont vous soupçonnez qu'elle est de nature infectieuse ? / Is there on board or has there been during the international voyage any case of disease which you suspect to be of an infectious nature? |
| Le nombre total de passagers malades pendant le voyage a-t-il été supérieur à la normale ? / Has the total number of ill passengers during the voyage been greater than normal/expected? |
| Y a-t-il actuellement des malades à bord ? / Is there any ill person on board now? |
| Un médecin a-t-il été consulté ? / Was a medical practitioner consulted? |
| Avez-vous connaissance d'une situation à bord susceptible d'entraîner une infection ou la propagation d'une maladie ? / Are you aware of any condition on board which may lead to infection or spread of disease? |
| Une mesure sanitaire (quarantaine, isolement, désinfection, décontamination) a-t-elle été appliquée à bord ? / Has any sanitary measure (quarantine, isolation, disinfection or decontamination) been applied on board? |
| Des passagers clandestins ont-ils été trouvés à bord ? / Have any stowaways been found on board? |
| Y a-t-il un animal malade à bord ? / Is there a sick animal or pet on board? |

**Section (texte) — Déclaration / Declaration**

> Je déclare par la présente que les renseignements et réponses contenus dans cette déclaration de santé (y compris le tableau en annexe) sont, à ma connaissance, exacts et conformes à la vérité.
>
> *I hereby declare that the particulars and answers to the questions given in this Declaration of Health (including the schedule) are true and correct to the best of my knowledge and belief.*


Note de section : Modèle de l'annexe 8 du Règlement sanitaire international (2005) de l'OMS. En cas de réponse « oui », joindre le tableau des cas. / Model of annex 8 of the WHO International Health Regulations (2005). If any answer is “yes”, attach the schedule of cases.

**Signatures** : NAV — Capitaine / Master · NAV — Médecin de bord (le cas échéant) / Ship's surgeon (if any)

## 6.13 `WASTE` — Notification préalable de dépôt des déchets / Advance notification form for waste delivery

Partie émettrice : NAV — Navire / capitaine. Standard : Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 1 (MARPOL, installations de réception portuaires) / IMO circular MEPC.1/Circ.834/Rev.1, appendix 1 (MARPOL port reception facilities). Rôles émetteurs : AGE, NAV. Type de document : `WASTE_NOTIFICATION`. Répond à : `M0:16`, `M6:6.01`. Offert : toujours. Orientation : portrait. Objet : La notification préalable des déchets à déposer (MARPOL, installations de réception).

**Section (champs) — Navire et escale / Ship and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom du navire / Name of ship | Vessel.name | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Pavillon / Flag State | Vessel.flag | demi |
| Heure d'arrivée prévue / Estimated time of arrival | PortCall.eta | demi |
| Heure de départ prévue / Estimated time of departure | PortCall.etd | demi |
| Dernier port d'escale / prochain port / Last port of call / next port | PortCall.last_port, PortCall.next_port | demi |
| Dernier port et date de dépôt des déchets / Last port and date of waste delivery | — (à compléter sur le papier) | demi |
| Agent / Agent | PortCall.agency (Organization.name) | demi |
| Dépôt : tout ☐ une partie ☐ aucun ☐ / Delivering: all ☐ some ☐ none ☐ | — (à compléter sur le papier) | demi |

**Section (tableau) — Type et quantité de déchets / Type and amount of waste**

Colonnes : Type / Type · À déposer (m³) / To be delivered (m³) · Capacité de stockage max. (m³) / Max. storage capacity (m³) · Quantité conservée à bord (m³) / Amount retained on board (m³) · Port de dépôt du reste / Port of delivery of remaining waste · Quantité estimée produite d'ici le prochain port (m³) / Estimated amount generated before next port (m³).

Lignes préremplies : aucune ; lignes vierges ajoutées : 0.

Note de section : Modèle de l'appendice 1 de la circulaire OMI MEPC.1/Circ.834/Rev.1 ; à transmettre au moins 24 h avant l'arrivée au prestataire et à l'autorité portuaire. / Model of appendix 1 of IMO circular MEPC.1/Circ.834/Rev.1; to be sent at least 24 h before arrival to the provider and the port authority.

**Section (texte) — Confirmation / Confirmation**

> Je confirme que les renseignements ci-dessus sont exacts et qu'il existe à bord une capacité de stockage suffisante pour conserver tous les déchets produits entre la notification et le prochain port où ils seront déposés.
>
> *I confirm that the above details are accurate and correct and that there is sufficient dedicated capacity on board to store all waste generated between notification and the next port at which waste will be delivered.*


**Signatures** : NAV — Capitaine / Master · PRE — Prestataire — reçu / Provider — received

## 6.14 `STS` — Listes de contrôle STS / STS checklists

Partie émettrice : PRE — Prestataires. Standard : Structure du Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF / ICS / CDI / SIGTTO, 2013) / Structure of the Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF / ICS / CDI / SIGTTO, 2013). Rôles émetteurs : NAV, PRE. Type de document : `STS_CHECKLISTS`. Répond à : `M3:3.10`. Offert : gabarit M3 ou escale reliée. Orientation : portrait. Objet : Les listes de contrôle de l'opération STS, avant l'opération, la mise à couple, le transfert et après.

**Section (champs) — Opération STS / STS operation**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire (ce dossier) / Vessel (this file) | Vessel.name, Vessel.imo | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call → Vessel.name, imo, PortCall.reference | demi |
| Zone STS / STS area | PortCall.berth ou zone de l'étape en cours | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |
| Prestataire STS / POAC / STS provider / POAC | CallParty PRE active (Organization.name) | demi |
| Mouillage ou en route / At anchor or under way | — (à compléter sur le papier) | demi |
| Limites météo convenues (vent, houle) / Agreed weather limits (wind, swell) | — (à compléter sur le papier) | demi |
| Défenses et flexibles (type, certificats) / Fenders and hoses (type, certificates) | — (à compléter sur le papier) | pleine |

**Section (liste de contrôle) — Liste 1 — Avant l'opération (compatibilité, plan, notifications) / Checklist 1 — Before operations (compatibility, plan, notifications)**

Colonnes à cocher : Navire / Ship · POAC / POAC ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Compatibilité des navires vérifiée (dimensions, francs-bords, collecteurs, amarrage) / Vessel compatibility verified (dimensions, freeboards, manifolds, mooring) |
| Plan d'opération STS (JPO) établi, approuvé et à bord des deux navires / STS operations plan (JPO) prepared, approved and on board both vessels |
| Notification à l'État côtier et à la capitainerie faite dans les délais / Coastal State and harbour master notified in time |
| Zone, mouillage ou route convenus ; limites météo et critères d'abandon convenus / Area, anchorage or route agreed; weather limits and abort criteria agreed |

**Section (liste de contrôle) — Liste 2 — Avant la mise à couple / Checklist 2 — Before run-in and mooring**

Colonnes à cocher : Navire / Ship · POAC / POAC ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Défenses primaires et secondaires en place et gonflées ; remorques de secours prêtes / Primary and secondary fenders rigged and inflated; emergency towing-off pennants ready |
| Communication entre navires et avec le POAC établie et testée / Ship-to-ship and POAC communication established and tested |
| Équipages briefés ; postes d'amarrage armés ; éclairage de nuit prêt / Crews briefed; mooring stations manned; night lighting ready |
| Ballast et assiette adaptés ; francs-bords compatibles / Ballast and trim suitable; freeboards compatible |

**Section (liste de contrôle) — Liste 3 — Avant le transfert / Checklist 3 — Before cargo transfer**

Colonnes à cocher : Navire / Ship · POAC / POAC ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Flexibles raccordés, supportés, testés ; collecteurs étanches / Hoses connected, supported, tested; manifolds tight |
| Débits, pression, séquence des citernes et procédure d'arrêt d'urgence convenus / Rates, pressure, tank sequence and emergency stop procedure agreed |
| Veille et communication continues ; moyens antipollution prêts / Continuous watch and communication; pollution response equipment ready |
| Gaz inerte, dégagements de citernes et sources d'ignition contrôlés / Inert gas, tank venting and ignition sources under control |

**Section (liste de contrôle) — Liste 5 — Après le transfert / Checklist 5 — After transfer**

Colonnes à cocher : Navire / Ship · POAC / POAC ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Flexibles vidangés, purgés et déconnectés ; collecteurs obturés / Hoses drained, purged and disconnected; manifolds blanked |
| Quantités constatées et documents échangés / Quantities agreed and documents exchanged |
| Amarres larguées dans l'ordre convenu ; défenses récupérées / Moorings released in the agreed order; fenders recovered |

Note de section : Structure des listes de contrôle du Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF/ICS/CDI/SIGTTO, 2013) ; le prestataire STS applique l'édition sous licence dont il dispose. / Structure of the checklists of the Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (OCIMF/ICS/CDI/SIGTTO, 2013); the STS provider applies its licensed edition.

**Signatures** : PRE — POAC / POAC · NAV — Capitaine / Master

## 6.15 `PILOT_CARD` — Fiche pilote / Pilot card

Partie émettrice : NAV — Navire / capitaine. Standard : Résolution OMI A.960(23), annexe 2 / IMO resolution A.960(23), annex 2. Rôles émetteurs : NAV, SVC. Type de document : `PILOT_CARD`. Répond à : `M0:18`, `M0:26`. Offert : toujours. Orientation : portrait. Objet : La fiche pilote remise au pilote à l'embarquement (échange capitaine-pilote).

**Section (champs) — Navire / Ship's particulars**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom du navire / Ship's name | Vessel.name | demi |
| Indicatif / Call sign | Vessel.call_sign | demi |
| Date / Date | PortCall.ata, sinon PortCall.eta | demi |
| Déplacement (t) / Displacement (t) | — (à compléter sur le papier) | demi |
| Port en lourd (t) / Deadweight (t) | Vessel.dwt | demi |
| Année de construction / Year built | Vessel.built_year | demi |
| Longueur hors tout (m) / Length overall (m) | Vessel.loa_m | demi |
| Largeur (m) / Breadth (m) | Vessel.beam_m | demi |
| Tirant d'eau AV / AR (m) / Draft fwd / aft (m) | — (à compléter sur le papier) | demi |
| Tirant d'air (m) / Air draft (m) | — (à compléter sur le papier) | demi |
| Type d'ancre ; chaîne (maillons) / Anchor type; chain (shackles) | — (à compléter sur le papier) | demi |
| Propulseur d'étrave / arrière (kW) / Bow / stern thruster (kW) | — (à compléter sur le papier) | demi |

**Section (tableau) — Propulsion et vitesses de manœuvre / Propulsion and manoeuvring speeds**

Colonnes : Allure / Order · Tours/min / RPM · Vitesse chargé (nd) / Speed loaded (kn) · Vitesse lège (nd) / Speed ballast (kn).

Lignes préremplies : aucune ; lignes vierges ajoutées : 0.

**Section (champs) — Appareil à gouverner et équipements / Steering and equipment**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Type de machine ; puissance maximale (kW) / Engine type; maximum power (kW) | — (à compléter sur le papier) | demi |
| Hélice (pas fixe / variable, sens de rotation) / Propeller (fixed / CPP, direction of rotation) | — (à compléter sur le papier) | demi |
| Angle maximal de barre ; temps bâbord-tribord (s) / Maximum rudder angle; hard-over to hard-over time (s) | — (à compléter sur le papier) | demi |
| Délai machine : arrêt → arrière toute (s) / Engine: stop to full astern (s) | — (à compléter sur le papier) | demi |
| Équipements vérifiés : ancres, indicateur de barre, gyrocompas, radars, VHF, loch, écho-sondeur, AIS, corne / Equipment checked: anchors, rudder indicator, gyro, radars, VHF, speed log, echo sounder, AIS, whistle | — (à compléter sur le papier) | pleine |
| Particularités de manœuvre / Manoeuvring peculiarities | — (à compléter sur le papier) | pleine |

Note de section : Modèle de la fiche pilote de l'annexe 2 de la résolution OMI A.960(23) ; l'échange d'informations capitaine-pilote se fait à l'embarquement. / Model of the pilot card of annex 2 to IMO resolution A.960(23); the master-pilot exchange takes place on boarding.

**Signatures** : NAV — Capitaine / Master · SVC — Pilote / Pilot

## 6.16 `BDN` — Note de livraison de soutes / Bunker delivery note

Partie émettrice : PRE — Prestataires. Standard : MARPOL, annexe VI, appendice V / MARPOL Annex VI, appendix V. Rôles émetteurs : PRE. Type de document : `BUNKER_DELIVERY_NOTE`. Répond à : `M4:4.08`. Offert : gabarit M4. Orientation : portrait. Objet : La note de livraison de soutes du fournisseur (MARPOL annexe VI).

**Section (champs) — Livraison de soutes / Bunker delivery**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom et numéro OMI du navire receveur / Name and IMO number of receiving ship | Vessel.name, Vessel.imo | demi |
| Port / Port | Port.name | demi |
| Date de début de la livraison / Date of commencement of delivery | — (à compléter sur le papier) | demi |
| Fournisseur (nom, adresse, téléphone) / Supplier (name, address, telephone) | CallParty PRE active (Organization.name) | pleine |
| Produit(s) / Product name(s) | — (à compléter sur le papier) | demi |
| Quantité (tonnes métriques) / Quantity (metric tons) | — (à compléter sur le papier) | demi |
| Masse volumique à 15 °C (kg/m³) / Density at 15 °C (kg/m³) | — (à compléter sur le papier) | demi |
| Teneur en soufre (% m/m) / Sulphur content (% m/m) | — (à compléter sur le papier) | demi |
| Échantillon MARPOL (numéro du scellé) / MARPOL sample (seal number) | — (à compléter sur le papier) | demi |

**Section (texte) — Déclaration du fournisseur / Supplier's declaration**

> Le fournisseur déclare que le fioul livré est conforme à la règle 18.3 de l'annexe VI de MARPOL et que sa teneur en soufre ne dépasse pas la limite applicable (règle 14.1 ou 14.4) ou, pour un navire équipé d'un système équivalent, la valeur indiquée ci-dessus.
>
> *The supplier declares that the fuel oil supplied is in conformity with regulation 18.3 of MARPOL Annex VI and that its sulphur content does not exceed the applicable limit (regulation 14.1 or 14.4) or, for a ship fitted with an equivalent arrangement, the value stated above.*


Note de section : Modèle de l'appendice V de l'annexe VI de MARPOL ; conservé à bord trois ans. / Model of appendix V to MARPOL Annex VI; kept on board for three years.

**Signatures** : PRE — Représentant du fournisseur / Supplier's representative · NAV — Chef mécanicien / Chief engineer

## 6.17 `AUTH_VESSEL_ACCEPTANCE` — Autorisation — Acceptation de navire (vetting) / Authorization — Vessel acceptance (vetting)

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : APO, CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:VESSEL_ACCEPTANCE`, `M0:07`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Acceptation de navire (vetting) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |
| Produit / Produit | ServiceRequest.data[product] | demi |
| Rapport SIRE 2.0 / CDI — date et observations en cours / Rapport SIRE 2.0 / CDI — date et observations en cours | ServiceRequest.data[inspection] | demi |
| Trois dernières cargaisons / Trois dernières cargaisons | ServiceRequest.data[last_cargoes] | demi |
| Résultat du vetting interne et conditions proposées / Résultat du vetting interne et conditions proposées | ServiceRequest.data[vetting_result] | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Acceptation du navire / Vessel acceptance**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Rapport SIRE / CDI pris en compte (date) / SIRE / CDI report considered (date) | — (à compléter sur le papier) | demi |
| Validité de l'acceptation / Validity of the acceptance | — (à compléter sur le papier) | demi |
| Conditions d'exploitation imposées / Operating conditions imposed | — (à compléter sur le papier) | pleine |

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code M9VXZWQJ3T — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · APO — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.18 `AUTH_GREEN_LIGHT` — Autorisation — Feu vert / Authorization — Green light

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:GREEN_LIGHT`, `M0:09`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Feu vert » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Feu vert / Green light**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Données navire et certificats vérifiés par / Vessel data and certificates checked by | — (à compléter sur le papier) | demi |
| Contrôle des listes de sanctions confirmé le / Sanctions screening confirmed on | — (à compléter sur le papier) | demi |

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code 758K34GTFG — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.19 `AUTH_BERTH` — Autorisation — Attribution de poste et de créneau (autorisation d'accostage) / Authorization — Berth and slot assignment (berthing authorization)

Partie émettrice : APO — Autorité portuaire. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : APO. Type de document : `AUTHORIZATION`. Répond à : `REQ:BERTH`, `M0:10`, `M0:11`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Attribution de poste et de créneau (autorisation d'accostage) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |
| Créneau souhaité — début / Créneau souhaité — début | ServiceRequest.data[window_from] | demi |
| Tirant d'eau à l'arrivée (m) / Tirant d'eau à l'arrivée (m) | ServiceRequest.data[arrival_draft] | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Poste attribué / Berth assigned | Authorization.berth | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Attribution de poste et de créneau / Berth and slot assignment**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Poste ou zone attribué / Berth or area assigned | Authorization.berth | demi |
| Créneau attribué (de / à) / Slot assigned (from / to) | — (à compléter sur le papier) | demi |
| Tirant d'eau maximal admis (m) / Maximum draft admitted (m) | — (à compléter sur le papier) | demi |
| Conditions d'accostage / Berthing conditions | — (à compléter sur le papier) | pleine |

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code PRZM6444CJ — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : APO — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.20 `AUTH_MOVEMENT` — Autorisation — Autorisation de mouvement / Authorization — Movement authorization

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:MOVEMENT`, `M0:25`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Autorisation de mouvement » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |
| Mouvement / Mouvement | ServiceRequest.data[movement] | demi |
| Heure souhaitée / Heure souhaitée | ServiceRequest.data[requested_time] | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Autorisation de mouvement / Movement authorization**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Mouvement (de / à) / Movement (from / to) | — (à compléter sur le papier) | demi |
| Heure autorisée / Authorized time | — (à compléter sur le papier) | demi |
| Pilote / Pilot | — (à compléter sur le papier) | demi |
| Remorqueurs / Tugs | — (à compléter sur le papier) | demi |
| Lamaneurs / Mooring gang | — (à compléter sur le papier) | demi |
| Conditions (visibilité, vent, marée) / Conditions (visibility, wind, tide) | — (à compléter sur le papier) | pleine |

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code X8TP2USSDR — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.21 `AUTH_FREE_PRATIQUE` — Autorisation — Libre pratique / Authorization — Free pratique

Partie émettrice : ADM — Douanes, immigration, santé. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : ADM. Type de document : `AUTHORIZATION`. Répond à : `REQ:FREE_PRATIQUE`, `M0:21`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Libre pratique » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |
| Équipage à bord / Équipage à bord | ServiceRequest.data[crew] | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Libre pratique / Free pratique**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Déclaration maritime de santé reçue le / Maritime declaration of health received on | — (à compléter sur le papier) | demi |
| Inspection sanitaire : non requise ☐ réalisée ☐ / Health inspection: not required ☐ carried out ☐ | — (à compléter sur le papier) | demi |
| Certificat de contrôle sanitaire du navire (validité) / Ship sanitation certificate (validity) | — (à compléter sur le papier) | demi |
| Mesures sanitaires prescrites / Health measures prescribed | — (à compléter sur le papier) | pleine |

Note de section : Règlement sanitaire international (2005), articles 27 et 28 : la libre pratique est accordée sur la base de la déclaration maritime de santé, sauf inspection. / International Health Regulations (2005), articles 27 and 28: free pratique is granted on the maritime declaration of health unless an inspection is required.

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code DK39ZK3B6P — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : ADM — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.22 `AUTH_CUSTOMS_IMMIGRATION` — Autorisation — Formalités douanières et d'immigration (arrivée) / Authorization — Customs and immigration formalities (arrival)

Partie émettrice : ADM — Douanes, immigration, santé. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : ADM. Type de document : `AUTHORIZATION`. Répond à : `REQ:CUSTOMS_IMMIGRATION`, `M0:22`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Formalités douanières et d'immigration (arrivée) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |
| Liste d'équipage déposée au guichet unique / Liste d'équipage déposée au guichet unique | ServiceRequest.data[crew_list] | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Formalités douanières et d'immigration — arrivée / Customs and immigration formalities — arrival**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Déclaration générale (FAL 1) reçue le / General declaration (FAL 1) received on | — (à compléter sur le papier) | demi |
| Liste d'équipage (FAL 5) visée / Crew list (FAL 5) endorsed | — (à compléter sur le papier) | demi |
| Provisions de bord (FAL 3) et effets (FAL 4) contrôlés / Ship's stores (FAL 3) and crew's effects (FAL 4) checked | — (à compléter sur le papier) | demi |
| Laissez-passer à terre délivrés (nombre) / Shore passes issued (number) | — (à compléter sur le papier) | demi |

**Section (tableau) — Scellés relevés et apposés / Seals removed and applied**

Colonnes : Local / magasin / Store / compartment · N° de scellé / Seal number · Apposé ☐ / relevé ☐ / Applied ☐ / removed ☐ · Heure / Time · Agent / Officer.

Lignes préremplies : aucune ; lignes vierges ajoutées : 5.

**Section (code de vérification) — Vérification publique / Public verification**

QR de l'adresse publique de vérification (`/verifier/<code>/`) ; légende : Code U6RVGTYH4Y — existence et validité vérifiables sans accès au dossier de l'escale.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : ADM — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.23 `AUTH_OUTWARD_FORMALITIES` — Autorisation — Formalités de sortie / Authorization — Outward formalities

Partie émettrice : ADM — Douanes, immigration, santé. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : ADM. Type de document : `AUTHORIZATION`. Répond à : `REQ:OUTWARD_FORMALITIES`, `M0:33`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Formalités de sortie » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Formalités de sortie / Outward formalities**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Prochain port / Next port | — (à compléter sur le papier) | demi |
| Déclaration de sortie n° / Outward declaration no. | — (à compléter sur le papier) | demi |
| Manifeste de sortie / cargaison déclarée / Outward manifest / cargo declared | — (à compléter sur le papier) | demi |
| Scellés contrôlés à la sortie / Seals checked on departure | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : ADM — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.24 `AUTH_DEPARTURE_CLEARANCE` — Autorisation — Congé de départ / Authorization — Departure clearance

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:DEPARTURE_CLEARANCE`, `M0:34`. Offert : toujours. Orientation : portrait. Objet : L'acte écrit de la décision « Congé de départ » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Congé de départ / Departure clearance**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Formalités de sortie accomplies le / Outward formalities completed on | — (à compléter sur le papier) | demi |
| Déchets remis — bordereau n° / Waste delivered — receipt no. | — (à compléter sur le papier) | demi |
| Redevances et frais portuaires / Port dues and charges | — (à compléter sur le papier) | demi |
| Heure d'appareillage autorisée / Authorized time of departure | — (à compléter sur le papier) | demi |
| Prochain port / Next port | — (à compléter sur le papier) | demi |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.25 `AUTH_ANCHORAGE_POSITION` — Autorisation — Position de mouillage / Authorization — Anchorage position

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:ANCHORAGE_POSITION`, `MA3:A3.01`. Offert : gabarit MA3. Orientation : portrait. Objet : L'acte écrit de la décision « Position de mouillage » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Position de mouillage / Anchorage position**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Zone de mouillage / Anchorage area | — (à compléter sur le papier) | demi |
| Position (latitude, longitude) / Position (latitude, longitude) | — (à compléter sur le papier) | demi |
| Rayon d'évitage (m) / Swinging radius (m) | — (à compléter sur le papier) | demi |
| Veille VHF (canal) / VHF watch (channel) | — (à compléter sur le papier) | demi |
| Durée autorisée / Authorized duration | — (à compléter sur le papier) | demi |
| Consignes / Instructions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.26 `AUTH_STS_ZONE` — Autorisation — Autorisation de zone et de fenêtre STS / Authorization — STS area and window authorization

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:STS_ZONE`, `M3:3.03`. Offert : gabarit M3 ou escale reliée. Orientation : portrait. Objet : L'acte écrit de la décision « Autorisation de zone et de fenêtre STS » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Autorisation de zone et de fenêtre STS / STS area and window authorization**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Zone STS / STS area | — (à compléter sur le papier) | demi |
| Fenêtre autorisée (de / à) / Authorized window (from / to) | — (à compléter sur le papier) | demi |
| Navire partenaire / Partner vessel | — (à compléter sur le papier) | demi |
| Prestataire STS / POAC / STS provider / POAC | — (à compléter sur le papier) | demi |
| Limites météo (vent, houle) / Weather limits (wind, swell) | — (à compléter sur le papier) | demi |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.27 `AUTH_BUNKERING` — Autorisation — Autorisation de soutage / Authorization — Bunkering authorization

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:BUNKERING`, `M4:4.01`. Offert : gabarit M4. Orientation : portrait. Objet : L'acte écrit de la décision « Autorisation de soutage » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Autorisation de soutage / Bunkering authorization**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Avitailleur / Bunker supplier | — (à compléter sur le papier) | demi |
| Moyen (barge, camion, pipeline) / Means (barge, truck, pipeline) | — (à compléter sur le papier) | demi |
| Produit et quantité / Product and quantity | — (à compléter sur le papier) | demi |
| Compatibilité avec l'opération cargaison en cours / Compatibility with the cargo operation under way | — (à compléter sur le papier) | pleine |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.28 `AUTH_BALLAST_DISCHARGE` — Autorisation — Rejet d'eaux de ballast / Authorization — Ballast water discharge

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : APO, CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:BALLAST_DISCHARGE`, `M5:5.04`. Offert : gabarit M5. Orientation : portrait. Objet : L'acte écrit de la décision « Rejet d'eaux de ballast » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Rejet d'eaux de ballast / Ballast water discharge**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Volume autorisé (m³) / Authorized volume (m³) | — (à compléter sur le papier) | demi |
| Méthode de conformité (D-1 / D-2) / Compliance method (D-1 / D-2) | — (à compléter sur le papier) | demi |
| Lieu de rejet / Place of discharge | — (à compléter sur le papier) | demi |
| Réception à terre imposée ☐ / Reception ashore required ☐ | — (à compléter sur le papier) | demi |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · APO — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.29 `AUTH_GAS_FREEING` — Autorisation — Nettoyage / dégazage à quai / Authorization — Cleaning / gas-freeing alongside

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:GAS_FREEING`, `M6:6.04`. Offert : gabarit M6. Orientation : portrait. Objet : L'acte écrit de la décision « Nettoyage / dégazage à quai » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Nettoyage / dégazage à quai / Tank cleaning / gas-freeing alongside**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Citernes concernées / Tanks concerned | — (à compléter sur le papier) | demi |
| Méthode / Method | — (à compléter sur le papier) | demi |
| Période autorisée / Authorized period | — (à compléter sur le papier) | demi |
| Effluents et vapeurs : destination / Effluents and vapours: destination | — (à compléter sur le papier) | demi |
| Mesures imposées / Measures imposed | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.30 `AUTH_HOT_WORK` — Autorisation — Autorisation de travaux (point chaud) / Authorization — Works authorization (hot work)

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:HOT_WORK`, `M7:7.04`. Offert : gabarit M7. Orientation : portrait. Objet : L'acte écrit de la décision « Autorisation de travaux (point chaud) » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Autorisation de travaux (point chaud) / Hot work authorization**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Lieu et nature des travaux / Place and nature of the works | — (à compléter sur le papier) | demi |
| Période autorisée / Authorized period | — (à compléter sur le papier) | demi |
| Certificat de dégazage n° / validité / Gas-free certificate no. / validity | — (à compléter sur le papier) | demi |
| Veille incendie et moyens imposés / Fire watch and means imposed | — (à compléter sur le papier) | pleine |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.31 `AUTH_IMMOBILIZATION` — Autorisation — Immobilisation des machines / Authorization — Engine immobilisation

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:IMMOBILIZATION`, `M7:7.08`. Offert : gabarit M7. Orientation : portrait. Objet : L'acte écrit de la décision « Immobilisation des machines » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Immobilisation des machines / Immobilization of the machinery**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Période d'immobilisation (de / à) / Immobilization period (from / to) | — (à compléter sur le papier) | demi |
| Moyens compensatoires (remorqueur en attente, veille renforcée) / Compensating means (tug on standby, reinforced watch) | — (à compléter sur le papier) | pleine |
| Remise en service garantie le / Guaranteed return to service on | — (à compléter sur le papier) | demi |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.32 `AUTH_CREW_CHANGE` — Autorisation — Relève d'équipage et laissez-passer / Authorization — Crew change and passes

Partie émettrice : ADM — Douanes, immigration, santé. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : ADM. Type de document : `AUTHORIZATION`. Répond à : `REQ:CREW_CHANGE`, `M8:8.02`. Offert : gabarit M8. Orientation : portrait. Objet : L'acte écrit de la décision « Relève d'équipage et laissez-passer » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity, quantity_unit | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Relève d'équipage et laissez-passer / Crew change and shore passes**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Documents contrôlés (passeports, visas, brevets, certificats médicaux) / Documents checked (passports, visas, certificates, medical) | — (à compléter sur le papier) | pleine |
| Effectif minimal de sécurité maintenu ☐ / Minimum safe manning maintained ☐ | — (à compléter sur le papier) | demi |

**Section (tableau) — Laissez-passer délivrés / Passes issued**

Colonnes : Nom / Name · Fonction / Rank · Passeport / Passport · Embarque ☐ / débarque ☐ / Joining ☐ / leaving ☐ · N° de laissez-passer / Pass number · Validité / Validity.

Lignes préremplies : aucune ; lignes vierges ajoutées : 6.

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : ADM — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt

## 6.33 `AUTH_DOUBLE_BANKING` — Autorisation — Accostage à couple / Authorization — Double banking

Partie émettrice : CAP — Capitainerie. Standard : Acte écrit de la décision du port sur la demande (FLX-SPEC-002, EF-2.5) ; code de vérification publique / Written act of the port's decision on the request (FLX-SPEC-002, EF-2.5); public verification code. Rôles émetteurs : CAP. Type de document : `AUTHORIZATION`. Répond à : `REQ:DOUBLE_BANKING`, `M9:9.01`. Offert : gabarit M9 ou escale reliée. Orientation : portrait. Objet : L'acte écrit de la décision « Accostage à couple » : la demande telle que déposée, la décision, sa validité, ses conditions et son code de vérification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |

**Section (champs) — Demande telle que déposée / Request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Demande / Request | ServiceRequest.reference | demi |
| Demandeur / Requester | ServiceRequest.requester_org, requester_role | demi |
| Déposée le / Submitted on | ServiceRequest.submitted_at | demi |
| Prestataire désigné / Provider named | ServiceRequest.provider_org | demi |

Note de section : Les valeurs ci-dessus sont celles saisies par le demandeur dans le registre ; elles ne sont pas modifiées par la décision. / The values above are those entered by the requester in the registry; the decision does not alter them.

**Section (champs) — Décision / Decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Décision / Decision | ServiceRequest.decision | demi |
| Prise par / Taken by | ServiceRequest.decision_org, decision_role | demi |
| Le / On | ServiceRequest.decided_at | demi |
| Numéro de l'autorisation / Authorization number | Authorization.number | demi |
| Effective du / Effective from | Authorization.valid_from | demi |
| Expire le / Expires on | Authorization.valid_until | demi |
| Portée / Scope | Authorization.scope | pleine |
| Conditions / Conditions | Authorization.conditions | pleine |

**Section (champs) — Accostage à couple / Double banking**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire intérieur / navire extérieur / Inner vessel / outer vessel | — (à compléter sur le papier) | demi |
| Durée autorisée / Authorized duration | — (à compléter sur le papier) | demi |
| États de chargement admis / Loading conditions admitted | — (à compléter sur le papier) | demi |
| Seuils météo / Weather thresholds | — (à compléter sur le papier) | demi |
| Conditions / Conditions | — (à compléter sur le papier) | pleine |

**Section (texte) — Mentions / Notes**

> La présente décision est prise au vu de la demande ci-dessus et des pièces du dossier de l'escale ; elle est enregistrée au journal chaîné du port. L'autorisation cesse de plein droit à sa date d'expiration ou en cas d'annulation, qui est notifiée au demandeur.
>
> *This decision is taken on the request above and the documents of the call file; it is recorded in the port's chained journal. The authorization lapses at its expiry or on cancellation, which is notified to the requester.*

> Un refus ou une demande d'information est motivé par écrit ; le motif est réservé au demandeur, à l'armateur et au service instructeur lorsque le type de demande le prévoit.
>
> *A refusal or a request for information is reasoned in writing; the reason is restricted to the requester, the owner and the instructing service where the request type so provides.*


**Signatures** : CAP — Autorité — décision / Authority — decision · AGE — Agence — réception / Agency — receipt · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.34 `BERTH_LIMITS` — Conditions limites d'exploitation du poste / Berth operating limits

Partie émettrice : CAP — Capitainerie. Standard : Pratique portuaire — ISGOTT 6e édition (limites du poste), PIANC (critères d'accostage), règlement d'exploitation du port / Port practice — ISGOTT 6th edition (berth limits), PIANC (berthing criteria), port operating regulations. Rôles émetteurs : CAP, TER. Type de document : `BERTH_LIMITS`. Répond à : `M0:12`, `M9:9.11`. Offert : toujours. Orientation : portrait. Objet : Les conditions limites (vent, houle, courant, visibilité, marée) publiées par la capitainerie pour le poste de l'escale.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Terminal / Terminal | CallParty TER active | demi |
| Type de poste / Kind of berth | Berth.kind | demi |

**Section (champs) — Caractéristiques du poste / Berth particulars**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Longueur utile / tirant d'eau maximal (m) / Usable length / maximum draft (m) | — (à compléter sur le papier) | demi |
| Déplacement / DWT maximal (t) / Maximum displacement / DWT (t) | — (à compléter sur le papier) | demi |
| Longueur hors tout maximale / minimale (m) / Maximum / minimum length overall (m) | — (à compléter sur le papier) | demi |
| Hauteur du collecteur admise (m) / Manifold height admitted (m) | — (à compléter sur le papier) | demi |
| Défenses (type, énergie) / Fenders (type, energy) | — (à compléter sur le papier) | demi |
| Bras / flexibles (nombre, diamètre, enveloppe) / Arms / hoses (number, diameter, envelope) | — (à compléter sur le papier) | demi |

**Section (tableau) — Limites d'exploitation / Operating limits**

Colonnes : Paramètre / Parameter · Accostage / Berthing · Séjour à quai / Stay alongside · Transfert / Transfer · Déhalage / appareillage / Unberthing.

Lignes préremplies : aucune ; lignes vierges ajoutées : 2.

Note de section : Au-delà d'une limite, l'opération concernée est suspendue et la capitainerie en est informée ; les limites sont rappelées au navire avant l'accostage (liste de contrôle, partie 1). / Beyond a limit the operation concerned is suspended and the harbour master informed; the limits are recalled to the ship before berthing (checklist, part 1).

**Section (champs) — Mesures et veille / Measures and watch**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Station météo de référence / Reference weather station | — (à compléter sur le papier) | demi |
| Fréquence de relevé pendant le séjour / Reading interval during the stay | — (à compléter sur le papier) | demi |
| Remorqueur en attente requis à partir de / Tug on standby required from | — (à compléter sur le papier) | demi |
| Moyens de largage d'urgence / Emergency release means | — (à compléter sur le papier) | demi |
| Publié le / valable jusqu'au / Published on / valid until | — (à compléter sur le papier) | demi |

**Signatures** : CAP — Capitainerie / Harbour master · TER — Terminal / Terminal · NAV — Capitaine — pris connaissance / Master — acknowledged

## 6.35 `ACCESS_LIST` — Demande et autorisation d'accès en zone portuaire / Port area access request and authorization

Partie émettrice : SUR — Sûreté. Standard : Code ISPS (contrôle d'accès à l'installation portuaire) ; règlement de sûreté du port / ISPS Code (port facility access control); port security regulations. Rôles émetteurs : AGE, SUR. Type de document : `ACCESS_LIST`. Répond à : `M8:8.04`. Offert : gabarit M7 ou M8. Orientation : portrait. Objet : La liste nominative des personnes et véhicules dont l'accès à la zone portuaire est demandé par l'agence et accordé par la sûreté.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Terminal / installation portuaire / Terminal / port facility | CallParty TER active | demi |
| Période d'accès demandée (de / à) / Access period requested (from / to) | — (à compléter sur le papier) | demi |

**Section (tableau) — Personnes / Persons**

Colonnes : Nom et prénom / Full name · Organisation / fonction / Organisation / capacity · Pièce d'identité n° / Identity document no. · Motif / Purpose · Date et heures / Date and hours · Autorisé ☐ / refusé ☐ / Granted ☐ / refused ☐.

Lignes préremplies : aucune ; lignes vierges ajoutées : 8.

**Section (tableau) — Véhicules et matériel / Vehicles and equipment**

Colonnes : Immatriculation / type / Registration / type · Conducteur / Driver · Chargement / Load · Date et heures / Date and hours · Autorisé ☐ / refusé ☐ / Granted ☐ / refused ☐.

Lignes préremplies : aucune ; lignes vierges ajoutées : 4.

**Section (champs) — Décision de l'autorité de sûreté / Security authority's decision**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Niveau de sûreté en vigueur / Security level in force | — (à compléter sur le papier) | demi |
| Badges délivrés (numéros) / Badges issued (numbers) | — (à compléter sur le papier) | demi |
| Conditions (escorte, zones, horaires) / Conditions (escort, areas, hours) | — (à compléter sur le papier) | pleine |
| Décision prise le / par / Decision taken on / by | — (à compléter sur le papier) | demi |

Note de section : Code ISPS, partie A §16 et partie B §16.10–16.17 : contrôle de l'accès à l'installation portuaire ; la liste est conservée avec le dossier de l'escale et n'y figure aucune donnée du domaine sûreté N4. / ISPS Code, part A §16 and part B §16.10–16.17: access control to the port facility; the list is kept with the call file and holds no N4 security data.

**Signatures** : AGE — Agence — demande / Agency — request · SUR — Autorité de sûreté — décision / Security authority — decision

## 6.36 `PRE_ARRIVAL_SECURITY` — Information de sûreté avant l'arrivée / Pre-arrival security information

Partie émettrice : SUR — Sûreté. Standard : SOLAS XI-2 règle 9.2.1 ; circulaire OMI MSC.1/Circ.1305 ; Convention FAL (formulaire d'information de sûreté) / SOLAS XI-2 regulation 9.2.1; IMO circular MSC.1/Circ.1305; FAL Convention (security information form). Rôles émetteurs : AGE, NAV. Type de document : `PRE_ARRIVAL_SECURITY`. Répond à : `M0:17`. Offert : toujours. Orientation : portrait. Objet : Les renseignements de sûreté que le navire communique avant l'arrivée : certificat ISSC, niveau de sûreté, dix dernières escales, opérations navire-navire.

**Section (champs) — Navire / Ship**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom / numéro OMI / Name / IMO number | Vessel.name, Vessel.imo | demi |
| Pavillon / port d'immatriculation / Flag / port of registry | Vessel.flag | demi |
| Indicatif / MMSI / Call sign / MMSI | Vessel.call_sign | demi |
| Jauge brute / Gross tonnage | — (à compléter sur le papier) | demi |
| Compagnie (exploitant) et n° OMI de compagnie / Company (operator) and company IMO number | — (à compléter sur le papier) | demi |
| Agent de sûreté de la compagnie (CSO) — contact / Company security officer (CSO) — contact | — (à compléter sur le papier) | demi |
| Certificat international de sûreté (ISSC) : délivré par, validité / International ship security certificate (ISSC): issued by, validity | — (à compléter sur le papier) | pleine |
| Port d'arrivée / poste / Port of arrival / berth | Port.name, poste | demi |
| ETA / ETA | PortCall.eta | demi |
| Niveau de sûreté actuel du navire / Current security level of the ship | — (à compléter sur le papier) | demi |
| Nombre de personnes à bord / Number of persons on board | — (à compléter sur le papier) | demi |

**Section (tableau) — Dix dernières escales (ordre chronologique) / Last ten ports of call (chronological order)**

Colonnes : Port, pays / Port, country · Installation portuaire / Port facility · Arrivée / Arrival · Départ / Departure · Niveau de sûreté / Security level · Mesures spéciales ou additionnelles / Special or additional measures.

Lignes préremplies : aucune ; lignes vierges ajoutées : 10.

**Section (tableau) — Opérations navire-navire pendant la période / Ship-to-ship activities during the period**

Colonnes : Lieu / Location · Date / Date · Navire / unité / Ship / unit · Nature de l'opération / Nature of activity · Mesures de sûreté appliquées / Security measures applied.

Lignes préremplies : aucune ; lignes vierges ajoutées : 3.

**Section (texte) — Déclaration / Declaration**

> Je certifie que les renseignements ci-dessus sont exacts et complets ; un plan de sûreté approuvé est en vigueur à bord et les procédures de sûreté ont été maintenues pendant la période indiquée.
>
> *I certify that the above information is true and complete; an approved ship security plan is in force on board and security procedures were maintained throughout the stated period.*


Note de section : Jeu de données normalisé de l'information de sûreté avant l'arrivée — SOLAS XI-2 règle 9.2.1 et circulaire OMI MSC.1/Circ.1305 ; formulaire FAL « pre-arrival security information ». / Standard data set of the pre-arrival security information — SOLAS XI-2 regulation 9.2.1 and IMO circular MSC.1/Circ.1305; FAL pre-arrival security information form.

**Signatures** : NAV — Capitaine ou agent de sûreté du navire (SSO) / Master or ship security officer (SSO) · SUR — Autorité de sûreté — reçu / Security authority — received

## 6.37 `ARRIVAL_NOTICE` — Avis d'arrivée (préavis 72 / 48 / 24 h) / Arrival notice (72 / 48 / 24 h pre-arrival notification)

Partie émettrice : AGE — Agence maritime. Standard : Pratique portuaire — règlement d'exploitation du port ; Convention FAL (notification préalable) / Port practice — port operating regulations; FAL Convention (advance notification). Rôles émetteurs : AGE. Type de document : `ARRIVAL_NOTICE`. Répond à : `M0:01`, `M0:08`. Offert : toujours. Orientation : portrait. Objet : Le préavis d'arrivée de l'agence : navire, heures prévues, opérations, services et formalités sollicités.

**Section (champs) — Navire / Vessel**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom / numéro OMI / Name / IMO number | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, vessel_type | demi |
| Indicatif / MMSI / Call sign / MMSI | Vessel.call_sign | demi |
| Port en lourd (t) / Deadweight (t) | Vessel.dwt | demi |
| Longueur hors tout / largeur (m) / Length overall / breadth (m) | Vessel.loa_m, beam_m | demi |
| Tirant d'eau à l'arrivée AV / AR (m) / Arrival draft fwd / aft (m) | — (à compléter sur le papier) | demi |
| Armateur / gestionnaire / Owner / manager | CallParty COM actives | demi |
| Agent consignataire / Shipping agent | PortCall.agency | demi |

**Section (champs) — Escale / Call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Référence / Reference | PortCall.reference | demi |
| Voyage / Voyage | PortCall.voyage_number | demi |
| ETA limite du port / ETA port limits | PortCall.eta | demi |
| ETB / ETB | PortCall.etb | demi |
| ETD / ETD | PortCall.etd | demi |
| Dernier port / prochain port / Last port / next port | PortCall.last_port, next_port | demi |
| Zone sollicitée / poste / Area requested / berth | PortCall.requested_berth_kind, berth | demi |
| Opérations / Operations | CallStage.operations | demi |
| Opération principale / Main operation | PortCall.template_codes | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity | demi |
| Terminal / réceptionnaire / Terminal / receiver | CallParty TER actives | demi |
| Inspecteur / Surveyor | CallParty INS actives | demi |

**Section (liste de contrôle) — Services et formalités sollicités / Services and formalities requested**

Colonnes à cocher : Oui / Yes · Non / No ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Pilotage, remorquage, lamanage à l'arrivée / Pilot, tugs, mooring gang on arrival |
| Libre pratique et formalités d'arrivée / Free pratique and arrival formalities |
| Soutage / Bunkering |
| Eau douce / provisions / relève d'équipage / Fresh water / provisions / crew change |
| Dépôt de déchets (notification préalable jointe) / Waste delivery (advance notification attached) |
| Travaux / immobilisation / Repairs / immobilization |

**Section (champs) — Pré-arrivée / Pre-arrival**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Jeu de données navire (Q88 / VPQ) transmis le / Vessel dataset (Q88 / VPQ) sent on | — (à compléter sur le papier) | demi |
| Certificats statutaires valides au départ prévu ☐ / Statutory certificates valid at planned departure ☐ | — (à compléter sur le papier) | demi |
| Contrôle des listes de sanctions (date, résultat) / Sanctions screening (date, result) | — (à compléter sur le papier) | demi |
| Dernière cargaison / état des citernes / Last cargo / tank condition | — (à compléter sur le papier) | demi |
| Marchandises dangereuses en colis à bord / Packaged dangerous goods on board | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

Note de section : Avis d'arrivée transmis à la capitainerie, à l'autorité portuaire, aux services nautiques et au terminal au moins 72 h, puis 48 h et 24 h avant l'arrivée (ou dès le départ du port précédent si le voyage est plus court). / Arrival notice sent to the harbour master, the port authority, the marine services and the terminal at least 72 h, then 48 h and 24 h before arrival (or on departure from the previous port when the voyage is shorter).

**Signatures** : AGE — Agence maritime / Shipping agency · CAP — Capitainerie — reçu / Harbour master — received

## 6.38 `SANCTIONS_CHECK` — Attestation de contrôle des listes de sanctions / Sanctions screening attestation

Partie émettrice : AGE — Agence maritime. Standard : OFAC Sanctions Advisory for the Maritime Industry (2020) ; guides BIMCO / ICS de conformité aux sanctions / OFAC Sanctions Advisory for the Maritime Industry (2020); BIMCO / ICS sanctions compliance guidance. Rôles émetteurs : AGE. Type de document : `SANCTIONS_CHECK`. Répond à : `M0:05`. Offert : toujours. Orientation : portrait. Objet : L'attestation par laquelle l'agence confirme le contrôle des listes de sanctions du navire, de ses intérêts et de la cargaison.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / origine / destination / Product / origin / destination | PortCall.product, last_port, next_port | demi |

**Section (tableau) — Parties et objets contrôlés / Parties and items screened**

Colonnes : Objet du contrôle / Item screened · Nom / identifiant / Name / identifier · Résultat (aucune correspondance / correspondance / levée) / Result (no match / match / cleared) · Date / Date.

Lignes préremplies : Vessel, CallParty COM et TER, PortCall.product ; lignes vierges ajoutées : 1.

**Section (champs) — Listes et outils consultés / Lists and tools consulted**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Listes de sanctions (ONU, UE, OFAC, OFSI, autres) / Sanctions lists (UN, EU, OFAC, OFSI, others) | — (à compléter sur le papier) | pleine |
| Outil ou prestataire de filtrage, version / Screening tool or provider, version | — (à compléter sur le papier) | demi |
| Pavillon et historique de changement de nom / pavillon / Flag and name / flag change history | — (à compléter sur le papier) | demi |
| Signalements AIS (coupures, falsifications) examinés / AIS reporting gaps and spoofing reviewed | — (à compléter sur le papier) | demi |
| Conclusion / Conclusion | — (à compléter sur le papier) | pleine |

**Section (texte) — Attestation / Attestation**

> L'agence atteste avoir effectué le contrôle ci-dessus à la date indiquée et n'avoir relevé aucune correspondance non levée ; toute correspondance est signalée à la capitainerie avant la déclaration de l'escale.
>
> *The agency attests that it carried out the screening above on the stated date and found no uncleared match; any match is reported to the harbour master before the call is declared.*


Note de section : Bonnes pratiques de conformité aux sanctions du transport maritime (OFAC Sanctions Advisory for the Maritime Industry, 2020 ; guides BIMCO / ICS) ; le contrôle se renouvelle avant chaque opération si les parties changent. / Maritime sanctions compliance good practice (OFAC Sanctions Advisory for the Maritime Industry, 2020; BIMCO / ICS guidance); the screening is renewed before each operation if the parties change.

**Signatures** : AGE — Agence — responsable conformité / Agency — compliance officer

## 6.39 `STS_NOTIFICATION` — Notification d'opération STS à l'État côtier / STS operation notification to the coastal State

Partie émettrice : AGE — Agence maritime. Standard : MARPOL annexe I, chapitre 8, règle 42 (notification 48 h) ; OCIMF Ship to Ship Transfer Guide / MARPOL Annex I, chapter 8, regulation 42 (48 h notification); OCIMF Ship to Ship Transfer Guide. Rôles émetteurs : AGE. Type de document : `STS_NOTIFICATION`. Répond à : `M3:3.01`. Offert : gabarit M3 ou escale reliée. Orientation : portrait. Objet : La notification préalable (48 h) de l'opération STS à l'État côtier : navires, lieu, date, produit, quantité, POAC.

**Section (champs) — Opération STS notifiée / STS operation notified**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire (ce dossier) / Vessel (this file) | Vessel.name, imo | demi |
| Pavillon / indicatif / Flag / call sign | Vessel.flag, call_sign | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Pavillon / indicatif du partenaire / Partner's flag / call sign | linked_call.vessel | demi |
| Date et heure prévues de début / Planned start date and time | PortCall.ets | demi |
| Durée prévue / Planned duration | — (à compléter sur le papier) | demi |
| Lieu (zone STS, position) / Location (STS area, position) | poste ou zone de l'étape | demi |
| Hydrocarbure (type) et quantité / Oil (type) and quantity | PortCall.product, quantity | demi |
| Prestataire STS / POAC / STS service provider / POAC | CallParty PRE active | demi |
| Autorité notifiée (État côtier, capitainerie) / Authority notified (coastal State, harbour master) | Port.name | demi |

**Section (liste de contrôle) — Confirmations / Confirmations**

Colonnes à cocher : Oui / Yes · Non / No ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Plan d'opérations STS approuvé par l'État du pavillon à bord (MARPOL annexe I, règle 41) / STS operations plan approved by the flag State on board (MARPOL Annex I, regulation 41) |
| Les deux navires sont des pétroliers de 150 jauge brute et plus au sens de la règle 40 / Both ships are oil tankers of 150 gross tonnage and above within the meaning of regulation 40 |
| Notification faite au moins 48 h avant l'opération (règle 42) / Notification given at least 48 h before the operation (regulation 42) |
| Les enregistrements de l'opération seront conservés à bord trois ans / Records of the operation will be kept on board for three years |

**Section (texte) — Notification / Notification**

> Conformément à la règle 42 de l'annexe I de MARPOL, l'agence notifie à l'État côtier, au nom du capitaine, l'opération de transbordement ci-dessus ; toute modification des éléments notifiés est communiquée sans délai.
>
> *In accordance with regulation 42 of MARPOL Annex I, the agency notifies the coastal State, on behalf of the master, of the above transfer operation; any change to the notified particulars is communicated without delay.*


**Signatures** : AGE — Agence, pour le capitaine / Agency, for the master · CAP — Autorité — reçu / Authority — received

## 6.40 `POAC_DESIGNATION` — Désignation du POAC — mandat écrit / POAC designation — written mandate

Partie émettrice : AGE — Agence maritime. Standard : OCIMF Ship to Ship Transfer Guide (2013) ; MARPOL annexe I, règle 41 / OCIMF Ship to Ship Transfer Guide (2013); MARPOL Annex I, regulation 41. Rôles émetteurs : AGE. Type de document : `STS_DOC`. Répond à : `M3:3.04`. Offert : gabarit M3 ou escale reliée. Orientation : portrait. Objet : Le mandat écrit désignant le POAC de l'opération STS, avec ses qualifications.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Prestataire STS / STS service provider | CallParty PRE active | demi |

**Section (champs) — Personne responsable de l'opération (POAC) / Person in overall advisory control (POAC)**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom et prénom / Full name | — (à compléter sur le papier) | demi |
| Employeur / Employer | — (à compléter sur le papier) | demi |
| Brevet de capitaine / qualification / Master's licence / qualification | — (à compléter sur le papier) | demi |
| Expérience STS (nombre d'opérations, types de navires) / STS experience (number of operations, ship types) | — (à compléter sur le papier) | pleine |
| Formation STS suivie (organisme, date) / STS training completed (body, date) | — (à compléter sur le papier) | demi |
| Contact (VHF, téléphone) / Contact (VHF, telephone) | — (à compléter sur le papier) | demi |

**Section (texte) — Mandat / Mandate**

> L'agence, au nom des parties à l'opération, désigne la personne ci-dessus comme POAC de l'opération de transbordement. Le POAC conseille les deux capitaines sur l'approche, l'amarrage, le transfert et la séparation ; la responsabilité de la sécurité de chaque navire reste à son capitaine.
>
> *The agency, on behalf of the parties to the operation, appoints the person above as POAC of the transfer operation. The POAC advises both masters on approach, mooring, transfer and unmooring; the safety of each ship remains the responsibility of its master.*

> Les justificatifs de qualification sont joints au dossier STS de l'escale.
>
> *The qualification documents are attached to the STS file of the call.*


Note de section : OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapitre 1.5 et 3 ; MARPOL annexe I, règle 41. / OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapters 1.5 and 3; MARPOL Annex I, regulation 41.

**Signatures** : AGE — Agence / Agency · PRE — POAC — accepte le mandat / POAC — accepts the mandate · NAV — Capitaine / Master

## 6.41 `CARGO_DECLARATION` — Déclaration de cargaison (FAL 2) — arrivée / Cargo declaration (FAL 2) — arrival

Partie émettrice : AGE — Agence maritime. Standard : Convention FAL de l'OMI, formulaire 2 / IMO FAL Convention, form 2. Rôles émetteurs : AGE. Type de document : `CARGO_DECLARATION`. Répond à : `M1:1.18`. Offert : gabarit M1. Orientation : portrait. Objet : La déclaration douanière de la cargaison déchargée (FAL 2), pré-remplie du produit et de la quantité de l'escale.

**Section (champs) — Navire et escale / Ship and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Arrivée ☐ Départ ☐ / Arrival ☐ Departure ☐ | — (à compléter sur le papier) | demi |
| Nom et type du navire / Name and type of ship | Vessel.name, vessel_type | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Indicatif / Call sign | Vessel.call_sign | demi |
| Pavillon / Flag State of ship | Vessel.flag | demi |
| Nom du capitaine / Name of master | — (à compléter sur le papier) | demi |
| Port d'arrivée / de départ / Port of arrival / departure | Port.name | demi |
| Date d'arrivée / de départ / Date of arrival / departure | PortCall.ata, eta | demi |
| Dernier port / prochain port / Last port / next port | PortCall.last_port, next_port | demi |
| Agent / Agent | PortCall.agency | demi |

**Section (tableau) — Cargaison / Cargo**

Colonnes : N° de connaissement / B/L number · Description des marchandises (produit, grade) / Description of goods (product, grade) · Quantité (masse / volume) / Quantity (mass / volume) · Port de chargement / Port of loading · Port de déchargement / Port of discharge · Marques, observations / Marks, remarks.

Lignes préremplies : PortCall.product, quantity, last_port, next_port ; lignes vierges ajoutées : 3.

**Section (champs) — Compléments / Additional particulars**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Cargaison restant à bord (transit) / Cargo remaining on board (in transit) | — (à compléter sur le papier) | demi |
| Date de fin des opérations / Date of completion of cargo operations | jalon TRANSFER_END | demi |
| Déclaration douanière / manifeste n° / Customs declaration / manifest number | — (à compléter sur le papier) | demi |
| Régime douanier / Customs procedure | — (à compléter sur le papier) | demi |

Note de section : Modèle de la déclaration de cargaison, formulaire FAL 2 de l'OMI (Convention FAL, annexe, section 2) ; vrac liquide : une ligne par produit et par connaissement. / Model of the cargo declaration, IMO FAL form 2 (FAL Convention, annex, section 2); liquid bulk: one line per product and per bill of lading.

**Section (texte) — Déclaration / Declaration**

> Le capitaine (ou l'agent autorisé) certifie l'exactitude de la présente déclaration.
>
> *The master (or authorized agent) certifies this declaration to be correct.*


**Signatures** : AGE — Agent autorisé / Authorized agent · ADM — Douanes — visa / Customs — endorsement

## 6.42 `EXPORT_MANIFEST` — Manifeste et déclaration de cargaison (FAL 2) — départ / Outward manifest and cargo declaration (FAL 2) — departure

Partie émettrice : AGE — Agence maritime. Standard : Convention FAL de l'OMI, formulaire 2 (départ) / IMO FAL Convention, form 2 (departure). Rôles émetteurs : AGE. Type de document : `EXPORT_MANIFEST`. Répond à : `M2:2.18`. Offert : gabarit M2. Orientation : portrait. Objet : Le manifeste de sortie et la déclaration d'exportation de la cargaison chargée (FAL 2).

**Section (champs) — Navire et escale / Ship and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Arrivée ☐ Départ ☐ / Arrival ☐ Departure ☐ | — (à compléter sur le papier) | demi |
| Nom et type du navire / Name and type of ship | Vessel.name, vessel_type | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Indicatif / Call sign | Vessel.call_sign | demi |
| Pavillon / Flag State of ship | Vessel.flag | demi |
| Nom du capitaine / Name of master | — (à compléter sur le papier) | demi |
| Port d'arrivée / de départ / Port of arrival / departure | Port.name | demi |
| Date d'arrivée / de départ / Date of arrival / departure | PortCall.ata, eta | demi |
| Dernier port / prochain port / Last port / next port | PortCall.last_port, next_port | demi |
| Agent / Agent | PortCall.agency | demi |

**Section (tableau) — Cargaison / Cargo**

Colonnes : N° de connaissement / B/L number · Description des marchandises (produit, grade) / Description of goods (product, grade) · Quantité (masse / volume) / Quantity (mass / volume) · Port de chargement / Port of loading · Port de déchargement / Port of discharge · Marques, observations / Marks, remarks.

Lignes préremplies : PortCall.product, quantity, last_port, next_port ; lignes vierges ajoutées : 3.

**Section (champs) — Compléments / Additional particulars**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Cargaison restant à bord (transit) / Cargo remaining on board (in transit) | — (à compléter sur le papier) | demi |
| Date de fin des opérations / Date of completion of cargo operations | jalon TRANSFER_END | demi |
| Déclaration douanière / manifeste n° / Customs declaration / manifest number | — (à compléter sur le papier) | demi |
| Régime douanier / Customs procedure | — (à compléter sur le papier) | demi |

Note de section : Modèle de la déclaration de cargaison, formulaire FAL 2 de l'OMI (Convention FAL, annexe, section 2) ; vrac liquide : une ligne par produit et par connaissement. / Model of the cargo declaration, IMO FAL form 2 (FAL Convention, annex, section 2); liquid bulk: one line per product and per bill of lading.

**Section (texte) — Déclaration / Declaration**

> Le capitaine (ou l'agent autorisé) certifie l'exactitude de la présente déclaration.
>
> *The master (or authorized agent) certifies this declaration to be correct.*


**Signatures** : AGE — Agent autorisé / Authorized agent · ADM — Douanes — visa / Customs — endorsement

## 6.43 `FAL_STORES` — Provisions de bord et effets de l'équipage (FAL 3 et 4) / Ship's stores and crew's effects (FAL 3 and 4)

Partie émettrice : AGE — Agence maritime. Standard : Convention FAL de l'OMI, formulaires 3 et 4 / IMO FAL Convention, forms 3 and 4. Rôles émetteurs : AGE, NAV. Type de document : `FAL_FORMS`. Répond à : `M0:13`, `M8:8.05`. Offert : toujours. Orientation : portrait. Objet : Les déclarations des provisions de bord et des effets de l'équipage (FAL 3 et 4) remises aux douanes.

**Section (champs) — Navire et escale / Ship and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Arrivée ☐ Départ ☐ / Arrival ☐ Departure ☐ | — (à compléter sur le papier) | demi |
| Nom et type du navire / Name and type of ship | Vessel.name, vessel_type | demi |
| Numéro OMI / IMO number | Vessel.imo | demi |
| Indicatif / Call sign | Vessel.call_sign | demi |
| Pavillon / Flag State of ship | Vessel.flag | demi |
| Nom du capitaine / Name of master | — (à compléter sur le papier) | demi |
| Port d'arrivée / de départ / Port of arrival / departure | Port.name | demi |
| Date d'arrivée / de départ / Date of arrival / departure | PortCall.ata, eta | demi |
| Dernier port / prochain port / Last port / next port | PortCall.last_port, next_port | demi |
| Agent / Agent | PortCall.agency | demi |

**Section (tableau) — Provisions de bord (FAL 3) / Ship's stores (FAL 3)**

Colonnes : Article / Name of article · Quantité / Quantity · Emplacement à bord / Location on board · Usage officiel / Official use.

Lignes préremplies : aucune ; lignes vierges ajoutées : 3.

**Section (tableau) — Effets de l'équipage (FAL 4) / Crew's effects (FAL 4)**

Colonnes : N° / No. · Nom de famille, prénoms / Family name, given names · Fonction / Rank or rating · Effets soumis à droits ou à restriction / Effects liable to duty or restriction · Signature / Signature.

Lignes préremplies : aucune ; lignes vierges ajoutées : 8.

**Section (texte) — Déclaration / Declaration**

> Le capitaine certifie que les provisions de bord et les effets déclarés ci-dessus sont exacts ; les provisions sous scellés sont tenues à la disposition des douanes.
>
> *The master certifies that the ship's stores and effects declared above are correct; bonded stores are kept at the disposal of customs.*


Note de section : Modèles des formulaires FAL 3 (provisions de bord) et FAL 4 (effets de l'équipage) de l'OMI. / Models of IMO FAL forms 3 (ship's stores) and 4 (crew's effects).

**Signatures** : NAV — Capitaine / Master · ADM — Douanes — visa / Customs — endorsement

## 6.44 `CREW_CHANGE_LIST` — Liste de relève d'équipage / Crew change list

Partie émettrice : AGE — Agence maritime. Standard : Convention FAL de l'OMI (relèves d'équipage) ; Convention STCW ; pratique de l'immigration / IMO FAL Convention (crew changes); STCW Convention; immigration practice. Rôles émetteurs : AGE. Type de document : `CREW_DOC`. Répond à : `M8:8.01`. Offert : gabarit M8. Orientation : portrait. Objet : La liste des embarquants et débarquants avec leurs documents, déposée pour la relève d'équipage.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Date de relève prévue / Planned crew change date | — (à compléter sur le papier) | demi |
| Effectif minimal de sécurité (document n°) / Minimum safe manning (document no.) | — (à compléter sur le papier) | demi |

**Section (tableau) — Embarquants / Joiners**

Colonnes : Nom et prénoms / Full name · Fonction / Rank · Nationalité / Nationality · Passeport n° / validité / Passport no. / validity · Visa / lettre de garantie / Visa / guarantee letter · Brevet (STCW) n° / Certificate (STCW) no. · Certificat médical valide ☐ / Valid medical certificate ☐ · Vol / arrivée / Flight / arrival.

Lignes préremplies : aucune ; lignes vierges ajoutées : 6.

**Section (tableau) — Débarquants / Leavers**

Colonnes : Nom et prénoms / Full name · Fonction / Rank · Nationalité / Nationality · Passeport n° / validité / Passport no. / validity · Visa / transit / Visa / transit · Vol / départ / Flight / departure · Rapatriement organisé par / Repatriation arranged by.

Lignes préremplies : aucune ; lignes vierges ajoutées : 6.

**Section (champs) — Accompagnement / Arrangements**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Hébergement et transport / Accommodation and transport | — (à compléter sur le papier) | demi |
| Laissez-passer demandés (nombre) / Passes requested (number) | — (à compléter sur le papier) | demi |
| Agence de manning / armateur / Manning agency / owner | CallParty COM actives | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

Note de section : Documents contrôlés par l'immigration (passeports, visas), l'autorité maritime (brevets STCW, effectif minimal) et la santé (certificats médicaux) ; Convention FAL, section 3 (relèves d'équipage). / Documents checked by immigration (passports, visas), the maritime authority (STCW certificates, safe manning) and health (medical certificates); FAL Convention, section 3 (crew changes).

**Signatures** : AGE — Agence / Agency · NAV — Capitaine / Master · ADM — Immigration — visa / Immigration — endorsement

## 6.45 `BILL_OF_LADING` — Connaissement — données d'émission / Bill of lading — issuing data

Partie émettrice : AGE — Agence maritime. Standard : Pratique du commerce des hydrocarbures (connaissement de charte-partie, type CONGENBILL / BIMCO) ; Règles de La Haye-Visby / Oil trade practice (charter-party bill of lading, CONGENBILL / BIMCO type); Hague-Visby Rules. Rôles émetteurs : AGE. Type de document : `BILL_OF_LADING`. Répond à : `M2:2.17`. Offert : gabarit M2. Orientation : portrait. Objet : Les données d'émission du connaissement, pré-remplies de la quantité convenue ; l'émission reste verrouillée par le point d'arrêt BL_ISSUE.

**Section (champs) — Parties / Parties**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Expéditeur (shipper) / Shipper | — (à compléter sur le papier) | pleine |
| Destinataire (consignee) — à l'ordre de / Consignee — to the order of | — (à compléter sur le papier) | pleine |
| Notifier (notify party) / Notify party | — (à compléter sur le papier) | pleine |
| Armateur / transporteur / Carrier | CallParty COM actives | demi |

**Section (champs) — Navire et voyage / Vessel and voyage**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, imo | demi |
| Pavillon / Flag | Vessel.flag | demi |
| Port de chargement / Port of loading | Port.name ou PortCall.last_port | demi |
| Port de déchargement / Port of discharge | PortCall.next_port ou Port.name | demi |
| Date d'embarquement (shipped on board) / Shipped on board date | PortCall.t1 (fin de transfert) | demi |
| Voyage / Voyage | PortCall.voyage_number | demi |

**Section (tableau) — Marchandises / Goods**

Colonnes : Description (produit, grade, spécification) / Description (product, grade, specification) · Quantité (masse) / Quantity (mass) · Volume à 15 °C / 60 °F / Volume at 15 °C / 60 °F · Densité à 15 °C / API / Density at 15 °C / API · Température / Temperature · Base du chiffre (bord / terre / inspecteur) / Basis of figure (ship / shore / surveyor).

Lignes préremplies : PortCall.product, quantity ; Measurement BL (valeurs bord, terre, inspecteur) ; lignes vierges ajoutées : 1.

**Section (champs) — Conditions / Terms**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Fret (payé d'avance / à destination) / Freight (prepaid / collect) | — (à compléter sur le papier) | demi |
| Nombre d'originaux / Number of originals | — (à compléter sur le papier) | demi |
| Charte-partie de référence (date) / Charter-party referred to (date) | — (à compléter sur le papier) | demi |
| Clauses (poids inconnu, said to contain…) / Clauses (weight unknown, said to contain…) | — (à compléter sur le papier) | pleine |
| Lieu et date d'émission / Place and date of issue | Port.name | demi |
| Signé par (capitaine / agent pour le capitaine) / Signed by (master / agent for the master) | — (à compléter sur le papier) | demi |

Note de section : Le connaissement est émis sur l'instruction documentaire écrite du mandant (tâche M2:2.16) et après accord sur la quantité : la plateforme refuse l'émission tant que le point d'arrêt BL_ISSUE n'est pas levé ; aucun rôle ne lève ce verrou. / The bill of lading is issued on the principal's written documentary instructions (task M2:2.16) and after agreement on the quantity: the platform refuses the issue until the BL_ISSUE hold point is cleared; no role lifts this lock.

**Signatures** : AGE — Agent, pour le capitaine / Agent, for the master · NAV — Capitaine / Master

## 6.46 `PORT_ACCOUNT` — Compte d'escale final (FDA) / Final disbursement account (FDA)

Partie émettrice : AGE — Agence maritime. Standard : Pratique de l'agence maritime (FONASBA — Standard Disbursement Account) / Shipping agency practice (FONASBA — Standard Disbursement Account). Rôles émetteurs : AGE. Type de document : `PORT_ACCOUNT`. Répond à : `M0:38`. Offert : toujours. Orientation : portrait. Objet : Le compte d'escale final transmis au mandant avec ses justificatifs.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Mandant (armateur / affréteur) / Principal (owner / charterer) | CallParty COM actives | demi |
| Arrivée / départ / Arrival / departure | PortCall.ata, atd | demi |

**Section (tableau) — Relevé des prestations / Statement of services**

Colonnes : Poste / Item · Prestataire / référence / Provider / reference · Base (durée, quantité) / Basis (duration, quantity) · Montant / Amount · Devise / Currency · Justificatif joint n° / Supporting document no..

Lignes préremplies : aucune ; lignes vierges ajoutées : 2.

**Section (champs) — Totaux / Totals**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Total des débours / Total disbursements | — (à compléter sur le papier) | demi |
| Avance de fonds reçue / Advance received | — (à compléter sur le papier) | demi |
| Solde dû / à rembourser / Balance due / refundable | — (à compléter sur le papier) | demi |
| Coordonnées bancaires de l'agence / Agency bank details | — (à compléter sur le papier) | pleine |

Note de section : Compte d'escale final (FDA) établi sur les justificatifs des prestataires et les durées du registre ; chaque justificatif est déposé comme document de l'escale (confidentialité N3 : mandant, agence). / Final disbursement account (FDA) built on the providers' supporting documents and the registry's durations; each supporting document is filed as a document of the call (N3: principal, agency).

**Signatures** : AGE — Agence / Agency · COM — Mandant — reçu / Principal — received

## 6.47 `BALLAST_NOTIFICATION` — Notification des eaux de ballast (BWRF) / Ballast water reporting form (BWRF)

Partie émettrice : NAV — Navire / capitaine. Standard : Convention BWM 2004 ; résolution OMI A.868(20), appendice 2 (Ballast Water Reporting Form) / BWM Convention 2004; IMO resolution A.868(20), appendix 2 (Ballast Water Reporting Form). Rôles émetteurs : NAV. Type de document : `BALLAST_NOTIFICATION`. Répond à : `M0:15`, `M5:5.02`, `M5:5.03`. Offert : toujours. Orientation : portrait. Objet : La notification des eaux de ballast à bord : volumes, origine, méthode de conformité, rejets prévus.

**Section (champs) — Navire / Vessel information**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom / numéro OMI / Name / IMO number | Vessel.name, imo | demi |
| Pavillon / Flag | Vessel.flag | demi |
| Armateur / gestionnaire / Owner / manager | CallParty COM actives | demi |
| Type / Type | Vessel.vessel_type | demi |
| Jauge brute / port en lourd (t) / Gross tonnage / deadweight (t) | Vessel.dwt | demi |
| Agent / Agent | PortCall.agency | demi |
| Port d'arrivée / date / Arrival port / date | Port.name, PortCall.ata/eta | demi |
| Dernier port / prochain port / Last port / next port | PortCall.last_port, next_port | demi |
| Capacité totale de ballast (m³) / Total ballast water capacity (m³) | — (à compléter sur le papier) | demi |
| Volume total de ballast à bord (m³) / Total ballast water on board (m³) | — (à compléter sur le papier) | demi |
| Nombre de citernes de ballast / Total number of ballast tanks | — (à compléter sur le papier) | demi |
| Citernes à rejeter dans le port (nombre) / Tanks to be discharged in port (number) | — (à compléter sur le papier) | demi |

**Section (champs) — Gestion des eaux de ballast / Ballast water management**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Plan de gestion des eaux de ballast à bord ☐ appliqué ☐ / Ballast water management plan on board ☐ implemented ☐ | — (à compléter sur le papier) | demi |
| Méthode de conformité : D-1 échange ☐ D-2 système de traitement ☐ autre ☐ / Compliance method: D-1 exchange ☐ D-2 treatment system ☐ other ☐ | — (à compléter sur le papier) | demi |
| Système de traitement (type, approbation) — état : opérationnel ☐ en dérogation ☐ / Treatment system (type, approval) — status: operational ☐ under exemption ☐ | — (à compléter sur le papier) | pleine |
| Certificat international de gestion des eaux de ballast (validité) / International ballast water management certificate (validity) | — (à compléter sur le papier) | demi |
| Registre des eaux de ballast à jour ☐ / Ballast water record book up to date ☐ | — (à compléter sur le papier) | demi |

**Section (tableau) — Historique des eaux de ballast par citerne / Ballast water history per tank**

Colonnes : Citerne / cale / Tank / hold · Origine : date, port ou position, volume (m³), temp. (°C) / Source: date, port or position, volume (m³), temp. (°C) · Échange / traitement : date, position, volume (m³), méthode / Exchange / treatment: date, position, volume (m³), method · Rejet prévu : date, port ou position, volume (m³) / Intended discharge: date, port or position, volume (m³) · Nature (séparé, propre, souillé) / Nature (segregated, clean, dirty).

Lignes préremplies : aucune ; lignes vierges ajoutées : 8.

**Section (texte) — Déclaration / Declaration**

> Le responsable de la gestion des eaux de ballast certifie que les renseignements ci-dessus sont exacts et que le registre des eaux de ballast en fait foi.
>
> *The responsible officer certifies that the above information is correct and that the ballast water record book bears it out.*


Note de section : Modèle du Ballast Water Reporting Form (résolution OMI A.868(20), appendice 2) adapté à la Convention BWM 2004 (règles B-4, D-1, D-2) ; à transmettre avant l'arrivée. / Model of the Ballast Water Reporting Form (IMO resolution A.868(20), appendix 2) adapted to the BWM Convention 2004 (regulations B-4, D-1, D-2); to be sent before arrival.

**Signatures** : NAV — Officier responsable des eaux de ballast / Responsible ballast water officer · CAP — Autorité — reçu / Authority — received

## 6.48 `DISCHARGE_PLAN` — Plan de déchargement et de ballastage / Discharge and ballast plan

Partie émettrice : NAV — Navire / capitaine. Standard : ISGOTT, 6e édition, chapitre 22 / ISGOTT, 6th edition, chapter 22. Rôles émetteurs : NAV. Type de document : `DISCHARGE_PLAN`. Répond à : `M1:1.02`. Offert : gabarit M1. Orientation : portrait. Objet : Le plan de déchargement et de ballastage remis au terminal avant la réunion pré-transfert.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Terminal / Terminal | CallParty TER active | demi |
| Produit / quantité nominée / Product / nominated quantity | PortCall.product, quantity | demi |

**Section (champs) — Paramètres du plan / Plan parameters**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Débit initial / maximal / de fin (m³/h) / Initial / maximum / topping-off rate (m³/h) | — (à compléter sur le papier) | demi |
| Pression maximale au collecteur (bar) / Maximum manifold pressure (bar) | — (à compléter sur le papier) | demi |
| Nombre de lignes et de pompes / Number of lines and pumps | — (à compléter sur le papier) | demi |
| Température du produit (°C) / densité / Product temperature (°C) / density | — (à compléter sur le papier) | demi |
| Tirant d'eau et assiette : début / fin (m) / Draft and trim: start / end (m) | — (à compléter sur le papier) | demi |
| Stabilité (GM) et contraintes de structure (SF, BM) vérifiées ☐ / Stability (GM) and structural limits (SF, BM) checked ☐ | — (à compléter sur le papier) | demi |
| Gaz inerte : O₂ (%) et pression des citernes / Inert gas: O₂ (%) and tank pressure | — (à compléter sur le papier) | demi |
| Durée prévue (h) / Planned duration (h) | — (à compléter sur le papier) | demi |

**Section (tableau) — Séquence de déchargement des citernes / Tank discharge sequence**

Colonnes : Ordre / Order · Citerne / Tank · Produit / Product · Quantité (m³ / t) / Quantity (m³ / t) · Creux final (m) / Final ullage (m) · Débit (m³/h) / Rate (m³/h) · Début / fin prévus / Planned start / end · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 10.

**Section (tableau) — Séquence de ballastage / déballastage simultané / Simultaneous ballasting / deballasting sequence**

Colonnes : Ordre / Order · Citerne de ballast / Ballast tank · Opération / Operation · Volume (m³) / Volume (m³) · Début / fin / Start / end · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 5.

**Section (texte) — Accord / Agreement**

> Le plan est établi par le chef de la cargaison sous l'autorité du capitaine et discuté avec le terminal à la réunion pré-transfert ; toute modification en cours d'opération est convenue entre les responsables de permanence et consignée.
>
> *The plan is prepared by the chief officer under the master's authority and discussed with the terminal at the pre-transfer meeting; any change during the operation is agreed between the persons on duty and recorded.*


Note de section : ISGOTT, 6e édition, chapitre 22 (plans de chargement et de déchargement) et 25 (réunion pré-transfert). / ISGOTT, 6th edition, chapter 22 (loading and discharge plans) and 25 (pre-transfer meeting).

**Signatures** : NAV — Chef de la cargaison / capitaine / Chief officer / master · TER — Terminal — accord / Terminal — agreed

## 6.49 `LOADING_PLAN` — Plan de chargement / Loading plan

Partie émettrice : NAV — Navire / capitaine. Standard : ISGOTT, 6e édition, chapitre 22 / ISGOTT, 6th edition, chapter 22. Rôles émetteurs : NAV. Type de document : `LOADING_PLAN`. Répond à : `M2:2.03`. Offert : gabarit M2. Orientation : portrait. Objet : Le plan de chargement : séquence, stabilité, contraintes de structure, tirant d'eau.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Terminal / Terminal | CallParty TER active | demi |
| Produit / quantité nominée / Product / nominated quantity | PortCall.product, quantity | demi |

**Section (champs) — Paramètres du plan / Plan parameters**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Débit initial / maximal / de fin (m³/h) / Initial / maximum / topping-off rate (m³/h) | — (à compléter sur le papier) | demi |
| Pression maximale au collecteur (bar) / Maximum manifold pressure (bar) | — (à compléter sur le papier) | demi |
| Nombre de lignes et de pompes / Number of lines and pumps | — (à compléter sur le papier) | demi |
| Température du produit (°C) / densité / Product temperature (°C) / density | — (à compléter sur le papier) | demi |
| Tirant d'eau et assiette : début / fin (m) / Draft and trim: start / end (m) | — (à compléter sur le papier) | demi |
| Stabilité (GM) et contraintes de structure (SF, BM) vérifiées ☐ / Stability (GM) and structural limits (SF, BM) checked ☐ | — (à compléter sur le papier) | demi |
| Gaz inerte : O₂ (%) et pression des citernes / Inert gas: O₂ (%) and tank pressure | — (à compléter sur le papier) | demi |
| Durée prévue (h) / Planned duration (h) | — (à compléter sur le papier) | demi |

**Section (tableau) — Séquence de chargement des citernes / Tank loading sequence**

Colonnes : Ordre / Order · Citerne / Tank · Produit / Product · Quantité (m³ / t) / Quantity (m³ / t) · Creux final (m) / Final ullage (m) · Débit (m³/h) / Rate (m³/h) · Début / fin prévus / Planned start / end · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 10.

**Section (tableau) — Séquence de ballastage / déballastage simultané / Simultaneous ballasting / deballasting sequence**

Colonnes : Ordre / Order · Citerne de ballast / Ballast tank · Opération / Operation · Volume (m³) / Volume (m³) · Début / fin / Start / end · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 5.

**Section (texte) — Accord / Agreement**

> Le plan est établi par le chef de la cargaison sous l'autorité du capitaine et discuté avec le terminal à la réunion pré-transfert ; toute modification en cours d'opération est convenue entre les responsables de permanence et consignée.
>
> *The plan is prepared by the chief officer under the master's authority and discussed with the terminal at the pre-transfer meeting; any change during the operation is agreed between the persons on duty and recorded.*


Note de section : ISGOTT, 6e édition, chapitre 22 (plans de chargement et de déchargement) et 25 (réunion pré-transfert). / ISGOTT, 6th edition, chapter 22 (loading and discharge plans) and 25 (pre-transfer meeting).

**Signatures** : NAV — Chef de la cargaison / capitaine / Chief officer / master · TER — Terminal — accord / Terminal — agreed

## 6.50 `LAST_CARGOES` — Déclaration des trois dernières cargaisons / Last three cargoes declaration

Partie émettrice : NAV — Navire / capitaine. Standard : Pratique des terminaux et du vetting (Q88, ISGOTT ch. 22.4) / Terminal and vetting practice (Q88, ISGOTT ch. 22.4). Rôles émetteurs : NAV. Type de document : `LAST_CARGOES`. Répond à : `M2:2.02`. Offert : gabarit M2. Orientation : portrait. Objet : La déclaration des trois dernières cargaisons par citerne et du nettoyage effectué, avant chargement.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit à charger / Product to be loaded | PortCall.product | demi |
| Terminal / Terminal | CallParty TER active | demi |

**Section (tableau) — Trois dernières cargaisons par citerne / Last three cargoes per tank**

Colonnes : Citerne / Tank · Dernière cargaison (produit, port, date) / Last cargo (product, port, date) · Avant-dernière / Second last · Antépénultième / Third last · Nettoyage effectué (méthode, date) / Cleaning carried out (method, date) · État : inerté ☐ dégazé ☐ / Condition: inerted ☐ gas-free ☐.

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

**Section (champs) — Lignes et pompes / Lines and pumps**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Dernier produit dans les lignes et pompes / Last product in lines and pumps | — (à compléter sur le papier) | demi |
| Lignes purgées / rincées (méthode) / Lines drained / flushed (method) | — (à compléter sur le papier) | demi |
| Revêtement des citernes / Tank coating | — (à compléter sur le papier) | demi |
| Ségrégation prévue pour la cargaison / Segregation planned for the cargo | — (à compléter sur le papier) | demi |

**Section (texte) — Déclaration / Declaration**

> Le capitaine déclare que les citernes désignées pour le chargement ont contenu les cargaisons ci-dessus et sont dans l'état indiqué ; l'inspection contradictoire des citernes et le certificat de propreté restent du ressort de l'inspecteur.
>
> *The master declares that the tanks nominated for loading carried the cargoes above and are in the stated condition; the joint tank inspection and the cleanliness certificate remain the surveyor's.*


Note de section : Exigence usuelle des terminaux et du vetting (questionnaire Q88 § cargo history ; ISGOTT ch. 22.4) : compatibilité du produit avec les cargaisons précédentes et le revêtement. / Usual terminal and vetting requirement (Q88 cargo history; ISGOTT ch. 22.4): compatibility of the product with the previous cargoes and the coating.

**Signatures** : NAV — Capitaine / Master · TER — Terminal — reçu / Terminal — received

## 6.51 `INERT_GAS_DECLARATION` — Déclaration d'inertage et de teneur en oxygène / Inert gas and oxygen content declaration

Partie émettrice : NAV — Navire / capitaine. Standard : SOLAS II-2 règle 16.3 ; code FSS chapitre 15 ; ISGOTT 6e édition, chapitre 7 / SOLAS II-2 regulation 16.3; FSS Code chapter 15; ISGOTT 6th edition, chapter 7. Rôles émetteurs : NAV. Type de document : `INERT_GAS_DECLARATION`. Répond à : `M1:1.04`, `M2:2.06`. Offert : gabarit M1 ou M2 ou M3 ou escale reliée. Orientation : portrait. Objet : La déclaration de l'état du gaz inerte et de la teneur en oxygène des citernes avant le transfert.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Opération / Operation | PortCall.template_codes | demi |
| Terminal / Terminal | CallParty TER active | demi |

**Section (champs) — Système de gaz inerte / Inert gas system**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Type (gaz de combustion, générateur, azote) / Type (flue gas, generator, nitrogen) | — (à compléter sur le papier) | demi |
| En service ☐ hors service ☐ — depuis / Operational ☐ out of service ☐ — since | — (à compléter sur le papier) | demi |
| Teneur en O₂ du gaz délivré (%) / O₂ content of the gas delivered (%) | — (à compléter sur le papier) | demi |
| Pression de dégagement / dépression (mbar) / P/V valve setting (mbar) | — (à compléter sur le papier) | demi |
| Analyseurs d'oxygène étalonnés le / Oxygen analysers calibrated on | — (à compléter sur le papier) | demi |
| Heure du relevé / Time of readings | — (à compléter sur le papier) | demi |

**Section (tableau) — Relevé par citerne / Readings per tank**

Colonnes : Citerne / Tank · O₂ (%) / O₂ (%) · Pression (mbar) / Pressure (mbar) · Teneur en hydrocarbures (% LEL / vol.) / Hydrocarbon content (% LEL / vol.) · Inertée ☐ / Inerted ☐ · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

**Section (texte) — Déclaration / Declaration**

> Le capitaine déclare que les citernes à cargaison sont inertées, que leur teneur en oxygène ne dépasse pas 8 % en volume et qu'une pression positive est maintenue ; en cas d'indisponibilité du système, aucune opération cargaison n'est entreprise sans l'accord écrit du terminal et de la capitainerie.
>
> *The master declares that the cargo tanks are inerted, that their oxygen content does not exceed 8 % by volume and that a positive pressure is maintained; should the system be unavailable, no cargo operation is undertaken without the written agreement of the terminal and the harbour master.*


Note de section : SOLAS II-2 règle 16.3 et FSS code ch. 15 (gaz inerte) ; ISGOTT 6e édition, chapitre 7 et liste de contrôle navire/terre, partie 1A. / SOLAS II-2 regulation 16.3 and FSS Code ch. 15 (inert gas); ISGOTT 6th edition, chapter 7 and ship/shore safety checklist, part 1A.

**Signatures** : NAV — Chef de la cargaison / capitaine / Chief officer / master · TER — Terminal — reçu / Terminal — received

## 6.52 `HOT_WORK_PERMIT` — Permis de travail par point chaud / Hot work permit

Partie émettrice : NAV — Navire / capitaine. Standard : ISGOTT 6e édition, chapitre 9 (modèle de permis de travail par point chaud) / ISGOTT 6th edition, chapter 9 (model hot work permit). Rôles émetteurs : NAV. Type de document : `HOT_WORK_PERMIT`. Répond à : `M7:7.06`. Offert : gabarit M7. Orientation : portrait. Objet : Le permis nominatif et limité dans le temps délivré par le capitaine pour les travaux par point chaud.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Autorisation de la capitainerie n° / Harbour master's authorization no. | Authorization HOT_WORK | demi |
| Terminal informé / Terminal informed | CallParty TER active | demi |

**Section (champs) — Travaux / Work**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Lieu exact (espace, pont, compartiment) / Exact location (space, deck, compartment) | — (à compléter sur le papier) | pleine |
| Nature des travaux et outillage / Nature of the work and tools | — (à compléter sur le papier) | pleine |
| Personnes autorisées (noms, fonctions) / Persons authorized (names, capacities) | — (à compléter sur le papier) | pleine |
| Entreprise extérieure / Outside contractor | CallParty PRE active | demi |
| Validité du permis : de / à (12 h maximum) / Permit validity: from / to (12 h maximum) | — (à compléter sur le papier) | demi |
| Certificat de dégazage n° / validité / Gas-free certificate no. / validity | — (à compléter sur le papier) | demi |

**Section (liste de contrôle) — Précautions / Precautions**

Colonnes à cocher : Fait / Done · S.O. / N/A ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Espace et espaces adjacents dégazés ; atmosphère contrôlée : O₂ 20,9 %, hydrocarbures < 1 % LEL, toxiques dans les limites / Space and adjacent spaces gas-free; atmosphere tested: O₂ 20.9 %, hydrocarbons < 1 % LEL, toxics within limits |
| Citernes et lignes adjacentes isolées, obturées ou inertées ; résidus enlevés / Adjacent tanks and lines isolated, blanked or inerted; residues removed |
| Aucune opération cargaison, ballast, soutage ou dégazage simultanée / No simultaneous cargo, ballast, bunkering or gas-freeing operation |
| Veille incendie désignée, extincteurs et manche en pression sur place ; pendant les travaux et 60 min après / Fire watch designated, extinguishers and charged hose at hand; during the work and 60 min after |
| Équipement de travail contrôlé (câbles, bouteilles, détendeurs) ; mise à la terre / Work equipment checked (cables, cylinders, regulators); earthing |
| Communication avec la passerelle / salle de contrôle ; arrêt immédiat sur alarme / Communication with the bridge / control room; immediate stop on alarm |

**Section (tableau) — Mesures d'atmosphère répétées / Repeated atmosphere tests**

Colonnes : Heure / Time · Lieu / Location · O₂ (%) / O₂ (%) · LEL (%) / LEL (%) · H₂S / CO (ppm) / H₂S / CO (ppm) · Testé par / Tested by.

Lignes préremplies : aucune ; lignes vierges ajoutées : 4.

**Section (texte) — Permis / Permit**

> Le capitaine délivre le présent permis, nominatif et limité dans le temps, aux conditions ci-dessus ; il est suspendu dès qu'une condition cesse d'être remplie. Il est délivré après l'autorisation écrite de la capitainerie et porté à la connaissance du terminal.
>
> *The master issues this permit, nominative and time-limited, on the conditions above; it is suspended as soon as a condition ceases to be met. It is issued after the harbour master's written authorization and brought to the terminal's attention.*


Note de section : ISGOTT 6e édition, chapitre 9 (travaux par point chaud) et modèle de permis ; code IGS/ISM de la compagnie. / ISGOTT 6th edition, chapter 9 (hot work) and model permit; the company's safety management system.

**Signatures** : NAV — Capitaine — délivre / Master — issues · NAV — Responsable des travaux / Person in charge of the work · TER — Terminal — informé / Terminal — informed

## 6.53 `ENCLOSED_SPACE_PERMIT` — Permis d'entrée en espace clos / Enclosed space entry permit

Partie émettrice : NAV — Navire / capitaine. Standard : Résolution OMI A.1050(27) ; ISGOTT 6e édition, chapitre 10 / IMO resolution A.1050(27); ISGOTT 6th edition, chapter 10. Rôles émetteurs : NAV. Type de document : `ENCLOSED_SPACE_PERMIT`. Répond à : `M6:6.06`. Offert : gabarit M6 ou M7. Orientation : portrait. Objet : Le permis nominatif et limité dans le temps délivré par le capitaine pour l'entrée dans un espace clos.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Terminal informé / Terminal informed | CallParty TER active | demi |
| Permis n° / validité (de / à) / Permit no. / validity (from / to) | — (à compléter sur le papier) | demi |

**Section (champs) — Espace et travaux / Space and work**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Espace à visiter / Space to be entered | — (à compléter sur le papier) | demi |
| Motif de l'entrée / Reason for entry | — (à compléter sur le papier) | demi |
| Personnes autorisées à entrer / Persons authorized to enter | — (à compléter sur le papier) | pleine |
| Surveillant à l'extérieur / Attendant outside | — (à compléter sur le papier) | demi |
| Équipement de sauvetage prêt (ARI, harnais, treuil) / Rescue equipment ready (SCBA, harness, hoist) | — (à compléter sur le papier) | pleine |

**Section (liste de contrôle) — Préparation / Preparation**

Colonnes à cocher : Fait / Done · S.O. / N/A ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Espace ventilé, isolé (vannes, lignes, électricité) et éclairé / Space ventilated, isolated (valves, lines, electricity) and lit |
| Atmosphère mesurée à plusieurs niveaux : O₂ 20,9 %, hydrocarbures < 1 % LEL, toxiques dans les limites / Atmosphere tested at several levels: O₂ 20.9 %, hydrocarbons < 1 % LEL, toxics within limits |
| Ventilation continue et mesures répétées convenues ; détecteur personnel porté / Continuous ventilation and repeat tests agreed; personal detector worn |
| Communication convenue (radio, signaux) ; passerelle informée / Communication agreed (radio, signals); bridge informed |

**Section (tableau) — Mesures d'atmosphère / Atmosphere tests**

Colonnes : Heure / Time · Niveau / Level · O₂ (%) / O₂ (%) · LEL (%) / LEL (%) · H₂S / CO / autre (ppm) / H₂S / CO / other (ppm) · Testé par / Tested by.

Lignes préremplies : aucune ; lignes vierges ajoutées : 4.

**Section (texte) — Permis / Permit**

> Le capitaine autorise l'entrée aux conditions ci-dessus ; le permis est nominatif, limité dans le temps et annulé dès qu'une condition change. Personne n'entre pour secourir sans équipement respiratoire.
>
> *The master authorizes the entry on the conditions above; the permit is nominative, time-limited and cancelled as soon as a condition changes. No one enters to rescue without breathing apparatus.*


Note de section : Résolution OMI A.1050(27) — recommandations révisées sur l'entrée dans les espaces clos à bord ; ISGOTT 6e édition, chapitre 10. / IMO resolution A.1050(27) — revised recommendations for entering enclosed spaces aboard ships; ISGOTT 6th edition, chapter 10.

**Signatures** : NAV — Capitaine — délivre / Master — issues · NAV — Responsable de l'entrée / Person in charge of the entry

## 6.54 `INCIDENT_REPORT` — Déclaration d'événement à bord ou au poste / Declaration of an event on board or at the berth

Partie émettrice : NAV — Navire / capitaine. Standard : Pratique portuaire (déclaration d'événement de mer) ; code IGS ; Convention FAL (passagers clandestins) / Port practice (declaration of a marine event); ISM Code; FAL Convention (stowaways). Rôles émetteurs : AGE, INS, NAV, PRE, SVC, TER. Type de document : `INCIDENT_REPORT`. Répond à : `M8:8.07`. Offert : toujours. Orientation : portrait. Objet : La déclaration à la capitainerie de tout événement particulier : blessé, décès, passager clandestin, pollution, avarie.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Déclaré par (nom, fonction) / Declared by (name, capacity) | — (à compléter sur le papier) | demi |
| Date et heure de l'événement / Date and time of the event | — (à compléter sur le papier) | demi |

**Section (champs) — Événement / Event**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nature : blessé grave ☐ décès ☐ passager clandestin ☐ pollution ☐ incendie ☐ avarie ☐ autre ☐ / Nature: serious injury ☐ death ☐ stowaway ☐ pollution ☐ fire ☐ damage ☐ other ☐ | — (à compléter sur le papier) | pleine |
| Lieu (à bord, à quai, en rade) / Place (on board, alongside, in the roads) | poste ou zone de l'étape | demi |
| Personnes concernées (nombre, nationalité) / Persons involved (number, nationality) | — (à compléter sur le papier) | demi |
| Circonstances / Circumstances | — (à compléter sur le papier) | pleine |
| Mesures prises à bord / Measures taken on board | — (à compléter sur le papier) | pleine |
| Secours et autorités alertés (heure) / Rescue services and authorities alerted (time) | — (à compléter sur le papier) | pleine |
| Conséquences sur l'opération / Consequences for the operation | — (à compléter sur le papier) | demi |

**Section (champs) — Suites / Follow-up**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Rapport de mer / déclaration d'accident déposé ☐ (référence) / Sea protest / accident report filed ☐ (reference) | — (à compléter sur le papier) | demi |
| Assureur / P&I informé ☐ / Insurer / P&I informed ☐ | — (à compléter sur le papier) | demi |
| Enquête demandée par / Investigation requested by | — (à compléter sur le papier) | demi |
| Pièces jointes (photos, témoignages) / Attachments (photos, statements) | — (à compléter sur le papier) | demi |

Note de section : La déclaration est faite sans délai à la capitainerie, qui la transmet aux services compétents (santé, police, environnement) ; elle ne préjuge pas des responsabilités. / The declaration is made without delay to the harbour master, who passes it to the competent services (health, police, environment); it prejudges no liability.

**Signatures** : NAV — Capitaine ou déclarant / Master or declarant · CAP — Capitainerie — reçu / Harbour master — received

## 6.55 `VETTING_REQUEST` — Demande d'acceptation du navire — synthèse du vetting / Vessel acceptance request — vetting summary

Partie émettrice : TER — Terminal / dépôt. Standard : OCIMF SIRE 2.0 / CDI ; TMSA ; politique de vetting du terminal / OCIMF SIRE 2.0 / CDI; TMSA; the terminal's vetting policy. Rôles émetteurs : TER. Type de document : `VETTING_REPORT`. Répond à : `M0:06`. Offert : toujours. Orientation : portrait. Objet : La synthèse du vetting interne du terminal jointe à la demande d'acceptation du navire.

**Section (champs) — Navire proposé / Vessel proposed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom / numéro OMI / Name / IMO number | Vessel.name, imo | demi |
| Pavillon / type / année / Flag / type / year | Vessel.flag, vessel_type, built_year | demi |
| Port en lourd (t) / LOA (m) / largeur (m) / Deadweight (t) / LOA (m) / beam (m) | Vessel.dwt, loa_m, beam_m | demi |
| Armateur / gestionnaire / Owner / manager | CallParty COM actives | demi |
| Société de classification / classe / Classification society / class | — (à compléter sur le papier) | demi |
| Produit / quantité / Product / quantity | ServiceRequest.data, PortCall | demi |
| Poste sollicité / Requested berth | ServiceRequest.data[requested_berth] | demi |

**Section (champs) — Éléments du vetting / Vetting elements**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Rapport SIRE 2.0 / CDI — date, inspecteur, observations ouvertes / SIRE 2.0 / CDI report — date, inspector, open observations | ServiceRequest.data[inspection] | pleine |
| Historique PSC (détentions, déficiences) — 36 mois / PSC history (detentions, deficiencies) — 36 months | ServiceRequest.data[psc_history] | pleine |
| Trois dernières cargaisons / Last three cargoes | ServiceRequest.data[last_cargoes] | pleine |
| Incidents, avaries, pollution — 5 ans / Incidents, casualties, pollution — 5 years | — (à compléter sur le papier) | pleine |
| Âge, changements de pavillon ou de gestionnaire / Age, flag or manager changes | — (à compléter sur le papier) | demi |
| Compatibilité avec le poste (dimensions, collecteur, défenses, tirant d'eau) / Compatibility with the berth (dimensions, manifold, fenders, draft) | — (à compléter sur le papier) | pleine |
| Résultat du vetting interne et conditions proposées / Internal vetting result and proposed conditions | ServiceRequest.data[vetting_result] | pleine |

**Section (texte) — Demande / Request**

> Le terminal demande à l'autorité portuaire l'acceptation du navire ci-dessus pour l'opération indiquée, au vu de son vetting interne dont le résultat est joint ; aucun poste n'est attribué à un navire non accepté.
>
> *The terminal requests the port authority to accept the vessel above for the stated operation, on the basis of its internal vetting whose result is attached; no berth is assigned to a vessel not accepted.*


Note de section : OCIMF SIRE 2.0 / CDI ; Tanker Management and Self Assessment (TMSA) ; politique de vetting du terminal. / OCIMF SIRE 2.0 / CDI; Tanker Management and Self Assessment (TMSA); the terminal's vetting policy.

**Signatures** : TER — Terminal — responsable vetting / Terminal — vetting officer · CAP — Autorité — reçu / Authority — received

## 6.56 `BERTH_READINESS` — Attestation de mise en sécurité du poste / Berth readiness and safety attestation

Partie émettrice : TER — Terminal / dépôt. Standard : ISGOTT 6e édition, chapitres 15–16 ; règlement d'exploitation du terminal / ISGOTT 6th edition, chapters 15–16; terminal operating regulations. Rôles émetteurs : TER. Type de document : `BERTH_READINESS`. Répond à : `M0:31`, `M1:1.03`. Offert : toujours. Orientation : portrait. Objet : L'attestation du terminal que le poste est prêt et mis en sécurité avant l'accostage.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| ETB / ATB / ETB / ATB | PortCall.atb, etb | demi |
| Opération / Operation | PortCall.template_codes | demi |

**Section (liste de contrôle) — Poste / Berth**

Colonnes à cocher : Fait / Done · S.O. / N/A ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Poste libre, dégagé, éclairé ; défenses contrôlées / Berth free, clear, lit; fenders checked |
| Bras ou flexibles disponibles, contrôlés, à l'essai en date ; réducteurs adaptés au collecteur / Arms or hoses available, checked, tests in date; reducers fitted to the manifold |
| Bacs, lignes et vannes alignés ; creux disponible ou produit prêt / Tanks, lines and valves lined up; ullage available or product ready |
| Dalots et plateaux de rétention du quai obturés / vidés / Quay scuppers and drip trays plugged / emptied |
| Kit antipollution, barrage flottant et moyens de récupération disponibles / Spill kit, boom and recovery means available |
| Moyens incendie du poste prêts (lances, mousse, canons, hydrants en pression) / Berth fire-fighting means ready (hoses, foam, monitors, hydrants charged) |
| Dispositif d'arrêt d'urgence (ESD) armé et testé / Emergency shutdown (ESD) armed and tested |
| Accès et passerelle, éclairage, zone de sûreté et contrôle d'accès en place / Access and gangway, lighting, security zone and access control in place |
| Communication avec le navire convenue (VHF, téléphone) ; personnel de permanence désigné / Communication with the ship agreed (VHF, telephone); duty personnel assigned |
| Prévisions météo et marée compatibles avec les limites du poste / Weather and tide forecasts within the berth limits |

**Section (champs) — Attestation / Attestation**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Poste mis en sécurité le (date, heure) / Berth made safe on (date, time) | — (à compléter sur le papier) | demi |
| Responsable du poste / Berth supervisor | — (à compléter sur le papier) | demi |
| Réserves / Reservations | — (à compléter sur le papier) | pleine |

Note de section : ISGOTT 6e édition, chapitre 15 et 16 (préparation du poste) et liste de contrôle navire/terre, partie 1B et 3 ; règlement d'exploitation du terminal. / ISGOTT 6th edition, chapters 15 and 16 (berth preparation) and ship/shore safety checklist, parts 1B and 3; terminal operating regulations.

**Signatures** : TER — Responsable du poste / Berth supervisor · CAP — Capitainerie — informée / Harbour master — informed

## 6.57 `SHORE_TANK_REPORT` — Relevé des bacs et compteurs à terre / Shore tank and meter measurement report

Partie émettrice : TER — Terminal / dépôt. Standard : API MPMS chapitres 3, 7 et 12 ; EI HM ; ASTM D1250 / API MPMS chapters 3, 7 and 12; EI HM; ASTM D1250. Rôles émetteurs : TER. Type de document : `SHORE_TANK_REPORT`. Répond à : `M1:1.06`, `M2:2.08`. Offert : gabarit M1 ou M2. Orientation : portrait. Objet : Le relevé des bacs récepteurs ou expéditeurs et des compteurs, avant et après le transfert.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / Product | PortCall.product | demi |
| Opération / Operation | PortCall.template_codes | demi |

**Section (champs) — Relevé / Measurement**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nature : avant transfert ☐ après transfert ☐ / Kind: before transfer ☐ after transfer ☐ | — (à compléter sur le papier) | demi |
| Date et heure / Date and time | — (à compléter sur le papier) | demi |
| Méthode : jaugeage manuel ☐ ATG ☐ compteurs ☐ / Method: manual gauging ☐ ATG ☐ meters ☐ | — (à compléter sur le papier) | demi |
| Tables de bac (date d'étalonnage) / Tank tables (calibration date) | — (à compléter sur le papier) | demi |
| Inspecteur présent / Surveyor present | CallParty INS active | demi |
| Opérateur terminal / Terminal operator | — (à compléter sur le papier) | demi |

**Section (tableau) — Bacs / Tanks**

Colonnes : Bac / Tank · Niveau (mm) / Level (mm) · Eau libre (mm) / Free water (mm) · Temp. (°C) / Temp. (°C) · Densité à 15 °C / Density at 15 °C · Volume brut (m³) / Gross volume (m³) · VCF / VCF · Volume à 15 °C (m³) / Volume at 15 °C (m³) · Masse (t) / Mass (t).

Lignes préremplies : aucune ; lignes vierges ajoutées : 8.

**Section (tableau) — Compteurs (le cas échéant) / Meters (if any)**

Colonnes : Compteur / Meter · Index début / Opening reading · Index fin / Closing reading · Facteur / Meter factor · Volume (m³) / Volume (m³) · Étalonnage (date) / Calibration (date).

Lignes préremplies : aucune ; lignes vierges ajoutées : 3.

**Section (champs) — Totaux / Totals**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Total bacs à 15 °C (m³) / masse (t) / Total tanks at 15 °C (m³) / mass (t) | — (à compléter sur le papier) | demi |
| Lignes : pleines ☐ vides ☐ — volume (m³) / Lines: full ☐ empty ☐ — volume (m³) | — (à compléter sur le papier) | demi |
| Quantité terre retenue (unité) / Shore figure retained (unit) | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

Note de section : API MPMS chapitres 3 (jaugeage), 7 (température), 12 (calculs) ; EI HM ; tables ASTM D1250. La quantité terre est saisie dans le registre (onglet Mesures) et comparée à la quantité bord. / API MPMS chapters 3 (gauging), 7 (temperature), 12 (calculations); EI HM; ASTM D1250 tables. The shore figure is entered in the registry (Quantities tab) and compared with the ship figure.

**Signatures** : TER — Terminal / Terminal · INS — Inspecteur — témoin / Surveyor — witness

## 6.58 `TERMINAL_RECEIPT` — Bon de réception du terminal / Terminal receipt

Partie émettrice : TER — Terminal / dépôt. Standard : Pratique des terminaux (outturn / discharge certificate) ; API MPMS chapitre 17 / Terminal practice (outturn / discharge certificate); API MPMS chapter 17. Rôles émetteurs : TER. Type de document : `TERMINAL_RECEIPT`. Répond à : `M1:1.17`. Offert : gabarit M1. Orientation : portrait. Objet : Le bon par lequel le terminal reconnaît la quantité reçue dans ses bacs.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / quantité nominée / Product / nominated quantity | PortCall.product, quantity | demi |
| Début / fin du transfert / Transfer start / end | jalons TRANSFER_START, TRANSFER_END | demi |

**Section (tableau) — Quantités du registre / Registry quantities**

Colonnes : Mesure / Measurement · Produit / Product · Unité / Unit · Bord / Ship · Terre / Shore · Inspecteur / Surveyor.

Lignes préremplies : Measurement et MeasurementValue (valeurs courantes par partie) ; lignes vierges ajoutées : 1.

**Section (champs) — Réception / Receipt**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Quantité reçue dans les bacs (unité, base de calcul) / Quantity received into tanks (unit, basis) | — (à compléter sur le papier) | demi |
| Bacs récepteurs / Receiving tanks | — (à compléter sur le papier) | demi |
| Température moyenne (°C) / densité à 15 °C / Average temperature (°C) / density at 15 °C | — (à compléter sur le papier) | demi |
| Eau libre et sédiments (BS&W) / Free water and sediment (BS&W) | — (à compléter sur le papier) | demi |
| Écart bord/terre (quantité, %) / Ship/shore difference (quantity, %) | — (à compléter sur le papier) | demi |
| Dans la tolérance ☐ hors tolérance — lettre de protestation ☐ / Within tolerance ☐ outside tolerance — letter of protest ☐ | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Section (texte) — Bon de réception / Receipt**

> Le terminal certifie avoir reçu du navire ci-dessus la quantité indiquée, relevée contradictoirement en présence de l'inspecteur ; le présent bon ne vaut pas accord sur les quantités qui font l'objet d'une contestation ouverte.
>
> *The terminal certifies that it received from the vessel above the stated quantity, measured jointly in the presence of the surveyor; this receipt is no agreement on quantities under an open dispute.*


**Signatures** : TER — Terminal / Terminal · NAV — Capitaine / Master · INS — Inspecteur / Surveyor

## 6.59 `SPM_INSPECTION` — Rapport d'inspection de la bouée (SPM) / SPM buoy inspection report

Partie émettrice : TER — Terminal / dépôt. Standard : OCIMF SMOG ; OCIMF GMPHOM (flexibles) / OCIMF SMOG; OCIMF GMPHOM (hoses). Rôles émetteurs : TER. Type de document : `SPM_DOC`. Répond à : `MA2:A2.01`. Offert : gabarit MA2. Orientation : portrait. Objet : Le rapport d'inspection de la bouée, des flexibles et du système d'amarrage avant l'escale.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Bouée / poste / Buoy / berth | PortCall.berth | demi |
| Dernière inspection complète (date, organisme) / Last full inspection (date, body) | — (à compléter sur le papier) | demi |

**Section (tableau) — Inspection avant l'escale / Pre-call inspection**

Colonnes : Élément / Item · Contrôle effectué (méthode, date) / Check carried out (method, date) · État : conforme ☐ réserve ☐ / Condition: compliant ☐ reservation ☐ · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 2.

**Section (champs) — Conclusion / Conclusion**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Bouée apte à recevoir le navire ☐ sous réserve ☐ inapte ☐ / Buoy fit to receive the vessel ☐ with reservations ☐ unfit ☐ | — (à compléter sur le papier) | demi |
| Limites d'exploitation rappelées (houle, vent, courant) / Operating limits recalled (swell, wind, current) | — (à compléter sur le papier) | demi |
| Inspecté par (nom, fonction) / Inspected by (name, capacity) | — (à compléter sur le papier) | demi |
| Date et heure / Date and time | — (à compléter sur le papier) | demi |

Note de section : OCIMF — Single Point Mooring Maintenance and Operations Guide (SMOG) et Guide to Purchasing, Manufacturing and Testing of Loading and Discharge Hoses for Offshore Moorings (GMPHOM). / OCIMF — Single Point Mooring Maintenance and Operations Guide (SMOG) and Guide to Purchasing, Manufacturing and Testing of Loading and Discharge Hoses for Offshore Moorings (GMPHOM).

**Signatures** : TER — Exploitant de la bouée / Buoy operator · CAP — Capitainerie — reçu / Harbour master — received

## 6.60 `DOUBLE_BANKING_STUDY` — Dossier d'accostage à couple — compatibilité, amarrage, déhalage d'urgence / Double banking file — compatibility, mooring, emergency unberthing

Partie émettrice : TER — Terminal / dépôt. Standard : OCIMF MEG4 ; OCIMF Ship to Ship Transfer Guide ; ISGOTT 6e édition, chapitre 23 / OCIMF MEG4; OCIMF Ship to Ship Transfer Guide; ISGOTT 6th edition, chapter 23. Rôles émetteurs : TER. Type de document : `DOUBLE_BANKING_DOC`. Répond à : `M9:9.03`, `M9:9.04`, `M9:9.06`, `M9:9.08`. Offert : gabarit M9 ou escale reliée. Orientation : portrait. Objet : L'étude de compatibilité, l'analyse d'amarrage, la matrice des opérations simultanées et le plan de déhalage d'urgence de l'accostage à couple.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Configuration : ce navire intérieur ☐ extérieur ☐ / Configuration: this vessel inner ☐ outer ☐ | PortCall.link_kind | demi |

**Section (tableau) — Compatibilité des deux navires / Compatibility of the two vessels**

Colonnes : Caractéristique / Particular · Ce navire / This vessel · Navire partenaire / Partner vessel · Compatible ☐ / réserve / Compatible ☐ / reservation.

Lignes préremplies : Vessel (ce navire et partenaire) : loa_m, beam_m, dwt ; lignes vierges ajoutées : 1.

**Section (champs) — Analyse d'amarrage du système combiné / Mooring analysis of the combined system**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Conditions extrêmes retenues (vent, houle, courant) / Extreme conditions considered (wind, swell, current) | — (à compléter sur le papier) | pleine |
| Charges maximales dans les amarres et les défenses / Maximum loads in lines and fenders | — (à compléter sur le papier) | demi |
| Méthode / logiciel et référence de l'étude / Method / software and study reference | — (à compléter sur le papier) | demi |
| Seuils météo de la configuration (plus restrictifs) / Weather thresholds of the configuration (more restrictive) | — (à compléter sur le papier) | demi |

**Section (tableau) — Matrice des opérations simultanées / Simultaneous operations matrix**

Colonnes : Opération / Operation · Navire intérieur / Inner vessel · Navire extérieur / Outer vessel · Autorisée ☐ / interdite ☐ / conditions / Allowed ☐ / prohibited ☐ / conditions.

Lignes préremplies : aucune ; lignes vierges ajoutées : 1.

**Section (champs) — Plan de déhalage d'urgence / Emergency unberthing plan**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Scénarios déclencheurs / Triggering scenarios | — (à compléter sur le papier) | pleine |
| Moyens (remorqueurs, pilote, lamaneurs) et délais de mise en œuvre / Means (tugs, pilot, mooring gang) and lead times | — (à compléter sur le papier) | pleine |
| Responsabilités nominatives (terminal, navires, capitainerie) / Named responsibilities (terminal, vessels, harbour master) | — (à compléter sur le papier) | pleine |
| Ordre de largage et séquence / Release order and sequence | — (à compléter sur le papier) | pleine |
| Plan d'accès, de coupée et d'évacuation des deux équipages / Access, gangway and evacuation plan of both crews | — (à compléter sur le papier) | pleine |

Note de section : OCIMF Mooring Equipment Guidelines (MEG4) ; OCIMF Ship to Ship Transfer Guide (amarrage à couple) ; ISGOTT 6e édition, chapitre 23. / OCIMF Mooring Equipment Guidelines (MEG4); OCIMF Ship to Ship Transfer Guide (alongside mooring); ISGOTT 6th edition, chapter 23.

**Signatures** : TER — Terminal / Terminal · NAV — Capitaine — ce navire / Master — this vessel · NAV — Capitaine — navire partenaire / Master — partner vessel · CAP — Capitainerie / Harbour master

## 6.61 `SAMPLING_RECORD` — Procès-verbal d'échantillonnage / Sampling record

Partie émettrice : INS — Inspecteur et laboratoire. Standard : API MPMS chapitre 8 ; ISO 3170 / 3171 ; EI HM 23 / API MPMS chapter 8; ISO 3170 / 3171; EI HM 23. Rôles émetteurs : INS. Type de document : `SAMPLING_RECORD`. Répond à : `M1:1.07`. Offert : gabarit M1 ou M2 ou M3 ou escale reliée. Orientation : portrait. Objet : Le procès-verbal des échantillons prélevés, scellés et distribués.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / Product | PortCall.product | demi |
| Inspecteur / Surveyor | CallParty INS active | demi |

**Section (tableau) — Échantillons prélevés / Samples drawn**

Colonnes : N° / No. · Point (citerne, bac, ligne, collecteur) / Point (tank, shore tank, line, manifold) · Type (haut / milieu / bas / composite / continu) / Type (upper / middle / lower / composite / running) · Heure / Time · Volume / flacon / Volume / container · N° de scellé / Seal number · Destination (laboratoire, bord, terminal, rétention) / Distribution (laboratory, ship, terminal, retained).

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

**Section (champs) — Conditions de prélèvement / Sampling conditions**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Méthode (manuelle, automatique en ligne) / Method (manual, automatic in-line) | — (à compléter sur le papier) | demi |
| Appareillage (préleveur, bouteille, flacons) / Equipment (sampler, bottle, containers) | — (à compléter sur le papier) | demi |
| Température du produit (°C) / Product temperature (°C) | — (à compléter sur le papier) | demi |
| Témoins (bord, terminal) / Witnesses (ship, terminal) | — (à compléter sur le papier) | demi |
| Durée de conservation des échantillons de rétention / Retention period of retained samples | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Section (texte) — Procès-verbal / Record**

> Les échantillons ci-dessus ont été prélevés, scellés et étiquetés contradictoirement ; leur distribution est consignée. L'échantillon MARPOL du soutage, le cas échéant, fait l'objet du bordereau du fournisseur.
>
> *The samples above were drawn, sealed and labelled jointly; their distribution is recorded. The MARPOL bunker sample, if any, is covered by the supplier's note.*


Note de section : API MPMS chapitre 8.1 (échantillonnage manuel) et 8.2 (automatique) ; ISO 3170 / 3171 ; EI HM 23. / API MPMS chapter 8.1 (manual sampling) and 8.2 (automatic); ISO 3170 / 3171; EI HM 23.

**Signatures** : INS — Inspecteur / Surveyor · NAV — Navire — témoin / Ship — witness · TER — Terminal — témoin / Terminal — witness

## 6.62 `QUANTITY_CERT` — Certificat de quantité / Certificate of quantity

Partie émettrice : INS — Inspecteur et laboratoire. Standard : API MPMS chapitres 11, 12 et 17 ; EI HM 28 / 50 ; ASTM D1250 / API MPMS chapters 11, 12 and 17; EI HM 28 / 50; ASTM D1250. Rôles émetteurs : INS. Type de document : `QQ_CERT`. Répond à : `M1:1.08`, `M1:1.16`, `M2:2.15`, `M3:3.14`. Offert : gabarit M1 ou M2 ou M3 ou escale reliée. Orientation : portrait. Objet : Le certificat de quantité de l'inspecteur, établi sur les jaugeages bord et terre du registre.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / Product | PortCall.product | demi |
| Opération / Operation | PortCall.template_codes | demi |

**Section (tableau) — Quantités du registre / Registry quantities**

Colonnes : Mesure / Measurement · Produit / Product · Unité / Unit · Bord / Ship · Terre / Shore · Inspecteur / Surveyor.

Lignes préremplies : Measurement et MeasurementValue (valeurs courantes par partie) ; lignes vierges ajoutées : 1.

**Section (champs) — Détermination de la quantité / Quantity determination**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Jaugeage initial bord (date, heure) / Initial ship gauging (date, time) | jalon TRANSFER_START | demi |
| Jaugeage final bord (date, heure) / Final ship gauging (date, time) | jalon TRANSFER_END | demi |
| Quantité bord (TCV / GSV / masse) avec VEF / Ship figure (TCV / GSV / mass) with VEF | — (à compléter sur le papier) | demi |
| Facteur d'expérience navire (VEF) appliqué / Vessel experience factor (VEF) applied | — (à compléter sur le papier) | demi |
| Quantité terre (bacs / compteurs) / Shore figure (tanks / meters) | — (à compléter sur le papier) | demi |
| Eau libre, sédiments, OBQ / ROB / Free water, sediment, OBQ / ROB | — (à compléter sur le papier) | demi |
| Densité à 15 °C / API et table de conversion / Density at 15 °C / API and conversion table | — (à compléter sur le papier) | demi |
| Quantité certifiée (unité) / Certified quantity (unit) | — (à compléter sur le papier) | demi |
| Écart bord/terre (quantité, %) et tolérance du port / Ship/shore difference (quantity, %) and port tolerance | — (à compléter sur le papier) | demi |
| Observations / Remarks | — (à compléter sur le papier) | pleine |

**Section (texte) — Certificat / Certificate**

> L'inspecteur certifie que la quantité ci-dessus a été déterminée contradictoirement selon les méthodes indiquées ; la plateforme ne désigne pas de valeur de référence, chaque partie conservant sa propre mesure au registre.
>
> *The surveyor certifies that the quantity above was determined jointly by the stated methods; the platform designates no reference value, each party keeping its own measurement in the registry.*


Note de section : API MPMS chapitre 17.1 (inspection des cargaisons maritimes), 11 et 12 (calculs) ; EI HM 28 / HM 50 ; tables ASTM D1250. / API MPMS chapter 17.1 (marine cargo inspection), 11 and 12 (calculations); EI HM 28 / HM 50; ASTM D1250 tables.

**Signatures** : INS — Inspecteur / Surveyor

## 6.63 `QUALITY_CERT` — Certificat de qualité — rapport d'analyse / Certificate of quality — analysis report

Partie émettrice : INS — Inspecteur et laboratoire. Standard : ISO/IEC 17025 (rapport d'essai) ; méthodes ISO / ASTM / EN / ISO/IEC 17025 (test report); ISO / ASTM / EN methods. Rôles émetteurs : INS. Type de document : `QUALITY_CERT`. Répond à : `M1:1.16`, `M2:2.07`. Offert : gabarit M1 ou M2 ou M3 ou M4 ou escale reliée. Orientation : portrait. Objet : Le rapport d'analyse du laboratoire et sa conclusion de conformité à la spécification.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit / grade / Product / grade | PortCall.product | demi |
| Laboratoire / Laboratory | CallParty INS active | demi |

**Section (champs) — Échantillon analysé / Sample analysed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Échantillon n° / scellé n° / Sample no. / seal no. | — (à compléter sur le papier) | demi |
| Point et date de prélèvement / Sampling point and date | — (à compléter sur le papier) | demi |
| Reçu au laboratoire le / Received at the laboratory on | — (à compléter sur le papier) | demi |
| Spécification de référence (norme, contrat) / Reference specification (standard, contract) | — (à compléter sur le papier) | demi |

**Section (tableau) — Résultats d'analyse / Analysis results**

Colonnes : Caractéristique / Property · Méthode / Method · Spécification (min / max) / Specification (min / max) · Résultat / Result.

Lignes préremplies : aucune ; lignes vierges ajoutées : 2.

**Section (champs) — Conclusion / Conclusion**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Conforme à la spécification ☐ non conforme ☐ (caractéristiques hors spécification) / On specification ☐ off specification ☐ (properties out of specification) | — (à compléter sur le papier) | pleine |
| Analyste / responsable du laboratoire / Analyst / laboratory manager | — (à compléter sur le papier) | demi |
| Date du rapport / Date of report | — (à compléter sur le papier) | demi |

Note de section : Rapport d'essai selon ISO/IEC 17025 ; méthodes ISO / ASTM / EN citées par caractéristique ; les spécifications sont celles du contrat ou de la norme nationale du produit. / Test report under ISO/IEC 17025; ISO / ASTM / EN methods cited per property; specifications are those of the contract or of the national product standard.

**Signatures** : INS — Laboratoire / Laboratory

## 6.64 `CLEANLINESS_CERT` — Certificat de propreté des citernes / Tank cleanliness certificate

Partie émettrice : INS — Inspecteur et laboratoire. Standard : Pratique de l'inspection des cargaisons ; ISGOTT 6e édition, chapitre 22.4 / Cargo inspection practice; ISGOTT 6th edition, chapter 22.4. Rôles émetteurs : INS. Type de document : `CLEANLINESS_CERT`. Répond à : `M2:2.04`. Offert : gabarit M2. Orientation : portrait. Objet : Le certificat de propreté des citernes délivré après l'inspection contradictoire, avant chargement.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit à charger / Product to be loaded | PortCall.product | demi |
| Inspection le (date, heure) / Inspection on (date, time) | — (à compléter sur le papier) | demi |

**Section (tableau) — Inspection des citernes / Tank inspection**

Colonnes : Citerne / Tank · Dernière cargaison / Last cargo · Méthode d'inspection (visuelle, wall-wash, mesure) / Inspection method (visual, wall-wash, measurement) · Résultat / Result · Acceptée ☐ refusée ☐ / Accepted ☐ rejected ☐ · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

**Section (champs) — Lignes, pompes, collecteur / Lines, pumps, manifold**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Lignes et pompes inspectées / purgées / Lines and pumps inspected / drained | — (à compléter sur le papier) | demi |
| Collecteur et réducteurs / Manifold and reducers | — (à compléter sur le papier) | demi |
| Atmosphère des citernes lors de l'inspection (O₂, LEL) / Tank atmosphere during inspection (O₂, LEL) | — (à compléter sur le papier) | demi |
| Réserves / Reservations | — (à compléter sur le papier) | pleine |

**Section (texte) — Certificat / Certificate**

> L'inspecteur certifie que les citernes ci-dessus ont été inspectées contradictoirement et jugées aptes à recevoir le produit indiqué, sous les réserves mentionnées. Le certificat ne couvre que l'état constaté à l'heure de l'inspection.
>
> *The surveyor certifies that the tanks above were inspected jointly and found fit to receive the stated product, subject to the reservations noted. The certificate covers only the condition found at the time of inspection.*


Note de section : Pratique de l'inspection des cargaisons (tank cleanliness / dry certificate) ; ISGOTT 6e édition, chapitre 22.4 ; normes de propreté du produit (contrat, terminal). / Cargo inspection practice (tank cleanliness / dry certificate); ISGOTT 6th edition, chapter 22.4; product cleanliness standards (contract, terminal).

**Signatures** : INS — Inspecteur / Surveyor · NAV — Chef de la cargaison / Chief officer · TER — Terminal / Terminal

## 6.65 `EMPTY_TANKS_CERT` — Certificat de citernes vides — constat de ROB / Empty tanks certificate — ROB statement

Partie émettrice : INS — Inspecteur et laboratoire. Standard : API MPMS chapitre 17.1 et 17.4 ; pratique de l'inspection des cargaisons / API MPMS chapter 17.1 and 17.4; cargo inspection practice. Rôles émetteurs : INS. Type de document : `EMPTY_TANKS_CERT`. Répond à : `M1:1.14`. Offert : gabarit M1 ou M3 ou escale reliée. Orientation : portrait. Objet : Le constat contradictoire des quantités restant à bord après déchargement.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Produit déchargé / Product discharged | PortCall.product | demi |
| Fin du déchargement / Completion of discharge | jalon TRANSFER_END | demi |

**Section (tableau) — Reste à bord par citerne (ROB) / Remaining on board per tank (ROB)**

Colonnes : Citerne / Tank · Sondage (mm) / Sounding (mm) · Liquide (m³) / Liquid (m³) · Non liquide (m³) / Non-liquid (m³) · Pompable ☐ / non pompable ☐ / Pumpable ☐ / non-pumpable ☐ · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 12.

**Section (champs) — Totaux et conditions / Totals and conditions**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| ROB total liquide / non liquide (m³) / Total ROB liquid / non-liquid (m³) | — (à compléter sur le papier) | demi |
| OBQ à l'arrivée (m³) pour comparaison / OBQ on arrival (m³) for comparison | — (à compléter sur le papier) | demi |
| Assiette et gîte lors du sondage / Trim and list at sounding | — (à compléter sur le papier) | demi |
| Lignes et pompes : vidangées ☐ — contenu estimé (m³) / Lines and pumps: drained ☐ — estimated content (m³) | — (à compléter sur le papier) | demi |
| Citernes vides au sens du contrat ☐ (seuil) / Tanks empty within the meaning of the contract ☐ (threshold) | — (à compléter sur le papier) | demi |
| Réserves (navire, terminal) / Reservations (ship, terminal) | — (à compléter sur le papier) | pleine |

**Section (texte) — Constat / Statement**

> Le présent constat, établi contradictoirement, consigne les quantités restant à bord après déchargement ; il sert de base au calcul de la quantité livrée et à toute réclamation de ROB.
>
> *This joint statement records the quantities remaining on board after discharge; it is the basis of the delivered quantity calculation and of any ROB claim.*


Note de section : API MPMS chapitre 17.1 et 17.4 (OBQ / ROB) ; pratique de l'inspection des cargaisons (dry tank / empty tank certificate). / API MPMS chapter 17.1 and 17.4 (OBQ / ROB); cargo inspection practice (dry tank / empty tank certificate).

**Signatures** : INS — Inspecteur / Surveyor · NAV — Chef de la cargaison / Chief officer · TER — Terminal / Terminal

## 6.66 `GAS_FREE_CERT` — Certificat de dégazage / Gas-free certificate

Partie émettrice : INS — Inspecteur et laboratoire. Standard : ISGOTT 6e édition, chapitres 9–10 ; NFPA 306 ; résolution OMI A.1050(27) / ISGOTT 6th edition, chapters 9–10; NFPA 306; IMO resolution A.1050(27). Rôles émetteurs : INS. Type de document : `GAS_FREE_CERT`. Répond à : `M6:6.05`, `M7:7.05`. Offert : gabarit M6 ou M7. Orientation : portrait. Objet : Le certificat de dégazage des espaces contrôlés, avec sa durée de validité explicite.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Objet : travaux par point chaud ☐ entrée en espace clos ☐ nettoyage ☐ réparation à quai ☐ / Purpose: hot work ☐ enclosed space entry ☐ cleaning ☐ repair alongside ☐ | — (à compléter sur le papier) | demi |
| Certificat n° / validité (de / à) / Certificate no. / validity (from / to) | — (à compléter sur le papier) | demi |

**Section (tableau) — Espaces contrôlés / Spaces tested**

Colonnes : Espace / Space · Heure / Time · O₂ (% vol.) / O₂ (% vol.) · Hydrocarbures (% LEL) / Hydrocarbons (% LEL) · H₂S (ppm) / H₂S (ppm) · Benzène / autres toxiques (ppm) / Benzene / other toxics (ppm) · Conclusion / Conclusion.

Lignes préremplies : aucune ; lignes vierges ajoutées : 10.

**Section (champs) — Conditions / Conditions**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Appareils de mesure (type, n° de série, étalonnage) / Instruments (type, serial no., calibration) | — (à compléter sur le papier) | pleine |
| Ventilation à maintenir ☐ ; nouvelles mesures toutes les (h) / Ventilation to be maintained ☐; new tests every (h) | — (à compléter sur le papier) | demi |
| Espaces adjacents couverts par le certificat / Adjacent spaces covered by the certificate | — (à compléter sur le papier) | pleine |
| Restrictions / Restrictions | — (à compléter sur le papier) | pleine |

**Section (texte) — Certificat / Certificate**

> L'inspecteur (chimiste maritime) certifie que les espaces ci-dessus, aux heures indiquées, sont : sûrs pour l'entrée ☐ / sûrs pour les travaux par point chaud ☐ / non sûrs ☐, aux conditions mentionnées. Le certificat cesse de valoir à l'expiration indiquée ou dès que les conditions changent.
>
> *The surveyor (marine chemist) certifies that the spaces above, at the stated times, are: safe for entry ☐ / safe for hot work ☐ / not safe ☐, on the conditions noted. The certificate lapses at the stated expiry or as soon as conditions change.*


Note de section : ISGOTT 6e édition, chapitres 9 et 10 ; NFPA 306 (Standard for the Control of Gas Hazards on Vessels) ; résolution OMI A.1050(27). / ISGOTT 6th edition, chapters 9 and 10; NFPA 306 (Standard for the Control of Gas Hazards on Vessels); IMO resolution A.1050(27).

**Signatures** : INS — Inspecteur / chimiste maritime / Surveyor / marine chemist · NAV — Capitaine — reçu / Master — received

## 6.67 `MOVEMENT_ORDER` — Ordre de mouvement — confirmation des services nautiques / Movement order — marine services confirmation

Partie émettrice : SVC — Services nautiques. Standard : Résolution OMI A.960(23) ; règlement des services nautiques du port / IMO resolution A.960(23); port marine services regulations. Rôles émetteurs : SVC. Type de document : `MOVEMENT_ORDER`. Répond à : `REQ:MARINE_SERVICES`, `M0:18`. Offert : toujours. Orientation : portrait. Objet : La confirmation des services nautiques réservés (pilote, remorqueurs, lamaneurs) et l'ordre de mouvement.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Autorisation de mouvement n° / validité / Movement authorization no. / validity | Authorization MOVEMENT | demi |
| Demande de services n° / Service request no. | ServiceRequest MARINE_SERVICES | demi |

**Section (champs) — Demande de services telle que déposée / Service request as filed**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Services demandés / Services requested | — (à compléter sur le papier) | pleine |

**Section (champs) — Mouvement ordonné / Movement ordered**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nature : entrée ☐ accostage ☐ déhalage ☐ sortie ☐ / Kind: inward ☐ berthing ☐ shifting ☐ outward ☐ | — (à compléter sur le papier) | demi |
| De / à / From / to | poste ou zone de l'étape | demi |
| Heure prévue d'embarquement du pilote / Planned pilot boarding time | — (à compléter sur le papier) | demi |
| Point d'embarquement du pilote / Pilot boarding point | — (à compléter sur le papier) | demi |
| Pilote désigné / Pilot assigned | — (à compléter sur le papier) | demi |
| Remorqueurs (noms, puissance, nombre) / Tugs (names, bollard pull, number) | — (à compléter sur le papier) | demi |
| Lamaneurs (équipe, vedette) / Mooring gang (team, launch) | — (à compléter sur le papier) | demi |
| Canal VHS de travail / Working VHF channel | — (à compléter sur le papier) | demi |
| Tirant d'eau annoncé AV / AR (m) / Declared draft fwd / aft (m) | — (à compléter sur le papier) | demi |
| Conditions (marée, courant, vent, visibilité) / Conditions (tide, current, wind, visibility) | — (à compléter sur le papier) | pleine |

**Section (texte) — Ordre / Order**

> Les services nautiques confirment la réservation ci-dessus et ordonnent le mouvement aux conditions indiquées, sous couvert de l'autorisation de mouvement en vigueur. Le capitaine conserve la conduite et la responsabilité du navire ; le pilote le conseille.
>
> *The marine services confirm the booking above and order the movement on the stated conditions, under the movement authorization in force. The master keeps the conduct and the responsibility of the ship; the pilot advises.*


Note de section : Résolution OMI A.960(23) (pilotage) ; règlement des services nautiques du port. / IMO resolution A.960(23) (pilotage); port marine services regulations.

**Signatures** : SVC — Services nautiques / Marine services · NAV — Capitaine — reçu / Master — received · CAP — Capitainerie — informée / Harbour master — informed

## 6.68 `SERVICE_NOTE` — Bon de prestation de service / Service delivery note

Partie émettrice : SVC — Services nautiques. Standard : Pratique portuaire (bon de pilotage, de remorquage, de lamanage, de livraison) ; FONASBA (compte d'escale) / Port practice (pilotage, towage, mooring, delivery vouchers); FONASBA (disbursement account). Rôles émetteurs : PRE, SVC. Type de document : `SERVICE_NOTE`. Répond à : `REQ:MARINE_SERVICES`, `REQ:WASTE_COLLECTION`, `M8:8.06`, `MA2:A2.03`. Offert : toujours. Orientation : portrait. Objet : Le bon de prestation signé par le capitaine pour chaque service rendu (pilotage, remorquage, lamanage, eau, provisions, vedette).

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Prestataire / Provider | CallParty SVC ou PRE active | demi |
| Commande / demande n° / Order / request no. | — (à compléter sur le papier) | demi |

**Section (tableau) — Prestation / Service**

Colonnes : Service / Service · Moyens (noms, nombre) / Means (names, number) · Début / Start · Fin / End · Durée / quantité / Duration / quantity · Observations / Remarks.

Lignes préremplies : aucune ; lignes vierges ajoutées : 2.

**Section (tableau) — Heures du registre / Registry times**

Colonnes : Événement / Event · Heure (UTC) / Time (UTC).

Lignes préremplies : jalons PILOT_ON_BOARD_ARR, FIRST_LINE, ALL_FAST, PILOT_ON_BOARD_DEP, LAST_LINE, DEPARTED ; lignes vierges ajoutées : 0.

**Section (champs) — Constat / Acknowledgement**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Prestation exécutée conformément à la commande ☐ avec réserves ☐ / Service performed as ordered ☐ with reservations ☐ | — (à compléter sur le papier) | demi |
| Réserves (retard, attente, dommage) / Reservations (delay, waiting, damage) | — (à compléter sur le papier) | pleine |
| Certificats joints (potabilité, étalonnage, agrément) / Certificates attached (potability, calibration, licence) | — (à compléter sur le papier) | pleine |
| Représentant du prestataire (nom) / Provider's representative (name) | — (à compléter sur le papier) | demi |

Note de section : Bon de prestation signé par le capitaine (ou l'agent) et le prestataire ; base de facturation du compte d'escale. Les heures de pilotage, d'amarrage et d'appareillage viennent du registre contradictoire. / Service note signed by the master (or the agent) and the provider; basis of the disbursement account. Pilotage, mooring and departure times come from the contradictory registry.

**Signatures** : SVC — Prestataire / Provider · NAV — Capitaine — reçu / Master — received · AGE — Agence — visa / Agency — endorsement

## 6.69 `WASTE_RECEIPT` — Bordereau de réception des déchets / Waste delivery receipt

Partie émettrice : PRE — Prestataires. Standard : Circulaire OMI MEPC.1/Circ.834/Rev.1, appendice 3 (MARPOL) / IMO circular MEPC.1/Circ.834/Rev.1, appendix 3 (MARPOL). Rôles émetteurs : PRE. Type de document : `WASTE_RECEIPT`. Répond à : `REQ:WASTE_COLLECTION`, `M0:32`, `M5:5.07`, `M6:6.07`. Offert : toujours. Orientation : portrait. Objet : Le bordereau par lequel l'installation de réception atteste les déchets reçus du navire.

**Section (champs) — Installation de réception / Reception facility**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom et adresse de l'installation / du prestataire / Name and address of the facility / provider | CallParty PRE active | pleine |
| Agrément (numéro, autorité, validité) / Licence (number, authority, validity) | — (à compléter sur le papier) | demi |
| Moyen de collecte (camion, barge, conteneur) / Collection means (truck, barge, container) | — (à compléter sur le papier) | demi |
| Port / Port | Port.name | demi |
| Date et heure de la réception / Date and time of delivery | — (à compléter sur le papier) | demi |

**Section (champs) — Navire / Ship**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Nom / numéro OMI / Name / IMO number | Vessel.name, imo | demi |
| Pavillon / Flag State | Vessel.flag | demi |
| Jauge brute / Gross tonnage | — (à compléter sur le papier) | demi |
| Armateur / exploitant / Owner / operator | — (à compléter sur le papier) | demi |
| Agent / Agent | PortCall.agency | demi |
| Notification préalable n° / date / Advance notification no. / date | — (à compléter sur le papier) | demi |

**Section (tableau) — Déchets reçus / Waste delivered**

Colonnes : Type / Type · Quantité reçue (m³) / Amount delivered (m³) · Observations (conteneurs, teneur en eau…) / Remarks (containers, water content…).

Lignes préremplies : aucune ; lignes vierges ajoutées : 1.

**Section (texte) — Attestation / Attestation**

> L'installation de réception atteste avoir reçu du navire ci-dessus les quantités indiquées, qui seront traitées conformément à la réglementation applicable ; le capitaine en reporte la remise aux registres MARPOL du bord.
>
> *The reception facility attests that it received from the ship above the stated amounts, which will be handled in accordance with the applicable regulations; the master records the delivery in the ship's MARPOL record books.*


Note de section : Modèle du bordereau de réception des déchets, appendice 3 de la circulaire OMI MEPC.1/Circ.834/Rev.1 (installations de réception portuaires). / Model of the waste delivery receipt, appendix 3 of IMO circular MEPC.1/Circ.834/Rev.1 (port reception facilities).

**Signatures** : PRE — Installation de réception / Reception facility · NAV — Capitaine / Master

## 6.70 `BUNKER_CHECKLIST` — Liste de contrôle sécurité soutage / Bunkering safety checklist

Partie émettrice : PRE — Prestataires. Standard : ISGOTT 6e édition, chapitre 25.5 ; ISO 13739 ; MEPC.1/Circ.875/Add.1 / ISGOTT 6th edition, chapter 25.5; ISO 13739; MEPC.1/Circ.875/Add.1. Rôles émetteurs : NAV, PRE. Type de document : `BUNKER_CHECKLIST`. Répond à : `M4:4.03`, `M4:4.04`, `M4:4.05`. Offert : gabarit M4. Orientation : portrait. Objet : La liste de contrôle signée conjointement avant le soutage, avec l'agrément de l'avitailleur et les scellés du comptage.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Avitailleur / moyen (barge, camion) / Supplier / means (barge, truck) | CallParty PRE active | demi |
| Autorisation de soutage n° / Bunkering authorization no. | Authorization BUNKERING | demi |

**Section (champs) — Commande / Order**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Produit (grade) / quantité commandée (t) / Product (grade) / quantity ordered (t) | — (à compléter sur le papier) | demi |
| Teneur en soufre max. (% m/m) / viscosité / point d'éclair / Max. sulphur (% m/m) / viscosity / flash point | — (à compléter sur le papier) | demi |
| Débit maximal convenu (m³/h) / pression maximale (bar) / Agreed maximum rate (m³/h) / maximum pressure (bar) | — (à compléter sur le papier) | demi |
| Citernes receveuses et séquence / Receiving tanks and sequence | — (à compléter sur le papier) | demi |
| Agrément du soutier (n°, validité) / certification du moyen / Bunker supplier licence (no., validity) / barge certification | — (à compléter sur le papier) | pleine |
| Système de comptage : scellés et vérification métrologique (date) / Metering system: seals and metrological verification (date) | — (à compléter sur le papier) | pleine |

**Section (liste de contrôle) — Avant le soutage / Before bunkering**

Colonnes à cocher : Navire / Ship · Avitailleur / Supplier ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Communication établie (VHF, signaux) ; procédure d'arrêt d'urgence convenue / Communication established (VHF, signals); emergency stop procedure agreed |
| Amarrage de la barge sûr ; défenses en place ; flexible supporté, certifié, à l'essai en date / Barge safely moored; fenders in place; hose supported, certified, test in date |
| Dalots obturés ; plateaux de rétention vides ; kit antipollution prêt des deux côtés / Scuppers plugged; drip trays empty; spill kit ready on both sides |
| Jaugeage initial contradictoire effectué ; compteurs relevés / Joint initial gauging done; meters read |
| Compatibilité avec l'opération cargaison en cours confirmée ; interdiction de fumer, sources d'ignition contrôlées / Compatibility with the cargo operation under way confirmed; no smoking, ignition sources controlled |
| Veille continue désignée (navire et avitailleur) ; manche incendie en pression / Continuous watch designated (ship and supplier); fire hose charged |

**Section (liste de contrôle) — Pendant et après / During and after**

Colonnes à cocher : Navire / Ship · Avitailleur / Supplier ; colonne remarques.

| Point de contrôle FR / EN |
|---|
| Débit et pression dans les limites ; niveaux des citernes surveillés ; topping-off annoncé / Rate and pressure within limits; tank levels monitored; topping-off announced |
| Échantillon MARPOL prélevé en continu au point de réception, scellé et signé / MARPOL sample drawn continuously at the receiving point, sealed and signed |
| Jaugeage final contradictoire ; flexible purgé et déconnecté ; note de livraison signée / Joint final gauging; hose drained and disconnected; delivery note signed |

Note de section : ISGOTT 6e édition, chapitre 25.5 (liste de contrôle soutage) ; IMO MEPC.1/Circ.875/Add.1 (bonnes pratiques d'achat et de livraison de fioul) ; ISO 13739. / ISGOTT 6th edition, chapter 25.5 (bunkering checklist); IMO MEPC.1/Circ.875/Add.1 (fuel oil purchase and delivery good practice); ISO 13739.

**Signatures** : PRE — Avitailleur / Supplier · NAV — Chef mécanicien / Chief engineer

## 6.71 `STS_COMPATIBILITY` — Étude de compatibilité STS des deux navires / STS compatibility study of the two vessels

Partie émettrice : PRE — Prestataires. Standard : OCIMF Ship to Ship Transfer Guide (2013), chapitres 2, 4, 5 et 6 / OCIMF Ship to Ship Transfer Guide (2013), chapters 2, 4, 5 and 6. Rôles émetteurs : PRE. Type de document : `STS_DOC`. Répond à : `M3:3.05`, `M3:3.11`. Offert : gabarit M3 ou escale reliée. Orientation : portrait. Objet : L'étude de compatibilité des deux navires et le plan d'opération du prestataire STS.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Prestataire STS / POAC / STS provider / POAC | CallParty PRE active | demi |

**Section (tableau) — Caractéristiques comparées / Compared particulars**

Colonnes : Caractéristique / Particular · Ce navire / This vessel · Navire partenaire / Partner vessel · Compatible ☐ / mesure / Compatible ☐ / measure.

Lignes préremplies : Vessel (ce navire et partenaire) : loa_m, beam_m, dwt ; lignes vierges ajoutées : 1.

**Section (champs) — Plan d'opération / Operations plan**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Zone, mouillage ou en route ; navire manœuvrant / navire constant / Area, at anchor or under way; manoeuvring / constant heading ship | — (à compléter sur le papier) | demi |
| Limites météo et critères d'abandon / Weather limits and abort criteria | — (à compléter sur le papier) | demi |
| Défenses : type, taille, nombre, pression, certificats / Fenders: type, size, number, pressure, certificates | — (à compléter sur le papier) | pleine |
| Flexibles : nombre, diamètre, longueur, pression d'essai, continuité, coupleur de rupture / Hoses: number, diameter, length, test pressure, continuity, breakaway coupling | — (à compléter sur le papier) | pleine |
| Débits, pression, séquence ; communications / Rates, pressure, sequence; communications | — (à compléter sur le papier) | demi |
| Conclusion : compatibles ☐ sous conditions ☐ incompatibles ☐ / Conclusion: compatible ☐ with conditions ☐ incompatible ☐ | — (à compléter sur le papier) | demi |

Note de section : OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapitres 2 (compatibilité), 4 (défenses), 5 (flexibles) et 6 (amarrage). / OCIMF Ship to Ship Transfer Guide for Petroleum, Chemicals and Liquefied Gases (2013), chapters 2 (compatibility), 4 (fenders), 5 (hoses) and 6 (mooring).

**Signatures** : PRE — Prestataire STS / POAC / STS provider / POAC · NAV — Capitaine — ce navire / Master — this vessel · NAV — Capitaine — navire partenaire / Master — partner vessel

## 6.72 `STS_EQUIPMENT` — Attestation des défenses et flexibles STS / STS fenders and hoses attestation

Partie émettrice : PRE — Prestataires. Standard : OCIMF Ship to Ship Transfer Guide (2013) ; ISO 17357 ; OCIMF GMPHOM 2009 / OCIMF Ship to Ship Transfer Guide (2013); ISO 17357; OCIMF GMPHOM 2009. Rôles émetteurs : PRE. Type de document : `STS_DOC`. Répond à : `M3:3.07`, `M3:3.08`, `M9:9.05`. Offert : gabarit M3 ou M9 ou escale reliée. Orientation : portrait. Objet : L'attestation des certificats et essais des défenses et des flexibles mis en œuvre.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Prestataire STS / STS provider | CallParty PRE active | demi |

**Section (tableau) — Défenses primaires et secondaires / Primary and secondary fenders**

Colonnes : Défense (n°, type) / Fender (no., type) · Dimensions / énergie / Size / energy · Pression de service (bar) / Working pressure (bar) · Certificat (n°, organisme, date) / Certificate (no., body, date) · Dernier essai / inspection / Last test / inspection · Vérification physique ☐ / Physical check ☐.

Lignes préremplies : aucune ; lignes vierges ajoutées : 6.

**Section (tableau) — Flexibles de transfert / Transfer hoses**

Colonnes : Flexible (n°) / Hose (no.) · Diamètre / longueur / Diameter / length · Pression d'essai (bar) / date / Test pressure (bar) / date · Continuité électrique (date) / Electrical continuity (date) · Certificat (n°) / Certificate (no.) · Coupleur de rupture ☐ / Breakaway coupling ☐.

Lignes préremplies : aucune ; lignes vierges ajoutées : 6.

**Section (champs) — Autres équipements / Other equipment**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Aussières, manilles, bouées de défense / Hawsers, shackles, fender buoys | — (à compléter sur le papier) | demi |
| Vedettes, remorqueurs d'assistance / Launches, assisting tugs | — (à compléter sur le papier) | demi |
| Moyens antipollution déployables / Deployable pollution response means | — (à compléter sur le papier) | demi |
| Vérifié par (nom, date) / Checked by (name, date) | — (à compléter sur le papier) | demi |

Note de section : OCIMF Ship to Ship Transfer Guide (2013), chapitres 4 et 5 ; ISO 17357 (défenses pneumatiques) ; OCIMF GMPHOM 2009 (flexibles). / OCIMF Ship to Ship Transfer Guide (2013), chapters 4 and 5; ISO 17357 (pneumatic fenders); OCIMF GMPHOM 2009 (hoses).

**Signatures** : PRE — Prestataire STS / STS provider · NAV — Capitaine — reçu / Master — received

## 6.73 `RECEPTION_FACILITY` — Attestation d'agrément et de capacité de l'installation de réception / Reception facility licence and capacity attestation

Partie émettrice : PRE — Prestataires. Standard : MARPOL ; circulaire OMI MEPC.1/Circ.834/Rev.1 / MARPOL; IMO circular MEPC.1/Circ.834/Rev.1. Rôles émetteurs : PRE. Type de document : `CLEANING_DOC`. Répond à : `M6:6.02`. Offert : gabarit M5 ou M6. Orientation : portrait. Objet : L'attestation d'agrément et de capacité disponible de l'installation de réception pour l'escale.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Installation / prestataire / Facility / provider | CallParty PRE active | demi |
| Opération demandée / Operation requested | — (à compléter sur le papier) | demi |

**Section (champs) — Agrément et capacité / Licence and capacity**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Agrément (numéro, autorité, validité) / Licence (number, authority, validity) | — (à compléter sur le papier) | demi |
| Types de déchets ou de résidus acceptés / Kinds of waste or residues accepted | — (à compléter sur le papier) | pleine |
| Capacité disponible aux dates de l'escale (m³) / Capacity available on the call dates (m³) | — (à compléter sur le papier) | demi |
| Moyens (barge, camions, bacs de réception, traitement) / Means (barge, trucks, reception tanks, treatment) | — (à compléter sur le papier) | pleine |
| Délai de mise à disposition / Lead time | — (à compléter sur le papier) | demi |
| Conditions (horaires, accès, tarif de référence) / Conditions (hours, access, reference tariff) | — (à compléter sur le papier) | pleine |

**Section (texte) — Attestation / Attestation**

> Le prestataire atteste disposer de l'agrément et de la capacité ci-dessus pour recevoir les déchets, résidus ou effluents de l'escale, et s'engage à délivrer un bordereau de réception pour chaque remise.
>
> *The provider attests that it holds the licence and the capacity above to receive the call's waste, residues or effluents, and undertakes to issue a receipt for each delivery.*


Note de section : MARPOL (installations de réception adéquates) ; circulaire OMI MEPC.1/Circ.834/Rev.1 ; agrément de l'autorité environnementale. / MARPOL (adequate reception facilities); IMO circular MEPC.1/Circ.834/Rev.1; environmental authority licence.

**Signatures** : PRE — Installation de réception / Reception facility · AGE — Agence — reçu / Agency — received

## 6.74 `WORKS_CREW` — Dossier des intervenants extérieurs — qualifications, certificats, assurances / Outside contractors' file — qualifications, certificates, insurance

Partie émettrice : PRE — Prestataires. Standard : Code IGS ; ISGOTT 6e édition, chapitre 9 ; règlement du port (entreprises extérieures) / ISM Code; ISGOTT 6th edition, chapter 9; port regulations (outside contractors). Rôles émetteurs : PRE. Type de document : `WORKS_DOC`. Répond à : `M7:7.02`. Offert : gabarit M7. Orientation : portrait. Objet : Le dossier des intervenants extérieurs : qualifications, certificats et assurances avant les travaux.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Entreprise intervenante / Contractor | CallParty PRE active | demi |
| Travaux (nature, lieu, période) / Works (nature, place, period) | — (à compléter sur le papier) | pleine |

**Section (tableau) — Intervenants / Personnel**

Colonnes : Nom et prénom / Full name · Fonction / Capacity · Qualification / habilitation (n°, validité) / Qualification / authorization (no., validity) · Formation sécurité (ISGOTT, espace clos, point chaud) / Safety training (ISGOTT, enclosed space, hot work) · Pièce d'identité / Identity document.

Lignes préremplies : aucune ; lignes vierges ajoutées : 8.

**Section (champs) — Entreprise / Company**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Assurance responsabilité civile (assureur, police, validité) / Liability insurance (insurer, policy, validity) | — (à compléter sur le papier) | pleine |
| Certifications (ISO 9001 / 45001, agrément chantier) / Certifications (ISO 9001 / 45001, yard licence) | — (à compléter sur le papier) | demi |
| Matériel apporté à bord (liste, contrôles) / Equipment brought on board (list, checks) | — (à compléter sur le papier) | pleine |
| Responsable des travaux à bord (contact) / Person in charge of the works on board (contact) | — (à compléter sur le papier) | demi |

Note de section : Pièces exigées avant les travaux à bord ou à quai : qualification des intervenants, certificats, assurances ; le permis de travail reste délivré par le capitaine. / Documents required before works on board or at the quay: personnel qualifications, certificates, insurance; the work permit remains issued by the master.

**Signatures** : PRE — Entreprise intervenante / Contractor · NAV — Capitaine — reçu / Master — received

## 6.75 `CP_RECAP` — Nomination et extrait de charte-partie / Nomination and charter-party recap

Partie émettrice : COM — Armateur / affréteur. Standard : Pratique de l'affrètement pétrolier (ASBATANKVOY, SHELLVOY, BPVOY) ; BIMCO / Tanker chartering practice (ASBATANKVOY, SHELLVOY, BPVOY); BIMCO. Rôles émetteurs : COM. Type de document : `CP_RECAP`. Répond à : `M0:04`. Offert : toujours. Orientation : portrait. Objet : L'extrait de recap ou de charte-partie et les clauses d'escale que le mandant communique à l'agence.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Mandant (armateur / affréteur) / Principal (owner / charterer) | CallParty COM actives | demi |
| Opération / quantité / Operation / quantity | PortCall.template_codes, quantity | demi |

**Section (champs) — Charte-partie / Charter-party**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Type et date de la charte-partie (voyage, à temps) / Type and date of the charter-party (voyage, time) | — (à compléter sur le papier) | demi |
| Affréteur / armateur disposant / Charterer / disponent owner | — (à compléter sur le papier) | demi |
| Laycan (de / à) / Laycan (from / to) | — (à compléter sur le papier) | demi |
| Ports de chargement et de déchargement / Loading and discharge ports | — (à compléter sur le papier) | demi |
| Cargaison (produit, quantité, tolérance) / Cargo (product, quantity, tolerance) | — (à compléter sur le papier) | pleine |
| Débit de pompage garanti / pression / Guaranteed pumping rate / pressure | — (à compléter sur le papier) | demi |
| Temps de planche (heures) ; NOR : délai et conditions / Laytime (hours); NOR: notice time and conditions | — (à compléter sur le papier) | pleine |
| Surestaries (taux) / dispatch / Demurrage (rate) / despatch | — (à compléter sur le papier) | demi |
| Clauses d'escale (agents, frais, douane, heures exclues) / Port-call clauses (agents, costs, customs, excepted periods) | — (à compléter sur le papier) | pleine |

**Section (champs) — Nomination / Nomination**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire nommé et accepté le / Vessel nominated and accepted on | — (à compléter sur le papier) | demi |
| Terminal / réceptionnaire / Terminal / receiver | CallParty TER actives | demi |
| Inspecteur désigné / Surveyor appointed | CallParty INS active | demi |
| Agent nommé par / Agent appointed by | PortCall.agency | demi |
| Instructions particulières (échantillonnage, documents, scellés) / Special instructions (sampling, documents, seals) | — (à compléter sur le papier) | pleine |

Note de section : Extrait communiqué à l'agence pour l'escale ; les clauses non reproduites restent celles de la charte-partie signée (BIMCO / ASBATANKVOY / SHELLVOY ou autre formule). / Extract provided to the agency for the call; clauses not reproduced remain those of the signed charter-party (BIMCO / ASBATANKVOY / SHELLVOY or other form).

**Signatures** : COM — Mandant / Principal · AGE — Agence — reçu / Agency — received

## 6.76 `DOC_INSTRUCTIONS` — Instruction documentaire du mandant (connaissement) / Principal's documentary instructions (bill of lading)

Partie émettrice : COM — Armateur / affréteur. Standard : Pratique du commerce des hydrocarbures ; Règles de La Haye-Visby / Oil trade practice; Hague-Visby Rules. Rôles émetteurs : COM. Type de document : `DOC_INSTRUCTIONS`. Répond à : `M2:2.16`. Offert : gabarit M2. Orientation : portrait. Objet : L'instruction écrite du mandant pour l'émission du connaissement et des documents de cargaison.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Mandant / Principal | CallParty COM actives | demi |
| Produit / quantité / Product / quantity | PortCall.product, quantity | demi |

**Section (champs) — Connaissement / Bill of lading**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Expéditeur (shipper) / Shipper | — (à compléter sur le papier) | pleine |
| Destinataire (consignee) — à l'ordre de / Consignee — to the order of | — (à compléter sur le papier) | pleine |
| Notifier / Notify party | — (à compléter sur le papier) | pleine |
| Nombre d'originaux et de copies / Number of originals and copies | — (à compléter sur le papier) | demi |
| Base du chiffre : terre ☐ bord ☐ inspecteur ☐ / Basis of figure: shore ☐ ship ☐ surveyor ☐ | — (à compléter sur le papier) | demi |
| Description des marchandises (libellé exact) / Description of goods (exact wording) | — (à compléter sur le papier) | pleine |
| Port de déchargement / destination / Port of discharge / destination | — (à compléter sur le papier) | demi |
| Mentions de fret ; clauses à insérer / Freight terms; clauses to insert | — (à compléter sur le papier) | pleine |
| Remise des originaux à (personne, adresse) / Originals to be delivered to (person, address) | — (à compléter sur le papier) | pleine |

**Section (champs) — Autres documents demandés / Other documents requested**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Certificats de quantité et de qualité (destinataires) / Certificates of quantity and quality (recipients) | — (à compléter sur le papier) | demi |
| Certificat d'origine, facture, liste de colisage / Certificate of origin, invoice, packing list | — (à compléter sur le papier) | demi |
| Reçu du capitaine (mate's receipt), time sheet, rapport des faits / Mate's receipt, time sheet, statement of facts | — (à compléter sur le papier) | demi |
| Lettre de protestation à émettre si / Letter of protest to be issued if | — (à compléter sur le papier) | demi |

**Section (texte) — Instruction / Instruction**

> Le mandant donne à l'agence l'instruction écrite d'émettre, pour le compte du capitaine, le connaissement selon les mentions ci-dessus. L'émission n'intervient qu'après accord sur la quantité ; toute divergence est signalée au mandant avant signature.
>
> *The principal instructs the agency in writing to issue, for the master, the bill of lading with the particulars above. The issue takes place only after agreement on the quantity; any discrepancy is reported to the principal before signature.*


Note de section : FLX-CDC-001 EF-7.4 — verrou du connaissement : l'instruction documentaire écrite (tâche M2:2.16) est l'une des conditions du point d'arrêt BL_ISSUE. / FLX-CDC-001 EF-7.4 — bill of lading lock: the written documentary instruction (task M2:2.16) is one of the conditions of the BL_ISSUE hold point.

**Signatures** : COM — Mandant / Principal · AGE — Agence — reçu / Agency — received

## 6.77 `INSURANCE` — Confirmation des couvertures d'assurance / Insurance cover confirmation

Partie émettrice : COM — Armateur / affréteur. Standard : Pratique du P&I et de l'assurance maritime ; OCIMF Ship to Ship Transfer Guide (assurances) / P&I and marine insurance practice; OCIMF Ship to Ship Transfer Guide (insurance). Rôles émetteurs : COM. Type de document : `INSURANCE`. Répond à : `M3:3.09`, `M9:9.10`. Offert : gabarit M3 ou M9 ou escale reliée. Orientation : portrait. Objet : La confirmation des couvertures d'assurance des navires et du prestataire pour l'opération STS ou à couple.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Navire partenaire / Partner vessel | PortCall.linked_call | demi |
| Prestataire STS / terminal / STS provider / terminal | CallParty PRE ou TER | demi |

**Section (tableau) — Couvertures / Covers**

Colonnes : Assuré / Insured · Nature (P&I, corps et machines, RC prestataire, pollution) / Kind (P&I, hull and machinery, provider's liability, pollution) · Assureur / club / Insurer / club · Police / certificat n° / Policy / certificate no. · Validité / Validity · Plafond / Limit.

Lignes préremplies : Vessel, PortCall.linked_call, CallParty PRE ; lignes vierges ajoutées : 2.

**Section (champs) — Confirmation / Confirmation**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Opération couverte : STS ☐ accostage à couple ☐ autre ☐ / Operation covered: STS ☐ double banking ☐ other ☐ | — (à compléter sur le papier) | demi |
| Clauses particulières (STS clause, knock-for-knock) / Special clauses (STS clause, knock-for-knock) | — (à compléter sur le papier) | pleine |
| Certificat CLC / Bunkers / assurance pollution (n°, validité) / CLC / Bunkers / pollution insurance certificate (no., validity) | — (à compléter sur le papier) | pleine |
| Confirmé par (nom, fonction) / Confirmed by (name, capacity) | — (à compléter sur le papier) | demi |

Note de section : Les attestations des assureurs sont jointes au dossier ; la confirmation du mandant ne se substitue pas aux certificats d'assurance statutaires du navire (CLC 1992, Convention Bunkers 2001). / The insurers' certificates are attached to the file; the principal's confirmation does not replace the ship's statutory insurance certificates (CLC 1992, Bunkers Convention 2001).

**Signatures** : COM — Mandant / Principal · AGE — Agence — reçu / Agency — received

## 6.78 `LOI` — Lettre de garantie — livraison sans connaissement original / Letter of indemnity — delivery without original bill of lading

Partie émettrice : COM — Armateur / affréteur. Standard : Formules types du Groupe international des clubs P&I (LOI A / B) / International Group of P&I Clubs standard forms (LOI A / B). Rôles émetteurs : COM. Type de document : `LOI`. Répond à : —. Offert : gabarit M1 ou M3 ou escale reliée. Orientation : portrait. Objet : La lettre de garantie remise à l'armateur pour une livraison sans présentation du connaissement original.

**Section (champs) — Navire et escale / Vessel and call**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Navire / Vessel | Vessel.name, Vessel.imo | demi |
| Pavillon / type / Flag / type | Vessel.flag, Vessel.vessel_type | demi |
| Escale / voyage / Call / voyage | PortCall.reference, PortCall.voyage_number | demi |
| Port / Port | Port.name, Port.code | demi |
| Poste / zone / Berth / area | PortCall.berth ou CallStage.berth_kind de l'étape en cours | demi |
| Agence / Agency | PortCall.agency (Organization.name) | demi |
| Destinataire (armateur / capitaine) / Addressee (owner / master) | — (à compléter sur le papier) | pleine |
| Date / Date | — (à compléter sur le papier) | demi |

**Section (champs) — Cargaison et livraison demandée / Cargo and delivery requested**

| Champ FR / EN | Source de préremplissage | Largeur |
|---|---|---|
| Cargaison (produit, quantité) / Cargo (product, quantity) | PortCall.product, quantity | demi |
| Connaissement(s) n° / date / port de chargement / Bill(s) of lading no. / date / port of loading | — (à compléter sur le papier) | pleine |
| Livrer à (réceptionnaire) / Deliver to (receiver) | CallParty TER actives | demi |
| Lieu de livraison / Place of delivery | Port.name | demi |
| Motif : originaux non parvenus ☐ port autre que celui du connaissement ☐ / Reason: originals not arrived ☐ port other than the B/L port ☐ | — (à compléter sur le papier) | demi |

**Section (texte) — Engagement / Undertaking**

> En contrepartie de la livraison de la cargaison sans présentation des connaissements originaux, le soussigné s'engage à indemniser l'armateur, le capitaine et leurs assureurs de toute responsabilité, perte, dommage ou dépense résultant de cette livraison, à fournir les fonds nécessaires à la défense de toute action, à procurer la mainlevée de toute saisie du navire et à remettre les originaux dès réception.
>
> *In consideration of delivering the cargo without production of the original bills of lading, the undersigned undertakes to indemnify the owner, the master and their insurers against any liability, loss, damage or expense arising from such delivery, to provide funds for the defence of any claim, to secure the release of the vessel from any arrest and to surrender the originals as soon as received.*

> Le présent engagement est régi par le droit désigné au contrat et prend fin à la remise des originaux.
>
> *This undertaking is governed by the law designated in the contract and ends on surrender of the originals.*


Note de section : Structure des lettres de garantie types du Groupe international des clubs P&I (formules A / B, livraison sans connaissement, livraison dans un port autre) ; à signer par le mandant et, le cas échéant, contresigner par une banque. / Structure of the International Group of P&I Clubs standard letters of indemnity (forms A / B, delivery without bill of lading, delivery at another port); signed by the principal and, where required, countersigned by a bank.

**Signatures** : COM — Mandant (réceptionnaire / affréteur) / Principal (receiver / charterer) · COM — Banque — contresignature (le cas échéant) / Bank — countersignature (if required) · AGE — Agence — reçu pour l'armateur / Agency — received for the owner
