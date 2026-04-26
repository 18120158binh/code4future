# Text-to-SQL with GraphRAG

Convert natural language questions to SQL using **GraphRAG** — a hybrid retrieval approach that combines Neo4j knowledge graph traversal with semantic vector search.

## Architecture

```
User Question → GraphRAG Retrieval → LLM SQL Generation → Validated SQL
                     ↓
              ┌──────────────┐
              │   Neo4j KG   │ ← dbt docs (manifest.json, catalog.json)
              │ (schema +    │
              │  lineage +   │
              │  embeddings) │
              └──────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker (for Neo4j)
- [Ollama](https://ollama.com/download) (free local LLM)

### 1. Setup

```bash
# Clone and enter the project
cd text-to-sql-graphrag

# Copy environment config
cp .env.example .env

# Start Neo4j
docker-compose up -d

# Install Python dependencies
pip install -e ".[dev]"

# Pull Ollama models (free, runs locally)
ollama pull llama3.1:8b
ollama pull nomic-embed-text
```

### 2. Ingest dbt Docs

```bash
# Place your manifest.json and catalog.json in the docs path
# Then run ingestion:
python -m scripts.ingest --docs-path ./sample_dbt_docs

# For incremental updates (after doc changes):
python -m scripts.ingest --docs-path ./sample_dbt_docs

# For full re-sync:
python -m scripts.ingest --docs-path ./sample_dbt_docs --full-sync
```

### 3. Start the API

```bash
uvicorn src.api.main:app --reload
```

### 4. Start the UI

```bash
streamlit run ui/app.py
```

### 5. Ask Questions!

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Show me total revenue by customer for last month"}'
```

## Project Structure

```
text-to-sql-graphrag/
├── src/
│   ├── config.py              # Settings (LLM provider, Neo4j, etc.)
│   ├── ingestion/             # dbt docs → Neo4j graph
│   │   ├── parser.py          # Parse manifest.json + catalog.json
│   │   ├── differ.py          # Hash-based change detection
│   │   ├── enricher.py        # LLM description generation
│   │   ├── graph_writer.py    # MERGE-based Neo4j upserts
│   │   └── pipeline.py        # Orchestrator
│   ├── graph/                 # Neo4j layer
│   │   ├── client.py          # Async Neo4j client
│   │   ├── schema.py          # Graph data model
│   │   └── indexes.py         # Index/constraint management
│   ├── retrieval/             # GraphRAG retrieval
│   │   ├── embedder.py        # Embedding service
│   │   ├── vector_search.py   # Neo4j vector index search
│   │   ├── graph_traversal.py # Cypher-based expansion
│   │   ├── assembler.py       # Sub-graph → prompt text
│   │   └── retriever.py       # Hybrid retriever
│   ├── agent/                 # SQL generation (LangGraph)
│   │   ├── state.py           # Agent state definition
│   │   ├── nodes.py           # Node functions
│   │   ├── prompts.py         # Prompt templates
│   │   ├── validator.py       # sqlglot validation
│   │   └── graph.py           # LangGraph workflow
│   └── api/                   # FastAPI backend
├── ui/app.py                  # Streamlit chat UI
├── scripts/                   # CLI tools
└── tests/                     # Unit tests
```

## LLM Provider Options

| Provider | Cost | Setup |
|:---------|:-----|:------|
| **Ollama** (default) | Free | `ollama pull llama3.1:8b` |
| OpenAI | Paid | Set `OPENAI_API_KEY` in `.env` |
| Google Gemini | Free tier | Set `GOOGLE_API_KEY` in `.env` |

Switch providers by changing `LLM_PROVIDER` in `.env`.

## Running Tests

```bash
pytest tests/ -v
```
