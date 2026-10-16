import io
import json
import logging
import unittest
from unittest.mock import patch

from observability.logging_levels import emit, level_catalog, timed_event, set_correlation_id, reset_correlation_id


class LoggingLevelsTests(unittest.TestCase):
    def test_catalog_contains_all_required_levels(self):
        self.assertEqual(set(level_catalog()), {"L0", "L1", "L2", "L3", "L4", "L5", "L6"})
        self.assertEqual([level_catalog()[key] for key in ("L0", "L1", "L2", "L3", "L4", "L5", "L6")], ["project", "observation", "evidence", "learning", "reasoning", "evaluation", "operations"])

    def test_each_level_emits_structured_json(self):
        logger = logging.getLogger("fgf.runtime")
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        logger.addHandler(handler)
        try:
            for level in level_catalog():
                record = emit(level, "test_event", correlation_id="test-correlation", answer_count=3)
                self.assertEqual(record["level"], level)
                self.assertEqual(record["schema"], "fgf.logging.v1")
            lines = stream.getvalue().splitlines()
            self.assertEqual(len(lines), 7)
            self.assertTrue(all(json.loads(line)["schema"] == "fgf.logging.v1" for line in lines))
        finally:
            logger.removeHandler(handler)

    def test_secret_like_fields_are_redacted(self):
        record = emit("L6", "redaction_test", api_key="not-a-real-key", token="do-not-log", path="/api/ask", duration_ms=12.5)
        self.assertEqual(record["api_key"], "[REDACTED]")
        self.assertEqual(record["token"], "[REDACTED]")
        self.assertEqual(record["path"], "/api/ask")
        self.assertEqual(record["duration_ms"], 12.5)

    def test_correlation_context_is_propagated(self):
        token = set_correlation_id("request-123")
        try:
            record = emit("L4", "reasoning_test")
            self.assertEqual(record["correlation_id"], "request-123")
        finally:
            reset_correlation_id(token)

    def test_unknown_level_is_rejected(self):
        with self.assertRaises(ValueError):
            emit("L7", "invalid")

    def test_timed_event_emits_on_success_and_error(self):
        with patch("observability.logging_levels.emit") as mocked:
            with timed_event("L5", "benchmark_test", test_case_count=50):
                pass
            self.assertEqual(mocked.call_args.args[:2], ("L5", "benchmark_test"))
            self.assertEqual(mocked.call_args.kwargs["status"], "ok")
            mocked.reset_mock()
            with self.assertRaises(RuntimeError):
                with timed_event("L5", "benchmark_failure"):
                    raise RuntimeError("expected")
            self.assertEqual(mocked.call_args.kwargs["status"], "error")
            self.assertEqual(mocked.call_args.kwargs["error_type"], "RuntimeError")


if __name__ == "__main__":
    unittest.main()
