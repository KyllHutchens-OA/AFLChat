"""
Test Dangerfield goals query to reproduce the issue.
"""
import asyncio
from app.agent import agent

async def test_dangerfield_query():
    """Test Dangerfield goals query."""
    print("=" * 80)
    print("Testing: How many goals did Dangerfield kick in 2022?")
    print("=" * 80)

    query = "How many goals did Dangerfield kick in 2022?"

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
    asyncio.run(test_dangerfield_query())
