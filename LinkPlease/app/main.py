"""Main FastAPI application entrypoint."""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.database import init_db
from app.api import webhook_router, rules_router, stats_router, health_router
from app.workers.dm_worker import dm_worker
from app.services.pseudogram_client import pseudogram_client

# Configure structured logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("linkplease")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("Initializing database tables...")
    await init_db()

    logger.info("Starting persistent Pseudogram Client session...")
    await pseudogram_client.start()

    logger.info("Starting DM background worker...")
    await dm_worker.start()

    yield

    logger.info("Stopping DM background worker...")
    await dm_worker.stop()

    logger.info("Stopping persistent Pseudogram Client session...")
    await pseudogram_client.stop()

    logger.info("Application shutdown complete.")


app = FastAPI(
    title="LinkPlease API",
    description="Reliable Instagram Comment DM Automation Engine",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routers
app.include_router(webhook_router)
app.include_router(rules_router)
app.include_router(stats_router)
app.include_router(health_router)

# Static files and Dashboard UI
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", include_in_schema=False)
    async def root():
        return FileResponse(os.path.join(static_dir, "index.html"))

    @app.get("/dashboard", include_in_schema=False)
    async def dashboard():
        return FileResponse(os.path.join(static_dir, "index.html"))
