"""Cypher-based graph traversal for structural context expansion.

After vector search identifies seed tables, this module expands
outward through the graph to discover:
- Join paths between tables (via DEPENDS_ON, FK_REFERENCES)
- All columns of matched tables
- Related upstream/downstream models
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel, RelType, PropKey

logger = structlog.get_logger(__name__)


@dataclass
class TableContext:
    """Full context for a single table retrieved from the graph."""

    unique_id: str
    name: str
    schema: str
    database: str
    description: str
    materialization: str
    table_type: str
    columns: list[ColumnContext] = field(default_factory=list)


@dataclass
class ColumnContext:
    """Column-level context for prompt assembly."""

    name: str
    data_type: str | None
    description: str
    is_pk: bool


@dataclass
class RelationshipContext:
    """A relationship between two tables."""

    from_table: str
    to_table: str
    relationship_type: str  # "DEPENDS_ON", "FK_REFERENCES"
    from_column: str | None = None
    to_column: str | None = None


@dataclass
class SubGraph:
    """The assembled sub-graph context for prompt building."""

    tables: list[TableContext]
    relationships: list[RelationshipContext]
    query_tables: list[str]  # Original seed table names from vector search


async def expand_from_seeds(
    client: Neo4jClient,
    seed_table_ids: list[str],
    hops: int | None = None,
) -> SubGraph:
    """Expand outward from seed tables to build a connected sub-graph.

    Steps:
    1. Fetch full context for each seed table (including columns)
    2. Traverse N hops to find connected tables
    3. Discover relationships (DEPENDS_ON, FK_REFERENCES) between all tables
    4. Return assembled SubGraph
    """
    hops = hops or settings.graph_expansion_hops

    if not seed_table_ids:
        return SubGraph(tables=[], relationships=[], query_tables=[])

    # 1. Get seed table names for reference
    seed_names = await _get_table_names(client, seed_table_ids)

    # 2. Expand to find all related table IDs within N hops
    all_table_ids = await _expand_neighbors(client, seed_table_ids, hops)

    # 3. Fetch full context for all tables
    tables = await _fetch_tables_with_columns(client, list(all_table_ids))

    # 4. Discover relationships between these tables
    relationships = await _fetch_relationships(client, list(all_table_ids))

    logger.info(
        "subgraph_expanded",
        seed_tables=len(seed_table_ids),
        total_tables=len(tables),
        relationships=len(relationships),
        hops=hops,
    )

    return SubGraph(
        tables=tables,
        relationships=relationships,
        query_tables=seed_names,
    )


async def _get_table_names(client: Neo4jClient, table_ids: list[str]) -> list[str]:
    """Fetch table names for a list of unique_ids."""
    query = f"""
    UNWIND $ids AS uid
    MATCH (t:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: uid}})
    RETURN t.{PropKey.NAME} AS name
    """
    records = await client.execute_query(query, {"ids": table_ids})
    return [r["name"] for r in records]


async def _expand_neighbors(
    client: Neo4jClient,
    seed_ids: list[str],
    hops: int,
) -> set[str]:
    """Find all tables within N hops of the seed tables.

    Traverses both DEPENDS_ON and FK_REFERENCES in both directions.
    """
    query = f"""
    UNWIND $seeds AS seed_id
    MATCH (seed:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: seed_id}})
    CALL apoc.neighbors.tohop(seed, '{RelType.DEPENDS_ON}|{RelType.FK_REFERENCES}', $hops)
    YIELD node
    WHERE node:{NodeLabel.TABLE}
      AND (node.{PropKey.DEPRECATED} IS NULL OR node.{PropKey.DEPRECATED} = false)
    RETURN DISTINCT node.{PropKey.UNIQUE_ID} AS unique_id
    """

    # Try with APOC first, fall back to manual traversal
    try:
        records = await client.execute_query(
            query, {"seeds": seed_ids, "hops": hops}
        )
        neighbor_ids = {r["unique_id"] for r in records}
    except Exception:
        logger.debug("apoc_not_available, falling back to manual traversal")
        neighbor_ids = await _expand_neighbors_manual(client, seed_ids, hops)

    # Always include seeds themselves
    neighbor_ids.update(seed_ids)
    return neighbor_ids


async def _expand_neighbors_manual(
    client: Neo4jClient,
    seed_ids: list[str],
    hops: int,
) -> set[str]:
    """Manual neighbor expansion without APOC, using variable-length paths."""
    query = f"""
    UNWIND $seeds AS seed_id
    MATCH (seed:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: seed_id}})
    MATCH (seed)-[:{RelType.DEPENDS_ON}|{RelType.FK_REFERENCES}*1..{hops}]-(neighbor:{NodeLabel.TABLE})
    WHERE neighbor.{PropKey.DEPRECATED} IS NULL OR neighbor.{PropKey.DEPRECATED} = false
    RETURN DISTINCT neighbor.{PropKey.UNIQUE_ID} AS unique_id
    """
    records = await client.execute_query(query, {"seeds": seed_ids})
    return {r["unique_id"] for r in records}


async def _fetch_tables_with_columns(
    client: Neo4jClient,
    table_ids: list[str],
) -> list[TableContext]:
    """Fetch complete table context including all columns."""
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
        t.{PropKey.MATERIALIZATION} AS materialization,
        t.{PropKey.TABLE_TYPE} AS table_type,
        collect({{
            name: c.{PropKey.NAME},
            data_type: c.{PropKey.DATA_TYPE},
            description: c.{PropKey.DESCRIPTION},
            is_pk: c.{PropKey.IS_PK}
        }}) AS columns
    """
    records = await client.execute_query(query, {"ids": table_ids})

    tables = []
    for r in records:
        columns = [
            ColumnContext(
                name=c["name"],
                data_type=c.get("data_type"),
                description=c.get("description", ""),
                is_pk=c.get("is_pk", False),
            )
            for c in r["columns"]
            if c.get("name") is not None  # Filter out empty collect results
        ]

        tables.append(
            TableContext(
                unique_id=r["unique_id"],
                name=r["name"],
                schema=r.get("schema", ""),
                database=r.get("database", ""),
                description=r.get("description", ""),
                materialization=r.get("materialization", ""),
                table_type=r.get("table_type", ""),
                columns=columns,
            )
        )

    return tables


async def _fetch_relationships(
    client: Neo4jClient,
    table_ids: list[str],
) -> list[RelationshipContext]:
    """Fetch all relationships between the given tables."""
    query = f"""
    UNWIND $ids AS uid
    MATCH (a:{NodeLabel.TABLE} {{{PropKey.UNIQUE_ID}: uid}})
        -[r:{RelType.DEPENDS_ON}|{RelType.FK_REFERENCES}]->
          (b:{NodeLabel.TABLE})
    WHERE b.{PropKey.UNIQUE_ID} IN $ids
    RETURN
        a.{PropKey.NAME} AS from_table,
        b.{PropKey.NAME} AS to_table,
        type(r) AS rel_type,
        r.from_column AS from_column,
        r.to_column AS to_column
    """
    records = await client.execute_query(query, {"ids": table_ids})

    return [
        RelationshipContext(
            from_table=r["from_table"],
            to_table=r["to_table"],
            relationship_type=r["rel_type"],
            from_column=r.get("from_column"),
            to_column=r.get("to_column"),
        )
        for r in records
    ]
