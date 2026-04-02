"""
Simple in-memory query cache to reduce redundant database calls.
Caches SQL query results by a hash of the SQL string.

Two-tier caching:
- Historical (queries referencing only past seasons): TTL 60 min, 500 entries
- Live/current-season: TTL 5 min, 100 entries
"""
import hashlib
import logging
import re
from datetime import datetime
from cachetools import TTLCache

logger = logging.getLogger(__name__)

# Historical data cache: long TTL since past seasons don't change
_historical_cache: TTLCache = TTLCache(maxsize=500, ttl=3600)  # 60 min

# Live/current-season cache: short TTL for fresh data
_live_cache: TTLCache = TTLCache(maxsize=100, ttl=300)  # 5 min

# Current year for cache routing
_CURRENT_YEAR = datetime.now().year


def get_cache_key(sql: str) -> str:
    """Generate a stable cache key from a SQL string."""
    return hashlib.md5(sql.strip().lower().encode()).hexdigest()


def _is_historical_query(sql: str) -> bool:
    """Determine if a SQL query only references past seasons (safe for long caching)."""
    sql_lower = sql.lower()

    # If it references live_games, it's always live
    if 'live_games' in sql_lower:
        return False

    # Extract all year references from the SQL
    years = re.findall(r'\b((?:19|20)\d{2})\b', sql)
    if not years:
        return False  # No years = can't determine, use short TTL

    # If ALL referenced years are before current year, it's historical
    return all(int(y) < _CURRENT_YEAR for y in years)


def get_cached_result(sql: str):
    """Return cached DataFrame result for this SQL, or None if not cached."""
    key = get_cache_key(sql)

    # Check historical cache first (larger, longer TTL)
    result = _historical_cache.get(key)
    if result is not None:
        logger.debug(f"Cache hit (historical) for query hash {key[:8]}")
        return result

    # Then check live cache
    result = _live_cache.get(key)
    if result is not None:
        logger.debug(f"Cache hit (live) for query hash {key[:8]}")
        return result

    return None


def set_cached_result(sql: str, result) -> None:
    """Store a DataFrame result in the appropriate cache bucket."""
    key = get_cache_key(sql)

    if _is_historical_query(sql):
        _historical_cache[key] = result
        logger.debug(f"Cached result (historical, 60min TTL) for hash {key[:8]} ({len(result)} rows)")
    else:
        _live_cache[key] = result
        logger.debug(f"Cached result (live, 5min TTL) for hash {key[:8]} ({len(result)} rows)")


def cache_stats() -> dict:
    """Return current cache statistics."""
    return {
        "historical_size": len(_historical_cache),
        "historical_maxsize": _historical_cache.maxsize,
        "historical_ttl": _historical_cache.ttl,
        "live_size": len(_live_cache),
        "live_maxsize": _live_cache.maxsize,
        "live_ttl": _live_cache.ttl,
    }
