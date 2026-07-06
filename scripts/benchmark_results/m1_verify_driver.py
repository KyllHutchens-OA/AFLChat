"""
Milestone 1 verification — targeted re-run of a subset of the M0 baseline
cases against the backend after the M1 fixes (dynamic season ceiling,
player-season mismatch warnings, correction cache-bypass, real token usage).

Reuses the exact WebSocket-driving machinery from benchmark_chat.py (same
socketio client, same event capture, same chat_message payload shape) so the
comparison against baseline_2026-07-07_raw.json is apples-to-apples. Does not
modify benchmark_chat.py.

Usage:
    backend/venv/bin/python scripts/benchmark_results/m1_verify_driver.py
"""
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from benchmark_chat import build_client, run_turn, TurnCapture, now_iso  # noqa: E402

TEST_CASES = [
    {"id": "single_01_2026season", "category": "single",
     "turns": ["How many games have Collingwood won this season?"]},
    {"id": "explicit_2026", "category": "single",
     "turns": ["Who kicked the most goals in 2026?"]},
    {"id": "pair_02_correction", "category": "pair",
     "turns": [
         "Show me Patrick Cripps's stats for 2023",
         "Sorry, I meant Marcus Bontempelli, not Cripps.",
     ]},
    {"id": "nodata_01_mismatch", "category": "nodata",
     "turns": ["What were Nick Daicos's stats in 2015?"]},
]

INTER_TURN_SLEEP_S = 6
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "m1_verify_raw.json")


def main():
    url = "http://localhost:5001"
    all_results = {
        "meta": {
            "generated_at": now_iso(),
            "backend_url": url,
            "num_cases": len(TEST_CASES),
            "num_turns": sum(len(c["turns"]) for c in TEST_CASES),
        },
        "cases": [],
    }

    capture = TurnCapture()
    sio = build_client(capture)

    print(f"Connecting to {url} ...")
    sio.connect(url, wait_timeout=15)
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

    with open(OUT_PATH, "w") as f:
        json.dump(all_results, f, indent=2, default=str)

    print(f"\nRaw results written to {OUT_PATH}")


if __name__ == "__main__":
    main()
