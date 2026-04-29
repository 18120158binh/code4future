"""Vanilla RAG retriever — best-practice baseline for benchmark comparison.

This retriever represents what a strong engineer would build WITHOUT
a knowledge graph. It uses the same vector search infrastructure but
replaces graph expansion with flat, DDL-style context assembly.

Competitive techniques included:
1. Schema Linking — keyword/fuzzy match query terms to table/column names
2. Vector Search — same Neo4j vector index as GraphRAG
3. Column-level search — find relevant columns, not just tables
4. DDL-style assembly — CREATE TABLE with data types and FK constraints
5. FK inference — detect foreign keys from shared column names + depends_on

What it does NOT do (the actual difference from GraphRAG):
- No multi-hop graph expansion (only top-K directly matched tables)
- No structural relationship traversal (FKs are flat text, not edges)
- No lineage-aware neighbor discovery
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel, PropKey, RelType
from src.retrieval.embedder import EmbedderService
from src.retrieval.vector_search import (
    search_tables_by_embedding,
    search_columns_by_embedding,
    fulltext_search_tables,
)
from src.retrieval.assembler import estimate_token_count

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class TableDDL:
    """A table and its DDL representation."""

    unique_id: str
    name: str
    schema: str
    database: str
    description: str
    columns: list[ColumnDDL] = field(default_factory=list)
    fk_constraints: list[str] = field(default_factory=list)


@dataclass
class ColumnDDL:
    """A column in DDL format."""

    name: str
    data_type: str | None
    description: str
    is_pk: bool


@dataclass
class VanillaRetrievalResult:
    """Result of a vanilla RAG retrieval."""

    context: str
    tables_found: list[str]
    seed_table_count: int
    total_table_count: int
    schema_linked_tables: list[str]
    vector_matched_tables: list[str]


# =============================================================================
# Schema Linking
# =============================================================================


def schema_link(
    query: str,
    all_tables: list[dict],
    all_columns: list[dict],
) -> list[str]:
    """Match query terms to table and column names using keyword matching.

    This gives the RAG system an advantage over pure vector search —
    if the user mentions "sessions" or "revenue", we can directly match
    those to table/column names without relying on semantic similarity.

    Args:
        query: User's natural language question.
        all_tables: List of dicts with 'unique_id' and 'name' keys.
        all_columns: List of dicts with 'name' and 'table_unique_id' keys.

    Returns:
        List of table unique_ids matched via schema linking.
    """
    query_lower = query.lower()

    # Tokenize the query into meaningful words (strip common SQL/question words)
    stop_words = {
        "show", "me", "the", "all", "from", "how", "many", "what", "is",
        "are", "do", "we", "have", "and", "or", "for", "by", "with", "in",
        "to", "a", "an", "of", "on", "that", "this", "which", "where",
        "their", "them", "each", "per", "last", "first", "most", "top",
        "total", "average", "avg", "sum", "count", "number", "compare",
        "vs", "versus", "between", "break", "down", "find", "list",
        "give", "get", "display", "include", "also", "about", "than",
        "more", "less", "higher", "lower", "had", "has", "been", "were",
        "was", "did", "does", "can", "could", "should", "would", "will",
        "into", "but", "not", "if", "when", "then", "so", "at",
    }
    query_words = set(re.findall(r'[a-z][a-z_]+', query_lower)) - stop_words

    matched_table_ids: set[str] = set()

    # Direct table name matching
    for table in all_tables:
        table_name = table["name"].lower()
        # Match full table name
        if table_name in query_lower:
            matched_table_ids.add(table["unique_id"])
            continue
        # Match meaningful parts of table name (e.g., "sessions" from "fct_sessions")
        name_parts = table_name.replace("fct_", "").replace("dim_", "").replace(
            "rpt_", ""
        ).replace("stg_", "").replace("int_", "").split("_")
        for part in name_parts:
            if len(part) >= 4 and part in query_words:
                matched_table_ids.add(table["unique_id"])
                break

    # Column name matching
    for col in all_columns:
        col_name = col["name"].lower()
        col_parts = col_name.split("_")
        for part in col_parts:
            if len(part) >= 4 and part in query_words:
                matched_table_ids.add(col["table_unique_id"])
                break

    return list(matched_table_ids)


# =============================================================================
# FK Inference
# =============================================================================


def infer_fk_constraints(
    table: TableDDL,
    all_tables: list[TableDDL],
    depends_on_map: dict[str, list[str]],
) -> list[str]:
    """Infer FK constraints by finding shared column names with related tables.

    This gives the RAG system FK information without a graph — the best
    a flat system can do by reading dbt manifest depends_on relationships.

    Algorithm:
    1. Get the tables this model depends_on (from manifest.json)
    2. For each dependency, find matching column names
    3. Generate FK constraint comments

    Args:
        table: The table to find FKs for.
        all_tables: All available tables for cross-reference.
        depends_on_map: Map of unique_id -> list of dependency unique_ids.

    Returns:
        List of FK constraint comment strings.
    """
    table_col_names = {col.name.lower() for col in table.columns}
    deps = depends_on_map.get(table.unique_id, [])
    all_tables_by_id = {t.unique_id: t for t in all_tables}

    fk_comments = []
    for dep_id in deps:
        dep_table = all_tables_by_id.get(dep_id)
        if dep_table is None:
            continue

        dep_col_names = {col.name.lower() for col in dep_table.columns}

        # Find shared column names — these are likely FK relationships
        shared = table_col_names & dep_col_names
        # Filter out generic columns that aren't meaningful FKs
        generic_cols = {"country_code", "city", "device_type", "os_name",
                        "browser_name", "utm_source", "utm_medium",
                        "utm_campaign", "subscription_tier"}
        meaningful_shared = shared - generic_cols

        for col_name in sorted(meaningful_shared):
            fk_comments.append(
                f"-- FK: {col_name} REFERENCES {dep_table.name}({col_name})"
            )

    # Also check for obvious FK patterns in tables that are in context
    # (not just depends_on) — e.g., session_id, user_id, event_id
    common_fk_patterns = {
        "user_id": "dim_users",
        "session_id": "fct_sessions",
        "event_id": "fct_events",
        "campaign_id": "dim_campaigns",
    }
    for col_name, ref_table in common_fk_patterns.items():
        if col_name in table_col_names and table.name != ref_table:
            ref_exists = any(t.name == ref_table for t in all_tables)
            if ref_exists:
                fk_line = f"-- FK: {col_name} REFERENCES {ref_table}({col_name})"
                if fk_line not in fk_comments:
                    fk_comments.append(fk_line)

    return fk_comments


# =============================================================================
# DDL Assembly
# =============================================================================


def format_table_as_ddl(table: TableDDL) -> str:
    """Format a table as CREATE TABLE DDL with comments.

    This is the best-practice format for text-to-SQL RAG —
    LLMs understand DDL natively and can extract data types and constraints.

    Example output:
    ```
    -- fct_conversions: Conversion event fact table with revenue attribution
    CREATE TABLE fct_conversions (
        conversion_id VARCHAR(36),  -- PK. Event_id of the conversion event
        conversion_type VARCHAR(50),  -- Type: 'purchase', 'sign_up', 'add_to_cart'
        revenue DECIMAL(10,2),  -- Revenue in USD for purchase conversions
        session_id VARCHAR(36),  -- Session where conversion happened
        user_id VARCHAR(64),  -- Converting user ID
        -- FK: session_id REFERENCES fct_sessions(session_id)
        -- FK: user_id REFERENCES dim_users(user_id)
    );
    ```
    """
    lines = []

    # Table description as comment
    if table.description:
        # Truncate long descriptions
        desc = table.description[:200]
        lines.append(f"-- {table.name}: {desc}")

    # CREATE TABLE
    lines.append(f"CREATE TABLE {table.name} (")

    # Columns
    for i, col in enumerate(table.columns):
        col_type = col.data_type or "TEXT"
        col_str = f"    {col.name} {col_type}"

        # Add comment with PK marker and description
        comment_parts = []
        if col.is_pk:
            comment_parts.append("PK")
        if col.description:
            desc = col.description[:100]
            comment_parts.append(desc)

        if comment_parts:
            col_str += f",  -- {'. '.join(comment_parts)}"
        else:
            col_str += ","

        lines.append(col_str)

    # FK constraints as comments
    for fk in table.fk_constraints:
        lines.append(f"    {fk}")

    lines.append(");")

    return "\n".join(lines)


def assemble_vanilla_context(tables: list[TableDDL], max_tokens: int = 4000) -> str:
    """Assemble all table DDLs into a flat context string.

    Respects the token budget. Tables are ordered with seed matches first.
    """
    sections = []
    running_tokens = 0

    for table in tables:
        ddl = format_table_as_ddl(table)
        ddl_tokens = estimate_token_count(ddl)

        if running_tokens + ddl_tokens > max_tokens:
            sections.append(
                "\n-- (additional tables truncated to fit token budget)"
            )
            break

        sections.append(ddl)
        running_tokens += ddl_tokens

    context = "\n\n".join(sections)

    logger.debug(
        "vanilla_context_assembled",
        tables=len(tables),
        token_estimate=estimate_token_count(context),
    )

    return context


# =============================================================================
# Vanilla Retriever
# =============================================================================


class VanillaRAGRetriever:
    """Best-practice vanilla RAG retriever for text-to-SQL.

    This represents the strongest non-graph baseline:
    1. Schema linking (keyword match table/column names)
    2. Vector search (same embeddings + Neo4j vector index as GraphRAG)
    3. Column-level search
    4. DDL-style context with data types
    5. FK constraint inference from depends_on + shared column names

    What it does NOT do (the only differences from GraphRAG):
    - No multi-hop graph expansion
    - No structural relationship traversal
    - No lineage-aware neighbor discovery
    """

    def __init__(
        self,
        client: Neo4jClient,
        embedder: EmbedderService | None = None,
    ):
        self._client = client
        self._embedder = embedder or EmbedderService()
        self._schema_cache: dict | None = None

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        max_tokens: int = 4000,
    ) -> VanillaRetrievalResult:
        """Retrieve schema context using vanilla RAG techniques.

        Args:
            query: User's natural language question.
            top_k: Number of tables to retrieve.
            max_tokens: Maximum token budget for context.

        Returns:
            VanillaRetrievalResult with DDL-formatted context.
        """
        top_k = top_k or settings.retrieval_top_k

        # Load schema metadata (cached)
        schema_meta = await self._load_schema_metadata()

        # Step 1: Schema linking (keyword match)
        schema_linked_ids = schema_link(
            query,
            schema_meta["tables"],
            schema_meta["columns"],
        )

        # Step 2: Vector search (semantic similarity)
        vector_matched_ids = await self._vector_search(query, top_k)

        # Step 3: Merge and deduplicate (schema-linked tables get priority)
        merged_ids = self._merge_results(
            schema_linked_ids, vector_matched_ids, top_k
        )

        if not merged_ids:
            logger.warning("vanilla_no_tables_found", query=query[:100])
            return VanillaRetrievalResult(
                context="No relevant schema context found for this query.",
                tables_found=[],
                seed_table_count=0,
                total_table_count=0,
                schema_linked_tables=[],
                vector_matched_tables=[],
            )

        # Step 4: Fetch full table context with columns and data types
        tables = await self._fetch_tables_with_ddl(merged_ids)

        # Step 5: Infer FK constraints
        all_tables_for_fk = await self._fetch_tables_with_ddl(
            list(schema_meta["all_table_ids"])
        )
        depends_on_map = schema_meta["depends_on_map"]
        for table in tables:
            table.fk_constraints = infer_fk_constraints(
                table, all_tables_for_fk, depends_on_map
            )

        # Step 6: Assemble as DDL text
        context = assemble_vanilla_context(tables, max_tokens)

        # Resolve table names for metadata
        table_names = [t.name for t in tables]
        sl_names = [
            t["name"] for t in schema_meta["tables"]
            if t["unique_id"] in set(schema_linked_ids)
        ]
        vm_names = [
            t["name"] for t in schema_meta["tables"]
            if t["unique_id"] in set(vector_matched_ids)
        ]

        result = VanillaRetrievalResult(
            context=context,
            tables_found=table_names,
            seed_table_count=len(merged_ids),
            total_table_count=len(tables),
            schema_linked_tables=sl_names,
            vector_matched_tables=vm_names,
        )

        logger.info(
            "vanilla_retrieval_complete",
            query=query[:80],
            schema_linked=len(schema_linked_ids),
            vector_matched=len(vector_matched_ids),
            total_tables=len(tables),
            context_chars=len(context),
        )

        return result

    async def _vector_search(
        self, query: str, top_k: int
    ) -> list[str]:
        """Same vector search as GraphRAG — find tables by embedding similarity."""
        try:
            query_embedding = await self._embedder.embed_query(query)

            # Table-level search
            table_results = await search_tables_by_embedding(
                self._client, query_embedding, top_k
            )
            # Column-level search (same as GraphRAG)
            column_results = await search_columns_by_embedding(
                self._client, query_embedding, top_k
            )

            # Merge scores
            seen: dict[str, float] = {}
            for r in table_results:
                if r.unique_id not in seen or r.score > seen[r.unique_id]:
                    seen[r.unique_id] = r.score

            for r in column_results:
                if r.unique_id not in seen or r.score > seen[r.unique_id]:
                    seen[r.unique_id] = r.score

            sorted_ids = sorted(
                seen.keys(), key=lambda uid: seen[uid], reverse=True
            )
            return sorted_ids[:top_k]

        except Exception as e:
            logger.warning("vanilla_vector_search_failed", error=str(e))
            # Fallback to fulltext
            results = await fulltext_search_tables(
                self._client, query, top_k
            )
            return [r.unique_id for r in results]

    def _merge_results(
        self,
        schema_linked_ids: list[str],
        vector_ids: list[str],
        top_k: int,
    ) -> list[str]:
        """Merge schema-linked and vector search results.

        Schema-linked tables get priority (they're direct keyword matches),
        then vector results fill the remaining slots.
        """
        merged: list[str] = []
        seen: set[str] = set()

        # Schema-linked first
        for uid in schema_linked_ids:
            if uid not in seen:
                merged.append(uid)
                seen.add(uid)

        # Then vector results
        for uid in vector_ids:
            if uid not in seen:
                merged.append(uid)
                seen.add(uid)

        return merged[:top_k]

    async def _fetch_tables_with_ddl(
        self, table_ids: list[str]
    ) -> list[TableDDL]:
        """Fetch tables with full column info including data types from Neo4j.

        Uses the SAME data as GraphRAG (from the Neo4j graph), but formats
        it as DDL instead of structured text.
        """
        query = f"""
        UNWIND $ids AS uid
        MATCH (t:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: uid}})
        OPTIONAL MATCH (t)-[:{RelType.HAS_COLUMN}]->(c:{NodeLabel.COLUMN})
        RETURN
            t.{PropKey.UNIQUE_ID} AS unique_id,
            t.{PropKey.NAME} AS name,
            t.{PropKey.SCHEMA_NAME} AS schema,
            t.{PropKey.DATABASE_NAME} AS database,
            t.{PropKey.DESCRIPTION} AS description,
            collect({{
                name: c.{PropKey.NAME},
                data_type: c.{PropKey.DATA_TYPE},
                description: c.{PropKey.DESCRIPTION},
                is_pk: c.{PropKey.IS_PK}
            }}) AS columns
        """
        records = await self._client.execute_query(query, {"ids": table_ids})

        tables = []
        for r in records:
            columns = [
                ColumnDDL(
                    name=c["name"],
                    data_type=c.get("data_type"),
                    description=c.get("description", ""),
                    is_pk=c.get("is_pk", False),
                )
                for c in r["columns"]
                if c.get("name") is not None
            ]

            tables.append(
                TableDDL(
                    unique_id=r["unique_id"],
                    name=r["name"],
                    schema=r.get("schema", ""),
                    database=r.get("database", ""),
                    description=r.get("description", ""),
                    columns=columns,
                )
            )

        return tables

    async def _load_schema_metadata(self) -> dict:
        """Load schema metadata from Neo4j for schema linking and FK inference.

        Cached after first call since schema doesn't change during a benchmark.
        """
        if self._schema_cache is not None:
            return self._schema_cache

        # Fetch all tables
        table_query = f"""
        MATCH (t:{NodeLabel.TABLE})
        WHERE t.{PropKey.DEPRECATED} IS NULL OR t.{PropKey.DEPRECATED} = false
        RETURN t.{PropKey.UNIQUE_ID} AS unique_id, t.{PropKey.NAME} AS name
        """
        table_records = await self._client.execute_query(table_query, {})
        tables = [
            {"unique_id": r["unique_id"], "name": r["name"]}
            for r in table_records
        ]
        all_table_ids = {r["unique_id"] for r in table_records}

        # Fetch all columns with parent table reference
        col_query = f"""
        MATCH (t:{NodeLabel.TABLE})-[:{RelType.HAS_COLUMN}]->(c:{NodeLabel.COLUMN})
        WHERE t.{PropKey.DEPRECATED} IS NULL OR t.{PropKey.DEPRECATED} = false
        RETURN c.{PropKey.NAME} AS name, t.{PropKey.UNIQUE_ID} AS table_unique_id
        """
        col_records = await self._client.execute_query(col_query, {})
        columns = [
            {"name": r["name"], "table_unique_id": r["table_unique_id"]}
            for r in col_records
        ]

        # Fetch depends_on relationships for FK inference
        dep_query = f"""
        MATCH (a:{NodeLabel.TABLE})-[:{RelType.DEPENDS_ON}]->(b:{NodeLabel.TABLE})
        WHERE (a.{PropKey.DEPRECATED} IS NULL OR a.{PropKey.DEPRECATED} = false)
          AND (b.{PropKey.DEPRECATED} IS NULL OR b.{PropKey.DEPRECATED} = false)
        RETURN a.{PropKey.UNIQUE_ID} AS from_id, b.{PropKey.UNIQUE_ID} AS to_id
        """
        dep_records = await self._client.execute_query(dep_query, {})
        depends_on_map: dict[str, list[str]] = {}
        for r in dep_records:
            depends_on_map.setdefault(r["from_id"], []).append(r["to_id"])

        self._schema_cache = {
            "tables": tables,
            "columns": columns,
            "all_table_ids": all_table_ids,
            "depends_on_map": depends_on_map,
        }

        logger.info(
            "schema_metadata_loaded",
            tables=len(tables),
            columns=len(columns),
            dependencies=sum(len(v) for v in depends_on_map.values()),
        )

        return self._schema_cache
