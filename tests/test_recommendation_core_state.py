import unittest
from unittest.mock import patch

import agent


class CoreRecommendationRegressionTests(unittest.TestCase):
    def test_core_25_routes_to_actionable_progression_recommendation(self):
        claims = [
            {"Claim": "Keeping Energy Core upgrades as the primary base-development priority is a source-stated recommendation.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
            {"Claim": "Energy Core governs maximum building levels.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
            {"Claim": "Energy Core governs fleet slots.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
            {"Claim": "Energy Core governs technology access.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
            {"Claim": "Energy Core level determines the maximum level of Flagships, Champions, and other buildings.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
            {"Claim": "Keeping Warehouse level on par with Energy Core is recommended to avoid losing valuable stockpiles upon defeat.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
        ]
        with patch.object(agent, "retrieve", return_value=claims):
            out = agent.recommend("core 25 and 4 what should i do")
        self.assertEqual(out["recommendation_type"], "core_progression")
        self.assertEqual(out["player_state"]["energy_core_level"], 25)
        self.assertIn("Energy Core 25", out["answer"])
        self.assertIn("primary base-development priority", out["answer"])
        self.assertIn("4", out["answer"])
        self.assertNotIn("No recommendation results", out["answer"])

    def test_core_recommendation_does_not_invent_next_level_requirements(self):
        claims = [
            {"Claim": "Keeping Energy Core upgrades as the primary base-development priority is a source-stated recommendation.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
        ]
        with patch.object(agent, "retrieve", return_value=claims):
            out = agent.recommend("core 25 what should i do")
        self.assertIn("exact next-level requirements", out["uncertainty"])
        self.assertIn("Upgrade screen", out["answer"])
        self.assertNotIn("Core 26 requires", out["answer"])


if __name__ == "__main__":
    unittest.main()
