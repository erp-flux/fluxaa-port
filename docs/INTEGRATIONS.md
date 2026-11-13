# Intégrations de données externes — ce que FLUXAA Port offre, ce que Kpler peut y apporter

Étude d'opportunité (version 1.6, 13 novembre 2026). Elle inventorie les points par lesquels la plateforme
reçoit ou donne des données, passe en revue les produits du groupe Kpler (Kpler, MarineTraffic, FleetMon et l'activité
AIS de Spire Maritime, que Kpler a reprise en 2025) et dit, pour chacun, ce qu'il pourrait apporter à une escale, par quel
point d'entrée de FLUXAA, à quelles conditions. Rien ici n'est une exigence du cahier des charges : les
intégrations retenues feront l'objet d'une version, après décision des ports et contractualisation avec Kpler.

## 1. Principes qui ne changent pas

* **Une donnée externe corrobore, elle ne décide pas.** Le registre reste contradictoire et humain : un jalon a un
  émetteur, une décision un décideur sous double authentification (règles d'or, `docs/ARCHITECTURE.md` §2). Une
  position AIS, une ETA prédite, un signalement de risque s'affichent *à côté* des faits déclarés — comme le
  tableau AIS le fait déjà (`apps/ais`, EF-3.6) — et n'écrivent jamais un jalon ni une autorisation.
* **Chaque donnée externe garde sa source et son heure.** Elle entre par un compte d'intégration nominatif, à
  portée limitée (`User.is_integration`, `integration_scopes`), est journalisée comme toute écriture, et peut être
  rejouée ou retirée sans toucher aux actes des parties.
* **Le besoin d'en connaître s'applique.** Ce qu'un fournisseur sait d'un navire (propriété, risques, cargaison
  estimée) n'est montré qu'aux rôles qui ont à le voir (matrice FLX-SPEC-001 §5) ; les données commerciales de
  Kpler ne sont pas redistribuées aux parties d'une escale au-delà de ce que le contrat Kpler permet.
* **Coût et dépendance maîtrisés.** Les API Kpler sont sous contrat commercial (pas d'inscription libre) et, pour
  MarineTraffic, décomptées en crédits : l'intégration interroge peu (le port, ses escales attendues), met en
  cache, et fonctionne sans Kpler quand la source est absente — la plateforme ne s'arrête jamais faute d'un flux.

## 2. Les points d'entrée et de sortie de FLUXAA Port aujourd'hui

| Point | Sens | Ce qu'il porte | Référence |
| --- | --- | --- | --- |
| `POST /api/v1/ais/positions/` | entrée | rapports de position AIS de tout fournisseur (`mmsi`, `lat`, `lon`, `observed_at`, vitesse, cap, statut, IMO, nom, destination, tirant d'eau) ; compte d'intégration de portée `ais` ; dédoublonnage ; purge à 24 h ; écarts calculés avec les faits déclarés (`ais.discrepancies`) | `docs/API.md`, `apps/ais/services.py` |
| `manage.py ais_listen --udp` / `--aisstream` | entrée | récepteur local NMEA ou flux aisstream.io | `docs/DEPLOIEMENT.md` §15 |
| `POST /api/v1/vessels/` | entrée | fiche navire (IMO, nom, pavillon, type, DWT, LOA, largeur, tirant d'eau, année, déplacement, collecteur, tirant d'air, grues) | `docs/API.md` |
| `POST /api/v1/calls/` et actions | entrée | annonce, déclaration, demandes, jalons, documents — par un système tiers (PCS, guichet unique) au nom d'une partie | `docs/API.md` |
| `POST C/documents/` | entrée | tout document rattaché à une tâche (un rapport de conformité, un certificat) | `docs/API.md` |
| Webhooks sortants | sortie | les entrées N1 du journal, signées HMAC, rejouées | `docs/API.md` §6, `PARAMETRAGE.md` §9 |
| `GET /api/v1/board/`, `board/occupation/` | sortie | conférence de placement, plan d'occupation | `docs/API.md` |
| Export `fluxaa-port-export/1.3` | sortie | l'escale complète, vérifiable hors plateforme | `docs/FORMAT_EXPORT.md` |

## 3. Les produits Kpler, et ce qu'ils peuvent apporter à une escale

Sources consultées le 13 novembre 2026 : la page *Maritime Data, APIs & Integrations* et les notes de version *Maritime* de mars et de mai 2026 de Kpler, la documentation des API
MarineTraffic et du SDK Python Kpler, les pages *Risk & Compliance* et *Artificial Intelligence* de Kpler, la notice
d'arrêt de l'API Maritime 2.0 (ex-Spire), et le profil public de la surface d'API Kpler tenu par API Evangelist — un
**tiers**, cité pour ce que Kpler ne publie pas en accès libre (liens en fin de document). Les noms de produits et les
limites citées sont ceux publiés ; ce qui ne vient que du profil tiers (absence d'inscription libre et de prix publiés) est signalé ; tout se vérifie sur le contrat. Le
portail développeurs de Kpler ne se lit pas sans session : son catalogue n'a pas été consulté directement.

| Produit Kpler | Ce qu'il donne | Ce qu'il apporterait à FLUXAA | Point d'entrée FLUXAA | Conditions |
| --- | --- | --- | --- | --- |
| **MarineTraffic API — Vessel Positions** (positions AIS en temps réel : d'un navire, d'une flotte, d'une zone prédéfinie ou personnalisée ; piste historique) et **Kpler AIS** (selon Kpler : plus de 1,2 milliard de messages par jour, fréquence inférieure à 30 s, historique de plus de 11 ans, livré par API REST, NMEA, Kafka ou extraction ; points *AIS-Latest* et *AIS-Historical* cités par les notes de version) ; **Vessel Observation API** (détections satellitaires rattachées au même identifiant de navire que l'AIS) | position, vitesse, cap, statut, destination et tirant d'eau de chaque navire | **le tableau AIS du port sans récepteur local** (eaux du port, rade, zone STS au large — là où un récepteur côtier n'entend pas) ; corroboration de l'arrivée, de l'ancrage, de l'accostage, de l'appareillage déclarés ; alerte sur un écart déclaré / observé ; un navire sans AIS détecté par satellite en rade ou en zone STS, signalé à la sûreté | `POST /api/v1/ais/positions/` — adaptateur livré : `scripts/kpler_marinetraffic_adapter.py` (lecture d'un extrait ou de l'API, projection vers le format FLUXAA, transmission) | contrat MarineTraffic ou Kpler AIS ; clé `api_key` (MarineTraffic, décomptée en crédits) ; une zone prédéfinie par port ; échelles (dixièmes de nœud et de mètre) confirmées sur le contrat |
| **MarineTraffic API — Voyage Info** : ETA prédite vers un port, prévisions de voyage, destinations prédites, **arrivées attendues par port** (expected / predictive port arrivals), congestion du port, route et distance au port | pour chaque navire attendu : ETA calculée, distance restante, port précédent | **la liste des attendus de la conférence de placement rapprochée de la réalité** : ETA déclarée par l'agence à côté de l'ETA prédite, alerte quand elles divergent de plus de n heures ; navires en approche sans escale annoncée (signalés à la capitainerie) ; aide à l'arbitrage des fenêtres de poste | nouveau service `integrations/kpler.py` (poll périodique par le planificateur `run_scheduler`, par UN/LOCODE du port — TGLFW, SLFNA) ; affichage sur l'aperçu et la conférence ; jamais une modification des heures déclarées | contrat MarineTraffic ; crédits par appel ; le port décide si l'ETA prédite est montrée aux agences |
| **Événements de port, de terminal et de poste** (Kpler : arrivées, départs, accostages et désaccostages ; changements d'ETA, de destination, de tirant d'eau, de statut) et **MarineTraffic API — Events** : escales (port calls) et accostages (berth calls) d'un navire ou d'un port, historiques et en direct | arrivée, départ, poste, durée observés | **corroboration des jalons** (arrivée, à quai, appareillage) et du time sheet ; **historique des escales d'un navire** avant son annonce (ports précédents, durées) | même service ; comparaison avec `Milestone` (écart montré, jamais corrigé) | contrat MarineTraffic |
| **Vessel ownership and particulars** (Kpler : plus de 2,5 millions de navires, caractéristiques et six niveaux de propriété et de gestion, livrés en GraphQL — la *MarineTraffic Vessels API* du profil tiers) et **Vessel Information** (particularités, photo — documentation publique) | LOA, largeur, tirant d'eau, DWT, année, type, propriétaire, gestionnaire, classification, assureur | **la fiche navire remplie à l'annonce** depuis l'IMO (bouton *Compléter depuis Kpler*), avec la source et l'heure ; les limites d'acceptation du poste lues à l'annonce (1.6) et la grille de vetting disposent alors de données complètes ; l'armateur et le gestionnaire proposés comme parties | `POST /api/v1/vessels/` (champs existants) ; un bouton sur le formulaire d'annonce ; `Vessel` reçoit `source` et `verified_at` (évolution de modèle) | contrat (Vessels API : sur devis) ; les données de propriété relèvent du besoin d'en connaître (AGE, CAP, APO, COM) |
| **Risk & Compliance (MarineTraffic)** : navires et entités sanctionnés (OFAC, OFSI, UE), couches de propriété, navires non couverts par un club P&I, trous et usurpation d'AIS, transbordements de cargaisons sanctionnées, risques de pavillon, historique des inspections de l'État du port, **Vessel Risk Indicator** (indicateur de risque par navire, à code couleur, annoncé en mars 2026) ; depuis mai 2026 : **alertes** sur les escales et les transbordements à haut risque, les transbordements « dark », les trous et l'usurpation d'AIS, manipulation d'identité AIS (navires « zombies »), indicateur de faux pavillon, et deux **flux Kafka** des risques par navire (sur demande au compte Kpler) | un rapport et un indicateur de risque par navire | **la tâche M0:05 — contrôle des listes de sanctions — étayée** : le rapport Kpler déposé comme document de la tâche (type `SANCTIONS_SCREENING`, à créer), l'indicateur montré à la capitainerie et à la sûreté (rôles SUR, CAP, APO) avant le feu vert de la base navale (M0:09b) ; alerte si un navire annoncé est signalé ; **à la capitainerie, au moment d'autoriser une zone et une fenêtre STS (demande `STS_ZONE`), l'alerte de transbordement à haut risque ou « dark » sur les deux navires** | `POST C/documents/` (rapport) ; service `integrations/kpler.py` pour l'indicateur ; nouveau type de document ; confidentialité N3 | contrat Risk & Compliance ; **la décision reste humaine** (l'agence confirme le contrôle, la sûreté donne ou refuse son feu vert) ; disponibilité par API à confirmer avec Kpler |
| **Kpler Direct Access APIs** — Liquids, LNG, LPG, Dry Bulk (flux et transactions, **port calls cargaison par cargaison** avec ETA, début et fin, quantités ; **ship-to-ships** ; stockages) et SDK Python | pour un port : les escales et les transbordements observés avec les produits et quantités estimés | **rapprochement des quantités** : quantité déclarée à l'annonce contre l'estimation Kpler (information pour la capitainerie et la direction, statistiques du port) ; **détection d'un STS non annoncé** dans la zone STS ; statistiques de trafic du port par produit | service `integrations/kpler.py` ; onglet Statistiques (DIR, APO, CAP) | contrat Kpler par plateforme (Liquids, Dry…) ; données commerciales : jamais montrées aux parties d'une escale, seulement au port |
| **Container Intelligence API** (v1.3.0, mars 2026 : escales filtrées par armateur (SCAC) et code de service, **congestion des terminaux** — attente moyenne, séjour moyen, navires à quai —, cap du navire ; 500 requêtes par minute) | pour un terminal à conteneurs : les escales prévues et la congestion | **la conférence de placement enrichie** pour les escales conteneurs (MC1) : attente moyenne, séjour moyen, escales des services réguliers | même service ; conférence et plan d'occupation | contrat Container Intelligence |
| **Kpler Freight API** (métriques de fret et de flotte, congestion, capacité sur lest) | congestion portuaire, flotte disponible | indicateurs de la direction du port | Statistiques | contrat Freight |
| **Kpler Copilot, Kpler MCP, Cloud DB** | un assistant dans le terminal Kpler, une couche d'intégration qui laisse un modèle de langage interroger les API Kpler, une offre de mise à disposition des données « cloud » | hors périmètre d'une escale ; l'assistant du port (EF-17) reste encadré et sans décision | — | — |

Ce qui **ne** passe **pas** par Kpler : les actes des parties (jalons, décisions, signatures, documents émis), le
domaine sûreté N4, les mesures contradictoires bord / terre / inspecteur, les listes de contrôle. Ce sont les
faits du registre ; aucune donnée externe ne les remplace.

## 4. Trajectoire proposée

| Étape | Contenu | Ce qu'il faut |
| --- | --- | --- |
| **A — positions** (livrable immédiat) | l'adaptateur `scripts/kpler_marinetraffic_adapter.py` alimente le tableau AIS à partir de MarineTraffic ou de Kpler AIS (zone du port) ; cadence de 2 à 5 minutes par le planificateur ou une tâche système ; les écarts déclaré / observé déjà calculés par le tableau | un compte d'intégration `ais` par port ; la clé et la zone du contrat ; validation des échelles sur un extrait réel |
| **B — attendus et ETA** | service `integrations/kpler.py` : arrivées attendues et ETA prédite par port, montrées sur la conférence de placement et l'aperçu ; navires en approche sans annonce signalés à la capitainerie | contrat MarineTraffic ; réglage du port : montrer ou non l'ETA prédite aux agences ; seuil d'écart |
| **C — navire** | *Compléter depuis Kpler* à l'annonce (particularités, propriété) ; `Vessel.source` / `verified_at` ; parties proposées (armateur, gestionnaire) | Vessels API ; évolution de modèle (migration) |
| **D — conformité** | rapport de sanctions et indicateur de risque rattachés à M0:05, visibles de la sûreté avant M0:09b ; type de document `SANCTIONS_SCREENING` ; alerte sur un navire signalé | contrat Risk & Compliance ; décision des ports sur qui lit l'indicateur |
| **E — corroboration et statistiques** | escales et transbordements observés (Direct Access), congestion conteneurs ; rapprochement des quantités et des jalons ; statistiques du port | contrats Kpler par plateforme ; règle d'affichage réservée au port |

Chaque étape se livre avec ses tests, sa documentation et sa ligne du journal des versions, comme toute version.

## 5. Sources

* Kpler — *Maritime product updates: Q1 2026* : https://www.kpler.com/blog/maritime-product-updates-smarter-risk-signals-stronger-apis-faster-mobile-experience
* MarineTraffic (Kpler) — ship tracking : https://www.kpler.com/product/maritime/ship-tracking
* MarineTraffic — Risk & Compliance : https://www.kpler.com/product/commodities/maritime-compliance-trade-finance
* Documentation des services de l'API MarineTraffic : https://servicedocs.marinetraffic.com/
* Kpler — SDK Python (port calls cargaison par cargaison, ship-to-ships, vessels, flows, inventories) : https://python-sdk.dev.kpler.com/resources/port_calls.html ; portail développeurs (catalogue sous session) : https://developers.kpler.com/
* API Maritime 2.0 (ex-Spire Maritime) — notice d'arrêt : Kpler en cesse les API et renvoie vers ses solutions maritimes : https://servicedocs-sm.kpler.com/maritime-2-0/
* Kpler — *Artificial Intelligence* (Copilot, MCP) : https://www.kpler.com/solutions/ai
* Kpler — *Maritime Data, APIs & Integrations* (Kpler AIS, événements de port et de poste, ETA, propriété des navires, Vessel Observation API) : https://www.kpler.com/solutions/fundamental-intelligence/maritime-data
* Kpler — mises à jour produits maritimes de mai 2026 (alertes de conformité, faux pavillon, flux Kafka), reprises par Hellenic Shipping News : https://www.hellenicshippingnews.com/maritime-product-updates-proactive-compliance-live-incident-intelligence-and-smarter-terminal-monitoring/
* Profil public de la surface d'API Kpler (API Evangelist, tiers) : https://github.com/api-evangelist/kpler
