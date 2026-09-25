"""Deterministic Radar 1 adaptive relevance from human APPROVED/REJECTED history.

No ML training, no embeddings API, no paid calls. Hard business rules always win;
this layer only adjusts confidence / P1↔P2 priority when the hard decision is keep|review.
"""
from __future__ import annotations

import logging
from threading import Lock

from app.modules.radar1_markets.policy import (
    folded, contains, HERITAGE_ASSETS, BUILT_HERITAGE_ASSETS, OLD_FABRIC, HERITAGE_WORK,
    PROFESSIONAL_SERVICES, ARCHITECTURAL_SCOPE, ARCHITECTURAL_COMPETITION, INFRASTRUCTURE_ONLY,
    PURE_WORKS, KEYWORDS,
)

logger = logging.getLogger(__name__)

# Minimum independent reviews before a feature becomes a strong signal.
MIN_FEATURE_SUPPORT = 3
# Soft influence caps (never flips a hard reject / never invents P1 from feedback alone).
MAX_ABS_SCORE = 0.85
CODE = 'RADAR_1_MARKETS'

POSITIVE_FEATURES = (
    ('heritage', HERITAGE_ASSETS + BUILT_HERITAGE_ASSETS + OLD_FABRIC),
    ('heritage_work', HERITAGE_WORK),
    ('professional', PROFESSIONAL_SERVICES),
    ('architecture', ARCHITECTURAL_SCOPE + ARCHITECTURAL_COMPETITION),
)
NEGATIVE_FEATURES = (
    ('infrastructure', INFRASTRUCTURE_ONLY),
    ('pure_works', PURE_WORKS),
    ('negative_goods', KEYWORDS['NEGATIVE']),
)


def extract_features(title, *, scope=None, category=None, procedure=None):
    """Sparse normalized feature set used for explainable overlap scoring."""
    text = folded(' '.join(part for part in (title, scope) if part))
    features = set()
    for name, terms in POSITIVE_FEATURES + NEGATIVE_FEATURES:
        hits = tuple(term for term in terms if contains(text, term))
        if hits:
            features.add(name)
            features.update(f'{name}:{term}' for term in hits[:8])
    if category:
        features.add('category:' + folded(str(category)))
    if procedure:
        features.add('procedure:' + folded(str(procedure)))
    # Stable title tokens longer than 4 chars (bounded).
    tokens = [tok for tok in text.split() if len(tok) >= 5][:12]
    features.update('token:' + tok for tok in tokens)
    return frozenset(features)


class Radar1FeedbackService:
    """In-process profile rebuilt from MarketReview / Result history."""

    def __init__(self):
        self._lock = Lock()
        self._profile = None  # {'approved': Counter-like dict, 'rejected': dict, 'n_approved', 'n_rejected'}

    def invalidate(self):
        with self._lock:
            self._profile = None

    def _empty(self):
        return {'approved': {}, 'rejected': {}, 'n_approved': 0, 'n_rejected': 0,
                'approved_examples': [], 'rejected_examples': []}

    def build_profile(self, app):
        """Load APPROVED/REJECTED Radar 1 rows and aggregate feature frequencies."""
        from collections import Counter
        from app.db.extensions import db
        from app.db.models import Result, Radar
        profile = self._empty()
        with app.app_context():
            rows = db.session.scalars(
                db.select(Result).join(Radar, Result.radar_id == Radar.id).where(
                    Radar.code == CODE,
                    Result.review_status.in_(('APPROVED', 'REJECTED'))).order_by(
                    Result.reviewed_at.desc().nullslast(), Result.id.desc()).limit(500)).all()
            approved_c, rejected_c = Counter(), Counter()
            for row in rows:
                meta = row.radar_metadata or {}
                feats = extract_features(
                    row.title, scope=meta.get('project_scope') or meta.get('scope'),
                    category=meta.get('business_category'), procedure=meta.get('procedure_type'))
                bucket = approved_c if row.review_status == 'APPROVED' else rejected_c
                examples = profile['approved_examples'] if row.review_status == 'APPROVED' else profile['rejected_examples']
                bucket.update(feats)
                if len(examples) < 12:
                    examples.append({'title': row.title, 'features': sorted(feats)[:20],
                                     'category': meta.get('business_category')})
            profile['approved'] = dict(approved_c)
            profile['rejected'] = dict(rejected_c)
            profile['n_approved'] = sum(1 for row in rows if row.review_status == 'APPROVED')
            profile['n_rejected'] = sum(1 for row in rows if row.review_status == 'REJECTED')
        with self._lock:
            self._profile = profile
        return profile

    def profile(self, app):
        with self._lock:
            cached = self._profile
        if cached is not None:
            return cached
        return self.build_profile(app)

    def score(self, app, title, *, scope=None, category=None, procedure=None, hard_decision=None):
        """Explainable feedback score in [-MAX_ABS_SCORE, +MAX_ABS_SCORE].

        hard_decision: keep|review|reject from hard policy. Feedback never overrides reject,
        and never promotes reject → keep.
        """
        features = extract_features(title, scope=scope, category=category, procedure=procedure)
        profile = self.profile(app)
        pos_hits, neg_hits = [], []
        pos_weight = neg_weight = 0.0
        for feat in features:
            a = profile['approved'].get(feat, 0)
            r = profile['rejected'].get(feat, 0)
            if a >= MIN_FEATURE_SUPPORT and a > r:
                strength = min(1.0, (a - r) / max(a + r, 1))
                pos_weight += strength
                pos_hits.append({'feature': feat, 'approved': a, 'rejected': r})
            if r >= MIN_FEATURE_SUPPORT and r > a:
                strength = min(1.0, (r - a) / max(a + r, 1))
                neg_weight += strength
                neg_hits.append({'feature': feat, 'approved': a, 'rejected': r})
        raw = pos_weight - neg_weight
        # Mixed evidence: dampen
        if pos_hits and neg_hits:
            raw *= 0.35
        score = max(-MAX_ABS_SCORE, min(MAX_ABS_SCORE, raw / 6.0))
        explanation = {
            'feedback_score': round(score, 3),
            'nearest_positive_patterns': sorted(pos_hits, key=lambda i: -i['approved'])[:5],
            'nearest_negative_patterns': sorted(neg_hits, key=lambda i: -i['rejected'])[:5],
            'n_approved_history': profile['n_approved'],
            'n_rejected_history': profile['n_rejected'],
            'features': sorted(features)[:30],
        }
        adjusted = hard_decision
        # Soft adjustments only.
        if hard_decision == 'reject':
            explanation['applied'] = 'hard_reject_unchanged'
        elif hard_decision == 'keep' and score <= -0.45 and len(neg_hits) >= 2:
            adjusted = 'review'
            explanation['applied'] = 'demote_keep_to_review'
        elif hard_decision == 'review' and score >= 0.45 and len(pos_hits) >= 2 and not neg_hits:
            # Stay review — never auto-promote to keep from feedback alone.
            explanation['applied'] = 'positive_support_keep_human_review'
        else:
            explanation['applied'] = 'score_only'
        explanation['adjusted_decision'] = adjusted
        return explanation


_feedback_service = Radar1FeedbackService()


def get_feedback_service():
    return _feedback_service
