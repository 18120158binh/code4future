# Architecture Overview: Text-to-SQL GraphRAG

This document outlines the architecture and design decisions behind the Text-to-SQL GraphRAG system. The system maps natural language questions to accurate SQL queries by grounding Large Language Models (LLMs) in a rich, semantic knowledge graph of the data warehouse schema.

## System Architecture

The project is divided into four main functional blocks:

1. **Ingestion Pipeline** (dbt -> Metadata -> Knowledge Graph)
2. **Retrieval System** (Hybrid Vector + Graph Search)
3. **Generative Agent** (LangGraph Orchestration + Self-Correction)
4. **User Interface & API** (FastAPI + Streamlit)

`mermaid
graph TD
    %% Ingestion Flow
    subgraph Ingestion Pipeline
        DBT[dbt Docs manifest.json/catalog.json] --> Parser
        Parser --> Differ
        Differ --> Enricher[LLM Enricher Generate Descriptions]
        Enricher --> Embedder[Embedding Model]
        Embedder --> Neo4jWriter
    end

    Neo4jWriter --> Neo[Neo4j Knowledge Graph]

    %% Query Flow
    subgraph Query Execution
        User[User/UI] --> API[FastAPI Server]
        API --> AgentState[LangGraph Agent]
        
        AgentState --> HybridRetriever[Hybrid Retriever]
        HybridRetriever -- 1. Vector Search --> Neo
        HybridRetriever -- 2. Graph Traversal --> Neo
        HybridRetriever -- Schema Context --> AgentState
        
        AgentState --> LLMGen[LLM Generator]
        LLMGen --> Validator[SQLGlot Validator]
        Validator -- Invalid Retry Loop --> LLMGen
        Validator -- Valid --> Formatter
    end

    Formatter --> API
`

## 1. Knowledge Graph Representation (Neo4j)

Instead of passing a flat list of tables directly to the LLM (which exceeds context windows and loses structural meaning), we map the data warehouse to a Neo4j Knowledge Graph.

*   **Nodes**: Table, Column, Schema, Database
*   **Relationships**: CONTAINS_SCHEMA, CONTAINS_TABLE, HAS_COLUMN, DEPENDS_ON (Lineage), FK_REFERENCES (Foreign Keys).
*   **Vector Indexes**: 	able_desc_embedding and column_desc_embedding store semantic vectors of the LLM-enriched descriptions.

## 2. Ingestion Pipeline

1.  **Parse**: Reads manifest.json and catalog.json from dbt.
2.  **Diff**: Compares newly parsed state against the existing Neo4j graph using content hashing.
3.  **Enrich**: For new missing tables/columns, Gemini extracts business context from the name and type.
4.  **Embed**: Converts descriptions into vectors. Batching prevents API quota exhaustion.
5.  **Write**: Upserts the unified graph into Neo4j using bulk UNWIND Cypher queries.

## 3. Hybrid Retrieval (GraphRAG)

Standard RAG (Vector Search only) fails in databases because finding "revenue" matches a column, but misses the fact that users must be joined to sessions. The retriever solves this:

1.  **Vector Search**: Finds the highly semantically relevant "seed" nodes.
2.  **Graph Traversal**: Explores 1-2 hops outward from the seeds along DEPENDS_ON or foreign key edges.
3.  **Assembly**: Serializes the resulting sub-graph (Tables + Columns + Relationships) into a clean format.

## 4. LangGraph Agent (Generation & Validation)

`mermaid
stateDiagram-v2
    [*] --> RetrieveContext
    RetrieveContext --> GenerateSQL
    GenerateSQL --> ValidateSQL
    ValidateSQL --> GenerateSQL : Syntax Error Self-Correction
    ValidateSQL --> FormatResponse : Valid SQL
    ValidateSQL --> HandleError : Max Retries Exceeded
    FormatResponse --> [*]
`

*   **Generation**: System prompts actively specify the requested target dialect (e.g., Postgres).
*   **Validation**: Utilizes sqlglot to parse the generated SQL offline ensuring grammatical correctness.
*   **Self-Correction**: If sqlglot spots an invalid query, the Agent feeds the error back to the LLM autonomously (up to 3 times).
