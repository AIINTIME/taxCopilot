"""Calibrated confidence score combining retrieval scores, source tier, and
cross-chunk agreement. Pure, zero I/O.

TIER IS CURRENTLY INERT. Every ingested chunk carries tier=10 -- api/admin.py
hardcodes it on upload -- so the tier term contributes a constant and adds no
discrimination between answers today. It is kept in the formula rather than
dropped because the signal is real once ingestion assigns tiers by source
authority (bare Act > CBDT circular > commentary), and removing it would mean
recalibrating everything downstream when that lands. Callers should not read
much into small differences in the returned score until then.
"""

# Retrieval scores arrive as cosine similarity in [0, 1]; anything at or below
# this is noise rather than a match, and should not lend confidence.
_SCORE_FLOOR = 0.3

# Tier 1 = most authoritative. Beyond this, extra tiers stop mattering.
_TIER_FLOOR = 10

_WEIGHT_RETRIEVAL = 0.5
_WEIGHT_TIER = 0.2
_WEIGHT_AGREEMENT = 0.3


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def calculate_confidence(
    retrieval_scores: list[float], tier: int, agreement: float
) -> float:
    """Combine retrieval quality, source authority, and corroboration into [0, 1].

    `agreement` is the caller's measure of cross-chunk corroboration (how much
    the retrieved chunks say the same thing); 0 when a single chunk supports a
    claim, approaching 1 when several independently do.
    """
    if not retrieval_scores:
        return 0.0

    # Best hit dominates, but a corroborating spread lifts it slightly: a claim
    # supported by several good chunks should beat one lucky match.
    best = max(retrieval_scores)
    mean = sum(retrieval_scores) / len(retrieval_scores)
    retrieval_term = _clamp((0.7 * best + 0.3 * mean - _SCORE_FLOOR) / (1 - _SCORE_FLOOR))

    # Retrieval gates everything. If nothing was actually matched, the source's
    # authority and the agreement between non-matches are meaningless -- a
    # weighted sum would still hand back a non-zero score off the tier term
    # alone, which reads as "somewhat confident" about a miss.
    if retrieval_term <= 0.0:
        return 0.0

    tier_term = _clamp(1.0 - (max(tier, 1) - 1) / _TIER_FLOOR)

    return round(
        _clamp(
            _WEIGHT_RETRIEVAL * retrieval_term
            + _WEIGHT_TIER * tier_term
            + _WEIGHT_AGREEMENT * _clamp(agreement)
        ),
        4,
    )
