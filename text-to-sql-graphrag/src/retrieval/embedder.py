"""Embedding service wrapper.

Provides a clean interface to the configured embeddings model
for both indexing (during ingestion) and querying (during retrieval).
"""

from __future__ import annotations

import structlog
from langchain_core.embeddings import Embeddings

from src.config import settings

logger = structlog.get_logger(__name__)


class EmbedderService:
    """Wraps the LangChain embeddings model for query-time use."""

    def __init__(self, embeddings_model: Embeddings | None = None):
        self._model = embeddings_model

    @property
    def model(self) -> Embeddings:
        """Lazy-initialize the embeddings model."""
        if self._model is None:
            self._model = settings.get_embeddings()
        return self._model

    async def embed_query(self, text: str) -> list[float]:
        """Embed a single query string.

        Args:
            text: The query text to embed.

        Returns:
            Embedding vector as a list of floats.
        """
        vector = await self.model.aembed_query(text)
        logger.debug("query_embedded", text_preview=text[:50], dims=len(vector))
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of documents.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.
        """
        vectors = await self.model.aembed_documents(texts)
        logger.debug("documents_embedded", count=len(texts))
        return vectors
