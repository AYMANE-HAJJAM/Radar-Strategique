"""Compact Telegram review for Radar 2 project signals."""
from app.bot.handlers.compact_review import build_handlers, default_run_line

CODE = 'RADAR_2_PROJECTS'


def _card(item, number):
    lines = [f'[{number}] {item["title"]}']
    if item.get('institution'):
        lines.append(f'🏛 {item["institution"]}')
    if item.get('city'):
        lines.append(f'📍 {item["city"]}')
    lines += [
        f'📌 Signal : {(item.get("signal") or "À confirmer").replace("_", " ").title()}',
        f'📊 Maturité : {item.get("maturity") or "—"}',
        f'📅 Date : {item.get("publication") or "—"}',
        '⚠️ Opportunité potentielle',
    ]
    return '\n'.join(lines)[:4000]


def _details(item):
    values = [
        ('Projet', item.get('title')), ('Signal', item.get('signal')), ('Maturité', item.get('maturity')),
        ('Institution', item.get('institution')), ('Localisation', item.get('city')),
        ('Partenaires', ', '.join(item.get('partners') or [])), ('Budget', item.get('budget')),
        ('Périmètre', item.get('scope')), ('Éléments probants', item.get('evidence')),
    ]
    return '\n'.join(f'{label} : {value}' for label, value in values if value)[:4000]


def _format_run(run):
    return default_run_line(2, run) + f'\nDéjà connus : {run["known"]}'


parse_project_callback, show_page, handle = build_handlers(
    CODE, 'p', 2, _card, _details, __name__, format_run=_format_run)
