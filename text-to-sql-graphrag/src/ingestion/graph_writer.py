"""Neo4j graph writer — MERGE-based upserts for the knowledge graph.

All write operations are idempotent using MERGE with ON CREATE/ON MATCH SET.
This ensures the graph stays consistent regardless of how many times
the ingestion pipeline runs.
"""

from __future__ import annotations

from datetime import datetime, timezone

import structlog

from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel, PropKey, RelType, ParsedTable
from src.ingestion.differ import compute_content_hash

logger = structlog.get_logger(__name__)


async def write_tables_to_graph(
    client: Neo4jClient,
    tables: list[ParsedTable],
    embeddings: dict[str, list[float]] | None = None,
) -> None:
    """Write parsed tables to Neo4j using MERGE-based upserts.

    Creates/updates:
    1. Database nodes
    2. Schema nodes + CONTAINS_SCHEMA edges
    3. Table nodes + CONTAINS_TABLE edges
    4. Column nodes + HAS_COLUMN edges
    5. DEPENDS_ON edges between tables
    """
    if not tables:
        logger.info("no_tables_to_write")
        return

    embeddings = embeddings or {}
    now = datetime.now(timezone.utc).isoformat()

    # 1. Upsert databases
    databases = {t.database for t in tables if t.database}
    for db_name in databases:
        await _upsert_database(client, db_name, now)

    # 2. Upsert schemas
    schemas = {(t.database, t.schema) for t in tables if t.schema}
    for db_name, schema_name in schemas:
        await _upsert_schema(client, db_name, schema_name, now)

    # 3. Upsert tables with columns
    for table in tables:
        content_hash = compute_content_hash(table)
        table_embedding = embeddings.get(f"table:{table.unique_id}")

        await _upsert_table(client, table, content_hash, table_embedding, now)

        # 4. Upsert columns
        for col in table.columns:
            col_embedding = embeddings.get(f"column:{table.unique_id}:{col.name}")
            await _upsert_column(client, table.unique_id, col, col_embedding, now)

    # 5. Create DEPENDS_ON edges
    for table in tables:
        for dep_id in table.depends_on:
            await _upsert_depends_on(client, table.unique_id, dep_id)

    logger.info("graph_write_complete", tables=len(tables))


async def soft_delete_tables(
    client: Neo4jClient,
    deleted_ids: list[str],
) -> None:
    """Mark tables as deprecated (soft-delete) instead of removing them.

    This preserves lineage history while signaling that the model
    no longer exists in the current dbt project.
    """
    if not deleted_ids:
        return

    now = datetime.now(timezone.utc).isoformat()
    query = f"""
    UNWIND $ids AS uid
    MATCH (t:{NodeLabel.TABLE} {{unique_id: uid}})
    SET t.{PropKey.DEPRECATED} = true,
        t.{PropKey.LAST_SYNCED_AT} = $now
    """
    await client.execute_query(query, {"ids": deleted_ids, "now": now})
    logger.info("tables_soft_deleted", count=len(deleted_ids))


# =============================================================================
# Private upsert functions
# =============================================================================


async def _upsert_database(client: Neo4jClient, name: str, now: str) -> None:
    """MERGE a Database node."""
    query = f"""
    MERGE (d:{NodeLabel.DATABASE} {{{PropKey.NAME}: $name}})
    ON CREATE SET d.{PropKey.LAST_SYNCED_AT} = $now
    ON MATCH SET d.{PropKey.LAST_SYNCED_AT} = $now
    """
    await client.execute_query(query, {"name": name, "now": now})


async def _upsert_schema(
    client: Neo4jClient,
    database: str,
    schema_name: str,
    now: str,
) -> None:
    """MERGE a Schema node and connect it to its Database."""
    query = f"""
    MATCH (d:{NodeLabel.DATABASE} {{{PropKey.NAME}: $database}})
    MERGE (s:{NodeLabel.SCHEMA} {{{PropKey.NAME}: $schema_name, database: $database}})
    ON CREATE SET s.{PropKey.LAST_SYNCED_AT} = $now
    ON MATCH SET s.{PropKey.LAST_SYNCED_AT} = $now
    MERGE (d)-[:{RelType.CONTAINS_SCHEMA}]->(s)
    """
    await client.execute_query(
        query, {"database": database, "schema_name": schema_name, "now": now}
    )


async def _upsert_table(
    client: Neo4jClient,
    table: ParsedTable,
    content_hash: str,
    embedding: list[float] | None,
    now: str,
) -> None:
    """MERGE a Table node and connect it to its Schema."""
    params = {
        "unique_id": table.unique_id,
        "name": table.name,
        "database": table.database,
        "schema_name": table.schema,
        "description": table.description,
        "materialization": table.materialization,
        "table_type": table.table_type,
        "compiled_sql": table.compiled_sql,
        "raw_sql": table.raw_sql,
        "tags": table.tags,
        "content_hash": content_hash,
        "now": now,
        "deprecated": False,
    }

    # Build the SET clause dynamically based on whether we have an embedding
    embedding_set = ""
    if embedding is not None:
        params["embedding"] = embedding
        embedding_set = f", t.{PropKey.DESCRIPTION_EMBEDDING} = $embedding"

    query = f"""
    MATCH (s:{NodeLabel.SCHEMA} {{{PropKey.NAME}: $schema_name, database: $database}})
    MERGE (t:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: $unique_id}})
    ON CREATE SET
        t.{PropKey.NAME} = $name,
        t.{PropKey.DESCRIPTION} = $description,
        t.{PropKey.MATERIALIZATION} = $materialization,
        t.{PropKey.TABLE_TYPE} = $table_type,
        t.{PropKey.COMPILED_SQL} = $compiled_sql,
        t.{PropKey.RAW_SQL} = $raw_sql,
        t.{PropKey.DATABASE_NAME} = $database,
        t.{PropKey.SCHEMA_NAME} = $schema_name,
        t.{PropKey.TAGS} = $tags,
        t.{PropKey.CONTENT_HASH} = $content_hash,
        t.{PropKey.LAST_SYNCED_AT} = $now,
        t.{PropKey.DEPRECATED} = $deprecated
        {embedding_set}
    ON MATCH SET
        t.{PropKey.NAME} = $name,
        t.{PropKey.DESCRIPTION} = $description,
        t.{PropKey.MATERIALIZATION} = $materialization,
        t.{PropKey.TABLE_TYPE} = $table_type,
        t.{PropKey.COMPILED_SQL} = $compiled_sql,
        t.{PropKey.RAW_SQL} = $raw_sql,
        t.{PropKey.DATABASE_NAME} = $database,
        t.{PropKey.SCHEMA_NAME} = $schema_name,
        t.{PropKey.TAGS} = $tags,
        t.{PropKey.CONTENT_HASH} = $content_hash,
        t.{PropKey.LAST_SYNCED_AT} = $now,
        t.{PropKey.DEPRECATED} = $deprecated
        {embedding_set}
    MERGE (s)-[:{RelType.CONTAINS_TABLE}]->(t)
    """
    await client.execute_query(query, params)


async def _upsert_column(
    client: Neo4jClient,
    table_unique_id: str,
    column,
    embedding: list[float] | None,
    now: str,
) -> None:
    """MERGE a Column node and connect it to its Table."""
    params = {
        "table_id": table_unique_id,
        "name": column.name,
        "data_type": column.data_type,
        "description": column.description,
        "is_pk": column.is_pk,
        "is_nullable": column.is_nullable,
        "column_index": column.column_index,
        "now": now,
    }

    embedding_set = ""
    if embedding is not None:
        params["embedding"] = embedding
        embedding_set = f", c.{PropKey.DESCRIPTION_EMBEDDING} = $embedding"

    query = f"""
    MATCH (t:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: $table_id}})
    MERGE (c:{NodeLabel.COLUMN} {{table_id: $table_id, {PropKey.NAME}: $name}})
    ON CREATE SET
        c.{PropKey.DATA_TYPE} = $data_type,
        c.{PropKey.DESCRIPTION} = $description,
        c.{PropKey.IS_PK} = $is_pk,
        c.is_nullable = $is_nullable,
        c.{PropKey.COLUMN_INDEX} = $column_index,
        c.{PropKey.LAST_SYNCED_AT} = $now
        {embedding_set}
    ON MATCH SET
        c.{PropKey.DATA_TYPE} = $data_type,
        c.{PropKey.DESCRIPTION} = $description,
        c.{PropKey.IS_PK} = $is_pk,
        c.is_nullable = $is_nullable,
        c.{PropKey.COLUMN_INDEX} = $column_index,
        c.{PropKey.LAST_SYNCED_AT} = $now
        {embedding_set}
    MERGE (t)-[:{RelType.HAS_COLUMN}]->(c)
    """
    await client.execute_query(query, params)


async def _upsert_depends_on(
    client: Neo4jClient,
    from_id: str,
    to_id: str,
) -> None:
    """MERGE a DEPENDS_ON edge between two tables."""
    query = f"""
    MATCH (a:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: $from_id}})
    MATCH (b:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: $to_id}})
    MERGE (a)-[:{RelType.DEPENDS_ON}]->(b)
    """
    await client.execute_query(query, {"from_id": from_id, "to_id": to_id})
