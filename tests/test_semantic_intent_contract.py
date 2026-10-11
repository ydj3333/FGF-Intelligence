"""Generic semantic-intent regression tests.

These tests assert relation-level behavior with synthetic evidence so they do not
encode an expected answer for every user question. Production truth still comes
from the versioned claims/evidence corpus.
"""
import unittest

from knowledge_query_engine import KnowledgeQueryEngine


class SemanticIntentContractTests(unittest.TestCase):
    def setUp(self):
        self.claims = [
            {
                "Claim": "During the Commerce Guild Duel Battlefield Showdown, Glory can be converted to points and attacking opposing Guild members acquires Glory at a rate of 150%.",
                "Category": "Event",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Damage against a countered style is increased by 5%.",
                "Category": "Combat",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Server migration requires 10 migration permits.",
                "Category": "Migration",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Migration permits can be obtained from the migration shop.",
                "Category": "Migration",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
        ]
        self.engine = KnowledgeQueryEngine(self.claims)

    def test_opponent_intent_is_distinct_from_combat_counter(self):
        questions = [
            "Commerce Guild Duel — whom do we fight against?",
            "Who are the opponents in Commerce Guild Duel League?",
            "During the guild battlefield showdown, who can we attack?",
        ]
        for question in questions:
            with self.subTest(question=question):
                parsed = self.engine.parse(question)
                self.assertEqual(parsed.property, "opponent")
                ranked = self.engine.rank(parsed, limit=4)
                self.assertTrue(ranked)
                self.assertIn("opposing guild members", ranked[0][0]["Claim"].lower())
                self.assertNotIn("countered style", ranked[0][0]["Claim"].lower())

    def test_counter_question_still_prefers_counter_evidence(self):
        parsed = self.engine.parse("What is the damage bonus against a countered style?")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertTrue(ranked)
        self.assertIn("countered style", ranked[0][0]["Claim"].lower())

    def test_numeric_question_prefers_claim_with_explicit_value(self):
        parsed = self.engine.parse("How many migration permits are required for server migration?")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertTrue(ranked)
        self.assertIn("10 migration permits", ranked[0][0]["Claim"].lower())

    def test_source_question_is_not_answered_with_an_unrelated_numeric_claim(self):
        parsed = self.engine.parse("Where can I obtain migration permits?")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertTrue(ranked)
        self.assertIn("obtained from the migration shop", ranked[0][0]["Claim"].lower())


if __name__ == "__main__":
    unittest.main()
