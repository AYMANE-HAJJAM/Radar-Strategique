# Final production validation — 2026-09-12

**A. Overall status.** Isolated operational validation and hardening completed; unconditional production acceptance is **not established**. All 384 tests pass. No production database reset, migration, radar search, external API call, or message to a real Telegram user was performed in this validation. Tests use isolated databases and simulated transport. Historical source artifacts below are evidence from earlier runs, not fresh validation.

**B. Critical issues found.** Source refresh comparisons mixed SQLite naive timestamps with timezone-aware timestamps. Source cache state was shared across radars for the same URL. Cached/not-due sources could trigger unnecessary paid fallback. Non-market Details/Back navigation could accumulate messages. Usage reporting omitted some direct detail fetches and could double-count kept results. Historical Radar 3 output does not demonstrate current officeholders; Radar 4 artifacts do not establish current legal status.

**C. Issues fixed.** Normalized source timestamps to UTC; scoped source state by radar and URL, with migration `c83d2e5f9a31`; suppressed fallback when source reports are unchanged; added in-flight callback deduplication alongside debounce; tracked and replaced Radars 2–5 queue/details messages and added Back; corrected future direct-fetch and final-kept accounting. README now documents multi-user configuration and safe ID acquisition. Existing business scope remains unchanged. Migration has been tested but not applied to production.

**D. Multi-click results.** Ten concurrent identical callbacks per action:

| Action | Callbacks | Effective actions | New SearchRun rows | Review decisions | Paid calls |
|---|---:|---:|---:|---:|---:|
| Search | 10 | 1 | 1 | 0 | 0 |
| Pending | 10 | 1 | 0 | 0 | 0 |
| Details | 2.382 | 7.723 | 0 | 0 | 0 |
| Next page | 10 | 1 | 0 | 0 | 0 |
| Validate | 10 | 1 | 0 | 1 | 0 |

Search worker was deliberately held pending: one submission and one background task, not a completed live search. Validate creates one decision plus its associated status/audit writes; this table counts logical decisions and run rows, not SQL statements. Pending/Next render one five-card page and its navigation message. Slow-action deduplication also passes after the short debounce window is cleared.

**E. Search idempotency.** Ten simultaneous database reservations from two users create exactly one run, using separate SQLite connections. Stale-run recovery permits a new reservation after a simulated crashed run expires. Existing job tests cover background acknowledgement and failure handling. This is database-backed protection; live PostgreSQL multi-process crash testing was not performed.

**F. Multi-user results.** Single and multiple allowlisted users work; spaces and empty comma-separated entries are supported; malformed IDs fail clearly. Unauthorized users and group access are rejected. Two-user concurrent search reservation passes.

**G. Shared queue results.** Queue queries use shared company review state. A decision by user A changes the state visible to user B. Audit evidence includes result/radar, actor, action, previous/new status and timestamp. Injected commit failure rolls back the decision without a partial review/audit record.

**H. Stale-action results.** The second user's stale decision is rejected without overwriting the first decision or adding another audit event. Service-level stale errors are translated into a concise Telegram response by existing handler tests.

**I. Pagination and Details/Back.** Each radar passes a 12-result fixture with pages of 5, 5 and 2 unique primary keys, stable order and no overlap. Repeated page clicks render once. Radars 2–5 pass repeated Details/Back cycles with tracked old messages removed; Radar 1 retains its existing tracked view. If Telegram refuses deletion or is unavailable, old messages may remain visible; callback validation still protects state. Live Telegram rendering was not inspected.

**J. Radar 1 quality.** Deterministic tests cover architecture relevance, irrelevant technical/supply scopes, current/open status, expiry and official identity resolution. Meaningful deadline changes update the existing record and reopen review; unchanged enrichment preserves review. Historical low-cost run retained 28 review candidates with PARTIAL health. Several official links remain unresolved: this is not proof that all 28 are verified current opportunities.

**K. Radar 2 quality.** Pipeline tests distinguish concrete preparatory project signals from generic/completed news. Historical direct-only run retained zero; low-cost run retained two review candidates. Saved examples include project signals embedded in festival news and Medina studies. Coverage and current usefulness remain unverified against fresh sources.

**L. Radar 3 quality.** Tests enforce evidence for current role verification and reject stale/self-asserted roles. Historical low-cost output reports zero current roles verified; its two review candidates are a Ben Youssef library article and an Al Omrane recruitment notice. These do not establish current decision-makers. This radar does not yet have sufficient live-quality evidence for acceptance.

**M. Radar 4 quality.** Tests exercise deterministic legal-status handling. Historical output contains two SGG draft building-sector texts; a generic source status of `active` is not proof of adoption or entry into force. Current legal status and freshness were not verified. Draft/adopted/in-force quality cannot be signed off from these artifacts alone.

**N. Radar 5 quality.** Tests distinguish Morocco relevance, program status and direct funding versus beneficiary procurement. Historical final artifact has 24 collector candidates, 18 rejections and 6 manual-review items. The earlier label “24 kept” describes collector output, not final useful results. Current eligibility/access remains subject to source verification.

**O. Memory second-run proof.** All five radars pass the same deterministic snapshot twice:

| Radar | First-pass new | Second-pass new | Second-pass duplicates | Result rows | Second-pass paid calls | Approval preserved |
|---|---:|---:|---:|---:|---:|---|
| 1 | 1 | 0 | 1 | 1 | 0 | Yes |
| 2 | 1 | 0 | 1 | 1 | 0 | Yes |
| 3 | 1 | 0 | 1 | 1 | 0 | Yes |
| 4 | 1 | 0 | 1 | 1 | 0 | Yes |
| 5 | 1 | 0 | 1 | 1 | 0 | Yes |

Last-seen remains current. These runs use deterministic fixtures with AI disabled. Separate cached-source tests prove Radars 2–5 do not call paid search on unchanged source reports. Meaningful-update behavior is covered by existing pipeline tests; this table specifically measures unchanged snapshots.

**P. Cost regression check.** Real application polling/lifecycle with simulated Telegram transport ran idle for **300.332 seconds**. Startup/idle, start/menus, pending/approved/rejected queues, details and approve/reject each recorded **0 direct source HTTP, 0 paid search, 0 OpenAI calls and 0 input/output tokens**. Direct-source parsing remains ahead of bounded fallback. Source timeout, 403, 429 and 500 simulations fail locally without an unbounded retry loop. Failed paid requests retain known usage. Configuration tests check Radar 1 discovery/resolution limits of 2/2 and Radars 2–5 discovery limits of 2/1/1/2. Radar 1's two separate budgets must not be described as a combined two-call maximum. Exhausting either daily search or AI cap returns a safe Telegram message with no worker submission and no new run in isolated tests. However, strict atomic global reservation across simultaneously running different radars is not proven; in-flight work can overshoot a shared cap.

**Q. Direct-only historical results.** No new source searches were run. Counts distinguish final retained review items from collector candidates.

| Radar | Recorded direct HTTP | Paid search | OpenAI | Input/output tokens | Final retained review items | Collector health |
|---|---:|---:|---:|---|---:|---|
| 1 | 60 | 0 | 0 | 0 / 0 | 28 | PARTIAL |
| 2 | 6* | 0 | 0 | 0 / 0 | 0 | DEGRADED |
| 3 | 2* | 0 | 0 | 0 / 0 | 0 | DEGRADED |
| 4 | 4 | 0 | 0 | 0 / 0 | 2 | HEALTHY |
| 5 | 4 | 0 | 0 | 0 / 0 | 6 | HEALTHY |

Sources: `audit-output/direct-only-radar1.json`, `direct-only-radar2.json`, `direct-only-radar3-final.json`, `direct-only-radar4.json`, `direct-only-radar5-final.json`. Radar 5 has 24 collector candidates before 18 rejections. These artifacts are isolated runs, not proof of production-persisted queue rows.

**R. Normal low-cost historical results.** Resolution requests are a subset of paid search, not an additional charge to add to the paid-search column.

| Radar | Recorded direct HTTP | Paid search | Resolution | OpenAI requests | Input tokens | Output tokens | Total tokens | Final retained review items | Health |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 60 | 2 | 2 | 2 | 10,490 | 141 | 10,631 | 28 | PARTIAL |
| 2 | 6* | 2 | 0 | 2 | 26,239 | 354 | 26,593 | 2 | HEALTHY |
| 3 | 2* | 1 | 0 | 1 | 12,993 | 955 | 13,948 | 2 | HEALTHY |
| 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 2 | HEALTHY |
| 5 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 6 | HEALTHY |
| Total | 76* | 5 | 2 | 5 | 49,722 | 1,450 | 51,172 | 40 | Mixed |

Sources: `audit-output/low-cost-radar1.json`, `low-cost-radar2.json`, `low-cost-radar3-final.json`, `low-cost-radar4.json`, `low-cost-radar5-final.json`. Retained counts use run-level manual-review counts, not collector-level `final_kept`. These dry-run review candidates have not all been established as useful intelligence.

*Historical direct-HTTP counters are incomplete: R2/R3 top-level counts omit detail attempts (low-cost collector metrics separately record 22 and 11). The sum 76 is the recorded top-level sum, not a validated total of network attempts. Future accounting now combines direct-adapter and detail-reader attempts; historical artifacts were not rewritten. Direct HTTP fetches are not OpenAI requests and incur no OpenAI token charge. No USD estimate is inferred here.

**S. Performance timings.** Local handlers plus isolated SQLite, simulated Telegram transport; median/max over five repetitions unless noted. Excludes real Telegram/network latency and production database load.

| Action | Median ms | Maximum ms |
|---|---:|---:|
| /start | 0.117 | 0.512 |
| Radar menu | 0.522 | 0.879 |
| Pending queue | 39.651 | 51.959 |
| Approved queue | 1.597 | 2.899 |
| Rejected queue | 2.547 | 2.661 |
| Details | 2.382 | 7.723 |
| Pagination | 29.816 | 64.227 |
| History | 2.690 | 8.137 |

Single operations: approve DB **6.720 ms**, reject DB **6.171 ms**, search acknowledgement **0.442 ms** with worker held pending. No local DB-only bottleneck observed at fixture scale. These timings do not establish live end-user latency.

**T. Security and failure checks.** Existing tests cover unauthorized/stale/foreign-result callbacks, result/radar relationships, source URL restrictions and secret-safe OpenAI/Telegram error logging. Missing token/DB configuration diagnostics and allowlist parsing pass. Telegram outage handler remains alive even when its error response also fails; no search retry is initiated by that handler. Source failures and review transaction rollback pass. This is targeted validation, not a penetration test or a guarantee that every exception path is secret-free.

**U. Tests passed.** `python -m pytest -q`: **384 passed in 26.36 seconds**. `python -m compileall -q app scripts migrations run.py run_bot.py`: passed. `python -m pip check`: no broken requirements. Migration tests include isolated SQLite upgrade/downgrade and offline PostgreSQL SQL generation. Evidence: `audit-output/production-tests.txt`, `audit-output/production-acceptance.json`, `audit-output/passive-usage.json`. Test transport blocks real HTTP. No production DB was reset by tests.

**V. Remaining limitations.** Production DB connectivity/schema and live Telegram delivery were not exercised. The source-state migration is required before deploying the changed code. PostgreSQL cross-process concurrency and production-scale latency remain unmeasured. Shared daily limits lack proof of an atomic global budget reservation; an exhausted cap can also block a direct-only launch. Some configured source domains fail local allowlist checks, reducing coverage. Old direct-fetch counters are incomplete. Direct-only Radars 2/3 yielded zero; Radar 3 officeholders and Radar 4 current legal status are not verified. Failed Telegram deletions can leave visible old cards. These findings prevent an unconditional all-five-radar production-quality signoff.

**W. Exact multi-user configuration.** In `.env`:

```dotenv
ALLOWED_TELEGRAM_USER_IDS=111111111,222222222,333333333
```

Examples only. Obtain an employee's ID by having them send `/start` privately while unauthorized; an administrator reads the corresponding `Access denied user_id=...` server log and verifies identity/timing with that employee. Append the ID and restart the bot. The denial log contains the user ID, not their message content or credentials. `/myid` was not reintroduced. No code change is required to add employees.

**X. Exact production commands.** From the project directory, after configuring the existing production credentials and taking the normal database backup, use:

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m flask --app run db current
.venv\Scripts\python.exe -m flask --app run db upgrade
.venv\Scripts\python.exe run_bot.py
```

These are deployment instructions, not operations performed during validation. Stop the old bot before migration/restart to avoid old code running against a changed schema. Do not use reset commands. Migration changes source-cache uniqueness; review/results data is not intentionally removed. Complete the outstanding production and source-quality checks before treating the system as fully accepted.
