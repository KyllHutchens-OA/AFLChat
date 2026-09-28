"""
WebSocket chat handler for AGENT_ENGINE=v3 (called from api/websocket.py).

Event order: received (before any DB work) -> thinking* (one per real tool
call) -> response_delta* (streamed answer) -> visualization? -> response
(full text, v2-compatible) -> complete. `response` and `complete` carry
`data_as_of` (latest match with player stats). Persistence, usage tracking
and the trace row happen after `complete`.
"""
import logging
import re
import time
from typing import Any, Callable, Dict, Optional

from app.agent.v3 import llm
from app.agent.v3.loop import AgentLoop
from app.services.conversation_service import ConversationService
from app.utils.json_serialization import make_json_serializable

logger = logging.getLogger(__name__)

_CONTROL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
GENERIC_ERROR = "Something went wrong processing your request. Please try again, or rephrase your question."


class _DeltaBuffer:
    """Coalesces token deltas into ~50ms chunks so a long answer is tens of
    socket events, not hundreds. Other events pass through (after a flush)."""

    def __init__(self, emit, interval_s: float = 0.05):
        self._emit, self._interval, self._buf, self._last = emit, interval_s, [], 0.0

    def emit(self, event: str, payload: Dict[str, Any]) -> None:
        if event != "response_delta":
            self.flush()
            self._emit(event, payload)
            return
        self._buf.append(payload["delta"])
        if time.monotonic() - self._last >= self._interval:
            self.flush()

    def flush(self) -> None:
        if self._buf:
            self._emit("response_delta", {"delta": "".join(self._buf)})
            self._buf = []
        self._last = time.monotonic()


def handle_chat_message_v3(payload: Any, *, emit: Callable[[str, Dict[str, Any]], None],
                           session_id: str, visitor_id: str, ip_address: str,
                           rate_limit_ok: Callable[[str], bool]) -> None:
    """`payload` is the validated ChatMessageRequest; `visitor_id` comes from the
    server-signed visitor token and `ip_address` from ProxyFix (api/websocket.py)."""
    from app.middleware.usage_tracker import UsageTracker

    user_query = payload.message
    emit("received", {"step": "Received your question...", "current_step": "received"})

    if not rate_limit_ok(ip_address or session_id):
        emit("error", {"message": "Rate limit exceeded. Please wait a moment before sending another message."})
        return
    allowed, error_msg = UsageTracker.check_limits(visitor_id, ip_address or "")
    if not allowed:
        logger.warning(f"Usage limit exceeded for visitor {visitor_id[:10]}...")
        emit("error", {"message": error_msg})
        return

    # Continue only a conversation this client owns (owner token); otherwise start a new one.
    conversation_id: Optional[str] = payload.conversation_id
    history = []
    if conversation_id and ConversationService.verify_owner(conversation_id, payload.owner_token):
        conv = ConversationService.get_conversation(conversation_id)
        history = (conv or {}).get("messages") or []
        if not conv:
            conversation_id = None
    else:
        conversation_id = None
    if not conversation_id:
        source = payload.source
        conversation_id, owner_token = ConversationService.create_owned_conversation(
            chat_type=source if source in ("afl", "aflagent") else "afl")
        # The only time the owner token leaves the server
        emit("conversation_started", {"conversation_id": conversation_id, "owner_token": owner_token})
    ConversationService.add_message(conversation_id=conversation_id, role="user", content=user_query)

    stream = _DeltaBuffer(emit)
    out = AgentLoop().run(user_query, history, spoiler_mode=bool(payload.spoiler_mode), emit=stream.emit)
    stream.flush()

    chart = None
    if out.chart_spec:
        chart = make_json_serializable(out.chart_spec)
        emit("visualization", {"spec": chart})
    text = _CONTROL.sub("", out.answer) if not out.error else (out.answer or GENERIC_ERROR)
    emit("response", {"text": text, "confidence": 0.0 if out.error else 1.0, "sources": [],
                      "data_as_of": out.data_as_of})
    emit("complete", {"conversation_id": conversation_id, "data_as_of": out.data_as_of})

    metadata = {"engine": "v3", "model": out.model, "tool_calls": make_json_serializable(out.memory),
                "data_as_of": out.data_as_of}
    if chart:
        metadata["visualization"] = chart
    ConversationService.add_message(conversation_id=conversation_id, role="assistant", content=text, metadata=metadata)
    llm.record_usage(out.model, llm.Usage(**out.usage), out.cost_usd, endpoint="afl_chat_v3",
                     visitor_id=visitor_id, ip_address=ip_address or "")
    from app.agent.v3.trace import write_trace
    write_trace(out, question=user_query, conversation_id=conversation_id, visitor_id=visitor_id)
