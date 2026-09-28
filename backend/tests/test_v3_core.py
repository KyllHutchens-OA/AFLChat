"""Unit tests for v3 plumbing that needs no DB or network."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.v3 import llm
from app.agent.v3.history import to_messages
from app.agent.v3.tools import TOOLS, tool_schemas


def test_cost_uses_cached_and_output_prices():
    u = llm.Usage(input_tokens=10_000, cached_input_tokens=6_000, output_tokens=1_000)
    # 4k uncached * 0.10 + 6k cached * 0.01 + 1k out * 0.50, per 1M
    assert llm.cost_usd("gpt-6-luna", u) == pytest.approx((4000 * 0.10 + 6000 * 0.01 + 1000 * 0.50) / 1e6)
    assert llm.cost_usd("gpt-6-luna", u, "flex") == pytest.approx(llm.cost_usd("gpt-6-luna", u) / 2)


def test_unknown_model_price_raises():
    with pytest.raises(llm.LLMError):
        llm.cost_usd("mystery-model", llm.Usage())


def test_provider_routing():
    assert llm.provider_for("gpt-6-luna") == "openai"
    assert llm.provider_for("gemini-3.5-flash-lite") == "gemini"
    assert llm.provider_for("claude-sonnet-5") == "anthropic"


def test_tool_schemas_are_strict():
    for spec in tool_schemas():
        p = spec["parameters"]
        assert p["additionalProperties"] is False
        assert set(p["required"]) == set(p["properties"]), spec["name"]
    assert "title" in next(s for s in tool_schemas() if s["name"] == "make_chart")["parameters"]["properties"]
    assert len(TOOLS) == 10


def test_history_renders_tool_calls_for_corrections():
    history = [
        {"role": "user", "content": "Most disposals in 2022?"},
        {"role": "assistant", "content": "Clayton Oliver, 753.",
         "tool_calls": [{"name": "leaderboard", "args": {"stat": "disposals", "season_from": 2022, "team": None},
                         "row_count": 10, "rows": [{"player": "Clayton Oliver", "disposals": 753}]}]},
    ]
    msgs = to_messages(history)
    assert msgs[0] == {"role": "user", "content": "Most disposals in 2022?"}
    assert '"stat": "disposals"' in msgs[1]["content"] and "team" not in msgs[1]["content"]
    assert msgs[1]["content"].endswith("Clayton Oliver, 753.")
