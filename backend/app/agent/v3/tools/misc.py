"""
news (cached RSS articles), run_sql (read-only escape hatch through
DatabaseTool, so 1A's validator and agent_ro role apply) and make_chart
(RechartsBuilder -> validated ChartSpecV1; errors go back to the model).
"""
import re
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field

from app.agent.v3.tools.base import ResultStore, clean_frame, log_sql, result

SQL_ROW_LIMIT = 500


class NewsArgs(BaseModel):
    query: Optional[str] = Field(description="Free-text search in titles/summaries; null = latest news")
    teams: List[str] = Field(description="Filter to these teams; empty = all")
    injury_only: bool = Field(description="Only injury news")
    days_back: int = Field(description="How many days back to search, 1-60")


def news(args: NewsArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    from app.agent.tools import NewsTool
    from app.analytics.entity_resolver import EntityResolver

    teams = [EntityResolver.resolve_team(t) or t for t in args.teams]
    filters = {"teams": teams or None, "injury_only": args.injury_only,
               "days_back": max(1, min(int(args.days_back or 7), 60))}
    out = NewsTool.search_news(args.query or "", {k: v for k, v in filters.items() if v}, max_results=8)
    df = pd.DataFrame([{k: a.get(k) for k in ("published_date", "title", "source", "category", "summary", "url")}
                       for a in out.get("articles", [])])
    return result(store, df, why_empty=f"no AFL news found in the last {filters['days_back']} days for that search")


class RunSqlArgs(BaseModel):
    sql: str = Field(description="One read-only PostgreSQL SELECT (or WITH ... SELECT) statement")
    purpose: str = Field(description="One short line: what this query answers")


def run_sql(args: RunSqlArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    from app.agent.tools import DatabaseTool

    sql = args.sql.strip().rstrip(";").strip()
    if ";" in sql:
        return {"error": "only one statement is allowed", "rows": [], "row_count": 0}
    if not re.match(r"(?is)^\s*(select|with)\b", sql):
        return {"error": "only SELECT queries are allowed", "rows": [], "row_count": 0}
    m = re.search(r"(?is)\blimit\s+(\d+)\s*$", sql)
    if m and int(m.group(1)) > SQL_ROW_LIMIT:
        sql = sql[:m.start()] + f"LIMIT {SQL_ROW_LIMIT}"
    elif not m:
        sql = f"{sql}\nLIMIT {SQL_ROW_LIMIT}"
    log_sql(sql)
    res = DatabaseTool.query_database(sql)
    if not res.get("success"):
        # Raw DB error goes to the model (never the user) so it can fix the query.
        return {"error": res.get("raw_error") or res.get("error"), "rows": [], "row_count": 0}
    df = clean_frame(res["data"])
    return result(store, df, why_empty="the query returned no rows; check filters (team names, round names, seasons)")


ChartType = Literal["line", "bar", "horizontal_bar", "grouped_bar", "stacked_bar", "scatter", "pie", "diverging_bar"]

# Categorical x cap: past this a bar/pie is unreadable — ask for a top-N or a table instead (2A).
MAX_CATEGORIES = 25


class MakeChartArgs(BaseModel):
    result_id: str = Field(description="result_id from an earlier tool call in this turn")
    chart_type: ChartType = Field(description="line for trends over seasons/rounds, bar/horizontal_bar for rankings, "
                                               "grouped_bar to compare several metrics or teams, scatter for X vs Y "
                                               "(e.g. 'A vs B' with many rows), pie for shares, diverging_bar for "
                                               "win/loss by season (y=[wins, losses]: wins plotted positive, losses negative)")
    x: str = Field(description="Column for the x axis (categories or season/round)")
    y: List[str] = Field(description="1-6 numeric columns to plot (2 for diverging_bar: positive column first)")
    series_by: Optional[str] = Field(description="Column whose values become separate lines/bars (e.g. team or player); null = none")
    title: str = Field(description="Specific title including who, what and when, e.g. 'Geelong wins per season, 2010-2024'")


def _intify(s: pd.Series) -> pd.Series:
    if s.dtype.kind == "f" and s.dropna().apply(float.is_integer).all():
        return s.astype("Int64").astype(object)
    return s


def make_chart(args: MakeChartArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    from app.visualization.recharts_builder import RechartsBuilder

    df = store.get(args.result_id) if store else None
    if df is None:
        return {"error": f"unknown result_id '{args.result_id}'"}
    ys = list(dict.fromkeys(args.y))[:6]
    missing = [c for c in [args.x, *ys, args.series_by] if c and c not in df.columns]
    if missing:
        return {"error": f"columns not in result: {missing}; available: {list(df.columns)}"}
    non_numeric = [c for c in ys if not pd.api.types.is_numeric_dtype(df[c])]
    if non_numeric:
        return {"error": f"y columns must be numeric: {non_numeric}"}
    if len(df) < 2 and not (args.chart_type == "pie" and len(ys) > 1):
        return {"error": "need at least 2 rows to chart (or a pie of several columns of one row)"}
    data = df.copy()
    ct = args.chart_type
    if ct == "pie" and len(ys) > 1 and len(data) == 1:
        # One row of several totals (e.g. goals vs behinds): each column is a slice.
        data = data[ys].melt(var_name="category", value_name="value")
        data["category"] = data["category"].str.replace("_", " ").str.title()
        args = args.model_copy(update={"x": "category", "series_by": None})
        ys = ["value"]
    data[args.x] = _intify(data[args.x])
    if ct != "scatter":
        # Categorical/ordinal x as text: builders iterate rows, which would upcast 2015 to "2015.0".
        data[args.x] = data[args.x].astype(str)
    params: Dict[str, Any] = {"x_col": args.x, "title": args.title}
    keys = [args.x] + ([args.series_by] if args.series_by else [])
    if ct != "scatter" and data.duplicated(subset=keys).any():
        return {"error": f"x values repeat for {keys}; pass series_by (e.g. team/player) or aggregate first"}
    if (ct in ("bar", "horizontal_bar", "grouped_bar", "stacked_bar", "pie", "diverging_bar")
            and data[args.x].nunique() > MAX_CATEGORIES):
        return {"error": f"too many categories (>{MAX_CATEGORIES}) for a bar/pie chart; use a top-N result or a table instead"}
    if ct == "pie" and (len(ys) > 1 or len(data) > 8):
        return {"error": "pie needs one y column and at most 8 slices; use bar instead"}
    if args.series_by and data[args.series_by].nunique() > 8:
        return {"error": "at most 8 series; for a scatter of many players pass series_by=null"}

    # A series_by with only one distinct value isn't a real split (a model
    # sometimes passes series_by='team' out of habit for a single-team chart)
    # — treat it as none, or a second y column silently gets dropped (B1).
    series_by = args.series_by if (args.series_by and data[args.series_by].nunique() > 1) else None

    if ct == "diverging_bar":
        if series_by:
            return {"error": "diverging_bar does not take series_by; it always plots exactly 2 columns"}
        if len(ys) != 2:
            return {"error": "diverging_bar needs exactly 2 y columns, e.g. y=['wins', 'losses'] (first plotted positive)"}
        params.update(pos_col=ys[0], neg_col=ys[1])
    elif series_by:
        params.update(group_col=series_by, y_col=ys[0])
        if ct in ("bar", "horizontal_bar"):
            ct = "grouped_bar"
    elif len(ys) > 1 and ct in ("line", "scatter"):
        # Several metrics over one x: long format, one line per metric.
        data = data.melt(id_vars=[args.x], value_vars=ys, var_name="metric", value_name="value")
        data["metric"] = data["metric"].str.replace("_", " ").str.title()
        params.update(group_col="metric", y_col="value")
        ct = "line"
    elif len(ys) > 1:
        ct = "stacked_bar" if ct == "stacked_bar" else "comparison"
        params.update(group_col=args.x, metric_cols=ys, y_col=ys[0])
    else:
        params["y_col"] = ys[0]
    spec, error = RechartsBuilder.build_with_errors(data, ct, params)
    if error:
        return {"error": error}
    _apply_highlights(spec, series_by, df)
    if store is not None:
        store.charts.append(spec)
    return {"ok": True, "chart_type": spec["chartType"], "points": len(spec["data"]),
            "series": [s.get("name") for s in spec["series"]]}


_TEAM_SERIES_COLS = {"team", "team_name", "home_team", "away_team", "opponent"}
_PLAYER_SERIES_COLS = {"player", "name", "player_name"}


def _apply_highlights(spec: Optional[Dict[str, Any]], series_col: Optional[str], df: pd.DataFrame) -> None:
    """Populate SeriesItem.highlight (an AFL team name) so the frontend can
    later colour series by club (2A #4): one highlight per series when
    series_by is a team/player column, or the same highlight on every series
    when the whole chart is about a single team or player."""
    if not spec:
        return
    season = pd.to_numeric(df["season"], errors="coerce").dropna() if "season" in df.columns else None
    lo, hi = (int(season.min()), int(season.max())) if season is not None and len(season) else (None, None)

    def _club_for(name: str) -> Optional[str]:
        from app.agent.v3.tools.entities import most_common_team
        try:
            return most_common_team(name, lo, hi)
        except Exception:
            return None

    if series_col:
        lc = series_col.lower()
        for s in spec.get("series", []):
            key = s.get("key")
            if not key:
                continue
            if lc in _TEAM_SERIES_COLS:
                s["highlight"] = key
            elif lc in _PLAYER_SERIES_COLS:
                club = _club_for(key)
                if club:
                    s["highlight"] = club
        return
    for col in _TEAM_SERIES_COLS:
        if col in df.columns and df[col].nunique() == 1:
            highlight = str(df[col].iloc[0])
            for s in spec.get("series", []):
                s["highlight"] = highlight
            return
    for col in _PLAYER_SERIES_COLS:
        if col in df.columns and df[col].nunique() == 1:
            club = _club_for(str(df[col].iloc[0]))
            if club:
                for s in spec.get("series", []):
                    s["highlight"] = club
            return


_TREND_WORDS = re.compile(r"\b(chart|graph|plot|trend|over time|over the years|by season|each season|per season|"
                          r"by year|each year|by round|each round|visuali[sz]e|compare|vs|versus|against|"
                          r"compared to)\b", re.I)
_VS_WORDS = re.compile(r"\b(vs\.?|versus|against)\b", re.I)
_NOT_METRICS = {"rank", "position", "games", "played", "first_season", "last_season", "id", "margin_rank"}
_CONTEXT_COLS = {"venue", "date", "home_away", "result", "opponent", "score", "opponent_score", "clubs"}


def _season_range_suffix(data: pd.DataFrame, x_col: str) -> str:
    """', 2015-2024' (or the single year) when x is a season/year column — a
    specific title beats a generic one (2A #3)."""
    if x_col not in ("season", "year") or x_col not in data.columns:
        return ""
    try:
        vals = sorted(int(v) for v in data[x_col].unique())
    except (TypeError, ValueError):
        return ""
    return f", {vals[0]}" if vals[0] == vals[-1] else f", {vals[0]}-{vals[-1]}"


def fallback_chart(question: str, store: ResultStore) -> Optional[Dict[str, Any]]:
    """When the model skipped make_chart but the question clearly wants one,
    use the ChartSelector heuristics (no LLM) on the last result."""
    df = store.last()
    if df is None or len(df) < 2 or not _TREND_WORDS.search(question or ""):
        return None
    from app.visualization.chart_selector import ChartSelector
    from app.visualization.recharts_builder import RechartsBuilder

    # Never plot bookkeeping columns (B1: charts of `games` instead of the metric).
    # Context columns (venue, date, ...) and single-valued labels must not become series.
    drop = [c for c in df.columns if c in _NOT_METRICS or c in _CONTEXT_COLS
            or (df[c].dtype == object and c not in ("round", "season") and df[c].nunique() <= 1)]
    data = df.drop(columns=drop).copy()
    if "season" in data.columns and data["season"].nunique() == 1:
        data = data.drop(columns=["season"])
    numeric = [c for c in data.columns if pd.api.types.is_numeric_dtype(data[c]) and c not in ("season", "year")]
    labels = [c for c in data.columns if c not in numeric and c not in ("season", "year", "date")]
    q = (question or "").lower()
    mentioned = [c for c in numeric if c.replace("_", " ") in q]

    # "Plot A vs B" / "A against B" with many rows and two numeric metrics: scatter,
    # not a 100+ category bar (review 5: "cannot be read"). Guarded to skip a
    # low-cardinality label (e.g. "team" with 2 values) — that's a team-vs-team
    # trend over seasons, not a many-entity scatter, and the branches below
    # (team pivot, per-season line) already handle it correctly.
    if (len(data) > 20 and _VS_WORDS.search(q) and len(numeric) >= 2
            and (not labels or all(data[c].nunique() > 8 for c in labels))):
        x_col, y_col = (mentioned[0], mentioned[1]) if len(mentioned) >= 2 else (numeric[0], numeric[1])
        spec, _ = RechartsBuilder.build_with_errors(data, "scatter", {
            "x_col": x_col, "y_col": y_col,
            "title": f"{x_col.replace('_', ' ').title()} vs {y_col.replace('_', ' ').title()}"})
        return spec
    if len(data) <= 6 and len(numeric) >= 2 and labels and "season" not in data.columns:
        metrics = [c for c in numeric if not c.endswith("_avg")][:6] or numeric[:6]
        spec, _ = RechartsBuilder.build_with_errors(data, "comparison", {
            "group_col": labels[0], "metric_cols": metrics, "title": ", ".join(data[labels[0]].astype(str))})
        return spec
    if len(data) < 3:
        return None
    asked = [c for c in numeric if re.sub(r"(es|s)$", "", c.split("_")[0]) in q]
    x_time = next((c for c in ("season", "round") if c in data.columns), None)
    if x_time and len(asked) >= 2 and not data.duplicated(subset=[x_time]).any():
        suffix = _season_range_suffix(data, x_time)
        data[x_time] = _intify(data[x_time]).astype(str)
        spec, _ = RechartsBuilder.build_with_errors(
            data.melt(id_vars=[x_time], value_vars=asked[:4], var_name="metric", value_name="value")
                .assign(metric=lambda d: d["metric"].str.replace("_", " ").str.title()),
            "line", {"x_col": x_time, "y_col": "value", "group_col": "metric",
                     "title": " and ".join(a.replace("_", " ") for a in asked[:4]).capitalize()
                              + f" by {x_time}{suffix}"})
        return spec
    # Only the metrics actually named in the question count as "requested" — the
    # heuristics below default to numeric_cols[0] otherwise (B1).
    config = ChartSelector._quick_heuristics(data, "", {"metrics": mentioned}, question)
    if not config or isinstance(config.get("y_col"), list):
        return None
    x, y, group = config.get("x_col"), config.get("y_col"), config.get("group_col")
    suffix = _season_range_suffix(data, x) if x else ""
    if x in data.columns:
        data[x] = _intify(data[x])
        if config["chart_type"] != "scatter":
            data[x] = data[x].astype(str)
    keys = [c for c in (x, group) if c]
    if not x or not y or data.duplicated(subset=keys).any():
        return None
    title = y.replace("_", " ").title() + (f" by {x.replace('_', ' ')}" if x else "") + suffix
    params = {"x_col": x, "y_col": y, "title": title}
    if group:
        params["group_col"] = group
    spec, _ = RechartsBuilder.build_with_errors(data, config["chart_type"], params)
    _apply_highlights(spec, group, df)
    return spec
