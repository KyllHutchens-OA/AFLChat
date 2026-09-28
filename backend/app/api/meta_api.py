"""
Meta API — small facts about the data the frontend needs (e.g. starter chips).
"""
import time
import logging
from datetime import datetime, date
from typing import Optional
from flask import Blueprint, jsonify
from sqlalchemy import text
from app.data.database import get_session

logger = logging.getLogger(__name__)

bp = Blueprint('meta', __name__, url_prefix='/api/meta')

_season_cache = {"data": None, "ts": 0}
_SEASON_CACHE_TTL = 3600  # 1 hour


def season_status(max_season: int, last_match_date: Optional[datetime],
                  last_round_matches: int, today: date) -> dict:
    """Pure rule: a season is over once its Grand Final is played.

    GF = latest completed match is in Sep/Oct and alone in its round.
    Also over once we're past 15 Oct of that year or into a later year.
    """
    gf_played = (
        last_match_date is not None
        and last_match_date.month >= 9
        and last_round_matches == 1
    )
    season_over = gf_played or today > date(max_season, 10, 15)
    return {
        "current_season": max_season,
        "latest_completed_season": max_season if season_over else max_season - 1,
        "in_season": not season_over,
    }


@bp.route('/season', methods=['GET'])
def get_season():
    """Latest completed season and whether a season is in progress. Cached 1h."""
    now = time.time()
    if _season_cache["data"] and (now - _season_cache["ts"]) < _SEASON_CACHE_TTL:
        return jsonify(_season_cache["data"])

    try:
        with get_session() as session:
            row = session.execute(text(
                "WITH last AS ("
                "  SELECT season, round, match_date FROM matches"
                "  WHERE match_status = 'completed'"
                "  ORDER BY match_date DESC LIMIT 1"
                ") "
                "SELECT l.season, l.match_date, "
                "  (SELECT COUNT(*) FROM matches m"
                "   WHERE m.season = l.season AND m.round = l.round) "
                "FROM last l"
            )).fetchone()
        if not row:
            return jsonify({"error": "No completed matches"}), 404

        data = season_status(row[0], row[1], row[2], date.today())
        _season_cache["data"] = data
        _season_cache["ts"] = now
        return jsonify(data)

    except Exception as e:
        logger.error(f"Failed to compute season status: {e}")
        return jsonify({"error": "Failed to compute season status"}), 500
