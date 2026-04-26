"""Request and response schemas for the API."""

from __future__ import annotations

from pydantic import BaseModel, Field


class QueryRequest(BaseModel):
    """Request body for the text-to-SQL endpoint."""

    query: str = Field(
        ...,
        description="Natural language question to convert to SQL.",
        min_length=3,
        examples=["Show me total revenue by product category for last quarter"],
    )
    sql_dialect: str | None = Field(
        default=None,
        description="Target SQL dialect. Defaults to config value.",
        examples=["postgres", "bigquery", "snowflake"],
    )


class QueryResponse(BaseModel):
    """Response body for the text-to-SQL endpoint."""

    sql: str = Field(
        ...,
        description="Generated SQL query.",
    )
    explanation: str = Field(
        default="",
        description="Human-readable explanation of what the SQL does.",
    )
    confidence: float = Field(
        default=0.0,
        description="Confidence score from 0.0 to 1.0.",
        ge=0.0,
        le=1.0,
    )
    tables_used: list[str] = Field(
        default_factory=list,
        description="List of table names used in the context.",
    )
    error: str | None = Field(
        default=None,
        description="Error message if generation failed.",
    )


class IngestRequest(BaseModel):
    """Request body for triggering ingestion."""

    docs_path: str | None = Field(
        default=None,
        description="Path to dbt docs directory. Defaults to config value.",
    )
    full_sync: bool = Field(
        default=False,
        description="Force full re-sync instead of incremental.",
    )
    skip_enrichment: bool = Field(
        default=False,
        description="Skip LLM description enrichment.",
    )
    skip_embeddings: bool = Field(
        default=False,
        description="Skip embedding generation.",
    )


class IngestResponse(BaseModel):
    """Response body for ingestion results."""

    new_count: int
    modified_count: int
    unchanged_count: int
    deleted_count: int
    embeddings_generated: int
    message: str


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    neo4j_connected: bool
    llm_provider: str
    sql_dialect: str
