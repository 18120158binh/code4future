"""Hash-based change detection for incremental graph updates.

Computes content hashes for parsed models and compares them against
stored hashes in Neo4j to determine what changed since the last sync.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import structlog

from src.graph.client import Neo4jClient
from src.graph.schema import NodeLabel, ParsedTable, PropKey

logger = structlog.get_logger(__name__)


@dataclass
class DiffResult:
    """Result of comparing current dbt docs against the existing graph."""

    new: list[ParsedTable]        # Nodes that don't exist in graph yet
    modified: list[ParsedTable]   # Nodes whose content hash changed
    unchanged: list[ParsedTable]  # Nodes with matching content hash
    deleted: list[str]            # unique_ids in graph but not in current docs


def compute_content_hash(table: ParsedTable) -> str:
    """Compute a deterministic SHA256 hash of a table's content.

    The hash captures all semantically meaningful fields so that
    any change in description, columns, SQL, or dependencies is detected.
    """
    content = {
        "unique_id": table.unique_id,
        "name": table.name,
        "database": table.database,
        "schema": table.schema,
        "description": table.description,
        "materialization": table.materialization,
        "table_type": table.table_type,
        "compiled_sql": table.compiled_sql,
        "tags": sorted(table.tags),
        "depends_on": sorted(table.depends_on),
        "columns": [
            {
                "name": col.name,
                "data_type": col.data_type,
                "description": col.description,
                "is_pk": col.is_pk,
            }
            for col in sorted(table.columns, key=lambda c: c.name)
        ],
    }
    serialized = json.dumps(content, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def compute_diff(
    client: Neo4jClient,
    parsed_tables: list[ParsedTable],
) -> DiffResult:
    """Compare parsed tables against the current graph state.

    Steps:
    1. Compute content hash for each parsed table
    2. Fetch existing hashes from Neo4j
    3. Classify each table as new, modified, or unchanged
    4. Identify deleted tables (in graph but not in current docs)
    """
    # 1. Compute hashes for all parsed tables
    current_hashes: dict[str, str] = {
        table.unique_id: compute_content_hash(table)
        for table in parsed_tables
    }

    # 2. Fetch stored hashes from Neo4j
    stored_hashes = await _fetch_stored_hashes(client)

    # 3. Classify
    new_tables: list[ParsedTable] = []
    modified_tables: list[ParsedTable] = []
    unchanged_tables: list[ParsedTable] = []

    for table in parsed_tables:
        uid = table.unique_id
        new_hash = current_hashes[uid]
        old_hash = stored_hashes.get(uid)

        if old_hash is None:
            new_tables.append(table)
        elif old_hash != new_hash:
            modified_tables.append(table)
        else:
            unchanged_tables.append(table)

    # 4. Find deleted nodes
    current_ids = set(current_hashes.keys())
    stored_ids = set(stored_hashes.keys())
    deleted_ids = list(stored_ids - current_ids)

    logger.info(
        "diff_computed",
        new=len(new_tables),
        modified=len(modified_tables),
        unchanged=len(unchanged_tables),
        deleted=len(deleted_ids),
    )

    return DiffResult(
        new=new_tables,
        modified=modified_tables,
        unchanged=unchanged_tables,
        deleted=deleted_ids,
    )


async def _fetch_stored_hashes(client: Neo4jClient) -> dict[str, str]:
    """Fetch all {unique_id: content_hash} pairs from Neo4j."""
    query = f"""
    MATCH (t:{NodeLabel.TABLE})
    WHERE t.{PropKey.CONTENT_HASH} IS NOT NULL
    RETURN t.{PropKey.UNIQUE_ID} AS unique_id, t.{PropKey.CONTENT_HASH} AS content_hash
    """
    records = await client.execute_query(query)
    return {r["unique_id"]: r["content_hash"] for r in records}
