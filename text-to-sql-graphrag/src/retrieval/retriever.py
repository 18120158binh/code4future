"""Hybrid retriever — combines vector search and graph traversal.

This is the main entry point for the retrieval layer.
It orchestrates: embed query → vector search → graph expansion → assembly.
"""

from __future__ import annotations

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.retrieval.embedder import EmbedderService
from src.retrieval.vector_search import (
    search_tables_by_embedding,
    search_columns_by_embedding,
    fulltext_search_tables,
)
from src.retrieval.graph_traversal import expand_from_seeds, SubGraph
from src.retrieval.assembler import (
    assemble_schema_context,
    truncate_context,
)

logger = structlog.get_logger(__name__)


class HybridRetriever:
    """Combines semantic vector search with structural graph traversal.

    Retrieval flow:
    1. Embed the user query
    2. Vector search: find top-K semantically similar tables/columns
    3. Graph expansion: traverse N hops from matched tables
    4. Assemble: serialize sub-graph into structured prompt context
    """

    def __init__(
        self,
        client: Neo4jClient,
        embedder: EmbedderService | None = None,
    ):
        self._client = client
        self._embedder = embedder or EmbedderService()

    async def retrieve(
        self,
        query: str,
        top_k: int | None = None,
        hops: int | None = None,
        max_tokens: int = 4000,
        use_fulltext_fallback: bool = True,
    ) -> RetrievalResult:
        """Retrieve relevant schema context for a natural language query.

        Args:
            query: The user's natural language question.
            top_k: Number of tables to retrieve from vector search.
            hops: Number of hops for graph expansion.
            max_tokens: Maximum token budget for the context.
            use_fulltext_fallback: Fall back to keyword search if vector fails.

        Returns:
            RetrievalResult with the assembled context and metadata.
        """
        top_k = top_k or settings.retrieval_top_k
        hops = hops or settings.graph_expansion_hops

        # Step 1: Find seed tables via vector search
        seed_table_ids = await self._find_seed_tables(
            query, top_k, use_fulltext_fallback
        )

        if not seed_table_ids:
            logger.warning("no_seed_tables_found", query=query[:100])
            return RetrievalResult(
                context="No relevant schema context found for this query.",
                subgraph=SubGraph(tables=[], relationships=[], query_tables=[]),
                seed_table_count=0,
                total_table_count=0,
            )

        # Step 2: Expand through graph
        subgraph = await expand_from_seeds(self._client, seed_table_ids, hops)

        # Step 3: Assemble into prompt text
        context = assemble_schema_context(subgraph)
        context = truncate_context(context, max_tokens)

        result = RetrievalResult(
            context=context,
            subgraph=subgraph,
            seed_table_count=len(seed_table_ids),
            total_table_count=len(subgraph.tables),
        )

        logger.info(
            "retrieval_complete",
            query=query[:80],
            seed_tables=result.seed_table_count,
            total_tables=result.total_table_count,
            context_chars=len(context),
        )

        return result

    async def _find_seed_tables(
        self,
        query: str,
        top_k: int,
        use_fulltext_fallback: bool,
    ) -> list[str]:
        """Find initial seed tables using vector search (with fallback)."""
        try:
            # Try vector search first
            query_embedding = await self._embedder.embed_query(query)

            # Search both tables and columns
            table_results = await search_tables_by_embedding(
                self._client, query_embedding, top_k
            )
            column_results = await search_columns_by_embedding(
                self._client, query_embedding, top_k
            )

            # Merge: collect unique table IDs, prioritizing higher scores
            seen: dict[str, float] = {}
            for r in table_results:
                if r.unique_id not in seen or r.score > seen[r.unique_id]:
                    seen[r.unique_id] = r.score

            for r in column_results:
                # Column results reference parent table
                if r.unique_id not in seen or r.score > seen[r.unique_id]:
                    seen[r.unique_id] = r.score

            # Sort by score and take top_k
            sorted_ids = sorted(seen.keys(), key=lambda uid: seen[uid], reverse=True)
            return sorted_ids[:top_k]

        except Exception as e:
            logger.warning("vector_search_failed", error=str(e))

            if use_fulltext_fallback:
                logger.info("falling_back_to_fulltext")
                results = await fulltext_search_tables(
                    self._client, query, top_k
                )
                return [r.unique_id for r in results]

            return []


class RetrievalResult:
    """Result of a hybrid retrieval operation."""

    def __init__(
        self,
        context: str,
        subgraph: SubGraph,
        seed_table_count: int,
        total_table_count: int,
    ):
        self.context = context
        self.subgraph = subgraph
        self.seed_table_count = seed_table_count
        self.total_table_count = total_table_count
