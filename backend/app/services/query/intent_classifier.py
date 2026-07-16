"""Deterministic routing of a query to computation, retrieval, or both.

This must be a deterministic classifier (keyword/pattern based), not an LLM
call -- the LLM never decides control flow in this system, only narrates
retrieved content.
"""

import re
from enum import Enum

_COMPUTATION_KEYWORDS = (
    "calculate", "compute", "how much tax", "tax payable", "tax liability",
    "taxable gain", "taxable income", "how much do i owe", "compare regime",
    "compare the old and new regime",
)
_COMPUTATION_AMOUNT_PATTERN = re.compile(r"(?:rs\.?|inr|₹)\s*[\d,]+|[\d,]+\s*(?:lakh|crore)", re.IGNORECASE)

_RETRIEVAL_KEYWORDS = (
    "what is", "what are", "explain", "define", "definition", "section",
    "exemption under", "eligibility", "eligible", "conditions for", "condition",
    "provision", "provisions", "which section", "applicable section", "rule",
)


class Intent(str, Enum):
    COMPUTATION = "computation"
    RETRIEVAL = "retrieval"
    BOTH = "both"


def classify_intent(query: str) -> Intent:
    """Deterministic (non-LLM) classification of `query` -> Intent.

    Keyword/pattern based only -- the LLM never makes this control-flow
    decision. Defaults to RETRIEVAL when neither signal is found, since a
    plain question with no computation cue needs statutory grounding, not a
    guessed calculation.
    """
    lowered = query.lower()

    is_computation = any(keyword in lowered for keyword in _COMPUTATION_KEYWORDS) or bool(
        _COMPUTATION_AMOUNT_PATTERN.search(lowered)
    )
    is_retrieval = any(keyword in lowered for keyword in _RETRIEVAL_KEYWORDS)

    if is_computation and is_retrieval:
        return Intent.BOTH
    if is_computation:
        return Intent.COMPUTATION
    return Intent.RETRIEVAL
