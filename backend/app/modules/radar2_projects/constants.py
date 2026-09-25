from app.core.radar_agent_base import RadarRules, SourceStrategy

SOURCES = SourceStrategy(('Official project announcements', 'Signed conventions', 'Investment programs'), ('Credible media',), True)
RULES = RadarRules(
    relevance=('Detect projects before procurement: conventions, secured funding, approved programs and feasibility studies.',
               'Monitor architecture, AMO, territorial strategy, diagnostics, restoration and urban planning opportunities.'),
    exclusions=('Exclude already published tenders.', 'Exclude completed projects without a new phase.'),
    priorities=('Prioritize financed or programmed projects, then official structuring announcements, then credible weak signals.',),
    categories=('project_preparation', 'feasibility', 'rehabilitation', 'development_program', 'other'),
    validation=('A: financed/programmed. B: official announcement/structuring. C: weak signal requiring credibility review.',
                'Reject completed projects unless a new phase is evidenced.'),
)

from app.core.conditions import StrictConditions, Predicate
CONDITIONS = StrictConditions(
    inclusion_rules=(Predicate('signal_type', 'in', ('PROJECT_ANNOUNCED', 'CONVENTION_SIGNED',
        'FINANCING_APPROVED', 'PROGRAM_APPROVED', 'STUDY_LAUNCHED', 'FEASIBILITY_PREPARATION',
        'DESIGN_PREPARATION', 'LAND_OR_SITE_PREPARATION', 'PARTNER_SELECTED', 'BUDGET_ALLOCATED',
        'IMPLEMENTATION_PREPARATION')),),
    exclusion_rules=(Predicate('published_tender', 'equals'), Predicate('vague_statement', 'equals')),
    freshness_days=90, geography_required=True, source_rules=('OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY', 'RELIABLE_SECONDARY'),
    mandatory_fields=(('title',), ('source',), ('url',), ('signal_evidence',), ('publication_date',)),
    priority_rules=(('financing_secured', 1), ('officially_announced', 2)),
    manual_review_triggers=(Predicate('source_quality', 'equals', 'RELIABLE_SECONDARY'), Predicate('future_opportunity_uncertain', 'equals')),
)
