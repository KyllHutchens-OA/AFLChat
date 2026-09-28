-- 1C step 06: remove phantom and duplicate player_stats rows (needs work_1c_* from step 05).
-- Phantom  = the player is NOT in that match's team lists on AFL Tables (work_1c_db_unmatched)
--            AND no kick, handball, mark, tackle, score, hitout, free kick or Brownlow vote
--            is recorded on the row (e.g. 2024 match 886: 58 Melbourne/Adelaide players
--            attached to North v Port by the old "first meeting" fallback; those junk rows
--            carry only TOG/CP/UP copied from the player's real game).
-- Duplicate = an extra row in the same match with exactly the stat line of a row that is
--            matched to the page (2026 'Unknown' copies).
-- Unmatched rows with real stats are kept and only reported.
-- Every deleted row is copied to archive_1c_phantom_player_stats first. Idempotent.
BEGIN;

CREATE TABLE IF NOT EXISTS archive_1c_phantom_player_stats (LIKE player_stats);
ALTER TABLE archive_1c_phantom_player_stats ADD COLUMN IF NOT EXISTS reason text;

CREATE TEMP TABLE phantom ON COMMIT DROP AS
SELECT ps.id, u.season,
       CASE WHEN u.duplicate_of IS NOT NULL THEN 'duplicate' ELSE 'not_in_team_lists' END AS reason
FROM work_1c_db_unmatched u
JOIN player_stats ps ON ps.id = u.ps_id
WHERE u.duplicate_of IS NOT NULL
   OR (coalesce(ps.kicks,0) + coalesce(ps.handballs,0) + coalesce(ps.disposals,0) + coalesce(ps.marks,0)
     + coalesce(ps.tackles,0) + coalesce(ps.goals,0) + coalesce(ps.behinds,0) + coalesce(ps.hitouts,0)
     + coalesce(ps.free_kicks_for,0) + coalesce(ps.free_kicks_against,0)
     + coalesce(ps.brownlow_votes,0)) = 0;

SELECT season, reason, count(*) AS rows_to_remove FROM phantom GROUP BY 1, 2 ORDER BY 1, 2;
SELECT count(*) AS unmatched_rows_with_stats_kept
FROM work_1c_db_unmatched u WHERE NOT EXISTS (SELECT 1 FROM phantom p WHERE p.id = u.ps_id)
  AND EXISTS (SELECT 1 FROM player_stats ps WHERE ps.id = u.ps_id);
SELECT count(*) AS player_stats_before FROM player_stats;

INSERT INTO archive_1c_phantom_player_stats
SELECT ps.*, p.reason FROM player_stats ps JOIN phantom p ON p.id = ps.id;
DELETE FROM player_stats ps USING phantom p WHERE ps.id = p.id;

SELECT count(*) AS player_stats_after FROM player_stats;
SELECT count(*) AS archived_total FROM archive_1c_phantom_player_stats;
COMMIT;
