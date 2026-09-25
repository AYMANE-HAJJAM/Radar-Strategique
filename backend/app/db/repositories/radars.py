import logging

from sqlalchemy.exc import SQLAlchemyError

from app.db.extensions import db
from app.db.models import Radar, SearchRun
from app.core.radar_registry import RADARS
from app.core.logging import log_failure

logger = logging.getLogger(__name__)


class RadarServiceError(RuntimeError):
    pass


def seed_radars():
    """Explicit, repeatable setup command; preserve administrator activation settings."""
    try:
        for definition in RADARS.values():
            radar = db.session.scalar(db.select(Radar).where(Radar.code == definition.code))
            if radar is None:
                radar = Radar(code=definition.code)
                db.session.add(radar)
            radar.name = definition.name
            radar.description = definition.description
        db.session.commit()
    except SQLAlchemyError as error:
        db.session.rollback()
        log_failure(logger, 'Radar seed database operation', error)
        raise RadarServiceError('Base de données indisponible. Vérifiez les migrations.') from None


def radar_action(flask_app, code, action):
    """Own the app/session context inside the worker thread; return only plain text."""
    definition = RADARS.get(code)
    if definition is None or action not in {'news', 'history'}:
        raise RadarServiceError('Action invalide. Utilisez /start.')
    with flask_app.app_context():
        try:
            radar = db.session.scalar(db.select(Radar).where(Radar.code == code))
            if radar is None:
                raise RadarServiceError('Radar non configuré. Contactez votre administrateur.')
            if not radar.is_active:
                raise RadarServiceError('Ce radar est désactivé.')
            if action == 'news':
                return 'Aucun résultat pour le moment.'
            runs = db.session.scalars(db.select(SearchRun).where(SearchRun.radar_id == radar.id)
                                      .order_by(SearchRun.started_at.desc(), SearchRun.id.desc()).limit(10)).all()
            if not runs:
                return 'Aucune recherche pour le moment.'
            lines = ['Historique des 10 dernières recherches (UTC) :']
            for run in runs:
                lines.append(f'#{run.id} — {run.started_at:%d/%m/%Y %H:%M} — {run.status} — {run.new_results_count} nouveautés')
            return '\n'.join(lines)
        except SQLAlchemyError as error:
            db.session.rollback()
            log_failure(logger, 'Radar database operation', error)
            raise RadarServiceError('Base de données temporairement indisponible. Réessayez plus tard.') from None
