"""Vector search using Neo4j's native vector index.

Performs semantic search over table and column description embeddings
to find the most relevant schema elements for a user's query.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel, PropKey, RelType

logger = structlog.get_logger(__name__)


@dataclass
class VectorSearchResult:
    """A single result from vector search."""

    unique_id: str         # Table unique_id or column table_id
    name: str
    label: str             # "Table" or "Column"
    description: str
    score: float           # Cosine similarity score
    table_name: str | None = None  # For columns: the parent table name


async def search_tables_by_embedding(
    client: Neo4jClient,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[VectorSearchResult]:
    """Search for tables whose descriptions are semantically similar to the query.

    Uses Neo4j's native vector index for cosine similarity search.
    """
    top_k = top_k or settings.retrieval_top_k

    query = f"""
    CALL db.index.vector.queryNodes('table_desc_embedding', $top_k, $embedding)
    YIELD node, score
    WHERE node.{PropKey.DEPRECATED} IS NULL OR node.{PropKey.DEPRECATED} = false
    RETURN
        node.{PropKey.UNIQUE_ID} AS unique_id,
        node.{PropKey.NAME} AS name,
        node.{PropKey.DESCRIPTION} AS description,
        score
    ORDER BY score DESC
    """
    records = await client.execute_query(
        query, {"embedding": query_embedding, "top_k": top_k}
    )

    results = [
        VectorSearchResult(
            unique_id=r["unique_id"],
            name=r["name"],
            label=NodeLabel.TABLE,
            description=r.get("description", ""),
            score=r["score"],
        )
        for r in records
    ]

    logger.debug("vector_search_tables", results=len(results), top_k=top_k)
    return results


async def search_columns_by_embedding(
    client: Neo4jClient,
    query_embedding: list[float],
    top_k: int | None = None,
) -> list[VectorSearchResult]:
    """Search for columns whose descriptions are semantically similar to the query."""
    top_k = top_k or settings.retrieval_top_k

    query = f"""
    CALL db.index.vector.queryNodes('column_desc_embedding', $top_k, $embedding)
    YIELD node, score
    MATCH (t:{NodeLabel.TABLE})-[:{RelType.HAS_COLUMN}]->(node)
    WHERE t.{PropKey.DEPRECATED} IS NULL OR t.{PropKey.DEPRECATED} = false
    RETURN
        node.table_id AS unique_id,
        node.{PropKey.NAME} AS name,
        node.{PropKey.DESCRIPTION} AS description,
        t.{PropKey.NAME} AS table_name,
        score
    ORDER BY score DESC
    """
    records = await client.execute_query(
        query, {"embedding": query_embedding, "top_k": top_k}
    )

    results = [
        VectorSearchResult(
            unique_id=r["unique_id"],
            name=r["name"],
            label=NodeLabel.COLUMN,
            description=r.get("description", ""),
            score=r["score"],
            table_name=r.get("table_name"),
        )
        for r in records
    ]

    logger.debug("vector_search_columns", results=len(results), top_k=top_k)
    return results


async def fulltext_search_tables(
    client: Neo4jClient,
    query_text: str,
    top_k: int | None = None,
) -> list[VectorSearchResult]:
    """Fallback: full-text keyword search when vector search is unavailable.

    Useful when embeddings haven't been generated yet or as a complement
    to vector search for exact name matches.
    """
    top_k = top_k or settings.retrieval_top_k

    query = f"""
    CALL db.index.fulltext.queryNodes('table_fulltext', $query)
    YIELD node, score
    WHERE node.{PropKey.DEPRECATED} IS NULL OR node.{PropKey.DEPRECATED} = false
    RETURN
        node.{PropKey.UNIQUE_ID} AS unique_id,
        node.{PropKey.NAME} AS name,
        node.{PropKey.DESCRIPTION} AS description,
        score
    ORDER BY score DESC
    LIMIT $top_k
    """
    records = await client.execute_query(
        query, {"query": query_text, "top_k": top_k}
    )

    results = [
        VectorSearchResult(
            unique_id=r["unique_id"],
            name=r["name"],
            label=NodeLabel.TABLE,
            description=r.get("description", ""),
            score=r["score"],
        )
        for r in records
    ]

    logger.debug("fulltext_search_tables", results=len(results), query=query_text[:50])
    return results
