"""
Milestone 0 — Baseline benchmark for the Footy-NAC chat pipeline.

Drives the WebSocket `chat_message` event (the only entry point that carries
conversation history) using a python-socketio client, exactly like the real
frontend (`frontend/src/hooks/useAgentWebSocket.ts`) does:

    socket.emit('chat_message', {message, conversation_id, source: 'aflagent'})

and listens for the same events the frontend listens for:

    thinking, conversation_started, visualization, response, complete, error

Each test "case" is either:
  - a single query, or
  - a two-turn pair (turn 1 query, then a turn 2 "correction" sent on the
    SAME conversation_id so the agent has history to correct against).

Results (raw event capture, no scoring) are written to:
    scripts/benchmark_results/baseline_<YYYY-MM-DD>_raw.json

Run scripts/score_baseline.py afterwards to attach scores and produce the
final scripts/benchmark_results/baseline_<YYYY-MM-DD>.json deliverable.

Usage:
    backend/venv/bin/python scripts/benchmark_chat.py [--url http://localhost:5001]

Requires the backend to already be running (see run.py, port 5001).
"""
import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone

import socketio  # python-socketio client (ships as a dep of flask-socketio)


# ---------------------------------------------------------------------------
# Test set: ~10 single queries sampled from eval_queries.txt across its
# categories (simple current-season stat, historical medal fact, career
# total, exact score lookup, chart - line, chart - pie, head-to-head record),
# plus 3 two-turn correction pairs, plus 2 known-no-data queries (verified
# against the DB before writing this file: Nick Daicos's earliest season in
# player_stats is 2022, and the matches table only goes up to season 2026).
# ---------------------------------------------------------------------------
TEST_CASES = [
    {"id": "single_01", "category": "single",
     "turns": ["How many games has Collingwood won this season?"]},
    {"id": "single_02", "category": "single",
     "turns": ["Who won the Brownlow Medal in 2023?"]},
    {"id": "single_03", "category": "single",
     "turns": ["Show me a chart of Melbourne's wins per season since 2018"]},
    {"id": "single_04", "category": "single",
     "turns": ["What's Dustin Martin's career goals tally?"]},
    {"id": "single_05", "category": "single",
     "turns": ["What was the score in the 2024 grand final?"]},
    {"id": "single_06", "category": "single",
     "turns": ["Show me a pie chart of scoring sources - goals vs behinds for Sydney in 2024"]},
    {"id": "single_07", "category": "single",
     "turns": ["What's Carlton's win-loss record against Essendon since 1990?"]},

    {"id": "pair_01", "category": "pair",
     "turns": [
         "Who kicked the most goals last round?",
         "No, I meant round 10 of the 2024 season, not last round.",
     ]},
    {"id": "pair_02", "category": "pair",
     "turns": [
         "Show me Patrick Cripps's stats for 2023",
         "Sorry, I meant Marcus Bontempelli, not Cripps.",
     ]},
    {"id": "pair_03", "category": "pair",
     "turns": [
         "What was the score in the 2023 grand final?",
         "Actually I meant the 2022 grand final, not 2023.",
     ]},

    {"id": "nodata_01", "category": "nodata",
     "turns": ["What were Nick Daicos's stats in 2015?"]},
    {"id": "nodata_02", "category": "nodata",
     "turns": ["What was the score in the 2030 AFL grand final?"]},
]

TURN_TIMEOUT_S = 90
INTER_TURN_SLEEP_S = 6  # keep well under the 10 msg/min per-IP WS rate limit


def now_iso():
    return datetime.now(timezone.utc).isoformat()


# conversation_id -> owner token (server requires it to append to a conversation)
OWNER_TOKENS = {}


class TurnCapture:
    """Mutable bucket for events belonging to the turn currently in flight."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.thinking = []
        self.conversation_started = None
        self.visualization = None
        self.response = None
        self.complete = None
        self.error = None
        self.done = threading.Event()
        self.t0 = None


def build_client(capture: TurnCapture):
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.event
    def connect():
        pass

    @sio.event
    def disconnect():
        pass

    @sio.on("thinking")
    def on_thinking(data):
        capture.thinking.append({"t_offset_ms": _offset_ms(capture), "data": data})

    @sio.on("conversation_started")
    def on_conversation_started(data):
        data = dict(data or {})
        token = data.pop("owner_token", None)
        if token and data.get("conversation_id"):
            OWNER_TOKENS[data["conversation_id"]] = token
        capture.conversation_started = data

    @sio.on("visualization")
    def on_visualization(data):
        capture.visualization = data

    @sio.on("response")
    def on_response(data):
        capture.response = data
        # Note: 'complete' is the authoritative end-of-turn signal (see
        # websocket.py — it's emitted right after 'response'), so we don't
        # set capture.done here.

    @sio.on("complete")
    def on_complete(data):
        capture.complete = data
        capture.done.set()

    @sio.on("error")
    def on_error(data):
        capture.error = data
        capture.done.set()

    return sio


def _offset_ms(capture: TurnCapture):
    if capture.t0 is None:
        return None
    return round((time.monotonic() - capture.t0) * 1000, 1)


def run_turn(sio, capture: TurnCapture, message: str, conversation_id):
    capture.reset()
    capture.t0 = time.monotonic()
    send_wall_time = now_iso()
    sio.emit("chat_message", {
        "message": message,
        "conversation_id": conversation_id,
        "owner_token": OWNER_TOKENS.get(conversation_id),
        "source": "aflagent",
    })
    finished = capture.done.wait(TURN_TIMEOUT_S)
    latency_ms = round((time.monotonic() - capture.t0) * 1000, 1)

    expected_events = ["response", "complete"]
    missing = []
    if capture.response is None:
        missing.append("response")
    if capture.complete is None:
        missing.append("complete")

    next_conversation_id = conversation_id
    if capture.conversation_started and capture.conversation_started.get("conversation_id"):
        next_conversation_id = capture.conversation_started["conversation_id"]
    elif capture.complete and capture.complete.get("conversation_id"):
        next_conversation_id = capture.complete["conversation_id"]

    result = {
        "query": message,
        "sent_conversation_id": conversation_id,
        "sent_at": send_wall_time,
        "timed_out": not finished,
        "latency_ms": latency_ms,
        "missing_events": missing,
        "events": {
            "thinking": capture.thinking,
            "conversation_started": capture.conversation_started,
            "visualization": capture.visualization,
            "response": capture.response,
            "complete": capture.complete,
            "error": capture.error,
        },
    }
    return result, next_conversation_id


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:5001")
    parser.add_argument("--out-dir", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "benchmark_results"))
    args = parser.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    date_str = datetime.now().strftime("%Y-%m-%d")
    out_path = os.path.join(args.out_dir, f"baseline_{date_str}_raw.json")

    all_results = {
        "meta": {
            "generated_at": now_iso(),
            "backend_url": args.url,
            "turn_timeout_s": TURN_TIMEOUT_S,
            "inter_turn_sleep_s": INTER_TURN_SLEEP_S,
            "num_cases": len(TEST_CASES),
            "num_turns": sum(len(c["turns"]) for c in TEST_CASES),
        },
        "cases": [],
    }

    capture = TurnCapture()
    sio = build_client(capture)

    print(f"Connecting to {args.url} ...")
    sio.connect(args.url, wait_timeout=15)
    print("Connected.")

    try:
        for case in TEST_CASES:
            print(f"\n=== Case {case['id']} ({case['category']}) ===")
            case_result = {"id": case["id"], "category": case["category"], "turns": []}
            conversation_id = None
            for i, message in enumerate(case["turns"]):
                print(f"  turn {i + 1}: {message!r}")
                turn_result, conversation_id = run_turn(sio, capture, message, conversation_id)
                status = "TIMEOUT" if turn_result["timed_out"] else (
                    "ERROR" if turn_result["events"]["error"] else "OK")
                print(f"    -> {status} in {turn_result['latency_ms']} ms"
                      f" (missing: {turn_result['missing_events']})")
                case_result["turns"].append(turn_result)
                time.sleep(INTER_TURN_SLEEP_S)
            all_results["cases"].append(case_result)
    finally:
        sio.disconnect()

    with open(out_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nRaw results written to {out_path}")
    print("Next: run scripts/score_baseline.py to attach scores.")


if __name__ == "__main__":
    main()
