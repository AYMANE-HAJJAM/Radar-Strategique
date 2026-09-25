"""Shared pagination math (no Telegram formatting)."""
from __future__ import annotations

from app.core.constants import MAX_PAGE_INDEX, PAGE_SIZE


def clamp_page(index: int, total_pages: int | None = None) -> int:
    page = max(0, min(int(index), MAX_PAGE_INDEX))
    if total_pages is not None:
        page = min(page, max(0, int(total_pages) - 1))
    return page


def page_offset(index: int, page_size: int = PAGE_SIZE) -> int:
    return clamp_page(index) * page_size


def has_next(total: int, index: int, page_size: int = PAGE_SIZE) -> bool:
    return total > (clamp_page(index) + 1) * page_size


def total_pages(total: int, page_size: int = PAGE_SIZE) -> int:
    return max(1, (max(0, total) + page_size - 1) // page_size)
