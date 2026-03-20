"""FastAPI application entry point."""
import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import health, jobs, addresses, pickup, labels


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: begin periodic job cleanup
    from .services.job_store import job_store
    cleanup_task = asyncio.create_task(_periodic_cleanup())
    yield
    # Shutdown: cancel cleanup
    cleanup_task.cancel()


async def _periodic_cleanup():
    from .services.job_store import job_store
    settings = get_settings()
    while True:
        await asyncio.sleep(settings.job_cleanup_interval_seconds)
        job_store.cleanup_expired()


app = FastAPI(
    title="ELC Tools API",
    version="3.0.0",
    lifespan=lifespan,
)

# CORS
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(addresses.router, prefix="/api/v1")
app.include_router(pickup.router, prefix="/api/v1")
app.include_router(labels.router, prefix="/api/v1")
