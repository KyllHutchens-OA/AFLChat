"""
Eval harness CLI.

Run from backend/ with the venv python:

    venv/bin/python -m app.agent.eval --subset smoke15
    venv/bin/python -m app.agent.eval --subset smoke15 --judge \
        --out ../scripts/benchmark_results/m5_smoke15.json
    venv/bin/python -m app.agent.eval --case pair_02
    venv/bin/python -m app.agent.eval --subset corrections --ws --url http://localhost:5001
    venv/bin/python -m app.agent.eval --list-subsets

Default mode is IN-PROCESS (imports the agent graph directly; needs
backend/.env DB + OpenAI credentials but no running server). --ws drives a
running backend over WebSocket instead, reusing scripts/benchmark_chat.py's
client.
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agent.eval.cases import build_subsets, get_case, get_subset
from app.agent.eval.models import CHECK_NAMES, EvalCase, EvalResult

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_cases(
    cases: List[EvalCase],
    use_ws: bool = False,
    url: str = "http://localhost:5001",
    judge: bool = False,
) -> List[EvalResult]:
    """Drive + score each case; returns EvalResults in input order."""
    from app.agent.eval.scorer import judge_case, score_case

    if use_ws:
        from app.agent.eval.runner import WsRunner

        runner = WsRunner(url=url)
    else:
        from app.agent.eval.runner import InProcessRunner

        runner = InProcessRunner()

    judge_client = None
    if judge:
        from app.agent.eval.scorer import _build_judge_client

        judge_client = _build_judge_client()

    results: List[EvalResult] = []
    try:
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case.id}: {case.queries[0][:70]!r}", flush=True)
            try:
                turns = runner.run_case(case)
                error = None
            except Exception as e:
                logger.exception(f"Runner failed for case {case.id}")
                turns, error = [], f"{type(e).__name__}: {e}"

            checks, passed = score_case(case, turns)
            result = EvalResult(
                case_id=case.id,
                tags=case.tags,
                source=case.source,
                turns=turns,
                checks=checks,
                passed=passed and error is None,
                error=error,
            )
            if judge and turns:
                result.judge = judge_case(case, turns, client=judge_client)

            status = "PASS" if result.passed else "FAIL"
            applicable = {k: v for k, v in checks.items() if v is not None}
            judge_str = f" judge={result.judge['verdict']}" if result.judge else ""
            print(
                f"    -> {status} in {result.total_latency_s}s "
                f"checks={applicable}{judge_str}",
                flush=True,
            )
            results.append(result)
    finally:
        if use_ws:
            runner.close()
    return results


def summarize(results: List[EvalResult]) -> Dict[str, Any]:
    """Aggregate pass rates, per-check tallies, latency and token totals."""
    latencies = [t.latency_s for r in results for t in r.turns if t.latency_s is not None]
    check_stats: Dict[str, Dict[str, int]] = {}
    for name in CHECK_NAMES:
        applicable = [r.checks.get(name) for r in results if r.checks.get(name) is not None]
        if applicable:
            check_stats[name] = {"n": len(applicable), "passed": sum(applicable)}

    judge_counts: Dict[str, int] = {}
    for r in results:
        if r.judge:
            judge_counts[r.judge["verdict"]] = judge_counts.get(r.judge["verdict"], 0) + 1

    summary: Dict[str, Any] = {
        "num_cases": len(results),
        "num_turns": sum(len(r.turns) for r in results),
        "passed": sum(r.passed for r in results),
        "failed": sum(not r.passed for r in results),
        "pass_rate": round(sum(r.passed for r in results) / len(results), 3) if results else None,
        "checks": check_stats,
        "latency_s": {
            "min": round(min(latencies), 3),
            "max": round(max(latencies), 3),
            "avg": round(sum(latencies) / len(latencies), 3),
        }
        if latencies
        else None,
        "tokens": {
            "input_tokens": sum(r.total_tokens["input_tokens"] for r in results),
            "output_tokens": sum(r.total_tokens["output_tokens"] for r in results),
        },
        "harness_errors": [r.case_id for r in results if r.error],
    }
    if judge_counts:
        summary["judge"] = judge_counts
    return summary


def build_report(
    results: List[EvalResult], subset: Optional[str], mode: str, judge: bool
) -> Dict[str, Any]:
    return {
        "meta": {
            "generated_at": _now_iso(),
            "subset": subset,
            "mode": mode,
            "judge": judge,
            "judge_model": os.getenv("OPENAI_MODEL", "gpt-5-mini") if judge else None,
        },
        "cases": [r.model_dump() for r in results],
        "summary": summarize(results),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.agent.eval",
        description="Footy-NAC chat eval harness (in-process by default).",
    )
    parser.add_argument("--subset", default="smoke15", help="Named subset to run (default: smoke15)")
    parser.add_argument("--case", default=None, help="Run a single case by id instead of a subset")
    parser.add_argument("--judge", action="store_true", help="Also grade responses with the LLM judge")
    parser.add_argument("--ws", action="store_true", help="Drive a running backend over WebSocket")
    parser.add_argument("--url", default="http://localhost:5001", help="Backend URL for --ws mode")
    parser.add_argument("--out", default=None, help="Write full JSON report to this path")
    parser.add_argument("--list-subsets", action="store_true", help="List subsets and exit")
    parser.add_argument("--max-cases", type=int, default=None, help="Cap the number of cases run")
    args = parser.parse_args(argv)

    if args.list_subsets:
        for name, cases in sorted(build_subsets().items()):
            print(f"{name:12s} {len(cases):3d} cases")
        return 0

    try:
        if args.case:
            cases = [get_case(args.case)]
            subset_label = None
        else:
            cases = get_subset(args.subset)
            subset_label = args.subset
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if args.max_cases:
        cases = cases[: args.max_cases]

    mode = "ws" if args.ws else "in_process"
    print(f"Running {len(cases)} case(s) [{mode}]" + (f" subset={subset_label}" if subset_label else ""))

    results = run_cases(cases, use_ws=args.ws, url=args.url, judge=args.judge)
    report = build_report(results, subset_label, mode, args.judge)

    print("\n=== Summary ===")
    print(json.dumps(report["summary"], indent=2, default=str))

    failed = [r for r in results if not r.passed]
    if failed:
        print("\nFailed cases:")
        for r in failed:
            applicable = {k: v for k, v in r.checks.items() if v is not None}
            print(f"  {r.case_id}: checks={applicable} error={r.error}")

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        print(f"\nReport written to {out_path}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
