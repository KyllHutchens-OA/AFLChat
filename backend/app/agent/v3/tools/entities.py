"""
resolve_entities: map user text (nicknames, typos, surnames) to canonical
players and teams, using an in-memory name cache (loaded once, refreshed
daily) so resolution costs no DB round trips. Namesakes come back as
multiple candidates with era and clubs so the model can disambiguate or ask.
"""
import difflib
import logging
import re
import threading
import time
import unicodedata
from typing import Any, Dict, List, Literal, Optional

import pandas as pd
from pydantic import BaseModel, Field, field_validator

from app.agent.v3.tools.base import AFL_TEAM_IDS, ResultStore, plain_names, query, result
from app.analytics.entity_resolver import EntityResolver

logger = logging.getLogger(__name__)

# Nickname -> canonical DB name. Entries not found in `players` are dropped at load.
PLAYER_ALIASES = {
    "dusty": "Dustin Martin", "buddy": "Lance Franklin", "bud": "Lance Franklin",
    "bont": "Marcus Bontempelli", "the bont": "Marcus Bontempelli",
    "danger": "Patrick Dangerfield", "tomahawk": "Tom Hawkins", "pendles": "Scott Pendlebury",
    "gaz": "Gary Ablett", "roughy": "Jarryd Roughead", "cotch": "Trent Cotchin",
    "fyfey": "Nat Fyfe", "gawny": "Max Gawn", "trac": "Christian Petracca",
    "clarry": "Clayton Oliver", "crippa": "Patrick Cripps", "swanny": "Dane Swan",
    "jezza": "Jeremy Cameron", "tex": "Taylor Walker", "plugger": "Tony Lockett",
    "fev": "Brendan Fevola", "juddy": "Chris Judd", "jobe": "Jobe Watson", "sids": "Steele Sidebottom",
    "mummy": "Shane Mumford", "jjk": "Josh J. Kennedy", "hodge": "Luke Hodge", "mitch": "Mitch Robinson",
    "joey": "Jonathan Brown", "bomber": "Jonathan Brown",
}

_REFRESH_S = 86400
_cache: Dict[str, Any] = {"at": 0.0, "players": None, "aliases": {}}
_lock = threading.Lock()


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s.lower().replace("-", " ").replace("'", "")).strip()


def load_name_cache(force: bool = False) -> pd.DataFrame:
    """Players with career span, games and clubs. One query, cached for a day."""
    with _lock:
        if _cache["players"] is not None and not force and time.time() - _cache["at"] < _REFRESH_S:
            return _cache["players"]
        t0 = time.monotonic()
        df = query(
            "SELECT p.id, p.name, MIN(m.season) AS first_season, MAX(m.season) AS last_season, "
            "COUNT(DISTINCT ps.match_id) AS games, "
            "(ARRAY_AGG(t.name ORDER BY m.match_date DESC))[1] AS last_team, "
            "ARRAY_AGG(DISTINCT t.name) AS clubs "
            "FROM players p JOIN player_stats ps ON ps.player_id = p.id "
            "JOIN matches m ON m.id = ps.match_id "
            "LEFT JOIN teams t ON t.id = ps.team_id AND t.id = ANY(:ids) "
            "GROUP BY p.id, p.name", {"ids": list(AFL_TEAM_IDS)})
        df["norm"] = df["name"].map(_norm)
        df["surname"] = df["norm"].str.split().str[-1]
        df["clubs"] = df["clubs"].map(lambda c: [x for x in (c or []) if x])
        names = set(df["name"])
        _cache.update(at=time.time(), players=df,
                      aliases={k: v for k, v in PLAYER_ALIASES.items() if v in names})
        logger.info(f"v3 name cache: {len(df)} players in {time.monotonic() - t0:.2f}s")
        return df


def warm_async() -> None:
    threading.Thread(target=lambda: _safe_load(), daemon=True).start()


def _safe_load():
    try:
        load_name_cache()
        from app.agent.v3.coverage import coverage
        coverage()
    except Exception as e:
        logger.warning(f"v3 cache warm failed: {e}")


def _active_in(df: pd.DataFrame, season: Optional[int]) -> pd.DataFrame:
    if season is None or df.empty:
        return df
    return df[(df["first_season"] <= season) & (df["last_season"] >= season)]


def find_players(text: str, season: Optional[int] = None) -> tuple[pd.DataFrame, str]:
    """Return (candidates, match_type). Candidates sorted by games desc."""
    players = load_name_cache()
    q = _norm(text)
    if not q:
        return players.head(0), "none"
    alias = _cache["aliases"].get(q)
    parts = q.split()
    if not alias and len(parts) >= 2:
        # "Buddy Franklin", "Dusty Martin": nickname + real surname.
        target = _cache["aliases"].get(parts[0])
        if target and _norm(target).split()[-1] == parts[-1]:
            alias = target
    if alias:
        return players[players["name"] == alias], "alias"
    for label, hits in (
        ("exact", players[players["norm"] == q]),
        ("surname", players[players["surname"] == q] if " " not in q else players.head(0)),
        ("prefix", players[players["norm"].str.startswith(q + " ")] if " " not in q else players.head(0)),
    ):
        if len(hits):
            active = _active_in(hits, season)
            return (active if len(active) else hits).sort_values("games", ascending=False), label
    # Partial first name ("Nick Daicos" vs "Nicholas Daicos"), then fuzzy.
    if len(parts) >= 2:
        hits = players[(players["surname"] == parts[-1]) & players["norm"].str.startswith(parts[0][:3])]
        if len(hits):
            return hits.sort_values("games", ascending=False), "partial"
    close = difflib.get_close_matches(q, players["norm"].tolist(), n=5, cutoff=0.82)
    if not close and " " not in q:
        close_s = difflib.get_close_matches(q, players["surname"].unique().tolist(), n=3, cutoff=0.85)
        hits = players[players["surname"].isin(close_s)]
    else:
        hits = players[players["norm"].isin(close)]
    active = _active_in(hits, season)
    return (active if len(active) else hits).sort_values("games", ascending=False), "fuzzy" if len(hits) else "none"


def resolve_player_ids(names: List[str], season: Optional[int] = None) -> tuple[List[int], List[str], List[str]]:
    """For stat tools: names -> ids. Returns (ids, labels, problems). Ambiguous
    namesakes are reported, not guessed, unless one dominates by era."""
    ids, labels, problems = [], [], []
    for name in names:
        if str(name).isdigit():
            ids.append(int(name))
            labels.append(str(name))
            continue
        hits, how = find_players(name, season)
        if hits.empty:
            problems.append(f"no player matching '{name}' in the database (1990 onwards)")
        elif len(hits) > 1 and how in ("exact", "surname", "fuzzy", "partial") and not _dominant(hits):
            cands = "; ".join(_describe(r) for r in hits.head(5).to_dict("records"))
            problems.append(f"'{name}' is ambiguous: {cands}. Pass player ids or ask the user.")
        else:
            row = hits.iloc[0]
            ids.append(int(row["id"]))
            labels.append(row["name"])
    return ids, labels, problems


def _dominant(hits: pd.DataFrame) -> bool:
    # Surname hits like "Cripps": take the clear leader only when others barely played.
    g = hits["games"].tolist()
    return len(g) > 1 and g[0] >= 50 and g[1] <= 0.15 * g[0]


def _describe(r: Dict[str, Any]) -> str:
    clubs = ", ".join(r["clubs"]) or "unknown club"
    return f"{r['name']} (id {r['id']}, {clubs}, {r['first_season']}-{r['last_season']}, {r['games']} games)"


def resolve_team_id(text: str) -> Optional[tuple[int, str]]:
    name = EntityResolver.resolve_team(text or "")
    if not name:
        return None
    df = query("SELECT id, name FROM teams WHERE name = :n AND id = ANY(:ids)", {"n": name, "ids": list(AFL_TEAM_IDS)})
    return (int(df["id"].iloc[0]), df["name"].iloc[0]) if len(df) else None


class ResolveEntitiesArgs(BaseModel):
    names: List[str] = Field(description="Player or team names as the user wrote them (nicknames, surnames, typos ok)")
    kind: Literal["auto", "player", "team"] = Field(description="What the names refer to; 'auto' tries team then player")
    season: Optional[int] = Field(description="Season in question, used to disambiguate namesakes; null if none")

    @field_validator("names")
    @classmethod
    def _plain_names(cls, v: List[str]) -> List[str]:
        return plain_names(v)


def resolve_entities(args: ResolveEntitiesArgs, store: Optional[ResultStore] = None) -> Dict[str, Any]:
    rows: List[Dict[str, Any]] = []
    notes: List[str] = []
    for name in args.names:
        team = resolve_team_id(name) if args.kind in ("auto", "team") else None
        exact_nick = name.strip().lower() in (EntityResolver._NICKNAME_LOOKUP or {})
        hits, how = (find_players(name, args.season) if args.kind == "player" or (args.kind == "auto" and not exact_nick)
                     else (pd.DataFrame(), "none"))
        if team and (args.kind == "team" or exact_nick or hits.empty):
            rows.append({"query": name, "kind": "team", "id": team[0], "name": team[1], "match": "team"})
            if team[1] == "Brisbane Lions":
                notes.append("Brisbane Bears (1990-96) and Brisbane Lions share one team record.")
            continue
        if args.kind == "team":
            notes.append(f"No AFL team matches '{name}'.")
            continue
        for r in hits.head(6).to_dict("records"):
            rows.append({"query": name, "kind": "player", "id": int(r["id"]), "name": r["name"], "match": how,
                         "clubs": r["clubs"], "seasons": f"{r['first_season']}-{r['last_season']}", "games": int(r["games"])})
        if len(hits) > 1 and not _dominant(hits):
            notes.append(f"'{name}' matches {len(hits)} players; choose by era/club or ask the user which one.")
        if hits.empty:
            notes.append(f"No player or team matches '{name}'.")
    df = pd.DataFrame(rows)
    matched = df[df["id"].notna()] if len(df) else df
    return result(store, matched, why_empty=None if len(matched) else
                  f"no player or team found for {', '.join(args.names)} (data covers 1990 onwards)", notes=notes)
