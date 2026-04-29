"""Benchmark report generator — side-by-side comparison of RAG vs GraphRAG.

Produces a clear, transparent report showing:
1. Overall accuracy comparison
2. Per-difficulty breakdown
3. Head-to-head per-case results
4. Hallucination comparison
5. Context comparison for cases where results diverge
"""

from __future__ import annotations

from tests.evaluation.test_evaluation import EvalResult


def print_benchmark_report(report) -> None:
    """Print the full benchmark comparison report.

    Args:
        report: A BenchmarkReport from benchmark.py.
    """
    comparisons = report.comparisons
    total = len(comparisons)

    if total == 0:
        print("No benchmark results to report.")
        return

    # Aggregate metrics
    rag_evals = [c.rag_eval for c in comparisons]
    graphrag_evals = [c.graphrag_eval for c in comparisons]

    rag_stats = _compute_stats(rag_evals, total)
    graphrag_stats = _compute_stats(graphrag_evals, total)

    # === Header ===
    print("\n" + "=" * 70)
    print("         RAG vs GraphRAG BENCHMARK REPORT")
    print("=" * 70)
    print(f"  Timestamp:    {report.timestamp}")
    print(f"  LLM Model:    {report.llm_model}")
    print(f"  Duration:     {report.total_duration_seconds}s")
    print(f"  Test Cases:   {total}")
    if report.config.get("dry_run"):
        print("  Mode:         DRY RUN (no LLM calls — used expected SQL)")
    print("=" * 70)

    # === Overall Results ===
    print("\n--- Overall Results ---\n")
    print(f"{'Metric':<30s} {'RAG':>10s} {'GraphRAG':>10s} {'Winner':>10s}")
    print("-" * 62)

    _print_metric_row(
        "SQL Syntax Valid",
        f"{rag_stats['valid']}/{total}",
        f"{graphrag_stats['valid']}/{total}",
        rag_stats['valid'],
        graphrag_stats['valid'],
    )
    _print_metric_row(
        "Table Recall (avg)",
        f"{rag_stats['avg_table_recall']:.0%}",
        f"{graphrag_stats['avg_table_recall']:.0%}",
        rag_stats['avg_table_recall'],
        graphrag_stats['avg_table_recall'],
    )
    _print_metric_row(
        "Column Recall (avg)",
        f"{rag_stats['avg_col_recall']:.0%}",
        f"{graphrag_stats['avg_col_recall']:.0%}",
        rag_stats['avg_col_recall'],
        graphrag_stats['avg_col_recall'],
    )
    _print_metric_row(
        "Correct Structure",
        f"{rag_stats['correct_structure']}/{total}",
        f"{graphrag_stats['correct_structure']}/{total}",
        rag_stats['correct_structure'],
        graphrag_stats['correct_structure'],
    )
    _print_metric_row(
        "Table Hallucinations (total)",
        str(rag_stats['total_hallucinated_tables']),
        str(graphrag_stats['total_hallucinated_tables']),
        -rag_stats['total_hallucinated_tables'],  # Lower is better
        -graphrag_stats['total_hallucinated_tables'],
    )
    _print_metric_row(
        "Missing Tables (total)",
        str(rag_stats['total_missing_tables']),
        str(graphrag_stats['total_missing_tables']),
        -rag_stats['total_missing_tables'],  # Lower is better
        -graphrag_stats['total_missing_tables'],
    )
    _print_metric_row(
        "Extra Tables (total)",
        str(rag_stats['total_extra_tables']),
        str(graphrag_stats['total_extra_tables']),
        -rag_stats['total_extra_tables'],  # Lower is better
        -graphrag_stats['total_extra_tables'],
    )

    # Composite score
    rag_composite = _composite_score(rag_stats)
    graphrag_composite = _composite_score(graphrag_stats)
    _print_metric_row(
        "COMPOSITE SCORE",
        f"{rag_composite:.1f}%",
        f"{graphrag_composite:.1f}%",
        rag_composite,
        graphrag_composite,
    )

    # === By Difficulty ===
    print("\n--- By Difficulty ---\n")
    print(f"{'Difficulty':<12s} {'RAG Valid':>12s} {'GR Valid':>12s} "
          f"{'RAG TblRecall':>14s} {'GR TblRecall':>14s} "
          f"{'RAG Struct':>12s} {'GR Struct':>12s}")
    print("-" * 80)

    for diff in ["easy", "medium", "hard", "expert"]:
        diff_comps = [c for c in comparisons if c.difficulty == diff]
        if not diff_comps:
            continue
        n = len(diff_comps)
        r_evals = [c.rag_eval for c in diff_comps]
        g_evals = [c.graphrag_eval for c in diff_comps]
        r_s = _compute_stats(r_evals, n)
        g_s = _compute_stats(g_evals, n)

        print(
            f"  {diff:<10s} "
            f"{r_s['valid']:>4d}/{n:<4d}     "
            f"{g_s['valid']:>4d}/{n:<4d}     "
            f"{r_s['avg_table_recall']:>10.0%}      "
            f"{g_s['avg_table_recall']:>10.0%}      "
            f"{r_s['correct_structure']:>4d}/{n:<4d}     "
            f"{g_s['correct_structure']:>4d}/{n:<4d}"
        )

    # === Head-to-Head ===
    print("\n--- Head-to-Head Results ---\n")
    rag_wins = 0
    graphrag_wins = 0
    ties = 0

    for comp in comparisons:
        r = comp.rag_eval
        g = comp.graphrag_eval

        r_score = _case_score(r)
        g_score = _case_score(g)

        if r_score > g_score:
            winner = "RAG"
            rag_wins += 1
            marker = "<-- RAG"
        elif g_score > r_score:
            winner = "GraphRAG"
            graphrag_wins += 1
            marker = "<-- GraphRAG"
        else:
            winner = "TIE"
            ties += 1
            marker = ""

        r_status = "OK" if r.sql_is_valid else "ERR"
        g_status = "OK" if g.sql_is_valid else "ERR"

        print(
            f"  [{comp.test_id:<10s}] "
            f"RAG: {r_status} tbl={r.table_recall:.0%} "
            f"struct={'Y' if r.has_correct_structure else 'N'}  |  "
            f"GR: {g_status} tbl={g.table_recall:.0%} "
            f"struct={'Y' if g.has_correct_structure else 'N'}  "
            f"{marker}"
        )

    print(f"\n  Summary: RAG wins={rag_wins}, GraphRAG wins={graphrag_wins}, "
          f"Ties={ties}")

    # === Cases where they differ ===
    divergent = [
        c for c in comparisons
        if _case_score(c.rag_eval) != _case_score(c.graphrag_eval)
    ]

    if divergent:
        print(f"\n--- Divergent Cases ({len(divergent)}) ---")
        print("  (Cases where RAG and GraphRAG produced different outcomes)\n")

        for comp in divergent:
            r = comp.rag_eval
            g = comp.graphrag_eval

            print(f"  [{comp.test_id}] \"{comp.question[:65]}\"")
            print(f"    RAG context tables:      {comp.rag_tables_in_context}")
            print(f"    GraphRAG context tables:  {comp.graphrag_tables_in_context}")

            if r.missing_tables:
                print(f"    RAG missing tables:      {r.missing_tables}")
            if g.missing_tables:
                print(f"    GraphRAG missing tables: {g.missing_tables}")

            if r.hallucinated_tables:
                print(f"    RAG hallucinated:        {r.hallucinated_tables}")
            if g.hallucinated_tables:
                print(f"    GraphRAG hallucinated:   {g.hallucinated_tables}")

            # Show SQL snippets
            print(f"    RAG SQL:     {r.generated_sql[:100]}...")
            print(f"    GraphRAG SQL: {g.generated_sql[:100]}...")
            print()

    # === Conclusion ===
    print("=" * 70)
    print("  CONCLUSION")
    print("=" * 70)

    if graphrag_composite > rag_composite + 5:
        print(f"  GraphRAG outperforms RAG by {graphrag_composite - rag_composite:.1f} points.")
        print(f"  GraphRAG wins {graphrag_wins}/{total} cases vs RAG's {rag_wins}/{total}.")
        print(f"  The graph expansion and structural relationships provide")
        print(f"  measurable accuracy improvements, especially on complex queries.")
    elif rag_composite > graphrag_composite + 5:
        print(f"  RAG outperforms GraphRAG by {rag_composite - graphrag_composite:.1f} points.")
        print(f"  The additional complexity of GraphRAG does not justify")
        print(f"  the infrastructure cost for this schema and query set.")
    else:
        print(f"  Results are close (delta={abs(graphrag_composite - rag_composite):.1f} points).")
        print(f"  RAG wins={rag_wins}, GraphRAG wins={graphrag_wins}, Ties={ties}.")
        print(f"  Consider running multiple times or on harder queries for")
        print(f"  a more conclusive result.")

    print("=" * 70)


# =============================================================================
# Helpers
# =============================================================================


def _compute_stats(evals: list[EvalResult], total: int) -> dict:
    """Compute aggregate statistics from a list of EvalResults."""
    valid = sum(1 for r in evals if r.sql_is_valid)
    correct_structure = sum(1 for r in evals if r.has_correct_structure)
    avg_table_recall = sum(r.table_recall for r in evals) / total if total else 0
    avg_col_recall = sum(r.column_recall for r in evals) / total if total else 0
    total_hallucinated = sum(len(r.hallucinated_tables) for r in evals)
    total_missing = sum(len(r.missing_tables) for r in evals)
    total_extra = sum(len(r.extra_tables) for r in evals)

    return {
        "valid": valid,
        "correct_structure": correct_structure,
        "avg_table_recall": avg_table_recall,
        "avg_col_recall": avg_col_recall,
        "total_hallucinated_tables": total_hallucinated,
        "total_missing_tables": total_missing,
        "total_extra_tables": total_extra,
    }


def _print_metric_row(
    name: str, rag_val: str, graphrag_val: str, rag_num: float, graphrag_num: float
):
    """Print a single metric comparison row."""
    if rag_num > graphrag_num:
        winner = "RAG"
    elif graphrag_num > rag_num:
        winner = "GraphRAG"
    else:
        winner = "TIE"

    print(f"  {name:<28s} {rag_val:>10s} {graphrag_val:>10s} {winner:>10s}")


def _case_score(eval_result: EvalResult) -> float:
    """Compute a simple composite score for a single case.

    Weights:
    - SQL valid: 25%
    - Table recall: 35%
    - Column recall: 20%
    - Structure match: 20%
    """
    return (
        (1.0 if eval_result.sql_is_valid else 0.0) * 25
        + eval_result.table_recall * 35
        + eval_result.column_recall * 20
        + (1.0 if eval_result.has_correct_structure else 0.0) * 20
    )


def _composite_score(stats: dict) -> float:
    """Compute overall composite score from aggregate stats.

    Higher is better. Penalizes hallucinations.
    """
    total = max(stats.get("valid", 0) + stats.get("correct_structure", 0), 1)
    base = (
        stats["avg_table_recall"] * 35
        + stats["avg_col_recall"] * 20
        + (stats["correct_structure"] / max(total, 1)) * 25
        + (stats["valid"] / max(total, 1)) * 20
    )
    # Penalty for hallucinations (each hallucinated table = -2 points)
    hallucination_penalty = stats["total_hallucinated_tables"] * 2
    return max(0, base - hallucination_penalty)
