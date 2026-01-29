"""
Test disambiguation when NO season is specified.
"""
import asyncio
from app.agent import agent

async def test_no_season():
    """Test Dangerfield with no season."""
    print("=" * 80)
    print("Test: Ambiguous player name WITHOUT season")
    print("Query: How many goals did Dangerfield kick?")
    print("=" * 80)

    result = await agent.run(user_query="How many goals did Dangerfield kick?")

    print(f"\nIntent: {result.get('intent')}")
    print(f"Entities: {result.get('entities')}")
    print(f"Needs Clarification: {result.get('needs_clarification')}")
    print(f"Clarification Question: {result.get('clarification_question')}")
    print(f"\nResponse:")
    print(result.get('natural_language_summary'))
    print(f"\nConfidence: {result.get('confidence')}")

if __name__ == "__main__":
    asyncio.run(test_no_season())
