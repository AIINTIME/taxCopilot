"""Retrieval layer tests (Phase 2).

Deliberately runs without credentials: the RRF fusion is pure, and the fan-out
behaviour is exercised by substituting the stores. The live-infrastructure
checks live in the integration script rather than here, so the suite stays fast
and green on a laptop with no .env.

The degradation tests carry the most weight. Every store is expected to be
unavailable in normal operation -- Neo4j Aura Free auto-pauses after three days
idle, and KnowledgeGraphProvision is empty -- so "one leg is down" is the
common case, not the exception, and a regression there would silently gut
retrieval quality rather than raise.
"""

import asyncio
from datetime import date

import pytest

from app.services.rag.retriever import hybrid_retriever
from app.services.rag.retriever.hybrid_retriever import (
    RRF_K,
    reciprocal_rank_fusion,
)
from app.shared.schemas.tax_year import (
    AssessmentYear,
    CapitalGainsPeriod,
    TaxActRegime,
    TaxYearContext,
)

AS_OF = TaxYearContext(
    as_of_date=date(2026, 3, 31),
    assessment_year=AssessmentYear(ay="2026-27", financial_year="2025-26"),
    regime=TaxActRegime.ACT_1961,
    capital_gains_period=CapitalGainsPeriod.POST_RATE_CHANGE,
)


def chunk(chunk_id: str, score: float = 0.5, **extra) -> dict:
    return {
        "chunk_id": chunk_id,
        "source_id": f"src-{chunk_id}",
        "content": f"content of {chunk_id}",
        "section_reference": None,
        "score": score,
        **extra,
    }


class TestReciprocalRankFusion:
    def test_empty_input_gives_empty_output(self):
        assert reciprocal_rank_fusion([]) == []
        assert reciprocal_rank_fusion([[], []]) == []

    def test_single_list_preserves_order(self):
        fused = reciprocal_rank_fusion([[chunk("a"), chunk("b"), chunk("c")]])
        assert [d["chunk_id"] for d in fused] == ["a", "b", "c"]

    def test_agreement_between_stores_beats_a_single_top_hit(self):
        # "b" is 2nd in both lists; "a" and "x" are 1st in one list each.
        # Agreement should win -- this is the entire reason to fuse.
        vector = [chunk("a"), chunk("b")]
        keyword = [chunk("x"), chunk("b")]

        fused = reciprocal_rank_fusion([vector, keyword])
        assert fused[0]["chunk_id"] == "b"

    def test_score_is_the_rrf_sum_not_the_input_score(self):
        # Input scores are on incomparable scales (cosine vs ts_rank), so the
        # fused score must be derived from RANK alone.
        fused = reciprocal_rank_fusion([[chunk("a", score=0.99)]])
        assert fused[0]["score"] == pytest.approx(1.0 / (RRF_K + 1))

    def test_duplicate_across_lists_appears_once(self):
        fused = reciprocal_rank_fusion([[chunk("a")], [chunk("a")]])
        assert len(fused) == 1
        assert fused[0]["score"] == pytest.approx(2.0 / (RRF_K + 1))

    def test_first_list_wins_for_content(self):
        vector = [chunk("a", content="from vector")]
        keyword = [chunk("a", content="from keyword")]
        assert reciprocal_rank_fusion([vector, keyword])[0]["content"] == "from vector"

    def test_chunks_without_an_id_are_skipped(self):
        assert reciprocal_rank_fusion([[{"content": "orphan"}]]) == []


class TestDegradation:
    """A store being down must cost results, never raise."""

    def _run(self, monkeypatch, *, vector, keyword, sections=None):
        async def fake_vector(q, a, k):
            if isinstance(vector, Exception):
                raise vector
            return vector

        async def fake_keyword(q, a, k):
            if isinstance(keyword, Exception):
                raise keyword
            return keyword

        async def fake_sections(ids):
            if isinstance(sections, Exception):
                raise sections
            return sections or {}

        monkeypatch.setattr(hybrid_retriever, "similarity_search", fake_vector)
        monkeypatch.setattr(hybrid_retriever, "keyword_search", fake_keyword)
        monkeypatch.setattr(hybrid_retriever, "sections_for_chunks", fake_sections)
        return asyncio.run(hybrid_retriever.hybrid_search("q", AS_OF, top_k=5))

    def test_vector_store_failure_still_returns_keyword_results(self, monkeypatch):
        out = self._run(
            monkeypatch, vector=RuntimeError("pinecone down"), keyword=[chunk("k1")]
        )
        assert [c.chunk_id for c in out] == ["k1"]

    def test_keyword_store_failure_still_returns_vector_results(self, monkeypatch):
        out = self._run(
            monkeypatch, vector=[chunk("v1")], keyword=RuntimeError("db down")
        )
        assert [c.chunk_id for c in out] == ["v1"]

    def test_both_stores_down_returns_empty_not_an_exception(self, monkeypatch):
        out = self._run(
            monkeypatch,
            vector=RuntimeError("pinecone down"),
            keyword=RuntimeError("db down"),
        )
        assert out == []

    def test_paused_graph_costs_section_labels_only(self, monkeypatch):
        # The live case today: Aura is asleep, but answers must still flow.
        out = self._run(
            monkeypatch,
            vector=[chunk("v1")],
            keyword=[],
            sections=RuntimeError("Unable to retrieve routing information"),
        )
        assert [c.chunk_id for c in out] == ["v1"]
        assert out[0].section_reference is None

    def test_a_hanging_graph_does_not_hang_the_query(self, monkeypatch):
        # The neo4j driver retries a paused instance with backoff for up to 30s.
        # Without the timeout, every query would block for half a minute.
        async def hangs(ids):
            await asyncio.sleep(30)
            return {}

        async def fake_vector(q, a, k):
            return [chunk("v1")]

        async def fake_keyword(q, a, k):
            return []

        monkeypatch.setattr(hybrid_retriever, "similarity_search", fake_vector)
        monkeypatch.setattr(hybrid_retriever, "keyword_search", fake_keyword)
        monkeypatch.setattr(hybrid_retriever, "sections_for_chunks", hangs)
        monkeypatch.setattr(hybrid_retriever, "GRAPH_BACKFILL_TIMEOUT_S", 0.05)

        async def timed():
            loop = asyncio.get_running_loop()
            start = loop.time()
            out = await hybrid_retriever.hybrid_search("q", AS_OF, top_k=5)
            return out, loop.time() - start

        out, elapsed = asyncio.run(timed())
        assert [c.chunk_id for c in out] == ["v1"]
        assert elapsed < 1.0


class TestSectionBackfill:
    """The vector/vectorless bridge: Pinecone has no section metadata, so the
    label can only come from the graph, joined on chunk_id.
    """

    def _run(self, monkeypatch, sections):
        async def fake_vector(q, a, k):
            return [chunk("c1"), chunk("c2")]

        async def fake_keyword(q, a, k):
            return []

        async def fake_sections(ids):
            return sections

        monkeypatch.setattr(hybrid_retriever, "similarity_search", fake_vector)
        monkeypatch.setattr(hybrid_retriever, "keyword_search", fake_keyword)
        monkeypatch.setattr(hybrid_retriever, "sections_for_chunks", fake_sections)
        return asyncio.run(hybrid_retriever.hybrid_search("q", AS_OF, top_k=5))

    def test_graph_supplies_the_section_a_vector_hit_lacks(self, monkeypatch):
        out = self._run(monkeypatch, {"c1": "Sec 80C"})
        by_id = {c.chunk_id: c for c in out}
        assert by_id["c1"].section_reference == "Sec 80C"

    def test_chunks_with_no_committed_rule_keep_a_null_section(self, monkeypatch):
        # Only ~4% of chunks yielded a committed rule, so this is the norm.
        out = self._run(monkeypatch, {"c1": "Sec 80C"})
        by_id = {c.chunk_id: c for c in out}
        assert by_id["c2"].section_reference is None
