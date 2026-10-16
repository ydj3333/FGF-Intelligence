"""Verify deployed FGF L0-L6 logging through safe public smoke requests."""
from __future__ import annotations

import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE_URL = os.getenv("FGF_PUBLIC_BASE_URL", "https://fgf-intelligence.onrender.com").rstrip("/")
DEADLINE_SECONDS = int(os.getenv("FGF_DEPLOY_WAIT_SECONDS", "600"))


def get_json(path: str, timeout: int = 45) -> tuple[int, dict]:
    request = Request(BASE_URL + path, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"body_excerpt": raw[:300]}
    except URLError as exc:
        return 0, {"error": str(exc.reason)[:300]}


def wait_for_deployed_logging() -> dict:
    deadline = time.monotonic() + DEADLINE_SECONDS
    last_error = None
    while time.monotonic() < deadline:
        status, body = get_json("/api/health", timeout=20)
        if status == 200 and isinstance(body.get("logging"), dict):
            print("logging-aware health endpoint is deployed")
            return body
        last_error = {"http_status": status, "response_keys": sorted(body.keys()), "error": body.get("error")}
        time.sleep(10)
    raise RuntimeError("Timed out waiting for logging-aware deployment: " + json.dumps(last_error))


def main() -> int:
    print("Waiting for the merged release to appear on the public health endpoint...")
    initial = wait_for_deployed_logging()
    print("release=" + str(initial.get("version", "unknown")))

    # L2/L4/L6: safe read-only evidence-backed answer request.
    status, body = get_json("/api/ask?q=energy%20types", timeout=90)
    if status != 200 or not body.get("answer"):
        raise RuntimeError("Ask API smoke test failed: " + json.dumps({"status": status, "keys": sorted(body.keys())}))

    # L5/L6: small deterministic benchmark smoke test, not a substitute for the 50Q gate.
    status, body = get_json("/api/benchmarks/quality", timeout=90)
    if status != 200:
        raise RuntimeError("Quality benchmark smoke test failed: " + json.dumps({"status": status, "keys": sorted(body.keys())}))

    # L1/L3/L6: deliberately unauthenticated request; expected to be rejected
    # before any observation is persisted. This proves rejection-path logging
    # without creating a session or modifying knowledge.
    req = Request(
        BASE_URL + "/api/v63/live/observe",
        data=b"{}",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as response:
            observation_status = response.status
            observation_body = response.read().decode("utf-8", "replace")
    except HTTPError as exc:
        observation_status = exc.code
        observation_body = exc.read().decode("utf-8", "replace")
    if observation_status not in (400, 401, 403):
        raise RuntimeError("Unauthenticated observer probe was not safely rejected: " + str(observation_status))

    # Health response is sampled after all routes have emitted their events.
    time.sleep(1)
    status, final = get_json("/api/health", timeout=30)
    if status != 200 or not isinstance(final.get("logging"), dict):
        raise RuntimeError("Final health/logging status unavailable")
    logging_status = final["logging"]
    required = {"L0", "L1", "L2", "L3", "L4", "L5", "L6"}
    observed = set(logging_status.get("observed_levels", []))
    counts = logging_status.get("event_counts", {})
    print(json.dumps({
        "release": final.get("version"),
        "required_levels": sorted(required),
        "observed_levels": sorted(observed),
        "event_counts": counts,
        "observation_probe_http_status": observation_status,
        "all_levels_observed": logging_status.get("all_levels_observed"),
        "counter_scope": logging_status.get("counter_scope"),
    }, indent=2))
    missing = required - observed
    if missing or not logging_status.get("all_levels_observed"):
        raise RuntimeError("Missing runtime logging levels: " + ", ".join(sorted(missing)))
    if any(int(counts.get(level, 0)) < 1 for level in required):
        raise RuntimeError("At least one required level has no runtime event")
    print("PASS: all seven logging levels observed in deployed runtime.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("FAIL: " + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        raise SystemExit(1)
