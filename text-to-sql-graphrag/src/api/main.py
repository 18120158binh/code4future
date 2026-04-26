"""FastAPI application entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.indexes import setup_indexes
from src.api.routes import router

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: startup and shutdown hooks."""
    # Startup
    logger.info("starting_up", llm_provider=settings.llm_provider.value)

    # Setup Neo4j indexes on startup
    try:
        async with Neo4jClient() as client:
            await setup_indexes(client)
        logger.info("neo4j_indexes_ready")
    except Exception as e:
        logger.warning("neo4j_startup_failed", error=str(e))

    yield

    # Shutdown
    logger.info("shutting_down")


app = FastAPI(
    title="Text-to-SQL GraphRAG",
    description=(
        "Convert natural language questions to SQL using "
        "GraphRAG-powered schema retrieval over Neo4j."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# CORS for Streamlit frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routes
app.include_router(router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=True,
    )
