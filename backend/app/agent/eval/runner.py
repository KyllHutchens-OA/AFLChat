"""
Eval runners.

`InProcessRunner` (default) drives `AFLAnalyticsAgent.run` directly — no
backend server needed, just DB + OpenAI credentials in backend/.env. For
multi-turn cases it synthesizes conversation history between turns using the
same message shape `ConversationService`/websocket.py persist (role/content
plus `sql`/`row_count`/`entities` metadata), so correction plumbing in
classify_resolve (`prior_sql` / `prior_row_count` / `prior_answer`) works
exactly as it does in production.

`WsRunner` (--ws) reuses scripts/benchmark_chat.py's socket.io client
machinery against an already-running backend, exercising the full
websocket.py path (rate limits apply: it sleeps between turns).
"""
import asyncio
import importlib.util
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.eval.models import EvalCase, TurnResult

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[4]
BENCHMARK_CHAT_PATH = REPO_ROOT / "scripts" / "benchmark_chat.py"


class InProcessRunner:
    """Drives the agent graph in-process, one asyncio.run per turn."""

    def __init__(self):
        # Deferred import: pulls in LangGraph, OpenAI client, DB engine.
        from app.agent import agent

        self.agent = agent

    def run_case(self, case: EvalCase) -> List[TurnResult]:
        # Copy so a case's preloaded synthetic history is never mutated.
        history: List[Dict[str, Any]] = [dict(m) for m in case.conversation_history]
        turns: List[TurnResult] = []

        for query in case.queries:
            t0 = time.monotonic()
            error: Optional[str] = None
            final_state: Dict[str, Any] = {}
            try:
                final_state = asyncio.run(
                    self.agent.run(
                        user_query=query,
                        conversation_id=None,
                        socketio_emit=None,
                        conversation_history=list(history),
                    )
                )
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                logger.error(f"[{case.id}] agent.run failed for {query!r}: {error}")
            latency_s = round(time.monotonic() - t0, 3)

            turn = self._to_turn_result(query, final_state, latency_s, error)
            turns.append(turn)

            # Synthesize history the way websocket.py persists it, so the
            # next turn's classify_resolve sees prior sql/row_count/answer.
            history.append({"role": "user", "content": query})
            history.append(
                {
                    "role": "assistant",
                    "content": turn.response_text,
                    "sql": turn.sql,
                    "row_count": turn.row_count,
                    "entities": final_state.get("entities") or {},
                }
            )

        return turns

    @staticmethod
    def _to_turn_result(
        query: str,
        final_state: Dict[str, Any],
        latency_s: float,
        error: Optional[str],
    ) -> TurnResult:
        from app.utils.json_serialization import make_json_serializable

        chart_spec = final_state.get("visualization_spec")
        if chart_spec is not None:
            try:
                chart_spec = make_json_serializable(chart_spec)
            except Exception as e:
                logger.warning(f"Chart spec not serializable: {e}")
                chart_spec = None

        row_count: Optional[int] = None
        query_results = final_state.get("query_results")
        if query_results is not None:
            try:
                row_count = len(query_results)
            except TypeError:
                row_count = None

        agent_errors = final_state.get("errors") or []
        if error is None and final_state.get("execution_error"):
            # Not a harness error; record it for visibility but the response
            # text (why-no-data facts etc.) is still what gets scored.
            logger.info(f"execution_error present: {final_state['execution_error']}")

        token_usage = final_state.get("token_usage") or {}

        return TurnResult(
            query=query,
            response_text=final_state.get("natural_language_summary", "") or "",
            latency_s=latency_s,
            chart_spec=chart_spec,
            sql=final_state.get("sql_query"),
            row_count=row_count,
            error=error or ("; ".join(str(e) for e in agent_errors) or None),
            input_tokens=int(token_usage.get("input_tokens", 0) or 0),
            output_tokens=int(token_usage.get("output_tokens", 0) or 0),
        )


class WsRunner:
    """Drives a running backend over WebSocket via scripts/benchmark_chat.py."""

    def __init__(self, url: str = "http://localhost:5001", inter_turn_sleep_s: float = 6.0):
        self.url = url
        self.inter_turn_sleep_s = inter_turn_sleep_s
        self._bench = self._load_benchmark_module()
        self.capture = self._bench.TurnCapture()
        self.sio = self._bench.build_client(self.capture)
        self._connected = False

    @staticmethod
    def _load_benchmark_module():
        spec = importlib.util.spec_from_file_location("benchmark_chat", BENCHMARK_CHAT_PATH)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def _ensure_connected(self):
        if not self._connected:
            self.sio.connect(self.url, wait_timeout=15)
            self._connected = True

    def close(self):
        if self._connected:
            self.sio.disconnect()
            self._connected = False

    def run_case(self, case: EvalCase) -> List[TurnResult]:
        if case.conversation_history:
            logger.warning(
                f"[{case.id}] preloaded conversation_history is not supported in "
                "--ws mode (server manages history); running without it."
            )
        self._ensure_connected()
        turns: List[TurnResult] = []
        conversation_id = None
        for query in case.queries:
            raw, conversation_id = self._bench.run_turn(
                self.sio, self.capture, query, conversation_id
            )
            events = raw["events"]
            response = events.get("response") or {}
            visualization = events.get("visualization") or {}
            error_event = events.get("error") or {}
            error = None
            if raw["timed_out"]:
                error = "timeout waiting for complete event"
            elif error_event:
                error = str(error_event.get("message") or error_event)
            turns.append(
                TurnResult(
                    query=query,
                    response_text=response.get("text", "") or "",
                    latency_s=round((raw["latency_ms"] or 0) / 1000.0, 3),
                    chart_spec=visualization.get("spec"),
                    sql=None,  # not exposed over the wire
                    row_count=None,
                    error=error,
                )
            )
            time.sleep(self.inter_turn_sleep_s)
        return turns
