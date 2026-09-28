"""
Team and match tools: team_results, head_to_head, match_lookup, ladder.
All read `matches` only (never live_games, which duplicates it), limited to
AFL clubs. Scores are returned as AFL strings, goals.behinds (total), plus
numeric columns for charts.
"""
import re
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from app.agent.v3.tools.base import (
    AFL_TEAM_IDS, ResultStore, check_seasons, finals_clause, is_final, normalise_round_name,
    query, result, round_name, round_number, score_str, seq,
)
from app.agent.v3.tools.entities import resolve_team_id
from app.analytics.entity_resolver import VenueResolver

Finals = Literal["include", "exclude", "only"]
EARLY_90S_NOTE = ("Seasons 1990-1996 are missing some matches (mostly Fitzroy), so early-90s "
                  "win totals and ladders may be understated.")
PLAYED = "(m.home_score IS NOT NULL AND (m.home_score > 0 OR m.away_score > 0))"


def _team_rows_cte(where: str) -> str:
    """One row per team per played match (home and away sides unrolled)."""
    cols = (f"m.id AS match_id, m.season, {round_name('m')} AS round, {round_number('m')} AS round_number, "
            f"{is_final('m')} AS is_final, m.match_date, m.venue, m.attendance")
    side = ("SELECT {cols}, m.{a}_team_id AS team_id, m.{b}_team_id AS opp_id, {home} AS is_home, "
            "m.{a}_score AS score, m.{b}_score AS opp_score, m.{a}_q4_goals AS goals, m.{a}_q4_behinds AS behinds, "
            "m.{b}_q4_goals AS opp_goals, m.{b}_q4_behinds AS opp_behinds FROM matches m "
            f"WHERE {PLAYED} AND m.home_team_id = ANY(:afl_ids) AND m.away_team_id = ANY(:afl_ids){where}")
    return ("WITH tm AS (" + side.format(cols=cols, a="home", b="away", home="TRUE") + " UNION ALL "
            + side.format(cols=cols, a="away", b="home", home="FALSE") + ")")


def _season_where(season_from, season_to, params) -> str:
    sql = ""
    if season_from:
        sql += " AND m.season >= :season_from"
        params["season_from"] = season_from
    if season_to:
        sql += " AND m.season <= :season_to"
        params["season_to"] = season_to
    return sql


def _early_note(season_from, season_to) -> Optional[str]:
    return EARLY_90S_NOTE if (season_from or 1990) <= 1996 and (season_to or 2100) >= 1990 else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _score_cols(df: pd.DataFrame, pairs) -> pd.DataFrame:
    for out, g, b, t in pairs:
        df[out] = [score_str(x, y, z) for x, y, z in zip(df[g], df[b], df[t])]
    return df


class TeamResultsArgs(BaseModel):
    team: str = Field(description="Team name or nickname")
    season_from: Optional[int] = Field(description="First season (inclusive), null = from 1990")
    season_to: Optional[int] = Field(description="Last season (inclusive), null = latest")
    opponent: Optional[str] = Field(description="Only games against this team; null = any")
    venue: Optional[str] = Field(description="Only games at this venue; null = any")
    finals: Finals = Field(description="include / exclude / only finals")
    per: Literal["match", "season", "total"] = Field(description="Each game, a row per season, or one total row")


def team_results(args: TeamResultsArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    problem = check_seasons(args.season_from, args.season_to)
    team = resolve_team_id(args.team)
    if problem or not team:
        return result(store, None, why_empty=problem or f"unknown team '{args.team}'")
    params: Dict[str, Any] = {"afl_ids": list(AFL_TEAM_IDS), "team_id": team[0]}
    where = _season_where(args.season_from, args.season_to, params) + finals_clause(args.finals)
    outer = " WHERE tm.team_id = :team_id"
    if args.opponent:
        opp = resolve_team_id(args.opponent)
        if not opp:
            return result(store, None, why_empty=f"unknown opponent '{args.opponent}'")
        outer += " AND tm.opp_id = :opp_id"
        params["opp_id"] = opp[0]
    if args.venue:
        where += " AND m.venue ILIKE :venue"
        params["venue"] = VenueResolver.resolve_venue(args.venue) or f"%{args.venue}%"
    cte = _team_rows_cte(where)
    if args.per == "match":
        df = query(cte + " SELECT tm.match_date::date AS date, tm.season, tm.round, o.name AS opponent, tm.venue, "
                   "CASE WHEN tm.is_home THEN 'home' ELSE 'away' END AS home_away, tm.goals, tm.behinds, "
                   "tm.score AS team_points, tm.opp_goals, tm.opp_behinds, tm.opp_score AS opponent_points, "
                   "CASE WHEN tm.score > tm.opp_score THEN 'W' WHEN tm.score < tm.opp_score THEN 'L' ELSE 'D' END AS result, "
                   "tm.score - tm.opp_score AS margin FROM tm JOIN teams o ON o.id = tm.opp_id"
                   + outer + " ORDER BY tm.match_date LIMIT 500", params)
        if len(df):
            df = _score_cols(df, [("score", "goals", "behinds", "team_points"),
                                  ("opponent_score", "opp_goals", "opp_behinds", "opponent_points")])
            df = df.drop(columns=["goals", "behinds", "opp_goals", "opp_behinds"])
    else:
        group = "tm.season" if args.per == "season" else "1"
        head = "tm.season, " if args.per == "season" else ""
        df = query(cte + f" SELECT {head}COUNT(*) AS games, "
                   "COUNT(*) FILTER (WHERE tm.score > tm.opp_score) AS wins, "
                   "COUNT(*) FILTER (WHERE tm.score < tm.opp_score) AS losses, "
                   "COUNT(*) FILTER (WHERE tm.score = tm.opp_score) AS draws, "
                   "SUM(tm.score) AS points_for, SUM(tm.opp_score) AS points_against, "
                   "ROUND(SUM(tm.score) * 100.0 / NULLIF(SUM(tm.opp_score), 0), 1) AS percentage, "
                   "ROUND(AVG(tm.score), 1) AS avg_score, ROUND(AVG(tm.opp_score), 1) AS avg_conceded "
                   f"FROM tm{outer} GROUP BY {group} ORDER BY {group}", params)
        if args.per == "total" and len(df) and int(df["games"].iloc[0]) == 0:
            df = df.head(0)
    notes = [_early_note(args.season_from, args.season_to)]
    if args.finals == "include" and args.per != "match":
        notes.append("Win/loss counts include finals; ladder position uses the ladder tool (home-and-away only).")
    return result(store, df, why_empty="no played matches for that team with those filters",
                  notes=notes, team=team[1])


class HeadToHeadArgs(BaseModel):
    team_a: str = Field(description="First team")
    team_b: str = Field(description="Second team")
    season_from: Optional[int] = Field(description="First season (inclusive), null = from 1990")
    season_to: Optional[int] = Field(description="Last season (inclusive), null = latest")
    finals: Finals = Field(description="include / exclude / only finals")


def head_to_head(args: HeadToHeadArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    problem = check_seasons(args.season_from, args.season_to)
    a, b = resolve_team_id(args.team_a), resolve_team_id(args.team_b)
    if problem or not a or not b:
        return result(store, None, why_empty=problem or f"unknown team '{args.team_a if not a else args.team_b}'")
    params: Dict[str, Any] = {"afl_ids": list(AFL_TEAM_IDS), "a": a[0], "b": b[0]}
    where = _season_where(args.season_from, args.season_to, params) + finals_clause(args.finals)
    cte = _team_rows_cte(where)
    sa, sb = _slug(a[1]), _slug(b[1])
    df = query(cte + " SELECT tm.season, COUNT(*) AS games, "
               f"COUNT(*) FILTER (WHERE tm.score > tm.opp_score) AS {sa}_wins, "
               f"COUNT(*) FILTER (WHERE tm.score < tm.opp_score) AS {sb}_wins, "
               "COUNT(*) FILTER (WHERE tm.score = tm.opp_score) AS draws, "
               f"SUM(tm.score) AS {sa}_points, SUM(tm.opp_score) AS {sb}_points "
               "FROM tm WHERE tm.team_id = :a AND tm.opp_id = :b GROUP BY tm.season ORDER BY tm.season", params)
    summary = None
    if len(df):
        last = query(cte + " SELECT tm.match_date::date AS date, tm.season, tm.round, tm.venue, "
                     "tm.goals, tm.behinds, tm.score, tm.opp_goals, tm.opp_behinds, tm.opp_score "
                     "FROM tm WHERE tm.team_id = :a AND tm.opp_id = :b ORDER BY tm.match_date DESC LIMIT 3", params)
        summary = {
            "games": int(df["games"].sum()), f"{sa}_wins": int(df[f"{sa}_wins"].sum()),
            f"{sb}_wins": int(df[f"{sb}_wins"].sum()), "draws": int(df["draws"].sum()),
            "last_meetings": [
                {"date": r["date"], "season": r["season"], "round": r["round"], "venue": r["venue"],
                 a[1]: score_str(r["goals"], r["behinds"], r["score"]),
                 b[1]: score_str(r["opp_goals"], r["opp_behinds"], r["opp_score"])}
                for r in last.to_dict("records")],
        }
    return result(store, df, why_empty=f"{a[1]} and {b[1]} have not met in those seasons",
                  notes=[_early_note(args.season_from, args.season_to)], summary=summary)


class MatchLookupArgs(BaseModel):
    season: Optional[int] = Field(description="Season; null = all seasons (use with order_by for records)")
    round_name: Optional[str] = Field(description="e.g. 'Round 5', 'Opening Round', 'Qualifying Final', 'Grand Final'")
    round_number: Optional[int] = Field(description="Round number instead of name; null if round_name used")
    date: Optional[str] = Field(description="Match date YYYY-MM-DD; null = any")
    teams: List[str] = Field(description="0-2 teams; with 2, only matches between them")
    finals: Finals = Field(description="include / exclude / only finals")
    order_by: Literal["date", "date_desc", "highest_total", "biggest_margin", "highest_team_score", "lowest_team_score"] = Field(
        description="Sort order; the record-style orders find e.g. the highest scoring game")
    include_quarters: bool = Field(description="Add quarter-by-quarter cumulative scores")
    limit: int = Field(description="Max matches, 1-50")


def match_lookup(args: MatchLookupArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    problem = check_seasons(args.season, args.season)
    if problem:
        return result(store, None, why_empty=problem)
    params: Dict[str, Any] = {"afl_ids": list(AFL_TEAM_IDS), "limit": max(1, min(int(args.limit or 10), 50))}
    where = f" WHERE {PLAYED} AND m.home_team_id = ANY(:afl_ids) AND m.away_team_id = ANY(:afl_ids)"
    if args.season:
        where += " AND m.season = :season"
        params["season"] = args.season
    rn = normalise_round_name(args.round_name)
    if rn:
        where += f" AND {round_name('m')} = :rn"
        params["rn"] = rn
    if args.round_number is not None:
        where += f" AND {round_number('m')} = :rnum"
        params["rnum"] = args.round_number
    if args.date:
        where += " AND m.match_date::date = CAST(:date AS date)"
        params["date"] = args.date
    where += finals_clause(args.finals)
    for i, t in enumerate(seq(args.teams)[:2]):
        tid = resolve_team_id(t)
        if not tid:
            return result(store, None, why_empty=f"unknown team '{t}'")
        where += f" AND :t{i} IN (m.home_team_id, m.away_team_id)"
        params[f"t{i}"] = tid[0]
    order = {
        "date": "m.match_date", "date_desc": "m.match_date DESC",
        "highest_total": "m.home_score + m.away_score DESC", "biggest_margin": "ABS(m.home_score - m.away_score) DESC",
        "highest_team_score": "GREATEST(m.home_score, m.away_score) DESC",
        "lowest_team_score": "LEAST(m.home_score, m.away_score) ASC",
    }[args.order_by]
    quarters = ""
    if args.include_quarters:
        quarters = ", " + ", ".join(f"m.{s}_q{q}_goals AS {s}_q{q}_g, m.{s}_q{q}_behinds AS {s}_q{q}_b"
                                     for s in ("home", "away") for q in (1, 2, 3, 4))
    df = query(f"SELECT m.match_date AS date, m.season, {round_name('m')} AS round, ht.name AS home_team, "
               "at.name AS away_team, m.home_q4_goals AS hg, m.home_q4_behinds AS hb, m.home_score AS home_points, "
               "m.away_q4_goals AS ag, m.away_q4_behinds AS ab, m.away_score AS away_points, "
               "CASE WHEN m.home_score > m.away_score THEN ht.name WHEN m.away_score > m.home_score THEN at.name ELSE 'Draw' END AS winner, "
               f"ABS(m.home_score - m.away_score) AS margin, m.venue, m.attendance{quarters} "
               "FROM matches m JOIN teams ht ON ht.id = m.home_team_id JOIN teams at ON at.id = m.away_team_id"
               f"{where} ORDER BY {order} LIMIT :limit", params)
    if len(df):
        df = _score_cols(df, [("home_score", "hg", "hb", "home_points"), ("away_score", "ag", "ab", "away_points")])
        if args.include_quarters:
            for s in ("home", "away"):
                for q in (1, 2, 3, 4):
                    g, b = df[f"{s}_q{q}_g"], df[f"{s}_q{q}_b"]
                    df[f"{s}_q{q}"] = [f"{int(x)}.{int(y)} ({int(x) * 6 + int(y)})" if pd.notna(x) and pd.notna(y) else None
                                       for x, y in zip(g, b)]
                    df = df.drop(columns=[f"{s}_q{q}_g", f"{s}_q{q}_b"])
        df = df.drop(columns=["hg", "hb", "ag", "ab"])
        if df["attendance"].isna().all():
            df = df.drop(columns=["attendance"])
    why = "no played match matches those filters"
    if rn and args.season and df.empty:
        rounds = query(f"SELECT DISTINCT {round_name('m')} AS r FROM matches m WHERE m.season = :s AND {is_final('m')}",
                       {"s": args.season})
        why += f" (finals rounds recorded for {args.season}: {', '.join(rounds['r'].tolist()) or 'none'})"
    return result(store, df, why_empty=why)


class LadderArgs(BaseModel):
    season: int = Field(description="Season")
    after_round: Optional[int] = Field(description="Ladder after this home-and-away round number; null = end of home-and-away season")
    teams: List[str] = Field(description="Only return these teams' rows (ranking is still over all teams); empty = full ladder")


def ladder(args: LadderArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    problem = check_seasons(args.season, args.season)
    if problem:
        return result(store, None, why_empty=problem)
    params: Dict[str, Any] = {"afl_ids": list(AFL_TEAM_IDS), "season": args.season}
    where = f" AND m.season = :season AND NOT {is_final('m')}"
    if args.after_round is not None:
        where += f" AND {round_number('m')} <= :after_round"
        params["after_round"] = args.after_round
    team_ids = []
    for t in seq(args.teams):
        tid = resolve_team_id(t)
        if not tid:
            return result(store, None, why_empty=f"unknown team '{t}'")
        team_ids.append(tid[0])
    # Rank over every team first, filter afterwards (B2: filtering first always ranks 1st).
    sql = (_team_rows_cte(where) + ", rec AS (SELECT tm.team_id, COUNT(*) AS played, "
           "COUNT(*) FILTER (WHERE tm.score > tm.opp_score) AS wins, "
           "COUNT(*) FILTER (WHERE tm.score < tm.opp_score) AS losses, "
           "COUNT(*) FILTER (WHERE tm.score = tm.opp_score) AS draws, "
           "SUM(tm.score) AS points_for, SUM(tm.opp_score) AS points_against FROM tm GROUP BY tm.team_id), "
           "ranked AS (SELECT RANK() OVER (ORDER BY wins * 4 + draws * 2 DESC, "
           "points_for::numeric / NULLIF(points_against, 0) DESC) AS position, t.name AS team, rec.* , "
           "wins * 4 + draws * 2 AS premiership_points, "
           "ROUND(points_for * 100.0 / NULLIF(points_against, 0), 1) AS percentage "
           "FROM rec JOIN teams t ON t.id = rec.team_id) "
           "SELECT position, team, played, wins, losses, draws, premiership_points, points_for, points_against, "
           "percentage FROM ranked" + (" WHERE team_id = ANY(:tids)" if team_ids else "") + " ORDER BY position")
    if team_ids:
        params["tids"] = team_ids
    df = query(sql, params)
    notes = ["Home-and-away matches only (finals excluded); 4 points per win, 2 per draw, ties split by percentage.",
             _early_note(args.season, args.season)]
    return result(store, df, why_empty=f"no home-and-away matches recorded for {args.season}"
                  + (f" up to round {args.after_round}" if args.after_round is not None else ""), notes=notes)
