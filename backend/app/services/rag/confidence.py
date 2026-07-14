"""Calibrated confidence score combining retrieval scores, source tier, and
cross-chunk agreement.
"""


def calculate_confidence(
    retrieval_scores: list[float], tier: int, agreement: float
) -> float:
    raise NotImplementedError(
        "TODO: combine retrieval_scores + tier + agreement into a single "
        "calibrated [0, 1] confidence score"
    )
