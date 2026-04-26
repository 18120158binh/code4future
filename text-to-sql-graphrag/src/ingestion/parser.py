"""dbt artifact parser.

Parses manifest.json and catalog.json into intermediate ParsedTable/ParsedColumn
representations that are decoupled from both dbt and Neo4j internals.
"""

from __future__ import annotations

import json
from pathlib import Path

import structlog

from src.graph.schema import ParsedColumn, ParsedTable

logger = structlog.get_logger(__name__)


def parse_dbt_docs(docs_path: Path) -> list[ParsedTable]:
    """Parse dbt manifest.json and catalog.json into ParsedTable objects.

    Args:
        docs_path: Path to directory containing manifest.json and catalog.json.

    Returns:
        List of ParsedTable objects representing all models and sources.
    """
    manifest_path = docs_path / "manifest.json"
    catalog_path = docs_path / "catalog.json"

    if not manifest_path.exists():
        raise FileNotFoundError(f"manifest.json not found at {manifest_path}")

    manifest = _load_json(manifest_path)
    catalog = _load_json(catalog_path) if catalog_path.exists() else None

    # Build column type lookup from catalog
    catalog_columns = _extract_catalog_columns(catalog) if catalog else {}

    tables: list[ParsedTable] = []

    # Parse models, seeds, snapshots from manifest nodes
    nodes = manifest.get("nodes", {})
    for unique_id, node in nodes.items():
        resource_type = node.get("resource_type", "")
        if resource_type not in ("model", "seed", "snapshot"):
            continue  # skip tests, analyses, etc.

        table = _parse_node(unique_id, node, catalog_columns)
        tables.append(table)

    # Parse sources
    sources = manifest.get("sources", {})
    for unique_id, source in sources.items():
        table = _parse_source(unique_id, source, catalog_columns)
        tables.append(table)

    logger.info(
        "dbt_docs_parsed",
        path=str(docs_path),
        models=sum(1 for t in tables if t.table_type == "model"),
        sources=sum(1 for t in tables if t.table_type == "source"),
        seeds=sum(1 for t in tables if t.table_type == "seed"),
        total_columns=sum(len(t.columns) for t in tables),
    )
    return tables


def _load_json(path: Path) -> dict:
    """Load and parse a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _extract_catalog_columns(catalog: dict) -> dict[str, dict[str, dict]]:
    """Build a lookup: {unique_id: {column_name: column_metadata}} from catalog.

    The catalog provides database-level metadata that the manifest may not have,
    like actual data types and column ordering.
    """
    result: dict[str, dict[str, dict]] = {}

    for unique_id, node_data in catalog.get("nodes", {}).items():
        columns = node_data.get("columns", {})
        result[unique_id] = {
            col_name.lower(): col_meta
            for col_name, col_meta in columns.items()
        }

    for unique_id, source_data in catalog.get("sources", {}).items():
        columns = source_data.get("columns", {})
        result[unique_id] = {
            col_name.lower(): col_meta
            for col_name, col_meta in columns.items()
        }

    return result


def _parse_node(
    unique_id: str,
    node: dict,
    catalog_columns: dict[str, dict[str, dict]],
) -> ParsedTable:
    """Parse a manifest node (model/seed/snapshot) into a ParsedTable."""
    columns = _merge_columns(
        unique_id=unique_id,
        manifest_columns=node.get("columns", {}),
        catalog_columns=catalog_columns.get(unique_id, {}),
    )

    depends_on_nodes = node.get("depends_on", {}).get("nodes", [])

    return ParsedTable(
        unique_id=unique_id,
        name=node.get("name", ""),
        database=node.get("database", ""),
        schema=node.get("schema", ""),
        description=node.get("description", ""),
        materialization=node.get("config", {}).get("materialized", "view"),
        table_type=node.get("resource_type", "model"),
        compiled_sql=node.get("compiled_code") or node.get("compiled_sql"),
        raw_sql=node.get("raw_code") or node.get("raw_sql"),
        tags=node.get("tags", []),
        depends_on=depends_on_nodes,
        columns=columns,
    )


def _parse_source(
    unique_id: str,
    source: dict,
    catalog_columns: dict[str, dict[str, dict]],
) -> ParsedTable:
    """Parse a manifest source into a ParsedTable."""
    columns = _merge_columns(
        unique_id=unique_id,
        manifest_columns=source.get("columns", {}),
        catalog_columns=catalog_columns.get(unique_id, {}),
    )

    return ParsedTable(
        unique_id=unique_id,
        name=source.get("name", ""),
        database=source.get("database", ""),
        schema=source.get("schema", ""),
        description=source.get("description", ""),
        materialization="table",  # sources are always physical tables
        table_type="source",
        compiled_sql=None,
        raw_sql=None,
        tags=source.get("tags", []),
        depends_on=[],  # sources have no upstream dependencies
        columns=columns,
    )


def _merge_columns(
    unique_id: str,
    manifest_columns: dict,
    catalog_columns: dict[str, dict],
) -> list[ParsedColumn]:
    """Merge column info from manifest (descriptions) and catalog (data types).

    The manifest has user-written descriptions and tests.
    The catalog has the actual database data types and column ordering.
    We merge both to get the richest possible column representation.
    """
    # Start with all column names from both sources
    all_column_names: set[str] = set()
    all_column_names.update(k.lower() for k in manifest_columns.keys())
    all_column_names.update(catalog_columns.keys())

    columns: list[ParsedColumn] = []
    for col_name in sorted(all_column_names):
        manifest_col = manifest_columns.get(col_name, {})
        # Case-insensitive lookup in manifest (dbt sometimes preserves case)
        if not manifest_col:
            for k, v in manifest_columns.items():
                if k.lower() == col_name:
                    manifest_col = v
                    break

        catalog_col = catalog_columns.get(col_name, {})

        # Determine data type: catalog is authoritative, manifest is fallback
        data_type = (
            catalog_col.get("type")
            or manifest_col.get("data_type")
            or None
        )

        # Column index from catalog
        col_index = catalog_col.get("index")

        # Check if column has primary key test in manifest
        is_pk = False
        if isinstance(manifest_col, dict):
            tests = manifest_col.get("tests", [])
            # dbt tests can be strings or dicts
            for test in tests:
                test_name = test if isinstance(test, str) else list(test.keys())[0] if isinstance(test, dict) else ""
                if test_name in ("unique", "not_null"):
                    is_pk = True

        columns.append(
            ParsedColumn(
                name=col_name,
                data_type=data_type,
                description=manifest_col.get("description", "") if isinstance(manifest_col, dict) else "",
                is_pk=is_pk,
                is_nullable=None,  # Could be inferred from tests
                column_index=col_index,
                table_unique_id=unique_id,
            )
        )

    return columns
