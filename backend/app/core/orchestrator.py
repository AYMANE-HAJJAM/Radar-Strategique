import logging
from dataclasses import dataclass

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.core.agent_errors import (ActiveRunError, CollectorError, InvalidAnalysisError,
                                   InvalidCandidateError, OpenAIServiceError)
from app.core.agent_schemas import AgentAnalysis, Candidate, ResultState, RunStatus, RunSummary, Stage
from app.db.extensions import db
from app.db.models import Radar, Result, SearchRun
from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.core.validation import today_in_morocco
from app.core.conditions import ConfidenceRules
from app.core.collector_registry import build_collector, SEARCH_LIMIT_SETTINGS
from app.core.collector_base import ProviderUnavailable
from app.integrations.openai.cost import CostService
from app.core.dedup import DedupService, identity_keys, discovery_snapshot
from app.integrations.openai.client import OpenAIService
from app.db.repositories.results import ResultService
from app.core.review import ResultWorkflowService, DiscoveryStatus, ReviewStatus
from app.db.repositories.search_runs import SearchRunService
from app.core.logging import log_failure, log_candidate_failure

logger = logging.getLogger(__name__)


@dataclass
class WorkItem:
    candidate: Candidate
    existing_id: int | None = None
    unchanged: bool = False
    analysis: AgentAnalysis | None = None
    skipped: bool = False
    agent_memory: dict | None = None
    deterministic: bool = False


class AgentOrchestrator:
    def __init__(self, flask_app, *, collector=None, analyzer=None, dry_run=False, no_ai=False):
        self.app = flask_app
        self.collector = collector
        self.analyzer = analyzer
        self.analyzer_supplied = analyzer is not None
        self.no_ai = no_ai
        self.runs = SearchRunService()
        self.dedup = DedupService()
        self.results = ResultService()
        self.workflow = ResultWorkflowService()
        self.costs = CostService.from_config(flask_app.config)
        self.dry_run = dry_run

    def reserve(self, radar_code, triggered_by=None, trigger_type='manual', launched_by_user_id=None):
        with self.app.app_context():
            return self.runs.reserve(radar_code, triggered_by, trigger_type, launched_by_user_id)

    def run_radar(self, radar_code, triggered_by=None, trigger_type='manual'):
        run_id = self.reserve(radar_code, triggered_by, trigger_type)
        return self.execute(run_id)

    def execute(self, run_id):
        with self.app.app_context():
            # Claim errors must never mark another worker's run as failed.
            run = self.runs.claim(run_id)
            radar_code = db.session.get(Radar, run.radar_id).code
            try:
                radar = RADAR_AGENT_REGISTRY.resolve(radar_code)
                if self.analyzer is None:
                    self.analyzer = OpenAIService(self.app.config['OPENAI_API_KEY'],
                        self.app.config['RADAR_MODELS'][radar_code],
                        max_source_chars=self.app.config['AI_MAX_SOURCE_CHARS'],
                        max_snippet_chars=self.app.config['AI_MAX_SNIPPET_CHARS'],
                        max_evidence_items=self.app.config['AI_MAX_EVIDENCE_ITEMS'],
                        max_output_tokens=self.app.config['AI_CLASSIFICATION_MAX_OUTPUT_TOKENS'])
                run.agent_name = type(radar).__name__
                as_of = today_in_morocco()
                self.runs.stage(run, Stage.COLLECTING)
                raw = self._collect(radar, run)
                run.candidates_count = len(raw)
                self.runs.stage(run, Stage.NORMALIZING)
                candidates = self._normalize(run, raw, radar)
                self.runs.stage(run, Stage.DEDUPLICATING)
                work = self._deduplicate(run, candidates, radar, as_of)
                self.runs.stage(run, Stage.ANALYZING)
                self._analyze(run, work, radar)
                self.runs.stage(run, Stage.VALIDATING)
                self._validate(run, work, radar, as_of)
                self.runs.stage(run, Stage.SAVING)
                self._save(run, work, radar)
                kept = (run.manual_review_count if self.dry_run else
                        run.new_results_count + run.updated_results_count if radar.workflow_enabled else
                        run.new_results_count + run.updated_results_count + run.manual_review_count)
                metadata = dict(run.run_metadata)
                metadata.update(
                    paid_search_calls=run.search_calls,
                    final_kept=kept,
                    openai_requests=metadata.get('search_api_calls', 0) + run.ai_calls,
                    openai_skipped=sum(metadata.get('ai_skipped_reasons', {}).values()),
                    tokens_per_kept_result=(round((run.input_tokens + run.output_tokens) / kept, 2) if kept else None),
                    openai_calls_per_kept_result=(round((metadata.get('search_api_calls', 0) + run.ai_calls) / kept, 3)
                                                  if kept else None),
                    paid_searches_per_kept_result=(round(run.search_calls / kept, 3) if kept else None),
                    direct_fetches_per_kept_result=(round(run.direct_fetches / kept, 3) if kept else None),
                    ai_cache_hits=metadata.get('ai_skipped_reasons', {}).get('ALREADY_CACHED', 0),
                    escalation_level=metadata.get('collector_metrics', {}).get('escalation_level', 0),
                    analysis_partial='analysis_limit' in metadata.get('truncation', []),
                    no_ai=self.no_ai,
                )
                run.run_metadata = metadata
                self.runs.complete(run)
                return self.runs.summary(run_id, radar_code)
            except Exception as error:
                kind = 'database' if isinstance(error, SQLAlchemyError) else getattr(error, 'kind', 'unexpected')
                log_failure(logger, f'run_id={run_id} radar={radar_code} kind={kind}', error)
                self.runs.safe_fail(run_id, kind)
                # If the database is down, still provide the committed run ID for investigation.
                try:
                    summary = self.runs.summary(run_id, radar_code)
                    if summary.status == RunStatus.FAILED:
                        return summary
                except SQLAlchemyError:
                    db.session.rollback()
                return RunSummary(id=run_id, radar_code=radar_code, status=RunStatus.FAILED,
                                  current_stage=Stage.FAILED, error_kind=kind)

    def _record_collection(self, run, report):
        metadata = dict(run.run_metadata)
        recorded = metadata.get('search_events_recorded', 0)
        for event in report.usage_events[recorded:]:
            self.costs.record(run, event.model if event else '', event.usage if event else None,
                              count_ai_call=False)
        if report.usage_events:
            # Search tool charges are separate from token rates; never understate the total.
            run.estimated_ai_cost = None
        metadata.update(search_events_recorded=len(report.usage_events), query_errors=report.query_errors,
                        source_errors=report.source_errors, collector_metrics=report.metrics,
                        collector_trace=report.trace, truncation=report.truncated,
                        collection_queries=report.query_metrics, collector_health=report.health,
                        collector_health_reasons=report.health_reasons,
                        query_performance=report.query_performance,
                        search_api_calls=len(report.usage_events),
                        search_models=sorted({event.model for event in report.usage_events if event and event.model}),
                        search_usage_complete=all(event is not None and event.usage is not None and event.usage.available for event in report.usage_events),
                        web_search_calls=sum(event.web_search_calls for event in report.usage_events if event),
                        search_call_purposes=[{
                            'purpose': event.diagnostics.get('purpose', 'DISCOVERY'),
                            'model': event.model, 'input_tokens': event.usage.input_tokens,
                            'output_tokens': event.usage.output_tokens,
                            'query_chars': event.diagnostics.get('query_chars'),
                        } for event in report.usage_events if event],
                        dry_run=self.dry_run)
        # Compatibility for existing operations tooling; new code should use collector_metrics.
        if getattr(report, 'metrics', None) is not None and run.agent_name == 'MarketRadarAgent':
            metadata['procurement_metrics'] = report.metrics
        run.run_metadata = metadata
        run.rejected_count = report.metrics.get('rejected', 0)
        run.queries_executed = report.queries_executed
        run.direct_fetches = next((report.metrics[key] for key in (
            'direct_fetches', 'direct_http_requests', 'direct_pages_fetched', 'direct_pages', 'official_sources_checked',
            'institutions_checked', 'funders_checked') if key in report.metrics), 0)
        run.search_calls = report.metrics.get('search_calls', len(report.usage_events))
        run.resolution_search_calls = report.metrics.get('resolution_search_calls', report.metrics.get('resolution_queries', 0))
        run.candidates_count = len(report.candidates)
        db.session.commit()

    def _collect(self, radar, run):
        try:
            if self.collector is not None:
                items = self.collector(radar)
            else:
                collector_config = dict(self.app.config)
                cap = self.app.config['MAX_DAILY_SEARCH_CALLS']
                if cap:
                    used = db.session.scalar(db.select(db.func.coalesce(db.func.sum(SearchRun.search_calls), 0)).where(
                        db.func.date(SearchRun.started_at) == run.started_at.date(), SearchRun.id != run.id)) or 0
                    remaining = max(0, cap - used)
                    if remaining == 0:
                        raise CollectorError('Daily search-call limit reached.')
                    limit_key = SEARCH_LIMIT_SETTINGS[radar.code]
                    collector_config[limit_key] = min(collector_config[limit_key], remaining)
                    if limit_key == 'RADAR1_MAX_QUERIES_PER_RUN':
                        collector_config['RADAR1_DISCOVERY_MAX_CALLS'] = min(
                            collector_config['RADAR1_DISCOVERY_MAX_CALLS'], remaining)
                collector = build_collector(radar.code, collector_config)
                if collector:
                    collector.query_performance = self._query_performance(run)
                    collector.known_unchanged = lambda candidate: self._early_known(run, candidate)
                    collector.source_recent = lambda url, days: self._source_recent(run, url, days)
                    def record_progress():
                        reader = getattr(collector.pages, 'reader', collector.pages)
                        if isinstance(getattr(reader, 'request_attempts', None), int):
                            collector.report.metrics['direct_fetches'] = (reader.request_attempts +
                                collector.report.metrics.get('direct_http_requests', 0))
                        self._record_collection(run, collector.report)
                    collector.on_progress = record_progress
                    try:
                        values = collector.collect(radar)
                        collector.report.metrics['representative_results'] = [{
                            'title': getattr(item, 'title', None),
                            'url': getattr(item, 'url', None),
                            'institution': getattr(item, 'institution', None),
                            'status': (getattr(item, 'source_status', None) or
                                       getattr(item, 'reported_funding_status', None) or
                                       getattr(item, 'legal_status', None)),
                        } for item in values[:5]]
                        return values
                    finally:
                        record_progress()
                items = radar.collect()
            collected = []
            for item in items:
                if len(collected) >= self.app.config['AGENT_MAX_CANDIDATES']:
                    run.run_metadata = {**run.run_metadata, 'truncation': ['candidate_limit']}
                    break
                collected.append(item)
            return collected
        except ProviderUnavailable:
            raise
        except Exception as error:
            raise CollectorError('Collector failed.') from error

    def _query_performance(self, current_run):
        """Aggregate ten prior runs without adding a table or AI planning call."""
        history = {}
        rows = db.session.scalars(db.select(SearchRun).where(
            SearchRun.radar_id == current_run.radar_id, SearchRun.id != current_run.id,
            SearchRun.status == 'completed').order_by(SearchRun.started_at.desc()).limit(10)).all()
        for row in rows:
            for query in (row.run_metadata or {}).get('collection_queries', []):
                strategy, family = query.get('source_strategy'), query.get('query_family')
                if not strategy or not family or strategy in {'RESOLUTION', 'CONTROL'}:
                    continue
                stats = history.setdefault(f'{strategy}:{family}', dict(executions=0, raw_results=0,
                    usable_observations=0, relevant_candidates=0, official_resolution_success=0,
                    zero_results=0, duplicates_skipped=0, generic_pages=0,
                    parser_failures=0, last_successful_at=None))
                stats['executions'] += 1
                raw = query.get('raw_results_count', 0)
                stats['raw_results'] += raw
                stats['usable_observations'] += query.get('candidates_created', 0)
                stats['relevant_candidates'] += query.get('relevant_candidates', 0)
                stats['official_resolution_success'] += query.get('official_resolution_success', 0)
                stats['zero_results'] += int(raw == 0)
                stats['duplicates_skipped'] += query.get('duplicates_skipped', 0)
                stats['generic_pages'] += query.get('generic_pages', 0)
                stats['parser_failures'] += query.get('parser_failures', 0)
                if raw and stats['last_successful_at'] is None:
                    stats['last_successful_at'] = row.started_at.isoformat()
        return history

    def _source_recent(self, run, url, days):
        """Avoid refetching a stable exact source URL before its refresh interval."""
        from datetime import timedelta
        from app.db.models import utcnow
        from app.core.dedup import canonical_url, digest
        try:
            key = digest([canonical_url(url)])
        except ValueError:
            return False
        return bool(db.session.scalar(db.select(Result.id).where(
            Result.radar_id == run.radar_id, Result.url_key == key,
            Result.last_seen_at >= utcnow() - timedelta(days=days))))

    def _early_known(self, run, candidate):
        """Only a complete matching commercial snapshot may skip a detail refresh."""
        from app.db.models import utcnow
        existing = self.dedup.find_existing(run.radar_id, candidate)
        if existing is None:
            return False
        if (hasattr(candidate, 'project_name') or hasattr(candidate, 'institution_name') or
                hasattr(candidate, 'legal_status') or hasattr(candidate, 'program_name')):
            if self.workflow.is_meaningful_update(existing, candidate):
                return False
            if not self.dry_run:
                existing.last_seen_at = utcnow()
            run.duplicate_count += 1
            return True
        # Pending fallback can recover official evidence on a later run. Human decisions stay remembered.
        if ((existing.radar_metadata or {}).get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE'
                and existing.review_status == 'PENDING'):
            return False
        old = (existing.source_metadata or {}).get('metadata', {}).get('discovery_snapshot')
        snapshot = discovery_snapshot(candidate)
        if not old or not candidate.reference or not candidate.institution or not candidate.deadline:
            return False
        if old != snapshot:
            return False
        if not self.dry_run:
            existing.last_seen_at = utcnow()
            existing.updated_at = existing.updated_at
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(existing, 'updated_at')
        run.duplicate_count += 1
        return True

    def _candidate_error(self, run, error, index, *, candidate=None, stage=None):
        run.candidate_errors_count += 1
        run.rejected_count += 1
        stage_label = stage or str(run.current_stage)
        detail = {
            'run_id': run.id,
            'radar_id': run.radar_id,
            'candidate_index': index,
            'stage': stage_label,
            'error_type': type(error).__name__,
            'error_message': str(error)[:500],
            'reference': getattr(candidate, 'reference', None) if candidate else None,
            'title': ((getattr(candidate, 'title', None) or '')[:120] if candidate else None),
            'source': getattr(candidate, 'source', None) if candidate else None,
        }
        failures = list(run.run_metadata.get('candidate_error_details', []))
        failures.append(detail)
        run.run_metadata = {
            **run.run_metadata,
            'candidate_error_details': failures[-30:],
            'policy_rejects_count': run.run_metadata.get(
                'policy_rejects_count', max(0, run.rejected_count - run.candidate_errors_count)),
        }
        log_candidate_failure(
            logger, run_id=run.id, radar_id=run.radar_id, stage=stage_label,
            candidate_index=index, error=error,
            reference=detail['reference'], title=detail['title'], source=detail['source'],
        )

    def _normalize(self, run, raw, radar):
        candidates = []
        for index, item in enumerate(raw):
            try:
                # Dictionaries are accepted only at the collector boundary.
                candidates.append(radar.normalize_candidate(item))
            except (ValidationError, ValueError, TypeError) as error:
                self._candidate_error(
                    run, error, index,
                    candidate=item if not isinstance(item, dict) else None,
                    stage='NORMALIZING',
                )
        return candidates

    def _deduplicate(self, run, candidates, radar, as_of):
        work, seen = [], set()
        for index, candidate in enumerate(candidates):
            keys = {(kind, key) for kind, key in enumerate(identity_keys(candidate)) if key is not None}
            if seen & keys:
                # Stable collector order: the first observation of an identity wins within a run.
                run.duplicate_count += 1
                continue
            try:
                decision = radar.validate_candidate(candidate, as_of=as_of)
                global_existing, material = (
                    self.dedup.find_global_source(run.radar_id, candidate)
                    if decision.accepted
                    else (None, False)
                )
                if global_existing is not None:
                    run.duplicate_count += int(not material)
                    run.updated_results_count += int(material)
                    metadata = dict(run.run_metadata.get('cross_radar_dedup', {}))
                    metadata['suppressed'] = metadata.get('suppressed', 0) + int(not material)
                    metadata['material_updates'] = metadata.get('material_updates', 0) + int(material)
                    metadata['reused_without_ai'] = metadata.get('reused_without_ai', 0) + 1
                    run.run_metadata = {**run.run_metadata, 'cross_radar_dedup': metadata}
                    if not self.dry_run:
                        self.results.record_cross_radar(run, global_existing, candidate,
                                                        radar.code, material=material)
                    continue
                needs_ai, ai_reason = radar.needs_ai_analysis(candidate, decision)
                if needs_ai:
                    run.candidates_after_rules += 1
                memory = radar.memory_tag(decision)
                memory['confidence_rules'] = self.app.config['RADAR_CONFIDENCE'][radar.code]
                reasons = dict(run.run_metadata.get('rule_reasons', {}))
                for reason in decision.reasons:
                    reasons[reason] = reasons.get(reason, 0) + 1
                run.run_metadata = {**run.run_metadata, 'rule_reasons': reasons, 'dry_run': self.dry_run}
                existing = self.dedup.find_existing(run.radar_id, candidate)
                if existing and ('result', existing.id) in seen:
                    run.duplicate_count += 1
                    continue
                same_memory = existing is not None and existing.source_metadata.get('agent_memory') == memory
                unchanged = (existing is not None and same_memory and (self.dedup.unchanged(existing, candidate) or
                             (radar.workflow_enabled and not self.workflow.is_meaningful_update(existing, candidate))))
                if unchanged:
                    run.duplicate_count += 1
                    skipped = dict(run.run_metadata.get('ai_skipped_reasons', {}))
                    skipped['ALREADY_CACHED'] = skipped.get('ALREADY_CACHED', 0) + 1
                    run.run_metadata = {**run.run_metadata, 'ai_skipped_reasons': skipped}
                item = WorkItem(candidate, existing.id if existing else None, unchanged, agent_memory=memory)
                if not decision.accepted and not unchanged:
                    item.analysis = radar.rejection_analysis(decision)
                    item.deterministic = True
                    logger.info('run_id=%s agent=%s candidate_index=%s decision=rejected_before_ai reasons=%s',
                                run.id, type(radar).__name__, index, ','.join(decision.reasons))
                elif not unchanged and (not needs_ai or self.dry_run or self.no_ai or
                        (not self.analyzer_supplied and self.app.config.get(f'RADAR{radar.number}_AI_ENABLED', 'conditional') == 'false')):
                    reason = ('NO_AI_MODE' if self.no_ai else 'DRY_RUN' if self.dry_run else
                              'AI_DISABLED_FOR_RADAR' if self.app.config.get(f'RADAR{radar.number}_AI_ENABLED') == 'false'
                              else ai_reason)
                    skipped = dict(run.run_metadata.get('ai_skipped_reasons', {}))
                    skipped[reason] = skipped.get(reason, 0) + 1
                    run.run_metadata = {**run.run_metadata, 'ai_skipped_reasons': skipped}
                    item.analysis = radar.candidate_review_analysis(candidate, decision.reasons or (reason,))
                    item.deterministic = True
                work.append(item)
                seen.update(keys)
                if existing:
                    seen.add(('result', existing.id))
            except InvalidCandidateError as error:
                self._candidate_error(run, error, index, candidate=candidate, stage='DEDUP')
        return work

    def _analyze(self, run, work, radar):
        limit = self.app.config[radar.analysis_limit_setting]
        token_budget = self.app.config[f'RADAR{radar.number}_MAX_INPUT_TOKENS_PER_RUN']
        daily_cap = self.app.config['MAX_DAILY_AI_CALLS']
        if daily_cap:
            used = db.session.scalar(db.select(db.func.coalesce(db.func.sum(SearchRun.ai_calls), 0)).where(
                db.func.date(SearchRun.started_at) == run.started_at.date(), SearchRun.id != run.id)) or 0
            limit = min(limit, max(0, daily_cap - used))
        analyses = 0
        for index, item in enumerate(work):
            if item.unchanged or item.analysis is not None:
                continue
            try:
                if analyses >= limit or run.input_tokens >= token_budget:
                    item.analysis = radar.candidate_review_analysis(item.candidate, ('analysis_limit_reached',))
                    item.deterministic = True
                    run.run_metadata = {**run.run_metadata, 'truncation': list(dict.fromkeys(run.run_metadata.get('truncation', []) + ['analysis_limit']))}
                    continue
                analyses += 1
                run.run_metadata = {**run.run_metadata, 'analysis_calls': analyses}
                logger.info('run_id=%s candidate_index=%s stage=ANALYZING action=ai_call', run.id, index)
                db.session.commit()  # No open transaction across network latency.
                from app.core.evidence import compact_candidate
                input_chars = len(compact_candidate(item.candidate,
                    max_chars=self.app.config['AI_MAX_SOURCE_CHARS'],
                    snippet_chars=self.app.config['AI_MAX_SNIPPET_CHARS'],
                    max_items=self.app.config['AI_MAX_EVIDENCE_ITEMS']))
                response = radar.analyze_candidate(item.candidate, self.analyzer)
                self.costs.record(run, response.model, response.usage, response.attempts)
                calls = list(run.run_metadata.get('classification_call_purposes', []))
                calls.append({'purpose': 'RESOLVE_MATERIAL_AMBIGUITY', 'radar': radar.code,
                    'model': response.model, 'input_chars': input_chars,
                    'input_tokens': response.usage.input_tokens, 'output_tokens': response.usage.output_tokens})
                run.run_metadata = {**run.run_metadata, 'classification_call_purposes': calls}
                run.analyzed_count += 1
                item.analysis = response.analysis
                db.session.commit()  # Keep billable usage even if a later candidate fails.
            except InvalidAnalysisError as error:
                self.costs.record(run, error.model, error.usage, error.attempts)
                self._candidate_error(run, error, index, candidate=item.candidate, stage='ANALYZING')
                item.skipped = True
                db.session.commit()
            except OpenAIServiceError as error:
                self.costs.record(run, error.model, error.usage, error.attempts)
                db.session.commit()
                run.candidate_errors_count += 1
                log_candidate_failure(
                    logger, run_id=run.id, radar_id=run.radar_id, stage='ANALYZING',
                    candidate_index=index, error=error,
                    reference=getattr(item.candidate, 'reference', None),
                    title=getattr(item.candidate, 'title', None),
                    source=getattr(item.candidate, 'source', None),
                )
                item.analysis = radar.candidate_review_analysis(item.candidate, ('analysis_unavailable:' + error.kind,))
                item.deterministic = True

    def _validate(self, run, work, radar, as_of):
        for index, item in enumerate(work):
            if item.unchanged or item.skipped or item.deterministic:
                continue
            try:
                thresholds = ConfidenceRules(**self.app.config['RADAR_CONFIDENCE'][radar.code])
                item.analysis = radar.validated_analysis(item.candidate, item.analysis, as_of=as_of, confidence_rules=thresholds)
            except InvalidCandidateError as error:
                run.candidate_errors_count += 1
                log_candidate_failure(
                    logger, run_id=run.id, radar_id=run.radar_id, stage='VALIDATING',
                    candidate_index=index, error=error,
                    reference=getattr(item.candidate, 'reference', None),
                    title=getattr(item.candidate, 'title', None),
                    source=getattr(item.candidate, 'source', None),
                )
                # A conservative deterministic review is safer than losing a
                # useful candidate when an optional AI assertion fails validation.
                item.analysis = radar.candidate_review_analysis(item.candidate,
                    ('ai_output_failed_validation',))
                item.deterministic = True
            except ValidationError as error:
                self._candidate_error(run, error, index, candidate=item.candidate, stage='VALIDATING')
                item.skipped = True

    def _save(self, run, work, radar):
        for index, item in enumerate(work):
            if item.skipped:
                continue
            existing = db.session.get(Result, item.existing_id) if item.existing_id else None
            if self.dry_run:
                if item.analysis and not item.analysis.relevant:
                    run.rejected_count += 1
                elif not item.unchanged:
                    run.manual_review_count += 1
                continue
            try:
                state = self.results.save(run, item.candidate, item.analysis, existing,
                                          agent_memory=item.agent_memory,
                                          workflow_enabled=radar.workflow_enabled)
                if radar.workflow_enabled:
                    if state == ResultState.UNCHANGED:
                        if not item.unchanged:
                            run.duplicate_count += 1
                        db.session.commit()
                        continue
                    if existing is None and item.analysis and item.analysis.relevant:
                        run.new_results_count += 1
                        run.manual_review_count += 1
                        run.accepted_count += int(not item.analysis.needs_manual_review)
                    elif existing is not None and item.analysis and item.analysis.relevant:
                        run.updated_results_count += 1
                        run.manual_review_count += 1
                        run.accepted_count += int(not item.analysis.needs_manual_review)
                    elif state == ResultState.REJECTED:
                        run.rejected_count += 1
                    db.session.commit()
                    continue
                if state == ResultState.NEW:
                    run.new_results_count += 1
                    run.accepted_count += 1
                elif state == ResultState.UPDATED:
                    run.updated_results_count += 1
                    run.accepted_count += 1
                elif state == ResultState.MANUAL_REVIEW:
                    run.manual_review_count += 1
                elif state == ResultState.REJECTED:
                    run.rejected_count += 1
                db.session.commit()
            except SQLAlchemyError:
                # Database connectivity / integrity failures remain run-level failures.
                db.session.rollback()
                raise
            except Exception as error:
                db.session.rollback()
                run = db.session.get(SearchRun, run.id) or run
                self._candidate_error(
                    run, error, index, candidate=item.candidate, stage='PERSIST_RESULT')
                db.session.commit()
