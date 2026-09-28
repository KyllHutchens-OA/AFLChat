"""
1E model bake-off for the v3 engine (roadmap D3): run the same eval cases
through AgentLoop for each model and report facts / charts / no-data /
corrections, latency (TTFT, total) and real cost.

Cases: SMOKE15 plus the first 5 SALVAGED cases from app/agent/eval/cases.py
(20 cases, 23 turns), scored with the existing deterministic scorer. Once the
1D harness lands (`python -m app.agent.eval --engine v3`), prefer that; this
script stays as the quick multi-model comparison.

    backend/venv/bin/python scripts/v3_bakeoff.py                      # all three models
    backend/venv/bin/python scripts/v3_bakeoff.py --models gpt-6-luna  # one model
    backend/venv/bin/python scripts/v3_bakeoff.py --out scripts/benchmark_results/v3_bakeoff.json

Models whose API key is not set are skipped with a message.
"""
import argparse
import json
import os
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START_DIR = Path.cwd()
sys.path.insert(0, str(ROOT / "backend"))
os.chdir(ROOT / "backend")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")

from app.agent.eval.cases import SALVAGED, SMOKE15  # noqa: E402
from app.agent.eval.models import CHECK_NAMES, TurnResult  # noqa: E402
from app.agent.eval.scorer import score_case  # noqa: E402
from app.agent.v3 import llm  # noqa: E402
from app.agent.v3.runner import history_entry, run_turn_sync  # noqa: E402

MODELS = ["gpt-6-luna", "gemini-3.5-flash-lite", "claude-sonnet-5"]
KEY_ENV = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}


def pct(values, p):
    values = sorted(v for v in values if v is not None)
    if not values:
        return None
    k = (len(values) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(values) - 1)
    return round(values[lo] + (values[hi] - values[lo]) * (k - lo), 2)


def run_case(case, model):
    history = [dict(m) for m in case.conversation_history]
    turns, extra = [], []
    for q in case.queries:
        out = run_turn_sync(q, history, model=model)
        turns.append(TurnResult(
            query=q, response_text=out.answer, latency_s=out.latency_s, chart_spec=out.chart_spec,
            sql="\n".join(out.sql) or None, row_count=len(out.rows), error=out.error,
            input_tokens=out.usage["input_tokens"], output_tokens=out.usage["output_tokens"]))
        extra.append({"ttft_s": out.ttft_s, "cost_usd": out.cost_usd, "tools": [c["name"] for c in out.tool_calls]})
        history += [{"role": "user", "content": q}, history_entry(out)]
    checks, passed = score_case(case, turns)
    return {"case_id": case.id, "passed": passed, "checks": checks,
            "turns": [{**t.model_dump(exclude={"chart_spec", "sql"}), "chart": t.chart_spec is not None, **e}
                      for t, e in zip(turns, extra)]}


def summarise(model, results):
    turns = [t for r in results for t in r["turns"]]
    axis = {}
    for name in CHECK_NAMES:
        vals = [r["checks"].get(name) for r in results if r["checks"].get(name) is not None]
        axis[name] = f"{sum(vals)}/{len(vals)}" if vals else "n/a"
    cost = sum(t["cost_usd"] for t in turns)
    return {
        "model": model, "cases": len(results), "passed": sum(r["passed"] for r in results), **axis,
        "ttft_p50": pct([t["ttft_s"] for t in turns], 0.5), "ttft_p90": pct([t["ttft_s"] for t in turns], 0.9),
        "total_p50": pct([t["latency_s"] for t in turns], 0.5), "total_p90": pct([t["latency_s"] for t in turns], 0.9),
        "cost_total_usd": round(cost, 5), "cost_per_turn_usd": round(cost / max(len(turns), 1), 6),
        "errors": sum(1 for t in turns if t["error"]),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="*", default=MODELS)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    cases = SMOKE15 + SALVAGED[:5]

    report = {"cases": [c.id for c in cases], "models": {}}
    for model in args.models:
        key = KEY_ENV[llm.provider_for(model)]
        if not os.getenv(key):
            print(f"SKIP {model}: {key} is not set")
            report["models"][model] = {"skipped": f"{key} not set"}
            continue
        print(f"== {model}")
        results = []
        for case in cases:
            r = run_case(case, model)
            failed = [k for k, v in r["checks"].items() if v is False]
            print(f"  {'PASS' if r['passed'] else 'FAIL'} {case.id} {failed or ''}")
            results.append(r)
        summary = summarise(model, results)
        print(json.dumps(summary, indent=2))
        report["models"][model] = {"summary": summary, "results": results}

    if args.out:
        out = START_DIR / args.out
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
