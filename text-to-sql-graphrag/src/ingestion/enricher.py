"""LLM enrichment for parsed models.

Generates descriptions for undocumented columns and creates
embeddings for all descriptions to populate the vector index.
"""

from __future__ import annotations

import structlog
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_core.messages import HumanMessage, SystemMessage

from src.graph.schema import ParsedColumn, ParsedTable

logger = structlog.get_logger(__name__)

# Prompt for generating column descriptions when they're missing
COLUMN_DESCRIPTION_SYSTEM = """You are a data documentation expert. Given a table name, its description, 
and a column name with its data type, generate a brief 1-sentence description for the column.

Rules:
- Be concise and factual
- Use present tense
- Mention the business meaning if inferrable from the name
- If the column is a foreign key (ends with _id), mention what entity it references
- Output ONLY the description, no extra text"""

COLUMN_DESCRIPTION_TEMPLATE = """Table: {table_name}
Table Description: {table_description}
Column: {column_name}
Data Type: {data_type}

Generate a brief description for this column:"""


async def enrich_descriptions(
    tables: list[ParsedTable],
    llm: BaseChatModel,
) -> list[ParsedTable]:
    """Generate descriptions for columns that don't have one.

    This is optional — if no LLM is available, tables are returned as-is.
    Only undocumented columns (empty description) are enriched.
    """
    enriched_count = 0

    for table in tables:
        undocumented = [c for c in table.columns if not c.description.strip()]

        if not undocumented:
            continue

        for column in undocumented:
            try:
                description = await _generate_column_description(
                    llm=llm,
                    table_name=table.name,
                    table_description=table.description,
                    column_name=column.name,
                    data_type=column.data_type or "UNKNOWN",
                )
                column.description = description
                enriched_count += 1
            except Exception as e:
                logger.warning(
                    "enrichment_failed",
                    table=table.name,
                    column=column.name,
                    error=str(e),
                )

    logger.info("enrichment_complete", columns_enriched=enriched_count)
    return tables


async def generate_embeddings(
    tables: list[ParsedTable],
    embeddings_model: Embeddings,
) -> dict[str, list[float]]:
    """Generate embeddings for all table and column descriptions.

    Returns a dict mapping unique identifiers to embedding vectors.
    Keys are formatted as:
    - "table:{unique_id}" for table descriptions
    - "column:{table_unique_id}:{column_name}" for column descriptions
    """
    # Collect all texts to embed in a single batch
    texts: list[str] = []
    keys: list[str] = []

    for table in tables:
        # Table-level embedding
        text = _build_table_embedding_text(table)
        if text.strip():
            keys.append(f"table:{table.unique_id}")
            texts.append(text)

        # Column-level embeddings
        for col in table.columns:
            col_text = _build_column_embedding_text(table.name, col)
            if col_text.strip():
                keys.append(f"column:{table.unique_id}:{col.name}")
                texts.append(col_text)

    if not texts:
        return {}

    # Batch embed with rate limiting for free-tier APIs
    import asyncio

    # Google free tier: 100 embed requests/min. langchain calls API once per text.
    # 20 texts per batch × 15s pause ≈ 80 requests/min → safe under 100 limit.
    BATCH_SIZE = 20
    BATCH_DELAY = 15.0  # seconds between batches
    MAX_RETRIES = 3

    logger.info("generating_embeddings", count=len(texts))
    all_vectors: list[list[float]] = []
    total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        logger.info(
            "embedding_batch",
            batch=f"{batch_num}/{total_batches}",
            size=len(batch),
        )

        # Retry with exponential backoff on rate limit errors
        for attempt in range(MAX_RETRIES):
            try:
                batch_vectors = await embeddings_model.aembed_documents(batch)
                all_vectors.extend(batch_vectors)
                break
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    wait_time = BATCH_DELAY * (attempt + 1)
                    logger.warning(
                        "rate_limited",
                        batch=batch_num,
                        attempt=attempt + 1,
                        wait_seconds=wait_time,
                    )
                    await asyncio.sleep(wait_time)
                else:
                    raise  # Non-rate-limit error, re-raise

        # Rate limit pause between batches (skip after last batch)
        if i + BATCH_SIZE < len(texts):
            await asyncio.sleep(BATCH_DELAY)

    result = dict(zip(keys, all_vectors))
    logger.info("embeddings_generated", count=len(result))
    return result


def _build_table_embedding_text(table: ParsedTable) -> str:
    """Build a rich text for table embedding that captures semantic meaning."""
    parts = [
        f"Table: {table.name}",
        f"Schema: {table.schema}",
    ]
    if table.description:
        parts.append(f"Description: {table.description}")
    if table.tags:
        parts.append(f"Tags: {', '.join(table.tags)}")

    # Include column names for context
    col_names = [c.name for c in table.columns]
    if col_names:
        parts.append(f"Columns: {', '.join(col_names)}")

    return "\n".join(parts)


def _build_column_embedding_text(table_name: str, column: ParsedColumn) -> str:
    """Build a rich text for column embedding."""
    parts = [
        f"Column: {column.name}",
        f"Table: {table_name}",
    ]
    if column.data_type:
        parts.append(f"Type: {column.data_type}")
    if column.description:
        parts.append(f"Description: {column.description}")

    return "\n".join(parts)


async def _generate_column_description(
    llm: BaseChatModel,
    table_name: str,
    table_description: str,
    column_name: str,
    data_type: str,
) -> str:
    """Use LLM to generate a description for an undocumented column."""
    messages = [
        SystemMessage(content=COLUMN_DESCRIPTION_SYSTEM),
        HumanMessage(
            content=COLUMN_DESCRIPTION_TEMPLATE.format(
                table_name=table_name,
                table_description=table_description,
                column_name=column_name,
                data_type=data_type,
            )
        ),
    ]
    response = await llm.ainvoke(messages)
    return response.content.strip()
