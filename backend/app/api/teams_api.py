"""
Teams API — team listing and fun stats endpoints.
"""
import time
import logging
from flask import Blueprint, jsonify
from sqlalchemy import text
from app.data.database import get_session
from app.analytics.entity_resolver import EntityResolver
from app.services.fun_stats_service import get_fun_stats

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


@bp.route('/<team_name>/fun-stats', methods=['GET'])
def team_fun_stats(team_name):
    """Return 2-3 fun/surprising stats for a team."""
    resolved = EntityResolver.resolve_team(team_name)
    if not resolved:
        return jsonify({"error": "Team not found"}), 404

    try:
        stats = get_fun_stats(resolved)
        return jsonify(stats)
    except Exception as e:
        logger.error(f"Failed to get fun stats for {team_name}: {e}")
        return jsonify({"error": "Failed to compute fun stats"}), 500
