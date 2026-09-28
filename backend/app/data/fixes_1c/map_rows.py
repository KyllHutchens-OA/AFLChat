"""1C step 05: map every player_stats row to its AFL Tables match-page entry.

    python -m app.data.fixes_1c.map_rows [--seasons 1990-2026]

Builds (per season: delete + rebuild; derived data only, no AFL rows are changed):
  work_1c_row_map         ps_id -> afltables_id, page club, page stats (jsonb), method
  work_1c_db_unmatched    player_stats rows not on the page (phantom candidates), or
                          duplicate_of = the mapped row with the identical stat line
  work_1c_page_unmatched  page players with no player_stats row (missing rows)
  work_1c_match_pages     match_id -> stats_url + recorded columns
Later steps (identity, team fixes, NULL fills, phantom removal) read these tables.

Row matching inside one match: the player's AFL Tables key (once labelled); same name + identical stat line
(kicks/handballs/marks/goals/behinds/tackles/hitouts); identical stat line with the
same surname (or, for rows stored as 'Unknown', a unique non-trivial line); same
name; unique surname. Anything else stays unmatched.
"""
import json
import re
import sys
from collections import Counter

from app.data.fixes_1c import db
from app.data.fixes_1c.reference import build_reference, match_db_rows
from app.data.fixes_1c.sources import TEAM_IDS, aflt_match_page
from app.data.fixes_1c.sync_matches import parse_seasons
from app.data.ingestion.afltables_pages import STAT_FIELDS, canonical_club

PLACEHOLDER_NAMES = {"unknown", ""}
FP = ("kicks", "handballs", "marks", "goals", "behinds", "tackles", "hitouts")

DDL = """
CREATE TABLE IF NOT EXISTS work_1c_row_map (ps_id int PRIMARY KEY, match_id int, season int, player_id int,
  db_team_id int, afltables_id text, page_name text, page_team_id int, method text, stats jsonb);
CREATE TABLE IF NOT EXISTS work_1c_db_unmatched (ps_id int PRIMARY KEY, match_id int, season int, player_id int,
  db_name text, db_team_id int, all_zero boolean, duplicate_of int);
CREATE TABLE IF NOT EXISTS work_1c_page_unmatched (match_id int, season int, afltables_id text, page_name text,
  page_team_id int, stats jsonb);
CREATE TABLE IF NOT EXISTS work_1c_match_pages (match_id int PRIMARY KEY, season int, stats_url text, recorded text[]);
"""


def norm(name: str) -> str:
    name = name or ""
    if "," in name:  # some 2026 rows were stored 'Last, First'
        last, first = name.split(",", 1)
        name = f"{first} {last}"
    return re.sub(r"\s+", " ", re.sub(r"[^a-z ]", "", name.lower().replace("-", " "))).strip()


def surname(name: str) -> str:
    parts = norm(name).split()
    return parts[-1] if parts else ""


def fingerprint(d) -> tuple:
    return tuple((d.get(k) or 0) for k in FP)


def map_match(db_rows, page_players):
    """Returns (pairs [(db_row, page_player, method)], duplicates [(db_row, kept_row)],
    unmatched_db, unmatched_page)."""
    pairs, dups, left_db, left_pg = [], [], list(db_rows), list(page_players)

    def take(r, p, how):
        pairs.append((r, p, how))
        left_db.remove(r)
        left_pg.remove(p)

    # 0. player already labelled with this AFL Tables key (after step 07)
    for r in list(left_db):
        hits = [p for p in left_pg if r.get("key") and p["afltables_id"] == r["key"]]
        if len(hits) == 1:
            take(r, hits[0], "key")
    # 1. same name and identical stat line (if several rows qualify, prefer the row
    #    already on the page's club, then the older player id)
    for p in list(left_pg):
        cands = [r for r in left_db if norm(r["name"]) == norm(p["name"]) and fingerprint(r) == fingerprint(p)]
        same_pg = [x for x in left_pg if norm(x["name"]) == norm(p["name"]) and fingerprint(x) == fingerprint(p)]
        if cands and len(same_pg) == 1:
            best = min(cands, key=lambda r: (r.get("team_id") != p.get("team_id"), r["player_id"]))
            take(best, p, "name")
    # 2. identical stat line; prefer the same surname when several rows share it
    #    (catches truncated DB names: 'Jacob Rooyen' = 'Jacob van Rooyen')
    for p in list(left_pg):
        fp = fingerprint(p)
        cands = [r for r in left_db if fingerprint(r) == fp]
        if not cands:
            continue
        named = [r for r in cands if surname(r["name"]) == surname(p["name"])]
        # a stat line alone only identifies rows stored under a placeholder name
        nameless = [r for r in cands if norm(r["name"]) in PLACEHOLDER_NAMES]
        others_same_fp = [x for x in left_pg if x is not p and fingerprint(x) == fp]
        if len(named) == 1:
            take(named[0], p, "stats+surname")
        elif len(nameless) == 1 and sum(fp) >= 5 and not others_same_fp:
            take(nameless[0], p, "stats")
    # 3. exact (normalised) name, unique on both sides (stats differ: NULL/zeroed rows)
    pg_names = Counter(norm(p["name"]) for p in left_pg)
    db_names = Counter(norm(r["name"]) for r in left_db)
    for r in list(left_db):
        n = norm(r["name"])
        hits = [p for p in left_pg if norm(p["name"]) == n]
        if len(hits) == 1 and pg_names[n] == 1 and db_names[n] == 1:
            take(r, hits[0], "name")
    # 4. unique surname on both sides
    for r in list(left_db):
        sn = surname(r["name"])
        hits = [p for p in left_pg if surname(p["name"]) == sn]
        if len(hits) == 1 and sum(1 for x in left_db if surname(x["name"]) == sn) == 1:
            take(r, hits[0], "surname")
    # leftover rows repeating a mapped row's non-trivial stat line are duplicates
    for r in list(left_db):
        fp = fingerprint(r)
        if sum(fp) == 0:
            continue
        kept = [k for k, _, _ in pairs if fingerprint(k) == fp]
        if len(kept) == 1:
            dups.append((r, kept[0]))
            left_db.remove(r)
    return pairs, dups, left_db, left_pg


def main():
    conn = db.connect()
    seasons = parse_seasons(sys.argv, db.one(conn, "SELECT max(season) FROM matches"))
    with conn.cursor() as cur:
        cur.execute(DDL)
        for t in ("work_1c_row_map", "work_1c_db_unmatched", "work_1c_page_unmatched", "work_1c_match_pages"):
            cur.execute(f"DELETE FROM {t} WHERE season = ANY(%s)", (seasons,))
    totals = Counter()
    for season in seasons:
        ref = build_reference(season)
        matches = db.rows(conn, "SELECT * FROM matches WHERE season = %s", (season,))
        mapping, _, _ = match_db_rows(matches, ref)
        ps = db.rows(conn, """
            SELECT ps.*, p.name, p.afltables_id AS key FROM player_stats ps JOIN players p ON p.id = ps.player_id
            JOIN matches m ON m.id = ps.match_id WHERE m.season = %s""", (season,))
        by_match = {}
        for r in ps:
            by_match.setdefault(r["match_id"], []).append(r)
        season_counts = Counter()
        for match_id, rows in by_match.items():
            g = mapping.get(match_id)
            page = aflt_match_page(g.stats_url) if g and g.stats_url else None
            if not page:
                season_counts["no_page"] += 1
                continue
            players = []
            for club in page["teams"]:
                tid = TEAM_IDS.get(club["club"]) or TEAM_IDS.get(canonical_club(club["club"]))
                for p in club["players"]:
                    players.append({**p, "team_id": tid})
            db.exec_(conn, "INSERT INTO work_1c_match_pages VALUES (%s,%s,%s,%s)",
                     (match_id, season, g.stats_url, page["recorded"]))
            pairs, dups, udb, upg = map_match(rows, players)
            with conn.cursor() as cur:
                cur.executemany(
                    "INSERT INTO work_1c_row_map VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(r["id"], match_id, season, r["player_id"], r["team_id"], p["afltables_id"],
                      p["name"], p["team_id"], how, json.dumps({f: p.get(f) for f in STAT_FIELDS}))
                     for r, p, how in pairs])
                cur.executemany(
                    "INSERT INTO work_1c_db_unmatched VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    [(r["id"], match_id, season, r["player_id"], r["name"], r["team_id"],
                      all(not r.get(f) for f in STAT_FIELDS), None) for r in udb]
                    + [(r["id"], match_id, season, r["player_id"], r["name"], r["team_id"],
                        all(not r.get(f) for f in STAT_FIELDS), k["id"]) for r, k in dups])
                cur.executemany(
                    "INSERT INTO work_1c_page_unmatched VALUES (%s,%s,%s,%s,%s,%s)",
                    [(match_id, season, p["afltables_id"], p["name"], p["team_id"],
                      json.dumps({f: p.get(f) for f in STAT_FIELDS})) for p in upg])
            season_counts["matches"] += 1
            season_counts["mapped"] += len(pairs)
            season_counts["db_unmatched"] += len(udb)
            season_counts["duplicates"] += len(dups)
            season_counts["page_unmatched"] += len(upg)
            for _, _, how in pairs:
                season_counts[f"by_{how}"] += 1
        print(season, dict(season_counts), flush=True)
        totals.update(season_counts)
        conn.commit()  # work tables only
    print("TOTAL", dict(totals))


if __name__ == "__main__":
    main()
