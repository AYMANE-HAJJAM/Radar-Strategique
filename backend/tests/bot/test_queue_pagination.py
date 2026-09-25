from types import SimpleNamespace

import pytest

from backend.app.bot.handlers.funding import parse_funding_callback
from backend.app.bot.handlers.institutions import parse_institution_callback
from backend.app.bot.handlers.markets import parse_market_callback
from backend.app.bot.handlers.policies import parse_policy_callback
from backend.app.bot.handlers.projects import parse_project_callback
from backend.app.bot.state import clamped_page, pagination_label, pagination_rows
from backend.app.core.review import page
from test_market_usability import CODE, review_rows


PARSERS = (
    ('m', parse_market_callback), ('p', parse_project_callback),
    ('i', parse_institution_callback), ('l', parse_policy_callback),
    ('f', parse_funding_callback),
)


def callbacks(rows):
    return [button.callback_data for row in rows for button in row]


@pytest.mark.parametrize('prefix,parser', PARSERS)
@pytest.mark.parametrize('mode', ('pending', 'approved', 'rejected'))
def test_all_radars_and_review_modes_preserve_page_context(prefix, parser, mode):
    assert parser(f'{prefix}:{mode}:5') == (mode, 5, None, None)
    assert parser(f'{prefix}:details:{mode}:42:5') == ('details_' + mode, 5, 42, None)
    with pytest.raises(ValueError):
        parser(f'{prefix}:{mode}:10001')


def test_navigation_layout_for_first_middle_last_and_single_pages():
    assert callbacks(pagination_rows('m', 'pending', 0, False, CODE)) == [f'radar:{CODE}']
    assert pagination_label([1], 0, 1) == 'Page 1/1'
    assert callbacks(pagination_rows('m', 'pending', 0, True, CODE)) == [
        'm:pending:1', f'radar:{CODE}']
    assert callbacks(pagination_rows('m', 'pending', 2, True, CODE)) == [
        'm:pending:1', 'm:pending:3', f'radar:{CODE}']
    assert callbacks(pagination_rows('m', 'pending', 5, False, CODE)) == [
        'm:pending:4', f'radar:{CODE}']


async def test_six_page_sequence_moves_exactly_one_page_each_direction():
    items = list(range(26))

    def load(index):
        selected = items[index * 5:(index + 1) * 5]
        return selected, len(items) > (index + 1) * 5, 6

    visited = []
    for requested in range(6):
        cards, more, total, current = await clamped_page(load, requested)
        visited.append(current)
        assert pagination_label(cards, current, total) == f'Page {requested + 1}/6'
        assert more is (requested < 5)
    assert visited == [0, 1, 2, 3, 4, 5]
    assert list(reversed(visited)) == [5, 4, 3, 2, 1, 0]


async def test_queue_shrink_clamps_stale_last_page_to_new_last_page():
    items = list(range(21))

    def load(index):
        total = max(1, (len(items) + 4) // 5)
        selected = items[index * 5:(index + 1) * 5]
        return selected, len(items) > (index + 1) * 5, total

    items[:] = items[:16]
    cards, more, total, current = await clamped_page(load, 4)
    assert current == 3 and total == 4 and cards == [15] and not more


def test_page_size_and_adjacent_pages_have_unique_ids(app):
    review_rows(app, 26)
    all_ids = []
    for index in range(6):
        cards, more, total = page(app, 'pending', index, include_total=True)
        assert len(cards) == (1 if index == 5 else 5)
        assert total == 6 and more is (index < 5)
        all_ids.extend(item['id'] for item in cards)
    assert len(all_ids) == len(set(all_ids)) == 26

