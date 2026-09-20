"""Run the Knowledge Analyzer against the repository's current machine-readable corpus."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_analyzer import KnowledgeAnalyzer


def main():
    root = ROOT
    with (root / "data" / "knowledge.json").open(encoding="utf-8") as fh:
        data = json.load(fh)

    claims = data.get("claims", [])
    sources_path = root / "data" / "sources.json"
    sources = []
    if sources_path.exists():
        with sources_path.open(encoding="utf-8") as fh:
            raw = json.load(fh)
            sources = raw if isinstance(raw, list) else raw.get("sources", [])

    analyzer = KnowledgeAnalyzer(claims, sources)
    analyzer.analyze_all()
    summary = analyzer.get_summary()

    print(json.dumps({
        "corpus_generated": data.get("generated"),
        "total_claims": summary["total_claims"],
        "quality_distribution": summary["quality_distribution"],
        "top_issues": summary["top_issues"],
        "average_quality": summary["average_quality"],
        "average_coverage": summary["average_coverage"],
        "average_confidence": summary["average_confidence"],
        "conflict_count": summary["conflict_count"],
        "superseded_count": summary["superseded_count"],
        "current_count": summary["current_count"],
    }, indent=2))


if __name__ == "__main__":
    main()
