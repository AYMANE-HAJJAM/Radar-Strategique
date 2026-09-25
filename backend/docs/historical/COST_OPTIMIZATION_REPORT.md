# Radar cost-optimization report

Date: 2026-09-11

## Scope and safety

The pass covers all five radars. Business rules, Telegram delivery, review states, source allowlists, and candidate schemas remain in place. The comparison runner used a fresh temporary SQLite database for every radar and mode. It did not run a production radar or write comparison data to the production database.

The live measurements are samples of web search behavior, so candidate counts can vary as the search service returns different sources. Deterministic fixtures and integration tests provide the stable behavioral check.

## OpenAI call inventory

| Call purpose | Radars | Trigger | Paid request control |
|---|---|---|---|
| `DISCOVER_PROCUREMENT` | 1 | Each configured procurement query | Existing query cap; compact structured response; no page body in the model input |
| `DISCOVER_PROJECTS` | 2 | Each configured project query | Query cap; minimal discovery schema; local page extraction |
| `DISCOVER_INSTITUTIONS` | 3 | Each configured institution query | Query cap and target-count early stop; minimal discovery schema; local page extraction |
| `DISCOVER_POLICIES` | 4 | Each configured policy query | Query cap and target-count early stop; minimal discovery schema; local page extraction |
| `DISCOVER_FUNDING` | 5 | Each configured funding query | Query cap and target-count early stop; minimal discovery schema; local page extraction |
| `CLASSIFY_*` | 1–5 | Only when deterministic rules report ambiguity | Evidence hash cache, explicit gate, per-run token budget, compact candidate/evidence context, 500-token output cap |

Developer-only connectivity checks remain in `scripts/check_openai.py` and the CLI `test-openai` command. They are not part of a radar run.

## Changes

- Replaced verbose discovery output for Radars 2–5 with a minimal hit schema. Prompts request URL, title, institution/date where present, and one short factual excerpt.
- Kept web pages out of classification requests. Local extraction ranks relevant sentences and sends at most four evidence snippets, 2,400 source characters, and 500 characters per snippet by default.
- Added an explicit `needs_ai_analysis` gate. Deterministic decisions, dry runs, no-AI runs, cached evidence, and exhausted token budgets skip classification with a recorded reason.
- Added stable evidence/config hashes to the analysis cache tag. Unchanged evidence reuses the stored analysis; changed evidence invalidates it.
- Added per-radar input-token budgets and configurable discovery/classification output caps.
- Added local detail-page extraction for Radars 2–5, source refresh checks for stable sources, and target-count early stopping where safe.
- Added `--no-ai` and required `--isolated` to the live runner. `scripts/run_optimization_comparison.py` executes all normal and no-AI controls with separate temporary databases.
- Added run metadata for purpose, model, input/output tokens, skipped calls, paid calls, calls per kept result, and tokens per kept result.

## Live measurements

The baseline was an isolated dry run made before the optimization. The optimized and no-AI columns are later isolated live samples. `Requests` includes discovery plus classification; all measured optimized classification counts were zero.

| Radar | Baseline candidates | Optimized candidates | No-AI candidates | Baseline requests | Optimized requests | No-AI requests | Baseline tokens (in/out) | Optimized tokens (in/out) | No-AI tokens (in/out) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Markets | 20 | 28 | 28 | 5 | 5 | 5 | 26,226 / 384 | 26,261 / 419 | 26,393 / 434 |
| Projects | 1 | 1 | 1 | 6 | 6 | 6 | 71,459 / 1,310 | 79,399 / 2,289 | 78,537 / 1,575 |
| Institutions | 4 | 3 | 2 | 5 | 5 | 5 | 65,207 / 4,607 | 64,351 / 4,464 | 51,542 / 2,937 |
| Policies | 3 | 0 | 0 | 5 | 5 | 5 | 57,422 / 3,495 | 56,887 / 2,415 | 57,297 / 2,409 |
| Funding | 17 | 6 | 6 | 6 | 6 | 6 | 79,275 / 7,824 | 73,503 / 3,788 | 78,064 / 3,708 |
| **Total** | **45** | **38** | **37** | **27** | **27** | **27** | **299,589 / 17,620** | **300,401 / 13,375** | **291,833 / 11,063** |

Optimized output tokens fell 24.1% in this sample. Total input plus output tokens fell 1.1%; web-search context dominates input usage and varies between live searches. The no-AI sample used 4.5% fewer total tokens than baseline and made no classification calls. It still uses OpenAI-backed web discovery, so `--no-ai` means no analysis/classification calls rather than zero discovery cost.

Radar 4 completed but returned no qualifying official policy text in both optimized modes. All five search calls succeeded, and both normal and no-AI runs produced the same result. This sample therefore cannot establish live output parity for Radar 4. Its deterministic collector and orchestration behavior remains covered by the passing test suite. Funding and institution counts also varied between live samples; the controls preserved useful results but should not be interpreted as a fixed recall benchmark.

The conservative default keeps one discovery request per query. Experimental batching reduced calls but materially reduced useful results, so it was not adopted. The batching facility remains configurable for later evaluation with a stable replay corpus.

## Verification

- `python -m pytest -q`: **344 passed** in 15.21 seconds.
- Added tests cover compact context limits, prompt size, bounded OpenAI inputs/outputs, explicit deterministic skip behavior, no-AI behavior, unchanged/changed evidence caching, token budgets, and query batching.
- All ten final live controls completed against isolated databases. The runner reports exit code 2 for the two Radar 4 controls because its quality guard treats zero candidates as degraded; the radar run records themselves completed without an exception.

Artifacts are in `audit-output/radar1.json` through `radar5.json`, `audit-output/optimized-radar1.json` through `optimized-radar5.json`, and `audit-output/no-ai-radar1.json` through `no-ai-radar5.json`.
