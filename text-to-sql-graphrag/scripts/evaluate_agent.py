"""Evaluate the LangGraph agent against the complete 30-case evaluation dataset."""

import asyncio
import sys
import argparse
import time
import json

# Ensure src and tests are importable
sys.path.insert(0, ".")

from tests.evaluation.test_evaluation import run_full_evaluation, load_test_cases
from src.agent.graph import compile_agent

async def main():
    parser = argparse.ArgumentParser(description="Run agent evaluation.")
    parser.add_argument("--difficulty", type=str, help="Filter by difficulty (easy, medium, hard, expert)")
    parser.add_argument("--limit", type=int, help="Limit number of tests to run")
    args = parser.parse_args()

    print("Compiling agent...")
    agent = compile_agent()
    print("Agent ready. Starting evaluation...\n")

    test_cases = load_test_cases()
    if args.difficulty:
        test_cases = [tc for tc in test_cases if tc["difficulty"] == args.difficulty]
    if args.limit:
        test_cases = test_cases[:args.limit]

    print(f"Running evaluation on {len(test_cases)} test cases.\n")

    async def agent_fn(question: str) -> str:
        """Wrapper to adapt the agent's dict output to the evaluator's string output, with rate limiting."""
        # 15 RPM free tier limit for Gemini 2.5 Flash -> ~4 seconds per request.
        await asyncio.sleep(4.5)
        
        result = await agent.ainvoke({
            "query": question,
            "sql_dialect": "postgres",
        })
        return result.get("final_sql") or result.get("generated_sql", "")

    start = time.time()
    await run_full_evaluation(agent_fn, test_cases)
    elapsed = time.time() - start
    print(f"\nEvaluation completed in {elapsed:.1f} seconds.")

if __name__ == "__main__":
    asyncio.run(main())
