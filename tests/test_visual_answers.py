import unittest

from visual_answers import build_visual_answer
from knowledge_query_engine import KnowledgeQueryEngine


class VisualAnswerTests(unittest.TestCase):
    def test_migration_permit_question_gets_numeric_visual(self):
        visual = build_visual_answer(
            "how many migration permits are required for server migration",
            {"answer": "Server migration requires 10 Migration Permits."},
        )
        self.assertIsNotNone(visual)
        self.assertEqual(visual["kind"], "number_card")
        self.assertEqual(visual["headline"], "10")
        self.assertEqual(visual["unit"], "Migration Permits")
        self.assertIn("not verified", " ".join(visual["warnings"]).lower())
        self.assertIn("fgfwiki.com", visual["source"])

    def test_migration_permit_question_retrieves_numeric_claim(self):
        claim = {
            "Claim": "Server migration requires 10 Migration Permits.",
            "Category": "Server Migration",
            "Claim Type": "Requirement",
            "Evidence Tier": "Tier 2 — Official FGF Wiki",
            "Confidence": "High",
            "Status": "confirmed",
            "Source": "https://fgfwiki.com/en/news/migration",
        }
        result = KnowledgeQueryEngine([claim]).compose(
            "how many migration permits are required for server migration"
        )
        self.assertIn("10 Migration Permits", result.get("answer", ""))
        self.assertTrue(result.get("evidence"))

    def test_migration_requirements_get_checklist_visual(self):
        visual = build_visual_answer(
            "show me server migration requirements",
            {"answer": "Check the official migration guide."},
        )
        self.assertIsNotNone(visual)
        self.assertEqual(visual["kind"], "checklist")
        self.assertEqual(len(visual["steps"]), 5)
        self.assertTrue(any("10 Migration Permits" in x for x in visual["requirements"]))
        self.assertTrue(any("25-day cooldown" in x for x in visual["warnings"]))

    def test_cost_unknown_f2p_plan_surfaces_uncertainty(self):
        import agent
        result = agent.answer(
            "Give me a safe F2P progression plan when exact resource costs are unknown."
        )
        answer = str(result.get("answer") or "").lower()
        uncertainty = str(result.get("uncertainty") or "").lower()
        self.assertTrue(
            any(term in answer + " " + uncertainty for term in (
                "does not establish", "not established", "unknown",
                "insufficient evidence", "uncertain"
            )),
            "Cost-unknown F2P guidance must explicitly state uncertainty."
        )
        self.assertIn("not invent totals", answer + " " + uncertainty)

    def test_unrelated_question_does_not_force_visual(self):
        visual = build_visual_answer(
            "what does kinetic counter",
            {"answer": "Kinetic counters Beam.", "evidence": []},
        )
        self.assertIsNone(visual)

    def test_explicit_visual_uses_only_retrieved_claims(self):
        evidence = [
            {"Claim": "Beam counters Kinetic."},
            {"Claim": "Kinetic counters Ionic."},
        ]
        visual = build_visual_answer(
            "show me a diagram of weapon counters",
            {"evidence": evidence, "uncertainty": "Illustration only."},
        )
        self.assertIsNotNone(visual)
        self.assertEqual(visual["kind"], "fact_summary")
        self.assertEqual(visual["headline"], "Beam counters Kinetic.")
        self.assertEqual(visual["items"], ["Kinetic counters Ionic."])


if __name__ == "__main__":
    unittest.main()
