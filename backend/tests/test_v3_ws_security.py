"""1A security checks applied in the v3 WebSocket path (app/agent/v3/ws_stream.py)."""
import os
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from pydantic import ValidationError

from app.agent.v3 import ws_stream
from app.utils.validators import ChatMessageRequest


def _out():
    return SimpleNamespace(chart_spec=None, answer="ok", error=None, data_as_of="2026-09-19",
                           model="gpt-6-luna", memory=[], usage={"input_tokens": 1, "output_tokens": 1},
                           cost_usd=0.0, tool_calls=[], sql=[], llm_calls=[], row_count=0,
                           columns=[], rows=[], latency_s=0.1, ttft_s=None)


def _run(payload, *, owner_ok, allowed=(True, "")):
    events = []
    calls = {}
    with patch.object(ws_stream.ConversationService, "verify_owner", return_value=owner_ok) as verify, \
         patch.object(ws_stream.ConversationService, "get_conversation",
                      return_value={"messages": [{"role": "user", "content": "earlier"}]}) as get_conv, \
         patch.object(ws_stream.ConversationService, "create_owned_conversation",
                      return_value=("new-id", "new-token")) as create, \
         patch.object(ws_stream.ConversationService, "add_message"), \
         patch("app.middleware.usage_tracker.UsageTracker.check_limits", return_value=allowed) as limits, \
         patch.object(ws_stream.llm, "record_usage") as record, \
         patch("app.agent.v3.trace.write_trace"), \
         patch.object(ws_stream, "AgentLoop") as loop:
        loop.return_value.run.side_effect = lambda q, h, **kw: (calls.update(history=h, **kw), _out())[1]
        ws_stream.handle_chat_message_v3(payload, emit=lambda e, p: events.append((e, p)), session_id="sid",
                                         visitor_id="v-signed", ip_address="1.2.3.4",
                                         rate_limit_ok=lambda key: True)
    return events, calls, SimpleNamespace(verify=verify, get_conv=get_conv, create=create,
                                          limits=limits, record=record, loop=loop)


def test_wrong_owner_token_starts_new_conversation():
    payload = ChatMessageRequest(message="hi", conversation_id="abc", owner_token="wrong")
    events, calls, m = _run(payload, owner_ok=False)
    m.get_conv.assert_not_called()  # never read someone else's history
    m.create.assert_called_once()
    assert ("conversation_started", {"conversation_id": "new-id", "owner_token": "new-token"}) in events
    assert calls["history"] == []


def test_owner_token_continues_conversation_and_uses_signed_visitor():
    payload = ChatMessageRequest(message="hi", conversation_id="abc", owner_token="good", spoiler_mode=True)
    events, calls, m = _run(payload, owner_ok=True)
    m.create.assert_not_called()
    assert calls["history"] and calls["spoiler_mode"] is True
    m.limits.assert_called_once_with("v-signed", "1.2.3.4")
    assert m.record.call_args.kwargs["visitor_id"] == "v-signed"
    assert events[0][0] == "received"
    # 2C: a trace event (for the "Show your working" drawer) fires before complete, with no PII.
    trace_events = [p for e, p in events if e == "trace"]
    assert len(trace_events) == 1
    assert set(trace_events[0]) >= {"model", "entities", "tool_calls", "sql", "retries", "tokens", "cost_usd"}
    assert [e for e, _ in events].index("trace") < [e for e, _ in events].index("complete")


def test_budget_refusal_stops_before_any_conversation_work():
    payload = ChatMessageRequest(message="hi")
    events, _, m = _run(payload, owner_ok=False, allowed=(False, "Daily limit reached"))
    m.create.assert_not_called()
    m.loop.assert_not_called()
    assert events[-1] == ("error", {"message": "Daily limit reached"})


def test_spoiler_mode_must_be_bool():
    ChatMessageRequest(message="hi", spoiler_mode=False)
    with pytest.raises(ValidationError):
        ChatMessageRequest(message="hi", spoiler_mode="true")
