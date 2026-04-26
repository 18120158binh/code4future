"""CLI script: Run dbt docs ingestion into Neo4j."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from src.config import settings
from src.graph.client import Neo4jClient
from src.graph.indexes import setup_indexes
from src.ingestion.pipeline import run_ingestion

app = typer.Typer(help="Ingest dbt docs into the Neo4j knowledge graph.")
console = Console()


@app.command()
def ingest(
    docs_path: str = typer.Option(
        None,
        "--docs-path", "-d",
        help="Path to dbt docs directory (containing manifest.json).",
    ),
    full_sync: bool = typer.Option(
        False,
        "--full-sync", "-f",
        help="Force full re-sync instead of incremental.",
    ),
    skip_enrichment: bool = typer.Option(
        False,
        "--skip-enrichment",
        help="Skip LLM description enrichment.",
    ),
    skip_embeddings: bool = typer.Option(
        False,
        "--skip-embeddings",
        help="Skip embedding generation.",
    ),
    setup: bool = typer.Option(
        True,
        "--setup/--no-setup",
        help="Run index setup before ingestion.",
    ),
):
    """Parse dbt docs and ingest into Neo4j knowledge graph."""
    asyncio.run(_run_ingest(
        docs_path=docs_path,
        full_sync=full_sync,
        skip_enrichment=skip_enrichment,
        skip_embeddings=skip_embeddings,
        run_setup=setup,
    ))


async def _run_ingest(
    docs_path: str | None,
    full_sync: bool,
    skip_enrichment: bool,
    skip_embeddings: bool,
    run_setup: bool,
):
    path = Path(docs_path) if docs_path else settings.dbt_docs_path

    console.print(f"\n[bold]Docs path:[/bold] [cyan]{path}[/cyan]")
    console.print(f"[bold]Mode:[/bold] [yellow]{'Full Sync' if full_sync else 'Incremental'}[/yellow]")
    console.print(f"[bold]LLM:[/bold] [green]{settings.llm_provider.value}[/green]")
    console.print()

    async with Neo4jClient() as client:
        # Setup indexes
        if run_setup:
            console.print("[bold]Setting up Neo4j indexes...[/bold]")
            await setup_indexes(client)
            console.print("[green]> Indexes ready[/green]\n")

        # Run ingestion
        console.print("[bold]Running ingestion pipeline...[/bold]\n")
        result = await run_ingestion(
            client=client,
            docs_path=path,
            skip_enrichment=skip_enrichment,
            skip_embeddings=skip_embeddings,
            full_sync=full_sync,
        )

        # Display results
        table = Table(title="Ingestion Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Count", style="green", justify="right")

        table.add_row("New tables", str(result.new_count))
        table.add_row("Modified tables", str(result.modified_count))
        table.add_row("Unchanged tables", str(result.unchanged_count))
        table.add_row("Deleted tables", str(result.deleted_count))
        table.add_row("Embeddings generated", str(result.embeddings_generated))

        console.print(table)
        console.print("\n[green]> Ingestion complete![/green]")


if __name__ == "__main__":
    app()

