"""
Rate limiting configuration using Flask-Limiter.
Uses in-memory storage (no Redis required) for free-tier friendly deployments.
"""
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import logging

logger = logging.getLogger(__name__)

# Keyed on request.remote_addr, which ProxyFix (create_app) sets from the trusted proxy hop.
# Initialize limiter with in-memory storage
# This is suitable for single-worker deployments on Railway
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://",
)


# Rate limit error handler
def ratelimit_error_handler(e):
    """Handle rate limit exceeded errors."""
    logger.warning(f"Rate limit exceeded: {get_remote_address()}")
    return {
        "error": "Rate limit exceeded",
        "message": "Too many requests. Please try again later.",
        "retry_after": e.description
    }, 429
