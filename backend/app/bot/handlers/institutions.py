"""Compact Telegram review for Radar 3 institutions."""
from app.bot.handlers.compact_review import build_handlers

CODE = 'RADAR_3_INSTITUTIONS'


def _card(item, number):
    lines = [f'[{number}] {item["title"]}', f'🏛 {item.get("institution") or "Institution"}']
    if item.get('city'):
        lines.append(f'📍 {item["city"]}')
    if item.get('person'):
        lines.append(f'👤 Nouveau responsable : {item["person"]}')
    if item.get('role_type'):
        lines.append('📌 Rôle : ' + item['role_type'].replace('_', ' ').title())
    lines.append('🆕 Changement récent' if item.get('activity_type') != 'CURRENT_PROFILE' else '⚠️ Institution à suivre')
    return '\n'.join(lines)[:4000]


def _details(item):
    values = [
        ('Institution', item.get('institution')), ('Région', item.get('city')),
        ('Responsable', item.get('person')), ('Fonction', item.get('position')), ('Rôle', item.get('role_type')),
        ('Activité récente', item.get('recent_activity')), ('Pertinence', item.get('relevance')),
        ('Programmes', ', '.join(item.get('programs') or [])), ('Projets', ', '.join(item.get('projects') or [])),
    ]
    return '\n'.join(f'{key} : {value}' for key, value in values if value)[:4000]


parse_institution_callback, show_page, handle = build_handlers(
    CODE, 'i', 3, _card, _details, __name__)
