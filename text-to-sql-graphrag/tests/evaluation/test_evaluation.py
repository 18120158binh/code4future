"""Evaluation harness for Text-to-SQL accuracy.

Compares generated SQL against expected SQL using multiple metrics:
1. Table coverage — did the model pick the right tables?
2. Column coverage — did it reference the right columns?
3. SQL validity — does the generated SQL parse without errors?
4. Semantic similarity — structural comparison via sqlglot AST

Usage:
    pytest tests/evaluation/test_evaluation.py -v
    pytest tests/evaluation/test_evaluation.py -v -k "easy"
    pytest tests/evaluation/test_evaluation.py -v -k "hard"
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest
import sqlglot
from sqlglot import exp

# Path to test cases
TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"


@dataclass
class EvalResult:
    """Result of evaluating a single test case."""

    test_id: str
    difficulty: str
    question: str
    generated_sql: str
    expected_sql: str
    sql_is_valid: bool
    tables_expected: set[str]
    tables_found: set[str]
    table_precision: float
    table_recall: float
    columns_expected: set[str]
    columns_found: set[str]
    column_recall: float
    has_correct_structure: bool
    errors: list[str] = field(default_factory=list)


def load_test_cases() -> list[dict]:
    """Load test cases from JSON file."""
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# =============================================================================
# SQL Analysis Utilities
# =============================================================================


def extract_tables_from_sql(sql: str) -> set[str]:
    """Extract all table names referenced in a SQL query using sqlglot AST."""
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
        tables = set()

        # Find all table references
        for table in parsed.find_all(exp.Table):
            table_name = table.name
            if table_name:
                tables.add(table_name.lower())

        return tables
    except Exception:
        # Fallback: regex extraction
        return _extract_tables_regex(sql)


def _extract_tables_regex(sql: str) -> set[str]:
    """Fallback regex-based table extraction."""
    patterns = [
        r'\bFROM\s+(\w+)',
        r'\bJOIN\s+(\w+)',
        r'\bINTO\s+(\w+)',
    ]
    tables = set()
    for pattern in patterns:
        for match in re.finditer(pattern, sql, re.IGNORECASE):
            table = match.group(1).lower()
            # Filter out SQL keywords that could be false positives
            if table not in {"select", "where", "and", "or", "not", "null",
                             "true", "false", "case", "when", "then", "else",
                             "end", "as", "on", "in", "is", "by", "set"}:
                tables.add(table)
    return tables


def extract_columns_from_sql(sql: str) -> set[str]:
    """Extract column names from SQL using sqlglot AST."""
    try:
        parsed = sqlglot.parse_one(sql, read="postgres")
        columns = set()

        for col in parsed.find_all(exp.Column):
            col_name = col.name
            if col_name:
                columns.add(col_name.lower())

        return columns
    except Exception:
        return set()


def validate_sql_syntax(sql: str) -> tuple[bool, str | None]:
    """Check if SQL is syntactically valid."""
    if not sql or not sql.strip():
        return False, "Empty SQL"

    try:
        parsed = sqlglot.parse(sql, read="postgres")
        if not parsed or parsed[0] is None:
            return False, "Failed to parse"
        return True, None
    except Exception as e:
        return False, str(e)


def check_query_structure(generated_sql: str, expected_sql: str) -> bool:
    """Compare high-level structural similarity between two SQL queries.

    Checks:
    - Same query type (SELECT, WITH...SELECT)
    - Same number of JOINs
    - Has GROUP BY if expected has GROUP BY
    - Has ORDER BY if expected has ORDER BY
    - Has LIMIT if expected has LIMIT
    """
    try:
        gen = sqlglot.parse_one(generated_sql, read="postgres")
        exp_parsed = sqlglot.parse_one(expected_sql, read="postgres")

        checks = []

        # Check for GROUP BY
        gen_has_group = bool(list(gen.find_all(sqlglot.exp.Group)))
        exp_has_group = bool(list(exp_parsed.find_all(sqlglot.exp.Group)))
        if exp_has_group:
            checks.append(gen_has_group)

        # Check for ORDER BY
        gen_has_order = bool(list(gen.find_all(sqlglot.exp.Order)))
        exp_has_order = bool(list(exp_parsed.find_all(sqlglot.exp.Order)))
        if exp_has_order:
            checks.append(gen_has_order)

        # Check for JOINs
        gen_joins = len(list(gen.find_all(sqlglot.exp.Join)))
        exp_joins = len(list(exp_parsed.find_all(sqlglot.exp.Join)))
        if exp_joins > 0:
            checks.append(gen_joins > 0)

        # Check for subqueries/CTEs
        gen_has_cte = bool(list(gen.find_all(sqlglot.exp.CTE)))
        exp_has_cte = bool(list(exp_parsed.find_all(sqlglot.exp.CTE)))
        if exp_has_cte:
            checks.append(gen_has_cte)

        # All structural checks must pass
        return all(checks) if checks else True

    except Exception:
        return False


def compute_precision_recall(
    expected: set[str], found: set[str]
) -> tuple[float, float]:
    """Compute precision and recall between expected and found sets."""
    if not expected and not found:
        return 1.0, 1.0
    if not found:
        return 0.0, 0.0
    if not expected:
        return 1.0, 1.0  # No expected items = anything is fine

    true_positives = len(expected & found)
    precision = true_positives / len(found) if found else 0.0
    recall = true_positives / len(expected) if expected else 0.0

    return round(precision, 3), round(recall, 3)


def evaluate_single(
    test_case: dict,
    generated_sql: str,
) -> EvalResult:
    """Evaluate a single generated SQL against its test case."""
    test_id = test_case["id"]
    difficulty = test_case["difficulty"]
    question = test_case["question"]
    expected_sql = test_case["expected_sql"]
    expected_tables = {t.lower() for t in test_case["expected_tables"]}
    expected_columns = {c.lower() for c in test_case["expected_columns"]}

    errors: list[str] = []

    # 1. Syntax validity
    is_valid, syntax_error = validate_sql_syntax(generated_sql)
    if not is_valid:
        errors.append(f"Syntax error: {syntax_error}")

    # 2. Table coverage
    found_tables = extract_tables_from_sql(generated_sql) if is_valid else set()
    table_precision, table_recall = compute_precision_recall(
        expected_tables, found_tables
    )

    # 3. Column coverage
    found_columns = extract_columns_from_sql(generated_sql) if is_valid else set()
    _, column_recall = compute_precision_recall(expected_columns, found_columns)

    # 4. Structural similarity
    has_correct_structure = False
    if is_valid:
        has_correct_structure = check_query_structure(generated_sql, expected_sql)

    return EvalResult(
        test_id=test_id,
        difficulty=difficulty,
        question=question,
        generated_sql=generated_sql,
        expected_sql=expected_sql,
        sql_is_valid=is_valid,
        tables_expected=expected_tables,
        tables_found=found_tables,
        table_precision=table_precision,
        table_recall=table_recall,
        columns_expected=expected_columns,
        columns_found=found_columns,
        column_recall=column_recall,
        has_correct_structure=has_correct_structure,
        errors=errors,
    )


def print_evaluation_report(results: list[EvalResult]) -> None:
    """Print a summary evaluation report."""
    total = len(results)
    valid = sum(1 for r in results if r.sql_is_valid)
    correct_tables = sum(1 for r in results if r.table_recall == 1.0)
    correct_structure = sum(1 for r in results if r.has_correct_structure)
    avg_table_recall = sum(r.table_recall for r in results) / total if total else 0
    avg_col_recall = sum(r.column_recall for r in results) / total if total else 0

    print("\n" + "=" * 70)
    print("EVALUATION REPORT")
    print("=" * 70)
    print(f"Total test cases:       {total}")
    print(f"SQL syntax valid:       {valid}/{total} ({valid*100//total}%)")
    print(f"Correct tables:         {correct_tables}/{total} ({correct_tables*100//total}%)")
    print(f"Correct structure:      {correct_structure}/{total} ({correct_structure*100//total}%)")
    print(f"Avg table recall:       {avg_table_recall:.1%}")
    print(f"Avg column recall:      {avg_col_recall:.1%}")

    # By difficulty
    print("\n--- By Difficulty ---")
    for diff in ["easy", "medium", "hard", "expert"]:
        diff_results = [r for r in results if r.difficulty == diff]
        if not diff_results:
            continue
        n = len(diff_results)
        v = sum(1 for r in diff_results if r.sql_is_valid)
        t = sum(1 for r in diff_results if r.table_recall == 1.0)
        s = sum(1 for r in diff_results if r.has_correct_structure)
        print(f"  {diff:8s}: valid={v}/{n}, tables={t}/{n}, structure={s}/{n}")

    # Failures
    failures = [r for r in results if not r.sql_is_valid or r.table_recall < 1.0]
    if failures:
        print(f"\n--- Failed Cases ({len(failures)}) ---")
        for r in failures:
            print(f"  [{r.test_id}] {r.question[:60]}")
            for err in r.errors:
                print(f"    ✗ {err}")
            if r.table_recall < 1.0:
                missing = r.tables_expected - r.tables_found
                print(f"    ✗ Missing tables: {missing}")

    print("=" * 70)


# =============================================================================
# Pytest test cases — validate the expected SQL itself is valid
# =============================================================================


@pytest.fixture
def test_cases() -> list[dict]:
    """Load all test cases."""
    return load_test_cases()


class TestExpectedSQLValidity:
    """Validate that all expected SQL in test cases is syntactically correct."""

    def test_all_expected_sql_parses(self, test_cases: list[dict]):
        """Every expected_sql in test_cases.json should be valid SQL."""
        failures = []
        for tc in test_cases:
            is_valid, error = validate_sql_syntax(tc["expected_sql"])
            if not is_valid:
                failures.append(f"[{tc['id']}] {error}")

        if failures:
            pytest.fail(
                f"{len(failures)} test cases have invalid expected SQL:\n"
                + "\n".join(failures)
            )

    def test_expected_tables_match_sql(self, test_cases: list[dict]):
        """Expected tables should actually appear in the expected SQL."""
        failures = []
        for tc in test_cases:
            expected_tables = {t.lower() for t in tc["expected_tables"]}
            found_tables = extract_tables_from_sql(tc["expected_sql"])

            missing = expected_tables - found_tables
            if missing:
                failures.append(
                    f"[{tc['id']}] Tables {missing} listed but not in SQL. "
                    f"Found: {found_tables}"
                )

        if failures:
            pytest.fail(
                f"{len(failures)} test cases have table mismatches:\n"
                + "\n".join(failures)
            )


class TestTestCaseMetadata:
    """Validate test case metadata completeness."""

    def test_unique_ids(self, test_cases: list[dict]):
        """All test case IDs must be unique."""
        ids = [tc["id"] for tc in test_cases]
        assert len(ids) == len(set(ids)), f"Duplicate IDs: {[x for x in ids if ids.count(x) > 1]}"

    def test_difficulty_distribution(self, test_cases: list[dict]):
        """Should have test cases across all difficulty levels."""
        difficulties = {tc["difficulty"] for tc in test_cases}
        assert "easy" in difficulties
        assert "medium" in difficulties
        assert "hard" in difficulties
        assert "expert" in difficulties

    def test_all_required_fields(self, test_cases: list[dict]):
        """Each test case must have all required fields."""
        required = {"id", "difficulty", "category", "question",
                     "expected_sql", "expected_tables", "notes"}
        for tc in test_cases:
            missing = required - set(tc.keys())
            assert not missing, f"[{tc['id']}] Missing fields: {missing}"

    def test_total_count(self, test_cases: list[dict]):
        """Should have a reasonable number of test cases."""
        assert len(test_cases) >= 30, f"Only {len(test_cases)} test cases, need at least 30"


class TestSQLStructure:
    """Test structural properties of expected SQL queries."""

    @pytest.mark.parametrize("difficulty", ["easy", "medium", "hard", "expert"])
    def test_no_mutation_queries(self, test_cases: list[dict], difficulty: str):
        """No test case should have INSERT/UPDATE/DELETE in expected SQL."""
        for tc in test_cases:
            if tc["difficulty"] != difficulty:
                continue
            sql_upper = tc["expected_sql"].upper().strip()
            assert not sql_upper.startswith("INSERT"), f"[{tc['id']}] has INSERT"
            assert not sql_upper.startswith("UPDATE"), f"[{tc['id']}] has UPDATE"
            assert not sql_upper.startswith("DELETE"), f"[{tc['id']}] has DELETE"
            assert not sql_upper.startswith("DROP"), f"[{tc['id']}] has DROP"

    def test_hard_cases_have_joins_or_ctes(self, test_cases: list[dict]):
        """Hard and expert cases should use JOINs, CTEs, subqueries, or advanced patterns."""
        for tc in test_cases:
            if tc["difficulty"] not in ("hard", "expert"):
                continue
            sql = tc["expected_sql"].upper()
            has_complexity = (
                "JOIN" in sql
                or "WITH " in sql
                or "SELECT" in sql.split("FROM", 1)[-1]  # subquery
                or "HAVING " in sql  # complex aggregation filtering
                or "NULLIF" in sql  # division-safe patterns
                or "CASE WHEN" in sql  # derived metric computation
                or len(tc.get("expected_tables", [])) > 1  # multi-table
            )
            assert has_complexity, (
                f"[{tc['id']}] ({tc['difficulty']}) should have advanced SQL patterns"
            )

    def test_easy_cases_are_simple(self, test_cases: list[dict]):
        """Easy cases should NOT require JOINs or CTEs."""
        for tc in test_cases:
            if tc["difficulty"] != "easy":
                continue
            sql = tc["expected_sql"].upper()
            assert "JOIN" not in sql, f"[{tc['id']}] easy case has JOIN"
            assert not sql.startswith("WITH"), f"[{tc['id']}] easy case has CTE"


# =============================================================================
# Evaluation runner (for use with the actual agent)
# =============================================================================


async def run_full_evaluation(
    agent_fn,
    test_cases: list[dict] | None = None,
    difficulty_filter: str | None = None,
) -> list[EvalResult]:
    """Run the full evaluation suite against an agent function.

    Args:
        agent_fn: Async function that takes a question string and returns SQL string.
                  Signature: async def agent_fn(question: str) -> str
        test_cases: Optional list of test cases. Loads from JSON if not provided.
        difficulty_filter: Optional filter by difficulty ("easy", "medium", "hard", "expert").

    Returns:
        List of EvalResult objects.
    """
    if test_cases is None:
        test_cases = load_test_cases()

    if difficulty_filter:
        test_cases = [tc for tc in test_cases if tc["difficulty"] == difficulty_filter]

    results: list[EvalResult] = []

    for tc in test_cases:
        try:
            generated_sql = await agent_fn(tc["question"])
            result = evaluate_single(tc, generated_sql)
        except Exception as e:
            result = EvalResult(
                test_id=tc["id"],
                difficulty=tc["difficulty"],
                question=tc["question"],
                generated_sql="",
                expected_sql=tc["expected_sql"],
                sql_is_valid=False,
                tables_expected={t.lower() for t in tc["expected_tables"]},
                tables_found=set(),
                table_precision=0.0,
                table_recall=0.0,
                columns_expected={c.lower() for c in tc.get("expected_columns", [])},
                columns_found=set(),
                column_recall=0.0,
                has_correct_structure=False,
                errors=[f"Agent error: {str(e)}"],
            )
        results.append(result)

    print_evaluation_report(results)
    return results
