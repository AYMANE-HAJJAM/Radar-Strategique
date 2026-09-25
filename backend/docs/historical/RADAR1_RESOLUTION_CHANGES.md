# Radar 1 official resolution and credible fallback

The approved relevance scorer, keywords and P1/P2/P3 rules were not changed.
Source verification is now separate from tender lifecycle (`open`, `closed`, etc.).
The existing Telegram menus, human decision actions and Radars 2–5 remain unchanged.

## Resolution and audit

Official recovery searches PMMP by exact reference, normalized reference, then title
fragment plus buyer. It then searches configured official buyer/institutional domains.
Only afterward does it inspect supporting aggregator links or request hosted public
page inspection. A blocked aggregator is never a prerequisite for official lookup.
Searches share the existing run budget; repeated lookup queries are cached.

Returned official notices must match the original identity, then pass the existing
HTML detail/title/buyer/deadline verification. PMMP singular/plural consultation routes
and `index.php`/`index.php5` variants are recognized; verified URLs get a canonical
PMMP identity. An observed document URL can identify a detail-page GET target, but is
never accepted as verification by itself. No DCE downloads, forms or challenge bypass.

Three persisted `resolution_state` values distinguish:

- `VERIFIED_OFFICIAL`: exact official detail verified.
- `UNVERIFIED_BUT_CREDIBLE`: credible whitelisted procurement source and strong,
  consistent reference/buyer/title identity; official verification still pending.
- `UNRESOLVED`: weak, conflicting or otherwise ineligible discovery; not retained.

Existing JSON metadata stores discovery URL, official URL, source type, attempted
searches, resolution error and confidence. The nested resolution audit calls this
verification value `source_status`; the existing top-level `source_status` retains
the tender lifecycle so expiry and closed-state filters continue working. No migration.

Credible fallback requires Moroccan scope and no identity/source conflict. Known
closed, cancelled, awarded, expired or future-dated evidence remains excluded, and
the existing freshness validator still runs. Strong identities with no dates can
enter manual review with an unclear-deadline warning; the existing approval guard
prevents approving undated evidence as current. No dates are invented.

403 failures are cached per URL for the run. A 429 suspends that host for the rest
of the run. There are no immediate retries; later runs can try again. HTTP counters
count actual failed fetches, not repeated cache/suspension checks. Successfully
recovered runs with limitations are `PARTIAL`; failures with no useful yield remain
`DEGRADED`. Search/provider errors and parser errors remain visible separately.

## Queue, DCE and persistence

Credible fallback enters the existing pending queue, always requiring human review
and without paid AI classification. Cards show **Lien officiel à confirmer** and
**Ouvrir la source**; verified notices use **Ouvrir l’offre**. Details identify the
aggregator/institutional listing and explicitly mark official verification pending.
Fallback clears all DCE claims. Absent verified availability displays **DCE : non vérifié**.

Fallback identity does not treat a shared listing URL as a unique offer. Reference,
buyer and title continue identifying the tender; consistent reference variants or
later buyer enrichment can resolve to the same stored record. Conflicting identities
still require reconciliation. Pending fallbacks can retry resolution on rediscovery;
unchanged human decisions remain remembered.

Evidence-only official enrichment updates the same record, records `OFFICIAL_ENRICHED`,
and preserves its human decision and commercial timestamp. A changed deadline, title,
buyer or other commercial field uses the existing UPDATED/reopening flow. No new
workflow action or menu was introduced.

## Validation

- Full suite: **253 passed**; `compileall` passed for `app`, `scripts`, `tests`.
- Tests prohibit real HTTP. Coverage includes blocked-source recovery, exact-reference
  and title/buyer resolution, credible/weak identities, retry limits, warning/buttons,
  DCE clearing, unchanged fallback rediscovery, shared-listing identities, later
  official enrichment, preserved human decisions, freshness vetoes and PMMP variants.
- All existing relevance regression cases and Radar 2–5 tests pass.

Both live validations used `--dry-run --isolated`: paid search only, no classification,
production Result writes or Telegram sends. Counts below are observations, not a claim
of deduplicated commercially useful architecture projects.

| Metric | General run | Known-reference control |
|---|---:|---:|
| Search calls | 1 (ceiling 8) | 6 (ceiling 6) |
| Tender observations | 20 | 1 |
| Passed business gate, including ambiguous | 19 | 1 |
| Verified official retained | 19 | 0 |
| Unverified credible retained | 0 | 1 |
| Unresolved | 0 | 0 |
| Relevance rejected | 1 | 0 |
| HTTP 403 | 0 | 1 |
| HTTP 429 | 0 | 0 |
| Final kept | 19 | 1 |
| P1 / P2 / P3 kept | 0 / 0 / 19 | 0 / 1 / 0 |
| Health | HEALTHY | PARTIAL |

The general run stopped after sufficient yield from a PMMP listing. **18 of its 19
retained titles score zero and require business review under the unchanged relevance
policy.** The other scores +2. This demonstrates official verification, not 19 confirmed
architecture opportunities. No relevance rules were adjusted to change these results.

The control reference `CA11/2026/APDN` was not officially resolved on this run. Its
credible P2 discovery survived HTTP 403 with a transparent warning. This is a live
fallback result, not a falsely claimed official-resolution success. The reference
remains an opt-in CLI control and is not hard-coded in production collection.

Artifacts: `radar1-resolution-tests.txt`, `radar1-resolution-live.json`,
`radar1-resolution-control.json` and their console `.txt` reports.

Commands:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m compileall -q app scripts tests
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 8 --max-candidates 30 --report-json radar1-resolution-live.json
.venv/Scripts/python.exe -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated --max-queries 6 --max-candidates 12 --control-reference CA11/2026/APDN --report-json radar1-resolution-control.json
```

Implementation: collector, new `collectors/markets/resolution.py`, access-limited page
reader, official resolver, PMMP normalization, MarketCandidate/validator, existing
review service and presenters; narrow fallback identity/enrichment support in shared
dedup/persistence/orchestrator code. Official buyer-site searches remain bounded by
the existing configured whitelist; this change does not trust arbitrary domains.
