"""Scope guard: refusing questions this system cannot honestly source.

The declines matter less than the FALSE POSITIVES. A missed decline yields a
bad answer to a question that was out of scope anyway; a wrongly-fired decline
refuses a question the system can genuinely answer, and the user has no way to
tell it is wrong. Each decline test below is paired with the in-scope question
it must not swallow.
"""

import asyncio
from datetime import date

import pytest

from app.orchestration.nodes.assemble_response import assemble_response
from app.services.query.scope_guard import DeclineReason, check_scope
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


def _reason(query: str):
    decline = check_scope(query)
    return decline.reason if decline else None


class TestOutOfDomain:
    @pytest.mark.parametrize(
        "query",
        [
            "Can you tell me the GST rate applicable on sale of a residential flat?",
            "What is the customs duty on imported machinery?",
            "How do I file GSTR-1?",
            "What is the excise duty on tobacco?",
            "What is the stamp duty on a sale deed in Maharashtra?",
        ],
    )
    def test_indirect_taxes_are_declined(self, query):
        assert _reason(query) is DeclineReason.OUT_OF_DOMAIN

    @pytest.mark.parametrize(
        "query",
        [
            # Mentioning an indirect tax is not asking about one. Each of these
            # is a direct-tax question and must reach the pipeline.
            "Is the GST I paid on business expenses deductible under income tax?",
            "Is stamp duty paid on a house purchase allowed as a deduction under 80C?",
            "Does customs duty paid form part of the cost of acquisition for capital gains?",
        ],
    )
    def test_a_direct_tax_question_may_mention_an_indirect_tax(self, query):
        assert _reason(query) is None

    def test_the_decline_names_the_subject_and_the_reason(self):
        answer = check_scope("What is the GST rate on a flat?").answer
        assert "GST" in answer
        # It must say WHY, or the user just rephrases and tries again.
        assert "indirect" in answer.lower() or "no source" in answer.lower()


class TestRecencyIsUnverifiable:
    @pytest.mark.parametrize(
        "query",
        [
            "What is the exact TDS threshold under Section 194A as amended by a "
            "notification issued this week?",
            "What did the latest circular change?",
            "Was there an amendment notified last week?",
            "What does today's notification say?",
        ],
    )
    def test_questions_predicated_on_recency_are_declined(self, query):
        assert _reason(query) is DeclineReason.RECENCY_UNVERIFIABLE

    @pytest.mark.parametrize(
        "query",
        [
            # A time cue with no instrument is an ordinary question. The first
            # one is the headline computation -- it carries "this year" and must
            # compute, not decline.
            "How much income tax will I personally owe this year if my salary is 18 lakh?",
            "What are the slab rates for this year?",
            "How much tax did I pay last month?",
        ],
    )
    def test_an_ordinary_time_reference_is_not_a_recency_question(self, query):
        assert _reason(query) is None

    def test_the_decline_admits_there_is_no_recency_tracking(self):
        answer = check_scope("What did the notification issued this week change?").answer
        assert "no recency tracking" in answer.lower()
        # Honest about the limit rather than implying the notification does not
        # exist: we cannot tell either way.
        assert "no issue date" in answer.lower() or "carry no issue date" in answer.lower()


class TestCrossActComparison:
    @pytest.mark.parametrize(
        "query",
        [
            "Has the section number or substantive content of the standard deduction "
            "for salaried individuals changed between IT Act 1961 and IT Act 2025?",
            "What does the Income Tax Act 2025 say about the standard deduction?",
            "What does the new income tax act change?",
            "Is section 80C the same in the 2025 Act?",
        ],
    )
    def test_2025_act_questions_are_declined(self, query):
        assert _reason(query) is DeclineReason.CROSS_ACT_COMPARISON

    @pytest.mark.parametrize(
        "query",
        [
            # "2025-26" is an assessment/financial YEAR, not the 2025 Act. These
            # are the most common questions the system answers; declining them
            # would break the rate-lookup path outright.
            "What are the income tax slab rates for the new regime for AY 2025-26?",
            "What are the slab rates for FY 2025-26?",
            "What is the 80C limit for AY 2025-26?",
        ],
    )
    def test_the_assessment_year_2025_26_is_not_the_2025_act(self, query):
        assert _reason(query) is None

    def test_the_decline_explains_that_2025_act_text_is_not_indexed(self):
        answer = check_scope("What changed between IT Act 1961 and IT Act 2025?").answer
        assert "2025" in answer
        assert "ingested" in answer.lower() or "indexed" in answer.lower()


class TestEmptyQuery:
    @pytest.mark.parametrize("query", ["", "   ", "\n"])
    def test_an_empty_query_is_not_declined(self, query):
        # Nothing to judge. The document-upload path sends an empty query.
        assert check_scope(query) is None


class TestDeclineResponse:
    def test_a_decline_is_verified_with_no_citations(self):
        # It asserts no tax fact, so there is nothing to verify and nothing to
        # flag. FLAGGED would render "Review required / citations could not be
        # verified" against a sentence that declines to answer.
        out = asyncio.run(
            assemble_response(
                {
                    "as_of": AS_OF,
                    "scope_decline": {
                        "reason": "out_of_domain",
                        "answer": "That question is about GST, which is outside scope.",
                    },
                }
            )
        )["final_response"]
        assert out["gate_status"] == "VERIFIED"
        assert out["citations"] == []
        assert out["clarification_needed"] is False
        assert "GST" in out["answer"]


class TestScopeRouting:
    def _route(self, query: str) -> str:
        from app.orchestration.graphs.query_graph import _route_after_temporal
        from app.services.query.intent_classifier_types import Intent

        return _route_after_temporal(
            {"query": query, "intent": Intent.RETRIEVAL, "computation_request": None}
        )

    def test_an_out_of_scope_question_never_reaches_retrieval(self):
        # The point of the guard. Retrieval has no score floor, so this query
        # would otherwise be handed ten direct-tax chunks as context and the
        # evidence gate could not tell that they do not address the question.
        assert self._route("What is the GST rate on a flat?") == "scoped_decline"

    def test_an_in_scope_question_still_routes_normally(self):
        assert self._route("Can I claim HRA and 24(b) together?") == "retrieval"
