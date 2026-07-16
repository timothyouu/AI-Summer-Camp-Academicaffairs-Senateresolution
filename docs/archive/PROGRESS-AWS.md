2026-07-15T01:29:15-07:00 G3 sonnet hit — infra/ CDK stack, py_compile clean, README deploy steps verified
2026-07-15T01:30:35-07:00 G1 codex-sol hit — dual-mode backend connectors, 12 pytest passed in orchestrator shell
2026-07-15T01:30:35-07:00 G4 codex-terra hit — trace panel, upload polling, Cognito PKCE flow; tsc+build clean
2026-07-15T01:44:22-07:00 G2 codex-sol hit — 6-agent pipeline, 17 pytest passed, both endpoints smoke-tested with full trace
2026-07-15T01:55:44-07:00 review fixes hit — upload contract routes (19 pytest), Lambda bundling, CORS context param
2026-07-15T02:02:51-07:00 review round-2 fixes hit — auth header, Cognito callbacks, DDB S-keys, ingestion terminal status (22 pytest)
2026-07-15T06:27:40-07:00 review round-3 fixes hit — reviewer-only mutations, ingestion job coalescing, DDB conditional update (26 pytest)
2026-07-15T06:31:22-07:00 review round-4 fixes hit (inline) — agent-endpoint timeouts, DDB scan pagination (27 pytest)
2026-07-15T06:35:18-07:00 review round-5 fixes hit — Lambda /tmp data root (inline), configured-API failure surfacing, bounded status polling
2026-07-15T06:42:07-07:00 review round-6 fixes hit — reviewer authz on uploads/resolution (inline, 29 pytest), Cognito login gate, ingestion IAM grants
2026-07-15T06:52:42-07:00 review round-7 fixes hit — unique upload ids + pending/retry lifecycle (sol), Function URL for agent endpoints (opus); 39 pytest, tsc/build, py_compile
2026-07-15T06:54:58-07:00 review round-8 fixes hit (inline) — Strands message text extraction, uploads/ S3 notification filter (40 pytest)
2026-07-15T06:58:04-07:00 review round-9 fixes hit (inline) — corpus bucket CORS for browser PUT, idempotent conflict create race (41 pytest)
2026-07-15T07:06:48-07:00 review round-10 fixes hit — app-wide Cognito auth middleware (inline), KB-backed topics (sol); 46 pytest
2026-07-15T07:09:28-07:00 review round-11 fixes hit (inline) — event-size upload limit, bearer token on same-backend PUT (47 pytest)
2026-07-15T07:12:10-07:00 review round-12 — ingesting-record preservation fixed (inline); JWT-500 finding verified false positive, pinned with 401 regression tests (51 pytest)
2026-07-15T07:14:48-07:00 review round-13 fix hit (inline) — oversized uploads deleted from S3 before rejection + grant_delete (51 pytest)
2026-07-15T07:17:46-07:00 review round-14 fix hit (inline) — AOSS index creation retries with backoff, provider timeout 10m
2026-07-15T09:34:00-07:00 review round-15 codex-terra hit — Cognito direct-route role enforcement and reviewer-only conflict-log access; 52 pytest, tsc/build clean
2026-07-15T09:34:00-07:00 review round-16 codex-sol hit — Strands extractor isolation, Cognito logout/role UX, and AWS handoff fixes; 53 pytest, tsc/build, infra py_compile, diff check clean
2026-07-15T09:52:30-07:00 review round-17 codex-terra hit — corpus prefix/metadata staging, DynamoDB seeding, and Amplify monorepo/SPA handoff; infra helper tests and diff check clean
2026-07-15T09:52:30-07:00 review round-18 codex-sol hit — authoritative grounded Strands outputs, shared Cognito role sync, terminal ingestion states, and combined Phase A-C gate; 57 pytest, 2 infra tests, tsc/build, py_compile, corpus dry-run, diff check clean
2026-07-15T15:44:38-07:00 implementation3 T1 hit — source registry and archive/activate lifecycle verified; commit 633fa3a
2026-07-15T15:44:38-07:00 implementation3 T2 hit — registry-aware archive filtering and 0.5 archived-edition weighting verified; commit 725571f
2026-07-15T15:44:38-07:00 implementation3 T3 hit — per-source-type permission store and upload enforcement verified; commit bf5e938
2026-07-15T15:44:38-07:00 implementation3 T4 hit — role-shaped conflict visibility verified; commit 61a7593
2026-07-15T15:44:38-07:00 implementation3 T5 hit — AI-assisted drafting loop and versioned draft store verified; commit bb23b4c
2026-07-15T15:44:38-07:00 implementation3 T6 hit — stdlib catalog scraper and edition-tagged ingestion verified with injected fetcher; live network smoke pending; commit 98fdc80
2026-07-15T15:44:38-07:00 implementation3 T7 hit — frontend identity, role, registry, permission, and drafting API bindings passed strict tsc and production build; commit bc4f199
2026-07-15T15:44:38-07:00 implementation3 T10 hit — persisted dark mode, shared back buttons, and emblem-to-login navigation passed strict tsc and production build; commit 1068a7d
2026-07-15T15:44:38-07:00 implementation3 T11 hit — three DynamoDB tables, catalog scraper Lambda, env wiring, IAM grants, py_compile, and infra tests verified; commit 3707d57
2026-07-15T15:56:00-07:00 implementation3 T8 hit — Sources archive lifecycle, upload-processing continuity, and permission panel passed 81 backend tests, strict tsc/build, and browser archive/unarchive plus permission-reload checks; commit 25bc50f
2026-07-15T15:56:00-07:00 implementation3 integration fix — registry startup reseeding now preserves catalog edition metadata; regression test added; commit 89870df
2026-07-15T15:56:00-07:00 implementation3 integration fix — frontend trace mappings accept backend citations=null; resolution and drafting browser flows restored; commit 6476a93
2026-07-15T15:56:00-07:00 implementation3 T9 hit — reviewer Draft Assistant, adopt/re-check loop, shared resource catalog, reviewer/employee visibility, and canonical links verified in browser; commit 0c02e1b
2026-07-15T15:56:00-07:00 implementation3 catalog live smoke hit — current 2026 catalog scraped 15 pages/89 chunks; archived 2024–2025 catalog scraped 15 pages/83 chunks; isolated registries confirmed active current/non-current metadata
2026-07-15T16:18:31-07:00 implementation3 consolidated review hit — fixed AWS catalog packaging/metadata and registry seeding, Bedrock filename lifecycle matching, local reviewer authorization, Cognito chat CORS, and concurrent DynamoDB draft versioning; 87 backend tests, strict tsc/build, 3 infra tests, py_compile, Lambda handler import, and diff check passed; commit 25bc582
2026-07-16T06:45:00-07:00 conformance-G1 codex hit — drafting llm_revision routed through pipeline.llm (was module generate, always raised -> silent deterministic fallback); 109 pytest
2026-07-16T06:45:00-07:00 conformance-G2 codex hit (1 rerun for tests/env) — Bedrock Guardrails: CfnGuardrail+Version per Notion §9, BEDROCK_GUARDRAIL_ID gating, StrandsLLM BedrockModel; 112 pytest
2026-07-16T06:45:00-07:00 conformance-G3 inline hit — FRONTEND_ORIGINS CORS knob (was hardcoded localhost:5173/5174); verified live: access-control-allow-origin: http://localhost:5175
2026-07-16T06:45:00-07:00 conformance-G4 inline hit — role switcher desync fixed (setDemoIdentity); employee->Policy Maker view now 0 console errors, permissions table populates
2026-07-16T06:45:00-07:00 conformance-verify hit — 112 pytest / tsc clean / vite build; both roles clicked through all routes; PRD calibration #2 passes; service-credit "align" confirmed deliberate
2026-07-16T06:50:00-07:00 conformance-G5 inline hit — registry source_type: _SEED_TYPE_BY_STEM mirrors prepare_corpus taxonomy (was all "uploads"); live 3 handbook/3 cba/3 policystat/7 uploads; 113 pytest
