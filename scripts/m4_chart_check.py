"""
Milestone 4 — end-to-end chart contract check.

Drives the same WebSocket `chat_message` entry point as
scripts/benchmark_chat.py, but with a small set of chart-producing queries
chosen to exercise the M4 changes specifically:

  1. Melbourne wins-by-season -> line chart
  2. Sydney scoring sources pie chart (goals vs behinds, <=5 slices)
  3. An explicit "box plot" request -> should now arrive as chartType
     "groupedBar" (median/range), never "box"

Captures the raw `visualization` payload for each turn and writes them to
scripts/benchmark_results/m4_chart_check.json. Validation against the
frontend zod schema is done separately (frontend/scripts/validateChartFixtures.ts
covers the static fixture set; this script's job is just to prove real,
live backend output is well-formed ChartSpecV1 — i.e. has the right shape:
version "1", chartType in the canonical set, series non-empty, data non-empty).

Usage:
    backend/venv/bin/python scripts/m4_chart_check.py [--url http://localhost:5001]

Requires the backend to already be running (see run.py, port 5001).
"""
import argparse
import json
import os
import threading
import time
from datetime import datetime, timezone

import socketio

TEST_CASES = [
    {"id": "m4_line", "query": "Show me a chart of Melbourne's wins per season since 2018"},
    {"id": "m4_pie", "query": "Show me a pie chart of scoring sources - goals vs behinds for Sydney in 2024"},
    {"id": "m4_box_reroute", "query": "Show me a box plot of Collingwood's disposals by round in 2024"},
]

TURN_TIMEOUT_S = 90

CANONICAL_CHART_TYPES = {"line", "bar", "groupedBar", "pie", "scatter", "area", "table"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


class Capture:
    def __init__(self):
        self.reset()

    def reset(self):
        self.visualization = None
        self.response = None
        self.complete = None
        self.error = None
        self.done = threading.Event()


def build_client(capture: Capture):
    sio = socketio.Client(logger=False, engineio_logger=False)

    @sio.on("visualization")
    def on_visualization(data):
        capture.visualization = data

    @sio.on("response")
    def on_response(data):
        capture.response = data

    @sio.on("complete")
    def on_complete(data):
        capture.complete = data
        capture.done.set()

    @sio.on("error")
    def on_error(data):
        capture.error = data
        capture.done.set()

    return sio


def check_spec_shape(spec: dict) -> list:
    """Lightweight structural check mirroring ChartSpecV1 (no pydantic here —
    this is the live e2e proof; the exhaustive contract checks live in
    backend/tests/test_recharts_builder.py and the frontend fixtures script)."""
    problems = []
    if spec is None:
        problems.append("no visualization payload received")
        return problems
    if spec.get("version") != "1":
        problems.append(f"version != '1' (got {spec.get('version')!r})")
    if spec.get("chartType") not in CANONICAL_CHART_TYPES:
        problems.append(f"chartType not in v1 canonical set (got {spec.get('chartType')!r})")
    if not spec.get("data"):
        problems.append("data is empty")
    if not spec.get("series"):
        problems.append("series is empty")
    if spec.get("chartType") == "bar" and spec.get("orientation") not in (None, "horizontal", "vertical"):
        problems.append(f"unexpected orientation value {spec.get('orientation')!r}")
    return problems


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://localhost:5001")
    parser.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "benchmark_results", "m4_chart_check.json"))
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    capture = Capture()
    sio = build_client(capture)

    print(f"Connecting to {args.url} ...")
    sio.connect(args.url, wait_timeout=15)
    print("Connected.")

    results = {"meta": {"generated_at": now_iso(), "backend_url": args.url}, "cases": []}
    overall_ok = True

    try:
        for case in TEST_CASES:
            print(f"\n=== {case['id']}: {case['query']!r} ===")
            capture.reset()
            sio.emit("chat_message", {
                "message": case["query"],
                "conversation_id": None,
                "source": "aflagent",
            })
            finished = capture.done.wait(TURN_TIMEOUT_S)
            spec = capture.visualization.get("spec") if capture.visualization else None
            problems = check_spec_shape(spec)
            ok = finished and not capture.error and not problems
            overall_ok = overall_ok and ok
            print(f"  finished={finished} error={capture.error} problems={problems}")
            if spec:
                print(f"  chartType={spec.get('chartType')!r} version={spec.get('version')!r} "
                      f"rows={len(spec.get('data', []))} series={len(spec.get('series', []))} "
                      f"orientation={spec.get('orientation')!r} showSliceLabels={spec.get('showSliceLabels')!r}")
            results["cases"].append({
                "id": case["id"],
                "query": case["query"],
                "ok": ok,
                "problems": problems,
                "response_text": (capture.response or {}).get("text"),
                "visualization_spec": spec,
            })
            time.sleep(6)  # stay under the per-IP WS rate limit
    finally:
        sio.disconnect()

    results["meta"]["overall_ok"] = overall_ok
    with open(args.out, "w") as f:
        json.dump(results, f, indent=2, default=str)

    print(f"\n{'ALL PASS' if overall_ok else 'SOME FAILED'} — results written to {args.out}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
