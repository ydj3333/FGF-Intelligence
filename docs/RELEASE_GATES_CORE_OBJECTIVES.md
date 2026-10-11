# FGF Intelligence — Core-Objective Release Gates

Last reviewed: 2026-10-11

## Purpose

Prevent regressions from being hidden by a green isolated workflow, a presentation change, or a narrowed test set. A release is not considered verified until the required gates pass on the same candidate commit SHA.

## Non-negotiable intelligence objectives

1. **Canonical core first.** Established current facts from the canonical Core Knowledge layer govern answers. The operating order is Core → validated Experience → YouTube/community fallback.
2. **Evidence authority and traceability.** Preserve source provenance, evidence tier, conflict visibility, and current/historical lifecycle distinctions. Community content is not automatically canonical truth.
3. **Safe uncertainty.** Do not invent exact costs, totals, dates, cooldowns, unlocks, point values, requirements, or reward values. When evidence is insufficient, state that plainly and provide a safe next action.
4. **Original benchmark integrity.** `data/objective_1_benchmark.json` is the original Objective #1 benchmark. Keep all 50 question IDs and their safety constraints. Never weaken assertions, drop cases, or change expected outcomes solely to obtain a green build.
5. **Player-state-aware recommendations.** Honor stated Core level, energy type, roster/champions actually available, inventory/resource constraints, F2P limits, event context, and explicit ambiguity. Do not recommend unavailable heroes as if owned.
6. **Event-first strategy routing.** Recognized event + explicit best/optimal/efficient strategy intent must reach the relevant event strategy handler before generic evidence-option retrieval. Protect T100, GvG, Shadowfront, Paths to Dominance and cross-event resource-reservation behavior.
7. **Fail visibly and safely.** Route exceptions should return useful JSON-safe diagnostics without exposing secrets/stack traces or silently dropping the request.
8. **Learning is not truth.** Observations, feedback and YouTube/community claims do not automatically overwrite canonical facts. Preserve candidate status and require conflict checks/review for promotion.
9. **Operational/privacy constraints.** Respect the two-hour/day live-observation cap, raw-video privacy defaults, and fail-closed handling of unknown screens.
10. **No unverified release claims.** Report test results against exact commit SHAs. A workflow passing on a parent commit does not certify a newer main commit.

## Required release gates

- Compile/import check for changed Python modules.
- Original 50-question interface matrix through `/api/ask`, `/api/recommend`, and `/api/v5/evidence`.
- Explicit uncertainty check for every benchmark item requiring uncertainty, including O1-49 F2P progression with unknown costs.
- Event-strategy regression suite for T100, GvG, Shadowfront, Paths to Dominance and cross-event resource allocation.
- Recommendation regression checks for explicit Core level, ambiguity, and roster/player constraints.
- Evidence Graph and lifecycle/authority tests.
- Corpus/knowledge-quality analysis.
- Visual-answer regressions, ensuring visuals cannot introduce claims unsupported by the answer's evidence.
- For each release candidate, publish workflow name, conclusion, URL and exact head SHA; verify all mandatory checks refer to the intended candidate SHA.

## Current audit snapshot — 2026-10-11

- PR #32 merged at commit `617890e86176c2142e12529d051f6ab165b8bd48`.
- Knowledge Analyzer workflow run `38143016470`: success on merge SHA.
- v6.5 experiential regression workflow run `38143016504`: success on merge SHA.
- Main subsequently advanced to `2940a32b7e781a53a7488c65f77a2dd89d80517d` for a knowledge-manifest sync.
- The green runs above are evidence about the merge SHA, not proof that all gates ran on the newer manifest-sync SHA.
- Tracking issue: https://github.com/ydj3333/FGF-Intelligence/issues/34
- Separate database-security review: https://github.com/ydj3333/FGF-Intelligence/issues/33

## Definition of done

A release is accepted only when all mandatory gates pass on the same release candidate, any failures have been fixed without weakening the objective, latest-source/current-state semantics are preserved, and the exact SHA and workflow evidence are recorded. Database RLS changes must separately demonstrate intended role access and continued ingestion/analysis operation before being accepted.
