from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint

from . import auth, chat, conflicts, drafting, permissions, registry, resolution, topics, uploads
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
    from .registry import seed_registry_from_corpus
    seed_registry_from_corpus()
    if not settings.permissions_aws:
        permissions.seed_default_permissions()
    if not settings.retrieval_aws and INDEX.size == 0:
        files = discover_corpus_files(CORPUS_DIR)
        if files:
            build_index(files)
            reload_index()
    yield


app = FastAPI(title="Policy Intelligence API", version="1.0.0", lifespan=lifespan)


# The agent Lambda Function URL (auth_type=NONE) exposes every route, not just
# the two it exists for, so authentication cannot rely on the API Gateway
# authorizer alone. In Cognito mode every /api route except health and login
# requires a verified JWT in-app; locally this is a no-op.
_AUTH_EXEMPT_PATHS = {"/api/health", "/api/login"}


@app.middleware("http")
async def _cognito_auth_middleware(request: Request, call_next: RequestResponseEndpoint) -> Response:
    settings = get_settings()
    if (
        settings.cognito_aws
        and request.url.path.startswith("/api")
        and request.url.path not in _AUTH_EXEMPT_PATHS
        and request.method != "OPTIONS"
    ):
        try:
            auth.verify_request_authorization(request.headers.get("authorization"), settings)
        except HTTPException as error:
            return JSONResponse(status_code=error.status_code, content={"detail": error.detail})
    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for api_router in (auth.router, chat.router, resolution.router, topics.router, conflicts.router, uploads.router, registry.router, permissions.router, drafting.router):
    app.include_router(api_router)


@app.get("/api/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok", index_chunks=INDEX.size, provider=PROVIDER_NAME)
