-- Drop the legacy betting_odds table (odds feature cut in roadmap 1B).
-- Not run automatically. Run manually against each DB once the 1B code is
-- deployed and nothing reads the table:
--   psql "$DB_STRING" -f scripts/db/drop_betting_odds.sql
-- Optional backup first:
--   pg_dump "$DB_STRING" -t betting_odds > betting_odds_backup.sql

BEGIN;
DROP TABLE IF EXISTS betting_odds;
COMMIT;
