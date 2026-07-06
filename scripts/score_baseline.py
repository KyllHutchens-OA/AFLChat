"""
Milestone 0 — Score the raw benchmark_chat.py output against ground truth.

For each of the 12 fixed test cases in benchmark_chat.py, this script embeds
the DB spot-check query used to establish ground truth (run manually against
the live Railway Postgres via psycopg2, DB_STRING from backend/.env) plus the
resulting 0/0.5/1 scores on up to four axes:

  numeric_correctness  - does a key number/fact in the response match the DB?
  chart_present_valid  - if a chart was requested, is the spec present AND
                         structurally valid (right chart type, populated data)?
  no_data_quality      - for genuinely-no-data queries, does the response
                         explain WHY (not just a generic fallback)?
  correction_effect    - for two-turn pairs, did turn 2 actually produce a
                         materially different, corrected answer?

Axes that don't apply to a given case/turn are left out of that turn's
`scores` dict entirely (not scored as 0).

This is intentionally a hand-verified scoring pass, not a generic NLG-to-SQL
grader: the ground truth values and verification SQL are recorded inline in
`GROUND_TRUTH` below so the baseline is fully auditable and reproducible.

Usage:
    backend/venv/bin/python scripts/score_baseline.py \
        scripts/benchmark_results/baseline_2026-07-07_raw.json
"""
import json
import sys
import os
from datetime import datetime


# ---------------------------------------------------------------------------
# Ground truth + scores, established by direct psycopg2 queries against the
# live DB (DB_STRING from backend/.env) on 2026-07-07. See the verification
# SQL in each entry's "verification_sql" field to reproduce.
# ---------------------------------------------------------------------------
GROUND_TRUTH = {
    "single_01": {
        "turns": [{
            "ground_truth": "Collingwood: 17 wins from 25 games in season 2025 "
                             "(matches.home_team_id/away_team_id=14). Note: the "
                             "matches table already has a FULLY completed season "
                             "2026 (207/207 games with scores) even though the "
                             "system clock reads 2026-07-07 — the agent's notion "
                             "of 'this season' resolved to 2025, not 2026.",
            "verification_sql": "select count(*) from matches where "
                                 "(home_team_id=14 or away_team_id=14) and season=2025 "
                                 "and ((home_team_id=14 and home_score>away_score) or "
                                 "(away_team_id=14 and away_score>home_score))",
            "scores": {"numeric_correctness": 1},
            "notes": "Response '17 wins' matches DB exactly for season=2025. "
                     "Flagging season-resolution logic as a surprise for later "
                     "milestones, not a numeric error: given the DB already has "
                     "a full season 2026, 'this season' should probably resolve "
                     "to 2026, but it didn't. Score reflects that the number "
                     "returned is internally consistent with SOME season, and "
                     "matches that season's data exactly.",
        }],
    },
    "single_02": {
        "turns": [{
            "ground_truth": "Real-world 2023 Brownlow Medal winner: Marcus "
                             "Bontempelli, 29 votes (matches response). BUT the "
                             "DB's player_stats.brownlow_votes column aggregated "
                             "by season 2023 gives Lachie Neale 31 votes as the "
                             "top scorer, not Bontempelli (29). The response's "
                             "minimal 'thinking' trace (no SQL-generation step) "
                             "shows this answer came from a hardcoded fast-path "
                             "fact, not a DB query — which is why it's correct "
                             "despite the underlying brownlow_votes column "
                             "apparently having a data-quality issue.",
            "verification_sql": "select p.name, sum(ps.brownlow_votes) from "
                                 "player_stats ps join players p on p.id=ps.player_id "
                                 "join matches m on m.id=ps.match_id where m.season=2023 "
                                 "group by p.name order by 2 desc limit 5",
            "scores": {"numeric_correctness": 1},
            "notes": "Correct against real-world ground truth via hardcoded "
                     "fast-path fact. Flagging as a DB data-quality finding: "
                     "brownlow_votes aggregation disagrees with the true medal "
                     "result for 2023 (Neale 31 > Bontempelli 29 in-DB), so any "
                     "future feature that answers Brownlow questions FROM the DB "
                     "rather than a hardcoded fact would currently get this wrong.",
        }],
    },
    "single_03": {
        "turns": [{
            "ground_truth": "Melbourne wins by season, matches.home/away_team_id=21: "
                             "2018:16, 2019:5, 2020:9, 2021:20, 2022:16, 2023:16, "
                             "2024:11, 2025:7, 2026:10.",
            "verification_sql": "select season, count(*) filter (where "
                                 "(home_team_id=21 and home_score>away_score) or "
                                 "(away_team_id=21 and away_score>home_score)) "
                                 "from matches where (home_team_id=21 or away_team_id=21) "
                                 "and season>=2018 group by season order by season",
            "scores": {"numeric_correctness": 1, "chart_present_valid": 1},
            "notes": "All 9 season values in the emitted line-chart spec match "
                     "the DB exactly. Chart spec is structurally valid (chartType, "
                     "data, xAxis/yAxis all present). Minor cosmetic bug (not "
                     "scored against 'valid'): chart title says 'Melbourne Wins "
                     "(2018-2025)' but the data series actually extends to 2026 — "
                     "title/data range are out of sync.",
        }],
    },
    "single_04": {
        "turns": [{
            "ground_truth": "Dustin Martin career goals (sum of player_stats.goals): 338.",
            "verification_sql": "select sum(goals) from player_stats ps join players p "
                                 "on p.id=ps.player_id where p.name ilike '%dustin martin%'",
            "scores": {"numeric_correctness": 1},
            "notes": "Exact match.",
        }],
    },
    "single_05": {
        "turns": [{
            "ground_truth": "2024 Grand Final: home=Sydney(26) 60, away=Brisbane "
                             "Lions(12) 120 -> Brisbane won 120-60.",
            "verification_sql": "select home_team_id, away_team_id, home_score, "
                                 "away_score from matches where season=2024 and "
                                 "round='Grand Final'",
            "scores": {"numeric_correctness": 1},
            "notes": "Exact match on winner, score, and margin.",
        }],
    },
    "single_06": {
        "turns": [{
            "ground_truth": "Sydney 2024 season totals from player_stats "
                             "(team_id=26, season=2024): goals=366, behinds=239. "
                             "The emitted pie chart shows Goals=871, Behinds=742 "
                             "— neither number is reproducible from any "
                             "team/season/2-season combination checked (single "
                             "season, both-teams-in-Sydney's-games, 2023+2024 "
                             "combined, all-time, team_stats.score) — it does not "
                             "match any traceable DB aggregate found during "
                             "verification.",
            "verification_sql": "select sum(ps.goals), sum(ps.behinds) from "
                                 "player_stats ps join matches m on m.id=ps.match_id "
                                 "where ps.team_id=26 and m.season=2024",
            "scores": {"numeric_correctness": 0, "chart_present_valid": 0.5},
            "notes": "Chart is structurally present/valid (correct pie shape, "
                     "two labeled slices, renders), but the two numbers in it "
                     "appear to be fabricated or computed from the wrong scope — "
                     "could not trace 871/742 to Sydney, any other team, any "
                     "season combination, or team_stats.score in the DB. This is "
                     "the single highest-severity finding in the baseline: a "
                     "confidently-presented, wrong, unverifiable chart.",
        }],
    },
    "single_07": {
        "turns": [{
            "ground_truth": "Carlton(13) vs Essendon(15) head-to-head since 1990: "
                             "69 games total, Carlton 31 wins, Essendon 34 wins "
                             "(4 draws).",
            "verification_sql": "select count(*), count(*) filter (where "
                                 "(home_team_id=13 and home_score>away_score) or "
                                 "(away_team_id=13 and away_score>home_score)), "
                                 "count(*) filter (where (home_team_id=15 and "
                                 "home_score>away_score) or (away_team_id=15 and "
                                 "away_score>home_score)) from matches where "
                                 "season>=1990 and ((home_team_id=13 and "
                                 "away_team_id=15) or (home_team_id=15 and "
                                 "away_team_id=13))",
            "scores": {"numeric_correctness": 0},
            "notes": "Response was 'Carlton finished the 1990 season with 10 "
                     "wins, 10 losses from 20 games' — this is Carlton's overall "
                     "1990 season record (all opponents), completely ignoring "
                     "both the Essendon-specific filter and the 'since' range. "
                     "It answered a different, easier question. Likely a "
                     "fast-path regex matching a generic 'team season record' "
                     "pattern instead of a head-to-head pattern.",
        }],
    },
    "pair_01": {
        "turns": [
            {
                "ground_truth": "Ambiguous but answerable: 'last round' could "
                                 "resolve to the most recent completed round in "
                                 "whichever season the app treats as current. "
                                 "The agent returned 0 SQL results and a generic "
                                 "fallback instead of resolving the relative "
                                 "time reference at all.",
                "verification_sql": "n/a (entity-resolution failure, not a DB fact)",
                "scores": {"numeric_correctness": 0},
                "notes": "Genuine gap: 'last round' / relative-time phrasing "
                         "isn't resolved to a concrete round+season, so the SQL "
                         "generation step produced a query with 0 results and "
                         "the agent fell back to the generic no-answer template "
                         "(same wording as the nodata_* cases — see no_data "
                         "quality notes below).",
            },
            {
                "ground_truth": "Charlie Cameron, round 10 2024: 5 goals.",
                "verification_sql": "select p.name, ps.goals from player_stats ps "
                                     "join players p on p.id=ps.player_id join "
                                     "matches m on m.id=ps.match_id where p.name "
                                     "ilike '%charlie cameron%' and m.season=2024 "
                                     "and m.round='10'",
                "scores": {"numeric_correctness": 1, "correction_effect": 1},
                "notes": "Correction ('round 10 of the 2024 season, not last "
                         "round') produced a concrete, DB-correct answer (5 "
                         "goals) after turn 1 failed outright — a real change in "
                         "outcome. Minor quality gap: response text ('...in "
                         "2024') doesn't explicitly confirm it scoped to round "
                         "10 specifically, only that the number happens to match "
                         "the round-10 figure.",
            },
        ],
    },
    "pair_02": {
        "turns": [
            {
                "ground_truth": "Patrick Cripps 2023: 24 games, 596 disposals "
                                 "(226 kicks/370 handballs), 51 marks, 130 "
                                 "tackles, 9 goals, 14 behinds, 3 hitouts, 146 "
                                 "clearances, 77 inside 50s.",
                "verification_sql": "select count(*), sum(disposals), sum(kicks), "
                                     "sum(handballs), sum(marks), sum(tackles), "
                                     "sum(goals), sum(behinds), sum(hitouts), "
                                     "sum(clearances), sum(inside_50s) from "
                                     "player_stats ps join players p on "
                                     "p.id=ps.player_id join matches m on "
                                     "m.id=ps.match_id where p.name ilike "
                                     "'%patrick cripps%' and m.season=2023",
                "scores": {"numeric_correctness": 1},
                "notes": "Every column in the returned table matches the DB "
                         "exactly.",
            },
            {
                "ground_truth": "Marcus Bontempelli 2023: 23 games, 636 "
                                 "disposals (370 kicks/266 handballs), 101 marks, "
                                 "172 tackles, 19 goals, 14 behinds, 1 hitout, "
                                 "175 clearances, 131 inside 50s.",
                "verification_sql": "select count(*), sum(disposals), sum(kicks), "
                                     "sum(handballs), sum(marks), sum(tackles), "
                                     "sum(goals), sum(behinds), sum(hitouts), "
                                     "sum(clearances), sum(inside_50s) from "
                                     "player_stats ps join players p on "
                                     "p.id=ps.player_id join matches m on "
                                     "m.id=ps.match_id where p.name ilike "
                                     "'%bontempelli%' and m.season=2023",
                "scores": {"numeric_correctness": 1, "correction_effect": 1},
                "notes": "Correction ('I meant Bontempelli, not Cripps') "
                         "produced a completely different player's exact, "
                         "DB-correct totals — the cleanest correction result in "
                         "the baseline.",
            },
        ],
    },
    "pair_03": {
        "turns": [
            {
                "ground_truth": "2023 Grand Final: home=Collingwood(14) 90, "
                                 "away=Brisbane Lions(12) 86 -> Collingwood won "
                                 "90-86.",
                "verification_sql": "select home_team_id, away_team_id, "
                                     "home_score, away_score from matches where "
                                     "season=2023 and round='Grand Final'",
                "scores": {"numeric_correctness": 1},
                "notes": "Exact match.",
            },
            {
                "ground_truth": "2022 Grand Final: home=Geelong(17) 133, "
                                 "away=Sydney(26) 52, venue=MCG -> Geelong won "
                                 "133-52 (margin 81).",
                "verification_sql": "select home_team_id, away_team_id, "
                                     "home_score, away_score, venue from matches "
                                     "where season=2022 and round='Grand Final'",
                "scores": {"numeric_correctness": 1, "correction_effect": 1},
                "notes": "Exact match on teams/score/margin/venue after the "
                         "correction. Formatting bug spotted (not scored): "
                         "response reads '...at MCG (Round Grand Final)' — the "
                         "raw round value 'Grand Final' is being interpolated "
                         "into a 'Round {round}' template meant for numbered "
                         "rounds, producing the malformed phrase 'Round Grand "
                         "Final'.",
            },
        ],
    },
    "nodata_01": {
        "turns": [{
            "ground_truth": "Nick Daicos has zero player_stats rows before "
                             "season 2022 (his earliest season in this DB); "
                             "2015 genuinely has no rows for him.",
            "verification_sql": "select min(m.season) from matches m join "
                                 "player_stats ps on ps.match_id=m.id join players "
                                 "p on p.id=ps.player_id where p.name='Nick Daicos'",
            "scores": {"no_data_quality": 0},
            "notes": "Correctly returns no data (0 SQL results per the "
                     "'thinking' trace), but the message is the generic fallback "
                     "template ('I had trouble finding an answer... Try "
                     "rephrasing...') with no mention of why — doesn't say "
                     "anything about Daicos's debut season or the data's actual "
                     "coverage for him. A quality response would explain the "
                     "player has no recorded stats for that year.",
        }],
    },
    "nodata_02": {
        "turns": [{
            "ground_truth": "matches table has no season beyond 2026 "
                             "(max(season)=2026); 2030 is out of range.",
            "verification_sql": "select max(season) from matches",
            "scores": {"no_data_quality": 0},
            "notes": "Same generic fallback template as nodata_01 and pair_01 "
                     "turn 1 — word-for-word identical text in all three cases. "
                     "Doesn't explain that the DB only covers 1990-2026, even "
                     "though the response elsewhere in the SAME message states "
                     "'I have AFL data from 1990 to 2026' — the season-range "
                     "fact is present in the boilerplate but never connected to "
                     "the specific out-of-range year (2030) the user asked "
                     "about.",
        }],
    },
}


def main():
    if len(sys.argv) != 2:
        print("Usage: score_baseline.py <raw_results.json>")
        sys.exit(1)

    raw_path = sys.argv[1]
    with open(raw_path) as f:
        raw = json.load(f)

    scored = {
        "meta": dict(raw["meta"], scored_at=datetime.now().isoformat()),
        "cases": [],
    }

    axis_totals = {
        "numeric_correctness": [],
        "chart_present_valid": [],
        "no_data_quality": [],
        "correction_effect": [],
    }

    for case in raw["cases"]:
        gt_case = GROUND_TRUTH.get(case["id"], {"turns": [{} for _ in case["turns"]]})
        scored_case = {"id": case["id"], "category": case["category"], "turns": []}
        for i, turn in enumerate(case["turns"]):
            gt_turn = gt_case["turns"][i] if i < len(gt_case["turns"]) else {}
            scores = gt_turn.get("scores", {})
            for axis, val in scores.items():
                axis_totals[axis].append(val)
            scored_turn = dict(turn)
            scored_turn["ground_truth"] = gt_turn.get("ground_truth")
            scored_turn["verification_sql"] = gt_turn.get("verification_sql")
            scored_turn["scores"] = scores
            scored_turn["notes"] = gt_turn.get("notes")
            scored_case["turns"].append(scored_turn)
        scored["cases"].append(scored_case)

    def avg(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    all_latencies = [t["latency_ms"] for c in raw["cases"] for t in c["turns"]]
    timeouts = [(c["id"], i) for c in raw["cases"] for i, t in enumerate(c["turns"]) if t["timed_out"]]
    missing = [(c["id"], i, t["missing_events"]) for c in raw["cases"] for i, t in enumerate(c["turns"]) if t["missing_events"]]

    scored["summary"] = {
        "num_cases": len(raw["cases"]),
        "num_turns": len(all_latencies),
        "axis_averages": {axis: avg(vals) for axis, vals in axis_totals.items()},
        "axis_counts": {axis: {"n": len(vals), "sum": sum(vals)} for axis, vals in axis_totals.items()},
        "latency_ms": {
            "min": min(all_latencies),
            "max": max(all_latencies),
            "avg": round(sum(all_latencies) / len(all_latencies), 1),
        },
        "timeouts": timeouts,
        "missing_events": missing,
    }

    out_path = raw_path.replace("_raw.json", ".json")
    with open(out_path, "w") as f:
        json.dump(scored, f, indent=2, default=str)

    print(f"Scored baseline written to {out_path}")
    print(json.dumps(scored["summary"], indent=2, default=str))


if __name__ == "__main__":
    main()
