# 15. Glossaire

> Chapitre **rédigé** (FLX-SPEC-003, onglet principal, section 12), tenu à la main à chaque livraison ; sa source de vérité est le code livré : quand un chapitre et le code divergent, le code fait foi et l'écart est consigné dans `docs/ARCHITECTURE.md` §11.

## 15.1 Glossaire et onglets de référence

| Terme | Définition |
| --- | --- |
| Acteur | une personne ou un lien sans compte, avec les rôles qu'il exerce sur une escale, son organisation et ses drapeaux (`strong_auth`, `is_link`, `is_master`) ; toute fonction de service reçoit un acteur |
| Ancre | heure de référence d'une échéance : NOM, ETA, ETB, ATB, T0, T1, ATD, NOR ; réelle si elle existe, estimée sinon |
| Autorisation | objet distinct produit par une approbation : validité obligatoire, sceau, code de vérification public ; en vigueur à une heure donnée ou non |
| Contresignature | accord d'une partie sur un jalon émis par une autre ; **tacite** quand le silence a duré plus que le délai du port (jamais un accord) |
| Contestation | désaccord d'une partie sur un jalon, une tâche, une mesure, un document, une demande ; répondue puis close avec ou sans accord ; jamais rejetée |
| Côté terre | l'organisation qui parle au nom de la terre (terminal à quai, prestataire en mer) : désignée ou seule de son rôle |
| Déhalage | départ d'une étape vers la suivante (`SHIFT_START`), statut `SHIFTING` |
| Étape | séjour de l'escale dans une zone (rade, STS, bouée, quai) avec poste, opérations, fenêtre, accostage et départ propres |
| Gabarit | modèle de tâches versionné (socle M0, opérations M1–M8, modules M9, MA1–MA3) ; seule une version publiée s'instancie |
| Jalon | fait horodaté à émetteur unique (type, heure déclarée, heure d'enregistrement, source, cause, contresignatures) |
| Lien d'accès | accès sans compte à une escale (capitaine : jusqu'au départ ; partie : jusqu'à la clôture), nominatif, jamais décideur |
| Point d'arrêt | transition refusée tant que ses tâches requises ne sont pas faites et ses invariants satisfaits |
| Rectification | nouveau jalon lié à celui qu'il corrige, motivé, par l'organisation émettrice ; l'original reste visible |
| Saisie différée | jalon dont l'heure déclarée précède l'enregistrement de plus de 30 min (hors ligne, papier) ; les deux heures sont conservées |
| Tâche | attente assignée à un rôle (et des co-rôles), datée par ancre, bloquante ou normale, de nature fournir / saisir / décider / confirmer / signer |
| Verrou | invariant non paramétrable (connaissement, vetting valide, clôture) |
| N1 … N4 | niveaux de confidentialité : escale, restreint, bilatéral, sûreté |
| ATA, ATB, T0, T1, ATD | arrivée réelle, amarrage terminé (all fast), début et fin du transfert, appareillage réel ; ETA, ETB, ETS, ETC, ETD leurs estimées |
| NOR | notice de disponibilité (notice of readiness) remise par l'agence, contresignée par le terminal et l'affréteur |
| SOF | rapport des faits (statement of facts), généré du registre, signé par le capitaine et le terminal |
| STS, SPM, POAC | transbordement navire-navire, poste bouée (single point mooring), personne responsable de l'opération STS (prestataire) |

**Onglets de référence.** Modèle de données champ par champ : 1. Modèle de données · Catalogue des écrans avec captures : 2. Écrans · Formulaires de saisie champ par champ : 3. Formulaires de saisie · Formulaires standards : 4. Formulaires standards · Catalogues de paramétrage (gabarits, jalons, demandes, documents, points d'arrêt, causes, ports) : 5. Catalogues de paramétrage · API publique : 6. API.

**Documents du dépôt complémentaires** : `README.md`, `docs/ARCHITECTURE.md` (arbitrages du corpus §11, points ouverts §12), `docs/DEPLOIEMENT.md`, `docs/SECURITE.md`, `docs/GUIDE_UTILISATEUR.md`, `docs/PARAMETRAGE.md`, `docs/API.md`, `docs/FORMAT_EXPORT.md`, `docs/FORMULAIRES.md`, `docs/TRACABILITE_CDC.md`, `docs/COMPOSANTS.md`, `CHANGELOG.md`.

## 15.2 Termes ajoutés en 1.4 (contrôle des pertes, interface navire/terre)

| Terme | Définition |
| --- | --- |
| Contrôle des pertes (*loss control*) | suivi contradictoire des quantités transférées, par le navire, le terminal, l'inspecteur et les intérêts cargaison (trader, superintendant, affréteur) ; dans la plateforme : journal de pompage des deux bords, relevés par citerne validés, écarts et tolérance |
| Feuille de journal de pompage | en-tête d'un côté du journal de pompage : citerne ou bac, barème (m³/m), densité, VCF, quantité prévue, débit et pression attendus, niveaux de départ et d'arrêt |
| Barème (m³ par mètre) | quantité contenue par mètre de niveau d'un bac ou d'une citerne, servant à convertir une variation de niveau en volume |
| Creux / innage (*ullage / innage*) | hauteur de vide au-dessus du liquide / hauteur de liquide, mesurées dans une citerne (mm) |
| TOV, GOV, GSV | volume total observé ; volume brut observé (sans eau libre ni sédiments) ; volume brut standard à 15 °C (GOV × VCF) — API MPMS ch. 12 |
| VCF | facteur de correction de volume de la température observée à 15 °C (tables ASTM D1250) |
| Écart terre − bord | différence entre la quantité reçue (ou livrée) relevée par le terminal et celle livrée (ou reçue) relevée par le navire, sur une heure ou en cumul, en m³ et en % du chiffre bord ; au-delà de la tolérance du port : arrêt pour investigation |
| Validation d'un relevé | acte de l'inspecteur qui rend un relevé de citerne visible des autres parties ; un rejet motivé appelle un relevé corrigé |
| Lecteurs d'un rapport | rôles autorisés à lire un rapport vivant (journal de pompage, mesures, liste de contrôle, tableau du port), décidés au paramétrage du port |
| Tableau des escales du port | vue de consultation de toutes les escales déclarées du port, aux seuls champs d'un tableau de port, sans information opérationnelle d'une autre agence |
| Liste de contrôle navire/terre en ligne | la SSSCL (structure ISGOTT) renseignée point par point par le navire et le terminal depuis la plateforme, signée par les deux, répétée pendant le transfert |
| Time sheet (structure des terminaux) | informations générales, activités standard (du / au / durée), activités non standard et arrêts (retard compté, imputation), quantités et performance, récapitulatif des temps, exclusions, quatre signatures |

## 15.3 Termes ajoutés en 1.5 (généralisation)

| Terme | Définition |
| --- | --- |
| Agent principal | l'agence qui a annoncé l'escale (`PortCall.agency`) : seule à déclarer, réviser, annuler, clore et refaire l'annonce ; elle donne à chaque partie son accès au dossier |
| Agence associée (co-nominée) | une autre agence du port invitée avec le rôle AGE sur l'escale, pour une partie des opérations ; elle agit dans l'accès que l'agent principal lui a donné, et n'invite pas |
| Accès au dossier | ce qu'une partie voit et fait sur l'escale : complet (tous ses onglets, agit dans son rôle), partiel (les onglets listés, y agit), lecture seule (tous ses onglets, aucun acte) — `CallParty.access`, `scopes` |
| Validité de l'annonce | la période, en jours, fixée à l'annonce (défaut et plafond du port) pendant laquelle l'annonce vaut ; conservée pour la facturation ; `validity_days`, `valid_until` |
| Escale obsolète | une escale dont la validité est échue sans que le navire soit à quai (`EXPIRED`) : lisible, plus modifiable, à annoncer de nouveau |
| Dépassement | les heures qu'une escale à quai passe au-delà de sa validité : jamais interrompue, signalée et comptée (`validity_overrun`) |
| Refaire l'annonce | créer, depuis une escale obsolète, annulée ou rejetée, une nouvelle escale en brouillon avec les mêmes données (`renew_call`, `renewed_from`) |
| Base de facturation | les chiffres que la plateforme donne pour facturer l'escale : validité annoncée, du / au, arrivée, départ, clôture, obsolescence, heures au port, heures de dépassement (`billing_basis`) ; la plateforme ne facture pas |
| Feu vert | l'accord d'une partie, en son nom, avant une étape : capitainerie (décision sur la demande), sûreté et base navale, terminal, mandant ; tâche `green_light` du socle commun, gardant un point d'arrêt, retirable avec motif |
| Mandant | l'armateur, l'affréteur ou le réceptionnaire pour le compte de qui l'opération se fait (rôle COM) ; il donne son feu vert |
| Nature de cargaison | vrac liquide, vrac sec, conteneurs, marchandises diverses, roulier, autre (`CargoKind`) : elle choisit les gabarits, les unités, les mesures, la liste de contrôle et les formulaires |
| Navire livreur, navire receveur | dans un transbordement navire-navire, celui qui donne la cargaison (`DONOR`) et celui qui la reçoit (`RECEIVER`) ; chacun a sa propre escale, son agence et son équipe |
| Documents attendus | les documents demandés à l'annonce ou depuis, au-delà de ceux que les gabarits exigent : facultatifs du catalogue ou liste ouverte ; chacun devient une tâche non bloquante de la partie qui l'émet (`requested_at_creation`) |
| Conférence de placement | la réunion où un port place les navires sur ses postes ; le tableau des escales du port en reprend la présentation : à quai, en rade, attendus, partis, avec la nature de la cargaison et le tonnage quand le port les montre |
| Plan d'occupation des postes | le tableau des escales par poste sur une période, comme les feuilles d'occupation des terminaux : opération, mandant, produit, quantité, ETA / ETB / ETD, état |
| Grille de vetting | la comparaison de chaque limite du poste avec la donnée du navire (statut Y dans la limite, N hors limite obligatoire, K vigilance, Z non évalué) et l'avis APTE / APTE SOUS VIGILANCE / INAPTE / NON ÉVALUÉ (`VETTING_CHECKLIST`) |
| PAEC | *pre-arrival exchange of information* (ISGOTT 22.2) : les informations que le navire et le terminal pétrolier échangent avant l'arrivée |
| Code BLU | le code OMI de bonnes pratiques pour le chargement et le déchargement sûrs des vraquiers ; sa liste de contrôle navire / terminal et son accord de chargement ou de déchargement |
| Draft survey | la détermination de la quantité d'un vrac sec par la différence des déplacements (tirants d'eau) avant et après l'opération ; mesure et rapport |
| Pointage (tally) | le comptage des unités, colis ou boîtes à la réception ou à la livraison ; feuille de pointage et constat de réception (out-turn) |

