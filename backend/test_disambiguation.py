"""
Test player disambiguation system.
"""
import asyncio
from app.agent import agent

async def test_disambiguation():
    """Test Dangerfield disambiguation."""
    print("=" * 80)
    print("Test 1: Ambiguous player name with season")
    print("Query: How many goals did Dangerfield kick in 2022?")
    print("=" * 80)

    result = await agent.run(user_query="How many goals did Dangerfield kick in 2022?")

    print(f"\nIntent: {result.get('intent')}")
    print(f"Entities: {result.get('entities')}")
    print(f"Needs Clarification: {result.get('needs_clarification')}")
    print(f"Clarification Question: {result.get('clarification_question')}")
    print(f"\nResponse:")
    print(result.get('natural_language_summary'))
    print(f"\nConfidence: {result.get('confidence')}")

    print("\n" + "=" * 80)
    print("Test 2: Specific player name (should work)")
    print("Query: How many goals did Patrick Dangerfield kick in 2022?")
    print("=" * 80)

    result2 = await agent.run(user_query="How many goals did Patrick Dangerfield kick in 2022?")

    print(f"\nIntent: {result2.get('intent')}")
    print(f"Entities: {result2.get('entities')}")
    print(f"Needs Clarification: {result2.get('needs_clarification')}")
    print(f"\nResponse:")
    print(result2.get('natural_language_summary'))
    print(f"\nConfidence: {result2.get('confidence')}")

if __name__ == "__main__":
    asyncio.run(test_disambiguation())
