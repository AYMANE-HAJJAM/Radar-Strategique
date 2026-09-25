# Radar 1 broader business relevance

Rules version 6 makes heritage a priority, not an admission requirement. Architecture,
rehabilitation, urban/territorial work and related built-environment opportunities can
enter the existing pending human-review queue at P1, P2 or P3.

## Implementation

- `app/collectors/markets/policy.py`: shared deterministic score, once per keyword
  family: heritage +5, architecture +4, urban/territorial +4, rehabilitation +3,
  related technical services +2, buildings/public spaces +2, negatives -5.
  Score >=2 keeps, <=-2 rejects, middle requires review. Technical signals require
  built-environment context. Heritage locations alone do not rescue cleaning,
  guarding or catering. Scores, signals and priorities appear in collection traces.
- Collector early and final business gates use this policy. Final kept counts are
  reported as `kept_p1`, `kept_p2`, `kept_p3` after all technical validation.
- Market validators classify priority deterministically using the procurement title,
  avoiding unrelated page boilerplate. Generic rehabilitation is P2, not P1.
- Radar 1 retains technically valid plausible candidates when AI says irrelevant or
  gives low confidence; it flags human review. Ambiguous business fit also requires
  human review. Technical rejection still wins. No AI confidence is fabricated.
- A shared candidate-review hook defaults to the previous behavior for other radars;
  Radar 1 supplies its deterministic priority for dry runs, unavailable analysis and
  analysis-budget fallbacks. No Radar 2–5 business behavior changes.
- Existing Telegram workflow, official-link verification, whitelist, freshness,
  expired/closed rules, DCE handling, deduplication and human decision memory remain.

## Validation

Full suite: **229 passed**. Compilation of `app`, `scripts`, `tests` passed.
Regression tests cover all 13 supplied manual-search examples, AI rejection and
low-confidence overrides, clear noise, technical vetoes, and P1/P2/P3 pending queues.
Existing unchanged human-rejected and approved memory tests pass.

`python -m scripts.compare_market_relevance` compares the previous deterministic
business gate with the new one on identical titles. It performs no network or DB work.
The archived old keywords live only in a test fixture, never in production logic.

| Identical-title snapshot | Titles | Old rejected | New rejected | New ambiguous |
|---|---:|---:|---:|---:|
| Supplied manual examples | 13 | 2 (15.4%) | 0 (0%) | 0 |
| Previous live trace, unique nonempty titles | 11 | 11 (100%) | 9 (81.8%) | 1 |
| New live trace, unique nonempty titles | 6 | 0 (0%) | 0 (0%) | 0 |

All 13 manual examples now pass business relevance: **P1=1, P2=10, P3=2**.
The old deterministic policy already admitted 11 of these titles; these fixtures
alone cannot explain a production count of one. The new AI-review behavior addresses
an additional downstream rejection path. These are synthetic regression examples,
not verified live tenders. Archived trace titles can be truncated to 250 characters;
offline comparisons measure only the title gate, not full end-to-end acceptance.

## Live dry-run

Command: `python -m scripts.run_live_radar RADAR_1_MARKETS --dry-run --isolated
--max-queries 4 --max-candidates 30 --report-json radar1-relevance-live.json`

- 4 billable search calls, 12 raw allowed-source pages, **6 tender observations**.
- **0 rejected by relevance; 0 final kept; final P1=0, P2=0, P3=0**.
- The six observed titles pass business relevance (P1=0, P2=5, P3=1).
- All six fail official resolution. Six additional page-fetch/parser failures are
  separate events, not six additional tender candidates. HTTP 403 and 429 responses
  leave collector health DEGRADED. Source checks were not relaxed to inflate results.
- No classification calls, production Result writes or Telegram sends.

Artifacts: `radar1-relevance-tests.txt`, `radar1-relevance-live.json`,
`radar1-relevance-comparison.json`; optional known-reference check is recorded in
`radar1-relevance-control.json`. The live search does not establish 10–15 verified
opportunities; its remaining bottleneck is official evidence access/resolution.

The separate known-reference control (`--control-reference CA11/2026/APDN`, four-query
budget, twelve-observation budget) completed HEALTHY: three searches, two observations,
one final kept opportunity, zero relevance rejections, **P1=0, P2=1, P3=0**. Its exact
official PMMP detail resolved successfully. This targeted control is not representative
of general discovery yield and is not hard-coded into production.
