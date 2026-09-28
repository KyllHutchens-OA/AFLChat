"""
Eval harness CLI.

Run from backend/ with the venv python:

    venv/bin/python -m app.agent.eval --subset smoke
    venv/bin/python -m app.agent.eval --subset full --engine v2 --save-baseline v2_2026-09-28
    venv/bin/python -m app.agent.eval --subset smoke --engine v3 --compare v2_2026-09-28 --strict
    venv/bin/python -m app.agent.eval --subset smoke --repeat 3          # stability
    venv/bin/python -m app.agent.eval --case fin_01,lad_01 --judge       # judge = triage only
    venv/bin/python -m app.agent.eval --subset full --truth-only         # print live ground truth, no LLM
    venv/bin/python -m app.agent.eval --diff v2_2026-09-28 path/to/new.json
    venv/bin/python -m app.agent.eval --rescore v2_2026-09-28 --compare v2_2026-09-28  # no LLM
    venv/bin/python -m app.agent.eval --list-subsets

Exit code: 0 when every scored case passed (skips do not fail the run);
1 otherwise. With --strict, flaky cases, per-turn budget breaches and a
run-level p90 over budget also fail the run.
"""
import argparse
import json
import logging
import math
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.agent.eval.cases import build_subsets, get_case, get_subset
from app.agent.eval.models import CHECK_NAMES, EvalCase, EvalResult, TurnResult

logger = logging.getLogger(__name__)

DEFAULT_P90_S = 15.0
DEFAULT_MAX_TURN_S = 30.0
DEFAULT_MAX_TURN_TOKENS = 20000


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _percentile(values: List[float], q: float) -> Optional[float]:
    """Nearest-rank percentile (q in 0..100)."""
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, math.ceil(q / 100 * len(s)) - 1))
    return round(s[k], 3)


def _integrity(store, case: EvalCase) -> Optional[Any]:
    if not case.integrity_sql:
        return None
    try:
        return store.query(case.integrity_sql)
    except Exception as e:
        return f"error: {e}"


def _prepare(case: EvalCase, store):
    """(truth, skip_reason, case_as_scored, caveat_required) for one case."""
    from app.agent.eval.truth import effective_case

    truth, skip = store.truth_for(case)
    if skip:
        return None, skip, case, False
    caveat_required = False
    if case.caveat_sql:
        try:
            rows = store.query(case.caveat_sql)
            caveat_required = bool(rows and list(rows[0].values())[0])
        except Exception as e:
            logger.warning(f"[{case.id}] caveat_sql failed, not requiring a caveat: {e}")
    return truth, None, effective_case(case, truth), caveat_required


def _score(case, scored_case, run, turns, truth, error, integrity_ok, caveat_required,
           max_turn_s, max_turn_tokens) -> EvalResult:
    from app.agent.eval.scorer import score_case

    checks, passed, fails = score_case(
        scored_case, turns, truth, integrity_ok, max_turn_s, max_turn_tokens, caveat_required
    )
    result = EvalResult(
        case_id=case.id, run=run, tags=case.tags, source=case.source,
        turns=turns, checks=checks, failures=fails,
        truth_rows=(truth or [])[:50],
        passed=passed and error is None,
        budget_ok=checks.get("budget"),
        integrity_ok=integrity_ok,
        error=error,
    )
    result.status = "error" if error else ("pass" if result.passed else "fail")
    return result


def rescore_report(
    report: Dict[str, Any],
    max_turn_s: float = DEFAULT_MAX_TURN_S,
    max_turn_tokens: int = DEFAULT_MAX_TURN_TOKENS,
) -> List[EvalResult]:
    """Re-score a saved report's turns against the CURRENT cases and live
    truth, without calling any engine (cheap harness iteration; also shows
    how an old run fares once 1C changes the data)."""
    from app.agent.eval.truth import TruthStore

    store = TruthStore()
    results: List[EvalResult] = []
    try:
        for old in report.get("cases", []):
            try:
                case = get_case(old["case_id"])
            except ValueError:
                continue  # case removed since the report was written
            truth, skip, scored_case, caveat_required = _prepare(case, store)
            if skip or old.get("status") == "skip":
                results.append(EvalResult(case_id=case.id, tags=case.tags, source=case.source, status="skip",
                                          skip_reason=skip or old.get("skip_reason")))
                continue
            turns = [TurnResult.model_validate(t) for t in old.get("turns", [])]
            result = _score(case, scored_case, old.get("run", 0), turns, truth, old.get("error"),
                            old.get("integrity_ok"), caveat_required, max_turn_s, max_turn_tokens)
            result.judge = old.get("judge")
            results.append(result)
    finally:
        store.close()
    return results


def run_cases(
    cases: List[EvalCase],
    engine_name: str = "v2",
    repeat: int = 1,
    judge: bool = False,
    judge_model: Optional[str] = None,
    max_turn_s: float = DEFAULT_MAX_TURN_S,
    max_turn_tokens: int = DEFAULT_MAX_TURN_TOKENS,
    engine_kwargs: Optional[Dict[str, Any]] = None,
    store=None,
) -> List[EvalResult]:
    """Drive + score each case `repeat` times; returns EvalResults in order."""
    from app.agent.eval.runner import drive_case, get_engine
    from app.agent.eval.scorer import _build_judge_client, judge_case
    from app.agent.eval.truth import TruthStore

    store = store or TruthStore()
    engine = get_engine(engine_name, **(engine_kwargs or {}))
    judge_client = _build_judge_client() if judge else None

    results: List[EvalResult] = []
    try:
        for i, case in enumerate(cases, 1):
            truth, skip, scored_case, caveat_required = _prepare(case, store)
            label = f"[{i}/{len(cases)}] {case.id}: {case.queries[0][:70]!r}"
            if skip:
                print(f"{label}\n    -> SKIP ({skip})", flush=True)
                results.append(EvalResult(case_id=case.id, tags=case.tags, source=case.source,
                                          status="skip", skip_reason=skip))
                continue
            for run in range(repeat):
                print(label + (f" (run {run + 1}/{repeat})" if repeat > 1 else ""), flush=True)
                before = _integrity(store, case)
                try:
                    turns = drive_case(engine, scored_case)
                    error = None
                except Exception as e:
                    logger.exception(f"Engine failed for case {case.id}")
                    turns, error = [], f"{type(e).__name__}: {e}"
                after = _integrity(store, case)
                integrity_ok = None if case.integrity_sql is None else (before == after)

                result = _score(case, scored_case, run, turns, truth, error, integrity_ok,
                                caveat_required, max_turn_s, max_turn_tokens)
                if judge and turns and run == 0:
                    result.judge = judge_case(scored_case, turns, truth, client=judge_client, model=judge_model)

                applicable = {k: v for k, v in checks.items() if v is not None}
                judge_str = f" judge={result.judge['verdict']}" if result.judge else ""
                print(f"    -> {result.status.upper()} in {result.total_latency_s}s checks={applicable}{judge_str}",
                      flush=True)
                for f in fails[:6]:
                    print(f"       - {f}", flush=True)
                results.append(result)
    finally:
        engine.close()
        store.close()
    return results


def _case_groups(results: List[EvalResult]) -> Dict[str, List[EvalResult]]:
    groups: Dict[str, List[EvalResult]] = {}
    for r in results:
        groups.setdefault(r.case_id, []).append(r)
    return groups


def summarize(
    results: List[EvalResult],
    p90_budget_s: float = DEFAULT_P90_S,
    max_turn_s: float = DEFAULT_MAX_TURN_S,
) -> Dict[str, Any]:
    """Aggregate case outcomes (over repeats), checks, latency, tokens, stability."""
    from app.agent.eval.baseline import case_status

    groups = _case_groups(results)
    statuses = {cid: case_status([r.model_dump() for r in runs]) for cid, runs in groups.items()}
    ran = [r for r in results if r.status != "skip"]
    latencies = [t.latency_s for r in ran for t in r.turns if t.latency_s is not None]
    turn_tokens = [t.total_tokens for r in ran for t in r.turns]

    check_stats: Dict[str, Dict[str, int]] = {}
    for name in CHECK_NAMES:
        vals = [r.checks.get(name) for r in ran if r.checks.get(name) is not None]
        if vals:
            check_stats[name] = {"n": len(vals), "passed": sum(vals)}

    by_family: Dict[str, Dict[str, int]] = {}
    for cid, st in statuses.items():
        fam = cid.split("_")[0]
        b = by_family.setdefault(fam, {"pass": 0, "fail": 0, "flaky": 0, "skip": 0, "error": 0})
        b[st] += 1

    p90 = _percentile(latencies, 90)
    worst = max(latencies) if latencies else None
    scored = [cid for cid, st in statuses.items() if st != "skip"]
    summary: Dict[str, Any] = {
        "num_cases": len(groups),
        "runs": len(results),
        "scored": len(scored),
        "passed": sum(st == "pass" for st in statuses.values()),
        "failed": sum(st == "fail" for st in statuses.values()),
        "flaky": sorted(cid for cid, st in statuses.items() if st == "flaky"),
        "errors": sorted(cid for cid, st in statuses.items() if st == "error"),
        "skipped": {cid: groups[cid][0].skip_reason for cid, st in statuses.items() if st == "skip"},
        "pass_rate": round(sum(st == "pass" for st in statuses.values()) / len(scored), 3) if scored else None,
        "checks": check_stats,
        "by_family": by_family,
        "latency_s": {
            "p50": _percentile(latencies, 50),
            "p90": p90,
            "max": round(worst, 3) if worst is not None else None,
            "mean": round(sum(latencies) / len(latencies), 3),
            "turns": len(latencies),
        } if latencies else None,
        "budget": {
            "p90_budget_s": p90_budget_s,
            "max_turn_budget_s": max_turn_s,
            "p90_ok": (p90 <= p90_budget_s) if p90 is not None else None,
            "max_ok": (worst <= max_turn_s) if worst is not None else None,
            "cases_over_budget": sorted({r.case_id for r in ran if r.budget_ok is False}),
        },
        "tokens": {
            "input_tokens": sum(r.total_tokens["input_tokens"] for r in ran),
            "output_tokens": sum(r.total_tokens["output_tokens"] for r in ran),
            "mean_per_turn": round(sum(turn_tokens) / len(turn_tokens)) if turn_tokens else None,
            "max_turn": max(turn_tokens) if turn_tokens else None,
        },
    }
    repeats = max((len(v) for v in groups.values()), default=1)
    if repeats > 1:
        summary["stability"] = {
            cid: f"{sum(r.status == 'pass' for r in runs)}/{len(runs)}"
            for cid, runs in groups.items() if statuses[cid] != "skip"
        }
    judged = [r for r in results if r.judge]
    if judged:
        counts: Dict[str, int] = {}
        for r in judged:
            counts[r.judge["verdict"]] = counts.get(r.judge["verdict"], 0) + 1
        summary["judge"] = counts
        # Triage: where the judge disagrees with the deterministic verdict.
        summary["triage"] = [
            {"case_id": r.case_id, "deterministic": r.status, "judge": r.judge["verdict"], "reason": r.judge["reason"]}
            for r in judged
            if (r.status == "pass" and r.judge["verdict"] == "incorrect")
            or (r.status == "fail" and r.judge["verdict"] == "correct")
        ]
    return summary


def build_report(results: List[EvalResult], meta: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {"meta": meta, "cases": [r.model_dump() for r in results], "summary": summary}


def run_is_green(summary: Dict[str, Any], strict: bool) -> bool:
    ok = summary["failed"] == 0 and not summary["errors"]
    if strict:
        b = summary["budget"]
        ok = ok and not summary["flaky"] and not b["cases_over_budget"] and b["p90_ok"] is not False
    return ok


def _truth_only(cases: List[EvalCase]) -> int:
    from app.agent.eval.truth import TruthStore

    store = TruthStore()
    print(f"Ground truth from {store.describe()}")
    n_skip = 0
    for case in cases:
        rows, skip = store.truth_for(case)
        if skip:
            n_skip += 1
            print(f"{case.id:22s} SKIP  {skip}")
        else:
            shown = json.dumps(rows[:3], default=str) if rows else "[]"
            more = f" (+{len(rows) - 3} rows)" if rows and len(rows) > 3 else ""
            print(f"{case.id:22s} {shown[:220]}{more}")
    store.close()
    print(f"\n{len(cases)} cases, {n_skip} skipped")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.agent.eval", description="Footy-NAC chat eval harness.")
    parser.add_argument("--engine", default="v2", help="Chat engine: v2 | v2-ws | v3 (default v2)")
    parser.add_argument("--subset", default="smoke", help="Named subset (default: smoke)")
    parser.add_argument("--case", default=None, help="Comma-separated case ids instead of a subset")
    parser.add_argument("--repeat", type=int, default=1, help="Run each case N times and report stability")
    parser.add_argument("--strict", action="store_true",
                        help="Also fail on flaky cases, per-turn budget breaches and p90 over budget")
    parser.add_argument("--p90-budget", type=float, default=DEFAULT_P90_S, help="Run-level p90 turn latency (s)")
    parser.add_argument("--max-turn-budget", type=float, default=DEFAULT_MAX_TURN_S, help="Any single turn (s)")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_MAX_TURN_TOKENS, help="Tokens per turn")
    parser.add_argument("--judge", action="store_true", help="LLM triage (never changes pass/fail)")
    parser.add_argument("--judge-model", default=None, help="Judge model (default: EVAL_JUDGE_MODEL or OPENAI_MODEL)")
    parser.add_argument("--ws", action="store_true", help="Alias for --engine v2-ws")
    parser.add_argument("--url", default="http://localhost:5001", help="Backend URL for v2-ws")
    parser.add_argument("--allow-db-writes", action="store_true",
                        help="Do not force the engine's DB connections read-only")
    parser.add_argument("--out", default=None, help="Write the full JSON report to this path")
    parser.add_argument("--save-baseline", default=None, help="Also save the report as baselines/<name>.json")
    parser.add_argument("--compare", default=None, help="Diff this run against a baseline (name or path)")
    parser.add_argument("--diff", nargs=2, metavar=("BASE", "NEW"), help="Diff two saved reports and exit")
    parser.add_argument("--show-all", action="store_true", help="With --compare/--diff, list unchanged cases too")
    parser.add_argument("--truth-only", action="store_true", help="Print live ground truth per case; no LLM")
    parser.add_argument("--rescore", default=None,
                        help="Re-score a saved report (name or path) against current cases + live truth; no LLM")
    parser.add_argument("--list-subsets", action="store_true", help="List subsets and exit")
    parser.add_argument("--max-cases", type=int, default=None, help="Cap the number of cases run")
    args = parser.parse_args(argv)

    from app.agent.eval import baseline as bl

    if args.diff:
        print(bl.format_diff(bl.diff(bl.load(args.diff[0]), bl.load(args.diff[1])), args.show_all))
        return 0

    if args.list_subsets:
        for name, cases in sorted(build_subsets().items()):
            print(f"{name:16s} {len(cases):3d} cases")
        return 0

    try:
        if args.case:
            cases = [get_case(cid.strip()) for cid in args.case.split(",") if cid.strip()]
            subset_label = None
        else:
            cases = get_subset(args.subset)
            subset_label = args.subset
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    if args.max_cases:
        cases = cases[: args.max_cases]

    if args.truth_only:
        return _truth_only(cases)

    from app.agent.eval.scorer import judge_model_name
    from app.agent.eval.truth import TruthStore

    if args.rescore:
        # Re-score saved turns against current cases + live truth; no engine calls.
        old = bl.load(args.rescore)
        print(f"Re-scoring {len(old.get('cases', []))} saved run(s) from {args.rescore}")
        results = rescore_report(old, args.max_turn_budget, args.token_budget)
        meta = dict(old.get("meta", {}), rescored_at=_now_iso(), rescored_from=args.rescore)
    else:
        engine_name = "v2-ws" if args.ws else args.engine
        store = TruthStore()
        db = store.describe()
        print(f"Running {len(cases)} case(s) x{args.repeat} engine={engine_name} db={db}"
              + (f" subset={subset_label}" if subset_label else ""))
        try:
            results = run_cases(
                cases,
                engine_name=engine_name,
                repeat=max(1, args.repeat),
                judge=args.judge,
                judge_model=args.judge_model,
                max_turn_s=args.max_turn_budget,
                max_turn_tokens=args.token_budget,
                engine_kwargs={"url": args.url, "read_only_db": not args.allow_db_writes},
                store=store,
            )
        except ValueError as e:  # e.g. engine not implemented
            print(f"error: {e}", file=sys.stderr)
            return 2
        meta = {
            "generated_at": _now_iso(),
            "engine": engine_name,
            "model": os.getenv("OPENAI_MODEL", "gpt-5-mini"),
            "subset": subset_label,
            "case_ids": [c.id for c in cases],
            "repeat": args.repeat,
            "db": db,
            "judge": args.judge,
            "judge_model": judge_model_name(args.judge_model) if args.judge else None,
            "budgets": {"p90_s": args.p90_budget, "max_turn_s": args.max_turn_budget,
                        "max_turn_tokens": args.token_budget},
        }

    summary = summarize(results, args.p90_budget, args.max_turn_budget)
    report = build_report(results, meta, summary)

    print("\n=== Summary ===")
    print(json.dumps({k: v for k, v in summary.items() if k not in ("stability",)}, indent=2, default=str))
    if "stability" in summary:
        print("stability: " + ", ".join(f"{k}={v}" for k, v in summary["stability"].items()))

    failed = [r for r in results if r.status in ("fail", "error")]
    if failed:
        print("\nFailed runs:")
        for r in failed:
            print(f"  {r.case_id} (run {r.run}): {'; '.join(r.failures[:3]) or r.error}")

    if args.out:
        out_path = os.path.abspath(args.out)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(report, f, indent=1, default=str)
        print(f"\nReport written to {out_path}")
    if args.save_baseline:
        print(f"Baseline saved to {bl.save(report, args.save_baseline)}")
    if args.compare:
        print()
        print(bl.format_diff(bl.diff(bl.load(args.compare), report), args.show_all))

    green = run_is_green(summary, args.strict)
    print(f"\nRESULT: {'GREEN' if green else 'RED'}" + (" (strict)" if args.strict else ""))
    return 0 if green else 1


if __name__ == "__main__":
    sys.exit(main())
