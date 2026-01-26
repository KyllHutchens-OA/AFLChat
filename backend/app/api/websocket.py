"""
AFL Analytics Agent - WebSocket Handlers

Handles both AFL chat and Resume chat via WebSocket.
"""
from app import socketio
from app.services.conversation_service import ConversationService
from app.utils.json_serialization import make_json_serializable
import logging
import asyncio

logger = logging.getLogger(__name__)


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    logger.info("Client connected")


@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection."""
    logger.info("Client disconnected")


@socketio.on('chat_message')
def handle_chat_message(data):
    """
    Handle incoming chat messages via WebSocket.

    Expected data:
        {
            "message": "user query",
            "conversation_id": "uuid" (optional)
        }
    """
    logger.info(f"Received message: {data}")

    try:
        user_query = data.get('message')
        conversation_id = data.get('conversation_id')

        if not user_query:
            socketio.emit('error', {'message': 'No message provided'})
            return

        # Import agent
        from app.agent import agent
        import asyncio

        # Create or load conversation
        if not conversation_id:
            conversation_id = ConversationService.create_conversation()
            socketio.emit('conversation_started', {'conversation_id': conversation_id})
            logger.info(f"Created new conversation: {conversation_id}")
        else:
            logger.info(f"Continuing conversation: {conversation_id}")

        # Save user message
        ConversationService.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_query
        )

        # Initial progress update
        socketio.emit('thinking', {'step': '🔍 Received your question...', 'current_step': 'received'})

        # Get conversation history for context
        conversation_history = ConversationService.get_recent_messages(
            conversation_id=conversation_id,
            limit=10  # Last 10 messages (5 exchanges)
        )

        # Run the async agent in a synchronous context
        logger.info(f"Running agent for query: {user_query}")
        final_state = asyncio.run(agent.run(
            user_query=user_query,
            conversation_id=conversation_id,
            socketio_emit=socketio.emit,  # Pass emit callback for real-time updates
            conversation_history=conversation_history
        ))
        logger.info(f"Agent completed, final state keys: {final_state.keys()}")

        # Send visualization if available
        if final_state.get('visualization_spec'):
            socketio.emit('visualization', {
                'spec': final_state['visualization_spec']
            })

        # Send response
        response_text = ""
        if final_state.get('natural_language_summary'):
            response_text = final_state['natural_language_summary']
            socketio.emit('response', {
                'text': response_text,
                'confidence': final_state.get('confidence', 0.0),
                'sources': final_state.get('sources', [])
            })
        else:
            response_text = 'I was unable to process your query.'
            socketio.emit('response', {
                'text': response_text,
                'confidence': 0.0
            })

        # Save assistant response to conversation
        # Sanitize metadata to ensure JSON serializability (remove Timestamp objects, etc.)
        logger.info(f"Preparing to save assistant response to conversation {conversation_id}")
        metadata = {
            "entities": make_json_serializable(final_state.get("entities", {})),
            "intent": str(final_state.get("intent", "")),
            "confidence": final_state.get("confidence", 0.0),
            "needs_clarification": final_state.get("needs_clarification", False),
            "clarification_question": final_state.get("clarification_question")
        }

        # If this was a clarification, include the candidate options for easy retrieval
        if final_state.get("needs_clarification") and final_state.get("entities"):
            # The entities in a clarification contain all the candidates
            if final_state["entities"].get("players"):
                metadata["clarification_candidates"] = final_state["entities"]["players"]
                logger.info(f"Added clarification_candidates (players): {final_state['entities']['players']}")
            elif final_state["entities"].get("teams"):
                metadata["clarification_candidates"] = final_state["entities"]["teams"]
                logger.info(f"Added clarification_candidates (teams): {final_state['entities']['teams']}")

        logger.info(f"Saving assistant message with metadata: needs_clarification={metadata['needs_clarification']}")
        success = ConversationService.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            metadata=metadata
        )
        if success:
            logger.info(f"Successfully saved assistant response to conversation {conversation_id}")
        else:
            logger.error(f"Failed to save assistant response to conversation {conversation_id}")

        # Send completion
        socketio.emit('complete', {'conversation_id': conversation_id})

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        socketio.emit('error', {'message': f'Error: {str(e)}'})


@socketio.on('resume_message')
def handle_resume_message(data):
    """
    Handle incoming resume chat messages via WebSocket.

    Expected data:
        {
            "message": "user query about resume",
            "conversation_id": "uuid" (optional)
        }
    """
    logger.info(f"Received resume message: {data}")

    try:
        user_query = data.get('message')
        conversation_id = data.get('conversation_id')

        if not user_query:
            socketio.emit('resume_error', {'message': 'No message provided'})
            return

        # Import resume agent
        from app.resume.agent import resume_agent

        # Create or load conversation (reuse same conversation service)
        if not conversation_id:
            conversation_id = ConversationService.create_conversation()
            socketio.emit('resume_conversation_started', {'conversation_id': conversation_id})
            logger.info(f"Created new resume conversation: {conversation_id}")
        else:
            logger.info(f"Continuing resume conversation: {conversation_id}")

        # Save user message
        ConversationService.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_query
        )

        # Initial progress update
        socketio.emit('resume_thinking', {'step': 'Received your question...', 'current_step': 'received'})

        # Get conversation history for context
        conversation_history = ConversationService.get_recent_messages(
            conversation_id=conversation_id,
            limit=10
        )

        # Run the resume agent
        logger.info(f"Running resume agent for query: {user_query}")
        final_state = asyncio.run(resume_agent.run(
            user_query=user_query,
            conversation_id=conversation_id,
            socketio_emit=socketio.emit,
            conversation_history=conversation_history
        ))
        logger.info(f"Resume agent completed")

        # Send response
        response_text = final_state.get('natural_language_response', 'I was unable to process your query.')
        socketio.emit('resume_response', {
            'text': response_text,
            'confidence': final_state.get('confidence', 0.0)
        })

        # Save assistant response to conversation
        ConversationService.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            metadata={
                "intent": str(final_state.get("intent", "")),
                "confidence": final_state.get("confidence", 0.0)
            }
        )

        # Send completion
        socketio.emit('resume_complete', {'conversation_id': conversation_id})

    except Exception as e:
        logger.error(f"Error processing resume message: {e}")
        import traceback
        traceback.print_exc()
        socketio.emit('resume_error', {'message': f'Error: {str(e)}'})
