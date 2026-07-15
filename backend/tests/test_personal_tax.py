"""Personal income-tax computation tests.

Pure functions throughout -- no DB, no LLM, no network. These run without any
credential configured, which is why this layer is built first.

Figures are asserted exactly. The rate tables are the oracle and they are
transcribed from the Income Tax Department's published AY 2026-27 rates; these
tests are what catches a mis-transcription, so re-derive an expectation by hand
before changing one to make it pass.
"""

from datetime import date

import pytest

from app.services.computation.engine import compute
from app.services.computation.rules.personal.deductions import DeductionInputs
from app.services.computation.rules.personal.regime_comparison_personal import (
    IncomeType,
    PersonalRegimeInput,
    RegimeRecommendation,
    compare_regimes_personal,
    compute_for_regime,
)
from app.services.computation.rules.personal.slab_tables import (
    PersonalRegime,
    RatesNotSeededError,
    get_params,
)
from app.services.query.input_extractor import extract_inputs, parse_amount
from app.services.query.temporal_resolver import resolve_as_of
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


def salary(amount: float, **deductions: float) -> PersonalRegimeInput:
    return PersonalRegimeInput(
        gross_income=amount,
        income_type=IncomeType.SALARY,
        deductions=DeductionInputs(**deductions),
    )


class TestSlabTax:
    """Hand-derived from the AY 2026-27 slabs. New regime bands: nil to 4L,
    5% to 8L, 10% to 12L, 15% to 16L, 20% to 20L, 25% to 24L, 30% above.
    """

    @pytest.mark.parametrize(
        "taxable, expected",
        [
            (400_000, 0),           # top of the nil band
            (400_001, 0.05),        # first rupee of the 5% band
            (800_000, 20_000),      # 4L @ 5%
            (1_200_000, 60_000),    # + 4L @ 10%
            (1_600_000, 120_000),   # + 4L @ 15%
            (2_000_000, 200_000),   # + 4L @ 20%
            (2_400_000, 300_000),   # + 4L @ 25%
            (3_000_000, 480_000),   # + 6L @ 30%
        ],
    )
    def test_new_regime_band_boundaries(self, taxable, expected):
        from app.services.computation.rules.personal.slab_tax import compute_slab_tax

        params = get_params("2026-27", PersonalRegime.NEW)
        tax, _ = compute_slab_tax(taxable, params)
        assert tax == pytest.approx(expected)

    @pytest.mark.parametrize(
        "taxable, expected",
        [
            (250_000, 0),
            (500_000, 12_500),      # 2.5L @ 5%
            (1_000_000, 112_500),   # + 5L @ 20%
            (2_000_000, 412_500),   # + 10L @ 30%
        ],
    )
    def test_old_regime_band_boundaries(self, taxable, expected):
        from app.services.computation.rules.personal.slab_tax import compute_slab_tax

        params = get_params("2026-27", PersonalRegime.OLD)
        tax, _ = compute_slab_tax(taxable, params)
        assert tax == pytest.approx(expected)

    def test_zero_and_negative_income_pay_nothing(self):
        from app.services.computation.rules.personal.slab_tax import compute_slab_tax

        params = get_params("2026-27", PersonalRegime.NEW)
        assert compute_slab_tax(0, params) == (0.0, [])
        assert compute_slab_tax(-50_000, params) == (0.0, [])


class TestFiveLakhWalkthrough:
    """Plan verification step 0: "my income is 5 lakhs per annum"."""

    def test_both_regimes_nil_and_recommendation_is_either(self):
        result = compare_regimes_personal(salary(500_000), AY_2026_27)

        assert result.old_regime_tax == 0
        assert result.new_regime_tax == 0
        assert result.delta == 0
        assert result.recommended is RegimeRecommendation.EITHER

    def test_tie_is_explained_by_the_rebate(self):
        result = compare_regimes_personal(salary(500_000), AY_2026_27)
        assert any("87A" in f for f in result.deciding_factors)

    def test_rebate_is_what_zeroes_it_not_the_slabs(self):
        # Without the rebate there IS slab tax; the rebate is doing the work.
        outcome = compute_for_regime(salary(500_000), PersonalRegime.NEW, AY_2026_27)
        assert outcome.taxable_income == 425_000     # 5L less the 75k std deduction
        assert any("87A" in (s.section_reference or "") for s in outcome.steps)
        assert outcome.total_tax == 0


class TestTwentyOneLakhWalkthrough:
    """Plan verification step 0: "my current salary is 21 lakhs per annum".

    New: 21L - 75k std = 20,25,000 taxable
         20,000 + 40,000 + 60,000 + 80,000 + 6,250 = 2,06,250; +4% cess = 2,14,500
    Old: 21L - 50k std = 20,50,000 taxable
         12,500 + 1,00,000 + 3,15,000 = 4,27,500; +4% cess = 4,44,600
    """

    def test_exact_liabilities(self):
        result = compare_regimes_personal(salary(2_100_000), AY_2026_27)
        assert result.new_regime_tax == 214_500
        assert result.old_regime_tax == 444_600
        assert result.recommended is RegimeRecommendation.NEW

    def test_breakeven_is_reported_and_is_large(self):
        result = compare_regimes_personal(salary(2_100_000), AY_2026_27)

        assert result.breakeven_deductions is not None
        # ~7.37L of deductions before the old regime catches up -- more than
        # 80C + 80D + 24(b) combined, so the recommendation is robust rather
        # than an artifact of the taxpayer not mentioning deductions.
        assert result.breakeven_deductions == pytest.approx(737_500, abs=100)

    def test_breakeven_actually_flips_the_recommendation(self):
        # The break-even figure is only meaningful if deducting it really does
        # make the old regime competitive.
        breakeven = compare_regimes_personal(
            salary(2_100_000), AY_2026_27
        ).breakeven_deductions

        below = compare_regimes_personal(
            salary(2_100_000, section_80c=breakeven - 200_000), AY_2026_27
        )
        assert below.recommended is RegimeRecommendation.NEW

    def test_no_surcharge_below_fifty_lakh(self):
        outcome = compute_for_regime(salary(2_100_000), PersonalRegime.NEW, AY_2026_27)
        assert not any("Surcharge" in s.label for s in outcome.steps)

    def test_every_slab_step_is_citable(self):
        # computation_citations resolves these against Neo4j; a step with no
        # section_reference cannot produce a citation.
        outcome = compute_for_regime(salary(2_100_000), PersonalRegime.NEW, AY_2026_27)
        for step in outcome.steps:
            if step.label.startswith("Slab"):
                assert step.section_reference == "Sec 115BAC(1A)"


class TestRegimeFlip:
    """Plan verification step 5: the recommendation must flip on deductions."""

    def test_heavy_deductions_favour_old_regime(self):
        # 80C 1.5L + 80D 25k + 24(b) 2L + HRA 5L = 8.75L on a 21L salary,
        # i.e. above the ~7.37L break-even. Old: 1,71,600 vs new: 2,14,500.
        result = compare_regimes_personal(
            salary(
                2_100_000,
                section_80c=150_000,
                section_80d=25_000,
                home_loan_interest_24b=200_000,
                hra_exemption=500_000,
            ),
            AY_2026_27,
        )
        assert result.recommended is RegimeRecommendation.OLD
        assert result.old_regime_tax == 171_600

    def test_no_deductions_favour_new_regime(self):
        result = compare_regimes_personal(salary(2_100_000), AY_2026_27)
        assert result.recommended is RegimeRecommendation.NEW

    def test_old_regime_cannot_win_at_or_below_twelve_lakh(self):
        # The new regime's 87A rebate (max 60k, income limit 12L) zeroes any
        # income up to 12L outright, so no amount of old-regime deductions can
        # beat it -- the best available outcome is a nil-vs-nil tie. Worth
        # pinning: it means "which regime?" is only a real question above 12L.
        result = compare_regimes_personal(
            salary(
                1_200_000,
                section_80c=150_000,
                section_80d=25_000,
                home_loan_interest_24b=200_000,
                hra_exemption=400_000,
            ),
            AY_2026_27,
        )
        assert result.new_regime_tax == 0
        assert result.old_regime_tax == 0
        assert result.recommended is RegimeRecommendation.EITHER

    def test_new_regime_reports_what_it_disallows(self):
        result = compare_regimes_personal(
            salary(1_200_000, section_80c=150_000, hra_exemption=400_000), AY_2026_27
        )
        assert "Sec 80C" in result.new_outcome.disallowed_deductions
        assert "Sec 10(13A)" in result.new_outcome.disallowed_deductions

    def test_over_claimed_80c_is_capped_not_accepted(self):
        # 2L claimed against a 1.5L cap -- the excess must not reduce tax.
        capped = compare_regimes_personal(salary(1_200_000, section_80c=200_000), AY_2026_27)
        at_cap = compare_regimes_personal(salary(1_200_000, section_80c=150_000), AY_2026_27)

        assert capped.old_regime_tax == at_cap.old_regime_tax
        assert "Sec 80C" in capped.old_outcome.capped_deductions


class TestSurcharge:
    def test_surcharge_applies_above_fifty_lakh(self):
        outcome = compute_for_regime(salary(6_000_000), PersonalRegime.NEW, AY_2026_27)
        assert any("Surcharge" in s.label for s in outcome.steps)

    def test_marginal_relief_stops_the_threshold_cliff(self):
        # Surcharge is a cliff: crossing 50L applies 10% to the WHOLE tax, so
        # 10k of extra income would otherwise cost ~1.1L. Marginal relief caps
        # tax+surcharge at (tax on the threshold + the excess income).
        #
        # Cess is then levied on the relieved figure, so the TOTAL still rises
        # by the excess plus 4% of it -- that is the statute, not a leak. The
        # bound below is therefore excess * (1 + cess_rate), not excess.
        just_under = compute_for_regime(salary(5_075_000), PersonalRegime.NEW, AY_2026_27)
        just_over = compute_for_regime(salary(5_085_000), PersonalRegime.NEW, AY_2026_27)

        extra_income = 10_000
        cess_rate = get_params("2026-27", PersonalRegime.NEW).cess_rate

        increase = just_over.total_tax - just_under.total_tax
        assert increase <= extra_income * (1 + cess_rate)

    def test_marginal_relief_step_is_shown_in_the_trace(self):
        outcome = compute_for_regime(salary(5_085_000), PersonalRegime.NEW, AY_2026_27)
        relief = [s for s in outcome.steps if "Marginal relief" in s.label]
        assert relief, "crossing the surcharge threshold must show its relief"
        assert relief[0].amount < 0

    def test_without_relief_the_cliff_would_be_punitive(self):
        # Guards the relief itself: the un-relieved 10% surcharge on the full
        # tax is an order of magnitude more than the extra income.
        outcome = compute_for_regime(salary(5_085_000), PersonalRegime.NEW, AY_2026_27)
        gross_surcharge = next(s.amount for s in outcome.steps if s.label.startswith("Surcharge"))
        assert gross_surcharge > 100_000


class TestRatesAreData:
    def test_unseeded_year_raises_rather_than_guessing(self):
        # Falling back to an adjacent year's rates would be confidently wrong.
        with pytest.raises(RatesNotSeededError):
            get_params("2099-00", PersonalRegime.NEW)

    def test_seeded_params_carry_a_source_reference(self):
        for regime in PersonalRegime:
            assert get_params("2026-27", regime).source_reference


class TestTemporalResolution:
    """Plan verification step 2. The regime must follow the TAX YEAR, never
    the wall clock -- see the module docstring in temporal_resolver.py.
    """

    def test_filing_season_query_resolves_to_the_completed_fy(self):
        ctx = resolve_as_of("what tax do I pay", today=date(2026, 7, 15))
        assert ctx.assessment_year.ay == "2026-27"
        assert ctx.assessment_year.financial_year == "2025-26"

    def test_july_2026_query_uses_the_1961_act_not_the_2025_act(self):
        # THE REGRESSION THIS GUARDS: today (2026-07-15) is past the
        # 1 Apr 2026 pivot, but FY 2025-26 ended before it. Resolving the
        # regime from "now" would answer under the wrong Act.
        ctx = resolve_as_of("what tax do I pay", today=date(2026, 7, 15))
        assert ctx.regime is TaxActRegime.ACT_1961

    def test_explicit_year_past_the_pivot_uses_the_2025_act(self):
        ctx = resolve_as_of("tax for AY 2027-28", today=date(2026, 7, 15))
        assert ctx.assessment_year.ay == "2027-28"
        assert ctx.regime is TaxActRegime.ACT_2025

    @pytest.mark.parametrize(
        "query, expected_ay",
        [("tax for FY 2024-25", "2025-26"), ("tax for AY 2025-26", "2025-26")],
    )
    def test_explicit_fy_and_ay_agree(self, query, expected_ay):
        ctx = resolve_as_of(query, today=date(2026, 7, 15))
        assert ctx.assessment_year.ay == expected_ay

    def test_capital_gains_pivot(self):
        old = resolve_as_of("tax for FY 2023-24", today=date(2026, 7, 15))
        new = resolve_as_of("tax for FY 2024-25", today=date(2026, 7, 15))
        assert old.capital_gains_period is CapitalGainsPeriod.PRE_RATE_CHANGE
        assert new.capital_gains_period is CapitalGainsPeriod.POST_RATE_CHANGE

    def test_explicit_date_wins(self):
        ctx = resolve_as_of("whatever", explicit_date=date(2024, 1, 1))
        assert ctx.as_of_date == date(2024, 1, 1)
        assert ctx.assessment_year.financial_year == "2023-24"


class TestInputExtraction:
    """Plan verification step 3. "5 lakhs" must be 500000, never 5."""

    @pytest.mark.parametrize(
        "text, expected",
        [
            ("5 lakhs", 500_000),
            ("5 lakh", 500_000),
            ("5L", 500_000),
            ("5,00,000", 500_000),
            ("500000", 500_000),
            ("21 lakhs", 2_100_000),
            ("1.2 crore", 12_000_000),
            ("Rs 1.2 crore", 12_000_000),
            ("50 lakh", 5_000_000),
            ("12k", 12_000),
        ],
    )
    def test_indian_numerals(self, text, expected):
        assert parse_amount(text) == pytest.approx(expected)

    def test_salary_query_is_fully_extracted(self):
        e = extract_inputs("My current salary is 21 lakhs per annum what tax should I pay")
        assert e.values["gross_income"] == 2_100_000
        assert e.income_type is IncomeType.SALARY
        assert not e.needs_clarification

    def test_business_income_is_recognised(self):
        e = extract_inputs("I earn 15 lakhs from my business")
        assert e.income_type is IncomeType.BUSINESS

    def test_unstated_income_type_asks_rather_than_guesses(self):
        # Assuming salary would apply a standard deduction the filer may not
        # be entitled to -- understating tax, silently.
        e = extract_inputs("my income is 5 lakhs per annum")
        assert e.values["gross_income"] == 500_000
        assert e.needs_clarification
        assert "income_type" in e.missing

    def test_missing_income_is_reported(self):
        assert "gross_income" in extract_inputs("what tax should I pay").missing

    def test_year_mentions_are_not_read_as_amounts(self):
        e = extract_inputs("my salary is 21 lakhs for AY 2026-27")
        assert e.values["gross_income"] == 2_100_000

    def test_unstated_deductions_are_surfaced_as_an_assumption(self):
        e = extract_inputs("my salary is 21 lakhs")
        assert any("deduction" in a.lower() for a in e.assumptions)


class TestEngineDispatch:
    def test_compute_returns_a_trace_with_citable_references(self):
        trace = compute(
            "personal_regime_comparison",
            {"gross_income": 2_100_000, "income_type": IncomeType.SALARY},
            AY_2026_27,
        )
        assert trace.rule_name == "personal_regime_comparison"
        assert trace.outputs["new_regime_tax"] == 214_500
        assert trace.outputs["recommended_regime"] == "new"
        assert "Sec 115BAC" in trace.statutory_references
        assert trace.steps

    def test_compute_accepts_plain_mapping_deductions(self):
        # income_type as a bare string and deductions as a plain dict -- the
        # shape orchestration will hand over from input_extractor.
        trace = compute(
            "personal_regime_comparison",
            {
                "gross_income": 2_100_000,
                "income_type": "salary",
                "deductions": {
                    "section_80c": 150_000,
                    "section_80d": 25_000,
                    "home_loan_interest_24b": 200_000,
                    "hra_exemption": 500_000,
                },
            },
            AY_2026_27,
        )
        assert trace.outputs["recommended_regime"] == "old"

    def test_unknown_rule_names_are_rejected_clearly(self):
        with pytest.raises(KeyError):
            compute("no_such_rule", {}, AY_2026_27)
