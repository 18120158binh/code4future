"""Head-to-head benchmark: Vanilla RAG vs GraphRAG for Text-to-SQL.

Runs both retrieval strategies on the same test cases with the same LLM
and prompt, comparing only the schema context each produces.

Usage:
    # Full benchmark (requires Neo4j + Google API)
    python -m tests.evaluation.benchmark

    # Dry run (test retrieval without LLM calls)
    python -m tests.evaluation.benchmark --dry-run

    # Filter by difficulty
    python -m tests.evaluation.benchmark --difficulty easy

    # Limit number of cases
    python -m tests.evaluation.benchmark --limit 5
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

import structlog

from src.config import settings
from src.graph.client import Neo4jClient
from src.retrieval.retriever import HybridRetriever
from src.retrieval.vanilla_retriever import VanillaRAGRetriever
from src.retrieval.embedder import EmbedderService
from src.agent.prompts import SQL_GENERATION_SYSTEM, SQL_GENERATION_USER
from src.agent.validator import extract_sql_from_response
from tests.evaluation.test_evaluation import (
    load_test_cases,
    evaluate_single,
    EvalResult,
    ALL_KNOWN_TABLES,
)

logger = structlog.get_logger(__name__)

# Rate limit delay between LLM calls (seconds)
RATE_LIMIT_DELAY = 4.0


# =============================================================================
# API Key Rotation
# =============================================================================


def _load_api_keys() -> list[str]:
    """Load all available Google API keys from environment."""
    from dotenv import load_dotenv
    load_dotenv()

    keys = []
    primary = os.getenv("GOOGLE_API_KEY")
    if primary:
        keys.append(primary)
    secondary = os.getenv("GOOGLE_API_KEY_2")
    if secondary:
        keys.append(secondary)
    return keys


class KeyRotatingLLM:
    """Rotates between multiple API keys to double rate limit quota."""

    def __init__(self):
        self._keys = _load_api_keys()
        self._index = 0
        self._llms: list = []

        if not self._keys:
            raise ValueError("No GOOGLE_API_KEY found in .env")

        from langchain_google_genai import ChatGoogleGenerativeAI

        for key in self._keys:
            self._llms.append(
                ChatGoogleGenerativeAI(
                    google_api_key=key,
                    model=settings.google_llm_model,
                    temperature=0,
                )
            )

        logger.info("api_key_rotation_init", num_keys=len(self._keys))

    def get_next(self):
        """Get the next LLM instance (round-robin)."""
        llm = self._llms[self._index % len(self._llms)]
        self._index += 1
        return llm


# =============================================================================
# Data Models
# =============================================================================


@dataclass
class CaseComparison:
    """Side-by-side comparison for a single test case."""

    test_id: str
    difficulty: str
    question: str
    # RAG results
    rag_context: str
    rag_generated_sql: str
    rag_eval: EvalResult
    # GraphRAG results
    graphrag_context: str
    graphrag_generated_sql: str
    graphrag_eval: EvalResult
    # Metadata
    rag_tables_in_context: list[str] = field(default_factory=list)
    graphrag_tables_in_context: list[str] = field(default_factory=list)


@dataclass
class BenchmarkReport:
    """Complete benchmark results."""

    comparisons: list[CaseComparison]
    timestamp: str
    total_duration_seconds: float
    llm_model: str
    config: dict = field(default_factory=dict)


# =============================================================================
# LLM Generation (shared by both pipelines)
# =============================================================================


async def generate_sql_with_context(
    query: str,
    schema_context: str,
    dialect: str | None = None,
    llm=None,
) -> str:
    """Generate SQL using the SAME prompt and LLM for both pipelines.

    This ensures the only variable is the schema_context string.
    """
    dialect = dialect or settings.sql_dialect.value
    if llm is None:
        llm = settings.get_llm()

    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(content=SQL_GENERATION_SYSTEM.format(dialect=dialect)),
        HumanMessage(
            content=SQL_GENERATION_USER.format(
                schema_context=schema_context,
                query=query,
            )
        ),
    ]

    response = await llm.ainvoke(messages)
    sql = extract_sql_from_response(response.content)

    return sql


# =============================================================================
# Benchmark Runner
# =============================================================================


async def run_benchmark(
    test_cases: list[dict] | None = None,
    difficulty_filter: str | None = None,
    limit: int | None = None,
    dry_run: bool = False,
) -> BenchmarkReport:
    """Run the full RAG vs GraphRAG benchmark.

    Args:
        test_cases: Test cases to use. Loads from JSON if None.
        difficulty_filter: Filter by difficulty level.
        limit: Max number of test cases to run.
        dry_run: If True, only test retrieval without LLM calls.

    Returns:
        BenchmarkReport with all comparisons.
    """
    if test_cases is None:
        test_cases = load_test_cases()

    if difficulty_filter:
        test_cases = [
            tc for tc in test_cases if tc["difficulty"] == difficulty_filter
        ]

    if limit:
        test_cases = test_cases[:limit]

    total = len(test_cases)
    print(f"\n{'=' * 70}")
    print(f"  RAG vs GraphRAG BENCHMARK")
    print(f"  Test cases: {total}")
    print(f"  LLM: {settings.google_llm_model}")
    print(f"  Mode: {'DRY RUN (no LLM calls)' if dry_run else 'LIVE'}")
    print(f"{'=' * 70}\n")

    comparisons: list[CaseComparison] = []
    start_time = time.time()

    # Share a single embedder to avoid re-initialization
    embedder = EmbedderService()

    # Initialize key rotation for LLM calls
    key_rotator = None
    if not dry_run:
        try:
            key_rotator = KeyRotatingLLM()
        except Exception as e:
            logger.warning("key_rotation_init_failed", error=str(e))

    async with Neo4jClient() as client:
        # Initialize both retrievers
        vanilla_retriever = VanillaRAGRetriever(client, embedder)
        graphrag_retriever = HybridRetriever(client, embedder)

        for i, tc in enumerate(test_cases, 1):
            test_id = tc["id"]
            question = tc["question"]
            safe_q = question[:60].encode('ascii', 'replace').decode('ascii')
            print(f"[{i}/{total}] {test_id}: {safe_q}...")

            try:
                comparison = await _run_single_comparison(
                    tc=tc,
                    vanilla_retriever=vanilla_retriever,
                    graphrag_retriever=graphrag_retriever,
                    dry_run=dry_run,
                    key_rotator=key_rotator,
                )
                comparisons.append(comparison)

                # Print quick result
                r = comparison.rag_eval
                g = comparison.graphrag_eval
                rag_status = "VALID" if r.sql_is_valid else "INVALID"
                graphrag_status = "VALID" if g.sql_is_valid else "INVALID"
                print(
                    f"  RAG:      {rag_status}, "
                    f"tables={r.table_recall:.0%}, "
                    f"structure={'Y' if r.has_correct_structure else 'N'}"
                )
                print(
                    f"  GraphRAG: {graphrag_status}, "
                    f"tables={g.table_recall:.0%}, "
                    f"structure={'Y' if g.has_correct_structure else 'N'}"
                )

            except Exception as e:
                logger.error(
                    "benchmark_case_failed", test_id=test_id, error=str(e)
                )
                print(f"  ERROR: {e}")

    duration = time.time() - start_time

    report = BenchmarkReport(
        comparisons=comparisons,
        timestamp=datetime.now().isoformat(),
        total_duration_seconds=round(duration, 1),
        llm_model=settings.google_llm_model,
        config={
            "top_k": settings.retrieval_top_k,
            "graph_expansion_hops": settings.graph_expansion_hops,
            "sql_dialect": settings.sql_dialect.value,
            "dry_run": dry_run,
            "difficulty_filter": difficulty_filter,
            "total_cases": total,
        },
    )

    print(f"\nBenchmark completed in {duration:.1f}s")

    return report


async def _run_single_comparison(
    tc: dict,
    vanilla_retriever: VanillaRAGRetriever,
    graphrag_retriever: HybridRetriever,
    dry_run: bool,
    key_rotator: KeyRotatingLLM | None = None,
) -> CaseComparison:
    """Run both pipelines on a single test case."""
    question = tc["question"]

    # --- RAG Pipeline ---
    rag_result = await vanilla_retriever.retrieve(question)
    rag_context = rag_result.context
    rag_tables_in_context = rag_result.tables_found

    if dry_run:
        rag_sql = tc["expected_sql"]  # Use expected SQL for eval testing
    else:
        llm = key_rotator.get_next() if key_rotator else None
        rag_sql = await generate_sql_with_context(question, rag_context, llm=llm)
        await asyncio.sleep(RATE_LIMIT_DELAY)

    rag_eval = evaluate_single(tc, rag_sql, ALL_KNOWN_TABLES)

    # --- GraphRAG Pipeline ---
    graphrag_result = await graphrag_retriever.retrieve(question)
    graphrag_context = graphrag_result.context
    graphrag_tables_in_context = [
        t.name for t in graphrag_result.subgraph.tables
    ]

    if dry_run:
        graphrag_sql = tc["expected_sql"]
    else:
        llm = key_rotator.get_next() if key_rotator else None
        graphrag_sql = await generate_sql_with_context(question, graphrag_context, llm=llm)
        await asyncio.sleep(RATE_LIMIT_DELAY)

    graphrag_eval = evaluate_single(tc, graphrag_sql, ALL_KNOWN_TABLES)

    return CaseComparison(
        test_id=tc["id"],
        difficulty=tc["difficulty"],
        question=question,
        rag_context=rag_context,
        rag_generated_sql=rag_sql,
        rag_eval=rag_eval,
        graphrag_context=graphrag_context,
        graphrag_generated_sql=graphrag_sql,
        graphrag_eval=graphrag_eval,
        rag_tables_in_context=rag_tables_in_context,
        graphrag_tables_in_context=graphrag_tables_in_context,
    )


# =============================================================================
# Report Serialization
# =============================================================================


def save_benchmark_results(
    report: BenchmarkReport,
    output_path: Path | None = None,
) -> Path:
    """Save benchmark results as JSON for further analysis."""
    if output_path is None:
        output_path = (
            Path(__file__).parent / "benchmark_results.json"
        )

    def _serialize(obj):
        if isinstance(obj, set):
            return sorted(list(obj))
        if isinstance(obj, EvalResult):
            d = {}
            for f in obj.__dataclass_fields__:
                v = getattr(obj, f)
                d[f] = sorted(list(v)) if isinstance(v, set) else v
            return d
        return str(obj)

    data = {
        "timestamp": report.timestamp,
        "duration_seconds": report.total_duration_seconds,
        "llm_model": report.llm_model,
        "config": report.config,
        "results": [],
    }

    for comp in report.comparisons:
        data["results"].append({
            "test_id": comp.test_id,
            "difficulty": comp.difficulty,
            "question": comp.question,
            "rag": {
                "generated_sql": comp.rag_generated_sql,
                "tables_in_context": comp.rag_tables_in_context,
                "eval": _serialize(comp.rag_eval),
            },
            "graphrag": {
                "generated_sql": comp.graphrag_generated_sql,
                "tables_in_context": comp.graphrag_tables_in_context,
                "eval": _serialize(comp.graphrag_eval),
            },
        })

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=_serialize)

    print(f"Results saved to: {output_path}")
    return output_path


# =============================================================================
# CLI entry point
# =============================================================================


def main():
    """CLI entry point for running the benchmark."""
    import argparse

    parser = argparse.ArgumentParser(
        description="RAG vs GraphRAG Text-to-SQL Benchmark"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Test retrieval only, skip LLM generation",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard", "expert"],
        help="Filter test cases by difficulty",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Maximum number of test cases to run",
    )
    parser.add_argument(
        "--output",
        type=str,
        help="Output path for JSON results",
    )

    args = parser.parse_args()

    output_path = Path(args.output) if args.output else None

    report = asyncio.run(
        run_benchmark(
            difficulty_filter=args.difficulty,
            limit=args.limit,
            dry_run=args.dry_run,
        )
    )

    # Generate and print the report
    from tests.evaluation.report import print_benchmark_report

    print_benchmark_report(report)

    # Save results
    save_benchmark_results(report, output_path)


if __name__ == "__main__":
    main()
