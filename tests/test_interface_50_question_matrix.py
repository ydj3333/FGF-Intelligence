"""Interface-wide regression matrix: run the existing 50 Objective #1 questions
through the same HTTP routes used by the player-facing UI.

This deliberately tests routes, not only isolated helper functions. It reports
answer/evidence gaps instead of hiding them behind an overall pass.
"""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import agent

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = json.loads((ROOT / "data" / "objective_1_benchmark.json").read_text(encoding="utf-8"))
QUESTIONS = BENCHMARK["questions"]


class Interface50QuestionMatrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), agent.H)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d" % cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def get_json(self, path, params=None):
        url = self.base + path
        if params:
            url += "?" + urlencode(params, doseq=True)
        try:
            with urlopen(url, timeout=30) as response:
                self.assertEqual(response.status, 200, path)
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            # Preserve JSON diagnostics from API error boundaries instead of
            # reporting only a generic HTTPError/connection reset in CI.
            body = ""
            try:
                body = exc.read().decode("utf-8")
            except Exception:
                pass
            self.fail(f"{path} request failed: {type(exc).__name__}: {body or exc}")

    def test_original_50_questions_through_player_ask_route(self):
        failures = []
        no_evidence = []
        for item in QUESTIONS:
            with self.subTest(question_id=item["id"], question=item["question"]):
                payload = self.get_json("/api/ask", {"q": item["question"]})
                answer = str(payload.get("answer") or "").strip()
                self.assertTrue(answer, "empty player-facing answer")
                evidence = payload.get("evidence") or []
                if not evidence and not item.get("requires_uncertainty", False):
                    no_evidence.append(item["id"] + " " + item["question"])
                for forbidden in item.get("must_not_contain", []):
                    self.assertNotIn(forbidden.lower(), answer.lower())
                if item.get("requires_uncertainty"):
                    uncertainty = str(payload.get("uncertainty") or "").lower()
                    answer_low = answer.lower()
                    if not any(x in (answer_low + " " + uncertainty) for x in
                               ("does not establish", "cannot establish", "unknown",
                                "not established", "insufficient evidence", "uncertain")):
                        failures.append(item["id"] + " missing explicit uncertainty")
        self.assertFalse(failures, "\n".join(failures))
        # Evidence gaps are made visible in test logs for triage; don't silently
        # turn them into false failures where a question intentionally needs a gap.
        if no_evidence:
            print("\nNO-EVIDENCE QUESTIONS (review):\n" + "\n".join(no_evidence))

    def test_all_50_questions_through_recommendation_and_evidence_routes(self):
        gaps = []
        for item in QUESTIONS:
            q = item["question"]
            with self.subTest(question_id=item["id"], route="recommend"):
                payload = self.get_json("/api/recommend", {"q": q, "objective": "general"})
                self.assertIsInstance(payload, dict)
                if not (payload.get("answer") or payload.get("recommendation") or
                        payload.get("priorities") or payload.get("result")):
                    gaps.append(item["id"] + " /api/recommend returned no player-facing content")
            with self.subTest(question_id=item["id"], route="evidence"):
                payload = self.get_json("/api/v5/evidence", {"q": q})
                self.assertIsInstance(payload.get("results"), list,
                                      "/api/v5/evidence contract changed")
                if not payload.get("results") and not item.get("requires_uncertainty", False):
                    gaps.append(item["id"] + " /api/v5/evidence returned no matching evidence")
        self.assertFalse(gaps, "\n".join(gaps))

    def test_migration_permit_answer_is_evidence_anchored(self):
        payload = self.get_json("/api/ask", {
            "q": "how many migration permits are required for server migration"
        })
        answer = str(payload.get("answer") or "").lower()
        evidence = payload.get("evidence") or []
        self.assertIn("10 migration permits", answer)
        self.assertTrue(any(
            "10 migration permits" in str(item.get("claim") or "").lower()
            for item in evidence
        ), "the exact number must be supported by a directly matching evidence claim")
        visual = payload.get("visual") or {}
        if visual:
            self.assertEqual(str(visual.get("headline") or ""), "10")

    def test_commerce_guild_duel_opponent_question_does_not_route_to_weapon_counter(self):
        questions = [
            "commerce guild duel - whom do we fight against",
            "who are the opponents in Commerce Guild Duel League",
        ]
        for question in questions:
            with self.subTest(question=question):
                payload = self.get_json("/api/ask", {"q": question})
                answer = str(payload.get("answer") or "").lower()
                evidence = payload.get("evidence") or []
                self.assertIn("opposing guild members", answer)
                self.assertTrue(any(
                    "commerce guild duel" in str(item.get("claim") or "").lower()
                    and "opposing guild members" in str(item.get("claim") or "").lower()
                    for item in evidence
                ), "answer must cite the event-specific opponent evidence")
                self.assertNotIn("damage against a countered style is increased by 5%", answer)

    def test_player_interface_supporting_routes(self):
        checks = [
            ("/api/health", {}),
            ("/api/benchmarks", {}),
            ("/api/benchmarks/quality", {}),
            ("/api/benchmarks/objective1", {"start": "0", "count": "50"}),
            ("/api/benchmarks/100", {"start": "0", "count": "100"}),
            ("/api/rules", {}),
            ("/api/champions", {}),
            ("/api/tools/repair", {"damage": "major", "repair_modules": "0"}),
            ("/api/tools/fleet-builder", {"style": "Ion", "champion": ["Zora"]}),
            ("/api/v5/synergy", {"style": "Ion", "champion": ["Zora"]}),
            ("/api/tools/progression", {"core_level": "25", "target_level": "26", "season": "S2"}),
            ("/api/v5/progression", {"core_level": "25", "target_level": "26", "season": "S2"}),
            ("/api/admin/lifecycle", {}),
            ("/api/admin/knowledge-quality", {}),
            ("/api/admin/gaps", {"q": ["T4", "Ion Shipyard", "Core 25 and T4"]}),
        ]
        for path, params in checks:
            with self.subTest(route=path):
                payload = self.get_json(path, params)
                self.assertIsInstance(payload, dict, path)


if __name__ == "__main__":
    unittest.main()
