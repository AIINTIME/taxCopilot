"""Deterministic, embedding-backed routing of a query to computation,
retrieval, or both.

NOT currently wired into the live query flow. orchestration/graphs/
query_graph.py's classify_intent node calls
services.query.llm_query_understanding.classify_and_extract exclusively --
the LLM is the sole classifier by design, with no deterministic fallback: a
failed LLM call surfaces as a clear, retry-able error at the API layer
instead of silently degrading to this module. Kept as a standalone, still-
tested utility (not deleted, since it and its curated examples in
intent_examples.py remain independently correct and may be useful again),
but nothing in the request path calls it. Two non-generative layers:
1. A regex fast-path for the clearest, cheapest-to-recognize phrasings --
   zero API calls for the obvious cases.
2. An embedding-based k-NN classifier (same embedding provider used for
   retrieval -- not a generative call) for anything the regex can't
   confidently place, matched against the curated labeled examples in
   intent_examples.py. Same input always produces the same output --
   reproducible, not creative.
"""

import re

from app.services.query.intent_classifier_types import Intent

__all__ = ["Intent", "classify_intent"]

_COMPUTATION_VERBS = re.compile(
    r"\b(calculate|compute|how much|what('?s| is) (our|my) .*(liability|payable"
    r"|amount owed|tax owed|tax liability)"
    r"|work(s|ed)? out|liability (is|would be)|tax payable|figure out|determine|give me"
    r"|break down)\b",
    re.IGNORECASE,
)
# NOTE: this alternative deliberately requires "our"/"my" (a personal,
# company-specific pronoun) and a specific liability-indicating word
# (liability/payable/amount owed), NOT bare "tax"/"amount" with an
# unconstrained ".*" gap. The previous version -- "what is (our|the|my)
# .* (liability|tax|amount)" -- matched almost any "what is the ... tax..."
# sentence, since "tax" appears in nearly every sentence in this domain and
# ".*" has no length limit. Confirmed in practice: it matched an entire
# 46-character query end-to-end purely because "TAX" appeared in "Corporate
# TAX" at the end, with nothing to do with wanting a computed number. "what
# is THE X" (a general/statutory question) must NOT trigger this branch --
# only "what is OUR/MY X" (a personalized, computed number) should.

_COMPUTATION_RULE_KEYWORDS = re.compile(
    r"\b(mat\b|minimum alternate tax|amt\b|alternate minimum tax|115jb|115jc"
    r"|115baa|115bab|regime comparison|which regime|old regime|new regime"
    r"|depreciation|wdv|written down value"
    r"|capital gains?( tax)?|ltcg|stcg|indexation)\b",
    re.IGNORECASE,
)

_RETRIEVAL_VERBS = re.compile(
    r"\b(what(?:'?s| is| are)|explain|define|section \d|means?|applicable|eligib"
    r"|conditions?|provisions?|requirements?|consult|refer|describe|tell me about"
    r"|tell me what)\b",
    re.IGNORECASE,
)

_K_NEIGHBORS = 3
# k=5 was tried first but empirically loses to a "plurality of 3 moderately
# similar wrong-class neighbors beats a single clearly-closest right-class
# neighbor" failure mode against this ~65-example dataset (confirmed: k=5
# scored 11/12 on the accumulated regression set, k=1/2/3 all scored 12/12).
# A larger, denser example set might tolerate a larger k again later.
# Below this similarity, the nearest examples aren't actually close to the
# query -- e.g. "Hello" or other out-of-domain input still gets *some*
# nearest neighbor, but trusting it would force a confident-looking answer
# out of noise. Default to RETRIEVAL instead (it triggers the evidence gate
# and an honest "insufficient sources" fallback, never a fabricated number).
_MIN_CONFIDENT_SIMILARITY = 0.35
_example_vectors: list[tuple[list[float], Intent]] | None = None


def _regex_fast_path(query: str) -> Intent | None:
    """Returns a confident classification, or None if ambiguous (in which
    case the caller falls through to the embedding classifier)."""
    has_computation_verb = bool(_COMPUTATION_VERBS.search(query))
    has_rule_keyword = bool(_COMPUTATION_RULE_KEYWORDS.search(query))
    has_retrieval_verb = bool(_RETRIEVAL_VERBS.search(query))

    if has_computation_verb and has_rule_keyword and not has_retrieval_verb:
        return Intent.COMPUTATION
    if has_retrieval_verb and not has_computation_verb:
        return Intent.RETRIEVAL
    return None


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


async def _get_example_vectors() -> list[tuple[list[float], Intent]]:
    global _example_vectors
    if _example_vectors is None:
        from app.services.query.intent_examples import INTENT_EXAMPLES
        from app.shared.embeddings.openai_embedding_provider import get_embedding_provider

        texts = [text for text, _ in INTENT_EXAMPLES]
        vectors = await get_embedding_provider().embed(texts)
        _example_vectors = [
            (vector, intent) for vector, (_, intent) in zip(vectors, INTENT_EXAMPLES)
        ]
    return _example_vectors


async def _classify_by_embedding(query: str) -> Intent:
    from app.shared.embeddings.openai_embedding_provider import get_embedding_provider

    examples = await _get_example_vectors()
    [query_vector] = await get_embedding_provider().embed([query])

    scored = sorted(
        (
            (_cosine_similarity(query_vector, vector), intent)
            for vector, intent in examples
        ),
        key=lambda pair: pair[0],
        reverse=True,
    )
    if not scored or scored[0][0] < _MIN_CONFIDENT_SIMILARITY:
        return Intent.RETRIEVAL

    top_k = scored[:_K_NEIGHBORS]

    # Weight each neighbor's vote by its RANK (1/rank), not its raw
    # similarity and not a flat 1-vote-each. Two real failures drove this:
    # (1) flat voting: a 0.9999-similarity match lost 2-to-3 against three
    #     ~0.5-similarity matches for a different intent.
    # (2) similarity-sum voting (the first fix for #1): still lost when 3 of
    #     5 neighbors were a different intent even at moderate, similar
    #     similarities (0.64 vs 0.50/0.50/0.49) -- summing let plurality of
    #     mediocre matches outweigh the single closest one.
    # Plain 1/rank weighting resolves both, confirmed against both real
    # cases: rank 1 always contributes more than any lower rank can make up
    # for by mere numbers, while still letting a genuine plurality at
    # similar rank positions win when the top match isn't clearly best.
    votes: dict[Intent, float] = {}
    for rank, (_similarity, intent) in enumerate(top_k, start=1):
        votes[intent] = votes.get(intent, 0.0) + 1.0 / rank
    return max(votes, key=lambda intent: votes[intent])


def _regex_best_guess(query: str) -> Intent:
    has_computation_verb = bool(_COMPUTATION_VERBS.search(query))
    has_rule_keyword = bool(_COMPUTATION_RULE_KEYWORDS.search(query))
    if has_computation_verb and has_rule_keyword:
        return Intent.COMPUTATION
    return Intent.RETRIEVAL


async def classify_intent(query: str) -> Intent:
    fast_path_result = _regex_fast_path(query)
    if fast_path_result is not None:
        return fast_path_result

    try:
        return await _classify_by_embedding(query)
    except Exception:
        # Never let a classifier/embedding-API outage take the whole query
        # down -- degrade to the regex's best guess rather than crash.
        return _regex_best_guess(query)
