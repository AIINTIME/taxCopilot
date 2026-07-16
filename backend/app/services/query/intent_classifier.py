"""Deterministic routing of a query to computation, retrieval, or both.

This must be a deterministic classifier (keyword/pattern based), not an LLM
call -- the LLM never decides control flow in this system, only narrates
retrieved content.

THE PRIMARY SIGNAL IS A STATED INCOME, NOT THE PHRASING OF THE QUESTION. If the
user says what they earn, that figure is an INPUT and they want it computed on,
however they happen to word the ask.

That rule is deliberate, and was learned the hard way. This module first tried
to match the QUESTION instead: a list of compute phrasings ("how much tax",
"what tax") against a list of law phrasings ("what is", "explain"). It
misroutes repeatedly, because the two are not separable by wording --

    "what is the tax i should pay"  -> compute   } identical openings
    "what is HRA"                   -> retrieve  }

-- and every miss degrades SILENTLY to "no computation was run for this
question": a plausible paragraph where a number was asked for. Two real user
phrasings escaped the enumerated list before this rule replaced it: "what is
the tax i should pay", then "what is my payable tax" (which merely reverses the
word order of "tax payable"). There is always a third phrasing. There is only
one income.

The compute markers below survive, but only to catch the case where NO income
is stated -- "how much tax do I pay?" -- so the graph can ask for the figure
rather than retrieving generic slab commentary. They are a backstop, not the
mechanism.

Biased toward RETRIEVAL when nothing matches. A misrouted retrieval returns a
grounded, cited answer that is merely broader than asked; a misrouted
computation would try to compute with no figure and have to bail. Wrong-but-
useful beats wrong-and-empty.
"""

import re
from enum import Enum

from app.services.query.input_extractor import states_income


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
#
# Phrasings of "what is my tax bill" are enumerated rather than matched loosely,
# because the natural ones collide head-on with _RETRIEVE_MARKERS' "what is".
# "What is the tax I should pay" is a computation request; "what is HRA" is not,
# and the two open identically. A phrasing missing from this list does not fail
# loudly -- it routes a calculation to retrieval, which answers "no computation
# was run for this question". So extend THIS list when a variant is missed;
# never loosen the retrieval side to compensate.
_COMPUTE_MARKERS = (
    "how much tax",
    "how much do i",
    "calculate",
    "compute",
    "tax liability",
    "tax payable",
    "what tax",
    "what is the tax",
    "what is my tax",
    "what will be my tax",
    "what would be my tax",
    "what will my tax",
    "tax i should pay",
    "tax should i pay",
    "tax i have to pay",
    "tax do i pay",
    "tax to pay",
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

    income_stated = states_income(query)
    has_amount = bool(_AMOUNT.search(lowered))
    wants_number = _has(lowered, _COMPUTE_MARKERS)
    wants_law = _has(lowered, _RETRIEVE_MARKERS)

    # A stated income settles it: the figure is an input, so compute on it.
    # Where the user ALSO asks what the law says -- "I earn 21 lakhs, can I
    # claim HRA?", or "my salary is 19 lakhs, what is my payable tax" where
    # "what is" reads as a law question -- take BOTH. It computes either way,
    # and the retrieved context only improves the narration around figures the
    # engine already produced.
    if income_stated or wants_number:
        return Intent.BOTH if wants_law else Intent.COMPUTATION

    # No income stated. A law question that quotes an amount is still a law
    # question: in "what is the 80C limit of 1.5 lakh?" the figure belongs to
    # the section, not to the taxpayer.
    if wants_law:
        return Intent.RETRIEVAL

    # A bare amount with no question attached -- "21 lakhs" -- is a computation
    # request by context: this is a tax calculator.
    if has_amount:
        return Intent.COMPUTATION

    return Intent.RETRIEVAL
