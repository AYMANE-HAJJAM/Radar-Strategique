# Radar 1 title filter experiment

Date: 2026-10-09. Read-only Neon snapshot: **2026-10-09 21:04:17.924986+00:00** (UTC).

**Verdict B: It needs targeted improvements.** A lightweight filter is useful for prioritizing professional heritage opportunities, but a strict title-only classifier misses real candidates and cannot establish strategic scale, complete scope or eligibility. This experiment does not establish production readiness.

## 1. Source, scope and safety

The source is the actual `pmmp_listing_index` in the existing configured Neon database, `neondb`. A single direct psycopg connection read all **5,209** rows ordered by index ID, in `BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY`. `transaction_read_only=on` was verified. Connection timeout was 5 seconds, transaction-local statement timeout 15 seconds and lock timeout 2 seconds. The transaction ended with `ROLLBACK`.

The SELECT read `id`, `consultation_id`, `title`, `reference`, `buyer`, `procedure`, `deadline`, `category`, `detail_url`, `location`, and `publication_date`. Every row's stored title and contextual fields were made available to the offline screening pass. A representative subset was then manually inspected, rather than claiming all 5,209 received independent human validation. No SearchRun was created or updated; no processing state, business result, configuration, worker or deployment was modified. No Flask application or existing collector/recovery/backfill was invoked. No PMMP HTTP, AI/model or paid-search call was made. Run #59 was not triggered or processed by this experiment.

The analysis used standalone temporary scripts and a local snapshot, not application imports. The only deliverables added to the repository are this Markdown report and the CSV. The configured Neon source is real; its mapping to the exact Render deployment was not separately verified through Render configuration.

Snapshot file SHA-256: `f80a591c4849c082640509dbc4ca7b11aac4b28cfda044e03351b51c0a409892`. This identifies the exact extracted dataset, not the live database after extraction.

### Data limitations

- All 5,209 stored titles end with `...`. The report and CSV reproduce the **entire stored title without further shortening**. The suffix alone does not prove every short title is truncated, but some objects visibly end mid-sentence. Complete official objects beyond what the index stores are unavailable under this no-fetch experiment. They have not been invented or expanded.
- There are no NULL/empty titles, deadlines or categories in this snapshot. Categories: **2,130 Travaux**, **1,282 Fournitures**, **1,797 Services**. Presence does not establish accuracy.
- **30 titles contain Arabic**. Accent/case normalization does not translate them. A language audit was needed to prevent French-keyword false negatives.
- No duplicate non-null consultation IDs were found. Counts are indexed listing rows, not necessarily unique underlying projects: related study/control tenders and reissued notices remain separate. References alone are not unique identifiers.
- No official detail or labeled ground-truth set was used. Category, procedure, deadline and buyer are contextual clues. A buyer such as ADERFES does not make every purchase relevant.

## 2. Experiment rules

This is a **title-led, metadata-assisted triage experiment**, followed by documented manual refinements. It is not evidence that titles alone suffice. Buyer does not create a positive match; procedure can reveal a competition absent from the title. References were used for exact verification, never as hard-coded relevance exceptions. Deadline was assessed separately from relevance.

Normalize Unicode NFKD, remove combining accents, casefold, map `oe` ligatures and curly apostrophes, and collapse whitespace. Preserve original values for output. Match concept combinations, not isolated positive words. No candidate-count cap was applied.

| Group | Positive concepts | Required qualification |
| --- | --- | --- |
| A - Heritage | Built/cultural/historical patrimoine, medina/ancienne medina, remparts, murailles, historic monuments, kasbah/casbah, ksour, fortification, historical memory/valorization, patrimonial restoration/rehabilitation/conservation/safeguarding | A professional study/design/planning/supervision commission. A place name or unrelated use of patrimoine/conservation is insufficient. |
| B - Professional services | Etude(s), architectural conception, maitrise d'oeuvre, technical studies and suivi, diagnostic, expertise, technical assistance, architectural mission, control; heritage safeguard plans and architectural charters also count as professional planning | A qualifying A/C/D context for a priority candidate. B alone is never automatic acceptance. Some boundary planning/facility objects are retained with LOW confidence to establish context in detail. |
| C - Competitions | Concours architectural/conception or consultation architecturale, in title or procedure | Explicit professional service, then project qualification. Ordinary schools/OFPPT/ISTA and staff housing are excluded. Other ordinary facilities do not become accepted because their procedure is architectural. |
| D - Major architecture | Museum/cultural complex, regional hospital, university/campus, public headquarters, structuring architectural complex | Professional building design/studies plus plausible strategic project. Equipment, ordinary repairs, a retaining wall or a building's address do not qualify. Missing scale/discipline is ambiguous. |

Rule order:

1. Route Arabic/non-covered language to review, rather than silently treating French-keyword absence as rejection. This experiment manually reviewed all 30 Arabic objects.
2. Exclude clear domain mismatches: software/IT/backups, supplies/equipment, catering, guarding/cleaning, agricultural/property patrimoine and water/soil conservation. Architectural conception must concern buildings, not software or communication materials.
3. Exclude ordinary schools/OFPPT/ISTA, staff housing and obvious generic agricultural/utility facilities where no explicit heritage or major-project evidence is present. A mosque in a mixed title or an explicit heritage restoration context warrants review rather than a blind school exclusion.
4. Separate **professional studies/supervision of works** from **execution of works**. A `Travaux` category is a clue, not an unconditional veto when the title clearly commissions professional services. Words `travaux`, `rehabilitation` and `restauration` never independently trigger rejection of a service.
5. Prioritize A+B. Specialist topography, geotechnics or quality control in a heritage context is retained as ambiguous unless architectural scope is established. Ordinary roads/sanitation/topography without that context is excluded.
6. Prioritize qualified C and plausible major D+B. Retain uncertain scale, historic status, service discipline, architectural charters, city/coastal planning and possible structuring facilities as ambiguous. Do not manufacture budget or size thresholds from missing amounts.
7. Keep the relevance shortlist independent of expiry so known historic examples and lexical misses remain measurable. Flag elapsed dates, future unverified dates, and same-day deadlines separately.

The literal distinction requested is satisfied by the real data: **145/2026, 36/BR/RGON/2026 and 42/2026/ADERFES** all concern studies/supervision of works and remain selected. **11/DH/BH/2026** and **015/2026/FNM** concern museum execution works and are excluded. No fabricated tender was used to demonstrate the distinction.

Confidence means confidence in **triage relevance from the stored evidence**, not legal eligibility or final business acceptance:

- HIGH: explicit heritage subject and a professional commission.
- MEDIUM: plausible strategic competition/major project, or a meaningful heritage/specialist boundary.
- LOW: possible architectural relevance, with major scope/history/discipline unresolved.

Every retained entry requires official detail before a business acceptance decision. `A?` means possible heritage; `D?` means major-building context without proven major scope. Group matches can overlap; primary result buckets below do not overlap. A B-only ambiguous row is retained to determine whether A/C/D context exists, not treated as a qualifying service by itself.

## 3. Actual result counts

These are counts from the frozen snapshot after the offline rules and documented review refinements. They are not estimated counts or simulated tenders.

| Exclusive final outcome | Count | Future stored date | Date is today | Date already elapsed |
| --- | ---: | ---: | ---: | ---: |
| Strong heritage candidates | 6 | 3 | 0 | 3 |
| Qualified architectural competition candidates | 3 | 3 | 0 | 0 |
| Major architecture candidates | 2 | 2 | 0 | 0 |
| Ambiguous candidates requiring detail | 101 | 76 | 1 | 24 |
| Rule exclusions | 5,097 | 4,061 | 94 | 942 |
| **Total inspected by the offline pass** | **5,209** | **4,145** | **95** | **969** |

The complete retained list contains **112 rows**: 11 priority candidates and 101 ambiguous entries, **2.15%** of the index. Among those 112, 84 have future stored dates, 1 has today's date, and 27 have elapsed dates. A future date is not confirmation that the tender is still open; no current detail/status was retrieved.

The 5,097 exclusions comprise **4,187 identifiable scope exclusions** and **910 rows with no combined positive context**. The latter are unselected by this experiment, not proved irrelevant by official details. It would be misleading to call all 5,097 independently verified obvious rejects.

Initial offline pass (already including the language audit): 6 heritage, 3 competition, 2 major, 98 ambiguous, 5,100 exclusions. Review removed six clear ambiguous false leads and restored nine initially excluded boundary objects to detail review. Final: 101 ambiguous and 5,097 exclusions. No priority row was removed. These refinements were made only in the experiment's temporary data.

### Exclusion reasons, mutually exclusive by first applicable rule

| Reason | Count |
| --- | ---: |
| Pure execution/construction/maintenance works; no professional study, design or supervision commission in stored title. | 1746 |
| Supply/equipment procurement, even where the beneficiary is a heritage site or major building. | 991 |
| No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. | 910 |
| Ordinary school/lycee/OFPPT/ISTA project without explicit heritage or major-campus evidence; competition procedure alone is insufficient. | 509 |
| IT/software/backup supply or maintenance; architectural/heritage words describe another domain. | 247 |
| Non-built heritage, cadastral property, soil/water conservation, catering, security or cleaning; not architectural professional scope. | 220 |
| Ordinary roads/water/sanitation/flood infrastructure or narrow civil engineering without explicit built-heritage architectural scope. | 173 |
| Execution/maintenance object without a professional-service commission. | 140 |
| Staff/ordinary housing without explicit heritage or strategic architectural scope. | 52 |
| Maintenance/repair or diagnostic repair package, not a target architectural design commission. | 39 |
| Generic agricultural/industrial utility, warehouse, vehicle depot, animal pound or cemetery facility without heritage/major-strategic evidence. | 35 |
| Arabic-language audit: leasing/operation/sale/catering, road execution, or ordinary school technical control; no target professional opportunity. | 29 |
| Agricultural processing/marketing or utility production facility; no built heritage or major strategic architecture. | 2 |
| Narrow retaining-wall reconstruction studies; hospital location alone does not make this a major architectural commission. | 1 |
| Communication/media-support design, not architectural conception. | 1 |
| Audio-equipment installation studies, not architectural professional scope. | 1 |
| Narrow waterproofing repair studies at an existing tribunal; no heritage or major architectural commission established. | 1 |

## 4. Verification of the four known references

Exact reference comparison strips only the index display suffix ` - ...`, then normalizes case. It does not match `04/2026/AUSY` as `04/2026/AUS`, or `145/2026/SKTRA` as `145/2026`. No reference-specific whitelist was used.

| Reference | Index ID | Filter result | Why | Deadline caveat |
| --- | ---: | --- | --- | --- |
| 04/2026/AUS - Settat | 3790 | Selected, A+B, HIGH | Study of valorization of cultural, natural and historical patrimoine. Cultural/historical context plus study is explicit. | 02/10/2026 11:00: elapsed. |
| 42/2026/ADERFES - Meknes | 2965 | Selected, A+B, HIGH | Technical studies and supervision of tourist-circuit works inside the ancienne medina. Travaux is the supervised object, not an execution-only commission. | 08/10/2026 10:30: elapsed. |
| 145/2026 - Safi | 1853 | Selected, A+B, HIGH | Technical studies, supervision and direction of medina rehabilitation/valorization works. | 15/10/2026 10:00: future stored date, opening status unverified. |
| 04/2026/CA/BR/RGON - Sidi Ifni | 781 | Selected, B+C+D, MEDIUM | Architectural studies/supervision of the corniche and stored procedure Concours Architectural. Strategic public-space relevance is plausible; no heritage status or budget was inferred. | 22/10/2026 11:00: future stored date, opening status unverified. |

All four are real rows, with full stored objects reproduced in the complete list below. The Sidi Ifni title does not say concours; the procedure supplies that evidence. A test limited to title competition phrases would miss its C classification. The two elapsed known examples are not current actionable opportunities merely because the relevance filter selects them.

## 5. Manual review and error measurement

The review unit is an indexed notice. Manual judgments here are based on the stored object and contextual fields. They are not substitutes for official detail or an independent labeled test set. No global precision/recall, true-negative rate or production false-negative rate can be estimated defensibly from this audit.

### Reviewed cohorts

- All 11 priority candidates: manually inspected; all 11 are plausible triage candidates from the stored evidence. Six have explicit heritage professional scope; five competition/major candidates still need scale and discipline confirmation. **This is not a measured 100% business precision.**
- Seeded initial ambiguous sample: 24 rows drawn with Python `random.Random(59).sample` from initial ambiguous rows ordered by index ID. Two definite false leads (IDs 711 and 2729), 22 unresolved from title. The observed false-lead fraction is **2/24 (8.33%)** in this specific triage sample; the unresolved 22 cannot be counted as true positives.
- Four additional targeted initial ambiguous rows (314, 4127, 4674, 5037): all four had clear unrelated/narrow scope. Across the combined 28-row ambiguous audit, six false leads were identified, **6/28 (21.43%)**. This deliberately enriched sample is not representative prevalence or final acceptance error rate.
- Seeded initial exclusion sample: 20 rows with the same seed and ordered-population method. No confirmed missed target opportunity was established from those titles. This does not prove no false negatives. Rural urban-planning objects can conceal heritage context, particularly when the stored title is incomplete.
- Targeted exclusion boundary audit: nine rows were retained for detail after inspection. These are **nine rescued review candidates**, not nine confirmed business-relevant false negatives. Their exact IDs and rationale are listed below.
- All 30 Arabic titles: 29 showed leasing/operation/sale/catering, road execution or ordinary school technical-control scope. ID 3730 showed a technical study and supervision of rehabilitation of Ksar Hanabou. A French-only matcher would lose this **real heritage-service candidate**; heritage status remains to be confirmed. This is one demonstrated language-coverage miss among the 30 inspected Arabic objects, not a corpus-wide recall estimate.

### Representative priority review

| Index ID | Reference | Manual assessment |
| --- | --- | --- |
| 724 | 03/2026 | Medina safeguard/aménagement plan. Professional planning is explicit even without etude; preserve. |
| 1853 | 145/2026 | Medina rehabilitation technical studies and direction of works. Preserve despite travaux. |
| 2321 | 36/BR/RGON/2026 | Studies and supervision for ancienne medina rehabilitation. Preserve. |
| 2965 | 42/2026/ADERFES | Old-medina tourism-circuit study and supervision. Preserve, but engineering versus architectural scope still needs detail. |
| 3790 | 04/2026/AUS | Cultural/natural/historical patrimoine valorization study. Strong lexical selection; built versus broader tourism deliverables need detail. |
| 3831 | 01/2026/CA/BP | Architectural historical-memory facility studies. Relevant historical-cultural project; not proof of restoration of a listed monument. |
| 13 | 06/2026 | Regional public headquarters competition. Scale and architect eligibility need detail. |
| 114 | 06/2026/CA/BR/RGON | Regional headquarters annex competition. Annex may be smaller than the strategic label suggests; verify. |
| 781 | 04/2026/CA/BR/RGON | Corniche design with competition procedure. Procedure adds evidence absent from title; verify urban/landscape commission. |
| 318 | O26/OP/2026 | Cultural-complex rehabilitation technical study. Architectural design versus BET engineering capability needs detail. |
| 1772 | 46/2026 | Regional hospital reconstruction technical studies/supervision. Major setting plausible; consortium/discipline requirements unknown. |

### Seeded ambiguous review: full sample identification

| ID | Reference | Result of manual scope review |
| --- | --- | --- |
| 1664 | 59/2026/BG | Retain for detail: Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works. |
| 591 | 18/DRAI/MS/BG/2026 | Retain for detail: Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required. |
| 4359 | 05/2026/AUSY | Retain for detail: Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not. |
| 3500 | 03/2026/DRDEAGADIR | Retain for detail: Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works. |
| 109 | 10/2026/DRANEFFM/SAP | Retain for detail: Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works. |
| 1071 | CA/02/2026/PUSMS | Retain for detail: Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission. |
| 2417 | 10/DRJCS/2026 | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 5002 | 17/DRAICS/BG/2026 | Retain for detail: Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required. |
| 4597 | 20/BC.OT/2026 | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 4184 | 04./2026/CZ | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 97 | 11/2026/DRANEFFM/SAP | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 3634 | 89/AREPFM/2026 | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 2892 | CA10/2026/APDN | Retain for detail: Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance. |
| 4425 | 05/.2026/CZ | Retain for detail: Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance. |
| 3844 | 51/2026 | Retain for detail: Professional technical study/control at a hospital; regional reconstruction specialist scope or limited extension/interior works requires discipline and scale verification. |
| 4790 | 42/2026/INDH/PT | Retain for detail: Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance. |
| 1203 | 01/26/SS | Retain for detail: Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance. |
| 4073 | 89/2026/CM | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 2729 | 69/2026 | Clear false lead: Communication/media-support design, not architectural conception. |
| 1332 | PX3129940/2026/DXR | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 3799 | 05/2026/AUS | Retain for detail: Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established. |
| 900 | 02/CA.BG/2026 | Retain for detail: Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance. |
| 711 | N84/2026/DPAO | Clear false lead: Agricultural processing/marketing or utility production facility; no built heritage or major strategic architecture. |
| 2885 | 43/2026/ADERFES | Retain for detail: Heritage place plus specialist topographic/quality-control service; confirm built conservation/design role rather than narrow engineering only. |

### Six clear false leads removed after ambiguous review

| ID | Reference | Full stored title | Why excluded |
| --- | --- | --- | --- |
| 314 | 20/2026 | Etude technique et suivi des travaux de démolition et de reconstruction du mur de soutènement au niveau de l’hôpital Mohamed V de Chefchaouen ... | Narrow retaining-wall reconstruction studies; hospital location alone does not make this a major architectural commission. |
| 711 | N84/2026/DPAO | ETUDE ARCHITECTURALE ET SUIVI DES TRAVAUX DE CONSTRUCTION D UNE PLATEFOMRE DE COMMERCIALISATION DES PRODUITS DE TERROIR AU NIVEAU DE LA COMMUNE DE TAFOUGHALT PROVINCE DE BERKANE DANS LE CADRE DU PROGRAMME IHYAE ... | Agricultural processing/marketing or utility production facility; no built heritage or major strategic architecture. |
| 2729 | 69/2026 | Conception et réalisation de supports d’information sur les activités culturelles de la Fondation Mohammed VI de Promotion Des Œuvres Sociales de l’Education – Formation. ... | Communication/media-support design, not architectural conception. |
| 4127 | 011/2026/DPAJ/SMOP | Etude architecturale pour la construction d'un atelier pour la production de cire, d'une chambre froide de 50 m2 et d'une clôture de 140 ml au niveau de la miellerie de l'union itihad nahaline de Jerada dans le cadre du ... | Agricultural processing/marketing or utility production facility; no built heritage or major strategic architecture. |
| 4674 | 13/DRAI/GON/BG/2026 | ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX D’INSTALLATION DES EQUIPEMENTS DE SONORISATION POUR 07 MOSQUEES DANS LA REGION DE GUELMIM OUED NOUN - en lot unique. ... | Audio-equipment installation studies, not architectural professional scope. |
| 5037 | 28/2026 | ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE REPRISE DE L’ETANCHIETE AU PROFIT DU TRIBUNAL DE PREMIERE INSTANCE DE BENAHMED ET SECTION DE FAMILLE DE SETTAT, PROVINCE DE SETTAT. ... | Narrow waterproofing repair studies at an existing tribunal; no heritage or major architectural commission established. |

### Nine exclusion-boundary rescues

| ID | Reference | Why retain for official detail |
| --- | --- | --- |
| 825 | 02/2026 | City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility. |
| 966 | 04/2026 | Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not. |
| 1208 | 03/2026/DRANEFMS/DPANEF_EKS | Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation. |
| 1598 | 12/AURS/2026 | City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility. |
| 2422 | 08/AUKSS/2026 | City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility. |
| 2863 | 44/2026/ADERFES | Topographic professional service inside an explicitly old-medina tourism circuit; architectural/conservation contribution is uncertain, so retain for detail rather than reject unrelated topography. |
| 3929 | 13/2026 | Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation. |
| 3934 | 12/2026 | Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation. |
| 4889 | 01/2026/AUSY | City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility. |

### Seeded exclusion review: full sample

| ID | Reference | Full stored title | Manual result |
| --- | --- | --- | --- |
| 1878 | 15/2026/CAS | LOCATION D'UN MAISON COMMUNALE N°02 AVENU 20 AOUT CENTRE TIGHMERT ... | No target professional opportunity evident: No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. |
| 709 | 10/2026/AUBM | Elaboration du plan de développement de l’agglomération rurale du centre de la commune territoriale d’Ait Oumdiss (Province d’Azilal) ... | Rural development plan: no explicit heritage or major architectural scope in title. Not a confirmed false negative; hidden heritage context remains possible. |
| 3845 | 38/2026/chro | Brancardage : Transport des malades à l’Intérieur du Centre Hospitalier Régional d’Oujda ... | No target professional opportunity evident: No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. |
| 194 | 26/2026/DRAFM | ACHAT DE FOURNITURE POUR MATERIEL INFORMATIQUE DESTINEE A LA DIRECTION REGIONALE DE L’AGRICULTURE DE FES MEKNES. ... | No target professional opportunity evident: IT/software/backup supply or maintenance; architectural/heritage words describe another domain. |
| 1140 | 24/2026/MAP | Maintenance des composants du système de production audio de la MAP. ... | No target professional opportunity evident: Execution/maintenance object without a professional-service commission. |
| 2504 | PM3130988/2026/DXM | Travaux d’entretien des vannes papillons, soufflets de dilatation et filtres autonettoyants de la conduite BONA des 4 tranches de la Direction Exploitation Mohammedia, marché cadre pour une durée d’une année ferme, ... | No target professional opportunity evident: Pure execution/construction/maintenance works; no professional study, design or supervision commission in stored title. |
| 198 | 49/2026/FES | TRAVAUX D’AMENAGEMENT ET DE REHABILITATION DE 9 ETABLISSEMENTS SCOLAIRES AUX DIFFERENTES COMMUNES, RELEVANTS DE LA DIRECTION PROVINCIALE A FES, répartis sur trois (03) Lots ... | No target professional opportunity evident: Ordinary school/lycee/OFPPT/ISTA project without explicit heritage or major-campus evidence; competition procedure alone is insufficient. |
| 5202 | 06/2026/CO/PAZ... | AMENAGEMENT DE DEUX PISTES AUX DOUARS ASSAMSSIL N’OUAMAN ET AIT OUMRI. ... | No target professional opportunity evident: Pure execution/construction/maintenance works; no professional study, design or supervision commission in stored title. |
| 89 | PJ4128723/2026/DXJ | Construction d’un mur de clôture de la centrale thermique à charbon de Jerada de 350MW ... | No target professional opportunity evident: Pure execution/construction/maintenance works; no professional study, design or supervision commission in stored title. |
| 4056 | 04/2026 | Achat de produits chimiques et biologiques pour le laboratoire de l’Hôpital HASSAN II, Centre Hospitalier Provincial TANTAN (Marché Cadre) ... | No target professional opportunity evident: Supply/equipment procurement, even where the beneficiary is a heritage site or major building. |
| 3161 | 31/2026/CF | ACHAT DE VOITURES ELECTRIQUES DE SERVICE AU PROFIT DE LA COMMUNE DE FES ... | No target professional opportunity evident: Supply/equipment procurement, even where the beneficiary is a heritage site or major building. |
| 4490 | 03/2026 | L’AFFERMAGE DE L’ABATTOIRE COMMUNALE DU SOUK HEBDOMADAIRE *ARBIAA BENSLIMANE* DE ZIAIDA POUR L’ANNE 2027. ... | No target professional opportunity evident: No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. |
| 2486 | 154/2026/SI | Acquisition des modules HSM (HARDWARE SECURITY MODULE) avec licences pour la gestion des Compteurs à prépaiement ... | No target professional opportunity evident: IT/software/backup supply or maintenance; architectural/heritage words describe another domain. |
| 1316 | 68J./INV/2026 | TRAVAUX D’EXTENSION DE L’ECOLE TNINE CHTOUKA, PAR (6) SIX SALLES DE CLASSE, A LA COMMUNE TERRITORIALE CHTOUKA. PROVINCE D’EL JADIDA ... | No target professional opportunity evident: Ordinary school/lycee/OFPPT/ISTA project without explicit heritage or major-campus evidence; competition procedure alone is insufficient. |
| 4876 | 66/DTZ/INV/2026 | TRAVAUX DE CONSTRUCTION DE 10 BLOCS SANITAIRES DANS 10 ETABLISSEMNTS SCOLAIRES AUX COMMUNES AJDIR , BOURED , GZANAYA EL JANOUBIYA ET JBARNA A LA PROVINCE DE TAZA ... | No target professional opportunity evident: Ordinary school/lycee/OFPPT/ISTA project without explicit heritage or major-campus evidence; competition procedure alone is insufficient. |
| 2830 | 51/2026 | Prestation de réservation d’hébergement dans le cadre des activités du Conseil de la Région Souss Massa. ... | No target professional opportunity evident: No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. |
| 1476 | 34/2026/DPA/46 | Etudes techniques pour l’aménagement de pistes rurales au niveau de la zone d’action de la Direction Provinciale de l’Agriculture de Tanger. ... | No target professional opportunity evident: Ordinary roads/water/sanitation/flood infrastructure or narrow civil engineering without explicit built-heritage architectural scope. |
| 4405 | 08/2026 | TRAVAUX DE CONSTRUCTION DE QUATRE TERRAINS DE PROXIMITE DANS DIVERS DOUARS A LA COMMUNE DE DRARGA ... | No target professional opportunity evident: Pure execution/construction/maintenance works; no professional study, design or supervision commission in stored title. |
| 955 | 10012475 | GESTION DES STATIONS DE POMPAGE D’ASSINISSEMENT LIQUIDE RELEVANT DE LA PROVINCE DE GUERCIF ... | No target professional opportunity evident: No combined heritage, qualifying competition or major-architecture professional-service evidence in the stored object. |
| 847 | 34/AOO/DPMR/ANP/2026 | ETUDE DE DIMENSIONNEMENT D’UN NOUVEAU RESEAU INCENDIE ALIMENTE EN EAU DE MER AU PORT DE MOHAMMEDIA ... | No target professional opportunity evident: Ordinary roads/water/sanitation/flood infrastructure or narrow civil engineering without explicit built-heritage architectural scope. |

### Concrete lexical failure modes found in real notices

| Index ID / reference | Failure of a naive title rule | Correct triage |
| --- | --- | --- |
| 203 / 23/DDE/DDI/2026 | Patrimoine foncier/immobilier plus maintenance actually describes AMLACS software support. | Reject IT. |
| 489 / 41/NARSA/2026 | Sauvegarde is a backup platform, not heritage safeguarding. | Reject IT. |
| 14 / 01/2026 | Restauration collective is catering at a youth center. | Reject catering. |
| 1261 / 08/2026/DRACS | Conservation des eaux et des sols is agricultural hydrology, not built conservation. | Reject unrelated scope. |
| 782 / 43/CS/2026 | Patrimoine de la commune concerns cadastral land topography. | Reject unrelated property topography. |
| 2629 / 22/2026/DRATTH/DPAD | Patrimoine agricole SIPAM is agricultural characterization. | Reject target-scope mismatch; not a claim it lacks cultural value. |
| 452 / 12/DRCRMS/2026 | Monuments historiques is the site of guarding/security, not a conservation study. | Reject guarding. |
| 153 / 101/2026/OFPPT | Concours Architectural for ISTA reconstruction. | Reject ordinary OFPPT/ISTA absent explicit heritage/strategic exception. |
| 1576 / 26/2026 | Consultation architecturale for an ordinary primary school. | Reject ordinary school. |
| 511 / 14/2026/BG | Architectural conception for staff housing. | Reject staff housing. |
| 815 / 11/DH/BH/2026 | Museum keyword alone would admit execution works. | Reject pure execution. |
| 4280 / 015/2026/FNM | Modern-art museum works are not an architect/study commission by this title. | Reject pure execution. |
| 2863 / 44/2026/ADERFES | Blanket topography rejection would discard a service in an ancienne-medina heritage circuit. | Retain ambiguous; official scope decides. |
| 3730 / 03/ASG/2026 | French words never match the Arabic study/supervision/ksar rehabilitation object. | Retain ambiguous A?+B after language review. |
| 966 / 04/2026 | Architectural charter elaboration lacks the literal etude service keyword. | Retain planning ambiguity. |
| 781 / 04/2026/CA/BR/RGON | Title lacks concours although the procedure is Concours Architectural. | Use procedure; retain qualified competition. |
| 3666 and 4665 / 195/2026/APDN variants | Ksar Majaz can be a place name; facade studies do not establish heritage status. | Both notices retained ambiguous, not asserted duplicates or historic-restoration projects. |

A broad heritage-looking title regex (`patrimoin|medina|rempart|muraille|monument|kasbah|casbah|ksar|ksour|fortific|histori|sauvegarde|conservation|restauration|rehabilitation`) matches **296** index objects. That raw count includes catering, infrastructure, supplies, place names and execution. It is not the number of heritage opportunities. The narrower heritage/place vocabulary matches 69. A literal title-only concours/consultation phrase screen matches 12; **121** stored procedures contain architectural wording. Neither broad count is a qualified-candidate count.

## 6. Complete retained candidate list

The CSV is [RADAR1_TITLE_FILTER_EXPERIMENT_SELECTED.csv](RADAR1_TITLE_FILTER_EXPERIMENT_SELECTED.csv). It contains the same **112** entries, including all ambiguous candidates, with 18 columns, original stored strings, clean and stored reference, index/consultation identity, rationale, confidence, deadline flag, and official URL. UTF-8 BOM and quoted fields preserve French accents, Arabic, commas and leading-zero reference strings. Import reference and consultation columns as text in spreadsheet software.

An official URL is an existing index value supplied for later inspection, not a fetched or verified detail page. No row is omitted because it is expired or has low confidence. Titles and buyers below retain their source display suffixes. All entries require official detail. The primary buckets are triage outcomes, not acceptances.

### Strong heritage candidates (6)

#### 03/2026 - index 724, consultation 1042105

- **Full stored title:** Elaboration du plan d’aménagement et de sauvegarde de la médina de tiznit ...
- **Buyer:** AGENCE URBAINE DE TAROUDANNT      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 22/10/2026 11:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / medina; plan d'amenagement.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042105](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042105&orgAcronyme=j8k).

#### 145/2026 - index 1853, consultation 1039623

- **Full stored title:** ETUDES TECHNIQUES, SUIVI ET DIRECTION DES TRAVAUX DE REHABILITATION ET DE LA MISE EN VALEUR DE LA MEDINA DE SAFI. ...
- **Buyer:** SOCIETE AL OMRANE MARRAKECH - SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / medina; etudes techniques; suivi.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039623](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039623&orgAcronyme=j8k).

#### 36/BR/RGON/2026 - index 2321, consultation 1030864

- **Full stored title:** REALISATION DES ETUDES ET SUIVI DES TRAVAUX DE REHABILITATION DE L'ANCIENNE MEDINA DE LA VILLE DE GUELMIM -PROVINCE DE GUELMIM ...
- **Buyer:** REGION DE GUELMIM - OUED NOUN      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 13/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / ancienne medina; medina; suivi.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1030864](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1030864&orgAcronyme=m8x).

#### 42/2026/ADERFES - index 2965, consultation 1040346

- **Full stored title:** Etudes techniques et suivi des travaux d’amélioration des circuits touristiques au sein de la médina de Meknès - circuit ancienne médina - Tronçon : Rue Dar Smen – Rue Rouamzine, en lot unique. ...
- **Buyer:** AGENCE POUR LE DEVELOPPEMENT ET LA REHABILITATION DE LA VILLE DE FES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 10:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / ancienne medina; medina; etudes techniques; suivi.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040346](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040346&orgAcronyme=g3h).

#### 04/2026/AUS - index 3790, consultation 1036481

- **Full stored title:** Appel d’offres ouvert National n° 04/2026 ayant pour objet l’étude de valorisation du patrimoine culturel, naturel et historique de la province de Settat. ...
- **Buyer:** AGENCE URBAINE DE SETTAT      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 02/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A+B+D / patrimoine culturel.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036481](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036481&orgAcronyme=j8k).

#### 01/2026/CA/BP - index 3831, consultation 1036880

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CREATION D’UN ESPACE DE LA MEMOIRE HISTORIQUE DE LA RESISTANCE ET DE LA LIBERATION A LA COMMUNE LEHRI DANS LE CADRE DE PARTENARIAT- PROVINCE DE KHENIFRA. ...
- **Buyer:** Province de KHENIFRA      -
- **Procedure / category:** Consultation architecturale ouverte simplifiée / Services
- **Deadline:** 02/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A+B+C / memoire historique; etudes architecturales; suivi; procedure: consultation architecturale ouverte simplifiee.
- **Selection reason:** Explicit built/cultural/historical heritage or medina planning plus studies/design/supervision; travaux describes the supervised project, not execution-only scope.
- **Confidence:** HIGH. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036880](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036880&orgAcronyme=q0x).

### Architectural competition candidates (3)

#### 06/2026 - index 13, consultation 1040198

- **Full stored title:** CONCOURS ARCHITECTURAL POUR LA CONCEPTION ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DU NOUVEAU SIEGE DE LA DIRECTION REGIONALE DE L’EQUIPEMENT, DU TRANSPORT ET DE LA LOGISTIQUE DE LAAYOUNE SAKIA EL HAMRA. ...
- **Buyer:** DIRECTEUR REGIONAL DE L'EQUIPEMENT ET DU TRANSPORT ET DE LA LOGISTIQUE ET DE L EAU LAAYOUNE      -
- **Procedure / category:** Concours Architectural / Services
- **Deadline:** 17/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D / suivi; conception architecturale; siege; procedure: concours architectural.
- **Selection reason:** Architectural competition procedure and regional public headquarters or public corniche design; strategic scope plausible but detail must establish scale and eligibility.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040198](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040198&orgAcronyme=o8p).

#### 06/2026/CA/BR/RGON - index 114, consultation 1037536

- **Full stored title:** Concours architectural pour la conception et le suivi des travaux de construction de l’annexe du siège de la Région Guelmim Oued Noun ...
- **Buyer:** REGION DE GUELMIM - OUED NOUN      -
- **Procedure / category:** Concours Architectural / Services
- **Deadline:** 03/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D / suivi; siege; procedure: concours architectural.
- **Selection reason:** Architectural competition procedure and regional public headquarters or public corniche design; strategic scope plausible but detail must establish scale and eligibility.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1037536](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1037536&orgAcronyme=m8x).

#### 04/2026/CA/BR/RGON - index 781, consultation 1032453

- **Full stored title:** L'élaboration des études architecturales et suivi des travaux d'aménagement de la corniche de SIDI IFNI. ...
- **Buyer:** REGION DE GUELMIM - OUED NOUN      -
- **Procedure / category:** Concours Architectural / Services
- **Deadline:** 22/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D / etudes architecturales; suivi; corniche; procedure: concours architectural.
- **Selection reason:** Architectural competition procedure and regional public headquarters or public corniche design; strategic scope plausible but detail must establish scale and eligibility.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032453](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032453&orgAcronyme=m8x).

### Major architecture candidates (2)

#### O26/OP/2026 - index 318, consultation 1045470

- **Full stored title:** L’ETUDE TECHNIQUE ET SUIVI DES TRAVAUX DE REHABILITATION ET D’EQUIPEMENT DU COMPLEXE CULTUREL DE NADOR – PROVINCE DE NADOR. ...
- **Buyer:** AGENCE DE L'ORIENTAL      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 27/10/2026 12:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D / etude technique; suivi; complexe culturel.
- **Selection reason:** Professional study/supervision of a cultural complex or regional hospital reconstruction; major architectural project plausible.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045470](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045470&orgAcronyme=a1t).

#### 46/2026 - index 1772, consultation 1032035

- **Full stored title:** ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE RECONSTRUCTION DU CENTRE HOSPITALIER REGIONAL DE SOUSS MASSA-AGADIR. ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EQUIPEMENTS PUBLICS DU SUD      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D / etudes techniques; suivi; centre hospitalier regional.
- **Selection reason:** Professional study/supervision of a cultural complex or regional hospital reconstruction; major architectural project plausible.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032035](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032035&orgAcronyme=o8p).

### Ambiguous candidates requiring official detail (101)

#### 12/2026 - index 10, consultation 1045092

- **Full stored title:** LA CONCEPTION ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION D’UN CENTRE D’ESTIVAGE DE LA FONDATION MOHAMMADIA DES ŒUVRES SOCIALES DES FONCTIONNAIRES DE LA JUSTICE A LAAYOUNE. ...
- **Buyer:** FONDATION MOHAMMEDIA DES OEUVRES SOCIALES DES FONCTIONNAIRES DE LA JUSTICE      -
- **Procedure / category:** Concours Architectural / Services
- **Deadline:** 17/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; conception architecturale; procedure: concours architectural.
- **Selection reason:** Concours Architectural in the stored procedure; the named project does not establish major strategic relevance by title alone.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045092](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045092&orgAcronyme=t5y).

#### 11/2026/DRANEFFM/SAP - index 97, consultation 1043754

- **Full stored title:** Réalisation des études et contrôle pour le réaménagement du Centre d’Education à l’Environnement et ses annexes et l’aménagement scénographique et paysager dudit Centre, relevant du Parc National de Tazekka, CT de ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EAUX ET FORETS DE FES-MEKNES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 04/11/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / controle; scenographique.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043754](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043754&orgAcronyme=w7t).

#### 10/2026/DRANEFFM/SAP - index 109, consultation 1043745

- **Full stored title:** Prestations d’études et de contrôle des travaux de réaménagement du bâtiment administratif, de la scénographie et de l’aménagement paysager du siège du Parc National de Tazekka, Province de Taza, en lot unique ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EAUX ET FORETS DE FES-MEKNES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 04/11/2026 09:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / controle; siege; scenographie.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043745](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043745&orgAcronyme=w7t).

#### 08/CONSA/2026/AREPO - index 122, consultation 1043886

- **Full stored title:** L’ETUDE ARCHITECTURALE, LA CONCEPTION ET LE SUIVI DES TRAVAUX DE LA CONSTRUCTION DU SOUK HEBDOMADAIRE A LA COMMUNE TEMSAMANE – PROVINCE DRIOUCH ...
- **Buyer:** AGENCE REGIONALE D'EXECUTION DES PROJETS DE L'ORIENTAL      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 03/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043886](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043886&orgAcronyme=f8y).

#### 07/CONSA/2026/AREPO - index 143, consultation 1043872

- **Full stored title:** L’ETUDE ARCHITECTURALE, LA CONCEPTION ET LE SUIVI DES TRAVAUX DE LA CONSTRUCTION DU SOUK HEBDOMADAIRE A LA COMMUNE FIGUIG – PROVINCE FIGUIG ...
- **Buyer:** AGENCE REGIONALE D'EXECUTION DES PROJETS DE L'ORIENTAL      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 03/11/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043872](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043872&orgAcronyme=f8y).

#### 27/2026/BR - index 305, consultation 1038727

- **Full stored title:** Etude architecturale et suivi des travaux d’entretien et de réhabilitation de la salle couverte Kindy-Préfecture d’arrondissement Ben M’sick Casablanca. ...
- **Buyer:** REGION CASABLANCA-SETTAT      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 27/10/2026 14:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038727](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038727&orgAcronyme=a1z).

#### 26/2026/BR - index 312, consultation 1038710

- **Full stored title:** Etude architecturale et suivi des travaux d’entretien et de réhabilitation de la salle couverte SBATA-Préfecture d’arrondissement Ben M’sick Casablanca ...
- **Buyer:** REGION CASABLANCA-SETTAT      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 27/10/2026 12:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038710](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038710&orgAcronyme=a1z).

#### 39/RDOE/2026 - index 382, consultation 1041080

- **Full stored title:** ÉTUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CRÉATION D'UNE GARE ROUTIÈRE AU CENTRE DE BIR GANDOUZ ...
- **Buyer:** REGION de OUED EDDAHAB      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 27/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041080](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041080&orgAcronyme=x8h).

#### 43/2026 - index 523, consultation 1040107

- **Full stored title:** CONTROLE DES ETUDES ET SUIVI DES TRAVAUX POUR LA CONSTRUCTION DU SIÈGE DE LA DELEGATION PROVINCIALE DE LA SANTÉ ET DE LA PROTECTION SOCIALE DE MIDELT RELEVANT DE LA REGION DRAA TAFILALET ...
- **Buyer:** DIRECTEUR REGIONAL DE LA SANTE A LA REGION DE DARAA TAFILALET      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 26/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040107](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040107&orgAcronyme=q9t).

#### 18/DRAI/MS/BG/2026 - index 591, consultation 1028216

- **Full stored title:** ÉLABORATION DES ÉTUDES TECHNIQUES ET SUIVI DES TRAVAUX D’AMÉNAGEMENT DES ACCESSIBILITÉS POUR PERSONNES A MOBILITÉ RÉDUITE POUR 19 MOSQUÉES A LA RÉGION DE MARRAKECH – SAFI ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION MARRAKECH SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 26/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquees.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1028216](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1028216&orgAcronyme=f4g).

#### 32/2026/DRAIRSK/BG - index 681, consultation 1040722

- **Full stored title:** LE SUIVI ET LE CONTRÔLE DE QUALITÉ DES TRAVAUX DE RENFORCEMENT ET DE RÉHABILITATION DE LA MOSQUÉE OMAR IBNOU EL KHATAB ET SES DÉPENDANCES SISE A SIDI KACEM EN LOT UNIQUE. ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION RABAT SALE KENITRA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 23/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040722](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040722&orgAcronyme=f4g).

#### 02/2026 - index 825, consultation 1042102

- **Full stored title:** L’actualisation et l’établissement du plan d’aménagement extra muros de la commune de Taroudannt (province de Taroudannt) ...
- **Buyer:** AGENCE URBAINE DE TAROUDANNT      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 22/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / plan d'amenagement.
- **Selection reason:** City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042102](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042102&orgAcronyme=j8k).

#### CA02/RRE/2026 - index 878, consultation 1044268

- **Full stored title:** ÉTUDES URBANISTIQUES ET ARCHITECTURALES RELATIVES À L’EXTENSION DU PARC INDUSTRIEL D’AIN JOHRA, SITUÉE DANS LA COMMUNE D’AIN JOHRA – SIDI BOUKHELKHAL, PROVINCE DE KHÉMISSET ...
- **Buyer:** SOCIETE RABAT REGION EMERGENCE      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 22/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1044268](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1044268&orgAcronyme=g3h).

#### 02/CA.BG/2026 - index 900, consultation 1041972

- **Full stored title:** LES ETUDES ET LA CONCEPTION ARCHITECTURALE ET LE SUIVI DES TRAVAUX DU PROJET DE CONSTRUCTION DE (10) DIX TERRAINS DE SPORT EN GAZON SYNTHETIQUE AUX COMMUNES DE BIOUGRA, SIDI BIBI, MASSA, SIDI OUASSAY, SIDI BOUSHAB, OUED ESSAFA, ...
- **Buyer:** DIRECTION PROVINCIALE DE L’EDUCATION NATIONALE DE CHTOUKA AIT BAHA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 22/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; conception architecturale; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041972](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041972&orgAcronyme=p8x).

#### 05/BET/UCD/2026 - index 904, consultation 1044189

- **Full stored title:** ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE DEMOLITION D’UN BATIMENT EXISTANT ET CONSTRUCTION DU PROJET DU CENTRE UNIVERSITAIRE D’INFORMATION, D’ACCUEIL ET D’ORIENTATION, CUIAO/CARRER CENTER D’EL JADIDA EN LOT UNIQUE ...
- **Buyer:** PRESIDENT DE L'UNIVERSITE CHOUAIB DOUKKALI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 22/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; universitaire.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1044189](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1044189&orgAcronyme=z7x).

#### 04/2026 - index 966, consultation 1043781

- **Full stored title:** L’élaboration de la charte architecturale et paysagère de la ville D’es-Smara ...
- **Buyer:** AGENCE URBAINE DE LAAYOUNE      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 22/10/2026 09:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043781](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043781&orgAcronyme=j8k).

#### 03/BCT/UCD/2026 - index 967, consultation 1044187

- **Full stored title:** CONTROLE ET OPTIMISATION DES ETUDES TECHNIQUES ET CONTROLE DES TRAVAUX DE DEMOLITION D’UN BATIMENT EXISTANT ET CONSTRUCTION DU PROJET DU CENTRE UNIVERSITAIRE D’INFORMATION, D’ACCUEIL ET D’ORIENTATION, DU CUIAO/CARRER ...
- **Buyer:** PRESIDENT DE L'UNIVERSITE CHOUAIB DOUKKALI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 22/10/2026 09:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; controle; universitaire.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1044187](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1044187&orgAcronyme=z7x).

#### CA/02/2026/PUSMS - index 1071, consultation 1042909

- **Full stored title:** L’étude, la conception architecturale et le suivi des travaux de construction d’Une Scolarité et des Bureaux des Professeurs à l’École Supérieure de l’Éducation et de la Formation de Béni Mellal. En Lot unique. ...
- **Buyer:** PRESIDENCE DE L'UNIVERSITE SULTAN MOULAY SLIMANE      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 21/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; conception architecturale; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042909](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042909&orgAcronyme=z7x).

#### 21/DRAI/MS/BG/2026 - index 1082, consultation 1039143

- **Full stored title:** ETUDES GÉOTECHNIQUES RELATIVES AUX TRAVAUX DE RECONSTRUCTION DE DEUX MOSQUÉES DANS LA REGION DE MARRAKECH-SAFI ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION MARRAKECH SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 21/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / mosquees.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039143](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039143&orgAcronyme=f4g).

#### 05/2026/Y/SP - index 1180, consultation 1038336

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CREATION DE VINGT DEUX TERRAINS DE SPORT EN GAZON SYNTHETIQUE AUX COMMUNES TERRITORIALES YOUSSOUFIA, CHEMAIA, EL GANTOUR, SBIAT, LAKHOUALKA, RAS EL AIN, TIAMIM, JDOUR, SIDI CHIKER, ...
- **Buyer:** DIRECTION PROVINCIALE DE L’EDUCATION NATIONALE DE DE YOUSSOUFIA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 20/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038336](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038336&orgAcronyme=p8x).

#### 01/26/SS - index 1203, consultation 1040556

- **Full stored title:** Etude architecturale et le suivi des travaux de construction d’une salle multisports couverte à la commune SIDI SMAIL ...
- **Buyer:** Commune rurale de SIDI SMAIL      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 20/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040556](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040556&orgAcronyme=p1v).

#### 03/2026/DRANEFMS/DPANEF_EKS - index 1208, consultation 1043326

- **Full stored title:** La réalisation d’une étude de requalification et de mise à niveau du Site Récréatif Saguia Yaagoubia, avec assistance à la maîtrise d’œuvre, comprenant la restructuration des aménagements existants et la conception ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EAUX ET FORETS MARRAKECH-SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 20/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / professional architectural/planning context; see selection reason.
- **Selection reason:** Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043326](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043326&orgAcronyme=w7t).

#### 16/DAR/2026 - index 1280, consultation 1035747

- **Full stored title:** Etude et Assistance technique pour le suivi et la coordination des actions des acteurs, dans le cadre de la convention d’aménagement et de réhabilitation des oasis de Zagora 2026-2029, Province de Zagora. ...
- **Buyer:** GOUVERNEUR DE ZAGOURA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 20/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / suivi.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1035747](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1035747&orgAcronyme=g3h).

#### PX3129940/2026/DXR - index 1332, consultation 1040903

- **Full stored title:** l’assistance technique pour l’expertise de réhabilitation de l’usine Kasba Zidania. ...
- **Buyer:** OFFICE NATIONALE DE L'ELECTRICITE ET DE L'EAU POTABLE - BRANCHE ELECTRICITE      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 20/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / professional architectural/planning context; see selection reason.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040903](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040903&orgAcronyme=d4q).

#### CA/01/2026/ANRUR - index 1438, consultation 1043177

- **Full stored title:** l’Etude architecturale et suivi des travaux de construction d’une annexe du centre de la femme et de l’enfant, inscrite dans le cadre du Plan de Rénovation Urbaine du quartier Akachmir sis à la Commune d’El Hajeb - ...
- **Buyer:** Agence Nationale pour la Rénovation Urbaine et la Réhabilitation des Bâtiments Menaçant Ruine      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 19/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043177](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043177&orgAcronyme=j8k).

#### 06/2026/D.R.L - index 1452, consultation 1038859

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE RECONSTRUCTION DE LA MAISON DE JEUNES AL MADINA A LA VILLE DE BOUJDOUR-PROVINCE DE BOUJDOUR. ...
- **Buyer:** DIRECTEUR REGIONAL DU MINISTERE DE LA JEUNESSE ET DES SPORTS REGION LAAYOUNE - SAKIA HAMRA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 19/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038859](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038859&orgAcronyme=s3d).

#### 07/2026/DRAI/BH - index 1498, consultation 1043191

- **Full stored title:** L’ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE REFECTION ET DE REHABILITATION DE LA MOSQUEE CENTRALE IDA OUGUENIDIF COMMUNE IDA OUGUENIDIF A CHTOUKA AIT BAHA, lot unique ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION SOUS-MASSA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 19/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043191](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043191&orgAcronyme=f4g).

#### 12/AURS/2026 - index 1598, consultation 1042011

- **Full stored title:** l’élaboration du plan d’aménagement sectoriel (pas) de la zone littorale des communes d’Ameur et de sidi Abi al Kanadil ...
- **Buyer:** AGENCE URBAINE DE RABAT-SALE      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 16/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / plan d'amenagement.
- **Selection reason:** City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042011](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042011&orgAcronyme=j8k).

#### 15/AUKSS/2026 - index 1636, consultation 1040968

- **Full stored title:** Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère dématérialisée du centre émergent de Lalla Yettou relevant de la commune de Kceibya (lot unique). ...
- **Buyer:** AGENCE URBAINE DE KENITRA-SIDI KACEM      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 12:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040968](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040968&orgAcronyme=j8k).

#### 47/2026 - index 1653, consultation 1032046

- **Full stored title:** ETUDE GEOTECHNIQUE, HYDROGEOLOGIQUE ET CONTROLE DE LA QUALITE DES TRAVAUX DE RECONSTRUCTION DU CENTRE HOSPITALIER REGIONAL DE SOUSS MASSA- AGADIR. ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EQUIPEMENTS PUBLICS DU SUD      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / controle; centre hospitalier regional.
- **Selection reason:** Professional technical study/control at a hospital; regional reconstruction specialist scope or limited extension/interior works requires discipline and scale verification.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032046](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032046&orgAcronyme=o8p).

#### 59/2026/BG - index 1664, consultation 1040233

- **Full stored title:** LA RÉALISATION DES ÉTUDES ARCHITECTURALES ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DU SIEGE DE LA CAIDAT TATOFT A LA COMMUNE DE TATOFT A LA PROVINCE DE LARACHE. ...
- **Buyer:** GOUVERNEUR DE LA PROVINCE DE LARACHE      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 15/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / etudes architecturales; suivi; siege; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040233](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040233&orgAcronyme=g3h).

#### 14/AUKSS/2026 - index 1685, consultation 1040954

- **Full stored title:** Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère dématérialisée du centre émergent de Sidi Taibi (lot unique). ...
- **Buyer:** AGENCE URBAINE DE KENITRA-SIDI KACEM      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040954](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040954&orgAcronyme=j8k).

#### 04/AUM/2026/ANEPMS - index 1795, consultation 1041799

- **Full stored title:** RECEPTION DE FONDS DE FOUILLES ET CONTROLE DE LA QUALITE DES TRAVAUX DE CONSTRUCTION DU NOUVEAU SIEGE DE L’AGENCE URBAINE DE MARRAKECH ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EQUIPEMENTS PUBLICS DE MARRAKECH - SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / controle; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041799](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041799&orgAcronyme=o8p).

#### 01/CA/2026/CCisfm - index 1859, consultation 1043020

- **Full stored title:** Etude architecturale et suivi des travaux d’aménagement du Centre Multiservices de la Zone Industrielle Ain Chkef. ...
- **Buyer:** CHAMBRE DE COMMERCE D'INDUSTRIE ET DE SERVICES DE LA REGION DE FES - MEKNES      -
- **Procedure / category:** Consultation architecturale ouverte simplifiée / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte simplifiee.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043020](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043020&orgAcronyme=m1w).

#### 13/AUKSS/2026 - index 1861, consultation 1040937

- **Full stored title:** Etude d’élaboration de la Charte Architecturale, Urbanistique et Paysagère dématérialisée du centre émergent de Zirara (lot unique). ...
- **Buyer:** AGENCE URBAINE DE KENITRA-SIDI KACEM      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040937](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040937&orgAcronyme=j8k).

#### 02/2026/CMR - index 1875, consultation 1041797

- **Full stored title:** consultation architecturale relative à études et suivi des travaux de construction d’un piscine communale au centre de la commune territoriale de Masmouda ...
- **Buyer:** Commune rurale de MASMOUDA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 15/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041797](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041797&orgAcronyme=i1t).

#### 05/2026/ASBMS - index 1968, consultation 1041446

- **Full stored title:** ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE RECONSTRUCTION DE DEUX UNITES SCOLAIRES MODULAIRES DES DOUARS TOUNKSIF ET TOUG EL KHIR ET D’UNE UNITE SCOLAIRE DEFINITIVE DU DOUAR TIGHZA ET DE CINQ MOSQUEES DES DOUARS ...
- **Buyer:** CHEF D'AMÉNAGEMENT DE LA SURELEVATION DU BARRAGE MOKHTAR SOUSSI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 14/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquees.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041446](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041446&orgAcronyme=o8p).

#### 12/DRJCS/2026 - index 2092, consultation 1036136

- **Full stored title:** CONTROLE ET OPTIMISATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE CONSTRUCTION D’UN COMPLEXE SOCIO EDUCATIF A LA PREFECTURE DES ARRONDISSEMENTS DE MOULAY RACHID. ...
- **Buyer:** DELEGUE PREFECTORAL DE LA JEUNESSE ET DES SPORTS - PREFECTURE D'ARRONDISSEMENT CASA ANFA      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 14/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; controle.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036136](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036136&orgAcronyme=s3d).

#### 26/DRAI/BG/2026 - index 2095, consultation 1039354

- **Full stored title:** L’ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE REFECTION ET DE REHABILITATION DE CINQ (05) MOSQUEES DANS LA PREFECTURE DE MEKNES REGION DE FES MEKNES ...
- **Buyer:** DELEGUATION REGIONALE DES AFFAIRES ISLAMIQUES DE LA REGION FES-MEKNES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 14/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquees.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039354](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039354&orgAcronyme=f4g).

#### 12/PK/BG/2026 - index 2369, consultation 1035554

- **Full stored title:** contrôle technique des études et suivi des travaux de construction du Siège du District Assam A Kenitra Province De Kenitra. ...
- **Buyer:** GOUVERNEUR PROVINCIAL DE KENITRA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 13/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1035554](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1035554&orgAcronyme=g3h).

#### 10/DRJCS/2026 - index 2417, consultation 1043973

- **Full stored title:** ELABORATION DES ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE CONSTRUCTION D’UN COMPLEXE SOCIO EDUCATIF A LA PREFECTURE DES ARRONDISSEMENTS DE MOULAY RACHID. ...
- **Buyer:** DELEGUE PREFECTORAL DE LA JEUNESSE ET DES SPORTS - PREFECTURE D'ARRONDISSEMENT CASA ANFA      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 13/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043973](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043973&orgAcronyme=s3d).

#### 08/AUKSS/2026 - index 2422, consultation 1038657

- **Full stored title:** Etude d’élaboration du plan d’aménagement de la ville de Mechra Bel Ksiri (lot unique). ...
- **Buyer:** AGENCE URBAINE DE KENITRA-SIDI KACEM      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 13/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / plan d'amenagement.
- **Selection reason:** City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038657](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038657&orgAcronyme=j8k).

#### 43/SMTF/DM/BG/2026 - index 2516, consultation 1038281

- **Full stored title:** LE SUIVI ET LE CONTROLE DE QUALITE DES TRAVAUX DE REFECTION DE LA MOSQUEE AL MOHAMMADI ET SES DEPENDANCES A CASABLANCA, EN LOT UNIQUE ...
- **Buyer:** Direction des Mosquées      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 12/10/2026 14:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038281](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038281&orgAcronyme=f4g).

#### 16/DRSM/FSSH/2026 - index 2518, consultation 1041232

- **Full stored title:** LA RECEPTION DES FONDS DE FOUILLES, SUIVI ET CONTROLE DE QUALITE DES TRAVAUX DE RESTAURATION DE LA MOSQUEE TAGADIRT NDOUSAROU COMMUNE TIOUT ENDOMMAGEE PAR LE SEISME D’AL HAOUZ DANS LA PROVINCE DE TAROUDANT, en lot unique ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION SOUS-MASSA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 12/10/2026 14:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041232](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041232&orgAcronyme=f4g).

#### 27/PB/DE/BG/2026 - index 2647, consultation 1040870

- **Full stored title:** L’ELABORATION DES ÉTUDES TECHNIQUES ET LE SUIVI DES TRAVAUX DE TRAITEMENT DES JOINTS DE DILATATION AU NIVEAU DU BATIMENT SIEGE DE LA PROVINCE DE BOULEMANE ...
- **Buyer:** GOUVERNEUR DE BOULMANE      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 12/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040870](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040870&orgAcronyme=g3h).

#### 14/CPTT/2026 - index 2708, consultation 1020736

- **Full stored title:** Etude architecturale et suivi des travaux de construction de deux terrains de proximité à la ville d’EL OUATIA. ...
- **Buyer:** Province de TAN-TAN      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 12/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / etude architecturale; suivi.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1020736](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1020736&orgAcronyme=m8x).

#### 05/2026/Larache. - index 2784, consultation 1040257

- **Full stored title:** ÉTUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CONSTRUCTION D’UN CENTRE DU JOUR POUR PERSONNES AGÉES ET RETRAITÉES À LARACHE RELEVANT DE LA DIRECTION REGIONALE DE L’ENTRAIDE NATIONALE DE LA REGION DE TANGER TETOUAN AL ...
- **Buyer:** ENTRAIDE NATIONALE      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 09/10/2026 11:00 (TODAY_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040257](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040257&orgAcronyme=y5l).

#### 41/SMTF/DM/BG/2026 - index 2853, consultation 1038063

- **Full stored title:** LA RECEPTION DES FONDS DE FOUILLES, SUIVI ET CONTROLE DE QUALITE DES TRAVAUX DE RECONSTRUCTION DE LA MOSQUEE AL QODS ET SES DEPENDANCES PROVINCE DE JERADA, EN LOT UNIQUE ...
- **Buyer:** Direction des Mosquées      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 14:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038063](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038063&orgAcronyme=f4g).

#### 44/2026/ADERFES - index 2863, consultation 1040355

- **Full stored title:** Prestations topographiques relatives à l’amélioration des circuits touristiques au sein de la médina de Meknès - circuit ancienne médina - Tronçon : Rue Dar Smen – Rue Rouamzine, en lot unique ...
- **Buyer:** AGENCE POUR LE DEVELOPPEMENT ET LA REHABILITATION DE LA VILLE DE FES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 12:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / ancienne medina; medina.
- **Selection reason:** Topographic professional service inside an explicitly old-medina tourism circuit; architectural/conservation contribution is uncertain, so retain for detail rather than reject unrelated topography.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040355](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040355&orgAcronyme=g3h).

#### 23/2026/CAR/CAM - index 2878, consultation 1029607

- **Full stored title:** Etude Architecturale Conception Et Suivi Des Travaux De Construction De La Maison Du Quartier Touhamou A La Commune Ait Melloul –Prefecture Inzegane/Ait Melloul ...
- **Buyer:** Commune urbaine de AIT MELLOUL      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 08/10/2026 11:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1029607](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1029607&orgAcronyme=f9f).

#### 43/2026/ADERFES - index 2885, consultation 1040351

- **Full stored title:** Contrôle de la qualité et suivi des travaux d’amélioration des circuits touristiques au sein de la médina de Meknès - circuit ancienne médina - Tronçon : Rue Dar Smen – Rue Rouamzine, en lot unique. ...
- **Buyer:** AGENCE POUR LE DEVELOPPEMENT ET LA REHABILITATION DE LA VILLE DE FES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 11:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A+B / ancienne medina; medina; suivi; controle.
- **Selection reason:** Heritage place plus specialist topographic/quality-control service; confirm built conservation/design role rather than narrow engineering only.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1040351](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1040351&orgAcronyme=g3h).

#### CA10/2026/APDN - index 2892, consultation 1038026

- **Full stored title:** ETUDE ARCHITECTURALE ET LE SUIVI DU PROJET DE CONSTRUCTION DE DAR TALIB ET TALIBA ASSEBBAB PROVINCE DE GUERCIF ...
- **Buyer:** AGENCE POUR LA PROMOTION ET LE DEVELOPPEMENT ECONOMIQUE ET SOCIAL DES PREFECTURES ET PROVINCES DU NORD DU ROYAUME      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 08/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038026](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038026&orgAcronyme=a1t).

#### 03/2026 - index 2954, consultation 1039992

- **Full stored title:** ETUDE ARCHITECTURALE ET LE SUIVI DES TRAVAUX DE CONSTRUCTION DES MAGASINS AU SOUK HAD IMOULASS PROVINCE DE TAROUDANT ...
- **Buyer:** C.T. IMOULASS      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 08/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039992](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039992&orgAcronyme=f9f).

#### 40/2026/CHM6M - index 3030, consultation 1039330

- **Full stored title:** la réalisation des études techniques et le suivi des travaux de construction d’espace d’accueil aux urgences de l’hôpital Ar-razi relevant du Centre Hospitalo-Universitaire Mohammed VI à Marrakech. ...
- **Buyer:** CENTRE HOSPITALIER UNIVERSITAIRE MOHAMMED VI - MARRAKECH      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; universitaire.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039330](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039330&orgAcronyme=q9t).

#### 41/2026/CHM6M - index 3031, consultation 1039337

- **Full stored title:** le contrôle et l’optimisation des études techniques et suivi des travaux de construction d’espace d’accueil aux urgences de l’hôpital ARRAZI relevant du Centre Hospitalo-Universitaire Mohammed VI à Marrakech. ...
- **Buyer:** CENTRE HOSPITALIER UNIVERSITAIRE MOHAMMED VI - MARRAKECH      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 08/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; controle; universitaire.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039337](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039337&orgAcronyme=q9t).

#### 22/2026/CAR/CAM - index 3069, consultation 1029384

- **Full stored title:** Etude Architecturale Conception Et Suivi Des Travaux De Construction De La Maison Du Quartier Oubairouk A La Commune Ait Melloul –Prefecture Inzegane/Ait Melloul ...
- **Buyer:** Commune urbaine de AIT MELLOUL      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 08/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1029384](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1029384&orgAcronyme=f9f).

#### Taounate - index 3245, consultation 1039520

- **Full stored title:** ELABORATION DES ETUDES TECHNIQUES ET LE SUIVI DES TRAVAUX D’AMENAGEMENT DE LA MOSQUEE MOULAY BOUCHTA DANS LA PROVINCE DE TAOUNATE ...
- **Buyer:** MINISTERE DES HABOUS ET DES AFFAIRES ISLAMIQUES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 07/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039520](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039520&orgAcronyme=f4g).

#### 35/SMTF/DM/FSH/2026 - index 3316, consultation 1039163

- **Full stored title:** LA RECEPTION DES FONDS DE FOUILLES, SUIVI ET CONTROLE DE QUALITE DES TRAVAUX DE RESTAURATION DE LA MOSQUEE TACHENBACHET AL KHARIJI ET SES DEPENDANCES A MARRAKECH, EN LOT UNIQUE ...
- **Buyer:** Direction des Mosquées      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 06/10/2026 14:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1039163](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1039163&orgAcronyme=f4g).

#### 11/PK/BG/2026 - index 3472, consultation 1035544

- **Full stored title:** études techniques et suivi des travaux de construction du Siege District Assam à Kenitra - Province de Kenitra. ...
- **Buyer:** GOUVERNEUR PROVINCIAL DE KENITRA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 06/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1035544](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1035544&orgAcronyme=g3h).

#### 03/CA/2026/INDH/PG - index 3474, consultation 1036989

- **Full stored title:** Etude Architecturale et Suivi des Travaux d’extension de Dar Talib et Taliba Berkine à la commune de Berkine -Province de Guercif-. ...
- **Buyer:** Province de Guercif      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 06/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036989](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036989&orgAcronyme=g3h).

#### 34/SKAD/2026 - index 3487, consultation 1043142

- **Full stored title:** ÉTUDES ET SUIVI DES TRAVAUX D’AMÉNAGEMENT DE LA CORNICHE D’OUED SEBOU DE LA VILLE DE KÉNITRA ...
- **Buyer:** SOCIETE DE DEVELOPPEMENT LOCAL KENITRA AMENAGEMENT ET DEVELOPPEMENT      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 06/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; corniche.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043142](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043142&orgAcronyme=g3h).

#### 03/2026/DRDEAGADIR - index 3500, consultation 1033747

- **Full stored title:** Etudes techniques et suivi des travaux d’aménagement du siège de la Délégation des Domaines de l’Etat de Tiznit en lot unique ...
- **Buyer:** DIRECTEUR REGIONAL DE DOMAINES A AGADIR      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 06/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1033747](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1033747&orgAcronyme=g8e).

#### 90/AREPFM/2026 - index 3592, consultation 1038895

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CONSTRUCTION DU CENTRE DE SECOURS DE LA PROTECTION CIVILE AL ISMAILIA A LA VILLE DE MEKNES – REGION FES MEKNES ...
- **Buyer:** AGENCE REGIONALE D'EXECUTION DES PROJETS DE LA REGION FES-MEKNES      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/10/2026 12:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038895](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038895&orgAcronyme=e5w).

#### .01/ASBMS/2026. - index 3603, consultation 1038764

- **Full stored title:** ETUDES ARCHITECTURALES, SUIVI ET COORDINATION DES TRAVAUX DE RECONSTRUCTION DE DEUX UNITES SCOLAIRES MODULAIRES DES DOUARS TOUNKSIF ET TOUG EL KHIR ET D’UNE UNITE SCOLAIRE DEFINITIVE DU DOUAR TIGHZA ET DE CINQ MOSQUEES DES ...
- **Buyer:** CHEF D'AMÉNAGEMENT DE LA SURELEVATION DU BARRAGE MOKHTAR SOUSSI      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / etudes architecturales; suivi; mosquees; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038764](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038764&orgAcronyme=o8p).

#### CA/01/2026/BG - index 3613, consultation 1036114

- **Full stored title:** Etude architecturale et le suivi des travaux pour la construction des bâtiments administratifs au sein du siège de la Préfecture d’Arrondissements de Sidi Bernoussi. ...
- **Buyer:** GOUVERNEUR DE LA PREFECTURE D'ARRONDISSEMENT DE SIDI BERNOUSSI      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / etude architecturale; suivi; siege; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036114](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036114&orgAcronyme=g3h).

#### 89/AREPFM/2026 - index 3634, consultation 1038866

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE DEMOLITION ET RECONSTRUCTION D’UNE CASERNE DE GENDARMERIE ROYALE - PROVINCE D’IFRANE - REGION FES MEKNES ...
- **Buyer:** AGENCE REGIONALE D'EXECUTION DES PROJETS DE LA REGION FES-MEKNES      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/10/2026 11:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038866](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038866&orgAcronyme=e5w).

#### 05/2026/CA/BR/RGON - index 3649, consultation 1032428

- **Full stored title:** ETUDE ARCHITECTURAL ET SUIVI DES TRAVAUX D’AMÉNAGEMENT EXTÉRIEUR DU CENTRE MOHAMED VI DES HANDICAPES A LA VILLE DE GUELMIM PROVINCE DE GUELMIM ...
- **Buyer:** REGION DE GUELMIM - OUED NOUN      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/10/2026 10:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032428](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032428&orgAcronyme=m8x).

#### 195/2026/APDN - index 3666, consultation 1038949

- **Full stored title:** ETUDES TECHNIQUES ET SUIVI DES TRAVAUX DE RÉHABILITATION DES FAÇADES ET MISE À NIVEAU DE L’ENVIRONNEMENT DE KSAR MAJAZ, PROVINCE FAHS ANJRA. ...
- **Buyer:** AGENCE POUR LA PROMOTION ET LE DEVELOPPEMENT ECONOMIQUE ET SOCIAL DES PREFECTURES ET PROVINCES DU NORD DU ROYAUME      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 05/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B / etudes techniques; suivi; rehabilitation des facades.
- **Selection reason:** Technical studies and supervision of facade rehabilitation at Ksar Majaz; Ksar may be a locality, not a historic ksar. Verify heritage status and architectural intervention.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038949](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038949&orgAcronyme=a1t).

#### 21/2026/PB/DE/BG - index 3670, consultation 1031693

- **Full stored title:** CONCEPTION ARCHITECTURALE ET SUIVI DES TRAVAUX CONSTRUCTION DU NOUVEAU SIEGE DU PACHALIK BOULEMANE SIS A COMMUNE DE BOULEMANE. PROVINCE DE BOULEMANE ...
- **Buyer:** GOUVERNEUR DE BOULMANE      -
- **Procedure / category:** Consultation architecturale ouverte simplifiée / Services
- **Deadline:** 05/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / suivi; conception architecturale; siege; procedure: consultation architecturale ouverte simplifiee.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1031693](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1031693&orgAcronyme=g3h).

#### 03/ASG/2026 - index 3730, consultation 1038225

- **Full stored title:** "دراسة تقنية وتتبع أشغال مشروع تأهيل لقصر حنابو، بجماعة عرب الصباح الغريس، إقليم الرشيدية (الشطر الأول) – حصة فريدة '' ...
- **Buyer:** Commune rurale de AARAB SEBBAH GHERIS      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 05/10/2026 10:00 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** A?+B / Arabic: technical study; Arabic: supervision; Arabic: rehabilitation; Arabic: ksar/palace Hanabou.
- **Selection reason:** Arabic title: technical study and supervision of rehabilitation of Ksar Hanabou; built-heritage identity and professional scope need confirmation.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1038225](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1038225&orgAcronyme=q0x).

#### 05/2026/AUS - index 3799, consultation 1036470

- **Full stored title:** Appel d’offres ouvert National n° 05/2026 ayant pour objet l’étude architecturale et paysagère pour l’émergence d’un modèle de développement territorial autour du barrage Al Massira (province de Settat). ...
- **Buyer:** AGENCE URBAINE DE SETTAT      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 02/10/2026 10:30 (EXPIRED; relative to 2026-10-09).
- **Matched groups / terms:** B / etude architecturale.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036470](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036470&orgAcronyme=j8k).

#### 51/2026 - index 3844, consultation 1036758

- **Full stored title:** CONTROLE ET OPTIMISATION DES ETUDES TECHNIQUES ET CONTROLE DES TRAVAUX DE RECONSTRUCTION DU CENTRE HOSPITALIER REGIONAL DE SOUSS MASSA- AGADIR. ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EQUIPEMENTS PUBLICS DU SUD      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 17/11/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; controle; centre hospitalier regional.
- **Selection reason:** Professional technical study/control at a hospital; regional reconstruction specialist scope or limited extension/interior works requires discipline and scale verification.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1036758](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1036758&orgAcronyme=o8p).

#### 91/2026/CM - index 3889, consultation 1032760

- **Full stored title:** Consultation architecturale relative à l’étude et suivi des travaux de construction d’un centre d’animation et d’épanouissement des jeunes à Ain Slim à l’Arrondissement Ennakhil -Marrakech ...
- **Buyer:** Commune urbaine de MARRAKECH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 03/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032760](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032760&orgAcronyme=j0w).

#### 92/2026/CM - index 3890, consultation 1032762

- **Full stored title:** Consultation architecturale relative à l’étude et suivi du projet de mise à niveau de la piscine publique Sidi Youssef Ben Ali à la ville de Marrakech ...
- **Buyer:** Commune urbaine de MARRAKECH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 03/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032762](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032762&orgAcronyme=j0w).

#### 13/2026 - index 3929, consultation 1045882

- **Full stored title:** Elaboration des études techniques, assistance à la maîtrise d’ouvrage et suivi technique de l’exécution des travaux de démolition et de reconstruction du pole socio-éducatif Bab Doukkala relevant de la Direction ...
- **Buyer:** ENTRAIDE NATIONALE      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 02/11/2026 12:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi.
- **Selection reason:** Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045882](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045882&orgAcronyme=y5l).

#### 12/2026 - index 3934, consultation 1045875

- **Full stored title:** Contrôle des études techniques et contrôle de l’exécution des travaux de démolition et de reconstruction du pole socio-éducatif Bab Doukkala relevant de la direction régionale de l’Entraide Nationale de la région de ...
- **Buyer:** ENTRAIDE NATIONALE      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 02/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; controle.
- **Selection reason:** Professional study/design or project assistance for a recreational/socio-educational site; architectural scale and heritage context need confirmation.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045875](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045875&orgAcronyme=y5l).

#### 44/SMTF/DM/FSH/2026 - index 4023, consultation 1042977

- **Full stored title:** LA RECEPTION DES FONDS DE FOUILLES, SUIVI ET CONTROLE DE QUALITE DES TRAVAUX DE RESTAURATION DE LA MOSQUE « DERB EL HALFAOUI » ET SES DEPENDANCES A MARRAKECH, EN LOT UNIQUE ...
- **Buyer:** Direction des Mosquées      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 29/10/2026 14:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042977](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042977&orgAcronyme=f4g).

#### CA09/2026/AREFBK - index 4062, consultation 1046590

- **Full stored title:** Études architecturales et suivi des travaux d’extension de l’Académie Régionale d’Éducation et de Formation Beni Mellal-Khénifra. ...
- **Buyer:** ACADEMIE REGIONALE D'EDUCATION ET DE FORMATION BENI MELLAL-KHENIFRA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1046590](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1046590&orgAcronyme=p8x).

#### 88/2026/CM - index 4072, consultation 1032755

- **Full stored title:** Consultation architecturale relative à l’étude et suivi du projet de construction d’un centre d’addictologie et de réinsertion des jeunes à l’Arrondissement Ménara ...
- **Buyer:** Commune urbaine de MARRAKECH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032755](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032755&orgAcronyme=j0w).

#### 89/2026/CM - index 4073, consultation 1032757

- **Full stored title:** Consultation architecturale relative à l’étude et suivi du projet de construction d’un centre d’addictologie et de réinsertion des jeunes à l’Arrondissement Sidi Youssef Ben Ali ...
- **Buyer:** Commune urbaine de MARRAKECH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032757](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032757&orgAcronyme=j0w).

#### 90/2026/CM - index 4074, consultation 1032758

- **Full stored title:** Consultation architecturale relative à l’étude et suivi du projet de construction d’une piscine publique Al Massira 3 à la ville de Marrakech. ...
- **Buyer:** Commune urbaine de MARRAKECH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1032758](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1032758&orgAcronyme=j0w).

#### 31/2026/0324 - index 4113, consultation 1041362

- **Full stored title:** ETUDES TECHNIQUES ET LE SUIVI DES TRAVAUX DE REHABILITATION DU TRIBUNAL DE PREMIERE INSTANCE DE SEFROU, EN LOT UNIQUE. ...
- **Buyer:** DIRECTION PROVINCIALE DE LA JUSTICE FES      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 29/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / etudes techniques; suivi.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1041362](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041362&orgAcronyme=t5y).

#### C01/2026 - index 4177, consultation 1046806

- **Full stored title:** ETUDES ARCHITECTURALES POUR LA CONCEPTION ET LE SUIVI DE REALISATION DES TRAVAUX DE CONSTRUCTION DE BLOC DE BUREAUX DES ENSEIGNANTS ET LOCAUX ANNEXES AU SEIN DE LA FACULTE DES SCIENCES DHAR EL MAHRAZ FES ...
- **Buyer:** FACULTE DES SCIENCES DHAR EL MEHRAZ - FES      -
- **Procedure / category:** Concours Architectural / Services
- **Deadline:** 29/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / etudes architecturales; suivi; procedure: concours architectural.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1046806](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1046806&orgAcronyme=z7x).

#### 04./2026/CZ - index 4184, consultation 1043188

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE VIABILISATION DE LOTISSEMENT POUR LA REALISATION D'EQUIPEMENTS PUBLICS DANS LA VILLE DE ZEMAMRA. ...
- **Buyer:** Commune urbaine de ZMAMRA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043188](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043188&orgAcronyme=p1v).

#### 42/SMTF/DM/FSH/2026 - index 4227, consultation 1042969

- **Full stored title:** LA RECEPTION DES FONDS DE FOUILLES, SUIVI ET CONTROLE DE QUALITE DES TRAVAUX DE RESTAURATION DE LA MOSQUEE QUETTA ET SES DEPENDANCES A MARRAKECH, EN LOT UNIQUE ...
- **Buyer:** Direction des Mosquées      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 28/10/2026 14:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; controle; mosquee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042969](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042969&orgAcronyme=f4g).

#### 243/2026 - index 4240, consultation 1045852

- **Full stored title:** ASSISTANCE TECHNIQUES ET SUIVI DES TRAVAUX DE CONSTRUCTION D’EXTENSION DE L’HOPITAL DE PROXIMITE DE MRIRT RELEVANT DE LA PROVINCE DE KHENIFRA. -LOT UNIQUE- ...
- **Buyer:** AGENCE REGIONALE D'EXECUTION DES PROJETS DE LA REGION BENI MELLAL- KHENIFRA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 28/10/2026 11:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi.
- **Selection reason:** Professional technical study/control at a hospital; regional reconstruction specialist scope or limited extension/interior works requires discipline and scale verification.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045852](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045852&orgAcronyme=g8e).

#### 52/2026 - index 4277, consultation 1042059

- **Full stored title:** L’ACHEVEMENT DE LA MISSION ARCHITECTURALE RELATIVE AUX TRAVAUX DE RECONSTRUCTION DE LA MOSQUEE IDBAYISME – PROVINCE DE SIDI IFNI. ...
- **Buyer:** DIRECTION REGIONALE DE L'AGENCE NATIONALE DES EQUIPEMENTS PUBLICS DU SUD      -
- **Procedure / category:** Consultation architecturale ouverte simplifiée / Services
- **Deadline:** 28/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / mosquee; procedure: consultation architecturale ouverte simplifiee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042059](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042059&orgAcronyme=o8p).

#### 05/2026/AUSY - index 4359, consultation 1045886

- **Full stored title:** L’étude d’élaboration de la charte architecturale, urbanistique et paysagère du littoral et de son monde rural de la Province de Safi. -Lot unique- ...
- **Buyer:** AGENCE URBAINE DE SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 27/10/2026 12:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045886](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045886&orgAcronyme=j8k).

#### 04/2026/AUSY - index 4364, consultation 1045878

- **Full stored title:** L’étude d’élaboration de la charte architecturale, paysagère et urbanistique des centres ruraux émergents au niveau des provinces de Safi et de Youssoufia. -Lot unique- ...
- **Buyer:** AGENCE URBAINE DE SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 27/10/2026 11:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / charte architecturale.
- **Selection reason:** Architectural, urbanistic or landscape charter for the named territory; professional scope is clear but heritage/major-project relevance is not.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045878](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045878&orgAcronyme=j8k).

#### C01/2026 - index 4365, consultation 1045966

- **Full stored title:** ETUDES ARCHITECTURALES POUR LA CONCEPTION ET LE SUIVI DE REALISATION DES TRAVAUX DE CONSTRUCTION D’UN CENTRE DE CODE 212 AU CAMPUS DHAR EL MAHRAZ FES. ...
- **Buyer:** PRESIDENCE DE L'UNIVERSITE SIDI MOHAMED BEN ABDELLAH      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 27/10/2026 11:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / etudes architecturales; suivi; campus; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045966](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045966&orgAcronyme=z7x).

#### 05/.2026/CZ - index 4425, consultation 1044554

- **Full stored title:** ETUDES ARCHITECTURALES ET SUIVI DES TRAVAUX DE CONSTRUCTION DE DAR ETTALIB A LA VILLE DE ZEMAMRA ...
- **Buyer:** Commune urbaine de ZMAMRA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 05/11/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturales; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1044554](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1044554&orgAcronyme=p1v).

#### 20/BC.OT/2026 - index 4597, consultation 1042502

- **Full stored title:** ETUDES ARCHITECTURALE ET SUIVI DES TRAVAUX DE CONSTRUCTION D'UNE GARE ROUTIERE À LA COMMUNE D'OULED TEIMA PROVINCE DE TAROUDANT ...
- **Buyer:** Commune urbaine de OULAD TAIMA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 03/11/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etudes architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042502](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042502&orgAcronyme=f9f).

#### .195/2026/apdn - index 4665, consultation 1048247

- **Full stored title:** Études techniques et suivi des travaux de réhabilitation des façades et mise à niveau de l’environnement de Ksar Majaz, province Fahs - Anjra. ...
- **Buyer:** AGENCE POUR LA PROMOTION ET LE DEVELOPPEMENT ECONOMIQUE ET SOCIAL DES PREFECTURES ET PROVINCES DU NORD DU ROYAUME      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 02/11/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / etudes techniques; suivi; rehabilitation des facades.
- **Selection reason:** Technical studies and supervision of facade rehabilitation at Ksar Majaz; Ksar may be a locality, not a historic ksar. Verify heritage status and architectural intervention.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1048247](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1048247&orgAcronyme=a1t).

#### 43/2026/INDH/PT - index 4783, consultation 1044278

- **Full stored title:** ETUDE ARCHITECTURALE ET SUIVI DU PROJET CONSTRUCTION DE DAR AL OMOUMA A LA COMMUNE DE MAGHRAOUA - PROVINCE DE TAZA. ...
- **Buyer:** GOUVERNEUR DE LA PROVINCE DE TAZA      -
- **Procedure / category:** Consultation architecturale ouverte / Services
- **Deadline:** 29/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C / etude architecturale; suivi; procedure: consultation architecturale ouverte.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1044278](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1044278&orgAcronyme=g3h).

#### 42/2026/INDH/PT - index 4790, consultation 1043771

- **Full stored title:** étude architecturale et suivi du projet de construction d’un centre d’accueil pour mendiants et vagabonds à la Ville de Taza - Province de Taza. ...
- **Buyer:** GOUVERNEUR DE LA PROVINCE DE TAZA      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 29/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / etude architecturale; suivi.
- **Selection reason:** Architectural service/consultation for an ordinary sport or social facility; no automatic acceptance. Detail must demonstrate strategic scale or heritage relevance.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1043771](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1043771&orgAcronyme=g3h).

#### 01/2026/AUSY - index 4889, consultation 1045784

- **Full stored title:** L’étude d’élaboration du plan d’aménagement de la Ville de Safi, Province de Safi. -Lot unique- ...
- **Buyer:** AGENCE URBAINE DE SAFI      -
- **Procedure / category:** Appel d'offres ouvert / Services
- **Deadline:** 27/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B / plan d'amenagement.
- **Selection reason:** City-scale, coastal-sector or extra-muros planning may involve strategic architecture or historic urban context; title does not establish eligibility.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045784](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045784&orgAcronyme=j8k).

#### 03/2026/ARCH/DRAI/SM - index 4925, consultation 1045307

- **Full stored title:** LA CONCEPTION ARCHITECTURALE ET SUIVI DES TRAVAUX D’AMENAGEMENT DE LA MOSQUÉE CENTRALE DE FOUM ZGUID, PROVINCE DE TATA, REGION SOUSS MASSA. ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION SOUS-MASSA      -
- **Procedure / category:** Consultation architecturale ouverte simplifiée / Services
- **Deadline:** 26/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+C+D? / suivi; conception architecturale; mosquee; procedure: consultation architecturale ouverte simplifiee.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045307](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045307&orgAcronyme=f4g).

#### 17/DRAICS/BG/2026 - index 5002, consultation 1047344

- **Full stored title:** Elaboration des études techniques et suivi des travaux d’aménagement des accessibilités pour les personnes à mobilité réduite dans plusieurs mosquées dans les préfectures et provinces de la région de Casablanca Settat, ...
- **Buyer:** DELEGUE REGIONAL DES AFFAIRES ISLAMIQUES DE LA REGION GRAND CASABLANCA      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 21/10/2026 10:30 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; mosquees.
- **Selection reason:** Professional study/supervision or architectural mission concerning a mosque; historical status is unstated and specialist/control or ordinary repair scope may be outside ARCHERITAGE. Detail required.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1047344](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1047344&orgAcronyme=f4g).

#### 60/2026 - index 5061, consultation 1042325

- **Full stored title:** l’étude technique et suivi des travaux d’aménagement des locaux du service réanimation pédiatrique au centre hospitalier universitaire Mohamed VI Oujda. ...
- **Buyer:** REGION de ORIENTAL      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 20/10/2026 11:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etude technique; suivi; universitaire.
- **Selection reason:** Professional design/study/control at a university or higher-education site; title concerns a limited building/extension rather than proving a major campus commission.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1042325](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1042325&orgAcronyme=f8y).

#### 36/SKAD/2025 - index 5164, consultation 1047169

- **Full stored title:** ÉTUDES ET SUIVI DES TRAVAUX D’AMÉNAGEMENT DE LA CORNICHE D’OUED SEBOU DE LA VILLE DE KÉNITRA. ...
- **Buyer:** SOCIETE DE DEVELOPPEMENT LOCAL KENITRA AMENAGEMENT ET DEVELOPPEMENT      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 19/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / suivi; corniche.
- **Selection reason:** Professional service with architectural/public-building/landscape context, but heritage status, project scale or appropriate discipline is not established.
- **Confidence:** MEDIUM. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1047169](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1047169&orgAcronyme=g3h).

#### 19/AO/INV/2026/DPTANTAN - index 5192, consultation 1045952

- **Full stored title:** ETUDES TECHNIQUES ET SUIVI DES TRAVAUX D’AMÉNAGEMENTS DU SIEGE DE LA DIRECTION PROVINCIALE DE TANTAN/AREF GON ...
- **Buyer:** DIRECTION PROVINCIALE DE L’EDUCATION NATIONALE DE TANTAN      -
- **Procedure / category:** Appel d'offres ouvert simplifié / Services
- **Deadline:** 16/10/2026 10:00 (FUTURE_UNVERIFIED; relative to 2026-10-09).
- **Matched groups / terms:** B+D? / etudes techniques; suivi; siege.
- **Selection reason:** Professional study/design/control for public administrative premises; title does not prove major headquarters scale and may concern ordinary local or repair works.
- **Confidence:** LOW. **Official detail needed:** YES.
- **Stored source:** [PMMP consultation 1045952](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1045952&orgAcronyme=p8x).

## 7. What remains to validate

The current sample demonstrates useful candidate reduction and catches the four known examples, but the same snapshot was used to discover and adjust the rules. It is exploratory calibration, not a held-out evaluation. The 101 unresolved objects account for most retained entries. Their inclusion protects recall at the cost of more detail review; sending all of them through a slow full pipeline could recreate avoidable workload.

Before considering an application change, freeze the rules and evaluate a separately labeled set of notices, with independent official-detail judgments for selected and rejected boundary samples. Assess heritage relevance, service discipline, scale/budget and contractor eligibility separately from whether the deadline has passed. Examine Arabic coverage, incomplete titles, ordinary consultation exclusions and whether technical-only commissions fit ARCHERITAGE's actual delivery capabilities. Measure precision/recall only when those labels exist. No such official-detail fetch or application change has been executed here.

Targeted improvements demonstrated by this experiment:

1. Preserve service-versus-execution grammar, including study/supervision of restoration works.
2. Disambiguate non-built heritage words and place names before assigning priority.
3. Use procedure as a competition clue, with independent project qualification.
4. Handle Arabic and planning-service synonyms. Keep heritage-linked specialist objects in an explicit review tier.
5. Verify scale and discipline for campus, hospital, headquarters, mosque and ordinary-facility projects through targeted detail, not title claims.
6. Keep deadline/current status separate from relevance and avoid matching references by broad prefix.

## Final verdict

**B. It needs targeted improvements.** The simple title-led approach is promising as a cheap discovery triage step. The real index provides six strong heritage candidates, three qualified competition candidates and two plausible major-architecture candidates, while preserving 101 unresolved objects. Language gaps, incomplete objects and unproven scale/discipline prevent a reliable title-only acceptance decision. Finding the known references is useful evidence, but does not establish production readiness. No filter has been implemented in Radar 1 or deployed.
