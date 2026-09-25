import logging
import traceback


def configure_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    # HTTP request URLs can contain Telegram tokens. SDK exception bodies can contain secrets.
    for name in ('httpx', 'httpcore', 'openai', 'sqlalchemy.engine'):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def log_failure(logger, operation, error):
    # Deliberately omit exception text, SQL parameters, request bodies and URLs.
    logger.error('%s failed; error_type=%s', operation, type(error).__name__)


def log_candidate_failure(logger, *, run_id, radar_id, stage, candidate_index, error,
                          reference=None, title=None, source=None):
    """Log a candidate-level pipeline failure with actionable diagnostics (not for Telegram)."""
    message = str(error)[:500].replace('\n', ' ')
    safe_title = (title or '')[:120].replace('\n', ' ')
    logger.error(
        'candidate_failure run_id=%s radar_id=%s stage=%s candidate_index=%s '
        'reference=%s title=%s source=%s error_type=%s error_message=%s\n%s',
        run_id, radar_id, stage, candidate_index, reference, safe_title, source,
        type(error).__name__, message, traceback.format_exc(),
    )
