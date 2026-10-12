import unittest

from scripts.question_bank_pipeline import audit, content_tokens, evaluation_candidates, is_safe_training_example, normalize_source_row, overlap_score


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
        self.assertEqual([r["id"] for r in evaluation_candidates(rows)], ["good"])

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
