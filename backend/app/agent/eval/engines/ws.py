"""
v2-ws engine adapter: drives a RUNNING backend over WebSocket, reusing
scripts/benchmark_chat.py's socket.io client. Exercises the full
websocket.py path; history lives server-side (conversation_id), so the
`history` argument is ignored and preloaded case history is unsupported.
SQL and result rows are not on the wire, so row/SQL checks are N/A here.
Rate limits apply: sleeps between turns.
"""
import importlib.util
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.eval.models import EvalCase, TurnResult
from app.agent.eval.runner import EngineAdapter

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[5]
BENCHMARK_CHAT_PATH = REPO_ROOT / "scripts" / "benchmark_chat.py"


class WsEngine(EngineAdapter):
    name = "v2-ws"

    def __init__(self, url: str = "http://localhost:5001", inter_turn_sleep_s: float = 6.0, **_: Any):
        self.url = url
        self.inter_turn_sleep_s = inter_turn_sleep_s
        spec = importlib.util.spec_from_file_location("benchmark_chat", BENCHMARK_CHAT_PATH)
        self._bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self._bench)
        self.capture = self._bench.TurnCapture()
        self.sio = self._bench.build_client(self.capture)
        self._connected = False
        self._conversation_id: Optional[str] = None

    def describe(self) -> Dict[str, Any]:
        return {"engine": self.name, "url": self.url}

    def start_case(self, case: EvalCase) -> None:
        if case.conversation_history:
            logger.warning(f"[{case.id}] preloaded history unsupported over WS; running without it.")
        self._conversation_id = None
        if not self._connected:
            self.sio.connect(self.url, wait_timeout=15)
            self._connected = True

    def close(self) -> None:
        if self._connected:
            self.sio.disconnect()
            self._connected = False

    def run_turn(self, question: str, history: List[Dict[str, Any]]) -> TurnResult:
        raw, self._conversation_id = self._bench.run_turn(
            self.sio, self.capture, question, self._conversation_id
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
        time.sleep(self.inter_turn_sleep_s)
        return TurnResult(
            query=question,
            response_text=response.get("text", "") or "",
            latency_s=round((raw["latency_ms"] or 0) / 1000.0, 3),
            chart_spec=visualization.get("spec"),
            error=error,
        )
