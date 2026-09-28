-- 1C step 01: structured round columns on matches (schema only, idempotent).
-- Values are backfilled by `python -m app.data.fixes_1c.sync_matches --apply`.
--
-- Contract (other code relies on this exactly):
--   round_number int      Opening Round = 0, home-and-away 1..N, finals continue
--                         numerically after the last H&A round (one number per finals week)
--   is_final     boolean  not null default false (Wildcard Round counts as a final)
--   round_name   text     'Opening Round', 'Round 5', 'Wildcard Round', 'Qualifying Final',
--                         'Elimination Final', 'Semi Final', 'Preliminary Final', 'Grand Final'
--                         (a replay of a drawn final gets ' Replay', e.g. 2010 'Grand Final Replay')
--   round (legacy varchar, kept): str(round_number) for H&A (Opening Round = '0'),
--                         round_name for finals.
-- Also: match_date = venue-local kick-off time as published by AFL Tables.
BEGIN;

SELECT count(*) AS matches_total,
       count(*) FILTER (WHERE round !~ '^\d+$') AS named_rounds_before
FROM matches;

ALTER TABLE matches ADD COLUMN IF NOT EXISTS round_number integer;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS is_final boolean NOT NULL DEFAULT false;
ALTER TABLE matches ADD COLUMN IF NOT EXISTS round_name text;

COMMENT ON COLUMN matches.round_number IS 'Opening Round = 0, H&A 1..N, finals continue numerically after the last H&A round';
COMMENT ON COLUMN matches.is_final IS 'true for all finals incl. Wildcard Round';
COMMENT ON COLUMN matches.round_name IS 'Opening Round | Round N | Wildcard Round | Qualifying Final | Elimination Final | Semi Final | Preliminary Final | Grand Final (+ '' Replay'' for replays of drawn finals)';
COMMENT ON COLUMN matches.round IS 'Legacy label: round_number as text for H&A (Opening Round = 0), round_name for finals';
COMMENT ON COLUMN matches.match_date IS 'Venue-local kick-off time (AFL Tables)';

CREATE INDEX IF NOT EXISTS ix_matches_season_round_number ON matches (season, round_number);
CREATE INDEX IF NOT EXISTS ix_player_stats_player_id ON player_stats (player_id);

SELECT count(*) FILTER (WHERE round_number IS NULL) AS round_number_null,
       count(*) FILTER (WHERE is_final) AS is_final_true
FROM matches;

COMMIT;
