"""
Ingest missing 2024 player statistics from CSV files.

Uses DatabaseTool for database access.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from app.agent.tools import DatabaseTool
import logging

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to player CSV files
PLAYERS_DIR = Path("/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players")

def get_team_id(team_name: str) -> int:
    """Get team ID from database."""
    # Map common team name variations
    team_mapping = {
        "Greater Western Sydney": "Greater Western Sydney",
        "GWS": "Greater Western Sydney",
        "Western Bulldogs": "Western Bulldogs",
        "Bulldogs": "Western Bulldogs",
        "Brisbane Lions": "Brisbane Lions",
        "Brisbane": "Brisbane Lions",
        "North Melbourne": "North Melbourne",
        "Kangaroos": "North Melbourne",
        "Port Adelaide": "Port Adelaide",
        "West Coast": "West Coast",
        "Gold Coast": "Gold Coast"
    }

    search_name = team_mapping.get(team_name, team_name)

    result = DatabaseTool.query_database(
        f"SELECT id FROM teams WHERE name ILIKE '{search_name}' LIMIT 1"
    )

    if result["success"] and len(result["data"]) > 0:
        return result["data"].iloc[0]["id"]

    logger.warning(f"Team not found: {team_name} (searched: {search_name})")
    return None

def get_player_id(player_name: str) -> int:
    """Get player ID from database."""
    result = DatabaseTool.query_database(
        f"SELECT id FROM players WHERE name ILIKE '{player_name}' LIMIT 1"
    )

    if result["success"] and len(result["data"]) > 0:
        return result["data"].iloc[0]["id"]

    return None

def get_match_id(team_id: int, opponent: str, season: int, round_num: str) -> int:
    """Get match ID by matching team, opponent, season, and round."""
    # Get opponent team ID
    opponent_id = get_team_id(opponent)
    if not opponent_id:
        return None

    # Try exact round first
    result = DatabaseTool.query_database(f"""
        SELECT id FROM matches
        WHERE season = {season}
        AND round = '{round_num}'
        AND ((home_team_id = {team_id} AND away_team_id = {opponent_id})
             OR (away_team_id = {team_id} AND home_team_id = {opponent_id}))
        LIMIT 1
    """)

    if result["success"] and len(result["data"]) > 0:
        return result["data"].iloc[0]["id"]

    # If no match, try round - 1 (CSV rounds are 1 higher due to Round 0 "Opening Round")
    try:
        adjusted_round = str(int(round_num) - 1)
        result = DatabaseTool.query_database(f"""
            SELECT id FROM matches
            WHERE season = {season}
            AND round = '{adjusted_round}'
            AND ((home_team_id = {team_id} AND away_team_id = {opponent_id})
                 OR (away_team_id = {team_id} AND home_team_id = {opponent_id}))
            LIMIT 1
        """)

        if result["success"] and len(result["data"]) > 0:
            return result["data"].iloc[0]["id"]
    except (ValueError, TypeError):
        pass  # Non-numeric round (e.g., "EF", "GF")

    return None

def safe_value(val):
    """Convert value to SQL-safe string."""
    if pd.isna(val) or val == '' or val is None:
        return 'NULL'
    return str(int(float(val)))

def ingest_2024_data():
    """Ingest all 2024 player statistics from CSV files."""

    # Find all performance CSV files
    csv_files = list(PLAYERS_DIR.glob("*_performance_details.csv"))
    logger.info(f"Found {len(csv_files)} player CSV files")

    total_stats = 0
    total_players = 0
    skipped_no_match = 0
    skipped_no_player = 0

    for idx, csv_file in enumerate(csv_files):
        try:
            # Read CSV
            df = pd.read_csv(csv_file)

            # Filter for 2024 season only
            df_2024 = df[df['year'] == 2024]

            if len(df_2024) == 0:
                continue  # No 2024 data for this player

            # Extract player name from filename
            filename_parts = csv_file.stem.split('_')
            if len(filename_parts) < 3:
                logger.warning(f"Invalid filename format: {csv_file.name}")
                continue

            last_name = filename_parts[0].capitalize()
            first_name = filename_parts[1].capitalize()
            player_name = f"{first_name} {last_name}"

            # Check if player exists
            player_id = get_player_id(player_name)
            if not player_id:
                skipped_no_player += 1
                continue

            total_players += 1

            # Insert player stats for each game
            for _, row in df_2024.iterrows():
                # Get team ID
                team_name = row['team']
                team_id = get_team_id(team_name)
                if not team_id:
                    continue

                # Get match ID
                match_id = get_match_id(
                    team_id,
                    row['opponent'],
                    2024,
                    row['round']
                )

                if not match_id:
                    skipped_no_match += 1
                    continue

                # Insert player stats
                insert_sql = f"""
                    INSERT INTO player_stats (
                        match_id, player_id, disposals, kicks, handballs,
                        marks, tackles, goals, behinds, hitouts, clearances,
                        inside_50s, rebound_50s, contested_possessions,
                        uncontested_possessions, contested_marks, marks_inside_50,
                        one_percenters, clangers, free_kicks_for, free_kicks_against,
                        brownlow_votes, time_on_ground_pct
                    ) VALUES (
                        {match_id}, {player_id},
                        {safe_value(row.get('disposals'))},
                        {safe_value(row.get('kicks'))},
                        {safe_value(row.get('handballs'))},
                        {safe_value(row.get('marks'))},
                        {safe_value(row.get('tackles'))},
                        {safe_value(row.get('goals'))},
                        {safe_value(row.get('behinds'))},
                        {safe_value(row.get('hit_outs'))},
                        {safe_value(row.get('clearances'))},
                        {safe_value(row.get('inside_50s'))},
                        {safe_value(row.get('rebound_50s'))},
                        {safe_value(row.get('contested_possessions'))},
                        {safe_value(row.get('uncontested_possessions'))},
                        {safe_value(row.get('contested_marks'))},
                        {safe_value(row.get('marks_inside_50'))},
                        {safe_value(row.get('one_percenters'))},
                        {safe_value(row.get('clangers'))},
                        {safe_value(row.get('free_kicks_for'))},
                        {safe_value(row.get('free_kicks_against'))},
                        {safe_value(row.get('brownlow_votes'))},
                        {safe_value(row.get('percentage_of_game_played'))}
                    )
                    ON CONFLICT (match_id, player_id) DO NOTHING
                """

                result = DatabaseTool.query_database(insert_sql)
                if result["success"]:
                    total_stats += 1

            if total_players % 100 == 0:
                logger.info(f"Processed {total_players} players, {total_stats} stats")

        except Exception as e:
            logger.error(f"Error processing {csv_file.name}: {e}")
            continue

    logger.info("=" * 80)
    logger.info(f"✅ Ingestion complete!")
    logger.info(f"   Players with 2024 data: {total_players}")
    logger.info(f"   Total stats ingested: {total_stats}")
    logger.info(f"   Skipped (no matching match): {skipped_no_match}")
    logger.info(f"   Skipped (player not in DB): {skipped_no_player}")
    logger.info("=" * 80)

if __name__ == "__main__":
    logger.info("Starting 2024 player data ingestion...")
    ingest_2024_data()
