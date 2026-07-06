"""
AFL Analytics Agent - Diagnose Empty Node (Milestone 3c)

Runs when `execute` returns ZERO rows (v2 pipeline only). Deterministic — no
LLM call, no SQL generation. Figures out WHY the query came back empty by:

  1. First consuming the M1 EntityResolver warnings already sitting in
     `state["warnings"]` (season-out-of-range, player-season-mismatch) if one
     of them already answers the question — this avoids re-running a query
     the resolver already ran during classify_resolve.
  2. Otherwise, running targeted deterministic probes against the DB:
       - does the resolved entity (player/team) exist at all?
       - which seasons DOES it actually have data for?

Outcome is a structured dict:
    {
        "reason_code": str,       # e.g. "player_season_mismatch", "season_out_of_range"
        "human_reason": str,      # plain-English explanation, names the specific reason
        "fixable": bool,          # True => obviously correctable by regenerating SQL once
        "suggestion": str | None, # instruction for the generate_sql retry prompt, if fixable
    }

`fixable=True` is reserved for cases where the 0 rows are very likely caused
by a mechanically-correctable mistake in the generated SQL — e.g. the query
pinned a season the entity doesn't have data for, but the user's own question
was phrased as "career"/"all-time" (so the SQL should never have added that
filter in the first place). Everything else — the user explicitly asked
about a season the entity/database doesn't cover, a name that doesn't
resolve to anything, or some other filter combination that just has no
matching rows — is NOT fixable by regenerating SQL. It's a genuine "no data"
answer, so it routes straight to respond, which states the reason plainly.
"""
import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

_CAREER_KEYWORDS = (
    "career", "all time", "all-time", "overall", "lifetime", "total", "ever", "throughout"
)

# Mirrors app/analytics/entity_resolver.py's warning message formats exactly —
# these are produced during classify_resolve (M1) and, when present, already
# answer the "why" question without another DB round-trip.
_SEASON_MISMATCH_RE = re.compile(
    r"^(?P<name>.+?) has no (?P<seasons>[\d,\s]+) data; seasons available: (?P<available>[\d,\s]+)$"
)
_NO_PLAYER_DATA_RE = re.compile(
    r"^(?P<name>.+?) has no player-stats data available for any season\.$"
)
_SEASON_RANGE_RE = re.compile(
    r"^Season (?P<year>\d+) outside data range \((?P<lo>\d+)-(?P<hi>\d+)\)$"
)
_UNKNOWN_TEAM_RE = re.compile(r"^Unknown team: '(?P<name>.+)'$")


def _is_career_style(user_query: str) -> bool:
    query_lower = (user_query or "").lower()
    return any(kw in query_lower for kw in _CAREER_KEYWORDS)


def _match_warning(warnings: Optional[List[str]], pattern: "re.Pattern"):
    for warning in warnings or []:
        m = pattern.match(warning)
        if m:
            return m
    return None


def _season_span(seasons: List[str]) -> str:
    if not seasons:
        return "(none)"
    ints = sorted({int(s) for s in seasons if str(s).isdigit()})
    if not ints:
        return ", ".join(seasons)
    if len(ints) == 1:
        return str(ints[0])
    return f"{ints[0]}–{ints[-1]}"


def _probe_player(name: str, seasons: List[str], is_career_style: bool) -> Optional[Dict[str, Any]]:
    """Deterministic DB probes for a player entity: exists? which seasons have data?"""
    from app.data.database import Session

    session = Session()
    try:
        row = session.execute(
            text("SELECT id, name FROM players WHERE LOWER(name) = LOWER(:name) LIMIT 1"),
            {"name": name},
        ).fetchone()
        if row is None:
            row = session.execute(
                text("SELECT id, name FROM players WHERE name ILIKE :pattern LIMIT 1"),
                {"pattern": f"%{name}%"},
            ).fetchone()

        if row is None:
            return {
                "reason_code": "player_not_found",
                "human_reason": f"I couldn't find a player named '{name}' in our database.",
                "fixable": False,
                "suggestion": None,
            }

        player_id, matched_name = row[0], row[1]

        avail_rows = session.execute(
            text(
                """
                SELECT DISTINCT m.season
                FROM player_stats ps
                JOIN matches m ON ps.match_id = m.id
                WHERE ps.player_id = :player_id
                ORDER BY m.season
                """
            ),
            {"player_id": player_id},
        ).fetchall()
        available_seasons = [str(r[0]) for r in avail_rows]

        if not available_seasons:
            return {
                "reason_code": "player_no_data",
                "human_reason": f"{matched_name} doesn't have any player-stats data in our database.",
                "fixable": False,
                "suggestion": None,
            }

        avail_span = f"{available_seasons[0]}–{available_seasons[-1]}"

        if seasons:
            requested = {str(s) for s in seasons}
            if not requested & set(available_seasons):
                fixable = is_career_style
                return {
                    "reason_code": "player_season_mismatch",
                    "human_reason": (
                        f"{matched_name} has no {_season_span(seasons)} stats — "
                        f"their data covers {avail_span}."
                    ),
                    "fixable": fixable,
                    "suggestion": (
                        f"The user asked a career/all-time question — re-run WITHOUT pinning "
                        f"the season filter, querying across {matched_name}'s full available "
                        f"range ({avail_span}) instead."
                        if fixable else None
                    ),
                }

        # Player exists and has data covering (or overlapping) the requested season(s) —
        # the empty result must be from some OTHER filter (round, venue, opponent, metric).
        return {
            "reason_code": "filter_excludes_all",
            "human_reason": (
                f"{matched_name} has data for {avail_span}, but no rows matched the other "
                f"filters in this query (e.g. round, venue, or opponent)."
            ),
            "fixable": False,
            "suggestion": None,
        }
    except Exception as e:
        logger.warning(f"DIAGNOSE_EMPTY: player probe failed for '{name}': {e}")
        return None
    finally:
        session.close()


def _probe_team(name: str, seasons: List[str], is_career_style: bool) -> Optional[Dict[str, Any]]:
    """Deterministic DB probes for a team entity: exists? which seasons have data?"""
    from app.data.database import Session

    session = Session()
    try:
        row = session.execute(
            text("SELECT id, name FROM teams WHERE LOWER(name) = LOWER(:name) LIMIT 1"),
            {"name": name},
        ).fetchone()

        if row is None:
            return {
                "reason_code": "team_not_found",
                "human_reason": f"I couldn't find a team named '{name}' in our database.",
                "fixable": False,
                "suggestion": None,
            }

        team_id, matched_name = row[0], row[1]

        span_row = session.execute(
            text(
                """
                SELECT MIN(season), MAX(season)
                FROM matches
                WHERE home_team_id = :team_id OR away_team_id = :team_id
                """
            ),
            {"team_id": team_id},
        ).fetchone()
        lo, hi = (span_row[0], span_row[1]) if span_row else (None, None)

        if lo is None or hi is None:
            return {
                "reason_code": "team_no_data",
                "human_reason": f"{matched_name} doesn't have any match data in our database.",
                "fixable": False,
                "suggestion": None,
            }

        if seasons:
            requested = [int(s) for s in seasons if str(s).isdigit()]
            in_range = [s for s in requested if lo <= s <= hi]
            if requested and not in_range:
                fixable = is_career_style
                return {
                    "reason_code": "team_season_mismatch",
                    "human_reason": (
                        f"{matched_name} has no data for {_season_span(seasons)} — "
                        f"their data covers {lo}–{hi}."
                    ),
                    "fixable": fixable,
                    "suggestion": (
                        f"The user asked a career/all-time question — re-run WITHOUT pinning "
                        f"the season filter, querying across {matched_name}'s full available "
                        f"range ({lo}–{hi}) instead."
                        if fixable else None
                    ),
                }

        return {
            "reason_code": "filter_excludes_all",
            "human_reason": (
                f"{matched_name} has data for {lo}–{hi}, but no rows matched the other "
                f"filters in this query (e.g. round, venue, or opponent)."
            ),
            "fixable": False,
            "suggestion": None,
        }
    except Exception as e:
        logger.warning(f"DIAGNOSE_EMPTY: team probe failed for '{name}': {e}")
        return None
    finally:
        session.close()


def diagnose_empty(
    user_query: str,
    entities: Optional[Dict[str, Any]] = None,
    warnings: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Deterministically diagnose why `execute` returned zero rows.

    Args:
        user_query: The current user question (used only for the cheap
            "career"/"all-time" keyword heuristic that decides fixability).
        entities: Resolved entities from classify_resolve (players/teams/seasons).
        warnings: state["warnings"] accumulated so far this turn — may already
            contain an EntityResolver (M1) season-mismatch/out-of-range warning
            that answers the question without hitting the DB again.

    Returns:
        Diagnosis dict: {reason_code, human_reason, fixable, suggestion}.
    """
    entities = entities or {}
    warnings = warnings or []
    is_career = _is_career_style(user_query)

    # ── 1. Season out of range (M1 EntityResolver warning) ─────────────────
    m = _match_warning(warnings, _SEASON_RANGE_RE)
    if m:
        year, lo, hi = m.group("year"), m.group("lo"), m.group("hi")
        return {
            "reason_code": "season_out_of_range",
            "human_reason": f"{year} is outside the data we have — the database covers {lo}–{hi}.",
            "fixable": False,
            "suggestion": None,
        }

    # ── 2. Player-season mismatch (M1 EntityResolver warning) ──────────────
    m = _match_warning(warnings, _SEASON_MISMATCH_RE)
    if m:
        name = m.group("name")
        seasons_str = m.group("seasons").strip()
        available_str = m.group("available").strip()
        fixable = is_career
        return {
            "reason_code": "player_season_mismatch",
            "human_reason": f"{name} has no {seasons_str} stats — their data covers {available_str}.",
            "fixable": fixable,
            "suggestion": (
                f"The user asked a career/all-time question — re-run WITHOUT pinning the "
                f"season filter, querying across {name}'s full available range ({available_str}) instead."
                if fixable else None
            ),
        }

    # ── 3. Player has no data at all (M1 EntityResolver warning) ───────────
    m = _match_warning(warnings, _NO_PLAYER_DATA_RE)
    if m:
        name = m.group("name")
        return {
            "reason_code": "player_no_data",
            "human_reason": f"{name} doesn't have any player-stats data in our database.",
            "fixable": False,
            "suggestion": None,
        }

    # ── 4. Unresolved team name (classify_resolve warning) ─────────────────
    m = _match_warning(warnings, _UNKNOWN_TEAM_RE)
    if m:
        name = m.group("name")
        return {
            "reason_code": "team_not_found",
            "human_reason": f"I couldn't match '{name}' to an AFL team in our database.",
            "fixable": False,
            "suggestion": None,
        }

    # ── 5. No warning already answered it — run deterministic DB probes ────
    players = entities.get("players") or []
    teams = entities.get("teams") or []
    seasons = entities.get("seasons") or []

    if players:
        probe = _probe_player(players[0], seasons, is_career)
        if probe:
            return probe

    if teams:
        probe = _probe_team(teams[0], seasons, is_career)
        if probe:
            return probe

    # ── 6. Generic fallback — no entity to probe, or probes errored out ────
    return {
        "reason_code": "filter_excludes_all",
        "human_reason": "No rows matched that specific combination of filters.",
        "fixable": False,
        "suggestion": None,
    }
