import unittest
from knowledge_analyzer import KnowledgeAnalyzer, ClaimQuality

class TestKnowledgeAnalyzer(unittest.TestCase):
    def test_tier_one_specific_claim_scores_high(self):
        claims = [{
            "id": 1,
            "Claim": "Energy Core 33 unlocks the fourth Battle Queue.",
            "Category": "Progression",
            "Evidence Tier": "Tier 1",
            "Source": "in-game screenshot",
            "Verification Status": "Verified",
            "Claim Type": "FACT",
            "Status": "Confirmed",
        }]
        a = KnowledgeAnalyzer(claims).analyze_claim(claims[0])
        self.assertGreaterEqual(a.quality_score, 0.85)
        self.assertGreaterEqual(a.confidence_score, 0.9)

    def test_under_review_and_conflict_are_not_silently_promoted(self):
        claims = [
            {"id": 1, "Claim": "Core 8 is required to create the Commerce Guild.",
             "Category": "Guild", "Evidence Tier": "Tier 1",
             "Source": "old screenshot", "Status": "Under Review"},
            {"id": 2, "Claim": "Core 9 is required to create the Commerce Guild.",
             "Category": "Guild", "Evidence Tier": "Tier 1",
             "Source": "new screenshot", "Status": "Confirmed"},
        ]
        analyzer = KnowledgeAnalyzer(claims)
        result = analyzer.analyze_claim(claims[0])
        self.assertIn("under_review", result.issues)
        self.assertIn("has_preserved_conflict", result.issues)

    def test_missing_source_is_flagged(self):
        claim = {"id": 3, "Claim": "Some mechanic exists.", "tier": 3}
        result = KnowledgeAnalyzer([claim]).analyze_claim(claim)
        self.assertIn("missing_source", result.issues)
        self.assertIn("missing_provenance", result.issues)

    def test_empty_summary_is_safe(self):
        summary = KnowledgeAnalyzer([]).get_summary()
        self.assertEqual(summary["total_claims"], 0)
        self.assertEqual(summary["average_quality"], 0.0)

if __name__ == "__main__":
    unittest.main()
