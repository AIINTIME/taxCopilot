"""Deterministic routing of a query to computation, retrieval, or both.

This must be a deterministic classifier (keyword/pattern based), not an LLM
call -- the LLM never decides control flow in this system, only narrates
retrieved content.

The rule, in one line: a query needs COMPUTATION when it carries a figure to
compute on, and RETRIEVAL when it asks what the law says. Asking both at once
(the common real case -- "I earn 21 lakhs, can I claim HRA?") is BOTH.

Biased toward RETRIEVAL when nothing matches. A misrouted retrieval returns a
grounded, cited answer that is merely broader than asked; a misrouted
computation would try to compute with no figure and have to bail. Wrong-but-
useful beats wrong-and-empty.
"""

import re
from enum import Enum


class Intent(str, Enum):
    COMPUTATION = "computation"
    RETRIEVAL = "retrieval"
    BOTH = "both"


# An amount in Indian notation, or any bare 4+ digit number. Reuses the same
# vocabulary as query/input_extractor.py's parser -- if this matches, the
# extractor stands a chance of producing an input.
_AMOUNT = re.compile(
    r"\b\d[\d,]*(?:\.\d+)?\s*(?:lakhs?|lacs?|crores?|cr|l|k)\b"
    r"|\b\d{4,}\b"
    r"|[₹]\s*\d",
    re.IGNORECASE,
)

# Asking for a number to be produced.
_COMPUTE_MARKERS = (
    "how much tax",
    "how much do i",
    "calculate",
    "compute",
    "tax liability",
    "tax payable",
    "what tax",
    "my tax",
    "which regime",
    "old or new",
    "new or old",
    "better regime",
    "regime should",
    "take home",
    "net salary",
)

# Asking what the law says / means.
_RETRIEVE_MARKERS = (
    "what is",
    "what are",
    "explain",
    "define",
    "definition",
    "can i claim",
    "am i eligible",
    "eligible for",
    "rules for",
    "rule for",
    "section",
    "provision",
    "penalty",
    "punishment",
    "case law",
    "verdict",
    "judgment",
    "judgement",
    "why",
    "difference between",
    "documents",
)


def _has(query: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query for marker in markers)


def classify_intent(query: str) -> Intent:
    lowered = query.lower()

    has_amount = bool(_AMOUNT.search(lowered))
    wants_number = _has(lowered, _COMPUTE_MARKERS)
    wants_law = _has(lowered, _RETRIEVE_MARKERS)

    # Asking for a figure AND what the law says: "I earn 21 lakhs, how much tax
    # and can I claim HRA?"
    if wants_number and wants_law:
        return Intent.BOTH

    # A law question that happens to quote an amount is still a law question:
    # in "what is the 80C limit of 1.5 lakh?" the figure is part of the
    # question, not an input to compute on.
    if wants_law:
        return Intent.RETRIEVAL

    # An amount with no question attached is a computation request. Stating
    # "my income is 5 lakhs per annum" inside a tax workflow means "work out my
    # tax" -- routing it to retrieval answers a question nobody asked and, with
    # no figures for the model to narrate, produces "no computation was run".
    if wants_number or has_amount:
        return Intent.COMPUTATION

    return Intent.RETRIEVAL
