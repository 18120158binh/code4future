"""Tests for the context assembler."""

from __future__ import annotations

import pytest

from src.retrieval.graph_traversal import (
    SubGraph,
    TableContext,
    ColumnContext,
    RelationshipContext,
)
from src.retrieval.assembler import (
    assemble_schema_context,
    estimate_token_count,
    truncate_context,
)


@pytest.fixture
def sample_subgraph() -> SubGraph:
    """Create a sample SubGraph for testing."""
    return SubGraph(
        tables=[
            TableContext(
                unique_id="model.shop.orders",
                name="orders",
                schema="analytics",
                database="warehouse",
                description="All completed customer orders",
                materialization="table",
                table_type="model",
                columns=[
                    ColumnContext(
                        name="order_id",
                        data_type="INTEGER",
                        description="Unique order identifier",
                        is_pk=True,
                    ),
                    ColumnContext(
                        name="customer_id",
                        data_type="INTEGER",
                        description="FK to customers table",
                        is_pk=False,
                    ),
                    ColumnContext(
                        name="total_amount",
                        data_type="DECIMAL(10,2)",
                        description="Total revenue for this order",
                        is_pk=False,
                    ),
                ],
            ),
            TableContext(
                unique_id="model.shop.customers",
                name="customers",
                schema="analytics",
                database="warehouse",
                description="Customer master data",
                materialization="table",
                table_type="model",
                columns=[
                    ColumnContext(
                        name="customer_id",
                        data_type="INTEGER",
                        description="Unique customer identifier",
                        is_pk=True,
                    ),
                    ColumnContext(
                        name="name",
                        data_type="VARCHAR",
                        description="Customer full name",
                        is_pk=False,
                    ),
                ],
            ),
        ],
        relationships=[
            RelationshipContext(
                from_table="orders",
                to_table="customers",
                relationship_type="DEPENDS_ON",
            ),
        ],
        query_tables=["orders"],
    )


class TestAssembler:
    """Tests for schema context assembly."""

    def test_assemble_basic(self, sample_subgraph: SubGraph):
        """Should produce a non-empty context string."""
        context = assemble_schema_context(sample_subgraph)
        assert len(context) > 0
        assert "orders" in context
        assert "customers" in context

    def test_assemble_contains_columns(self, sample_subgraph: SubGraph):
        """Should include column names and types."""
        context = assemble_schema_context(sample_subgraph)
        assert "order_id" in context
        assert "INTEGER" in context
        assert "DECIMAL(10,2)" in context

    def test_assemble_contains_relationships(self, sample_subgraph: SubGraph):
        """Should include relationship information."""
        context = assemble_schema_context(sample_subgraph)
        assert "DEPENDS_ON" in context

    def test_assemble_pk_columns_first(self, sample_subgraph: SubGraph):
        """PK columns should appear before non-PK columns."""
        context = assemble_schema_context(sample_subgraph)
        lines = context.split("\n")
        # Find column lines for orders
        orders_columns = [
            l.strip() for l in lines
            if l.strip().startswith("- ") and "order" in l.lower()
        ]
        # order_id (PK) should come before customer_id and total_amount
        if len(orders_columns) >= 2:
            assert "order_id" in orders_columns[0]

    def test_assemble_seed_tables_first(self, sample_subgraph: SubGraph):
        """Seed tables (from vector search) should appear before expanded tables."""
        context = assemble_schema_context(sample_subgraph)
        orders_pos = context.index("orders")
        # "orders" is the query table, so it should appear first
        assert orders_pos < context.index("Customer master data")

    def test_assemble_empty_subgraph(self):
        """Should handle empty subgraph gracefully."""
        empty = SubGraph(tables=[], relationships=[], query_tables=[])
        context = assemble_schema_context(empty)
        assert "No relevant schema" in context


class TestTokenEstimation:
    """Tests for token counting and truncation."""

    def test_estimate_tokens(self):
        text = "a" * 400
        assert estimate_token_count(text) == 100

    def test_truncate_short_context(self):
        """Short context should not be truncated."""
        text = "This is short"
        assert truncate_context(text, max_tokens=1000) == text

    def test_truncate_long_context(self):
        """Long context should be truncated with message."""
        text = "\n\n".join(["x" * 2000 for _ in range(10)])
        truncated = truncate_context(text, max_tokens=500)
        assert len(truncated) < len(text)
        assert "truncated" in truncated
