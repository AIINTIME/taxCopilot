"""Resolves the sections a computation trace cited into verbatim citations.

Without this node a computation query returns `citations: []` -- "you owe
2,14,500 under Sec 115BAC" with nothing a reader could check -- even though
every TraceStep is already tagged with its section. This closes that gap by
looking each section up in the Neo4j rule graph.

These citations never pass through an LLM: they are assembled from a
SOURCED_FROM edge whose evidence_span was checked verbatim against its source
chunk at ingestion. They are therefore verified by construction and skip the
Evidence Gate, which exists to catch LLM invention. Keep that distinct from the
narration path, where citations are model-produced and must be gated.

TIMEOUT IS LOAD-BEARING, not defensive habit. The neo4j driver retries a failed
transaction with exponential backoff up to max_transaction_retry_time (30s
default), and Neo4j Aura Free auto-pauses after three days idle -- measured in
Phase 2, an asleep instance stalled every query for ~30s before failing. Since
this node only decorates an already-correct answer with provenance, waiting on
it is never worth more than a moment.
"""

import asyncio
import logging

from app.orchestration.state import QueryGraphState
from app.services.rag.retriever.graph_store import citations_for_sections

logger = logging.getLogger(__name__)

CITATION_LOOKUP_TIMEOUT_S = 2.0


async def resolve_computation_citations(state: QueryGraphState) -> dict:
    trace = state.get("computation_trace") or {}
    sections: list[str] = list(trace.get("statutory_references") or [])

    if not sections:
        return {"gated_citations": [], "uncited_sections": [], "gate_status": "VERIFIED"}

    citations = await _citations_best_effort(sections, state["as_of"])
    cited = {c.section_reference for c in citations}
    uncited = [s for s in sections if s not in cited]

    # VERIFIED even when nothing resolved: the figures come from pure functions
    # over versioned rate tables and never touch an LLM, so there is nothing
    # hallucinated for a gate to catch -- citations are provenance, not
    # correctness. `uncited_sections` rides along so the response can show
    # "source text unavailable" rather than hiding the gap.
    #
    # Today `uncited` is expected to be EVERY section: the rule graph holds zero
    # rules for Sec 115BAC, Sec 87A or Sec 16(ia), because the extraction schema
    # is capital-gains shaped and cannot represent a slab or a rebate. That is a
    # data gap, resolved by re-extraction, not a defect here.
    if uncited:
        logger.info(
            "computation cited %d section(s) the rule graph could not resolve: %s",
            len(uncited),
            ", ".join(uncited),
        )

    return {
        "gated_citations": citations,
        "uncited_sections": uncited,
        "gate_status": "VERIFIED",
    }


async def _citations_best_effort(sections: list[str], as_of) -> list:
    try:
        return await asyncio.wait_for(
            citations_for_sections(sections, as_of),
            timeout=CITATION_LOOKUP_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        logger.warning(
            "graph citation lookup timed out after %ss; answering without sources",
            CITATION_LOOKUP_TIMEOUT_S,
        )
        return []
    except Exception as exc:
        logger.warning("graph citation lookup failed: %s", exc)
        return []
