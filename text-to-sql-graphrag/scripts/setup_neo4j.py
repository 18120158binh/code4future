"""CLI script: Setup Neo4j indexes and constraints."""

from __future__ import annotations

import asyncio

import typer
from rich.console import Console

from src.graph.client import Neo4jClient
from src.graph.indexes import setup_indexes

app = typer.Typer(help="Setup Neo4j indexes and constraints.")
console = Console()


@app.command()
def setup(
    uri: str = typer.Option(None, "--uri", help="Neo4j URI override."),
    user: str = typer.Option(None, "--user", help="Neo4j user override."),
    password: str = typer.Option(None, "--password", help="Neo4j password override."),
):
    """Create all required Neo4j indexes, constraints, and vector indexes."""
    asyncio.run(_setup(uri, user, password))


async def _setup(uri: str | None, user: str | None, password: str | None):
    console.print("\n🔧 Setting up Neo4j indexes and constraints...\n")

    client = Neo4jClient(uri=uri, user=user, password=password)
    try:
        await client.connect()
        console.print("[green]✓[/green] Connected to Neo4j")

        await setup_indexes(client)

        console.print("\n[green]✓ All indexes and constraints created![/green]")
    except Exception as e:
        console.print(f"\n[red]✗ Failed: {e}[/red]")
        raise typer.Exit(code=1)
    finally:
        await client.close()


if __name__ == "__main__":
    app()
