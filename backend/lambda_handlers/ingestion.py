from __future__ import annotations

from typing import Any
from urllib.parse import unquote_plus

from backend.app.config import get_settings
from backend.app.stores import upload_store


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    del context
    settings = get_settings()
    if not settings.retrieval_aws:
        raise RuntimeError("AWS_REGION and BEDROCK_KB_ID are required")
    import boto3  # type: ignore[import-not-found]
    bedrock = boto3.client("bedrock-agent", region_name=settings.aws_region)
    processed = 0
    for record in event.get("Records", []):
        key = unquote_plus(str(record["s3"]["object"]["key"]))
        filename = key.rsplit("/", 1)[-1]
        store = upload_store()
        try:
            response = bedrock.start_ingestion_job(knowledgeBaseId=settings.bedrock_kb_id, dataSourceId=_data_source_id(settings.bedrock_kb_id, settings.aws_region))
            job_id = str(response.get("ingestionJob", {}).get("ingestionJobId", ""))
            store.register(filename, "ingesting", upload_id=filename)
        except Exception:
            store.register(filename, "failed", upload_id=filename)
            raise
        processed += 1
    return {"processed": processed}


def _data_source_id(knowledge_base_id: str, region: str | None) -> str:
    import boto3  # type: ignore[import-not-found]
    client = boto3.client("bedrock-agent", region_name=region)
    response = client.list_data_sources(knowledgeBaseId=knowledge_base_id, maxResults=10)
    sources = response.get("dataSourceSummaries", [])
    if not sources:
        raise RuntimeError("Knowledge Base has no data source")
    return str(sources[0]["dataSourceId"])
