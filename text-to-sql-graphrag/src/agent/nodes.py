"""Agent node functions for the LangGraph SQL generation workflow.

Each function is a node in the LangGraph state machine. Nodes read from
and write to the shared AgentState.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import HumanMessage, SystemMessage

from src.config import settings
from src.graph.client import Neo4jClient
from src.retrieval.retriever import HybridRetriever
from src.agent.state import AgentState
from src.agent.prompts import (
    SQL_GENERATION_SYSTEM,
    SQL_GENERATION_USER,
    SQL_CORRECTION_SYSTEM,
    SQL_CORRECTION_USER,
)
from src.agent.validator import (
    validate_sql,
    extract_sql_from_response,
    extract_explanation,
    extract_confidence,
)

logger = structlog.get_logger(__name__)


async def retrieve_context(state: AgentState) -> dict:
    """Node: Retrieve relevant schema context from the knowledge graph.

    Runs the full GraphRAG pipeline:
    embed query → vector search → graph expansion → context assembly.
    """
    query = state["query"]

    async with Neo4jClient() as client:
        retriever = HybridRetriever(client)
        result = await retriever.retrieve(query)

    logger.info(
        "context_retrieved",
        query=query[:80],
        tables=result.total_table_count,
    )

    return {
        "schema_context": result.context,
        "subgraph": result.subgraph,
    }


async def generate_sql(state: AgentState) -> dict:
    """Node: Generate SQL from the user query and schema context.

    Uses the LLM with the assembled schema context to produce SQL.
    On retry, uses the correction prompt with the error context.
    """
    query = state["query"]
    schema_context = state["schema_context"]
    dialect = state.get("sql_dialect", settings.sql_dialect.value)
    retry_count = state.get("retry_count", 0)
    validation_error = state.get("validation_error")

    llm = settings.get_llm()

    # Choose prompt based on whether this is a retry
    if retry_count > 0 and validation_error and state.get("generated_sql"):
        # Self-correction mode
        messages = [
            SystemMessage(
                content=SQL_CORRECTION_SYSTEM.format(dialect=dialect)
            ),
            HumanMessage(
                content=SQL_CORRECTION_USER.format(
                    schema_context=schema_context,
                    query=query,
                    failed_sql=state["generated_sql"],
                    error=validation_error,
                )
            ),
        ]
        logger.info("sql_correction_attempt", retry=retry_count)
    else:
        # First attempt
        messages = [
            SystemMessage(
                content=SQL_GENERATION_SYSTEM.format(dialect=dialect)
            ),
            HumanMessage(
                content=SQL_GENERATION_USER.format(
                    schema_context=schema_context,
                    query=query,
                )
            ),
        ]

    response = await llm.ainvoke(messages)
    response_text = response.content

    # Parse the response
    sql = extract_sql_from_response(response_text)
    explanation = extract_explanation(response_text)
    confidence = extract_confidence(response_text)

    logger.info(
        "sql_generated",
        sql_preview=sql[:100],
        confidence=confidence,
        retry=retry_count,
    )

    return {
        "generated_sql": sql,
        "explanation": explanation,
        "confidence": confidence,
        "retry_count": retry_count,
    }


async def validate_generated_sql(state: AgentState) -> dict:
    """Node: Validate the generated SQL using sqlglot.

    Checks syntax and safety. If valid, sets final_sql.
    If invalid, sets validation_error for the correction loop.
    """
    sql = state.get("generated_sql", "")
    dialect = state.get("sql_dialect", settings.sql_dialect.value)

    from src.config import SQLDialect
    sql_dialect = SQLDialect(dialect)

    result = validate_sql(sql, sql_dialect)

    if result.is_valid:
        logger.info("sql_validation_passed")
        return {
            "final_sql": result.formatted_sql or sql,
            "validation_error": None,
        }
    else:
        retry_count = state.get("retry_count", 0) + 1
        logger.warning(
            "sql_validation_failed",
            error=result.error_message,
            retry_count=retry_count,
        )
        return {
            "validation_error": result.error_message,
            "retry_count": retry_count,
        }


async def format_response(state: AgentState) -> dict:
    """Node: Format the final response for the user."""
    return {
        "final_sql": state.get("final_sql", state.get("generated_sql", "")),
        "explanation": state.get("explanation", ""),
        "confidence": state.get("confidence", 0.0),
        "error": None,
    }


async def handle_error(state: AgentState) -> dict:
    """Node: Handle the case where SQL generation failed after max retries."""
    retry_count = state.get("retry_count", 0)
    last_error = state.get("validation_error", "Unknown error")

    logger.error(
        "sql_generation_failed",
        retries=retry_count,
        error=last_error,
    )

    return {
        "error": (
            f"Failed to generate valid SQL after {retry_count} attempts. "
            f"Last error: {last_error}"
        ),
        "final_sql": "",
    }
