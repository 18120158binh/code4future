"""Neo4j schema definitions — node labels, relationship types, and properties.

This is the canonical reference for the graph data model.
All graph operations should use these constants to avoid typos.
"""

from __future__ import annotations

from dataclasses import dataclass


# =============================================================================
# Node Labels
# =============================================================================

class NodeLabel:
    """Constants for Neo4j node labels."""

    DATABASE = "Database"
    SCHEMA = "Schema"
    TABLE = "Table"
    COLUMN = "Column"
    SOURCE = "Source"
    BUSINESS_TERM = "BusinessTerm"


# =============================================================================
# Relationship Types
# =============================================================================

class RelType:
    """Constants for Neo4j relationship types."""

    CONTAINS_SCHEMA = "CONTAINS_SCHEMA"
    CONTAINS_TABLE = "CONTAINS_TABLE"
    HAS_COLUMN = "HAS_COLUMN"
    DEPENDS_ON = "DEPENDS_ON"
    FK_REFERENCES = "FK_REFERENCES"
    TAGGED_WITH = "TAGGED_WITH"
    SOURCE_OF = "SOURCE_OF"


# =============================================================================
# Property Keys
# =============================================================================

class PropKey:
    """Constants for commonly used property keys."""

    # Common
    NAME = "name"
    DESCRIPTION = "description"
    UNIQUE_ID = "unique_id"

    # Metadata / sync
    CONTENT_HASH = "_content_hash"
    LAST_SYNCED_AT = "_last_synced_at"
    DEPRECATED = "_deprecated"

    # Table-specific
    MATERIALIZATION = "materialization"
    TABLE_TYPE = "table_type"
    COMPILED_SQL = "compiled_sql"
    RAW_SQL = "raw_sql"
    DATABASE_NAME = "database_name"
    SCHEMA_NAME = "schema_name"
    TAGS = "tags"

    # Column-specific
    DATA_TYPE = "data_type"
    IS_PK = "is_pk"
    IS_NULLABLE = "is_nullable"
    COLUMN_INDEX = "column_index"

    # Embedding
    DESCRIPTION_EMBEDDING = "description_embedding"


# =============================================================================
# Parsed Model (intermediate representation between dbt and Neo4j)
# =============================================================================

@dataclass
class ParsedTable:
    """Intermediate representation of a dbt model/table."""

    unique_id: str
    name: str
    database: str
    schema: str
    description: str
    materialization: str
    table_type: str  # "model", "source", "seed", "snapshot"
    compiled_sql: str | None
    raw_sql: str | None
    tags: list[str]
    depends_on: list[str]  # list of unique_ids this model depends on
    columns: list[ParsedColumn]


@dataclass
class ParsedColumn:
    """Intermediate representation of a column."""

    name: str
    data_type: str | None
    description: str
    is_pk: bool
    is_nullable: bool | None
    column_index: int | None
    table_unique_id: str  # FK back to parent table
