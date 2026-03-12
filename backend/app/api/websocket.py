"""
AFL Analytics Agent - WebSocket Handlers
"""
from app import socketio
from app.services.conversation_service import ConversationService
from app.utils.json_serialization import make_json_serializable
from app.middleware.usage_tracker import UsageTracker
from collections import defaultdict
from datetime import datetime, timedelta
import logging
import asyncio

logger = logging.getLogger(__name__)

# In-memory WebSocket rate limiter (10 messages/minute per IP)
_ws_rate_limit: dict = defaultdict(list)
WS_RATE_LIMIT = 10  # messages per minute


def _check_ws_rate_limit(ip: str) -> bool:
    """Return True if request is allowed, False if rate limit exceeded."""
    now = datetime.utcnow()
    cutoff = now - timedelta(minutes=1)
    _ws_rate_limit[ip] = [t for t in _ws_rate_limit[ip] if t > cutoff]
    if len(_ws_rate_limit[ip]) >= WS_RATE_LIMIT:
        return False
    _ws_rate_limit[ip].append(now)
    return True


@socketio.on('connect')
def handle_connect():
    """Handle client connection."""
    from flask import request
    session_id = request.sid
    logger.info(f"Client connected - Session ID: {session_id}")


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
    from flask import request
    session_id = request.sid
    logger.info(f"Received message from session {session_id}: {data}")

    try:
        user_query = data.get('message')
        conversation_id = data.get('conversation_id')
        visitor_id = data.get('visitor_id') or session_id
        source = data.get('source')  # 'aflagent' from standalone app, or None

        # Get client IP
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        if ip_address:
            ip_address = ip_address.split(',')[0].strip()

        # Emit function - send only to the requesting client using their session ID
        def session_emit(event, data):
            """Emit to the requesting client only"""
            socketio.emit(event, data, room=session_id)

        if not user_query:
            session_emit('error', {'message': 'No message provided'})
            return

        # WebSocket rate limit check (10/min per IP)
        if not _check_ws_rate_limit(ip_address or session_id):
            logger.warning(f"WebSocket rate limit exceeded for IP {ip_address}")
            session_emit('error', {'message': 'Rate limit exceeded. Please wait a moment before sending another message.'})
            return

        # Daily usage limit check
        allowed, error_msg = UsageTracker.check_limits(visitor_id, ip_address or '')
        if not allowed:
            logger.warning(f"Usage limit exceeded for visitor {visitor_id[:8]}...")
            session_emit('error', {'message': error_msg})
            return

        # Import agent
        from app.agent import agent
        import asyncio

        # Create or load conversation
        chat_type = source if source in ('afl', 'aflagent') else 'afl'
        if not conversation_id:
            conversation_id = ConversationService.create_conversation(chat_type=chat_type)
            session_emit('conversation_started', {'conversation_id': conversation_id})
            logger.info(f"Created new {chat_type} conversation: {conversation_id}")
        else:
            logger.info(f"Continuing conversation: {conversation_id}")

        # Save user message
        ConversationService.add_message(
            conversation_id=conversation_id,
            role="user",
            content=user_query
        )

        # Initial progress update
        session_emit('thinking', {'step': 'Received your question...', 'current_step': 'received'})

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
            socketio_emit=session_emit,  # Pass session-specific emit
            conversation_history=conversation_history
        ))
        logger.info(f"Agent completed, final state keys: {final_state.keys()}")

        # Track API usage for cost control
        UsageTracker.track_usage(
            visitor_id=visitor_id,
            ip_address=ip_address or '',
            model="gpt-5-nano",
            input_tokens=500,   # Per-request estimate (2 OpenAI calls per query)
            output_tokens=200,
            endpoint="afl_chat"
        )

        # Send visualization if available
        chart_sent = False
        if final_state.get('visualization_spec'):
            logger.info("Emitting 'visualization' event to frontend")
            try:
                import json
                # Ensure visualization spec is JSON-serializable (convert numpy types, etc.)
                viz_spec = make_json_serializable(final_state['visualization_spec'])
                logger.info(f"Visualization spec type: {type(viz_spec)}")
                logger.info(f"Visualization spec keys: {viz_spec.keys() if isinstance(viz_spec, dict) else 'N/A'}")

                viz_data = {'spec': viz_spec}
                # Test serialization
                serialized = json.dumps(viz_data, ensure_ascii=True)
                logger.info(f"Serialized viz length: {len(serialized)} bytes")

                session_emit('visualization', viz_data)
                logger.info("Successfully emitted 'visualization' event")
                chart_sent = True
            except Exception as e:
                logger.error(f"Error with visualization: {e}")
                logger.error(f"Visualization spec preview: {str(final_state['visualization_spec'])[:200]}")
                # Skip visualization if it can't be serialized
                chart_sent = False

        # Send response
        response_text = ""
        logger.info(f"WebSocket: Checking final_state for response - errors={final_state.get('errors')}, execution_error={final_state.get('execution_error')}")
        if final_state.get('natural_language_summary'):
            response_text = final_state['natural_language_summary']
            logger.info(f"Emitting 'response' event with text length={len(response_text)}")
            logger.info(f"Response preview: {response_text[:200]}...")

            # Ensure response text is clean and serializable
            try:
                # Remove any control characters that might break WebSocket frames
                import re
                clean_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', response_text)

                response_data = {
                    'text': clean_text,
                    'confidence': float(final_state.get('confidence', 0.0)),
                    'sources': final_state.get('sources', []) or []
                }

                # Test JSON serialization before emitting
                import json
                json.dumps(response_data)

                session_emit('response', response_data)
                logger.info("Successfully emitted 'response' event")
            except Exception as e:
                logger.error(f"Error serializing response: {e}")
                logger.error(f"Response text preview: {response_text[:200]}")
                session_emit('response', {
                    'text': 'I generated a response but encountered an encoding error. Please try rephrasing your question.',
                    'confidence': 0.0,
                    'sources': []
                })
        else:
            response_text = 'I was unable to process your query.'
            logger.info("Emitting 'response' event with error text")
            session_emit('response', {
                'text': response_text,
                'confidence': 0.0
            })

        # Send completion IMMEDIATELY (before slow database save)
        logger.info(f"Emitting 'complete' event with conversation_id={conversation_id}")
        session_emit('complete', {'conversation_id': conversation_id})

        # Save assistant response to conversation (in background, after sending complete)
        # Sanitize metadata to ensure JSON serializability (remove Timestamp objects, etc.)
        logger.info(f"Preparing to save assistant response to conversation {conversation_id}")
        metadata = {
            "entities": make_json_serializable(final_state.get("entities", {})),
            "intent": str(final_state.get("intent", "")),
            "confidence": final_state.get("confidence", 0.0),
            "needs_clarification": final_state.get("needs_clarification", False),
            "clarification_question": final_state.get("clarification_question"),
            "sources": final_state.get("sources", [])
        }

        # Store visualization spec if chart was generated (for history restoration)
        if chart_sent and final_state.get("visualization_spec"):
            metadata["visualization"] = make_json_serializable(final_state["visualization_spec"])

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

    except Exception as e:
        logger.error(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()
        # session_emit might not be defined if error happens early
        try:
            session_emit('error', {'message': f'Error: {str(e)}'})
        except:
            socketio.emit('error', {'message': f'Error: {str(e)}'}, room=session_id)


# ========== LIVE GAMES WEBSOCKET HANDLERS ==========

@socketio.on('subscribe_live_game')
def handle_subscribe_live_game(data):
    """
    Subscribe client to live game updates.

    Expected data:
        {
            "game_id": 123  // LiveGame.id
        }
    """
    from flask import request
    from flask_socketio import join_room

    session_id = request.sid
    game_id = data.get('game_id')

    if not game_id:
        socketio.emit('error', {'message': 'No game_id provided'}, room=session_id)
        return

    # Join room for this specific game
    room = f"live_game_{game_id}"
    join_room(room)

    logger.info(f"Client {session_id} subscribed to live game {game_id}")
    socketio.emit('subscribed', {'game_id': game_id}, room=session_id)


@socketio.on('unsubscribe_live_game')
def handle_unsubscribe_live_game(data):
    """Unsubscribe from live game updates."""
    from flask import request
    from flask_socketio import leave_room

    session_id = request.sid
    game_id = data.get('game_id')

    if game_id:
        room = f"live_game_{game_id}"
        leave_room(room)
        logger.info(f"Client {session_id} unsubscribed from live game {game_id}")
