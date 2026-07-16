"""ITR analysis tests (Phase 5).

Pure throughout -- reconciler, ai_score and itr_extractor take no I/O, so this
runs with no credentials. penalty_mapper's Neo4j path is covered by
substitution; its live behaviour is untestable while Aura is paused and the
graph holds no PenaltyRule nodes.
"""

import asyncio
from datetime import date

import pytest

from app.services.analysis.ai_score import Grade, score_return
from app.services.analysis.itr_extractor import extract_from_text
from app.services.analysis.penalty_mapper import penalties_for
from app.services.analysis.reconciler import (
    DiscrepancyType,
    FiledReturn,
    Severity,
    reconcile,
)
from app.services.computation.rules.personal.deductions import DeductionInputs
from app.services.computation.rules.personal.regime_comparison_personal import (
    IncomeType,
    RegimeRecommendation,
)
from app.services.computation.rules.personal.slab_tables import PersonalRegime
from app.shared.schemas.tax_year import (
    AssessmentYear,
    CapitalGainsPeriod,
    TaxActRegime,
    TaxYearContext,
)

AY_2026_27 = TaxYearContext(
    as_of_date=date(2026, 3, 31),
    assessment_year=AssessmentYear(ay="2026-27", financial_year="2025-26"),
    regime=TaxActRegime.ACT_1961,
    capital_gains_period=CapitalGainsPeriod.POST_RATE_CHANGE,
)


def filed(**kwargs) -> FiledReturn:
    base = dict(
        gross_income=2_100_000,
        income_type=IncomeType.SALARY,
        regime_filed=PersonalRegime.OLD,
    )
    base.update(kwargs)
    return FiledReturn(**base)


class TestExcessDeductionDetection:
    """Plan verification step 6: an 80C over-claim of 2L against the 1.5L cap."""

    def test_over_claimed_80c_is_caught(self):
        result = reconcile(
            filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27
        )
        excess = [
            d for d in result.discrepancies if d.type is DiscrepancyType.EXCESS_DEDUCTION
        ]
        assert len(excess) == 1
        assert excess[0].section_reference == "Sec 80C"
        assert excess[0].declared == 200_000
        assert excess[0].correct == 150_000
        assert excess[0].severity is Severity.HIGH

    def test_the_summary_quantifies_the_excess(self):
        result = reconcile(
            filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27
        )
        assert "50,000" in result.discrepancies[0].summary

    def test_a_claim_at_the_cap_is_clean(self):
        result = reconcile(
            filed(deductions=DeductionInputs(section_80c=150_000)), AY_2026_27
        )
        assert not [
            d for d in result.discrepancies if d.type is DiscrepancyType.EXCESS_DEDUCTION
        ]

    def test_the_excess_does_not_reduce_the_recomputed_tax(self):
        # The point of recomputing: the disallowed 50k must not shelter income.
        over = reconcile(filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27)
        at_cap = reconcile(filed(deductions=DeductionInputs(section_80c=150_000)), AY_2026_27)
        assert over.computed_tax == at_cap.computed_tax


class TestDisallowedDeduction:
    def test_claiming_80c_under_the_new_regime_is_flagged(self):
        result = reconcile(
            filed(
                regime_filed=PersonalRegime.NEW,
                deductions=DeductionInputs(section_80c=150_000),
            ),
            AY_2026_27,
        )
        disallowed = [
            d
            for d in result.discrepancies
            if d.type is DiscrepancyType.DISALLOWED_DEDUCTION
        ]
        assert disallowed
        assert disallowed[0].section_reference == "Sec 80C"
        assert disallowed[0].correct == 0.0

    def test_employer_nps_survives_the_new_regime(self):
        result = reconcile(
            filed(
                regime_filed=PersonalRegime.NEW,
                deductions=DeductionInputs(employer_nps_80ccd2=50_000),
            ),
            AY_2026_27,
        )
        assert not [
            d
            for d in result.discrepancies
            if d.type is DiscrepancyType.DISALLOWED_DEDUCTION
        ]


class TestTaxMismatch:
    def test_understated_tax_is_caught_and_costed(self):
        result = reconcile(
            filed(regime_filed=PersonalRegime.NEW, declared_tax=100_000), AY_2026_27
        )
        mismatch = [
            d for d in result.discrepancies if d.type is DiscrepancyType.TAX_MISMATCH
        ]
        assert mismatch
        # Computed is 214,500; declared 100,000 -> 114,500 underpaid.
        assert mismatch[0].cost == pytest.approx(114_500)
        assert "under-stated" in mismatch[0].summary

    def test_correct_tax_raises_nothing(self):
        result = reconcile(
            filed(regime_filed=PersonalRegime.NEW, declared_tax=214_500), AY_2026_27
        )
        assert not [
            d for d in result.discrepancies if d.type is DiscrepancyType.TAX_MISMATCH
        ]

    def test_rounding_noise_is_not_an_error(self):
        # Returns are filed in whole rupees and preparers round differently;
        # flagging a 3-rupee gap would bury the real findings.
        result = reconcile(
            filed(regime_filed=PersonalRegime.NEW, declared_tax=214_503), AY_2026_27
        )
        assert not [
            d for d in result.discrepancies if d.type is DiscrepancyType.TAX_MISMATCH
        ]


class TestSuboptimalRegime:
    """'Which regime would have been better, and why' — answered with a number."""

    def test_filing_old_with_no_deductions_is_flagged_as_costly(self):
        result = reconcile(filed(regime_filed=PersonalRegime.OLD), AY_2026_27)
        sub = [
            d
            for d in result.discrepancies
            if d.type is DiscrepancyType.SUBOPTIMAL_REGIME
        ]
        assert sub
        assert result.better_regime is RegimeRecommendation.NEW
        assert result.potential_saving == pytest.approx(230_100)

    def test_a_lawful_but_costly_choice_is_never_high_severity(self):
        # Nothing is owed and nothing is penalised -- it is money left on the
        # table, not a defect.
        result = reconcile(filed(regime_filed=PersonalRegime.OLD), AY_2026_27)
        sub = [
            d
            for d in result.discrepancies
            if d.type is DiscrepancyType.SUBOPTIMAL_REGIME
        ][0]
        assert sub.severity is Severity.MEDIUM

    def test_the_breakeven_is_reported_so_the_advice_is_actionable(self):
        result = reconcile(filed(regime_filed=PersonalRegime.OLD), AY_2026_27)
        assert result.breakeven_deductions == pytest.approx(737_500, abs=100)

    def test_filing_the_better_regime_raises_nothing(self):
        result = reconcile(filed(regime_filed=PersonalRegime.NEW), AY_2026_27)
        assert not [
            d
            for d in result.discrepancies
            if d.type is DiscrepancyType.SUBOPTIMAL_REGIME
        ]

    def test_a_tie_is_not_a_finding(self):
        # At 5L both regimes are nil; neither choice is wrong.
        result = reconcile(
            filed(gross_income=500_000, regime_filed=PersonalRegime.OLD), AY_2026_27
        )
        assert result.better_regime is RegimeRecommendation.EITHER
        assert not result.discrepancies


class TestAIScore:
    def test_a_clean_return_scores_a(self):
        score = score_return(
            reconcile(
                filed(regime_filed=PersonalRegime.NEW, declared_tax=214_500), AY_2026_27
            )
        )
        assert score.accuracy == 100.0
        assert score.risk == 0.0
        assert score.grade is Grade.A

    def test_understated_tax_hurts_accuracy_and_raises_risk(self):
        score = score_return(
            reconcile(
                filed(regime_filed=PersonalRegime.NEW, declared_tax=100_000), AY_2026_27
            )
        )
        assert score.accuracy < 60
        assert score.risk > 0
        assert score.exposure == pytest.approx(114_500)

    def test_a_costly_regime_choice_carries_no_compliance_risk(self):
        # Accurate arithmetic, lawful filing, but money left on the table: the
        # score must not treat that like an over-claim.
        score = score_return(
            reconcile(
                filed(regime_filed=PersonalRegime.OLD, declared_tax=444_600), AY_2026_27
            )
        )
        assert score.accuracy == 100.0
        assert score.risk == 0.0
        assert score.findings == 1

    def test_risk_is_zero_when_the_error_favours_the_department(self):
        # Overpaying is a loss to the filer, not an exposure -- nobody is
        # penalised for paying too much.
        score = score_return(
            reconcile(
                filed(regime_filed=PersonalRegime.NEW, declared_tax=300_000), AY_2026_27
            )
        )
        assert score.exposure == 0.0
        assert score.risk == 0.0

    def test_scores_stay_in_bounds(self):
        score = score_return(
            reconcile(
                filed(
                    regime_filed=PersonalRegime.NEW,
                    declared_tax=0,
                    deductions=DeductionInputs(section_80c=500_000),
                ),
                AY_2026_27,
            )
        )
        assert 0 <= score.accuracy <= 100
        assert 0 <= score.risk <= 100
        assert 0 <= score.overall <= 100

    def test_every_finding_is_explained(self):
        score = score_return(
            reconcile(
                filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27
            )
        )
        assert len(score.explanation) >= score.findings


class TestITRExtractor:
    FORM = """
    Form 16 - Certificate of Tax Deducted at Source
    Employer: Acme Ltd
    Regime opted: New tax regime under section 115BAC
    Gross Salary                              21,00,000
    Deduction under 80CCD(2)                      50,000
    Total tax payable                          2,14,500
    """

    def test_extracts_the_load_bearing_facts(self):
        out = extract_from_text(self.FORM)
        assert out.is_usable
        assert out.filed.gross_income == 2_100_000
        assert out.filed.regime_filed is PersonalRegime.NEW
        assert out.filed.income_type is IncomeType.SALARY
        assert out.filed.declared_tax == 214_500

    def test_every_figure_keeps_its_source_line(self):
        # A number nobody can trace back to the document is a number nobody can
        # check -- the same discipline as evidence_span at ingestion.
        out = extract_from_text(self.FORM)
        assert "21,00,000" in out.provenance["gross_income"]
        assert "2,14,500" in out.provenance["declared_tax"]

    def test_missing_income_is_reported_not_guessed(self):
        out = extract_from_text("Regime opted: New tax regime\nSalary slip")
        assert not out.is_usable
        assert "gross_income" in out.missing

    def test_an_ambiguous_regime_is_reported_not_coin_flipped(self):
        # Forms print the election as a choice, naming both. The regime is what
        # the whole reconciliation is measured against; guessing it wrong
        # invalidates every finding.
        out = extract_from_text(
            "Gross Total Income 21,00,000\nSalary\n"
            "Compare old tax regime and new tax regime"
        )
        assert not out.is_usable
        assert "regime_filed" in out.missing

    def test_deductions_are_read_with_their_sections(self):
        out = extract_from_text(
            "Gross Salary 12,00,000\nRegime: old regime\nForm 16\n"
            "Deduction under 80C                 1,50,000\n"
            "Deduction under 80D                   25,000\n"
        )
        assert out.filed.deductions.section_80c == 150_000
        assert out.filed.deductions.section_80d == 25_000

    def test_absent_deductions_mean_not_claimed_not_missing(self):
        out = extract_from_text(self.FORM)
        assert out.is_usable
        assert out.filed.deductions.section_80c == 0

    def test_extract_then_reconcile_round_trips(self):
        # The form claims 50,000 of 80CCD(2), which the new regime DOES allow,
        # so taxable income is 21L - 75k standard - 50k NPS = 19,75,000 and the
        # correct liability is 2,02,800 -- not the 2,14,500 the form declares.
        out = extract_from_text(self.FORM)
        result = reconcile(out.filed, AY_2026_27)
        assert result.computed_tax == 202_800

    def test_the_forms_own_declared_tax_is_caught_as_overstated(self):
        # Falls out of the fixture above: the return declares 2,14,500 having
        # apparently not applied its own NPS deduction. Overstating tax is an
        # accuracy failure, not an exposure -- the filer overpaid.
        result = reconcile(extract_from_text(self.FORM).filed, AY_2026_27)
        mismatch = [
            d for d in result.discrepancies if d.type is DiscrepancyType.TAX_MISMATCH
        ]
        assert mismatch
        assert "over-stated" in mismatch[0].summary
        assert score_return(result).risk == 0.0


class TestPenaltyMapper:
    def test_a_lawful_regime_choice_never_looks_up_a_penalty(self, monkeypatch):
        # Guards against the worst output this product could produce: implying
        # a penalty for something entirely legal.
        called = False

        async def spy(*a, **k):
            nonlocal called
            called = True
            return []

        import app.services.analysis.penalty_mapper as pm

        monkeypatch.setattr(pm, "_query_best_effort", spy)

        result = reconcile(filed(regime_filed=PersonalRegime.OLD), AY_2026_27)
        out = asyncio.run(penalties_for(list(result.discrepancies), AY_2026_27))

        assert out == []
        assert called is False

    def test_an_unreachable_graph_yields_no_penalties_rather_than_raising(self):
        # The live case: Aura paused, no PenaltyRule nodes. Reporting findings
        # without penalty exposure is correct; inventing one would not be.
        result = reconcile(
            filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27
        )
        assert asyncio.run(penalties_for(list(result.discrepancies), AY_2026_27)) == []

    def test_graph_rows_become_exposures_with_a_disclaimer(self, monkeypatch):
        import app.services.analysis.penalty_mapper as pm

        async def fake(sections):
            return [
                {
                    "section_number": "270A",
                    "quantum": "50% of tax on under-reported income",
                    "trigger": "under-reporting of income",
                    "chunk_id": "c1",
                    "evidence_span": "shall be fifty per cent of the amount of tax",
                }
            ]

        monkeypatch.setattr(pm, "_query_best_effort", fake)

        result = reconcile(
            filed(deductions=DeductionInputs(section_80c=200_000)), AY_2026_27
        )
        out = asyncio.run(penalties_for(list(result.discrepancies), AY_2026_27))

        assert out[0].section_reference == "270A"
        assert out[0].evidence_span
        assert "qualified tax professional" in out[0].disclaimer
