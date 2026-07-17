"""Diagnose why chat answers fall back to the safe message.

Run this in the SAME environment your server/Lambda runs in (not a shell that
injects Bedrock credentials for you). It checks, in order:

  1. Is BEDROCK_KB_ID set (authoritative path on)?
  2. Which generation seam is selected (Strands vs boto3 converse)?
  3. Are AWS credentials resolvable?
  4. Does a real Bedrock ``converse`` call succeed for the configured model/region?

Any failure here is the reason the app returns
"I found related policy sources but can't confidently summarize an answer...".

Usage:
    python -m backend.scripts.diagnose_bedrock
"""

from __future__ import annotations

import os


def main() -> int:
    from backend.app.config import get_settings

    settings = get_settings()
    print("== Configuration ==")
    print(f"BEDROCK_KB_ID   : {settings.bedrock_kb_id or '<UNSET>'}")
    print(f"AWS_REGION      : {settings.aws_region or os.getenv('AWS_REGION') or '<UNSET>'}")
    print(f"AWS_PROFILE     : {settings.aws_profile or '<UNSET>'}")
    print(f"BEDROCK_MODEL_ID: {settings.bedrock_model_id}")
    print(f"guardrail set   : {settings.guardrails_aws}")

    if not settings.retrieval_aws:
        print("\nRESULT: BEDROCK_KB_ID is not set -> pipeline stays LOCAL, generation")
        print("        is disabled by design. Set BEDROCK_KB_ID to enable answers.")
        return 1

    from backend.app.agents.factory import strands_available

    print(f"\nstrands installed: {strands_available()}")
    seam = "StrandsLLM" if strands_available() else "BedrockConverseLLM (boto3 converse)"
    print(f"generation seam : {seam}")

    print("\n== AWS credentials ==")
    try:
        import boto3

        creds = boto3.Session(profile_name=settings.aws_profile).get_credentials()
        if creds is None:
            print("RESULT: No AWS credentials resolvable in this environment.")
            print("        boto3 will raise NoCredentialsError -> safe fallback message.")
            print("        Fix: configure credentials (aws configure / SSO / instance role).")
            return 1
        print("credentials     : resolved OK")
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT: credential lookup failed: {type(exc).__name__}: {exc}")
        return 1

    print("\n== Live Bedrock converse ==")
    try:
        client = boto3.client("bedrock-runtime", region_name=settings.aws_region)
        response = client.converse(
            modelId=settings.bedrock_model_id,
            messages=[{"role": "user", "content": [{"text": "Reply with the word OK."}]}],
            inferenceConfig={"maxTokens": 20, "temperature": 0.0},
        )
        text = response["output"]["message"]["content"][0]["text"]
        print(f"converse OK     : {text!r}")
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT: converse FAILED: {type(exc).__name__}: {exc}")
        print("\n        Common causes:")
        print("        - AccessDeniedException  -> enable model access in the Bedrock console")
        print(f"                                   for {settings.bedrock_model_id} in {settings.aws_region}")
        print("        - ResourceNotFound / ValidationException -> wrong model id or region")
        print("        - ExpiredToken / Unauthorized -> refresh credentials")
        print("        Set BEDROCK_MODEL_ID to a model your account has enabled if needed.")
        return 1

    # The stage the earlier version never tested: the live KB retrieve() call.
    # This is where a hang/stall most plausibly originates for a specific query.
    print(f"\n== Live KB retrieve (mode={settings.bedrock_kb_search_mode}) ==")
    import time

    from backend.app.retrieval import search

    question = os.getenv(
        "DIAGNOSE_QUESTION",
        "Can a newly hired probationary faculty member request service credit during the first three months",
    )
    print(f"query           : {question!r}")
    try:
        t0 = time.time()
        results = search(question, k=12)
        elapsed = time.time() - t0
        print(f"retrieve OK     : {len(results)} passage(s) in {elapsed:.2f}s")
        distinct = sorted({r.source for r in results})
        print(f"distinct sources: {len(distinct)} -> {distinct}")
        if not results:
            print("\nRESULT: KB returned ZERO passages for this query. The pipeline then has")
            print("        nothing to ground on -> abstains / safe message. Check the KB is")
            print("        synced/ingested and that this topic exists in the corpus.")
            return 1
        print("\nRESULT: Full retrieval path works for this question. Retrieval, credentials,")
        print("        and generation are all healthy -> the earlier no-response was the")
        print("        unbounded-timeout hang (now fixed) or a transient stall. Re-run chat;")
        print("        if it still fails, capture the server WARNING with exc_info.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"RESULT: KB retrieve FAILED: {type(exc).__name__}: {exc}")
        print("\n        This is almost certainly what caused the no-response/hang.")
        print("        - ValidationException 'managed knowledge base' -> set BEDROCK_KB_SEARCH_MODE=managed")
        print("        - AccessDenied / ResourceNotFound -> KB id/region/permissions")
        print("        - ReadTimeout -> KB is slow/stalled (now bounded; was the ~5-min hang)")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
