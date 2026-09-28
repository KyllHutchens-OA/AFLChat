"""
Eval case definitions and subsets.

Sources, merged here:

1. GATE — the original 15-case M5 gate set (same ids as the Milestone-0
   benchmark so before/after comparison stays trivial), rewritten in 1D to
   use LIVE ground truth: each case's `verification_sql` runs at eval time
   and `truth` / `chart` expectations point at its columns. No hard-coded
   numbers, so "this season" cases no longer rot.

2. BANK (case_bank.py) — 1D ground-truth families: current-season finals,
   ladder, nicknames, corrections, clarification, off-topic, injection,
   namesakes, Brisbane Bears/Lions, per-game averages, multi-team trends,
   scatter, multi-metric compare, quarters, ties, win/loss, no-data,
   coverage caveats, history.

3. SALVAGED — the old `app/agent/eval/test_cases.py` suite, recovered from
   its bytecode in M5. Static string checks only; kept as a legacy subset.

4. eval_queries.txt (repo root) — 128 exploratory queries, auto-tagged, no
   ground truth (only meaningful with --judge).

Subsets (see build_subsets): smoke, full, dev, heldout, adversarial, plus
per-family subsets (e.g. fin, lad, chart) and the legacy smoke15,
corrections, no-data, charts, salvaged, queries, all.
"""
import re
from pathlib import Path
from typing import Dict, List

from app.agent.eval.case_bank import BANK, T, TR
from app.agent.eval.models import ChartExpect, EvalCase, Fact, PairCheck
from app.agent.eval.sqlkit import CUR, grand_final, leaders, per_season_wins, player_total, record

# Repo root: backend/app/agent/eval/cases.py -> up 4 levels.
REPO_ROOT = Path(__file__).resolve().parents[4]
EVAL_QUERIES_PATH = REPO_ROOT / "eval_queries.txt"


# ---------------------------------------------------------------------------
# 1. GATE — the M5 smoke15 cases with live ground truth.
# ---------------------------------------------------------------------------
GATE: List[EvalCase] = [
    EvalCase(
        id="single_01",
        queries=["How many games has Collingwood won this season?"],
        tags=["smoke", "smoke15", "single", "current_season"],
        source="m0_benchmark",
        description="Current-season team wins; 'this season' = max season in the DB.",
        expected_facts=["collingwood"],
        verification_sql=record(14, CUR),
        truth=[T("wins", alts=["wins_ha"])],
    ),
    EvalCase(
        id="single_02",
        queries=["Who won the Brownlow Medal in 2023?"],
        tags=["smoke", "smoke15", "single", "award"],
        source="m0_benchmark",
        description="Historical award fact.",
        # Lachie Neale won the 2023 Brownlow with 31 votes; Marcus Bontempelli
        # was runner-up on 29. The DB's brownlow_votes agree. (The M5 comment
        # here had it backwards and accepted either name: a false pass.)
        verification_sql=leaders("sum(coalesce(ps.brownlow_votes,0))", "2023", 1, alias="votes"),
        truth=[T("name", all_rows=True), T("votes")],
        notes="Neale 31 won; Bontempelli 29 was second. Naming Bontempelli as winner is wrong.",
    ),
    EvalCase(
        id="single_03",
        queries=["Show me a chart of Melbourne's wins per season since 2018"],
        tags=["smoke15", "single", "chart", "trend"],
        source="m0_benchmark",
        description="Wins-per-season trend; one line, one point per season, values = DB.",
        expected_facts=["melbourne"],
        verification_sql=per_season_wins({21: "Melbourne"}, 2018),
        chart=ChartExpect(
            types=["line", "bar", "area"],
            series=1,
            pairs=[PairCheck(key="season", value="value", min_frac=0.9)],
        ),
    ),
    EvalCase(
        id="single_04",
        queries=["What's Dustin Martin's career goals tally?"],
        tags=["smoke15", "single", "career_total"],
        source="m0_benchmark",
        description="Career aggregate for a retired player.",
        verification_sql=player_total("Dustin Martin", {"goals": "sum(coalesce(ps.goals,0))"}),
        truth=[T("goals")],
    ),
    EvalCase(
        id="single_05",
        queries=["What was the score in the 2024 grand final?"],
        tags=["smoke", "smoke15", "single", "match_result"],
        source="m0_benchmark",
        description="Exact score lookup.",
        verification_sql=grand_final("2024"),
        truth=[T("winner"), T("loser"), T("winner_score"), T("loser_score")],
    ),
    EvalCase(
        id="single_06",
        queries=["Show me a pie chart of scoring sources - goals vs behinds for Sydney in 2024"],
        tags=["smoke15", "single", "chart", "pie"],
        source="m0_benchmark",
        description="Pie with two DB-verifiable slices. Team behinds include rushed behinds "
        "(match level); player_stats behinds do not. Either total is accepted.",
        expected_facts=["sydney"],
        verification_sql=(
            "select (select sum(case when home_team_id=26 then home_q4_goals else away_q4_goals end) from matches "
            "where season=2024 and 26 in (home_team_id, away_team_id)) goals, "
            "(select sum(case when home_team_id=26 then home_q4_behinds else away_q4_behinds end) from matches "
            "where season=2024 and 26 in (home_team_id, away_team_id)) behinds, "
            "(select sum(coalesce(ps.goals,0)) from player_stats ps join matches m on m.id=ps.match_id "
            "where m.season=2024 and ps.team_id=26) ps_goals, "
            "(select sum(coalesce(ps.behinds,0)) from player_stats ps join matches m on m.id=ps.match_id "
            "where m.season=2024 and ps.team_id=26) ps_behinds"
        ),
        chart=ChartExpect(types=["pie", "bar"]),
        truth=[
            Fact(col="goals", alts=["ps_goals"], where=["chart", "text"]),
            Fact(col="behinds", alts=["ps_behinds"], where=["chart", "text"]),
        ],
    ),
    EvalCase(
        id="single_07",
        queries=["What's Carlton's win-loss record against Essendon since 1990?"],
        tags=["smoke", "smoke15", "single", "head_to_head"],
        source="m0_benchmark",
        description="Head-to-head record with a since-year filter.",
        verification_sql=(
            "select count(*) games, count(*) filter (where (home_team_id=13 and home_score>away_score) "
            "or (away_team_id=13 and away_score>home_score)) carlton_wins, count(*) filter (where "
            "(home_team_id=15 and home_score>away_score) or (away_team_id=15 and away_score>home_score)) essendon_wins "
            "from matches where season>=1990 and home_score is not null and "
            "((home_team_id=13 and away_team_id=15) or (home_team_id=15 and away_team_id=13))"
        ),
        truth=[T("carlton_wins"), T("essendon_wins")],
    ),
    EvalCase(
        id="pair_01",
        queries=[
            "Who kicked the most goals last round?",
            "No, I meant round 10 of the 2024 season, not last round.",
        ],
        tags=["smoke15", "pair", "correction"],
        source="m0_benchmark",
        description="Relative-time query then an explicit correction pinning round+season.",
        is_correction=True,
        verification_sql=leaders("sum(coalesce(ps.goals,0))", "2024", 1, "m.round = '10'"),
        truth=[T("value"), T("name", all_rows=True)],
    ),
    EvalCase(
        id="pair_02",
        queries=[
            "Show me Patrick Cripps's stats for 2023",
            "Sorry, I meant Marcus Bontempelli, not Cripps.",
        ],
        tags=["smoke15", "pair", "correction"],
        source="m0_benchmark",
        description="Player-swap correction; final answer must be Bontempelli's 2023 numbers.",
        is_correction=True,
        expected_facts=["bontempelli"],
        verification_sql=player_total(
            "Marcus Bontempelli",
            {"disposals": "sum(ps.disposals)", "avg_disposals": "round(avg(ps.disposals), 2)"},
            "2023",
            where="coalesce(ps.disposals, 0) > 0",
        ),
        truth=[TR("disposals", alts=["avg_disposals"])],
    ),
    EvalCase(
        id="pair_03",
        queries=[
            "What was the score in the 2023 grand final?",
            "Actually I meant the 2022 grand final, not 2023.",
        ],
        tags=["smoke", "smoke15", "pair", "correction"],
        source="m0_benchmark",
        description="Year-swap correction on an exact score lookup.",
        is_correction=True,
        verification_sql=grand_final("2022"),
        truth=[T("winner"), T("winner_score"), T("loser_score")],
    ),
    EvalCase(
        id="nodata_01",
        queries=["What were Nick Daicos's stats in 2015?"],
        tags=["smoke15", "nodata"],
        source="m0_benchmark",
        description="Player has no rows before his debut; response must explain why.",
        expects_no_data=True,
        expected_facts=["daicos"],
        expected_any=["covers", "debut", "first season", "didn't play", "did not play"],
        verification_sql=(
            "select min(m.season) first_season from matches m join player_stats ps on ps.match_id=m.id "
            "join players p on p.id=ps.player_id where p.name='Nick Daicos'"
        ),
    ),
    EvalCase(
        id="nodata_02",
        queries=["What was the score in the 2030 AFL grand final?"],
        tags=["smoke", "smoke15", "nodata"],
        source="m0_benchmark",
        description="Season out of range; response must name the covered range.",
        expects_no_data=True,
        verification_sql="select min(season) lo, max(season) hi from matches",
        truth=[T("hi", alts=["lo"])],
    ),
    EvalCase(
        id="salv_player_goals",
        queries=["How many goals did Charlie Curnow kick in 2024?"],
        tags=["smoke15", "single", "salvaged"],
        source="salvaged",
        description="Salvaged 'player_goals_season' case: player+season stat join.",
        expected_facts=["curnow"],
        verification_sql=player_total("Charlie Curnow", {"goals": "sum(coalesce(ps.goals,0))"}, "2024"),
        truth=[T("goals")],
    ),
    EvalCase(
        id="salv_top_disposals",
        queries=["Top 5 disposal getters in 2024"],
        tags=["smoke15", "single", "top_n", "salvaged"],
        source="salvaged",
        description="Top-N ranking; names AND totals must match (Tom Green's 770 is split by team-swapped rows).",
        verification_sql=leaders("sum(ps.disposals)", "2024", 5),
        truth=[T("name", all_rows=True)],
        pairs=[PairCheck(key="name", value="value", min_frac=0.8)],
    ),
    EvalCase(
        id="salv_chart_trend",
        queries=["Show Carlton's average score per season from 2015 to 2024"],
        tags=["smoke15", "chart", "trend", "salvaged"],
        source="salvaged",
        description="Season trend chart with DB-equal values.",
        expected_facts=["carlton"],
        verification_sql=(
            "select m.season, round(avg(case when m.home_team_id=13 then m.home_score else m.away_score end), 2) value "
            "from matches m where 13 in (m.home_team_id, m.away_team_id) and m.season between 2015 and 2024 "
            "group by m.season order by 1"
        ),
        chart=ChartExpect(
            types=["line", "bar", "area"],
            series=1,
            pairs=[PairCheck(key="season", value="value", tol=0.6, min_frac=0.9)],
        ),
    ),
]
# Back-compat alias for older imports.
SMOKE15 = GATE


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
# Families = id prefix of BANK cases (fin, lad, nick, ...).
def _family(case: EvalCase) -> str:
    return case.id.split("_")[0]


def truth_cases() -> List[EvalCase]:
    """Every case with ground truth or asserted behaviour (gate + bank)."""
    return [*GATE, *BANK]


def build_subsets() -> Dict[str, List[EvalCase]]:
    """Build the named subset -> cases mapping (parses eval_queries.txt lazily)."""
    full = truth_cases()
    parsed = parse_eval_queries()
    subsets: Dict[str, List[EvalCase]] = {
        # Fast gate: representative, one or two per family.
        "smoke": [c for c in full if "smoke" in c.tags],
        # The 1E gate: every ground-truth case, held-out included.
        "full": full,
        # For iterating on prompts/tools: never tune against held-out cases.
        "dev": [c for c in full if "heldout" not in c.tags],
        "heldout": [c for c in full if "heldout" in c.tags],
        "adversarial": [c for c in full if "adversarial" in c.tags],
        "charts": [c for c in full if c.expects_chart or c.chart is not None],
        "current-season": [c for c in full if "current_season" in c.tags],
        # Legacy subsets (M5 names).
        "smoke15": list(GATE),
        "corrections": [c for c in full if c.is_correction],
        "no-data": [c for c in full if c.expects_no_data or c.on_empty_truth == "expect_no_data"],
        "salvaged": list(SALVAGED),
        "queries": parsed,
    }
    for case in BANK:
        subsets.setdefault(f"fam:{_family(case)}", []).append(case)
    # "all": everything, without duplicate ids.
    seen = set()
    everything: List[EvalCase] = []
    for case in [*full, *SALVAGED, *parsed]:
        if case.id not in seen:
            seen.add(case.id)
            everything.append(case)
    subsets["all"] = everything
    return subsets


def get_subset(name: str) -> List[EvalCase]:
    """Return the cases for a named subset; raises ValueError on unknown name."""
    subsets = build_subsets()
    if name not in subsets:
        raise ValueError(f"Unknown subset '{name}'. Available: {', '.join(sorted(subsets))}")
    return subsets[name]


def get_case(case_id: str) -> EvalCase:
    """Return a single case by id from the union of all subsets."""
    for case in build_subsets()["all"]:
        if case.id == case_id:
            return case
    raise ValueError(f"Unknown case id '{case_id}'")
