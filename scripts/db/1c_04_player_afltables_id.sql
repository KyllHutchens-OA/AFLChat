-- 1C step 04: stable player identity (schema only, idempotent).
-- players.afltables_id = AFL Tables player key, e.g. 'T/Tom_Green' or 'J/Josh_Kennedy1'
-- (the path of afltables.com/afl/stats/players/<key>.html). Namesakes have distinct keys,
-- so this is the identity the stats ingester and the identity fixes (step 06) rely on.
BEGIN;
ALTER TABLE players ADD COLUMN IF NOT EXISTS afltables_id text;
CREATE UNIQUE INDEX IF NOT EXISTS ux_players_afltables_id ON players (afltables_id) WHERE afltables_id IS NOT NULL;
COMMENT ON COLUMN players.afltables_id IS 'AFL Tables player key (players/<key>.html); unique per real person';
SELECT count(*) AS players, count(afltables_id) AS with_afltables_id FROM players;
COMMIT;
