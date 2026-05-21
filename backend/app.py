import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.logging_setup import configure_logging
from backend.routers.auth import router as auth_router
from backend.routers.movies import router as movies_router
from backend.routers.conversations import router as conversations_router
from backend.routers.cluster_snapshots import router as cluster_snapshots_router

log = logging.getLogger(__name__)

DOCS_PATH = "/docs"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: configure logging, then serve.

    Args:
        app: The FastAPI application instance.

    Yields:
        Control to the request-handling phase.
    """
    configure_logging()

    host = os.environ.get("HOST", "127.0.0.1")
    port = os.environ.get("PORT", "8000")
    log.info("CinePal backend started")
    log.info(f"Docs available at http://{host}:{port}{DOCS_PATH}")

    yield

    log.info("CinePal backend stopped")


app = FastAPI(
    title="CinePal",
    description="Conversational multi-view clustering for movie exploration.",
    docs_url=DOCS_PATH,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(auth_router)
app.include_router(movies_router)
app.include_router(conversations_router)
app.include_router(cluster_snapshots_router)
