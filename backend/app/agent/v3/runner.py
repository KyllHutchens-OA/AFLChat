"""
Entry point for callers outside the WebSocket path (the 1D eval harness's
v3 adapter, benchmark scripts):

    out: TurnOutput = await run_turn(question, history, model="gpt-6-luna")

`history` is a list of conversation messages shaped like ConversationService
stores them ({"role", "content"} plus assistant metadata such as
`tool_calls`). To chain turns, append
    {"role": "user", "content": question}
    history_entry(out)
TurnOutput fields: answer, chart_spec (ChartSpecV1 dict or None), rows,
tool_calls, sql, llm_calls, usage {input_tokens, cached_input_tokens,
cache_write_tokens, output_tokens, reasoning_tokens}, cost_usd, model,
latency_s, ttft_s, data_as_of, error.
"""
import asyncio
from typing import Any, Dict, List, Optional

from app.agent.v3.loop import AgentLoop, TurnOutput

__all__ = ["TurnOutput", "run_turn", "run_turn_sync", "history_entry"]


def run_turn_sync(question: str, history: Optional[List[Dict[str, Any]]] = None, *,
                  model: Optional[str] = None, spoiler_mode: bool = False, emit=None) -> TurnOutput:
    return AgentLoop(model=model).run(question, history or [], spoiler_mode=spoiler_mode, emit=emit)


async def run_turn(question: str, history: Optional[List[Dict[str, Any]]] = None, *,
                   model: Optional[str] = None, spoiler_mode: bool = False) -> TurnOutput:
    return await asyncio.to_thread(run_turn_sync, question, history, model=model, spoiler_mode=spoiler_mode)


def history_entry(out: TurnOutput) -> Dict[str, Any]:
    """The assistant message to append to `history` after a turn."""
    return {"role": "assistant", "content": out.answer, "tool_calls": out.memory}
