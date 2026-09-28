"""
v3 tool registry: name -> (pydantic args model, function, description,
progress label). JSON schemas are generated from the args models, and
`execute` validates model-supplied arguments, returning validation errors to
the model instead of raising.
"""
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from app.agent.v3.tools.base import ResultStore, start_sql_log, strict_schema
from app.agent.v3.tools.entities import ResolveEntitiesArgs, resolve_entities
from app.agent.v3.tools.misc import MakeChartArgs, NewsArgs, RunSqlArgs, make_chart, news, run_sql
from app.agent.v3.tools.stats import LeaderboardArgs, PlayerStatsArgs, leaderboard, player_stats
from app.agent.v3.tools.teams import (
    HeadToHeadArgs, LadderArgs, MatchLookupArgs, TeamResultsArgs, head_to_head, ladder,
    match_lookup, team_results,
)

logger = logging.getLogger(__name__)


@dataclass
class ToolDef:
    name: str
    args: Type[BaseModel]
    fn: Callable[[Any, Optional[ResultStore]], Dict[str, Any]]
    description: str
    label: Callable[[Dict[str, Any]], str]


def _who(a: Dict[str, Any], key: str) -> str:
    v = a.get(key)
    return ", ".join(v[:2]) if isinstance(v, list) else (v or "")


def _when(a: Dict[str, Any]) -> str:
    lo, hi = a.get("season_from") or a.get("season"), a.get("season_to")
    if lo and hi and lo != hi:
        return f" ({lo}-{hi})"
    return f" ({lo or hi})" if (lo or hi) else ""


TOOLS: Dict[str, ToolDef] = {t.name: t for t in [
    ToolDef("resolve_entities", ResolveEntitiesArgs, resolve_entities,
            "Resolve player/team names, nicknames (Dusty, Buddy, Bont, Cats), surnames and typos to canonical "
            "database names and ids. Returns several candidates for namesakes, with clubs and seasons.",
            lambda a: f"Finding {_who(a, 'names')}"),
    ToolDef("player_stats", PlayerStatsArgs, player_stats,
            "Stats for specific players: per game, per season or career, totals and/or per-game averages, "
            "optionally filtered by seasons, round, opponent, venue, finals. Accepts names directly.",
            lambda a: f"Looking up {_who(a, 'players')}'s stats{_when(a)}"),
    ToolDef("leaderboard", LeaderboardArgs, leaderboard,
            "Rank players by one stat (total, per-game average, or best single games) over seasons/rounds, "
            "optionally for one club or against one opponent. Ties at the cut-off are kept.",
            lambda a: f"Ranking players by {a.get('stat', 'stat').replace('_', ' ')}{_when(a)}"),
    ToolDef("team_results", TeamResultsArgs, team_results,
            "A team's results: every game, per-season win/loss/draw records with points for/against and "
            "percentage, or one total. Filters: seasons, opponent, venue, finals.",
            lambda a: f"Checking {a.get('team', 'team')} results{_when(a)}"),
    ToolDef("head_to_head", HeadToHeadArgs, head_to_head,
            "Head-to-head record between two teams per season with totals and the last meetings.",
            lambda a: f"Comparing {a.get('team_a', '')} and {a.get('team_b', '')}{_when(a)}"),
    ToolDef("match_lookup", MatchLookupArgs, match_lookup,
            "Find matches by season, round (name or number, finals by name), date and/or teams, or record "
            "games via order_by (highest total, biggest margin). Scores as goals.behinds (total); optional quarters.",
            lambda a: "Finding the match" + _when(a)),
    ToolDef("ladder", LadderArgs, ladder,
            "Home-and-away ladder for a season (optionally after a round): position, W/L/D, premiership points, "
            "percentage. Ranks all teams, then filters to the requested teams.",
            lambda a: f"Building the {a.get('season', '')} ladder"),
    ToolDef("news", NewsArgs, news,
            "Recent AFL news articles (injuries, trades, match reports) from cached RSS feeds.",
            lambda a: "Checking the latest news"),
    ToolDef("run_sql", RunSqlArgs, run_sql,
            "Escape hatch: one read-only SELECT against the AFL tables when no other tool fits. Max 500 rows.",
            lambda a: "Running a custom query"),
    ToolDef("make_chart", MakeChartArgs, make_chart,
            "Chart an earlier tool result (by result_id). Call it when a chart helps: trends over seasons/rounds, "
            "rankings, comparisons. Returns an error to fix if the spec is invalid.",
            lambda a: "Drawing a chart"),
]}


def tool_schemas() -> List[Dict[str, Any]]:
    """Neutral tool specs for llm.chat, in a fixed order (cache-stable prefix)."""
    return [{"name": t.name, "description": t.description, "parameters": strict_schema(t.args)}
            for t in TOOLS.values()]


def progress_label(name: str, raw_args: str) -> str:
    tool = TOOLS.get(name)
    try:
        return tool.label(json.loads(raw_args or "{}")) if tool else name
    except Exception:
        return name.replace("_", " ").capitalize()


def execute(name: str, raw_args: str, store: ResultStore) -> Dict[str, Any]:
    """Run one tool call. Returns {output (dict for the model), sql, error, latency_s}."""
    t0 = time.monotonic()
    sql_log = start_sql_log()
    tool = TOOLS.get(name)
    out: Dict[str, Any]
    error = None
    if tool is None:
        out = {"error": f"unknown tool '{name}'"}
    else:
        try:
            args = tool.args.model_validate_json(raw_args or "{}")
            out = tool.fn(args, store)
        except ValidationError as e:
            out = {"error": f"invalid arguments: {e.errors(include_url=False)}"}
        except Exception as e:
            logger.exception(f"v3 tool {name} failed")
            out = {"error": f"tool failed: {type(e).__name__}"}
    error = out.get("error")
    return {"output": out, "sql": list(sql_log), "error": error, "latency_s": round(time.monotonic() - t0, 3)}
