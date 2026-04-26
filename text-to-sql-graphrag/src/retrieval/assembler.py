"""Sub-graph assembler — converts graph context into LLM-ready prompt text.

Takes the raw SubGraph from traversal and serializes it into a structured
schema description that the LLM can use to generate accurate SQL.
"""

from __future__ import annotations

import structlog

from src.retrieval.graph_traversal import SubGraph, TableContext, ColumnContext

logger = structlog.get_logger(__name__)


def assemble_schema_context(subgraph: SubGraph) -> str:
    """Convert a SubGraph into a structured text format for the LLM prompt.

    Output format:
    ```
    ### Table: orders (schema: analytics, type: model)
    Description: All completed customer orders
    Columns:
      - order_id (INTEGER, PK) — Unique order identifier
      - customer_id (INTEGER) — FK to customers.customer_id
      ...

    ### Relationships:
      - orders DEPENDS_ON customers
      - orders.customer_id FK_REFERENCES customers.customer_id
    ```
    """
    if not subgraph.tables:
        return "No relevant schema context found."

    sections: list[str] = []

    # Sort tables: seed tables first, then alphabetical
    seed_set = set(subgraph.query_tables)
    sorted_tables = sorted(
        subgraph.tables,
        key=lambda t: (t.name not in seed_set, t.name),
    )

    # Table sections
    for table in sorted_tables:
        section = _format_table(table)
        sections.append(section)

    # Relationships section
    if subgraph.relationships:
        rel_section = _format_relationships(subgraph)
        sections.append(rel_section)

    context = "\n\n".join(sections)

    logger.debug(
        "schema_context_assembled",
        tables=len(subgraph.tables),
        total_columns=sum(len(t.columns) for t in subgraph.tables),
        relationships=len(subgraph.relationships),
        char_count=len(context),
    )

    return context


def _format_table(table: TableContext) -> str:
    """Format a single table and its columns."""
    header = f"### Table: {table.name}"
    meta_parts = []
    if table.schema:
        meta_parts.append(f"schema: {table.schema}")
    if table.database:
        meta_parts.append(f"database: {table.database}")
    if table.materialization:
        meta_parts.append(f"materialization: {table.materialization}")
    if table.table_type:
        meta_parts.append(f"type: {table.table_type}")

    if meta_parts:
        header += f" ({', '.join(meta_parts)})"

    lines = [header]

    if table.description:
        lines.append(f"Description: {table.description}")

    if table.columns:
        lines.append("Columns:")
        for col in sorted(table.columns, key=lambda c: (not c.is_pk, c.name)):
            col_str = _format_column(col)
            lines.append(f"  - {col_str}")
    else:
        lines.append("Columns: (no column information available)")

    return "\n".join(lines)


def _format_column(col: ColumnContext) -> str:
    """Format a single column for display."""
    parts = [col.name]

    # Type and constraints
    annotations = []
    if col.data_type:
        annotations.append(col.data_type)
    if col.is_pk:
        annotations.append("PK")

    if annotations:
        parts.append(f"({', '.join(annotations)})")

    # Description
    if col.description:
        parts.append(f"— {col.description}")

    return " ".join(parts)


def _format_relationships(subgraph: SubGraph) -> str:
    """Format the relationships section."""
    lines = ["### Relationships:"]

    for rel in subgraph.relationships:
        if rel.from_column and rel.to_column:
            # FK relationship with column specifics
            lines.append(
                f"  - {rel.from_table}.{rel.from_column} "
                f"{rel.relationship_type} {rel.to_table}.{rel.to_column}"
            )
        else:
            # Model-level relationship
            lines.append(
                f"  - {rel.from_table} {rel.relationship_type} {rel.to_table}"
            )

    return "\n".join(lines)


def estimate_token_count(text: str) -> int:
    """Rough estimate of token count (1 token ≈ 4 chars for English text)."""
    return len(text) // 4


def truncate_context(context: str, max_tokens: int = 4000) -> str:
    """Truncate context to fit within a token budget.

    Preserves complete table sections — doesn't cut mid-table.
    """
    if estimate_token_count(context) <= max_tokens:
        return context

    sections = context.split("\n\n")
    kept: list[str] = []
    running_tokens = 0

    for section in sections:
        section_tokens = estimate_token_count(section)
        if running_tokens + section_tokens > max_tokens:
            kept.append("\n... (additional tables truncated to fit token budget)")
            break
        kept.append(section)
        running_tokens += section_tokens

    truncated = "\n\n".join(kept)
    logger.debug(
        "context_truncated",
        original_tokens=estimate_token_count(context),
        truncated_tokens=estimate_token_count(truncated),
    )
    return truncated
