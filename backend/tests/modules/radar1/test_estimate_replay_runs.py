"""Offline replay of the run #33 and #35 candidates dropped on '* TTC MAD'."""
import importlib

from app.core.orchestrator import AgentOrchestrator
from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.db.extensions import db
from app.db.models import Result, SearchRun
from app.modules.radar1_markets.validators import business_relevance
from tests.modules.radar1.test_radar1_persistence_regression import enriched_keep

CODE = 'RADAR_1_MARKETS'

RUN_35 = (
    {
        'run': 35,
        'reference': '101/2026/OFPPT',
        'title': ("Études architecturales et la conduite des travaux de démolition "
                  "et reconstruction de l'ISTA TAHANNAOUT et son Internat."),
        'url': ('https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation'
                '&refConsultation=1041342&orgAcronyme=o4d'),
        'institution': 'MEFPE / OFPPT - OFFICE DE LA FORMATION PROFESSIONNELLE ET DE LA PROMOTION DU TRAVAIL',
        'location': 'Tahannaout, Maroc',
    },
    {
        'run': 35,
        'reference': '04/2026/CA/BR/RGON',
        'title': ("L'élaboration des études architecturales et suivi des travaux "
                  "d'aménagement de la corniche de SIDI IFNI."),
        'url': ('https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation'
                '&refConsultation=1032453&orgAcronyme=m8x'),
        'institution': 'RGON / RGON - REGION DE GUELMIM - OUED NOUN',
        'location': 'Sidi Ifni, Maroc',
    },
    {
        'run': 35,
        'reference': '03/2026',
        'title': "Elaboration du plan d’aménagement et de sauvegarde de la médina de tiznit",
        'url': ('https://www.marchespublics.gov.ma/index.php?page=entreprise.EntrepriseDetailsConsultation'
                '&refConsultation=1042105&orgAcronyme=j8k'),
        'institution': 'MHUAE / AUT - AGENCE URBAINE DE TAROUDANNT',
        'location': 'Tiznit, Maroc',
    },
)
RUN_33 = tuple(item for item in RUN_35 if item['reference'] != '03/2026')


def _poisoned(spec):
    """Collector-shaped keep with the placeholder still sitting on estimated_amount."""
    item = enriched_keep(
        mutate_inplace=True,
        reference=spec['reference'],
        title=spec['title'],
        url=spec['url'],
        institution=spec['institution'],
    )
    return item.model_copy(update={
        'estimated_amount': '* TTC MAD',
        'estimated_amount_verified': True,
        'location_evidence': spec['location'],
        'provisional_bond_amount': 70_000,
        'provisional_bond_currency': 'MAD',
    })


def _analyzer(radar):
    """Build the analysis response with the same model module the running agent uses."""
    parent = radar.analysis_schema.__mro__[1]
    module = importlib.import_module(parent.__module__)

    class Analyzer:
        def analyze_candidate(self, candidate, radar_context, *, analysis_schema, instructions=None):
            return module.AnalysisResponse(
                analysis=analysis_schema(
                    relevant=True, priority=2, score=80, category='architectural_consultation',
                    summary='Candidat de demonstration.', reason='Donnees fictives de test.',
                    confidence=0.95, needs_manual_review=True),
                usage=module.TokenUsage(), model='mock')

    return Analyzer()


def _run(app, specs):
    items = [_poisoned(spec) for spec in specs]
    radar = RADAR_AGENT_REGISTRY.resolve(CODE)
    summary = AgentOrchestrator(
        app, collector=lambda radar: items, analyzer=_analyzer(radar),
    ).run_radar(CODE)
    outcomes = []
    with app.app_context():
        run = db.session.get(SearchRun, summary.id)
        errors = (run.run_metadata or {}).get('candidate_error_details') or []
        for spec, item in zip(specs, items):
            normalized = radar.normalize_candidate(item)
            row = db.session.scalar(db.select(Result).where(Result.reference == spec['reference']))
            policy = business_relevance(normalized)
            outcomes.append({
                'run': spec['run'],
                'reference': spec['reference'],
                'amount': normalized.estimated_amount,
                'verified': normalized.estimated_amount_verified,
                'currency': normalized.estimated_currency,
                'tax': normalized.estimated_amount_tax_mode,
                'bond': normalized.provisional_bond_amount,
                'policy': policy['decision'],
                'reason_code': policy['reason_code'],
                'discovery_status': None if row is None else row.discovery_status,
                'review_status': None if row is None else row.review_status,
            })
    return summary, errors, outcomes


def test_run_35_placeholders_normalize_and_persist(app):
    summary, errors, outcomes = _run(app, RUN_35)
    assert summary.status == 'completed'
    assert summary.candidate_errors_count == 0
    assert not any('* TTC MAD' in (error.get('error_message') or '') for error in errors)
    assert len(outcomes) == 3
    for outcome in outcomes:
        assert outcome['amount'] is None
        assert outcome['verified'] is False
        assert outcome['currency'] == 'MAD'
        assert outcome['tax'] == 'TTC'
        assert outcome['bond'] == 70_000
        if outcome['reference'] == '101/2026/OFPPT':
            assert outcome['policy'] == 'reject'
            assert outcome['reason_code'] == 'REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC'
            continue
        assert outcome['policy'] in {'keep', 'review'}
        assert outcome['discovery_status'] == 'NEW'
    by_ref = {item['reference']: item for item in outcomes}
    assert by_ref['04/2026/CA/BR/RGON']['policy'] == 'keep'
    assert by_ref['03/2026']['policy'] in {'keep', 'review'}


def test_run_33_placeholders_replay_without_normalization_error(app):
    first, first_errors, _ = _run(app, RUN_33)
    assert first.candidate_errors_count == 0
    assert not first_errors
    second, errors, outcomes = _run(app, RUN_33)
    assert second.status == 'completed'
    assert second.candidate_errors_count == 0
    assert not any('* TTC MAD' in (error.get('error_message') or '') for error in errors)
    assert {item['reference'] for item in outcomes} == {'101/2026/OFPPT', '04/2026/CA/BR/RGON'}
    for outcome in outcomes:
        assert outcome['amount'] is None
        if outcome['reference'] == '101/2026/OFPPT':
            assert outcome['policy'] == 'reject'
            assert outcome['reason_code'] == 'REJECT_GENERIC_ARCHITECTURE_NOT_STRATEGIC'
            continue
        assert outcome['discovery_status'] == 'UNCHANGED', outcome
        assert outcome['policy'] == 'keep'
