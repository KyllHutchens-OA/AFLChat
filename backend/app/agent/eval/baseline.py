"""
Baselines and per-case diffs.

A baseline is simply a full eval report JSON saved under
app/agent/eval/baselines/<name>.json (--save-baseline <name>). `--compare
<name-or-path>` diffs the current run against it; `--diff A B` diffs two
saved reports without running anything.

Per case (aggregated over repeats) the diff shows status changes
(pass/fail/flaky/skip), mean latency delta and mean token delta, then run
totals. Cases present in only one report are listed separately.
"""
import json
from pathlib import Path
from statistics import mean
from typing import Any, Dict, List, Optional

BASELINE_DIR = Path(__file__).resolve().parent / "baselines"


def resolve_path(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if p.suffix == ".json" and p.exists():
        return p
    candidate = BASELINE_DIR / (name_or_path if name_or_path.endswith(".json") else f"{name_or_path}.json")
    if candidate.exists():
        return candidate
    raise FileNotFoundError(f"No baseline '{name_or_path}' (looked at {p} and {candidate})")


def load(name_or_path: str) -> Dict[str, Any]:
    with open(resolve_path(name_or_path)) as f:
        return json.load(f)


def save(report: Dict[str, Any], name: str) -> Path:
    BASELINE_DIR.mkdir(parents=True, exist_ok=True)
    path = BASELINE_DIR / (name if name.endswith(".json") else f"{name}.json")
    with open(path, "w") as f:
        json.dump(report, f, indent=1, default=str)
    return path


def case_status(runs: List[Dict[str, Any]]) -> str:
    """pass | fail | flaky | skip | error for one case's runs."""
    statuses = {r.get("status", "pass" if r.get("passed") else "fail") for r in runs}
    if statuses == {"skip"}:
        return "skip"
    if statuses <= {"error"}:
        return "error"
    if statuses == {"pass"}:
        return "pass"
    if "pass" in statuses:
        return "flaky"
    return "fail"


def aggregate(report: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """case_id -> {status, pass_runs, runs, latency_s, tokens}."""
    by_case: Dict[str, List[Dict[str, Any]]] = {}
    for r in report.get("cases", []):
        by_case.setdefault(r["case_id"], []).append(r)
    out: Dict[str, Dict[str, Any]] = {}
    for cid, runs in by_case.items():
        ran = [r for r in runs if r.get("status") not in ("skip",)]
        lat = [sum(t.get("latency_s") or 0 for t in r.get("turns", [])) for r in ran]
        tok = [sum((t.get("input_tokens") or 0) + (t.get("output_tokens") or 0) for t in r.get("turns", [])) for r in ran]
        out[cid] = {
            "status": case_status(runs),
            "pass_runs": sum(r.get("status") == "pass" for r in runs),
            "runs": len(runs),
            "latency_s": round(mean(lat), 2) if lat else None,
            "tokens": round(mean(tok)) if tok else None,
            "skip_reason": next((r.get("skip_reason") for r in runs if r.get("skip_reason")), None),
        }
    return out


def _delta(a: Optional[float], b: Optional[float], fmt: str) -> str:
    if a is None or b is None:
        return "n/a"
    d = b - a
    return f"{d:+{fmt}}"


def diff(base: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
    """Structured per-case diff (base -> new)."""
    a, b = aggregate(base), aggregate(new)
    rows = []
    for cid in sorted(set(a) & set(b)):
        x, y = a[cid], b[cid]
        rows.append({
            "case_id": cid,
            "before": x["status"],
            "after": y["status"],
            "changed": x["status"] != y["status"],
            "latency_before": x["latency_s"],
            "latency_after": y["latency_s"],
            "tokens_before": x["tokens"],
            "tokens_after": y["tokens"],
        })
    return {
        "rows": rows,
        "only_in_base": sorted(set(a) - set(b)),
        "only_in_new": sorted(set(b) - set(a)),
        "summary_before": base.get("summary", {}),
        "summary_after": new.get("summary", {}),
    }


def format_diff(d: Dict[str, Any], show_all: bool = False) -> str:
    lines = []
    changed = [r for r in d["rows"] if r["changed"]]
    lines.append(f"=== Per-case diff ({len(changed)} status change(s) of {len(d['rows'])} shared cases) ===")
    order = {"pass": 0, "flaky": 1, "fail": 2, "error": 3, "skip": 4}
    for r in d["rows"]:
        if not (r["changed"] or show_all):
            continue
        arrow = ""
        # Transitions to/from skip are neither fixes nor regressions.
        if r["changed"] and "skip" not in (r["before"], r["after"]):
            arrow = "  FIXED" if order[r["after"]] < order[r["before"]] else "  REGRESSED"
        lines.append(
            f"  {r['case_id']:28s} {r['before']:>6s} -> {r['after']:<6s} "
            f"latency {_delta(r['latency_before'], r['latency_after'], '.1f')}s "
            f"tokens {_delta(r['tokens_before'], r['tokens_after'], '.0f')}{arrow}"
        )
    shared = [r for r in d["rows"] if r["latency_before"] is not None and r["latency_after"] is not None]
    if shared:
        lb = mean(r["latency_before"] for r in shared)
        la = mean(r["latency_after"] for r in shared)
        tb = mean((r["tokens_before"] or 0) for r in shared)
        ta = mean((r["tokens_after"] or 0) for r in shared)
        lines.append(f"  mean case latency {lb:.1f}s -> {la:.1f}s ({la - lb:+.1f}s); "
                     f"mean case tokens {tb:.0f} -> {ta:.0f} ({ta - tb:+.0f})")
    sb, sa = d["summary_before"], d["summary_after"]
    if sb and sa:
        lines.append(
            f"  passed {sb.get('passed')}/{sb.get('scored')} -> {sa.get('passed')}/{sa.get('scored')}; "
            f"p90 turn {sb.get('latency_s', {}).get('p90') if sb.get('latency_s') else None}s -> "
            f"{sa.get('latency_s', {}).get('p90') if sa.get('latency_s') else None}s"
        )
    if d["only_in_base"]:
        lines.append(f"  only in baseline: {', '.join(d['only_in_base'])}")
    if d["only_in_new"]:
        lines.append(f"  only in new run: {', '.join(d['only_in_new'])}")
    return "\n".join(lines)
