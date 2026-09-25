"""Reproduce and lock the run #28+ Radar 1 keep persistence failure."""
from __future__ import annotations

import json
import logging
import traceback
from datetime import timedelta

import pytest
from pydantic import ValidationError

from backend.app.core.constants import MAX_CANDIDATE_METADATA_CHARS
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.core.radar_registry import RADAR_AGENT_REGISTRY
from backend.app.core.validation import today_in_morocco
from backend.app.db.extensions import db
from backend.app.db.models import Result, ResultObservation, SearchRun
from backend.app.modules.radar1_markets.schemas import MarketCandidate
from backend.scripts.test_agent import MockAnalyzer

CODE = 'RADAR_1_MARKETS'
PMMP_URL = (
    'https://www.marchespublics.gov.ma/index.php?'
    'page=entreprise.EntrepriseDetailsConsultation&refConsultation=1041342&orgAcronyme=o4d'
)


def _pmmp_blob(**extra):
    payload = {
        'reference': '101/2026/OFPPT',
        'buyer': 'MEFPE / OFPPT - OFFICE DE LA FORMATION PROFESSIONNELLE ET DE LA PROMOTION DU TRAVAIL',
        'object': ("Études architecturales et la conduite des travaux de démolition "
                   "et reconstruction de l'ISTA TAHANNAOUT et son Internat."),
        'announcement_type': "Avis d'appel d'offres ouvert",
        'procedure': "Appel d'offres ouvert",
        'main_category': 'Prestations intellectuelles',
        'execution_location': 'Tahannaout, Maroc',
        'estimate': {
            'amount': 3_552_000, 'currency': 'MAD', 'tax_basis': 'TTC',
            'verified': True, 'source': 'PMMP',
        },
        'deadline': {'date': '2026-10-15', 'time': '10:30'},
        'provisional_guarantee': {'amount': 70_000, 'currency': 'MAD'},
        'activity_domains': ["Services d'architecture", 'Architecture', 'Patrimoine'],
        'sme_reserved': False,
        'allotment': 'Non alloti',
        'withdrawal_mode': 'Plateforme PMMP',
        'deposit_mode': 'Dépôt électronique',
        'opening_place': 'Siège OFPPT',
        'plan_price': {'amount': 500, 'currency': 'MAD'},
        'qualifications': "Architecte / Bureau d'études",
        'documents_notice': 'DCE CPS RC BPU plans annexes disponibles',
        'meeting': None,
        'site_visit': None,
        'variant': None,
        'admin_contact': 'Service des marchés publics',
        'eligibility_conditions': ('Être architecte inscrit à l’Ordre. ' * 40)[:2000],
        'documents': {
            'dce': True, 'cps': True, 'rc': True, 'bpu_dqe': True, 'plans': True,
            'annexes': True, 'types': ['DCE', 'CPS', 'RC', 'BPU', 'PLANS', 'ANNEXES'],
        },
        'official_url': PMMP_URL,
        'detail_enriched': True,
    }
    payload.update(extra)
    return payload


def _feedback_blob(feature_pad: int = 0):
    features = [
        'architecture', 'architecture:architectural', 'architecture:architecturales',
        'architecture:etudes architecturales', 'category:p1 concours', 'procedure:competition',
        'professional', 'professional:etudes', 'professional:suivi des travaux',
        'pure_works', 'pure_works:travaux', 'token:architecturales', 'token:conduite',
        'token:demolition', 'token:etudes', 'token:internat', 'token:reconstruction',
        'token:suivi', 'token:tahannaout', 'token:travaux',
    ]
    features.extend(f'token:pad{i:04d}' for i in range(feature_pad))
    return {
        'applied': 'score_only',
        'feedback_score': -0.2,
        'adjusted_decision': 'keep',
        'n_approved_history': 3,
        'n_rejected_history': 5,
        'features': features[:30],
        'nearest_negative_patterns': [
            {'feature': 'token:travaux', 'approved': 1, 'rejected': 5},
            {'feature': 'pure_works', 'approved': 1, 'rejected': 5},
        ],
        'nearest_positive_patterns': [],
    }


def enriched_keep(*, mutate_inplace: bool = True, feature_pad: int = 0, title=None, reference='101/2026/OFPPT',
                  url=PMMP_URL, institution=None, bloated_attempts: int = 0) -> MarketCandidate:
    """Mirror collector keep: validate once, then optionally mutate metadata in place."""
    today = today_in_morocco()
    title = title or ("Études architecturales et la conduite des travaux de démolition "
                      "et reconstruction de l'ISTA TAHANNAOUT et son Internat.")
    institution = institution or (
        'MEFPE / OFPPT - OFFICE DE LA FORMATION PROFESSIONNELLE ET DE LA PROMOTION DU TRAVAIL')
    business = {
        'score': 5,
        'signals': {
            'COMPETITION': True,
            'ARCHITECTURAL_SCOPE': ['architectural', 'architecturales', 'etudes architecturales'],
        },
        'decision': 'keep',
        'priority': 1,
        'role_fit': True,
        'domain_fit': True,
        'reason_code': 'ACCEPT_ARCHITECTURAL_COMPETITION',
        'business_tracks': ['CONCOURS'],
        'rejection_reason': None,
        'business_category': 'P1_CONCOURS',
        'architecture_scope': True,
        'feedback': _feedback_blob(feature_pad),
    }
    discovery = (
        'https://www.marchespublics.gov.ma/index.php?keyWord=etudes+architecturales+patrimoine'
        '&page=entreprise.EntrepriseAdvancedSearch&searchAnnCons='
    )
    attempts = [
        discovery + f'&pad={i}&' + ('x' * 80)
        for i in range(bloated_attempts)
    ]
    meta = {
        'discovery_url': discovery,
        'pipeline': 'procurement_v5',
        'evidence_origin': 'search_provider_extraction',
        'pmmp': _pmmp_blob(),
        'detail_enrichment_status': 'enriched',
        'business_relevance': business,
        'preliminary_relevance': 'continue',
        'original_discovery_url': discovery,
        'discovered_from': discovery,
        'discovery_snapshot': {
            'title': title.casefold(),
            'reference': reference.casefold(),
            'institution': institution.casefold(),
            'deadline': (today + timedelta(days=30)).isoformat(),
            'publication_date': (today - timedelta(days=5)).isoformat(),
            'source_status': 'open',
            'url': url,
        },
        'resolution': {
            'source_status': 'VERIFIED_OFFICIAL',
            'source_type': 'OFFICIAL_PROCUREMENT',
            'discovery_url': discovery,
            'official_url': url,
            'resolution_attempted': True,
            'resolution_error': None,
            'resolution_confidence': 1.0,
            'attempts': attempts,
        },
    }
    base_fields = dict(
        title=title,
        url=url,
        source='www.marchespublics.gov.ma',
        reference=reference,
        institution=institution,
        publication_date=today - timedelta(days=5),
        deadline=today + timedelta(days=30),
        source_status='open',
        procedure_type='competition',
        morocco_related=True,
        location_evidence='Tahannaout, Maroc',
        source_quality='OFFICIAL_PRIMARY',
        official_confirmation=True,
        detail_verified=True,
        official_url=url,
        official_url_status='VERIFIED_DIRECT',
        access_mode='DIRECT_OFFICIAL',
        source_type='OFFICIAL_PROCUREMENT',
        resolution_state='VERIFIED_OFFICIAL',
        resolution_attempted=True,
        estimated_amount=3_552_000,
        estimated_currency='MAD',
        estimated_amount_tax_mode='TTC',
        estimated_amount_source='PMMP',
        estimated_amount_verified=True,
        provisional_bond_amount=70_000,
        provisional_bond_currency='MAD',
        deadline_time='10:30',
        deadline_source='PMMP',
        deadline_verified=True,
        publication_date_source='PMMP',
        publication_date_verified=True,
        document_types=['DCE', 'CPS', 'RC', 'BPU', 'PLANS', 'ANNEXES'],
        business_category='P1_CONCOURS',
        current_evidence=True,
        raw_text=title,
        eligibility_conditions=_pmmp_blob()['eligibility_conditions'],
    )
    if not mutate_inplace:
        return MarketCandidate(**base_fields, metadata=meta)
    # Legacy collector habit: construct lean, then mutate metadata without re-validation.
    lean = {k: meta[k] for k in ('discovery_url', 'pipeline', 'evidence_origin')}
    candidate = MarketCandidate(**base_fields, metadata=lean)
    for key, value in meta.items():
        if key not in lean:
            candidate.metadata[key] = value
    return candidate


def test_reproduce_normalize_failure_on_oversized_mutated_metadata():
    """PHASE 1: capture the exact exception from the keep→normalize path (old 10k guard)."""
    radar = RADAR_AGENT_REGISTRY.resolve(CODE)
    item = enriched_keep(mutate_inplace=True, bloated_attempts=20)
    meta_len = len(json.dumps(item.metadata, ensure_ascii=False, allow_nan=False))
    assert meta_len > 10000, meta_len
    # With the raised budget, production-sized keeps normalize; only absurd sizes fail.
    if meta_len <= MAX_CANDIDATE_METADATA_CHARS:
        out = radar.normalize_candidate(item)
        assert out.reference == item.reference
        return
    with pytest.raises((ValidationError, ValueError)) as caught:
        radar.normalize_candidate(item)
    assert 'Metadata exceeds' in str(caught.value)


def test_realistic_enriched_keep_metadata_size_near_production():
    """Production-like PMMP+feedback must fit the metadata budget and normalize."""
    item = enriched_keep(mutate_inplace=True, feature_pad=0, bloated_attempts=5)
    meta_len = len(json.dumps(item.metadata, ensure_ascii=False, allow_nan=False))
    assert meta_len > 2000
    assert meta_len < MAX_CANDIDATE_METADATA_CHARS
    radar = RADAR_AGENT_REGISTRY.resolve(CODE)
    assert radar.normalize_candidate(item).reference == item.reference


def test_orchestrator_persists_enriched_keep_without_candidate_error(app):
    """Run #28+ fix: collector keep → Result + Observation, zero candidate_errors."""
    item = enriched_keep(mutate_inplace=True, bloated_attempts=5)
    summary = AgentOrchestrator(
        app, collector=lambda radar: [item], analyzer=MockAnalyzer(),
    ).run_radar(CODE)
    assert summary.status == 'completed'
    assert summary.candidate_errors_count == 0
    assert summary.new_results_count + summary.manual_review_count + summary.updated_results_count >= 1
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) >= 1
        assert db.session.scalar(db.select(db.func.count()).select_from(ResultObservation)) >= 1
        run = db.session.get(SearchRun, summary.id)
        assert run.candidate_errors_count == 0
        assert not (run.run_metadata or {}).get('candidate_error_details')


def test_orchestrator_persists_multiple_keeps(app):
    """Three valid keeps must all persist; one failure must not block the others."""
    items = [
        enriched_keep(mutate_inplace=True, reference=f'10{i}/2026/OFPPT',
                      title=f'Études architecturales ISTA lot {i}',
                      url=PMMP_URL + f'&lot={i}')
        for i in (1, 2, 3)
    ]
    summary = AgentOrchestrator(
        app, collector=lambda radar: items, analyzer=MockAnalyzer(),
    ).run_radar(CODE)
    assert summary.status == 'completed'
    assert summary.candidate_errors_count == 0
    with app.app_context():
        assert db.session.scalar(db.select(db.func.count()).select_from(Result)) == 3


def test_candidate_error_logging_includes_diagnostics(app, caplog):
    """Forced persistence failure must log run_id, stage, type, message (no secrets)."""
    item = enriched_keep(mutate_inplace=True)

    class BoomResults:
        def save(self, *args, **kwargs):
            raise RuntimeError('forced_persist_boom')

    orch = AgentOrchestrator(app, collector=lambda radar: [item], analyzer=MockAnalyzer())
    orch.results = BoomResults()
    with caplog.at_level(logging.ERROR):
        summary = orch.run_radar(CODE)
    assert summary.candidate_errors_count == 1
    text = caplog.text
    assert 'forced_persist_boom' in text
    assert 'error_type=RuntimeError' in text
    assert f'run_id={summary.id}' in text
    assert 'stage=PERSIST_RESULT' in text
    assert '101/2026/OFPPT' in text
    with app.app_context():
        run = db.session.get(SearchRun, summary.id)
        details = (run.run_metadata or {}).get('candidate_error_details') or []
        assert details
        assert details[-1]['error_type'] == 'RuntimeError'
        assert details[-1]['stage'] == 'PERSIST_RESULT'
