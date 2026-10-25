"""Regression tests for F2P constraint enforcement and evidence-backed abstention."""
import unittest

from agent import answer_quality_gate


class SemanticQualityGateRegressions(unittest.TestCase):
    def test_f2p_repair_rejects_paid_recommendation_even_if_free_option_is_mentioned(self):
        question = "I'm F2P and my ship took major damage, how do I repair it without spending?"
        answer = (
            "Repair your fleet with the premium pack; buy the pack to finish faster. "
            "Free options exist too."
        )
        claims = [
            {
                "Claim": "Free repair bay restores ships after major damage.",
                "Evidence Tier": "Tier 1",
                "Status": "current",
            }
        ]
        result = answer_quality_gate(question, answer, claims, [1])
        self.assertFalse(result["respects_constraints"])
        self.assertFalse(result["passes"])

    def test_f2p_repair_accepts_no_spend_answer_when_supported(self):
        question = "I'm F2P and my ship took major damage, how do I repair it without spending?"
        answer = "Use the free repair bay to recover your ship without spending or buying a paid pack."
        claims = [
            {
                "Claim": "Free repair bay restores ships after major damage.",
                "Evidence Tier": "Tier 1",
                "Status": "current",
            }
        ]
        result = answer_quality_gate(question, answer, claims, [1])
        self.assertTrue(result["respects_constraints"])
        self.assertTrue(result["passes"])

    def test_unknown_exact_fusion_seed_cost_can_pass_as_safe_abstention(self):
        question = "How much does Core 35 cost in Fusion Seeds?"
        answer = (
            "The current evidence does not establish the exact Fusion Seed cost "
            "for Core 35, so I will not guess or substitute another upgrade cost."
        )
        result = answer_quality_gate(question, answer, [], [])
        self.assertTrue(result["addresses_question"])
        self.assertTrue(result["uses_relevant_evidence"])
        self.assertTrue(result["passes"])

    def test_supported_numeric_cost_claim_is_recognized(self):
        question = "How much does Core 35 cost in Fusion Seeds?"
        answer = "Core 35 requires 1,000 Fusion Seeds."
        claims = [
            {
                "Claim": "Core 35 requires 1,000 Fusion Seeds.",
                "Evidence Tier": "Tier 1",
                "Status": "current",
            }
        ]
        result = answer_quality_gate(question, answer, claims, [1])
        self.assertTrue(result["addresses_question"])
        self.assertTrue(result["evidence_ids_valid"])


if __name__ == "__main__":
    unittest.main()
