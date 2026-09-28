"""
Player-level tools: player_stats (one or more named players) and leaderboard
(rank all players by a stat). SQL is parameterised from the verified
examples in app/agent/sql_examples.py, with the review fixes applied:
group by player only (team = the club they played most games for), NULL
stats count as 0 so per-game averages use every game, and ties at the
cut-off are kept (RANK, not LIMIT).
"""
from typing import Any, Dict, List, Literal, Optional, Tuple

from pydantic import BaseModel, Field, field_validator

from app.agent.v3.coverage import coverage, missing_rounds_text
from app.agent.v3.tools.base import (
    AFL_TEAM_IDS, STAT_FIRST_SEASON, ResultStore, check_seasons, finals_clause,
    normalise_round_name, plain_names, query, result, round_name,
)
from app.agent.v3.tools.entities import load_name_cache, resolve_player_ids, resolve_team_id
from app.analytics.entity_resolver import VenueResolver

Stat = Literal[
    "goals", "behinds", "disposals", "kicks", "handballs", "marks", "tackles", "hitouts",
    "clearances", "inside_50s", "rebound_50s", "contested_possessions",
    "uncontested_possessions", "contested_marks", "marks_inside_50", "one_percenters",
    "bounces", "clangers", "free_kicks_for", "free_kicks_against", "brownlow_votes",
    "goal_assist", "time_on_ground_pct", "fantasy_points",
]
Finals = Literal["include", "exclude", "only"]
DEFAULT_STATS = ["disposals", "kicks", "handballs", "marks", "tackles", "goals", "behinds"]
MAX_SEASON_GAMES = 28  # 24 rounds + Opening Round + up to 4 finals (incl. wildcard) is the ceiling in practice


def _filters(season_from, season_to, round_name_arg, finals, opponent, venue, team=None) -> Tuple[str, Dict, List[str]]:
    """Shared WHERE fragment over ps/m. Returns (sql, params, problems)."""
    sql = " AND ps.team_id = ANY(:afl_ids)"
    params: Dict[str, Any] = {"afl_ids": list(AFL_TEAM_IDS)}
    problems: List[str] = []
    if season_from:
        sql += " AND m.season >= :season_from"
        params["season_from"] = season_from
    if season_to:
        sql += " AND m.season <= :season_to"
        params["season_to"] = season_to
    rn = normalise_round_name(round_name_arg)
    if rn:
        sql += f" AND {round_name('m')} = :round_name"
        params["round_name"] = rn
    sql += finals_clause(finals)
    if opponent:
        opp = resolve_team_id(opponent)
        if opp:
            sql += " AND (CASE WHEN ps.team_id = m.home_team_id THEN m.away_team_id ELSE m.home_team_id END) = :opp_id"
            params["opp_id"] = opp[0]
        else:
            problems.append(f"unknown opponent '{opponent}'")
    if team:
        t = resolve_team_id(team)
        if t:
            sql += " AND ps.team_id = :team_id"
            params["team_id"] = t[0]
        else:
            problems.append(f"unknown team '{team}'")
    if venue:
        sql += " AND m.venue ILIKE :venue"
        params["venue"] = VenueResolver.resolve_venue(venue) or f"%{venue}%"
    return sql, params, problems


def coverage_notes(stats: List[str], season_from: Optional[int], season_to: Optional[int]) -> List[str]:
    cov = coverage()
    notes = []
    lo = season_from or cov["first_season"]
    hi = season_to or cov["last_season"]
    for s in stats:
        first = STAT_FIRST_SEASON.get(s)
        if first and lo < first:
            notes.append(f"{s} is only recorded from {first}; earlier seasons show 0.")
    scoped = season_from is not None or season_to is not None
    if scoped and cov["missing_stats_rounds"] and lo <= cov["missing_stats_season"] <= hi:
        notes.append(f"{cov['missing_stats_season']} player stats not loaded yet for: "
                     f"{missing_rounds_text(cov['missing_stats_rounds'])}. Totals for that season are partial.")
    if "brownlow_votes" in stats:
        notes.append("brownlow_votes are the per-game votes stored in this database; they may differ from official medal tallies.")
    return notes


class PlayerStatsArgs(BaseModel):
    players: List[str] = Field(description="Player names (nicknames ok) or numeric player ids from resolve_entities")
    stats: List[Stat] = Field(description="Stats to return; empty list = disposals, kicks, handballs, marks, tackles, goals, behinds")
    season_from: Optional[int] = Field(description="First season (inclusive), null = from 1990")
    season_to: Optional[int] = Field(description="Last season (inclusive), null = latest")
    round_name: Optional[str] = Field(description="e.g. 'Round 5', 'Opening Round', 'Grand Final'; null = all rounds")
    opponent: Optional[str] = Field(description="Only games against this team; null = any")
    venue: Optional[str] = Field(description="Only games at this venue; null = any")
    finals: Finals = Field(description="include / exclude / only finals")
    per: Literal["match", "season", "career"] = Field(description="Row granularity: each game, per season, or career total")
    agg: Literal["total", "average", "both"] = Field(description="For season/career rows: totals, per-game averages, or both")

    @field_validator("players")
    @classmethod
    def _plain_players(cls, v: List[str]) -> List[str]:
        return plain_names(v)


def player_stats(args: PlayerStatsArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    stats = list(dict.fromkeys(args.stats or DEFAULT_STATS))
    season_problem = check_seasons(args.season_from, args.season_to)
    if season_problem:
        return result(store, None, why_empty=season_problem)
    ids, labels, problems = resolve_player_ids(args.players, args.season_to or args.season_from)
    where, params, fproblems = _filters(args.season_from, args.season_to, args.round_name, args.finals,
                                        args.opponent, args.venue)
    problems += fproblems
    if not ids:
        return result(store, None, why_empty="; ".join(problems) or "no players given")
    params["pids"] = ids
    base = (" FROM player_stats ps JOIN matches m ON m.id = ps.match_id JOIN players p ON p.id = ps.player_id "
            "LEFT JOIN teams t ON t.id = ps.team_id WHERE ps.player_id = ANY(:pids)" + where)

    if args.per == "match":
        cols = ", ".join(f"ps.{s}" for s in stats)
        sql = (f"SELECT p.name AS player, m.season, {round_name('m')} AS round, m.match_date::date AS date, "
               "t.name AS team, opp.name AS opponent, m.venue, " + cols + base.replace(
                   "LEFT JOIN teams t ON t.id = ps.team_id",
                   "LEFT JOIN teams t ON t.id = ps.team_id LEFT JOIN teams opp ON opp.id = "
                   "(CASE WHEN ps.team_id = m.home_team_id THEN m.away_team_id ELSE m.home_team_id END)")
               + " ORDER BY p.name, m.match_date LIMIT 500")
    else:
        aggs = []
        for s in stats:
            if args.agg in ("total", "both") and s != "time_on_ground_pct":
                aggs.append(f"SUM(COALESCE(ps.{s}, 0)) AS {s}")
            if args.agg in ("average", "both") or s == "time_on_ground_pct":
                aggs.append(f"ROUND(SUM(COALESCE(ps.{s}, 0))::numeric / NULLIF(COUNT(DISTINCT m.id), 0), 2) AS {s}_avg")
        group = "p.id, p.name" + (", m.season" if args.per == "season" else "")
        head = "p.name AS player" + (", m.season" if args.per == "season" else "")
        extra = ("mode() WITHIN GROUP (ORDER BY t.name) AS team" if args.per == "season" else
                 "MIN(m.season) AS first_season, MAX(m.season) AS last_season, "
                 "STRING_AGG(DISTINCT t.name, ', ') AS clubs")
        sql = (f"SELECT {head}, {extra}, COUNT(DISTINCT m.id) AS games, {', '.join(aggs)}{base} "
               f"GROUP BY {group} ORDER BY p.name{', m.season' if args.per == 'season' else ''}")
    df = query(sql, params)
    notes = coverage_notes(stats, args.season_from, args.season_to) + problems
    if args.per == "season" and len(df) and (df["games"] > MAX_SEASON_GAMES).any():
        seasons = [int(s) for s in df.loc[df["games"] > MAX_SEASON_GAMES, "season"]]
        split = query("SELECT m.season, t.name AS team, COUNT(*) AS games FROM player_stats ps "
                      "JOIN matches m ON m.id = ps.match_id JOIN teams t ON t.id = ps.team_id "
                      "WHERE ps.player_id = ANY(:pids) AND m.season = ANY(:seasons) GROUP BY 1, 2 ORDER BY 1, 3 DESC",
                      {"pids": ids, "seasons": seasons})
        by_club = "; ".join(f"{r['season']} {r['team']} {r['games']}" for r in split.to_dict("records"))
        notes.append(f"More than {MAX_SEASON_GAMES} games in a season is impossible: this record likely merges "
                     f"namesakes who played for different clubs (games by club: {by_club}). Tell the user and ask "
                     "which club's player they mean.")
    why = None
    if df.empty:
        why = _why_no_player_rows(ids, args)
    return result(store, df, why_empty=why, notes=notes, players_resolved=labels)


def _why_no_player_rows(ids: List[int], args) -> str:
    cache = load_name_cache()
    reasons = []
    for pid in ids:
        rows = cache[cache["id"] == pid]
        if rows.empty:
            continue
        r = rows.iloc[0]
        lo, hi = args.season_from, args.season_to
        if (lo and lo > r["last_season"]) or (hi and hi < r["first_season"]):
            reasons.append(f"{r['name']} played {r['first_season']}-{r['last_season']} "
                           f"(debut {r['first_season']}), so has no games in the requested seasons")
    cov = coverage()
    rn = normalise_round_name(args.round_name)
    season = args.season_to or args.season_from
    if rn and season == cov["missing_stats_season"] and rn in cov["missing_stats_rounds"]:
        reasons.append(f"player stats for {season} {rn} are not loaded yet")
    return "; ".join(reasons) or "no games match those filters (check round, opponent, venue or finals)"


class LeaderboardArgs(BaseModel):
    stat: Stat = Field(description="Stat to rank players by")
    agg: Literal["total", "average", "single_game"] = Field(
        description="total = sum over the period, average = per game, single_game = best individual games")
    season_from: Optional[int] = Field(description="First season (inclusive), null = from 1990")
    season_to: Optional[int] = Field(description="Last season (inclusive), null = latest")
    round_name: Optional[str] = Field(description="Restrict to one round, e.g. 'Round 20' or 'Grand Final'")
    finals: Finals = Field(description="include / exclude / only finals (Coleman Medal = exclude)")
    team: Optional[str] = Field(description="Only games played for this club; null = all clubs")
    opponent: Optional[str] = Field(description="Only games against this team; null = any")
    min_games: Optional[int] = Field(description="Minimum games to qualify (useful for averages); null = auto")
    limit: int = Field(description="How many places to return (ties at the cut-off are kept), 1-50")
    order: Literal["desc", "asc"] = Field(description="desc = highest first")


def leaderboard(args: LeaderboardArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    season_problem = check_seasons(args.season_from, args.season_to)
    if season_problem:
        return result(store, None, why_empty=season_problem)
    where, params, problems = _filters(args.season_from, args.season_to, args.round_name, args.finals,
                                       args.opponent, None, team=args.team)
    if problems:
        return result(store, None, why_empty="; ".join(problems))
    limit = max(1, min(int(args.limit or 10), 50))
    params["limit"] = limit
    direction = "DESC" if args.order == "desc" else "ASC"
    s = args.stat
    base = (" FROM player_stats ps JOIN matches m ON m.id = ps.match_id JOIN players p ON p.id = ps.player_id "
            "LEFT JOIN teams t ON t.id = ps.team_id WHERE TRUE" + where)
    if args.agg == "single_game":
        sql = (f"SELECT * FROM (SELECT RANK() OVER (ORDER BY ps.{s} {direction}) AS rank, p.name AS player, "
               f"t.name AS team, opp.name AS opponent, m.season, {round_name('m')} AS round, m.match_date::date AS date, "
               f"ps.{s} AS {s}" + base.replace(
                   "LEFT JOIN teams t ON t.id = ps.team_id",
                   "LEFT JOIN teams t ON t.id = ps.team_id LEFT JOIN teams opp ON opp.id = "
                   "(CASE WHEN ps.team_id = m.home_team_id THEN m.away_team_id ELSE m.home_team_id END)")
               + f" AND ps.{s} IS NOT NULL) x WHERE rank <= :limit ORDER BY rank, date")
    else:
        min_games = args.min_games if args.min_games is not None else (5 if args.agg == "average" else 1)
        params["min_games"] = min_games
        value = (f"SUM(COALESCE(ps.{s}, 0))" if args.agg == "total"
                 else f"ROUND(SUM(COALESCE(ps.{s}, 0))::numeric / COUNT(DISTINCT m.id), 2)")
        col = s if args.agg == "total" else f"{s}_per_game"
        sql = (f"SELECT * FROM (SELECT RANK() OVER (ORDER BY {value} {direction}) AS rank, p.name AS player, "
               "mode() WITHIN GROUP (ORDER BY t.name) AS team, COUNT(DISTINCT m.id) AS games, "
               f"{value} AS {col}{base} GROUP BY p.id, p.name HAVING COUNT(DISTINCT m.id) >= :min_games) x "
               "WHERE rank <= :limit ORDER BY rank, player")
    df = query(sql, params)
    notes = coverage_notes([s], args.season_from, args.season_to)
    if len(df) > limit:
        notes.append(f"{len(df)} rows because of ties at the cut-off; mention the tie.")
    why = None
    if df.empty:
        cov = coverage()
        rn = normalise_round_name(args.round_name)
        season = args.season_to or args.season_from
        if rn and season == cov["missing_stats_season"] and rn in cov["missing_stats_rounds"]:
            why = f"player stats for {season} {rn} are not loaded yet (data as of {cov['data_as_of']})"
        else:
            why = "no player games match those filters"
    return result(store, df, why_empty=why, notes=notes)
