"""
API Usage Tracking for OpenAI cost control.
Tracks token usage and enforces per-visitor and global daily limits.
"""
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
import os
import logging

from sqlalchemy import func
from app.data.database import Session

logger = logging.getLogger(__name__)

# Daily limits from environment (with sensible defaults)
DAILY_LIMIT_PER_VISITOR = int(os.getenv("DAILY_LIMIT_PER_VISITOR", "50"))
GLOBAL_DAILY_LIMIT_USD = float(os.getenv("GLOBAL_DAILY_LIMIT_USD", "5.00"))


class UsageTracker:
    """Track and limit API usage."""

    @staticmethod
    def check_limits(visitor_id: str, ip_address: str) -> Tuple[bool, str]:
        """
        Check if visitor or global limits are exceeded.

        Returns:
            Tuple of (allowed: bool, error_message: str)
        """
        # Import here to avoid circular imports
        from app.data.models import APIUsage

        session = Session()
        try:
            # Get start of today (UTC)
            today = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            )

            # Check per-visitor limit
            visitor_count = session.query(func.count(APIUsage.id)).filter(
                APIUsage.visitor_id == visitor_id,
                APIUsage.timestamp >= today
            ).scalar() or 0

            if visitor_count >= DAILY_LIMIT_PER_VISITOR:
                logger.warning(f"Visitor {visitor_id[:8]}... hit daily limit ({visitor_count})")
                return False, f"Daily limit reached ({DAILY_LIMIT_PER_VISITOR} requests). Please try again tomorrow."

            # Check global daily spend
            total_cost = session.query(func.sum(APIUsage.estimated_cost_usd)).filter(
                APIUsage.timestamp >= today
            ).scalar() or Decimal('0')

            if float(total_cost) >= GLOBAL_DAILY_LIMIT_USD:
                logger.warning(f"Global daily limit reached (${total_cost:.2f})")
                return False, "Service temporarily unavailable due to high demand. Please try again later."

            return True, ""

        except Exception as e:
            logger.error(f"Error checking usage limits: {e}")
            # Allow request on error to avoid blocking users due to DB issues
            return True, ""
        finally:
            session.close()

    @staticmethod
    def track_usage(
        visitor_id: str,
        ip_address: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        endpoint: str = "chat",
        cost_usd: Optional[float] = None,
    ) -> None:
        """
        Record API usage for cost tracking.

        Args:
            visitor_id: Unique visitor identifier ("system" for background jobs)
            ip_address: Client IP address
            model: model name used
            input_tokens: Number of input tokens (cached included)
            output_tokens: Number of output tokens (reasoning included)
            endpoint: API endpoint name
            cost_usd: real cost from llm.cost_usd (cache-aware); computed
                from uncached list prices when omitted
        """
        # Import here to avoid circular imports
        from app.data.models import APIUsage
        from app.agent.v3.llm import LLMError, Usage, cost_usd as price

        session = Session()
        try:
            cost = cost_usd
            if cost is None:
                try:
                    cost = price(model, Usage(input_tokens=input_tokens, output_tokens=output_tokens))
                except LLMError as e:
                    logger.error(f"Usage cost unknown: {e}")
                    cost = 0.0

            usage = APIUsage(
                visitor_id=visitor_id,
                ip_address=ip_address,
                endpoint=endpoint,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_cost_usd=Decimal(str(round(cost, 6)))
            )
            session.add(usage)
            session.commit()

            logger.info(
                f"API usage tracked: visitor={visitor_id[:8]}..., "
                f"model={model}, tokens={input_tokens}+{output_tokens}, "
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
