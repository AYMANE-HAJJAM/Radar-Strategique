from unittest.mock import patch

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from backend.app.db.extensions import db
from backend.app.db.models import Radar, Result, SearchRun
from backend.app.core.radar_registry import RADARS
from backend.app.core.dedup import fingerprint
from backend.app.db.repositories.radars import RadarServiceError, radar_action, seed_radars

CODE = 'RADAR_1_MARKETS'


def test_health_and_database_outage(app):
    client = app.test_client()
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/ready').status_code == 200
    with patch.object(db.session, 'execute', side_effect=OperationalError('secret SQL', {}, None)):
        response = client.get('/api/ready')
    assert response.status_code == 503
    assert 'secret' not in response.get_data(as_text=True)


def test_seed_history_and_empty_collectors(app):
    from backend.app.core.orchestrator import AgentOrchestrator
    with app.app_context():
        seed_radars()
        assert db.session.scalar(db.select(db.func.count()).select_from(Radar)) == 5
    assert 'Aucune recherche' in radar_action(app, CODE, 'history')
    summary = AgentOrchestrator(app).run_radar(CODE)
    assert summary.status == 'completed' and summary.ai_calls == 0
    assert 'completed' in radar_action(app, CODE, 'history')
    assert radar_action(app, CODE, 'news') == 'Aucun résultat pour le moment.'
    with app.app_context():
        radar = db.session.scalar(db.select(Radar).where(Radar.code == CODE))
        radar.is_active = False
        db.session.commit()
        seed_radars()
        assert not radar.is_active
    with pytest.raises(RadarServiceError, match='désactivé'):
        radar_action(app, CODE, 'history')


def test_database_read_failure_recovers(app):
    with patch.object(db.session, 'scalar', side_effect=OperationalError('secret', {}, None)):
        with pytest.raises(RadarServiceError, match='indisponible'):
            radar_action(app, CODE, 'history')
    assert 'Aucune recherche' in radar_action(app, CODE, 'history')


def test_fingerprint_normalization_and_identity():
    assert fingerprint(reference=' AB  12 ', institution='Ministère', title='old') == fingerprint(
        reference='ab 12', institution='MINISTÈRE', title='new')
    assert fingerprint(url='https://EXAMPLE.com/a#one') == fingerprint(url='https://example.com/a#two')
    assert fingerprint(url='https://example.com/A') != fingerprint(url='https://example.com/a')
    assert fingerprint(title='Projet   PME') == fingerprint(title=' projet pme ')
    with pytest.raises(ValueError):
        fingerprint()


def test_database_duplicate_constraint_is_per_radar(app):
    with app.app_context():
        radars = db.session.scalars(db.select(Radar).order_by(Radar.id)).all()
        digest = fingerprint(title='Example')
        for radar in radars[:2]:
            db.session.add(Result(radar_id=radar.id, title='Example', fingerprint=digest))
        db.session.commit()
        db.session.add(Result(radar_id=radars[0].id, title='Duplicate', fingerprint=digest))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_all_radars_have_empty_collection_and_typed_context():
    for radar in RADARS.values():
        assert radar.collect() == []
        assert radar.get_analysis_context().code == radar.code
        assert radar.normalize([]) == []
        for stage in ('analyze', 'save_results'):
            with pytest.raises(NotImplementedError):
                getattr(radar, stage)([])
