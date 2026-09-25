from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from app.bot.keyboards.constants import COMPLETION_LABELS, RADAR_PREFIXES
from app.core.radar_registry import RADARS

__all__ = ['main_keyboard', 'radar_keyboard', 'radar_completion_keyboard', 'radar_failure_keyboard',
           'COMPLETION_LABELS', 'RADAR_PREFIXES']


def main_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(f'{radar.emoji} Radar {radar.number} — {radar.name}', callback_data=f'radar:{code}')]
        for code, radar in RADARS.items()
    ] + [[InlineKeyboardButton('🎯 Recherche ciblée', callback_data='t:menu')]])


def radar_keyboard(code):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔎 Lancer une recherche', callback_data=f'search:{code}')],
        [InlineKeyboardButton('📥 À traiter', callback_data=f'pending:{code}')],
        [InlineKeyboardButton('✅ Validés', callback_data=f'approved:{code}')],
        [InlineKeyboardButton('❌ Rejetés', callback_data=f'rejected:{code}')],
        [InlineKeyboardButton('🕘 Recherches précédentes', callback_data=f'runs:{code}')],
        [InlineKeyboardButton('⬅️ Retour', callback_data='menu')],
    ])


def radar_completion_keyboard(code, run_id=None, has_pending=True):
    """Exact-run completion: Voir+Retour when actionable; Retour only otherwise."""
    rows = []
    if has_pending:
        callback = (f'{RADAR_PREFIXES[code]}:run:{run_id}:0' if run_id is not None
                    else f'pending:{code}')
        rows.append([InlineKeyboardButton(COMPLETION_LABELS[code], callback_data=callback)])
    rows.append([InlineKeyboardButton('⬅️ Retour', callback_data=f'radar:{code}')])
    return InlineKeyboardMarkup(rows)


def radar_failure_keyboard(code):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton('🔄 Réessayer', callback_data=f'search:{code}')],
        [InlineKeyboardButton('⬅️ Retour', callback_data=f'radar:{code}')],
    ])
