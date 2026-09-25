"""Typed PMMP structures (parser currently returns plain dicts; names document shape)."""
from __future__ import annotations

from typing import Any, TypedDict


class PMMPEstimate(TypedDict, total=False):
    amount: float
    currency: str | None
    tax_basis: str | None
    verified: bool
    source: str | None


class PMMPDocumentAvailability(TypedDict, total=False):
    dce: bool
    cps: bool
    rc: bool
    bpu_dqe: bool
    plans: bool
    annexes: bool
    types: list[str]


class PMMPDetail(TypedDict, total=False):
    reference: str | None
    buyer: str | None
    object: str | None
    announcement_type: str | None
    procedure: str | None
    main_category: str | None
    execution_location: str | None
    estimate: PMMPEstimate | None
    deadline: dict[str, Any] | None
    provisional_guarantee: dict[str, Any] | None
    activity_domains: list[str]
    sme_reserved: bool | None
    allotment: str | None
    withdrawal_mode: str | None
    deposit_mode: str | None
    opening_place: str | None
    plan_price: Any
    qualifications: str | None
    documents: PMMPDocumentAvailability
    official_url: str
    detail_enriched: bool


__all__ = ['PMMPEstimate', 'PMMPDocumentAvailability', 'PMMPDetail']
