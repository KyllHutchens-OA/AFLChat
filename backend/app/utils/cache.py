"""
Simple in-memory query cache to reduce redundant OpenAI calls.
Caches SQL query results by a hash of the SQL string.
TTL: 5 minutes, Max: 100 entries
"""
import hashlib
import logging
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# 5-minute TTL, 100 entries max
query_cache: TTLCache = TTLCache(maxsize=100, ttl=300)


def get_cache_key(sql: str) -> str:
    """Generate a stable cache key from a SQL string."""
    return hashlib.md5(sql.strip().lower().encode()).hexdigest()


def get_cached_result(sql: str):
    """Return cached DataFrame result for this SQL, or None if not cached."""
    key = get_cache_key(sql)
    result = query_cache.get(key)
    if result is not None:
        logger.debug(f"Cache hit for query hash {key[:8]}")
    return result


def set_cached_result(sql: str, result) -> None:
    """Store a DataFrame result in the cache."""
    key = get_cache_key(sql)
    query_cache[key] = result
    logger.debug(f"Cached result for query hash {key[:8]} ({len(result)} rows)")


def cache_stats() -> dict:
    """Return current cache statistics."""
    return {
        "size": len(query_cache),
        "maxsize": query_cache.maxsize,
        "ttl": query_cache.ttl,
    }
