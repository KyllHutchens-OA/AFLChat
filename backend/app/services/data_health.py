"""Data-health checks and the data-coverage note for the agent.

`data_health()` -> dict served at GET /api/health/data (and logged daily):
  completed matches without player stats, placeholder kick-off times, player rows
  per match outside the era's range, NULL rates per season, matches vs live_games
  score mismatches, and a coverage summary (which seasons have attendance, TOG, CP...).
`data_coverage()` -> small dict for the agent's "data as of" line.
Both are cached in-process for a few minutes.
"""
import time
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import text

from app.data.database import get_session

_CACHE: Dict[str, tuple] = {}
CACHE_SECONDS = 300

# Players listed per side by era (20 + interchange / sub rules). A match is an outlier
# when its player_stats row count is outside [2*side - 4, 2*side + 2].
SIDE_SIZE = [(1990, 20), (1994, 21), (1998, 22), (2021, 23)]

# Verified against AFL Tables team lists; not errors
KNOWN_ROW_COUNT_EXCEPTIONS = {
    (1996, "St Kilda", "Essendon", "1996-06-08"): "AFL Tables lists 25 + 26 players",
}

NULL_RATE_COLUMNS = (
    "disposals", "goals", "behinds", "tackles", "hitouts", "clearances", "inside_50s",
    "contested_possessions", "uncontested_possessions", "brownlow_votes", "time_on_ground_pct",
)
COVERAGE_COLUMNS = NULL_RATE_COLUMNS + ("goal_assist", "bounces", "contested_marks", "one_percenters")


def _side_size(season: int) -> int:
    size = SIDE_SIZE[0][1]
    for start, n in SIDE_SIZE:
        if season >= start:
            size = n
    return size


def _cached(key: str, fn):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < CACHE_SECONDS:
        return hit[1]
    value = fn()
    _CACHE[key] = (time.time(), value)
    return value


def _rows(session, sql: str, **params):
    return [dict(r._mapping) for r in session.execute(text(sql), params)]


def _season_ranges(seasons) -> list:
    """[1999, 2000, 2001, 2026] -> ['1999-2001', '2026']"""
    out, run = [], []
    for s in sorted(seasons):
        if run and s != run[-1] + 1:
            out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
            run = []
        run.append(s)
    if run:
        out.append(f"{run[0]}-{run[-1]}" if len(run) > 1 else str(run[0]))
    return out


def compute_data_health(session) -> Dict:
    now = datetime.utcnow()
    missing = _rows(session, """
        SELECT m.id, m.season, m.round_name, m.match_date::date AS date
        FROM matches m
        WHERE m.match_status = 'completed'
          AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)
        ORDER BY m.match_date DESC""")
    # AFL Tables publishes 1-3 days after a game; older gaps are a failure
    overdue = [m for m in missing if (now.date() - m["date"]).days > 3]

    # Placeholder fixture times: midnight kick-offs, or (from 2002, when simultaneous
    # Saturday 2:10pm rounds ended) 3+ matches sharing one exact kick-off.
    placeholder = _rows(session, """
        SELECT season, match_date, count(*) AS n FROM matches WHERE season >= 2002
        GROUP BY season, match_date HAVING count(*) >= 3
        UNION ALL
        SELECT season, match_date, 1 FROM matches WHERE match_date::time = '00:00'
        ORDER BY 1, 2""")

    per_match = _rows(session, """
        SELECT m.id, m.season, m.round_name, h.name AS home, a.name AS away,
               m.match_date::date::text AS date, count(ps.id) AS n
        FROM matches m JOIN player_stats ps ON ps.match_id = m.id
        JOIN teams h ON h.id = m.home_team_id JOIN teams a ON a.id = m.away_team_id
        GROUP BY m.id, m.season, m.round_name, h.name, a.name""")
    outliers = []
    for r in per_match:
        if (r["season"], r["home"], r["away"], r["date"]) in KNOWN_ROW_COUNT_EXCEPTIONS:
            continue
        side = _side_size(r["season"])
        if not (2 * side - 4 <= r["n"] <= 2 * side + 2):
            outliers.append({**r, "expected": f"{2 * side - 4}-{2 * side + 2}"})

    null_cols = ", ".join(
        f"round(100.0 * count(*) FILTER (WHERE ps.{c} IS NULL) / count(*), 1) AS {c}"
        for c in NULL_RATE_COLUMNS)
    null_rates = _rows(session, f"""
        SELECT m.season, count(*) AS rows, {null_cols}
        FROM player_stats ps JOIN matches m ON m.id = ps.match_id
        GROUP BY m.season ORDER BY m.season""")

    live = _rows(session, """
        SELECT m.id AS match_id, lg.id AS live_game_id, m.season, m.round_name,
               m.home_score, m.away_score,
               CASE WHEN m.home_team_id = lg.home_team_id THEN lg.home_score ELSE lg.away_score END AS live_home,
               CASE WHEN m.home_team_id = lg.home_team_id THEN lg.away_score ELSE lg.home_score END AS live_away,
               (m.home_q4_goals IS NOT NULL) AS afltables_confirmed
        FROM live_games lg JOIN matches m ON m.id = lg.match_id
        WHERE lg.status = 'completed' AND lg.complete_percent >= 100""")
    mismatches = [r for r in live if (r["home_score"], r["away_score"]) != (r["live_home"], r["live_away"])]
    # Squiggle and AFL Tables occasionally differ by a point; AFL Tables wins once confirmed
    unresolved = [r for r in mismatches if not r["afltables_confirmed"]]

    cov_cols = ", ".join(
        f"count(*) FILTER (WHERE ps.{c} IS NOT NULL AND ps.{c} <> 0) > 0 AS {c}" for c in COVERAGE_COLUMNS)
    cov = _rows(session, f"""
        SELECT m.season, {cov_cols}
        FROM player_stats ps JOIN matches m ON m.id = ps.match_id GROUP BY m.season""")
    att = _rows(session, """
        SELECT season, round(100.0 * count(attendance) / count(*)) AS pct
        FROM matches GROUP BY season""")
    coverage = {c: _season_ranges([r["season"] for r in cov if r[c]]) for c in COVERAGE_COLUMNS}
    coverage["attendance"] = _season_ranges([r["season"] for r in att if r["pct"] >= 90])

    checks = {
        "completed_matches_without_stats": len(overdue),
        "placeholder_times": len(placeholder),
        "rows_per_match_outliers": len(outliers),
        "live_score_mismatches": len(unresolved),
    }
    return {
        "status": "ok" if not any(checks.values()) else "warn",
        "generated_at": now.isoformat() + "Z",
        "checks": checks,
        "completed_matches_without_stats": {
            "count": len(missing), "overdue_count": len(overdue),
            "examples": [{**m, "date": m["date"].isoformat()} for m in missing[:20]],
        },
        "placeholder_times": [{**p, "match_date": p["match_date"].isoformat()} for p in placeholder[:50]],
        "rows_per_match_outliers": {
            "count": len(outliers),
            "examples": sorted(outliers, key=lambda r: (-r["season"], r["id"]))[:30],
        },
        "null_rates_pct": [{k: float(v) if hasattr(v, "is_finite") else v for k, v in r.items()} for r in null_rates],
        "live_score_mismatches": mismatches,
        "coverage_seasons": coverage,
        "latest": data_coverage_from(session),
    }


def data_coverage_from(session) -> Dict:
    r = _rows(session, """
        SELECT
          (SELECT max(m.match_date) FROM matches m
            WHERE EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)) AS latest_with_stats,
          (SELECT max(match_date) FROM matches WHERE match_status = 'completed') AS latest_completed,
          (SELECT count(*) FROM matches m WHERE m.match_status = 'completed'
             AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)) AS completed_without_stats
    """)[0]
    return {
        "latest_match_with_stats": r["latest_with_stats"].date().isoformat() if r["latest_with_stats"] else None,
        "latest_completed_match": r["latest_completed"].date().isoformat() if r["latest_completed"] else None,
        "completed_matches_without_stats": r["completed_without_stats"],
    }


def data_health() -> Dict:
    def run():
        with get_session() as session:
            return compute_data_health(session)
    return _cached("health", run)


def data_coverage() -> Dict:
    """{'latest_match_with_stats': 'YYYY-MM-DD', ...} for a subtle "data as of" line."""
    def run():
        with get_session() as session:
            return data_coverage_from(session)
    return _cached("coverage", run)


def latest_match_with_stats() -> Optional[str]:
    return data_coverage().get("latest_match_with_stats")
