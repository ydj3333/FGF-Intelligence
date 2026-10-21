# FGF AI Agent v8.0 — Integration Candidate

This document accompanies the v8.0 AI-agent integration candidate. It does not by itself activate the agent. The production release must wire the `fgf_agent` modules into the HTTP service, preserve the Core-first evidence policy, and pass the original 50-question release benchmark before deployment.

## Database contract

The live Supabase project `FGF-V4-Intelligence` (`qdoixzfkkmvzjfkhzups`) currently contains 10,051 distinct rows in `public.fgf_question_bank`. Of these, 10,038 remain `needs_review`, 13 are approved, 0 are marked `training_eligible`, and 9,000 are generated paraphrase shells. Treat this table as a retrieval/evaluation corpus, not as 10,051 verified gold answers. For model context, retrieve relevant rows on demand and resolve them to linked `public.claims` plus `public.claim_evidence` / `public.evidence_items`; do not pass the whole table into every prompt or treat generated wording as canonical truth.

## Release gates

- Core → validated Experience → YouTube/community fallback remains unchanged.
- Preserve the original 50-question benchmark and the 10,000-question governed-bank audit.
- Never auto-approve question-bank rows or train model weights from unreviewed rows.
- Keep source tier, lifecycle, season/version, conflicts, and provenance with every retrieved claim.
- Do not deploy until CI passes on the exact candidate SHA, live evaluation passes, and production L0–L6 logging is verified.
- No secrets belong in Git. Configure provider and Supabase server credentials only in the deployment environment.

## Current status

Candidate branch: `feature/fgf-v8-ai-agent-integration`. This file is a guardrail/hand-over note; deployment and full v8 code integration remain pending until the runtime, retrieval adapter, tests, and deployment environment are validated together.
