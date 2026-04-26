"""End-to-end test: Run the LangGraph agent on sample questions."""

import asyncio
import sys
import time

# Ensure src is importable
sys.path.insert(0, ".")


async def test_single_query(agent, question: str, label: str):
    """Run a single query through the agent and print results."""
    print(f"\n{'='*70}")
    print(f"[{label}] {question}")
    print("=" * 70)

    start = time.time()
    try:
        result = await agent.ainvoke({
            "query": question,
            "sql_dialect": "postgres",
        })
        elapsed = time.time() - start

        if result.get("error"):
            print(f"  ERROR: {result['error']}")
        else:
            print(f"  SQL:\n    {result.get('final_sql', 'N/A')}")
            print(f"  Explanation: {result.get('explanation', 'N/A')}")
            print(f"  Confidence: {result.get('confidence', 'N/A')}")
            print(f"  Retries: {result.get('retry_count', 0)}")

        print(f"  Time: {elapsed:.1f}s")
        return result

    except Exception as e:
        elapsed = time.time() - start
        print(f"  EXCEPTION: {type(e).__name__}: {e}")
        print(f"  Time: {elapsed:.1f}s")
        return None


async def main():
    from src.agent.graph import compile_agent

    print("Compiling agent...")
    agent = compile_agent()
    print("Agent ready.\n")

    # Test cases: easy → hard
    test_questions = [
        ("easy", "How many users do we have?"),
        ("medium", "What is the average session duration by device type?"),
        ("hard", "Show me the top 5 landing pages that lead to the most purchases, include the total revenue"),
    ]

    results = []
    for label, question in test_questions:
        result = await test_single_query(agent, question, label)
        results.append((label, question, result))

        # Small delay to avoid API rate limits
        await asyncio.sleep(2)

    # Summary
    print(f"\n{'='*70}")
    print("SUMMARY")
    print("=" * 70)
    for label, question, result in results:
        if result is None:
            status = "EXCEPTION"
        elif result.get("error"):
            status = "FAILED"
        elif result.get("final_sql"):
            status = "OK"
        else:
            status = "EMPTY"
        print(f"  [{label:6s}] {status:10s} | {question[:60]}")


if __name__ == "__main__":
    asyncio.run(main())
