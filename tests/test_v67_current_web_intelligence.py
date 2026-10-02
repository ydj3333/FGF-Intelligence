import json
import unittest
from pathlib import Path

from operational_intelligence import build_operational_output


class CurrentWebIntelligenceTests(unittest.TestCase):
    def test_current_web_snapshot_is_present(self):
        path = Path(__file__).resolve().parents[1] / "data" / "current_web_intelligence.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["snapshot_date"], "2026-10-02")
        self.assertGreaterEqual(len(data["sources"]), 8)
        self.assertTrue(any(s["id"] == "official.fgf.season2.calendar.2026-09-29" for s in data["sources"]))

    def test_paths_output_contains_current_web_context(self):
        out = build_operational_output("Paths to Dominance event plan", [])
        ctx = out["current_web_context"]
        self.assertIn("in-game calendar", ctx["season2_schedule"])
        self.assertIn("24-hour", ctx["paths_duration"])
        self.assertIn("Level 9", ctx["paths_scoring_update"])
        self.assertIn("Siwenna", ctx["season2_map"])

    def test_fleet_mechanics_are_explicit(self):
        out = build_operational_output("Paths to Dominance event plan", [])
        fleet = out["current_web_context"]["fleet_mechanics"]
        self.assertIn("Beam", fleet["energy_types"])
        self.assertIn("+5%", fleet["energy_advantage"])
        self.assertIn("+20%", fleet["champion_synergy"])
        self.assertIn("left-to-right", fleet["skill_order"])

    def test_superseded_epoch_prerequisite_is_not_silently_current(self):
        out = build_operational_output("Paths to Dominance event plan", [])
        warning = out["current_web_context"]["lifecycle_warning"]
        self.assertIn("40%", warning)
        self.assertIn("superseded", warning)


if __name__ == "__main__":
    unittest.main()
