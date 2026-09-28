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


def test_configured_models_must_be_priced(monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "gpt-5-mini")
    validate_configured_models()
    monkeypatch.setenv("OPENAI_MODEL_FAST", "gpt-imaginary")
    with pytest.raises(ValueError):
        validate_configured_models()


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
