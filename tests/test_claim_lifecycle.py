import unittest

from claim_lifecycle import (
    ClaimState,
    lifecycle_metadata,
    normalize_state,
    production_eligible,
    promotion_decision,
    summarize_states,
    temporal_scope,
)


class ClaimLifecycleTests(unittest.TestCase):
    def test_legacy_status_mapping_is_non_destructive(self):
        self.assertEqual(normalize_state("Confirmed"), ClaimState.CURRENT)
        self.assertEqual(normalize_state("Under Review"), ClaimState.CANDIDATE)
        self.assertEqual(normalize_state("Conflicting"), ClaimState.CONFLICTING)
        self.assertEqual(normalize_state("Superseded"), ClaimState.SUPERSEDED)

    def test_under_review_is_not_production_current(self):
        claim = {"Status": "Under Review", "Evidence Tier": "Tier 1 — Ultimate/Official"}
        self.assertFalse(production_eligible(claim))
        decision = promotion_decision(
            claim, ClaimState.CURRENT, human_approval=False, temporal_validated=True
        )
        self.assertFalse(decision.allowed)

    def test_candidate_requires_human_validation(self):
        claim = {"Status": "Under Review", "Evidence Tier": "Tier 1 — Ultimate/Official"}
        self.assertFalse(
            promotion_decision(claim, ClaimState.VALIDATED, human_approval=False).allowed
        )
        self.assertTrue(
            promotion_decision(claim, ClaimState.VALIDATED, human_approval=True).allowed
        )

    def test_current_requires_temporal_validation(self):
        claim = {"Status": "Validated", "Evidence Tier": "Tier 1 — Ultimate/Official"}
        self.assertFalse(
            promotion_decision(
                claim, ClaimState.CURRENT, human_approval=True, temporal_validated=False
            ).allowed
        )
        self.assertTrue(
            promotion_decision(
                claim,
                ClaimState.CURRENT,
                human_approval=True,
                temporal_validated=True,
            ).allowed
        )

    def test_conflict_blocks_promotion_until_resolved(self):
        claim = {"Status": "Conflicting", "Evidence Tier": "Tier 1 — Ultimate/Official"}
        self.assertFalse(
            promotion_decision(
                claim,
                ClaimState.CURRENT,
                human_approval=True,
                temporal_validated=True,
            ).allowed
        )

    def test_temporal_scope_does_not_infer_unknown_values(self):
        claim = {
            "Status": "Confirmed",
            "Season/Version": "S2 / 2026-09",
            "metadata": {"temporal": {"server_scope": "Servers 1001–1016"}},
        }
        scope = temporal_scope(claim)
        self.assertEqual(scope.server_scope, "Servers 1001–1016")
        self.assertEqual(scope.season_scope, "S2 / 2026-09")
        self.assertIsNone(scope.valid_from)
        self.assertIsNone(scope.valid_until)

    def test_lifecycle_metadata_is_additive(self):
        claim = {
            "Status": "Under Review",
            "Evidence Tier": "Tier 3 — Creator/Community",
            "metadata": {"foo": "bar"},
        }
        meta = lifecycle_metadata(claim)
        self.assertEqual(meta["lifecycle"]["state"], "candidate")
        self.assertEqual(meta["lifecycle"]["tier"], 3)
        self.assertEqual(meta["temporal"], {})

    def test_state_summary(self):
        claims = [
            {"Status": "Confirmed"},
            {"Status": "Under Review"},
            {"Status": "Conflicting"},
        ]
        summary = summarize_states(claims)
        self.assertEqual(summary["current"], 1)
        self.assertEqual(summary["candidate"], 1)
        self.assertEqual(summary["conflicting"], 1)


if __name__ == "__main__":
    unittest.main()
