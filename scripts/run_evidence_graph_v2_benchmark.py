"""Evidence Graph v2 deterministic benchmark.

Checks entity resolution, explicit relation chains, 2-hop/3-hop completeness,
lifecycle/authority gates, and provenance preservation without any external API.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evidence_graph import EvidenceGraph


def confirmed(claim: str, tier: str = "Tier 1 — Ultimate/Official", status: str = "Confirmed") -> dict:
    return {"Claim": claim, "Evidence Tier": tier, "Status": status}


def run() -> dict:
    checks = []

    graph = EvidenceGraph(
        [confirmed("Energy Core requires Core progression.")],
        alias_groups=[["energy core", "core level"]],
    )
    checks.append(("explicit_entity_alias", bool(graph.outgoing("core level", "requires"))))

    two_hop = EvidenceGraph([
        confirmed("Research Academy requires Energy Core Level 10."),
        confirmed("Energy Core Level 10 can be obtained through Core progression."),
    ])
    paths = two_hop.derive(
        ["Research Academy"],
        ("requires", "obtained_from"),
        max_hops=2,
        require_current=True,
        min_tier_score=2.0,
    )
    checks.append(("complete_two_hop", len(paths) == 1 and len(paths[0]) == 2))

    incomplete = EvidenceGraph([
        confirmed("Research Academy requires Energy Core Level 10."),
    ])
    paths = incomplete.derive(
        ["Research Academy"],
        ("requires", "obtained_from"),
        max_hops=2,
        require_current=True,
        min_tier_score=2.0,
    )
    checks.append(("incomplete_two_hop_abstains", paths == []))

    three_hop = EvidenceGraph([
        confirmed("Research Academy requires Energy Core Level 10."),
        confirmed("Energy Core Level 10 can be obtained through Core progression."),
        confirmed("Core progression is available at Research Academy."),
    ])
    paths = three_hop.derive(
        ["Research Academy"],
        ("requires", "obtained_from", "available_at"),
        max_hops=3,
        require_current=True,
        min_tier_score=2.0,
    )
    checks.append((
        "complete_three_hop_with_provenance",
        len(paths) == 1
        and len(paths[0]) == 3
        and len(three_hop.provenance(paths[0])) == 3,
    ))

    under_review = EvidenceGraph([
        confirmed("Research Academy requires Energy Core Level 10."),
        confirmed(
            "Energy Core Level 10 can be obtained through Core progression.",
            status="Under Review",
        ),
    ])
    paths = under_review.derive(
        ["Research Academy"],
        ("requires", "obtained_from"),
        max_hops=2,
        require_current=True,
        min_tier_score=2.0,
    )
    checks.append(("under_review_link_blocked", paths == []))

    tier3 = EvidenceGraph([
        confirmed("Research Academy requires Energy Core Level 10.", tier="Tier 3 — Community"),
        confirmed("Energy Core Level 10 can be obtained through Core progression.", tier="Tier 3 — Community"),
    ])
    paths = tier3.derive(
        ["Research Academy"],
        ("requires", "obtained_from"),
        max_hops=2,
        require_current=True,
        min_tier_score=2.0,
    )
    checks.append(("low_authority_chain_blocked", paths == []))

    failed = [name for name, ok in checks if not ok]
    return {
        "benchmark": "evidence_graph_v2",
        "cases": len(checks),
        "passed": len(checks) - len(failed),
        "hard_failures": len(failed),
        "entity_resolution_rate": 1.0 if checks[0][1] else 0.0,
        "chain_safety_rate": sum(ok for _, ok in checks[1:]) / max(1, len(checks) - 1),
        "checks": [{"name": name, "passed": ok} for name, ok in checks],
        "hard_failure_details": failed,
    }


if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["hard_failures"]:
        raise SystemExit(1)
