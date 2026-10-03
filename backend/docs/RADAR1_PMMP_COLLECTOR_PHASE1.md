# Radar 1 PMMP listing collector — phase 1

**Date:** 2026-10-02

**Scope:** Discovery only. Legacy keyword discovery and Marché Facile stay in place. Production Radar 1 still calls `MarketsCollector.collect`. No relevance-policy change, no dedup or persistence change, no migration, no Radars 2–5, no UI.

The new entry point is `new_pmmp_collector()`. The old entry point is `legacy_discovery()`.

---

## Old discovery boundary

Radar 1 discovery today is keyword search over public pages, then an early relevance decision inside the same collector. That path is unchanged and is now named.

### A. Discovery we intend to replace later

These pieces choose what to look for. They are still the production path.

| Piece | Role |
|---|---|
| `app/modules/radar1_markets/discovery_strategies.py` | Keyword families and page plans. `FAMILY_TERMS`, `direct_discovery_plan`, `build_discovery_plan`, `PmmpDiscoveryStrategy`, `AggregatorDiscoveryStrategy`, `InstitutionalDiscoveryStrategy` |
| `MarketsCollector.legacy_discovery` in `collector.py` | Runs the plan. `collect()` delegates here and is still what `COLLECTORS['RADAR_1_MARKETS']` uses |
| `MarketsCollector._direct_page` | One GET of a keyword search URL or a Marché Facile sector URL. Stops at `RADAR1_QUERY_OBSERVATION_LIMIT` (20) rows from `extract_rows` |
| `MarketsCollector._query` | Paid search fallback (`provider.search`) when direct discovery has not met the target |
| `MarketsCollector._discover` / `_process` | Turns a search hit into an observation and applies preliminary plus final relevance before anything reaches the orchestrator |

PMMP search entry point: `direct_discovery_plan` builds

`https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseAdvancedSearch&searchAnnCons&keyWord=<term>`

Query families and the exact terms of each family:

| Family | Terms executed as `keyWord` |
|---|---|
| architecture | `etudes architecturales patrimoine`, `conception architecturale grand projet`, `diagnostic architectural patrimoine` |
| competition | `concours architectural`, `concours de conception architecturale` |
| major_architecture | `maitrise oeuvre grand equipement public`, `conception suivi grand projet architectural` |
| rehabilitation | `etude restauration conservation patrimoine`, `etude rehabilitation reconversion patrimoine` |
| urbanism | `medina ancienne ville`, `revitalisation centre historique` |
| territorial_studies | `etude valorisation patrimoine culturel`, `etude circuits sites patrimoniaux` |
| project_management | `amo plan sauvegarde patrimoine`, `suivi travaux restauration patrimoniale`, `diagnostic inventaire patrimonial` |
| built_environment | `bati ancien menacant ruine`, `remparts murailles fortifications`, `kasbah ksar fondouk` |
| technical_studies | `etude technique consolidation batiment historique` |

Each PMMP keyword page is a single results page of about 10 rows. There is no second page. The run also caps observations at `RADAR1_MAX_CANDIDATES` (100).

Marché Facile collector: the same plan inserts

`https://marchefacile.ma/appels-offres/secteur/services-architecturales-et-topographiques`

and `?page=2`. Rows are parsed by `extract_rows`. There is no separate Marché Facile class.

Paid-search fallback: after direct pages, `build_discovery_plan` emits `site:marchespublics.gov.ma "<term>"` queries, plus aggregator `restauration patrimoine Maroc` and institutional queries. `MarketsCollector._query` calls the configured search provider. A control-reference mode uses the same paid search. Basic PMMP listing collection does not use this.

Where candidates enter the common pipeline: `MarketsCollector.collect` returns the list the orchestrator already consumes (`AgentOrchestrator._collect`, then normalize, dedup, and save). That return value is still the legacy relevance-filtered list. The new collector is not in that chain.

### B. Reusable pieces left untouched

| Piece | Why it stays |
|---|---|
| `app/integrations/pmmp/parser.py` `enrich_detail`, `verify_detail`, `extract_rows` | Official detail parsing and the existing listing-row parser |
| `app/integrations/pmmp/client.py` `canonical_detail_url`, `is_direct_notice` | Stable PMMP detail identity |
| `app/integrations/http/html.py` `PublicPages`, `Page` | Existing fetch and HTML reader used by the legacy path |
| `MarketsRadarAgent.normalize_candidate` | Orchestrator normalization |
| `policy.py` `evaluate_relevance` and the validators | Approved ARCHERITAGE final policy |
| `app/core/dedup.py`, result save, `ResultObservation`, review workflow | Unchanged. The new index does not write results |
| `SearchRun` tracking | Still records the legacy run |

`extract_rows` still slices to 100 hits per page. The new collector does not use that slice. It reads the PMMP result DOM directly.

---

## New collector

File: `app/modules/radar1_markets/pmmp_listing_collector.py`

```text
new_pmmp_collector(mode='full' | 'incremental' | 'reconciliation', index=None)
  GET the public consultations-en-cours form
  POST "Lancer la recherche" when the response is the form, not a result table
  parse listing rows
  POST the Prado next control until a real stop condition
  compare each row to ListingIndex
  return observations plus the updated index
```

It does not import the relevance policy, a search provider, or a model client.

A listing keeps only fields the row actually contains:

- source `marchespublics.gov.ma`
- `consultation_id` and `organization` (hidden `refCons` / `orgCons`)
- reference, object/title, buyer
- publication date, deadline (date and time when shown)
- procedure, category (`Travaux`, `Services`, or `Fournitures`)
- location
- detail URL built with `canonical_detail_url`

Estimate is left empty. The listing row observed on 2026-10-02 does not publish an estimate. The collector does not invent one.

Identity, in order:

1. source + PMMP consultation id + organization acronym
2. otherwise the canonical detail URL
3. otherwise source + reference + buyer

Reference alone is not an identity. Two notices can share a reference under different buyers when the PMMP id is missing.

The content fingerprint covers title, buyer, deadline, publication date, procedure, category, location, detail URL, reference, and estimate when present. A change in any of those is `UPDATED`.

Outcomes are `NEW`, `UNCHANGED`, `UPDATED`, and `DUPLICATE`. `DUPLICATE` is a second copy of the same identity inside one crawl. It does not become a second `NEW`.

---

## Pagination observed on 2026-10-02

Two public GETs and a few POSTs. This was not a full crawl and not a Radar 1 production run.

| Listing | What it is | Count shown |
|---|---|---|
| `EntrepriseAdvancedSearch&searchAnnCons` | Search form for consultations en cours. Dates on the form were 02/10/2026–02/04/2027, with a calculated window 02/04/2026–02/10/2026 | No result table until search is launched |
| POST `lancerRecherche` on that form | Current consultation results. Page size offers 10, 20, 50, 100, 500. The default response is 10 rows | **3,817 results, 382 pages** |
| `EntrepriseAdvancedSearch&AllCons` | Full consultation archive, not the open baseline | **100,766 results, 10,077 pages** |

Paging is not a `page=` query. The result form carries an 80 KB `PRADO_PAGESTATE`.

- Setting `numPageTop` / `numPageBottom` to 2 did not change the rows.
- Posting `PRADO_POSTBACK_TARGET=ctl0$CONTENU_PAGE$resultSearch$PagerTop$ctl2` did. Page 1 ids started at `1040952`. The next page started at `963011`, `1013524`, `1040198`.
- On page 1, first and previous are images. Next and last are links whose href is `javascript:;//ctl0_CONTENU_PAGE_resultSearch_PagerTop_ctl2` (and `_ctl3` for last).

The collector uses that next control. It does not guess page numbers.

---

## How full crawl works

`mode='full'` is the baseline walk of the consultations-en-cours result, not the 100,766-row archive.

Stop only when one of these is true:

1. The next-page link is absent (`final_page`).
2. The declared page count (`nombrePageTop`) has been fetched (`final_page`).
3. The next response repeats a previous page's consultation-id set (`pagination_loop`).
4. A result page has no rows and no next link (`empty_page`).

There is no default 100-row cap. `max_pages` exists only so a caller can bound a trial. A full baseline should leave it unset.

Requests go through `PmmpHttp`: host limited to `marchespublics.gov.ma`, HTML only, 2 MB page limit, 0.35 seconds between requests, three attempts on timeout, connection errors, and HTTP 500/502/503/504. HTTP 403 and 429 are not retried. Each page and the stop reason are logged as `pmmp_listing`.

A live full baseline is about 382 requests after the search post. This pass did not run that crawl.

---

## How incremental crawl works

`mode='incremental'` walks from the first result page. On 2026-10-02 that page held higher consultation ids than the following page.

- An unseen identity is `NEW` and resets the stable-page count.
- A changed fingerprint is `UPDATED` and resets it.
- A matching fingerprint is `UNCHANGED`.
- After `overlap_pages` consecutive pages that contain only `UNCHANGED` rows (default 2), the crawl stops with `incremental_overlap`.
- It does not stop on the first known row. A page that mixes new and known rows is not a stable page.
- With an empty index, nothing is unchanged, so incremental walks through to the site's last page.

`mode='reconciliation'` uses the same walk as full crawl and the same comparison. It ignores the overlap stop, so an older row that PMMP edits is still visited. Nothing schedules it.

---

## NEW, UPDATED, UNCHANGED

`ListingIndex` is a dict of identity to fingerprint. `classify` writes the new fingerprint and returns the state. `to_dict` and `from_dict` let a caller keep that dict between calls.

`SearchRun`, `Result`, and `ResultObservation` cannot store this baseline cleanly:

- `results` and `result_observations` hold notices that already passed the final policy and were saved. A listing index of every open consultation would write rejects and non-architectural notices into the review queue.
- `source_states` is one row per source URL (etag and page hash), not one row per consultation.
- `search_runs.run_metadata` could hold a JSON blob, but it is not an index, it is rewritten each run, and a few thousand fingerprints do not belong in a run log.

A durable cross-run baseline needs a new table (identity, fingerprint, listing fields, last seen). **No migration was created.** Until that table exists, incremental mode remembers listings only for the life of the `ListingIndex` the caller passes in. Tests keep it in memory.

---

## Tests

`tests/modules/radar1/test_pmmp_listing_collector.py` uses scripted HTML. It does not call PMMP.

Covered: multi-page collection and final-page stop, repeated-page stop, `NEW` / `UNCHANGED` / `UPDATED`, overlap that continues past the first known page, reconciliation past known pages, transient HTTP retry, duplicate identity, reference-plus-buyer identity, search-form submission, and the absence of a model or paid-search client.

The Settat notice `04/2026/AUS` is only in the test fixture, on a later page among other rows. The collector source does not contain that reference. The fixture asserts the crawl returns it when the page contains it.

Results on 2026-10-02:

- The new tests plus the existing discovery and collection diagnostics: 47 passed.
- Full `tests/modules/radar1`: **397 passed**.

---

## Before switching production traffic

1. Decide the listing-index table and add the migration in a later change. Do not put every open notice into `results`.
2. Run one non-production full crawl (`mode='full'`) and keep the returned `ListingIndex`. Confirm the volume is near the 3,817 current consultations, and confirm `04/2026/AUS` is present only if PMMP still lists it.
3. Compare that set with one legacy keyword run and with Marché Facile rows. Keep both until the unique contribution is measured.
4. Only then place the new collector in front of the existing detail enrichment and ARCHERITAGE policy, still without deleting `legacy_discovery`.
5. Leave dedup, review, and the UI on the existing save path.
