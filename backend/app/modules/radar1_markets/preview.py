"""Offline policy preview in disposable SQLite; source data is SELECT-only."""
import json

import click
from flask import Flask
from sqlalchemy import MetaData, Table, select, text

from app.db.extensions import db
from app.db.models.pmmp_listing_index import PmmpListingIndex
from app.core.radar_registry import RADAR_AGENT_REGISTRY
from app.integrations.http.html import Page
from .collector import COUNTERS, MarketsCollector, listing_to_search_hit
from .pmmp_listing_index import import_baseline, listing_from_record
from . import processing


class OfflineProvider:
    def search(self, *args, **kwargs):
        raise AssertionError('Paid/network search is forbidden in preview.')


class FixturePages:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url):
        if url not in self.pages:
            raise OSError('preview_offline_detail_not_supplied')
        return url, Page(self.pages[url])


def source_snapshot():
    """Read the configured DB without requiring the new migration to be applied."""
    snapshot = {}
    with db.engine.connect() as connection:
        with connection.begin():
            if connection.dialect.name == 'postgresql':
                connection.execute(text('SET TRANSACTION READ ONLY'))
            metadata = MetaData()
            for name in ('radars', 'results', 'pmmp_listing_index'):
                table = Table(name, metadata, autoload_with=connection)
                snapshot[name] = [dict(row) for row in connection.execute(select(table)).mappings()]
    return snapshot


def preview(config, *, fixture=None, snapshot=None, limit=100):
    """Never construct an orchestrator or fetch HTTP. All evaluation uses a clone."""
    isolated = Flask('radar1_preview')
    isolated.config.update(config)
    isolated.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI='sqlite://',
                           SQLALCHEMY_ENGINE_OPTIONS={}, OPENAI_API_KEY='',
                           RADAR1_DISCOVERY_MAX_CALLS=0, RADAR1_RESOLUTION_MAX_CALLS=0,
                           RADAR1_MAX_CANDIDATES=limit)
    db.init_app(isolated)
    mode = 'fixture_prediction' if fixture is not None else 'database_snapshot_offline_prediction'
    report = dict(mode=mode, live_observations=False, paid_calls=0, search_runs_created=0,
                  discovered=0, queued=0, evaluated=0, rejected=0, accepted_or_review=0,
                  candidates=[], discovery_mode=config.get('RADAR1_DISCOVERY_MODE', 'legacy'),
                  queue_applies_to_mode='pmmp_index',
                  limitations=['No current board or official detail HTTP is fetched.',
                               'No AI analysis or business persistence is simulated.',
                               'Feedback training is not copied; missing fixture detail can yield unverified review.'])
    with isolated.app_context():
        try:
            db.create_all()
            if snapshot is not None:
                for name in ('radars', 'results', 'pmmp_listing_index'):
                    table = db.metadata.tables[name]
                    for record in snapshot.get(name, []):
                        values = {key: value for key, value in record.items() if key in table.c}
                        if name == 'pmmp_listing_index' and 'processing_state' not in values:
                            values['processing_state'] = None
                        db.session.execute(table.insert().values(**values))
                db.session.commit()
            else:
                from app.db.repositories.radars import seed_radars
                seed_radars()
                import_baseline((fixture or {}).get('listings', []))
            collector = MarketsCollector(OfflineProvider(), isolated.config,
                                         pages=FixturePages((fixture or {}).get('detail_pages', {})))
            collector.known_unchanged = lambda candidate: False
            # Do not read/train/mutate the process-wide feedback profile cache.
            collector._apply_feedback = lambda business, candidate, context: {
                **business, 'feedback': {'applied': 'preview_skipped', 'feedback_score': 0.0}}
            report['recovery_prediction'] = processing.recover_legacy(
                lambda listing: collector._normalize(listing_to_search_hit(listing), listing.detail_url))
            report['discovered'] = db.session.scalar(db.select(db.func.count()).select_from(PmmpListingIndex))
            rows = processing.pending_rows()
            report['queued'] = len(rows)
            pending_ids = {row.id for row in rows}
            for row in db.session.scalars(db.select(PmmpListingIndex).order_by(PmmpListingIndex.id)):
                if row.id not in pending_ids:
                    report['candidates'].append(dict(reference=row.reference, consultation_id=row.consultation_id,
                        fingerprint=row.fingerprint, processing_state=row.processing_state,
                        outcome='rejected' if row.processing_state == processing.REJECTED else 'already_processed',
                        reason=row.processing_reason))
            stats = {**dict.fromkeys(COUNTERS, 0), 'query_index': None, 'new_identity': 0}
            radar = RADAR_AGENT_REGISTRY.resolve('RADAR_1_MARKETS')
            for row in rows:
                listing = listing_from_record(row)
                gate = processing.listing_gate(listing)
                item = dict(reference=listing.reference, consultation_id=listing.consultation_id,
                            fingerprint=listing.fingerprint, processing_state=row.processing_state)
                if gate['decision'] == 'reject':
                    item.update(outcome='rejected', reason=gate['reason_code'])
                    report['rejected'] += 1
                elif report['evaluated'] >= limit:
                    item.update(outcome='pending', reason='processing_cap_overflow')
                else:
                    report['evaluated'] += 1
                    before = len(collector.report.candidates)
                    collector._process(listing_to_search_hit(listing), radar, stats, listing.detail_url)
                    state, reason = collector.last_processing_outcome
                    if len(collector.report.candidates) > before:
                        candidate = collector.report.candidates[-1]
                        business = candidate.metadata.get('business_relevance') or {}
                        item.update(outcome='accepted_or_review', reason=business.get('reason_code'),
                                    resolution_state=candidate.resolution_state)
                        report['accepted_or_review'] += 1
                    else:
                        item.update(outcome=state.lower(), reason=reason)
                        report['rejected'] += int(state == processing.REJECTED)
                    event = next((event for event in reversed(collector.report.trace)
                                  if event.get('reference') == listing.reference
                                  and event.get('discovered_from') == listing.detail_url), None)
                    if event:
                        item['business_relevance'] = event.get('business_relevance')
                report['candidates'].append(item)
            report['rejected'] += report['recovery_prediction']['rejected']
            report['queued_after_cap_prediction'] = sum(
                item['outcome'] == 'pending' for item in report['candidates'])
        finally:
            db.session.remove()
            db.engine.dispose()
    return report


def register_preview_command(app):
    @app.cli.command('radar1-preview')
    @click.option('--fixture', type=click.Path(exists=True, dir_okay=False),
                  help='JSON with listings and optional detail_pages keyed by URL; no DB source access.')
    @click.option('--limit', type=click.IntRange(1, 5000), default=100, show_default=True)
    def radar1_preview(fixture, limit):
        """Preview offline in memory. Default source: a read-only configured DB snapshot."""
        try:
            if fixture:
                with open(fixture, encoding='utf-8') as stream:
                    payload = json.load(stream)
                if not isinstance(payload, dict) or not isinstance(payload.get('listings'), list):
                    raise click.ClickException('Fixture requires an object with a listings array.')
                output = preview(dict(app.config), fixture=payload, limit=limit)
            else:
                output = preview(dict(app.config), snapshot=source_snapshot(), limit=limit)
        except click.ClickException:
            raise
        except Exception as error:
            # Database exceptions can contain connection details; do not echo them.
            raise click.ClickException('Preview failed: ' + type(error).__name__) from None
        click.echo(json.dumps(output, ensure_ascii=False, indent=2))
