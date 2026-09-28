"""
Teams API: team listing endpoint.
"""
import time
import logging
from flask import Blueprint, jsonify
from sqlalchemy import text
from app.data.database import get_session

logger = logging.getLogger(__name__)

bp = Blueprint('teams', __name__, url_prefix='/api/teams')

# In-memory cache for team list
_teams_cache = {"data": None, "ts": 0}
_TEAMS_CACHE_TTL = 86400  # 24 hours


@bp.route('/', methods=['GET'])
def list_teams():
    """Return all 18 AFL teams with basic metadata. Cached for 24 hours."""
    now = time.time()
    if _teams_cache["data"] and (now - _teams_cache["ts"]) < _TEAMS_CACHE_TTL:
        return jsonify(_teams_cache["data"])

    try:
        with get_session() as session:
            rows = session.execute(text(
                "SELECT id, name, abbreviation, primary_color, secondary_color "
                "FROM teams ORDER BY name"
            )).fetchall()

        teams = [
            {
                "id": r[0],
                "name": r[1],
                "abbreviation": r[2],
                "primary_color": r[3],
                "secondary_color": r[4],
            }
            for r in rows
        ]

        _teams_cache["data"] = teams
        _teams_cache["ts"] = now
        return jsonify(teams)

    except Exception as e:
        logger.error(f"Failed to fetch teams: {e}")
        return jsonify({"error": "Failed to fetch teams"}), 500

