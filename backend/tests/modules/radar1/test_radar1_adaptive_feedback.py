"""Adaptive Radar 1 feedback — local, explainable, hard-rules win, zero paid calls."""
from types import SimpleNamespace
from unittest.mock import Mock

from backend.app.modules.radar1_markets.policy import evaluate_relevance
from backend.app.modules.radar1_markets.feedback import (
    Radar1FeedbackService, extract_features, MIN_FEATURE_SUPPORT)


def _profile_with(approved_titles, rejected_titles):
    service = Radar1FeedbackService()
    approved, rejected = {}, {}
    for title in approved_titles:
        for feat in extract_features(title):
            approved[feat] = approved.get(feat, 0) + 1
    for title in rejected_titles:
        for feat in extract_features(title):
            rejected[feat] = rejected.get(feat, 0) + 1
    # Amplify shared features to meet minimum support.
    for feat, count in list(approved.items()):
        if count >= 1:
            approved[feat] = max(count, MIN_FEATURE_SUPPORT)
    for feat, count in list(rejected.items()):
        if count >= 1:
            rejected[feat] = max(count, MIN_FEATURE_SUPPORT)
    service._profile = {
        'approved': approved, 'rejected': rejected,
        'n_approved': len(approved_titles), 'n_rejected': len(rejected_titles),
        'approved_examples': [], 'rejected_examples': [],
    }
    return service


def test_positive_heritage_history_raises_feedback_score():
    service = _profile_with(
        approved_titles=[
            'Études et suivi réhabilitation ancienne médina',
            'Étude patrimoniale médina patrimoine',
            'Diagnostic architectural médina patrimoine',
        ],
        rejected_titles=[],
    )
    app = SimpleNamespace()
    explanation = service.score(
        app, 'Études et suivi des travaux de réhabilitation de l’ancienne médina',
        hard_decision='keep')
    assert explanation['feedback_score'] > 0
    assert explanation['nearest_positive_patterns']


def test_negative_infrastructure_history_lowers_score():
    service = _profile_with(
        approved_titles=[],
        rejected_titles=[
            'Études voirie assainissement',
            'Études techniques réseaux voirie',
            'Suivi travaux assainissement voirie',
        ],
    )
    app = SimpleNamespace()
    explanation = service.score(
        app, 'Études et suivi des travaux de voirie et assainissement',
        hard_decision='review')
    assert explanation['feedback_score'] < 0
    assert explanation['nearest_negative_patterns']


def test_mixed_history_does_not_force_reject():
    service = _profile_with(
        approved_titles=['Études médina patrimoine', 'Étude médina patrimoine', 'Diagnostic médina patrimoine'],
        rejected_titles=['Études voirie', 'Études assainissement', 'Études réseaux voirie'],
    )
    app = SimpleNamespace()
    explanation = service.score(app, 'Études mixtes', hard_decision='review')
    assert explanation['adjusted_decision'] == 'review'


def test_hard_reject_overrides_positive_feedback():
    service = _profile_with(
        approved_titles=['Études médina patrimoine'] * 3,
        rejected_titles=[],
    )
    hard = evaluate_relevance('Travaux de restauration d’un monument historique')
    assert hard['decision'] == 'reject'
    explanation = service.score(
        SimpleNamespace(), 'Travaux de restauration d’un monument historique',
        hard_decision='reject')
    assert explanation['adjusted_decision'] == 'reject'
    assert explanation['applied'] == 'hard_reject_unchanged'


def test_feedback_scoring_makes_zero_external_calls(monkeypatch):
    service = _profile_with(
        approved_titles=['Études médina patrimoine'] * 3,
        rejected_titles=['Études voirie'] * 3,
    )
    calls = {'http': 0, 'openai': 0}

    def boom(*a, **k):
        calls['http'] += 1
        raise AssertionError('HTTP must not be called')

    monkeypatch.setattr('urllib.request.build_opener', boom)
    monkeypatch.setattr('urllib.request.urlopen', boom)
    explanation = service.score(
        SimpleNamespace(), 'Études et suivi ancienne médina', hard_decision='keep')
    assert calls['http'] == 0
    assert 'feedback_score' in explanation
