"""Compact Telegram review for Radar 5 financing."""
from app.bot.handlers.compact_review import build_handlers

CODE = 'RADAR_5_FUNDING'


def label(value):
    return (value or 'À confirmer').replace('_', ' ').title()


def card(item, n):
    amount = (f'{item["amount"]} {item.get("currency") or ""}'.strip()
              if item.get('amount') is not None else None)
    return '\n'.join(filter(None, [
        f'[{n}] {item.get("program_name") or item["title"]}',
        f'💰 {item.get("funder") or "Bailleur"}', '🇲🇦 Maroc',
        f'📌 Statut : {item.get("funding_status") or "—"}',
        f'🎯 Accès : {label(item.get("opportunity_type"))}',
        f'💵 Montant : {amount}' if amount else None,
    ]))[:4000]


def details(item):
    values = (
        ('Bailleur', item.get('funder')), ('Programme', item.get('program_name')),
        ('Pertinence Maroc', item.get('morocco_relevance')), ('Bénéficiaire', item.get('beneficiary')),
        ('Statut', item.get('funding_status')), ('Accès', label(item.get('opportunity_type'))),
        ('Montant', f'{item.get("amount")} {item.get("currency") or ""}' if item.get('amount') is not None else None),
        ('Résumé', item.get('funding_summary')), ('Lien potentiel', item.get('funding_relevance')),
    )
    return '\n'.join(f'{k} : {v}' for k, v in values if v)[:4000]


parse_funding_callback, show_page, handle = build_handlers(
    CODE, 'f', 5, card, details, __name__)
