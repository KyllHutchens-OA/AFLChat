# 1C data fixes: production runbook

Run only after owner approval. Every step is idempotent (a re-run reports nothing to
do) and runs in one transaction (step 10 commits per match). Python steps are dry runs
unless `--apply` is passed: run each once without it, compare with the expected counts
below, then run with `--apply`.

Counts are from `afl_dev` (restored from the 2026-09-28 prod dump) on 2026-09-28.

## 0. Prepare

```bash
# fresh backup first; keep it until step 12 passes and the owner signs off
pg_dump -Fc "$PROD_DB" -f afl_prod_pre_1c.dump

cd backend
export DB_STRING="$PROD_DB"
# AFL Tables + Squiggle page cache (~7,300 files). Copy the dev cache so prod uses
# exactly the pages dev used and nothing is re-scraped. Without it every page is
# fetched again at 1.5s per request (~3h).
export AFL_1C_CACHE=/path/to/afl_1c_cache
PSQL="psql $PROD_DB -v ON_ERROR_STOP=1"
```

- Stop the scheduler (`RUN_SCHEDULER=false`) for the duration so the live sync and
  ingester do not write concurrently.
- Deploy the `p1/1c-data` code after step 04 and before re-enabling the scheduler (the
  new jobs, live sync and Squiggle lookups use `round_number` and `afltables_id`).

## Steps

| # | Command | What it changes | Expected (dev) |
|---|---|---|---|
| 01 | `$PSQL -f ../scripts/db/1c_01_round_columns.sql` | adds `matches.round_number`, `is_final`, `round_name`; indexes on `matches(season, round_number)` and `player_stats(player_id)` | schema only |
| 02 | `$PSQL -f ../scripts/db/1c_02_dedupe_matches.sql` | archives + deletes the duplicate 2025 Brisbane v Geelong (id 6626, round '0'; keeps id 1239, round '3') | 1 match + 46 player rows archived |
| 03 | `python -m app.data.fixes_1c.sync_matches --apply` | all seasons: round columns + normalised legacy `round`; venue-local kick-offs; scores and cumulative quarter scores from AFL Tables; NULL attendance filled; missing matches inserted. Pre-image: `archive_1c_matches_pre` | 6,956 rows labelled (328 finals); 641 kick-offs fixed (2026 placeholder Mondays, 2025 midnight dates, UTC 2026 rows); 108 wrong 2026 scores fixed (GF Brisbane 90 -> 96, and 107 others captured before full time); 131 quarter sets; 6,353 attendances; 134 matches inserted (130 missing 1990-96 incl. Fitzroy, 1990 QF replay, 1994 QF, 2010 GF replay, 2017 EF) |
| 04 | `$PSQL -f ../scripts/db/1c_04_player_afltables_id.sql` | adds `players.afltables_id` + partial unique index | schema only |
| 05 | `python -m app.data.fixes_1c.map_rows` | builds derived `work_1c_*` tables (no AFL rows change) | ~298k rows mapped; 1,102 rows not on the team lists, 503 duplicates, 2,319 page players without a row |
| 06 | `$PSQL -f ../scripts/db/1c_06_remove_phantom_rows.sql` | archives (`archive_1c_phantom_player_stats`) + deletes rows for players not in the match's AFL Tables team lists with nothing recorded, and exact duplicates | 1,600 rows: 983 (2024), 113 (2026), 1 (2021) unlisted; 503 duplicates (370 are Gary Ablett Sr rows copied onto a second id) |
| 07 | `python -m app.data.fixes_1c.identity --apply` | splits merged namesakes, merges same-person splits, sets `players.afltables_id`. Logs: `archive_1c_player_splits`, `archive_1c_merged_players` | 37 splits moving 710 rows (Bailey Williams, Gary Ablett, Mark Williams, Callum Brown, ...), 43 players created, 33 merged away (Josh J. Kennedy Carlton + WCE, De Koning, Ah Chee, van Rooyen, De Goey, ...), 3 empty players removed, ~3,700 players keyed; uncertain: only the 'Unknown' placeholder (all its rows re-attributed) |
| 08 | `python -m app.data.fixes_1c.reconcile_stats --overwrite-seasons 2026 --apply` | team_id from the page; every recorded stat set to the AFL Tables value; unlisted 2026 rows archived; missing players inserted. Pre-images: `archive_1c_player_stats_pre` | team_id fixed on 3,959 rows (68-172 per season); ~27k rows with stat values replaced (4,404 NULL 2024 goals, 2,959 zeroed 2024 rows, zero advanced stats in finals 2008-2023, 12 same-name stat swaps); 2,319 rows inserted |
| 09 | `$PSQL -f ../scripts/db/1c_09_unrecorded_stats_null.sql` | 0 -> NULL where AFL Tables does not record the stat | ~98k rows 1990-2002: CP, UP, contested marks, marks inside 50, one percenters, bounces before 1999; clearances, inside 50s, rebound 50s, clangers before 1998; goal assists before 2003 |
| 10 | `python -m app.data.fixes_1c.backfill` | player stats for every completed match that has none (the stats ingester through the page cache) | 227 matches, 9,734 rows (92 in 2026 incl. R13, R16-R24 and all finals; 132 in 1990-96; 2010 GF replay; 2017 EF; one 1999 match); 0 unavailable |
| 11 | `$PSQL -f ../scripts/db/1c_11_sync_live_games_scores.sql` | for every completed match AFL Tables has confirmed (`matches.home_q4_goals IS NOT NULL`), overwrites `live_games`' final score, goals/behinds and cumulative Q1-Q4 scores from `matches` (the corrected source). Pre-image: `archive_1c_live_games_pre` | 187 `live_games` rows fixed (found in the 2026-09-28 rollout rehearsal: step 03's match corrections, incl. the GF, were never propagated to `live_games`, so its own Q4 disagreed with its own final score, e.g. GF away_q4_score 90 against a final of 96); 0 remaining mismatches |
| 12 | `$PSQL -f ../scripts/db/1c_verify.sql` | read-only spot checks | 30/30 PASS |
| 13 | `curl $API/api/health/data` | read-only | `"status": "ok"` |

Afterwards, once verified: `DROP TABLE work_1c_row_map, work_1c_db_unmatched,
work_1c_page_unmatched, work_1c_match_pages;`. Keep every `archive_1c_*` table until
the owner signs off.

## Notes from the dev run

- Dev ran steps 05-09 several times while the matching and "recorded" rules were
  refined; the final passes changed nothing, and step 05 on the final data maps all
  310,423 rows by AFL Tables key with nothing unmatched. One pass on prod in the order
  above reaches the same state; its counts may differ a little from the table because
  the dev figures are summed over passes.
- Final dev state: 7,090 matches (per-season counts equal AFL Tables), 310,423
  player_stats rows (was 299,975), every completed match has stats, every recorded stat
  equals AFL Tables, `1c_verify.sql` 30/30 PASS, `/api/health/data` ok.
- One source disagreement, kept on the AFL Tables side: 2026 R24 Essendon v Port
  Adelaide, AFL Tables 16.9 (105) vs Squiggle 16.8 (104). The nightly Squiggle job and
  the live sync no longer overwrite a result once AFL Tables quarter scores exist. Step
  11 also brings this match's `live_games` row onto the AFL Tables number, consistent
  with that policy.
- Step 11 exists because step 03 corrects `matches` but nothing in 1C wrote those
  corrections back to `live_games`; before step 11 the 2026 Grand Final (and most of
  the rest of the 2026 season) had a `live_games` row whose own Q1-Q4 breakdown
  disagreed with its own final score. Confirm after running it: `SELECT m.home_score,
  m.away_score, lg.home_q4_score, lg.away_q4_score FROM matches m JOIN live_games lg ON
  lg.match_id = m.id WHERE m.season = 2026 AND m.round_name = 'Grand Final';` should
  show 89, 96, 89, 96.
- Known genuine outlier: 1996 R10 St Kilda v Essendon lists 25 + 26 players on AFL
  Tables (allow-listed in `data_health.py`).
- NBA rows in `teams` are removed by the separate D1 work, not by these scripts.

## Rollback

Everything removed or changed is kept, so any step can be undone without the dump.

- **Step 10 and 08 inserts** (new player_stats rows):
  `DELETE FROM player_stats WHERE created_at >= '<run start>' AND id NOT IN (SELECT id FROM archive_1c_player_stats_pre);`
- **Steps 08 and 09 updates**: restore pre-images. Generate the column list with
  `SELECT string_agg(format('%1$I = a.%1$I', column_name), ', ') FROM information_schema.columns WHERE table_name = 'player_stats' AND column_name <> 'id';`
  then `UPDATE player_stats ps SET <list> FROM archive_1c_player_stats_pre a WHERE a.id = ps.id;`
- **Step 07**: `UPDATE player_stats ps SET player_id = s.old_player_id FROM archive_1c_player_splits s WHERE ps.id = s.ps_id;`
  re-insert merged players with `INSERT INTO players SELECT <players columns> FROM archive_1c_merged_players;`
  (rows merged into a keeper can be pointed back with the ps_id/player_id pairs in
  `archive_1c_player_stats_pre`), then `UPDATE players SET afltables_id = NULL;`
- **Steps 06 and 02**: `INSERT INTO player_stats SELECT <player_stats columns> FROM archive_1c_phantom_player_stats;`,
  `INSERT INTO matches SELECT * FROM archive_1c_dup_matches;` then the same for
  `archive_1c_dup_player_stats`.
- **Step 03**: `archive_1c_matches_pre` is the full pre-image of `matches`: restore
  columns with `UPDATE matches m SET ... FROM archive_1c_matches_pre a WHERE a.id = m.id`,
  and remove inserted matches with `DELETE FROM matches WHERE id NOT IN (SELECT id FROM archive_1c_matches_pre);`
  (cascades their player_stats).
- **Steps 01 and 04** only add columns: `ALTER TABLE matches DROP COLUMN round_number, DROP COLUMN is_final, DROP COLUMN round_name;`
  and `ALTER TABLE players DROP COLUMN afltables_id;` (after reverting the code).
- **Step 11**: `UPDATE live_games lg SET home_score = a.home_score, away_score = a.away_score,
  home_goals = a.home_goals, home_behinds = a.home_behinds, away_goals = a.away_goals,
  away_behinds = a.away_behinds, home_q1_score = a.home_q1_score, home_q2_score = a.home_q2_score,
  home_q3_score = a.home_q3_score, home_q4_score = a.home_q4_score, away_q1_score = a.away_q1_score,
  away_q2_score = a.away_q2_score, away_q3_score = a.away_q3_score, away_q4_score = a.away_q4_score,
  winner_team_id = a.winner_team_id FROM archive_1c_live_games_pre a WHERE a.id = lg.id;`
- Last resort: `pg_restore --clean -d "$PROD_DB" afl_prod_pre_1c.dump`.
