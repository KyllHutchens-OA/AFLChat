-- 1C step 09: "not recorded" is NULL, not 0 (needs work_1c_row_map from step 05).
-- Rule: for a player_stats row matched to its AFL Tables match page, an advanced stat
-- that the page does not record for that match (column absent, or blank for every
-- player of both clubs) and that the DB holds as 0 becomes NULL.
-- In practice (dev, 2026-09-28): contested/uncontested possessions, contested marks,
-- marks inside 50, one percenters, bounces before 1999; clearances, inside 50s,
-- rebound 50s, clangers before 1998; goal assists before 2003; time on ground before
-- 2003. Basic stats (kicks..free kicks) and Brownlow votes are never touched.
-- Changed rows are copied to archive_1c_player_stats_pre first (once per row). Idempotent.
BEGIN;

CREATE TABLE IF NOT EXISTS archive_1c_player_stats_pre (LIKE player_stats);
CREATE UNIQUE INDEX IF NOT EXISTS ux_archive_1c_ps_pre ON archive_1c_player_stats_pre (id);

CREATE TEMP TABLE unrec ON COMMIT DROP AS
SELECT ps.id, r.season,
  (ps.contested_possessions = 0 AND r.stats->>'contested_possessions' IS NULL) AS cp,
  (ps.uncontested_possessions = 0 AND r.stats->>'uncontested_possessions' IS NULL) AS up,
  (ps.contested_marks = 0 AND r.stats->>'contested_marks' IS NULL) AS cm,
  (ps.marks_inside_50 = 0 AND r.stats->>'marks_inside_50' IS NULL) AS mi,
  (ps.one_percenters = 0 AND r.stats->>'one_percenters' IS NULL) AS op,
  (ps.bounces = 0 AND r.stats->>'bounces' IS NULL) AS bo,
  (ps.goal_assist = 0 AND r.stats->>'goal_assist' IS NULL) AS ga,
  (ps.clearances = 0 AND r.stats->>'clearances' IS NULL) AS cl,
  (ps.inside_50s = 0 AND r.stats->>'inside_50s' IS NULL) AS i50,
  (ps.rebound_50s = 0 AND r.stats->>'rebound_50s' IS NULL) AS rb,
  (ps.clangers = 0 AND r.stats->>'clangers' IS NULL) AS cg,
  (ps.time_on_ground_pct = 0 AND r.stats->>'time_on_ground_pct' IS NULL) AS tog
FROM work_1c_row_map r JOIN player_stats ps ON ps.id = r.ps_id;
DELETE FROM unrec WHERE (cp OR up OR cm OR mi OR op OR bo OR ga OR cl OR i50 OR rb OR cg OR tog) IS NOT TRUE;

SELECT season, count(*) AS rows, count(*) FILTER (WHERE cp) AS cp, count(*) FILTER (WHERE cl) AS clearances,
       count(*) FILTER (WHERE ga) AS goal_assist, count(*) FILTER (WHERE tog) AS tog
FROM unrec GROUP BY 1 ORDER BY 1;

INSERT INTO archive_1c_player_stats_pre
SELECT ps.* FROM player_stats ps JOIN unrec u ON u.id = ps.id ON CONFLICT (id) DO NOTHING;

UPDATE player_stats ps SET
  contested_possessions   = CASE WHEN u.cp  THEN NULL ELSE ps.contested_possessions END,
  uncontested_possessions = CASE WHEN u.up  THEN NULL ELSE ps.uncontested_possessions END,
  contested_marks         = CASE WHEN u.cm  THEN NULL ELSE ps.contested_marks END,
  marks_inside_50         = CASE WHEN u.mi  THEN NULL ELSE ps.marks_inside_50 END,
  one_percenters          = CASE WHEN u.op  THEN NULL ELSE ps.one_percenters END,
  bounces                 = CASE WHEN u.bo  THEN NULL ELSE ps.bounces END,
  goal_assist             = CASE WHEN u.ga  THEN NULL ELSE ps.goal_assist END,
  clearances              = CASE WHEN u.cl  THEN NULL ELSE ps.clearances END,
  inside_50s              = CASE WHEN u.i50 THEN NULL ELSE ps.inside_50s END,
  rebound_50s             = CASE WHEN u.rb  THEN NULL ELSE ps.rebound_50s END,
  clangers                = CASE WHEN u.cg  THEN NULL ELSE ps.clangers END,
  time_on_ground_pct      = CASE WHEN u.tog THEN NULL ELSE ps.time_on_ground_pct END,
  updated_at = now()
FROM unrec u WHERE ps.id = u.id;

-- which seasons now have each stat (non-NULL)
SELECT min(m.season) FILTER (WHERE ps.contested_possessions IS NOT NULL) AS cp_from,
       min(m.season) FILTER (WHERE ps.clearances IS NOT NULL) AS clearances_from,
       min(m.season) FILTER (WHERE ps.goal_assist IS NOT NULL) AS goal_assist_from,
       min(m.season) FILTER (WHERE ps.time_on_ground_pct IS NOT NULL) AS tog_from
FROM player_stats ps JOIN matches m ON m.id = ps.match_id;
COMMIT;
