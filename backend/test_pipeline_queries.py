"""
Pipeline Test Suite - 20 Diverse AFL Queries
Tests SQL generation, data retrieval, and result plausibility.
"""
import os
import sys
sys.path.insert(0, '.')

os.environ['DB_STRING'] = 'postgresql+psycopg://postgres.igdcvgxbglzhhfczznhw:Wbn56t7pq!ky@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres'

from sqlalchemy import create_engine, text
import pandas as pd
from datetime import datetime

engine = create_engine(os.environ['DB_STRING'])

# Define 20 test queries with expected characteristics
TEST_QUERIES = [
    # === PLAYER STATS ===
    {
        "id": 1,
        "query": "How many goals did Nick Daicos kick in 2024?",
        "sql": """
            SELECT SUM(ps.goals) as total_goals
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE p.name ILIKE '%Daicos%' AND p.name ILIKE '%Nick%'
            AND m.season = 2024
        """,
        "expected": "Single number, should be around 10-20 goals for a midfielder"
    },
    {
        "id": 2,
        "query": "Nick Daicos goals by round in 2024",
        "sql": """
            SELECT m.round, ps.goals, m.match_date
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE p.name ILIKE '%Daicos%' AND p.name ILIKE '%Nick%'
            AND m.season = 2024
            ORDER BY m.match_date
        """,
        "expected": "24+ rows (one per round plus finals), goals 0-3 per game typically"
    },
    {
        "id": 3,
        "query": "Top 10 goal kickers in 2024",
        "sql": """
            SELECT p.name, SUM(ps.goals) as total_goals
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE m.season = 2024
            GROUP BY p.id, p.name
            ORDER BY total_goals DESC NULLS LAST
            LIMIT 10
        """,
        "expected": "10 rows, top scorer should have 50-80 goals"
    },
    {
        "id": 4,
        "query": "Patrick Cripps average disposals in 2024",
        "sql": """
            SELECT AVG(ps.disposals) as avg_disposals
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE p.name ILIKE '%Cripps%' AND p.name ILIKE '%Patrick%'
            AND m.season = 2024
        """,
        "expected": "Single number, should be 25-35 for elite midfielder"
    },
    {
        "id": 5,
        "query": "Marcus Bontempelli career stats",
        "sql": """
            SELECT m.season,
                   COUNT(*) as games,
                   SUM(ps.goals) as total_goals,
                   SUM(ps.disposals) as total_disposals,
                   AVG(ps.disposals) as avg_disposals
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE p.name ILIKE '%Bontempelli%'
            GROUP BY m.season
            ORDER BY m.season
        """,
        "expected": "Multiple seasons (2015-2025), 20-25 games per season, avg disposals 25-30"
    },

    # === TEAM STATS ===
    {
        "id": 6,
        "query": "Collingwood wins in 2024",
        "sql": """
            SELECT COUNT(*) as wins
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'Collingwood' AND m.season = 2024
            AND (
                (m.home_team_id = t.id AND m.home_score > m.away_score)
                OR (m.away_team_id = t.id AND m.away_score > m.home_score)
            )
        """,
        "expected": "Single number, should be 10-18 wins for a finals team"
    },
    {
        "id": 7,
        "query": "Carlton vs Richmond head to head last 5 years",
        "sql": """
            SELECT m.season, m.round, m.match_date,
                   t1.name as home_team, m.home_score,
                   t2.name as away_team, m.away_score
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            WHERE ((t1.name = 'Carlton' AND t2.name = 'Richmond')
                OR (t1.name = 'Richmond' AND t2.name = 'Carlton'))
            AND m.season >= 2020
            ORDER BY m.match_date DESC
        """,
        "expected": "10-12 rows (2 games per year), scores 60-120 typically"
    },
    {
        "id": 8,
        "query": "Melbourne average score in 2024",
        "sql": """
            SELECT AVG(CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END) as avg_score
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'Melbourne' AND m.season = 2024
        """,
        "expected": "Single number, should be 70-100 points"
    },
    {
        "id": 9,
        "query": "Highest scoring game in 2024",
        "sql": """
            SELECT m.match_date, m.round,
                   t1.name as home_team, m.home_score,
                   t2.name as away_team, m.away_score,
                   (m.home_score + m.away_score) as total_score
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            WHERE m.season = 2024
            ORDER BY total_score DESC
            LIMIT 1
        """,
        "expected": "1 row, total score should be 200-280"
    },
    {
        "id": 10,
        "query": "2024 ladder (wins by team)",
        "sql": """
            SELECT t.name,
                   SUM(CASE
                       WHEN m.home_team_id = t.id AND m.home_score > m.away_score THEN 1
                       WHEN m.away_team_id = t.id AND m.away_score > m.home_score THEN 1
                       ELSE 0 END) as wins,
                   COUNT(*) as games
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE m.season = 2024 AND m.round NOT LIKE '%Final%'
            GROUP BY t.id, t.name
            ORDER BY wins DESC
        """,
        "expected": "18 rows (all teams), top teams 15-18 wins, bottom teams 2-6 wins"
    },

    # === HISTORICAL/COMPARISON ===
    {
        "id": 11,
        "query": "Grand Final winners since 2015",
        "sql": """
            SELECT m.season,
                   CASE WHEN m.home_score > m.away_score THEN t1.name ELSE t2.name END as winner,
                   m.home_score, m.away_score
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            WHERE m.round = 'Grand Final' AND m.season >= 2015
            ORDER BY m.season DESC
        """,
        "expected": "10 rows (2015-2024), various winners"
    },
    {
        "id": 12,
        "query": "Geelong total goals in 2023 season",
        "sql": """
            SELECT SUM(ps.goals) as total_goals
            FROM player_stats ps
            JOIN matches m ON ps.match_id = m.id
            JOIN teams t ON ps.team_id = t.id
            WHERE t.name = 'Geelong' AND m.season = 2023
        """,
        "expected": "Single number, should be 300-450 goals for a season (using player_stats.team_id)"
    },
    {
        "id": 13,
        "query": "Most games played all time",
        "sql": """
            SELECT p.name, COUNT(*) as games_played
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            GROUP BY p.id, p.name
            ORDER BY games_played DESC
            LIMIT 10
        """,
        "expected": "10 rows, top should have 350-400+ games"
    },
    {
        "id": 14,
        "query": "Sydney performance at home vs away 2024",
        "sql": """
            SELECT
                'Home' as venue,
                COUNT(*) as games,
                SUM(CASE WHEN m.home_score > m.away_score THEN 1 ELSE 0 END) as wins,
                AVG(m.home_score) as avg_score
            FROM matches m
            JOIN teams t ON m.home_team_id = t.id
            WHERE t.name = 'Sydney' AND m.season = 2024
            UNION ALL
            SELECT
                'Away' as venue,
                COUNT(*) as games,
                SUM(CASE WHEN m.away_score > m.home_score THEN 1 ELSE 0 END) as wins,
                AVG(m.away_score) as avg_score
            FROM matches m
            JOIN teams t ON m.away_team_id = t.id
            WHERE t.name = 'Sydney' AND m.season = 2024
        """,
        "expected": "2 rows, typically more wins at home"
    },
    {
        "id": 15,
        "query": "Brownlow votes leaders 2024",
        "sql": """
            SELECT p.name, SUM(ps.brownlow_votes) as total_votes
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE m.season = 2024 AND ps.brownlow_votes > 0
            GROUP BY p.id, p.name
            ORDER BY total_votes DESC
            LIMIT 10
        """,
        "expected": "10 rows, winner should have 25-35 votes"
    },

    # === SPECIFIC STATS ===
    {
        "id": 16,
        "query": "Players with 40+ disposals in a game 2024",
        "sql": """
            SELECT p.name, ps.disposals, m.round, m.match_date, t.name as opponent
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            JOIN teams t ON (
                CASE WHEN m.home_team_id = p.team_id
                THEN m.away_team_id ELSE m.home_team_id END = t.id
            )
            WHERE ps.disposals >= 40 AND m.season = 2024
            ORDER BY ps.disposals DESC
        """,
        "expected": "5-20 rows, disposals 40-50+"
    },
    {
        "id": 17,
        "query": "Adelaide scoring by quarter in 2024",
        "sql": """
            SELECT
                'Q1' as quarter,
                AVG(CASE WHEN m.home_team_id = t.id THEN m.home_q1_goals * 6 + m.home_q1_behinds
                         ELSE m.away_q1_goals * 6 + m.away_q1_behinds END) as avg_score
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'Adelaide' AND m.season = 2024
            UNION ALL
            SELECT 'Q2', AVG(CASE WHEN m.home_team_id = t.id
                THEN (m.home_q2_goals - m.home_q1_goals) * 6 + (m.home_q2_behinds - m.home_q1_behinds)
                ELSE (m.away_q2_goals - m.away_q1_goals) * 6 + (m.away_q2_behinds - m.away_q1_behinds) END)
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'Adelaide' AND m.season = 2024
        """,
        "expected": "2-4 rows, avg quarter score 15-25 points"
    },
    {
        "id": 18,
        "query": "West Coast worst losing margin 2024",
        "sql": """
            SELECT m.match_date, m.round,
                   t1.name as home_team, m.home_score,
                   t2.name as away_team, m.away_score,
                   ABS(m.home_score - m.away_score) as margin
            FROM matches m
            JOIN teams t1 ON m.home_team_id = t1.id
            JOIN teams t2 ON m.away_team_id = t2.id
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'West Coast' AND m.season = 2024
            AND (
                (m.home_team_id = t.id AND m.home_score < m.away_score)
                OR (m.away_team_id = t.id AND m.away_score < m.home_score)
            )
            ORDER BY margin DESC
            LIMIT 5
        """,
        "expected": "5 rows, margins could be 50-100+ for struggling team"
    },
    {
        "id": 19,
        "query": "Most tackles in a game 2024",
        "sql": """
            SELECT p.name, ps.tackles, m.round, m.match_date
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            WHERE m.season = 2024 AND ps.tackles IS NOT NULL
            ORDER BY ps.tackles DESC
            LIMIT 10
        """,
        "expected": "10 rows, top should have 12-18 tackles"
    },
    {
        "id": 20,
        "query": "Hawthorn wins by round in 2024",
        "sql": """
            SELECT m.round,
                   CASE
                       WHEN m.home_team_id = t.id AND m.home_score > m.away_score THEN 'Win'
                       WHEN m.away_team_id = t.id AND m.away_score > m.home_score THEN 'Win'
                       WHEN m.home_score = m.away_score THEN 'Draw'
                       ELSE 'Loss'
                   END as result,
                   CASE WHEN m.home_team_id = t.id THEN m.home_score ELSE m.away_score END as team_score,
                   CASE WHEN m.home_team_id = t.id THEN m.away_score ELSE m.home_score END as opponent_score
            FROM matches m
            JOIN teams t ON (m.home_team_id = t.id OR m.away_team_id = t.id)
            WHERE t.name = 'Hawthorn' AND m.season = 2024
            ORDER BY m.match_date
        """,
        "expected": "24+ rows, mix of wins and losses"
    },
]


def run_test(test):
    """Run a single test query and return results."""
    try:
        with engine.connect() as conn:
            df = pd.read_sql(text(test['sql']), conn)
            return {
                'id': test['id'],
                'query': test['query'],
                'expected': test['expected'],
                'row_count': len(df),
                'columns': list(df.columns),
                'data': df.to_dict('records')[:10],  # First 10 rows
                'full_data': df if len(df) <= 30 else df.head(30),
                'status': 'SUCCESS',
                'error': None
            }
    except Exception as e:
        return {
            'id': test['id'],
            'query': test['query'],
            'expected': test['expected'],
            'status': 'ERROR',
            'error': str(e)
        }


def analyze_result(result):
    """Analyze if result is plausible."""
    issues = []

    if result['status'] == 'ERROR':
        return f"❌ ERROR: {result['error']}"

    data = result['data']
    row_count = result['row_count']
    query_id = result['id']

    # Specific validations based on query type
    if query_id == 1:  # Nick Daicos goals 2024
        if row_count == 1 and data:
            goals = data[0].get('total_goals', 0)
            if goals is None or goals < 5 or goals > 50:
                issues.append(f"Goals ({goals}) seems off for a midfielder")

    elif query_id == 2:  # Nick Daicos by round
        if row_count < 20:
            issues.append(f"Only {row_count} rows, expected 24+ rounds")

    elif query_id == 3:  # Top goal kickers
        if row_count != 10:
            issues.append(f"Expected 10 rows, got {row_count}")
        top_goals = data[0].get('total_goals') if data else None
        if top_goals is not None and top_goals < 40:
            issues.append(f"Top scorer only has {top_goals} goals, seems low")

    elif query_id == 4:  # Cripps avg disposals
        if data and data[0].get('avg_disposals'):
            avg = float(data[0]['avg_disposals'])
            if avg < 20 or avg > 40:
                issues.append(f"Avg disposals ({avg:.1f}) seems off")

    elif query_id == 6:  # Collingwood wins
        if data and data[0].get('wins'):
            wins = data[0]['wins']
            if wins < 5 or wins > 22:
                issues.append(f"Wins ({wins}) seems implausible")

    elif query_id == 10:  # Ladder
        if row_count != 18:
            issues.append(f"Expected 18 teams, got {row_count}")

    elif query_id == 11:  # Grand finals
        if row_count < 9:
            issues.append(f"Expected 10 grand finals since 2015, got {row_count}")

    elif query_id == 13:  # Most games all time
        top_games = data[0].get('games_played') if data else None
        if top_games is not None and top_games < 300:
            issues.append(f"Top games ({top_games}) seems low for all-time record")

    elif query_id == 15:  # Brownlow votes
        top_votes = data[0].get('total_votes') if data else None
        if top_votes is None or top_votes == 0:
            issues.append("No Brownlow votes found - data might be missing")

    if not issues:
        return "✅ PLAUSIBLE"
    else:
        return "⚠️ ISSUES: " + "; ".join(issues)


def main():
    print("=" * 80)
    print("AFL Pipeline Test Suite - 20 Queries")
    print("=" * 80)
    print()

    results = []
    for test in TEST_QUERIES:
        print(f"Running Query {test['id']}: {test['query'][:50]}...")
        result = run_test(test)
        result['analysis'] = analyze_result(result)
        results.append(result)

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    for r in results:
        print(f"\n--- Query {r['id']}: {r['query'][:60]}{'...' if len(r['query']) > 60 else ''}")
        print(f"Expected: {r['expected']}")

        if r['status'] == 'SUCCESS':
            print(f"Rows: {r['row_count']} | Columns: {r['columns']}")
            if r['data']:
                print(f"Sample data: {r['data'][0]}")
        else:
            print(f"Error: {r['error']}")

        print(f"Analysis: {r['analysis']}")

    # Count issues
    successes = sum(1 for r in results if '✅' in r['analysis'])
    issues = sum(1 for r in results if '⚠️' in r['analysis'])
    errors = sum(1 for r in results if '❌' in r['analysis'])

    print("\n" + "=" * 80)
    print(f"FINAL SCORE: {successes}/20 Plausible | {issues} with Issues | {errors} Errors")
    print("=" * 80)

    return results


if __name__ == '__main__':
    results = main()
