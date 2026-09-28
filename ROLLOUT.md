# Footy-NAC Part 1 production rollout

This is the executable checklist for cutting prod over to `p1/integration` (v3 agent
loop, 1C data fixes, least-privilege DB roles). It was rehearsed end to end on
2026-09-28 against a restored copy of the prod dump taken at 15:52 that day (NBA data
already removed). Every command below was run for real in that rehearsal; the
"expected" counts are what the rehearsal produced, not estimates. Nothing in this
rehearsal touched Railway or production: it ran entirely against a local Postgres 18
database named `afl_rollout_rehearsal`.

`$PROD` below stands for the production Postgres connection string. It is never
written out in this file; the owner supplies it at run time (e.g.
`export PROD="postgresql://postgres@<prod-host>:<port>/<db>"`, using the current
`postgres` superuser credential from `~/afl-db-backups/`).

## Prerequisites

- A fresh `pg_dump -Fc "$PROD" -f afl_prod_pre_rollout.dump` (this is the safety net;
  keep it until step 12's smoke checklist passes and the owner signs off).
- The 1C page cache (AFL Tables + Squiggle pages, ~7,300 files) copied somewhere the
  prod box (or wherever you run the migration from) can read it. Rehearsed at
  `AFL_1C_CACHE=/path/to/1c/cache`; the rehearsal made zero live HTTP requests (every
  page was a cache hit) and finished the whole 1C sequence in about 4 minutes.
- Postgres 18 client tools (`psql`, `pg_dump`, `pg_restore`) matching the prod server
  version (18.6).
- `backend/venv` with the `p1/integration` `requirements.txt` installed (the 1C fix
  scripts and the app itself run from here).
- The owner in the loop: per the roadmap decision, every step that writes to prod or
  deploys needs explicit go-ahead.
- Postgres access as the `postgres` superuser (owns every table in the current dump)
  for the DB steps; new low-privilege roles are created partway through.

## Order and why

DB steps 1-6 below are additive: they change data and add tables/columns/roles
without removing anything the *currently running* (pre-rollout) app depends on, with
one exception called out at step 5 (dropping `betting_odds`). Everything is designed
so prod keeps serving traffic on the old code throughout, then a single fast-forward
deploy (step 8) cuts over the app code and env vars together. Aim for zero downtime.

## Steps

### 1. Fresh prod backup

```bash
pg_dump -Fc "$PROD" -f afl_prod_pre_rollout.dump
```
Verification: `pg_restore --list afl_prod_pre_rollout.dump | head` shows a non-empty
TOC and today's dump date. Rollback: not applicable (this step only reads).

### 2. V7 migration (conversation owner tokens, api_usage request grouping)

```bash
psql "$PROD" -v ON_ERROR_STOP=1 -f database/migrations/V7__conversation_owner_token_and_usage_request_id.sql
```
Expected (rehearsal): `ALTER TABLE` x2, `CREATE INDEX` x1, under 0.1s. Purely additive
(`ADD COLUMN IF NOT EXISTS`), safe to run against the live DB while the old code is
still running (it does not read these columns).
Verification: `psql "$PROD" -c "\d conversations" -c "\d api_usage"` shows
`owner_token_hash` and `request_id`.
Rollback: `ALTER TABLE conversations DROP COLUMN owner_token_hash; ALTER TABLE api_usage DROP COLUMN request_id;`
(only safe once the new code, which writes them, is not running).

### 3. chat_traces table (1E trace rows)

```bash
psql "$PROD" -v ON_ERROR_STOP=1 -f scripts/db/1e_chat_traces.sql
```
Expected (rehearsal): `CREATE TABLE`, 2x `CREATE INDEX`, under 0.1s. New table, no
effect on the running app.
Verification: `psql "$PROD" -c "\d chat_traces"`.
Rollback: `DROP TABLE IF EXISTS chat_traces;`

### 4. 1C data fixes (scripts/db/1C_RUNBOOK.md, now 13 steps)

Run exactly the runbook in `scripts/db/1C_RUNBOOK.md` on `p1/integration`, in order,
against `$PROD` (its own doc uses `$PROD_DB` for the same thing). Rehearsal results,
which matched the runbook's dev-derived expectations on every step:

| # | Command | Expected (rehearsal) | Time |
|---|---|---|---|
| 01 | `psql "$PROD" -f scripts/db/1c_01_round_columns.sql` | adds round_number/is_final/round_name, all NULL/false pre-backfill | 0.13s |
| 02 | `psql "$PROD" -f scripts/db/1c_02_dedupe_matches.sql` | 1 duplicate 2025 match + 46 player rows archived; matches 6957 -> 6956 | 0.34s |
| 03 | `venv/bin/python -m app.data.fixes_1c.sync_matches --apply` (dry run first, no flag) | 134 matches inserted, round columns backfilled on all, 328 finals; matches 6956 -> 7090 | 3.9s |
| 04 | `psql "$PROD" -f scripts/db/1c_04_player_afltables_id.sql` | schema only | 0.04s |
| 05 | `venv/bin/python -m app.data.fixes_1c.map_rows` | 298,370 rows mapped; 1,102 not on team lists, 503 duplicates, 2,319 page players without a row | 191s (no `--apply`; builds work tables only) |
| 06 | `psql "$PROD" -f scripts/db/1c_06_remove_phantom_rows.sql` | 1,600 rows archived + deleted (983 2024, 113 2026, 1 2021 unlisted; ~497 exact duplicates) | 0.12s |
| 07 | `venv/bin/python -m app.data.fixes_1c.identity --apply` (dry run first) | 37 splits moving 710 rows, 43 players created, 33 merged away, 3 empty removed, ~3,700 keyed; 1 uncertain ('Unknown', expected) | 2.1s |
| 08 | `venv/bin/python -m app.data.fixes_1c.reconcile_stats --overwrite-seasons 2026 --apply` (dry run first) | team_id fixed on 3,959 rows; ~20,223 stat values replaced; 2,319 rows inserted | 5.2s |
| 09 | `psql "$PROD" -f scripts/db/1c_09_unrecorded_stats_null.sql` | ~92,000 pre-era rows set to NULL (CP/UP/etc. before 1999, clearances/inside 50s/etc. before 1998, goal assist before 2003) | 3.1s |
| 10 | `venv/bin/python -m app.data.fixes_1c.backfill` | 227 matches backfilled, 9,734 player_stats rows created, 0 unavailable | 17.2s |
| 11 | `psql "$PROD" -f scripts/db/1c_11_sync_live_games_scores.sql` (new; see below) | 187 `live_games` rows corrected to match `matches`; 0 remaining mismatches | <0.1s |
| 12 | `psql "$PROD" -f scripts/db/1c_verify.sql` | 30/30 PASS | 0.6s |
| 13 | `curl "$API/api/health/data"` | `"status": "ok"`, all four `checks` at 0 | n/a |

Total DB rehearsal time end to end (steps 1-13 of this table plus V7 and chat_traces):
about 3.5 minutes, dominated by step 05 (in-memory matching against the page cache,
no network).

**Step 11 is new**, found during this rehearsal, not in the original 1C work: step 03
corrects `matches` but nothing in 1C wrote those corrections back to `live_games`, so
`live_games`' own quarter breakdown could disagree with its own final score. Concretely,
before step 11 the 2026 Grand Final's `live_games` row showed `away_q4_score = 90`
against a final score of 96 (the correct `matches` result, Brisbane Lions d Fremantle
96-89). `scripts/db/1c_11_sync_live_games_scores.sql` overwrites `live_games`' score,
goals/behinds and Q1-Q4 cumulative scores from `matches` for every match AFL Tables has
confirmed. It is new in this branch; full detail and rollback SQL are in
`scripts/db/1C_RUNBOOK.md` (step 11) and in the script's own header comment.

Verification query for step 11 specifically:
```sql
SELECT m.home_score, m.away_score, lg.home_q4_score, lg.away_q4_score
FROM matches m JOIN live_games lg ON lg.match_id = m.id
WHERE m.season = 2026 AND m.round_name = 'Grand Final';
-- expect 89, 96, 89, 96
```

Rollback: each 1C step has its own rollback recipe in `scripts/db/1C_RUNBOOK.md`
("Rollback" section); every step archives what it touches (`archive_1c_*` tables), so
nothing is destructive. Last resort for the whole sequence:
`pg_restore --clean -d "$PROD" afl_prod_pre_rollout.dump`.

**Ordering risk (accepted):** the *currently running* prod code (pre-rollout) still
has an odds-fetch scheduler job and references `betting_odds` in its SQL allowlist.
Steps 1-13 above do not touch it, so there is no risk yet. The betting-odds drop is
step 5 below, still before the code deploy (step 8) per the roadmap's decision; between
step 5 and step 8, the old code's odds cron job will log a caught, non-fatal error
twice a day (9am/5pm) and an odds-related agent question would fail its SQL and get a
graceful "no data" style answer rather than crash. This is a bounded, self-healing
gap of a few hours at most, not an outage; call it out to the owner rather than skip it
silently, since the health check will show up as noise in logs.

### 5. Drop betting_odds

```bash
psql "$PROD" -v ON_ERROR_STOP=1 -f scripts/db/drop_betting_odds.sql
```
Expected (rehearsal): 1,710 rows dropped with the table, under 0.1s.
Verification: `psql "$PROD" -c "SELECT to_regclass('public.betting_odds')"` returns
NULL.
Rollback: restore from the step 1 dump (`pg_restore -t betting_odds`) or from an
ad hoc `pg_dump -t betting_odds "$PROD"` backup taken first if you want a lighter-weight
rollback path (`scripts/db/drop_betting_odds.sql`'s header suggests this).

### 6. Roles: footynac_app, agent_ro, afl_fantasy

```bash
psql "$PROD" -v ON_ERROR_STOP=1 \
     -v agent_ro_password="$AGENT_RO_PASSWORD" \
     -v app_password="$APP_DB_PASSWORD" \
     -v afl_fantasy_password="$AFL_FANTASY_DB_PASSWORD" \
     -f scripts/db/roles.sql
```
Generate three fresh random passwords first (rehearsed with throwaway values; use a
real generator, e.g. `openssl rand -base64 32`, for prod). Expected (rehearsal): 3
roles created/updated, grants applied, betting_odds grant lines skipped with a NOTICE
(already dropped), under 0.3s. This step is additive and safe with the old app still
running: it does not touch the `postgres` role the old app currently connects as.
Verification: the script's own final `SELECT rolname, ... FROM pg_roles ...` summary,
plus (rehearsed):
```sql
SELECT usename, count(*) FROM pg_stat_activity GROUP BY 1;  -- confirm old app is still on postgres, not broken
```
Rollback: `DROP OWNED BY agent_ro, footynac_app, afl_fantasy; DROP ROLE agent_ro, footynac_app, afl_fantasy;`
(only if nothing has connected as them yet).

## Railway environment variable changes

Names only; generate real values at rollout time and store them nowhere but Railway's
env var UI and the owner's password manager.

### Backend service (`lively-love`)

Set:
- `DB_STRING` -> the `footynac_app` connection string (was `postgres`)
- `AGENT_DB_STRING` -> the `agent_ro` connection string (new)
- `AGENT_ENGINE=v3` (new; cuts over from the v2 LangGraph pipeline)
- `AGENT_MODEL`, `AGENT_EFFORT` (new; defaults are fine if unset, but set explicitly
  so a future default change doesn't silently move prod)
- `SUMMARY_MODEL`, `NEWS_ENRICHMENT_MODEL`, `NEWS_SERVICE_TIER` (new)
- `ANALYTICS_ADMIN_TOKEN` (new, long random string; needed even if the hotfix already
  set it, confirm it's still there)
- `RUN_SCHEDULER=true` (confirm still set; only one backend process should have this)
- `FLASK_ENV=production` (confirm still set)
- `SECRET_KEY` (confirm still set; do not rotate this in the same change as the DB
  password, to keep the blast radius of any one change small)

Remove:
- `OPENAI_MODEL`, `OPENAI_MODEL_FAST`, `OPENAI_MODEL_RESPONSE` (v2-era; the models
  they name retire from the OpenAI API on 2026-12-11, and v3 reads `AGENT_MODEL` /
  `SUMMARY_MODEL` / `NEWS_ENRICHMENT_MODEL` instead)
- `THEODDSAPI_KEY` (odds cut, D5; dead code as of this branch)
- `API_SPORTS_KEY` (API-Sports removed; dead code as of this branch)
- `FLASK_DEBUG` (if present at all; must not be set in production)

### Frontend service (`AFLChat`)

Remove (if still present; 1A hotfix should already have removed them, confirm):
- `OPENAI_API_KEY`
- `SECRET_KEY`

Leave as is: `VITE_BACKEND_URL`, and `API_ORIGIN` / `API_WS_ORIGIN` only if the API
is not at `https://api.footynac.com` (the Caddyfile defaults to that host).

## AFL Fantasy: switch to the afl_fantasy role (do this BEFORE rotating the postgres password)

The AFL Fantasy project (`~/Code/AFL Fantasy`) is a separate app on the same Postgres
instance, run locally via three launchd jobs (`com.afl-dfs.flask`,
`com.afl-dfs.scheduler`, `com.afl-dfs.discord`). It currently connects as `postgres`.
Once the `postgres` password is rotated (step 10), it will fail until switched. Do this
switch any time after step 6 (the `afl_fantasy` role exists) and confirm it works
**before** step 10, so there is no gap where AFL Fantasy can't reach the database.

Files that hold the connection string (none of them are edited from this repo):
- `~/Code/AFL Fantasy/backend/.env` -> `DB_STRING=` (read by `com.afl-dfs.flask`)
- `~/Library/LaunchAgents/com.afl-dfs.scheduler.plist` -> inline `DB_STRING` in its
  `EnvironmentVariables` dict (this value wins over the `.env` file for that job)
- `~/Library/LaunchAgents/com.afl-dfs.discord.plist` -> same, inline `DB_STRING`

Set all three to the `afl_fantasy` connection string built from the password chosen
in step 6 (`postgresql://afl_fantasy:$AFL_FANTASY_DB_PASSWORD@<prod-host>:<port>/<db>`).

Reload the three jobs after editing:
```bash
launchctl bootout gui/$(id -u)/com.afl-dfs.flask      2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.afl-dfs.flask.plist
launchctl bootout gui/$(id -u)/com.afl-dfs.scheduler  2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.afl-dfs.scheduler.plist
launchctl bootout gui/$(id -u)/com.afl-dfs.discord    2>/dev/null; launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.afl-dfs.discord.plist
```
(`launchctl unload` / `launchctl load` with the plist path is the older equivalent if
`bootout`/`bootstrap` aren't available on this macOS version.)

Verification (rehearsed against the local `afl_fantasy` role, not against AFL
Fantasy's actual code, since that project's own jobs were not run): a representative
SELECT/INSERT/UPDATE against every table class it uses succeeded and rolled back
cleanly as `afl_fantasy`; a DDL attempt (`ALTER TABLE players ADD COLUMN ...`) was
correctly rejected ("must be owner of table players"). After the real switch, confirm
for real: the Flask app boots and answers a request, the scheduler completes one
cycle without a permission error in its log, and the weekly `sync_afl_data.py` job's
next scheduled run (or a manual dry run) completes without a permission error.

## 7. Merge and push (fast-forward to main)

`p1/integration` was merged with `origin/main` in this rehearsal (fetch, then merge
`p1/1c-data` and `origin/main`, resolving conflicts in favour of 1A/1E/1C behaviour;
see the merge commits on `p1/integration`). It is already a fast-forward of `main`.
Immediately before deploying:
```bash
git fetch origin
git switch p1/integration
git merge --ff-only origin/main   # should be a no-op if nothing landed on main since
git push origin p1/integration:main
```
If `--ff-only` fails, something new landed on `main`; stop and re-merge before pushing.
Rollback: `git push origin <previous main sha>:main --force-with-lease` (coordinate
with the owner; Railway will redeploy on this push too).

## 8. Deploy

Railway redeploys the backend and frontend automatically on the push to `main` in step
7, once the env var changes above are saved. Both services use their Procfile-declared
gunicorn command (`gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker --workers 1 ... run:app`);
this rehearsal booted the app with exactly that command (plus `--worker-connections
1000 --timeout 120` from the Procfile) against the rehearsal database and it started
cleanly. Note there is a long-standing Procfile/nixpacks.toml disagreement (nixpacks
lacks the `--worker-connections`/`--timeout` flags); Railway uses the Procfile when
both are present, which is what was rehearsed, but this drift is worth fixing
separately (still open in the 1F backlog).

## 9. Post-deploy smoke checklist

All of these were exercised in the rehearsal (against the rehearsal DB, not prod) and
passed; repeat them against the real deploy:

- `GET /api/health` -> 200, `database.status: ok`, `openai: configured`
- `GET /api/health/data` -> `status: ok` (or `warn` with an explained, expected reason)
- `GET /api/analytics/traffic` with no `Authorization` header -> 401; with a wrong
  bearer token -> 401; with `Authorization: Bearer $ANALYTICS_ADMIN_TOKEN` -> 200
- A WebSocket chat conversation of 5 questions including one that should produce a
  chart and "who won the 2026 grand final" (rehearsed answer: "Brisbane Lions won the
  2026 Grand Final, defeating Fremantle 14.12 (96) to 12.17 (89)." with a chart on the
  Geelong-wins question); confirm no `error` events
- `GET /api/conversations/<id>` for that conversation: 401 with no
  `X-Conversation-Token` header, 404 with a wrong token, 200 with the real owner token
  returned in `conversation_started`
- Confirm the scheduler logs show all jobs registered ("Poll Squiggle for live games",
  "Ingest player stats from AFL Tables", "Data health check", etc.) and no
  errors/tracebacks in the first few minutes
- Confirm AFL Fantasy still works end to end (see the AFL Fantasy section above)

## 10. Rotate the postgres password

Only after step 9 passes and the AFL Fantasy switch (above) is confirmed working.
```bash
psql "$PROD" -c "SELECT usename, application_name, client_addr FROM pg_stat_activity;"
-- confirm nothing still connects as postgres (the app, the scheduler, AFL Fantasy)
-- other than your own interactive session
psql "$PROD" -c "ALTER ROLE postgres WITH PASSWORD '<new random password>';"
```
Update the new password in `~/afl-db-backups/` (or wherever the owner keeps the
superuser credential) immediately; nothing else should need it day to day now that
`footynac_app`, `agent_ro` and `afl_fantasy` exist.
Rollback: `ALTER ROLE postgres WITH PASSWORD '<old password>';` while it is still
known.

## 11. Close the public TCP proxy (optional, per 1A)

Only after confirming AFL Fantasy (which runs on the Mac, not Railway) can still reach
Postgres some other way, or accepting that it needs the proxy to stay open. The 1A
handover left this open deliberately ("The public DB proxy stays open, because AFL
Fantasy runs on the Mac"); do not close it without a replacement access path for AFL
Fantasy.

## 12. Delete v2 (later, per roadmap 1E gate)

Not part of this rollout; do this after a few stable days on v3, per the roadmap's
"Gate and cut over" section.

## Estimated total downtime

**Zero**, by design: every DB step (2-6) is additive or affects only a table
(`betting_odds`) whose loss is caught and logged, not fatal, in the old running code.
The cutover itself is a single `git push` that Railway redeploys from; Railway's
rolling restart of a single-worker service means a short window (rehearsed startup:
about 1-2 seconds from `gunicorn` start to "Scheduler started" and the app answering
health checks) where requests may briefly queue or 502 while the new worker boots,
the same as any other deploy on this app. No maintenance window is needed. The riskiest
window is between step 5 (drop betting_odds) and step 8 (deploy): at most a few hours
of harmless, logged odds-job errors on the old code, bounded by how quickly steps 5-8
are run back to back.
