from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status

from .config import UPLOAD_DIR, ensure_data_directories, get_settings
from .ingest import append_to_index
from .models import IngestionResponse, PresignedUploadRequest, PresignedUploadResponse, UploadResponse
from .retrieval import reload_index
from .stores import upload_store


router = APIRouter(prefix="/api", tags=["uploads"])
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
INGESTION_STATUSES = {"pending", "ingesting", "ready", "failed"}


def _safe_filename(filename: str) -> str:
    base = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    if not safe:
        raise ValueError("Invalid filename")
    return safe


@router.post("/upload", response_model=UploadResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
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
        key = f"uploads/{filename}"
        url = client.generate_presigned_url(
            "put_object", Params={"Bucket": settings.corpus_bucket, "Key": key, "ContentType": file.content_type or "application/octet-stream"},
            ExpiresIn=900,
        )
        upload_store().register(filename, "pending", upload_id=filename)
        return UploadResponse(filename=filename, status="pending", chunks_added=0, upload_url=str(url))
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return _save_local_upload(filename, content)


@router.put("/upload", response_model=UploadResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def direct_upload(request: Request, filename: str) -> UploadResponse:
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
async def presign_upload(payload: PresignedUploadRequest, request: Request) -> PresignedUploadResponse:
    try:
        filename = _safe_filename(payload.filename)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    if Path(filename).suffix.lower() not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, MD, or TXT file")
    settings = get_settings()
    upload_id = upload_store().register(filename, "pending", upload_id=filename)
    if settings.corpus_aws:
        import boto3  # type: ignore[import-not-found]
        upload_url = boto3.client("s3", region_name=settings.aws_region).generate_presigned_url(
            "put_object", Params={"Bucket": settings.corpus_bucket, "Key": f"uploads/{filename}", "ContentType": payload.content_type}, ExpiresIn=900,
        )
        return PresignedUploadResponse(upload_id=upload_id, upload_url=str(upload_url), headers={"Content-Type": payload.content_type})
    direct_url = f"{str(request.base_url).rstrip('/')}/api/upload?{urlencode({'filename': filename})}"
    return PresignedUploadResponse(upload_id=upload_id, upload_url=direct_url, headers={})


@router.get("/uploads/{upload_id}", response_model=IngestionResponse, response_model_exclude_none=True)
async def ingestion_status(upload_id: str) -> IngestionResponse:
    record = upload_store().get(upload_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Upload not found")
    if record.status not in INGESTION_STATUSES:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Upload has an invalid ingestion status")
    return IngestionResponse(upload_id=record.upload_id, status=record.status, chunks_added=record.chunks_added)
