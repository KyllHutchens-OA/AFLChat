"""
Test script to reproduce the follow-up query failure.
"""
import asyncio
from app.agent import agent
from app.services.conversation_service import ConversationService

async def test_followup_failure():
    """Test follow-up query to see why it fails."""
    print("=" * 80)
    print("Testing Follow-up Query: 'Can you show this by year?'")
    print("=" * 80)

    # Create conversation
    conv_id = ConversationService.create_conversation(user_id="test_user")

    # Query 1: Initial question
    query1 = "How many touches did Rory Sloane have in his career?"
    print(f"\nQuery 1: {query1}\n")

    ConversationService.add_message(conv_id, "user", query1)
    history = ConversationService.get_recent_messages(conv_id, limit=10)

    result1 = await agent.run(
        user_query=query1,
        conversation_id=conv_id,
        conversation_history=history
    )

    response1 = result1.get("natural_language_summary", "No response")
    print(f"Response 1:\n{response1}\n")

    # Save assistant response
    ConversationService.add_message(
        conv_id,
        "assistant",
        response1,
        metadata={
            "entities": result1.get("entities", {}),
            "intent": str(result1.get("intent", "")),
            "confidence": result1.get("confidence", 0.0)
        }
    )

    # Query 2: Follow-up question
    print("=" * 80)
    query2 = "Can you show this by year?"
    print(f"\nQuery 2: {query2}\n")

    ConversationService.add_message(conv_id, "user", query2)
    history = ConversationService.get_recent_messages(conv_id, limit=10)

    print(f"Conversation history loaded: {len(history)} messages")
    for msg in history:
        print(f"  - {msg['role']}: {msg['content'][:80]}...")
        if msg['role'] == 'assistant' and 'entities' in msg:
            print(f"    Entities: {msg['entities']}")

    print("\nRunning agent with conversation context...\n")

    result2 = await agent.run(
        user_query=query2,
        conversation_id=conv_id,
        conversation_history=history
    )

    response2 = result2.get("natural_language_summary", "No response")
    errors = result2.get("errors", [])
    execution_error = result2.get("execution_error")

    print(f"Intent: {result2.get('intent')}")
    print(f"Entities: {result2.get('entities')}")
    print(f"SQL Query: {result2.get('sql_query')}")
    print(f"Execution Error: {execution_error}")
    print(f"Errors: {errors}")
    print(f"\nResponse 2:\n{response2}\n")

    if execution_error or errors:
        print("❌ Query failed!")
        print(f"Execution Error: {execution_error}")
        print(f"Errors: {errors}")
    else:
        print("✅ Query succeeded!")

if __name__ == "__main__":
    asyncio.run(test_followup_failure())
