# Guide d'utilisation par rôle

Une page par rôle : ce que vous voyez, ce que vous faites, ce que la plateforme refusera. L'interface est en français ou en anglais (bouton FR / EN en haut à droite) ; les heures sont celles du port, dont le fuseau est rappelé en haut de chaque écran.

Trois principes valent pour tout le monde :

* **Vos droits viennent du rôle de votre organisation sur l'escale**, pas de votre personne. Sur une escale où votre organisation n'a pas de rôle, vous ne voyez rien.
* **Vous saisissez ce qui relève de vous, les autres contresignent ou contestent.** Une contestation ne bloque jamais l'opération ; elle empêche seulement la clôture tant qu'elle est ouverte.
* **Rien ne s'efface.** Une erreur se corrige par une rectification motivée, qui reste visible à côté de l'original.
* **« Sans objet »** se déclare avec un motif. Pour une décision, une demande ou une tâche qu'attend un point d'arrêt, seul le rôle qui en répond peut le faire : on ne déclare jamais sans objet la décision qu'on attend.
* **Double authentification** : remplacer son application d'authentification exige un code de l'ancienne ; téléphone perdu, l'administrateur du port réinitialise (acte journalisé). Après plusieurs codes ou mots de passe erronés, la saisie est suspendue jusqu'à quinze minutes.

Et quatre règles valables pour toutes les parties de l'escale :

* **Chacun est convoqué dès la déclaration.** À la déclaration de l'escale, chaque partie est notifiée pour saisir ou consulter ce qui la concerne. Une partie qui a un compte reçoit la notification habituelle ; une partie **sans compte** (terminal, inspecteur, armateur, prestataire, service nautique) reçoit par courriel **son propre lien**, valable jusqu'à la **clôture** de l'escale et limité à elle. Le titulaire donne son nom complet à la première ouverture : tout ce qu'il saisit est nominatif. Les rôles qui décident (capitainerie, autorité portuaire, douanes, sûreté) gardent toujours un compte avec double authentification — un lien ne décide jamais. L'agence ou la capitainerie peut émettre ou révoquer un lien à tout moment (*Parties › Accès des parties sans compte*).
* **Chacun dépose ses documents.** L'onglet Documents accepte, de toute partie et pour son rôle (compte ou lien), les pièces de son type : certificats, rapports, photos de terrain, relevés, et tout autre document (« Autre document »). Chaque pièce porte son empreinte SHA-256 ; une pièce signée ne change plus, elle se remplace par une nouvelle version.
* **Une escale peut changer de zone.** Allègement au large puis déchargement du reliquat à quai, chargement à la bouée puis complément à quai, attente en rade entre deux postes : l'escale se compose d'**étapes** successives (*Aperçu › Étapes de l'escale*), chacune avec sa zone, son poste, ses opérations, ses heures. L'agence ou la capitainerie planifie l'étape suivante — ses tâches sont créées aussitôt pour chaque partie — ; les services nautiques enregistrent le **déhalage** (départ du poste ou de la zone), refusé sans autorisation de mouvement en vigueur ; l'accostage à l'étape suivante se saisit avec les jalons habituels, sans conflit avec ceux de l'étape précédente. Le rapport des faits présente les étapes et rattache chaque jalon à la sienne.
* **Chaque partie émet ses documents depuis la plateforme, qui les archive.** Bouton **Formulaires** de l'escale : les formulaires que vos rôles émettent, groupés par partie — l'agence (avis d'arrivée, time sheet, FAL, connaissement, compte d'escale…), le navire (NOR, déclaration de santé, eaux de ballast, plans, permis…), le terminal (liste de contrôle, bon de réception, relevé des bacs…), les autorités (l'**acte écrit de chaque décision** : feu vert, poste, mouvement, libre pratique, formalités, congé de départ… avec son code de vérification), les services nautiques (ordre de mouvement, bon de prestation), l'inspecteur (certificats de quantité, de qualité, de propreté, de dégazage, procès-verbal d'échantillonnage), l'armateur (recap, instruction documentaire, assurances, lettre de garantie) et les prestataires (bordereau des déchets, liste de contrôle soutage, dossier STS…) : soixante-seize formulaires, tous dans la même structure (en-tête, corps du standard, signatures par rôle, pied scellé). Ce que le registre connaît est rempli, le reste se complète et se signe sur le papier, qui revient ensuite dans l'escale comme version du document. Voir [FORMULAIRES.md](FORMULAIRES.md).

---

## Agence maritime (AGE)

* **Annoncer une escale** (*Escales › Annoncer une escale*) : navire, zone (quai, rade, bouée, zone STS), opérations, heures estimées, cargaison, parties invitées. L'escale naît en brouillon ; la plateforme crée aussitôt les tâches de chaque partie.
* **Inviter les parties — une liste ouverte.** Les autorités du port sont invitées d'office. Pour toutes les autres parties (terminal, inspecteur, laboratoire, armateur, affréteur, réceptionnaire, prestataire STS, avitailleur, collecteur de déchets, plongeurs, chantier, pilotes et remorqueurs d'un autre port…), ajoutez autant de lignes que nécessaire : le rôle (qui porte les droits), puis soit une **organisation enregistrée** dans le port, soit une **nouvelle organisation** — son nom, sa **nature** (choisie dans la liste suggérée ou écrite librement : la liste n'est pas exhaustive), son courriel et son téléphone. Une nouvelle organisation est créée dans le port avec le rôle que vous lui donnez (l'administrateur la complète ensuite) ; sans compte, elle reçoit son propre lien d'accès à la déclaration, à l'adresse indiquée — ou, sans adresse, un lien que vous lui remettez par QR ou impression. La même invitation reste possible après la création (*Parties › Inviter une partie*).
* **Déclarer** (*Aperçu › Déclarer l'escale*) une fois fournis le Q88 (M0:02), les certificats du capitaine (M0:03) et le contrôle des sanctions (M0:05). Sinon, un encadré nomme ce qui manque.
* **Délivrer l'accès capitaine** (*Parties › Accès capitaine*) : un lien et un code à huit caractères, affichés une seule fois, à remettre au capitaine (courriel, QR code, impression). Les autres parties sans compte sont convoquées d'office à la déclaration (lien envoyé à l'adresse de leur organisation) ; vous pouvez aussi émettre un lien nominatif pour l'une d'elles (*Parties › Accès des parties sans compte*).
* **Planifier une étape** (*Aperçu › Étapes de l'escale › Planifier l'étape suivante*) quand le navire doit changer de zone pendant l'escale : zone, poste souhaité, opérations, fenêtre, motif. Les tâches des nouvelles opérations sont créées aussitôt ; une étape planifiée s'annule avec un motif, elle ne s'efface pas.
* **Demander** feu vert, poste, mouvements, libre pratique, formalités, services (*Demandes › Nouvelle demande*). Vous ne décidez jamais vos propres demandes. Quand plusieurs prestataires participent à l'escale, désignez celui qui réalise le service (collecte des déchets, par exemple) : les autres ne la voient pas. Une commande passée avant l'arrivée de tout prestataire revient à celui qui rejoint l'escale s'il est seul de son métier ; à défaut, *Demandes › Désigner le prestataire* (une seule fois).
* **Désigner qui parle au nom du côté terre** (*Parties › Désigner pour le côté terre*) : quand deux terminaux, ou plusieurs prestataires en mer, participent à l'escale, un seul enregistre les jalons et le chiffre terre et contresigne au nom de la terre. Vous le désignez ; la capitainerie le peut aussi. Seul de son rôle, un terminal ou un prestataire n'a pas à être désigné ; à plusieurs, tant que personne n'est désigné, aucun ne le peut.
* **Relier une escale partenaire** (STS, double banking) : *Aperçu › Relier une escale partenaire*, avec sa référence. Vous reliez vos propres escales ; deux escales d'agences différentes sont reliées par la capitainerie.
* **Réviser les heures** (*Aperçu › Réviser les heures*) : toutes les échéances suivent ; aucune rafale de notifications.
* **Après les opérations** : générer le rapport des faits (vos remarques éventuelles y figurent sous votre nom), le faire signer par le capitaine et le terminal, demander la clôture.
* **Sûreté** : gardes armés, escorte, incident → *Dépôt confidentiel de sûreté*. Vous recevez un récépissé ; rien n'apparaît dans l'escale.

## Capitaine (NAV) — sans compte

* Ouvrez le lien reçu, ou saisissez le code sur `/bord/`. L'accès est limité à votre escale et prend fin après le départ.
* **Formulaires** : NOR, liste de contrôle navire/terre, FAL, déclaration maritime de santé, fiche pilote… préremplis depuis le registre, à imprimer, compléter, signer et déposer (voir en tête de guide).
* Enregistrez **vos** jalons (arrivée, mouillage, passerelle, appareillage…), fournissez les documents demandés (certificats), saisissez la valeur **bord** des mesures.
* Contresignez ou contestez les jalons des autres (pilote, amarrage, interruptions) ; signez les documents qui vous attendent (rapport des faits).
* Sur la passerelle sans réseau : **Appli terrain** — vos saisies partent dès que la connexion revient, avec l'heure du fait et l'heure de saisie.

## Terminal ou dépôt (TER)

* Demandez l'**acceptation du navire (vetting)** avec le rapport SIRE/CDI : le port décide, avec une durée de validité. Vos formulaires : synthèse du vetting, attestation de mise en sécurité du poste, relevé des bacs et compteurs, bon de réception, rapport d'inspection de la bouée, dossier d'accostage à couple, en plus de la liste de contrôle, de l'accord pré-transfert et du relevé des flexibles (*Formulaires*).
* Signez avec le bord la **réunion pré-transfert** et la **liste de contrôle navire/terre** (tâches conjointes) ; consignez l'**essai d'arrêt d'urgence** — sans eux, le début du transfert est refusé.
* Enregistrez raccordement, début et fin de transfert, **interruptions avec leur cause** (liste fermée), le **journal de pompage**, la valeur **terre** des mesures. Si un autre terminal participe à l'escale, seul celui que l'agence ou la capitainerie a désigné pour le côté terre le fait ; la fin d'une interruption revient à la partie qui en a saisi le début.
* Sur l'appontement : **Appli terrain**, utilisable avec des gants (grandes cibles), hors ligne.

## Capitainerie (CAP)

* Double authentification obligatoire ; elle est redemandée pour chaque décision.
* Décidez feu vert, acceptation du navire, mouvements, autorisation de départ (*Demandes › Décider*). Chaque autorisation porte une expiration et un code vérifiable publiquement sur `/verifier/` ; son **acte écrit** (demande telle que déposée, décision, validité, conditions, QR de vérification) est **déposé automatiquement dans les documents de l'escale** au moment de la décision — approbation comme refus — et s'imprime depuis *Documents* ou *Formulaires*, avec les conditions limites d'exploitation du poste.
* Vous voyez toutes les tâches et le journal ; les refus de points d'arrêt y sont consignés avec leur auteur.
* Clôturez l'escale après le départ : refusé tant qu'une contestation n'est pas close (une réponse ne suffit pas) ou qu'une mesure est incomplète. Vous pouvez clore une contestation **sans accord** — jamais la trancher.
* Reliez entre elles les escales de deux agences différentes (STS, double banking) ; désignez, si l'agence ne l'a pas fait, le terminal ou le prestataire qui parle au nom du côté terre (*Parties*).
* Vous accédez à l'**espace sûreté** (dossiers N4) ; chaque consultation est journalisée nominativement.
* **Tableau AIS**, **Statistiques** et **Assistant** du port : voir les sections en fin de guide.

## Autorité portuaire (APO)

* Double authentification obligatoire. Attribuez les **postes** (la plateforme refuse un poste à un navire non accepté ou dont l'acceptation a expiré) et décidez avec la capitainerie l'acceptation des navires ; l'acte d'attribution du poste et du créneau s'émet depuis *Formulaires*.
* Le **plan des postes** du tableau de bord montre 72 heures : réel en plein, estimé en contour, transfert en vert.

## Services nautiques (SVC)

* Programmez puis confirmez pilotage, remorquage, lamanage (*Demandes › Confirmer la prestation*) ; émettez l'**ordre de mouvement** et le **bon de prestation** signé par le capitaine (*Formulaires*).
* Enregistrez pilote à bord, première amarre, amarrage terminé, dernière amarre — le pilote à bord est refusé sans autorisation de mouvement.
* Quand l'escale change de zone (rade → STS → quai…), enregistrez le **déhalage** (« Déhalage — départ du poste ou de la zone ») : refusé tant qu'aucune étape suivante n'est planifiée ou sans autorisation de mouvement en vigueur ; l'accostage à l'étape suivante se saisit ensuite normalement.

## Douanes, immigration, santé (ADM)

* Double authentification obligatoire. Décidez libre pratique, formalités d'entrée et de sortie, relève d'équipage ; chaque décision dépose d'elle-même son acte écrit dans les documents de l'escale (libre pratique, formalités d'arrivée avec relevé des scellés, formalités de sortie, laissez-passer), réimprimable depuis *Formulaires*. Les formalités déclaratives (FAL) restent au guichet unique : la plateforme n'en garde que la preuve de dépôt, mais prépare les déclarations FAL 1 à 5 de l'agence et du navire.

## Sûreté et base navale (SUR)

* Double authentification obligatoire. **Espace sûreté** : dossiers déposés par l'agence ou le capitaine (gardes armés, escortes, incidents), décision et modalités, confirmations d'embarquement et de débarquement, pièces chiffrées, journal des accès. Ces dossiers n'apparaissent nulle part ailleurs. Hors N4, vos formulaires : déclaration de sûreté, autorisation d'accès en zone portuaire (liste des personnes et véhicules demandée par l'agence), information de sûreté avant l'arrivée du navire.

## Inspecteur indépendant et laboratoire (INS)

* Ouvrez les **mesures** (jaugeages, chiffre du connaissement, OBQ, ROB) et saisissez la valeur inspecteur ; enregistrez les jaugeages initial et final. La plateforme calcule tous les écarts et n'en désigne aucun comme référence ; la tolérance s'applique à l'écart bord/terre.
* Émettez vos **certificats** depuis *Formulaires* : procès-verbal d'échantillonnage, rapport de jaugeage, certificat de quantité (quantités du registre préremplies), certificat de qualité (rapport d'analyse), certificat de propreté des citernes, constat de ROB, certificat de dégazage.
* Toute partie peut **contester une quantité** (*Mesures › Contester cette quantité*) : tant que la contestation n'est pas close, le connaissement ne peut pas être émis.

## Armateur ou affréteur (COM)

* Lecture de l'escale, documents qui vous sont demandés — recap de nomination et de charte-partie, instruction documentaire pour le connaissement, confirmation des assurances, lettre de garantie (*Formulaires*) —, contresignature ou contestation de la NOR, **export** de l'escale. Vous voyez le motif d'un refus de vetting. Aucune saisie d'événement ni de mesure.

## Prestataires (PRE)

* Vous ne voyez que **votre service** : vos tâches, les commandes qui vous sont confiées, vos jalons (remise des déchets, par exemple), les contestations qui vous concernent. Un autre prestataire du même métier sur l'escale ne voit ni les commandes qui vous sont confiées, ni les documents et les échanges que vous émettez.
* Vos formulaires (*Formulaires*) : bordereau de réception des déchets, bon de prestation, liste de contrôle sécurité soutage et note de livraison de soutes, étude de compatibilité STS, attestation des défenses et flexibles, listes de contrôle STS, attestation d'agrément de l'installation de réception, dossier des intervenants extérieurs — selon les opérations de l'escale.
* En mer (STS, rade), le prestataire qui opère pour le côté terre enregistre l'opération et contresigne au nom de la terre : d'office s'il est seul, sur désignation de l'agence ou de la capitainerie sinon.

## Direction du port (DIR)

* Tableau de bord, **sept indicateurs** (chacun liste les escales dont il est calculé), export des escales, journal des accès, page **Pilotage** (bruit des alertes, retards, délais de saisie par rôle). L'administrateur fonctionnel du port est un utilisateur de la direction, avec double authentification obligatoire : voir [PARAMETRAGE.md](PARAMETRAGE.md).
* Page **Statistiques** et **assistant du port** (point du port, questions sur le registre) : voir ci-dessous.

---

## Tableau AIS (toutes les parties du port)

Menu **Tableau AIS** (`/carte/`). Sur le plan des eaux du port — postes en carrés, zones de mouillage et STS en cercles — chaque navire entendu au cours des 24 dernières heures est dessiné à sa dernière position, orienté selon son cap, avec son escale si vous pouvez l'ouvrir : plein pour un navire à quai ou en opération, vide pour un navire attendu, grisé pour un navire appareillé, en pointillé pour un navire sans escale dans ce port. La page se rafraîchit chaque minute. Le tableau du bas donne la position (degrés et minutes), la vitesse et la route, le statut AIS déclaré par le navire, sa destination et l'âge du dernier rapport.

Le tableau **informe et corrobore, il ne décide rien** : aucune position ne crée, ne modifie ni ne contresigne un jalon. Quand l'image AIS et le registre ne disent pas la même chose — navire entendu amarré alors qu'aucune arrivée n'est enregistrée, navire sorti des eaux du port alors que l'escale est « en opération », navire muet depuis plus de six heures, navire toujours amarré après l'appareillage enregistré — un encart **« écarts entre l'image AIS et le registre »** pose la question à la capitainerie et à l'agence, qui vérifient auprès de l'émetteur du jalon. Sans source de positions raccordée (voir le guide de déploiement, §15), la page reste une liste vide.

## Statistiques (direction, autorité portuaire, capitainerie)

Menu **Statistiques** (`/statistiques/`). Choisissez une période (douze mois glissants par défaut) : la page recalcule tout depuis le registre, sans rien stocker ni ajuster, et l'export **CSV** reprend les mêmes tableaux.

* **Escales et quantités par mois** : escales (par mois d'ETA), terminées, annulées, tonnes déclarées, attente moyenne en rade, durée nette moyenne de transfert, durée moyenne dans le port — quatre graphiques et un tableau mensuel.
* **Ce que le port a traité** : par modèle d'opération, par zone demandée, par produit, par poste (escales, heures à quai, taux d'occupation des quais).
* **Interruptions et temps morts** : par cause et par imputation (terre, bord, tiers, météo), avec la part des temps morts à cause établie contradictoirement.
* **Décisions des autorités** : par type de demande, qui décide, délais moyen, médian et le plus long entre soumission et décision, refus et décisions sous conditions.
* **Contestations et contresignatures** : ouvertes, closes avec ou sans accord, ouvertes par la plateforme, délai de clôture ; contresignatures expresses, tacites et contestées.
* **Saisies, documents et alertes** : jalons par source (en ligne, hors ligne, papier, système), saisies différées, documents déposés, alertes par nature.
* **Tâches dans les délais, par rôle** : tâches faites et bloquantes faites à l'heure, par rôle — jamais par personne.

Ces chiffres jugent le fonctionnement du port et son paramétrage, pas les personnes : les délais de décision décrivent le flux des demandes, et un long délai signifie le plus souvent un dossier qui a attendu des pièces.

## Assistant du port (direction, autorité portuaire, capitainerie)

Menu **Assistant** (`/assistant/`), présent seulement quand l'assistance IA est activée pour le port (voir [PARAMETRAGE.md](PARAMETRAGE.md) §10). Deux usages, tous deux tracés et sans effet sur le registre :

* **Point du port** : à la demande, l'assistant rédige en une page ce qui est à quai ou en opération, ce qui est attendu et sa prochaine étape, les décisions qui attendent une autorité et les tâches en retard par escale, les contestations ouvertes, les alertes des dernières 24 heures, les écarts AIS et les indicateurs des 90 derniers jours.
* **Interroger le registre** : une question en français ou en anglais (« quelles escales ont une décision en attente depuis plus de quatre heures ? », « le prochain navire attendu est-il entendu sur l'AIS ? »), une réponse qui cite les escales dont elle est tirée et dit quand le registre ne montre pas quelque chose.

L'assistant lit le registre tel que vous le voyez (jamais le domaine sûreté, jamais une personne : des rôles), n'approuve, ne signe, ne clôture ni ne corrige rien, et renvoie à la page Statistiques pour les périodes antérieures. Le repli « ce qui a été transmis à l'assistant » liste les objets dont chaque réponse a été construite.

---

## Démonstration en dix minutes (données de démonstration)

Comptes : `<rôle>.tglfw@demo.fluxaa.test` (Lomé, en français) ou `<rôle>.slfna@…` (Freetown, en anglais), mot de passe choisi au chargement des données.

1. **`dir`** — *Tableau de bord* : le plan des postes, l'escale MT ATLANTIC DEMO en opération, MT GULF DEMO attendue, la paire STS déclarée.
2. **`age`** — MT ATLANTIC DEMO › *Aperçu* : « Ce que la plateforme refusera — et pourquoi » ; *Jalons* : une interruption contestée par le capitaine ; *Demandes* : les autorisations, une expirée.
3. **`ter`** — même escale : le terminal ne voit pas les tâches de l'agence ; *Contestations* : sa réponse au capitaine. Ouvrez l'**Appli terrain**, coupez le réseau, enregistrez une interruption : elle part au retour de la connexion, marquée « saisie différée » si elle arrive en retard.
4. **`svc`** — MT GULF DEMO › *Jalons* : enregistrer « pilote à bord » est **refusé**, l'encadré nomme la tâche manquante (autorisation de mouvement, capitainerie) et le refus est au journal.
5. **`sur`** — *Espace sûreté* : le dépôt de gardes armés de l'agence. Reconnectez-vous en **`ter`** et cherchez-le : il n'existe nulle part, ni à l'écran, ni dans l'API.
6. **`com`** — *Exporter* l'escale : une archive au format ouvert, avec les empreintes de chaque pièce.
