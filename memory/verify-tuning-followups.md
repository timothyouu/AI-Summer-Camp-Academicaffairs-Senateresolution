---
name: verify-tuning-followups
description: Deferred perf/quality follow-ups on the chat pipeline (latency, over-detection) — MVP works, these are next
metadata:
  type: project
---

Live chat works end-to-end (~36s/question, 2026-07-16) but two known follow-ups were deliberately deferred for the MVP — suggest, don't auto-apply:

1. **Latency ~36s — Haiku split now BUILT (2026-07-16), opt-in, not yet live-verified.** Four sequential Bedrock stages: retrieve ~3s, extract ~8s, detect ~9s, verify ~15s (capped 6, parallel), synthesis ~7s. The lever is now wired: set `BEDROCK_FAST_MODEL_ID` (e.g. `us.anthropic.claude-haiku-4-5-20251001-v1:0`) and the mechanical JSON stages (extract/detect/verify via `pipeline.llm`) use the fast model while prose (synthesis + draft revision via new `pipeline.synthesis_llm`) stays on `BEDROCK_MODEL_ID`. **Unset = byte-for-byte identical to today** (both LLMs are the same instance). Expected 36s → ~15-20s but UNMEASURED live. Tests: `test_factory_generation_gate.py` (175 backend total). To try live: add `$env:BEDROCK_FAST_MODEL_ID=...` to the runbook launch, POST a question, compare wall-clock. Watch answer quality — Haiku extract/detect could change which conflicts surface.

2. **Over-detection (the deeper issue).** 35 claims → **213 contradictions** flagged for one question — far too many for a corpus that mostly agrees. `MAX_VERIFIED_CONTRADICTIONS=6` (pipeline.py) makes it fast and the *answer* correct, but the conflict flag is built from likely-noisy candidates and real conflicts could rank below the cap. Investigate the detector prompt/pairing in `AgentPipeline._detect` before trusting conflict output in production. Fine for the demo.

Also: streaming the synthesis would cut *perceived* latency a lot (text at ~2s) without touching accuracy — frontend + endpoint work.

See [[live-bedrock-runbook]]. All fixes committed on branch `lambda-variance-spec` (commits 3657ef4, cc569b2).
