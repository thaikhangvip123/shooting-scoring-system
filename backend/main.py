"""
backend/main.py
FastAPI application factory.

Run with:
    uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import get_settings
from backend.routers import shots as shots_router
from backend.routers import stats as stats_router
from backend.routers import websocket as ws_router
from backend.routers.websocket import manager as ws_manager

# ─── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level   = logging.INFO,
    format  = "%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt = "%H:%M:%S",
)
logger = logging.getLogger(__name__)


# ─── Patch shot_service to broadcast via WebSocket ───────────────────────────
# We inject the WS broadcast into the shot service here to avoid circular imports.

from backend.services import shot_service as _ss
from backend.models.shot import ShotResponse

_original_register = _ss.register_shot

async def _register_and_broadcast(payload) -> ShotResponse:
    result = await _original_register(payload)
    # Broadcast to all WS clients — fire-and-forget
    if ws_manager.client_count > 0:
        import asyncio
        asyncio.create_task(ws_manager.broadcast(result.model_dump(mode="json")))
    return result

_ss.register_shot = _register_and_broadcast  # monkey-patch


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    from backend.db.firebase import get_store
    get_store()   # warm up DB connection / in-memory store
    yield
    logger.info("Shutting down")


# ─── App ──────────────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title       = settings.app_name,
        version     = settings.app_version,
        description = "Real-time shooting scoring system API",
        docs_url    = "/docs",
        redoc_url   = "/redoc",
        lifespan    = lifespan,
    )

    # ── CORS ──────────────────────────────────────────────────────────────────
    app.add_middleware(
        CORSMiddleware,
        allow_origins     = settings.cors_origins,
        allow_credentials = True,
        allow_methods     = ["*"],
        allow_headers     = ["*"],
    )

    # ── Request timing middleware ──────────────────────────────────────────────
    @app.middleware("http")
    async def add_process_time(request: Request, call_next):
        start    = time.perf_counter()
        response = await call_next(request)
        elapsed  = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{elapsed:.1f}"
        return response

    # ── Global error handler ──────────────────────────────────────────────────
    @app.exception_handler(Exception)
    async def global_error(request: Request, exc: Exception):
        logger.exception("Unhandled error on %s %s", request.method, request.url)
        return JSONResponse(
            status_code = 500,
            content     = {"detail": "Internal server error"},
        )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(shots_router.router)
    app.include_router(stats_router.router)
    app.include_router(ws_router.router)

    # ── Health check ──────────────────────────────────────────────────────────
    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status":  "ok",
            "version": settings.app_version,
            "ws_clients": ws_manager.client_count,
        }

    return app


app = create_app()