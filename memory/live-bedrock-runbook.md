---
name: live-bedrock-runbook
description: How to run the app against the live Bedrock KB (managed mode, env vars, the stale-code trap)
metadata:
  type: project
---

Running chat against the live Bedrock Knowledge Base (verified working 2026-07-16, ~36s/question).

**KB `HFZTQXXMHJ` is a MANAGED KB** — you MUST set `BEDROCK_KB_SEARCH_MODE=managed` or retrieval throws a ValidationException on every request (current code retries once as managed, but set it to avoid the wasted round-trip).

Launch (PowerShell, same shell as the env vars):
```
$env:AWS_REGION = "us-west-2"
$env:AWS_PROFILE = "csub-policy"
$env:BEDROCK_KB_ID = "HFZTQXXMHJ"
$env:BEDROCK_KB_SEARCH_MODE = "managed"
python -m uvicorn backend.app.main:app --port 8000
```
Health check (GET, browser-safe): http://127.0.0.1:8000/api/health
Diagnose failures: `python -m backend.scripts.diagnose_bedrock` (tests creds, converse, AND live KB retrieve).

**The stale-code trap that cost hours (2026-07-16):** a hung request runs in a background *thread* on a blocking Bedrock socket — CTRL+C cannot kill it, and the old process keeps holding port 8000, so "restarts" launch new procs that never bind. The server image is `python3.13.exe`, not `python.exe` (so `taskkill /IM python.exe` misses it). Kill by PID; confirm `netstat -ano | findstr :8000` is EMPTY before relaunching. Never POST to /api/chat from the same terminal running uvicorn — a stall locks that terminal.

Test the endpoint from a SEPARATE terminal (Invoke-RestMethod with `-TimeoutSec`), never the browser address bar (that's a GET → 405). See [[verify-tuning-followups]].
