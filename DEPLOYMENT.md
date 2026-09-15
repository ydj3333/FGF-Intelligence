# FGF Agent v2 — Deployment

## GitHub
Create/connect the FGF repository and push this project to the default branch.

## Render
The included `render.yaml` and `Dockerfile` are ready for a web service deployment. Set the service health check to `/api/health`.

## Production hardening before public launch
- Add persistent database/search index.
- Add authenticated Admin API for claim decisions.
- Add LLM synthesis only after retrieval; never let the LLM invent evidence.
- Add automated tests for all Tier-1 conflict rules.
- Add rate limiting and logging.
- Add current-version/source refresh jobs.
- Keep evidence/admin endpoints private; public users get read/query access.
