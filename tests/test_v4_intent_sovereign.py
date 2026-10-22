import unittest
from agent import classify_intent, extract_constraints, retrieve, answer_quality_gate

class V4IntentFirstTests(unittest.TestCase):
    def test_repair_beats_combat_overlap(self):
        q="what's the best ways to repair your fleets ad free way"
        self.assertEqual(classify_intent(q),"Fleet Damage/Repair")
        self.assertIn("F2P",extract_constraints(q))
        self.assertIn("Best",extract_constraints(q))
        hits=retrieve(q,10)
        self.assertTrue(hits)
        text="Repair methods: Minor Damage can recover without Repair Modules; Major Damage requires Repair Modules."
        # The gate now requires answers to declare the evidence they used
        # (uncited answers are only accepted as explicit abstentions).
        repair_refs=[i+1 for i,c in enumerate(hits) if 'repair' in c.get('Claim','').lower() or 'damage' in c.get('Claim','').lower()][:2]
        gate=answer_quality_gate(q,text,hits,repair_refs)
        self.assertTrue(gate["passes"])
        self.assertFalse("command point" in text.lower())

if __name__=="__main__":
    unittest.main()
