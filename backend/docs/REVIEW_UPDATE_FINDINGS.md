# Reviewed result updates — 3 October 2026

The configured database was inspected in a PostgreSQL read-only transaction.
No production records or decisions were changed. Full query findings are in
`REVIEW_UPDATE_CURRENT_AUDIT.json`.

| Result | Most recent human decision | Latest reopen trigger recorded by the old code | Actual business difference in surrounding persisted observations | Assessment |
| --- | --- | --- | --- | --- |
| #103, Sidi Ifni corniche, `04/2026/CA/BR/RGON` | Rejected, 30 September 2026; previously approved 14 September, then rejected 16 September | `estimated_currency`, `estimated_amount_tax_mode`, `estimated_amount_source` | Currency and tax labels became MAD / TTC, but the estimate amount stayed unknown; title, deadline, buyer, location and procedure did not change | Not materially justified. Placeholder/provenance enrichment must preserve the rejection. Earlier reopens with empty changed fields and `business_category` alone were also unjustified. |
| #138, ancienne médina de Guelmim, `36/BR/RGON/2026` | Rejected, 18 September 2026 | The same estimate labels/provenance plus `business_category` | Provisional guarantee changed **7,000,000 → 70,000 MAD**; the old detector omitted this field. No title, deadline, buyer, location or procedure change was found | Material correction in the stored business value warrants review. This is not proof that the procurement authority amended its notice; it could be a parsing correction. |
| #139, Guelmim regional headquarters annex, `06/2026/CA/BR/RGON` | Approved, 18 September 2026 | None | No reopen event | Remains approved. This is a separate opportunity from the médina result. |

The other matching Guelmim records (#109 and #161) have no recorded human
decisions or reopen events and are not examples of reviewed results reopening.

## Implementation

- Discovery collection, identities, hashes and relevance rules are unchanged.
- Reopening a reviewed Radar 1 result now requires a normalized procurement
  difference. Technical provenance, classification and formatting alone do not
  reopen it. Currency / tax labels without an estimate amount do not reopen it.
- Location, deadline time, guarantees and documents are compared alongside
  title, buyer, deadline, estimate and procedure.
- Each new review stores a business snapshot in the existing append-only review
  and audit tables. Subsequent reviews add records; they do not replace history.
- Result cards expose the prior review and only recorded before/after values.
  Legacy snapshots are compared only for keys they actually contain.
- The shared table shows “Mis à jour” with “Validé auparavant” or “Rejeté auparavant”,
  plus expandable “Modifications” when a supported comparison exists.

The changes prevent future false reopens. Existing production queue decisions
were left intact; this change does not silently undo historical reopen events.

## Validation

Frontend typecheck, lint and production build pass. Regression coverage includes
unchanged and technical updates, material fields, rejection context, both kinds
of second decision, append-only history, unknown legacy values and the list /
run-scoped / detail API payloads. A React render check verifies the French context
labels, date changes and hiding the summary when no recorded differences exist.

Five existing tests in `test_official_resolution_fallback.py` fail before result
persistence: the pre-existing collector changes call the listing index outside
a Flask application context. That discovery path was not modified for this task;
those five cases are reported separately from the passing review/API checks.
