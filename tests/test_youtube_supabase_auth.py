import unittest
from scripts.acquire_and_upload_transcripts import auth_headers

class TestSupabaseKeyHeaders(unittest.TestCase):
    def test_new_secret_key_uses_apikey_only(self):
        h = auth_headers("sb_secret_example", "application/json")
        self.assertEqual(h["apikey"], "sb_secret_example")
        self.assertNotIn("Authorization", h)

    def test_new_publishable_key_uses_apikey_only(self):
        h = auth_headers("sb_publishable_example", "application/json")
        self.assertEqual(h["apikey"], "sb_publishable_example")
        self.assertNotIn("Authorization", h)

    def test_legacy_jwt_uses_bearer(self):
        jwt = "eyJhbGciOiJIUzI1NiJ9.test.signature"
        h = auth_headers(jwt, "application/json")
        self.assertEqual(h["apikey"], jwt)
        self.assertEqual(h["Authorization"], f"Bearer {jwt}")

if __name__ == "__main__":
    unittest.main()
