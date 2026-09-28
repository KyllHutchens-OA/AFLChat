-- 1C step 02: remove duplicate match rows (D4: 2025 Brisbane v Geelong 2025-03-29 stored
-- as both round '3' (id 1239, correct per Squiggle/AFL Tables) and round '0' (id 6626)).
-- Rule: two rows in the same season with the same two teams within 1 day of each other are
-- the same match. Keep the lowest id, re-point child rows the keeper lacks, archive the rest.
-- Idempotent: a re-run finds no duplicates and changes nothing.
BEGIN;

CREATE TEMP TABLE dup_map ON COMMIT DROP AS
SELECT b.id AS dup_id, a.id AS keep_id
FROM matches a
JOIN matches b
  ON a.id < b.id AND a.season = b.season
 AND least(a.home_team_id, a.away_team_id) = least(b.home_team_id, b.away_team_id)
 AND greatest(a.home_team_id, a.away_team_id) = greatest(b.home_team_id, b.away_team_id)
 AND abs(a.match_date::date - b.match_date::date) <= 1;

SELECT d.*, m.season, m.round, m.match_date,
       (SELECT count(*) FROM player_stats WHERE match_id = d.dup_id) AS dup_player_stats
FROM dup_map d JOIN matches m ON m.id = d.dup_id;

SELECT count(*) AS matches_before FROM matches;

-- archives (same columns as the source tables)
CREATE TABLE IF NOT EXISTS archive_1c_dup_matches (LIKE matches);
CREATE TABLE IF NOT EXISTS archive_1c_dup_player_stats (LIKE player_stats);
CREATE TABLE IF NOT EXISTS archive_1c_dup_team_stats (LIKE team_stats);

INSERT INTO archive_1c_dup_matches SELECT m.* FROM matches m JOIN dup_map d ON d.dup_id = m.id;

-- player_stats: move rows the keeper does not have, archive the duplicates
UPDATE player_stats ps SET match_id = d.keep_id
FROM dup_map d
WHERE ps.match_id = d.dup_id
  AND NOT EXISTS (SELECT 1 FROM player_stats k WHERE k.match_id = d.keep_id AND k.player_id = ps.player_id);
INSERT INTO archive_1c_dup_player_stats SELECT ps.* FROM player_stats ps JOIN dup_map d ON d.dup_id = ps.match_id;

UPDATE team_stats ts SET match_id = d.keep_id
FROM dup_map d
WHERE ts.match_id = d.dup_id
  AND NOT EXISTS (SELECT 1 FROM team_stats k WHERE k.match_id = d.keep_id AND k.team_id = ts.team_id);
INSERT INTO archive_1c_dup_team_stats SELECT ts.* FROM team_stats ts JOIN dup_map d ON d.dup_id = ts.match_id;

-- 1:n children without a per-match uniqueness conflict are simply re-pointed
UPDATE live_games t SET match_id = d.keep_id FROM dup_map d WHERE t.match_id = d.dup_id;
UPDATE betting_odds t SET match_id = d.keep_id FROM dup_map d WHERE t.match_id = d.dup_id;
UPDATE match_previews t SET match_id = d.keep_id FROM dup_map d WHERE t.match_id = d.dup_id;
UPDATE match_weather t SET match_id = d.keep_id FROM dup_map d WHERE t.match_id = d.dup_id;
UPDATE squiggle_predictions t SET match_id = d.keep_id FROM dup_map d WHERE t.match_id = d.dup_id;
UPDATE match_lineups t SET match_id = d.keep_id FROM dup_map d
WHERE t.match_id = d.dup_id
  AND NOT EXISTS (SELECT 1 FROM match_lineups k WHERE k.match_id = d.keep_id AND k.player_id = t.player_id);

-- cascade removes the (archived) duplicate child rows
DELETE FROM matches m USING dup_map d WHERE m.id = d.dup_id;

SELECT count(*) AS matches_after FROM matches;
SELECT count(*) AS archived_matches FROM archive_1c_dup_matches;
SELECT count(*) AS archived_player_stats FROM archive_1c_dup_player_stats;

COMMIT;
