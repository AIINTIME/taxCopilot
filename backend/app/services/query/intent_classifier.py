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
from app.services.query.rate_lookup import detect_deduction_query

# A "how much / what limit" cue. Required for DEDUCTION_LOOKUP so that
# "explain 80C" (conceptual -> retrieval) is not mistaken for "what is the 80C
# limit" (figure lookup). Naming a section alone is not enough.
#
# "deduction under" / "rebate under" were here and had to go: they appear in
# ordinary prose that merely REFERS to a section ("home loan interest deduction
# under Section 24(b)"), so they hijacked qualitative questions and answered
# them with a limits table.
_LIMIT_CUE = (
    "limit",
    "maximum",
    "max ",
    "how much",
    "what is the",
    "upto",
    "up to",
    "amount",
    "quantum",
    "deduction available",
)

# Eligibility / interaction questions want reasoning, not a number, even though
# they name sections and may carry a limit cue. "Can I claim both HRA and
# 24(b)?" is answered by retrieval; returning the 24(b) cap answers a question
# nobody asked. These always beat the limit cue.
_ELIGIBILITY_MARKERS = (
    "can i",
    "can a",
    "can an",
    "am i",
    "are we",
    "eligible",
    "both",
    "together",
    "same time",
    "simultaneously",
    "as well as",
    "along with",
    "difference between",
)


class Intent(str, Enum):
    COMPUTATION = "computation"
    RETRIEVAL = "retrieval"
    BOTH = "both"
    RATE_LOOKUP = "rate_lookup"
    DEDUCTION_LOOKUP = "deduction_lookup"


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


# Asking to be shown the rate table itself -- "what are the slab rates",
# "tax slabs for AY 2025-26", "new regime rates". Distinct from a computation
# ("what is MY tax") because no income is involved: the answer is the table,
# read from slab_tables, not a figure computed for the user.
# Kept to phrases that clearly ask for the rate TABLE. Deliberately excludes
# "standard deduction" / "rebate" / "surcharge" on their own: those are as often
# conceptual ("explain the standard deduction" -> retrieval) as lookups, and the
# rate card already lists all three, so a slab-rate lookup shows them anyway.
_RATE_LOOKUP_MARKERS = (
    "slab rate",
    "slab rates",
    "tax slab",
    "tax slabs",
    "slabs for",
    "slab for",
    "rates for",
    "tax rate",
    "tax rates",
    "income tax rate",
    "rate of tax",
    "regime rate",
    "regime rates",
)


def _has(query: str, markers: tuple[str, ...]) -> bool:
    return any(marker in query for marker in markers)


def classify_intent(query: str) -> Intent:
    lowered = query.lower()

    income_stated = states_income(query)
    has_amount = bool(_AMOUNT.search(lowered))
    wants_number = _has(lowered, _COMPUTE_MARKERS)
    wants_law = _has(lowered, _RETRIEVE_MARKERS)
    wants_rates = _has(lowered, _RATE_LOOKUP_MARKERS)

    # A rate-table request -- but ONLY when no income is stated. "What are the
    # slab rates?" is a lookup; "my salary is 21L, what rate applies?" states an
    # income and should compute. So a stated income (or an explicit compute
    # phrasing) always wins over the rate-lookup markers.
    if wants_rates and not income_stated and not wants_number:
        return Intent.RATE_LOOKUP

    # A deduction/rebate LIMIT lookup: names a specific section AND asks how much
    # (the limit cue), with no income stated. "What is the 80D limit?" -> the
    # figure from slab_tables; "explain 80D" -> retrieval, because it lacks the
    # cue. The figure is a fact in the tables, so answer it deterministically
    # rather than sending it to the figure-banned LLM.
    if (
        not income_stated
        and not wants_number
        and not _has(lowered, _ELIGIBILITY_MARKERS)
        and _has(lowered, _LIMIT_CUE)
        and detect_deduction_query(query)
    ):
        return Intent.DEDUCTION_LOOKUP

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
