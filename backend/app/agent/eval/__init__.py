"""
Footy-NAC chat eval harness (engine-agnostic; the gate for 1E).

Usage (from backend/):
    venv/bin/python -m app.agent.eval --subset smoke [--engine v2|v3] [--repeat N] [--strict]
        [--judge] [--compare <baseline>] [--save-baseline <name>] [--truth-only]

Modules:
    models     EvalCase / Fact / PairCheck / ChartExpect / TurnResult / EvalResult
    sqlkit     verification-SQL builders (robust before and after 1C)
    case_bank  1D ground-truth case families
    cases      gate set, legacy salvaged + eval_queries.txt, subsets
    truth      live ground truth (read-only verification SQL at eval time)
    runner     EngineAdapter interface, engine registry, drive_case
    engines/   v2 (in-process), v2-ws (WebSocket); v3 added in 1E
    assertions number/name/chart matching against truth
    scorer     deterministic checks + LLM judge (triage only)
    baseline   save / load / per-case diff of reports (baselines/)
    cli        argparse entry point (also exposed via __main__)
"""
from app.agent.eval.models import CHECK_NAMES, EvalCase, EvalResult, TurnResult

__all__ = ["CHECK_NAMES", "EvalCase", "EvalResult", "TurnResult"]
