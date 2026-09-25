# Radar 1 zero-results fix report

**Date:** 2026-09-23

**Scope:** Corrective implementation for the two confirmed failures in `RADAR1_ZERO_RESULTS_DIAGNOSTIC.md`. No architecture redesign, no production search, no Telegram send, no migration.

Evidence: `docs/historical/audits/radar1-zero-fix-replay.json`

---

## 1. Exact persistence exception found

```
pydantic_core._pydantic_core.ValidationError
  1 validation error for MarketCandidate
  metadata
    Value error, Metadata exceeds 10000 characters
```

Captured offline by replaying the keep → `radar.normalize_candidate()` path with a production-like enriched keep (PMMP detail + business_relevance/feedback + resolution attempts) after collector-style **in-place** `candidate.metadata[...]` mutation.

Failing stage: **NORMALIZING** (orchestrator `_normalize`)

Failing field: `MarketCandidate.metadata` (`bounded_metadata` validator)

DB operation: none yet — failure occurs before dedup/save, so `candidates_after_rules=0` and every keep becomes `candidate_errors`.

---

## 2. Exact root cause

1. Collector enriches keeps with large structured metadata (`pmmp`, `business_relevance`+feedback, `resolution`, snapshots).
2. Several metadata writes used **in-place dict mutation**, bypassing Pydantic re-validation at collection time.
3. Orchestrator always re-validates via `normalize_candidate` → `model_dump` + `model_validate`.
4. The old **10 000-character** metadata budget was too small for legitimate enriched Radar 1 keeps (eligibility text, PMMP labels, resolution attempts, feedback features).
5. Every keep raised `ValidationError` → `_candidate_error` → Telegram “Rejetés” inflation with **0 NEW / 0 UPDATED**.

---

## 3. Why it started at run #28

Through run **#27**, keeps still persisted (`candidate_errors=0`, `candidates_after_rules>0`, `rule_reasons` / `ai_skipped_reasons` present).

From run **#28** onward:

- New fuller PMMP enrichment payloads (eligibility / qualifications / richer detail)
- In-place post-enrichment metadata growth
- All orchestrator candidates failed normalize (`candidate_errors == candidates_count`, `after_rules=0`, no `rule_reasons`)

ISTA Tahannaout and re-enriched Corniche/Logements all hit the same validator.

---

## 4. Persistence code changed

| File | Change |
|---|---|
| `app/core/constants.py` | `MAX_CANDIDATE_METADATA_CHARS = 65536` |
| `app/core/agent_schemas.py` | `bounded_metadata` uses the new budget + `ensure_ascii=False` |
| `app/modules/radar1_markets/collector.py` | `_with_metadata()` applies metadata via `model_copy` so validation runs at collection time |
| `app/core/orchestrator.py` | Richer `_candidate_error`; per-candidate save commit; non-DB persist errors isolated |

Valid enriched metadata (including approved PMMP/feedback/resolution) is kept intact — not stripped.

---

## 5. Transaction / session fix

- Successful saves **commit per candidate** (same pattern as AI analyze commits).
- Non-DB persist exceptions: `rollback` → log candidate error → `commit` counters → continue.
- `SQLAlchemyError` still **re-raised** as run-level database failure (distinct `error_kind`).

---

## 6. Logging improvements

`log_candidate_failure` logs:

- `run_id`, `radar_id`, `stage`, `candidate_index`
- `reference`, `title` (truncated), `source`
- `error_type`, `error_message` (truncated)
- traceback (logs only — **not** Telegram)

`run_metadata.candidate_error_details` stores compact diagnostics (last 30).  
`policy_rejects_count` kept distinguishable from `candidate_errors_count`.

---

## 7. Policy false-negative root cause

Step-8 fallthrough rejected titles with explicit **études / conception / suivi architectural** when heritage / concours / major-asset tracks did not fire — emitting `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` despite `ARCHITECTURAL_SCOPE`.

`procedure_type='competition'` was an accidental lifeline via the concours track.

---

## 8. Architectural-scope precedence fix

Added `STRONG_ARCHITECTURAL_SCOPE` and `REASON_ACCEPT_ARCH_SERVICE` (`ACCEPT_ARCHITECTURAL_PROFESSIONAL_SERVICE`).

Order now:

1. pure execution  
2. unrelated goods  
3. infrastructure (ordinary voirie/assainissement still reject)  
4. heritage  
5. competition  
6. major architecture (when professional role present)  
7. **strong architectural professional-service scope** (role + domain; no heritage/competition required)  
8. require professional role  
9. no-domain reject  

---

## 9. Preliminary-filter change

`preliminary_plausible` unchanged for obvious garbage.

Listing-stage hard reject for `REJECT_NO_DOMAIN` / `REJECT_NO_ROLE` is **deferred** when a PMMP/official detail URL exists (`_should_enrich_before_reject`), so detail can supply procedure / activity domains before final rejection.

---

## 10. Detail-enrichment behavior

- Obvious garbage still rejected before detail.
- Plausible no-domain cases with a detail URL continue to `enrich_detail` once.
- `_business()` now includes PMMP `activity_domains`, procedure, object, main_category in scope so detail evidence participates in final policy.

---

## 11–13. Run #28 / #29 / #30 offline replay

| Run | Previous keeps | Normalize OK after fix | Remaining candidate errors | FN no-domain prior | FN recovered |
|---:|---:|---:|---:|---:|---:|
| 28 | 3 | **3** | **0** | 27 | 13 |
| 29 | 3 | **3** | **0** | 25 | 12 |
| 30 | 4 | **4** | **0** | 26 | 10 |

Run **#29**: the 3 collector keeps no longer fail persistence in offline normalize simulation.

---

## 14. False negatives recovered

Recovered titles move from `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` → `ACCEPT_ARCHITECTURAL_PROFESSIONAL_SERVICE` / `P2_REVIEW` (explicit études/conception architecturales).

Not maximized: ordinary voirie/assainissement études, pure travaux, IT/goods remain rejected.

---

## 15. Remaining rejects (why)

Still correct rejects include:

- `REJECT_OUT_OF_SCOPE_INFRASTRUCTURE` — voirie / assainissement / réseaux without architecture+heritage rescue  
- `REJECT_PURE_EXECUTION` — travaux-only heritage/building works  
- `REJECT_IRRELEVANT_DOMAIN` — goods / IT / security / catering  
- Residual `REJECT_NO_HERITAGE_OR_ARCHITECTURE_CONTEXT` — professional role without strong architecture/heritage wording (e.g. bare études+suivi, AMO on roads)

---

## 16. Candidate errors before / after

| | Before (#28–#30) | After (offline replay) |
|---|---|---|
| candidate_errors | = every keep (3–4) | **0** |
| after_rules | 0 | would increment for needs_ai keeps |
| Result / Observation | none for those keeps | persist path green in tests |

---

## 17. Tests added / updated

- `tests/modules/radar1/test_radar1_persistence_regression.py` — exception lock, persist keep, multi-keep, logging  
- `tests/modules/radar1/test_radar1_architectural_scope_fix.py` — required cases 1–8 + detail fixture  
- Updated heritage / market_relevance / queue / major snapshot / phase3 expectations for intentional eligibility

---

## 18. Total tests passed

**767 passed** (`pytest -q`)

---

## 19. Alembic state

```
db current = f19a7c4d2e61 (head)
db heads   = f19a7c4d2e61 (head)
```

Confirmed via `flask db current` / `flask db heads` and `alembic_version` table.

---

## 20. Migration status

**No migration.** Schema unchanged.

---

## 21. Remaining limitations

- Remaining no-domain rejects without strong architectural wording still need detail evidence or heritage/major/competition to survive — by design.  
- Adaptive feedback still soft-demotes keep→review only; it does not hard-reject strong architecture.  
- Offline replay validates normalize + policy; it does not re-fetch live PMMP pages.  
- Telegram UX still aggregates technical errors into “Rejetés” count; internals keep `candidate_errors` separate for diagnostics.
