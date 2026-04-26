"""Neo4j async client wrapper.

Provides a reusable async client for all Neo4j operations
with connection pooling and automatic session management.
"""

from __future__ import annotations

import structlog
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncSession

from src.config import settings

logger = structlog.get_logger(__name__)


class Neo4jClient:
    """Async Neo4j client with connection lifecycle management."""

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
    ):
        self._uri = uri or settings.neo4j_uri
        self._user = user or settings.neo4j_user
        self._password = password or settings.neo4j_password
        self._driver: AsyncDriver | None = None

    async def connect(self) -> None:
        """Establish connection to Neo4j."""
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=(self._user, self._password),
        )
        # Verify connectivity
        await self._driver.verify_connectivity()
        logger.info("neo4j_connected", uri=self._uri)

    async def close(self) -> None:
        """Close the Neo4j connection."""
        if self._driver:
            await self._driver.close()
            self._driver = None
            logger.info("neo4j_disconnected")

    @property
    def driver(self) -> AsyncDriver:
        """Get the active driver, raising if not connected."""
        if self._driver is None:
            raise RuntimeError("Neo4j client not connected. Call connect() first.")
        return self._driver

    def session(self, **kwargs) -> AsyncSession:
        """Create a new async session."""
        return self.driver.session(**kwargs)

    async def execute_query(
        self,
        query: str,
        parameters: dict | None = None,
        database: str | None = None,
    ) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        async with self.session(database=database) as session:
            result = await session.run(query, parameters or {})
            records = await result.data()
            return records

    async def execute_write(
        self,
        query: str,
        parameters: dict | None = None,
        database: str | None = None,
    ) -> list[dict]:
        """Execute a write transaction."""
        async with self.session(database=database) as session:
            result = await session.execute_write(
                lambda tx: tx.run(query, parameters or {})
            )
            return await result.data() if result else []

    async def execute_batch(
        self,
        query: str,
        batch_params: list[dict],
        database: str | None = None,
    ) -> None:
        """Execute a parameterized query for each item in the batch.

        Uses UNWIND for efficient batch processing.
        """
        unwind_query = f"UNWIND $batch AS row\n{query}"
        async with self.session(database=database) as session:
            await session.execute_write(
                lambda tx: tx.run(unwind_query, {"batch": batch_params})
            )
        logger.debug("batch_executed", query_preview=query[:80], batch_size=len(batch_params))

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Module-level singleton (lazy initialization)
_client: Neo4jClient | None = None


async def get_client() -> Neo4jClient:
    """Get or create the singleton Neo4j client."""
    global _client
    if _client is None:
        _client = Neo4jClient()
        await _client.connect()
    return _client
