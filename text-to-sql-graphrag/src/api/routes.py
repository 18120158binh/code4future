"""API route definitions."""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, HTTPException

from src.config import settings
from src.graph.client import Neo4jClient
from src.ingestion.pipeline import run_ingestion
from src.agent.graph import agent
from src.api.schemas import (
    QueryRequest,
    QueryResponse,
    IngestRequest,
    IngestResponse,
    HealthResponse,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Check the health of the service and its dependencies."""
    neo4j_ok = False
    try:
        async with Neo4jClient() as client:
            await client.execute_query("RETURN 1")
            neo4j_ok = True
    except Exception:
        pass

    return HealthResponse(
        status="ok" if neo4j_ok else "degraded",
        neo4j_connected=neo4j_ok,
        llm_provider=settings.llm_provider.value,
        sql_dialect=settings.sql_dialect.value,
    )


@router.post("/query", response_model=QueryResponse)
async def text_to_sql(request: QueryRequest):
    """Convert a natural language question to SQL.

    This endpoint runs the full GraphRAG pipeline:
    1. Retrieve relevant schema context from Neo4j
    2. Generate SQL using the configured LLM
    3. Validate and self-correct if needed
    """
    try:
        # Build initial state
        initial_state = {
            "query": request.query,
            "sql_dialect": request.sql_dialect or settings.sql_dialect.value,
            "retry_count": 0,
        }

        # Run the agent
        result = await agent.ainvoke(initial_state)

        # Check for errors
        if result.get("error"):
            return QueryResponse(
                sql="",
                explanation="",
                confidence=0.0,
                error=result["error"],
            )

        # Extract table names from subgraph
        tables_used = []
        subgraph = result.get("subgraph")
        if subgraph and hasattr(subgraph, "tables"):
            tables_used = [t.name for t in subgraph.tables]

        return QueryResponse(
            sql=result.get("final_sql", ""),
            explanation=result.get("explanation", ""),
            confidence=result.get("confidence", 0.0),
            tables_used=tables_used,
        )

    except Exception as e:
        logger.error("query_failed", error=str(e), query=request.query[:100])
        raise HTTPException(
            status_code=500,
            detail=f"SQL generation failed: {str(e)}",
        )


@router.post("/ingest", response_model=IngestResponse)
async def trigger_ingestion(request: IngestRequest):
    """Trigger dbt docs ingestion into the knowledge graph.

    Supports both incremental (default) and full sync modes.
    """
    try:
        docs_path = Path(request.docs_path) if request.docs_path else None

        async with Neo4jClient() as client:
            result = await run_ingestion(
                client=client,
                docs_path=docs_path,
                skip_enrichment=request.skip_enrichment,
                skip_embeddings=request.skip_embeddings,
                full_sync=request.full_sync,
            )

        return IngestResponse(
            new_count=result.new_count,
            modified_count=result.modified_count,
            unchanged_count=result.unchanged_count,
            deleted_count=result.deleted_count,
            embeddings_generated=result.embeddings_generated,
            message=(
                f"Ingestion complete: {result.new_count} new, "
                f"{result.modified_count} modified, "
                f"{result.deleted_count} deleted."
            ),
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("ingestion_failed", error=str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Ingestion failed: {str(e)}",
        )
