"""Check what's in the conversation database."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from app.services.conversation_service import ConversationService
from app.data.database import Session
from app.data.models import Conversation

# Get all conversations
session = Session()
conversations = session.query(Conversation).order_by(Conversation.updated_at.desc()).limit(5).all()

print("=" * 80)
print("RECENT CONVERSATIONS")
print("=" * 80)

for conv in conversations:
    print(f"\nConversation ID: {conv.id}")
    print(f"Created: {conv.created_at}")
    print(f"Updated: {conv.updated_at}")
    print(f"Message count: {len(conv.messages) if conv.messages else 0}")

    if conv.messages:
        print("\nMessages:")
        for i, msg in enumerate(conv.messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")[:80]
            needs_clarification = msg.get("needs_clarification")
            candidates = msg.get("clarification_candidates")

            print(f"  {i+1}. [{role}] {content}")
            if needs_clarification:
                print(f"      → needs_clarification=True")
                print(f"      → candidates={candidates}")

    print("-" * 80)

session.close()
