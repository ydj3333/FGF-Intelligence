import json

from canonical_query_coverage import (
    build_query_cases,
    load_canonical_claims,
    run_coverage_benchmark,
)


def test_canonical_query_case_generation_is_deterministic():
    claims = load_canonical_claims()
    first = [(x["entity"], x["intent"], x["query"]) for x in build_query_cases(claims)]
    second = [(x["entity"], x["intent"], x["query"]) for x in build_query_cases(claims)]
    assert first == second
    assert first


def test_supported_specialized_queries_are_not_invented():
    claims = [
        {
            "Claim": "Weapon Prisms are obtained through the Intel Shop.",
            "Evidence Tier": "Tier 1 — Ultimate/Official",
            "Status": "Confirmed",
        },
        {
            "Claim": "Commerce Guild rewards changed in the September 22, 2026 hot update.",
            "Evidence Tier": "Tier 2 — Official Developer",
            "Status": "Current",
        },
        {
            "Claim": "Shadowfront contains 8 Lesser Vaults.",
            "Evidence Tier": "Tier 1 — Ultimate/Official",
            "Status": "Confirmed",
        },
    ]
    cases = build_query_cases(claims)
    by_intent = {(c["entity"], c["intent"]) for c in cases}
    assert ("weapon prisms", "source") in by_intent
    assert ("commerce guild", "update") in by_intent
    assert ("commerce guild", "numeric") not in by_intent
    assert ("shadowfront", "numeric") in by_intent


def test_canonical_coverage_has_zero_retrieval_failures():
    claims = load_canonical_claims()
    report = run_coverage_benchmark(claims)
    assert report["entity_count"] > 0
    assert report["case_count"] >= report["entity_count"]
    assert report["failed"] == 0, (
        "Canonical query coverage regression:\n"
        + json.dumps(report["failures"][:20], indent=2)
    )


def test_specialized_cases_require_entity_local_relations():
    claims = [
        {
            "Claim": "Weapon Prisms are listed in the Discount Shop. The Commerce Guild has permanent rewards.",
            "Evidence Tier": "Tier 1 — Ultimate/Official",
            "Status": "Confirmed",
        },
    ]
    cases = build_query_cases(claims)
    by_intent = {(c["entity"], c["intent"]) for c in cases}
    assert ("weapon prisms", "source") not in by_intent
    assert ("discount shop", "source") not in by_intent
    assert ("commerce guild", "event") not in by_intent


def test_numeric_case_uses_the_canonical_cardinality_object():
    claims = [
        {
            "Claim": "Shadowfront contains 8 Lesser Vaults and 2 Central Vaults.",
            "Evidence Tier": "Tier 1 — Ultimate/Official",
            "Status": "Confirmed",
            "Category": "Events",
        },
    ]
    cases = build_query_cases(claims)
    numeric = [c["query"] for c in cases if c["intent"] == "numeric"]
    assert numeric
    assert any("lesser vaults" in q for q in numeric)
    assert any("shadowfront" in q for q in numeric)


if __name__ == "__main__":
    claims = load_canonical_claims()
    report = run_coverage_benchmark(claims)
    print(json.dumps(report, indent=2))
