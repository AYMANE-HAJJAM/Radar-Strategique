# Code Review Refactor Report

Deep senior-level code-quality pass on Telegram Radar. **No architecture redesign. No intentional product behavior change. No migrations.**

---

## 1. Key code-quality problems found

### CRITICAL
- None that blocked correctness of the approved product contract.

### HIGH VALUE
| Module | Issue | Why it matters | Fix | Behavior risk |
|--------|--------|----------------|-----|---------------|
| `result_review_service.page` | Radars 2–5 loaded full result tables then sliced in Python | UI N× cost grows with backlog | SQL `OFFSET`/`LIMIT` (+ count when needed) | Low — R2–5 have no Python eligibility gate |
| `result_review_service` | `_official_domains(app)` recomputed per card | Repeated config work on every queue card | Cache once per page/detail call | None |
| `dedup_service.find_global_source` | Full-table scan for every candidate | Cross-radar hot path O(n) always | Indexed `url_key` fast path; scan only for title/legacy | Low — URL equality still verified |
| Collectors ×5 | Duplicated `fold` / `parse_date` | Drift risk, harder tests | `app.common.text.fold_text` / `parse_fr_date` | None if same formats |
| `market_review_service` shim | Misleading name + extra indirection | Import confusion | Retarget tests; delete shim | None |
| Handlers / targeted / jobs | Broad `except Exception` with silent or weak context | Hard ops debugging | `log_failure` then preserve UX | None |
| Callback parsers | Magic `10000` / `5` / debounce literals | Inconsistent limits | `MAX_PAGE_INDEX`, `PAGE_SIZE`, debounce constants | None |

### MEDIUM
| Module | Issue | Fix |
|--------|--------|-----|
| `result_workflow_service.changed_fields` | Four near-identical metadata loops | Table-driven groups + `_meta_changed` |
| `markets.parse_market_callback` | Duplicated run-callback regex vs `run_queue` | Delegate run family to `run_queue.parse` |
| `handlers` | Identical if/else for Radar 1 vs others | Single `show_page` call |
| `callbacks.parse_callback` | Hardcoded radar code set | Use `RADAR_CODES` |
| `current()` | Still called legacy `architecture_pending` | Use `business_queue_eligible` |

### LOW / STYLE ONLY (mostly deferred)
- Cosmetic whitespace in older scripts
- Historical docs still mention `market_review_service` (left as history)
- Further Radar 1 queue SQL pagination blocked by Python `business_queue_eligible` gate (keep streaming + filter)

---

## 2. High-value refactors performed

1. Shared text utilities (`app/common/text.py`) wired through collectors.
2. Shared pagination / debounce constants (`app/common/constants.py`).
3. SQL pagination for non–Radar-1 queues.
4. Domains-once + `MAX_PAGE_INDEX` in review service.
5. Cross-radar dedup URL-key fast path.
6. Workflow `changed_fields` consolidation.
7. Markets callback parse via `run_queue`.
8. Shim removal + test retarget to `result_review_service`.
9. Exception logging in targeted search, job submission, completion path (already logged).
10. Dead identical handler branch removed.

---

## 3. Manual repetition → iteration / config

- Run-scoped callback patterns: one `run_queue.parse(prefix)` used by markets + compact review.
- Page size / max index / debounce: single constants module.
- Radar code allowlist in Telegram top-level callbacks: `RADAR_CODES`.
- Metadata field comparison lists: `_RAW_META` + `_TEXT_META_GROUPS`.

---

## 4. Duplicate logic removed

- Collector fold/date implementations → thin wrappers over `fold_text` / `parse_fr_date`.
- Markets run-callback regex duplication → `run_queue.parse`.
- `market_review_service` re-export shim deleted.
- Live architecture doc no longer advertises the shim.

---

## 5. DB / query improvements

- **Radars 2–5 `page()`:** `OFFSET`/`LIMIT` (and `COUNT` when `include_total`).
- **Radar 1 `page()`:** still streams with `yield_per` + `_unique_eligible` (required for business gate).
- **`run_result_page` / `detail`:** `_official_domains` once per request.
- **`find_global_source`:** `Result.url_key == digest([canonical_url])` before full scan; legacy URL rows without matching key still scanned.

---

## 6. Loop / data-structure improvements

- Dedup cross-radar: set-style short-circuit when title fingerprint too short **and** no URL.
- Queue card loops use `PAGE_SIZE` instead of literal `5`.
- Callback debounce prune uses named limits.

---

## 7. Large functions simplified

- `ResultWorkflowService.changed_fields` — loops replaced with field-group tables + helper.
- `find_global_source` — `_evaluate` helper separates URL vs title-mirror decisions.

Handlers remain thin; no god-function split that would obscure flow.

---

## 8. Domain readability improvements

- `business_queue_eligible` is the canonical Radar 1 gate name; `current()` calls it directly.
- `architecture_pending` kept only as a legacy alias (no remaining production call sites needed it).
- Domain entrypoint `app.domain.markets.relevance` unchanged as stable surface.

---

## 9. Error / transaction improvements

| Location | Change |
|----------|--------|
| `bot/targeted.py` | Log failure before user-facing error message |
| `targeted_search_service.execute` | Log before marking session `FAILED` and re-raise |
| `agent_job_service.launch_radar` | Log job submission failure before `safe_fail` |
| Review `decide()` | Unchanged single commit boundary |

No multi-commit transaction reshaping (behavior-preserving).

---

## 10. Callback / UI improvements

- Shared `MAX_PAGE_INDEX` across markets, compact_review, run_queue, targeted.
- Markets reuses run-queue parser for `m:run*` family.
- Identical Radar queue dispatch branch in `handlers` collapsed.
- Callback debounce constants centralized.

**Product UX unchanged:** labels, keyboards, completion CTA rules, review lifecycle, Targeted Search flows.

---

## 11. Collector improvements

- `fold` / `parse_date` → `app.common.text` (markets keep `oe_ligature=True`; others keep Arabic retention where previously enabled).
- No collector business-rule edits.

---

## 12. Targeted Search improvements

- Page enumeration uses `PAGE_SIZE`.
- Parser page clamp uses `MAX_PAGE_INDEX`.
- Failures logged once with operation context (still re-raise / still show same FR message).

---

## 13. Test cleanup / parametrization

- All active tests import `result_review_service` (shim gone).
- Business-specific Radar tests left explicit (not over-parameterized).
- Full suite green without rewriting fixtures.

---

## 14. Dead code / shims removed

- Deleted `app/services/market_review_service.py`.
- Removed dead identical if/else in `_handle_callback` queue dispatch.
- Historical markdown still mentions old names (intentional archive).

---

## 15. Performance observations

- Cross-radar URL matches: indexed lookup first (major win when URLs present).
- R2–5 queue pages: bounded SQL instead of full-table Python filter.
- Radar 1 pending queue remains eligibility-bound (cannot purely SQL without expressing the business gate in SQL — deferred).
- Title/content cross-radar mirror still scans other radars when needed.

---

## 16. Possible future DB-index improvements (no migration now)

| Query / pattern | Suggestion |
|-----------------|------------|
| Radar 1 pending + observation joins | Composite index on `(run_id, state)` already useful; consider covering `(result_id, run_id, state)` if explain shows seq scans |
| Cross-radar title mirror | Persist `global_title_key` / fingerprint as columns if table grows large (today JSON metadata) |
| Legacy `identity_key IS NULL` hydration in `find_existing` | One-off backfill of keys would shrink scan set |
| `Result.review_status` + `radar_id` + `last_seen_at` | Composite for pending queues |

---

## 17. Tests passed

```
702 passed, 1 warning in ~56s
```

Warning: local `.pytest_cache` Windows path quirk only — not a product failure.

Focused batches also green (workflow, dedup, pagination, run-scoped, uniqueness).

---

## 18. Alembic state

| | |
|--|--|
| Heads | `f19a7c4d2e61` |
| Current | `f19a7c4d2e61` |
| Migrations added this task | **None** |

---

## 19. Remaining technical debt

1. Radar 1 queue still filters in Python after streaming (by design of business gate).
2. Cross-radar title/content mirror still needs a scan when URL key misses.
3. `MarketReview` table/model name still market-centric (schema rename = migration; out of scope).
4. AI `PROMPT` strings remain per-radar modules (explicit on purpose; shared base deferred).
5. Some scripts still use dense one-liner style.
6. `.env` holds live secrets locally (expected) — never commit; rotate if ever exposed.

---

## 20. Exact files with important changes

| File | Change |
|------|--------|
| `app/common/text.py` | Shared fold + FR/ISO date parse |
| `app/common/constants.py` | `PAGE_SIZE`, `MAX_PAGE_INDEX`, debounce constants |
| `app/services/result_review_service.py` | SQL page for R2–5; domains once; naming |
| `app/services/dedup_service.py` | `url_key` fast path for global source |
| `app/services/result_workflow_service.py` | Table-driven `changed_fields` |
| `app/services/agent_job_service.py` | Log submission failures |
| `app/services/targeted_search_service.py` | Log execute failures |
| `app/services/market_review_service.py` | **Deleted** |
| `app/bot/handlers.py` | Debounce constants; dead branch removed |
| `app/bot/markets.py` | `run_queue.parse`; named constants |
| `app/bot/run_queue.py` | Named constants; readable layout |
| `app/bot/compact_review.py` | Named constants / `PAGE_SIZE` |
| `app/bot/targeted.py` | Logging; named constants |
| `app/bot/callbacks.py` | `RADAR_CODES` |
| Collectors `*/policy.py`, `web_discovery.py` | Use common text helpers |
| `docs/architecture/ARCHITECTURE.md` | Shim note removed |
| `tests/*.py` (imports) | Point at `result_review_service` |
| `CODE_REVIEW_REFACTOR_REPORT.md` | This report |

---

## Behavior diff (BEFORE → AFTER)

| Area | Expected |
|------|----------|
| Search completion text / keyboards | Unchanged |
| Queues / pagination semantics | Unchanged (R2–5 same page contents, fewer rows loaded) |
| Review approve/reject / stale version | Unchanged |
| Targeted Search | Unchanged UX; failures now logged |
| Radar 1–5 business decisions | Unchanged |
| Dedup identity / cross-radar match rules | Unchanged (fast path only when URL keys agree + canonical URL equal) |
| Cost path (paid calls after local filters) | Unchanged; no paid work moved earlier |
| Schema / migrations / production data | Untouched |

---

## Metrics (practical)

| Metric | Result |
|--------|--------|
| Tests | 702 → 702 green |
| Shim modules removed | 1 |
| Duplicated fold/date blocks | Consolidated to 1 module |
| Obvious N+1 on R2–5 queue cards | Reduced (domains once; SQL page) |
| Full-table cross-radar URL lookups | Fast-pathed via `url_key` |
| Migrations | 0 |
| Intentional product behavior changes | 0 |

---

## Acceptance checklist

- [x] Manual repetition reviewed; Radar boilerplate consolidated where safe
- [x] No obvious N+1 left on normal R2–5 UI page paths
- [x] Meaningful hot-path O(n) reduced where practical (`url_key`)
- [x] Business predicates / gate naming clearer
- [x] Handlers remain thin
- [x] Side effects unchanged and obvious at service boundaries
- [x] Broad silent exception swallowing reduced (logged)
- [x] Proven-safe shim removed
- [x] Tests green
- [x] No migration added
- [x] Behavior preserved
- [x] Compile / Flask factory / bot build / Alembic head OK
