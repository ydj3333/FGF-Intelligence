import unittest

from scripts.sync_corpus import build_claim, checksum, validate


class CorpusSyncTests(unittest.TestCase):
    def test_supabase_metadata_is_preserved(self):
        row = {
            "id": "uuid-1",
            "claim_key": "key-1",
            "claim": "A test claim.",
            "category": "Test",
            "claim_type": "FACT",
            "season": "S2",
            "version": "2026-09",
            "tier": "Tier 1 — Ultimate/Official",
            "confidence": "High",
            "status": "Confirmed",
            "canonical": False,
            "metadata": {
                "Source": "Official source",
                "Notes": "Keep this.",
                "Timestamp": "2026-09-21",
            },
        }
        claim = build_claim(row, {})
        self.assertEqual(claim["Source"], "Official source")
        self.assertEqual(claim["Notes"], "Keep this.")
        self.assertEqual(claim["metadata"]["lifecycle"]["state"], "current")
        self.assertEqual(claim["Season/Version"], "S2 / 2026-09")

    def test_validation_rejects_duplicate_claim_keys(self):
        with self.assertRaises(RuntimeError):
            validate([
                {"claim_key": "x", "claim": "one"},
                {"claim_key": "x", "claim": "two"},
            ])

    def test_validation_rejects_duplicate_claim_text(self):
        with self.assertRaises(RuntimeError):
            validate([
                {"claim_key": "x", "claim": "Same text"},
                {"claim_key": "y", "claim": " same   text "},
            ])

    def test_checksum_is_deterministic(self):
        claims = [
            {"claim_key": "b", "Claim": "B", "Category": "x", "Evidence Tier": "Tier 2",
             "Confidence": "High", "Status": "Confirmed", "metadata": {}},
            {"claim_key": "a", "Claim": "A", "Category": "x", "Evidence Tier": "Tier 1",
             "Confidence": "High", "Status": "Confirmed", "metadata": {}},
        ]
        self.assertEqual(checksum(claims), checksum(list(reversed(claims))))


if __name__ == "__main__":
    unittest.main()
