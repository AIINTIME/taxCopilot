"""Declines questions this system cannot honestly answer, before it tries.

Three kinds, each a *capability* boundary rather than a bug:

  * OUT_OF_DOMAIN -- indirect taxes (GST, customs, excise). The corpus is
    direct-tax only; nothing indexed can answer them.
  * RECENCY_UNVERIFIABLE -- "as amended by a notification issued this week".
    There is no recency tracking anywhere in this system.
  * CROSS_ACT_COMPARISON -- "what changed between the 1961 Act and the 2025
    Act". No 2025-Act text is ingested, and no section mapping exists.

Why a deterministic guard rather than trusting the model to decline: it already
declines a GST question correctly, but only because it *chose* to obey a soft
prompt rule, and that decline is recognised downstream by an exact full-string
match. Retrieval has no score floor, so an out-of-domain query still pulls ten
direct-tax chunks and hands them to the model as context; whether it answers
from them is luck. The evidence gate cannot help -- it verifies that a claim
came from a retrieved chunk, not that the chunk is *about the question asked*.
A GST answer fabricated from Income-tax chunks would pass it.

Pure, zero I/O, no LLM. Same discipline as rate_lookup.py: a question this
system cannot source is refused by code, not by disposition.

Each message says WHY, because "I can't answer that" invites a rephrase that
cannot work either. A user told the corpus has no GST stops asking; a user told
"insufficient sources" tries again with different words.
"""

import re
from dataclasses import dataclass
from enum import Enum


class DeclineReason(str, Enum):
    OUT_OF_DOMAIN = "out_of_domain"
    RECENCY_UNVERIFIABLE = "recency_unverifiable"
    CROSS_ACT_COMPARISON = "cross_act_comparison"


@dataclass(frozen=True)
class ScopeDecline:
    reason: DeclineReason
    answer: str


# --- Out of domain: indirect taxes -------------------------------------------

# Subject -> how to name it back to the user.
_OUT_OF_DOMAIN_SUBJECTS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("GST", re.compile(r"\b(gst|goods\s+and\s+services\s+tax|gstr\-?\d?|e\-?way\s+bill|input\s+tax\s+credit|itc)\b", re.IGNORECASE)),
    ("customs duty", re.compile(r"\b(customs?\s+dut(?:y|ies)|basic\s+customs|bcd)\b", re.IGNORECASE)),
    ("excise duty", re.compile(r"\b(excise\s+dut(?:y|ies)|cenvat)\b", re.IGNORECASE)),
    ("VAT", re.compile(r"\bvat\b", re.IGNORECASE)),
    ("stamp duty", re.compile(r"\bstamp\s+dut(?:y|ies)\b", re.IGNORECASE)),
)

# A direct-tax question is allowed to MENTION an indirect tax -- "is the GST I
# paid on business expenses deductible under income tax?" is squarely in scope
# and must not be refused. So an indirect-tax word only declines when the
# question carries no direct-tax subject of its own. Mentioning is not asking.
_DIRECT_TAX_MARKERS = re.compile(
    r"\b(income[\s\-]?tax|itr|tds|tcs|capital\s+gains?|ltcg|stcg|deduction|"
    r"exemption|regime|assessment\s+year|\bay\b|financial\s+year|advance\s+tax|"
    r"salary|salaried|80[a-z]{1,3}|87a|115[a-z]{3}|24\(b\)|10\(13a\)|16\(ia\)|"
    r"depreciation|mat\b|amt\b|surcharge|cess|rebate|slab)\b",
    re.IGNORECASE,
)


# --- Recency: no notification is dated in this system -------------------------

_RECENCY_CUE = re.compile(
    r"\b(this\s+week|last\s+week|past\s+(?:few\s+)?(?:days|weeks)|yesterday|"
    r"today'?s|this\s+month|last\s+month|recently|just\s+(?:issued|notified|released)|"
    r"latest|newest|most\s+recent)\b",
    re.IGNORECASE,
)

# The recency cue must attach to an INSTRUMENT. "How much tax will I owe this
# year?" carries a time cue and is an ordinary computation -- it must compute,
# not decline. Requiring an instrument word keeps the two apart.
_INSTRUMENT = re.compile(
    r"\b(notification|notifications|circular|circulars|press\s+release|"
    r"amendment|amendments|notified|gazette)\b",
    re.IGNORECASE,
)


# --- Cross-Act: the 2025 Act is not ingested ----------------------------------

# Must not match "AY 2025-26" / "FY 2025-26", which are ordinary and in scope --
# hence requiring the word "act" adjacent, and a negative lookahead on the
# hyphenated year form.
_ACT_2025 = re.compile(
    r"\b(?:i\.?t\.?|income[\s\-]?tax)\s+act,?\s+2025\b(?!\s*[-–]\s*\d)"
    r"|\b2025\s+act\b"
    r"|\bnew\s+income[\s\-]?tax\s+act\b",
    re.IGNORECASE,
)


def _decline(reason: DeclineReason, answer: str) -> ScopeDecline:
    return ScopeDecline(reason=reason, answer=answer)


def check_scope(query: str) -> ScopeDecline | None:
    """The reason this question cannot be answered, or None to proceed."""
    if not query or not query.strip():
        return None

    # Cross-Act first: "has X changed between the 1961 Act and the 2025 Act?"
    # carries direct-tax markers and would otherwise sail through to retrieval
    # and be answered from 1961-only chunks as though it had compared them.
    if _ACT_2025.search(query):
        return _decline(
            DeclineReason.CROSS_ACT_COMPARISON,
            "I can't answer questions about the Income-tax Act 2025, or compare it "
            "against the 1961 Act. Only 1961-Act material is indexed here — no "
            "2025-Act text has been ingested and no mapping between the two Acts' "
            "section numbers exists, so any comparison would be guesswork rather "
            "than something I could source. Please check the bare Act, or ask about "
            "the 1961 Act instead.",
        )

    if _RECENCY_CUE.search(query) and _INSTRUMENT.search(query):
        return _decline(
            DeclineReason.RECENCY_UNVERIFIABLE,
            "I can't answer questions that turn on how recently something was "
            "issued. This system has no recency tracking: indexed documents carry "
            "no issue date, so I cannot confirm whether a notification or circular "
            "from this week exists, nor what it changed. Anything I told you would "
            "reflect the corpus as it was ingested, with no way to know if it is "
            "current. Please check the CBDT / Income Tax Department site directly "
            "for recently issued instruments.",
        )

    if not _DIRECT_TAX_MARKERS.search(query):
        for subject, pattern in _OUT_OF_DOMAIN_SUBJECTS:
            if pattern.search(query):
                return _decline(
                    DeclineReason.OUT_OF_DOMAIN,
                    f"That question is about {subject}, which is outside what this "
                    "assistant covers. It answers direct-tax questions under the "
                    "Income-tax Act 1961 — personal and corporate income tax, "
                    "capital gains, TDS/TCS and notices. No indirect-tax material "
                    f"is indexed, so I have no source for a {subject} question and "
                    "would only be guessing. Please consult a specialist for it.",
                )

    return None
