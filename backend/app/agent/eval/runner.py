"""
Engine-agnostic runner interface.

The harness never touches pipeline internals directly. Every chat engine is
wrapped in an `EngineAdapter`:

    run_turn(question, history) -> TurnResult
        question: the user's message for this turn
        history:  prior messages, shaped however the engine persists them
                  (built by the engine's own `history_messages`)
        returns:  answer text, chart spec, result rows (capped), final SQL,
                  tool calls, token usage, latency (and ttft if streamed)

Adapters live in app/agent/eval/engines/ and are chosen with --engine:
    v2      AFLAnalyticsAgent (LangGraph pipeline), in-process
    v2-ws   the same pipeline through a running backend's WebSocket
    v3      single tool-calling agent loop (added in 1E as engines/v3.py)
"""
import importlib
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List

from app.agent.eval.models import EvalCase, TurnResult

logger = logging.getLogger(__name__)

# Cap on persisted result rows per turn (keeps baselines small).
MAX_ROWS = 200

ENGINES: Dict[str, str] = {
    "v2": "app.agent.eval.engines.v2:V2Engine",
    "v2-ws": "app.agent.eval.engines.ws:WsEngine",
    "v3": "app.agent.eval.engines.v3:V3Engine",
}


class EngineAdapter(ABC):
    """One chat engine behind a uniform turn-level interface."""

    name: str = "base"

    def start_case(self, case: EvalCase) -> None:
        """Hook: reset per-conversation state before a case."""

    def close(self) -> None:
        """Hook: release connections at the end of the run."""

    def describe(self) -> Dict[str, Any]:
        """Engine metadata recorded in the report (model ids etc.)."""
        return {"engine": self.name}

    @abstractmethod
    def run_turn(self, question: str, history: List[Dict[str, Any]]) -> TurnResult:
        """Answer one user message given prior history."""

    def history_messages(self, turn: TurnResult) -> List[Dict[str, Any]]:
        """Messages to append to history after `turn` (engine's own shape)."""
        return [
            {"role": "user", "content": turn.query},
            {"role": "assistant", "content": turn.response_text},
        ]


def get_engine(name: str, **kwargs: Any) -> EngineAdapter:
    """Instantiate an engine by name; clear error if it is not built yet."""
    if name not in ENGINES:
        raise ValueError(f"Unknown engine '{name}'. Available: {', '.join(ENGINES)}")
    module_name, cls_name = ENGINES[name].split(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name == module_name:
            raise ValueError(
                f"Engine '{name}' is not implemented yet ({module_name}). "
                "Add an EngineAdapter subclass there (see runner.py)."
            ) from e
        raise
    return getattr(module, cls_name)(**kwargs)


def drive_case(engine: EngineAdapter, case: EvalCase) -> List[TurnResult]:
    """Run every query of a case through the engine, threading history."""
    engine.start_case(case)
    # Copy so a case's preloaded synthetic history is never mutated.
    history: List[Dict[str, Any]] = [dict(m) for m in case.conversation_history]
    turns: List[TurnResult] = []
    for query in case.queries:
        turn = engine.run_turn(query, list(history))
        turns.append(turn)
        history.extend(engine.history_messages(turn))
    return turns
