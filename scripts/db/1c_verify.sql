-- 1C verification: spot checks from reviews/2026-09-28 (6_eval_accuracy 4.4, 5_functional_qa D1-D8).
-- Read-only. Every row must say PASS.
WITH gf AS (
  SELECT m.season, h.name AS home, m.home_score, a.name AS away, m.away_score
  FROM matches m JOIN teams h ON h.id = m.home_team_id JOIN teams a ON a.id = m.away_team_id
  WHERE m.round_name = 'Grand Final'
),
pstat AS (
  SELECT p.name, p.afltables_id, m.season, m.is_final, ps.*
  FROM player_stats ps JOIN players p ON p.id = ps.player_id JOIN matches m ON m.id = ps.match_id
),
checks(check_name, actual, expected) AS (
  SELECT '2023 GF Collingwood 90 d Brisbane Lions 86',
         (SELECT string_agg(home || ' ' || home_score || ' v ' || away || ' ' || away_score, ';') FROM gf WHERE season = 2023),
         'Collingwood 90 v Brisbane Lions 86'
  UNION ALL SELECT '2022 GF Geelong 133 d Sydney 52',
         (SELECT string_agg(home || ' ' || home_score || ' v ' || away || ' ' || away_score, ';') FROM gf WHERE season = 2022),
         'Geelong 133 v Sydney 52'
  UNION ALL SELECT '2024 GF Brisbane Lions 120 d Sydney 60',
         (SELECT string_agg(home || ' ' || home_score || ' v ' || away || ' ' || away_score, ';') FROM gf WHERE season = 2024),
         'Sydney 60 v Brisbane Lions 120'
  UNION ALL SELECT '2026 GF Brisbane Lions 96 d Fremantle 89 (D5, B5)',
         (SELECT string_agg(home || ' ' || home_score || ' v ' || away || ' ' || away_score, ';') FROM gf WHERE season = 2026),
         'Fremantle 89 v Brisbane Lions 96'
  UNION ALL SELECT '2010 GF drawn + replay both present',
         (SELECT string_agg(round_name || ' ' || home_score || '-' || away_score, '; ' ORDER BY match_date) FROM matches WHERE season = 2010 AND round_name LIKE 'Grand Final%'),
         'Grand Final 68-68; Grand Final Replay 108-52'
  UNION ALL SELECT 'Charlie Curnow 2023 goals H&A / all',
         (SELECT sum(goals) FILTER (WHERE NOT is_final) || ' / ' || sum(goals) FROM pstat WHERE name = 'Charlie Curnow' AND season = 2023),
         '78 / 81'
  UNION ALL SELECT 'Jeremy Cameron 2023 goals (games)',
         (SELECT sum(goals) || ' (' || count(*) || ')' FROM pstat WHERE name = 'Jeremy Cameron' AND season = 2023),
         '53 (20)'
  UNION ALL SELECT 'Lance Franklin career goals / games',
         (SELECT sum(goals) || ' / ' || count(*) FROM pstat WHERE name = 'Lance Franklin'),
         '1066 / 354'
  UNION ALL SELECT 'Dustin Martin career goals / games',
         (SELECT sum(goals) || ' / ' || count(*) FROM pstat WHERE name = 'Dustin Martin'),
         '338 / 302'
  UNION ALL SELECT '2023 Brownlow Neale / Bontempelli',
         (SELECT sum(brownlow_votes) FILTER (WHERE name = 'Lachie Neale') || ' / ' || sum(brownlow_votes) FILTER (WHERE name = 'Marcus Bontempelli') FROM pstat WHERE season = 2023),
         '31 / 29'
  UNION ALL SELECT '2024 Brownlow Cripps',
         (SELECT sum(brownlow_votes)::text FROM pstat WHERE name = 'Patrick Cripps' AND season = 2024),
         '45'
  UNION ALL SELECT 'Tom Green (GWS) 2024 disposals, one team',
         (SELECT sum(disposals) || ' ' || string_agg(DISTINCT team_id::text, ',') FROM pstat WHERE name = 'Tom Green' AND season = 2024),
         '770 19'
  UNION ALL SELECT 'Jesse Hogan 2024 goals, one team',
         (SELECT sum(goals) || ' ' || string_agg(DISTINCT team_id::text, ',') FROM pstat WHERE name = 'Jesse Hogan' AND season = 2024),
         '77 19'
  UNION ALL SELECT '2024 NULL goals / max rows per match <= 46 (D3)',
         (SELECT count(*) FILTER (WHERE goals IS NULL) FROM pstat WHERE season = 2024) || ' / ' ||
         (SELECT (max(n) <= 46)::text FROM (SELECT count(*) n FROM player_stats ps JOIN matches m ON m.id = ps.match_id WHERE m.season = 2024 GROUP BY ps.match_id) x),
         '0 / true'
  UNION ALL SELECT 'matches whose player goals <> team goals (1990-2026)',
         (SELECT count(*)::text FROM matches m
           JOIN (SELECT match_id, sum(goals) g FROM player_stats GROUP BY 1) s ON s.match_id = m.id
           WHERE s.g <> m.home_q4_goals + m.away_q4_goals),
         '0'
  UNION ALL SELECT '2025 Geelong games = 26 (D4 duplicate removed)',
         (SELECT count(*)::text FROM matches WHERE season = 2025 AND 17 IN (home_team_id, away_team_id)),
         '26'
  UNION ALL SELECT '2026 completed matches without player stats (D2)',
         (SELECT count(*)::text FROM matches m WHERE m.season = 2026 AND m.match_status = 'completed'
            AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)),
         '0'
  UNION ALL SELECT '2026 round 20 has 9 matches with stats',
         (SELECT count(DISTINCT m.id)::text FROM matches m JOIN player_stats ps ON ps.match_id = m.id
           WHERE m.season = 2026 AND m.round_number = 20 AND NOT m.is_final),
         '9'
  UNION ALL SELECT '2026 finals round names (D8)',
         (SELECT string_agg(DISTINCT round_number || ':' || round_name, ', ') FROM matches WHERE season = 2026 AND is_final),
         '25:Wildcard Round, 26:Elimination Final, 26:Qualifying Final, 27:Semi Final, 28:Preliminary Final, 29:Grand Final'
  UNION ALL SELECT 'Opening Round = round_number 0 (2024-2026)',
         (SELECT string_agg(DISTINCT season || ':' || round, ',') FROM matches WHERE round_name = 'Opening Round'),
         '2024:0,2025:0,2026:0'
  UNION ALL SELECT 'legacy round finals labels consistent 1990-2026',
         (SELECT count(*)::text FROM matches WHERE is_final AND round <> round_name OR NOT is_final AND round <> round_number::text),
         '0'
  UNION ALL SELECT 'match counts 1990-1996 = AFL Tables (D7)',
         (SELECT string_agg(n::text, ',' ORDER BY season) FROM (SELECT season, count(*) n FROM matches WHERE season BETWEEN 1990 AND 1996 GROUP BY 1) x),
         '161,172,172,157,174,185,185'
  UNION ALL SELECT 'Fitzroy matches 1990-1996',
         (SELECT count(*)::text FROM matches WHERE 29 IN (home_team_id, away_team_id)),
         '152'
  UNION ALL SELECT 'Carlton 1995 games (QA Q20)',
         (SELECT count(*)::text FROM matches WHERE season = 1995 AND 13 IN (home_team_id, away_team_id)),
         '25'
  UNION ALL SELECT '1990-1996 matches without player stats',
         (SELECT count(*)::text FROM matches m WHERE m.season <= 1996
            AND NOT EXISTS (SELECT 1 FROM player_stats ps WHERE ps.match_id = m.id)),
         '0'
  UNION ALL SELECT '1995 contested possessions not recorded -> NULL',
         (SELECT count(*) FILTER (WHERE contested_possessions IS NOT NULL)::text FROM pstat WHERE season = 1995),
         '0'
  UNION ALL SELECT 'placeholder kick-offs (midnight, or 3+ at one time since 2002)',
         (SELECT (count(*) FILTER (WHERE match_date::time = '00:00') +
                 (SELECT count(*) FROM (SELECT 1 FROM matches WHERE season >= 2002 GROUP BY season, match_date HAVING count(*) >= 3) x))::text
            FROM matches),
         '0'
  UNION ALL SELECT 'player rows whose team is not in the match',
         (SELECT count(*)::text FROM player_stats ps JOIN matches m ON m.id = ps.match_id
           WHERE ps.team_id NOT IN (m.home_team_id, m.away_team_id)),
         '0'
  UNION ALL SELECT 'Josh J. Kennedy: one player with Carlton + West Coast rows',
         (SELECT count(DISTINCT player_id) || ' ' || string_agg(DISTINCT team_id::text, ',') FROM pstat
           WHERE name = 'Josh Kennedy' AND player_id IN (SELECT player_id FROM pstat WHERE name = 'Josh Kennedy' AND team_id = 27)),
         '1 13,27'
  UNION ALL SELECT 'Bailey Williams 2024: each player id <= 26 games, one club each',
         (SELECT (max(n) <= 26 AND max(t) = 1)::text FROM (SELECT player_id, count(*) n, count(DISTINCT team_id) t
            FROM pstat WHERE name = 'Bailey Williams' AND season = 2024 GROUP BY 1) x),
         'true'
)
SELECT CASE WHEN actual IS NOT DISTINCT FROM expected THEN 'PASS' ELSE 'FAIL' END AS result,
       check_name, actual, expected
FROM checks;
