"""
Conversation Service - Manages conversation history for contextual queries.
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
import logging

from app.data.database import Session
from app.data.models import Conversation

logger = logging.getLogger(__name__)


class ConversationService:
    """
    Service for managing conversation history.

    Stores messages in JSONB format:
    [
        {"role": "user", "content": "...", "timestamp": "..."},
        {"role": "assistant", "content": "...", "entities": {...}, "timestamp": "..."}
    ]
    """

    @classmethod
    def create_conversation(cls, user_id: Optional[str] = None) -> str:
        """
        Create a new conversation.

        Args:
            user_id: Optional user identifier

        Returns:
            conversation_id (UUID string)
        """
        session = Session()
        try:
            conversation = Conversation(
                user_id=user_id,
                messages=[]
            )
            session.add(conversation)
            session.commit()

            conversation_id = str(conversation.id)
            logger.info(f"Created new conversation: {conversation_id}")
            return conversation_id

        except Exception as e:
            session.rollback()
            logger.error(f"Error creating conversation: {e}")
            raise
        finally:
            session.close()

    @classmethod
    def get_conversation(cls, conversation_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve a conversation by ID.

        Args:
            conversation_id: UUID string

        Returns:
            Dict with conversation data or None if not found
        """
        session = Session()
        try:
            conversation = session.query(Conversation).filter(
                Conversation.id == uuid.UUID(conversation_id)
            ).first()

            if not conversation:
                logger.warning(f"Conversation not found: {conversation_id}")
                return None

            return {
                "id": str(conversation.id),
                "user_id": conversation.user_id,
                "messages": conversation.messages,
                "created_at": conversation.created_at.isoformat(),
                "updated_at": conversation.updated_at.isoformat()
            }

        except Exception as e:
            logger.error(f"Error retrieving conversation {conversation_id}: {e}")
            return None
        finally:
            session.close()

    @classmethod
    def add_message(
        cls,
        conversation_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a message to a conversation.

        Args:
            conversation_id: UUID string
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (entities, intent, etc.)

        Returns:
            True if successful
        """
        session = Session()
        try:
            logger.info(f"add_message: Looking up conversation {conversation_id}")
            conversation = session.query(Conversation).filter(
                Conversation.id == uuid.UUID(conversation_id)
            ).first()

            if not conversation:
                logger.error(f"Conversation not found: {conversation_id}")
                return False

            logger.info(f"add_message: Found conversation, current message count = {len(conversation.messages or [])}")

            # Build message
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.utcnow().isoformat()
            }

            # Add metadata if provided
            if metadata:
                message.update(metadata)
                logger.info(f"add_message: Added metadata keys: {list(metadata.keys())}")

            # Append to messages (JSONB array)
            messages = conversation.messages or []
            logger.info(f"add_message: Current messages array length: {len(messages)}")
            messages.append(message)
            logger.info(f"add_message: After append, messages array length: {len(messages)}")

            # CRITICAL: For JSONB columns, SQLAlchemy doesn't auto-detect mutations
            # We must explicitly flag the column as modified
            from sqlalchemy.orm.attributes import flag_modified
            conversation.messages = messages
            flag_modified(conversation, "messages")
            conversation.updated_at = datetime.utcnow()

            logger.info(f"add_message: Flagged 'messages' as modified for SQLAlchemy")

            logger.info(f"add_message: About to commit. Setting conversation.messages to array with {len(messages)} messages")
            session.commit()
            logger.info(f"add_message: Commit successful. Added {role} message to conversation {conversation_id}")

            # Verify the save
            session.refresh(conversation)
            logger.info(f"add_message: After refresh, message count = {len(conversation.messages or [])}")

            return True

        except Exception as e:
            session.rollback()
            logger.error(f"Error adding message to conversation {conversation_id}: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            session.close()

    @classmethod
    def get_recent_messages(
        cls,
        conversation_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Get recent messages from a conversation.

        Args:
            conversation_id: UUID string
            limit: Maximum number of messages to return

        Returns:
            List of message dicts (most recent first)
        """
        conversation = cls.get_conversation(conversation_id)

        if not conversation or not conversation.get("messages"):
            return []

        messages = conversation["messages"]
        return messages[-limit:] if len(messages) > limit else messages

    @classmethod
    def format_context_for_prompt(
        cls,
        conversation_id: Optional[str],
        max_messages: int = 5
    ) -> str:
        """
        Format recent conversation history for inclusion in prompts.

        Args:
            conversation_id: UUID string or None
            max_messages: Maximum number of previous exchanges to include

        Returns:
            Formatted string with conversation context
        """
        if not conversation_id:
            return ""

        messages = cls.get_recent_messages(conversation_id, limit=max_messages * 2)

        if not messages:
            return ""

        # Format as conversation history
        formatted = "## Previous Conversation Context\n\n"
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                formatted += f"**User**: {content}\n\n"
            elif role == "assistant":
                formatted += f"**Assistant**: {content}\n\n"

        formatted += "---\n\n"
        return formatted

    @classmethod
    def get_conversation_summary(cls, conversation_id: str) -> Dict[str, Any]:
        """
        Get a summary of the conversation (message count, entities discussed, etc.).

        Args:
            conversation_id: UUID string

        Returns:
            Dict with summary information
        """
        conversation = cls.get_conversation(conversation_id)

        if not conversation:
            return {"error": "Conversation not found"}

        messages = conversation.get("messages", [])

        # Extract unique entities mentioned
        teams = set()
        players = set()
        seasons = set()

        for msg in messages:
            if msg.get("role") == "assistant":
                entities = msg.get("entities", {})
                teams.update(entities.get("teams", []))
                players.update(entities.get("players", []))
                seasons.update(entities.get("seasons", []))

        return {
            "message_count": len(messages),
            "user_messages": len([m for m in messages if m.get("role") == "user"]),
            "assistant_messages": len([m for m in messages if m.get("role") == "assistant"]),
            "teams_discussed": sorted(list(teams)),
            "players_discussed": sorted(list(players)),
            "seasons_discussed": sorted(list(seasons)),
            "created_at": conversation.get("created_at"),
            "updated_at": conversation.get("updated_at")
        }
