import unittest
from operational_intelligence import build_operational_output

class OperationalIntelligenceTests(unittest.TestCase):
    def test_gvg_is_day_table(self):
        out=build_operational_output("Give me a GvG day-by-day plan", [])
        self.assertEqual(out["mode"], "event_day_plan")
        self.assertEqual(len(out["rows"]), 6)
        self.assertIn("Not established", out["rows"][0][1])

    def test_top100_has_explicit_days(self):
        out=build_operational_output("Top 100 Galactic Traders day by day plan", [])
        self.assertEqual(out["mode"], "event_day_plan")
        self.assertIn("Commissions", out["rows"][1][1])
        self.assertIn("Beacons", out["rows"][2][1])

    def test_shop_matrix(self):
        out=build_operational_output("best resources to buy in different shops", [])
        self.assertEqual(out["mode"], "shop_matrix")
        shops=[r[0] for r in out["rows"]]
        self.assertIn("Intel Shop", shops)
        self.assertIn("Regular Shop", shops)

    def test_kaboom_combo_is_structured(self):
        out=build_operational_output("best combo for Kaboom event", [])
        self.assertEqual(out["mode"], "event_combo")
        self.assertTrue(any("Zora + Lily + Jodie" in row[1] for row in out["rows"]))
        self.assertIn("community", out["basis"].lower())

    def test_no_operational_trigger_for_plain_mechanic(self):
        self.assertIsNone(build_operational_output("What does Kinetic counter?", []))

if __name__ == "__main__":
    unittest.main()
