"""Reciprocal Rank Fusion over the vector, keyword, and graph stores.

Fans out to Pinecone (semantic), Postgres FTS (lexical), and Neo4j (structured)
and fuses their rankings with RRF. RRF is used rather than score-weighting
because the three stores' scores are not comparable -- cosine similarity,
ts_rank, and a graph match live on different scales -- while their RANKS are.

DEGRADES, NEVER FAILS. Every store is currently expected to be partially or
wholly unavailable in normal operation: Neo4j Aura Free auto-pauses after three
days idle, and KnowledgeGraphProvision has no rows because nothing writes it
yet. A retrieval that returned nothing because one leg was asleep -- or worse,
raised and took the whole query down -- would be a much bigger problem than a
slightly thinner result set. So each leg is gathered with return_exceptions and
a failure degrades that leg to empty, logged at warning.

The graph leg is not a ranker here. It backfills `section_reference` onto
chunks the other stores found, via the chunk_id join in graph_store. That is
the vector/vectorless bridge: Pinecone knows WHICH chunk is relevant, the graph
knows WHAT SECTION that chunk states.
"""

import asyncio
import logging

from pydantic import BaseModel

from app.services.rag.retriever.graph_store import sections_for_chunks
from app.services.rag.retriever.keyword_store import keyword_search
from app.services.rag.retriever.vector_store import similarity_search
from app.shared.schemas.tax_year import TaxYearContext

logger = logging.getLogger(__name__)

# Standard RRF damping. Large enough that a top rank does not dominate the sum,
# so a chunk found by two stores at middling rank can outrank one found by a
# single store at rank 1 -- which is the point of fusing at all.
RRF_K = 60

# Seconds to wait on the graph before answering without section labels.
GRAPH_BACKFILL_TIMEOUT_S = 2.0


class RetrievedChunk(BaseModel):
    chunk_id: str
    source_id: str
    content: str
    section_reference: str | None = None
    score: float


def _settle(result: list[dict] | BaseException, store: str) -> list[dict]:
    if isinstance(result, BaseException):
        logger.warning("%s retrieval failed, degrading to empty: %s", store, result)
        return []
    return result


def reciprocal_rank_fusion(
    ranked_lists: list[list[dict]], k: int = RRF_K
) -> list[dict]:
    """Fuse ranked lists by summing 1/(k + rank) per chunk_id.

    Returns dicts carrying the fused score, ordered best-first. Note the fused
    score is NOT on the same scale as any input score (a cosine of 0.66 becomes
    an RRF contribution of ~0.016) -- it is a ranking quantity only, and must
    not be shown to a user or thresholded as if it were a similarity.
    """
    scores: dict[str, float] = {}
    docs: dict[str, dict] = {}

    for ranked in ranked_lists:
        for rank, doc in enumerate(ranked, start=1):
            chunk_id = doc.get("chunk_id")
            if not chunk_id:
                continue
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            # First writer wins: stores earlier in the list supply the content.
            docs.setdefault(chunk_id, doc)

    return [
        {**docs[chunk_id], "score": score}
        for chunk_id, score in sorted(
            scores.items(), key=lambda item: item[1], reverse=True
        )
    ]


async def hybrid_search(
    query: str, as_of: TaxYearContext, top_k: int = 10
) -> list[RetrievedChunk]:
    # Over-fetch each leg so fusion has room to reorder; fusing two top-10s
    # then cutting to 10 would mostly reproduce whichever leg ranked first.
    fetch_k = top_k * 2

    vector_result, keyword_result = await asyncio.gather(
        similarity_search(query, as_of, fetch_k),
        keyword_search(query, as_of, fetch_k),
        return_exceptions=True,
    )

    vector_hits = _settle(vector_result, "vector_store")
    keyword_hits = _settle(keyword_result, "keyword_store")

    if not vector_hits and not keyword_hits:
        return []

    fused = reciprocal_rank_fusion([vector_hits, keyword_hits])[:top_k]

    sections = await _sections_best_effort([d["chunk_id"] for d in fused])

    return [
        RetrievedChunk(
            chunk_id=doc["chunk_id"],
            source_id=doc.get("source_id", ""),
            content=doc.get("content", ""),
            section_reference=doc.get("section_reference")
            or sections.get(doc["chunk_id"]),
            score=doc["score"],
        )
        for doc in fused
    ]


async def _sections_best_effort(chunk_ids: list[str]) -> dict[str, str]:
    """Graph section backfill. An unreachable or empty graph costs section
    labels, not results -- so it must never propagate.

    The timeout is not belt-and-braces. The neo4j driver retries a failed
    transaction with exponential backoff for up to max_transaction_retry_time
    (30s by default), so an Aura instance that has auto-paused makes every
    single query hang for half a minute before this except clause is even
    reached. Since this leg only decorates results with section labels, waiting
    on it is never worth more than a moment.
    """
    try:
        return await asyncio.wait_for(
            sections_for_chunks(chunk_ids), timeout=GRAPH_BACKFILL_TIMEOUT_S
        )
    except asyncio.TimeoutError:
        logger.warning(
            "graph_store section backfill timed out after %ss; "
            "returning chunks without section labels",
            GRAPH_BACKFILL_TIMEOUT_S,
        )
        return {}
    except Exception as exc:
        logger.warning("graph_store section backfill failed: %s", exc)
        return {}
