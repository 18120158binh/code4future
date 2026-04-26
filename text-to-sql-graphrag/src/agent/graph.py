"""LangGraph workflow definition for the SQL generation agent.

Defines the state machine: retrieve → generate → validate → (retry|respond).
This is the main entry point for running the agent.
"""

from __future__ import annotations

import structlog
from langgraph.graph import StateGraph, END

from src.config import settings
from src.agent.state import AgentState
from src.agent.nodes import (
    retrieve_context,
    generate_sql,
    validate_generated_sql,
    format_response,
    handle_error,
)

logger = structlog.get_logger(__name__)


def should_retry(state: AgentState) -> str:
    """Conditional edge: decide whether to retry or finalize.

    Returns the name of the next node to visit.
    """
    # If validation passed (no error), proceed to format
    if not state.get("validation_error"):
        return "format_response"

    # If we've exceeded max retries, go to error handler
    retry_count = state.get("retry_count", 0)
    if retry_count >= settings.max_retry_attempts:
        return "handle_error"

    # Otherwise, retry generation
    return "generate_sql"


def build_agent_graph() -> StateGraph:
    """Build the LangGraph state machine for SQL generation.

    Graph structure:
        retrieve_context → generate_sql → validate_sql
                                              ↓
                                    ┌─────────┴──────────┐
                                    ↓         ↓          ↓
                              format_response  │   handle_error
                                    ↓         ↓          ↓
                                   END   generate_sql   END
                                         (retry)
    """
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("retrieve_context", retrieve_context)
    graph.add_node("generate_sql", generate_sql)
    graph.add_node("validate_sql", validate_generated_sql)
    graph.add_node("format_response", format_response)
    graph.add_node("handle_error", handle_error)

    # Define edges
    graph.set_entry_point("retrieve_context")
    graph.add_edge("retrieve_context", "generate_sql")
    graph.add_edge("generate_sql", "validate_sql")

    # Conditional routing after validation
    graph.add_conditional_edges(
        "validate_sql",
        should_retry,
        {
            "format_response": "format_response",
            "handle_error": "handle_error",
            "generate_sql": "generate_sql",
        },
    )

    graph.add_edge("format_response", END)
    graph.add_edge("handle_error", END)

    return graph


def compile_agent():
    """Compile the agent graph into a runnable.

    Returns a compiled LangGraph that can be invoked with:
        result = await agent.ainvoke({"query": "...", "sql_dialect": "postgres"})
    """
    graph = build_agent_graph()
    compiled = graph.compile()
    logger.info("agent_compiled")
    return compiled


# Pre-built agent for direct import
# Usage: from src.agent.graph import agent
#        result = await agent.ainvoke({"query": "show me top customers"})
agent = compile_agent()
