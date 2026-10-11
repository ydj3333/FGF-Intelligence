import unittest

from scripts.question_bank_pipeline import audit, is_safe_training_example


def row(**overrides):
    base = {
        "review_status": "approved",
        "training_eligible": True,
        "source_canonical": True,
        "source_status": "confirmed",
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

    def test_audit_counts_rows_without_promoting_them(self):
        rows = [row(), row(review_status="needs_review", training_eligible=False)]
        result = audit(rows)
        self.assertEqual(result["total_rows"], 2)
        self.assertEqual(result["training_eligible_rows"], 1)
        self.assertIn("not model training", result["note"])


if __name__ == "__main__":
    unittest.main()
