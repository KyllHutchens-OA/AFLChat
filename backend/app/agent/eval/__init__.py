"""
Footy-NAC chat eval harness.

Usage (from backend/):
    venv/bin/python -m app.agent.eval --subset smoke15 [--judge] [--ws] [--out path.json]

Modules:
    models  - EvalCase / TurnResult / EvalResult
    cases   - smoke15 gate set, salvaged legacy suite, eval_queries.txt parsing, subsets
    runner  - InProcessRunner (drives AFLAnalyticsAgent.run directly) and WsRunner
    scorer  - deterministic checks + optional LLM judge
    cli     - argparse entry point (also exposed via __main__)
"""
from app.agent.eval.models import CHECK_NAMES, EvalCase, EvalResult, TurnResult

__all__ = ["CHECK_NAMES", "EvalCase", "EvalResult", "TurnResult"]
