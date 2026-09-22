import unittest
from scripts.fetch_playlist_index import iso8601_seconds
from scripts.cross_reference_claims import similarity

class TestVideoPipeline(unittest.TestCase):
    def test_duration_parser(self):
        self.assertEqual(iso8601_seconds("PT1H2M3S"), 3723)
        self.assertEqual(iso8601_seconds("PT45S"), 45)

    def test_similarity_identical(self):
        self.assertGreaterEqual(similarity("Core 33 unlocks fourth battle queue", "Core 33 unlocks fourth battle queue"), 0.99)

if __name__=="__main__":
    unittest.main()
