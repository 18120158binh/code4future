"""Tests for SQL validation and response parsing."""

from __future__ import annotations

import pytest

from src.config import SQLDialect
from src.agent.validator import (
    validate_sql,
    extract_sql_from_response,
    extract_explanation,
    extract_confidence,
)


class TestValidateSQL:
    """Tests for SQL syntax validation."""

    def test_valid_select(self):
        sql = "SELECT customer_id, first_name FROM customers WHERE customer_id = 1"
        result = validate_sql(sql, SQLDialect.POSTGRES)
        assert result.is_valid
        assert result.formatted_sql is not None

    def test_valid_join(self):
        sql = """
        SELECT o.order_id, c.first_name
        FROM orders o
        JOIN customers c ON o.customer_id = c.customer_id
        WHERE o.order_date > '2024-01-01'
        ORDER BY o.order_date DESC
        LIMIT 100
        """
        result = validate_sql(sql, SQLDialect.POSTGRES)
        assert result.is_valid

    def test_valid_aggregation(self):
        sql = """
        SELECT
            p.category,
            COUNT(*) AS order_count,
            SUM(o.total_amount) AS total_revenue
        FROM orders o
        JOIN products p ON o.product_id = p.product_id
        GROUP BY p.category
        HAVING SUM(o.total_amount) > 1000
        ORDER BY total_revenue DESC
        """
        result = validate_sql(sql, SQLDialect.POSTGRES)
        assert result.is_valid

    def test_empty_sql(self):
        result = validate_sql("", SQLDialect.POSTGRES)
        assert not result.is_valid
        assert "Empty" in result.error_message

    def test_block_drop(self):
        result = validate_sql("DROP TABLE customers", SQLDialect.POSTGRES)
        assert not result.is_valid
        assert "Blocked" in result.error_message

    def test_block_delete(self):
        result = validate_sql("DELETE FROM customers WHERE id = 1", SQLDialect.POSTGRES)
        assert not result.is_valid
        assert "Blocked" in result.error_message

    def test_block_insert(self):
        result = validate_sql("INSERT INTO customers VALUES (1, 'John')", SQLDialect.POSTGRES)
        assert not result.is_valid

    def test_block_update(self):
        result = validate_sql("UPDATE customers SET name = 'test'", SQLDialect.POSTGRES)
        assert not result.is_valid

    def test_cte_query(self):
        sql = """
        WITH monthly AS (
            SELECT DATE_TRUNC('month', order_date) AS month,
                   SUM(amount) AS total
            FROM orders
            GROUP BY 1
        )
        SELECT month, total
        FROM monthly
        ORDER BY month
        """
        result = validate_sql(sql, SQLDialect.POSTGRES)
        assert result.is_valid


class TestExtractSQL:
    """Tests for extracting SQL from LLM responses."""

    def test_extract_from_code_block(self):
        response = """Here is the query:

```sql
SELECT * FROM customers
```

EXPLANATION: Gets all customers.
CONFIDENCE: 0.9"""
        sql = extract_sql_from_response(response)
        assert sql == "SELECT * FROM customers"

    def test_extract_from_plain_text(self):
        response = """SELECT customer_id, name
FROM customers
WHERE active = true

EXPLANATION: Active customers only.
CONFIDENCE: 0.8"""
        sql = extract_sql_from_response(response)
        assert "SELECT customer_id" in sql
        assert "FROM customers" in sql
        assert "EXPLANATION" not in sql

    def test_extract_from_generic_code_block(self):
        response = """```
SELECT * FROM orders LIMIT 10
```"""
        sql = extract_sql_from_response(response)
        assert "SELECT * FROM orders" in sql


class TestExtractMetadata:
    """Tests for extracting explanation and confidence from responses."""

    def test_extract_explanation(self):
        response = "EXPLANATION: This query joins orders and customers."
        assert extract_explanation(response) == "This query joins orders and customers."

    def test_extract_explanation_missing(self):
        assert extract_explanation("Just some SQL") == ""

    def test_extract_confidence(self):
        response = "CONFIDENCE: 0.85"
        assert extract_confidence(response) == 0.85

    def test_extract_confidence_missing(self):
        assert extract_confidence("No confidence here") == 0.5

    def test_extract_confidence_invalid(self):
        response = "CONFIDENCE: high"
        assert extract_confidence(response) == 0.5
