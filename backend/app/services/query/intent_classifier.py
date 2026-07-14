"""Deterministic routing of a query to computation, retrieval, or both.

This must be a deterministic classifier (keyword/pattern based), not an LLM
call -- the LLM never decides control flow in this system, only narrates
retrieved content.
"""

from enum import Enum


class Intent(str, Enum):
    COMPUTATION = "computation"
    RETRIEVAL = "retrieval"
    BOTH = "both"


def classify_intent(query: str) -> Intent:
    raise NotImplementedError(
        "TODO: deterministic (non-LLM) classification of query -> Intent"
    )
