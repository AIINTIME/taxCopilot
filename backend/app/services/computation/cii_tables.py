"""Versioned Cost Inflation Index lookup, keyed by financial year, as
notified by the CBDT. Not under rules/ because it's static reference data
rather than a rule, but it is still pure/zero-I/O -- consumed by
rules/capital_gains.py for indexed cost computations.
"""

# TODO: populate from CBDT CII notifications, e.g. {"2024-25": 363, ...}
CII_TABLE: dict[str, int] = {}


def get_cii(financial_year: str) -> int:
    raise NotImplementedError(
        "TODO: look up CII_TABLE[financial_year], raising a clear error for "
        "years not yet notified"
    )
