"""Unit tests for pricing and per-model usage accounting (app/middleware/usage_tracker.py)."""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.middleware.usage_tracker import (
    estimate_cost,
    get_pricing,
    record_llm_usage,
    validate_configured_models,
)


def test_unknown_model_raises():
    with pytest.raises(ValueError):
        get_pricing("gpt-imaginary")
    with pytest.raises(ValueError):
        estimate_cost("gpt-imaginary", 10, 10)


def test_dated_snapshot_uses_base_price():
    assert get_pricing("gpt-5-mini-2025-08-07") == get_pricing("gpt-5-mini")


def test_cost_gpt5_mini_and_nano():
    # 1M input + 1M output tokens at list price
    assert estimate_cost("gpt-5-mini", 1_000_000, 1_000_000) == pytest.approx(0.25 + 2.00)
    assert estimate_cost("gpt-5-nano", 1_000_000, 1_000_000) == pytest.approx(0.05 + 0.40)
    # cached input billed at the cached rate
    assert estimate_cost("gpt-5-mini", 1_000_000, 0, cached_input_tokens=1_000_000) == pytest.approx(0.025)


def test_cost_uses_llm_prices():
    # One pricing table (llm.PRICES, USD per 1M tokens)
    assert estimate_cost("gpt-6-luna", 1_000_000, 1_000_000) == pytest.approx(0.10 + 0.50)
    assert estimate_cost("gpt-6-luna", 1_000_000, 0, cached_input_tokens=1_000_000) == pytest.approx(0.01)
    get_pricing("gemini-3.5-flash-lite")
    get_pricing("claude-sonnet-5")


def test_configured_models_must_be_priced(monkeypatch):
    for var in ("AGENT_MODEL", "SUMMARY_MODEL", "NEWS_ENRICHMENT_MODEL", "EVAL_JUDGE_MODEL"):
        monkeypatch.delenv(var, raising=False)
    validate_configured_models()  # defaults (gpt-6-luna) are priced
    monkeypatch.setenv("AGENT_MODEL", "gpt-5-mini")
    validate_configured_models()
    monkeypatch.setenv("SUMMARY_MODEL", "gpt-imaginary")
    with pytest.raises(ValueError):
        validate_configured_models()
    monkeypatch.delenv("SUMMARY_MODEL")
    monkeypatch.setenv("EVAL_JUDGE_MODEL", "gpt-imaginary")
    with pytest.raises(ValueError):
        validate_configured_models()


def test_removed_model_env_vars_are_ignored(monkeypatch):
    for var in ("AGENT_MODEL", "SUMMARY_MODEL", "NEWS_ENRICHMENT_MODEL", "EVAL_JUDGE_MODEL"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("OPENAI_MODEL_FAST", "gpt-imaginary")
    validate_configured_models()  # warns, does not select a model


def test_record_llm_usage_by_model():
    state = {}
    usage = SimpleNamespace(
        prompt_tokens=100, completion_tokens=20,
        prompt_tokens_details=SimpleNamespace(cached_tokens=40),
    )
    record_llm_usage(state, usage, "gpt-5-mini-2025-08-07")
    record_llm_usage(state, {"input_tokens": 10, "output_tokens": 5, "model": "gpt-5-nano"})

    totals = state["token_usage"]
    assert (totals["input_tokens"], totals["output_tokens"], totals["cached_input_tokens"]) == (110, 25, 40)
    assert totals["by_model"]["gpt-5-mini"] == {"input_tokens": 100, "output_tokens": 20, "cached_input_tokens": 40}
    assert totals["by_model"]["gpt-5-nano"]["input_tokens"] == 10


def test_record_llm_usage_accepts_llm_usage():
    from app.agent.v3.llm import Usage
    state = {}
    record_llm_usage(state, Usage(input_tokens=50, cached_input_tokens=30, output_tokens=7), "gpt-6-luna")
    assert state["token_usage"]["by_model"]["gpt-6-luna"] == {
        "input_tokens": 50, "output_tokens": 7, "cached_input_tokens": 30}
