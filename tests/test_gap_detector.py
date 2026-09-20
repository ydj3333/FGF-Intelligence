import unittest
from gap_detector import GapDetector

class TestGapDetector(unittest.TestCase):
    def test_unsupported_exact_cost_is_gap(self):
        claims = [{
            "id": 1,
            "Claim": "Energy Core 33 unlocks the fourth Battle Queue.",
            "Category": "Progression",
            "Evidence Tier": "Tier 2",
            "Status": "Confirmed",
        }]
        gaps = GapDetector(claims, failed_questions=["How much does Core 35 cost in fusion seeds?"]).detect_gaps()
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0]["gap_type"], "missing_or_unsupported_evidence")

    def test_supported_repair_question_is_not_false_gap(self):
        claims = [{
            "id": 1,
            "Claim": "Major Damage requires Repair Modules and is repaired in the Repair Bay.",
            "Category": "Fleet Repair",
            "Evidence Tier": "Tier 1",
            "Status": "Confirmed",
        }]
        gaps = GapDetector(claims, failed_questions=["How do I repair major damage?"]).detect_gaps()
        self.assertEqual(gaps[0]["unsupported_count"], 0)
        self.assertEqual(gaps[0]["gap_type"], "retrieval_or_reasoning_gap")

    def test_no_questions(self):
        d = GapDetector([])
        self.assertEqual(d.get_summary()["total_gaps"], 0)

if __name__ == "__main__":
    unittest.main()
