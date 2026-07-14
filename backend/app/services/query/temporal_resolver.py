"""Resolves the as-of date / Assessment Year / Tax Year / regime for a query.

This must run FIRST, before computation or retrieval, per the architecture's
temporal-resolution-first rule. It must branch on the two hard pivot dates
defined in app.shared.schemas.tax_year:

- CG_RATE_CHANGE_DATE (23 Jul 2024): which side of the capital-gains
  rate/indexation change a query's as-of date falls on.
- ACT_2025_EFFECTIVE_DATE (1 Apr 2026): whether the 1961 Act or the 2025 Act
  applies as of that date.
"""

from datetime import date

from app.shared.schemas.tax_year import TaxYearContext


def resolve_as_of(query: str, explicit_date: date | None = None) -> TaxYearContext:
    raise NotImplementedError(
        "TODO: parse an as-of date out of `query` (or use explicit_date), "
        "derive the Assessment Year, and branch on CG_RATE_CHANGE_DATE / "
        "ACT_2025_EFFECTIVE_DATE to build a TaxYearContext"
    )
