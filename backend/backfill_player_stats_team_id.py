"""
Backfill team_id in player_stats table using CSV source data.

The CSV files contain the team each player was on for each game,
which correctly handles player trades.
"""
import os
import sys
import csv
import logging
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

os.environ['DB_STRING'] = 'postgresql+psycopg://postgres.igdcvgxbglzhhfczznhw:Wbn56t7pq!ky@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres'

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# CSV data directory
CSV_DIR = Path("/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players")

# Team name mappings (CSV team names -> database team names)
TEAM_MAPPINGS = {
    "Adelaide": "Adelaide",
    "Brisbane Lions": "Brisbane Lions",
    "Brisbane Bears": "Brisbane Lions",
    "Carlton": "Carlton",
    "Collingwood": "Collingwood",
    "Essendon": "Essendon",
    "Fitzroy": "Fitzroy",
    "Fremantle": "Fremantle",
    "Geelong": "Geelong",
    "Gold Coast": "Gold Coast",
    "Greater Western Sydney": "Greater Western Sydney",
    "GWS": "Greater Western Sydney",
    "Hawthorn": "Hawthorn",
    "Melbourne": "Melbourne",
    "North Melbourne": "North Melbourne",
    "Port Adelaide": "Port Adelaide",
    "Richmond": "Richmond",
    "St Kilda": "St Kilda",
    "Sydney": "Sydney",
    "West Coast": "West Coast",
    "Western Bulldogs": "Western Bulldogs",
    "Footscray": "Western Bulldogs",
}


def load_team_ids(engine):
    """Load team name -> id mapping from database."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM teams"))
        return {row[1]: row[0] for row in result}


def normalize_player_name(csv_filename):
    """Extract player name from CSV filename.

    Format: lastname_firstname_ddmmyyyy_performance_details.csv
    """
    parts = csv_filename.replace("_performance_details.csv", "").split("_")
    if len(parts) >= 2:
        # lastname_firstname -> "Firstname Lastname"
        lastname = parts[0].title()
        firstname = parts[1].title()
        return f"{firstname} {lastname}"
    return None


def load_csv_data():
    """Load all player performance CSV files and build lookup dict.

    Returns dict: {(player_name_lower, season, round): team_name}
    """
    logger.info("Loading CSV data...")

    csv_files = list(CSV_DIR.glob("*_performance_details.csv"))
    logger.info(f"Found {len(csv_files)} performance CSV files")

    # Build lookup: (player_name, season, round, opponent) -> team
    lookup = {}
    player_names = {}  # CSV name -> standardized name

    for i, csv_file in enumerate(csv_files):
        if i % 1000 == 0:
            logger.info(f"Processing CSV {i}/{len(csv_files)}...")

        player_name = normalize_player_name(csv_file.name)
        if not player_name:
            continue

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    team = row.get('team', '').strip()
                    year = row.get('year', '').strip()
                    round_num = row.get('round', '').strip()
                    opponent = row.get('opponent', '').strip()

                    if team and year and round_num:
                        # Normalize team name
                        team = TEAM_MAPPINGS.get(team, team)

                        # Store with multiple key formats for matching
                        key = (player_name.lower(), int(year), round_num)
                        lookup[key] = team

                        # Also store with opponent for disambiguation
                        key_with_opp = (player_name.lower(), int(year), round_num, opponent)
                        lookup[key_with_opp] = team

        except Exception as e:
            logger.warning(f"Error reading {csv_file.name}: {e}")
            continue

    logger.info(f"Loaded {len(lookup)} CSV records")
    return lookup


def get_player_names_mapping(engine):
    """Get mapping of player_id -> player_name from database."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM players"))
        return {row[0]: row[1] for row in result}


def get_match_info(engine):
    """Get match info for all matches."""
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT m.id, m.season, m.round,
                   th.name as home_team, ta.name as away_team
            FROM matches m
            JOIN teams th ON m.home_team_id = th.id
            JOIN teams ta ON m.away_team_id = ta.id
        """))
        return {row[0]: {'season': row[1], 'round': row[2],
                        'home_team': row[3], 'away_team': row[4]}
                for row in result}


def backfill_team_ids(engine, csv_lookup, batch_size=5000):
    """Backfill team_id in player_stats using CSV lookup."""

    team_ids = load_team_ids(engine)
    player_names = get_player_names_mapping(engine)
    match_info = get_match_info(engine)

    logger.info(f"Loaded {len(team_ids)} teams, {len(player_names)} players, {len(match_info)} matches")

    # Get all player_stats that need updating
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT id, match_id, player_id
            FROM player_stats
            WHERE team_id IS NULL
        """))
        records = list(result)

    logger.info(f"Found {len(records)} player_stats records to update")

    updated = 0
    not_found = 0
    errors = 0

    # Process in batches
    for batch_start in range(0, len(records), batch_size):
        batch = records[batch_start:batch_start + batch_size]
        updates = []

        for ps_id, match_id, player_id in batch:
            player_name = player_names.get(player_id, '')
            match = match_info.get(match_id, {})

            if not player_name or not match:
                not_found += 1
                continue

            season = match.get('season')
            round_num = match.get('round')
            home_team = match.get('home_team')
            away_team = match.get('away_team')

            # Try to find team from CSV
            team_name = None

            # Try exact match with round
            key = (player_name.lower(), season, round_num)
            if key in csv_lookup:
                team_name = csv_lookup[key]

            # Try with opponent (both home and away)
            if not team_name:
                key_home = (player_name.lower(), season, round_num, away_team)
                key_away = (player_name.lower(), season, round_num, home_team)

                if key_home in csv_lookup:
                    team_name = csv_lookup[key_home]
                elif key_away in csv_lookup:
                    team_name = csv_lookup[key_away]

            # If still not found, try to infer from match teams
            if not team_name:
                # Player must be on one of the two teams
                # Use whatever team_id the player has if it matches
                not_found += 1
                continue

            # Get team_id
            team_id = team_ids.get(team_name)
            if team_id:
                updates.append((team_id, ps_id))

        # Execute batch update
        if updates:
            with engine.connect() as conn:
                for team_id, ps_id in updates:
                    conn.execute(text(
                        "UPDATE player_stats SET team_id = :team_id WHERE id = :id"
                    ), {"team_id": team_id, "id": ps_id})
                conn.commit()
            updated += len(updates)

        logger.info(f"Progress: {batch_start + len(batch)}/{len(records)} | Updated: {updated} | Not found: {not_found}")

    logger.info(f"Backfill complete: Updated {updated}, Not found {not_found}, Errors {errors}")
    return updated, not_found


def fallback_from_match_teams(engine):
    """For remaining NULL team_ids, try to infer from match teams.

    If player's current team_id matches one of the match teams, use that.
    """
    logger.info("Running fallback: inferring from match teams...")

    with engine.connect() as conn:
        # Update where player's team_id matches home_team
        result = conn.execute(text("""
            UPDATE player_stats ps
            SET team_id = p.team_id
            FROM players p
            JOIN matches m ON ps.match_id = m.id
            WHERE ps.player_id = p.id
            AND ps.team_id IS NULL
            AND p.team_id IS NOT NULL
            AND (p.team_id = m.home_team_id OR p.team_id = m.away_team_id)
        """))
        conn.commit()

        # Count remaining nulls
        result = conn.execute(text(
            "SELECT COUNT(*) FROM player_stats WHERE team_id IS NULL"
        ))
        remaining = result.fetchone()[0]

    logger.info(f"Fallback complete. Remaining NULL team_ids: {remaining}")
    return remaining


def main():
    logger.info("=" * 60)
    logger.info("Player Stats Team ID Backfill")
    logger.info("=" * 60)

    engine = create_engine(os.environ['DB_STRING'])

    # Load CSV data
    csv_lookup = load_csv_data()

    # Backfill from CSV
    updated, not_found = backfill_team_ids(engine, csv_lookup)

    # Fallback for remaining records
    remaining = fallback_from_match_teams(engine)

    logger.info("=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"Updated from CSV: {updated}")
    logger.info(f"Not found in CSV: {not_found}")
    logger.info(f"Remaining NULL: {remaining}")


if __name__ == "__main__":
    main()
