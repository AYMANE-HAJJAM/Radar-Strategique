"""Independent discovery and human-decision lifecycle for actionable results."""
from enum import StrEnum

from app.db.extensions import db
from app.db.models import ResultAuditEvent
from app.core.dedup import canonical_url, normalize_text


class DiscoveryStatus(StrEnum):
    NEW = 'NEW'
    UPDATED = 'UPDATED'
    UNCHANGED = 'UNCHANGED'


class ReviewStatus(StrEnum):
    PENDING = 'PENDING'
    APPROVED = 'APPROVED'
    REJECTED = 'REJECTED'


COMMERCIAL_FIELDS = ('title', 'institution', 'reference', 'publication_date', 'deadline', 'source_status')
_TEXT_COMMERCIAL = frozenset({'title', 'institution', 'reference', 'source_status'})

# Metadata keys compared raw (no text normalize).
_RAW_META = (
    'estimated_amount', 'estimated_currency', 'estimated_amount_tax_mode',
    'estimated_amount_source', 'estimated_amount_verified', 'estimated_lots',
    'publication_date_source', 'publication_date_verified', 'deadline_time',
    'business_category', 'competition_prize_amount',
    'competition_regulation_available', 'eligibility_conditions',
)

# Metadata keys compared with normalize_text when either side is a string.
_TEXT_META_GROUPS = (
    ('signal_type', 'maturity', 'estimated_budget', 'partners', 'project_name', 'location'),
    ('person', 'position', 'role_type', 'institution_name', 'activity_type',
     'recent_activity', 'current_programs', 'recent_projects', 'decision_makers'),
    ('document_type', 'legal_status', 'reported_status', 'reference_number',
     'effective_date', 'scope', 'official_document_url'),
    ('program_name', 'funder', 'opportunity_type', 'funding_status', 'reported_funding_status',
     'beneficiary', 'amount', 'currency', 'approval_date', 'closing_date', 'procurement_url'),
)


def _url(value):
    try:
        return canonical_url(value) if value else None
    except ValueError:
        return None


def _meta_changed(old_meta, new_fields, field, *, normalize=False):
    """True when a metadata field differs; optional text normalize for string sides."""
    if normalize and field not in old_meta and field not in new_fields:
        return False
    old, new = old_meta.get(field), new_fields.get(field)
    if field == 'official_url':
        old, new = _url(old), _url(new)
    elif normalize and (isinstance(old, str) or isinstance(new, str)):
        old, new = normalize_text(old), normalize_text(new)
    return old != new


class ResultWorkflowService:
    def changed_fields(self, existing, candidate):
        changed = []
        for field in COMMERCIAL_FIELDS:
            old, new = getattr(existing, field, None), getattr(candidate, field, None)
            if field in _TEXT_COMMERCIAL:
                old, new = normalize_text(old), normalize_text(new)
            if old != new:
                changed.append(field)
        old_meta, new_fields = existing.radar_metadata or {}, candidate.radar_fields()
        for field in ('official_url', 'procedure_type', 'official_confirmation'):
            if _meta_changed(old_meta, new_fields, field):
                changed.append(field)
        for field in _RAW_META:
            if old_meta.get(field) != new_fields.get(field):
                changed.append(field)
        for group in _TEXT_META_GROUPS:
            for field in group:
                if _meta_changed(old_meta, new_fields, field, normalize=True):
                    changed.append(field)
        return changed

    def is_meaningful_update(self, existing, candidate):
        return bool(self.changed_fields(existing, candidate))

    def mark_unchanged(self, row):
        row.discovery_status = DiscoveryStatus.UNCHANGED

    def apply_saved_result(self, row, *, is_new, relevant, changed_fields):
        if is_new:
            row.discovery_status = DiscoveryStatus.NEW
            if relevant:
                row.review_status = ReviewStatus.PENDING
            row.update_reason = {'changed_fields': []}
            self.audit(row, 'DISCOVERED', {'review_status': row.review_status})
            return
        row.discovery_status = DiscoveryStatus.UPDATED
        row.update_reason = {'changed_fields': changed_fields}
        previous = row.review_status
        if relevant:
            row.review_status = ReviewStatus.PENDING
            event = 'REOPENED' if previous in {ReviewStatus.APPROVED, ReviewStatus.REJECTED} else 'UPDATED'
        else:
            event = 'UPDATED'
        self.audit(row, event, {'changed_fields': changed_fields, 'previous_review_status': previous})

    def audit(self, row, event_type, metadata=None, performed_by=None):
        db.session.add(ResultAuditEvent(result_id=row.id, event_type=event_type,
            performed_by=performed_by, event_metadata=metadata or {}))

    def apply_human_decision(self, row, decision, user_id, at, previous_reason, radar_code=None):
        previous_status = row.review_status
        status = ReviewStatus.APPROVED if decision == 'approved' else ReviewStatus.REJECTED
        row.review_status, row.reviewed_by, row.reviewed_at = status, user_id, at
        self.audit(row, status.value, {'previous_review_reason': previous_reason,
            'discovery_status': row.discovery_status, 'content_hash': row.content_hash,
            'radar': radar_code, 'decision': decision,
            'previous_status': str(previous_status), 'new_status': status.value}, user_id)


"""Shared result queue browsing and audited human decisions (all radars); no network calls."""
from datetime import datetime, timezone
from itertools import islice

from app.core.constants import PAGE_SIZE, MAX_PAGE_INDEX
from app.db.extensions import db
from app.db.models import Result, Radar, MarketReview, SearchRun, ResultObservation, utcnow
from app.core.validation import today_in_morocco
from app.core.dedup import canonical_url
from app.modules.radar1_markets.validators import review_code
from app.core.review import ResultWorkflowService, ReviewStatus
from app.modules.radar1_markets.policy import detail_url, aggregate_title, evaluate_relevance
from app.integrations.pmmp.client import is_pmmp, is_direct_notice
from app.modules.radar1_markets.institutional_search import official_institution

CODE = 'RADAR_1_MARKETS'


def queue_scope(row):
    """Title + optional scope text used by the final Radar 1 business gate."""
    metadata = row.radar_metadata or {}
    return metadata.get('project_scope') or metadata.get('scope') or (row.analysis or {}).get('project_scope')


def business_queue_eligible(row):
    """Radar 1 final business gate before a Result may appear in À traiter."""
    from flask import current_app, has_app_context
    metadata = row.radar_metadata or {}
    threshold = current_app.config.get('MAJOR_PROJECT_ESTIMATE_THRESHOLD_MAD', 20_000_000) if has_app_context() else 20_000_000
    return evaluate_relevance(row.title, scope=queue_scope(row),
        estimated_amount=metadata.get('estimated_amount'),
        amount_verified=bool(metadata.get('estimated_amount_verified')),
        procedure_type=metadata.get('procedure_type'), threshold_mad=threshold)['decision'] != 'reject'


# Legacy alias — prefer business_queue_eligible in new code.
architecture_pending = business_queue_eligible


def pending_eligible(row, code=CODE):
    if code != CODE:
        return True
    if obsolete(row):
        return False
    return business_queue_eligible(row)


def _official_domains(app):
    from app.modules.radar1_markets.policy import source_role
    return tuple(domain for domain in app.config['RADAR1_SOURCE_WHITELIST']
                 if source_role('https://' + domain, app.config) in {'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'})


def obsolete(row):
    today = today_in_morocco()
    metadata = row.radar_metadata or {}
    if aggregate_title(row.title) or (not metadata.get('detail_verified') and metadata.get('resolution_state') != 'UNVERIFIED_BUT_CREDIBLE'):
        return True
    if row.source_status in {'closed', 'expired', 'awarded', 'cancelled'} or metadata.get('morocco_related') is False:
        return True
    if row.deadline and row.deadline < today:
        return True
    if metadata.get('deadline_at'):
        try:
            stamp = datetime.fromisoformat(metadata['deadline_at'])
            if stamp.tzinfo and stamp <= datetime.now(timezone.utc):
                return True
        except ValueError:
            pass
    return bool(row.publication_date and (today - row.publication_date).days > 30 and
                not metadata.get('current_evidence') and not (row.deadline and row.deadline >= today))


def current(row):
    if not business_queue_eligible(row) or obsolete(row):
        return False
    today = today_in_morocco()
    metadata = row.radar_metadata or {}
    if row.source_status != 'open' or metadata.get('morocco_related') is False:
        return False
    if row.deadline and row.deadline < today:
        return False
    if metadata.get('deadline_at'):
        try:
            stamp = datetime.fromisoformat(metadata['deadline_at'])
            if stamp.tzinfo is None or stamp <= datetime.now(timezone.utc):
                return False
        except ValueError:
            return False
    return bool((row.deadline and row.deadline >= today) or metadata.get('current_evidence') or
                (row.publication_date and 0 <= (today - row.publication_date).days <= 30))


def best_link(row, domains=()):
    metadata = row.radar_metadata or {}
    discovery = (row.source_metadata or {}).get('metadata', {}).get('discovery_url')
    choices = []
    official_choices = () if metadata.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE' else (metadata.get('official_url'), row.url, discovery)
    for url in official_choices:
        if not url:
            continue
        try:
            canonical_url(url)
        except (ValueError, TypeError):
            continue
        if len(url) > 2000 or not detail_url(url) or aggregate_title(row.title):
            continue
        if is_direct_notice(url):
            rank, label = 0, 'officiel PMMP'
        elif official_institution(url, domains) and not is_pmmp(url):
            rank, label = 1, 'institutionnel officiel'
        else:
            continue
        choices.append((rank, url, label))
    if not choices and metadata.get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE':
        from flask import current_app
        from app.modules.radar1_markets.policy import source_role
        for url in (discovery, row.url):
            if url and source_role(url, current_app.config) in {'PROCUREMENT_AGGREGATOR', 'OFFICIAL_PROCUREMENT', 'OFFICIAL_INSTITUTIONAL'}:
                try:
                    canonical_url(url)
                    return url, 'source secondaire'
                except (ValueError, TypeError):
                    pass
    if not choices:
        return None, 'indisponible'
    _, url, label = min(choices, key=lambda item: item[0])
    return url, label


def card(row, domains=(), code=CODE):
    metadata = row.radar_metadata or {}
    pmmp = metadata.get('pmmp') or {}
    estimate = pmmp.get('estimate') if isinstance(pmmp.get('estimate'), dict) else {}
    guarantee = (pmmp.get('provisional_guarantee')
                 if isinstance(pmmp.get('provisional_guarantee'), dict) else {})

    def stored(primary, fallback=None):
        """Prefer a persisted top-level value (including zero), then PMMP detail data."""
        value = metadata.get(primary)
        return value if value is not None and value != '' else fallback

    if code != CODE:
        url = (metadata.get('official_url') or metadata.get('official_document_url') or
               metadata.get('source_url') or row.url)
        label = 'source officielle' if metadata.get('official_url') or metadata.get('official_document_url') else 'source'
    else:
        url, label = best_link(row, domains)
    reason = metadata.get('review_reason') or (row.analysis or {}).get('review_reason') or ''
    return dict(id=row.id, version=(row.content_hash or '')[:12], title=row.title,
                discovery_status=row.discovery_status, review_status=row.review_status,
                business_category=metadata.get('business_category'),
                institution=row.institution, city=(metadata.get('location_evidence') or metadata.get('location') or
                    metadata.get('city_region') or metadata.get('territory')),
                procedure=stored('procedure_type', pmmp.get('procedure')), publication=str(row.publication_date or '—'),
                deadline=str(row.deadline or '—'), status=row.source_status, reference=row.reference,
                estimated_amount=stored('estimated_amount', estimate.get('amount') if estimate else metadata.get('budget')),
                estimated_currency=stored('estimated_currency', estimate.get('currency') if estimate else metadata.get('currency')),
                estimated_amount_tax_mode=stored('estimated_amount_tax_mode', estimate.get('tax_basis')),
                estimated_amount_source=metadata.get('estimated_amount_source'),
                estimated_amount_verified=bool(metadata.get('estimated_amount_verified')),
                estimated_lots=metadata.get('estimated_lots') or [],
                provisional_bond_amount=stored('provisional_bond_amount', guarantee.get('amount')),
                provisional_bond_currency=stored('provisional_bond_currency', guarantee.get('currency')),
                publication_verified=bool(metadata.get('publication_date_verified')),
                publication_source=metadata.get('publication_date_source'),
                deadline_verified=bool(metadata.get('deadline_verified')),
                deadline_source=metadata.get('deadline_source'),
                deadline_time=metadata.get('deadline_time'),
                document_types=metadata.get('document_types') or [],
                competition_prize_amount=metadata.get('competition_prize_amount'),
                competition_prize_currency=metadata.get('competition_prize_currency'),
                eligibility_conditions=metadata.get('eligibility_conditions'),
                competition_regulation_available=bool(metadata.get('competition_regulation_available')),
                source=row.source, url=url, link_label=label,
                resolution_state=metadata.get('resolution_state'), source_type=metadata.get('source_type'),
                official_verified=bool(metadata.get('detail_verified') and metadata.get('official_confirmation')),
                dce_available=bool(metadata.get('dce_available', False) and metadata.get('detail_verified') and metadata.get('official_confirmation')), dce_access_mode=metadata.get('dce_access_mode'),
                reason='; '.join(review_code(part.strip()) for part in reason.split(';') if part.strip()),
                signal=metadata.get('signal_type'), maturity=metadata.get('maturity'),
                partners=metadata.get('partners') or [], budget=metadata.get('estimated_budget'),
                scope=metadata.get('project_scope'), evidence=metadata.get('evidence_summary'),
                person=metadata.get('person'), position=metadata.get('position'),
                role_type=metadata.get('role_type'), activity_type=metadata.get('activity_type'),
                recent_activity=metadata.get('recent_activity'), programs=metadata.get('current_programs') or [],
                projects=metadata.get('recent_projects') or [], relevance=metadata.get('architecture_heritage_relevance'),
                document_type=metadata.get('document_type'), legal_status=metadata.get('legal_status'),
                effective_date=metadata.get('effective_date'), policy_scope=metadata.get('scope'),
                policy_summary=metadata.get('summary'), implications=metadata.get('business_implications'),
                official_document_url=metadata.get('official_document_url'), funder=metadata.get('funder'),
                program_name=metadata.get('program_name'), opportunity_type=metadata.get('opportunity_type'),
                funding_status=metadata.get('funding_status'), beneficiary=metadata.get('beneficiary'),
                amount=metadata.get('amount'), currency=metadata.get('currency'),
                morocco_relevance=metadata.get('morocco_relevance'), funding_summary=metadata.get('summary'),
                funding_relevance=metadata.get('business_relevance'), procurement_url=metadata.get('procurement_url'),
                pmmp=pmmp,
                reason_code=(metadata.get('business_relevance') or {}).get('reason_code') if isinstance(metadata.get('business_relevance'), dict) else metadata.get('reason_code'),
                announcement_type=pmmp.get('announcement_type'),
                main_category=pmmp.get('main_category'),
                activity_domains=pmmp.get('activity_domains') or [],
                sme_reserved=pmmp.get('sme_reserved'),
                withdrawal_mode=pmmp.get('withdrawal_mode'),
                deposit_mode=pmmp.get('deposit_mode'),
                opening_place=pmmp.get('opening_place'),
                plan_price=pmmp.get('plan_price'),
                qualifications=pmmp.get('qualifications'))


# Exact-run actionable: observation recorded NEW/UPDATED (or workflow 'manual_review')
# for this SearchRun, and the Result is still PENDING for human review.
_ACTIONABLE_OBSERVATION = ('new', 'updated', 'manual_review')


def _run_member(run_id, result_id, code):
    return db.session.scalar(db.select(ResultObservation.id).join(
        SearchRun, ResultObservation.run_id == SearchRun.id).join(
        Radar, SearchRun.radar_id == Radar.id).where(
        ResultObservation.run_id == run_id, ResultObservation.result_id == result_id,
        ResultObservation.state.in_(_ACTIONABLE_OBSERVATION), Radar.code == code,
        SearchRun.status == 'completed')) is not None


def detail(app, result_id, code=CODE, run_id=None):
    """Read one Radar 1 record for the Telegram details view, without side effects."""
    with app.app_context():
        if run_id is not None:
            row = db.session.get(Result, result_id) if _run_member(run_id, result_id, code) else None
        else:
            row = db.session.scalar(db.select(Result).join(Radar, Result.radar_id == Radar.id).where(
                Result.id == result_id, Radar.code == code))
        return card(row, _official_domains(app), code) if row else None


def _run_exists(app, run_id, code):
    return db.session.scalar(db.select(SearchRun.id).join(Radar, SearchRun.radar_id == Radar.id).where(
        SearchRun.id == run_id, Radar.code == code, SearchRun.status == 'completed')) is not None


def run_result_page(app, run_id, index, *, include_total=False, code=CODE):
    """Current pending NEW/UPDATED Results observed by one exact completed run."""
    if not 0 <= index <= MAX_PAGE_INDEX:
        raise ValueError('Page invalide.')
    with app.app_context():
        if not _run_exists(app, run_id, code):
            return ([], False, 1) if include_total else ([], False)
        rows = db.session.scalars(db.select(Result).join(ResultObservation,
            ResultObservation.result_id == Result.id).where(
            ResultObservation.run_id == run_id,
            ResultObservation.state.in_(_ACTIONABLE_OBSERVATION),
            Result.review_status == 'PENDING').order_by(
            Result.last_seen_at.desc(), Result.deadline.asc().nullslast(), Result.id.desc()))
        eligible = _unique_eligible(rows, 'pending', code)
        domains = _official_domains(app)
        selected, total = [], 0
        for position, row in enumerate(eligible):
            total += 1
            if index * PAGE_SIZE <= position < (index + 1) * PAGE_SIZE:
                selected.append(card(row, domains, code))
        payload = (selected, total > (index + 1) * PAGE_SIZE, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE))
        return payload if include_total else payload[:2]


def run_actionable_count(app, run_id, code=CODE):
    return len(_run_result_ids(app, run_id, code))


def _run_result_ids(app, run_id, code):
    with app.app_context():
        if not _run_exists(app, run_id, code):
            return []
        rows = db.session.scalars(db.select(Result).join(ResultObservation,
            ResultObservation.result_id == Result.id).where(
            ResultObservation.run_id == run_id,
            ResultObservation.state.in_(_ACTIONABLE_OBSERVATION),
            Result.review_status == 'PENDING'))
        return [row.id for row in _unique_eligible(rows, 'pending', code)]


def run_page(app, index, code=CODE):
    if not 0 <= index <= MAX_PAGE_INDEX:
        raise ValueError('Page invalide.')
    with app.app_context():
        radar_id = db.session.scalar(db.select(Radar.id).where(Radar.code == code))
        total = db.session.scalar(db.select(db.func.count()).select_from(SearchRun).where(SearchRun.radar_id == radar_id)) or 0
        rows = db.session.scalars(db.select(SearchRun).where(SearchRun.radar_id == radar_id)
            .order_by(SearchRun.started_at.desc(), SearchRun.id.desc()).offset(index * PAGE_SIZE).limit(PAGE_SIZE)).all()
        items = []
        for run in rows:
            duration = int((run.finished_at - run.started_at).total_seconds()) if run.finished_at else None
            items.append({'started_at': run.started_at, 'status': run.status,
                'found': run.candidates_count, 'new': run.new_results_count,
                'updated': run.updated_results_count, 'known': run.duplicate_count,
                'auto_rejected': run.rejected_count, 'duration': duration})
        return items, total > (index + 1) * PAGE_SIZE, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)


def _unique_eligible(rows, mode, code):
    """Collapse join fan-out and enforce one card per Result primary key."""
    seen = set()
    for row in rows:
        if row.id in seen:
            continue
        if code == CODE and mode == 'approved' and not business_queue_eligible(row):
            continue
        if mode == 'pending' and not pending_eligible(row, code):
            continue
        seen.add(row.id)
        yield row


def page(app, mode, index, *, include_total=False, code=CODE):
    if mode not in {'pending', 'approved', 'rejected'} or not 0 <= index <= MAX_PAGE_INDEX:
        raise ValueError('Page invalide.')
    with app.app_context():
        query = db.select(Result).join(Radar, Result.radar_id == Radar.id).where(Radar.code == code)
        query = query.where(Result.review_status == mode.upper())
        if mode == 'pending':
            lifecycle_rank = db.case((Result.discovery_status == 'NEW', 0),
                                     (Result.discovery_status == 'UPDATED', 1), else_=2)
            query = query.order_by(lifecycle_rank, Result.last_seen_at.desc(),
                                   Result.deadline.asc().nullslast(), Result.priority.asc(), Result.id.desc())
        else:
            query = query.order_by(Result.reviewed_at.desc(), Result.id.desc())
        domains = _official_domains(app)
        # Radars 2–5 have no Python eligibility gate — paginate in SQL.
        if code != CODE:
            if include_total:
                total = db.session.scalar(db.select(db.func.count()).select_from(query.subquery())) or 0
                rows = db.session.scalars(query.offset(index * PAGE_SIZE).limit(PAGE_SIZE)).all()
                return [card(row, domains, code) for row in rows], total > (index + 1) * PAGE_SIZE, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
            rows = db.session.scalars(query.offset(index * PAGE_SIZE).limit(PAGE_SIZE + 1)).all()
            return [card(row, domains, code) for row in rows[:PAGE_SIZE]], len(rows) > PAGE_SIZE
        rows = db.session.scalars(query.execution_options(yield_per=100))
        eligible = _unique_eligible(rows, mode, code)
        if include_total:
            selected, total = [], 0
            for position, row in enumerate(eligible):
                total += 1
                if index * PAGE_SIZE <= position < (index + 1) * PAGE_SIZE:
                    selected.append(card(row, domains, code))
            return selected, total > (index + 1) * PAGE_SIZE, max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        selected = list(islice(eligible, index * PAGE_SIZE, index * PAGE_SIZE + PAGE_SIZE + 1))
        return [card(row, domains, code) for row in selected[:PAGE_SIZE]], len(selected) > PAGE_SIZE


def decide(app, result_id, version, decision, user_id, code=CODE, run_id=None):
    """Persist a human review decision. Caller must already enforce Telegram allowlist."""
    if decision not in {'approved', 'rejected'}:
        raise ValueError('Décision invalide.')
    with app.app_context():
        if run_id is not None:
            row = (db.session.get(Result, result_id) if _run_member(run_id, result_id, code) else None)
        else:
            row = db.session.scalar(db.select(Result).join(Radar, Result.radar_id == Radar.id).where(
                Result.id == result_id, Radar.code == code).with_for_update())
        if (not row or row.status == 'archived' or row.review_status != ReviewStatus.PENDING or
                not row.content_hash or row.content_hash[:12] != version):
            raise ValueError('Résultat déjà traité ou modifié. Rechargez À vérifier.')
        if decision == 'approved' and code == CODE and not current(row):
            raise ValueError('Validation impossible : statut ouvert et actualité doivent être confirmés.')
        now = utcnow()
        reason = (row.radar_metadata or {}).get('review_reason') or (row.analysis or {}).get('review_reason')
        db.session.add(MarketReview(result_id=row.id, content_hash=row.content_hash, decision=decision,
            reviewed_by=user_id, reviewed_at=now, previous_review_reason=reason,
            snapshot={'status': row.status, 'analysis': row.analysis, 'radar_metadata': row.radar_metadata,
                      'title': row.title, 'url': row.url, 'source_status': row.source_status}))
        metadata = {**row.radar_metadata, 'needs_manual_review': False, 'review_reason': None, 'relevant': decision == 'approved',
            'manual_review_status': decision, 'reviewed_by': user_id, 'reviewed_at': now.isoformat(),
            'previous_review_reason': reason}
        analysis = {**(row.analysis or {}), 'needs_manual_review': False, 'relevant': decision == 'approved',
                    'review_reason': None}
        # Compare-and-set also protects SQLite tests and stale concurrent callbacks.
        changed = db.session.execute(db.update(Result).where(Result.id == row.id,
            Result.review_status == ReviewStatus.PENDING, Result.content_hash == row.content_hash).values(
                status='new' if decision == 'approved' else 'rejected', radar_metadata=metadata,
                analysis=analysis, review_status=ReviewStatus.APPROVED if decision == 'approved' else ReviewStatus.REJECTED,
                reviewed_by=user_id, reviewed_at=now, updated_at=now).execution_options(synchronize_session=False))
        if changed.rowcount != 1:
            db.session.rollback()
            raise ValueError('Résultat déjà traité. Rechargez À vérifier.')
        workflow = ResultWorkflowService()
        workflow.apply_human_decision(row, decision, user_id, now, reason, radar_code=code)
        db.session.commit()
        if code == CODE:
            try:
                from app.modules.radar1_markets.feedback import get_feedback_service
                get_feedback_service().invalidate()
            except Exception:
                pass
        return 'Résultat validé.' if decision == 'approved' else 'Résultat rejeté et conservé dans l’historique.'
