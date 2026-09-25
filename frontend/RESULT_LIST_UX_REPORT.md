# Radar result-list UX report

## API field audit

The frontend was audited against the existing result payload before implementation. No API, database, authentication, or business-rule changes were made.

Radar 1 list fields now used: `title`, `reference`, `institution`, `city`, `estimated_amount`, `estimated_currency`, `estimated_amount_tax_mode`, `publication`, `deadline`, `deadline_time`, `procedure`, `announcement_type`, `review_status`, and `discovery_status`.

Radar 1 detail fields additionally used when present: `main_category`, `activity_domains`, `estimated_lots`/PMMP fallback values, visit/opening PMMP values, `provisional_bond_amount`, `provisional_bond_currency`, `plan_price`, `document_types`, `dce_available`, `business_category`, `reason`, and `url`.

Other Radar lists use only already-exposed domain fields: institution/location/maturity for Radar 2; institution/person/position for Radar 3; institution/document/legal status for Radar 4; and funder/beneficiary/amount/currency for Radar 5.

Fields that remain hidden from the list are evidence, verification/source flags, summaries, policy text, qualification detail, internal resolution state, and other verbose metadata. These would reduce scan speed and belong in details or future specialist views.

## List hierarchy and columns

Radar 1 now prioritizes Objet, Acheteur, Lieu, Estimation, Publication, Échéance, Type / procédure, Statut, and Actions. Titles and buyers are clamped to two lines, references are secondary text, money and dates are compact, and row actions are lightweight.

Radars 2–5 use the same shell but domain-specific columns rather than forcing procurement fields into every view. Filtering operates on the currently loaded page, sorting is client-side and non-mutating, and API pagination remains authoritative.

## Formatting and states

Shared helpers in `lib/format.ts` normalize French dates, date/time combinations, compact/full money values, procedure labels, missing values, and status vocabulary. Shared components provide status badges plus loading, empty, and retryable error states.

## Detail view

Radar 1 details are organized into Résumé, Marché, Dates, Budget, Documents, and Classification, with a direct official-source action. Unavailable document metadata is explicitly shown as “Non vérifié” instead of being inferred.

## Responsive behavior

Desktop retains a compact comparison table. Lower-priority columns progressively hide on tablet. On mobile, rows become labeled cards and all domain fields return in a readable stacked layout. Detail sections collapse to one column and document states reflow to a single column on narrow screens.

## Validation

- `npm run typecheck`: passed
- `npm run lint`: passed
- `npm run build`: passed

Browser-based visual inspection was not available in the current automation surface, so no visual QA claim is made beyond the responsive CSS review and successful production build.
