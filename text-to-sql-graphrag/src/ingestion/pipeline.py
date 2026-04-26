"""Ingestion pipeline orchestrator.

Ties together: parse → diff → enrich → embed → write.
This is the main entry point for both full and incremental syncs.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.ingestion.parser import parse_dbt_docs
from src.ingestion.differ import compute_diff, DiffResult
from src.ingestion.enricher import enrich_descriptions, generate_embeddings
from src.ingestion.graph_writer import write_tables_to_graph, soft_delete_tables

logger = structlog.get_logger(__name__)


@dataclass
class IngestionResult:
    """Summary of an ingestion run."""

    new_count: int
    modified_count: int
    unchanged_count: int
    deleted_count: int
    embeddings_generated: int


async def run_ingestion(
    client: Neo4jClient,
    docs_path: Path | None = None,
    skip_enrichment: bool = False,
    skip_embeddings: bool = False,
    full_sync: bool = False,
) -> IngestionResult:
    """Run the full ingestion pipeline.

    Args:
        client: Connected Neo4j client.
        docs_path: Path to dbt docs directory. Defaults to config value.
        skip_enrichment: If True, skip LLM description generation.
        skip_embeddings: If True, skip embedding generation.
        full_sync: If True, skip diffing and re-process everything.

    Returns:
        IngestionResult with counts of what was processed.
    """
    docs_path = docs_path or settings.dbt_docs_path

    # ─── Step 1: Parse dbt docs ───
    logger.info("ingestion_step", step="parse", docs_path=str(docs_path))
    parsed_tables = parse_dbt_docs(docs_path)

    if not parsed_tables:
        logger.warning("no_tables_parsed")
        return IngestionResult(0, 0, 0, 0, 0)

    # ─── Step 2: Compute diff (unless full sync) ───
    if full_sync:
        logger.info("ingestion_step", step="full_sync_mode")
        tables_to_process = parsed_tables
        deleted_ids: list[str] = []
        diff = None
    else:
        logger.info("ingestion_step", step="diff")
        diff = await compute_diff(client, parsed_tables)
        tables_to_process = diff.new + diff.modified
        deleted_ids = diff.deleted

    if not tables_to_process and not deleted_ids:
        logger.info("no_changes_detected")
        return IngestionResult(
            new_count=0,
            modified_count=0,
            unchanged_count=len(parsed_tables),
            deleted_count=0,
            embeddings_generated=0,
        )

    # ─── Step 3: LLM enrichment (optional) ───
    if not skip_enrichment and tables_to_process:
        try:
            logger.info("ingestion_step", step="enrich")
            llm = settings.get_llm()
            tables_to_process = await enrich_descriptions(tables_to_process, llm)
        except Exception as e:
            logger.warning(
                "enrichment_skipped",
                reason=str(e),
                hint="LLM not available. Install Ollama and run: ollama pull llama3.1:8b",
            )

    # ─── Step 4: Generate embeddings (optional) ───
    embeddings: dict[str, list[float]] = {}
    if not skip_embeddings and tables_to_process:
        try:
            logger.info("ingestion_step", step="embed")
            embeddings_model = settings.get_embeddings()
            embeddings = await generate_embeddings(tables_to_process, embeddings_model)
        except Exception as e:
            logger.warning(
                "embeddings_skipped",
                reason=str(e),
                hint="Embedding model not available. Install Ollama and run: ollama pull nomic-embed-text",
            )

    # ─── Step 5: Write to Neo4j ───
    logger.info("ingestion_step", step="write", count=len(tables_to_process))
    await write_tables_to_graph(client, tables_to_process, embeddings)

    # ─── Step 6: Handle deletions ───
    if deleted_ids:
        logger.info("ingestion_step", step="soft_delete", count=len(deleted_ids))
        await soft_delete_tables(client, deleted_ids)

    # ─── Done ───
    result = IngestionResult(
        new_count=len(diff.new) if diff else len(tables_to_process),
        modified_count=len(diff.modified) if diff else 0,
        unchanged_count=len(diff.unchanged) if diff else 0,
        deleted_count=len(deleted_ids),
        embeddings_generated=len(embeddings),
    )
    logger.info("ingestion_complete", **result.__dict__)
    return result
