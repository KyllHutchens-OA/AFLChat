"""
Test Grand Final query to see the date issue.
"""
import asyncio
from app.agent import agent

async def test_grandfinal_query():
    """Test Grand Final query."""
    print("=" * 80)
    print("Testing: Who won the 2024 Grand Final?")
    print("=" * 80)

    query = "Who won the 2024 Grand Final?"

    result = await agent.run(user_query=query)

    print(f"\nIntent: {result.get('intent')}")
    print(f"Entities: {result.get('entities')}")
    print(f"\nSQL Query:")
    print(result.get('sql_query'))
    print(f"\nQuery Results:")
    print(result.get('query_results'))
    print(f"\nResponse:")
    print(result.get('natural_language_summary'))
    print(f"\nErrors: {result.get('errors')}")

if __name__ == "__main__":
    asyncio.run(test_grandfinal_query())
