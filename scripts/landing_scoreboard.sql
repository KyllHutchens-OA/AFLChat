-- Regenerates frontend/src/data/landingScoreboard.json (the 3 pre-baked
-- scoreboard answers) and frontend/src/data/landingProof.json (the two
-- data-backed proof cards). Read-only, run against afl_dev:
-- psql "$DB_STRING" -f scripts/landing_scoreboard.sql
-- Then hand-transcribe the goals/behinds cumulative-by-quarter columns into
-- the JSON (goals*6 + behinds = cumulative score at that quarter).

-- 1. 2026 Grand Final result (also drives the "Sunday arvo" off-season strip)
select m.season, m.round_name, m.match_date::date, ht.name home, ht.abbreviation home_abbr,
  at.name away, at.abbreviation away_abbr, m.home_score, m.away_score,
  m.home_q1_goals, m.home_q1_behinds, m.home_q2_goals, m.home_q2_behinds,
  m.home_q3_goals, m.home_q3_behinds, m.home_q4_goals, m.home_q4_behinds,
  m.away_q1_goals, m.away_q1_behinds, m.away_q2_goals, m.away_q2_behinds,
  m.away_q3_goals, m.away_q3_behinds, m.away_q4_goals, m.away_q4_behinds
from matches m
join teams ht on ht.id = m.home_team_id
join teams at on at.id = m.away_team_id
where m.season = 2026 and m.round_name ilike '%grand final%';

-- 2. Highest team score in a match since 1990 (biggest blowout, fun trivia)
select m.season, m.round_name, m.match_date::date, ht.name home, ht.abbreviation home_abbr,
  at.name away, at.abbreviation away_abbr, m.home_score, m.away_score,
  m.home_q1_goals, m.home_q1_behinds, m.home_q2_goals, m.home_q2_behinds,
  m.home_q3_goals, m.home_q3_behinds, m.home_q4_goals, m.home_q4_behinds,
  m.away_q1_goals, m.away_q1_behinds, m.away_q2_goals, m.away_q2_behinds,
  m.away_q3_goals, m.away_q3_behinds, m.away_q4_goals, m.away_q4_behinds
from matches m
join teams ht on ht.id = m.home_team_id
join teams at on at.id = m.away_team_id
where m.season >= 1990 and m.home_score is not null and m.away_score is not null
order by greatest(m.home_score, m.away_score) desc
limit 1;

-- 3. Closest finals margin since 1990 (nail-biter, good for the flip-digit effect)
select m.season, m.round_name, m.match_date::date, ht.name home, ht.abbreviation home_abbr,
  at.name away, at.abbreviation away_abbr, m.home_score, m.away_score,
  abs(m.home_score - m.away_score) as margin,
  m.home_q1_goals, m.home_q1_behinds, m.home_q2_goals, m.home_q2_behinds,
  m.home_q3_goals, m.home_q3_behinds, m.home_q4_goals, m.home_q4_behinds,
  m.away_q1_goals, m.away_q1_behinds, m.away_q2_goals, m.away_q2_behinds,
  m.away_q3_goals, m.away_q3_behinds, m.away_q4_goals, m.away_q4_behinds
from matches m
join teams ht on ht.id = m.home_team_id
join teams at on at.id = m.away_team_id
where m.season >= 1990 and m.home_score <> m.away_score and m.is_final
order by margin asc, m.match_date desc
limit 1;

-- Honest numbers for the "How it thinks" section (also read from CLAUDE.md / V3_HANDOVER.md):
select count(*) as matches, min(season) as first_season, max(season) as last_season from matches;
select count(*) as player_stat_rows from player_stats;

-- Proof card 1: most career goals in the AFL era (data starts 1990, so this
-- is exact for any career fully inside the window, e.g. Lance Franklin's).
select p.name, sum(ps.goals) as career_goals
from player_stats ps join players p on p.id = ps.player_id
group by p.id, p.name
order by career_goals desc limit 5;

select m.season, sum(ps.goals) as goals
from player_stats ps
join players p on p.id = ps.player_id
join matches m on m.id = ps.match_id
where p.name ilike '%Lance Franklin%'
group by m.season order by m.season;

-- Proof card 2: Daicos vs Bontempelli, average disposals per season since 2021
select m.season,
  round(avg(case when p.name ilike '%Daicos%' then ps.disposals end)::numeric, 1) as daicos_avg,
  round(avg(case when p.name ilike '%Bontempelli%' then ps.disposals end)::numeric, 1) as bont_avg
from player_stats ps
join players p on p.id = ps.player_id
join matches m on m.id = ps.match_id
where m.season >= 2021 and (p.name ilike '%Daicos%' or p.name ilike '%Bontempelli%')
group by m.season order by m.season;
