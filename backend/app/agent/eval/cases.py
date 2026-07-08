"""
Eval case definitions.

Three sources of cases, merged here:

1. SMOKE15 — the 15-case gate set. Mirrors the Milestone-0 benchmark
   (scripts/benchmark_chat.py: 7 singles + 3 two-turn correction pairs +
   2 known-no-data queries, same ids so before/after comparison is trivial)
   plus 3 cases derived from the salvaged pre-restructure eval data.
   Expected facts were verified against the live DB on 2026-07-08; each
   case's `verification_sql` records how.

2. SALVAGED — the old `app/agent/eval/test_cases.py` suite, recovered from
   its CPython 3.14 bytecode (`test_cases.cpython-314.pyc`) by walking
   `co_consts` (the source file itself was deleted). Old field semantics
   were mapped onto the new EvalCase model:
       expect_response_contains  -> expected_facts
       expect_response_not_contains -> forbidden
       expect_chart_type         -> expects_chart (type-agnostic: validity
                                    is checked against ChartSpecV1, not the
                                    old Plotly type vocabulary)
       expect_no_chart           -> expects_no_chart
       expect_sql_substring      -> expected_sql_substrings
       conversation_history      -> conversation_history (as-is)

3. eval_queries.txt (repo root) — all 128 exploratory queries, parsed and
   auto-tagged. These carry no hand-verified facts, so they are only
   meaningfully scored with --judge.

Subsets (see SUBSETS): smoke15, corrections, no-data, charts, salvaged,
queries, all.
"""
import re
from pathlib import Path
from typing import Dict, List

from app.agent.eval.models import EvalCase

# Repo root: backend/app/agent/eval/cases.py -> up 4 levels.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_QUERIES_PATH = REPO_ROOT / "eval_queries.txt"


# ---------------------------------------------------------------------------
# 1. SMOKE15 — the gate set (12 M0-benchmark mirrors + 3 salvaged-derived).
# ---------------------------------------------------------------------------
SMOKE15: List[EvalCase] = [
    EvalCase(
        id="single_01",
        queries=["How many games has Collingwood won this season?"],
        tags=["smoke", "single", "current_season"],
        source="m0_benchmark",
        description="Current-season team wins; 'this season' resolves via the dynamic season ceiling (M1).",
        expected_facts=["collingwood"],
        # 9 = Collingwood wins in season 2026 (both completed-to-date and
        # full-season counts agree); 17 = the 2025 answer accepted at baseline.
        expected_any=["9", "17"],
        verification_sql=(
            "select count(*) filter (where (home_team_id=14 and home_score>away_score) "
            "or (away_team_id=14 and away_score>home_score)) from matches "
            "where (home_team_id=14 or away_team_id=14) and season=2026 and home_score is not null"
        ),
    ),
    EvalCase(
        id="single_02",
        queries=["Who won the Brownlow Medal in 2023?"],
        tags=["smoke", "single", "award"],
        source="m0_benchmark",
        description="Historical award fact.",
        # Real-world winner is Bontempelli (29 votes); the DB's brownlow_votes
        # column aggregates to Neale 31 for 2023 (known data-quality quirk
        # flagged at baseline) — accept either name.
        expected_any=["bontempelli", "neale"],
        verification_sql=(
            "select p.name, sum(ps.brownlow_votes) v from player_stats ps "
            "join players p on p.id=ps.player_id join matches m on m.id=ps.match_id "
            "where m.season=2023 group by p.name order by v desc limit 3"
        ),
    ),
    EvalCase(
        id="single_03",
        queries=["Show me a chart of Melbourne's wins per season since 2018"],
        tags=["smoke", "single", "chart", "trend"],
        source="m0_benchmark",
        description="Wins-per-season trend; should emit a valid ChartSpecV1 (line).",
        expected_facts=["melbourne"],
        expected_any=["2018"],
        expects_chart=True,
        verification_sql=(
            "select season, count(*) filter (where (home_team_id=21 and home_score>away_score) "
            "or (away_team_id=21 and away_score>home_score)) from matches "
            "where (home_team_id=21 or away_team_id=21) and season>=2018 group by season"
        ),
        notes="DB wins by season: 2018:16 2019:5 2020:9 2021:20 2022:16 2023:16 2024:11 2025:7 2026:10",
    ),
    EvalCase(
        id="single_04",
        queries=["What's Dustin Martin's career goals tally?"],
        tags=["smoke", "single", "career_total"],
        source="m0_benchmark",
        description="Career aggregate for a retired player.",
        expected_facts=["338"],
        verification_sql=(
            "select sum(goals) from player_stats ps join players p on p.id=ps.player_id "
            "where p.name ilike '%dustin martin%'"
        ),
    ),
    EvalCase(
        id="single_05",
        queries=["What was the score in the 2024 grand final?"],
        tags=["smoke", "single", "match_result"],
        source="m0_benchmark",
        description="Exact score lookup.",
        expected_facts=["brisbane", "120", "60"],
        verification_sql=(
            "select home_team_id, away_team_id, home_score, away_score from matches "
            "where season=2024 and round='Grand Final'  -- Sydney 60, Brisbane Lions 120"
        ),
    ),
    EvalCase(
        id="single_06",
        queries=["Show me a pie chart of scoring sources - goals vs behinds for Sydney in 2024"],
        tags=["smoke", "single", "chart", "pie"],
        source="m0_benchmark",
        description="Pie chart with two DB-verifiable slices (baseline's worst failure: fabricated numbers).",
        expected_facts=["sydney"],
        expected_any=["366", "239"],
        expects_chart=True,
        verification_sql=(
            "select sum(ps.goals), sum(ps.behinds) from player_stats ps "
            "join matches m on m.id=ps.match_id where ps.team_id=26 and m.season=2024"
            "  -- goals=366, behinds=239"
        ),
    ),
    EvalCase(
        id="single_07",
        queries=["What's Carlton's win-loss record against Essendon since 1990?"],
        tags=["smoke", "single", "head_to_head"],
        source="m0_benchmark",
        description="Head-to-head record with a since-year filter (baseline answered the wrong question).",
        expected_facts=["31", "34"],
        expected_any=["69"],
        verification_sql=(
            "select count(*), count(*) filter (where (home_team_id=13 and home_score>away_score) "
            "or (away_team_id=13 and away_score>home_score)), count(*) filter (where "
            "(home_team_id=15 and home_score>away_score) or (away_team_id=15 and "
            "away_score>home_score)) from matches where season>=1990 and "
            "((home_team_id=13 and away_team_id=15) or (home_team_id=15 and away_team_id=13))"
            "  -- 69 games, Carlton 31, Essendon 34"
        ),
    ),
    EvalCase(
        id="pair_01",
        queries=[
            "Who kicked the most goals last round?",
            "No, I meant round 10 of the 2024 season, not last round.",
        ],
        tags=["smoke", "pair", "correction"],
        source="m0_benchmark",
        description="Relative-time query then an explicit correction pinning round+season.",
        is_correction=True,
        expected_facts=["5"],
        expected_any=["cameron", "lohmann", "waterman", "hardwick"],
        verification_sql=(
            "select p.name, ps.goals from player_stats ps join players p on p.id=ps.player_id "
            "join matches m on m.id=ps.match_id where m.season=2024 and m.round='10' "
            "order by ps.goals desc nulls last limit 4"
            "  -- Lohmann/Cameron/Waterman/Hardwick all 5"
        ),
    ),
    EvalCase(
        id="pair_02",
        queries=[
            "Show me Patrick Cripps's stats for 2023",
            "Sorry, I meant Marcus Bontempelli, not Cripps.",
        ],
        tags=["smoke", "pair", "correction"],
        source="m0_benchmark",
        description="Player-swap correction; final answer must be Bontempelli's 2023 numbers.",
        is_correction=True,
        expected_facts=["bontempelli"],
        expected_any=["636", "27.7", "27.65"],  # total disposals or per-game average
        verification_sql=(
            "select count(*), sum(disposals) from player_stats ps join players p on "
            "p.id=ps.player_id join matches m on m.id=ps.match_id where p.name ilike "
            "'%bontempelli%' and m.season=2023  -- 23 games, 636 disposals"
        ),
    ),
    EvalCase(
        id="pair_03",
        queries=[
            "What was the score in the 2023 grand final?",
            "Actually I meant the 2022 grand final, not 2023.",
        ],
        tags=["smoke", "pair", "correction"],
        source="m0_benchmark",
        description="Year-swap correction on an exact score lookup.",
        is_correction=True,
        expected_facts=["geelong", "133", "52"],
        verification_sql=(
            "select home_team_id, away_team_id, home_score, away_score from matches "
            "where season=2022 and round='Grand Final'  -- Geelong 133, Sydney 52"
        ),
    ),
    EvalCase(
        id="nodata_01",
        queries=["What were Nick Daicos's stats in 2015?"],
        tags=["smoke", "nodata"],
        source="m0_benchmark",
        description="Player existed but has no rows before 2022; response must explain why.",
        expects_no_data=True,
        expected_facts=["daicos"],
        expected_any=["2022", "covers", "debut"],
        verification_sql=(
            "select min(m.season) from matches m join player_stats ps on ps.match_id=m.id "
            "join players p on p.id=ps.player_id where p.name='Nick Daicos'  -- 2022"
        ),
    ),
    EvalCase(
        id="nodata_02",
        queries=["What was the score in the 2030 AFL grand final?"],
        tags=["smoke", "nodata"],
        source="m0_benchmark",
        description="Season out of range (data covers 1990-2026); response must say so.",
        expects_no_data=True,
        expected_any=["2026", "1990"],
        verification_sql="select max(season) from matches  -- 2026",
    ),
    # ── Salvaged-derived additions (old eval suite, DB-verified 2026-07-08) ──
    EvalCase(
        id="salv_player_goals",
        queries=["How many goals did Charlie Curnow kick in 2024?"],
        tags=["smoke", "single", "salvaged"],
        source="salvaged",
        description="Salvaged 'player_goals_season' case: player+season stat join.",
        expected_facts=["curnow", "57"],
        verification_sql=(
            "select sum(ps.goals) from player_stats ps join players p on p.id=ps.player_id "
            "join matches m on m.id=ps.match_id where p.name ilike '%charlie curnow%' "
            "and m.season=2024  -- 57"
        ),
    ),
    EvalCase(
        id="salv_top_disposals",
        queries=["Top 5 disposal getters in 2024"],
        tags=["smoke", "single", "top_n", "salvaged"],
        source="salvaged",
        description="Salvaged 'top_disposals' case: top-N ranking.",
        expected_facts=["green"],
        expected_any=["770", "neale", "whitfield"],
        verification_sql=(
            "select p.name, sum(ps.disposals) d from player_stats ps join players p on "
            "p.id=ps.player_id join matches m on m.id=ps.match_id where m.season=2024 "
            "group by p.name order by d desc limit 5"
            "  -- Tom Green 770, Neale 762, Whitfield 754, Treloar 725, Zorko 711"
        ),
    ),
    EvalCase(
        id="salv_chart_trend",
        queries=["Show Carlton's average score per season from 2015 to 2024"],
        tags=["smoke", "chart", "trend", "salvaged"],
        source="salvaged",
        description="Salvaged 'chart_trend_line' case: season trend should chart.",
        expected_facts=["carlton"],
        expects_chart=True,
    ),
]


# ---------------------------------------------------------------------------
# 2. SALVAGED — the full old test_cases.py suite (recovered from bytecode).
# ---------------------------------------------------------------------------
SALVAGED: List[EvalCase] = [
    EvalCase(
        id="salvaged_grand_final_winner",
        queries=["Who won the 2024 grand final?"],
        tags=["salvaged", "sql", "simple"],
        source="salvaged",
        description="Basic grand final query — should use matches table with round='Grand Final'",
        expected_facts=["brisbane"],
        expects_no_chart=True,
        expected_sql_substrings=["grand final"],
    ),
    EvalCase(
        id="salvaged_team_wins_season",
        queries=["How many games did Collingwood win in 2023?"],
        tags=["salvaged", "sql", "simple"],
        source="salvaged",
        description="Team record query — should filter by team and season",
        expected_sql_substrings=["collingwood"],
    ),
    EvalCase(
        id="salvaged_player_goals_season",
        queries=["How many goals did Charlie Curnow kick in 2024?"],
        tags=["salvaged", "sql", "simple"],
        source="salvaged",
        description="Player stat query — should join player_stats, filter by player and season",
        expected_facts=["57"],
        expected_sql_substrings=["curnow"],
    ),
    EvalCase(
        id="salvaged_top_disposals",
        queries=["Top 5 disposal getters in 2024"],
        tags=["salvaged", "sql", "top_n"],
        source="salvaged",
        description="Top-N query — should ORDER BY DESC LIMIT 5",
        expected_sql_substrings=["limit 5"],
    ),
    EvalCase(
        id="salvaged_player_comparison",
        queries=["Compare Patrick Cripps and Clayton Oliver in 2024"],
        tags=["salvaged", "sql", "comparison"],
        source="salvaged",
        description="Player comparison — should return stats for both players",
        expected_facts=["cripps", "oliver"],
        expected_sql_substrings=["cripps"],
    ),
    EvalCase(
        id="salvaged_home_away_record",
        queries=["What was Carlton's home record in 2024?"],
        tags=["salvaged", "sql", "tricky"],
        source="salvaged",
        description="Home record — should filter to home_team_id only, not include away games",
        expected_sql_substrings=["home_team_id"],
        notes="Old case also asserted expect_sql_not_contain='away_team_id = t.id' (not modeled).",
    ),
    EvalCase(
        id="salvaged_trend_over_seasons",
        queries=["Show Geelong's win count per season from 2018 to 2024"],
        tags=["salvaged", "sql", "trend"],
        source="salvaged",
        description="Trend query — should GROUP BY season, return one row per season",
        expected_sql_substrings=["group by"],
    ),
    EvalCase(
        id="salvaged_player_name_full",
        queries=["How many goals did Will Ashcroft kick in 2024?"],
        tags=["salvaged", "sql", "entity"],
        source="salvaged",
        description="Full name match — SQL should match both first and last name, not just surname",
        expected_sql_substrings=["will"],
    ),
    EvalCase(
        id="salvaged_chart_trend_line",
        queries=["Show Carlton's average score per season from 2015 to 2024"],
        tags=["salvaged", "chart", "trend"],
        source="salvaged",
        description="Trend over seasons — should produce a line chart",
        expects_chart=True,
    ),
    EvalCase(
        id="salvaged_chart_comparison_bar",
        queries=["Compare the top 5 goal kickers in 2024"],
        tags=["salvaged", "chart", "comparison"],
        source="salvaged",
        description="Top-N comparison — should produce a bar chart",
        expects_chart=True,
        expected_any=["hogan", "cameron", "daniher"],
        verification_sql=(
            "select p.name, sum(ps.goals) g from player_stats ps join players p on "
            "p.id=ps.player_id join matches m on m.id=ps.match_id where m.season=2024 "
            "group by p.name order by g desc nulls last limit 5"
            "  -- Hogan 77, J.Cameron 64, Daniher 58, Curnow 57, Waterman 53"
        ),
    ),
    EvalCase(
        id="salvaged_chart_single_stat_no_chart",
        queries=["How many games did Melbourne play in 2024?"],
        tags=["salvaged", "chart"],
        source="salvaged",
        description="Single number result — should NOT produce a chart",
        expects_no_chart=True,
    ),
    EvalCase(
        id="salvaged_off_topic_query",
        queries=["What is the recipe for chocolate cake?"],
        tags=["salvaged", "error", "off_topic"],
        source="salvaged",
        description="Off-topic query — should be caught and return helpful redirect",
        expected_any=["afl", "footy", "stat", "help", "sorry"],
        expects_no_chart=True,
    ),
    EvalCase(
        id="salvaged_misspelled_team",
        queries=["How did Colllingwood go in 2024?"],
        tags=["salvaged", "error", "entity"],
        source="salvaged",
        description="Misspelled team name — should still resolve or give helpful message",
        expected_any=["collingwood"],
    ),
    EvalCase(
        id="salvaged_nonexistent_player",
        queries=["How many goals did Zxcvbn Qwerty kick in 2024?"],
        tags=["salvaged", "error", "nodata"],
        source="salvaged",
        description="Nonexistent player — should return empty results with helpful message",
        expects_no_data=True,
    ),
    EvalCase(
        id="salvaged_response_concise_simple",
        queries=["Who won the 2023 grand final?"],
        tags=["salvaged", "response", "concise"],
        source="salvaged",
        description="Simple fact — response should be concise, not a paragraph",
        expected_facts=["collingwood"],
        forbidden=["additional analysis", "i could also"],
    ),
    EvalCase(
        id="salvaged_response_match_result_format",
        queries=["What was the score of the 2024 grand final?"],
        tags=["salvaged", "response", "format"],
        source="salvaged",
        description="Match result — response should include both teams and scores",
        expected_facts=["brisbane"],
        expected_any=["120", "60"],
    ),
    EvalCase(
        id="salvaged_meta_what_can_you_do",
        queries=["What can you do?"],
        tags=["salvaged", "meta"],
        source="salvaged",
        description="Meta question — should explain capabilities",
        expected_any=["stat", "question", "ask", "help"],
    ),
    EvalCase(
        id="salvaged_meta_help",
        queries=["Help me understand how to use this"],
        tags=["salvaged", "meta"],
        source="salvaged",
        description="Help query — should explain what the agent can do",
        expected_any=["question", "ask", "stat", "help"],
    ),
    EvalCase(
        id="salvaged_followup_pronoun_resolution",
        queries=["What about his career average?"],
        tags=["salvaged", "followup", "pronoun"],
        source="salvaged",
        description="Follow-up with pronoun — should resolve 'his' to player from context",
        conversation_history=[
            {"role": "user", "content": "How many goals did Tom Hawkins kick in 2024?"},
            {
                "role": "assistant",
                "content": "Tom Hawkins kicked 31 goals in 2024.",
                "entities": {"players": ["Hawkins"], "teams": ["Geelong"], "seasons": [2024]},
            },
        ],
        expected_facts=["hawkins"],
        expected_sql_substrings=["hawkins"],
    ),
]


# ---------------------------------------------------------------------------
# 3. eval_queries.txt parsing (auto-tagged exploratory queries).
# ---------------------------------------------------------------------------
_CHART_RE = re.compile(
    r"\b(chart|plot|graph|worm|heatmap|scatter|pie|trend line)\b", re.IGNORECASE
)
_COMPARISON_RE = re.compile(
    r"\b(compare|comparison|versus|vs\.?|side by side|head-to-head)\b", re.IGNORECASE
)
_TREND_RE = re.compile(
    r"\b(per season|by season|each season|since \d{4}|from \d{4}|over the last|"
    r"over their career|trend|progression|track)\b",
    re.IGNORECASE,
)


def parse_eval_queries(path: Path = EVAL_QUERIES_PATH) -> List[EvalCase]:
    """Parse eval_queries.txt (one query per line) into auto-tagged EvalCases."""
    cases: List[EvalCase] = []
    lines = path.read_text().splitlines()
    n = 0
    for line in lines:
        query = line.strip()
        if not query:
            continue
        n += 1
        tags = ["queries"]
        expects_chart = bool(_CHART_RE.search(query))
        if expects_chart:
            tags.append("chart")
        if _COMPARISON_RE.search(query):
            tags.append("comparison")
        if _TREND_RE.search(query):
            tags.append("trend")
        cases.append(
            EvalCase(
                id=f"q{n:03d}",
                queries=[query],
                tags=tags,
                source="eval_queries",
                expects_chart=expects_chart,
            )
        )
    return cases


# ---------------------------------------------------------------------------
# Subsets
# ---------------------------------------------------------------------------
def build_subsets() -> Dict[str, List[EvalCase]]:
    """Build the named subset -> cases mapping (parses eval_queries.txt lazily)."""
    parsed = parse_eval_queries()
    subsets: Dict[str, List[EvalCase]] = {
        "smoke15": list(SMOKE15),
        "corrections": [c for c in SMOKE15 if c.is_correction],
        "no-data": [c for c in SMOKE15 if c.expects_no_data]
        + [c for c in SALVAGED if c.expects_no_data],
        "charts": [c for c in SMOKE15 if c.expects_chart]
        + [c for c in SALVAGED if c.expects_chart or c.expects_no_chart],
        "salvaged": list(SALVAGED),
        "queries": parsed,
    }
    # "all": everything, without duplicate ids.
    seen = set()
    everything: List[EvalCase] = []
    for case in [*SMOKE15, *SALVAGED, *parsed]:
        if case.id not in seen:
            seen.add(case.id)
            everything.append(case)
    subsets["all"] = everything
    return subsets


def get_subset(name: str) -> List[EvalCase]:
    """Return the cases for a named subset; raises ValueError on unknown name."""
    subsets = build_subsets()
    if name not in subsets:
        raise ValueError(
            f"Unknown subset '{name}'. Available: {', '.join(sorted(subsets))}"
        )
    return subsets[name]


def get_case(case_id: str) -> EvalCase:
    """Return a single case by id from the union of all subsets."""
    for case in build_subsets()["all"]:
        if case.id == case_id:
            return case
    raise ValueError(f"Unknown case id '{case_id}'")
