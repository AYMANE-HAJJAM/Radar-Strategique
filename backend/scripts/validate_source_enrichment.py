﻿"""Bounded direct-only live dry-runs, then offline replay in disposable databases."""
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from backend.app import create_app
from backend.app.db.extensions import db
from backend.app.db.models import Result, Radar
from backend.app.core.collector_registry import build_collector
from backend.app.core.orchestrator import AgentOrchestrator
from backend.app.db.repositories.radars import seed_radars


def main():
    logging.disable(logging.CRITICAL)
    evidence = {}
    with TemporaryDirectory(prefix='source-enrichment-quality-', ignore_cleanup_errors=True) as directory:
        app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite:///' +
            (Path(directory) / 'quality.db').as_posix(), 'SQLALCHEMY_ENGINE_OPTIONS': {}})
        app.config.update(RADAR3_NORMAL_SEARCH_BUDGET=0, RADAR4_NORMAL_SEARCH_BUDGET=0)
        with app.app_context(): db.create_all(); seed_radars()
        for number, code in [(3, 'RADAR_3_INSTITUTIONS'), (4, 'RADAR_4_POLICIES')]:
            collector = build_collector(code, app.config)
            with patch('app.core.orchestrator.build_collector', return_value=collector):
                first = AgentOrchestrator(app, dry_run=True, no_ai=True).run_radar(code)
            snapshots = list(collector.report.candidates)
            cached = AgentOrchestrator(app, dry_run=True, no_ai=True).run_radar(code)
            # Replay the exact extracted snapshot without fetching sources or calling AI.
            replay = AgentOrchestrator(app, collector=lambda _: snapshots, no_ai=True)
            saved = replay.run_radar(code)
            with app.app_context():
                rows = db.session.scalars(db.select(Result).join(Radar, Result.radar_id == Radar.id).where(Radar.code == code)).all()
                old = {r.id: (r.first_seen_at, r.last_seen_at, r.content_hash, r.review_status) for r in rows}
            second = replay.run_radar(code)
            with app.app_context():
                rows = db.session.scalars(db.select(Result).join(Radar, Result.radar_id == Radar.id).where(Radar.code == code)).all()
                preserved = all(r.id in old and r.first_seen_at == old[r.id][0] and r.last_seen_at >= old[r.id][1]
                    and r.content_hash == old[r.id][2] and r.review_status == old[r.id][3] for r in rows)
            evidence[str(number)] = {'live_dry_run': first.model_dump(mode='json'),
                'verification_documents':[{k:v for k,v in d.items() if k in {'url','text','kind','date','bo_number'}}
                    for d in collector.verification_pages.cache.values() if d],
                'cached_dry_run': cached.model_dump(mode='json'),
                'candidates': [c.model_dump(mode='json') for c in snapshots],
                'bulletins': [{k:v for k,v in doc.items() if k in {'url','date','bo_number','sections'}}
                    for doc in getattr(collector,'bo_documents',[])],
                'memory': {'first_new': saved.new_results_count, 'second_new': second.new_results_count,
                    'second_duplicates': second.duplicate_count, 'rows': len(rows),
                    'first_seen_hash_review_preserved': preserved, 'second_search': second.search_calls,
                    'second_ai': second.ai_calls, 'second_input': second.input_tokens, 'second_output': second.output_tokens}}
            Path('audit-output/source-enrichment-quality.json').write_text(json.dumps(evidence, indent=2, ensure_ascii=True,default=str))
            print(json.dumps({'radar': number, 'live_candidates': len(snapshots),
                'health': first.run_metadata.get('collector_health'), 'memory': evidence[str(number)]['memory']}))
        with app.app_context(): db.session.remove(); db.engine.dispose()


if __name__ == '__main__': main()

