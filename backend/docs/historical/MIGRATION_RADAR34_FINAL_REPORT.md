# Production migration and Radar 3/4 quality — 12 September 2026

**A. Migration status — APPLIED and verified.** Production moved from `a91f3d2c4e10` to the sole Alembic head `c83d2e5f9a31`. Applied `migrations/versions/b72c1d4e8f20_direct_source_state.py` and `migrations/versions/c83d2e5f9a31_source_state_per_radar.py`. No active initialized/running search existed; local process inspection found no Python bot. No production radar results or Telegram test messages were written.

The first two guarded attempts failed before migration SQL because the Neon pooler rejects `lock_timeout` in connection startup options. Removing that unsupported option allowed the existing Flask migration command to complete. The guard retains a five-second timeout for acquiring its own locks and a 120-second CLI timeout.

**B. Exact migration command executed.** The safety wrapper invoked the existing project command as a subprocess:

```powershell
.venv\Scripts\python.exe -m flask --app run db upgrade
```

The enclosing command was `.venv\Scripts\python.exe -m scripts.safe_source_migration --apply`. It checked revision and active runs, acquired temporary write-blocking locks on existing business tables, created and checksum-verified a local snapshot, executed the CLI, and compared all protected business rows before releasing the locks. No reset command was executed against production.

**C. Revision, backup and preservation evidence.**

| Table | Before | After |
|---|---:|---:|
| alembic_version | 1 | 1 |
| radars | 5 | 5 |
| results | 0 | 0 |
| search_runs | 0 | 0 |
| result_observations | 0 | 0 |
| market_reviews | 0 | 0 |
| result_audit_events | 0 | 0 |
| source_states | Absent | 0 |

Business-row contents are identical, not merely their counts. The new source table has no foreign keys; `radar_code` is non-null with default `''`; `source_name`, `source_url`, `last_checked_at` and `health` are non-null; health defaults to `HEALTHY`. Its unique constraint/index is `uq_source_states_radar_url (radar_code, source_url)`, replacing source-URL-only uniqueness. Both checked/changed timestamps are PostgreSQL timezone-aware. Existing table keys, indexes and business fields were not altered. Environment credentials, allowlist and configured budgets were not changed.

Backup: `backups/source-migration-20260912T180723652198Z.json`, with adjacent `.sha256`. SHA-256: `2884d7d56734f3a52f36606c2a9ba77aa0430025a827c7a3cee1aa8be1563cbc`. This is a logical snapshot using the project's existing typed row encoding, plus reflected schema/DDL. Its checksum and data restoration into isolated SQLite were verified, normalizing SQLite timestamps to UTC. It is not a native PostgreSQL/PITR recovery rehearsal and is not passed directly to the reset utility's restore command.

Postcheck inserted two negative-ID cache rows in a transaction, verified same-URL/different-radar isolation and timezone-safe refresh checks, then rolled back. No cache test rows or sequence increments remained. All model-backed tables were accessible. Actual bot entrypoint/application initialization and a short polling lifecycle passed with simulated Telegram transport: zero unexpected external requests, paid searches, OpenAI calls or tokens. Live Telegram connectivity was not exercised and no persistent production poller was launched.

The initial approval review rejected the broad backup/lock operation. A subsequent read-only check established that every business table was empty and only five radar definitions existed; approval review then allowed the guarded operation. No approval remains pending.

Evidence: `audit-output/source-migration.json`, `migration-readonly-preflight.json`, `source-migration-postcheck.json`, `migration-backup-restore-check.json`, and `pending-migration.sql`. Downgrading `b72c1d4e8f20` would drop source-cache state, and undoing per-radar uniqueness can fail when shared URLs exist; neither downgrade was executed. Run the upgraded application with this schema rather than mixing older cache code with the new schema.

**D. Radar 3 before/after.** Historical low-cost output retained two weak review candidates: a generic library article and a recruitment notice, with zero verified current roles. The new direct-only live sample retains **one relevant official institution profile**, with its public mission and architectural/territorial relevance. Recruitment, generic non-actionable content, stale named roles and unverified named people are rejected deterministically. Profiles without verified leadership explicitly include **“Responsable actuel non vérifié”**. Structured result types and verification fields are stored; no person is invented.

The obsolete Al Omrane governance URL was replaced by its actual institutional profile page. Its parser scopes evidence after the page heading, excluding navigation/recruitment links, and hashes the profile body so mission changes can invalidate the source cache. Only Radar 3 uses this parser. Bounded fallback queries now start from named institutions and their official domains instead of generic people searches; the live samples did not need fallback.

**E. Radar 3 representative quality.** The accepted [Groupe Al Omrane profile](https://www.alomrane.gov.ma/Le-groupe/A-propos) describes its public development, urban and land-development mission. This supports monitoring the institution; it does not establish who holds a current office. No new appointment or verified officeholder appeared in the final live sample.

| Radar 3 measure | Final live sample |
|---|---:|
| Configured sources considered | 3 |
| Successful source HTTP fetches | 2 |
| Institution candidates discovered/retained | 1 / 1 |
| Current officeholders verified | 0 |
| Retained profiles with unverified holder | 1 |
| New appointments | 0 |
| Recruitment/obsolete-role rejections observed live | 0 / 0 |
| Health | PARTIAL |

The live sample did not contain those rejection cases. Separate regressions prove rejection of recruitment, generic heritage and conference content, and stale/unverified named profiles; they are not counted as live discoveries. A dated official appointment fixture is accepted, and a meaningful role change updates the same row. The configured Culture ministry source fails the existing allowlist; broadening unrelated radar allowlists was avoided. Current-leadership coverage remains insufficient for full production-quality acceptance.

**F. Radar 4 before/after.** Historical samples retained two building-sector draft items without proving present legal status. The corrected parser reads SGG's actual repeating list blocks and preserves the instrument type separately from the title. The final live sample retains **11 relevant official draft versions**, excluding 336 unrelated/nonqualifying list links. It no longer treats cited enabling laws as the type/status of the main instrument, promotes a draft because its text mentions an in-force law, or includes medical rehabilitation legislation as architectural rehabilitation.

| Radar 4 measure | Final live sample |
|---|---:|
| Configured official sources checked | 4 |
| Productive official sources | 1 — SGG |
| Direct-source retained items | 11 |
| Draft laws | 5 |
| Draft decrees | 3 |
| Draft orders | 3 |
| Adopted/in-force laws verified | 0 |
| Strategies / studies | 0 / 0 |
| Unrelated/nonqualifying list links rejected | 336 |
| Listed-version draft status supported | 11 |
| Present legal effectiveness unverified | 11 |
| Publication dates verified | 0 |
| Health | PARTIAL |

Counts are derived from structured candidates. The legacy collector `laws` metric groups decrees/orders together; it is not a count of adopted laws. Rejected links include alternative-language documents and are not necessarily 336 distinct legal instruments.

**G. Official-source/status accuracy.** All eleven items link from the [official SGG draft list](https://www.sgg.gov.ma/Legislation/ListeAvantProjets.aspx) to exact public document URLs. Representative subjects include cultural heritage protection, construction operations, territorial planning and building-sector qualifications. Status is `DRAFT` for the listed version; summaries explicitly say subsequent adoption and current entry into force are unverified. The parser leaves publication dates and unproven reference numbers empty rather than interpreting a cited law or URL filename as the new instrument's reference.

Manual inspection of the [national cultural heritage charter PDF](https://www.sgg.gov.ma/portals/0/AvantProjet/46/Avp_Loicadre_51.13_Fr.pdf) confirms that it describes itself as a project and concerns heritage preservation and planning. One representative decree PDF timed out during manual verification. Individual PDF contents, later Bulletin Officiel publication and current effectiveness were not all verified. Parliament, CESE and HCP endpoints failed in the live run. This demonstrates useful official draft-document extraction, not complete current legal-monitoring coverage.

**H. Cost metrics.** Final measured application dry-runs only:

| Radar | Direct HTTP attempts | Paid search | Resolution search | OpenAI requests | Input tokens | Output tokens | Total tokens | Retained review candidates |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| 4 | 4 | 0 | 0 | 0 | 0 | 0 | 0 | 11 |
| Total | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 12 |

Direct HTTP is not an OpenAI request or token cost. These are final per-run measurements, not totals for all debugging attempts or manual browser inspection. Earlier bounded diagnostics exposed parser/harness errors and were superseded by the final artifact. No paid application search/classification was used in this task. Production fallback/token budgets remain unchanged; these live validations explicitly selected direct-only mode.

**I. Second-run memory proof.** After each live dry-run, the source-cache repeat made zero direct HTTP requests, paid searches, OpenAI calls and tokens. Then the exact extracted candidates were replayed into disposable SQLite with AI disabled:

| Radar | First replay NEW | Second replay NEW | Second duplicates | Final result rows | Second paid/AI calls | First-seen/hash/review preserved |
|---|---:|---:|---:|---:|---|---|
| 3 | 1 | 0 | 1 | 1 | 0 / 0 | Yes |
| 4 | 11 | 0 | 11 | 11 | 0 / 0 | Yes |

Last-seen advanced or remained equal at timestamp precision; no duplicate result or review reopening occurred. Cache repeats skip discovery entirely; replay tests separately prove result memory. Run/observation bookkeeping can still be written in the isolated DB—the “last-seen only” assertion refers to unchanged result evidence/review state. Existing all-five regression tests also preserve a prior human approval. Role changes and draft-to-adopted changes are tested as `UPDATED + PENDING` on the same record. No live legal transition was observed during this short validation window.

**J. Tests and compatibility.** **399 tests passed in 19.59 seconds**. Compilation of app/scripts/migrations/entrypoints passed; dependency check reports no broken requirements. Added regressions cover weak institution content, official/unverified leadership, role-change persistence, draft/adopted distinctions, cited-law contamination, nonofficial legal sources, irrelevant medical legislation, SGG parsing and profile-body cache changes. Older tests that expected unverified named people to be retained were updated to the requested rejection behavior. Radar 1/2/5 business code, Telegram handlers, credentials and budgets were not changed. Their existing regression tests remain passing.

Evidence: `audit-output/final-migration-quality-tests.txt` and `audit-output/institution-policy-quality.json` (full candidates, live/cached run metrics and replay proof). The last cited-law guard was added after live capture; it does not change these eleven explicitly overridden SGG draft statuses and is covered in the final full suite.

**K. Remaining limitations.** Radar 3 has useful institution evidence but no live verified current officeholder. Radar 4 has official draft-version evidence but no verified current legal lifecycle, dates, or fresh strategies/studies. Failed source endpoints and the existing Culture-domain allowlist mismatch reduce coverage. Document reference extraction remains conservative, so a title/reference change across different publication sources without a verified common reference can still evade deterministic deduplication. Same-reference lifecycle behavior is tested. Neither radar is declared fully production-ready from these samples. No broad search, AI-first fallback, business-scope expansion or production search was used to hide these gaps.

**L. Exact production startup commands.** Migration is already at head. From the project directory:

```powershell
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe -m flask --app run db current
.venv\Scripts\python.exe run_bot.py
```

Ensure only one bot poller runs. These startup instructions do not automatically launch any radar. The production token was not sent to Telegram during validation; startup transport was simulated.
