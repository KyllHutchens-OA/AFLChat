"""
v2 engine adapter: drives `AFLAnalyticsAgent.run` in-process.

No backend server needed, just DB + OpenAI credentials in backend/.env.
History is synthesized exactly like websocket.py persists it (role/content
plus sql/row_count/entities/needs_clarification metadata, with entities
enriched from result columns), so correction plumbing in classify_resolve
(prior_sql / prior_row_count / prior_answer) behaves as in production.

Safety: by default every connection in the app's SQLAlchemy pool is forced
into read-only transactions, so a prompt-injection case can never mutate
the dev DB even if a destructive statement got past the SQL validator.
"""
import asyncio
import logging
import os
import time
from typing import Any, Dict, List, Optional

from app.agent.eval.models import ToolCall, TurnResult
from app.agent.eval.runner import MAX_ROWS, EngineAdapter

logger = logging.getLogger(__name__)


def _force_read_only(engine) -> None:
    """Make every pooled connection default to READ ONLY transactions."""
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def _set_read_only(dbapi_conn, _record):  # pragma: no cover - trivial
        cur = dbapi_conn.cursor()
        cur.execute("SET default_transaction_read_only = on")
        cur.close()
        # psycopg3 opens a transaction for the SET; end it so the setting sticks.
        dbapi_conn.commit()

    engine.dispose()  # drop connections opened before the hook existed


def _rows_from_frame(df: Any) -> tuple:
    """(columns, capped plain rows, full row count) from a DataFrame."""
    from app.utils.json_serialization import make_json_serializable

    try:
        n = len(df)
        cols = [str(c) for c in df.columns]
        rows = make_json_serializable(df.head(MAX_ROWS).to_dict(orient="records"))
        return cols, rows, n
    except Exception as e:
        logger.warning(f"Could not serialize query_results: {e}")
        return [], [], None


def _enrich_entities(entities: Dict[str, Any], columns: List[str], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Mirror websocket.py's entity enrichment from result columns."""
    entities = dict(entities or {})
    if not entities.get("teams"):
        for col in ("name", "team", "team_name"):
            if col in columns:
                vals = list(dict.fromkeys(str(r[col]) for r in rows if r.get(col) is not None))
                if vals and len(vals) <= 20:
                    entities["teams"] = vals
                break
    if not entities.get("players"):
        for col in ("player", "player_name"):
            if col in columns:
                vals = list(dict.fromkeys(str(r[col]) for r in rows if r.get(col) is not None))
                if vals and len(vals) <= 20:
                    entities["players"] = vals
                break
    return entities


class V2Engine(EngineAdapter):
    """AFLAnalyticsAgent (LangGraph v2 pipeline), one asyncio.run per turn."""

    name = "v2"

    def __init__(self, read_only_db: bool = True, clear_sql_cache: bool = True, **_: Any):
        # Deferred import: pulls in LangGraph, OpenAI client, DB engine.
        from app.agent import agent
        from app.data.database import engine

        self.agent = agent
        self.clear_sql_cache = clear_sql_cache
        if read_only_db:
            _force_read_only(engine)

    def describe(self) -> Dict[str, Any]:
        from app.agent.v3.llm import model_for

        return {"engine": self.name, "model": model_for("AGENT_MODEL")}

    def _clear_caches(self) -> None:
        # Repeats must not be served from the SQL result cache (skews latency).
        from app.utils import cache

        cache._historical_cache.clear()
        cache._live_cache.clear()

    def run_turn(self, question: str, history: List[Dict[str, Any]]) -> TurnResult:
        if self.clear_sql_cache:
            self._clear_caches()
        t0 = time.monotonic()
        error: Optional[str] = None
        state: Dict[str, Any] = {}
        try:
            state = asyncio.run(
                self.agent.run(
                    user_query=question,
                    conversation_id=None,
                    socketio_emit=None,
                    conversation_history=history,
                )
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            logger.error(f"agent.run failed for {question!r}: {error}")
        latency_s = round(time.monotonic() - t0, 3)
        return self._to_turn(question, state, latency_s, error)

    @staticmethod
    def _to_turn(question: str, state: Dict[str, Any], latency_s: float, error: Optional[str]) -> TurnResult:
        from app.utils.json_serialization import make_json_serializable

        chart_spec = state.get("visualization_spec")
        if chart_spec is not None:
            try:
                chart_spec = make_json_serializable(chart_spec)
            except Exception as e:
                logger.warning(f"Chart spec not serializable: {e}")
                chart_spec = None

        columns, rows, row_count = [], [], None
        if state.get("query_results") is not None:
            columns, rows, row_count = _rows_from_frame(state["query_results"])

        # v2 exposes its last failed attempt + the final SQL; that is the
        # closest thing it has to a tool-call trace.
        calls: List[ToolCall] = []
        if state.get("failed_sql"):
            calls.append(ToolCall(name="sql", sql=state["failed_sql"], error=state.get("sql_error")))
        if state.get("sql_query"):
            calls.append(ToolCall(name="sql", sql=state["sql_query"], row_count=row_count,
                                  error=state.get("execution_error")))

        usage = state.get("token_usage") or {}
        agent_errors = state.get("errors") or []
        entities = make_json_serializable(state.get("entities") or {})
        return TurnResult(
            query=question,
            response_text=state.get("natural_language_summary", "") or "",
            latency_s=latency_s,
            chart_spec=chart_spec,
            sql=state.get("sql_query"),
            tool_calls=calls,
            columns=columns,
            rows=rows,
            row_count=row_count,
            error=error or ("; ".join(str(e) for e in agent_errors) or None),
            input_tokens=int(usage.get("input_tokens", 0) or 0),
            output_tokens=int(usage.get("output_tokens", 0) or 0),
            engine_meta={
                "entities": _enrich_entities(entities, columns, rows),
                "intent": str(state.get("intent", "")),
                "turn_type": state.get("turn_type"),
                "needs_clarification": bool(state.get("needs_clarification")),
                "clarification_question": state.get("clarification_question"),
                "sql_attempts": state.get("sql_attempts"),
            },
        )

    def history_messages(self, turn: TurnResult) -> List[Dict[str, Any]]:
        meta = turn.engine_meta
        return [
            {"role": "user", "content": turn.query},
            {
                "role": "assistant",
                "content": turn.response_text,
                "sql": turn.sql,
                "row_count": turn.row_count,
                "entities": meta.get("entities") or {},
                "intent": meta.get("intent"),
                "needs_clarification": meta.get("needs_clarification", False),
                "clarification_question": meta.get("clarification_question"),
            },
        ]
