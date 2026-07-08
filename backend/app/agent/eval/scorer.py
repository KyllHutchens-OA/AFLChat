"""
Eval scoring.

Two layers:

1. Deterministic checks (`score_case`) — pure functions of (EvalCase, turns),
   no LLM, no network:
     facts       expected_facts all present, >=1 expected_any present, no
                 forbidden strings — matched word-boundary, case-insensitive,
                 against the FINAL turn's response text + serialized chart spec
     chart       expects_chart -> a chart spec is present on the final turn AND
                 validates against ChartSpecV1;
                 expects_no_chart -> no chart spec was emitted
     no_data     expects_no_data -> the response explains WHY (mentions a year
                 or a coverage/debut keyword) and is not the old generic
                 "I had trouble finding an answer... try rephrasing" fallback
     correction  is_correction -> the final turn's answer materially differs
                 from the first turn's
     sql         expected_sql_substrings all appear in the final turn's SQL

   Each check is True/False when applicable, None when not. A case passes iff
   every applicable check is True.

2. Optional LLM judge (`judge_case`) — a gpt-5-mini (OPENAI_MODEL) call that
   grades the final response against the case's expected facts / notes and
   returns {"verdict": correct|partially_correct|incorrect|cannot_judge,
   "reason": ...}. Enabled with --judge; never affects the deterministic
   pass/fail gate.
"""
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.agent.eval.models import EvalCase, TurnResult

logger = logging.getLogger(__name__)

# Fragments of the pre-restructure generic fallback template. A no-data
# response containing any of these is NOT an explanation.
GENERIC_FALLBACK_MARKERS = [
    "i had trouble finding an answer",
    "try rephrasing",
    "unable to process your query",
]

# Words that signal the response explains WHY there is no data.
NO_DATA_EXPLANATION_KEYWORDS = [
    "covers",
    "coverage",
    "outside",
    "debut",
    "no stats",
    "no data",
    "no recorded",
    "doesn't have",
    "does not have",
    "don't have",
    "do not have",
    "not in",
    "only have",
    "earliest",
    "no results",
    "no rows",
    "hasn't played",
    "has not played",
    "didn't play",
    "did not play",
    "couldn't find",
    "could not find",
]

_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def _contains(haystack: str, needle: str) -> bool:
    """Case-insensitive, word-boundary-aware substring check.

    Word boundaries stop "9" matching inside "1990" while still matching
    "9 wins", "120-60", "(9)". Multi-word needles work unchanged.
    """
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


def _check_facts(case: EvalCase, turns: List[TurnResult]) -> Optional[bool]:
    if not (case.expected_facts or case.expected_any or case.forbidden):
        return None
    haystack = _final_haystack(turns)
    if not haystack.strip():
        return False
    if not all(_contains(haystack, f) for f in case.expected_facts):
        return False
    if case.expected_any and not any(_contains(haystack, f) for f in case.expected_any):
        return False
    if any(_contains(haystack, f) for f in case.forbidden):
        return False
    return True


def _chart_spec_valid(spec: Dict[str, Any]) -> bool:
    """True iff the spec validates against the ChartSpecV1 contract."""
    try:
        from app.visualization.spec import ChartSpecV1
        from pydantic import ValidationError
    except ImportError:  # pragma: no cover - contract module always present
        logger.error("ChartSpecV1 unavailable; cannot validate chart spec")
        return False
    try:
        ChartSpecV1.model_validate(spec)
        return True
    except ValidationError as e:
        logger.warning(f"Chart spec failed ChartSpecV1 validation: {e}")
        return False


def _check_chart(case: EvalCase, turns: List[TurnResult]) -> Optional[bool]:
    spec = turns[-1].chart_spec if turns else None
    if case.expects_chart:
        return spec is not None and _chart_spec_valid(spec)
    if case.expects_no_chart:
        return spec is None
    return None


def _check_no_data(case: EvalCase, turns: List[TurnResult]) -> Optional[bool]:
    if not case.expects_no_data:
        return None
    response = (turns[-1].response_text or "") if turns else ""
    lowered = response.lower()
    if not lowered.strip():
        return False
    if any(marker in lowered for marker in GENERIC_FALLBACK_MARKERS):
        return False
    has_year = _YEAR_RE.search(response) is not None
    has_keyword = any(kw in lowered for kw in NO_DATA_EXPLANATION_KEYWORDS)
    return has_year or has_keyword


def _check_correction(case: EvalCase, turns: List[TurnResult]) -> Optional[bool]:
    if not case.is_correction:
        return None
    if len(turns) < 2:
        return False
    first = _normalize(turns[0].response_text)
    last = _normalize(turns[-1].response_text)
    return bool(last) and first != last


def _check_sql(case: EvalCase, turns: List[TurnResult]) -> Optional[bool]:
    if not case.expected_sql_substrings:
        return None
    sql = (turns[-1].sql or "") if turns else ""
    # SQL text is not available in --ws mode (the wire doesn't carry it);
    # treat as not-applicable rather than failing the case.
    if not sql:
        return None
    lowered = sql.lower()
    return all(fragment.lower() in lowered for fragment in case.expected_sql_substrings)


def score_case(case: EvalCase, turns: List[TurnResult]) -> Tuple[Dict[str, Optional[bool]], bool]:
    """Run all deterministic checks. Returns (checks, passed)."""
    checks: Dict[str, Optional[bool]] = {
        "facts": _check_facts(case, turns),
        "chart": _check_chart(case, turns),
        "no_data": _check_no_data(case, turns),
        "correction": _check_correction(case, turns),
        "sql": _check_sql(case, turns),
    }
    applicable = [v for v in checks.values() if v is not None]
    # A case with no applicable checks (bare eval_queries.txt entries) counts
    # as passed deterministically iff the agent produced a non-empty response
    # without a harness error — correctness is then the judge's job.
    if not applicable:
        passed = bool(turns and (turns[-1].response_text or "").strip())
    else:
        passed = all(applicable)
    return checks, passed


# ---------------------------------------------------------------------------
# Optional LLM judge
# ---------------------------------------------------------------------------
JUDGE_VERDICTS = {"correct", "partially_correct", "incorrect", "cannot_judge"}

_JUDGE_PROMPT = """You are grading an AFL statistics assistant's answer.

User query (final turn{multi_turn_note}):
{query}

{expectations}

Assistant's final response:
\"\"\"{response}\"\"\"

Chart emitted: {chart_summary}
{chart_data}

Grade ONLY factual correctness and appropriateness against the expectations.
Respond with JSON: {{"verdict": "correct" | "partially_correct" | "incorrect" | "cannot_judge", "reason": "<one sentence>"}}
Use "cannot_judge" only when no expectations are given and the answer's facts
cannot be assessed from the information provided.
"""


def _build_judge_client():
    """OpenAI client using the project's standard construction pattern."""
    import httpx
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("OPENAI_API_KEY"),
        timeout=httpx.Timeout(60.0, connect=10.0),
    )


def judge_case(
    case: EvalCase,
    turns: List[TurnResult],
    client: Any = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """LLM-judge the final turn's response against the case expectations."""
    if client is None:
        client = _build_judge_client()
    model = model or os.getenv("OPENAI_MODEL", "gpt-5-mini")

    expectation_lines = []
    if case.expected_facts:
        expectation_lines.append(f"- Must contain ALL of: {case.expected_facts}")
    if case.expected_any:
        expectation_lines.append(f"- Must contain at least ONE of: {case.expected_any}")
    if case.forbidden:
        expectation_lines.append(f"- Must contain NONE of: {case.forbidden}")
    if case.expects_chart:
        expectation_lines.append("- A chart was expected.")
    if case.expects_no_data:
        expectation_lines.append(
            "- No matching data exists; the response should clearly explain WHY."
        )
    if case.is_correction:
        expectation_lines.append(
            "- The final turn is a user correction; the answer must reflect the corrected question."
        )
    if case.notes:
        expectation_lines.append(f"- Grader notes: {case.notes}")
    if case.verification_sql:
        expectation_lines.append(f"- Ground truth was established via: {case.verification_sql}")
    expectations = (
        "Expectations:\n" + "\n".join(expectation_lines)
        if expectation_lines
        else "Expectations: none recorded — grade general plausibility/appropriateness."
    )

    last = turns[-1] if turns else None
    chart_summary = "yes" if (last and last.chart_spec) else "no"
    chart_data = ""
    if last and last.chart_spec:
        spec = last.chart_spec
        try:
            chart_data = (
                "Chart data (what the user sees plotted): "
                f"type={spec.get('chartType')}, title={spec.get('title')!r}, "
                f"rows={json.dumps(spec.get('data', [])[:15], default=str)}"
            )
        except (TypeError, ValueError):
            chart_data = ""
    multi_turn_note = ""
    query = case.queries[-1]
    if case.multi_turn:
        multi_turn_note = "; earlier turns: " + " | ".join(case.queries[:-1])

    prompt = _JUDGE_PROMPT.format(
        multi_turn_note=multi_turn_note,
        query=query,
        expectations=expectations,
        response=(last.response_text if last else "")[:2000],
        chart_summary=chart_summary,
        chart_data=chart_data,
    )

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            reasoning_effort="low",
        )
        raw = (response.choices[0].message.content or "").strip()
        data = json.loads(raw)
        verdict = data.get("verdict")
        if verdict not in JUDGE_VERDICTS:
            verdict = "cannot_judge"
        return {"verdict": verdict, "reason": str(data.get("reason", ""))[:500]}
    except Exception as e:  # judge failures must never sink the run
        logger.error(f"Judge call failed for case {case.id}: {type(e).__name__}: {e}")
        return {"verdict": "cannot_judge", "reason": f"judge error: {type(e).__name__}: {e}"}
