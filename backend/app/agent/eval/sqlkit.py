"""
SQL builders for verification queries.

Written to work BEFORE and AFTER 1C's schema/data work:
  - home-and-away = numeric round <= 24 (2026 stores finals as '25'-'29'
    today; after 1C they may be named; both are excluded either way)
  - finals = NOT home-and-away (catches '25'-'29' and 'Grand Final' alike)
  - a season's grand final = its last match by date (2007/2020 finals carry
    numeric rounds, 2026 uses '29', others 'Grand Final')
  - player totals group by player id (team-swapped stat rows cannot split
    them); "games" = rows with disposals > 0 (ignores phantom all-zero rows)
  - NULL goals count as 0 (2024 stores NULL for many zero-goal games)
"""

HA = "(m.round ~ '^[0-9]+$' and m.round::int <= 24)"
FINALS = f"(not {HA})"
CUR = "(select max(season) from matches)"
PLAYED = "coalesce(ps.disposals, 0) > 0"


def win(t: int) -> str:
    return f"((m.home_team_id={t} and m.home_score>m.away_score) or (m.away_team_id={t} and m.away_score>m.home_score))"


def loss(t: int) -> str:
    return f"((m.home_team_id={t} and m.home_score<m.away_score) or (m.away_team_id={t} and m.away_score<m.home_score))"


def pts_for(t: int) -> str:
    return f"(case when m.home_team_id={t} then m.home_score else m.away_score end)"


def record(t: int, season: str, where: str = "true") -> str:
    """wins/losses/draws/games (all matches) + HA wins/losses for one team-season."""
    return (
        f"select count(*) filter (where {win(t)}) wins, count(*) filter (where {loss(t)}) losses, "
        f"count(*) filter (where m.home_score=m.away_score) draws, count(*) games, "
        f"count(*) filter (where {win(t)} and {HA}) wins_ha, count(*) filter (where {loss(t)} and {HA}) losses_ha "
        f"from matches m where {t} in (m.home_team_id, m.away_team_id) and m.season={season} "
        f"and m.home_score is not null and {where}"
    )


def per_season_wins(teams: dict, lo: int, hi: str = CUR, losses: bool = False) -> str:
    """Long rows (season, team, metric, value) of wins (and losses) per season."""
    parts = []
    for t, name in teams.items():
        parts.append(
            f"select m.season, '{name}' team, 'wins' metric, count(*) filter (where {win(t)}) value "
            f"from matches m where {t} in (m.home_team_id, m.away_team_id) and m.season between {lo} and {hi} "
            f"and m.home_score is not null group by m.season"
        )
        if losses:
            parts.append(
                f"select m.season, '{name}' team, 'losses' metric, count(*) filter (where {loss(t)}) value "
                f"from matches m where {t} in (m.home_team_id, m.away_team_id) and m.season between {lo} and {hi} "
                f"and m.home_score is not null group by m.season"
            )
    return " union all ".join(parts) + " order by 1, 2, 3"


def grand_final(season: str) -> str:
    """winner/loser/scores/margin of a season's last match."""
    return (
        "select w.name winner, l.name loser, greatest(m.home_score, m.away_score) winner_score, "
        "least(m.home_score, m.away_score) loser_score, abs(m.home_score - m.away_score) margin, m.match_date "
        f"from (select * from matches where season={season} and home_score is not null "
        "order by match_date desc, id desc limit 1) m "
        "join teams w on w.id = case when m.home_score > m.away_score then m.home_team_id else m.away_team_id end "
        "join teams l on l.id = case when m.home_score > m.away_score then m.away_team_id else m.home_team_id end"
    )


def ladder(season: str) -> str:
    """Home-and-away ladder: pos, team, wins, draws, losses, pts, pct (ranked over ALL teams)."""
    return (
        "with g as (select m.home_team_id t, m.home_score f, m.away_score a from matches m "
        f"where m.season={season} and {HA} and m.home_score is not null "
        "union all select m.away_team_id, m.away_score, m.home_score from matches m "
        f"where m.season={season} and {HA} and m.home_score is not null), "
        "l as (select t, count(*) played, sum((f>a)::int) wins, sum((f=a)::int) draws, sum((f<a)::int) losses, "
        "sum(f) pf, sum(a) pa, 4*sum((f>a)::int)+2*sum((f=a)::int) pts, round(100.0*sum(f)/sum(a), 2) pct from g group by t) "
        "select rank() over (order by pts desc, pct desc) pos, tm.name team, l.* from l join teams tm on tm.id=l.t"
    )


def ladder_team(season: str, team: str) -> str:
    # Filter AFTER ranking (B2: filtering inside the CTE always yields rank 1).
    return f"select * from ({ladder(season)}) x where team='{team}'"


def player_total(name: str, cols: dict, season: str = None, team: int = None, where: str = "true") -> str:
    """Sum/avg of stats for one player name. cols: alias -> SQL expr over ps/m."""
    sel = ", ".join(f"{expr} {alias}" for alias, expr in cols.items())
    filt = [f"p.name = '{name}'", where]
    if season:
        filt.append(f"m.season = {season}")
    if team:
        filt.append(f"ps.team_id = {team}")
    return (
        f"select {sel} from player_stats ps join players p on p.id=ps.player_id "
        f"join matches m on m.id=ps.match_id where {' and '.join(filt)}"
    )


def leaders(stat_expr: str, season: str, n: int = 1, where: str = "true", alias: str = "value") -> str:
    """Players ranked by a season total (ties included via rank()).

    Also returns `<alias>_ha`, the home-and-away-only total: "most goals in
    2023" is fairly answered either way (Coleman counts H&A only).
    """
    ha_expr = f"{stat_expr} filter (where {HA})" if stat_expr.startswith("sum(") else "null"
    return (
        f"select * from (select p.name, {stat_expr} {alias}, {ha_expr} {alias}_ha, "
        f"rank() over (order by {stat_expr} desc nulls last) rnk "
        "from player_stats ps join players p on p.id=ps.player_id join matches m on m.id=ps.match_id "
        f"where m.season={season} and {where} group by p.id, p.name) x where rnk <= {n} order by rnk, name"
    )


def season_range() -> str:
    return "select min(season) lo, max(season) hi from matches"
