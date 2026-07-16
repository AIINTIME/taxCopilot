"""Calibrated confidence score combining retrieval scores, source tier, and
cross-chunk agreement.
"""


_TIER_WEIGHT = 0.2
_AGREEMENT_WEIGHT = 0.3
_RETRIEVAL_WEIGHT = 0.5


def calculate_confidence(
    retrieval_scores: list[float], tier: int, agreement: float
) -> float:
    """Combine retrieval scores + source tier + cross-chunk agreement into a
    single calibrated [0, 1] confidence score.

    `tier` follows KnowledgeGraphProvision.tier: 1 is the most authoritative
    source (e.g. the bare Act text), higher numbers are progressively less
    authoritative (e.g. commentary) -- so it contributes as 1/tier.
    """
    retrieval_component = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0.0
    tier_component = 1.0 / max(tier, 1)

    confidence = (
        _RETRIEVAL_WEIGHT * retrieval_component
        + _AGREEMENT_WEIGHT * agreement
        + _TIER_WEIGHT * tier_component
    )
    return max(0.0, min(1.0, confidence))
