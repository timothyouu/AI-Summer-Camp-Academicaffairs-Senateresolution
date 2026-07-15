from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from .config import UPLOAD_DIR, ensure_data_directories, get_settings
from .ingest import append_to_index
from .models import UploadResponse
from .retrieval import reload_index
from .stores import upload_store


router = APIRouter(prefix="/api", tags=["uploads"])
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


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
        upload_store().register(filename, "Pending upload")
        return UploadResponse(filename=filename, status="Pending upload", chunks_added=0, upload_url=str(url))
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB")
    ensure_data_directories()
    destination = UPLOAD_DIR / filename
    destination.write_bytes(content)
    chunks_added = append_to_index(destination)
    reload_index()
    upload_store().register(filename, "Ready", chunks_added)
    return UploadResponse(filename=filename, status="Ready", chunks_added=chunks_added)
