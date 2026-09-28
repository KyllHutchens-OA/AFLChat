-- Least-privilege roles for Footy-NAC. Idempotent: safe to re-run (also re-sets passwords).
--
-- Run as the database owner (e.g. postgres), passwords as psql variables, never inline:
--   psql "$OWNER_DB_STRING" -v ON_ERROR_STOP=1 \
--        -v agent_ro_password="$AGENT_RO_PASSWORD" \
--        -v app_password="$APP_DB_PASSWORD" \
--        -v afl_fantasy_password="$AFL_FANTASY_DB_PASSWORD" \
--        -f scripts/db/roles.sql
--
-- agent_ro     : LLM-generated SQL (AGENT_DB_STRING). SELECT on AFL stat tables only,
--                read-only by default, 5s statement timeout. Must match
--                SQLValidator.ALLOWED_TABLES (backend/app/analytics/validators.py).
-- footynac_app : the web app / scheduler (DB_STRING). DML on the app's own tables, no DDL.
-- afl_fantasy  : the separate AFL Fantasy project (~/Code/AFL Fantasy, launchd com.afl-dfs.*).
--                DML on its dfs_* / pipeline tables; reads AFL tables; its weekly
--                sync_afl_data job runs AFL App ingestion, so it also writes players,
--                player_stats, matches, squiggle_predictions. No DDL: its migrate_*.py
--                scripts must run as the owner.

\if :{?agent_ro_password}
\else
  \echo 'ERROR: pass -v agent_ro_password=...'
  \quit
\endif
\if :{?app_password}
\else
  \echo 'ERROR: pass -v app_password=...'
  \quit
\endif
\if :{?afl_fantasy_password}
\else
  \echo 'ERROR: pass -v afl_fantasy_password=...'
  \quit
\endif

-- Create roles if missing (passwords set below)
SELECT 'CREATE ROLE agent_ro' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_ro') \gexec
SELECT 'CREATE ROLE footynac_app' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'footynac_app') \gexec
SELECT 'CREATE ROLE afl_fantasy' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'afl_fantasy') \gexec

ALTER ROLE agent_ro WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 10 PASSWORD :'agent_ro_password';
ALTER ROLE agent_ro SET default_transaction_read_only = on;
ALTER ROLE agent_ro SET statement_timeout = '5s';
ALTER ROLE agent_ro SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE agent_ro SET search_path = public;

ALTER ROLE footynac_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 40 PASSWORD :'app_password';
ALTER ROLE footynac_app SET statement_timeout = '60s';
ALTER ROLE footynac_app SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE footynac_app SET search_path = public;

ALTER ROLE afl_fantasy WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS
    CONNECTION LIMIT 20 PASSWORD :'afl_fantasy_password';
ALTER ROLE afl_fantasy SET statement_timeout = '120s';
ALTER ROLE afl_fantasy SET idle_in_transaction_session_timeout = '60s';
ALTER ROLE afl_fantasy SET search_path = public;

-- Neither role may hold server-file / program / superuser-adjacent memberships
DO $$
DECLARE r text; g text;
BEGIN
  FOREACH r IN ARRAY ARRAY['agent_ro', 'footynac_app', 'afl_fantasy'] LOOP
    FOR g IN SELECT b.rolname FROM pg_auth_members m
             JOIN pg_roles a ON a.oid = m.member JOIN pg_roles b ON b.oid = m.roleid
             WHERE a.rolname = r LOOP
      EXECUTE format('REVOKE %I FROM %I', g, r);
    END LOOP;
  END LOOP;
END $$;

GRANT CONNECT ON DATABASE :"DBNAME" TO agent_ro, footynac_app, afl_fantasy;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agent_ro, footynac_app, afl_fantasy;

-- Start from zero on every run, then grant the allowlist
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM agent_ro, footynac_app, afl_fantasy;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM agent_ro, footynac_app, afl_fantasy;

DO $$
DECLARE t text;
BEGIN
  -- agent_ro: AFL stat tables only (no conversations, api_usage, page_views, user_reports, admin tables)
  FOREACH t IN ARRAY ARRAY[
    'teams', 'players', 'matches', 'player_stats', 'team_stats',
    'live_games', 'betting_odds', 'squiggle_predictions', 'news_articles'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT ON public.%I TO agent_ro', t);
    ELSE
      RAISE NOTICE 'agent_ro: table % not found, skipped', t;
    END IF;
  END LOOP;

  -- footynac_app: every table the app's SQLAlchemy models use (backend/app/data/models.py)
  FOREACH t IN ARRAY ARRAY[
    'teams', 'players', 'matches', 'player_stats', 'team_stats',
    'live_games', 'live_game_events', 'quarter_snapshots', 'match_lineups',
    'match_previews', 'match_weather', 'betting_odds', 'squiggle_predictions',
    'news_articles', 'conversations', 'api_usage', 'page_views', 'user_reports',
    'api_sports_players', 'api_sports_team_mappings', 'api_request_logs', 'admin_users'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO footynac_app', t);
    ELSE
      RAISE NOTICE 'footynac_app: table % not found, skipped', t;
    END IF;
  END LOOP;

  -- afl_fantasy: its own tables (created by its migrate_*.py), full DML + serial sequences
  FOREACH t IN ARRAY ARRAY[
    'dfs_slates', 'dfs_salaries', 'dfs_projections', 'dfs_lineups', 'dfs_contests',
    'dfs_results', 'dfs_bankroll_log', 'dfs_name_mappings', 'dfs_entries',
    'dfs_notification_queue', 'dfs_actual_ownership', 'dfs_correlations', 'dfs_sim_results',
    'dfs_round_eval', 'dfs_model_promotions', 'dfs_projections_challenger', 'dfs_submission_log',
    'strategy_change_log', 'suggestions', 'heartbeats', 'pipeline_runs'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON public.%I TO afl_fantasy', t);
    ELSE
      RAISE NOTICE 'afl_fantasy: table % not found, skipped', t;
    END IF;
  END LOOP;

  -- afl_fantasy: AFL tables it reads (features, optimizer, slate poller)
  FOREACH t IN ARRAY ARRAY[
    'teams', 'players', 'matches', 'player_stats', 'match_weather', 'squiggle_predictions', 'betting_odds'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT SELECT ON public.%I TO afl_fantasy', t);
    END IF;
  END LOOP;

  -- afl_fantasy: weekly sync_afl_data job runs AFL App ingestion (stats_ingester, squiggle_fetcher).
  -- Drop these once that job moves into the AFL App worker.
  FOREACH t IN ARRAY ARRAY['players', 'player_stats', 'squiggle_predictions'] LOOP
    IF to_regclass('public.' || t) IS NOT NULL THEN
      EXECUTE format('GRANT INSERT, UPDATE ON public.%I TO afl_fantasy', t);
    END IF;
  END LOOP;
  IF to_regclass('public.matches') IS NOT NULL THEN
    GRANT UPDATE ON public.matches TO afl_fantasy;
  END IF;

  -- afl_fantasy: serial id sequences of every table it inserts into
  FOREACH t IN ARRAY ARRAY[
    'dfs_slates', 'dfs_salaries', 'dfs_projections', 'dfs_lineups', 'dfs_contests',
    'dfs_results', 'dfs_bankroll_log', 'dfs_name_mappings', 'dfs_entries',
    'dfs_notification_queue', 'dfs_actual_ownership', 'dfs_correlations', 'dfs_sim_results',
    'dfs_round_eval', 'dfs_model_promotions', 'dfs_projections_challenger', 'dfs_submission_log',
    'strategy_change_log', 'suggestions', 'heartbeats', 'pipeline_runs',
    'players', 'player_stats', 'squiggle_predictions'
  ] LOOP
    IF to_regclass('public.' || t) IS NOT NULL AND pg_get_serial_sequence('public.' || t, 'id') IS NOT NULL THEN
      EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO afl_fantasy', pg_get_serial_sequence('public.' || t, 'id'));
    END IF;
  END LOOP;
END $$;

-- footynac_app: serial sequences of the tables it was granted above (not the AFL Fantasy ones)
DO $$
DECLARE seq text;
BEGIN
  FOR seq IN
    SELECT DISTINCT pg_get_serial_sequence(format('public.%I', g.table_name), c.column_name)
      FROM information_schema.role_table_grants g
      JOIN information_schema.columns c
        ON c.table_schema = 'public' AND c.table_name = g.table_name
     WHERE g.grantee = 'footynac_app' AND g.privilege_type = 'INSERT' AND g.table_schema = 'public'
       AND pg_get_serial_sequence(format('public.%I', g.table_name), c.column_name) IS NOT NULL
  LOOP
    EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE %s TO footynac_app', seq);
  END LOOP;
END $$;

-- No default privileges: a table added by a migration gets no grants until it is added
-- to the right list above and this script is re-run.

-- Summary
SELECT r.rolname, r.rolsuper, r.rolbypassrls, r.rolconfig,
       (SELECT string_agg(table_name, ', ' ORDER BY table_name)
          FROM information_schema.role_table_grants g
         WHERE g.grantee = r.rolname AND g.privilege_type = 'SELECT') AS select_on
  FROM pg_roles r WHERE r.rolname IN ('agent_ro', 'footynac_app', 'afl_fantasy');
