from app.core.radar_agent_base import RadarRules, SourceStrategy

SOURCES = SourceStrategy(('SGG', 'Bulletin Officiel', 'Ministries', 'Parliament'), ('CESE', 'HCP', 'Policy studies'), True)
RULES = RadarRules(
    relevance=('Monitor laws, drafts, decrees, orders, circulars, standards, strategies, reforms and planning studies.',
               'Explain what changed, who is affected and which projects or studies may follow.'),
    exclusions=('Never present draft laws as adopted, announcements as regulation, or media interpretation as official law.',),
    priorities=('Prioritize verified changes affecting relevant projects and studies; keep prospective impacts conditional.',),
    categories=('law', 'draft_law', 'decree', 'strategy', 'public_program', 'planning_study', 'other'),
    validation=('A: adopted/in force. B: implementation underway. C: officially in preparation. D: monitor signal.',
                'Legal claims require explicit reliable status evidence; draft/adopted contradictions are rejected.'),
)

from app.core.conditions import StrictConditions, Predicate
CONDITIONS = StrictConditions(
    inclusion_rules=(), exclusion_rules=(Predicate('outdated_without_relevance', 'equals'),),
    freshness_days=365, geography_required=False, source_rules=('OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY', 'RELIABLE_SECONDARY'),
    mandatory_fields=(('title',), ('url',), ('source',), ('reported_status',)),
    priority_rules=(('legal_status', 1),),
    manual_review_triggers=(Predicate('reported_status', 'equals', 'POLICY_SIGNAL'), Predicate('source_conflict', 'equals')),
)
