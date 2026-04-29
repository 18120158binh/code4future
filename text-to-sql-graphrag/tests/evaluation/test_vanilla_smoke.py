"""Quick smoke test for vanilla retriever components (no Neo4j needed)."""

from src.retrieval.vanilla_retriever import (
    schema_link, infer_fk_constraints, format_table_as_ddl,
    TableDDL, ColumnDDL,
)

# Test schema linking
tables = [
    {"unique_id": "model.fct_sessions", "name": "fct_sessions"},
    {"unique_id": "model.fct_conversions", "name": "fct_conversions"},
    {"unique_id": "model.dim_users", "name": "dim_users"},
    {"unique_id": "model.rpt_user_engagement", "name": "rpt_user_engagement"},
]
columns = [
    {"name": "revenue", "table_unique_id": "model.fct_conversions"},
    {"name": "session_id", "table_unique_id": "model.fct_sessions"},
    {"name": "engagement_score", "table_unique_id": "model.rpt_user_engagement"},
    {"name": "device_type", "table_unique_id": "model.fct_sessions"},
]

# Test 1: Revenue mentions
result = schema_link("Show me total revenue by customer", tables, columns)
matched = [t["name"] for t in tables if t["unique_id"] in result]
print(f"Q: 'total revenue by customer' -> {matched}")
assert "fct_conversions" in matched, f"Expected fct_conversions, got {matched}"

# Test 2: Session mentions
result = schema_link("How many sessions per country?", tables, columns)
matched = [t["name"] for t in tables if t["unique_id"] in result]
print(f"Q: 'sessions per country' -> {matched}")
assert "fct_sessions" in matched, f"Expected fct_sessions, got {matched}"

# Test 3: Engagement column match
result = schema_link("Users with engagement score above 80", tables, columns)
matched = [t["name"] for t in tables if t["unique_id"] in result]
print(f"Q: 'engagement score above 80' -> {matched}")
assert "rpt_user_engagement" in matched, f"Expected rpt_user_engagement, got {matched}"

# Test DDL formatting
table = TableDDL(
    unique_id="model.fct_conversions",
    name="fct_conversions",
    schema="marts",
    database="analytics",
    description="Conversion events with revenue attribution",
    columns=[
        ColumnDDL("conversion_id", "VARCHAR(36)", "unique conversion ID", True),
        ColumnDDL("revenue", "DECIMAL(10,2)", "Revenue in USD", False),
        ColumnDDL("session_id", "VARCHAR(36)", "Session FK", False),
    ],
    fk_constraints=["-- FK: session_id REFERENCES fct_sessions(session_id)"],
)
ddl = format_table_as_ddl(table)
print(f"\nDDL output:\n{ddl}")
assert "CREATE TABLE fct_conversions" in ddl
assert "PK" in ddl
assert "FK: session_id REFERENCES fct_sessions" in ddl

# Test FK inference
tbl_conversions = TableDDL(
    unique_id="model.fct_conversions", name="fct_conversions",
    schema="", database="", description="",
    columns=[
        ColumnDDL("conversion_id", "VARCHAR(36)", "", True),
        ColumnDDL("session_id", "VARCHAR(36)", "", False),
        ColumnDDL("user_id", "VARCHAR(64)", "", False),
    ],
)
tbl_sessions = TableDDL(
    unique_id="model.fct_sessions", name="fct_sessions",
    schema="", database="", description="",
    columns=[
        ColumnDDL("session_id", "VARCHAR(36)", "", True),
        ColumnDDL("user_id", "VARCHAR(64)", "", False),
    ],
)
tbl_users = TableDDL(
    unique_id="model.dim_users", name="dim_users",
    schema="", database="", description="",
    columns=[
        ColumnDDL("user_id", "VARCHAR(64)", "", True),
    ],
)
depends_on = {"model.fct_conversions": ["model.fct_sessions"]}
all_tbls = [tbl_conversions, tbl_sessions, tbl_users]
fks = infer_fk_constraints(tbl_conversions, all_tbls, depends_on)
print(f"\nInferred FKs for fct_conversions: {fks}")
assert any("session_id REFERENCES fct_sessions" in fk for fk in fks), f"Missing session FK: {fks}"
assert any("user_id REFERENCES dim_users" in fk for fk in fks), f"Missing user FK: {fks}"

print("\n=== ALL SMOKE TESTS PASSED ===")
