"""LangGraph state definition for the SQL generation agent.

The state is the shared "whiteboard" that all agent nodes read from and write to.
It persists the full lifecycle of a query: from input through retrieval to generation.
"""

from __future__ import annotations

from typing import TypedDict

from src.retrieval.graph_traversal import SubGraph


class AgentState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes.

    Fields:
        query: The user's natural language question.
        sql_dialect: Target SQL dialect (postgres, bigquery, etc.).

        # Retrieval
        schema_context: Serialized schema context from GraphRAG.
        subgraph: The raw SubGraph (for traceability).

        # Generation
        generated_sql: The LLM-generated SQL query.
        validation_error: Error message from SQL validation (if any).
        retry_count: Number of generation retries so far.

        # Output
        explanation: Human-readable explanation of the SQL.
        confidence: Confidence score (0-1) from the LLM.
        final_sql: The validated, final SQL query.
        error: Error message if generation failed entirely.
    """

    # Input
    query: str
    sql_dialect: str

    # Retrieval
    schema_context: str
    subgraph: SubGraph

    # Generation loop
    generated_sql: str
    validation_error: str | None
    retry_count: int

    # Output
    explanation: str
    confidence: float
    final_sql: str
    error: str | None
