"""
Per-turn trace rows in chat_traces (scripts/db/1e_chat_traces.sql). Written
through the app DB session, not the read-only agent role. Never raises.
"""
import json
import logging
from typing import Optional

from sqlalchemy import text

from app.agent.v3.loop import TurnOutput
from app.data.database import Session

logger = logging.getLogger(__name__)


def _slim_calls(out: TurnOutput):
    return [{"name": c["name"], "args": c["args"], "latency_s": c["latency_s"], "error": c["error"],
             "row_count": c.get("row_count"), "why_empty": (c.get("output") or {}).get("why_empty")}
            for c in out.tool_calls]


def _entities_from_calls(tool_calls):
    """Matched players/teams, from every resolve_entities call this turn (2C "Show your working")."""
    ents = []
    for c in tool_calls:
        if c["name"] != "resolve_entities":
            continue
        for r in (c.get("output") or {}).get("rows") or []:
            ents.append({"query": r.get("query"), "kind": r.get("kind"), "name": r.get("name"), "id": r.get("id")})
    return ents


def build_trace_payload(out: TurnOutput) -> dict:
    """"Show your working" drawer data: entities, tool calls (with args and SQL),
    row counts, model round-trips, tokens, cost, latency, data freshness. Built
    only from this turn's own TurnOutput -- no secrets, no other users' data."""
    return {
        "model": out.model,
        "entities": _entities_from_calls(out.tool_calls),
        "tool_calls": [
            {"name": c["name"], "args": c.get("args") or {}, "sql": c.get("sql") or [],
             "row_count": c.get("row_count"), "latency_s": c["latency_s"], "error": c.get("error")}
            for c in out.tool_calls
        ],
        "sql": out.sql,
        "row_count": out.row_count,
        # Model round-trips beyond the first: every extra one re-read tool results before answering.
        "retries": max(len(out.llm_calls) - 1, 0),
        "tokens": out.usage,
        "cost_usd": out.cost_usd,
        "latency_s": out.latency_s,
        "ttft_s": out.ttft_s,
        "data_as_of": out.data_as_of,
        "error": out.error,
    }


def write_trace(out: TurnOutput, *, question: str, conversation_id: Optional[str] = None,
                visitor_id: Optional[str] = None) -> None:
    u = out.usage
    session = Session()
    try:
        session.execute(text(
            "INSERT INTO chat_traces (conversation_id, visitor_id, engine, question, answer, model, tool_calls, sql, "
            "llm_calls, latency_ms, ttft_ms, input_tokens, cached_input_tokens, output_tokens, reasoning_tokens, "
            "cost_usd, has_chart, error) VALUES (CAST(:cid AS uuid), :vid, 'v3', :q, :a, :model, CAST(:tools AS jsonb), "
            "CAST(:sql AS jsonb), CAST(:llm AS jsonb), :lat, :ttft, :in_t, :cached, :out_t, :reason, :cost, :chart, :err)"),
            {"cid": conversation_id, "vid": visitor_id, "q": question, "a": out.answer, "model": out.model,
             "tools": json.dumps(_slim_calls(out), default=str), "sql": json.dumps(out.sql),
             "llm": json.dumps(out.llm_calls, default=str), "lat": int(out.latency_s * 1000),
             "ttft": int(out.ttft_s * 1000) if out.ttft_s is not None else None,
             "in_t": u.get("input_tokens", 0), "cached": u.get("cached_input_tokens", 0),
             "out_t": u.get("output_tokens", 0), "reason": u.get("reasoning_tokens", 0),
             "cost": out.cost_usd, "chart": out.chart_spec is not None, "err": out.error})
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"chat_traces insert failed: {e}")
    finally:
        session.close()
