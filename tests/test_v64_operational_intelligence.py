import unittest
from operational_intelligence import build_operational_output

class OperationalIntelligenceTests(unittest.TestCase):
    def test_paths_to_dominance_is_structured(self):
        out=build_operational_output("give me the Paths to Dominance event plan", [])
        self.assertEqual(out["mode"], "event_operational_overview")
        self.assertEqual(out["title"], "Paths to Dominance — Trader Prince operational intelligence")
        self.assertTrue(any("Energy Core level 16+" in row[1] for row in out["position_rules"]))
        self.assertTrue(any(row[0] == "Prosperity" and "15%" in row[1] for row in out["abilities"]))
        self.assertTrue(any(row[0] == "Leaderboard threshold" and "1,000" in row[1] for row in out["scoring"]))

    def test_paths_to_dominance_does_not_infer_dates(self):
        out=build_operational_output("when does Paths to Dominance start?", [])
        self.assertEqual(out["mode"], "event_operational_overview")
        self.assertIn("dates were not supplied", out["basis"])
        self.assertIn("Do not invent event start/end dates", out["guardrail"])

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

    def test_t100_shorthand_routes_to_same_six_day_playbook(self):
        out=build_operational_output("Top 100 Galactic Traders day by day plan", [])
        self.assertEqual(out["mode"], "event_day_plan")
        self.assertEqual(out["title"], "Top 100 Galactic Traders — operational plan")
        self.assertEqual(len(out["rows"]), 6)
        self.assertIn("Commissions", out["rows"][1][1])
        self.assertIn("Beacons", out["rows"][2][1])

    def test_t100_best_way_returns_strategy_not_generic_options(self):
        out=build_operational_output("best way to do T100", [])
        self.assertEqual(out["mode"], "event_best_strategy")
        self.assertEqual(out["title"], "Top 100 Galactic Traders — best execution strategy")
        self.assertGreaterEqual(len(out["rows"]), 7)
        self.assertIn("stop when marginal reward value drops", out["recommendation"])
        self.assertTrue(any(row[0] == "Day 5" and "third milestone" in row[1] for row in out["rows"]))

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
