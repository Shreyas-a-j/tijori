"""FastAPI entrypoint (lane 2 owns this file).

Run with: uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import hmac
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import get_api_key, get_audit_retention_days, settings
from app.pipeline.pipeline import PrivacyPipeline

# Without a handler, the module logger's INFO lines (the startup retention
# dry run) are dropped and only WARNING+ appears. Configure the root logger at
# the documented level; uvicorn keeps its own handlers for its loggers.
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("tijori.gateway")


def create_app(*, pipeline: PrivacyPipeline | None = None) -> FastAPI:
    """Build the app. Tests may inject a pipeline with a fake provider/DB."""

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        active = pipeline or PrivacyPipeline()
        application.state.pipeline = active
        application.state.repository = active.repository

        retention_days = get_audit_retention_days()
        would_purge = active.repository.purge_older_than(
            days=retention_days,
            dry_run=True,
        )
        logger.info(
            f"audit retention: would purge {would_purge} rows older than {retention_days} days"
        )
        yield

    application = FastAPI(
        title="Tijori — DPDP Privacy Gateway",
        version="0.1.0",
        description="Detect, mask, forward sanitized text, reinsert locally.",
        lifespan=lifespan,
    )

    @application.middleware("http")
    async def api_key_auth_middleware(request: Request, call_next):
        path = request.url.path
        if path == "/v1" or path.startswith("/v1/"):
            expected_key = get_api_key()
            if expected_key:
                presented_key = request.headers.get("x-api-key")
                if not presented_key or not hmac.compare_digest(presented_key, expected_key):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "unauthorized"},
                        headers={"WWW-Authenticate": "X-API-Key"},
                    )
        return await call_next(request)

    application.include_router(router)
    return application


app = create_app()
