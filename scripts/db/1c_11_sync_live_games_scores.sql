-- 1C follow-up: sync live_games quarter/final scores from the AFL-Tables-confirmed
-- `matches` row for every completed game. Found during the Part 1 rollout rehearsal:
-- 1C's match-sync (step 03) corrects `matches`, but never wrote those corrections back
-- to `live_games`, so a live_games row can show the pre-correction Squiggle score even
-- though `matches` (and the chat agent, which reads `matches`) has the right one.
--
-- Concretely: the 2026 Grand Final's `matches` row is 96-89 (Brisbane Lions d Fremantle,
-- D5/B5), but `live_games` still had away_q4_score = 90, not 96 -- Live's own quarter
-- breakdown disagreed with its own final score. The same staleness affects most of the
-- 2026 season's live_games rows once 1C corrected `matches` under them.
--
-- Idempotent: only touches rows that actually differ; a re-run reports 0 rows.
-- Pre-image kept in archive_1c_live_games_pre for rollback.
--
-- Run: psql "$DB_STRING" -v ON_ERROR_STOP=1 -f scripts/db/1c_11_sync_live_games_scores.sql

BEGIN;

CREATE TABLE IF NOT EXISTS archive_1c_live_games_pre AS
    SELECT * FROM live_games WHERE false;
INSERT INTO archive_1c_live_games_pre
    SELECT lg.* FROM live_games lg
    JOIN matches m ON m.id = lg.match_id
    WHERE m.home_q4_goals IS NOT NULL  -- AFL Tables confirmed final quarter
      AND (lg.home_score IS DISTINCT FROM m.home_score
        OR lg.away_score IS DISTINCT FROM m.away_score
        OR lg.home_q1_score IS DISTINCT FROM (m.home_q1_goals * 6 + m.home_q1_behinds)
        OR lg.home_q2_score IS DISTINCT FROM (m.home_q2_goals * 6 + m.home_q2_behinds)
        OR lg.home_q3_score IS DISTINCT FROM (m.home_q3_goals * 6 + m.home_q3_behinds)
        OR lg.home_q4_score IS DISTINCT FROM (m.home_q4_goals * 6 + m.home_q4_behinds)
        OR lg.away_q1_score IS DISTINCT FROM (m.away_q1_goals * 6 + m.away_q1_behinds)
        OR lg.away_q2_score IS DISTINCT FROM (m.away_q2_goals * 6 + m.away_q2_behinds)
        OR lg.away_q3_score IS DISTINCT FROM (m.away_q3_goals * 6 + m.away_q3_behinds)
        OR lg.away_q4_score IS DISTINCT FROM (m.away_q4_goals * 6 + m.away_q4_behinds)
        OR lg.home_goals IS DISTINCT FROM m.home_q4_goals
        OR lg.home_behinds IS DISTINCT FROM m.home_q4_behinds
        OR lg.away_goals IS DISTINCT FROM m.away_q4_goals
        OR lg.away_behinds IS DISTINCT FROM m.away_q4_behinds)
      AND lg.id NOT IN (SELECT id FROM archive_1c_live_games_pre);

SELECT count(*) AS rows_to_fix FROM archive_1c_live_games_pre;

UPDATE live_games lg
SET home_score      = m.home_score,
    away_score      = m.away_score,
    home_goals      = m.home_q4_goals,
    home_behinds    = m.home_q4_behinds,
    away_goals      = m.away_q4_goals,
    away_behinds    = m.away_q4_behinds,
    home_q1_score   = m.home_q1_goals * 6 + m.home_q1_behinds,
    home_q2_score   = m.home_q2_goals * 6 + m.home_q2_behinds,
    home_q3_score   = m.home_q3_goals * 6 + m.home_q3_behinds,
    home_q4_score   = m.home_q4_goals * 6 + m.home_q4_behinds,
    away_q1_score   = m.away_q1_goals * 6 + m.away_q1_behinds,
    away_q2_score   = m.away_q2_goals * 6 + m.away_q2_behinds,
    away_q3_score   = m.away_q3_goals * 6 + m.away_q3_behinds,
    away_q4_score   = m.away_q4_goals * 6 + m.away_q4_behinds,
    winner_team_id  = CASE WHEN m.home_score > m.away_score THEN m.home_team_id
                           WHEN m.away_score > m.home_score THEN m.away_team_id
                           ELSE NULL END,
    last_updated    = now()
FROM matches m
WHERE lg.match_id = m.id
  AND m.home_q4_goals IS NOT NULL
  AND lg.id IN (SELECT id FROM archive_1c_live_games_pre);

-- Verify: the 2026 GF now agrees exactly, Q4 equals the final score on both sides.
SELECT m.home_score, m.away_score, lg.home_score AS lg_home, lg.away_score AS lg_away,
       lg.home_q4_score, lg.away_q4_score
FROM matches m JOIN live_games lg ON lg.match_id = m.id
WHERE m.season = 2026 AND m.round_name = 'Grand Final';

-- Any completed, AFL-Tables-confirmed match still disagreeing (should be 0 rows).
SELECT count(*) AS remaining_mismatches
FROM live_games lg JOIN matches m ON m.id = lg.match_id
WHERE m.home_q4_goals IS NOT NULL
  AND (lg.home_score IS DISTINCT FROM m.home_score
    OR lg.away_score IS DISTINCT FROM m.away_score
    OR lg.home_q4_score IS DISTINCT FROM (m.home_q4_goals * 6 + m.home_q4_behinds)
    OR lg.away_q4_score IS DISTINCT FROM (m.away_q4_goals * 6 + m.away_q4_behinds));

COMMIT;

-- Rollback: UPDATE live_games lg SET <all columns above> FROM archive_1c_live_games_pre a
-- WHERE a.id = lg.id; (restores every touched row byte for byte).
