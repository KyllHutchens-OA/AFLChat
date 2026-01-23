"""
FINAL 2024 Player Data Ingestion Script

Uses SQLAlchemy directly with proper commits to ensure data is persisted.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from sqlalchemy import text
import logging
from app.data.database import Session

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Path to player CSV files
PLAYERS_DIR = Path("/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players")

# Team name mappings
TEAM_MAPPING = {
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

# Cache for team IDs
TEAM_CACHE = {}
PLAYER_CACHE = {}

def get_team_id(session, team_name: str) -> int:
    """Get team ID from database with caching."""
    if team_name in TEAM_CACHE:
        return TEAM_CACHE[team_name]

    search_name = TEAM_MAPPING.get(team_name, team_name)

    result = session.execute(
        text("SELECT id FROM teams WHERE name ILIKE :name LIMIT 1"),
        {"name": search_name}
    )
    row = result.fetchone()

    if row:
        TEAM_CACHE[team_name] = row[0]
        return row[0]

    logger.warning(f"Team not found: {team_name}")
    return None

def get_player_id(session, player_name: str) -> int:
    """Get player ID from database with caching."""
    if player_name in PLAYER_CACHE:
        return PLAYER_CACHE[player_name]

    result = session.execute(
        text("SELECT id FROM players WHERE name ILIKE :name LIMIT 1"),
        {"name": player_name}
    )
    row = result.fetchone()

    if row:
        PLAYER_CACHE[player_name] = row[0]
        return row[0]

    return None

def get_match_id(session, team_id: int, opponent_id: int, season: int, round_num: str) -> int:
    """Get match ID with round offset handling."""
    # Try exact round first
    result = session.execute(
        text("""
            SELECT id FROM matches
            WHERE season = :season
            AND round = :round
            AND ((home_team_id = :team_id AND away_team_id = :opponent_id)
                 OR (away_team_id = :team_id AND home_team_id = :opponent_id))
            LIMIT 1
        """),
        {"season": season, "round": round_num, "team_id": team_id, "opponent_id": opponent_id}
    )
    row = result.fetchone()
    if row:
        return row[0]

    # Try round - 1 (CSV rounds are 1 higher due to Round 0 "Opening Round")
    try:
        adjusted_round = str(int(round_num) - 1)
        result = session.execute(
            text("""
                SELECT id FROM matches
                WHERE season = :season
                AND round = :round
                AND ((home_team_id = :team_id AND away_team_id = :opponent_id)
                     OR (away_team_id = :team_id AND home_team_id = :opponent_id))
                LIMIT 1
            """),
            {"season": season, "round": adjusted_round, "team_id": team_id, "opponent_id": opponent_id}
        )
        row = result.fetchone()
        if row:
            return row[0]
    except (ValueError, TypeError):
        pass  # Non-numeric round (e.g., "EF", "GF")

    return None

def safe_int(val):
    """Convert value to int or None."""
    if pd.isna(val) or val == '' or val is None:
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None

def ingest_2024_data():
    """Ingest all 2024 player statistics."""
    csv_files = list(PLAYERS_DIR.glob("*_performance_details.csv"))
    logger.info(f"Found {len(csv_files)} player CSV files")

    total_stats = 0
    total_players = 0
    skipped_no_match = 0
    skipped_no_player = 0
    errors = 0

    session = Session()
    try:
        for idx, csv_file in enumerate(csv_files):
            try:
                # Read CSV
                df = pd.read_csv(csv_file)

                # Filter for 2024 season only
                df_2024 = df[df['year'] == 2024]

                if len(df_2024) == 0:
                    continue

                # Extract player name
                filename_parts = csv_file.stem.split('_')
                if len(filename_parts) < 3:
                    continue

                last_name = filename_parts[0].capitalize()
                first_name = filename_parts[1].capitalize()
                player_name = f"{first_name} {last_name}"

                # Get player ID
                player_id = get_player_id(session, player_name)
                if not player_id:
                    skipped_no_player += 1
                    continue

                total_players += 1

                # Process each game
                for _, row in df_2024.iterrows():
                    try:
                        # Get team and opponent IDs
                        team_id = get_team_id(session, row['team'])
                        if not team_id:
                            continue

                        opponent_id = get_team_id(session, row['opponent'])
                        if not opponent_id:
                            continue

                        # Get match ID
                        match_id = get_match_id(session, team_id, opponent_id, 2024, row['round'])
                        if not match_id:
                            skipped_no_match += 1
                            continue

                        # Insert player stats
                        session.execute(
                            text("""
                                INSERT INTO player_stats (
                                    match_id, player_id, disposals, kicks, handballs,
                                    marks, tackles, goals, behinds, hitouts, clearances,
                                    inside_50s, rebound_50s, contested_possessions,
                                    uncontested_possessions, contested_marks, marks_inside_50,
                                    one_percenters, clangers, free_kicks_for, free_kicks_against,
                                    brownlow_votes, time_on_ground_pct
                                ) VALUES (
                                    :match_id, :player_id, :disposals, :kicks, :handballs,
                                    :marks, :tackles, :goals, :behinds, :hitouts, :clearances,
                                    :inside_50s, :rebound_50s, :contested_possessions,
                                    :uncontested_possessions, :contested_marks, :marks_inside_50,
                                    :one_percenters, :clangers, :free_kicks_for, :free_kicks_against,
                                    :brownlow_votes, :time_on_ground_pct
                                )
                                ON CONFLICT (match_id, player_id) DO NOTHING
                            """),
                            {
                                "match_id": match_id,
                                "player_id": player_id,
                                "disposals": safe_int(row.get('disposals')),
                                "kicks": safe_int(row.get('kicks')),
                                "handballs": safe_int(row.get('handballs')),
                                "marks": safe_int(row.get('marks')),
                                "tackles": safe_int(row.get('tackles')),
                                "goals": safe_int(row.get('goals')),
                                "behinds": safe_int(row.get('behinds')),
                                "hitouts": safe_int(row.get('hit_outs')),
                                "clearances": safe_int(row.get('clearances')),
                                "inside_50s": safe_int(row.get('inside_50s')),
                                "rebound_50s": safe_int(row.get('rebound_50s')),
                                "contested_possessions": safe_int(row.get('contested_possessions')),
                                "uncontested_possessions": safe_int(row.get('uncontested_possessions')),
                                "contested_marks": safe_int(row.get('contested_marks')),
                                "marks_inside_50": safe_int(row.get('marks_inside_50')),
                                "one_percenters": safe_int(row.get('one_percenters')),
                                "clangers": safe_int(row.get('clangers')),
                                "free_kicks_for": safe_int(row.get('free_kicks_for')),
                                "free_kicks_against": safe_int(row.get('free_kicks_against')),
                                "brownlow_votes": safe_int(row.get('brownlow_votes')),
                                "time_on_ground_pct": safe_int(row.get('percentage_of_game_played'))
                            }
                        )
                        total_stats += 1

                    except Exception as insert_error:
                        # Roll back the failed transaction and start fresh
                        session.rollback()
                        logger.error(f"Error inserting stat for {player_name}: {insert_error}")
                        errors += 1
                        continue

                # Commit after each player to avoid losing data on errors
                session.commit()

                # Log progress every 100 players
                if total_players % 100 == 0:
                    logger.info(f"Progress: {total_players} players, {total_stats} stats committed")

            except Exception as e:
                logger.error(f"Error processing {csv_file.name}: {e}")
                errors += 1
                continue

        # Final commit
        session.commit()
        logger.info("Final commit completed")

    finally:
        session.close()

    logger.info("=" * 80)
    logger.info("✅ 2024 PLAYER DATA INGESTION COMPLETE!")
    logger.info(f"   Players processed: {total_players}")
    logger.info(f"   Total stats ingested: {total_stats}")
    logger.info(f"   Skipped (no matching match): {skipped_no_match}")
    logger.info(f"   Skipped (player not in DB): {skipped_no_player}")
    logger.info(f"   Errors: {errors}")
    logger.info("=" * 80)

if __name__ == "__main__":
    logger.info("Starting 2024 player data ingestion...")
    logger.info(f"CSV directory: {PLAYERS_DIR}")
    logger.info("=" * 80)

    ingest_2024_data()
