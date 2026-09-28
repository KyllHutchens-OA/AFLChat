-- Least-privilege roles for Footy-NAC. Idempotent: safe to re-run (also re-sets passwords).
--
-- Run as the database owner (e.g. postgres), passwords as psql variables, never inline:
--   psql "$OWNER_DB_STRING" -v ON_ERROR_STOP=1 \
--        -v agent_ro_password="$AGENT_RO_PASSWORD" \
--        -v app_password="$APP_DB_PASSWORD" \
--        -f scripts/db/roles.sql
--
-- agent_ro     : LLM-generated SQL (AGENT_DB_STRING). SELECT on AFL stat tables only,
--                read-only by default, 5s statement timeout. Must match
--                SQLValidator.ALLOWED_TABLES (backend/app/analytics/validators.py).
-- footynac_app : the web app / scheduler (DB_STRING). DML on the app's own tables, no DDL.

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

-- Create roles if missing (passwords set below)
SELECT 'CREATE ROLE agent_ro' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'agent_ro') \gexec
SELECT 'CREATE ROLE footynac_app' WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'footynac_app') \gexec

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

-- Neither role may hold server-file / program / superuser-adjacent memberships
DO $$
DECLARE r text; g text;
BEGIN
  FOREACH r IN ARRAY ARRAY['agent_ro', 'footynac_app'] LOOP
    FOR g IN SELECT b.rolname FROM pg_auth_members m
             JOIN pg_roles a ON a.oid = m.member JOIN pg_roles b ON b.oid = m.roleid
             WHERE a.rolname = r LOOP
      EXECUTE format('REVOKE %I FROM %I', g, r);
    END LOOP;
  END LOOP;
END $$;

GRANT CONNECT ON DATABASE :"DBNAME" TO agent_ro, footynac_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO agent_ro, footynac_app;

-- Start from zero on every run, then grant the allowlist
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM agent_ro, footynac_app;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM agent_ro, footynac_app;

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
END $$;

-- Serial/identity sequences for inserts
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO footynac_app;

-- Tables created later by the owner (migrations) become usable by the app, never by agent_ro
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO footynac_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO footynac_app;

-- Summary
SELECT r.rolname, r.rolsuper, r.rolbypassrls, r.rolconfig,
       (SELECT string_agg(table_name, ', ' ORDER BY table_name)
          FROM information_schema.role_table_grants g
         WHERE g.grantee = r.rolname AND g.privilege_type = 'SELECT') AS select_on
  FROM pg_roles r WHERE r.rolname IN ('agent_ro', 'footynac_app');
