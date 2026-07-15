from __future__ import annotations

import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from .config import UPLOAD_DIR, ensure_data_directories
from .database import connection
from .ingest import append_to_index
from .models import UploadResponse
from .retrieval import reload_index


router = APIRouter(prefix="/api", tags=["uploads"])
ALLOWED_SUFFIXES = {".pdf", ".md", ".txt"}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def _safe_filename(filename: str) -> str:
    base = Path(filename).name
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", base).strip(".-")
    if not safe:
        raise ValueError("Invalid filename")
    return safe


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    try:
        filename = _safe_filename(file.filename or "")
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Upload a PDF, MD, or TXT file")
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="File exceeds 20 MB")
    ensure_data_directories()
    destination = UPLOAD_DIR / filename
    destination.write_bytes(content)
    chunks_added = append_to_index(destination)
    reload_index()
    with connection() as database:
        database.execute(
            """INSERT INTO uploads(filename, status, chunks_added) VALUES (?, 'Ready', ?)
            ON CONFLICT(filename) DO UPDATE SET status = 'Ready', chunks_added = excluded.chunks_added""",
            (filename, chunks_added),
        )
    return UploadResponse(filename=filename, status="Ready", chunks_added=chunks_added)
