# Radar 1 estimate normalization fix

**Date:** 2026-09-29

A placeholder estimate can no longer drop an otherwise valid Radar 1 opportunity.

## 1. Exact bug

Run #35 handed three verified keep/review offers to the orchestrator. All three died at `NORMALIZING` with:

```text
MarketCandidate.estimated_amount
unable to parse string as a number
input_value='* TTC MAD'
```

PMMP prints an unpublished estimate as `*`. The label `Estimation (en Dhs TTC)` appends `TTC MAD`, so the raw value becomes `* TTC MAD`. `model_copy` stored that string without validating it. The orchestrator then called `model_validate`, counted a `candidate_error`, and never reached dedup or persistence. Telegram therefore showed 0 nouveaux and 0 mis à jour.

## 2. Affected runs

| Run | Candidates lost to `* TTC MAD` |
|---|---|
| #35 | `101/2026/OFPPT` ISTA Tahannaout (keep), `04/2026/CA/BR/RGON` corniche de Sidi Ifni (keep), `03/2026` médina de Tiznit (review) |
| #33 | the same ISTA and Sidi Ifni notices |

Run #33 still saved three other offers that did not carry this placeholder.

## 3. Normalization change

One helper, `normalize_estimate` in `app/integrations/pmmp/parser.py`, now owns estimate parsing. `_amount` remains the numeric parser it calls. Call sites:

- `procurement_metadata` writes the helper result, including `amount=None`, so the raw label cannot survive
- `coerce_estimate_fields` runs again in `enrich_detail` immediately before `model_copy`
- `build_pmmp_detail` stores a numeric amount or `None`, and sets `verified` false when there is no number
- the listing collector uses the same helper for `hit.estimated_amount`
- `MarketCandidate.sanitize_optional_estimate` coerces leftover strings, dicts, and placeholders before strict field validation
- `MarketsRadarAgent.normalize_candidate` coerces a poisoned in-memory amount before the base serializer

Relevance rules, discovery queries, PMMP fetching, and dedup behavior are unchanged. No migration.

## 4. Placeholder handling

`* TTC MAD`, `-`, `—`, `N/A`, `Non communiqué`, `À définir`, an empty string, and `None` all become `amount=None`.

`* TTC MAD` with an official source keeps the wording that is actually present:

| Field | Value |
|---|---|
| `estimated_amount` | `None` |
| `estimated_currency` | `MAD` |
| `estimated_amount_tax_mode` | `TTC` |
| `estimated_amount_verified` | `false` |

A missing number is not marked verified. A non-numeric optional estimate logs at debug (`estimate_not_numeric`) and is not a `candidate_error`.

## 5. Valid amount handling

| Input | Amount |
|---|---:|
| `28 400 000,00` | 28400000 |
| `28 400 000,00 MAD TTC` | 28400000, currency MAD, tax TTC, verified when the source is official |
| `3 552 000,00` | 3552000 |
| integer or float | same number |
| structured dict `{amount, currency, tax_basis, verified, source}` | the parsed amount, with `verified` kept only when the amount is numeric |

## 6. Estimate / caution separation

`caution provisoire` still maps only to `provisional_bond_amount`. A page with estimate `*` and caution `10 000 MAD` keeps the estimate empty and the caution at 10000. The caution is never copied into the estimate.

## 7. Run #33 replay

Offline replay of the two stored failures (`101/2026/OFPPT`, `04/2026/CA/BR/RGON`) with `estimated_amount='* TTC MAD'`:

| Reference | Normalization | First persistence | Second replay | Policy |
|---|---|---|---|---|
| `101/2026/OFPPT` | passes, amount `None`, not verified | `NEW` | `UNCHANGED` | keep |
| `04/2026/CA/BR/RGON` | passes, amount `None`, not verified | `NEW` | `UNCHANGED` | keep |

Normalization errors caused by `* TTC MAD`: **0**.

## 8. Run #35 replay

Same offline path for all three former failures.

| Reference | Normalization | Persistence | Policy on the stored title |
|---|---|---|---|
| `101/2026/OFPPT` | passes | `NEW` | keep |
| `04/2026/CA/BR/RGON` | passes | `NEW` | keep |
| `03/2026` | passes | `NEW` | keep |

The live run #35 trace had classified the médina de Tiznit notice as `REVIEW_AMBIGUOUS_RELEVANCE` from the enriched page. This replay uses the stored title, not a new fetch. Current title-level policy returns keep, and the row is persisted rather than dropped. Currency `MAD` and tax `TTC` stay on the placeholder. The caution amount stays on its own field.

## 9. Candidate errors before / after

| Run | Before | After offline replay |
|---|---:|---:|
| #35 | 3 `NORMALIZING` errors, all `* TTC MAD` | 0 |
| #33 | 2 `NORMALIZING` errors, same string | 0 |

No production search was launched. Replay used the test database and the stored titles, references, and detail URLs.

## 10. Tests passed

`python -m pytest` on the estimate suite and the existing PMMP detail tests:

**21 passed**

- `tests/modules/radar1/test_estimate_normalization.py`
- `tests/modules/radar1/test_estimate_replay_runs.py`
- `tests/modules/radar1/test_pmmp_detail_enrichment.py`
- `tests/modules/radar1/test_pmmp_rgo_detail_estimate.py`

Covered cases: `* TTC MAD` survives, dashes and `Non communiqué` are empty amounts, French amounts `28 400 000,00` and `3 552 000,00` parse, a structured estimate is preserved, a missing estimate survives, and an invalid estimate does not absorb a valid caution.

The broader Radar 1 folder currently reports many failures in orchestrator tests (`AnalysisResponse` / dual `app` and `backend.app` imports, and a second SQLAlchemy instance). Those same persistence and phase-3 tests fail on the tree before this fix. `tests/api` is 20 passed. `tests/bot` is 38 passed, 57 failed. `tests/core` is 26 passed, 25 failed. `tests/integration` did not finish; it stalled in the production-acceptance group. That hang is outside this estimate change.

`python -m compileall -q app` passed. `python -m compileall -q scripts` stops on a pre-existing BOM in `scripts/validate_source_enrichment.py`, which this change does not touch. `python -m pip check` reported no broken requirements. Import of `normalize_estimate('* TTC MAD', official=True)` returns amount `None`, currency `MAD`, tax `TTC`, verified false.

## 11. Migration status

No migration. `flask db heads` and `flask db current` are both `c4d8e1a72b05 (head)`.

## Acceptance

A malformed or placeholder estimate no longer raises `MarketCandidate` validation and no longer increments `candidate_errors`. The offer continues through normalize, dedup, and persistence as `NEW`, and a second identical replay is `UNCHANGED`.
