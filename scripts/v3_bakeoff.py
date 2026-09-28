"""
1E model bake-off (roadmap D3): run the 1D eval harness on the v3 engine
once per model and compare facts, charts, no-data, latency and real cost.

    backend/venv/bin/python scripts/v3_bakeoff.py                          # all three models, smoke subset
    backend/venv/bin/python scripts/v3_bakeoff.py --models gpt-6-luna --subset full

Each model runs `python -m app.agent.eval --engine v3` with AGENT_MODEL set;
reports land in scripts/benchmark_results/v3_<subset>_<model>.json and the
comparison table is printed (and saved with --out). Models whose API key is
not set are skipped with a message.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
RESULTS = ROOT / "scripts" / "benchmark_results"
MODELS = ["gpt-6-luna", "gemini-3.5-flash-lite", "claude-sonnet-5"]
KEY_ENV = {"gpt": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "claude": "ANTHROPIC_API_KEY"}


def _env_value(name):
    if os.getenv(name):
        return os.getenv(name)
    env_file = BACKEND / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f"{name}="):
                return line.split("=", 1)[1].strip().strip("'\"")
    return None


def pct(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def axis(summary, name):
    c = summary["checks"].get(name) or {}
    return f"{c.get('passed', 0)}/{c.get('n', 0)}" if c else "n/a"


def summarise(model, report):
    s = report["summary"]
    turns = [t for c in report["cases"] for t in c.get("turns", [])]
    cost = sum((t.get("engine_meta") or {}).get("cost_usd", 0) for t in turns)
    return {
        "model": model, "passed": f"{s['passed']}/{s['scored']}",
        "facts": axis(s, "truth_text"), "rows": axis(s, "truth_rows"), "charts": axis(s, "chart"),
        "chart_values": axis(s, "chart_values"), "no_data": axis(s, "no_data"), "behaviour": axis(s, "behaviour"),
        "ttft_p50": pct([t.get("ttft_s") for t in turns], 0.5), "ttft_p90": pct([t.get("ttft_s") for t in turns], 0.9),
        "total_p50": s["latency_s"]["p50"], "total_p90": s["latency_s"]["p90"],
        "cost_per_turn_usd": round(cost / max(len(turns), 1), 6), "cost_total_usd": round(cost, 5),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=MODELS)
    ap.add_argument("--subset", default="smoke")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    rows = []
    for model in args.models:
        key = KEY_ENV[model.split("-")[0]]
        if not _env_value(key):
            print(f"SKIP {model}: {key} is not set")
            rows.append({"model": model, "skipped": f"{key} not set"})
            continue
        out = RESULTS / f"v3_{args.subset}_{model}.json"
        print(f"== {model} ({args.subset}) -> {out.name}", flush=True)
        env = {**os.environ, "AGENT_MODEL": model, "FLASK_ENV": os.getenv("FLASK_ENV", "production")}
        subprocess.run([sys.executable, "-m", "app.agent.eval", "--engine", "v3", "--subset", args.subset,
                        "--out", str(out)], cwd=BACKEND, env=env, check=False)
        rows.append(summarise(model, json.loads(out.read_text())))

    print(json.dumps(rows, indent=2))
    if args.out:
        (Path.cwd() / args.out).write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
