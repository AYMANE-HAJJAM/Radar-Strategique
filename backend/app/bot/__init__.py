from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.bot.handlers.common import fallback, on_callback, on_error, start
from app.core.job_runner import LocalJobRunner


async def shutdown_jobs(application):
    import asyncio
    await asyncio.to_thread(application.bot_data['job_runner'].shutdown)


def build_application(flask_app):
    token = flask_app.config['TELEGRAM_BOT_TOKEN']
    if not token:
        raise ValueError('TELEGRAM_BOT_TOKEN is required to start the bot.')
    application = Application.builder().token(token).concurrent_updates(False).post_shutdown(shutdown_jobs).build()
    application.bot_data['flask_app'] = flask_app
    application.bot_data['job_runner'] = LocalJobRunner()
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CallbackQueryHandler(on_callback))
    application.add_handler(MessageHandler(filters.ALL, fallback))
    application.add_error_handler(on_error)
    return application
