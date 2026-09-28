"""
AFL Analytics Agent - Curated Schema Documentation (Milestone 3b)

Replaces the ~300-line embedded schema block inside the old (removed)
`consolidated_llm.py`'s
mega-prompt with small, per-table documentation strings that `retrieve_context`
prunes down to only the tables relevant to the current query before handing
them to `generate_sql`.

Ground truth for this file:
  - `backend/app/data/models.py` (SQLAlchemy models)
  - the removed `consolidated_llm.py`'s `_INTENT_AND_SQL_PROMPT` (the
    schema/gotchas block being replaced)
  - Live DB introspection (2026-07-07) via
    `SELECT column_name, data_type FROM information_schema.columns` against
    DB_STRING from `backend/.env` — this caught two drifts from the mega
    prompt / models.py that are captured in the gotchas below:
      1. `teams` contains non-AFL rows (NBA teams alongside the 18 AFL clubs
         + Fitzroy) — 49 total rows, only 19 are ever referenced by `matches`.
      2. `player_stats` has a `draftstars_points` column not mentioned
         anywhere in the mega prompt or models.py.
"""
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Per-table documentation. Kept short and information-dense — this is meant
# to be pruned to 1-4 tables per query, not dumped whole into every prompt.
# ---------------------------------------------------------------------------

SCHEMA_DOCS: Dict[str, str] = {
    "teams": """\
### teams
Purpose: AFL club reference table (name, abbreviation, home stadium).
Columns: id (int, PK), name (varchar — canonical club name), abbreviation (varchar),
  stadium (varchar), primary_color/secondary_color (hex), founded_year (int).
Join key: teams.id <- matches.home_team_id / matches.away_team_id / player_stats.team_id / live_games.home_team_id/away_team_id.
Gotchas:
  - Use EXACT canonical names in WHERE clauses: 'Adelaide' (not "Adelaide Crows"),
    'Geelong' (not "Geelong Cats"), 'Greater Western Sydney' (not "GWS Giants"),
    'Sydney' (not "Sydney Swans"), 'West Coast' (not "West Coast Eagles").
  - CRITICAL DATA QUALITY ISSUE: this table has 49 rows but only 19 are AFL clubs
    (18 current clubs + historical 'Fitzroy') — the rest are NBA team names that
    leaked in from unrelated seed data. NEVER `SELECT DISTINCT name FROM teams`
    or otherwise trust an unfiltered scan of this table to enumerate "all teams" —
    always resolve team names against a known AFL name/nickname, or filter to
    teams actually referenced by `matches`/`live_games`.""",

    "matches": """\
### matches
Purpose: Historical + backfilled match results, one row per completed/scheduled game.
Columns: id (int, PK), season (int), round (varchar — see gotcha below),
  round_number (int: Opening Round = 0, home-and-away 1..N, finals continue after the last
  H&A round), is_final (bool), round_name (text: 'Opening Round', 'Round 5', 'Wildcard Round',
  'Qualifying Final', 'Elimination Final', 'Semi Final', 'Preliminary Final', 'Grand Final';
  replays of drawn finals are 'Grand Final Replay' / 'Qualifying Final Replay'),
  match_date (timestamp, venue-local kick-off), venue (varchar), home_team_id/away_team_id
  (int, FK teams), home_score/away_score (int), attendance (int),
  home_q1_goals/home_q1_behinds..home_q4_goals/home_q4_behinds (int, CUMULATIVE at each break),
  away_q1_goals/away_q1_behinds..away_q4_goals/away_q4_behinds (int, CUMULATIVE).
Join key: matches.home_team_id/away_team_id -> teams.id; matches.id <- player_stats.match_id,
  team_stats.match_id, betting_odds.match_id, squiggle_predictions.match_id, live_games.match_id.
Season coverage: 1990-2026 (season 2026 is a fully completed 218-game season incl. finals in this DB
  even though it's the "current" season — do not assume 2026 is partial/in-progress).
Gotchas:
  - Prefer `round_number` / `is_final` / `round_name`. Regular season = `NOT m.is_final`;
    grand final = `m.round_name = 'Grand Final'`; "round 20" = `m.round_number = 20 AND NOT m.is_final`.
  - Legacy `round` is a VARCHAR: H&A rounds are the strings '0'-'24' (Opening Round = '0');
    finals are the literal strings 'Wildcard Round', 'Qualifying Final', 'Elimination Final',
    'Semi Final', 'Preliminary Final', 'Grand Final' (same in every season, 2026 included).
    Always quote round values: WHERE m.round = '5', never WHERE m.round = 5.
  - Quarter columns are cumulative (AFL Tables style): score at 3/4 time = q3_goals*6 + q3_behinds;
    points scored IN quarter 3 = (q3_goals*6+q3_behinds) - (q2_goals*6+q2_behinds).
  - A team can be on either the home or away side in any given match — NEVER select raw
    home_score/away_score when the question is about a specific team; always use
    `CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END`.
  - "Since <year>" / "all-time" questions need `m.season >= <year>` (a range), not
    `m.season = <year>` (a single season) — this exact mistake (using = instead of >=,
    or ignoring an opponent filter) produced a wrong answer for a Carlton-vs-Essendon
    head-to-head "since 1990" question in benchmarking; always re-check that BOTH the
    season range AND every named team are present in the WHERE clause.
  - Fixture/future rows exist with home_score=0 AND away_score=0 (unplayed games) —
    filter these out unless the question is specifically about upcoming fixtures.""",

    "players": """\
### players
Purpose: Player registry (one row per player).
Columns: id (int, PK), name (varchar, "First Last"), first_name/last_name (varchar),
  team_id (int, FK teams — CURRENT team ONLY), position (varchar, NOT populated —
  do not filter on it), jersey_number, height_cm, weight_kg, date_of_birth, debut_year,
  debut_date, is_active (bool).
Join key: players.id <- player_stats.player_id.
Gotchas:
  - players.team_id is the player's CURRENT club only — WRONG for any historical/
    traded-player query. For "which team did X play for in season Y" use
    player_stats.team_id (the team they were actually contracted to for that match),
    never players.team_id.
  - Multiple players share the same name (e.g. 4 different "Josh Kennedy"s, 2 "Tom
    Lynch"s, 2 "Gary Ablett"s, 2 "Nathan Brown"s). ALWAYS GROUP BY p.id, p.name when
    aggregating — GROUP BY p.name alone silently merges distinct players into one row.
  - Surname-only searches should use `p.name ILIKE '%Surname%'`; when the user gives a
    full name, match BOTH parts (`p.name ILIKE 'First%Last%'`) so you don't pull in a
    different player with the same surname (e.g. "Will Ashcroft" vs "Levi Ashcroft").
  - `position` is present in the schema but not populated for any row — never filter on
    it; if asked for "midfielders"/"forwards" etc., suggest filtering by relevant stats
    instead (high disposals for mids, high goals for forwards).""",

    "player_stats": """\
### player_stats
Purpose: Per-match player statistics (the main table for any player-level SQL).
Columns: id (int, PK), match_id (FK matches), player_id (FK players),
  team_id (FK teams — team the player played FOR in THIS match, correct across trades),
  disposals, kicks, handballs, marks, tackles, goals, behinds, hitouts, clearances,
  inside_50s, rebound_50s, contested_possessions, uncontested_possessions,
  contested_marks, marks_inside_50, one_percenters, bounces, goal_assist, clangers,
  free_kicks_for, free_kicks_against, brownlow_votes, fantasy_points (int, PRE-COMPUTED
  official AFL Fantasy score — SELECT directly, never ask the user which scoring system),
  time_on_ground_pct (numeric), draftstars_points (numeric — a second, separate fantasy
  scoring system present in the live DB but not documented elsewhere; don't confuse with
  fantasy_points unless the user specifically asks about DraftStars).
Join key: player_stats.match_id -> matches.id; player_stats.player_id -> players.id;
  player_stats.team_id -> teams.id.
Gotchas:
  - Use player_stats.team_id (NOT players.team_id) whenever aggregating stats "for team
    X" — this is the only column that's correct for traded players.
  - ALWAYS GROUP BY p.id, p.name (see players gotchas) — never GROUP BY p.name alone.
  - Known DB data-quality issue: `brownlow_votes` aggregated by season does not always
    match the real-world Brownlow Medal result exactly (e.g. season 2023 sums to Lachie
    Neale 31 > Marcus Bontempelli 29 in this DB, but Bontempelli won the real medal) —
    treat brownlow_votes as the DB's internal record, not a guaranteed real-world match.
  - `goals`/`behinds` here are PLAYER-level; do not confuse with matches' quarter-level
    goals/behinds columns (team-level, per quarter) when a query mixes player and team
    scoring language.""",

    "team_stats": """\
### team_stats
Purpose: Per-match TEAM-level advanced stats (one row per team per match) — distinct
  from `matches` (which only has scores) and from aggregating `player_stats` per team.
Columns: id (int, PK), match_id (FK matches), team_id (FK teams), is_home (bool),
  score (int), inside_50s, clearances, contested_possessions, uncontested_possessions,
  tackles, marks, hitouts, free_kicks_for, free_kicks_against (all int).
Join key: team_stats.match_id -> matches.id; team_stats.team_id -> teams.id.
Gotchas:
  - Sparse relative to player_stats/matches — only use this table when the question is
    specifically about team-level advanced stats (e.g. "Collingwood's inside 50s per
    game") that aren't just SUM/AVG of matches.home_score/away_score. For plain win/loss/
    score questions, `matches` alone is sufficient and simpler.
  - `score` here should equal the corresponding matches.home_score/away_score for that
    team/match — if cross-checking, join on match_id AND team_id.""",

    "live_games": """\
### live_games
Purpose: Live/recent-game tracking table populated from the Squiggle SSE feed for the
  current season, used as a stopgap for games not yet backfilled into `matches`.
Columns: id (int, PK), squiggle_game_id (int), match_id (int, FK matches — set once the
  completed game has been backfilled), season (int), round (varchar: Squiggle round
  NUMBER as text, even for finals, e.g. '29' = 2026 GF; use matches.round_name via
  match_id for names), home_team_id/away_team_id (FK teams),
  home_score/away_score, home_goals/home_behinds/away_goals/away_behinds (int),
  home_q1_score..away_q4_score (int, cumulative per quarter), status (varchar:
  'scheduled'|'playing'|'completed'|'post_match'), complete_percent (int 0-100),
  time_str (varchar), current_quarter (int), venue, match_date, winner_team_id.
Join key: live_games.match_id -> matches.id (nullable — null until backfilled);
  live_games.home_team_id/away_team_id -> teams.id.
Gotchas:
  - CRITICAL: rows in `live_games` DUPLICATE rows in `matches` once a game is backfilled
    (typically within 1-3 days) — `live_games.match_id` is then set to point at the
    matching `matches.id` row. NEVER UNION `matches` with `live_games` for a season
    total/aggregate: every already-backfilled game would be double-counted (verified
    live 2026-07-07: currently 100% of `live_games` rows already have `match_id` set,
    i.e. every one of them is also present in `matches` right now).
  - Use `live_games` ONLY for the handful of most-recent games not yet in `matches`
    (current-round in-progress/just-finished scores). For season totals, ladder
    position, or any "this season"/"since <year>" aggregate, query `matches` ALONE.
  - If you ever must combine both tables in one query, exclude already-backfilled rows
    with `AND lg.match_id IS NULL` on the live_games side.
  - status values: 'scheduled' (not started), 'playing' (in progress), 'completed',
    'post_match'. "games left"/"remaining"/"upcoming" -> status NOT IN ('completed',
    'post_match'); "results so far" -> status IN ('completed', 'post_match').""",

    "betting_odds": """\
### betting_odds
Purpose: Bookmaker odds snapshots for matches (fetched from The Odds API).
Columns: id (int, PK), match_id (FK matches), bookmaker (varchar),
  home_odds/away_odds (numeric, decimal odds format), odds_fetched_at (timestamp).
Join key: betting_odds.match_id -> matches.id.
Gotchas: multiple rows per match (one per bookmaker/fetch time) — take the most recent
  odds_fetched_at per bookmaker, or average across bookmakers, depending on the question.
  Betting/tipping questions are normally answered via the BettingTool/TippingTool
  (execute_node routes them there directly, no SQL needed) — this table is documented
  here for completeness, not because generate_sql typically needs to query it directly.""",

    "squiggle_predictions": """\
### squiggle_predictions
Purpose: Match outcome predictions from the Squiggle model.
Columns: id (int, PK), match_id (FK matches), predicted_winner_id (FK teams),
  predicted_margin (numeric), home_win_probability/away_win_probability (numeric 0-100),
  source_model (varchar), prediction_date (timestamp).
Join key: squiggle_predictions.match_id -> matches.id; predicted_winner_id -> teams.id.
Gotchas: tipping/prediction questions are normally answered via TippingTool
  (execute_node routes them there directly, no SQL needed) — documented here for
  completeness.""",
}

# Tables the SQL layer can query, per SQLValidator.ALLOWED_TABLES — news_articles is
# handled by NewsTool (execute_node), never by generated SQL, so it's intentionally not
# documented here.
_ALL_TABLES = frozenset(SCHEMA_DOCS.keys())

# ---------------------------------------------------------------------------
# Pruning
# ---------------------------------------------------------------------------

_PLAYER_METRIC_KEYWORDS = frozenset({
    "goals", "behinds", "disposals", "kicks", "handballs", "marks", "tackles",
    "hitouts", "clearances", "inside_50s", "inside 50s", "rebound_50s", "rebound 50s",
    "contested_possessions", "contested possessions", "uncontested_possessions",
    "uncontested possessions", "contested_marks", "contested marks", "one_percenters",
    "one percenters", "bounces", "clangers", "free_kicks", "free kicks",
    "brownlow", "brownlow_votes", "fantasy", "fantasy_points", "draftstars",
    "time_on_ground", "time on ground",
})

_TEAM_ADVANCED_METRIC_KEYWORDS = frozenset({
    "inside 50s", "inside_50s", "clearances", "contested possessions",
    "uncontested possessions", "tackles", "marks", "hitouts",
})

# The DB's most recent season — used only as a deterministic pruning heuristic
# (whether to include live_games docs), NOT for any actual query logic (SQL
# generation itself gets the real current season dynamically elsewhere via
# app.data.database.get_data_recency()).
_LATEST_KNOWN_SEASON = 2026


def _entity_seasons_are_recent(seasons: List[Any]) -> bool:
    """True if any season entity is at/after the latest known season, or none given."""
    if not seasons:
        # No season specified at all is a common shape for "current"/"latest" style
        # questions ("who's playing this week", "top of the ladder") — err on the
        # side of including live_games docs.
        return True
    for s in seasons:
        try:
            if int(str(s).strip()) >= _LATEST_KNOWN_SEASON:
                return True
        except (TypeError, ValueError):
            continue
    return False


def get_schema_docs(intent: Optional[str], entities: Optional[Dict[str, Any]] = None) -> str:
    """
    Return pruned schema documentation relevant to `intent` + `entities`.

    Deterministic, keyword/entity-driven — no LLM, no DB access. `intent` may be a
    QueryIntent enum, its `.value` string, or a plain string (e.g. from a cheap
    heuristic classifier run before generate_sql has produced a real intent) —
    normalized to lowercase text for matching.

    Pruning rules (kept intentionally simple):
      - `matches` + `teams` are always included (nearly every query joins through them).
      - `players` + `player_stats` are added when entities name any players, or the
        intent/metrics look player-shaped (e.g. "player_comparison", or any metric that
        is a player_stats column like disposals/goals/tackles).
      - `live_games` is added when no season is specified, or a named season is the
        latest known season (current-year queries commonly touch live/recent games).
      - `betting_odds` / `squiggle_predictions` are added only for their matching
        intents (mostly for documentation completeness — those intents are normally
        answered by dedicated tools, not generated SQL).
      - `team_stats` is added only for team_analysis queries whose metrics name a
        team-level advanced stat (inside 50s, clearances, etc.) not just scores.
    """
    entities = entities or {}
    intent_str = str(intent).lower().replace("queryintent.", "") if intent else ""

    players = entities.get("players") or []
    teams = entities.get("teams") or []
    seasons = entities.get("seasons") or []
    metrics = [str(m).lower().strip() for m in (entities.get("metrics") or [])]

    tables = {"matches", "teams"}

    player_related = bool(players) or intent_str == "player_comparison" or any(
        m in _PLAYER_METRIC_KEYWORDS for m in metrics
    )
    if player_related:
        tables.add("players")
        tables.add("player_stats")

    if intent_str == "betting_odds":
        tables.add("betting_odds")
    if intent_str == "tipping_advice":
        tables.add("squiggle_predictions")

    if _entity_seasons_are_recent(seasons):
        tables.add("live_games")

    if intent_str == "team_analysis" and any(m in _TEAM_ADVANCED_METRIC_KEYWORDS for m in metrics):
        tables.add("team_stats")

    # Deterministic ordering so prompts/tests are stable regardless of set iteration order.
    ordered = [t for t in ("teams", "matches", "players", "player_stats", "team_stats",
                           "live_games", "betting_odds", "squiggle_predictions") if t in tables]
    return "\n\n".join(SCHEMA_DOCS[t] for t in ordered)


def get_all_table_names() -> frozenset:
    """All documented table names (for tests / sanity checks)."""
    return _ALL_TABLES
