"""
AgentLoop: one tool-calling loop per chat turn.

  history + question -> model -> (tool calls, run in parallel) -> model ... -> streamed answer

At most MAX_TOOL_CALLS tool calls per turn; after that the model must answer.
Progress (`thinking`) comes from the real tool calls, answer text streams as
`response_delta`. If the model skipped make_chart but the question clearly
wants a chart, ChartSelector heuristics make one from the last result.
"""
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.agent.v3 import llm
from app.agent.v3.coverage import data_as_of
from app.agent.v3.history import compact_calls, to_messages
from app.agent.v3.prompt import system_prompt
from app.agent.v3.tools import execute, progress_label, tool_schemas
from app.agent.v3.tools.base import ResultStore
from app.agent.v3.tools.misc import fallback_chart

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 6
MAX_MODEL_CALLS = 8
TOOL_OUTPUT_CHARS = 12000
RESULT_ROWS = 200  # rows of the final result kept on TurnOutput (evals compare them to ground truth)

Emit = Callable[[str, Dict[str, Any]], None]


@dataclass
class TurnOutput:
    """What one v3 turn produced. Shape consumed by ws_stream, the eval
    runner (runner.run_turn) and the chat_traces writer."""
    answer: str
    chart_spec: Optional[Dict[str, Any]]
    rows: List[Dict[str, Any]]                  # last non-empty tool result, up to RESULT_ROWS
    columns: List[str]
    row_count: Optional[int]                    # uncapped size of that result
    tool_calls: List[Dict[str, Any]]            # name, args, output, sql, latency_s, error
    sql: List[str]
    llm_calls: List[Dict[str, Any]]             # model, latency_s, first_text_s, usage, cost_usd
    usage: Dict[str, int]
    cost_usd: float
    model: str
    latency_s: float
    ttft_s: Optional[float]
    data_as_of: str
    error: Optional[str] = None
    memory: List[Dict[str, Any]] = field(default_factory=list)  # compact tool calls for conversation metadata

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


class AgentLoop:
    def __init__(self, model: Optional[str] = None, effort: Optional[str] = None):
        self.model = model or llm.model_for("AGENT_MODEL")
        self.effort = effort or os.getenv("AGENT_EFFORT", "low")

    def run(self, question: str, history: Optional[List[Dict[str, Any]]] = None, *,
            spoiler_mode: bool = False, emit: Optional[Emit] = None) -> TurnOutput:
        emit = emit or (lambda event, payload: None)
        t0 = time.monotonic()
        store = ResultStore()
        system = system_prompt()
        tools = tool_schemas()
        user = f"[spoiler_mode: on]\n{question}" if spoiler_mode else question
        messages = to_messages(history or []) + [{"role": "user", "content": user}]

        calls_made: List[Dict[str, Any]] = []
        llm_calls: List[Dict[str, Any]] = []
        usage = llm.Usage()
        cost = 0.0
        answer, error, ttft = "", None, None
        streamed = {"any": False}

        def on_text(delta: str):
            nonlocal ttft
            if ttft is None:
                ttft = round(time.monotonic() - t0, 3)
            streamed["any"] = True
            emit("response_delta", {"delta": delta})

        try:
            for _ in range(MAX_MODEL_CALLS):
                budget = MAX_TOOL_CALLS - len(calls_made)
                res = llm.chat(messages, system=system, tools=tools if budget > 0 else None,
                               model=self.model, effort=self.effort, on_text=on_text)
                usage, cost = usage + res.usage, cost + res.cost_usd
                llm_calls.append({"model": res.model, "latency_s": res.latency_s, "first_text_s": res.first_text_s,
                                  "usage": res.usage.as_dict(), "cost_usd": res.cost_usd,
                                  "tool_calls": [c.name for c in res.tool_calls]})
                if not res.tool_calls:
                    answer = res.text
                    break
                if res.text and streamed["any"]:
                    emit("response_reset", {})  # preamble before tool calls is not the answer
                messages.append(res.assistant_message())
                messages.extend(self._run_tools(res.tool_calls, budget, store, calls_made, emit))
            else:
                error = "model call limit reached"
        except Exception as e:
            logger.exception("v3 loop failed")
            error = f"{type(e).__name__}: {e}"

        if not answer:
            answer = ("Sorry, I couldn't finish that one. Please try again or rephrase your question."
                      if error else "I couldn't find an answer to that.")

        chart = store.charts[-1] if store.charts else None
        if chart is None and not error:
            try:
                chart = fallback_chart(question, store)
            except Exception as e:
                logger.warning(f"fallback chart failed: {e}")
        last = store.last()
        last_rows = []
        if last is not None:
            head = last.head(RESULT_ROWS).astype(object)
            last_rows = head.where(head.notna(), None).to_dict(orient="records")
        return TurnOutput(
            answer=answer.strip(), chart_spec=chart, rows=last_rows,
            columns=list(last.columns) if last is not None else [],
            row_count=int(len(last)) if last is not None else None, tool_calls=calls_made,
            sql=[s for c in calls_made for s in c.get("sql", [])], llm_calls=llm_calls,
            usage=usage.as_dict(), cost_usd=round(cost, 8), model=self.model,
            latency_s=round(time.monotonic() - t0, 3), ttft_s=ttft, data_as_of=data_as_of(),
            error=error, memory=compact_calls(calls_made))

    def _run_tools(self, tool_calls, budget: int, store: ResultStore,
                   calls_made: List[Dict[str, Any]], emit: Emit) -> List[Dict[str, Any]]:
        allowed, refused = tool_calls[:max(budget, 0)], tool_calls[max(budget, 0):]
        for c in allowed:
            emit("thinking", {"step": progress_label(c.name, c.arguments), "current_step": "tool", "tool": c.name})
        # Charts depend on results from the same batch, so run them after data tools.
        data_calls = [c for c in allowed if c.name != "make_chart"]
        chart_calls = [c for c in allowed if c.name == "make_chart"]
        results: Dict[str, Dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            for c, r in zip(data_calls, pool.map(lambda c: execute(c.name, c.arguments, store), data_calls)):
                results[c.id] = r
        for c in chart_calls:
            results[c.id] = execute(c.name, c.arguments, store)

        out = []
        for c in allowed:
            r = results[c.id]
            try:
                args = json.loads(c.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_raw": c.arguments}
            calls_made.append({"name": c.name, "args": args, "output": r["output"], "sql": r["sql"],
                               "latency_s": r["latency_s"], "error": r["error"],
                               "row_count": r["output"].get("row_count")})
            out.append({"role": "tool", "tool_call_id": c.id, "name": c.name,
                        "content": json.dumps(r["output"], default=str)[:TOOL_OUTPUT_CHARS]})
        for c in refused:
            out.append({"role": "tool", "tool_call_id": c.id, "name": c.name,
                        "content": json.dumps({"error": "tool call limit reached; answer with what you have"})})
        return out
