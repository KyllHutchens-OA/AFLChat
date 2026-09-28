"""1C step 07: player identity from AFL Tables keys (needs work_1c_row_map, step 05/06).

    python -m app.data.fixes_1c.identity [--apply]

Evidence = player_stats rows matched to a page entry by exact name or by identical
stat line + surname ("strong"). Rows matched only by surname or stat line are not
used to split or merge; conflicts that rest on them are listed as uncertain.

  split : one players.id whose strong rows belong to 2+ AFL Tables people (merged
          namesakes, e.g. Bailey Williams WCE/WB). The key whose page name equals the
          DB name keeps the id; every other key's rows move to that person's player
          (existing one, or a new player row). Logged in archive_1c_player_splits.
  merge : one AFL Tables person spread over 2+ players.id (e.g. 'Watkins, Jack' and
          'Jack Watkins'). All rows and references move to the id with most rows; the
          emptied players are copied to archive_1c_merged_players, then deleted.
  label : players.afltables_id is set for every player with consistent evidence.
Dry run unless --apply.
"""
from collections import Counter, defaultdict

from app.data.fixes_1c import db
from app.data.fixes_1c.map_rows import PLACEHOLDER_NAMES, norm

STRONG = ("name", "stats+surname")


def player_fk_refs(conn):
    """(table, column) pairs referencing players.id, other than player_stats."""
    return [(r["tbl"], r["col"]) for r in db.rows(conn, """
        SELECT c.conrelid::regclass::text AS tbl, a.attname AS col
        FROM pg_constraint c JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
        WHERE c.contype = 'f' AND c.confrelid = 'players'::regclass""") if r["tbl"] != "player_stats"]


def main():
    apply = db.apply_flag()
    conn = db.connect()
    db.exec_(conn, """CREATE TABLE IF NOT EXISTS archive_1c_player_splits (
        ps_id int, match_id int, old_player_id int, new_player_id int, afltables_id text,
        created_at timestamp DEFAULT now())""")
    db.exec_(conn, "CREATE TABLE IF NOT EXISTS archive_1c_merged_players (LIKE players)")
    db.exec_(conn, "ALTER TABLE archive_1c_merged_players ADD COLUMN IF NOT EXISTS merged_into int")
    before = db.one(conn, "SELECT count(*) FROM players")

    rows = db.rows(conn, """
        SELECT r.ps_id, r.match_id, r.player_id, r.afltables_id, r.page_name, r.method,
               r.page_team_id, m.match_date, p.name AS db_name, p.afltables_id AS current_key
        FROM work_1c_row_map r
        JOIN player_stats ps ON ps.id = r.ps_id AND ps.player_id = r.player_id
        JOIN players p ON p.id = r.player_id
        JOIN matches m ON m.id = r.match_id""")
    by_player = defaultdict(list)
    for r in rows:
        by_player[r["player_id"]].append(r)

    uncertain, splits, created, split_sources = [], 0, 0, []
    key_owner = {k["afltables_id"]: k["id"] for k in db.rows(
        conn, "SELECT id, afltables_id FROM players WHERE afltables_id IS NOT NULL")}

    # --- splits -------------------------------------------------------------
    for pid, prs in sorted(by_player.items()):
        # stat-line-only matches are evidence only for 'Unknown' placeholder players
        ok = STRONG + (("stats",) if norm(prs[0]["db_name"]) in PLACEHOLDER_NAMES else ())
        strong = Counter(r["afltables_id"] for r in prs if r["method"] in ok)
        weak = {r["afltables_id"] for r in prs if r["method"] not in ok}
        if len(strong) <= 1:
            if weak - set(strong):
                uncertain.append(f"player {pid} {prs[0]['db_name']!r}: weak-only match(es) to {sorted(weak - set(strong))}")
            continue
        db_name = norm(prs[0]["db_name"])
        keep = [k for k in strong if norm(next(r["page_name"] for r in prs if r["afltables_id"] == k)) == db_name]
        # same-name namesakes: the person with most rows keeps the id
        keep_key = max(keep, key=lambda k: (strong[k], k)) if keep else None
        split_sources.append(pid)
        for key in strong:
            if key == keep_key:
                continue
            key_rows = [r for r in prs if r["afltables_id"] == key]
            target = key_owner.get(key)
            if target is None:
                latest = max(key_rows, key=lambda r: r["match_date"])
                name = latest["page_name"]
                parts = name.split()
                target = db.one(conn, """
                    INSERT INTO players (name, first_name, last_name, team_id, is_active, afltables_id,
                                         created_at, updated_at)
                    VALUES (%s, %s, %s, %s, false, %s, now(), now()) RETURNING id""",
                    (name, parts[0], parts[-1] if len(parts) > 1 else "", latest["page_team_id"], key))
                key_owner[key] = target
                created += 1
            for r in key_rows:
                clash = db.one(conn, "SELECT id FROM player_stats WHERE match_id = %s AND player_id = %s",
                               (r["match_id"], target))
                if clash:
                    uncertain.append(f"split clash ps {r['ps_id']} -> player {target} already in match {r['match_id']}")
                    continue
                db.exec_(conn, "UPDATE player_stats SET player_id = %s WHERE id = %s", (target, r["ps_id"]))
                db.exec_(conn, "INSERT INTO archive_1c_player_splits (ps_id, match_id, old_player_id, new_player_id, afltables_id) VALUES (%s,%s,%s,%s,%s)",
                         (r["ps_id"], r["match_id"], pid, target, key))
                splits += 1
        if keep_key is None:
            uncertain.append(f"player {pid} {prs[0]['db_name']!r}: no key matches its name; all rows moved off {dict(strong)}")
        print(f"split player {pid} {prs[0]['db_name']!r}: keys {dict(strong)} keep={keep_key}")

    # --- merges ---------------------------------------------------------------
    rows = db.rows(conn, """
        SELECT r.afltables_id, ps.player_id, count(*) AS n
        FROM work_1c_row_map r JOIN player_stats ps ON ps.id = r.ps_id
        WHERE r.method = ANY(%s) GROUP BY 1, 2""", (list(STRONG) + ["stats"],))
    by_key = defaultdict(list)
    for r in rows:
        by_key[r["afltables_id"]].append(r)
    refs = player_fk_refs(conn)
    merged = 0
    for key, owners in sorted(by_key.items()):
        if len(owners) < 2:
            continue
        owners.sort(key=lambda r: (-r["n"], r["player_id"]))
        keep = owners[0]["player_id"]  # the id with most rows survives
        key_owner[key] = keep
        for o in owners:
            old = o["player_id"]
            if old == keep:
                continue
            clash = db.one(conn, """SELECT count(*) FROM player_stats a JOIN player_stats b
                ON a.match_id = b.match_id WHERE a.player_id = %s AND b.player_id = %s""", (old, keep))
            if clash:
                uncertain.append(f"merge {key}: players {old} and {keep} both have rows in {clash} match(es); not merged")
                continue
            db.exec_(conn, "UPDATE player_stats SET player_id = %s WHERE player_id = %s", (keep, old))
            ok = True
            for tbl, col in refs:
                db.exec_(conn, "SAVEPOINT ref")
                try:
                    db.exec_(conn, f"UPDATE {tbl} SET {col} = %s WHERE {col} = %s", (keep, old))
                    db.exec_(conn, "RELEASE SAVEPOINT ref")
                except Exception as e:
                    db.exec_(conn, "ROLLBACK TO SAVEPOINT ref")
                    uncertain.append(f"merge {key}: could not re-point {tbl}.{col} for player {old}: {e}")
                    ok = False
            if ok:
                db.exec_(conn, "INSERT INTO archive_1c_merged_players SELECT p.*, %s FROM players p WHERE id = %s", (keep, old))
                db.exec_(conn, "DELETE FROM players WHERE id = %s", (old,))
            merged += 1
            print(f"merge {key}: player {old} -> {keep}")

    # --- split sources left with no rows (e.g. 'Unknown') ------------------------
    for pid in split_sources:
        left = db.one(conn, "SELECT count(*) FROM player_stats WHERE player_id = %s", (pid,))
        other = sum(db.one(conn, f"SELECT count(*) FROM {t} WHERE {c} = %s", (pid,)) for t, c in refs)
        if left == 0 and other == 0:
            db.exec_(conn, "INSERT INTO archive_1c_merged_players SELECT p.*, NULL FROM players p WHERE id = %s", (pid,))
            db.exec_(conn, "DELETE FROM players WHERE id = %s", (pid,))
            print(f"removed empty player {pid}")

    # --- labels ---------------------------------------------------------------
    rows = db.rows(conn, """
        SELECT ps.player_id, array_agg(DISTINCT r.afltables_id) AS keys
        FROM work_1c_row_map r JOIN player_stats ps ON ps.id = r.ps_id
        WHERE r.method = ANY(%s) GROUP BY 1""", (list(STRONG),))
    labelled = 0
    for r in rows:
        if len(r["keys"]) != 1:
            uncertain.append(f"player {r['player_id']}: still has keys {r['keys']}")
            continue
        owner = db.one(conn, "SELECT id FROM players WHERE afltables_id = %s", (r["keys"][0],))
        if owner and owner != r["player_id"]:
            uncertain.append(f"key {r['keys'][0]} owned by {owner}, also on {r['player_id']}")
            continue
        labelled += db.exec_(conn, "UPDATE players SET afltables_id = %s WHERE id = %s AND afltables_id IS DISTINCT FROM %s",
                             (r["keys"][0], r["player_id"], r["keys"][0]))

    print(f"\nplayers before {before} after {db.one(conn, 'SELECT count(*) FROM players')}")
    print(f"rows moved by splits: {splits}, players created: {created}, players merged away: {merged}, "
          f"players newly labelled: {labelled}")
    print(f"players with afltables_id: {db.one(conn, 'SELECT count(afltables_id) FROM players')}")
    print(f"uncertain ({len(uncertain)}):")
    for u in uncertain:
        print("  ?", u)
    db.finish(conn, apply)


if __name__ == "__main__":
    main()
