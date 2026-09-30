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

    def test_kaboom_five_lineup_request_returns_five_options(self):
        out=build_operational_output("best strategy for kaboom champions combo 5 line ups", [])
        self.assertEqual(out["mode"], "event_combo_options")
        self.assertEqual(len(out["rows"]), 5)
        self.assertIn("Zora + Lily + Jodie", out["rows"][0][1])
        self.assertEqual(out["rows"][0][4], "Concrete")
        self.assertTrue(all(row[4] in {"Concrete", "Roster required"} for row in out["rows"]))
        self.assertTrue(any("Roster required" == row[4] for row in out["rows"][1:]))
        self.assertIn("without guessing", out["guardrail"])

    def test_kaboom_roster_aware_generates_actual_owned_lineups(self):
        profile={"champion_levels":{
            "Zora Domini":30,"Lily":30,"Jodie Beart":30,
            "Evan Rogers":30,"Kama Moai":30,"Killer Bee":30
        }}
        claims=[
            {"Claim":"Zora Domini is described as specializing in burst damage, penetration, multi-hit attacks, and AoE pressure","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
            {"Claim":"Zora's active skill is reported by the community to group enemies tightly in Kaboom Robot.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
            {"Claim":"Lily is recommended by the community for Kaboom Robot because of high AoE damage and effectiveness against grouped enemies.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
            {"Claim":"Jodie is reported by the community to work well alongside Zora and Lily in Kaboom Robot because her weapon effects add damage against grouped enemies.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
            {"Claim":"Evan Rogers is described as providing sustained Beam damage and formation-wide benefits","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
            {"Claim":"Killer Bee is described as combining high damage with health recovery/sustain","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
            {"Claim":"Kama Moai is described as a dependable Kinetic damage dealer and alternative when Zora Domini is unavailable","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
        ]
        out=build_operational_output(
            "give me 5 Kaboom lineups",
            [],
            player_context=profile,
            all_claims=claims
        )
        self.assertEqual(out["mode"],"event_combo_roster_options")
        self.assertEqual(out["verification"]["requested_option_count"],5)
        self.assertGreaterEqual(out["verification"]["returned_option_count"],3)
        self.assertLessEqual(out["verification"]["returned_option_count"],5)
        self.assertEqual(out["verification"]["count_match"], out["verification"]["returned_option_count"] == 5)
        self.assertIn("Zora Domini + Lily + Jodie Beart", [row[1] for row in out["rows"]])
        self.assertTrue(any("not Kaboom-validated" in row[2] for row in out["rows"][1:]))

    def test_kaboom_roster_aware_refuses_unsupported_count(self):
        profile={"champion_levels":{"Zora Domini":30,"Lily":30}}
        claims=[
            {"Claim":"Zora's active skill is reported by the community to group enemies tightly in Kaboom Robot.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
            {"Claim":"Lily is recommended by the community for Kaboom Robot because of high AoE damage and effectiveness against grouped enemies.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
        ]
        out=build_operational_output(
            "show 5 Kaboom combos",
            [],
            player_context=profile,
            all_claims=claims
        )
        self.assertEqual(out["mode"],"event_combo_roster_options")
        self.assertFalse(out["verification"]["count_match"])
        self.assertLess(out["verification"]["returned_option_count"],5)
        self.assertIn("no invented champions", out["guardrail"].lower())

    def test_kaboom_five_lineup_request_is_verified(self):
        out=build_operational_output("give me 5 Kaboom lineups", [])
        verification=out["verification"]
        self.assertEqual(verification["requested_option_count"], 5)
        self.assertEqual(verification["returned_option_count"], 5)
        self.assertTrue(verification["count_match"])
        self.assertEqual(verification["concrete_validated_options"], 1)
        self.assertEqual(verification["roster_required_options"], 4)
        self.assertTrue(verification["requires_player_roster"])

    def test_option_count_parser_supports_word_form(self):
        out=build_operational_output("show five Kaboom combos", [])
        self.assertEqual(out["verification"]["requested_option_count"], 5)
        self.assertTrue(out["verification"]["count_match"])

    def test_tier12_terms_are_auto_keywords(self):
        from knowledge_query_engine import KnowledgeQueryEngine
        claims=[
            {
                "Claim":"Commerce Guild rewards in Shadowfront were increased in the September 22, 2026 hot update.",
                "Evidence Tier":"Tier 2 — Official Developer",
                "Status":"Current"
            }
        ]
        engine=KnowledgeQueryEngine(claims)
        parsed=engine.parse("what changed in Shadowfront")
        self.assertEqual(parsed.entity, "shadowfront")

    def test_all_tier12_claims_have_keyword_path(self):
        import json
        from pathlib import Path
        from knowledge_query_engine import KnowledgeQueryEngine, STOP, _tokens
        data=json.loads((Path(__file__).resolve().parents[1]/"data"/"knowledge.json").read_text(encoding="utf-8"))
        tier12=[c for c in data.get("claims",[]) if "tier 1" in str(c.get("Evidence Tier",c.get("tier",""))).lower() or "tier 2" in str(c.get("Evidence Tier",c.get("tier",""))).lower()]
        self.assertGreater(len(tier12), 0)
        engine=KnowledgeQueryEngine(tier12)
        checked=0
        for claim in tier12:
            text=str(claim.get("Claim",claim.get("claim","")))
            terms=[t for t in _tokens(text) if t not in STOP and len(t)>=5]
            if not terms:
                continue
            term=max(terms,key=len)
            parsed=engine.parse("what is "+term)
            self.assertNotEqual(parsed.entity,"unknown",msg="Tier-1/Tier-2 term not discoverable: "+term)
            checked+=1
        self.assertGreaterEqual(checked, 1)

    def test_canonical_phrases_accept_plural_queries(self):
        from knowledge_query_engine import KnowledgeQueryEngine
        claims=[
            {"Claim":"Commerce Guild rewards in Shadowfront were increased.","Evidence Tier":"Tier 2 — Official Developer","Status":"Current"},
            {"Claim":"Weapon Prisms are listed in the Discount Shop.","Evidence Tier":"Tier 2 — Official Developer","Status":"Current"},
            {"Claim":"The Outer Rim Outpost Shadowfront protects traders.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        ]
        engine=KnowledgeQueryEngine(claims)
        self.assertEqual(engine.parse("what changed in Commerce Guilds").entity, "commerce guild")
        self.assertEqual(engine.parse("where are Weapon Prisms").entity, "weapon prisms")
        self.assertEqual(engine.parse("what is the Outer Rim Outpost").entity, "outer rim outpost")

    def test_canonical_vocabulary_audit_is_populated(self):
        import json
        from pathlib import Path
        from knowledge_query_engine import KnowledgeQueryEngine
        data=json.loads((Path(__file__).resolve().parents[1]/"data"/"knowledge.json").read_text(encoding="utf-8"))
        engine=KnowledgeQueryEngine(data.get("claims",[]))
        audit=engine.parser.vocabulary_audit()
        self.assertGreater(audit["tier12_keyword_count"], 0)
        self.assertGreater(audit["tier12_phrase_alias_count"], 0)
        self.assertGreater(audit["tier12_phrase_count"], 0)

    def test_canonical_named_entities_survive_common_query_variants(self):
        from knowledge_query_engine import KnowledgeQueryEngine
        claims=[
            {"Claim":"Commerce Guild rewards in Shadowfront were increased.","Evidence Tier":"Tier 2 — Official Developer","Status":"Current"},
            {"Claim":"Weapon Prisms are listed in the Discount Shop.","Evidence Tier":"Tier 2 — Official Developer","Status":"Current"},
            {"Claim":"The Outer Rim Outpost Shadowfront protects traders.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        ]
        engine=KnowledgeQueryEngine(claims)
        variants=[
            ("Commerce Guild", "Commerce Guilds", "what changed in Commerce Guilds"),
            ("Weapon Prism", "Weapon Prisms", "where are Weapon Prisms"),
            ("Outer Rim Outpost", "Outer Rim Outpost", "what is the Outer Rim Outpost"),
        ]
        for singular,plural,question in variants:
            p=engine.parse(question)
            self.assertNotEqual(p.entity,"unknown")
            self.assertIn(p.entity, {singular.lower(),plural.lower()})

    def test_no_operational_trigger_for_plain_mechanic(self):
        self.assertIsNone(build_operational_output("What does Kinetic counter?", []))

if __name__ == "__main__":
    unittest.main()
