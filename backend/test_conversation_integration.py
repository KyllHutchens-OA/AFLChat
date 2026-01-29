"""
Test script for conversation history and WebSocket progress updates.
"""
import asyncio
from app.services.conversation_service import ConversationService
from app.agent import agent

# Mock socketio emit for testing
emitted_messages = []

def mock_emit(event, data):
    """Mock socketio emit to capture progress updates."""
    emitted_messages.append({
        'event': event,
        'data': data
    })
    print(f"[WebSocket] {event}: {data.get('step', data)}")

async def test_conversation_flow():
    """Test conversation history and progress updates."""
    print("=" * 80)
    print("Testing Conversation History & WebSocket Progress Updates")
    print("=" * 80)

    # Create a new conversation
    conv_id = ConversationService.create_conversation(user_id="test_user_123")
    print(f"\n✅ Created conversation: {conv_id}\n")

    # Test 1: First query
    print("📝 Test 1: Initial query about Richmond")
    print("-" * 80)
    query1 = "How many wins did Richmond have in 2024?"

    # Add user message
    ConversationService.add_message(conv_id, "user", query1)

    # Get conversation history
    history = ConversationService.get_recent_messages(conv_id, limit=10)

    # Run agent with WebSocket and history
    result = await agent.run(
        user_query=query1,
        conversation_id=conv_id,
        socketio_emit=mock_emit,
        conversation_history=history
    )

    response1 = result.get("natural_language_summary", "No response")
    print(f"\n🤖 Agent Response:\n{response1}\n")

    # Save assistant response
    ConversationService.add_message(
        conv_id,
        "assistant",
        response1,
        metadata={
            "entities": result.get("entities", {}),
            "intent": str(result.get("intent", "")),
            "confidence": result.get("confidence", 0.0)
        }
    )

    # Check progress updates
    print(f"\n📊 WebSocket Progress Updates: {len(emitted_messages)} emitted")
    for msg in emitted_messages[:5]:  # Show first 5
        print(f"  - {msg['event']}: {msg['data'].get('step', msg['data'])}")

    # Test 2: Follow-up query (should use conversation context)
    print("\n" + "=" * 80)
    print("📝 Test 2: Follow-up query (should reference Richmond from context)")
    print("-" * 80)

    emitted_messages.clear()  # Reset

    query2 = "What about 2023?"  # This should understand we're still talking about Richmond

    # Add user message
    ConversationService.add_message(conv_id, "user", query2)

    # Get updated conversation history
    history = ConversationService.get_recent_messages(conv_id, limit=10)
    print(f"\n📜 Conversation history: {len(history)} messages loaded")

    # Run agent with context
    result2 = await agent.run(
        user_query=query2,
        conversation_id=conv_id,
        socketio_emit=mock_emit,
        conversation_history=history
    )

    response2 = result2.get("natural_language_summary", "No response")
    print(f"\n🤖 Agent Response:\n{response2}\n")

    # Check if Richmond was understood from context
    entities2 = result2.get("entities", {})
    print(f"\n🔍 Entities extracted: {entities2}")

    if "Richmond" in str(entities2.get("teams", [])):
        print("✅ SUCCESS: Agent understood 'Richmond' from conversation context!")
    else:
        print("⚠️ WARNING: Agent may not have used conversation context properly")

    # Show conversation summary
    print("\n" + "=" * 80)
    print("📊 Conversation Summary")
    print("-" * 80)
    summary = ConversationService.get_conversation_summary(conv_id)
    print(f"Message count: {summary['message_count']}")
    print(f"User messages: {summary['user_messages']}")
    print(f"Assistant messages: {summary['assistant_messages']}")
    print(f"Teams discussed: {summary['teams_discussed']}")
    print(f"Players discussed: {summary['players_discussed']}")

    print("\n✅ All tests completed!")

if __name__ == "__main__":
    asyncio.run(test_conversation_flow())
