from app.core.radar_agent_base import RadarRules, SourceStrategy

SOURCES = SourceStrategy(('Donor official sites', 'Project pipelines', 'Procurement plans', 'Financing agreements'), collection_enabled=True)
DONORS = ('World Bank', 'AfDB', 'EIB', 'EBRD', 'AFD', 'EU', 'KfW', 'Public financing institutions',
          'Development funds', 'Investment funds', 'Climate funds', 'Territorial funds', 'Cultural funds')
RULES = RadarRules(
    relevance=('Monitor financing related to Morocco, including territorial, cultural, development and climate programs.',
               'Distinguish direct applicant, consultant, beneficiary contractor, future procurement and monitoring roles.'),
    exclusions=('Exclude programs confirmed unrelated to Morocco.', 'Do not infer direct eligibility from geographic relevance.'),
    priorities=('Prioritize evidenced accessible funding and consulting/procurement pathways; retain strategic closed programs.',),
    categories=('grant', 'loan', 'technical_assistance', 'investment', 'procurement_pipeline', 'other'),
    validation=('A: open/mobilizable. B: active. C: preparation. D: pipeline. E: closed but strategically useful.',
                'Direct application requires explicit eligibility evidence; unknown scope/status/access requires review.'),
)

from app.core.conditions import StrictConditions, Predicate
CONDITIONS = StrictConditions(
    inclusion_rules=(), exclusion_rules=(Predicate('general_donor_page', 'equals'),),
    freshness_days=180, geography_required=True, source_rules=('OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY'),
    mandatory_fields=(('title',), ('source',), ('url',), ('funder',), ('program',), ('reported_funding_status',),
                      ('beneficiary', 'eligibility', 'potential_procurement')),
    priority_rules=(('open', 1), ('active', 2), ('closed', 3)),
    manual_review_triggers=(Predicate('source_conflict', 'equals'),),
)
