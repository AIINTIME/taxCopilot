"""Ground-truth verification: checks a ComputationTrace's applied rate
against what the graph DB (Neo4j -- structured rate rules committed by
services/ingestion/kg_graph_extraction/graph_writer.py) and the vector DB
(statutory text chunks retrieved via hybrid_search) say should apply.

Sibling to evidence_gate.py, which verifies *citations* against retrieved
chunks -- this module plays the same "never silently trust, flag mismatches"
role for a *computed result* instead. It never blocks a response outright;
it attaches its verdict so the caller (assemble_response) can surface
mismatches to the user rather than silently trusting either the engine or
the graph.

No graph rule for the asset class/section in question is reported as
`verified=False` with an empty `mismatches` list -- "no ground truth
available yet" (e.g. the statutory PDF hasn't been ingested) is a distinct
state from "ground truth disagrees with the engine", and the two must never
be conflated.

Matching against the graph is fuzzy (see retriever/graph_store.py) -- a
keyword search over free-text asset_class labels returns candidates, not one
authoritative hit, and some candidates will be irrelevant noise (e.g. a
promoter-buyback rate also containing the word "capital"). So this looks for
*corroboration* among candidates rather than requiring unanimous agreement:
if at least one matched rule's rate agrees with what the engine applied,
that's verification, even if other noisy candidates disagree. Only when
every matched rule disagrees is it reported as unconfirmed -- phrased as
"not corroborated," not a confident contradiction, since fuzzy matches may
simply be off-topic rather than genuinely conflicting.
"""

import re

from pydantic import BaseModel

from app.services.computation.computation_trace import ComputationTrace
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk

_GAIN_TYPE_KEYWORDS = {
    "long_term": ["long-term", "long term"],
    "short_term": ["short-term", "short term"],
}
_BASE_KEYWORDS = ["capital gain", "capital asset"]


class GroundTruthCheckResult(BaseModel):
    verified: bool
    mismatches: list[str]
    matched_graph_rules: list[dict]
    supporting_chunk_ids: list[str]


def derive_ground_truth_keywords(rule_name: str, trace_outputs: dict) -> list[str]:
    """Build the keyword list services/rag/retriever/graph_store.py's
    lookup_rate_rule expects, from a computation's own result -- e.g.
    gain_type="long_term" -> ["capital gain", "capital asset", "long-term",
    "long term"]. Only capital_gains-family rules are covered; other rule
    names have no ground-truth lookup wired up yet.
    """
    if rule_name not in ("capital_gains", "capital_gains_exemption"):
        return []
    keywords = list(_BASE_KEYWORDS)
    keywords.extend(_GAIN_TYPE_KEYWORDS.get(trace_outputs.get("gain_type"), []))
    return keywords


def _parse_rate(rate_text: str | None) -> float | None:
    if not rate_text:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", rate_text)
    if not match:
        return None
    return float(match.group(1)) / 100.0


def _rates_agree(applied_rate: float, graph_rate: float, tolerance: float = 0.001) -> bool:
    return abs(applied_rate - graph_rate) <= tolerance


def verify_computation_ground_truth(
    trace: ComputationTrace,
    retrieved_chunks: list[RetrievedChunk],
    graph_rules: list[dict],
) -> GroundTruthCheckResult:
    supporting_chunk_ids = [chunk.chunk_id for chunk in retrieved_chunks]

    if not graph_rules:
        return GroundTruthCheckResult(
            verified=False,
            mismatches=[],
            matched_graph_rules=[],
            supporting_chunk_ids=supporting_chunk_ids,
        )

    applied_rate = trace.outputs.get("tax_rate_applied")
    matched_graph_rules: list[dict] = []
    agreeing_rules: list[dict] = []

    for rule in graph_rules:
        graph_rate = _parse_rate(rule.get("rate"))
        if graph_rate is None:
            continue
        matched_graph_rules.append(rule)
        if applied_rate is not None and _rates_agree(applied_rate, graph_rate):
            agreeing_rules.append(rule)

    if not matched_graph_rules:
        return GroundTruthCheckResult(
            verified=False,
            mismatches=[],
            matched_graph_rules=[],
            supporting_chunk_ids=supporting_chunk_ids,
        )

    if agreeing_rules:
        return GroundTruthCheckResult(
            verified=True,
            mismatches=[],
            matched_graph_rules=matched_graph_rules,
            supporting_chunk_ids=supporting_chunk_ids,
        )

    sample_rates = ", ".join(repr(rule.get("rate")) for rule in matched_graph_rules[:3])
    mismatches = [
        f"Engine applied rate {applied_rate!r} for rule {trace.rule_name!r}, "
        f"but none of the {len(matched_graph_rules)} matched graph rule(s) "
        f"corroborate it (sample rates found: {sample_rates})"
    ]
    return GroundTruthCheckResult(
        verified=False,
        mismatches=mismatches,
        matched_graph_rules=matched_graph_rules,
        supporting_chunk_ids=supporting_chunk_ids,
    )
