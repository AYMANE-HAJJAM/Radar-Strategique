import asyncio
import logging
import time

from telegram.error import Conflict, InvalidToken, NetworkError, TelegramError

from backend.app import create_app
from backend.app.bot import build_application
from backend.app.core.logging import log_failure


def main():
    flask_app = create_app()
    logger = logging.getLogger(__name__)
    if not flask_app.config['ALLOWED_TELEGRAM_USER_IDS']:
        logger.warning('Allowlist is empty: all users will be denied.')
    while True:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            application = build_application(flask_app)
            logger.info('Bot starting in polling mode')
            application.run_polling(allowed_updates=['message', 'callback_query'],
                                    bootstrap_retries=3, close_loop=False)
            return
        except NetworkError as error:
            log_failure(logger, 'Telegram connection; retrying in 10 seconds', error)
            time.sleep(10)
        except (InvalidToken, Conflict, TelegramError, ValueError) as error:
            log_failure(logger, 'Bot startup; check token and ensure only one poller is running', error)
            return
        finally:
            loop.close()
            asyncio.set_event_loop(None)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
