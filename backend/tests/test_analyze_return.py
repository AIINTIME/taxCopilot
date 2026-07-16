"""Tests for the analyze-return pipeline (Phase 10).

Exercises analyze_return_text -- the HTTP-free core -- so no file, DB, or LLM is
needed. The route itself is just parse_pdf + this function.
"""

from app.services.analysis.routes import analyze_return_text

# A return that is wrong three ways: 80C over the cap, tax understated, and filed
# under the costlier regime. The exact case demoed end-to-end this session.
FLAWED_ITR = """
ITR-1 Assessment Year 2026-27
Regime opted: Old tax regime
Form 16 - Salary income from employer
Gross Total Income                        21,00,000
Deduction under 80C                        2,00,000
Deduction under 80D                          25,000
Total tax payable                          3,50,000
"""


class TestDetection:
    def test_all_three_findings_surface(self):
        r = analyze_return_text(FLAWED_ITR)
        assert r.usable
        kinds = {d.type for d in r.discrepancies}
        assert kinds == {"excess_deduction", "tax_mismatch", "suboptimal_regime"}

    def test_the_score_reflects_the_problems(self):
        score = analyze_return_text(FLAWED_ITR).score
        assert score.grade == "C"
        assert score.exposure == 40_000  # tax understated by 40k
        assert score.risk > 0

    def test_a_clean_return_scores_well_with_no_findings(self):
        clean = """
        ITR-1 Assessment Year 2026-27
        Regime opted: New tax regime under section 115BAC
        Form 16 - Salary income
        Gross Total Income                        21,00,000
        Total tax payable                          2,14,500
        """
        r = analyze_return_text(clean)
        assert not [d for d in r.discrepancies if d.type != "suboptimal_regime"]
        assert r.score.grade == "A"


class TestWhereItWentWrong:
    """Each finding must point at the line it came from -- the highlight."""

    def test_a_deduction_finding_cites_its_source_line(self):
        r = analyze_return_text(FLAWED_ITR)
        excess = next(d for d in r.discrepancies if d.type == "excess_deduction")
        assert excess.source_line is not None
        assert "80C" in excess.source_line
        assert "2,00,000" in excess.source_line

    def test_the_tax_finding_cites_the_declared_tax_line(self):
        r = analyze_return_text(FLAWED_ITR)
        mismatch = next(d for d in r.discrepancies if d.type == "tax_mismatch")
        assert mismatch.source_line is not None
        assert "3,50,000" in mismatch.source_line

    def test_the_regime_finding_cites_a_real_line_not_the_parsed_value(self):
        # Regression: provenance used to store the parsed value ("old"), which
        # rendered as a meaningless "where". It must be the source line.
        r = analyze_return_text(FLAWED_ITR)
        regime = next(d for d in r.discrepancies if d.type == "suboptimal_regime")
        assert regime.source_line == "Regime opted: Old tax regime"

    def test_declared_facts_and_provenance_are_returned(self):
        r = analyze_return_text(FLAWED_ITR)
        assert r.declared["gross_income"] == 2_100_000
        assert r.declared["regime_filed"] == "old"
        assert "provenance" in r.declared


class TestGracefulDegradation:
    def test_an_unreadable_document_asks_rather_than_crashing(self):
        r = analyze_return_text("some notes with no tax figures at all")
        assert r.usable is False
        assert "gross_income" in r.missing
        assert r.clarification is not None
        assert r.discrepancies == []
        assert r.score is None

    def test_an_ambiguous_regime_is_reported_not_guessed(self):
        # Names both regimes -> the extractor refuses rather than coin-flipping
        # the basis the whole reconciliation depends on.
        both = """
        Gross Total Income 21,00,000
        Salary
        Compare old tax regime versus new tax regime
        Total tax payable 3,50,000
        """
        r = analyze_return_text(both)
        assert r.usable is False
        assert "regime_filed" in r.missing

    def test_penalties_are_empty_and_that_is_explicit(self):
        # Present-but-empty, because the graph is unavailable -- not omitted in
        # a way that implies there are none.
        r = analyze_return_text(FLAWED_ITR)
        assert r.penalties == []
