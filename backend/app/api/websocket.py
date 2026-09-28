"""
AFL Analytics Agent - WebSocket Handlers
"""
from app import socketio
from app.services.conversation_service import ConversationService
from app.utils.json_serialization import make_json_serializable
from app.utils.validators import ChatMessageRequest
from app.middleware.usage_tracker import UsageTracker
from app.middleware.visitor_identity import issue_visitor_token, verify_visitor_token
from collections import defaultdict
from datetime import datetime, timedelta
from pydantic import ValidationError
import logging
import asyncio
import json
import os
import re

logger = logging.getLogger(__name__)

# In-memory WebSocket rate limiter (10 messages/minute per IP)
_ws_rate_limit: dict = defaultdict(list)
WS_RATE_LIMIT = 10  # messages per minute

# sid -> server-issued visitor id (single worker, see Procfile)
_sid_visitors: dict = {}

# v2 (LangGraph pipeline) is the default; v3 is the tool-calling loop in app/agent/v3.
AGENT_ENGINE = os.getenv("AGENT_ENGINE", "v2").lower()
if AGENT_ENGINE == "v3":
    from app.agent.v3.tools.entities import warm_async
    warm_async()


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
def handle_connect(auth=None):
    """
    Handle client connection. Resolves the visitor from the signed token in the
    connect `auth` payload, or issues a new one (sent back as 'visitor_token').
    """
    from flask import request
    from flask_socketio import emit
    session_id = request.sid

    token = auth.get('visitor_token') if isinstance(auth, dict) else None
    visitor_id = verify_visitor_token(token)
    if not visitor_id:
        visitor_id, token = issue_visitor_token()
        emit('visitor_token', {'token': token})
    _sid_visitors[session_id] = visitor_id
    logger.info(f"Client connected - Session ID: {session_id}")


@socketio.on('disconnect')
def handle_disconnect(*_args):
    """Handle client disconnection."""
    from flask import request
    _sid_visitors.pop(request.sid, None)
    logger.info("Client disconnected")


@socketio.on('chat_message')
def handle_chat_message(data):
    """
    Handle incoming chat messages via WebSocket.

    Expected data (validated by ChatMessageRequest; anything else is ignored):
        {
            "message": "user query" (1-2000 chars),
            "conversation_id": "uuid" (optional),
            "owner_token": "token from conversation_started" (required to continue a conversation),
            "source": "aflagent" (optional),
            "spoiler_mode": true/false (optional, v3 only)
        }
    """
    from flask import request
    session_id = request.sid

    # Emit function - send only to the requesting client using their session ID
    def session_emit(event, data):
        """Emit to the requesting client only"""
        socketio.emit(event, data, room=session_id)

    try:
        try:
            if not isinstance(data, dict):
                raise TypeError("payload must be an object")
            payload = ChatMessageRequest(**data)
        except (ValidationError, TypeError) as e:
            logger.info(f"Rejected chat_message from session {session_id}: invalid payload ({type(e).__name__})")
            session_emit('error', {'message': 'Invalid message. Messages must be text of at most 2000 characters.'})
            return

        user_query = payload.message
        conversation_id = payload.conversation_id
        ip_address = request.remote_addr or ''  # ProxyFix resolves the trusted proxy hop
        visitor_id = _sid_visitors.get(session_id)
        if not visitor_id:
            # Connected before identity was recorded (should not happen); quota on a per-session id
            visitor_id = f"sid-{session_id}"

        logger.info(
            f"Received message from session {session_id}: length={len(user_query)}, "
            f"conversation_id={conversation_id}"
        )
        logger.debug(f"Message content: {user_query}")

        if AGENT_ENGINE == "v3":
            from app.agent.v3.ws_stream import handle_chat_message_v3
            handle_chat_message_v3(payload, emit=session_emit, session_id=session_id,
                                   visitor_id=visitor_id, ip_address=ip_address,
                                   rate_limit_ok=_check_ws_rate_limit)
            return

        # WebSocket rate limit check (10/min per IP)
        if not _check_ws_rate_limit(ip_address or session_id):
            logger.warning(f"WebSocket rate limit exceeded for session {session_id}")
            session_emit('error', {'message': 'Rate limit exceeded. Please wait a moment before sending another message.'})
            return

        # Daily usage limit check (per visitor, per IP, global; fails closed)
        allowed, error_msg = UsageTracker.check_limits(visitor_id, ip_address)
        if not allowed:
            logger.warning(f"Usage limit exceeded for visitor {visitor_id[:10]}...")
            session_emit('error', {'message': error_msg})
            return

        # Import agent
        from app.agent import agent

        # Continue only a conversation this client owns; otherwise start a new one
        chat_type = payload.source if payload.source in ('afl', 'aflagent') else 'afl'
        if not conversation_id or not ConversationService.verify_owner(conversation_id, payload.owner_token):
            conversation_id, owner_token = ConversationService.create_owned_conversation(chat_type=chat_type)
            # The only time the owner token leaves the server
            session_emit('conversation_started', {'conversation_id': conversation_id, 'owner_token': owner_token})
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
        logger.info(f"Running agent for conversation {conversation_id}")
        final_state = asyncio.run(agent.run(
            user_query=user_query,
            conversation_id=conversation_id,
            socketio_emit=session_emit,  # Pass session-specific emit
            conversation_history=conversation_history
        ))
        logger.info("Agent completed")

        # Track API usage for cost control: one row per model actually called,
        # with real token counts accumulated across every OpenAI call in this turn.
        UsageTracker.track_request(
            visitor_id=visitor_id,
            ip_address=ip_address,
            token_usage=final_state.get("token_usage") or {},
            endpoint="afl_chat",
        )

        # Send visualization if available
        chart_sent = False
        if final_state.get('visualization_spec'):
            try:
                # Ensure visualization spec is JSON-serializable (convert numpy types, etc.)
                viz_spec = make_json_serializable(final_state['visualization_spec'])
                viz_data = {'spec': viz_spec}
                serialized = json.dumps(viz_data, ensure_ascii=True)
                logger.info(f"Emitting 'visualization' event ({len(serialized)} bytes)")
                session_emit('visualization', viz_data)
                chart_sent = True
            except Exception as e:
                logger.error(f"Error with visualization: {e}")
                # Skip visualization if it can't be serialized
                chart_sent = False

        # Send response
        response_text = ""
        if final_state.get('execution_error') or final_state.get('errors'):
            logger.info("WebSocket: final_state carries execution errors")
        if final_state.get('natural_language_summary') not in (None, ''):
            response_text = final_state['natural_language_summary']
            logger.info(f"Emitting 'response' event with text length={len(response_text)}")
            logger.debug(f"Response text: {response_text}")

            # Ensure response text is clean and serializable
            try:
                # Remove any control characters that might break WebSocket frames
                clean_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', response_text)

                response_data = {
                    'text': clean_text,
                    'confidence': float(final_state.get('confidence', 0.0)),
                    'sources': final_state.get('sources', []) or []
                }

                # Test JSON serialization before emitting
                json.dumps(response_data)

                session_emit('response', response_data)
            except Exception as e:
                logger.error(f"Error serializing response: {e}")
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
        session_emit('complete', {'conversation_id': conversation_id})

        # Save assistant response to conversation (after sending complete)
        # Enrich entities with team/player names from query results so follow-up
        # questions ("which teams are these?", "show me their stats") have context
        entities = make_json_serializable(final_state.get("entities", {}))
        query_results = final_state.get("query_results")
        try:
            if query_results is not None and hasattr(query_results, 'columns'):
                if not entities.get("teams"):
                    for col in ("name", "team", "team_name"):
                        if col in query_results.columns:
                            result_teams = query_results[col].dropna().unique().tolist()
                            if result_teams and len(result_teams) <= 20:
                                entities["teams"] = [str(t) for t in result_teams]
                                logger.info(f"Enriched entities with {len(result_teams)} teams from results")
                            break
                if not entities.get("players"):
                    for col in ("player", "player_name"):
                        if col in query_results.columns:
                            result_players = query_results[col].dropna().unique().tolist()
                            if result_players and len(result_players) <= 20:
                                entities["players"] = [str(p) for p in result_players]
                                logger.info(f"Enriched entities with {len(result_players)} players from results")
                            break
        except Exception as e:
            logger.warning(f"Entity enrichment from results failed: {e}")

        # Persist the final SQL + row count alongside this turn so a future
        # correction turn (turn_type == "correction") can load prior_sql /
        # prior_row_count / prior_answer (see app/agent/classify_resolve.py).
        # Server-side only: the public conversation GET strips these fields.
        row_count = None
        if query_results is not None:
            try:
                row_count = len(query_results)
            except TypeError:
                row_count = None

        metadata = {
            "entities": entities,
            "intent": str(final_state.get("intent", "")),
            "confidence": final_state.get("confidence", 0.0),
            "needs_clarification": final_state.get("needs_clarification", False),
            "clarification_question": final_state.get("clarification_question"),
            "sources": final_state.get("sources", []),
            "sql": final_state.get("sql_query"),
            "row_count": row_count,
        }

        # Store visualization spec if chart was generated (for history restoration)
        if chart_sent and final_state.get("visualization_spec"):
            metadata["visualization"] = make_json_serializable(final_state["visualization_spec"])

        # If this was a clarification, include the candidate options for easy retrieval
        if final_state.get("needs_clarification") and final_state.get("entities"):
            # The entities in a clarification contain all the candidates
            if final_state["entities"].get("players"):
                metadata["clarification_candidates"] = final_state["entities"]["players"]
            elif final_state["entities"].get("teams"):
                metadata["clarification_candidates"] = final_state["entities"]["teams"]

        success = ConversationService.add_message(
            conversation_id=conversation_id,
            role="assistant",
            content=response_text,
            metadata=metadata
        )
        if not success:
            logger.error(f"Failed to save assistant response to conversation {conversation_id}")

    except Exception as e:
        logger.error(f"Error processing message: {e}", exc_info=True)
        # Send a generic error message — never expose raw exception details to users
        generic_error = "Something went wrong processing your request. Please try again, or rephrase your question."
        try:
            session_emit('error', {'message': generic_error})
        except Exception:
            socketio.emit('error', {'message': generic_error}, room=session_id)


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
