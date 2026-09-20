import unittest
from knowledge_analyzer import KnowledgeAnalyzer, ClaimQuality


class TestKnowledgeAnalyzer(unittest.TestCase):
    def test_tier_one_specific_claim_scores_high(self):
        claim = {
            "id": 1,
            "Claim": "Energy Core 33 unlocks the fourth Battle Queue.",
            "Category": "Progression",
            "Evidence Tier": "Tier 1",
            "Source": "in-game screenshot",
            "Verification Status": "Verified",
            "Claim Type": "FACT",
            "Status": "Confirmed",
        }
        result = KnowledgeAnalyzer([claim]).analyze_claim(claim)
        self.assertGreaterEqual(result.quality_score, 0.85)
        self.assertEqual(result.quality_tier, ClaimQuality.EXCELLENT)
        self.assertGreaterEqual(result.confidence_score, 0.9)
        self.assertTrue(result.is_current)
        self.assertFalse(result.is_superseded)

    def test_tier1_with_conflict_stays_excellent(self):
        claim1 = {
            "id": 1,
            "Claim": "Commerce Guild Core 8 requires 5000 alloy",
            "Category": "Guild",
            "Evidence Tier": "Tier 1",
            "Source": "Official game documentation, v2.1",
            "Status": "Under Review",
        }
        claim2 = {
            "id": 2,
            "Claim": "Commerce Guild Core 8 requires 6000 alloy",
            "Category": "Guild",
            "Evidence Tier": "Tier 1",
            "Source": "Official game documentation, v2.2",
            "Status": "Under Review",
        }
        result = KnowledgeAnalyzer([claim1, claim2]).analyze_claim(claim1)
        self.assertEqual(result.quality_tier, ClaimQuality.EXCELLENT)
        self.assertTrue(result.has_preserved_conflict)
        self.assertIn(2, result.contradictions)
        self.assertIn("has_preserved_conflict", result.issues)
        self.assertGreaterEqual(result.quality_score, 0.85)

    def test_conflict_flag_present_but_not_quality_penalty(self):
        claim1 = {
            "id": 1, "Claim": "Core 8 requires 5000 alloy",
            "Category": "Guild", "Evidence Tier": "Tier 1", "Status": "Under Review",
        }
        claim2 = {
            "id": 2, "Claim": "Core 8 requires 6000 alloy",
            "Category": "Guild", "Evidence Tier": "Tier 1", "Status": "Under Review",
        }
        analyzer = KnowledgeAnalyzer([claim1, claim2])
        analysis1 = analyzer.analyze_claim(claim1)
        analysis2 = analyzer.analyze_claim(claim2)
        self.assertEqual(analysis1.quality_tier, ClaimQuality.EXCELLENT)
        self.assertEqual(analysis2.quality_tier, ClaimQuality.EXCELLENT)
        self.assertTrue(analysis1.has_preserved_conflict)
        self.assertTrue(analysis2.has_preserved_conflict)
        self.assertGreaterEqual(analysis1.quality_score, 0.85)
        self.assertGreaterEqual(analysis2.quality_score, 0.85)

    def test_superseded_claim_stays_good_quality(self):
        claim = {
            "id": 1, "Claim": "Core 8 requires 5000 alloy",
            "Category": "Guild", "Evidence Tier": "Tier 1",
            "Source": "Official game documentation, v2.1", "Status": "Superseded",
        }
        result = KnowledgeAnalyzer([claim]).analyze_claim(claim)
        self.assertEqual(result.quality_tier, ClaimQuality.EXCELLENT)
        self.assertTrue(result.is_superseded)
        self.assertFalse(result.is_current)
        self.assertIn("superseded", result.issues)

    def test_unrelated_increase_decrease_not_conflict(self):
        claim1 = {
            "id": 1, "Claim": "Research Office increases research speed",
            "Category": "Technology", "Evidence Tier": "Tier 1",
        }
        claim2 = {
            "id": 2, "Claim": "Crew Cabins decrease building time",
            "Category": "Crew", "Evidence Tier": "Tier 1",
        }
        result = KnowledgeAnalyzer([claim1, claim2]).analyze_claim(claim1)
        self.assertEqual(result.contradictions, [])
        self.assertFalse(result.has_preserved_conflict)

    def test_numerical_disagreement_requires_entity_alignment(self):
        claim1 = {
            "id": 1, "Claim": "Core 8 requires 5000 alloy",
            "Category": "Progression", "Evidence Tier": "Tier 1",
        }
        claim2 = {
            "id": 2, "Claim": "Core 9 requires 6000 alloy",
            "Category": "Progression", "Evidence Tier": "Tier 1",
        }
        claim3 = {
            "id": 3, "Claim": "Core 8 requires 6000 alloy",
            "Category": "Progression", "Evidence Tier": "Tier 1",
        }
        result = KnowledgeAnalyzer([claim1, claim2, claim3]).analyze_claim(claim1)
        self.assertIn(3, result.contradictions)
        self.assertNotIn(2, result.contradictions)

    def test_conflict_does_not_reduce_confidence(self):
        base = {
            "id": 1, "Claim": "Core 8 requires 5000 alloy",
            "Category": "Progression", "Evidence Tier": "Tier 1",
            "Source": "Official source", "Verification Status": "Verified",
            "Confidence": "High",
        }
        result_without = KnowledgeAnalyzer([base]).analyze_claim(base)
        other = dict(base)
        other["id"] = 2
        other["Claim"] = "Core 8 requires 6000 alloy"
        result_with = KnowledgeAnalyzer([base, other]).analyze_claim(base)
        self.assertEqual(result_with.confidence_score, result_without.confidence_score)

    def test_corpus_without_explicit_ids_is_analyzed(self):
        claims = [
            {
                "Claim": "Core 8 requires 5000 alloy",
                "Category": "Progression",
                "Evidence Tier": "Tier 1",
                "Source": "Official source",
            },
            {
                "Claim": "Core 8 requires 6000 alloy",
                "Category": "Progression",
                "Evidence Tier": "Tier 1",
                "Source": "Official source",
            },
        ]
        analyzer = KnowledgeAnalyzer(claims)
        analyses = analyzer.analyze_all()
        self.assertEqual(len(analyses), 2)
        self.assertIn(1, analyses)
        self.assertIn(2, analyses)
        self.assertTrue(analyses[1].has_preserved_conflict)
        self.assertIn(2, analyses[1].contradictions)

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
