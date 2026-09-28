"""
Eval scoring.

1. Deterministic checks (`score_case`): pure functions of (case, turns,
   truth_rows, budgets). No LLM, no network. Axes (see models.CHECK_NAMES):

     facts         static expected_facts / expected_any / forbidden strings
     truth_text    live truth Facts found in the answer text
     truth_rows    live truth Facts / PairChecks found in the agent's rows
     chart         presence/absence, ChartSpecV1 validity, chartType,
                   series count, unique x per series, min points, labels
     chart_values  plotted values equal live DB values (pairs, scatter)
     no_data       expects_no_data -> explains WHY, not a generic fallback
     correction    final answer materially differs from the first turn's
     behaviour     refusal / clarification / disambiguation / DB integrity
     sql           expected SQL substrings present; forbidden SQL absent
     budget        per-turn latency and token budgets (gates in --strict)

   A Fact with several `where` targets passes if found in ANY of them, and is
   scored on the axis of the first target listed ("text" -> truth_text,
   "rows"/"chart" -> truth_rows).

2. LLM judge (`judge_case`): TRIAGE ONLY. It sees the live truth rows and the
   agent's rows as evidence and returns a verdict that is reported next to
   the deterministic result (disagreements are listed for a human to look
   at). It never changes pass/fail. Model: --judge-model / EVAL_JUDGE_MODEL /
   AGENT_MODEL, called through app.agent.v3.llm, so a different model family
   (e.g. claude-sonnet-5) works once its API key is set.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent.eval import assertions as A
from app.agent.eval.models import (
    CORRECTNESS_CHECKS,
    EvalCase,
    Fact,
    PairCheck,
    TurnResult,
)

logger = logging.getLogger(__name__)

# Fragments of the pre-restructure generic fallback template. A no-data
# response containing any of these is NOT an explanation.
GENERIC_FALLBACK_MARKERS = [
    "i had trouble finding an answer",
    "try rephrasing",
    "unable to process your query",
    "no rows matched",
]

# Words that signal the response explains WHY there is no data.
NO_DATA_EXPLANATION_KEYWORDS = [
    "covers", "coverage", "outside", "debut", "no stats", "no data",
    "no recorded", "not recorded", "doesn't have", "does not have", "don't have",
    "do not have", "not in", "only have", "earliest",
    "hasn't played", "has not played", "didn't play", "did not play",
    "couldn't find", "could not find", "not available", "isn't available",
    "wasn't recorded", "weren't recorded", "starts in", "starts from", "begins in",
]

# Coverage caveat: the answer admits the data is partial.
COVERAGE_CAVEAT_MARKERS = [
    "limited", "partial", "missing", "incomplete", "not available", "unavailable", "coverage",
    "gap", "only have", "only available", "not recorded", "no attendance", "sparse",
    "no data", "excluded", "note:", "caveat", "covid", "not all",
]

# Refusal: the answer must steer back to AFL.
REFUSAL_REDIRECT_MARKERS = ["afl", "footy", "football", "aussie rules"]

# Clarification: a question back to the user.
CLARIFICATION_MARKERS = [
    "which", "what do you mean", "do you mean", "did you mean", "could you",
    "can you", "clarify", "specify", "best at", "what kind", "by what",
    "which metric", "which player", "which season", "let me know",
    "more specific", "narrow",
]

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _contains(haystack: str, needle: str) -> bool:
    """Case-insensitive, word-boundary-aware substring check."""
    pattern = r"(?<!\w)" + re.escape(needle.lower()) + r"(?!\w)"
    return re.search(pattern, haystack.lower()) is not None


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _final_haystack(turns: List[TurnResult]) -> str:
    """Response text + serialized chart spec of the final turn."""
    if not turns:
        return ""
    last = turns[-1]
    parts = [last.response_text or ""]
    if last.chart_spec:
        try:
            parts.append(json.dumps(last.chart_spec, default=str))
        except (TypeError, ValueError):
            parts.append(str(last.chart_spec))
    return " ".join(parts)


def _all_sql(turns: List[TurnResult]) -> str:
    """SQL/tool args that actually EXECUTED (blocked or failed attempts are harmless)."""
    parts = []
    for t in turns:
        if not t.tool_calls:
            parts.append(t.sql or "")  # engines without a call trace
        for c in t.tool_calls:
            if c.error is None and c.row_count is not None:
                parts.append(c.sql or "")
                parts.append(json.dumps(c.args, default=str))
    return "\n".join(parts).lower()


def _is_clarification(text: str) -> bool:
    lowered = (text or "").lower()
    return "?" in lowered and any(m in lowered for m in CLARIFICATION_MARKERS)


# ---------------------------------------------------------------------------
# Static checks (unchanged semantics from M5)
# ---------------------------------------------------------------------------
def _check_facts(case: EvalCase, turns: List[TurnResult], fails: List[str]) -> Optional[bool]:
    if not (case.expected_facts or case.expected_any or case.forbidden):
        return None
    haystack = _final_haystack(turns)
    if not haystack.strip():
        fails.append("facts: empty response")
        return False
    ok = True
    missing = [f for f in case.expected_facts if not _contains(haystack, f)]
    if missing:
        fails.append(f"facts: missing {missing}")
        ok = False
    if case.expected_any and not any(_contains(haystack, f) for f in case.expected_any):
        fails.append(f"facts: none of {case.expected_any}")
        ok = False
    present = [f for f in case.forbidden if _contains(haystack, f)]
    if present:
        fails.append(f"facts: forbidden present {present}")
        ok = False
    return ok


def _chart_spec_valid(spec: Dict[str, Any]) -> bool:
    try:
        from pydantic import ValidationError

        from app.visualization.spec import ChartSpecV1
    except ImportError:  # pragma: no cover
        return False
    try:
        ChartSpecV1.model_validate(spec)
        return True
    except ValidationError as e:
        logger.warning(f"Chart spec failed ChartSpecV1 validation: {e}")
        return False


def _check_no_data(case: EvalCase, turns: List[TurnResult], fails: List[str]) -> Optional[bool]:
    if not case.expects_no_data:
        return None
    response = (turns[-1].response_text or "") if turns else ""
    lowered = response.lower()
    if not lowered.strip() or any(m in lowered for m in GENERIC_FALLBACK_MARKERS):
        fails.append("no_data: empty or generic fallback")
        return False
    ok = _YEAR_RE.search(response) is not None or any(kw in lowered for kw in NO_DATA_EXPLANATION_KEYWORDS)
    if not ok:
        fails.append("no_data: no explanation of why")
    return ok


def _check_correction(case: EvalCase, turns: List[TurnResult], fails: List[str]) -> Optional[bool]:
    if not case.is_correction:
        return None
    if len(turns) < 2:
        fails.append("correction: fewer than 2 turns")
        return False
    # Compare against the turn before the correction (the last one).
    before = _normalize(turns[-2].response_text)
    last = _normalize(turns[-1].response_text)
    ok = bool(last) and before != last
    if not ok:
        fails.append("correction: final answer unchanged")
    return ok


def _check_sql(case: EvalCase, turns: List[TurnResult], fails: List[str]) -> Optional[bool]:
    results = []
    if case.expected_sql_substrings:
        sql = (turns[-1].sql or "") if turns else ""
        # SQL is not available in --engine v2-ws; not applicable then.
        if sql:
            missing = [f for f in case.expected_sql_substrings if f.lower() not in sql.lower()]
            if missing:
                fails.append(f"sql: missing {missing}")
            results.append(not missing)
    if case.forbidden_sql:
        all_sql = _all_sql(turns)
        present = [f for f in case.forbidden_sql if f.lower() in all_sql]
        if present:
            fails.append(f"sql: forbidden {present}")
        results.append(not present)
    return all(results) if results else None


# ---------------------------------------------------------------------------
# Live-truth checks
# ---------------------------------------------------------------------------
def _fact_rows(fact: Fact, truth: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if fact.all_rows:
        return truth[: fact.top] if fact.top else truth
    return [truth[fact.row]] if fact.row < len(truth) else []


def _fact_found(fact: Fact, value: Any, turn: TurnResult) -> bool:
    num = A.as_number(value)
    for where in fact.where:
        if where == "text":
            text = turn.response_text or ""
            if fact.render == "ordinal" and num is not None:
                if A.text_has_ordinal(text, num):
                    return True
            elif num is not None:
                if A.text_has_number(text, num, fact.tol):
                    return True
            elif value is not None and A.text_has_name(text, str(value)):
                return True
        elif where == "rows":
            if A.rows_have_value(turn.rows, value, fact.tol):
                return True
        elif where == "chart":
            if turn.chart_spec and A.chart_has_value(turn.chart_spec, value, fact.tol):
                return True
    return False


def _check_truth_facts(
    case: EvalCase, turn: TurnResult, truth: List[Dict[str, Any]], fails: List[str]
) -> Tuple[Optional[bool], Optional[bool]]:
    """(truth_text, truth_rows) from case.truth + case.pairs."""
    text_res: List[bool] = []
    rows_res: List[bool] = []
    for fact in case.truth:
        axis = text_res if fact.where[0] == "text" else rows_res
        for r in _fact_rows(fact, truth):
            cols = [fact.col] + fact.alts
            values = [r.get(c) for c in cols if c in r]
            if not values:
                fails.append(f"truth: column {fact.col!r} not in truth rows")
                axis.append(False)
                continue
            ok = any(_fact_found(fact, v, turn) for v in values if v is not None)
            if not ok:
                shown = values[0] if len(values) == 1 else values
                fails.append(f"truth[{'/'.join(fact.where)}]: {fact.col}={shown!r} not found")
            axis.append(ok)
    for pc in case.pairs:
        ok = _check_pairs(pc, truth, turn, fails)
        rows_res.append(ok)
    return (all(text_res) if text_res else None, all(rows_res) if rows_res else None)


def _check_pairs(pc: PairCheck, truth: List[Dict[str, Any]], turn: TurnResult, fails: List[str]) -> bool:
    rows = truth[: pc.top] if pc.top else truth
    if not rows:
        return True
    misses = []
    for r in rows:
        key, value = r.get(pc.key), r.get(pc.value)
        series = r.get(pc.series) if pc.series else None
        values = [v for v in [value] + [r.get(a) for a in pc.alts] if v is not None]
        if pc.where == "rows":
            hit = any(A.row_pair_match(turn.rows, key, v, series, pc.tol) for v in values)
        else:
            hit = bool(turn.chart_spec) and any(
                A.chart_pair_match(turn.chart_spec, key, v, series, pc.tol) for v in values)
        if not hit:
            misses.append(f"{key}{'/' + str(series) if series is not None else ''}={value}")
    frac = 1 - len(misses) / len(rows)
    ok = frac >= pc.min_frac - 1e-9
    if not ok:
        fails.append(f"pairs[{pc.where}] {pc.key}->{pc.value}: {len(misses)}/{len(rows)} wrong, e.g. {misses[:4]}")
    return ok


def _check_chart(
    case: EvalCase, turn: Optional[TurnResult], truth: List[Dict[str, Any]], fails: List[str]
) -> Tuple[Optional[bool], Optional[bool]]:
    """(chart, chart_values)."""
    spec = turn.chart_spec if turn else None
    exp = case.chart
    if case.expects_no_chart:
        if spec is not None:
            fails.append(f"chart: expected none, got {spec.get('chartType')}")
        return spec is None, None
    if not (case.expects_chart or exp):
        return None, None
    if spec is None:
        fails.append("chart: expected a chart, none emitted")
        return False, (False if exp and (exp.pairs or exp.scatter_truth) else None)
    if not _chart_spec_valid(spec):
        fails.append("chart: spec fails ChartSpecV1 validation")
        return False, None
    if exp is None:
        return True, None

    ok = True
    ctype = spec.get("chartType")
    n_series = len(spec.get("series") or [])
    if ctype == "scatter":
        n_series = len({d.get("group") for d in spec.get("data") or []}) or 1
    if exp.types and ctype not in exp.types:
        fails.append(f"chart: type {ctype!r} not in {exp.types}")
        ok = False
    if exp.series is not None and n_series != exp.series:
        fails.append(f"chart: {n_series} series, expected {exp.series}")
        ok = False
    if exp.min_series is not None and n_series < exp.min_series:
        fails.append(f"chart: {n_series} series, expected >= {exp.min_series}")
        ok = False
    if exp.max_series is not None and n_series > exp.max_series:
        fails.append(f"chart: {n_series} series, expected <= {exp.max_series}")
        ok = False
    if exp.unique_x and ctype not in ("pie", "scatter"):
        dups = A.duplicate_x(spec)
        if dups:
            fails.append(f"chart: duplicate x values {sorted(set(dups))[:5]}")
            ok = False
    if exp.min_points is not None and len(spec.get("data") or []) < exp.min_points:
        fails.append(f"chart: {len(spec.get('data') or [])} points, expected >= {exp.min_points}")
        ok = False
    if exp.labels:
        labels = A.chart_labels(spec)
        missing = [l for l in exp.labels if not any(A.label_matches(x, l) for x in labels)]
        if missing:
            fails.append(f"chart: requested labels not plotted {missing}")
            ok = False

    values: List[bool] = []
    for pc in exp.pairs:
        pc_chart = pc.model_copy(update={"where": "chart"})
        values.append(_check_pairs(pc_chart, truth, turn, fails))
    if exp.scatter_truth:
        frac = A.scatter_match_frac(spec, truth, exp.scatter_truth["x"], exp.scatter_truth["y"])
        if frac < exp.scatter_min_frac:
            fails.append(f"chart: only {frac:.0%} of scatter points match DB pairs")
        values.append(frac >= exp.scatter_min_frac)
    return ok, (all(values) if values else None)


def _check_behaviour(
    case: EvalCase,
    turns: List[TurnResult],
    integrity: Optional[bool],
    fails: List[str],
    caveat_required: bool = False,
) -> Optional[bool]:
    res: List[bool] = []
    text = (turns[-1].response_text or "") if turns else ""
    lowered = text.lower()
    if caveat_required:
        ok = any(m in lowered for m in COVERAGE_CAVEAT_MARKERS)
        if not ok:
            fails.append("behaviour: data is partial but the answer has no coverage caveat")
        res.append(ok)
    if case.expects_refusal:
        redirect = any(m in lowered for m in REFUSAL_REDIRECT_MARKERS)
        charted = bool(turns and turns[-1].chart_spec)
        if not redirect:
            fails.append("behaviour: refusal does not redirect to AFL")
        if charted:
            fails.append("behaviour: refusal emitted a chart")
        res.append(redirect and not charted)
    if case.expects_clarification:
        ok = _is_clarification(text) and not (turns and turns[-1].chart_spec)
        if not ok:
            fails.append("behaviour: no clarifying question")
        res.append(ok)
    if case.disambiguate:
        all_named = all(_contains(text, d) for d in case.disambiguate)
        ok = all_named or _is_clarification(text)
        if not ok:
            fails.append(f"behaviour: did not disambiguate {case.disambiguate} or ask which")
        res.append(ok)
    if integrity is not None:
        if not integrity:
            fails.append("behaviour: DB integrity check changed after the case ran")
        res.append(integrity)
    return all(res) if res else None


def _check_budget(
    case: EvalCase, turns: List[TurnResult], max_turn_s: float, max_turn_tokens: int, fails: List[str]
) -> Optional[bool]:
    if not turns:
        return None
    lim_s = case.budget.max_turn_s or max_turn_s
    lim_t = case.budget.max_turn_tokens or max_turn_tokens
    ok = True
    for i, t in enumerate(turns):
        if t.latency_s is not None and t.latency_s > lim_s:
            fails.append(f"budget: turn {i + 1} took {t.latency_s:.1f}s > {lim_s:.0f}s")
            ok = False
        if lim_t and t.total_tokens > lim_t:
            fails.append(f"budget: turn {i + 1} used {t.total_tokens} tokens > {lim_t}")
            ok = False
    return ok


def score_case(
    case: EvalCase,
    turns: List[TurnResult],
    truth: Optional[List[Dict[str, Any]]] = None,
    integrity_ok: Optional[bool] = None,
    max_turn_s: float = 30.0,
    max_turn_tokens: int = 20000,
    caveat_required: bool = False,
) -> Tuple[Dict[str, Optional[bool]], bool, List[str]]:
    """Run all deterministic checks. Returns (checks, passed, failure_reasons)."""
    truth = truth or []
    fails: List[str] = []
    last = turns[-1] if turns else None
    truth_text, truth_rows = (None, None)
    if last is not None and (case.truth or case.pairs):
        truth_text, truth_rows = _check_truth_facts(case, last, truth, fails)
    elif case.truth or case.pairs:
        truth_text = False
        fails.append("truth: no turns")
    chart, chart_values = _check_chart(case, last, truth, fails)
    checks: Dict[str, Optional[bool]] = {
        "facts": _check_facts(case, turns, fails),
        "truth_text": truth_text,
        "truth_rows": truth_rows,
        "chart": chart,
        "chart_values": chart_values,
        "no_data": _check_no_data(case, turns, fails),
        "correction": _check_correction(case, turns, fails),
        "behaviour": _check_behaviour(case, turns, integrity_ok, fails, caveat_required),
        "sql": _check_sql(case, turns, fails),
        "budget": _check_budget(case, turns, max_turn_s, max_turn_tokens, fails),
    }
    applicable = [checks[k] for k in CORRECTNESS_CHECKS if checks[k] is not None]
    if not applicable:
        # Bare exploratory queries: pass iff a non-empty answer came back.
        passed = bool(last and (last.response_text or "").strip())
    else:
        passed = all(applicable)
    return checks, passed, fails


# ---------------------------------------------------------------------------
# LLM judge (triage only)
# ---------------------------------------------------------------------------
JUDGE_VERDICTS = {"correct", "partially_correct", "incorrect", "cannot_judge"}

_JUDGE_PROMPT = """You are triaging an AFL statistics assistant's answer.

User query (final turn{multi_turn_note}):
{query}

{expectations}

DATABASE EVIDENCE (ground truth computed live from the app's database; trust
this over your own memory):
{truth}

Rows the assistant retrieved:
{agent_rows}

Assistant's final response:
\"\"\"{response}\"\"\"

Chart emitted: {chart_summary}
{chart_data}

Grade factual correctness against the DATABASE EVIDENCE and appropriateness
(refusals, clarifying questions). Do not use outside knowledge to overrule
the evidence.
Respond with JSON: {{"verdict": "correct" | "partially_correct" | "incorrect" | "cannot_judge", "reason": "<one sentence>"}}
"""


def _build_judge_client():
    """Kept for the cli signature; judge calls go through app.agent.v3.llm (any provider)."""
    return None


def judge_model_name(model: Optional[str] = None) -> str:
    from app.agent.v3.llm import model_for

    return model or os.getenv("EVAL_JUDGE_MODEL") or model_for("AGENT_MODEL")


def judge_case(
    case: EvalCase,
    turns: List[TurnResult],
    truth: Optional[List[Dict[str, Any]]] = None,
    client: Any = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """LLM-triage the final turn with DB rows as evidence. Never gates."""
    if client is None:
        client = _build_judge_client()
    model = judge_model_name(model)

    lines = []
    if case.description:
        lines.append(f"- Case intent: {case.description}")
    if case.expects_chart or case.chart:
        lines.append("- A chart was expected.")
    if case.expects_no_data:
        lines.append("- No matching data exists; the response should clearly explain WHY.")
    if case.expects_refusal:
        lines.append("- The request is off-topic or malicious; it should be politely refused and redirected to AFL.")
    if case.expects_clarification:
        lines.append("- The question is ambiguous; a clarifying question is the right answer.")
    if case.is_correction:
        lines.append("- The final turn corrects the previous one; the answer must reflect the correction.")
    if case.notes:
        lines.append(f"- Grader notes: {case.notes}")
    expectations = "Expectations:\n" + "\n".join(lines) if lines else "Expectations: none recorded."

    last = turns[-1] if turns else None
    chart_data = ""
    if last and last.chart_spec:
        spec = last.chart_spec
        chart_data = (
            f"Chart data: type={spec.get('chartType')}, title={spec.get('title')!r}, "
            f"series={[s.get('key') for s in spec.get('series', [])]}, "
            f"rows={json.dumps(spec.get('data', [])[:15], default=str)}"
        )
    multi_turn_note = "; earlier turns: " + " | ".join(case.queries[:-1]) if case.multi_turn else ""
    prompt = _JUDGE_PROMPT.format(
        multi_turn_note=multi_turn_note,
        query=case.queries[-1],
        expectations=expectations,
        truth=json.dumps((truth or [])[:20], default=str) if truth else "(none for this case)",
        agent_rows=json.dumps((last.rows if last else [])[:15], default=str) or "[]",
        response=(last.response_text if last else "")[:2500],
        chart_summary="yes" if (last and last.chart_spec) else "no",
        chart_data=chart_data,
    )
    try:
        from app.agent.v3.llm import complete as llm_complete, parse_json

        response = llm_complete(prompt, model=model, json_mode=True, effort="low")
        data = parse_json(response.text)
        verdict = data.get("verdict")
        if verdict not in JUDGE_VERDICTS:
            verdict = "cannot_judge"
        return {"verdict": verdict, "reason": str(data.get("reason", ""))[:500], "model": model}
    except Exception as e:  # judge failures must never sink the run
        logger.error(f"Judge call failed for case {case.id}: {type(e).__name__}: {e}")
        return {"verdict": "cannot_judge", "reason": f"judge error: {type(e).__name__}: {e}", "model": model}
