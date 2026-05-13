"""Cinepal — FastAPI application entry point.

Start the server:
    uvicorn backend.app:app --reload

In production pass --host and --port; set HOST / PORT env vars to match so
the startup log prints the correct docs URL.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from backend.logging_setup import configure_logging
from backend.orchestrator.orchestrator import Orchestrator
from backend.routers.sessions import movies_router, router as sessions_router

log = logging.getLogger(__name__)

DOCS_PATH = "/docs"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: configure logging, wire dependencies, then serve.

    Runs once at startup before the first request and once at shutdown after
    the last. Any exception raised here aborts startup — fail loudly by design.

    Args:
        app: The FastAPI application instance (provided by the framework).

    Yields:
        Control to the request-handling phase.
    """
    configure_logging()
    app.state.orchestrator = Orchestrator()

    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "8000")
    log.info(
        "CinePal backend started",
    )
    log.info(f"Docs available at http://{host}:{port}{DOCS_PATH}")

    yield

    log.info("cinepal backend stopped")


app = FastAPI(
    title="CinePal",
    description="Conversational movie recommender — session/turn API.",
    docs_url=DOCS_PATH,
    lifespan=lifespan,
)

app.include_router(sessions_router)
app.include_router(movies_router)
