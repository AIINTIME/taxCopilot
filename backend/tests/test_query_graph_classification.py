"""Node-level tests for query_graph.py's LLM-only classification.

The LLM is the sole intent classifier -- there is no regex/embedding
fallback. Scoped to _classify_intent_node and _computation_node directly
rather than the full compiled graph: running the whole graph needs a live
Postgres (audit_log_node, via Prisma), Neo4j and Pinecone (ground_truth_check/
retrieval), none of which this change touches or this codebase currently has
a test harness for. asyncio.run(...) is used the same way test_analysis.py
already does for this codebase's other async service functions -- there is
no pytest-asyncio dependency here.
"""

import asyncio
from datetime import date

import pytest

from app.orchestration.graphs import query_graph as qg
from app.services.computation.engine import compute
from app.services.computation.rules.personal.regime_comparison_personal import IncomeType
from app.services.query.input_extractor import ExtractedInputs
from app.services.query.intent_classifier_types import Intent
from app.services.query.llm_query_understanding import QueryUnderstanding, QueryUnderstandingError
from app.shared.schemas.tax_year import AssessmentYear, CapitalGainsPeriod, TaxActRegime, TaxYearContext

AY_2026_27 = TaxYearContext(
    as_of_date=date(2026, 3, 31),
    assessment_year=AssessmentYear(ay="2026-27", financial_year="2025-26"),
    regime=TaxActRegime.ACT_1961,
    capital_gains_period=CapitalGainsPeriod.POST_RATE_CHANGE,
)


class TestClassifyIntentNodeIsLLMOnly:
    def test_uses_llm_result_including_extraction_when_it_succeeds(self, monkeypatch):
        extracted = ExtractedInputs(
            values={"gross_income": 2_100_000.0},
            income_type=IncomeType.SALARY,
            deductions={"hra_exemption": 400_000.0},
            assumptions=("some assumption",),
            missing=(),
            provenance={},
        )
        understanding = QueryUnderstanding(
            intent=Intent.COMPUTATION,
            rule_name="personal_regime_comparison",
            extracted=extracted,
        )

        async def fake_classify_and_extract(query):
            return understanding

        monkeypatch.setattr(qg, "classify_and_extract", fake_classify_and_extract)

        result = asyncio.run(qg._classify_intent_node({"query": "my salary is 21 lakhs"}))

        assert result["intent"] == Intent.COMPUTATION
        assert result["rule_name"] == "personal_regime_comparison"
        assert result["parsed_query_inputs"] == extracted.to_rule_inputs()
        assert result["parsed_query_missing_fields"] == []
        assert result["assumptions"] == ["some assumption"]

    def test_raises_query_understanding_error_when_llm_call_fails_no_fallback(self, monkeypatch):
        async def fake_classify_and_extract(query):
            raise RuntimeError("simulated LLM outage")

        monkeypatch.setattr(qg, "classify_and_extract", fake_classify_and_extract)

        # No deterministic classifier to fall back to -- the failure must
        # propagate as a real error, not be swallowed into a guessed intent.
        with pytest.raises(QueryUnderstandingError):
            asyncio.run(qg._classify_intent_node({"query": "What is Section 115BAA?"}))


class TestComputationNodeTrustsClassifyIntentNodeUnconditionally:
    def test_uses_state_supplied_rule_name_and_parsed_inputs(self):
        query = "please size up what I owe"
        parsed_inputs = {
            "gross_income": 5_000_000.0,
            "income_type": IncomeType.BUSINESS,
            "deductions": {},
        }
        state = {
            "query": query,
            "as_of": AY_2026_27,
            "rule_name": "personal_regime_comparison",
            "parsed_query_inputs": parsed_inputs,
            "parsed_query_missing_fields": [],
            "assumptions": [],
        }

        result = asyncio.run(qg._computation_node(state))

        assert result["computation_result"]["status"] == "computed"
        expected_trace = compute("personal_regime_comparison", parsed_inputs, AY_2026_27)
        assert result["computation_result"]["trace"]["outputs"] == expected_trace.model_dump(
            mode="json"
        )["outputs"]

    def test_reports_missing_data_when_state_supplied_extraction_is_incomplete(self):
        state = {
            "query": "please size up what I owe",
            "as_of": AY_2026_27,
            "rule_name": "personal_regime_comparison",
            "parsed_query_inputs": {},
            "parsed_query_missing_fields": ["gross_income", "income_type"],
            "assumptions": [],
        }

        result = asyncio.run(qg._computation_node(state))

        assert result["computation_result"]["status"] == "missing_data"
        assert result["computation_result"]["missing_fields"] == ["gross_income", "income_type"]

    def test_reports_missing_data_when_llm_could_not_identify_a_rule(self):
        state = {
            "query": "hello there",
            "as_of": AY_2026_27,
            "rule_name": None,
        }

        result = asyncio.run(qg._computation_node(state))

        assert result["computation_result"]["status"] == "missing_data"

    def test_requires_rule_name_to_already_be_in_state_no_regex_fallback(self):
        # There is no _infer_rule_name to fall back to anymore -- the graph
        # can only reach _computation_node after classify_intent's LLM call
        # succeeded and populated rule_name, so its absence is a programming
        # error, not a case to silently handle.
        state = {"query": "my salary is 21 lakhs", "as_of": AY_2026_27}

        with pytest.raises(KeyError):
            asyncio.run(qg._computation_node(state))
