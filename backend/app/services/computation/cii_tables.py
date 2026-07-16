"""Versioned Cost Inflation Index lookup, keyed by financial year, as
notified by the CBDT. Not under rules/ because it's static reference data
rather than a rule, but it is still pure/zero-I/O -- consumed by
rules/capital_gains.py for indexed cost computations.

Populated from CBDT CII notifications, base year 2001-02 = 100 through
2024-25 = 363 -- the last year CBDT notified a value, since the Finance
(No. 2) Act, 2024 withdrew indexation prospectively from 23-Jul-2024.
"""

CII_TABLE: dict[str, int] = {
    "2001-02": 100,
    "2002-03": 105,
    "2003-04": 109,
    "2004-05": 113,
    "2005-06": 117,
    "2006-07": 122,
    "2007-08": 129,
    "2008-09": 137,
    "2009-10": 148,
    "2010-11": 167,
    "2011-12": 184,
    "2012-13": 200,
    "2013-14": 220,
    "2014-15": 240,
    "2015-16": 254,
    "2016-17": 264,
    "2017-18": 272,
    "2018-19": 280,
    "2019-20": 289,
    "2020-21": 301,
    "2021-22": 317,
    "2022-23": 331,
    "2023-24": 348,
    "2024-25": 363,
}

_BASE_YEAR = "2001-02"
_LATEST_NOTIFIED_YEAR = "2024-25"


def get_cii(financial_year: str) -> int:
    """Look up the CII for `financial_year` (e.g. "2024-25").

    Years before the base year raise -- no CII exists for them. Years after
    the latest notified year fall back to the latest notified value (frozen)
    rather than raising, since CBDT will not notify further values now that
    indexation has been withdrawn prospectively; this keeps the Sec 112
    grandfathering comparison computable for transfers in FY 2025-26 (before
    the 1-Apr-2026 Act 2025 transition).
    """
    if financial_year in CII_TABLE:
        return CII_TABLE[financial_year]

    if financial_year < _BASE_YEAR:
        raise ValueError(
            f"No CII notified for financial year {financial_year!r} -- "
            f"predates the base year {_BASE_YEAR} (CII=100)"
        )

    if financial_year > _LATEST_NOTIFIED_YEAR:
        return CII_TABLE[_LATEST_NOTIFIED_YEAR]

    raise ValueError(f"No CII notified for financial year {financial_year!r}")
