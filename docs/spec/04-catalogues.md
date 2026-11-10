# 4. Catalogues de référence
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Contenu chargé dans chaque port par `bootstrap_ports` (`apps/registry/catalog.py`), puis modifiable par l'administrateur fonctionnel sans code (gabarits versionnés, types, causes, points d'arrêt). Les codes sont stables : ils sont cités par les points d'arrêt, les demandes et les documents.

## 4.1 Échéances relatives (`TIMING`)

| Code | Ancre | Décalage (min) | Libellé FR / EN |
|---|---|---|---|
| `NOM` | NOM | 0 | à la nomination / at nomination |
| `ETA-7j` | ETA | -10080 | ETA − 7 j / ETA − 7 d |
| `ETA-5j` | ETA | -7200 | ETA − 5 j / ETA − 5 d |
| `ETA-72h` | ETA | -4320 | ETA − 72 h / ETA − 72 h |
| `ETA-48h` | ETA | -2880 | ETA − 48 h / ETA − 48 h |
| `ETA-24h` | ETA | -1440 | ETA − 24 h / ETA − 24 h |
| `ETA-12h` | ETA | -720 | ETA − 12 h / ETA − 12 h |
| `ETA` | ETA | 0 | à l'arrivée / on arrival |
| `ETA+2h` | ETA | 120 | ETA + 2 h / ETA + 2 h |
| `ETA+4h` | ETA | 240 | ETA + 4 h / ETA + 4 h |
| `ETB-48h` | ETB | -2880 | ETB − 48 h / ETB − 48 h |
| `ETB-24h` | ETB | -1440 | ETB − 24 h / ETB − 24 h |
| `ETB-12h` | ETB | -720 | ETB − 12 h / ETB − 12 h |
| `ETB-6h` | ETB | -360 | ETB − 6 h / ETB − 6 h |
| `ETB-2h` | ETB | -120 | ETB − 2 h / ETB − 2 h |
| `ATB+2h` | ATB | 120 | ATB + 2 h / ATB + 2 h |
| `T0-5j` | T0 | -7200 | T0 − 5 j / T0 − 5 d |
| `T0-72h` | T0 | -4320 | T0 − 72 h / T0 − 72 h |
| `T0-48h` | T0 | -2880 | T0 − 48 h / T0 − 48 h |
| `T0-24h` | T0 | -1440 | T0 − 24 h / T0 − 24 h |
| `T0-6h` | T0 | -360 | T0 − 6 h / T0 − 6 h |
| `T0-2h` | T0 | -120 | T0 − 2 h / T0 − 2 h |
| `T0` | T0 | 0 | avant T0 / before T0 |
| `T1-1h` | T1 | -60 | T1 − 1 h / T1 − 1 h |
| `T1` | T1 | 0 | fin d'opération / end of operation |
| `T1+1h` | T1 | 60 | T1 + 1 h / T1 + 1 h |
| `T1+2h` | T1 | 120 | T1 + 2 h / T1 + 2 h |
| `T1+4h` | T1 | 240 | T1 + 4 h / T1 + 4 h |
| `T1+8h` | T1 | 480 | T1 + 8 h / T1 + 8 h |
| `T1+12h` | T1 | 720 | T1 + 12 h / T1 + 12 h |
| `T1+24h` | T1 | 1440 | T1 + 24 h / T1 + 24 h |
| `NOR+6h` | NOR | 360 | NOR + 6 h / NOR + 6 h |
| `ATD` | ATD | 0 | avant ATD / before ATD |
| `ATD-4h` | ATD | -240 | ATD − 4 h / ATD − 4 h |
| `ATD-2h` | ATD | -120 | ATD − 2 h / ATD − 2 h |
| `ATD+24h` | ATD | 1440 | ATD + 24 h / ATD + 24 h |
| `ATD+15j` | ATD | 21600 | ATD + 15 j / ATD + 15 d |
| `ATD+30j` | ATD | 43200 | ATD + 30 j / ATD + 30 d |
| `EVT` | — (événement) | 0 | événement / event |
| `CONT` | — (événement) | 0 | en continu / continuous |
| `NOW` | — (événement) | 0 | immédiat / immediate |
| `CP` | — (événement) | 0 | selon C/P / per C/P |
| `DAILY` | — (événement) | 0 | quotidien / daily |
| `PHASE` | — (événement) | 0 | par phase / per phase |
| `DUR` | — (événement) | 0 | pendant la configuration / throughout |
| `DELIV` | — (événement) | 0 | à la livraison / on delivery |

Ancres : NOM nomination (création de l'escale), ETA, ETB, ATB, T0, T1, NOR, ATD. Un décalage négatif précède l'ancre. Les échéances sont recalculées en cascade à chaque révision des heures.

## 4.2 Gabarits d'escale et tâches (`TEMPLATES`)

Natures : D décision · F fourniture (document) · S saisie (jalon ou mesure) · R réalisation · Cs contresignature ; criticité : B bloquante (point d'arrêt) · N normale. Les colonnes « demande », « jalons » et « document » relient la tâche à l'objet qui la fait automatiquement.

### `M0` — Socle commun / Common base

Nature : BASE · ordre 0 · zones : toutes zones · Instancié pour toute escale, quelle que soit l'opération.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M0:01` | Nomination et déclaration | AGE | R | à la nomination | B | N2 | Créer l'escale et inviter les parties prenantes / Create the call and invite the stakeholders | auto `call.created` | jamais sans objet | FLX-SPEC-001 règle 1 — l'agence crée l'escale |
| `M0:02` | Nomination et déclaration | AGE | F | ETA − 7 j | B | N2 | Fournir le jeu de données navire : Q88 ou VPQ, plans, particularités du collecteur, débit de pompage / Provide the vessel dataset: Q88 or VPQ, plans, manifold particulars, pumping rate | document `Q88` |  | PRO-MAR-001 §3.2 — dossier navire / OCIMF |
| `M0:03` | Nomination et déclaration | NAV | F | ETA − 72 h | B | N2 | Fournir les certificats statutaires et d'assurance — validité contrôlée à la date de départ prévue / Provide statutory and insurance certificates — validity checked against the planned departure date | document `CERTIFICATES` |  | SOLAS / MARPOL / CLC — certificats statutaires |
| `M0:04` | Nomination et déclaration | COM | F | ETA − 72 h | N | N2 | Fournir l'extrait de recap ou de charte-partie et les clauses d'escale / Provide the recap or charter-party extract and the port-call clauses | document `CP_RECAP` |  |  |
| `M0:05` | Nomination et déclaration | AGE | C | ETA − 72 h | B | N2 | Confirmer le contrôle des listes de sanctions (navire, armateur, affréteur, cargaison, origine) / Confirm the sanctions screening (vessel, owner, charterer, cargo, origin) |  |  | Obligations de sanctions / sanctions compliance |
| `M0:06` | Nomination et déclaration | TER | F | ETA − 7 j | B | N2 | Demander l'acceptation du navire (vetting) avec rapport SIRE/CDI, historique PSC, trois dernières cargaisons / Request vessel acceptance (vetting) with SIRE/CDI report, PSC history, last three cargoes | demande `VESSEL_ACCEPTANCE` (submit) |  | PRO-MAR-001 §3.2.2.1 — circuit de vetting |
| `M0:07` | Nomination et déclaration | CAP + APO | D | ETA − 5 j | B | N2 | Décider l'acceptation du navire, avec durée de validité et conditions — motif de refus en N3 / Decide vessel acceptance, with validity and conditions — refusal reason is N3 | demande `VESSEL_ACCEPTANCE` (decide) |  | PRO-MAR-001 §3.2.2.1 — acceptation du navire |
| `M0:08` | Nomination et déclaration | AGE | R | ETA − 72 h | B | N2 | Déclarer l'escale et solliciter le green light / Declare the call and request the green light | auto `call.declared` |  | Règlement d'exploitation du port — déclaration d'escale |
| `M0:09` | Nomination et déclaration | CAP | D | ETA − 48 h | B | N2 | Accorder le green light / Grant the green light | demande `GREEN_LIGHT` (decide) |  | PRO-MAR-001 — green light de la capitainerie |
| `M0:10` | Nomination et déclaration | AGE | F | ETA − 72 h | B | N2 | Demander le poste et le créneau / Request the berth and the slot | demande `BERTH` (submit) |  | Règlement d'exploitation — attribution des postes |
| `M0:11` | Nomination et déclaration | APO | D | ETA − 24 h | B | N2 | Attribuer le poste et le créneau / Assign the berth and the slot | demande `BERTH` (decide) |  | PRO-MAR-001 — attribution du poste |
| `M0:12` | Nomination et déclaration | CAP + TER | F | ETA − 24 h | N | N2 | Publier les conditions limites d'exploitation du poste (vent, houle, courant, visibilité) / Publish the berth operating limits (wind, swell, current, visibility) | document `BERTH_LIMITS` | zones JETTY/SPM |  |
| `M0:13` | Nomination et déclaration | AGE | F | ETA − 24 h | B | N2 | Enregistrer la preuve de dépôt des formulaires FAL au guichet unique — le dépôt lui-même reste hors plateforme / Record proof of filing of the FAL forms with the single window — the filing itself stays outside the platform | document `FAL_PROOF` |  | Convention FAL |
| `M0:14` | Nomination et déclaration | NAV | F | ETA − 24 h | B | N2 | Transmettre la déclaration maritime de santé / Send the maritime declaration of health | document `MDH` |  | RSI 2005 — déclaration maritime de santé |
| `M0:15` | Nomination et déclaration | NAV | F | ETA − 72 h | B | N2 | Notifier les eaux de ballast : volumes, origine, méthode de conformité / Notify ballast water: volumes, origin, compliance method | document `BALLAST_NOTIFICATION` |  | Convention BWM |
| `M0:16` | Nomination et déclaration | AGE | F | ETA − 24 h | N | N2 | Notification préalable de remise de déchets / Advance notification of waste delivery | demande `WASTE_COLLECTION` (submit) |  |  |
| `M0:17` | Nomination et déclaration | SUR | R | ETA − 24 h | B | N2 | Communiquer le niveau de sûreté ISPS applicable / Communicate the applicable ISPS security level |  |  | Code ISPS |
| `M0:18` | Nomination et déclaration | SVC | C | ETB − 12 h | B | N2 | Réserver et confirmer pilote, remorqueurs, lamaneurs / Book and confirm pilot, tugs and mooring gang | demande `MARINE_SERVICES` (decide) | zones JETTY/SPM | Règlement de pilotage — pilotage obligatoire |
| `M0:19` | Nomination et déclaration | AGE | C | ETB − 12 h | N | N2 | Réserver surveyor, laboratoire et prestataires / Book surveyor, laboratory and providers |  |  |  |
| `M0:20` | Arrivée et mise à disposition | NAV | R | événement | B | N2 | Enregistrer l'arrivée à la limite du port — corroboration AIS / Record arrival at the port limit — AIS corroboration | jalons `ARRIVAL` |  | PRO-MAR-001 — arrivée |
| `M0:21` | Arrivée et mise à disposition | ADM | D | ETA + 2 h | B | N2 | Accorder la libre pratique / Grant free pratique | demande `FREE_PRATIQUE` (decide) |  | RSI 2005 — libre pratique |
| `M0:22` | Arrivée et mise à disposition | ADM | D | ETA + 4 h | B | N2 | Traiter les formalités douanières et d'immigration ; relever les scellés / Process customs and immigration formalities; check the seals | demande `CUSTOMS_IMMIGRATION` (decide) |  | Code des douanes / immigration |
| `M0:23` | Arrivée et mise à disposition | AGE | F | selon C/P | B | N1 | Remettre la NOR aux destinataires désignés par la charte-partie — visibilité N1 / Tender the NOR to the recipients named in the charter party — N1 visibility | jalons `NOR_TENDERED` |  | Charte-partie — remise de la NOR |
| `M0:24` | Arrivée et mise à disposition | TER + COM | S | NOR + 6 h | N | N2 | Accuser réception de la NOR / Acknowledge the NOR | jalons `NOR_TENDERED` | conjointe |  |
| `M0:25` | Arrivée et mise à disposition | CAP | D | ETB − 2 h | B | N2 | Délivrer l'autorisation de mouvement / Issue the movement authorization | demande `MOVEMENT` (decide) | zones JETTY/SPM | PRO-MAR-001 — autorisation de mouvement |
| `M0:26` | Accostage et interface navire/terre | SVC + NAV | R | événement | B | N2 | Enregistrer pilote à bord, première amarre, all fast, passerelle en place / Record pilot on board, first line, all fast, gangway in place | jalons `PILOT_ON_BOARD_ARR`, `FIRST_LINE`, `ALL_FAST`, `GANGWAY` | zones JETTY/SPM | PRO-MAR-001 — accostage |
| `M0:27` | Accostage et interface navire/terre | TER + NAV | S | ATB + 2 h | B | N2 | Tenir la réunion pré-transfert et signer le compte rendu / Hold the pre-transfer meeting and sign the minutes |  | conjointe, zones JETTY/SPM | ISGOTT — réunion pré-transfert |
| `M0:28` | Accostage et interface navire/terre | TER + NAV | S | avant T0 | B | N2 | Compléter et signer conjointement la liste de contrôle navire/terre / Complete and jointly sign the ship/shore safety checklist |  | conjointe, jamais sans objet, zones JETTY/SPM | ISGOTT chap. 26 — SSSCL |
| `M0:29` | Accostage et interface navire/terre | TER + NAV | R | avant T0 | B | N2 | Réaliser et consigner l'essai d'arrêt d'urgence / Perform and record the emergency shutdown test | jalons `ESD_TEST` | jamais sans objet, zones JETTY/SPM | ISGOTT — essai ESD |
| `M0:30` | Accostage et interface navire/terre | SUR + NAV | S | ATB + 2 h | N | N2 | Établir la déclaration de sûreté si requise / Establish the declaration of security if required |  | conjointe |  |
| `M0:31` | Accostage et interface navire/terre | TER | C | avant T0 | B | N2 | Confirmer la mise en sécurité du poste : dalots obturés, plateaux, kit antipollution, moyens incendie / Confirm berth safety: scuppers plugged, drip trays, spill kit, firefighting means |  | zones JETTY/SPM | ISGOTT / MARPOL — prévention de la pollution |
| `M0:32` | Clôture et appareillage | PRE | F | avant ATD | B | N2 | Remettre les déchets et fournir le bordereau de réception / Deliver the waste and issue the waste receipt | jalons `WASTE_DELIVERED` |  | MARPOL — installations de réception |
| `M0:33` | Clôture et appareillage | ADM | D | ATD − 4 h | B | N2 | Traiter les formalités de sortie / Process outward formalities | demande `OUTWARD_FORMALITIES` (decide) |  | Code des douanes — formalités de sortie |
| `M0:34` | Clôture et appareillage | CAP | D | ATD − 2 h | B | N2 | Délivrer le congé de départ / Issue the departure clearance | demande `DEPARTURE_CLEARANCE` (decide) |  | PRO-MAR-001 — congé de départ |
| `M0:35` | Clôture et appareillage | SVC + NAV | R | événement | B | N2 | Enregistrer pilote à bord, dernière amarre larguée, appareillage / Record pilot on board, last line released, departure | jalons `PILOT_ON_BOARD_DEP`, `LAST_LINE`, `DEPARTED` | zones JETTY/SPM | PRO-MAR-001 — appareillage |
| `M0:35b` | Clôture et appareillage | NAV | R | événement | B | N2 | Enregistrer l'appareillage de la rade ou de la zone STS / Record departure from the roads or the STS area | jalons `DEPARTED` | zones ANCHORAGE/STS_AREA | PRO-MAR-001 — appareillage |
| `M0:36` | Clôture et appareillage | AGE + NAV/TER | F | ATD + 24 h | B | N2 | Produire le rapport des faits consolidé et le faire signer / Produce the consolidated statement of facts and have it signed | document `SOF` | jamais sans objet | PRO-MAR-001 — rapport des faits |
| `M0:37` | Clôture et appareillage | AGE | F | ATD + 24 h | N | N2 | Transmettre le time sheet / Send the time sheet | document `TIME_SHEET` |  |  |
| `M0:38` | Clôture et appareillage | AGE | F | ATD + 15 j | N | N2 | Transmettre le compte d'escale final avec justificatifs / Send the final port-call account with supporting documents | document `PORT_ACCOUNT` |  |  |
| `M0:39` | Clôture et appareillage | AGE + CAP | C | ATD + 30 j | B | N2 | Clôturer l'escale — refusé si contestation ouverte non tracée / Close the call — refused while a dispute is open |  | conjointe, jamais sans objet | FLX-CDC-001 EF-4.3 — clôture |

### `M1` — Déchargement (import) / Discharge (import)

Nature : OPERATION · ordre 1 · zones : JETTY, SPM · En complément de M0.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M1:1.01` |  | AGE | F | ETA − 7 j | B | N2 | Fournir l'autorisation d'importation du produit / Provide the product import authorization | document `IMPORT_AUTH` |  | Réglementation des importations pétrolières |
| `M1:1.02` |  | NAV | F | ETB − 24 h | B | N2 | Fournir le plan de déchargement et de ballastage / Provide the discharge and ballasting plan | document `DISCHARGE_PLAN` |  | ISGOTT — plan de cargaison |
| `M1:1.03` |  | TER | R | ETB − 12 h | B | N2 | Confirmer le creux disponible, l'alignement des bacs et la ligne dédiée / Confirm available ullage, tank line-up and dedicated line |  |  | PRO-MAR-001 — préparation terminal |
| `M1:1.04` |  | NAV | R | avant T0 | B | N2 | Confirmer la disponibilité du gaz inerte et la teneur en oxygène / Confirm inert gas availability and oxygen content |  |  | SOLAS II-2 / ISGOTT — gaz inerte |
| `M1:1.05` |  | INS + NAV/TER | R | avant T0 | B | N2 | Réaliser le jaugeage initial à bord — creux, températures, eau libre, densité / Perform initial gauging on board — ullages, temperatures, free water, density | jalons `INITIAL_GAUGING` |  | API MPMS — jaugeage |
| `M1:1.06` |  | TER + INS | R | avant T0 | B | N2 | Relever les jauges des bacs récepteurs ou les index compteurs / Read receiving tank gauges or meter totalisers |  |  | API MPMS — mesurage à terre |
| `M1:1.07` |  | INS | R | avant T0 | B | N2 | Prélever, sceller et étiqueter les échantillons / Draw, seal and label the samples |  |  | API MPMS 8 — échantillonnage |
| `M1:1.08` |  | INS | R | avant T0 | N | N2 | Calculer la quantité de départ et la comparer au connaissement / Compute the opening quantity and compare it with the bill of lading |  |  |  |
| `M1:1.09` |  | TER | R | événement | B | N2 | Enregistrer le raccordement des bras ou flexibles / Record connection of the arms or hoses | jalons `HOSES_CONNECTED` |  | ISGOTT — raccordement |
| `M1:1.10` |  | TER + NAV | R | événement | B | N2 | Enregistrer le démarrage et l'atteinte du débit de régime / Record start and full rate reached | jalons `TRANSFER_START`, `FULL_RATE` |  | PRO-MAR-001 — démarrage du transfert |
| `M1:1.11` |  | TER + NAV | R | en continu | B | N2 | Renseigner le journal de pompage — pression au collecteur, débit, température / Keep the pumping log — manifold pressure, rate, temperature |  | continue | ISGOTT — surveillance du transfert |
| `M1:1.12` |  | ANY | R | immédiat | B | N2 | Déclarer chaque interruption : début, fin et cause en liste fermée / Declare every interruption: start, end and cause from the closed list |  | continue | FLX-SPEC-001 §7 — événement 18 |
| `M1:1.13` |  | TER + NAV | R | événement | B | N2 | Enregistrer l'assèchement, la fin de transfert et la vidange des lignes / Record stripping, end of transfer and line draining | jalons `TOPPING_OFF`, `TRANSFER_END`, `LINES_DRAINED` |  | PRO-MAR-001 — fin de transfert |
| `M1:1.14` |  | INS | F | T1 + 2 h | B | N2 | Produire le certificat de citernes vides ou le constat contradictoire de ROB / Issue the empty-tanks certificate or the joint ROB statement | document `EMPTY_TANKS_CERT` |  | API MPMS — ROB |
| `M1:1.15` |  | INS + NAV/TER | R | T1 + 4 h | B | N2 | Réaliser le jaugeage final à bord et à terre / Perform final gauging on board and ashore | jalons `FINAL_GAUGING` |  | API MPMS — jaugeage final |
| `M1:1.16` |  | INS | F | T1 + 12 h | B | N2 | Produire les certificats de quantité et de qualité / Issue the quantity and quality certificates | document `QQ_CERT` |  | API MPMS / ASTM |
| `M1:1.17` |  | TER | F | T1 + 12 h | N | N2 | Émettre le bon de réception du terminal / Issue the terminal receipt | document `TERMINAL_RECEIPT` |  |  |
| `M1:1.18` |  | AGE | F | T1 + 24 h | B | N2 | Déposer la déclaration douanière de cargaison / File the customs cargo declaration | document `CARGO_DECLARATION` |  | Code des douanes |
| `M1:1.19` |  | ANY | F | T1 + 24 h | N | N2 | Émettre une lettre de protêt si l'écart bord/terre excède la tolérance / Issue a letter of protest if the ship/shore difference exceeds tolerance | document `PROTEST` |  |  |

### `M2` — Chargement (export) / Loading (export)

Nature : OPERATION · ordre 2 · zones : JETTY, SPM · En complément de M0.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M2:2.01` |  | AGE | F | ETA − 7 j | B | N2 | Fournir l'autorisation d'exportation du produit / Provide the product export authorization | document `EXPORT_AUTH` |  | Réglementation des exportations |
| `M2:2.02` |  | NAV | F | ETA − 72 h | B | N2 | Déclarer les trois dernières cargaisons / Declare the last three cargoes | document `LAST_CARGOES` |  | ISGOTT — compatibilité des cargaisons |
| `M2:2.03` |  | NAV | F | ETB − 24 h | B | N2 | Fournir le plan de chargement : séquence, stabilité, contraintes de structure, tirant d'eau / Provide the loading plan: sequence, stability, structural stresses, draft | document `LOADING_PLAN` |  | SOLAS / ISGOTT — plan de chargement |
| `M2:2.04` |  | INS + NAV/TER | F | avant T0 | B | N2 | Réaliser l'inspection contradictoire des citernes et délivrer le certificat de propreté / Carry out the joint tank inspection and issue the cleanliness certificate | document `CLEANLINESS_CERT` |  | API MPMS — inspection des citernes |
| `M2:2.05` |  | INS | R | avant T0 | B | N2 | Mesurer et consigner l'OBQ / Measure and record the OBQ | jalons `INITIAL_GAUGING` |  | API MPMS — OBQ |
| `M2:2.06` |  | NAV | R | avant T0 | B | N2 | Confirmer l'inertage, la teneur en oxygène et la pression positive / Confirm inerting, oxygen content and positive pressure |  |  | SOLAS II-2 — gaz inerte |
| `M2:2.07` |  | INS | F | avant T0 | B | N2 | Produire le certificat de qualité du produit à terre / Issue the shore product quality certificate | document `QUALITY_CERT` |  | ASTM — qualité produit |
| `M2:2.08` |  | TER + INS | R | avant T0 | B | N2 | Relever les jauges des bacs expéditeurs ou les index compteurs / Read shipping tank gauges or meter totalisers |  |  | API MPMS — mesurage à terre |
| `M2:2.09` |  | TER + NAV | S | avant T0 | B | N2 | Confirmer la compatibilité et l'essai du système de récupération des vapeurs — si le poste en est équipé / Confirm compatibility and test of the vapour recovery system — if the berth is so equipped |  | conjointe | ISGOTT — récupération des vapeurs |
| `M2:2.10` |  | TER + NAV | R | événement | B | N2 | Enregistrer le démarrage à débit réduit et la montée en régime / Record start at reduced rate and ramp-up to full rate | jalons `TRANSFER_START`, `FULL_RATE` |  | PRO-MAR-001 — démarrage du transfert |
| `M2:2.11` |  | TER + NAV | R | en continu | B | N2 | Renseigner le journal de pompage / Keep the pumping log |  | continue | ISGOTT — surveillance du transfert |
| `M2:2.12` |  | ANY | R | immédiat | B | N2 | Déclarer chaque interruption : début, fin et cause en liste fermée / Declare every interruption: start, end and cause from the closed list |  | continue | FLX-SPEC-001 §7 — événement 18 |
| `M2:2.13` |  | TER | C | T1 − 1 h | B | N2 | Émettre les préavis de topping-off convenus / Give the agreed topping-off notices |  |  | ISGOTT — topping-off |
| `M2:2.14` |  | INS + NAV/TER | R | T1 + 4 h | B | N2 | Réaliser le jaugeage final contradictoire / Perform the joint final gauging | jalons `FINAL_GAUGING` |  | API MPMS |
| `M2:2.15` |  | INS | F | T1 + 8 h | B | N2 | Produire le certificat de quantité / Issue the certificate of quantity | document `QQ_CERT` |  | API MPMS — certificat de quantité |
| `M2:2.16` |  | COM | F | T1 + 8 h | B | N2 | Fournir l'instruction documentaire écrite du mandant (connaissement, jeux originaux) / Provide the principal's written documentary instructions (bill of lading, original sets) | document `DOC_INSTRUCTIONS` | jamais sans objet | FLX-CDC-001 EF-7.4 — verrou du connaissement |
| `M2:2.17` |  | AGE | F | T1 + 24 h | B | N2 | Émettre le connaissement — verrou : impossible sans la tâche 2.16 et sans accord sur la quantité / Issue the bill of lading — lock: impossible without task 2.16 and an agreed quantity | document `BILL_OF_LADING` | jamais sans objet | FLX-CDC-001 EF-7.4 — verrou du connaissement |
| `M2:2.18` |  | AGE | F | T1 + 24 h | B | N2 | Déposer le manifeste et la déclaration d'exportation / File the manifest and the export declaration | document `EXPORT_MANIFEST` |  | Code des douanes |

### `M3` — Transbordement navire-navire (STS) / Ship-to-ship transfer (STS)

Nature : OPERATION · ordre 3 · zones : ANCHORAGE, STS_AREA · exige une escale reliée · Relie deux escales : chaque navire a la sienne, avec son capitaine. Le POAC est porté par le prestataire STS (rôle PRE).

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M3:3.01` |  | AGE | F | T0 − 48 h | B | N2 | Notifier l'opération à l'État côtier — 48 heures / Notify the coastal State of the operation — 48 hours | document `STS_NOTIFICATION` |  | MARPOL Annexe I règle 42 |
| `M3:3.02` |  | NAV | F | T0 − 72 h | B | N2 | Fournir le plan d'opérations STS approuvé par l'État du pavillon / Provide the STS operations plan approved by the flag State | document `STS_PLAN` | par navire | MARPOL Annexe I règle 41 |
| `M3:3.03` |  | CAP | D | T0 − 48 h | B | N2 | Autoriser la zone et la fenêtre horaire / Authorize the area and the time window | demande `STS_ZONE` (decide) |  | Règlement de la rade |
| `M3:3.04` |  | AGE + COM | F | T0 − 72 h | B | N2 | Désigner le POAC : mandat écrit et justificatifs de qualification / Appoint the POAC: written mandate and qualification records | document `STS_DOC` |  | OCIMF STS Transfer Guide — POAC |
| `M3:3.05` |  | PRE | F | T0 − 72 h | B | N2 | Produire l'étude de compatibilité des deux navires / Produce the compatibility study of both vessels | document `STS_DOC` |  | OCIMF STS Transfer Guide |
| `M3:3.06` |  | NAV + PRE | S | T0 − 24 h | B | N2 | Signer le plan conjoint d'opération — deux capitaines et POAC / Sign the joint operation plan — both masters and the POAC |  | conjointe, par navire | OCIMF STS Transfer Guide |
| `M3:3.07` |  | PRE | F | T0 − 48 h | B | N2 | Fournir les certificats et essais des défenses primaires et secondaires / Provide certificates and tests of primary and secondary fenders | document `STS_DOC` |  | OCIMF — défenses |
| `M3:3.08` |  | PRE | F | T0 − 48 h | B | N2 | Fournir les certificats, essais en pression et continuité électrique des flexibles, et le coupleur de rupture / Provide hose certificates, pressure tests, electrical continuity and the breakaway coupling | document `STS_DOC` |  | OCIMF — flexibles |
| `M3:3.09` |  | COM | F | T0 − 72 h | B | N2 | Confirmer les couvertures d'assurance STS des deux navires et du prestataire / Confirm STS insurance cover of both vessels and the provider | document `INSURANCE` | par navire | Exigence d'assurance STS |
| `M3:3.10` |  | NAV + PRE | S | par phase | B | N2 | Compléter les listes de contrôle STS — avant opération, avant accostage, avant transfert, avant séparation / Complete the STS checklists — pre-operation, pre-mooring, pre-transfer, pre-unmooring |  | conjointe, par navire | OCIMF STS Transfer Guide — listes de contrôle |
| `M3:3.11` |  | PRE | C | T0 − 6 h | B | N2 | Confirmer la fenêtre météo, avec marge sur les critères d'accostage / Confirm the weather window, with margin on the mooring criteria |  |  | OCIMF — critères météo |
| `M3:3.12` |  | SUR | C | T0 − 24 h | B | N2 | Confirmer les mesures de sûreté renforcées en zone de mouillage / Confirm reinforced security measures in the anchorage area |  |  | Code ISPS — golfe de Guinée |
| `M3:3.13` |  | PRE + NAV | R | événement | B | N2 | Enregistrer les jalons d'accostage, de transfert et de séparation / Record the mooring, transfer and unmooring milestones | jalons `STS_ALONGSIDE`, `STS_TRANSFER_START`, `STS_TRANSFER_END`, `STS_SEPARATED` |  | PRO-MAR-001 — jalons STS |
| `M3:3.14` |  | INS + NAV | R | T1 + 4 h | B | N2 | Consigner contradictoirement les quantités transférées / Jointly record the quantities transferred | jalons `FINAL_GAUGING` |  | API MPMS |
| `M3:3.15` |  | AGE | C | T1 + 24 h | N | N2 | Confirmer la conservation des enregistrements STS (3 ans) / Confirm retention of STS records (3 years) |  |  |  |

### `M4` — Soutage / Bunkering

Nature : OPERATION · ordre 4 · zones : toutes zones · Peut se greffer sur M1 ou M2.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M4:4.01` |  | CAP + TER | D | T0 − 24 h | B | N2 | Autoriser le soutage et statuer sur sa compatibilité avec l'opération cargaison en cours / Authorize bunkering and rule on its compatibility with the ongoing cargo operation | demande `BUNKERING` (decide) |  | ISGOTT — opérations simultanées |
| `M4:4.02` |  | NAV + COM | F | T0 − 24 h | B | N2 | Confirmer la commande : grade, quantité, teneur en soufre, spécifications, point d'éclair, viscosité / Confirm the order: grade, quantity, sulphur content, specifications, flash point, viscosity | document `BUNKER_DOC` |  | MARPOL Annexe VI |
| `M4:4.03` |  | PRE | F | T0 − 48 h | B | N2 | Fournir l'agrément du soutier et la certification du moyen avitailleur / Provide the bunker supplier licence and the barge certification | document `BUNKER_DOC` |  | Agrément des fournisseurs de soutes |
| `M4:4.04` |  | PRE + NAV | S | T0 − 2 h | B | N2 | Contrôler les scellés et la vérification métrologique du système de comptage / Check the seals and the metrological verification of the metering system |  | conjointe | Métrologie légale |
| `M4:4.05` |  | PRE + NAV | S | avant T0 | B | N2 | Signer conjointement la liste de contrôle sécurité soutage / Jointly sign the bunkering safety checklist |  | conjointe | ISGOTT — liste soutage |
| `M4:4.06` |  | PRE + NAV | R | avant T0 | B | N2 | Effectuer le relevé initial contradictoire / Take the joint opening reading |  |  | Métrologie légale |
| `M4:4.07` |  | PRE + NAV | S | en continu | B | N2 | Prélever, sceller et signer l'échantillon MARPOL au point de réception / Draw, seal and sign the MARPOL sample at the receiving point |  | conjointe | MARPOL Annexe VI règle 18 |
| `M4:4.08` |  | PRE | F | T1 + 2 h | B | N2 | Effectuer le relevé final et émettre la note de livraison de soutes / Take the final reading and issue the bunker delivery note | document `BUNKER_DELIVERY_NOTE` |  | MARPOL Annexe VI — BDN |
| `M4:4.09` |  | NAV | F | T1 + 4 h | N | N2 | Émettre une lettre de protêt en cas d'écart, d'aération ou de non-conformité documentaire / Issue a letter of protest for a shortfall, aeration or documentary non-compliance | document `PROTEST` |  |  |

### `M5` — Déballastage et eaux de ballast / Deballasting and ballast water

Nature : OPERATION · ordre 5 · zones : toutes zones

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M5:5.01` |  | NAV | F | ETA − 72 h | B | N2 | Fournir le certificat BWM, le plan de gestion approuvé et le registre à jour / Provide the BWM certificate, the approved management plan and the up-to-date record book | document `BALLAST_DOC` |  | Convention BWM |
| `M5:5.02` |  | NAV | R | ETA − 24 h | B | N2 | Déclarer l'état du système de traitement — opérationnel ou en dérogation / Declare the treatment system status — operational or under exemption |  |  | Convention BWM |
| `M5:5.03` |  | NAV | R | ETB − 12 h | B | N2 | Déclarer la nature du ballast par citerne — séparé, propre, souillé / Declare the ballast type per tank — segregated, clean, dirty |  |  | MARPOL Annexe I |
| `M5:5.04` |  | CAP + APO | D | ETB − 12 h | B | N2 | Autoriser le rejet dans les eaux du port, ou imposer la réception à terre / Authorize discharge into port waters, or require reception ashore | demande `BALLAST_DISCHARGE` (decide) |  | Convention BWM / MARPOL |
| `M5:5.05` |  | NAV | R | en continu | B | N2 | Confirmer le fonctionnement de l'ODME et la surveillance visuelle au point de rejet / Confirm ODME operation and visual monitoring at the discharge point |  | continue | MARPOL Annexe I — ODME |
| `M5:5.06` |  | NAV | R | fin d'opération | B | N2 | Consigner les volumes, dates, positions et méthode aux registres eaux de ballast et hydrocarbures / Record volumes, dates, positions and method in the ballast water and oil record books |  |  | MARPOL / BWM — registres |
| `M5:5.07` |  | PRE | F | T1 + 4 h | B | N2 | Fournir le bon de prise en charge en cas de remise à une installation agréée / Provide the reception receipt when delivered to an approved facility | document `WASTE_RECEIPT` |  | MARPOL — installations de réception |

### `M6` — Résidus, slops, dégazage et nettoyage / Residues, slops, gas-freeing and cleaning

Nature : OPERATION · ordre 6 · zones : JETTY, ANCHORAGE

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M6:6.01` |  | NAV + AGE | F | ETA − 24 h | B | N2 | Notifier la nature et le volume des déchets à remettre / Notify the type and volume of waste to be delivered | document `WASTE_NOTIFICATION` |  | MARPOL — notification préalable |
| `M6:6.02` |  | PRE | F | ETA − 12 h | B | N2 | Confirmer l'agrément et la capacité disponible de l'installation de réception / Confirm the licence and available capacity of the reception facility | document `CLEANING_DOC` |  | MARPOL — installations de réception |
| `M6:6.03` |  | NAV + AGE | F | T0 − 72 h | B | N2 | Déposer la demande motivée de nettoyage ou de dégazage à quai — méthode, effluents, vapeurs, analyse de risque / File the reasoned request for cleaning or gas-freeing alongside — method, effluents, vapours, risk assessment | document `CLEANING_DOC` |  | ISGOTT — dégazage |
| `M6:6.04` |  | CAP + TER | D | T0 − 48 h | B | N2 | Autoriser le nettoyage ou le dégazage à quai — interdit par défaut / Authorize cleaning or gas-freeing alongside — forbidden by default | demande `GAS_FREEING` (decide) |  | Règlement d'exploitation — interdiction par défaut |
| `M6:6.05` |  | INS | F | avant T0 | B | N2 | Fournir le certificat de dégazage, avec durée de validité explicite / Provide the gas-free certificate, with explicit validity | document `GAS_FREE_CERT` |  | ISGOTT — gas-free |
| `M6:6.06` |  | NAV + TER | S | avant T0 | B | N2 | Émettre le permis d'entrée en espace confiné, nominatif et limité dans le temps / Issue the confined-space entry permit, nominative and time-limited |  | conjointe | ISGOTT / SOLAS — espaces confinés |
| `M6:6.07` |  | PRE | F | T1 + 4 h | B | N2 | Émettre le bordereau de réception des déchets / Issue the waste receipt | document `WASTE_RECEIPT` |  | MARPOL — bordereau |
| `M6:6.08` |  | NAV | R | T1 + 4 h | B | N2 | Reporter la remise aux registres MARPOL / Record the delivery in the MARPOL record books |  |  | MARPOL — registres |
| `M6:6.09` |  | AGE | F | T1 + 24 h | N | N2 | Signaler toute insuffisance de l'installation de réception / Report any inadequacy of the reception facility | document `OTHER` |  |  |

### `M7` — Maintenance, réparations et immobilisation / Maintenance, repairs and immobilisation

Nature : OPERATION · ordre 7 · zones : toutes zones

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M7:7.01` |  | NAV + AGE | F | T0 − 5 j | B | N2 | Déposer la demande de travaux : nature, méthode, phasage, analyse de risque, plan d'urgence / File the works request: nature, method, phasing, risk assessment, emergency plan | document `WORKS_DOC` |  | ISGOTT — travaux |
| `M7:7.02` |  | PRE | F | T0 − 72 h | B | N2 | Fournir la qualification, les certificats et les assurances des intervenants extérieurs / Provide qualifications, certificates and insurance of contractors | document `WORKS_DOC` |  | Exigences d'accès des entreprises extérieures |
| `M7:7.03` |  | COM | F | T0 − 72 h | B | N2 | Fournir l'avis de la société de classification si la classe est concernée / Provide the classification society's opinion if class is affected | document `WORKS_DOC` |  | Règles de la société de classification |
| `M7:7.04` |  | CAP + TER | D | T0 − 48 h | B | N2 | Autoriser les travaux / Authorize the works | demande `HOT_WORK` (decide) |  | Règlement d'exploitation — travaux à quai |
| `M7:7.05` |  | INS | F | avant T0 | B | N2 | Fournir le certificat de dégazage couvrant l'espace concerné et les espaces adjacents / Provide the gas-free certificate covering the space concerned and adjacent spaces | document `GAS_FREE_CERT` |  | ISGOTT — point chaud |
| `M7:7.06` |  | NAV + TER | S | avant T0 | B | N2 | Émettre le permis de travail par point chaud — nominatif, limité dans le temps / Issue the hot-work permit — nominative, time-limited |  | conjointe | ISGOTT — permis de feu |
| `M7:7.07` |  | NAV + AGE | F | T0 − 48 h | B | N2 | Déposer la demande d'immobilisation des machines, avec durée exacte et remise en service garantie / File the engine immobilisation request, with exact duration and guaranteed return to service | document `WORKS_DOC` |  | Règlement d'exploitation — immobilisation |
| `M7:7.08` |  | CAP | D | T0 − 24 h | B | N2 | Autoriser l'immobilisation et fixer les moyens compensatoires — remorqueur, veille renforcée / Authorize the immobilisation and set compensating measures — tug, reinforced watch | demande `IMMOBILIZATION` (decide) |  | Règlement d'exploitation — immobilisation |
| `M7:7.09` |  | TER + PRE | C | T1 + 1 h | B | N2 | Confirmer la veille incendie dédiée, pendant les travaux et 60 minutes après / Confirm the dedicated fire watch, during the works and 60 minutes after |  |  | ISGOTT — veille incendie |
| `M7:7.10` |  | NAV | C | fin d'opération | B | N2 | Confirmer l'essai et la remise en service / Confirm the test and return to service |  |  | ISM — remise en service |
| `M7:7.11` |  | AGE | R | immédiat | B | N2 | Notifier la fin d'immobilisation à la capitainerie / Notify the harbour master of the end of immobilisation |  |  | Règlement d'exploitation |
| `M7:7.12` |  | NAV + COM | F | avant ATD | B | N2 | Mettre à jour les certificats affectés avant l'appareillage / Update the affected certificates before departure | document `CERTIFICATES` |  | SOLAS — validité des certificats |

### `M8` — Escale technique, relève, avitaillement et assistance / Technical call, crew change, provisions and assistance

Nature : OPERATION · ordre 8 · zones : toutes zones

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M8:8.01` |  | AGE | F | ETA − 7 j | B | N2 | Fournir les documents des relevants et des débarquants : passeports, visas, brevets, certificats médicaux / Provide the documents of joining and leaving crew: passports, visas, certificates of competency, medicals | document `CREW_DOC` |  | Réglementation immigration / STCW |
| `M8:8.02` |  | ADM | D | ETA − 48 h | B | N2 | Autoriser la relève et délivrer les laissez-passer / Authorize the crew change and issue the passes | demande `CREW_CHANGE` (decide) |  | Réglementation immigration |
| `M8:8.03` |  | NAV | C | avant ATD | B | N2 | Confirmer le maintien de l'effectif minimal de sécurité et des brevets requis / Confirm minimum safe manning and required certificates are maintained |  |  | SOLAS V/14 — effectif |
| `M8:8.04` |  | AGE | F | ETA − 24 h | N | N2 | Déposer la demande d'accès des personnes et véhicules en zone portuaire / File the access request for persons and vehicles in the port area | document `OTHER` |  |  |
| `M8:8.05` |  | AGE | F | ETA − 24 h | N | N2 | Commander et dédouaner les provisions de bord ; respecter les scellés / Order and clear ship's provisions; respect the seals | document `OTHER` |  |  |
| `M8:8.06` |  | PRE | F | à la livraison | N | N2 | Fournir le contrôle de potabilité de l'eau douce livrée / Provide the potability test of the fresh water delivered | document `OTHER` |  |  |
| `M8:8.07` |  | NAV | F | immédiat | B | N3 | Déclarer tout événement particulier — blessé grave, décès, passager clandestin / Declare any particular event — serious injury, death, stowaway | document `OTHER` |  | SOLAS / FAL — événements à bord |

### `M9` — Accostage à couple (double banking) / Double banking

Nature : MODULE · ordre 9 · zones : JETTY · exige une escale reliée · Ne s'instancie jamais seul : il se greffe sur un modèle d'opération et relie deux escales. Le navire intérieur perd sa liberté d'appareillage : son accord ne peut être présumé.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `M9:9.01` |  | AGE | F | T0 − 72 h | B | N2 | Déposer la demande d'accostage à couple : objet, durée, états de chargement prévisionnels / File the double-banking request: purpose, duration, expected loading conditions | demande `DOUBLE_BANKING` (submit) |  | PRO-MAR-001 §4.9 |
| `M9:9.02` |  | NAV | S | T0 − 72 h | B | N2 | Recueillir l'accord exprès du navire intérieur / Obtain the express consent of the inner vessel |  | conjointe, jamais sans objet | PRO-MAR-001 §4.9 — accord du navire intérieur |
| `M9:9.03` |  | TER | F | T0 − 72 h | B | N2 | Produire l'étude de compatibilité des deux navires / Produce the compatibility study of both vessels | document `DOUBLE_BANKING_DOC` |  | OCIMF |
| `M9:9.04` |  | TER + COM | F | T0 − 72 h | B | N2 | Produire l'analyse d'amarrage du système combiné, aux conditions extrêmes du poste / Produce the mooring analysis of the combined system at the berth's extreme conditions | document `DOUBLE_BANKING_DOC` | jamais sans objet | OCIMF MEG4 — analyse d'amarrage |
| `M9:9.05` |  | PRE | F | T0 − 48 h | B | N2 | Fournir le plan de défenses et les certificats — vérification physique attestée / Provide the fender plan and certificates — physical check attested | document `DOUBLE_BANKING_DOC` |  | OCIMF — défenses |
| `M9:9.06` |  | TER + CAP | S | T0 − 48 h | B | N2 | Valider la matrice des opérations simultanées / Validate the simultaneous operations matrix |  | conjointe, jamais sans objet | ISGOTT — SIMOPS |
| `M9:9.07` |  | NAV | S | T0 − 48 h | B | N2 | Produire le plan d'accès, de coupée et d'évacuation des deux équipages / Produce the access, gangway and evacuation plan for both crews |  | conjointe, par navire | ISGOTT — accès et évacuation |
| `M9:9.08` |  | TER + CAP | F | T0 − 48 h | B | N2 | Produire le plan de déhalage d'urgence : moyens, délais, responsabilités nominatives / Produce the emergency unmooring plan: means, delays, named responsibilities | document `DOUBLE_BANKING_DOC` | jamais sans objet | PRO-MAR-001 §4.9 — déhalage d'urgence |
| `M9:9.09` |  | SUR + NAV | S | T0 − 24 h | B | N2 | Établir les déclarations de sûreté navire/navire et navire/installation / Establish the ship/ship and ship/facility declarations of security |  | conjointe | Code ISPS |
| `M9:9.10` |  | COM | F | T0 − 72 h | B | N2 | Confirmer les couvertures d'assurance des deux navires pour la configuration / Confirm both vessels' insurance cover for the configuration | document `INSURANCE` | par navire | Exigence d'assurance |
| `M9:9.11` |  | CAP | F | T0 − 24 h | B | N2 | Publier les seuils météo spécifiques à la configuration — plus restrictifs qu'en configuration simple / Publish the configuration-specific weather limits — stricter than single berthing | document `BERTH_LIMITS` |  | PRO-MAR-001 §4.9 — seuils météo |
| `M9:9.12` |  | TER + NAV | S | T0 − 6 h | B | N2 | Signer le compte rendu de la réunion préalable à trois / Sign the minutes of the three-party preliminary meeting |  | conjointe | ISGOTT — réunion préalable |
| `M9:9.13` |  | CAP | C | pendant la configuration | N | N2 | Confirmer la coordination des mouvements avec le VTS pendant toute la configuration / Confirm movement coordination with VTS throughout the configuration |  |  |  |
| `M9:9.14` |  | NAV | S | fin d'opération | B | N2 | Compléter la liste de contrôle avant séparation / Complete the pre-separation checklist |  | conjointe, par navire | ISGOTT |
| `M9:9.15` |  | NAV + SVC | C | T1 + 1 h | B | N2 | Revérifier et consigner l'amarrage du navire intérieur après séparation / Re-check and record the inner vessel's mooring after separation |  |  | PRO-MAR-001 §4.9 — après séparation |

### `MA2` — Poste bouée / monobouée (SPM) / Buoy / single point mooring (SPM)

Nature : MODULE · ordre 11 · zones : SPM · Ajouté automatiquement pour une opération offshore sur bouée.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `MA2:A2.01` |  | TER | F | ETB − 48 h | B | N2 | Fournir le rapport d'inspection de la bouée, des flexibles sous-marins et du système d'amarrage / Provide the inspection report of the buoy, subsea hoses and mooring system | document `SPM_DOC` |  | OCIMF — SPM |
| `MA2:A2.02` |  | CAP + TER | C | ETB − 6 h | B | N2 | Confirmer les conditions de houle et de courant dans les limites d'exploitation / Confirm swell and current within operating limits |  |  | Limites d'exploitation SPM |
| `MA2:A2.03` |  | SVC | C | avant T0 | B | N2 | Confirmer la disponibilité des moyens d'assistance et de largage d'urgence / Confirm availability of support craft and emergency release |  |  | OCIMF — SPM |
| `MA2:A2.04` |  | TER + NAV | R | événement | B | N2 | Enregistrer l'amarrage à la bouée et le raccordement du flexible / Record mooring to the buoy and hose connection | jalons `ALL_FAST`, `HOSES_CONNECTED` |  | PRO-MAR-001 — SPM |

### `MA3` — Séjour au mouillage / Stay at anchorage

Nature : MODULE · ordre 12 · zones : toutes zones · Ajouté automatiquement pour la rade et les zones STS ; à cocher pour un navire qui attend en rade avant d'accoster.

| Tâche | Section | Rôle (+ co-rôles) | Nat. | Échéance | Crit. | Conf. | Intitulé FR / EN | Objet lié | Particularités | Base |
|---|---|---|---|---|---|---|---|---|---|---|
| `MA3:A3.01` |  | CAP | D | à l'arrivée | B | N2 | Assigner la position de mouillage / Assign the anchorage position | demande `ANCHORAGE_POSITION` (decide) |  | Règlement de la rade |
| `MA3:A3.02` |  | NAV | C | quotidien | B | N2 | Confirmer la veille radio et la veille anti-intrusion renforcée / Confirm radio watch and reinforced anti-intrusion watch |  |  | Code ISPS — golfe de Guinée |
| `MA3:A3.03` |  | NAV | C | quotidien | B | N2 | Confirmer qu'aucune opération non autorisée n'est conduite au mouillage / Confirm no unauthorized operation is conducted at anchorage |  |  | Règlement de la rade |
| `MA3:A3.04` |  | SUR + NAV | C | à l'arrivée | N | N2 | Confirmer le report de sûreté au centre régional compétent / Confirm the security report to the competent regional centre |  |  |  |

## 4.3 Points d'arrêt (`HOLD_POINTS`)

Chaque transition est refusée tant qu'une des tâches requises est « à faire » ou que l'autorisation issue d'une tâche de décision n'est pas en vigueur à l'heure du fait. Les tâches d'une autre étape de l'escale ne gardent pas la transition. Invariants non paramétrables en plus : voir chapitre 5.

| Transition | Tâches requises |
|---|---|
| `DECLARE` | `M0:02`, `M0:03`, `M0:05` |
| `GREEN_LIGHT` | `M0:06`, `M0:07` |
| `BERTH_ASSIGN` | `M0:06`, `M0:07`, `M0:09` |
| `MOVEMENT_AUTH` | `M0:21`, `M0:22`, `M5:5.04` |
| `PILOT_BOARDING` | `M0:25` |
| `BERTHING` | `M0:25`, `M3:3.03`, `MA2:A2.02` |
| `START_TRANSFER` | `M0:27`, `M0:28`, `M0:29`, `M0:31`, `M1:1.04`, `M1:1.05`, `M1:1.06`, `M1:1.07`, `M2:2.04`, `M2:2.05`, `M2:2.06`, `M2:2.07`, `M2:2.08`, `M2:2.09`, `M3:3.01`, `M3:3.02`, `M3:3.03`, `M3:3.04`, `M3:3.05`, `M3:3.06`, `M3:3.07`, `M3:3.08`, `M3:3.09`, `M3:3.10`, `M3:3.11`, `M4:4.01`, `M4:4.02`, `M4:4.03`, `M4:4.04`, `M4:4.05`, `M4:4.06` |
| `DOUBLE_BANKING` | `M9:9.02`, `M9:9.04`, `M9:9.06`, `M9:9.08` |
| `HOT_WORK` | `M7:7.04`, `M7:7.05`, `M7:7.06` |
| `BL_ISSUE` | `M2:2.16` |
| `DEPARTURE_CLEARANCE` | `M0:32`, `M0:33`, `M7:7.12` |
| `PILOT_BOARDING_DEP` | `M0:34` |
| `DEPARTURE` | `M0:34` |
| `CLOSE` | `M0:36` |

## 4.4 Types de jalons (`MILESTONES`)

| N° | Code | Émetteur | Contresignataires | Contestataires | Libellé FR / EN | Effets et options |
|---|---|---|---|---|---|---|
| 1 | `ARRIVAL` | NAV | CAP | AGE, COM | Arrivée à la limite du port / Arrival at the port limit | sets_anchor=ATA ; sets_status=APPROACHING ; completes_tasks=['M0:20'] ; ais_corroboration=True |
| 2 | `ANCHORED` | NAV | CAP | COM | Mouillage / Anchored | repeatable=True |
| 2 | `ANCHOR_AWEIGH` | NAV | CAP | COM | Appareillage du mouillage / Anchor aweigh | repeatable=True |
| 3 | `NOR_TENDERED` | AGE | TER, COM | COM | NOR remise / NOR tendered | sets_anchor=NOR ; completes_tasks=['M0:23'] |
| 4 | `FREE_PRATIQUE` | ADM | — | — | Libre pratique accordée / Free pratique granted |  |
| 5 | `GREEN_LIGHT` | CAP | — | AGE | Feu vert / escale acceptée / Green light / call accepted |  |
| 6 | `BERTH_ASSIGNED` | APO | — | AGE, TER | Poste attribué / Berth assigned |  |
| 7 | `PILOT_ON_BOARD_ARR` | SVC | NAV | AGE | Pilote à bord (arrivée) / Pilot on board (arrival) | hold_point=PILOT_BOARDING ; completes_tasks=['M0:26'] |
| 8 | `FIRST_LINE` | SVC | TER | NAV | Première amarre à terre / First line ashore | hold_point=BERTHING ; completes_tasks=['M0:26'] |
| 9 | `ALL_FAST` | SVC | NAV, TER | AGE, COM | Amarrage terminé (all fast) / All fast | sets_anchor=ATB ; sets_status=AT_BERTH ; hold_point=BERTHING ; completes_tasks=['M0:26', 'MA2:A2.04'] |
| 10 | `GANGWAY` | NAV | TER | — | Passerelle en place / Gangway in place | completes_tasks=['M0:26'] |
| 11 | `SSSCL_SIGNED` | SYSTEM | — | — | Liste de contrôle navire/terre signée / Ship/shore safety checklist signed |  |
| 12 | `PRE_TRANSFER_MEETING` | SYSTEM | — | — | Réunion pré-transfert tenue / Pre-transfer meeting held |  |
| 13 | `ESD_TEST` | TER | NAV | — | Essai d'arrêt d'urgence concluant / Emergency shutdown test successful | completes_tasks=['M0:29'] |
| 14 | `INITIAL_GAUGING` | INS | NAV, TER | COM | Jaugeage initial terminé / Initial gauging completed | completes_tasks=['M1:1.05', 'M2:2.05'] |
| 15 | `HOSES_CONNECTED` | TER | NAV | — | Bras / flexibles raccordés / Arms / hoses connected | completes_tasks=['M1:1.09', 'MA2:A2.04'] |
| 16 | `TRANSFER_START` | TER | NAV | AGE, COM | Début du transfert / Start of transfer | sets_anchor=T0 ; sets_status=IN_OPERATION ; hold_point=START_TRANSFER ; completes_tasks=['M1:1.10', 'M2:2.10'] |
| 17 | `FULL_RATE` | TER | NAV | COM | Débit de régime atteint / Full rate reached | completes_tasks=['M1:1.10', 'M2:2.10'] |
| 18 | `INTERRUPTION_START` | ORIGIN | — | * | Interruption — début / Interruption — start | repeatable=True ; requires_cause=True |
| 18 | `INTERRUPTION_END` | ORIGIN | — | * | Interruption — fin / Interruption — end | repeatable=True |
| 19 | `TOPPING_OFF` | NAV | TER | — | Début topping-off / assèchement / Topping-off / stripping started | completes_tasks=['M1:1.13'] |
| 20 | `TRANSFER_END` | TER | NAV | AGE, COM | Fin du transfert / End of transfer | sets_anchor=T1 ; sets_status=OPS_COMPLETE ; completes_tasks=['M1:1.13'] |
| 21 | `LINES_DRAINED` | TER | NAV | — | Lignes vidangées / Lines drained | completes_tasks=['M1:1.13'] |
| 22 | `HOSES_DISCONNECTED` | TER | NAV | — | Bras / flexibles déconnectés / Arms / hoses disconnected |  |
| 23 | `FINAL_GAUGING` | INS | NAV, TER | COM | Jaugeage final terminé / Final gauging completed | completes_tasks=['M1:1.15', 'M2:2.14', 'M3:3.14'] |
| 24 | `WASTE_DELIVERED` | PRE | NAV | AGE | Déchets remis / bordereau émis / Waste delivered / receipt issued | completes_tasks=['M0:32'] |
| 25 | `DOCUMENTS_SIGNED` | AGE | NAV | COM | Documents signés / Documents signed |  |
| 26 | `DEPARTURE_CLEARANCE` | CAP | — | AGE | Congé de départ délivré / Departure clearance issued |  |
| 27 | `PILOT_ON_BOARD_DEP` | SVC | NAV | — | Pilote à bord (départ) / Pilot on board (departure) | hold_point=PILOT_BOARDING_DEP ; completes_tasks=['M0:35'] |
| 28 | `LAST_LINE` | SVC | NAV | AGE | Dernière amarre larguée / Last line released | hold_point=DEPARTURE ; completes_tasks=['M0:35'] |
| 29 | `DEPARTED` | NAV | CAP | — | Navire appareillé / Vessel departed | sets_anchor=ATD ; sets_status=DEPARTED ; hold_point=DEPARTURE ; completes_tasks=['M0:35', 'M0:35b'] ; ais_corroboration=True |
| 29 | `SHIFT_START` | SVC | NAV, TER | AGE | Déhalage — départ du poste ou de la zone / Shifting — leaving the berth or area | sets_status=SHIFTING ; hold_point=PILOT_BOARDING ; repeatable=True |
| 30 | `STS_ALONGSIDE` | PRE | NAV | AGE, COM | STS — navires à couple / STS — vessels alongside | sets_anchor=ATB ; sets_status=AT_BERTH ; hold_point=BERTHING ; completes_tasks=['M3:3.13'] |
| 31 | `STS_TRANSFER_START` | PRE | NAV | AGE, COM | STS — début du transfert / STS — start of transfer | sets_anchor=T0 ; sets_status=IN_OPERATION ; hold_point=START_TRANSFER ; completes_tasks=['M3:3.13'] |
| 32 | `STS_TRANSFER_END` | PRE | NAV | AGE, COM | STS — fin du transfert / STS — end of transfer | sets_anchor=T1 ; sets_status=OPS_COMPLETE ; completes_tasks=['M3:3.13'] |
| 33 | `STS_SEPARATED` | PRE | NAV | — | STS — séparation des navires / STS — vessels separated | completes_tasks=['M3:3.13'] |

## 4.5 Types de demande (`REQUEST_TYPES`) et leurs formulaires


### `VESSEL_ACCEPTANCE` — Acceptation de navire (vetting) / Vessel acceptance (vetting)

demandeurs : TER · décideurs : CAP, APO · exécutant : — · confidentialité : N2 · refusal_confidentiality : N3 · validity_hours : 720 · processing_minutes : 2880 · is_vetting : True · submit_completes : ['M0:06'] · decision_completes : ['M0:07'] · expected_documents : ['VETTING_REPORT', 'Q88']

Le dépôt adresse au port, par le canal officiel, le résultat de son vetting. Le port n'attribue pas de poste à un navire non accepté. / The depot sends the port, through the official channel, the result of its vetting. No berth for a vessel not accepted.

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `product` | text | oui | Produit / Product |  |
| `quantity` | number | non | Quantité / Quantity |  |
| `requested_berth` | text | non | Poste sollicité / Requested berth |  |
| `inspection` | textarea | oui | Rapport SIRE 2.0 / CDI — date et observations en cours / SIRE 2.0 / CDI report — date and open observations |  |
| `psc_history` | textarea | non | Historique PSC, détentions, incidents / PSC history, detentions, incidents |  |
| `last_cargoes` | textarea | oui | Trois dernières cargaisons / Last three cargoes |  |
| `vetting_result` | textarea | oui | Résultat du vetting interne et conditions proposées / Internal vetting result and proposed conditions |  |

### `GREEN_LIGHT` — Feu vert / Green light

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 168 · processing_minutes : 720 · hold_point : GREEN_LIGHT · decision_completes : ['M0:09'] · approval_milestone : GREEN_LIGHT · approval_status : ACCEPTED · refusal_status : REJECTED

Sans champ de formulaire.

### `BERTH` — Attribution de poste et de créneau (autorisation d'accostage) / Berth and slot assignment (berthing authorization)

demandeurs : AGE · décideurs : APO · exécutant : — · confidentialité : N1 · validity_hours : 72 · processing_minutes : 720 · hold_point : BERTH_ASSIGN · assigns_berth : True · submit_completes : ['M0:10'] · decision_completes : ['M0:11'] · approval_milestone : BERTH_ASSIGNED · approval_status : PLANNED

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `window_from` | datetime | oui | Créneau souhaité — début / Requested window — from |  |
| `window_to` | datetime | non | Créneau souhaité — fin / Requested window — to |  |
| `arrival_draft` | number | oui | Tirant d'eau à l'arrivée (m) / Arrival draft (m) |  |
| `notes` | textarea | non | Observations / Remarks |  |

### `MOVEMENT` — Autorisation de mouvement / Movement authorization

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 12 · processing_minutes : 120 · hold_point : MOVEMENT_AUTH · decision_completes : ['M0:25']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `movement` | select | oui | Mouvement / Movement | `ARRIVAL` Entrée / accostage / Arrival / berthing; `SHIFT` Déhalage / Shifting; `DEPARTURE` Sortie / Departure |
| `requested_time` | datetime | oui | Heure souhaitée / Requested time |  |

### `MARINE_SERVICES` — Demande de pilote, remorqueurs et lamaneurs / Pilot, tugs and mooring request

demandeurs : AGE · décideurs : — (commande de service) · exécutant : SVC · confidentialité : N2 · validity_hours : 24 · processing_minutes : 360 · decision_completes : ['M0:18']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `movement` | select | oui | Mouvement / Movement | `ARRIVAL` Entrée / accostage / Arrival / berthing; `SHIFT` Déhalage / Shifting; `DEPARTURE` Sortie / Departure |
| `requested_time` | datetime | oui | Heure de prise du pilote / Pilot boarding time |  |
| `tugs` | integer | non | Nombre de remorqueurs / Number of tugs |  |
| `mooring_gang` | boolean | non | Lamaneurs / Mooring gang |  |
| `notes` | textarea | non | Observations / Remarks |  |

### `FREE_PRATIQUE` — Libre pratique / Free pratique

demandeurs : AGE · décideurs : ADM · exécutant : — · confidentialité : N1 · validity_hours : 720 · processing_minutes : 120 · decision_completes : ['M0:21'] · approval_milestone : FREE_PRATIQUE · expected_documents : ['MDH']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `crew` | integer | oui | Équipage à bord / Crew on board |  |
| `health_events` | textarea | non | Événements sanitaires à bord / Health events on board |  |

### `CUSTOMS_IMMIGRATION` — Formalités douanières et d'immigration (arrivée) / Customs and immigration formalities (arrival)

demandeurs : AGE · décideurs : ADM · exécutant : — · confidentialité : N2 · validity_hours : 720 · processing_minutes : 240 · decision_completes : ['M0:22']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `crew_list` | boolean | oui | Liste d'équipage déposée au guichet unique / Crew list filed with the single window |  |
| `notes` | textarea | non | Observations / Remarks |  |

### `WASTE_COLLECTION` — Demande d'enlèvement des ordures et déchets / Garbage and waste collection request

demandeurs : AGE · décideurs : — (commande de service) · exécutant : PRE · confidentialité : N2 · validity_hours : 72 · processing_minutes : 720 · submit_completes : ['M0:16']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `categories` | text | oui | Catégories MARPOL (I, IV, V, VI) / MARPOL categories (I, IV, V, VI) |  |
| `volume_m3` | number | oui | Volume estimé (m³) / Estimated volume (m³) |  |
| `requested_time` | datetime | non | Heure souhaitée / Requested time |  |

### `OUTWARD_FORMALITIES` — Formalités de sortie / Outward formalities

demandeurs : AGE · décideurs : ADM · exécutant : — · confidentialité : N2 · validity_hours : 48 · processing_minutes : 240 · decision_completes : ['M0:33']

Sans champ de formulaire.

### `DEPARTURE_CLEARANCE` — Congé de départ / Departure clearance

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 24 · processing_minutes : 120 · hold_point : DEPARTURE_CLEARANCE · decision_completes : ['M0:34'] · approval_milestone : DEPARTURE_CLEARANCE

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `requested_time` | datetime | oui | Heure d'appareillage prévue / Planned departure time |  |

### `ANCHORAGE_POSITION` — Position de mouillage / Anchorage position

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 360 · processing_minutes : 120 · decision_completes : ['MA3:A3.01']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `eta_anchorage` | datetime | oui | Arrivée prévue en rade / Expected arrival at anchorage |  |

### `STS_ZONE` — Autorisation de zone et de fenêtre STS / STS area and window authorization

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 72 · processing_minutes : 1440 · decision_completes : ['M3:3.03']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `partner_vessel` | text | oui | Navire partenaire / Partner vessel |  |
| `window_from` | datetime | oui | Fenêtre — début / Window — from |  |
| `window_to` | datetime | oui | Fenêtre — fin / Window — to |  |
| `poac` | text | oui | POAC désigné / Appointed POAC |  |

### `BUNKERING` — Autorisation de soutage / Bunkering authorization

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N2 · validity_hours : 24 · processing_minutes : 720 · decision_completes : ['M4:4.01']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `grade` | text | oui | Grade / Grade |  |
| `quantity_mt` | number | oui | Quantité (t) / Quantity (t) |  |
| `supplier` | text | oui | Soutier / Supplier |  |
| `terminal_agreement` | boolean | non | Accord du terminal (SIMOPS) / Terminal agreement (SIMOPS) |  |

### `BALLAST_DISCHARGE` — Rejet d'eaux de ballast / Ballast water discharge

demandeurs : AGE · décideurs : CAP, APO · exécutant : — · confidentialité : N2 · validity_hours : 48 · processing_minutes : 720 · decision_completes : ['M5:5.04']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `volume_m3` | number | oui | Volume (m³) / Volume (m³) |  |
| `method` | text | oui | Méthode de conformité / Compliance method |  |

### `GAS_FREEING` — Nettoyage / dégazage à quai / Cleaning / gas-freeing alongside

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N2 · validity_hours : 24 · processing_minutes : 1440 · decision_completes : ['M6:6.04']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `method` | textarea | oui | Méthode, effluents, vapeurs / Method, effluents, vapours |  |

### `HOT_WORK` — Autorisation de travaux (point chaud) / Works authorization (hot work)

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N2 · validity_hours : 24 · processing_minutes : 1440 · hold_point : HOT_WORK · decision_completes : ['M7:7.04']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `works` | textarea | oui | Nature et méthode des travaux / Nature and method of works |  |

### `IMMOBILIZATION` — Immobilisation des machines / Engine immobilisation

demandeurs : AGE · décideurs : CAP · exécutant : — · confidentialité : N2 · validity_hours : 72 · processing_minutes : 720 · decision_completes : ['M7:7.08']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `duration_h` | number | oui | Durée (h) / Duration (h) |  |
| `return_to_service` | datetime | oui | Remise en service garantie / Guaranteed return to service |  |

### `CREW_CHANGE` — Relève d'équipage et laissez-passer / Crew change and passes

demandeurs : AGE · décideurs : ADM · exécutant : — · confidentialité : N2 · validity_hours : 72 · processing_minutes : 1440 · decision_completes : ['M8:8.02']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `joining` | integer | oui | Relevants / Joining crew |  |
| `leaving` | integer | oui | Débarquants / Leaving crew |  |

### `DOUBLE_BANKING` — Accostage à couple / Double banking

demandeurs : AGE, TER · décideurs : CAP · exécutant : — · confidentialité : N1 · validity_hours : 72 · processing_minutes : 1440 · hold_point : DOUBLE_BANKING · submit_completes : ['M9:9.01']

| Clé | Type | Obligatoire | Libellé FR / EN | Options |
|---|---|---|---|---|
| `purpose` | textarea | oui | Objet / Purpose |  |
| `duration_h` | number | oui | Durée (h) / Duration (h) |  |
| `inner_vessel` | text | oui | Navire intérieur / Inner vessel |  |

## 4.6 Types de document (`DOCUMENT_TYPES`)

| Code | Libellé FR / EN | Émetteurs | Conf. | Signataires | Lecteurs (N2) | Généré | B/L | Conservation (ans) |
|---|---|---|---|---|---|---|---|---|
| `Q88` | Q88 / VPQ, plans, particularités du collecteur / Q88 / VPQ, plans, manifold particulars | AGE, NAV | N2 | — | TER, CAP, APO, SVC, INS |  |  | 10 |
| `CERTIFICATES` | Certificats statutaires et d'assurance / Statutory and insurance certificates | NAV, AGE | N2 | — | CAP, APO, ADM, TER |  |  | 10 |
| `CP_RECAP` | Recap / extrait de charte-partie et clauses d'escale / Recap / charter-party extract and call clauses | COM | N3 | — | AGE |  |  | 10 |
| `VETTING_REPORT` | Rapport SIRE / CDI et résultat du vetting / SIRE / CDI report and vetting result | TER | N2 | — | CAP, APO |  |  | 10 |
| `FAL_PROOF` | Preuve de dépôt FAL au guichet unique / Proof of FAL filing with the single window | AGE | N2 | — | ADM, CAP |  |  | 10 |
| `MDH` | Déclaration maritime de santé / Maritime declaration of health | NAV | N2 | — | ADM |  |  | 10 |
| `BALLAST_NOTIFICATION` | Notification eaux de ballast / Ballast water notification | NAV | N2 | — | CAP, APO |  |  | 10 |
| `BERTH_LIMITS` | Conditions limites d'exploitation du poste / Berth operating limits | CAP, TER | N1 | — | — |  |  | 10 |
| `NOR` | Notice de disponibilité (NOR) / Notice of readiness (NOR) | AGE, NAV | N1 | — | — |  |  | 10 |
| `SSSCL` | Liste de contrôle navire/terre (ISGOTT) / Ship/shore safety checklist (ISGOTT) | TER, NAV | N2 | — | INS |  |  | 10 |
| `PRE_TRANSFER_MINUTES` | Compte rendu de réunion pré-transfert / Pre-transfer meeting minutes | TER, NAV | N2 | — | — |  |  | 10 |
| `SECURITY_DECLARATION` | Déclaration de sûreté / Declaration of security | SUR, NAV | N2 | — | — |  |  | 10 |
| `WASTE_RECEIPT` | Bordereau de réception des déchets / Waste delivery receipt | PRE | N2 | — | APO, NAV |  |  | 10 |
| `SOF` | Rapport des faits / Statement of facts | AGE | N1 | NAV, TER | — | oui |  | 10 |
| `TIME_SHEET` | Time sheet / Time sheet | AGE | N2 | — | COM, TER | oui |  | 10 |
| `PORT_ACCOUNT` | Compte d'escale final / Final port-call account | AGE | N3 | — | COM |  |  | 10 |
| `IMPORT_AUTH` | Autorisation d'importation / Import authorization | AGE | N2 | — | ADM, TER |  |  | 10 |
| `EXPORT_AUTH` | Autorisation d'exportation / Export authorization | AGE | N2 | — | ADM, TER |  |  | 10 |
| `DISCHARGE_PLAN` | Plan de déchargement et de ballastage / Discharge and ballast plan | NAV | N2 | — | TER, INS |  |  | 10 |
| `LOADING_PLAN` | Plan de chargement / Loading plan | NAV | N2 | — | TER, INS |  |  | 10 |
| `LAST_CARGOES` | Trois dernières cargaisons / Last three cargoes | NAV | N2 | — | TER, INS |  |  | 10 |
| `EMPTY_TANKS_CERT` | Certificat de citernes vides / constat de ROB / Empty tanks certificate / ROB statement | INS | N2 | — | NAV, TER |  |  | 10 |
| `CLEANLINESS_CERT` | Certificat de propreté des citernes / Tank cleanliness certificate | INS | N2 | NAV, TER | — |  |  | 10 |
| `QQ_CERT` | Certificat de quantité et de qualité / Quantity and quality certificate | INS | N2 | — | NAV, TER |  |  | 10 |
| `QUALITY_CERT` | Certificat de qualité à terre / Shore quality certificate | INS | N2 | — | NAV, TER |  |  | 10 |
| `TERMINAL_RECEIPT` | Bon de réception du terminal / Terminal receipt | TER | N2 | — | INS |  |  | 10 |
| `CARGO_DECLARATION` | Déclaration douanière de cargaison / Customs cargo declaration | AGE | N2 | — | ADM |  |  | 10 |
| `PROTEST` | Lettre de protêt / Letter of protest | AGE, NAV, TER, INS, PRE | N2 | — | NAV, TER, INS |  |  | 10 |
| `DOC_INSTRUCTIONS` | Instruction documentaire écrite du mandant / Principal's written documentary instructions | COM | N3 | — | AGE |  |  | 10 |
| `BILL_OF_LADING` | Connaissement / Bill of lading | AGE | N2 | — | NAV, TER |  | oui | 10 |
| `EXPORT_MANIFEST` | Manifeste et déclaration d'exportation / Manifest and export declaration | AGE | N2 | — | ADM |  |  | 10 |
| `STS_NOTIFICATION` | Notification STS à l'État côtier / STS notification to the coastal State | AGE | N2 | — | SUR |  |  | 10 |
| `STS_PLAN` | Plan d'opérations STS / STS operations plan | NAV | N2 | — | PRE |  |  | 10 |
| `STS_DOC` | Dossier STS (POAC, compatibilité, défenses, flexibles) / STS file (POAC, compatibility, fenders, hoses) | AGE, PRE, NAV | N2 | — | NAV, PRE |  |  | 10 |
| `INSURANCE` | Attestation d'assurance / Insurance certificate | COM, AGE | N2 | — | NAV, PRE |  |  | 10 |
| `BUNKER_DOC` | Dossier de soutage / Bunkering file | NAV, PRE | N2 | — | NAV, PRE |  |  | 10 |
| `BUNKER_DELIVERY_NOTE` | Note de livraison de soutes / Bunker delivery note | PRE | N3 | — | NAV |  |  | 10 |
| `BALLAST_DOC` | Certificat BWM et plan de gestion / BWM certificate and management plan | NAV | N2 | — | — |  |  | 10 |
| `WASTE_NOTIFICATION` | Notification des déchets à remettre / Notification of waste to deliver | NAV, AGE | N2 | — | PRE, APO |  |  | 10 |
| `CLEANING_DOC` | Dossier nettoyage / dégazage / Cleaning / gas-freeing file | NAV, AGE, PRE | N2 | — | TER |  |  | 10 |
| `GAS_FREE_CERT` | Certificat de dégazage / Gas-free certificate | INS | N2 | — | NAV, TER |  |  | 10 |
| `WORKS_DOC` | Dossier de travaux / Works file | NAV, AGE, PRE, COM | N2 | — | TER |  |  | 10 |
| `CREW_DOC` | Documents d'équipage / Crew documents | AGE | N2 | — | ADM |  |  | 10 |
| `DOUBLE_BANKING_DOC` | Dossier d'accostage à couple / Double-banking file | TER, PRE, COM | N2 | — | NAV |  |  | 10 |
| `SPM_DOC` | Rapport d'inspection SPM / SPM inspection report | TER | N2 | — | SVC |  |  | 10 |
| `PHOTO` | Photo terrain / Field photo | AGE, NAV, TER, INS, SVC, PRE, CAP, APO, ADM, SUR, COM | N2 | — | — |  |  | 10 |
| `ULLAGE_REPORT` | Rapport de jaugeage (ullage / sondage, API MPMS ch. 17) / Ullage / sounding report (API MPMS ch. 17) | INS, NAV, TER | N2 | — | NAV, TER, INS, COM |  |  | 10 |
| `HOSE_RECORD` | Relevé de connexion et de déconnexion des flexibles / bras / Hose / loading arm connection and disconnection record | TER, NAV | N2 | — | INS |  |  | 10 |
| `PILOT_CARD` | Fiche pilote et échange d'informations capitaine-pilote (IMO A.960) / Pilot card and master-pilot exchange (IMO A.960) | NAV, SVC | N2 | — | CAP |  |  | 10 |
| `FAL_FORMS` | Formulaires FAL de l'OMI (déclaration générale, équipage, provisions, effets, marchandises dangereuses) / IMO FAL forms (general declaration, crew, stores, effects, dangerous goods) | AGE, NAV | N2 | — | ADM, CAP, SUR |  |  | 10 |
| `STS_CHECKLISTS` | Listes de contrôle STS (OCIMF Ship to Ship Transfer Guide) / STS checklists (OCIMF Ship to Ship Transfer Guide) | PRE, NAV | N2 | — | CAP, AGE |  |  | 10 |
| `AUTHORIZATION` | Acte d'autorisation (décision sur une demande, code de vérification) / Authorization act (decision on a request, verification code) | CAP, APO, ADM | N1 | — | — | oui |  | 10 |
| `ARRIVAL_NOTICE` | Avis d'arrivée (préavis 72 / 48 / 24 h) / Arrival notice (72 / 48 / 24 h pre-arrival notification) | AGE | N1 | — | — |  |  | 10 |
| `SANCTIONS_CHECK` | Attestation de contrôle des listes de sanctions / Sanctions screening attestation | AGE | N2 | — | CAP, APO, COM |  |  | 10 |
| `ACCESS_LIST` | Liste d'accès en zone portuaire (personnes, véhicules) / Port area access list (persons, vehicles) | AGE, SUR | N2 | — | SUR, TER, CAP |  |  | 10 |
| `PRE_ARRIVAL_SECURITY` | Information de sûreté avant l'arrivée (ISPS) / Pre-arrival security information (ISPS) | NAV, AGE | N2 | — | SUR, CAP |  |  | 10 |
| `INERT_GAS_DECLARATION` | Déclaration d'inertage et de teneur en oxygène / Inert gas and oxygen content declaration | NAV | N2 | — | TER, INS, CAP |  |  | 10 |
| `HOT_WORK_PERMIT` | Permis de travail par point chaud / Hot work permit | NAV | N2 | — | TER, CAP, PRE |  |  | 10 |
| `ENCLOSED_SPACE_PERMIT` | Permis d'entrée en espace clos / Enclosed space entry permit | NAV | N2 | — | TER, CAP, PRE |  |  | 10 |
| `INCIDENT_REPORT` | Déclaration d'événement (blessé, décès, passager clandestin, pollution, avarie) / Declaration of an event (injury, death, stowaway, pollution, damage) | NAV, AGE, TER, SVC, INS, PRE | N2 | — | CAP, APO, ADM, SUR |  |  | 10 |
| `MOVEMENT_ORDER` | Ordre de mouvement — confirmation des services nautiques / Movement order — marine services confirmation | SVC | N1 | — | — |  |  | 10 |
| `SERVICE_NOTE` | Bon de prestation de service / Service delivery note | SVC, PRE | N2 | — | AGE, NAV, COM |  |  | 10 |
| `BERTH_READINESS` | Attestation de mise en sécurité du poste / Berth readiness and safety attestation | TER | N2 | — | CAP, NAV, SVC |  |  | 10 |
| `SHORE_TANK_REPORT` | Relevé des bacs et compteurs à terre / Shore tank and meter measurement report | TER | N2 | — | INS, NAV, COM |  |  | 10 |
| `SAMPLING_RECORD` | Procès-verbal d'échantillonnage / Sampling record | INS | N2 | — | NAV, TER, COM |  |  | 10 |
| `BUNKER_CHECKLIST` | Liste de contrôle sécurité soutage / Bunkering safety checklist | PRE, NAV | N2 | — | CAP, AGE |  |  | 10 |
| `LOI` | Lettre de garantie (livraison sans connaissement original) / Letter of indemnity (delivery without original bill of lading) | COM | N3 | — | AGE |  |  | 10 |
| `OTHER` | Autre document / Other document | AGE, NAV, TER, INS, ADM, SUR, PRE, CAP, APO, SVC, COM, DIR | N2 | — | — |  |  | 10 |

## 4.7 Causes d'interruption (`CAUSES`, liste fermée)

| Code | Imputation | Libellé FR / EN |
|---|---|---|
| `SHORE_TANK_SWITCH` | SHORE | Changement de bac à terre / Shore tank switch |
| `SHORE_ULLAGE` | SHORE | Creux insuffisant à terre / Insufficient shore ullage |
| `SHORE_PUMP` | SHORE | Panne de pompe ou de ligne à terre / Shore pump or line failure |
| `SHORE_POWER` | SHORE | Coupure électrique terminal / Terminal power failure |
| `SHORE_LAB` | SHORE | Attente d'analyse laboratoire terre / Waiting for shore laboratory |
| `SHIP_PUMP` | SHIP | Panne de pompe ou d'équipement bord / Ship pump or equipment failure |
| `SHIP_BALLAST` | SHIP | Ballastage / déballastage du navire / Ship ballasting / deballasting |
| `SHIP_INERT_GAS` | SHIP | Gaz inerte ou O₂ hors limites / Inert gas or O₂ out of limits |
| `SHIP_STRIPPING` | SHIP | Assèchement / changement de citerne bord / Stripping / ship tank change |
| `SHIP_REQUEST` | SHIP | Arrêt demandé par le bord / Stop requested by the ship |
| `SURVEYOR` | THIRD | Attente surveyor / jaugeage intermédiaire / Waiting for surveyor / intermediate gauging |
| `CUSTOMS` | THIRD | Blocage douanier / Customs hold |
| `AUTHORITY_ORDER` | THIRD | Ordre de la capitainerie / Harbour master's order |
| `SECURITY_ALERT` | THIRD | Alerte de sûreté / Security alert |
| `WEATHER_LIMITS` | WEATHER | Dépassement des limites météo (vent, houle, courant) / Weather limits exceeded (wind, swell, current) |
| `LIGHTNING` | WEATHER | Orage / risque de foudre / Thunderstorm / lightning risk |
| `OTHER` | — (à préciser) | Autre — motif obligatoire / Other — reason mandatory |

## 4.8 Ports pilotes et postes (`PORTS`)


### `SLFNA` — Freetown (SL, Africa/Freetown, langue en)

Cadre de la carte AIS : lat 8.350000 → 8.580000, lon -13.550000 → -13.120000 (indicatif, à valider par la capitainerie).

| Code | Zone | Nom FR / EN | Latitude | Longitude | Rayon (m) |
|---|---|---|---|---|---|
| `KISSY-JETTY` | JETTY | Appontement pétrolier de Kissy / Kissy oil jetty | 8.480000 | -13.195000 | — |
| `FNA-ANCH` | ANCHORAGE | Rade de Freetown — mouillage pétroliers / Freetown roads — tanker anchorage | 8.500000 | -13.260000 | 1500 |
| `FNA-STS` | STS_AREA | Zone STS au large de Freetown / Freetown offshore STS area | 8.400000 | -13.450000 | 2500 |

### `TGLFW` — Lomé (TG, Africa/Lome, langue fr)

Cadre de la carte AIS : lat 5.950000 → 6.160000, lon 1.180000 → 1.420000 (indicatif, à valider par la capitainerie).

| Code | Zone | Nom FR / EN | Latitude | Longitude | Rayon (m) |
|---|---|---|---|---|---|
| `LFW-APP` | JETTY | Appontement pétrolier de Lomé / Lomé oil jetty | 6.128000 | 1.287000 | — |
| `LFW-RADE` | ANCHORAGE | Rade de Lomé — mouillage / Lomé roads — anchorage | 6.080000 | 1.300000 | 1500 |
| `LFW-STS` | STS_AREA | Zone STS au large de Lomé / Lomé offshore STS area | 6.000000 | 1.350000 | 2500 |
