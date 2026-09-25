"""Compact Telegram review for Radar 4 policies."""
from app.bot.handlers.compact_review import build_handlers

CODE = 'RADAR_4_POLICIES'


def _label(value):
    return (value or 'À confirmer').replace('_', ' ').title()


def _card(item, n):
    return '\n'.join(filter(None, [
        f'[{n}] {item["title"]}', f'🏛 {item.get("institution") or "Institution"}',
        f'📄 Type : {_label(item.get("document_type"))}', f'⚖️ Statut : {_label(item.get("legal_status"))}',
        f'📅 Date : {item.get("publication") or "—"}',
        f'📌 Impact potentiel : {item.get("policy_scope") or "à examiner"}',
    ]))[:4000]


def _details(item):
    values = (
        ('Texte', item.get('title')), ('Statut exact', _label(item.get('legal_status'))),
        ('Institution', item.get('institution')), ('Référence', item.get('reference')),
        ('Entrée en vigueur', item.get('effective_date')), ('Changement', item.get('policy_summary')),
        ('Pertinence', item.get('policy_scope')), ('Implication potentielle', item.get('implications')),
    )
    return '\n'.join(f'{k} : {v}' for k, v in values if v)[:4000]


parse_policy_callback, show_page, handle = build_handlers(
    CODE, 'l', 4, _card, _details, __name__)
