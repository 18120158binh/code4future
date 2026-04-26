"""Neo4j index and constraint management.

Creates all required indexes and constraints for the knowledge graph.
Should be run once during initial setup and idempotently on restarts.
"""

from __future__ import annotations

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel

logger = structlog.get_logger(__name__)


# Each statement is idempotent (IF NOT EXISTS)
CONSTRAINTS = [
    # Uniqueness constraints
    f"""
    CREATE CONSTRAINT unique_table_id IF NOT EXISTS
    FOR (t:{NodeLabel.TABLE}) REQUIRE t.unique_id IS UNIQUE
    """,
    f"""
    CREATE CONSTRAINT unique_source_id IF NOT EXISTS
    FOR (s:{NodeLabel.SOURCE}) REQUIRE s.unique_id IS UNIQUE
    """,
    f"""
    CREATE CONSTRAINT unique_database_name IF NOT EXISTS
    FOR (d:{NodeLabel.DATABASE}) REQUIRE d.name IS UNIQUE
    """,
    f"""
    CREATE CONSTRAINT unique_business_term IF NOT EXISTS
    FOR (bt:{NodeLabel.BUSINESS_TERM}) REQUIRE bt.name IS UNIQUE
    """,
]

INDEXES = [
    # Schema lookup
    f"""
    CREATE INDEX schema_lookup IF NOT EXISTS
    FOR (s:{NodeLabel.SCHEMA}) ON (s.name, s.database)
    """,
    # Column lookup by table
    f"""
    CREATE INDEX column_table_lookup IF NOT EXISTS
    FOR (c:{NodeLabel.COLUMN}) ON (c.table_id, c.name)
    """,
    # Full-text search indexes
    f"""
    CREATE FULLTEXT INDEX table_fulltext IF NOT EXISTS
    FOR (t:{NodeLabel.TABLE}) ON EACH [t.name, t.description]
    """,
    f"""
    CREATE FULLTEXT INDEX column_fulltext IF NOT EXISTS
    FOR (c:{NodeLabel.COLUMN}) ON EACH [c.name, c.description]
    """,
]

# Vector indexes are created separately because they require dimension config
VECTOR_INDEXES = [
    {
        "name": "table_desc_embedding",
        "label": NodeLabel.TABLE,
        "property": "description_embedding",
    },
    {
        "name": "column_desc_embedding",
        "label": NodeLabel.COLUMN,
        "property": "description_embedding",
    },
]


def _build_vector_index_query(name: str, label: str, prop: str, dims: int) -> str:
    """Build a CREATE VECTOR INDEX Cypher statement."""
    return f"""
    CREATE VECTOR INDEX {name} IF NOT EXISTS
    FOR (n:{label}) ON (n.{prop})
    OPTIONS {{
        indexConfig: {{
            `vector.dimensions`: {dims},
            `vector.similarity_function`: 'cosine'
        }}
    }}
    """


async def setup_indexes(client: Neo4jClient) -> None:
    """Create all constraints, indexes, and vector indexes.

    This function is idempotent — safe to call on every startup.
    """
    dims = settings.embedding_dimensions

    # 1. Constraints
    for stmt in CONSTRAINTS:
        try:
            await client.execute_query(stmt.strip())
            logger.debug("constraint_created", statement=stmt.strip()[:60])
        except Exception as e:
            logger.warning("constraint_skipped", error=str(e)[:100])

    # 2. Standard indexes
    for stmt in INDEXES:
        try:
            await client.execute_query(stmt.strip())
            logger.debug("index_created", statement=stmt.strip()[:60])
        except Exception as e:
            logger.warning("index_skipped", error=str(e)[:100])

    # 3. Vector indexes
    for vi in VECTOR_INDEXES:
        query = _build_vector_index_query(vi["name"], vi["label"], vi["property"], dims)
        try:
            await client.execute_query(query.strip())
            logger.debug("vector_index_created", name=vi["name"], dimensions=dims)
        except Exception as e:
            logger.warning("vector_index_skipped", name=vi["name"], error=str(e)[:100])

    logger.info(
        "indexes_setup_complete",
        constraints=len(CONSTRAINTS),
        indexes=len(INDEXES),
        vector_indexes=len(VECTOR_INDEXES),
    )
