"""1C step 08: reconcile player_stats with AFL Tables match pages (needs steps 05-07).

    python -m app.data.fixes_1c.reconcile_stats [--apply] [--overwrite-seasons 2026]

For rows matched to a page entry (work_1c_row_map):
  team   : team_id := the club the page lists the player under (team-swapped rows,
           e.g. Tom Green 2024 under Hawthorn, Jesse Hogan under Melbourne)
  values : every stat the page records replaces the DB value when they differ: NULLs
           (2024 goals), zeros the page contradicts (2024 rows written on 2026-03-16,
           finals advanced stats 2008-2023), stat lines swapped between same-name
           players in one match (Josh Kennedy SYD v WCE). Columns the page does not
           record are left alone (step 09 handles those).
  --overwrite-seasons: in these seasons rows for players the page does not list are
           also archived and removed (2026 R0-R15 rows came from a live feed)
Page players with no row in a match that has stats get a row (players by AFL Tables key).
Every touched row is first copied to archive_1c_player_stats_pre (once per row).
Dry run unless --apply.
"""
import sys

from app.data.fixes_1c import db
from app.data.fixes_1c.identity import remove_emptied_players
from app.data.ingestion.afltables_pages import STAT_FIELDS
from app.data.ingestion.stats_ingester import _calculate_fantasy_points

def season_counts(conn, label):
    print(f"\n{label}:")
    for r in db.rows(conn, """
        SELECT m.season, count(*) AS rows,
               count(*) FILTER (WHERE ps.goals IS NULL) AS null_goals,
               count(*) FILTER (WHERE ps.clearances IS NULL) AS null_clearances,
               count(*) FILTER (WHERE ps.team_id NOT IN (m.home_team_id, m.away_team_id)) AS team_not_in_match
        FROM player_stats ps JOIN matches m ON m.id = ps.match_id
        WHERE m.season IN (SELECT DISTINCT season FROM work_1c_row_map)
        GROUP BY 1 ORDER BY 1"""):
        print("  ", dict(r))


def main():
    apply = db.apply_flag()
    overwrite = []
    if "--overwrite-seasons" in sys.argv:
        spec = sys.argv[sys.argv.index("--overwrite-seasons") + 1]
        lo, _, hi = spec.partition("-")
        overwrite = list(range(int(lo), int(hi or lo) + 1))
    conn = db.connect()
    season_counts(conn, "before")

    db.exec_(conn, "CREATE TABLE IF NOT EXISTS archive_1c_player_stats_pre (LIKE player_stats)")
    db.exec_(conn, "CREATE UNIQUE INDEX IF NOT EXISTS ux_archive_1c_ps_pre ON archive_1c_player_stats_pre (id)")

    diff_any = " OR ".join(
        f"(r.stats->>'{f}' IS NOT NULL AND ps.{f} IS DISTINCT FROM (r.stats->>'{f}')::numeric)" for f in STAT_FIELDS)
    db.exec_(conn, f"""
        CREATE TEMP TABLE touch AS
        SELECT ps.id,
               ps.team_id IS DISTINCT FROM r.page_team_id AS fix_team,
               ({diff_any}) AS fix_values
        FROM work_1c_row_map r JOIN player_stats ps ON ps.id = r.ps_id""")
    db.exec_(conn, "DELETE FROM touch WHERE NOT (fix_team OR fix_values)")
    for r in db.rows(conn, """SELECT count(*) FILTER (WHERE fix_team) team, count(*) FILTER (WHERE fix_values) stat_values,
                              count(*) total FROM touch"""):
        print("\nrows to change:", dict(r))
    for r in db.rows(conn, "SELECT " + ", ".join(
            f"count(*) FILTER (WHERE r.stats->>'{f}' IS NOT NULL AND ps.{f} IS DISTINCT FROM (r.stats->>'{f}')::numeric) AS {f}"
            for f in STAT_FIELDS) + " FROM work_1c_row_map r JOIN player_stats ps ON ps.id = r.ps_id"):
        print("values to change per column:", {k: v for k, v in r.items() if v})

    db.exec_(conn, """INSERT INTO archive_1c_player_stats_pre
        SELECT ps.* FROM player_stats ps JOIN touch t ON t.id = ps.id
        ON CONFLICT (id) DO NOTHING""")

    db.exec_(conn, """UPDATE player_stats ps SET team_id = r.page_team_id, updated_at = now()
        FROM work_1c_row_map r JOIN touch t ON t.id = r.ps_id
        WHERE ps.id = r.ps_id AND t.fix_team""")
    sets = ", ".join(f"{f} = coalesce((r.stats->>'{f}')::numeric, ps.{f})" for f in STAT_FIELDS)
    db.exec_(conn, f"""UPDATE player_stats ps SET {sets}, updated_at = now()
        FROM work_1c_row_map r JOIN touch t ON t.id = r.ps_id
        WHERE ps.id = r.ps_id AND t.fix_values""")

    # rebuilt seasons: rows for players the page does not list (live-feed leftovers such as
    # 'Unknown' or a second row under another player's name) are archived and removed
    if overwrite:
        db.exec_(conn, "CREATE TABLE IF NOT EXISTS archive_1c_phantom_player_stats (LIKE player_stats)")
        db.exec_(conn, "ALTER TABLE archive_1c_phantom_player_stats ADD COLUMN IF NOT EXISTS reason text")
        db.exec_(conn, """INSERT INTO archive_1c_phantom_player_stats
            SELECT ps.*, 'not_in_team_lists_rebuilt_season' FROM player_stats ps
            JOIN work_1c_db_unmatched u ON u.ps_id = ps.id WHERE u.season = ANY(%s)""", (overwrite,))
        n = db.exec_(conn, """DELETE FROM player_stats ps USING work_1c_db_unmatched u
            WHERE u.ps_id = ps.id AND u.season = ANY(%s)""", (overwrite,))
        print(f"\nunlisted rows removed in rebuilt seasons {overwrite}: {n}")

    # missing rows: page players absent from a match that has stats
    missing = db.rows(conn, """
        SELECT u.* FROM work_1c_page_unmatched u
        WHERE EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = u.match_id)""")
    added = 0
    for u in missing:
        pid = db.one(conn, "SELECT id FROM players WHERE afltables_id = %s", (u["afltables_id"],))
        if pid is None:
            cands = db.rows(conn, "SELECT id, team_id FROM players WHERE lower(name) = lower(%s) AND afltables_id IS NULL",
                            (u["page_name"],))
            same = [c for c in cands if c["team_id"] == u["page_team_id"]]
            pick = same if len(same) == 1 else cands if len(cands) == 1 else []
            if pick:
                pid = pick[0]["id"]
                db.exec_(conn, "UPDATE players SET afltables_id = %s WHERE id = %s", (u["afltables_id"], pid))
            else:
                parts = u["page_name"].split()
                pid = db.one(conn, """INSERT INTO players (name, first_name, last_name, team_id, is_active,
                        afltables_id, created_at, updated_at) VALUES (%s,%s,%s,%s,false,%s,now(),now()) RETURNING id""",
                             (u["page_name"], parts[0], parts[-1] if len(parts) > 1 else "", u["page_team_id"],
                              u["afltables_id"]))
        if db.one(conn, "SELECT id FROM player_stats WHERE match_id = %s AND player_id = %s", (u["match_id"], pid)):
            print(f"  ? {u['page_name']} ({u['afltables_id']}) already has a row in match {u['match_id']} under player {pid}")
            continue
        stats = {f: u["stats"].get(f) for f in STAT_FIELDS}  # explicit NULLs beat the 0 defaults
        cols = ", ".join(stats)
        ph = ", ".join(["%s"] * len(stats))
        db.exec_(conn, f"""INSERT INTO player_stats (match_id, player_id, team_id, {cols}, fantasy_points,
                           created_at, updated_at) VALUES (%s, %s, %s, {ph}, %s, now(), now())""",
                 (u["match_id"], pid, u["page_team_id"], *stats.values(), _calculate_fantasy_points(stats)))
        added += 1
    print(f"\nmissing page players inserted: {added} (of {len(missing)})")
    remove_emptied_players(conn)
    season_counts(conn, "after")
    db.finish(conn, apply)


if __name__ == "__main__":
    main()
