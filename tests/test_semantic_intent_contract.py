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
            {
                "Claim": "When a fleet has Champions matching the Style of its Flagship, the matching count grants additional attributes to the Flagship and combat craft of the same Style: 2 matching Champions = Attack +10%, DEF +10%, INT +10%; 3 matching Champions = Attack +20%, DEF +20%, INT +20%.",
                "Category": "Fleet",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Champion skills activate in the order Champions are placed, from left to right in the formation.",
                "Category": "Combat",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Champion Star Level determines which Champion abilities can be unlocked or awakened and increases their ability level caps at certain levels.",
                "Category": "Champions",
                "Evidence Tier": "Tier 1 — Ultimate/Official",
                "Status": "Confirmed",
            },
            {
                "Claim": "Commerce Guild rewards in Shadowfront were increased in the September 22, 2026 hot update.",
                "Category": "Official Update",
                "Evidence Tier": "Tier 2 — Official Developer",
                "Status": "Current",
            },
            {
                "Claim": "Weapon Prism was added to the Discount Shop in the September 22, 2026 hot update.",
                "Category": "Official Update",
                "Evidence Tier": "Tier 2 — Official Developer",
                "Status": "Current",
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

    def test_matching_champion_count_uses_exact_numeric_bonus_evidence(self):
        question = "What attribute bonuses do 2 matching Champions grant to a matching-Style fleet?"
        parsed = self.engine.parse(question)
        self.assertEqual(parsed.property, "numeric_effect")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertTrue(ranked)
        self.assertIn("2 matching champions = attack +10%", ranked[0][0]["Claim"].lower())
        result = self.engine.compose(question)
        self.assertIn("+10%", result["answer"])
        self.assertTrue(any("+10%" in item["claim"] for item in result["evidence"]))
        self.assertFalse(any("star level" in item["claim"].lower() for item in result["evidence"]))

    def test_champion_skill_order_uses_sequence_evidence(self):
        question = "In what order do Champion skills activate?"
        parsed = self.engine.parse(question)
        self.assertEqual(parsed.property, "sequence")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertIn("left to right", ranked[0][0]["Claim"].lower())
        result = self.engine.compose(question)
        self.assertIn("left to right", result["answer"].lower())
        self.assertFalse(any("star level" in item["claim"].lower() for item in result["evidence"]))

    def test_direct_answer_abstains_when_only_adjacent_evidence_exists(self):
        engine = KnowledgeQueryEngine([{
            "Claim": "Champion Star Level determines which Champion abilities can be unlocked.",
            "Category": "Champions",
            "Evidence Tier": "Tier 1 — Ultimate/Official",
            "Status": "Confirmed",
        }])
        result = engine.compose("In what order do Champion skills activate?")
        self.assertEqual(result["answer_type"], "knowledge_abstention")
        self.assertFalse(result["evidence"])
        self.assertIn("does not directly establish", result["answer"].lower())

    def test_update_answer_excludes_unrelated_claims_from_same_update(self):
        result = self.engine.compose("What changed for Commerce Guild rewards in Shadowfront on September 22, 2026?")
        evidence_text = " ".join(item["claim"] for item in result["evidence"]).lower()
        self.assertIn("commerce guild rewards in shadowfront", evidence_text)
        self.assertNotIn("weapon prism", evidence_text)

    def test_source_question_is_not_answered_with_an_unrelated_numeric_claim(self):
        parsed = self.engine.parse("Where can I obtain migration permits?")
        ranked = self.engine.rank(parsed, limit=4)
        self.assertTrue(ranked)
        self.assertIn("obtained from the migration shop", ranked[0][0]["Claim"].lower())


if __name__ == "__main__":
    unittest.main()
