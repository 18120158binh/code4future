"""Tests for the dbt document parser."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.ingestion.parser import parse_dbt_docs


# Sample manifest.json (minimal)
SAMPLE_MANIFEST = {
    "metadata": {
        "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v11.json",
        "dbt_version": "1.7.0",
    },
    "nodes": {
        "model.jaffle_shop.customers": {
            "resource_type": "model",
            "name": "customers",
            "database": "analytics",
            "schema": "public",
            "description": "This table has basic information about a customer, as well as some derived facts based on a customer's orders",
            "columns": {
                "customer_id": {
                    "name": "customer_id",
                    "description": "This is a unique identifier for a customer",
                    "data_type": None,
                    "tests": ["unique", "not_null"],
                },
                "first_name": {
                    "name": "first_name",
                    "description": "Customer's first name",
                    "data_type": None,
                },
                "last_name": {
                    "name": "last_name",
                    "description": "Customer's last name",
                    "data_type": None,
                },
                "first_order": {
                    "name": "first_order",
                    "description": "Date of first order",
                    "data_type": None,
                },
                "most_recent_order": {
                    "name": "most_recent_order",
                    "description": "Date of most recent order",
                    "data_type": None,
                },
                "number_of_orders": {
                    "name": "number_of_orders",
                    "description": "Count of the number of orders a customer has placed",
                    "data_type": None,
                },
                "customer_lifetime_value": {
                    "name": "customer_lifetime_value",
                    "description": "Total value of the customer's orders",
                    "data_type": None,
                },
            },
            "config": {"materialized": "table"},
            "depends_on": {
                "nodes": [
                    "model.jaffle_shop.stg_customers",
                    "model.jaffle_shop.stg_orders",
                    "model.jaffle_shop.stg_payments",
                ],
            },
            "compiled_code": "SELECT * FROM customers",
            "raw_code": "SELECT * FROM {{ ref('stg_customers') }}",
            "tags": ["pii", "core"],
        },
        "model.jaffle_shop.stg_customers": {
            "resource_type": "model",
            "name": "stg_customers",
            "database": "analytics",
            "schema": "public",
            "description": "Staging layer for raw customer data",
            "columns": {
                "customer_id": {
                    "name": "customer_id",
                    "description": "Primary key",
                    "data_type": None,
                    "tests": ["unique", "not_null"],
                },
            },
            "config": {"materialized": "view"},
            "depends_on": {"nodes": ["source.jaffle_shop.raw.customers"]},
            "compiled_code": "SELECT * FROM raw.customers",
            "raw_code": "SELECT * FROM {{ source('raw', 'customers') }}",
            "tags": [],
        },
        "model.jaffle_shop.stg_orders": {
            "resource_type": "model",
            "name": "stg_orders",
            "database": "analytics",
            "schema": "public",
            "description": "Staging layer for raw order data",
            "columns": {},
            "config": {"materialized": "view"},
            "depends_on": {"nodes": ["source.jaffle_shop.raw.orders"]},
            "compiled_code": None,
            "raw_code": None,
            "tags": [],
        },
        "model.jaffle_shop.stg_payments": {
            "resource_type": "model",
            "name": "stg_payments",
            "database": "analytics",
            "schema": "public",
            "description": "Staging layer for raw payment data",
            "columns": {},
            "config": {"materialized": "view"},
            "depends_on": {"nodes": ["source.jaffle_shop.raw.payments"]},
            "compiled_code": None,
            "raw_code": None,
            "tags": [],
        },
        "test.jaffle_shop.unique_customers_customer_id": {
            "resource_type": "test",
            "name": "unique_customers_customer_id",
            "database": "analytics",
            "schema": "public",
            "description": "",
            "columns": {},
            "config": {},
            "depends_on": {"nodes": ["model.jaffle_shop.customers"]},
        },
    },
    "sources": {
        "source.jaffle_shop.raw.customers": {
            "resource_type": "source",
            "name": "customers",
            "database": "raw_db",
            "schema": "raw",
            "description": "Raw customer data from the production system",
            "columns": {
                "id": {
                    "name": "id",
                    "description": "Customer ID in the source system",
                },
                "first_name": {
                    "name": "first_name",
                    "description": "",
                },
                "last_name": {
                    "name": "last_name",
                    "description": "",
                },
            },
            "tags": [],
        },
        "source.jaffle_shop.raw.orders": {
            "resource_type": "source",
            "name": "orders",
            "database": "raw_db",
            "schema": "raw",
            "description": "Raw order data",
            "columns": {},
            "tags": [],
        },
        "source.jaffle_shop.raw.payments": {
            "resource_type": "source",
            "name": "payments",
            "database": "raw_db",
            "schema": "raw",
            "description": "Raw payment data",
            "columns": {},
            "tags": [],
        },
    },
}


SAMPLE_CATALOG = {
    "nodes": {
        "model.jaffle_shop.customers": {
            "columns": {
                "customer_id": {"type": "INTEGER", "index": 1},
                "first_name": {"type": "VARCHAR", "index": 2},
                "last_name": {"type": "VARCHAR", "index": 3},
                "first_order": {"type": "DATE", "index": 4},
                "most_recent_order": {"type": "DATE", "index": 5},
                "number_of_orders": {"type": "INTEGER", "index": 6},
                "customer_lifetime_value": {"type": "DECIMAL(10,2)", "index": 7},
            },
        },
    },
    "sources": {
        "source.jaffle_shop.raw.customers": {
            "columns": {
                "id": {"type": "INTEGER", "index": 1},
                "first_name": {"type": "TEXT", "index": 2},
                "last_name": {"type": "TEXT", "index": 3},
            },
        },
    },
}


@pytest.fixture
def sample_docs_dir(tmp_path: Path) -> Path:
    """Create a temp directory with sample dbt docs."""
    manifest_path = tmp_path / "manifest.json"
    catalog_path = tmp_path / "catalog.json"

    manifest_path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")
    catalog_path.write_text(json.dumps(SAMPLE_CATALOG), encoding="utf-8")

    return tmp_path


class TestParser:
    """Tests for parse_dbt_docs."""

    def test_parse_basic(self, sample_docs_dir: Path):
        """Should parse models and sources from manifest."""
        tables = parse_dbt_docs(sample_docs_dir)

        # 4 models + 3 sources = 7 total (tests are skipped)
        assert len(tables) == 7

    def test_parse_model_fields(self, sample_docs_dir: Path):
        """Should extract all model fields correctly."""
        tables = parse_dbt_docs(sample_docs_dir)
        customers = next(t for t in tables if t.name == "customers" and t.table_type == "model")

        assert customers.unique_id == "model.jaffle_shop.customers"
        assert customers.database == "analytics"
        assert customers.schema == "public"
        assert customers.materialization == "table"
        assert customers.table_type == "model"
        assert "pii" in customers.tags
        assert len(customers.depends_on) == 3

    def test_parse_columns_with_catalog_types(self, sample_docs_dir: Path):
        """Should merge column data types from catalog."""
        tables = parse_dbt_docs(sample_docs_dir)
        customers = next(t for t in tables if t.name == "customers" and t.table_type == "model")

        customer_id_col = next(c for c in customers.columns if c.name == "customer_id")
        assert customer_id_col.data_type == "INTEGER"
        assert customer_id_col.description == "This is a unique identifier for a customer"

        clv_col = next(c for c in customers.columns if c.name == "customer_lifetime_value")
        assert clv_col.data_type == "DECIMAL(10,2)"

    def test_parse_skips_tests(self, sample_docs_dir: Path):
        """Should skip test nodes from manifest."""
        tables = parse_dbt_docs(sample_docs_dir)
        test_tables = [t for t in tables if "test" in t.unique_id]
        assert len(test_tables) == 0

    def test_parse_sources(self, sample_docs_dir: Path):
        """Should parse source definitions."""
        tables = parse_dbt_docs(sample_docs_dir)
        sources = [t for t in tables if t.table_type == "source"]

        assert len(sources) == 3

        raw_customers = next(s for s in sources if s.name == "customers")
        assert raw_customers.database == "raw_db"
        assert raw_customers.schema == "raw"
        assert len(raw_customers.depends_on) == 0
        assert raw_customers.materialization == "table"

    def test_parse_missing_manifest_raises(self, tmp_path: Path):
        """Should raise FileNotFoundError if manifest.json is missing."""
        with pytest.raises(FileNotFoundError):
            parse_dbt_docs(tmp_path)

    def test_parse_without_catalog(self, tmp_path: Path):
        """Should work without catalog.json (columns won't have types)."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(SAMPLE_MANIFEST), encoding="utf-8")

        tables = parse_dbt_docs(tmp_path)
        assert len(tables) == 7

        # Without catalog, types come from manifest (which has none in this sample)
        customers = next(t for t in tables if t.name == "customers" and t.table_type == "model")
        customer_id = next(c for c in customers.columns if c.name == "customer_id")
        assert customer_id.data_type is None
