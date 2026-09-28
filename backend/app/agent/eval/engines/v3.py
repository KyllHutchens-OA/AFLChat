"""
v3 engine adapter: drives the single tool-calling AgentLoop in-process
(app.agent.v3.runner). The model comes from AGENT_MODEL (the bake-off sets it
per run). History is threaded the way ws_stream persists it: the assistant
message carries its compact tool calls, so corrections see what was asked.

Like v2, the app's pooled DB connections are forced read-only by default.
"""
import os
from typing import Any, Dict, List

from app.agent.eval.models import ToolCall, TurnResult
from app.agent.eval.runner import MAX_ROWS, EngineAdapter


class V3Engine(EngineAdapter):
    name = "v3"

    def __init__(self, read_only_db: bool = True, model: str = None, **_: Any):
        from app.agent.v3.llm import model_for

        self.model = model or model_for("AGENT_MODEL")
        if read_only_db:
            from app.agent.eval.engines.v2 import _force_read_only
            from app.data.database import engine

            _force_read_only(engine)

    def describe(self) -> Dict[str, Any]:
        return {"engine": self.name, "model": self.model, "effort": os.getenv("AGENT_EFFORT", "low")}

    def run_turn(self, question: str, history: List[Dict[str, Any]]) -> TurnResult:
        from app.agent.v3.runner import run_turn_sync

        out = run_turn_sync(question, history, model=self.model)
        data_calls = [c for c in out.tool_calls if c["name"] != "make_chart"]
        final_sql = next((c["sql"][-1] for c in reversed(data_calls) if c.get("sql")), None)
        return TurnResult(
            query=question,
            response_text=out.answer,
            latency_s=out.latency_s,
            ttft_s=out.ttft_s,
            chart_spec=out.chart_spec,
            sql=final_sql,
            tool_calls=[ToolCall(name=c["name"], args=c.get("args") or {}, sql="\n".join(c.get("sql") or []) or None,
                                 row_count=c.get("row_count"), error=c.get("error")) for c in out.tool_calls],
            columns=out.columns,
            rows=out.rows[:MAX_ROWS],
            row_count=out.row_count,
            error=out.error,
            input_tokens=out.usage.get("input_tokens", 0),
            output_tokens=out.usage.get("output_tokens", 0),
            engine_meta={"memory": out.memory, "model": out.model, "cost_usd": out.cost_usd,
                         "cached_input_tokens": out.usage.get("cached_input_tokens", 0),
                         "reasoning_tokens": out.usage.get("reasoning_tokens", 0), "data_as_of": out.data_as_of},
        )

    def history_messages(self, turn: TurnResult) -> List[Dict[str, Any]]:
        return [
            {"role": "user", "content": turn.query},
            {"role": "assistant", "content": turn.response_text, "tool_calls": turn.engine_meta.get("memory") or []},
        ]
