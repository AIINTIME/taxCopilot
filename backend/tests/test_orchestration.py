"""Orchestration layer tests.

Everything here is pure or substituted -- no DB, no Pinecone, no LLM. The
graph's own wiring is exercised end-to-end in the integration run; these cover
the decision logic that would otherwise only fail in production.

Ported onto the dev_parna designs after the merge (6ed4d0b). Three contracts
changed, and the tests below assert the NEW ones:

  * `verify_citations` returns EVERY citation tagged `verified=True/False`
    rather than dropping the failures, and `strip_unverified_claims` removes
    the claims from the prose. No citations at all is FLAGGED, not vacuously
    verified -- an ungrounded narrative asserts something and cites nothing.
  * `assemble_response` reads `computation_result` (`{"status", "trace"}`),
    not a bare `computation_trace`.
  * Intent is classified by embedding k-NN (`intent_classifier`, async), so the
    old sync keyword-classifier tests are gone. `rate_lookup` detection stays
    deterministic and is covered in test_personal_tax.py.
"""

import asyncio
from datetime import date

from app.orchestration.nodes.assemble_response import assemble_response
from app.services.rag.evidence_gate import (
    INSUFFICIENT_SOURCES_MESSAGE,
    extract_citations,
    strip_unverified_claims,
    verify_citations,
)
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


def _computed(outputs: dict, rule_name: str = "personal_regime_comparison") -> dict:
    """A successful computation_result, in the post-merge shape."""
    return {"status": "computed", "trace": {"rule_name": rule_name, "outputs": outputs}}


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

    def test_invented_excerpt_is_tagged_unverified_and_flagged(self):
        # Kept, not dropped: the gate reports what the model claimed alongside
        # the verdict, so a reviewer can see the invention rather than only its
        # absence. strip_unverified_claims is what keeps it out of the prose.
        cites, status = verify_citations(
            [self._cite(excerpt="the rebate is one crore")], [self._chunk()]
        )
        assert status == "FLAGGED"
        assert cites[0].verified is False

    def test_citing_a_chunk_that_was_never_retrieved_is_unverified(self):
        # The signature of an invented source.
        cites, status = verify_citations([self._cite(chunk_id="ghost")], [self._chunk()])
        assert status == "FLAGGED"
        assert cites[0].verified is False

    def test_partial_when_some_verify_and_some_do_not(self):
        cites, status = verify_citations(
            [self._cite(), self._cite(excerpt="not in the chunk at all")],
            [self._chunk()],
        )
        assert status == "PARTIAL"
        assert [c.verified for c in cites] == [True, False]

    def test_no_citations_is_flagged(self):
        # An answer that asserts something and cites nothing is ungrounded, so
        # it is flagged rather than passed. (A computation with no citations is
        # a different path: it never reaches the gate at all.)
        assert verify_citations([], []) == ([], "FLAGGED")

    def test_rewrapped_whitespace_still_matches(self):
        # Chunk text carries PDF line breaks mid-sentence; a model quoting it
        # normalises them. Without whitespace collapsing, correct citations
        # would be marked unverified for cosmetic reasons and every answer
        # would read as FLAGGED.
        chunk = self._chunk(content="The standard\ndeduction   is\nallowed.")
        _, status = verify_citations([self._cite()], [chunk])
        assert status == "VERIFIED"

    def test_case_insensitive(self):
        _, status = verify_citations(
            [self._cite(excerpt="STANDARD DEDUCTION IS ALLOWED")], [self._chunk()]
        )
        assert status == "VERIFIED"

    def test_the_gate_cannot_detect_staleness(self):
        # Documents the gate's boundary rather than a behaviour to rely on: a
        # superseded figure that genuinely appears in the corpus passes, because
        # this checks provenance, not currency. Staleness is handled by never
        # letting the model emit figures at all.
        stale = self._chunk(content="Income below 7L attracts zero tax with rebate.")
        _, status = verify_citations(
            [self._cite(excerpt="Income below 7L attracts zero tax")], [stale]
        )
        assert status == "VERIFIED"

    def test_unverified_claims_are_stripped_from_the_prose(self):
        # The other half of the tagging contract, exercised through the real
        # chain (extract -> verify -> strip) rather than a hand-built Citation:
        # the excerpt is sliced verbatim out of the narrative by
        # extract_citations, so constructing one by hand can silently test a
        # shape the pipeline never produces.
        text = "The rebate is Rs 1,00,00,000 [1]."
        chunk = self._chunk(content="The rebate is Rs 60,000 under Sec 87A.")

        cites, status = verify_citations(extract_citations(text, [chunk]), [chunk])

        assert status == "FLAGGED"
        assert cites[0].verified is False
        stripped = strip_unverified_claims(text, cites)
        assert "1,00,00,000" not in stripped
        assert INSUFFICIENT_SOURCES_MESSAGE in stripped

    def test_a_verified_claim_is_left_in_the_prose(self):
        text = "The rebate is Rs 60,000 [1]."
        chunk = self._chunk(content="The rebate is Rs 60,000 under Sec 87A.")

        cites, status = verify_citations(extract_citations(text, [chunk]), [chunk])

        assert status == "VERIFIED"
        assert strip_unverified_claims(text, cites) == text


class TestAssembleResponse:
    def _run(self, state):
        return asyncio.run(assemble_response(state))["final_response"]

    def test_computation_answer_names_the_regime_and_both_figures(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_result": _computed(
                    {
                        "old_regime_tax": 444600,
                        "new_regime_tax": 214500,
                        "recommended_regime": "new",
                        "breakeven_deductions": 737498,
                        "deciding_factors": ["wider slabs win"],
                    }
                ),
            }
        )
        assert "214,500" in out["answer"]
        assert "444,600" in out["answer"]
        assert "737,498" in out["answer"]

    def test_a_tie_is_reported_as_a_tie(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_result": _computed(
                    {
                        "old_regime_tax": 0,
                        "new_regime_tax": 0,
                        "recommended_regime": "either",
                        "deciding_factors": [],
                    }
                ),
            }
        )
        assert "identical under both regimes" in out["answer"]

    def test_uncited_sections_are_surfaced_not_hidden(self):
        # A computation is VERIFIED because its figures come from pure
        # functions, not because anything was cited. The reader must still be
        # able to see which claims currently lack a source.
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_result": _computed({"new_regime_tax": 214500}),
                "uncited_sections": ["Sec 115BAC"],
            }
        )
        assert out["uncited_sections"] == ["Sec 115BAC"]
        assert out["gate_status"] == "VERIFIED"

    def test_clarification_becomes_the_answer(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_result": {
                    "status": "missing_data",
                    "clarification": "Salary or business?",
                },
            }
        )
        assert out["answer"] == "Salary or business?"
        assert out["clarification_needed"] is True

    def test_missing_fields_are_named_rather_than_assumed(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "computation_result": {
                    "status": "missing_data",
                    "rule_name": "personal_regime_comparison",
                    "missing_fields": ["gross_income"],
                },
            }
        )
        assert "gross_income" in out["answer"]
        assert out["clarification_needed"] is False

    def test_llm_narrative_is_used_when_there_is_no_computation(self):
        out = self._run(
            {"as_of": AS_OF, "llm_response": {"text": "narrated prose"}}
        )
        assert out["answer"] == "narrated prose"

    def test_a_computation_is_never_overwritten_by_narration(self):
        # The division of labour: the engine supplies every number, the LLM only
        # explains. Where both ran, the computed answer is what is returned.
        out = self._run(
            {
                "as_of": AS_OF,
                "llm_response": {"text": "narrated prose"},
                "computation_result": _computed(
                    {
                        "old_regime_tax": 444600,
                        "new_regime_tax": 214500,
                        "recommended_regime": "new",
                        "deciding_factors": [],
                    }
                ),
            }
        )
        assert "214,500" in out["answer"]
        assert out["answer"] != "narrated prose"


class TestRateLookupResponse:
    """A rate/deduction lookup is answered from slab_tables, never the LLM."""

    def _run(self, state):
        return asyncio.run(assemble_response(state))["final_response"]

    def test_rate_card_is_verified_without_citations(self):
        # Same justification as a computation: the figures come from versioned
        # rate tables via pure functions and never pass through an LLM, so there
        # is nothing hallucinated for the gate to catch.
        out = self._run(
            {
                "as_of": AS_OF,
                "rate_card": {
                    "assessment_year": "2026-27",
                    "available": True,
                    "regimes": [
                        {
                            "regime": "new",
                            "slab_section": "Sec 115BAC",
                            "bands": [{"range": "0 to 400,000", "rate": "0%"}],
                            "standard_deduction": 75000,
                            "rebate_87a_income_limit": 1200000,
                            "rebate_87a_max": 60000,
                            "cess_rate": 0.04,
                            "source_reference": "incometax.gov.in",
                        }
                    ],
                },
            }
        )
        assert out["gate_status"] == "VERIFIED"
        assert out["citations"] == []
        assert "0 to 400,000" in out["answer"]
        assert "incometax.gov.in" in out["answer"]

    def test_an_unseeded_year_is_refused_not_guessed(self):
        # The RatesNotSeededError contract at the response layer. A rate that is
        # quietly a year out is worse than a refusal: it looks right.
        out = self._run(
            {
                "as_of": AS_OF,
                "rate_card": {
                    "assessment_year": "2031-32",
                    "available": False,
                    "regimes": [],
                },
            }
        )
        assert "not available" in out["answer"]
        assert "2031-32" in out["answer"]

    def test_deduction_card_lists_the_limit_and_its_source(self):
        out = self._run(
            {
                "as_of": AS_OF,
                "deduction_card": {
                    "assessment_year": "2026-27",
                    "available": True,
                    "entries": [
                        {
                            "item": "Sec 80D",
                            "limit": "25,000 (self/family)",
                            "note": "Up to 50,000 additional for senior-citizen parents.",
                            "source_reference": "incometax.gov.in",
                        }
                    ],
                },
            }
        )
        assert out["gate_status"] == "VERIFIED"
        assert "Sec 80D" in out["answer"]
        assert "50,000" in out["answer"]
        assert "incometax.gov.in" in out["answer"]


class TestRuleInference:
    """Which rule a query is asking for, guessed from its text.

    None is a useful answer here -- it routes to a real RAG search. A WRONG
    guess is far worse than no guess, because a named rule is treated as
    authoritative and dead-ends on its own missing inputs.
    """

    def _infer(self, query: str):
        from app.orchestration.graphs.query_graph import _infer_rule_name

        return _infer_rule_name(query)

    def test_a_regime_law_question_is_not_a_corporate_computation(self):
        # REGRESSION (live UI): this pure law question -- no income, no company --
        # matched the bare word "regime", was answered by the CORPORATE
        # 115BAA/115BAB rule, and dead-ended asking the user for `total_income`
        # and `is_new_manufacturing_company`. It must reach retrieval instead.
        assert self._infer(
            "Under the Old Tax Regime, what deduction can a taxpayer claim under "
            "Section 80D for medical insurance premiums, and does this deduction "
            "survive under the New Regime?"
        ) is None

    def test_the_word_regime_alone_is_not_a_corporate_cue(self):
        assert self._infer("Which regime should I choose?") is None

    def test_a_company_asking_about_regimes_still_gets_the_corporate_rule(self):
        # The other side of the guard: it must not break the rule it protects.
        assert self._infer(
            "Which regime should a domestic company with turnover of 300 crore choose?"
        ) == "regime_comparison"

    def test_an_explicit_corporate_section_is_a_cue_on_its_own(self):
        assert self._infer("Should we opt for 115BAA?") == "regime_comparison"

    def test_a_stated_personal_income_is_decisive_for_the_personal_rule(self):
        assert self._infer(
            "My salary is 21 lakhs, which regime should I choose?"
        ) == "personal_regime_comparison"

    def test_other_rules_keep_their_own_keywords(self):
        assert self._infer("How is MAT computed under 115JB?") == "mat"
        assert self._infer("What is indexation for LTCG?") == "capital_gains"


class TestInferredRuleFallsBackRatherThanDeadEnding:
    """A rule guessed from the query text, whose inputs the query never carried,
    is evidence the guess was wrong -- not that the user withheld data."""

    def _run(self, state):
        from app.orchestration.graphs.query_graph import (
            _computation_node,
            _route_after_computation,
        )

        out = asyncio.run(_computation_node({"as_of": AS_OF, **state}))
        return out, _route_after_computation({**state, **out})

    def test_an_inferred_rule_with_absent_inputs_routes_to_retrieval(self):
        out, route = self._run(
            {
                "query": "Which regime should a domestic company with turnover of 300 crore choose?",
                "computation_request": None,
            }
        )
        # rule_name omitted is the signal _route_after_computation reads.
        assert "rule_name" not in out["computation_result"]
        assert route == "computation_fallback"

    def test_an_explicit_request_with_missing_fields_still_asks_the_user(self):
        # The genuine case: the caller named the rule, so missing fields really
        # are numbers only the user has. This must NOT degrade to a search.
        out, route = self._run(
            {
                "query": "compute it",
                "computation_request": {"rule_name": "mat", "inputs": {}},
            }
        )
        assert out["computation_result"]["rule_name"] == "mat"
        assert route == "assemble_response"


class TestMissingDataIsNotAFailedVerification:
    def test_a_request_for_input_is_not_flagged_for_review(self):
        # REGRESSION (live UI): the missing_data branch hardcoded FLAGGED, which
        # the client renders as "Review required / 30% confidence / citations
        # could not be verified and were removed". No citation was offered,
        # nothing was retrieved, and the gate never ran -- it dressed a dead end
        # up as a failed verification.
        out = asyncio.run(
            assemble_response(
                {
                    "as_of": AS_OF,
                    "computation_result": {
                        "status": "missing_data",
                        "rule_name": "mat",
                        "missing_fields": ["book_profit"],
                    },
                }
            )
        )["final_response"]
        assert out["gate_status"] == "VERIFIED"
        assert out["citations"] == []
        assert "book_profit" in out["answer"]


class TestNarrationDegradation:
    """A failing LLM must not discard an answer that is already computed."""

    def _run_narrate(self, monkeypatch, raises: Exception, state_extra: dict | None = None):
        from app.orchestration.graphs import query_graph

        async def boom(system_prompt, messages):
            raise raises

        monkeypatch.setattr(query_graph, "generate_narrative", boom)
        return asyncio.run(
            query_graph._narrate_node(
                {
                    "query": "my salary is 21 lakhs",
                    "retrieved_chunks": [],
                    "assumptions": [],
                    **(state_extra or {}),
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
        out = self._run_narrate(
            monkeypatch,
            RuntimeError("boom"),
            {"assumptions": ["No deductions were read from your question"]},
        )
        assert len(out["assumptions"]) == 2

    def test_the_gate_preserves_the_degraded_state(self):
        # The gate must not rebuild llm_response as {"text": ""}: that would
        # overwrite the None telling assemble_response to fall back to the
        # computed figures, turning a survivable outage into a blank answer.
        from app.orchestration.graphs import query_graph

        out = asyncio.run(
            query_graph._evidence_gate_node(
                {"llm_response": None, "retrieved_chunks": []}
            )
        )
        assert "llm_response" not in out
        assert out["gated_citations"] == []

    def test_assemble_still_produces_the_computed_answer(self):
        # The other half of the contract: with llm_response None, the response
        # is rendered from the trace rather than being empty.
        out = asyncio.run(
            assemble_response(
                {
                    "as_of": AS_OF,
                    "llm_response": None,
                    "computation_result": _computed(
                        {
                            "old_regime_tax": 241_800,
                            "new_regime_tax": 214_500,
                            "recommended_regime": "new",
                            "deciding_factors": [],
                        }
                    ),
                }
            )
        )["final_response"]
        assert "214,500" in out["answer"]

    def test_retrieval_with_no_computation_says_so_rather_than_returning_blank(self):
        # Nothing to fall back on here, so the degradation must be stated: an
        # empty answer reads as "no comment", not "the call failed".
        out = asyncio.run(
            assemble_response({"as_of": AS_OF, "llm_response": None})
        )["final_response"]
        assert "could not be generated" in out["answer"]
