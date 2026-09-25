from app.core.radar_agent_base import RadarRules, SourceStrategy

SOURCES = SourceStrategy(('PMMP', 'Institutional procurement pages'), ('Official buyer notices',), collection_enabled=True)
RULES = RadarRules(
    relevance=('Morocco only: current tenders, consultations, architectural competitions and purchase orders.',
               'Built heritage plus plausible cultural/historical heritage studies and valorisation.',
               'Architectural competitions and proven major architecture projects.'),
    exclusions=('Exclude confirmed expired opportunities and opportunities outside Morocco.',
                'Reject ordinary architecture/construction and infrastructure without central architectural scope.'),
    priorities=('P1: heritage, restoration and historic architecture.',
                'P1: architectural competitions and proven major architecture projects.',
                'P2: credible heritage or major-architecture potential requiring manual review.'),
    categories=('tender', 'consultation', 'architectural_consultation', 'competition', 'purchase_order', 'study', 'amo', 'other'),
    validation=('Reject confirmed expired deadline.', 'Reject confirmed non-Moroccan scope.',
                'Unknown scope or deadline requires manual review; prefer official evidence.'),
)

from app.core.conditions import StrictConditions, Predicate, ConfidenceRules

from app.modules.radar1_markets.policy import KEYWORDS
P1_TERMS = KEYWORDS['HERITAGE_STRONG']
P2_TERMS = ('bati ancien', 'tissu ancien', 'menacant ruine')
ALLOWED_PROCEDURES = ('tender', 'consultation', 'architectural_consultation', 'competition', 'purchase_order',
                      'study', 'intellectual_services', 'amo', 'moe', 'expression_of_interest', 'unknown')
CONDITIONS = StrictConditions(
    inclusion_rules=(Predicate('procedure_type', 'in', ALLOWED_PROCEDURES),),
    exclusion_rules=(Predicate('source_status', 'in', ('closed', 'expired', 'cancelled', 'awarded')),),
    freshness_days=30, geography_required=True,
    source_rules=('OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY'),
    mandatory_fields=(('title',), ('source',), ('url',), ('institution',), ('publication_date', 'official_date_evidence'),
                      ('source_status',), ('location_evidence',)),
    priority_rules=tuple((term, 1) for term in P1_TERMS) + tuple((term, 2) for term in P2_TERMS),
    manual_review_triggers=(Predicate('source_conflict', 'equals'), Predicate('reference_conflict', 'equals')),
)

# Each family is always scoped to one configured source strategy.
QUERY_CLUSTERS = ('restauration conservation', 'sauvegarde rehabilitation',
    'concours architectural', 'grand projet architectural',
    'valorisation patrimoine culturel', 'centre historique ancienne ville',
    'sites archeologiques circuits patrimoniaux', 'architecture traditionnelle',
    'bati ancien consolidation')
