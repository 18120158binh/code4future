"""Quick verification of Neo4j graph contents."""
from neo4j import GraphDatabase

d = GraphDatabase.driver("bolt://localhost:7687", auth=("neo4j", "text2sql_dev"))
s = d.session()

# Node counts
for label in ["Table", "Column", "Source", "Database", "Schema"]:
    r = s.run(f"MATCH (n:{label}) RETURN count(n) AS c").single()
    print(f"{label:10s}: {r['c']}")

# Relationship counts
rels = s.run("""
    MATCH ()-[r]->()
    RETURN type(r) AS rel_type, count(r) AS cnt
    ORDER BY cnt DESC
""").data()
print("\nRelationships:")
for row in rels:
    print(f"  {row['rel_type']:25s}: {row['cnt']}")

# Embeddings
emb_t = s.run("MATCH (t:Table) WHERE t.description_embedding IS NOT NULL RETURN count(t) AS c").single()
emb_c = s.run("MATCH (c:Column) WHERE c.description_embedding IS NOT NULL RETURN count(c) AS c").single()
print(f"\nEmbeddings:")
print(f"  Tables with embeddings:  {emb_t['c']}")
print(f"  Columns with embeddings: {emb_c['c']}")

# Sample tables
tables = s.run("MATCH (t:Table) RETURN t.name AS name ORDER BY name").data()
print(f"\nTables ({len(tables)}):")
for t in tables:
    print(f"  - {t['name']}")

s.close()
d.close()
