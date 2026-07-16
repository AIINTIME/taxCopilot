"""Orchestration layer tests (Phase 3).

Everything here is pure or substituted -- no DB, no Pinecone, no LLM. The
graph's own wiring is exercised end-to-end in the integration run; these cover
the decision logic that would otherwise only fail in production.
"""

import asyncio
from datetime import date

import pytest

from app.orchestration.nodes.assemble_response import assemble_response
from app.services.query.intent_classifier import Intent, classify_intent
from app.services.rag.confidence import calculate_confidence
from app.services.rag.evidence_gate import verify_citations
from app.services.rag.prompts import build_narration_messages, parse_narration
from app.services.rag.retriever.hybrid_retriever import RetrievedChunk
from app.shared.schemas.citation import Citation
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


class TestIntentClassifier:
    @pytest.mark.parametrize(
        "query",
        [
            "My current salary is 21 lakhs per annum what tax should I pay",
            "how much tax do I pay",
            "calculate my tax liability",
            "which regime should I choose",
        ],
    )
    def test_computation_queries(self, query):
        assert classify_intent(query) is Intent.COMPUTATION

    def test_a_bare_income_statement_is_a_computation_request(self):
        # No "what tax" phrasing at all. Stating an income inside a tax
        # workflow means "work this out" -- routing it to retrieval answers a
        # question nobody asked, and with no figures to narrate the model
        # replies "no computation was run". Regression: this shipped wrong.
        assert classify_intent("my income is 5 lakhs per annum") is Intent.COMPUTATION

    @pytest.mark.parametrize(
        "query",
        [
            # Both of these escaped an enumerated list of compute phrasings, in
            # production, one after the other.
            "My current salary is 21 Lakhs per annum what is the tax i should pay",
            "My salary is 19 lakhs per annum what is my payable tax",
            # Phrasings nobody would think to enumerate. That is the point: the
            # signal is the stated income, not the wording of the question.
            "I earn 12 lakhs, whats the damage",
            "salary 21 lakhs. tax?",
            "my salary is 18lpa, what is my tax payable",
            "what will be my tax if my salary is 18lpa",
        ],
    )
    def test_a_stated_income_always_computes_however_it_is_asked(self, query):
        # REGRESSION x2, both found against the real UI. Matching the QUESTION
        # cannot work: "what is the tax i should pay" and "what is HRA" open
        # identically, and "payable tax" reverses "tax payable". Each miss
        # degrades silently to "no computation was run" -- a plausible paragraph
        # where a number was asked for. Route on the income instead: there is
        # always another phrasing, but only one income.
        assert classify_intent(query) in (Intent.COMPUTATION, Intent.BOTH)

    def test_an_amount_owned_by_a_section_is_not_an_income(self):
        # The counterweight: routing on "there is a number" would drag every
        # law question that quotes a threshold into the computation branch.
        # "What is the 80C limit" is a deduction-limit lookup (answered from the
        # tables); the 1.5 lakh is the answer, not the taxpayer's income, so the
        # key property is that it is NOT a computation.
        assert classify_intent("what is the 80C limit of 1.5 lakh") is Intent.DEDUCTION_LOOKUP

    @pytest.mark.parametrize(
        "query",
        [
            "What are the income tax slab rates for the new regime for AY 2025-26?",
            "tax slabs for AY 2026-27",
            "show me the new regime rates",
            "income tax rate for old regime",
        ],
    )
    def test_rate_table_questions_route_to_rate_lookup(self, query):
        # The bug that prompted this: a rate-table question is a figure lookup,
        # but with no income it went to the LLM -- which is forbidden from
        # stating figures -- and answered "no information". Route it to
        # slab_tables instead.
        assert classify_intent(query) is Intent.RATE_LOOKUP

    def test_a_stated_income_beats_the_rate_markers(self):
        # "my salary is 21L, what rate applies" states an income: compute, do
        # not just show the table.
        assert classify_intent("my salary is 21 lakhs, what tax rate applies") in (
            Intent.COMPUTATION,
            Intent.BOTH,
        )

    def test_explain_is_a_retrieval_not_a_table_lookup(self):
        # "explain the standard deduction" wants prose, not the rate table.
        assert classify_intent("explain the standard deduction") is Intent.RETRIEVAL

    @pytest.mark.parametrize(
        "query",
        [
            "What is the maximum deduction available under Section 80D for senior citizen parents?",
            "What is the rebate limit under Section 87A?",
            "how much is the 80C limit",
            "what is the standard deduction limit",
        ],
    )
    def test_deduction_limit_questions_route_to_deduction_lookup(self, query):
        # These ask for a FIGURE that lives in slab_tables. Sent to retrieval
        # they hit the figure ban and return "no information"; they must be
        # answered from the tables instead.
        assert classify_intent(query) is Intent.DEDUCTION_LOOKUP

    def test_naming_a_section_without_a_limit_cue_stays_retrieval(self):
        # "explain 80C" / "what does 80D cover" want prose, not the number.
        assert classify_intent("explain Section 80C") is Intent.RETRIEVAL
        assert classify_intent("what does Section 80D cover") is Intent.RETRIEVAL

    @pytest.mark.parametrize(
        "query",
        [
            "Can a salaried individual claim both HRA exemption under Section 10(13A) and "
            "home loan interest deduction under Section 24(b) in the same assessment year?",
            "Am I eligible for 80C and 80D together?",
            "what is the difference between 80C and 80D",
        ],
    )
    def test_eligibility_questions_are_not_hijacked_by_the_limit_lookup(self, query):
        # REGRESSION, found by re-running the question battery: the phrase
        # "deduction under Section 24(b)" merely REFERS to a section, but it
        # matched the limit cue, so an eligibility question was answered with a
        # limits table -- a confident answer to a question nobody asked.
        # Eligibility wants reasoning; it always beats the limit cue.
        assert classify_intent(query) is Intent.RETRIEVAL

    @pytest.mark.parametrize(
        "query",
        [
            "what is HRA exemption under section 10(13A)",
            "explain the standard deduction",
            "can I claim 80C and HRA together",
            "what is the penalty for under-reporting income",
        ],
    )
    def test_retrieval_queries(self, query):
        assert classify_intent(query) is Intent.RETRIEVAL

    def test_an_amount_inside_a_lookup_is_not_treated_as_income(self):
        # The 1.5 lakh is part of the question, not an input to compute on. It
        # routes to the deduction-limit lookup, never to computation.
        assert classify_intent("what is the 80C limit of 1.5 lakh") is not Intent.COMPUTATION

    def test_asking_for_both_a_figure_and_the_law(self):
        assert (
            classify_intent("I earn 21 lakhs, how much tax and can I claim HRA?")
            is Intent.BOTH
        )

    def test_never_reaches_an_llm(self):
        # The LLM makes no control-flow decisions in this system. Assert it
        # structurally, by what the module can reach, rather than by grepping
        # prose -- the docstrings legitimately discuss the LLM.
        import inspect

        from app.services.query import intent_classifier

        imports = [
            line
            for line in inspect.getsource(intent_classifier).splitlines()
            if line.startswith(("import ", "from "))
        ]
        assert not any("llm" in line or "openai" in line for line in imports)


class TestEvidenceGate:
    def _chunk(self, chunk_id="c1", content="The standard deduction is allowed."):
        return RetrievedChunk(
            chunk_id=chunk_id, source_id="s1", content=content, score=0.5
        )

    def _cite(self, chunk_id="c1", excerpt="standard deduction is allowed"):
        return Citation(
            chunk_id=chunk_id, source_id="s1", excerpt=excerpt, confidence=0.5
        )

    def test_verbatim_citation_survives_and_is_marked_verified(self):
        cites, status = verify_citations([self._cite()], [self._chunk()])
        assert status == "VERIFIED"
        assert cites[0].verified is True

    def test_invented_excerpt_is_stripped_and_flagged(self):
        cites, status = verify_citations(
            [self._cite(excerpt="the rebate is one crore")], [self._chunk()]
        )
        assert cites == []
        assert status == "FLAGGED"

    def test_citing_a_chunk_that_was_never_retrieved_is_stripped(self):
        # The signature of an invented source.
        cites, status = verify_citations([self._cite(chunk_id="ghost")], [self._chunk()])
        assert cites == []
        assert status == "FLAGGED"

    def test_partial_when_some_survive(self):
        cites, status = verify_citations(
            [self._cite(), self._cite(excerpt="not in the chunk at all")],
            [self._chunk()],
        )
        assert len(cites) == 1
        assert status == "PARTIAL"

    def test_no_citations_is_vacuously_verified(self):
        # A pure computation or a clarifying question asserts nothing needing a
        # source.
        assert verify_citations([], []) == ([], "VERIFIED")

    def test_rewrapped_whitespace_still_matches(self):
        # Chunk text carries PDF line breaks mid-sentence; a model quoting it
        # normalises them. Without whitespace collapsing, correct citations
        # would be stripped for cosmetic reasons and every answer would read as
        # FLAGGED.
        chunk = self._chunk(content="The standard\ndeduction   is\nallowed.")
        cites, status = verify_citations([self._cite()], [chunk])
        assert status == "VERIFIED"

    def test_case_insensitive(self):
        cites, status = verify_citations(
            [self._cite(excerpt="STANDARD DEDUCTION IS ALLOWED")], [self._chunk()]
        )
        assert status == "VERIFIED"

    def test_the_gate_cannot_detect_staleness(self):
        # Documents the gate's boundary rather than a behaviour to rely on: a
        # superseded figure that genuinely appears in the corpus passes, because
        # this checks provenance, not currency. Staleness is handled by never
        # letting the model emit figures at all.
        stale = self._chunk(content="Income below 7L attracts zero tax with rebate.")
        cites, status = verify_citations(
            [self._cite(excerpt="Income below 7L attracts zero tax")], [stale]
        )
        assert status == "VERIFIED"


class TestNarrationPrompt:
    def test_system_prompt_forbids_emitting_figures(self):
        system, _ = build_narration_messages("q", [])
        assert "NEVER state a monetary amount" in system

    def test_computed_figures_are_marked_authoritative(self):
        _, messages = build_narration_messages(
            "q", [], computation={"new_regime_tax": 214500}
        )
        body = messages[0].content
        assert "214500" in body
        assert "authoritative" in body

    def test_absent_computation_is_stated_not_hidden(self):
        _, messages = build_narration_messages("q", [])
        assert "no computation was run" in messages[0].content

    def test_chunks_are_labelled_with_their_ids_for_citation(self):
        _, messages = build_narration_messages(
            "q", [{"chunk_id": "abc123", "content": "text"}]
        )
        assert "chunk_id: abc123" in messages[0].content

    def test_assumptions_are_passed_through_for_the_model_to_state(self):
        _, messages = build_narration_messages(
            "q", [], assumptions=["No deductions were stated"]
        )
        assert "No deductions were stated" in messages[0].content


class TestParseNarration:
    def test_splits_answer_from_citations(self):
        answer, cites = parse_narration(
            'The deduction applies.\nCITATIONS:\n[{"chunk_id": "c1", "excerpt": "the deduction"}]'
        )
        assert answer == "The deduction applies."
        assert cites[0].chunk_id == "c1"

    def test_missing_block_yields_no_citations_rather_than_raising(self):
        answer, cites = parse_narration("Just prose, no citations block.")
        assert answer == "Just prose, no citations block."
        assert cites == []

    def test_malformed_json_degrades_instead_of_500ing(self):
        # A model formatting slip must cost sources, not the whole request.
        answer, cites = parse_narration("Prose.\nCITATIONS:\n[{broken json")
        assert answer == "Prose."
        assert cites == []

    def test_empty_citations_list(self):
        answer, cites = parse_narration("Prose.\nCITATIONS: []")
        assert cites == []

    def test_parsed_citations_are_never_pre_verified(self):
        # Only the Evidence Gate may set verified=True.
        _, cites = parse_narration(
            'X\nCITATIONS:\n[{"chunk_id": "c1", "excerpt": "e"}]'
        )
        assert cites[0].verified is False

    def test_entries_missing_required_fields_are_dropped(self):
        _, cites = parse_narration(
            'X\nCITATIONS:\n[{"chunk_id": "c1"}, {"excerpt": "e"}, '
            '{"chunk_id": "c2", "excerpt": "ok"}]'
        )
        assert [c.chunk_id for c in cites] == ["c2"]


class TestAssembleResponse:
    def _run(self, state):
        return asyncio.run(assemble_response(state))["final_response"]

    def test_computation_answer_names_the_regime_and_both_figures(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_trace": {
                    "outputs": {
                        "old_regime_tax": 444600,
                        "new_regime_tax": 214500,
                        "recommended_regime": "new",
                        "breakeven_deductions": 737498,
                        "deciding_factors": ["wider slabs win"],
                    }
                },
            }
        )
        assert "214,500" in out["answer"]
        assert "444,600" in out["answer"]
        assert "737,498" in out["answer"]

    def test_a_tie_is_reported_as_a_tie(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_trace": {
                    "outputs": {
                        "old_regime_tax": 0,
                        "new_regime_tax": 0,
                        "recommended_regime": "either",
                        "deciding_factors": [],
                    }
                },
            }
        )
        assert "identical under both regimes" in out["answer"]

    def test_uncited_sections_are_surfaced_not_hidden(self):
        # A computation is VERIFIED because its figures come from pure
        # functions, not because anything was cited. The reader must still be
        # able to see which claims currently lack a source.
        out = self._run(
            {"as_of": AS_OF, "uncited_sections": ["Sec 115BAC"], "gate_status": "VERIFIED"}
        )
        assert out["uncited_sections"] == ["Sec 115BAC"]
        assert out["gate_status"] == "VERIFIED"

    def test_clarification_becomes_the_answer(self):
        out = self._run({"as_of": AS_OF, "clarification": "Salary or business?"})
        assert out["answer"] == "Salary or business?"
        assert out["clarification_needed"] is True

    def test_llm_narrative_wins_over_the_computed_fallback(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "llm_response": {"answer": "narrated prose"},
                "computation_trace": {"outputs": {"old_regime_tax": 1}},
            }
        )
        assert out["answer"] == "narrated prose"


class TestNarrationDegradation:
    """A failing LLM must not discard an answer that is already computed."""

    def _run_narrate(self, monkeypatch, raises: Exception):
        from app.orchestration.graphs import query_graph

        async def boom(system_prompt, messages):
            raise raises

        monkeypatch.setattr(query_graph, "generate_narrative", boom)
        return asyncio.run(
            query_graph._narrate_node(
                {
                    "query": "my salary is 21 lakhs",
                    "retrieved_chunks": [],
                    "computation_trace": {"outputs": {"new_regime_tax": 214_500}},
                    "assumptions": [],
                }
            )
        )

    def test_llm_failure_does_not_raise(self, monkeypatch):
        # REGRESSION: a revoked API key returned a 500 and threw away a correct
        # computation. The LLM writes prose; it does not produce the figures.
        out = self._run_narrate(monkeypatch, RuntimeError("401 invalid api key"))
        assert out["llm_response"] is None

    def test_the_missing_explanation_is_disclosed(self, monkeypatch):
        # Degrading must not be silent -- otherwise a reader assumes there was
        # simply nothing to explain.
        out = self._run_narrate(monkeypatch, RuntimeError("boom"))
        assert any("could not be generated" in a for a in out["assumptions"])

    def test_prior_assumptions_survive_the_degradation(self, monkeypatch):
        from app.orchestration.graphs import query_graph

        async def boom(system_prompt, messages):
            raise RuntimeError("boom")

        monkeypatch.setattr(query_graph, "generate_narrative", boom)
        out = asyncio.run(
            query_graph._narrate_node(
                {
                    "query": "q",
                    "retrieved_chunks": [],
                    "computation_trace": None,
                    "assumptions": ["No deductions were read from your question"],
                }
            )
        )
        assert len(out["assumptions"]) == 2

    def test_assemble_still_produces_the_computed_answer(self):
        # The other half of the contract: with llm_response None, the response
        # is rendered from the trace rather than being empty.
        out = asyncio.run(
            assemble_response(
                {
                    "as_of": AS_OF,
                    "llm_response": None,
                    "computation_trace": {
                        "outputs": {
                            "old_regime_tax": 241_800,
                            "new_regime_tax": 214_500,
                            "recommended_regime": "new",
                            "deciding_factors": [],
                        }
                    },
                }
            )
        )["final_response"]
        assert "214,500" in out["answer"]


class TestConfidence:
    def test_no_retrieval_means_no_confidence(self):
        assert calculate_confidence([], tier=1, agreement=1.0) == 0.0

    def test_stays_within_bounds(self):
        assert 0.0 <= calculate_confidence([0.9], 1, 1.0) <= 1.0
        assert 0.0 <= calculate_confidence([0.01], 10, 0.0) <= 1.0

    def test_better_retrieval_scores_raise_confidence(self):
        low = calculate_confidence([0.35], tier=1, agreement=0.5)
        high = calculate_confidence([0.95], tier=1, agreement=0.5)
        assert high > low

    def test_corroboration_raises_confidence(self):
        alone = calculate_confidence([0.8], tier=1, agreement=0.0)
        corroborated = calculate_confidence([0.8], tier=1, agreement=1.0)
        assert corroborated > alone

    def test_authoritative_source_beats_commentary(self):
        assert calculate_confidence([0.8], tier=1, agreement=0.5) > calculate_confidence(
            [0.8], tier=10, agreement=0.5
        )

    def test_noise_level_scores_contribute_nothing(self):
        assert calculate_confidence([0.3], tier=10, agreement=0.0) == 0.0
