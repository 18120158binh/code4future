"""SQL validation using sqlglot.

Parses generated SQL to catch syntax errors before execution.
Returns structured error messages for the self-correction loop.
"""

from __future__ import annotations

from dataclasses import dataclass

import structlog
import sqlglot
from sqlglot.errors import ParseError

from src.config import SQLDialect

logger = structlog.get_logger(__name__)

# Map our SQLDialect enum to sqlglot dialect names
DIALECT_MAP = {
    SQLDialect.POSTGRES: "postgres",
    SQLDialect.BIGQUERY: "bigquery",
    SQLDialect.SNOWFLAKE: "snowflake",
    SQLDialect.TRINO: "trino",
    SQLDialect.MYSQL: "mysql",
}


@dataclass
class ValidationResult:
    """Result of SQL validation."""

    is_valid: bool
    error_message: str | None = None
    formatted_sql: str | None = None  # Pretty-printed SQL if valid


def validate_sql(sql: str, dialect: SQLDialect) -> ValidationResult:
    """Validate SQL syntax using sqlglot.

    Args:
        sql: The SQL query string to validate.
        dialect: The target SQL dialect for parsing.

    Returns:
        ValidationResult indicating validity and any errors.
    """
    if not sql or not sql.strip():
        return ValidationResult(
            is_valid=False,
            error_message="Empty SQL query.",
        )

    sg_dialect = DIALECT_MAP.get(dialect, "postgres")

    try:
        # Parse the SQL
        parsed = sqlglot.parse(sql, read=sg_dialect)

        if not parsed:
            return ValidationResult(
                is_valid=False,
                error_message="Failed to parse SQL: no statements found.",
            )

        # Check for parse errors (sqlglot sometimes produces partial results)
        for expression in parsed:
            if expression is None:
                return ValidationResult(
                    is_valid=False,
                    error_message="SQL parsed to None — likely malformed.",
                )

            # Check for common dangerous patterns
            safety_error = _check_safety(expression)
            if safety_error:
                return ValidationResult(
                    is_valid=False,
                    error_message=safety_error,
                )

        # Format the SQL for clean output
        formatted = sqlglot.transpile(sql, read=sg_dialect, write=sg_dialect, pretty=True)
        formatted_sql = formatted[0] if formatted else sql

        logger.debug("sql_validation_passed", dialect=sg_dialect)
        return ValidationResult(
            is_valid=True,
            formatted_sql=formatted_sql,
        )

    except ParseError as e:
        logger.debug("sql_validation_failed", error=str(e))
        return ValidationResult(
            is_valid=False,
            error_message=f"SQL syntax error: {str(e)}",
        )
    except Exception as e:
        logger.warning("sql_validation_unexpected_error", error=str(e))
        return ValidationResult(
            is_valid=False,
            error_message=f"Unexpected validation error: {str(e)}",
        )


def _check_safety(expression) -> str | None:
    """Check for dangerous SQL patterns that should be blocked.

    We only allow SELECT queries from the LLM — no mutations.
    """
    sql_str = expression.sql().upper().strip()

    # Block write operations
    dangerous_keywords = ["DROP", "DELETE", "TRUNCATE", "ALTER", "INSERT", "UPDATE", "GRANT"]
    for keyword in dangerous_keywords:
        if sql_str.startswith(keyword):
            return f"Blocked: {keyword} queries are not allowed. Only SELECT queries are permitted."

    return None


def extract_sql_from_response(response: str) -> str:
    """Extract SQL from LLM response that may contain markdown code blocks.

    Handles formats like:
    ```sql
    SELECT ...
    ```

    Or plain SQL text.
    """
    # Try to extract from markdown code block
    if "```sql" in response:
        parts = response.split("```sql")
        if len(parts) > 1:
            sql_block = parts[1].split("```")[0]
            return sql_block.strip()

    if "```" in response:
        parts = response.split("```")
        if len(parts) > 1:
            return parts[1].strip()

    # Fallback: try to find SELECT statement
    lines = response.strip().split("\n")
    sql_lines: list[str] = []
    in_sql = False

    for line in lines:
        stripped = line.strip().upper()
        if stripped.startswith("SELECT") or stripped.startswith("WITH"):
            in_sql = True
        if in_sql:
            # Stop at EXPLANATION or CONFIDENCE markers
            if stripped.startswith("EXPLANATION:") or stripped.startswith("CONFIDENCE:"):
                break
            sql_lines.append(line)

    if sql_lines:
        return "\n".join(sql_lines).strip()

    # Last resort: return everything
    return response.strip()


def extract_explanation(response: str) -> str:
    """Extract the EXPLANATION field from the LLM response."""
    for line in response.split("\n"):
        if line.strip().upper().startswith("EXPLANATION:"):
            return line.split(":", 1)[1].strip()
    return ""


def extract_confidence(response: str) -> float:
    """Extract the CONFIDENCE score from the LLM response."""
    for line in response.split("\n"):
        if line.strip().upper().startswith("CONFIDENCE:"):
            try:
                value = line.split(":", 1)[1].strip()
                return float(value)
            except (ValueError, IndexError):
                return 0.5
    return 0.5
