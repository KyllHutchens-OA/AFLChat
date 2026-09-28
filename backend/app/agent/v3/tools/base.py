"""
Shared plumbing for v3 tools: DB access, value coercion, the per-turn result
store, round-column expressions and the strict JSON schema generator.

Every tool returns a ToolResult dict:
  {rows (capped), row_count, result_id, columns, why_empty, notes}
`rows` is what the model sees; the full DataFrame stays in the ResultStore
under `result_id` so make_chart can plot all of it.
"""
import contextvars
import datetime as dt
import logging
import math
import re
import threading
import time
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence, Type

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import text

from app.data.database import Session

logger = logging.getLogger(__name__)

# 18 current clubs + Fitzroy. Tools never touch other `teams` rows.
AFL_TEAM_IDS: tuple = tuple(range(11, 30))
MODEL_ROW_CAP = 25

STATS = (
    "goals", "behinds", "disposals", "kicks", "handballs", "marks", "tackles", "hitouts",
    "clearances", "inside_50s", "rebound_50s", "contested_possessions",
    "uncontested_possessions", "contested_marks", "marks_inside_50", "one_percenters",
    "bounces", "clangers", "free_kicks_for", "free_kicks_against", "brownlow_votes",
    "goal_assist", "time_on_ground_pct", "fantasy_points",
)

# Stat -> first season it is recorded (earlier seasons hold 0/NULL, not real values).
STAT_FIRST_SEASON = {
    "contested_possessions": 1999, "uncontested_possessions": 1999, "contested_marks": 1999,
    "marks_inside_50": 1999, "one_percenters": 1999, "bounces": 1999, "goal_assist": 2003,
    "clearances": 1998, "rebound_50s": 1998, "inside_50s": 1998, "clangers": 1998,
    "time_on_ground_pct": 2003,
}


# SQL executed during the current tool call, collected for the chat trace.
_sql_log: contextvars.ContextVar = contextvars.ContextVar("v3_sql_log", default=None)


def start_sql_log() -> List[str]:
    log: List[str] = []
    _sql_log.set(log)
    return log


def log_sql(sql: str) -> None:
    log = _sql_log.get()
    if log is not None:
        log.append(" ".join(sql.split()))


def query(sql: str, params: Optional[Dict[str, Any]] = None) -> pd.DataFrame:
    log_sql(sql)
    session = Session()
    try:
        result = session.execute(text(sql), params or {})
        return clean_frame(pd.DataFrame(result.fetchall(), columns=list(result.keys())))
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _clean_value(v: Any) -> Any:
    if isinstance(v, Decimal):
        v = float(v)
    if isinstance(v, float):
        return None if math.isnan(v) or math.isinf(v) else round(v, 2)
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        return v.strftime("%Y-%m-%d %H:%M") if (v.hour or v.minute) else v.strftime("%Y-%m-%d")
    if isinstance(v, dt.date):
        return v.isoformat()
    if hasattr(v, "item"):
        return v.item()
    return v


def clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Decimal -> float (rounded), dates -> strings, so rows are JSON-safe."""
    for col in df.columns:
        if df[col].dtype == object or str(df[col].dtype).startswith("datetime"):
            df[col] = df[col].map(_clean_value)
            try:
                if df[col].map(lambda x: x is None or isinstance(x, (int, float))).all() and df[col].notna().any():
                    df[col] = pd.to_numeric(df[col])
            except (TypeError, ValueError):
                pass
        elif str(df[col].dtype).startswith("float"):
            df[col] = df[col].round(2)
    return df


class ResultStore:
    """Per-turn store of full tool results, addressed by result_id."""

    def __init__(self):
        self._frames: Dict[str, pd.DataFrame] = {}
        self._lock = threading.Lock()
        self.charts: List[Dict[str, Any]] = []  # validated ChartSpecV1 dicts from make_chart

    def put(self, df: pd.DataFrame) -> str:
        with self._lock:  # tools run in parallel threads
            rid = f"r{len(self._frames) + 1}"
            self._frames[rid] = df
        return rid

    def get(self, rid: str) -> Optional[pd.DataFrame]:
        return self._frames.get(rid)

    def last(self) -> Optional[pd.DataFrame]:
        return list(self._frames.values())[-1] if self._frames else None


def result(store: Optional[ResultStore], df: Optional[pd.DataFrame], *, why_empty: Optional[str] = None,
           notes: Optional[List[str]] = None, cap: int = MODEL_ROW_CAP, **extra) -> Dict[str, Any]:
    df = df if df is not None else pd.DataFrame()
    rid = store.put(df) if (store is not None and len(df)) else None
    head = df.head(cap).astype(object)
    out = {
        "rows": head.where(head.notna(), None).to_dict(orient="records"),
        "row_count": int(len(df)),
        "result_id": rid,
        "columns": list(df.columns),
        "why_empty": why_empty if not len(df) else None,
        "notes": [n for n in (notes or []) if n],
    }
    if len(df) > cap:
        out["notes"].append(f"Showing first {cap} of {len(df)} rows; make_chart can use all rows via result_id.")
    out.update(extra)
    return out


# ── Round columns (1C) with a legacy fallback ───────────────────────────────

_round_cols: Dict[str, Any] = {"checked": 0.0, "native": None}


def has_round_columns() -> bool:
    """True once matches.round_number/round_name/is_final exist (1C migration)."""
    if _round_cols["native"] is None or time.time() - _round_cols["checked"] > 3600:
        try:
            df = query("SELECT count(*) AS n FROM information_schema.columns WHERE table_name = 'matches' "
                       "AND column_name IN ('round_number', 'round_name', 'is_final')")
            _round_cols["native"] = int(df["n"].iloc[0]) == 3
        except Exception as e:
            logger.warning(f"round column check failed: {e}")
            _round_cols["native"] = False
        _round_cols["checked"] = time.time()
    return bool(_round_cols["native"])


def round_name(a: str = "m") -> str:
    if has_round_columns():
        return f"{a}.round_name"
    return (f"(CASE WHEN {a}.round = '0' THEN 'Opening Round' WHEN {a}.round ~ '^[0-9]+$' "
            f"THEN 'Round ' || {a}.round ELSE {a}.round END)")


def is_final(a: str = "m") -> str:
    return f"{a}.is_final" if has_round_columns() else f"({a}.round !~ '^[0-9]+$')"


def round_number(a: str = "m") -> str:
    if has_round_columns():
        return f"{a}.round_number"
    return f"(CASE WHEN {a}.round ~ '^[0-9]+$' THEN {a}.round::int END)"


def finals_clause(mode: str, a: str = "m") -> str:
    return {"exclude": f" AND NOT {is_final(a)}", "only": f" AND {is_final(a)}"}.get(mode, "")


def normalise_round_name(name: Optional[str]) -> Optional[str]:
    """'GF' / 'grand final' / 'r5' / '5' -> canonical round_name."""
    if not name:
        return None
    s = str(name).strip().lower().replace("round ", "r").replace("rd ", "r")
    aliases = {
        "gf": "Grand Final", "grand final": "Grand Final", "pf": "Preliminary Final",
        "preliminary final": "Preliminary Final", "prelim": "Preliminary Final",
        "sf": "Semi Final", "semi final": "Semi Final", "semi": "Semi Final",
        "qf": "Qualifying Final", "qualifying final": "Qualifying Final",
        "ef": "Elimination Final", "elimination final": "Elimination Final",
        "wildcard": "Wildcard Round", "wildcard round": "Wildcard Round", "wild card round": "Wildcard Round",
        "opening round": "Opening Round", "r0": "Opening Round", "0": "Opening Round",
    }
    if s in aliases:
        return aliases[s]
    s = s.lstrip("r")
    return f"Round {int(s)}" if s.isdigit() else str(name).strip().title()


def score_str(goals: Any, behinds: Any, total: Any) -> str:
    """AFL score format: goals.behinds (total)."""
    if goals is None or behinds is None or (isinstance(goals, float) and math.isnan(goals)):
        return str(total)
    return f"{int(goals)}.{int(behinds)} ({int(total)})"


# ── Strict JSON schema from pydantic models ─────────────────────────────────

def strict_schema(model: Type[BaseModel]) -> Dict[str, Any]:
    """Pydantic schema -> OpenAI/Anthropic strict schema: refs inlined, every
    property required (optional ones nullable), no extra properties."""
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})

    def walk(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            # Drop schema annotations, but never entries of `properties` (a field may be called "title").
            node = {k: ({pk: walk(pv) for pk, pv in v.items()} if k == "properties" else walk(v))
                    for k, v in node.items() if k not in ("title", "default")}
            if node.get("type") == "object" and "properties" in node:
                node["required"] = list(node["properties"].keys())
                node["additionalProperties"] = False
            return node
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(raw)


_SQLISH = re.compile(r";|--|/\*|\)|\(|\b(drop|delete|insert|update|select|alter|truncate)\b", re.I)


def plain_names(values: List[str]) -> List[str]:
    """Pydantic validator body: names are data, never SQL or instructions."""
    for v in values:
        if _SQLISH.search(v or ""):
            raise ValueError(f"'{v}' is not a player or team name; ask the user who they mean")
    return values


def season_bounds() -> Dict[str, int]:
    from app.agent.v3.coverage import coverage
    c = coverage()
    return {"min": c["first_season"], "max": c["last_season"]}


def check_seasons(season_from: Optional[int], season_to: Optional[int]) -> Optional[str]:
    b = season_bounds()
    lo, hi = season_from or b["min"], season_to or b["max"]
    if hi < b["min"] or lo > b["max"]:
        return f"season outside {b['min']}-{b['max']} (the database covers {b['min']}-{b['max']} only)"
    if lo > hi:
        return f"season range {lo}-{hi} is empty"
    return None


def seq(values: Optional[Sequence[Any]]) -> List[Any]:
    return [v for v in (values or []) if v not in (None, "")]
