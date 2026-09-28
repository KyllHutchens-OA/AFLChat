"""1C step 03: sync `matches` with AFL Tables (+ Squiggle round numbers), all seasons.

    python -m app.data.fixes_1c.sync_matches [--apply] [--seasons 1990-2026]

Per matched row sets round_number / round_name / is_final, normalises the legacy
`round`, sets match_date to the venue-local kick-off, fixes final and quarter
scores that disagree with AFL Tables (e.g. 2026 GF Brisbane 90 -> 96, 107 other
2026 scores captured before full time), fills NULL quarter scores / attendance,
and inserts matches missing from the DB (Fitzroy 1990-96 etc.).
Never deletes. First run snapshots `matches` into archive_1c_matches_pre.
Dry run unless --apply.
"""
import sys
from collections import Counter

from app.analytics.entity_resolver import VenueResolver
from app.data.fixes_1c import db
from app.data.fixes_1c.reference import (
    build_reference, legacy_round, match_db_rows, quarter_columns, scores_for,
)

Q_COLS = [f"{s}_q{i}_{k}" for s in ("home", "away") for i in range(1, 5) for k in ("goals", "behinds")]


def parse_seasons(argv, default_hi):
    if "--seasons" in argv:
        spec = argv[argv.index("--seasons") + 1]
        lo, _, hi = spec.partition("-")
        return list(range(int(lo), int(hi or lo) + 1))
    return list(range(1990, default_hi + 1))


def target_values(row, g):
    """Column values the row should have according to the reference game."""
    hs, as_ = scores_for(g, row["home_team_id"])
    vals = {
        "round_number": g.round_number,
        "round_name": g.round_name,
        "is_final": g.is_final,
        "round": legacy_round(g.round_number, g.round_name, g.is_final),
        "match_date": g.local_dt,
        "home_score": hs,
        "away_score": as_,
        "match_status": "completed",
    }
    vals.update(quarter_columns(g, row["home_team_id"]))
    if row.get("attendance") is None and g.attendance:
        vals["attendance"] = g.attendance
    return vals


def main():
    apply = db.apply_flag()
    conn = db.connect()
    seasons = parse_seasons(sys.argv, db.one(conn, "SELECT max(season) FROM matches"))

    db.exec_(conn, "CREATE TABLE IF NOT EXISTS archive_1c_matches_pre AS SELECT * FROM matches")
    print("archive_1c_matches_pre rows:", db.one(conn, "SELECT count(*) FROM archive_1c_matches_pre"))

    before = {r["season"]: r["n"] for r in db.rows(conn, "SELECT season, count(*) n FROM matches GROUP BY 1")}
    changed = Counter()
    inserted, unmatched_db = [], []

    for season in seasons:
        ref = build_reference(season)
        rows = db.rows(conn, "SELECT * FROM matches WHERE season = %s ORDER BY id", (season,))
        mapping, udb, uref = match_db_rows(rows, ref)
        unmatched_db += udb
        by_id = {r["id"]: r for r in rows}

        # Two passes so label swaps never collide on UNIQUE(season, round, home, away):
        # park every changing legacy label on a temporary value first.
        updates = []
        for mid, g in mapping.items():
            row = by_id[mid]
            diff = {k: v for k, v in target_values(row, g).items() if row.get(k) != v}
            if diff:
                updates.append((mid, diff))
                cats = {"score" if k in ("home_score", "away_score") else "quarters" if k in Q_COLS else k
                        for k in diff}
                changed.update(cats)
                if "score" in cats:
                    print(f"   score fix {season} id={mid} {row['round']}: "
                          f"{row['home_score']}-{row['away_score']} -> {diff.get('home_score', row['home_score'])}-"
                          f"{diff.get('away_score', row['away_score'])}")
        for mid, diff in updates:
            if "round" in diff:
                db.exec_(conn, "UPDATE matches SET round = %s WHERE id = %s", (f"__1c_{mid}", mid))
        for mid, diff in updates:
            cols = ", ".join(f"{k} = %s" for k in diff)
            db.exec_(conn, f"UPDATE matches SET {cols}, updated_at = now() WHERE id = %s", (*diff.values(), mid))

        for g in uref:
            vals = {
                "season": season, "home_team_id": g.home_id, "away_team_id": g.away_id,
                "venue": VenueResolver.normalize_venue(g.venue), "attendance": g.attendance,
            }
            vals.update(target_values({"home_team_id": g.home_id, "attendance": None}, g))
            cols = ", ".join(vals)
            ph = ", ".join(["%s"] * len(vals))
            new_id = db.one(conn, f"INSERT INTO matches ({cols}, created_at, updated_at) VALUES ({ph}, now(), now()) RETURNING id", tuple(vals.values()))
            inserted.append((new_id, season, g.round_name, g.home, g.away, g.home_score, g.away_score))

    after = {r["season"]: r["n"] for r in db.rows(conn, "SELECT season, count(*) n FROM matches GROUP BY 1")}
    print("\nfield changes on existing rows:", dict(changed))
    print(f"inserted matches: {len(inserted)}")
    for i in inserted:
        print("   +", i)
    print(f"unmatched DB rows (left untouched): {len(unmatched_db)}")
    for r in unmatched_db:
        print("   ?", r["id"], r["season"], r["round"], r["match_date"], r["home_team_id"], r["away_team_id"])
    print("\nseason: before -> after")
    for s in seasons:
        if before.get(s) != after.get(s):
            print(f"   {s}: {before.get(s)} -> {after.get(s)}")
    print("round_number NULL after:", db.one(conn, "SELECT count(*) FROM matches WHERE round_number IS NULL"))
    print("finals after:", db.one(conn, "SELECT count(*) FROM matches WHERE is_final"))
    db.finish(conn, apply)


if __name__ == "__main__":
    main()
