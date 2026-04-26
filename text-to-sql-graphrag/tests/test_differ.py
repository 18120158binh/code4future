"""Tests for hash-based change detection."""

from __future__ import annotations

import pytest

from src.graph.schema import ParsedTable, ParsedColumn
from src.ingestion.differ import compute_content_hash


def _make_table(
    unique_id: str = "model.test.table1",
    name: str = "table1",
    description: str = "A test table",
    columns: list[ParsedColumn] | None = None,
) -> ParsedTable:
    """Create a minimal ParsedTable for testing."""
    return ParsedTable(
        unique_id=unique_id,
        name=name,
        database="test_db",
        schema="public",
        description=description,
        materialization="table",
        table_type="model",
        compiled_sql="SELECT 1",
        raw_sql="SELECT 1",
        tags=["test"],
        depends_on=[],
        columns=columns or [],
    )


class TestContentHash:
    """Tests for deterministic content hashing."""

    def test_same_content_same_hash(self):
        """Identical tables should produce identical hashes."""
        t1 = _make_table()
        t2 = _make_table()
        assert compute_content_hash(t1) == compute_content_hash(t2)

    def test_different_description_different_hash(self):
        """Changing description should change the hash."""
        t1 = _make_table(description="Version 1")
        t2 = _make_table(description="Version 2")
        assert compute_content_hash(t1) != compute_content_hash(t2)

    def test_different_columns_different_hash(self):
        """Adding a column should change the hash."""
        col = ParsedColumn(
            name="id", data_type="INTEGER", description="PK",
            is_pk=True, is_nullable=False, column_index=1,
            table_unique_id="model.test.table1",
        )
        t1 = _make_table(columns=[])
        t2 = _make_table(columns=[col])
        assert compute_content_hash(t1) != compute_content_hash(t2)

    def test_column_order_independent(self):
        """Hash should be the same regardless of column order."""
        col_a = ParsedColumn(
            name="a_col", data_type="TEXT", description="",
            is_pk=False, is_nullable=True, column_index=1,
            table_unique_id="model.test.table1",
        )
        col_b = ParsedColumn(
            name="b_col", data_type="TEXT", description="",
            is_pk=False, is_nullable=True, column_index=2,
            table_unique_id="model.test.table1",
        )
        t1 = _make_table(columns=[col_a, col_b])
        t2 = _make_table(columns=[col_b, col_a])
        assert compute_content_hash(t1) == compute_content_hash(t2)

    def test_hash_is_sha256_hex(self):
        """Hash should be a 64-character hex string (SHA256)."""
        t = _make_table()
        h = compute_content_hash(t)
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)
