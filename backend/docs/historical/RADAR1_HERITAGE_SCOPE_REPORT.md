# Radar 1: patrimoine-first scope — 14 September 2026

Radar 1 now requires built-heritage relevance. Architecture alone, ordinary building rehabilitation and generic public construction are rejected before AI. P1 is direct patrimonial work; P2 is explicit adjacent old built fabric and always requires review. No ambiguous P3 is automatically retained.

The deterministic gate is shared by collection, candidate validation and manager queue filtering. Legacy generic records are hidden from pending and approved queues without deleting or changing production records. Source, deadline, geography and official-link requirements still apply: P1 is business eligibility, not fabricated official approval. Human approvals remain available for relevant records.

Discovery terms now target patrimoine, medina, monuments, remparts, kasbahs and old built fabric. Query-family counts and cost limits were not increased. The Radar 1 rules version is now 8 so cached decisions are revalidated. Radar 2–5 implementation and configuration were not changed.

## Saved live-data comparison

Replayed `radar1-architecture-scope-live.json`, deduplicating by reference and title. These are historical collection observations, not a count of human-approved database rows.

| Measure | Count |
|---|---:|
| Unique observations | 60 |
| Previously business-eligible | 18 |
| Previously eligible, now rejected | 18 |
| Direct patrimonial records remaining in that snapshot (P1) | 0 |
| Adjacent records remaining in that snapshot (P2) | 0 |

Rejected examples include construction of six preschool units in Khouribga, demolition/reconstruction of the caïdat of Beni Bouyafrour, construction of the Al Amal school, staff housing in Casablanca and generic corniche development in Sidi Ifni. The snapshot did not contain a qualifying explicit built-heritage opportunity; the stricter gate does not invent context from an institution or place name.

Reproduce with `.venv/Scripts/python.exe scripts/validate_radar1_heritage.py`.
Full record decisions: [comparison JSON](audit-output/radar1-heritage-comparison.json).

## Isolated live validation

Command: `.venv/Scripts/python.exe scripts/run_live_radar.py RADAR_1_MARKETS --isolated --dry-run --direct-only --report-json audit-output/radar1-heritage-live.json`

| Measure | Count |
|---|---:|
| Raw source results | 164 |
| Rejected by relevance | 99 |
| Final direct patrimonial opportunities (P1) | 1 |
| Final adjacent opportunities (P2) | 0 |
| Verified official notices | 1 |
| Direct fetches | 21 |
| Source errors | 0 |
| Paid search calls / AI calls | 0 / 0 |
| Production result writes / Telegram messages | 0 / 0 |
| Estimated API cost | $0 |

Retained: **39/2026/ADERFES — Réalisation des études et de la mission d’accompagnement pour la valorisation du patrimoine historique bâti de la Médina de Fès, en lot unique.** [Official notice](https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation&refConsultation=1035689&orgAcronyme=g3h).

The dry-run reports this P1 candidate as manual review because classification is disabled; it does not approve or publish it. P2 examples such as old-fabric intervention and threatened housing in historic medina are verified in regression tests, but none survived this live collection. Counts describe this bounded run, not exhaustive market coverage. Raw results include repeated source observations and are not the same denominator as the saved snapshot.

An initial sandbox attempt failed to fetch sources. The network-enabled isolated retry completed successfully. Live evidence also prompted explicit rejection tests for natural/intangible heritage and a new building for historical memory: neither establishes historic built fabric by itself.

Report: [live JSON](audit-output/radar1-heritage-live.json).

## Validation and cost

Full suite: **492 passed**, including new school, gendarmerie, cemetery, generic center, public equipment, ordinary rehabilitation, location-only heritage, restoration, conservation, medina, ramparts, old fabric and mandatory P2-review regressions. Existing official-resolution, fallback-source and DCE tests pass.

Results: [pytest output](audit-output/heritage-tests-final.txt).

No additional paid service or budget was introduced. Generic candidates are stopped before enrichment/AI; P2 is reviewed deterministically without AI. Actual future savings depend on source yield and were not extrapolated from this zero-cost run. The application was not restarted or deployed, and production data was not modified.
