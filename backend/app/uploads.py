from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status

from .auth import require_reviewer
from .config import MAX_UPLOAD_BYTES, UPLOAD_DIR, ensure_data_directories, get_settings
from .ingest import append_to_index
from .models import IngestionResponse, PresignedUploadRequest, PresignedUploadResponse, UploadResponse
from .retrieval import reload_index
from .stores import UploadRecord, UploadStore, upload_store


router = APIRouter(prefix="/api", tags=["uploads"])
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}
INGESTION_STATUSES = {"pending", "ingesting", "ready", "failed"}


def _safe_filename(filename: str) -> str:
    base = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    if not safe:
        raise ValueError("Invalid filename")
    return safe


@router.post("/upload", response_model=UploadResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...), _: None = Depends(require_reviewer)) -> UploadResponse:
    try:
        filename = _safe_filename(file.filename or "")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, MD, or TXT file")
    settings = get_settings()
    if settings.corpus_aws:
        import boto3  # type: ignore[import-not-found]
        client = boto3.client("s3", region_name=settings.aws_region)
        upload_id = str(uuid4())
        key = f"uploads/{upload_id}/{filename}"
        url = client.generate_presigned_url(
            "put_object", Params={"Bucket": settings.corpus_bucket, "Key": key, "ContentType": file.content_type or "application/octet-stream"},
            ExpiresIn=900,
        )
        upload_store().register(filename, "pending", upload_id=upload_id)
        return UploadResponse(filename=filename, status="pending", chunks_added=0, upload_url=str(url))
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return _save_local_upload(filename, content)


@router.put("/upload", response_model=UploadResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def direct_upload(request: Request, filename: str, _: None = Depends(require_reviewer)) -> UploadResponse:
    try:
        safe_filename = _safe_filename(filename)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if Path(safe_filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, MD, or TXT file")
    content = await request.body()
    return _save_local_upload(safe_filename, content)


def _save_local_upload(filename: str, content: bytes) -> UploadResponse:
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB")
    ensure_data_directories()
    destination = UPLOAD_DIR / filename
    destination.write_bytes(content)
    chunks_added = append_to_index(destination)
    reload_index()
    upload_store().register(filename, "ready", chunks_added, upload_id=filename)
    return UploadResponse(filename=filename, status="ready", chunks_added=chunks_added)


@router.post("/uploads/presign", response_model=PresignedUploadResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def presign_upload(payload: PresignedUploadRequest, request: Request, _: None = Depends(require_reviewer)) -> PresignedUploadResponse:
    try:
        filename = _safe_filename(payload.filename)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, MD, or TXT file")
    settings = get_settings()
    if settings.corpus_aws:
        upload_id = str(uuid4())
        upload_store().register(filename, "pending", upload_id=upload_id)
        import boto3  # type: ignore[import-not-found]
        upload_url = boto3.client("s3", region_name=settings.aws_region).generate_presigned_url(
            "put_object", Params={"Bucket": settings.corpus_bucket, "Key": f"uploads/{upload_id}/{filename}", "ContentType": payload.content_type}, ExpiresIn=900,
        )
        return PresignedUploadResponse(upload_id=upload_id, upload_url=str(upload_url), headers={"Content-Type": payload.content_type})
    upload_id = upload_store().register(filename, "pending", upload_id=filename)
    direct_url = f"{str(request.base_url).rstrip('/')}/api/upload?{urlencode({'filename': filename})}"
    return PresignedUploadResponse(upload_id=upload_id, upload_url=direct_url, headers={})


@router.get("/uploads/{upload_id}", response_model=IngestionResponse, response_model_exclude_none=True)
async def ingestion_status(upload_id: str) -> IngestionResponse:
    store = upload_store()
    record = store.get(upload_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    settings = get_settings()
    if settings.uploads_aws:
        if record.status == "pending" and not record.ingestion_job_id:
            record = _start_aws_ingestion(store, record, settings.bedrock_kb_id, settings.aws_region)
        elif record.status == "ingesting" and record.ingestion_job_id:
            record = _refresh_aws_ingestion_status(store, record, settings.bedrock_kb_id, settings.aws_region)
    if record.status not in INGESTION_STATUSES:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload has an invalid ingestion status")
    return IngestionResponse(
        upload_id=record.upload_id, status=record.status, chunks_added=record.chunks_added, error=record.error,
    )


def _start_aws_ingestion(
    store: UploadStore, record: UploadRecord, knowledge_base_id: str | None, region: str | None,
) -> UploadRecord:
    """Try to give a pending upload its own Bedrock ingestion job."""
    if not knowledge_base_id:
        return record
    import boto3  # type: ignore[import-not-found]
    client: Any = boto3.client("bedrock-agent", region_name=region)
    try:
        data_source_id = _data_source_id(client, knowledge_base_id)
        response: dict[str, Any] = client.start_ingestion_job(
            knowledgeBaseId=knowledge_base_id, dataSourceId=data_source_id,
        )
        job_id = str(response.get("ingestionJob", {}).get("ingestionJobId", ""))
        if not job_id:
            raise RuntimeError("Bedrock did not return an ingestion job ID")
    except Exception as error:
        if _is_concurrent_ingestion_error(error):
            return record
        message = str(error) or error.__class__.__name__
        store.register(record.filename, "failed", record.chunks_added, upload_id=record.upload_id, error=message)
        return UploadRecord(
            upload_id=record.upload_id, filename=record.filename, status="failed",
            chunks_added=record.chunks_added, error=message,
        )
    store.register(
        record.filename, "ingesting", record.chunks_added,
        upload_id=record.upload_id, ingestion_job_id=job_id,
    )
    return UploadRecord(
        upload_id=record.upload_id, filename=record.filename, status="ingesting",
        chunks_added=record.chunks_added, ingestion_job_id=job_id,
    )


def _refresh_aws_ingestion_status(
    store: UploadStore, record: UploadRecord, knowledge_base_id: str | None, region: str | None,
) -> UploadRecord:
    """Poll Bedrock once and persist the terminal upload status when available."""
    if not knowledge_base_id:
        return record
    import boto3  # type: ignore[import-not-found]
    client: Any = boto3.client("bedrock-agent", region_name=region)
    data_source_id = _data_source_id(client, knowledge_base_id)
    response: dict[str, Any] = client.get_ingestion_job(
        knowledgeBaseId=knowledge_base_id,
        dataSourceId=data_source_id,
        ingestionJobId=record.ingestion_job_id,
    )
    bedrock_status = str(response.get("ingestionJob", {}).get("status", ""))
    mapped_status = {"COMPLETE": "ready", "FAILED": "failed"}.get(bedrock_status, "ingesting")
    if mapped_status != "ingesting":
        store.register(
            record.filename, mapped_status, record.chunks_added,
            upload_id=record.upload_id, ingestion_job_id=record.ingestion_job_id,
        )
        return UploadRecord(
            upload_id=record.upload_id, filename=record.filename, status=mapped_status,
            chunks_added=record.chunks_added, ingestion_job_id=record.ingestion_job_id,
        )
    return record


def _data_source_id(client: Any, knowledge_base_id: str) -> str:
    response: dict[str, Any] = client.list_data_sources(knowledgeBaseId=knowledge_base_id, maxResults=10)
    sources = response.get("dataSourceSummaries", [])
    if not sources:
        raise RuntimeError("Knowledge Base has no data source")
    return str(sources[0]["dataSourceId"])


def _is_concurrent_ingestion_error(error: Exception) -> bool:
    response = getattr(error, "response", {})
    details = response.get("Error", {}) if isinstance(response, dict) else {}
    code = str(details.get("Code", "")) if isinstance(details, dict) else ""
    message = str(details.get("Message", "")).lower() if isinstance(details, dict) else ""
    return code in {"ConflictException", "ValidationException"} and any(
        marker in message for marker in ("concurrent", "already running", "active ingestion job", "another ingestion job")
    )
