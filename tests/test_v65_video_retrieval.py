import unittest

from youtube_evidence_provider import YouTubeEvidenceProvider
from fgf_orchestrator import FGFOrchestrator


class FakeProvider(YouTubeEvidenceProvider):
    def __init__(self, candidates, videos):
        super().__init__(supabase_url="https://example.invalid")
        self._fake = (candidates, videos)

    def _load(self):
        return self._fake


class VideoRetrievalTests(unittest.TestCase):
    def test_event_alias_connects_candidate_to_video(self):
        provider = FakeProvider(
            [
                {
                    "id": 1,
                    "video_database_id": 10,
                    "video_id": "abc",
                    "claim_text": "Zora and Lily are used for fast Kaboom Robot wave clearing.",
                    "evidence_tier": 3,
                    "confidence": 0.9,
                    "status": "candidate",
                    "source_url": "https://youtube.example/abc",
                    "evidence_excerpt": "Kaboom Robot wave clear",
                }
            ],
            [
                {
                    "id": 10,
                    "video_id": "abc",
                    "title": "FGF Kaboom Robot Guide",
                    "video_url": "https://youtube.example/abc",
                    "description": "Foundation Galactic Frontier Kaboom Robot strategy",
                    "processing_status": "indexed",
                }
            ],
        )
        hits = provider.find_relevant("best combo for Kaboom event", limit=4)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["event_match"], "kaboom robot")
        self.assertEqual(hits[0]["video_url"], "https://youtube.example/abc")
        self.assertFalse(hits[0]["provenance"]["canonical_promotion"])

    def test_generic_video_cannot_leak_into_event_answer(self):
        provider = FakeProvider(
            [
                {
                    "id": 1,
                    "video_database_id": 10,
                    "video_id": "abc",
                    "claim_text": "Use strong AoE champions for wave clearing.",
                    "status": "candidate",
                    "source_url": "https://youtube.example/abc",
                }
            ],
            [
                {
                    "id": 10,
                    "video_id": "abc",
                    "title": "Generic wave clearing guide",
                    "video_url": "https://youtube.example/abc",
                    "description": "Generic strategy",
                    "processing_status": "indexed",
                }
            ],
        )
        self.assertEqual(provider.find_relevant("best combo for Kaboom event"), [])

    def test_rejected_video_candidate_is_blocked(self):
        provider = FakeProvider(
            [
                {
                    "id": 1,
                    "video_database_id": 10,
                    "video_id": "abc",
                    "claim_text": "Kaboom Robot uses fast AoE wave clearing.",
                    "status": "rejected",
                    "source_url": "https://youtube.example/abc",
                }
            ],
            [
                {
                    "id": 10,
                    "video_id": "abc",
                    "title": "FGF Kaboom Robot Guide",
                    "video_url": "https://youtube.example/abc",
                    "description": "Foundation Galactic Frontier Kaboom Robot",
                    "processing_status": "indexed",
                }
            ],
        )
        self.assertEqual(provider.find_relevant("best combo for Kaboom event"), [])

    def test_factual_core_does_not_use_youtube_fallback(self):
        calls = []

        def core(_q, _ctx=None):
            return {
                "answer": "I cannot establish the requested mechanic.",
                "answer_type": "knowledge_abstention",
                "evidence": [],
                "query": {"question_type": "definition"},
            }

        class P:
            def find_relevant(self, *args, **kwargs):
                calls.append(1)
                return [{"claim": "community claim"}]

        result = FGFOrchestrator(core, youtube_provider=P()).answer("what is Kaboom Robot")
        self.assertEqual(calls, [])
        self.assertTrue(result["abstained"])


if __name__ == "__main__":
    unittest.main()
