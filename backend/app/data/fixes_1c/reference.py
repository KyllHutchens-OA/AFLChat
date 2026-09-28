"""Build the per-season reference fixture and match it to `matches` rows.

Round contract (matches.round_number / round_name / is_final):
  - Opening Round = 0, home-and-away rounds 1..N (Squiggle numbering; AFL
    Tables folds the Opening Round into its Round 1 so we do not use its numbers)
  - finals continue numerically: N+1 for finals week 1, N+2 week 2, ...
    (weeks grouped by date; a GF replay is its own week)
  - round_name: 'Opening Round', 'Round 5', 'Wildcard Round', 'Qualifying Final',
    'Elimination Final', 'Semi Final', 'Preliminary Final', 'Grand Final'
    (replays of a drawn final get ' Replay', e.g. 1990 QF, 2010 GF)
  - legacy matches.round: str(round_number) for H&A, round_name for finals
"""
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from app.data.fixes_1c.sources import RefGame, aflt_season, squiggle_games, TEAM_IDS
from app.data.rounds import legacy_round, ha_round_name  # noqa: F401 (re-exported)

FINAL_NAMES = {"Wildcard Final": "Wildcard Round"}


def build_reference(year: int) -> List[RefGame]:
    games = sorted(aflt_season(year), key=lambda g: g.local_dt)
    sq = squiggle_games(year)
    sq_by_pair = defaultdict(list)
    for s in sq:
        pair = frozenset((TEAM_IDS[s["hteam"]], TEAM_IDS[s["ateam"]]))
        sq_by_pair[pair].append(s)

    used = set()
    for g in games:
        best = None
        for s in sq_by_pair[g.pair]:
            if s["id"] in used:
                continue
            sdate = (s.get("localtime") or s["date"])[:10]
            gap = abs((g.local_dt.date() - _d(sdate)).days)
            if gap <= 1 and (best is None or gap < best[0]):
                best = (gap, s)
        if best is None:
            raise ValueError(f"{year}: no Squiggle game for {g.home} v {g.away} {g.local_dt}")
        used.add(best[1]["id"])
        g.squiggle_id = best[1]["id"]
        g.extra["squiggle"] = best[1]

    ha = [g for g in games if not g.is_final]
    last_ha = max(g.extra["squiggle"]["round"] for g in ha)
    for g in ha:
        g.round_number = g.extra["squiggle"]["round"]
        g.round_name = ha_round_name(g.round_number)

    # finals: group into weeks by date, number after the last H&A round
    finals = [g for g in games if g.is_final]
    week, week_start, seen = 0, None, set()
    for g in finals:
        if week_start is None or (g.local_dt.date() - week_start).days >= 5:
            week += 1
            week_start = g.local_dt.date()
        g.round_number = last_ha + week
        name = FINAL_NAMES.get(g.label, g.label)
        key = (name, g.pair)
        g.round_name = f"{name} Replay" if key in seen else name
        seen.add(key)
    return games


def _d(s: str):
    from datetime import date
    return date.fromisoformat(s)


def match_db_rows(db_rows: List[Dict], ref: List[RefGame]) -> Tuple[Dict[int, RefGame], List[Dict], List[RefGame]]:
    """Pair DB matches (dicts with id, round, match_date, home_team_id, away_team_id)
    with reference games of the same season.

    Pass 1: same team pair and kick-off date within 1 day.
    Pass 2 (placeholder dates): same team pair and same round label
    (DB '18' == Squiggle round 18, or DB finals name == reference name).
    Never falls back to "first meeting this season".
    Returns (db_id -> ref, unmatched db rows, unmatched ref games).
    """
    by_pair = defaultdict(list)
    for g in ref:
        by_pair[g.pair].append(g)
    taken, out = set(), {}

    def labels(g: RefGame):
        sq_round = str(g.extra["squiggle"]["round"]) if "squiggle" in g.extra else None
        return {str(g.round_number), g.round_name, g.label, FINAL_NAMES.get(g.label, g.label), sq_round}

    for pass_no in (1, 2):
        for row in db_rows:
            if row["id"] in out:
                continue
            pair = frozenset((row["home_team_id"], row["away_team_id"]))
            cands = [g for g in by_pair.get(pair, []) if id(g) not in taken]
            hit = None
            if pass_no == 1:
                close = sorted(
                    (abs((g.local_dt.date() - row["match_date"].date()).days), i, g)
                    for i, g in enumerate(cands)
                )
                close = [c for c in close if c[0] <= 1]
                if close:
                    hit = close[0][2]
            else:
                same = [g for g in cands if str(row["round"]) in labels(g)]
                if len(same) == 1:
                    hit = same[0]
            if hit is not None:
                taken.add(id(hit))
                out[row["id"]] = hit
    unmatched_db = [r for r in db_rows if r["id"] not in out]
    unmatched_ref = [g for g in ref if id(g) not in taken]
    return out, unmatched_db, unmatched_ref


def quarter_columns(g: RefGame, db_home_id: int) -> Dict[str, Optional[int]]:
    """Cumulative quarter goals/behinds oriented to the DB row's home team."""
    hq, aq = (g.home_q, g.away_q) if g.home_id == db_home_id else (g.away_q, g.home_q)
    cols = {}
    for side, q in (("home", hq), ("away", aq)):
        for i in range(4):
            gl, bh = q[i] if i < len(q) else (None, None)
            # extra-time games list 5+ periods; the final period is the result
            if i == 3 and len(q) > 4:
                gl, bh = q[-1]
            cols[f"{side}_q{i+1}_goals"] = gl
            cols[f"{side}_q{i+1}_behinds"] = bh
    return cols


def scores_for(g: RefGame, db_home_id: int) -> Tuple[int, int]:
    return (g.home_score, g.away_score) if g.home_id == db_home_id else (g.away_score, g.home_score)
