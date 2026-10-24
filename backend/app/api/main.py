"""FastAPI application. Run with: uvicorn app.api.main:app --reload (from backend/)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    app = FastAPI(
        title="Bangladesh News Intelligence API",
        version=__version__,
        description="Phase 1: collected articles, sources and source health. "
                    "Full article text is for private analysis; link to the publisher when sharing.",
    )
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=["*"])
    app.include_router(router)

    @app.get("/healthz", tags=["meta"])
    def healthz() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
