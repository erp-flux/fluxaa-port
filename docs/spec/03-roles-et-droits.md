# 3. Rôles et droits
> Chapitre **généré** par `python manage.py generate_spec` à partir du code livré — ne pas modifier à la main : modifier le code (modèles, catalogue, formulaires, vues, API) puis régénérer.

Les droits viennent du **rôle d'une organisation sur l'escale** (`CallParty`), jamais d'une personne. La matrice ci-dessous (FLX-SPEC-001 §5) est appliquée côté serveur par `services/rights.py` ; l'interface n'ajoute aucun droit, elle masque ce qui est refusé. Verbes : C créer · V voir · S saisir/modifier · A approuver/décider · Cs contresigner · Ct contester · K clore · E exporter.

## 3.1 Les douze rôles

| Code | Libellé FR / EN | Groupes |
|---|---|---|
| `AGE` | Agence maritime / Shipping agency | vue d'ensemble des tâches |
| `NAV` | Navire / capitaine / Vessel / master | sans tableau de bord |
| `TER` | Terminal / dépôt / Terminal / depot |  |
| `CAP` | Capitainerie / Harbour master | vue d'ensemble des tâches, décideur (second facteur), journal des accès, domaine N4 |
| `APO` | Autorité portuaire / Port authority | décideur (second facteur) |
| `SVC` | Services nautiques / Marine services |  |
| `ADM` | Douanes, immigration, santé / Customs, immigration, health | décideur (second facteur) |
| `SUR` | Sûreté et base navale / Security & naval base | décideur (second facteur), journal des accès, domaine N4 |
| `INS` | Inspecteur et laboratoire / Surveyor & laboratory |  |
| `COM` | Armateur / affréteur / Owner / charterer | lecture seule commerciale, export |
| `PRE` | Prestataire / Service provider |  |
| `DIR` | Direction du port / Port management | export, journal des accès |

Pseudo-rôle `ANY` dans les gabarits : « la partie à l'origine / toute partie ».

## 3.2 Matrice objets × rôles (`rights.MATRIX`)

| Objet | AGE | NAV | TER | CAP | APO | SVC | ADM | SUR | INS | COM | PRE | DIR |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `call` | CVSK | V | V | VAK | VS | V | V | V | V | VE | V | VE |
| `vessel` | CVS | VCt | V | VA | V | V | V | V | V | V | — | V |
| `party` | CV | V | V | VA | V | V | V | V | V | V | V | V |
| `request` | CVS | VCt | CVS | VA | VA | V | VA | VA | — | V | CVS | V |
| `authorization` | V | V | V | CVA | CVA | V | CVA | CVA | — | V | V | VE |
| `milestone` | VSCs | VCsCt | VSCs | VCt | V | VS | VS | VS | VSCs | VCt | S | VE |
| `measurement` | V | VSCs | VSCs | V | — | — | — | — | VSCs | VCt | — | VE |
| `dispute` | CV | CV | CV | VA | V | V | V | V | CV | CV | V | VE |
| `document` | CVS | CVCs | CVS | VA | V | V | CVA | CV | CVS | V | C | VE |
| `correspondence` | CV | CV | CV | CV | CV | CV | CV | CV | CV | CV | CV | V |
| `berth` | V | — | V | VA | CVSA | VS | — | — | — | — | — | V |
| `dashboard` | V | — | V | V | V | V | V | V | V | V | V | VE |
| `audit` | — | — | — | V | — | — | — | V | — | — | — | VE |

Superviseurs N2 (voient les objets « restreints » en plus de l'émetteur et des destinataires) : AGE, CAP, DIR. Rôles du côté terre : TER, PRE.

## 3.3 Règles de visibilité et d'attribution (fonctions de `services/rights.py`)

| Fonction | Règle |
|---|---|
| `access_of(actor, call) -> 'tuple[str, set[str] \| None]'` | The access the actor holds on the file: ``("FULL", None)`` — every tab, acts within its role —, ``("PARTIAL", {tabs})`` — the tabs listed, acts within them —, ``("READ", None)`` — every tab, no act. The system, the account-less links (a master, a party's link: their role is their whole access), the principal agent and the port's own parties hold the file in full |
| `acts_for(actor, role: 'str', org_id, *, by_master: 'bool' = False) -> 'bool'` | The actor acts for the party that made a record: same role and, for a shore party, same organisation — whether the record was made from an account or from the organisation's access link. Several organisations may hold one role on a call (two providers, owner and charterer, two surveyors): the role alone never lets one of them read, replace, cancel or close what another one issued. The ship is one party: any valid master link of the call speaks for it |
| `acts_for_side(actor, side: 'str', org_id=None) -> 'bool'` | The actor is the party of *side*: the ship through the master's link (or a NAV account), the shore through the terminal that entered the record (or, with no record yet, the terminal that speaks for the shore) |
| `alert_visible(actor, alert) -> 'bool'` | An alert is a record addressed to some roles; the harbour master and the port management see them all |
| `allowed_tabs(actor, call) -> 'set[str] \| None'` | The tabs of the file the actor may open (None = every tab) |
| `call_queryset_for_user(user)` | Calls on which the user's organisation holds an active role that the user may exercise |
| `can(actor, verb: 'str', kind: 'str') -> 'bool'` | — |
| `can_act_in(actor, call, scope: 'str') -> 'bool'` | May the actor act (enter, decide, upload…) in this part of the file? Reading only never acts; a partial access acts in its tabs only |
| `can_export(actor) -> 'bool'` | — |
| `can_read_audit(actor) -> 'bool'` | — |
| `can_read_report(actor, code: 'str') -> 'bool'` | — |
| `can_see_full_call(actor) -> 'bool'` | The product, the quantity and what the agency declared at the announcement (v1.6): for every reader of the call but a provider, who reads what concerns it in the request addressed to it |
| `can_see_refusal_reason(actor, req: 'ServiceRequest') -> 'bool'` | Vetting refusal reasons are N3: agency, owner and the instructing service only (EF-2.6, S7) |
| `dispute_content_visible(actor, dispute: 'Dispute') -> 'bool'` | Statements are bilateral (N3): the two parties plus the harbour master |
| `dispute_header_visible(actor, dispute: 'Dispute') -> 'bool'` | — |
| `document_readers(doc: 'Document') -> 'set[str]'` | The roles that read a restricted (N2) document besides its issuer: the listed readers and the required signers, plus — unless the document type limits its readers to that list — the coordinating roles (agency, harbour master, port management) and the owner. A laboratory's quality certificate limits its readers (FLX-CDC-002 v1.4, EXG-Q-06): the agency does not read it |
| `document_visible(actor, doc: 'Document') -> 'bool'` | — |
| `draft_visible(actor, call) -> 'bool'` | A draft call is visible to its agency (and to the master, who provides certificates) until declared |
| `ensure_visible(predicate: 'bool') -> 'None'` | — |
| `is_dispute_counterpart(actor, dispute: 'Dispute') -> 'bool'` | The party a dispute is addressed to: the author of the disputed item when it has one, else the role |
| `is_dispute_opener(actor, dispute: 'Dispute') -> 'bool'` | — |
| `is_document_issuer(actor, doc: 'Document') -> 'bool'` | — |
| `is_principal_agent(actor, call) -> 'bool'` | The agency that created the call: it declares, revises, cancels and closes it, and grants the other parties their access. A co-nominated agency acts within the access it was given |
| `is_thread_creator(actor, thread: 'Thread') -> 'bool'` | — |
| `measurements_visible(actor) -> 'bool'` | Quantities and validated tank readings: the readers the port decided at parametrage |
| `milestone_visible(actor, milestone: 'Milestone') -> 'bool'` | — |
| `only_provider(actor) -> 'bool'` | Providers see only their own service, not the full call (FLX-SPEC-001 §5 note 4) |
| `provider_answers_for(actor, milestone: 'Milestone') -> 'bool'` | A provider is the countersigner of this milestone (addressed to "PRE") as the shore side of the call |
| `report_readers(port, code: 'str') -> 'set[str]'` | The roles that read a live report of the port (pumping log, validated measurements, safety checklist, call board): the port administrator's setting, else the catalogue's default (FLX-CDC-002 v1.4, EXG-Q-08) |
| `request_visible(actor, req: 'ServiceRequest') -> 'bool'` | — |
| `request_visible_roles(req: 'ServiceRequest') -> 'set[str]'` | — |
| `require(actor, verb: 'str', kind: 'str', message: 'str \| None' = None) -> 'None'` | — |
| `require_act(actor, call, scope: 'str') -> 'None'` | — |
| `responsible_label(role: 'str') -> 'str'` | — |
| `roles_with(verb: 'str', kind: 'str') -> 'set[str]'` | — |
| `shore_org_id(call, role: 'str')` | The organisation that speaks for the shore side in *role* — the terminal at a berth, the provider operating at sea (FLX-SPEC-001 §7): the party the agency or the harbour master designated, else the only organisation holding that role on the call. With several and none designated, none of them speaks for the shore side |
| `sole_holder(call, role: 'str')` | The organisation holding *role* on the call, when it is the only one |
| `speaks_for_shore(actor, role: 'str', call) -> 'bool'` | — |
| `tank_reading_visible(actor, reading) -> 'bool'` | A validated reading is read by the measurement readers; a pending or rejected one by its own side and the surveyor only (FLX-CDC-002 v1.4, EXG-Q-05) |
| `task_visible(actor, task: 'Task') -> 'bool'` | — |
| `thread_visible(actor, thread: 'Thread') -> 'bool'` | The creating side within its own organisation, and the invited parties |
| `visible_documents(actor, call)` | — |
| `visible_milestones(actor, call)` | — |
| `visible_requests(actor, call)` | — |
| `visible_tasks(actor, call)` | — |
