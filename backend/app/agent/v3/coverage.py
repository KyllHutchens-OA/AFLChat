"""
Data coverage for the v3 agent: season range, latest match with player
stats ("data as of"), and which recent rounds still lack player stats.

The "data as of" date comes from 1C's `data_coverage()`
(`app/services/data_health.py`), the authoritative source used by
`GET /api/health/data`. This module adds the v3-specific parts (season
bounds, per-round-name missing-stats breakdown for the current season) and
caches the merged result for an hour so the system prompt's coverage line
stays byte-stable between requests.
"""
import logging
import time
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

_TTL_S = 3600
_cache: Dict[str, Any] = {"at": 0.0, "data": None}


def coverage(force: bool = False) -> Dict[str, Any]:
    if not force and _cache["data"] and time.time() - _cache["at"] < _TTL_S:
        return _cache["data"]
    from app.agent.v3.tools.base import query, round_name, round_number
    from app.services.data_health import data_coverage as afl_data_coverage

    data: Dict[str, Any] = {"first_season": 1990, "last_season": 2026, "data_as_of": None,
                            "latest_match": None, "missing_stats_rounds": [], "missing_stats_season": None}
    try:
        df = query("SELECT MIN(season) AS first_season, MAX(season) AS last_season FROM matches")
        row = df.iloc[0].to_dict()
        data.update({k: row[k] for k in ("first_season", "last_season")})

        cov = afl_data_coverage()
        data["data_as_of"] = cov.get("latest_match_with_stats")
        data["latest_match"] = cov.get("latest_completed_match")

        missing = query(
            f"SELECT {round_name('m')} AS round_name, MIN({round_number('m')}) AS rn, COUNT(*) AS matches "
            "FROM matches m WHERE m.season = :season AND (m.home_score > 0 OR m.away_score > 0) "
            "AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id) "
            "GROUP BY 1 ORDER BY MIN(m.match_date)", {"season": int(data["last_season"])})
        data["missing_stats_season"] = int(data["last_season"])
        data["missing_stats_rounds"] = missing["round_name"].tolist() if len(missing) else []
    except Exception as e:
        logger.warning(f"coverage query failed, using defaults: {e}")
    _cache.update(at=time.time(), data=data)
    return data


def data_as_of() -> str:
    """Latest match date that has player stats, e.g. '2026-09-19'."""
    return coverage().get("data_as_of") or ""


def missing_rounds_text(rounds: List[str], limit: int = 12) -> str:
    return ", ".join(rounds[:limit]) + (" ..." if len(rounds) > limit else "")
