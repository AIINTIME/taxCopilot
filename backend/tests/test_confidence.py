"""Tests for services/rag/confidence.py's calibrated confidence score.

Pure and substituted -- no DB, no Pinecone, no LLM.
"""

from app.services.rag.confidence import calculate_confidence


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
