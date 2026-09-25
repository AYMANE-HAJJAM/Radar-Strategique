from app.core.radar_agent_base import RadarRules, SourceStrategy

SOURCES = SourceStrategy(('Official institution websites', 'Organization charts', 'Nomination announcements'),
                         ('LinkedIn and public professional sources',), True)
MAX_ROLE_VERIFICATION_AGE_DAYS = 180
RULES = RadarRules(
    relevance=('Monitor ministries, agencies, regions, municipalities, public companies, foundations and associations.',
               'Identify strategic, technical, project-preparation, procurement and partnership/funding roles.'),
    exclusions=('Do not label obsolete office holders as current without recent verification.',),
    priorities=('Prioritize verified responsibility and recent relevant activity, not merely job seniority.',),
    categories=('institution', 'appointment', 'institutional_activity', 'other'),
    validation=('Current role requires explicit verification, official source and verification date no older than 180 days.',
                'Unverified or stale roles must be flagged for manual review.'),
)

from app.core.conditions import StrictConditions, Predicate
CONDITIONS = StrictConditions(
    inclusion_rules=(Predicate('institution_relevant', 'equals'),),
    exclusion_rules=(Predicate('obsolete_holder', 'equals'),), freshness_days=180, geography_required=False,
    source_rules=('OFFICIAL_PRIMARY', 'OFFICIAL_SECONDARY', 'RELIABLE_SECONDARY'),
    mandatory_fields=(('institution',), ('source',), ('url',)),
    priority_rules=(('role_verified', 1),),
    manual_review_triggers=(Predicate('source_conflict', 'equals'), Predicate('nomination_unconfirmed', 'equals')),
)
