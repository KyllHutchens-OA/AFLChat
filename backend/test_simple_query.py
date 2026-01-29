"""
Test script to verify simple queries get concise responses.
"""
import asyncio
from app.agent import agent

async def test_simple_query():
    """Test a simple stat query for concise response."""
    print("=" * 80)
    print("Testing Simple Query Response Style")
    print("=" * 80)

    query = "How many career disposals did Rory Sloane have?"
    print(f"\nQuery: {query}\n")

    result = await agent.run(user_query=query)

    response = result.get("natural_language_summary", "No response")
    intent = result.get("intent")
    analysis_mode = result.get("analysis_mode")

    print(f"Intent: {intent}")
    print(f"Analysis Mode: {analysis_mode}")
    print(f"\nResponse:\n{response}\n")

    # Check response length
    sentences = response.split('. ')
    print(f"Number of sentences: {len(sentences)}")

    if len(sentences) <= 3:
        print("✅ Response is concise!")
    else:
        print(f"⚠️ Response is too long ({len(sentences)} sentences)")

if __name__ == "__main__":
    asyncio.run(test_simple_query())
