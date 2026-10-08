import unittest
from unittest.mock import patch
import agent

class FleetStateRecommendationTests(unittest.TestCase):
    def test_core_25_and_t4_preserves_both_constraints(self):
        claims=[
            {"Claim":"Keeping Energy Core upgrades as the primary base-development priority is a source-stated recommendation.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
            {"Claim":"Energy Core level determines the maximum level of Flagships, Champions, and other buildings.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        ]
        with patch.object(agent,"retrieve",return_value=claims):
            out=agent.recommend("core 25 and t4 what should i do")
        self.assertEqual(out["player_state"]["energy_core_level"],25)
        self.assertEqual(out["player_state"]["fleet_tier"],"T4")
        self.assertIn("Fleet Tier T4",out["answer"])
        self.assertNotIn("detected “4”",out["answer"])

    def test_t1_to_t5_are_all_parsed_as_fleet_state(self):
        from constraint_extractor import extract_constraints
        for tier in ("T1","T2","T3","T4","T5"):
            self.assertEqual(extract_constraints(f"my fleet is {tier}").fleet_tier,tier)

if __name__ == "__main__":
    unittest.main()
