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
