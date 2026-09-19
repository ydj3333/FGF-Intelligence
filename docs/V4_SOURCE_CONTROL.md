# FGF V4 — Source & Plugin Control Master

## Objective
Build an evidence-first, version-aware FGF intelligence system at the 0.01% target. The system must continuously acquire, compare, classify, preserve, test and reuse text, images, video and structured game data.

## System of record
- **Notion:** human evidence control, claim verification, conflict decisions, source registry, operating standards and change history.
- **GitHub:** version-controlled code, schemas, reproducible machine-readable release snapshots and tests.
- **Supabase:** persistent learning/data store for evidence metadata, candidate knowledge, formulas, simulations, benchmark Q&A, media metadata, ingestion runs and evaluation results. Provisioning is still required before production use.
- **Public FGF app:** player-facing answers/calculators/builders/recommendations only; never canonical truth storage.

## Tools and control boundaries
| Tool | Primary responsibility | Secondary/overlap | Truth authority |
|---|---|---|---|
| Notion | evidence/control/admin review | documentation | human verification record |
| GitHub | code/data versioning | reproducible snapshots | release integrity |
| Supabase | persistent learning database | query/analytics | storage, not truth authority |
| Firecrawl | broad web search/crawl/extraction/change monitoring | discovery | source acquisition only |
| TinyFish | interactive/dynamic browser acquisition | discovery/verification | source acquisition only |
| Web search | independent discovery/cross-check | source discovery | source acquisition only |
| LLM | synthesis, hypothesis generation, Q&A generation | reasoning | never autonomous canonical authority |

## Source coverage
1. FGF Wiki / Encyclopedia Galactica / calculators
2. FGF Fandom/community wiki
3. Official FGF portal, news, guides and patch information
4. Official social media: X, Facebook, Instagram, TikTok, YouTube
5. Official Discord and accessible community Discord material
6. Reddit and player posts/comments
7. YouTube videos and playlists, including gameplay/testing/bug/event demonstrations
8. Steam, Google Play, Apple App Store and update history
9. Third-party guides and specialist gaming sites
10. User-supplied screenshots, videos, observations and calculations

## Evidence hierarchy
- **T1:** direct current in-game evidence; exact visible proposition only
- **T2:** official game/portal/patch/developer communications
- **T3:** strong tested technical/community evidence
- **T4:** creator/video/written guides
- **T5:** meta opinions/recommendations
- **T6:** rumours/unverified

Images and videos inherit their tier from what they actually establish. A video can be T1 if it directly demonstrates current in-game state, but commentary around it is not automatically T1.

## Required media fields
`media_id`, `source_url`, `media_type`, `creator`, `published_at`, `acquired_at`, `game_version`, `season`, `server_scope`, `timestamp_or_frame`, `ocr_text`, `transcript_ref`, `visual_claims`, `content_hash`, `duplicate_group`, `tier`, `confidence`, `status`.

## Learning lifecycle
`discover → acquire → fingerprint → deduplicate → OCR/transcribe → extract atomic claims → classify evidence/version → cross-check → calculate/infer → detect conflicts → candidate layer → benchmark Q&A → evaluate → admin review → promote/supersede → release snapshot`

## Canonical safety rules
1. Never silently overwrite old knowledge.
2. Never promote a recommendation into a mechanic.
3. Never promote an inference into T1 without direct supporting evidence.
4. Preserve season/version/server scope.
5. Preserve conflicting evidence and competing hypotheses.
6. Candidate/adaptive data may inform answers with an explicit provisional label.
7. Every promoted claim retains provenance and change history.
8. Every important formula must have evidence, assumptions and regression tests.
9. Search/crawl/API failures must be recorded rather than interpreted as absence of information.
10. Multiple tools may perform the same task; keep provenance and compare outputs.

## Current live discovery monitor
Firecrawl monitor: `01a0a780-e7ea-737c-b09f-43b5e0a28d52`
- Name: FGF V4 Discovery — 6h
- Schedule: every 6 hours
- Time zone: Asia/Kolkata
- Scope: S2/patches/events/mechanics/resource-power formulas/bugs/fixes/guides/testing/videos/official announcements
- Retention: 30 days
- This monitor detects changes; it does not itself promote facts into canonical knowledge.

## Initial source discoveries (2026-09-16)
- Official portal: https://www.foundation.game/en
- Official news: https://www.foundation.game/en/news
- Official X: https://x.com/FoundationGF_EN
- Official Instagram: https://www.instagram.com/foundation_gf_en/
- Official YouTube: https://www.youtube.com/@Foundation_GalacticFrontier
- Official Discord: https://discord.gg/GrndnDvBPS
- Official/alternate Discord surfaced in discovery: https://discord.com/invite/X4xMWpargF
- FGF Wiki: https://fgfwiki.com/
- FGF Fandom: https://foundation-galactic-frontier.fandom.com/wiki/Foundation:_Galactic_Frontier_Wiki
- Reddit: https://www.reddit.com/r/FoundationGFrontier/
- Steam: https://store.steampowered.com/app/4223760/Foundation_Galactic_Frontier/
- Google Play: https://play.google.com/store/apps/details?id=com.games.foundation

## Important current observation
The official site currently exposes a Sep 9, 2026 item titled `Epoch of Fusion Seed — LV35 Buildings & 4th Battle Queue`. Official social discovery also exposes S2 rollout information, including server-specific scheduling. These are high-priority ingestion targets because they are current/version-sensitive.

## Next implementation gate
Provision Supabase, then implement ingestion tables and media/evidence pipelines. Until then, GitHub remains the reproducible release store and Notion remains the human control room.

## Global monitoring and season model — mandatory
The acquisition scope is **the whole game**, not S2. Every 6-hour cycle must check all registered source families for meaningful changes. **S1 is the baseline for new servers; S2/S3/future seasons are overlays tied to server age/week, season, game version and event window.** A seasonal finding must never be generalized to all servers.

### Zero-paid-first acquisition budget
- Recurring paid Firecrawl monitoring is currently **disabled** to protect the free-first target.
- The active design is a 6-hour orchestration cycle using free/native discovery and independent cross-checks first.
- Firecrawl/TinyFish are reserved for targeted deep acquisition, dynamic pages or sources that cannot be reliably acquired through the free path. Any metered use is recorded and budget-controlled.
- Deduplicate/fingerprint before OCR, transcription, browser automation or other metered work.
- Supabase project **FGF Intelligence V4** is provisioned in **ap-south-1** at **$0/month project cost** according to the current cost check.

### Uniform control names
Use these identifiers everywhere — Notion, GitHub, Supabase, automation logs and plugin records:
- **FGF V4 — Global Source Discovery — 6h** = acquisition cycle
- **FGF V4 — Source & Plugin Control Master** = master governance document
- **FGF V4 — Learning Laboratory** = Supabase persistent learning/data layer
- **FGF V4 — Evidence Promotion Pipeline** = candidate → verification → canonical workflow

### 6-hour source families
Each cycle checks, where accessible: FGF Wiki/Encyclopedia, Fandom, official portal/news/guides, official social accounts, official/community Discord, Reddit/player posts, YouTube/videos/playlists, Steam/store metadata, third-party guides/forums, and user evidence. Results are tagged by season/server/version and classified T1–T6. Images/video are first-class evidence, not leftovers.

### Redundancy rule
When two or three acquisition paths can cover the same source, use independent paths where practical, compare provenance and content, preserve disagreements, and use the strongest supported evidence. Redundancy does not mean duplicating expensive work.
