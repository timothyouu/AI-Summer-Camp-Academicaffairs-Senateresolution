from __future__ import annotations

from typing import Any
from urllib.parse import unquote_plus

from backend.app.config import MAX_UPLOAD_BYTES, get_settings
from backend.app.stores import upload_store


def handler(event: dict[str, Any], context: object) -> dict[str, int]:
    del context
    settings = get_settings()
    if not settings.retrieval_aws:
        raise RuntimeError("AWS_REGION and BEDROCK_KB_ID are required")
    import boto3  # type: ignore[import-not-found]
    bedrock: Any = boto3.client("bedrock-agent", region_name=settings.aws_region)
    store = upload_store()
    uploads: list[tuple[str, str]] = []
    rejected = 0
    for record in event.get("Records", []):
        s3_object = record["s3"]["object"]
        upload_id, filename = _upload_from_key(str(s3_object["key"]))
        # Presigned PUT URLs cannot carry a size policy, so the local
        # MAX_UPLOAD_BYTES limit is enforced here from the event's object size
        # before any ingestion job is started.
        if int(s3_object.get("size", 0)) > MAX_UPLOAD_BYTES:
            # Remove the object too: the KB data source includes uploads/, so a
            # leftover oversized file would ride along with the next sync.
            bucket_name = str(record["s3"].get("bucket", {}).get("name", ""))
            if bucket_name:
                boto3.client("s3", region_name=settings.aws_region).delete_object(
                    Bucket=bucket_name, Key=unquote_plus(str(s3_object["key"])),
                )
            store.register(filename, "failed", upload_id=upload_id, error=f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB upload limit")
            rejected += 1
            continue
        uploads.append((upload_id, filename))
    if not uploads:
        return {"processed": rejected}
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
            for upload_id, filename in uploads:
                store.register(filename, "failed", upload_id=upload_id, error=str(error) or error.__class__.__name__)
            raise
        for upload_id, filename in uploads:
            # Status polling may have already started a job for this upload;
            # overwriting its record would orphan the active job id.
            existing = store.get(upload_id)
            if existing is not None and existing.status == "ingesting" and existing.ingestion_job_id:
                continue
            store.register(filename, "pending", upload_id=upload_id)
        return {"processed": len(uploads) + rejected}
    for upload_id, filename in uploads:
        store.register(filename, "ingesting", upload_id=upload_id, ingestion_job_id=job_id)
    return {"processed": len(uploads) + rejected}


def _upload_from_key(encoded_key: str) -> tuple[str, str]:
    parts = unquote_plus(encoded_key).split("/")
    if len(parts) < 3 or parts[0] != "uploads" or not parts[1] or not parts[-1]:
        raise ValueError("S3 upload key must have the form uploads/{upload_id}/{filename}")
    return parts[1], parts[-1]


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
