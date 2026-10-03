# Radar 1 PMMP collector — phase 2

**Date:** 2026-10-02  
**Scope:** Durable listing index and incremental sync. Production Radar 1 still uses `MarketsCollector.legacy_discovery`. ARCHERITAGE policy, Radars 2–5, Marché Facile, and legacy keyword discovery are unchanged.

Phase 1 proved a live full crawl of the consultations-en-cours board (3,821 rows / 3,820 unique, including `04/2026/AUS`). Phase 2 stores that board memory without writing Radar business results.

---

## Schema added

Table: `pmmp_listing_index`

| Column | Purpose |
|---|---|
| `source` | Always `marchespublics.gov.ma` for this collector |
| `consultation_id` | PMMP `refConsultation` when present |
| `organization` | PMMP `orgAcronyme` |
| `detail_url` | Canonical official detail URL |
| `reference` | Buyer-facing reference |
| `buyer` | Contracting authority |
| `title` | Object / title from the listing row |
| `publication_date` | Listing date string when present |
| `deadline` | Deadline string when present |
| `procedure` | Procedure label when present |
| `category` | Travaux / Services / Fournitures when present |
| `location` | Execution place when present |
| `fingerprint` | Content digest of listing fields |
| `identity_key` | Stable identity digest |
| `first_seen_at` | First index insert |
| `last_seen_at` | Updated on every observation |
| `last_changed_at` | Updated only when the fingerprint changes |

This table is not the Radar `results` queue. Irrelevant notices stay here and do not become review cards.

**Migration id:** `a1b2c3d4e5f6`  
**Revises:** `c4d8e1a72b05`

Indexes:

- unique `identity_key`
- unique `(source, consultation_id)` where `consultation_id IS NOT NULL`
- non-unique `(source, consultation_id)` lookup helper

---

## Identity strategy

Lookup order for a live listing:

1. Prefer `(source, consultation_id)` when a PMMP consultation id is present.
2. Otherwise use `identity_key`.

`identity_key` is the same digest the phase-1 collector already computes:

1. source + consultation id + organization, when both PMMP ids exist
2. otherwise canonical detail URL
3. otherwise source + reference + buyer

Reference alone is never enough. Two notices with the same reference and different buyers remain distinct when there is no consultation id.

When the same consultation id reappears with a changed organization or other fields, the existing row is updated. A second row is not inserted.

---

## Fingerprint strategy

Unchanged from phase 1. Digest of:

title, buyer, deadline, publication date, procedure, category, location, detail URL, reference, estimate (when present)

Same fingerprint → `UNCHANGED`  
Different fingerprint → `UPDATED`  
No prior row → `NEW`

`last_seen_at` advances for every known observation. `last_changed_at` advances only for `NEW` and `UPDATED`.

---

## Baseline behavior

`import_baseline(records)` loads an offline full-crawl dataset (dicts, `PmmpListing` objects, or index rows) into `pmmp_listing_index`.

| Case | State | Side effect |
|---|---|---|
| Unknown identity | `NEW` | Insert index row |
| Known + same fingerprint | `UNCHANGED` | Refresh `last_seen_at` |
| Known + changed fingerprint | `UPDATED` | Refresh fields, fingerprint, `last_seen_at`, `last_changed_at` |

No `Result` or `ResultObservation` rows are created.

---

## Incremental behavior

`sync_listings(mode='incremental')` runs the existing HTTP collector with a `DurableListingIndex` adapter.

1. Start on the newest live page.
2. Classify each listing against the durable table.
3. Continue through pages that contain any `NEW` or `UPDATED` listing.
4. Count consecutive pages whose rows are only `UNCHANGED`.
5. Stop when that count reaches the overlap setting.

`actionable` on the sync result is only `NEW` and `UPDATED`. `UNCHANGED` and in-crawl `DUPLICATE` rows stay out of the later relevance handoff.

Default overlap: **`RADAR1_PMMP_OVERLAP_PAGES = 3`**. Override with the `overlap_pages` argument.

---

## Reconciliation behavior

`sync_listings(mode='reconciliation')` walks the full live board (same stop conditions as phase-1 `full`) and refreshes the durable index. Overlap does not stop it. Nothing schedules it yet.

Use this to catch older notices that PMMP edits or reorders after the first baseline.

---

## Stopping rule (incremental)

Stop with `incremental_overlap` only when:

- at least one listing page was fetched, and
- the last `overlap_pages` consecutive pages contained only `UNCHANGED` identities (no `NEW`, no `UPDATED`), and
- those pages were not empty.

Do not stop on the first known row. A page that mixes known and unknown rows resets the stable-page counter. Slight board reordering therefore still gets an overlap cushion before the crawl ends.

Other stop reasons from the collector remain: `final_page`, `pagination_loop`, `empty_page`, `max_pages`.

---

## Downstream handoff

```text
sync_listings(...) → ListingSyncResult
  .observations   # every row seen this run
  .actionable     # NEW + UPDATED only
```

`actionable_listings(result)` returns that list. Later relevance / detail enrichment should consume only those items. Phase 2 does not call detail enrichment, AI, or paid search for `UNCHANGED` rows.

Production `MarketsCollector.collect` is still the keyword path. Nothing in the orchestrator calls `sync_listings` yet.

---

## Cost guarantee

Index sync uses HTTP, HTML parsing, and database comparison only. The sync module does not import a search provider or a model client. Tests assert that.

---

## Files

| File | Role |
|---|---|
| `app/db/models/pmmp_listing_index.py` | ORM table |
| `migrations/versions/a1b2c3d4e5f6_pmmp_listing_index.py` | Alembic migration |
| `app/modules/radar1_markets/pmmp_listing_index.py` | Durable adapter, baseline import, sync, actionable handoff |
| `app/modules/radar1_markets/pmmp_listing_collector.py` | Unchanged crawl engine from phase 1 |
| `tests/modules/radar1/test_pmmp_listing_index.py` | Phase-2 tests |

---

## Test results

2026-10-02:

- `tests/modules/radar1/test_pmmp_listing_index.py` + collector tests: 22 passed
- `tests/modules/radar1`: **407 passed**
- full backend suite: **844 passed**

Covered: baseline insert, unchanged second run, updated listing, new listing, duplicate consultation id, fallback identity, `last_seen_at`, incremental overlap, reconciliation, restart persistence, no paid calls, actionable handoff.

---

## Before production switch

1. Apply migration `a1b2c3d4e5f6` in each environment.
2. Import the validated full-crawl dataset with `import_baseline`.
3. Run a non-production incremental sync and confirm stop reason / actionable counts.
4. Wire `actionable` into detail enrichment and ARCHERITAGE policy behind a feature flag.
5. Compare unique contribution against legacy keyword discovery and Marché Facile.
6. Only then replace `MarketsCollector.collect` for production traffic, still keeping legacy code until that comparison is accepted.
