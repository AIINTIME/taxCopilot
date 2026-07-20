"""Tests for services.query.llm_query_understanding.

The core guarantee under test: routing (intent, rule_name) is trusted
directly from the LLM, but no number reaching the computation engine is ever
the LLM's own stated value -- it is always re-derived from a verified,
verbatim evidence span using the same deterministic parser input_extractor.py
already uses. generate_narrative is monkeypatched (no network, no
credentials), matching the asyncio.run(...) pattern test_analysis.py already
uses for this codebase's other async service functions -- there is no
pytest-asyncio dependency here.
"""

import asyncio
import json

import pytest

import app.services.query.llm_query_understanding as lqu
from app.services.computation.rules.personal.regime_comparison_personal import IncomeType
from app.services.query.intent_classifier_types import Intent
from app.services.query.llm_query_understanding import (
    QueryUnderstandingError,
    classify_and_extract,
)
from app.shared.llm.base import LLMResponse


def _fake_response(payload: dict) -> LLMResponse:
    return LLMResponse(
        text=json.dumps(payload),
        model_version="test",
        provider_name="test",
        latency_ms=0.0,
    )


def _patch_llm(monkeypatch, payload: dict | str):
    async def fake_generate_narrative(system_prompt, messages):
        if isinstance(payload, str):
            return LLMResponse(
                text=payload, model_version="test", provider_name="test", latency_ms=0.0
            )
        return _fake_response(payload)

    monkeypatch.setattr(lqu, "generate_narrative", fake_generate_narrative)


class TestNumbersAreReDerivedNeverTrusted:
    def test_verified_field_reparses_amount_from_evidence_span_ignoring_llm_value(
        self, monkeypatch
    ):
        # The LLM's own numeric `value` is deliberately wrong here (999999,
        # 1) -- the assertion is that the number actually used comes from
        # parse_amount() on the evidence_span, not from these fields.
        _patch_llm(
            monkeypatch,
            {
                "intent": "computation",
                "rule_name": "personal_regime_comparison",
                "fields": {
                    "gross_income": {"value": 999999, "evidence_span": "21 lakhs"},
                    "income_type": {"value": "salary", "evidence_span": "salary"},
                    "hra_exemption": {"value": 1, "evidence_span": "HRA of 4 lakhs"},
                },
            },
        )
        query = "my salary is 21 lakhs, I have HRA of 4 lakhs"

        result = asyncio.run(classify_and_extract(query))

        assert result.intent == Intent.COMPUTATION
        assert result.rule_name == "personal_regime_comparison"
        assert result.extracted is not None
        assert result.extracted.values["gross_income"] == 2_100_000
        assert result.extracted.deductions["hra_exemption"] == 400_000
        assert result.extracted.missing == ()

    def test_fabricated_evidence_span_is_dropped_not_trusted(self, monkeypatch):
        # evidence_span is not a substring of the query at all -- must be
        # treated as unverified, not silently accepted.
        _patch_llm(
            monkeypatch,
            {
                "intent": "computation",
                "rule_name": "personal_regime_comparison",
                "fields": {
                    "gross_income": {"value": 5_000_000, "evidence_span": "50 lakhs"},
                    "income_type": {"value": "salary", "evidence_span": "salary"},
                },
            },
        )
        query = "my salary is 21 lakhs"

        result = asyncio.run(classify_and_extract(query))

        assert "gross_income" in result.extracted.missing
        assert "gross_income" not in result.extracted.values

    def test_deduction_evidence_must_match_its_own_section_pattern(self, monkeypatch):
        # The span is a real substring, but it doesn't actually mention 80C --
        # a mislabeled field must not silently populate the wrong section.
        _patch_llm(
            monkeypatch,
            {
                "intent": "computation",
                "rule_name": "personal_regime_comparison",
                "fields": {
                    "gross_income": {"value": 2_100_000, "evidence_span": "21 lakhs"},
                    "income_type": {"value": "salary", "evidence_span": "salary"},
                    "section_80c": {"value": 400_000, "evidence_span": "HRA of 4 lakhs"},
                },
            },
        )
        query = "my salary is 21 lakhs, I have HRA of 4 lakhs"

        result = asyncio.run(classify_and_extract(query))

        assert "section_80c" not in result.extracted.deductions

    def test_income_type_is_reverified_against_evidence_span_markers(self, monkeypatch):
        # The LLM claims "salary", but the cited span only supports
        # "business" by the existing marker list -- the re-derived type must
        # win, not the LLM's assertion.
        _patch_llm(
            monkeypatch,
            {
                "intent": "computation",
                "rule_name": "personal_regime_comparison",
                "fields": {
                    "gross_income": {"value": 1_500_000, "evidence_span": "15 lakhs"},
                    "income_type": {"value": "salary", "evidence_span": "freelance work"},
                },
            },
        )
        query = "I earn 15 lakhs from freelance work"

        result = asyncio.run(classify_and_extract(query))

        assert result.extracted.income_type == IncomeType.BUSINESS


class TestRoutingIsTakenDirectlyFromTheLLM:
    def test_retrieval_query_has_no_extraction(self, monkeypatch):
        _patch_llm(
            monkeypatch,
            {"intent": "retrieval", "rule_name": None, "fields": {}},
        )

        result = asyncio.run(classify_and_extract("What is Section 115BAA?"))

        assert result.intent == Intent.RETRIEVAL
        assert result.rule_name is None
        assert result.extracted is None

    def test_computation_rule_other_than_personal_has_no_extraction(self, monkeypatch):
        # Free-text extraction only exists for personal_regime_comparison
        # today -- other rules still require an explicit computation_request.
        _patch_llm(
            monkeypatch,
            {
                "intent": "computation",
                "rule_name": "mat",
                "fields": {"gross_income": {"value": 1, "evidence_span": "book profit"}},
            },
        )

        result = asyncio.run(classify_and_extract("Calculate our MAT liability"))

        assert result.rule_name == "mat"
        assert result.extracted is None


class TestMarkdownFencedResponsesAreStillParsed:
    def test_json_wrapped_in_markdown_fence_is_parsed_not_rejected(self, monkeypatch):
        # Observed in practice: the model wraps its JSON in a ```json ... ```
        # block despite the prompt asking for raw JSON. This must not be
        # treated as a malformed response.
        async def fake_generate_narrative(system_prompt, messages):
            return LLMResponse(
                text='```json\n{"intent": "retrieval", "rule_name": null, "fields": {}}\n```',
                model_version="test",
                provider_name="test",
                latency_ms=0.0,
            )

        monkeypatch.setattr(lqu, "generate_narrative", fake_generate_narrative)

        result = asyncio.run(classify_and_extract("What is the rebate limit under Section 87A?"))

        assert result.intent == Intent.RETRIEVAL
        assert result.rule_name is None


class TestUntrustedResponsesRaiseForCallerFallback:
    def test_malformed_json_raises(self, monkeypatch):
        _patch_llm(monkeypatch, "not json at all")

        with pytest.raises(QueryUnderstandingError):
            asyncio.run(classify_and_extract("some query"))

    def test_unknown_intent_raises(self, monkeypatch):
        _patch_llm(monkeypatch, {"intent": "bogus", "rule_name": None, "fields": {}})

        with pytest.raises(QueryUnderstandingError):
            asyncio.run(classify_and_extract("some query"))

    def test_unknown_rule_name_raises(self, monkeypatch):
        _patch_llm(
            monkeypatch,
            {"intent": "computation", "rule_name": "not_a_real_rule", "fields": {}},
        )

        with pytest.raises(QueryUnderstandingError):
            asyncio.run(classify_and_extract("some query"))
