from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import auth, chat, conflicts, resolution, topics, uploads
from .config import CORPUS_DIR, ensure_data_directories, get_settings
from .conflicts import seed_demo_conflicts
from .database import initialize_database
from .ingest import build_index, discover_corpus_files
from .llm import PROVIDER_NAME
from .models import HealthResponse
from .retrieval import INDEX, reload_index


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    ensure_data_directories()
    initialize_database()
    if not settings.conflicts_aws:
        seed_demo_conflicts()
    reload_index()
    if not settings.retrieval_aws and INDEX.size == 0:
        files = discover_corpus_files(CORPUS_DIR)
        if files:
            build_index(files)
            reload_index()
    yield


app = FastAPI(title="Policy Intelligence API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for api_router in (auth.router, chat.router, resolution.router, topics.router, conflicts.router, uploads.router):
    app.include_router(api_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", index_chunks=INDEX.size, provider=PROVIDER_NAME)
