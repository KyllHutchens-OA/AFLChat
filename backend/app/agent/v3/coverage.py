"""
Data coverage for the v3 agent: season range, latest match with player
stats ("data as of"), and which recent rounds still lack player stats.

Stand-in for 1C's data_coverage helper (same intent: latest
match-with-stats date). Cached for an hour so the system prompt's coverage
line stays byte-stable between requests.
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
    from app.agent.v3.tools.base import AFL_TEAM_IDS, query, round_name, round_number

    data: Dict[str, Any] = {"first_season": 1990, "last_season": 2026, "data_as_of": None,
                            "latest_match": None, "missing_stats_rounds": [], "missing_stats_season": None}
    try:
        df = query(
            "SELECT MIN(m.season) AS first_season, MAX(m.season) AS last_season, "
            "MAX(m.match_date) FILTER (WHERE m.home_score IS NOT NULL AND (m.home_score > 0 OR m.away_score > 0)) AS latest_match, "
            "MAX(m.match_date) FILTER (WHERE EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)) AS data_as_of "
            "FROM matches m WHERE m.home_team_id = ANY(:ids)", {"ids": list(AFL_TEAM_IDS)})
        row = df.iloc[0].to_dict()
        data.update({k: row[k] for k in ("first_season", "last_season")})
        data["latest_match"] = str(row["latest_match"])[:10] if row["latest_match"] else None
        data["data_as_of"] = str(row["data_as_of"])[:10] if row["data_as_of"] else None
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
