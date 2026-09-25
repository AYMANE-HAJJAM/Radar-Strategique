from app.core.agent_schemas import AgentAnalysis, ResultState
from app.db.extensions import db
from app.db.models import Result, ResultObservation, utcnow
from app.core.dedup import (content_hash, digest, fingerprint, identity_keys,
    source_content_fingerprint, source_identity_metadata)
from app.core.review import ResultWorkflowService
from sqlalchemy.orm.attributes import flag_modified


class ResultService:
    def __init__(self):
        self.workflow = ResultWorkflowService()

    def save(self, run, candidate, analysis: AgentAnalysis | None, existing=None, *, agent_memory=None,
             workflow_enabled=False):
        now = utcnow()
        if (existing is not None and workflow_enabled and
                (existing.radar_metadata or {}).get('resolution_state') == 'UNVERIFIED_BUT_CREDIBLE' and
                getattr(candidate, 'resolution_state', None) == 'VERIFIED_OFFICIAL' and
                not set(self.workflow.changed_fields(existing, candidate)) - {'official_url', 'official_confirmation'}):
            # Evidence-only enrichment preserves the human decision and commercial
            # content timestamp. A changed deadline/title/buyer follows normal UPDATE.
            existing.url = candidate.url
            existing.source = candidate.source
            existing.canonical_url, existing.reference_key, existing.identity_key = identity_keys(candidate)
            existing.url_key = digest([existing.canonical_url]) if existing.canonical_url else None
            existing.content_hash = content_hash(candidate)
            existing.source_metadata = {'metadata': candidate.metadata, 'radar_fields': candidate.radar_fields(),
                                        'agent_memory': agent_memory}
            existing.radar_metadata = {**existing.radar_metadata, **candidate.radar_fields()}
            for field in ('radar_metadata', 'analysis'):
                payload = dict(getattr(existing, field) or {})
                parts = [part.strip() for part in (payload.get('review_reason') or '').split(';')
                         if part.strip() and part.strip() not in {'OFFICIAL_URL_NOT_CONFIRMED', 'SECONDARY_SOURCE_ONLY'}]
                payload['review_reason'] = '; '.join(parts) or None
                setattr(existing, field, payload)
            self.workflow.audit(existing, 'OFFICIAL_ENRICHED', {'official_url': candidate.official_url})
            analysis = None
        if existing is not None and analysis is None:
            # Do not overwrite archived/rejected business states on rediscovery.
            if existing.status not in {ResultState.ARCHIVED, ResultState.REJECTED, ResultState.MANUAL_REVIEW}:
                existing.status = ResultState.UNCHANGED
            existing.last_seen_at = now
            if workflow_enabled:
                self.workflow.mark_unchanged(existing)
            # Explicit assignment prevents SQLAlchemy's onupdate from changing content time.
            existing.updated_at = existing.updated_at
            flag_modified(existing, 'updated_at')
            self.observe(run.id, existing, ResultState.UNCHANGED)
            return ResultState.UNCHANGED

        if not isinstance(analysis, AgentAnalysis):
            raise TypeError('Persistence requires a validated BaseAnalysis instance.')
        analysis = type(analysis).model_validate(analysis.model_dump())
        changed_fields = self.workflow.changed_fields(existing, candidate) if workflow_enabled and existing else []
        state = ResultState.REJECTED if not analysis.relevant else (
            ResultState.MANUAL_REVIEW if analysis.needs_manual_review else
            ResultState.UPDATED if existing is not None else ResultState.NEW)
        row = existing
        if row is None:
            row = Result(radar_id=run.radar_id, fingerprint=fingerprint(
                reference=candidate.reference, institution=candidate.institution,
                title=candidate.title, url=None if getattr(candidate, 'resolution_state', None) == 'UNVERIFIED_BUT_CREDIBLE' else candidate.url))
            db.session.add(row)
        elif row.analysis is None:
            # Capture the pre-agent version of a legacy Phase 1 record before replacing it.
            self.observe(run.id, row, row.status)
        for field in ('title', 'url', 'source', 'reference', 'institution', 'publication_date', 'deadline', 'source_status'):
            setattr(row, field, getattr(candidate, field))
        row.canonical_url, row.reference_key, row.identity_key = identity_keys(candidate)
        row.url_key = digest([row.canonical_url]) if row.canonical_url else None
        row.content_hash = content_hash(candidate)
        row.source_metadata = {'metadata': candidate.metadata, 'radar_fields': candidate.radar_fields(),
                               'agent_memory': agent_memory}
        row.analysis = analysis.model_dump()
        from app.db.models import Radar
        radar_code = db.session.get(Radar, run.radar_id).code
        global_metadata = ((existing.radar_metadata or {}).get('global_source') if existing else None)
        global_metadata = global_metadata or source_identity_metadata(candidate, radar_code)
        row.radar_metadata = {**candidate.radar_fields(), **analysis.model_dump(), 'source_quality': candidate.source_quality,
                              'validation': (agent_memory or {}).get('validation', {}),
                              'global_source': global_metadata}
        row.ai_score, row.priority = analysis.score, str(analysis.priority)
        row.status = ResultState.ARCHIVED if existing is not None and existing.status == ResultState.ARCHIVED else state
        row.last_seen_at = row.updated_at = now
        db.session.flush()
        if workflow_enabled:
            self.workflow.apply_saved_result(row, is_new=existing is None,
                relevant=analysis.relevant, changed_fields=changed_fields)
        self.observe(run.id, row, state)
        return state

    def record_cross_radar(self, run, row, candidate, radar_code, *, material=False):
        """Attach another radar's extraction while preserving the first visible owner card."""
        now = utcnow()
        metadata = dict(row.radar_metadata or {})
        global_source = dict(metadata.get('global_source') or {})
        related = list(global_source.get('related_radars') or [])
        owner = global_source.get('first_seen_radar')
        if not owner:
            from app.db.models import Radar
            owner = db.session.get(Radar, row.radar_id).code
        for code in (owner, radar_code):
            if code not in related:
                related.append(code)
        extractions = dict(global_source.get('radar_extractions') or {})
        extractions[radar_code] = candidate.radar_fields()
        global_source.update(first_seen_radar=owner, related_radars=related,
            source_type=global_source.get('source_type') or candidate.source_quality,
            global_content_fingerprint=(source_content_fingerprint(candidate) if material else
                global_source.get('global_content_fingerprint') or source_content_fingerprint(candidate)),
            radar_extractions=extractions)
        metadata['global_source'] = global_source
        row.radar_metadata = metadata
        flag_modified(row, 'radar_metadata')
        row.last_seen_at = now
        if material:
            self.workflow.apply_saved_result(row, is_new=False, relevant=True,
                                             changed_fields=['source_content'])
            row.updated_at = now
            state = ResultState.UPDATED
        else:
            row.updated_at = row.updated_at
            flag_modified(row, 'updated_at')
            state = ResultState.UNCHANGED
        self.observe(run.id, row, state)
        return state

    def observe(self, run_id, row, state):
        snapshot = {field: getattr(row, field) for field in (
            'title', 'url', 'source', 'reference', 'institution', 'source_status', 'source_metadata', 'radar_metadata',
            'analysis', 'discovery_status', 'review_status', 'reviewed_by', 'update_reason')}
        snapshot['reviewed_at'] = row.reviewed_at.isoformat() if row.reviewed_at else None
        for field in ('publication_date', 'deadline'):
            value = getattr(row, field)
            snapshot[field] = value.isoformat() if value else None
        db.session.add(ResultObservation(run_id=run_id, result_id=row.id, state=state, snapshot=snapshot))
