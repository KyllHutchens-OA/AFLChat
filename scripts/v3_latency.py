"""
1E latency check for the v3 engine: time to `received`, first `thinking`,
first streamed token (TTFT) and total, over ~15 representative questions.

    # against a running backend started with AGENT_ENGINE=v3
    backend/venv/bin/python scripts/v3_latency.py --url http://localhost:5001
    # or in-process (no server; TTFT = first streamed text from the model)
    backend/venv/bin/python scripts/v3_latency.py --in-process

Targets (roadmap 1E gate): median TTFT <= 5s, p90 total <= 15s.
The WS mode sleeps between turns to stay under the 10 messages/min limit.
"""
import argparse
import json
import os
import statistics
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [
    "Who were the top goal kickers in 2025?",
    "Collingwood vs Carlton head to head over the last 10 years",
    "Marcus Bontempelli disposals per season",
    "Geelong wins by season since 2010",
    "Compare Patrick Cripps and Marcus Bontempelli in 2024",
    "Who won the 2023 grand final?",
    "What was the highest scoring game ever?",
    "How did the Cats go in 2024?",
    "Dusty Martin career goals",
    "Who had the most disposals in 2023?",
    "Show me the top goal kickers in 1985",
    "Who won the 2026 grand final?",
    "Top 5 disposal getters in 2026",
    "hi",
    "Where did Richmond finish on the ladder in 2023?",
]


def pct(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def run_ws(url, questions, sleep_s):
    import socketio

    sio = socketio.Client()
    state = {}
    done = threading.Event()

    def mark(name):
        def handler(data=None):
            state.setdefault(name, time.monotonic())
            if name in ("complete", "error"):
                done.set()
        return handler

    for ev in ("received", "thinking", "response_delta", "visualization", "response", "complete", "error"):
        sio.on(ev, mark(ev))
    sio.connect(url, wait_timeout=15)
    rows = []
    for q in questions:
        state.clear()
        done.clear()
        t0 = time.monotonic()
        sio.emit("chat_message", {"message": q, "source": "aflagent"})
        done.wait(90)
        rel = {k: round(v - t0, 2) for k, v in state.items()}
        rows.append({"question": q, "received": rel.get("received"), "first_thinking": rel.get("thinking"),
                     "ttft": rel.get("response_delta") or rel.get("response"), "total": rel.get("complete"),
                     "chart": "visualization" in rel, "error": "error" in rel})
        print(json.dumps(rows[-1]))
        time.sleep(sleep_s)
    sio.disconnect()
    return rows


def run_in_process(questions, model):
    sys.path.insert(0, str(ROOT / "backend"))
    os.chdir(ROOT / "backend")
    from dotenv import load_dotenv
    load_dotenv(".env")
    from app.agent.v3.runner import run_turn_sync

    rows = []
    for q in questions:
        out = run_turn_sync(q, [], model=model)
        rows.append({"question": q, "ttft": out.ttft_s, "total": out.latency_s, "chart": out.chart_spec is not None,
                     "error": bool(out.error), "cost_usd": out.cost_usd, "tools": [c["name"] for c in out.tool_calls]})
        print(json.dumps(rows[-1]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:5001")
    ap.add_argument("--in-process", action="store_true")
    ap.add_argument("--model", default=None)
    ap.add_argument("--sleep", type=float, default=6.5)
    ap.add_argument("--out", default=None, help="write JSON results here")
    args = ap.parse_args()

    rows = run_in_process(QUESTIONS, args.model) if args.in_process else run_ws(args.url, QUESTIONS, args.sleep)
    ttft, total = [r["ttft"] for r in rows], [r["total"] for r in rows]
    summary = {
        "mode": "in-process" if args.in_process else "websocket", "n": len(rows),
        "ttft_p50": pct(ttft, 0.5), "ttft_p90": pct(ttft, 0.9),
        "total_p50": pct(total, 0.5), "total_p90": pct(total, 0.9),
        "received_p50": pct([r.get("received") for r in rows], 0.5),
        "errors": sum(r["error"] for r in rows), "charts": sum(r["chart"] for r in rows),
    }
    print(json.dumps(summary, indent=2))
    if args.out:
        Path(args.out).write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
