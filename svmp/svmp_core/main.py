"""FastAPI application factory and runtime wiring for SVMP."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from svmp_core.config import Settings, get_dashboard_cors_origins, get_settings
from svmp_core.db.base import Database
from svmp_core.db.mongo import MongoDatabase
from svmp_core.logger import configure_logging
from svmp_core.routes import build_billing_router, build_dashboard_router, build_webhook_router
from svmp_core.workflows import run_workflow_b, run_workflow_c


def _job_exists(scheduler: Any, job_id: str) -> bool:
    """Check whether a scheduler already has a job with the given id."""

    get_job = getattr(scheduler, "get_job", None)
    if callable(get_job):
        return get_job(job_id) is not None

    jobs = getattr(scheduler, "jobs", None)
    if isinstance(jobs, dict):
        return job_id in jobs

    return False


def _register_scheduler_jobs(
    scheduler: Any,
    database: Database,
    settings: Settings,
) -> None:
    """Attach Workflow B and Workflow C jobs to the runtime scheduler."""

    if not _job_exists(scheduler, "workflow_b"):
        scheduler.add_job(
            run_workflow_b,
            trigger="interval",
            seconds=settings.WORKFLOW_B_INTERVAL_SECONDS,
            id="workflow_b",
            replace_existing=True,
            kwargs={"database": database, "settings": settings},
        )

    if not _job_exists(scheduler, "workflow_c"):
        scheduler.add_job(
            run_workflow_c,
            trigger="interval",
            hours=settings.WORKFLOW_C_INTERVAL_HOURS,
            id="workflow_c",
            replace_existing=True,
            kwargs={"database": database, "settings": settings},
        )


def create_app(
    *,
    settings: Settings | None = None,
    database: Database | None = None,
    scheduler: Any | None = None,
) -> FastAPI:
    """Create the SVMP FastAPI application with runtime dependencies wired."""

    runtime_settings = settings or get_settings()
    runtime_database = database or MongoDatabase(settings=runtime_settings)
    runtime_scheduler = scheduler or AsyncIOScheduler(timezone="UTC")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime_settings.validate_runtime()
        configure_logging()
        await runtime_database.connect()
        _register_scheduler_jobs(runtime_scheduler, runtime_database, runtime_settings)

        if not getattr(runtime_scheduler, "running", False):
            runtime_scheduler.start()

        app.state.settings = runtime_settings
        app.state.database = runtime_database
        app.state.scheduler = runtime_scheduler

        try:
            yield
        finally:
            if getattr(runtime_scheduler, "running", False):
                runtime_scheduler.shutdown(wait=False)
            await runtime_database.disconnect()

    app = FastAPI(title=runtime_settings.APP_NAME, lifespan=lifespan)

    dashboard_cors_origins = get_dashboard_cors_origins(runtime_settings)
    if dashboard_cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=dashboard_cors_origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=[
                "Authorization",
                "Content-Type",
                "X-SVMP-Organization-Id",
                "X-SVMP-User-Email",
                "X-SVMP-User-Id",
            ],
        )

    @app.get("/health")
    async def healthcheck() -> dict[str, str]:
        """Simple health endpoint for boot and smoke tests."""

        return {"status": "ok"}

    app.include_router(build_dashboard_router())
    app.include_router(build_billing_router())
    app.include_router(build_webhook_router(runtime_database, settings=runtime_settings))

    return app


app = create_app()
