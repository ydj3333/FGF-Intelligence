import unittest
from unittest.mock import MagicMock, patch

from scripts.question_bank_pipeline import audit, call_ask, content_tokens, evaluation_candidates, is_safe_training_example, normalize_source_row, overlap_score, score_evidence_items, wait_for_api


def row(**overrides):
    base = {
        "review_status": "approved",
        "training_eligible": True,
        "source_canonical": True,
        "source_status": "confirmed",
        "source_claim_text": "Migration requires ten permits for the documented group.",
        "source_claim_id": "claim-1",
        "question": "What is the verified rule?",
        "ideal_answer": "The verified rule is documented.",
        "generation_method": "reviewed_source_grounded",
    }
    base.update(overrides)
    return base


class QuestionBankGovernanceTests(unittest.TestCase):
    def test_approved_canonical_source_row_is_export_eligible(self):
        self.assertTrue(is_safe_training_example(row()))

    def test_needs_review_row_is_not_training_eligible(self):
        self.assertFalse(is_safe_training_example(row(review_status="needs_review")))

    def test_candidate_or_noncanonical_source_is_not_training_eligible(self):
        self.assertFalse(is_safe_training_example(row(source_canonical=False)))
        self.assertFalse(is_safe_training_example(row(source_status="candidate")))

    def test_generated_paraphrase_shell_is_not_training_eligible(self):
        self.assertFalse(
            is_safe_training_example(
                row(generation_method="verified_claim_template_v4_paraphrase_shell")
            )
        )

    def test_missing_provenance_is_not_training_eligible(self):
        self.assertFalse(is_safe_training_example(row(source_claim_id=None)))

    def test_live_probe_uses_supported_get_ask_route(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"answer":"ok"}'
        response.__enter__.return_value = response
        with patch("scripts.question_bank_pipeline.urlopen", return_value=response) as mocked:
            result = call_ask("https://example.test", "How many migration permits?")
        request = mocked.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIn("/api/ask?q=How+many+migration+permits%3F", request.full_url)
        self.assertEqual(result["payload"]["answer"], "ok")

    def test_live_probe_retries_transient_503(self):
        from urllib.error import HTTPError

        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"answer":"ok"}'
        response.__enter__.return_value = response
        transient = HTTPError("https://example.test", 503, "Service Unavailable", {}, None)
        with patch("scripts.question_bank_pipeline.urlopen", side_effect=[transient, response]) as mocked, \
             patch("scripts.question_bank_pipeline.time.sleep") as sleep:
            result = call_ask("https://example.test", "How many migration permits?")
        self.assertEqual(result["http_status"], 200)
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once()

    def test_health_warmup_retries_cold_start_once_before_batch(self):
        from urllib.error import HTTPError

        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"ok":true,"version":"test"}'
        response.__enter__.return_value = response
        transient = HTTPError("https://example.test/api/health", 503, "Waking", {}, None)
        with patch("scripts.question_bank_pipeline.urlopen", side_effect=[transient, response]) as mocked, \
             patch("scripts.question_bank_pipeline.time.sleep") as sleep:
            result = wait_for_api("https://example.test", max_attempts=3)
        self.assertEqual(result["payload"]["ok"], True)
        self.assertEqual(mocked.call_count, 2)
        sleep.assert_called_once()

    def test_source_join_normalization_uses_claim_lifecycle_and_fails_closed(self):
        linked = normalize_source_row({
            "source_claim": {
                "id": "claim-1",
                "claim": "Ten permits are required.",
                "status": "Confirmed",
                "canonical": True,
                "tier": "Tier 1",
                "version": "S2",
            }
        })
        self.assertEqual(linked["source_status"], "Confirmed")
        self.assertTrue(linked["source_canonical"])
        self.assertEqual(linked["source_claim_text"], "Ten permits are required.")
        missing = normalize_source_row({"source_claim": None})
        self.assertIsNone(missing["source_status"])
        self.assertFalse(missing["source_canonical"])
        self.assertIsNone(missing["source_claim_text"])

    def test_shell_variants_are_excluded_from_live_evaluation_candidates(self):
        rows = [
            row(id="good", generation_method="verified_claim_template_v3_subject_aware"),
            row(id="shell", generation_method="verified_claim_template_v4_paraphrase_shell"),
            row(id="noncanonical", source_canonical=False),
            row(id="missing_claim_text", source_claim_text=""),
        ]
        self.assertEqual([r["id"] for r in evaluation_candidates(rows)], ["good", "noncanonical"])

    def test_noncanonical_source_rows_are_exploratory_not_gold(self):
        rows = [
            row(id="noncanonical", source_canonical=False, training_eligible=False, generation_method="verified_claim_template_v3_subject_aware"),
            row(id="curated", review_status="needs_review", training_eligible=False, generation_method="expert_curated_source_grounded_v1"),
        ]
        candidates = evaluation_candidates(rows)
        self.assertEqual([r["id"] for r in candidates], ["curated", "noncanonical"])
        self.assertFalse(any(is_safe_training_example(r) for r in candidates))

    def test_evidence_scoring_does_not_let_one_good_claim_hide_noise(self):
        result = score_evidence_items(
            "Commerce Guild rewards in Shadowfront were increased in the September 22 update.",
            [
                {"claim": "Commerce Guild rewards in Shadowfront were increased in the September 22 update."},
                {"claim": "Weapon Prism was added to the Discount Shop in the September 22 update."},
            ],
        )
        self.assertTrue(result["source_claim_supported_by_evidence"])
        self.assertEqual(result["irrelevant_evidence_count_triage"], 1)
        self.assertEqual(len(result["evidence_item_scores"]), 2)

    def test_token_overlap_is_triage_not_training_approval(self):
        self.assertGreater(overlap_score(
            "Commerce Guild Duel grants Glory for attacking opposing guild members",
            "During Commerce Guild Duel, attacking opposing Guild members acquires Glory"
        ), 0.2)
        self.assertEqual(overlap_score("migration permits", "damage counter bonus"), 0.0)
        self.assertIn("migration", content_tokens("How many migration permits are needed?"))

    def test_audit_counts_rows_without_promoting_them(self):
        rows = [row(), row(review_status="needs_review", training_eligible=False)]
        result = audit(rows)
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["training_eligible_rows"], 1)
        self.assertIn("not model training", result["note"])


if __name__ == "__main__":
    unittest.main()
