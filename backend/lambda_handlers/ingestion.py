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
    bedrock: Any = boto3.client("bedrock-agent", region_name=settings.aws_region)
    filenames = [
        unquote_plus(str(record["s3"]["object"]["key"])).rsplit("/", 1)[-1]
        for record in event.get("Records", [])
    ]
    if not filenames:
        return {"processed": 0}
    store = upload_store()
    data_source_id = _data_source_id(bedrock, str(settings.bedrock_kb_id))
    try:
        response = bedrock.start_ingestion_job(
            knowledgeBaseId=settings.bedrock_kb_id, dataSourceId=data_source_id,
        )
        job_id = str(response.get("ingestionJob", {}).get("ingestionJobId", ""))
        if not job_id:
            raise RuntimeError("Bedrock did not return an ingestion job ID")
    except Exception as error:
        if not _is_concurrent_ingestion_error(error):
            for filename in filenames:
                store.register(filename, "failed", upload_id=filename)
            raise
        job_id = _active_ingestion_job_id(bedrock, str(settings.bedrock_kb_id), data_source_id)
    for filename in filenames:
        store.register(filename, "ingesting", upload_id=filename, ingestion_job_id=job_id)
    return {"processed": len(filenames)}


def _data_source_id(client: Any, knowledge_base_id: str) -> str:
    response = client.list_data_sources(knowledgeBaseId=knowledge_base_id, maxResults=10)
    sources = response.get("dataSourceSummaries", [])
    if not sources:
        raise RuntimeError("Knowledge Base has no data source")
    return str(sources[0]["dataSourceId"])


def _is_concurrent_ingestion_error(error: Exception) -> bool:
    response = getattr(error, "response", {})
    details = response.get("Error", {}) if isinstance(response, dict) else {}
    code = str(details.get("Code", "")) if isinstance(details, dict) else ""
    message = str(details.get("Message", "")).lower() if isinstance(details, dict) else ""
    concurrent_job_markers = (
        "concurrent" in message,
        "already running" in message,
        "active ingestion job" in message,
        "another ingestion job" in message,
    )
    return code in {"ConflictException", "ValidationException"} and any(concurrent_job_markers)


def _active_ingestion_job_id(client: Any, knowledge_base_id: str, data_source_id: str) -> str:
    response: dict[str, Any] = client.list_ingestion_jobs(
        knowledgeBaseId=knowledge_base_id, dataSourceId=data_source_id, maxResults=100,
    )
    summaries = response.get("ingestionJobSummaries", [])
    for summary in summaries:
        if str(summary.get("status", "")) in {"STARTING", "IN_PROGRESS"}:
            job_id = str(summary.get("ingestionJobId", ""))
            if job_id:
                return job_id
    raise RuntimeError("Bedrock reported a concurrent ingestion job but no active job was found")
