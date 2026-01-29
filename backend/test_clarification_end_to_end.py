"""
End-to-end test for clarification chain resolution.
Simulates the exact scenario from the user's screenshot.
"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.agent import agent
from app.services.conversation_service import ConversationService


async def test_daicos_clarification():
    """Test the exact scenario: Daicos → Josh please"""
    print("=" * 80)
    print("END-TO-END TEST: Daicos Clarification Chain")
    print("=" * 80)

    # Create a new conversation
    conversation_id = ConversationService.create_conversation()
    print(f"\n✓ Created conversation: {conversation_id}")

    # Step 1: Ask about Daicos
    print("\n" + "=" * 80)
    print("STEP 1: User asks 'How many goals did Daicos kick last year?'")
    print("=" * 80)

    result1 = await agent.run(
        user_query="How many goals did Daicos kick last year?",
        conversation_id=conversation_id,
        conversation_history=[]
    )

    print(f"\nIntent: {result1.get('intent')}")
    print(f"Entities: {result1.get('entities')}")
    print(f"Needs Clarification: {result1.get('needs_clarification')}")
    print(f"\nResponse:")
    print(result1.get('natural_language_summary'))

    # Verify we got a clarification
    if not result1.get('needs_clarification'):
        print("\n❌ FAILED: Expected clarification but got direct answer")
        return False

    if "josh daicos" not in result1.get('natural_language_summary', '').lower():
        print("\n❌ FAILED: Expected 'Josh Daicos' in clarification options")
        return False

    print("\n✓ PASSED: Got clarification with multiple Daicos players")

    # Save the assistant's clarification to conversation history (simulating websocket behavior)
    from app.utils.json_serialization import make_json_serializable

    metadata = {
        "entities": make_json_serializable(result1.get("entities", {})),
        "intent": str(result1.get("intent", "")),
        "confidence": result1.get("confidence", 0.0),
        "needs_clarification": result1.get("needs_clarification", False),
        "clarification_question": result1.get("clarification_question")
    }

    # Add clarification candidates
    if result1.get("needs_clarification") and result1.get("entities"):
        if result1["entities"].get("players"):
            metadata["clarification_candidates"] = result1["entities"]["players"]

    ConversationService.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content=result1.get('natural_language_summary'),
        metadata=metadata
    )

    print(f"\n✓ Saved clarification to conversation with candidates: {metadata.get('clarification_candidates')}")

    # Step 2: User responds with "Josh please"
    print("\n" + "=" * 80)
    print("STEP 2: User responds 'Josh please'")
    print("=" * 80)

    # Get conversation history (simulating websocket behavior)
    # First save the user's message
    ConversationService.add_message(
        conversation_id=conversation_id,
        role="user",
        content="Josh please"
    )

    # Get conversation history
    conversation_history = ConversationService.get_recent_messages(
        conversation_id=conversation_id,
        limit=10
    )

    print(f"\n✓ Conversation history has {len(conversation_history)} messages")
    print("\nConversation history:")
    for i, msg in enumerate(conversation_history):
        role = msg.get("role")
        content = msg.get("content", "")[:80]
        needs_clarification = msg.get("needs_clarification")
        candidates = msg.get("clarification_candidates")
        print(f"  {i+1}. {role}: {content}...")
        if needs_clarification:
            print(f"      → needs_clarification={needs_clarification}")
            print(f"      → clarification_candidates={candidates}")

    # Run agent with conversation history
    result2 = await agent.run(
        user_query="Josh please",
        conversation_id=conversation_id,
        conversation_history=conversation_history
    )

    print(f"\nIntent: {result2.get('intent')}")
    print(f"Entities: {result2.get('entities')}")
    print(f"Needs Clarification: {result2.get('needs_clarification')}")
    print(f"\nResponse:")
    print(result2.get('natural_language_summary'))

    # Verify the result
    print("\n" + "=" * 80)
    print("VERIFICATION")
    print("=" * 80)

    if result2.get('needs_clarification'):
        print("\n❌ FAILED: Should NOT need clarification after user said 'Josh please'")
        print(f"   Got another clarification: {result2.get('clarification_question')}")
        return False

    resolved_players = result2.get('entities', {}).get('players', [])
    print(f"\nResolved players: {resolved_players}")

    if len(resolved_players) != 1:
        print(f"\n❌ FAILED: Expected exactly 1 player, got {len(resolved_players)}")
        return False

    if resolved_players[0].lower() != "josh daicos":
        print(f"\n❌ FAILED: Expected 'Josh Daicos', got '{resolved_players[0]}'")
        return False

    # Check response mentions Josh Daicos, not all Joshs
    response_lower = result2.get('natural_language_summary', '').lower()
    if "josh battle" in response_lower or "josh begley" in response_lower:
        print("\n❌ FAILED: Response mentions other Josh players (should only be Josh Daicos)")
        print(f"   Response: {result2.get('natural_language_summary')}")
        return False

    print("\n✅ PASSED: Successfully resolved 'Josh please' to 'Josh Daicos'")
    print(f"✅ PASSED: Response correctly answers about Josh Daicos")

    return True


if __name__ == "__main__":
    print("\nRunning end-to-end clarification test...")
    success = asyncio.run(test_daicos_clarification())

    print("\n" + "=" * 80)
    if success:
        print("✅ ALL TESTS PASSED")
        print("=" * 80)
        sys.exit(0)
    else:
        print("❌ TESTS FAILED")
        print("=" * 80)
        sys.exit(1)
