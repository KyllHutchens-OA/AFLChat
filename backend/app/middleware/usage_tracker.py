"""
API Usage Tracking for OpenAI cost control.
Tracks token usage per model and enforces per-visitor, per-IP and global daily limits.
Limits fail closed: if usage can't be read, the request is refused.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
import os
import re
import uuid
import logging

from sqlalchemy import String, cast, func
from app.data.database import Session

logger = logging.getLogger(__name__)

# Prices and model env vars live in ONE place: app/agent/v3/llm.py (PRICES,
# MODEL_ENV_DEFAULTS). Unknown models raise: add them there before configuring them.
# Removed model env vars (1E): warn if still set so stale Railway config is noticed.
REMOVED_MODEL_ENV_VARS = ("OPENAI_MODEL", "OPENAI_MODEL_FAST", "OPENAI_MODEL_RESPONSE")

# Daily limits from environment (with sensible defaults)
DAILY_LIMIT_PER_VISITOR = int(os.getenv("DAILY_LIMIT_PER_VISITOR", "50"))
DAILY_LIMIT_PER_IP = int(os.getenv("DAILY_LIMIT_PER_IP", "150"))
GLOBAL_DAILY_LIMIT_USD = float(os.getenv("GLOBAL_DAILY_LIMIT_USD", "5.00"))

_DATED_SUFFIX = re.compile(r"-\d{4}-\d{2}-\d{2}$")


def normalize_model(model: str) -> str:
    """'gpt-5-mini-2025-08-07' -> 'gpt-5-mini' (API responses carry the dated snapshot)."""
    return _DATED_SUFFIX.sub("", (model or "").strip())


def get_pricing(model: str) -> Dict[str, float]:
    """USD per 1M tokens for a model; raises ValueError for unknown models (no silent fallback)."""
    from app.agent.v3.llm import PRICES
    prices = PRICES.get(normalize_model(model))
    if prices is None:
        raise ValueError(f"No price for model {model!r}; add it to app/agent/v3/llm.py PRICES")
    p_in, p_cached, p_write, p_out = prices
    return {"input": p_in, "cached_input": p_cached, "cache_write": p_write, "output": p_out}


def estimate_cost(model: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0) -> float:
    """USD cost via llm.cost_usd; cached input tokens are a subset of input_tokens."""
    from app.agent.v3.llm import Usage, cost_usd
    get_pricing(model)  # ValueError for unknown models
    inp = input_tokens or 0
    return cost_usd(normalize_model(model), Usage(
        input_tokens=inp,
        cached_input_tokens=min(cached_input_tokens or 0, inp),
        output_tokens=output_tokens or 0,
    ))


def validate_configured_models() -> None:
    """Raise at startup if any configured model has no price."""
    from app.agent.v3.llm import MODEL_ENV_DEFAULTS, model_for
    for role in MODEL_ENV_DEFAULTS:
        get_pricing(model_for(role))
    if os.getenv("EVAL_JUDGE_MODEL"):
        get_pricing(os.environ["EVAL_JUDGE_MODEL"])
    stale = [v for v in REMOVED_MODEL_ENV_VARS if os.getenv(v)]
    if stale:
        logger.warning(f"Ignoring removed model env vars {stale}; use AGENT_MODEL / SUMMARY_MODEL")


def record_llm_usage(state: Dict[str, Any], usage: Any, model: Optional[str] = None) -> None:
    """
    Accumulate one LLM call into state["token_usage"]:
    {"input_tokens", "output_tokens", "cached_input_tokens", "by_model": {model: {...same keys}}}.
    `usage` is an llm.Usage, an OpenAI CompletionUsage object, or a dict with
    input_tokens/output_tokens (optionally cached_input_tokens and model).
    """
    if not usage:
        return
    def _n(value: Any) -> int:
        return value if isinstance(value, int) else 0

    if isinstance(usage, dict):
        inp = _n(usage.get("input_tokens"))
        out = _n(usage.get("output_tokens"))
        cached = _n(usage.get("cached_input_tokens"))
        model = model or usage.get("model")
    elif hasattr(usage, "prompt_tokens"):
        inp = _n(getattr(usage, "prompt_tokens", 0))
        out = _n(getattr(usage, "completion_tokens", 0))
        details = getattr(usage, "prompt_tokens_details", None)
        cached = _n(getattr(details, "cached_tokens", 0)) if details else 0
    else:  # llm.Usage
        inp = _n(getattr(usage, "input_tokens", 0))
        out = _n(getattr(usage, "output_tokens", 0))
        cached = _n(getattr(usage, "cached_input_tokens", 0))

    totals = state.setdefault("token_usage", {"input_tokens": 0, "output_tokens": 0})
    totals["input_tokens"] = totals.get("input_tokens", 0) + inp
    totals["output_tokens"] = totals.get("output_tokens", 0) + out
    totals["cached_input_tokens"] = totals.get("cached_input_tokens", 0) + cached

    key = normalize_model(model) if isinstance(model, str) and model else "unknown"
    per = totals.setdefault("by_model", {}).setdefault(
        key, {"input_tokens": 0, "output_tokens": 0, "cached_input_tokens": 0}
    )
    per["input_tokens"] += inp
    per["output_tokens"] += out
    per["cached_input_tokens"] += cached


class UsageTracker:
    """Track and limit API usage."""

    @staticmethod
    def check_limits(visitor_id: str, ip_address: str) -> Tuple[bool, str]:
        """
        Check per-visitor, per-IP and global daily limits. Fails closed on DB errors.

        Returns:
            Tuple of (allowed: bool, error_message: str)
        """
        # Import here to avoid circular imports
        from app.data.models import APIUsage

        session = Session()
        try:
            # Start of today (UTC); timestamps are stored as naive UTC
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0, tzinfo=None
            )
            # One chat turn = one request_id (several rows when several models were used)
            requests = func.count(func.distinct(func.coalesce(APIUsage.request_id, cast(APIUsage.id, String))))

            visitor_count = session.query(requests).filter(
                APIUsage.visitor_id == visitor_id,
                APIUsage.timestamp >= today
            ).scalar() or 0
            if visitor_count >= DAILY_LIMIT_PER_VISITOR:
                logger.warning(f"Visitor {visitor_id[:10]}... hit daily limit ({visitor_count})")
                return False, f"Daily limit reached ({DAILY_LIMIT_PER_VISITOR} requests). Please try again tomorrow."

            if ip_address:
                ip_count = session.query(requests).filter(
                    APIUsage.ip_address == ip_address,
                    APIUsage.timestamp >= today
                ).scalar() or 0
                if ip_count >= DAILY_LIMIT_PER_IP:
                    logger.warning(f"IP hit daily limit ({ip_count})")
                    return False, "Daily limit reached for your network. Please try again tomorrow."

            total_cost = session.query(func.sum(APIUsage.estimated_cost_usd)).filter(
                APIUsage.timestamp >= today
            ).scalar() or Decimal('0')
            if float(total_cost) >= GLOBAL_DAILY_LIMIT_USD:
                logger.warning(f"Global daily limit reached (${total_cost:.2f})")
                return False, "Service temporarily unavailable due to high demand. Please try again later."

            return True, ""

        except Exception as e:
            logger.error(f"Error checking usage limits (failing closed): {e}")
            return False, "Service temporarily unavailable. Please try again shortly."
        finally:
            session.close()

    @staticmethod
    def track_request(
        visitor_id: str,
        ip_address: str,
        token_usage: Dict[str, Any],
        endpoint: str = "chat",
    ) -> None:
        """
        Record one request's usage: one APIUsage row per model actually called, sharing a request_id.
        Raises ValueError for unpriced models.
        """
        from app.agent.v3.llm import model_for
        by_model = (token_usage or {}).get("by_model") or {}
        if not by_model and (token_usage or {}).get("input_tokens"):
            by_model = {model_for("AGENT_MODEL"): token_usage}
        if not by_model:
            # No LLM call (e.g. cached answer) still counts toward request quotas
            by_model = {model_for("AGENT_MODEL"): {}}

        request_id = str(uuid.uuid4())
        for model, counts in by_model.items():
            UsageTracker.track_usage(
                visitor_id=visitor_id,
                ip_address=ip_address,
                model=model,
                input_tokens=counts.get("input_tokens", 0) or 0,
                output_tokens=counts.get("output_tokens", 0) or 0,
                cached_input_tokens=counts.get("cached_input_tokens", 0) or 0,
                endpoint=endpoint,
                request_id=request_id,
            )

    @staticmethod
    def track_usage(
        visitor_id: str,
        ip_address: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        endpoint: str = "chat",
        cached_input_tokens: int = 0,
        request_id: Optional[str] = None,
        cost_usd: Optional[float] = None,
    ) -> None:
        """
        Record API usage for one model. Raises ValueError for unpriced models;
        DB write errors are logged, not raised.

        input_tokens include cached ones; output_tokens include reasoning.
        cost_usd: real cost from llm.cost_usd (cache and service-tier aware);
        computed from llm.PRICES when omitted.
        """
        # Import here to avoid circular imports
        from app.data.models import APIUsage

        cost = cost_usd
        if cost is None:
            cost = estimate_cost(model, input_tokens, output_tokens, cached_input_tokens)

        session = Session()
        try:
            usage = APIUsage(
                visitor_id=visitor_id,
                ip_address=ip_address,
                endpoint=endpoint,
                model=normalize_model(model),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=Decimal(str(round(cost, 6))),
                request_id=request_id,
            )
            session.add(usage)
            session.commit()

            logger.info(
                f"API usage tracked: visitor={visitor_id[:10]}..., "
                f"model={model}, tokens={input_tokens}+{output_tokens} (cached {cached_input_tokens}), "
                f"cost=${cost:.4f}"
            )

        except Exception as e:
            logger.error(f"Error tracking API usage: {e}")
            session.rollback()
        finally:
            session.close()

    @staticmethod
    def get_daily_stats() -> dict:
        """Get current day's usage statistics."""
        from app.data.models import APIUsage

        session = Session()
        try:
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            total_requests = session.query(func.count(APIUsage.id)).filter(
                APIUsage.timestamp >= today
            ).scalar() or 0

            total_cost = session.query(func.sum(APIUsage.estimated_cost_usd)).filter(
                APIUsage.timestamp >= today
            ).scalar() or Decimal('0')

            total_tokens = session.query(
                func.sum(APIUsage.input_tokens + APIUsage.output_tokens)
            ).filter(APIUsage.timestamp >= today).scalar() or 0

            unique_visitors = session.query(
                func.count(func.distinct(APIUsage.visitor_id))
            ).filter(APIUsage.timestamp >= today).scalar() or 0

            return {
                "total_requests": total_requests,
                "total_cost_usd": float(total_cost),
                "total_tokens": total_tokens,
                "unique_visitors": unique_visitors,
                "daily_limit_per_visitor": DAILY_LIMIT_PER_VISITOR,
                "global_daily_limit_usd": GLOBAL_DAILY_LIMIT_USD,
                "remaining_budget_usd": max(0, GLOBAL_DAILY_LIMIT_USD - float(total_cost))
            }

        except Exception as e:
            logger.error(f"Error getting daily stats: {e}")
            return {}
        finally:
            session.close()
