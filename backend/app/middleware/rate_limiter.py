"""
Rate limiting configuration using Flask-Limiter.
Uses in-memory storage (no Redis required) for free-tier friendly deployments.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask import request
import logging

logger = logging.getLogger(__name__)

# Initialize limiter with in-memory storage
# This is suitable for single-worker deployments on Railway
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


def get_visitor_key():
    """
    Get rate limit key from visitor_id (if available) or IP address.
    This allows rate limiting by visitor identity for analytics tracking.
    """
    if request.is_json:
        data = request.get_json(silent=True)
        if data and data.get('visitor_id'):
            return f"visitor:{data['visitor_id']}"
    return get_remote_address()


def get_ip_key():
    """
    Get rate limit key from IP address.
    Handles X-Forwarded-For header for proxied requests.
    """
    forwarded_for = request.headers.get('X-Forwarded-For')
    if forwarded_for:
        # Take the first IP (client IP) from the chain
        return forwarded_for.split(',')[0].strip()
    return request.remote_addr or "unknown"


# Rate limit error handler
def ratelimit_error_handler(e):
    """Handle rate limit exceeded errors."""
    logger.warning(f"Rate limit exceeded: {get_remote_address()}")
    return {
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": e.description
    }, 429
