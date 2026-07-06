"""
AFL Analytics Agent - Verified SQL Example Library (Milestone 3b)

Harvested from two sources:
  1. The ~16 SQL templates in the old (removed) `fast_path.py` (team wins,
     grand final winners, top-N lists, head-to-head, etc.) — these encode
     correct query *shapes* for the fast-path's own use, parameterized with
     `{year}`/`{team}`/etc. placeholders.
  2. The few-shot SQL examples embedded in `consolidated_llm.py`'s mega-prompt
     (`_INTENT_AND_SQL_PROMPT`) — trend/venue/ladder-style queries that
     fast_path doesn't cover.

Every example below was HARVESTED THEN RE-VERIFIED by executing it (with
concrete literal values substituted for the placeholders) directly against
the live DB (DB_STRING from backend/.env) on 2026-07-07, and sanity-checked
against known facts. Two real bugs were found and fixed during this pass
(see notes below); anything that couldn't be verified was dropped rather than
included broken. This module is intentionally NOT auto-generated from
fast_path.py's templates — each entry below is concrete SQL with a matching
concrete question, suitable for direct few-shot use in a prompt.

Bugs found + fixed while harvesting (do not "restore" these — they are bugs):
  - fast_path.py's pattern-matching ORDER + `_HEAD_TO_HEAD_SQL`'s single-season-only
    filter (`m.season = {year}`, no support for "since <year>" ranges) is the root
    cause of a known baseline failure: "What's Carlton's win-loss record against
    Essendon since 1990?" matched the generic `team_season_record` pattern before
    `head_to_head` could, AND even the head_to_head SQL itself couldn't express a
    "since" range. Fixed here as `head_to_head_since` using `season >= :year` plus
    an explicit per-team win/draw tally (verified: Carlton 31, Essendon 34, 4 draws,
    69 games total since 1990 — matches the DB exactly).
  - fast_path.py's `_TEAM_BYE_ROUNDS_SQL` is `SELECT DISTINCT m2.round ... ORDER BY
    CAST(m2.round AS INTEGER)` — this raises `InvalidColumnReference: for SELECT
    DISTINCT, ORDER BY expressions must appear in select list` in Postgres (verified
    by executing it directly). Fixed here by adding the cast as a second selected
    column (`round_num`) so it's a valid ORDER BY target.
  - fast_path.py's `_TEAM_LADDER_SQL` computes ladder position from raw wins/points-
    diff over ALL rounds including finals, and ranks by wins alone — this both counts
    finals wins toward ladder position (wrong — the ladder is regular-season only)
    and ignores draws/percentage as the real tiebreaker. Dropped entirely in favour of
    the correct premiership-points-based CTE from consolidated_llm.py's few-shot
    (`team_ladder_position` below), which excludes finals and ranks by
    wins*4+draws*2 then percentage, matching real AFL ladder rules.
"""
from typing import Any, Dict, List, Optional

# Each entry: {"id": str, "question": str, "sql": str, "tags": [str, ...]}
# `sql` uses concrete literal values matching `question` — copy-and-adapt style,
# not a template to `.format()`.
SQL_EXAMPLES: List[Dict[str, Any]] = [
    {
        "id": "grand_final_winner",
        "question": "Who won the 2024 AFL Grand Final?",
        "sql": (
            "SELECT CASE WHEN m.home_score > m.away_score THEN ht.name ELSE at.name END AS winner, "
            "CASE WHEN m.home_score > m.away_score THEN at.name ELSE ht.name END AS loser, "
            "GREATEST(m.home_score, m.away_score) AS winning_score, "
            "LEAST(m.home_score, m.away_score) AS losing_score, "
            "ht.name AS home_team, at.name AS away_team, m.home_score, m.away_score "
            "FROM matches m JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id "
            "WHERE m.season = 2024 AND m.round = 'Grand Final'"
        ),
        "tags": ["grand_final", "match_result", "winner", "simple_stat"],
        # Verified: home=Sydney(26) 60, away=Brisbane Lions(12) 120 -> Brisbane won 120-60.
    },
    {
        "id": "team_season_record",
        "question": "What was Carlton's win-loss record in 2023?",
        "sql": (
            "SELECT t.name AS team, "
            "SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score > m.home_score) THEN 1 ELSE 0 END) AS wins, "
            "SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score < m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score < m.home_score) THEN 1 ELSE 0 END) AS losses, "
            "SUM(CASE WHEN m.home_score = m.away_score THEN 1 ELSE 0 END) AS draws, "
            "COUNT(*) AS total_matches "
            "FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "WHERE t.name = 'Carlton' AND m.season = 2023 GROUP BY t.name"
        ),
        "tags": ["team_record", "wins_losses", "season", "simple_stat", "team_analysis"],
    },
    {
        "id": "current_season_total_no_union",
        "question": "How many games has Richmond won in 2026?",
        "sql": (
            "SELECT SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score > m.home_score) THEN 1 ELSE 0 END) AS wins, "
            "COUNT(*) AS games FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "WHERE t.name = 'Richmond' AND m.season = 2026"
        ),
        "tags": ["team_record", "wins_losses", "current_season", "simple_stat", "anti_union_guardrail"],
        # Verified against DB: 9 wins from 23 games. IMPORTANT: query `matches` ALONE for
        # season totals, even for the current season — never UNION with live_games (see
        # schema_docs.py live_games gotchas). This example exists specifically to model
        # that guardrail, not just the win-count shape already covered above.
    },
    {
        "id": "top_goal_kickers",
        "question": "Who were the top 5 goal kickers in 2024?",
        "sql": (
            "SELECT p.name, SUM(ps.goals) AS total_goals, t.name AS team "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE m.season = 2024 AND ps.goals IS NOT NULL "
            "GROUP BY p.id, p.name, t.id, t.name ORDER BY total_goals DESC NULLS LAST LIMIT 5"
        ),
        "tags": ["player_ranking", "goals", "top_n", "leaderboard"],
        # Verified top result: Jesse Hogan (GWS) 73 goals.
    },
    {
        "id": "top_disposal_getters",
        "question": "Who had the most disposals in 2024?",
        "sql": (
            "SELECT p.name, SUM(ps.disposals) AS total_disposals, t.name AS team "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE m.season = 2024 AND ps.disposals IS NOT NULL "
            "GROUP BY p.id, p.name, t.id, t.name ORDER BY total_disposals DESC NULLS LAST LIMIT 5"
        ),
        "tags": ["player_ranking", "disposals", "top_n", "leaderboard"],
    },
    {
        "id": "afl_fantasy_top_scorers",
        "question": "Who were the top AFL Fantasy scorers in 2024 (min. 5 games)?",
        "sql": (
            "SELECT p.name, t.name AS team, "
            "ROUND(AVG(ps.fantasy_points), 1) AS avg_fantasy, "
            "SUM(ps.fantasy_points) AS total_fantasy, COUNT(*) AS games_played "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE m.season = 2024 GROUP BY p.id, p.name, t.id, t.name "
            "HAVING COUNT(*) >= 5 ORDER BY avg_fantasy DESC NULLS LAST LIMIT 5"
        ),
        "tags": ["player_ranking", "fantasy", "top_n", "leaderboard"],
        # NOTE: the old fast_path.py recomputed fantasy points from raw stat columns by hand —
        # unnecessary and a source of drift. player_stats.fantasy_points is PRE-COMPUTED
        # in the DB using official AFL Fantasy scoring; SELECT it directly (see
        # schema_docs.py player_stats gotchas).
    },
    {
        "id": "brownlow_winner",
        "question": "Who won the Brownlow Medal in 2023 (per this database)?",
        "sql": (
            "SELECT p.name, SUM(ps.brownlow_votes) AS total_votes, t.name AS team "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE m.season = 2023 AND ps.brownlow_votes IS NOT NULL AND ps.brownlow_votes > 0 "
            "GROUP BY p.id, p.name, t.id, t.name ORDER BY total_votes DESC NULLS LAST LIMIT 1"
        ),
        "tags": ["brownlow", "award", "season", "simple_stat"],
        # Verified: this SQL returns Lachie Neale (31 votes) for 2023, NOT the real-world
        # winner Marcus Bontempelli (29) — a known DB data-quality gap (see schema_docs.py
        # player_stats gotchas). Kept as an example of the correct SQL SHAPE for querying
        # brownlow_votes, not as a claim that the result matches the real medal count.
    },
    {
        "id": "player_season_stats",
        "question": "What were Patrick Cripps's stats in 2023?",
        "sql": (
            "SELECT p.name, t.name AS team, COUNT(*) AS games, SUM(ps.goals) AS goals, "
            "SUM(ps.disposals) AS disposals, SUM(ps.kicks) AS kicks, SUM(ps.handballs) AS handballs, "
            "SUM(ps.marks) AS marks, SUM(ps.tackles) AS tackles, SUM(ps.hitouts) AS hitouts, "
            "SUM(ps.clearances) AS clearances, SUM(ps.inside_50s) AS inside_50s "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE p.name ILIKE 'Patrick%Cripps%' AND m.season = 2023 "
            "GROUP BY p.id, p.name, t.id, t.name"
        ),
        "tags": ["player_season", "player_stats", "simple_stat"],
        # Verified against ground truth (baseline pair_02): 24 games, 596 disposals
        # (226 kicks/370 handballs), 51 marks, 130 tackles, 9 goals, 146 clearances,
        # 77 inside 50s — exact match. NOTE the full-name ILIKE pattern: a bare
        # '%Cripps%' also matches "Jamie Cripps" (a different player, St Kilda/West
        # Coast) — always match on full name when the user gives one (see
        # schema_docs.py players gotchas).
    },
    {
        "id": "player_comparison",
        "question": "Compare Patrick Cripps and Marcus Bontempelli's disposals in 2023",
        "sql": (
            "SELECT p.name, SUM(ps.disposals) AS total_disposals "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id JOIN matches m ON ps.match_id = m.id "
            "WHERE (p.name ILIKE 'Patrick%Cripps%' OR p.name ILIKE 'Marcus%Bontempelli%') AND m.season = 2023 "
            "GROUP BY p.id, p.name ORDER BY total_disposals DESC"
        ),
        "tags": ["player_comparison", "disposals", "comparison"],
        # Verified: Bontempelli 636, Cripps 596.
    },
    {
        "id": "team_ladder_position",
        "question": "Where did Richmond finish on the ladder in 2023?",
        "sql": (
            "WITH season_records AS ("
            "SELECT m.season, t.name, "
            "SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score > m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score > m.home_score) THEN 1 ELSE 0 END) AS wins, "
            "SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score < m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score < m.home_score) THEN 1 ELSE 0 END) AS losses, "
            "SUM(CASE WHEN (m.home_team_id = t.id AND m.home_score = m.away_score) "
            "OR (m.away_team_id = t.id AND m.away_score = m.home_score) THEN 1 ELSE 0 END) AS draws, "
            "SUM(CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END) AS points_for, "
            "SUM(CASE WHEN m.home_team_id = t.id THEN m.away_score ELSE m.home_score END) AS points_against "
            "FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "WHERE m.round NOT IN ('Qualifying Final','Elimination Final','Semi Final','Preliminary Final','Grand Final') "
            "GROUP BY m.season, t.name"
            "), ranked AS ("
            "SELECT *, wins * 4 + draws * 2 AS premiership_points, "
            "ROUND(CASE WHEN points_against > 0 THEN points_for * 100.0 / points_against ELSE 0 END, 1) AS percentage, "
            "RANK() OVER (PARTITION BY season ORDER BY wins * 4 + draws * 2 DESC, "
            "CASE WHEN points_against > 0 THEN points_for * 1.0 / points_against ELSE 0 END DESC) AS position "
            "FROM season_records"
            ") "
            "SELECT season, position, wins, losses, draws, premiership_points, percentage "
            "FROM ranked WHERE name = 'Richmond' AND season = 2023"
        ),
        "tags": ["ladder", "standings", "team_analysis", "season"],
        # Verified: Richmond finished 13th in 2023 (10 wins, 12 losses, 1 draw, 42 pts,
        # 93.6%). Excludes finals (correct — ladder position is regular-season only) and
        # ranks by premiership points then percentage (correct tiebreaker), unlike
        # fast_path.py's buggy `_TEAM_LADDER_SQL` (see module docstring — dropped).
    },
    {
        "id": "team_bye_rounds",
        "question": "When did Geelong have a bye in 2025?",
        "sql": (
            "SELECT DISTINCT m2.round, CAST(m2.round AS INTEGER) AS round_num "
            "FROM matches m2 WHERE m2.season = 2025 AND m2.round ~ '^[0-9]+$' "
            "AND m2.round NOT IN ("
            "SELECT m.round FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "WHERE m.season = 2025 AND t.name = 'Geelong'"
            ") ORDER BY round_num"
        ),
        "tags": ["bye", "team_analysis", "season"],
        # Verified: Geelong's bye in 2025 was round 16. The original fast_path.py SQL
        # (`SELECT DISTINCT m2.round ... ORDER BY CAST(m2.round AS INTEGER)` with no
        # second selected column) raises a Postgres error for SELECT DISTINCT queries —
        # fixed here by selecting the cast as its own column so it's a valid ORDER BY
        # target (see module docstring).
    },
    {
        "id": "round_byes",
        "question": "Which teams had a bye in round 13 of 2025?",
        "sql": (
            "SELECT t.name AS team FROM teams t WHERE t.id NOT IN ("
            "SELECT m.home_team_id FROM matches m WHERE m.season = 2025 AND m.round = '13' "
            "UNION SELECT m.away_team_id FROM matches m WHERE m.season = 2025 AND m.round = '13'"
            ") AND t.id IN ("
            "SELECT m.home_team_id FROM matches m WHERE m.season = 2025 "
            "UNION SELECT m.away_team_id FROM matches m WHERE m.season = 2025"
            ") ORDER BY t.name"
        ),
        "tags": ["bye", "round", "season"],
        # Verified: Fremantle and St Kilda had the bye in round 13, 2025. The second
        # `t.id IN (...)` filter is required precisely because `teams` contains
        # non-AFL rows (see schema_docs.py teams gotchas) — without it, every NBA team
        # row would also show up as "on a bye".
    },
    {
        "id": "highest_score",
        "question": "What was the highest score in 2024?",
        "sql": (
            "SELECT ht.name AS home_team, at.name AS away_team, m.home_score, m.away_score, "
            "GREATEST(m.home_score, m.away_score) AS highest_score, "
            "ABS(m.home_score - m.away_score) AS margin, m.round, m.venue "
            "FROM matches m JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id "
            "WHERE m.season = 2024 ORDER BY highest_score DESC NULLS LAST LIMIT 1"
        ),
        "tags": ["highest_score", "record", "season", "simple_stat"],
        # Verified: Hawthorn 170 def. North Melbourne 46, round 24, York Park.
    },
    {
        "id": "head_to_head_single_season",
        "question": "Carlton vs Adelaide, round 5, 2024",
        "sql": (
            "SELECT ht.name AS home_team, at.name AS away_team, m.home_score, m.away_score, "
            "m.round, m.venue FROM matches m JOIN teams ht ON m.home_team_id = ht.id "
            "JOIN teams at ON m.away_team_id = at.id WHERE m.season = 2024 AND m.round = '5' "
            "AND ((ht.name = 'Carlton' AND at.name = 'Adelaide') OR (ht.name = 'Adelaide' AND at.name = 'Carlton'))"
        ),
        "tags": ["match_result", "head_to_head", "single_match"],
        # Verified: Carlton (home) 98, Adelaide (away) 100 — Adelaide won by 2.
    },
    {
        "id": "head_to_head_since",
        "question": "What's Carlton's win-loss record against Essendon since 1990?",
        "sql": (
            "SELECT COUNT(*) AS games, "
            "COUNT(*) FILTER (WHERE (home_team_id = 13 AND home_score > away_score) "
            "OR (away_team_id = 13 AND away_score > home_score)) AS carlton_wins, "
            "COUNT(*) FILTER (WHERE (home_team_id = 15 AND home_score > away_score) "
            "OR (away_team_id = 15 AND away_score > home_score)) AS essendon_wins, "
            "COUNT(*) FILTER (WHERE home_score = away_score) AS draws "
            "FROM matches WHERE season >= 1990 "
            "AND ((home_team_id = 13 AND away_team_id = 15) OR (home_team_id = 15 AND away_team_id = 13))"
        ),
        "tags": ["head_to_head", "wins_losses", "since_range", "team_analysis"],
        # Verified: 69 games, Carlton 31 wins, Essendon 34 wins, 4 draws — matches the
        # ground truth in scripts/benchmark_results/baseline_2026-07-07.json exactly.
        # This is the FIXED shape for the "since <year>" head-to-head query the baseline
        # got wrong (see module docstring). Written with literal team_ids (13, 15) here
        # to keep the example concrete/verifiable; generate_sql should substitute the
        # correct team_ids (or names, via a teams join) for whichever two teams are named.
    },
    {
        "id": "round_results",
        "question": "What happened in round 5 of 2024?",
        "sql": (
            "SELECT ht.name AS home_team, at.name AS away_team, m.home_score, m.away_score, "
            "CASE WHEN m.home_score > m.away_score THEN ht.name WHEN m.away_score > m.home_score THEN at.name "
            "ELSE 'Draw' END AS winner, ABS(m.home_score - m.away_score) AS margin, m.venue "
            "FROM matches m JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id "
            "WHERE m.season = 2024 AND m.round = '5' ORDER BY m.match_date"
        ),
        "tags": ["round_results", "match_result", "season"],
        # Verified: 8 matches returned for round 5, 2024, scores match DB.
    },
    {
        "id": "coleman_medal_winner",
        "question": "Who won the Coleman Medal in 2024?",
        "sql": (
            "SELECT p.name, SUM(ps.goals) AS total_goals, t.name AS team "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "JOIN matches m ON ps.match_id = m.id JOIN teams t ON ps.team_id = t.id "
            "WHERE m.season = 2024 AND ps.goals IS NOT NULL AND m.round ~ '^[0-9]+$' "
            "GROUP BY p.id, p.name, t.id, t.name ORDER BY total_goals DESC NULLS LAST LIMIT 1"
        ),
        "tags": ["coleman", "award", "goals", "season", "simple_stat"],
        # Verified: Jesse Hogan (GWS), 65 goals in the home-and-away season (round ~
        # '^[0-9]+$' excludes finals, which is how the real Coleman Medal is scored).
    },
    {
        "id": "player_career_stats",
        "question": "What are Dustin Martin's career stats?",
        "sql": (
            "SELECT p.name, COUNT(DISTINCT m.id) AS games, SUM(ps.goals) AS career_goals, "
            "SUM(ps.disposals) AS career_disposals, SUM(ps.marks) AS career_marks, "
            "SUM(ps.tackles) AS career_tackles, MIN(m.season) AS first_season, MAX(m.season) AS last_season "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id JOIN matches m ON ps.match_id = m.id "
            "WHERE p.name ILIKE 'Dustin%Martin%' GROUP BY p.id, p.name"
        ),
        "tags": ["player_career", "career_stats", "simple_stat"],
        # Verified against ground truth (baseline single_04): 338 career goals exactly.
        # Deliberately does NOT join/group by team_id — a career total should span every
        # club a player has been at, not fragment by team (players.team_id would also be
        # wrong here for the same reason — see players gotchas).
    },
    {
        "id": "team_scoring_trend",
        "question": "Show Geelong's scoring trend from 2018 to 2024",
        "sql": (
            "SELECT m.season, ROUND(AVG(CASE WHEN m.home_team_id = t.id THEN m.home_score "
            "ELSE m.away_score END), 1) AS avg_score FROM matches m "
            "JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "WHERE t.name = 'Geelong' AND m.season BETWEEN 2018 AND 2024 GROUP BY m.season ORDER BY m.season"
        ),
        "tags": ["trend", "scoring", "team_analysis", "trend_analysis", "chart"],
        # Verified: 7 rows (2018-2024), e.g. 2018=90.9, 2022=99.1, 2024=95.5.
    },
    {
        "id": "team_scores_at_venue",
        "question": "What were Adelaide's scores at the MCG in 2025?",
        "sql": (
            "SELECT m.round, "
            "CASE WHEN m.home_team_id = t.id THEN t_opp.name ELSE t_home.name END AS opponent, "
            "CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END AS adelaide_score, "
            "CASE WHEN m.home_team_id = t.id THEN m.away_score ELSE m.home_score END AS opponent_score "
            "FROM matches m JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id) "
            "JOIN teams t_home ON m.home_team_id = t_home.id JOIN teams t_opp ON m.away_team_id = t_opp.id "
            "WHERE t.name = 'Adelaide' AND m.season = 2025 AND m.venue = 'MCG' ORDER BY m.match_date"
        ),
        "tags": ["venue", "team_analysis", "team_specific_score_case"],
        # Verified: 3 rows for Adelaide at the MCG in 2025 (vs Essendon, Collingwood,
        # Richmond) — demonstrates the mandatory CASE pattern for team-specific
        # scores/opponents since a team can be on either the home or away side.
    },
]


def _normalize_word(word: str) -> str:
    """Crude deterministic stemming (strip one trailing 's') so goal/goals,
    disposal/disposals etc. match — good enough for keyword scoring, not real NLP."""
    word = word.strip()
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _score_example(example: Dict[str, Any], question_words: set, intent_str: str, entity_tokens: set) -> float:
    """
    Simple deterministic keyword/tag overlap score — no embeddings.

    Many examples legitimately share broad tags like "simple_stat" or "season",
    so an exact-intent match is only a small tiebreaker, not a dominant signal —
    otherwise topically-irrelevant examples that happen to share the intent tag
    would drown out examples with much stronger keyword/topic overlap.
    """
    tags = set(example["tags"])
    normalized_question_words = {_normalize_word(w) for w in question_words}
    score = 0.0

    # Intent match — small tiebreaker only (see docstring).
    if intent_str and intent_str in tags:
        score += 1.0

    # Individual words within each tag (e.g. "top_n" -> "top", "n") that also
    # appear in the question, normalized so plurals match singulars.
    for tag in tags:
        for tag_word in tag.replace("_", " ").split():
            if _normalize_word(tag_word) in normalized_question_words:
                score += 0.8

    # Overlap between the example's own question tokens and the input question tokens.
    example_tokens = set(example["question"].lower().replace("'", "").replace("?", "").split())
    overlap = example_tokens & question_words
    score += 0.4 * len(overlap)

    # Entity token overlap (team/player names mentioned in both).
    tag_overlap = entity_tokens & example_tokens
    score += 0.8 * len(tag_overlap)

    return score


def get_examples(
    question: str,
    intent: Optional[str] = None,
    entities: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    """
    Return the `top_k` most relevant examples for `question`/`intent`/`entities`,
    ranked by simple deterministic tag/keyword scoring (no embeddings, no LLM).

    Ties are broken by the example's position in SQL_EXAMPLES (stable sort) so
    results are fully deterministic given the same inputs.
    """
    entities = entities or {}
    intent_str = str(intent).lower().replace("queryintent.", "") if intent else ""
    question_lower = (question or "").lower()
    question_words = set(question_lower.replace("'", "").replace("?", "").split())

    entity_tokens: set = set()
    for key in ("teams", "players"):
        for v in (entities.get(key) or []):
            entity_tokens.update(str(v).lower().split())

    scored = [
        (_score_example(ex, question_words, intent_str, entity_tokens), i, ex)
        for i, ex in enumerate(SQL_EXAMPLES)
    ]
    # Sort by score desc, then original index asc (stable / deterministic).
    scored.sort(key=lambda t: (-t[0], t[1]))

    return [ex for score, i, ex in scored[:top_k] if score > 0] or [ex for _, _, ex in scored[:top_k]]


def get_example_count() -> int:
    return len(SQL_EXAMPLES)
