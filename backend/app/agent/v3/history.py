"""
Conversation memory for v3. Each assistant message stores its tool calls and
a compact view of their results in metadata (`tool_calls`). When the
conversation continues, those are rendered back into the assistant turn, so
follow-ups and corrections ("no, I meant kicks") see exactly what was asked
and returned, with no bespoke correction plumbing.
"""
import json
from typing import Any, Dict, List

MAX_TURNS = 6          # user+assistant pairs fed back
MAX_ROWS_PER_CALL = 5  # rows kept per tool call in stored history


def compact_calls(tool_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Trace-level tool calls -> what we persist in conversation metadata."""
    out = []
    for c in tool_calls:
        if c["name"] == "make_chart":
            continue
        res = c.get("output") or {}
        out.append({
            "name": c["name"],
            "args": c.get("args") or {},
            "row_count": res.get("row_count"),
            "rows": (res.get("rows") or [])[:MAX_ROWS_PER_CALL],
            "why_empty": res.get("why_empty"),
            "error": res.get("error"),
        })
    return out


def _render_calls(calls: List[Dict[str, Any]]) -> str:
    lines = []
    for c in calls:
        args = {k: v for k, v in (c.get("args") or {}).items() if v not in (None, [], "")}
        detail = c.get("why_empty") or c.get("error")
        if not detail:
            detail = f"{c.get('row_count')} rows, first: {json.dumps(c.get('rows') or [], default=str)}"
        lines.append(f"- {c['name']}({json.dumps(args, default=str)}) -> {detail}")
    return "\n".join(lines)


def to_messages(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Stored conversation messages -> neutral llm messages (oldest first)."""
    msgs: List[Dict[str, Any]] = []
    for m in history:
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role == "user" and content:
            msgs.append({"role": "user", "content": content})
        elif role == "assistant":
            calls = m.get("tool_calls") or (m.get("metadata") or {}).get("tool_calls") or []
            text = content
            if calls:
                text = f"[Tool calls I made for this answer]\n{_render_calls(calls)}\n[My answer]\n{content}"
            if text:
                msgs.append({"role": "assistant", "content": text})
    # Keep whole recent turns, starting on a user message.
    msgs = msgs[-MAX_TURNS * 2:]
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs
