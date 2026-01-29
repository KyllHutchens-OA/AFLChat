"""
Backfill team_id for traded players using CSV source data.

This handles the ~58k records where the player's current team doesn't match
the match teams (i.e., the player was traded).
"""
import os
import sys
import csv
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

os.environ['DB_STRING'] = 'postgresql+psycopg://postgres.igdcvgxbglzhhfczznhw:Wbn56t7pq!ky@aws-1-ap-southeast-2.pooler.supabase.com:6543/postgres'

from sqlalchemy import create_engine, text

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CSV_DIR = Path("/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players")

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


def main():
    engine = create_engine(os.environ['DB_STRING'])

    # Load team IDs
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM teams"))
        team_ids = {row[1]: row[0] for row in result}

    # Get records that need updating with player/match info
    logger.info("Loading records needing update...")
    with engine.connect() as conn:
        result = conn.execute(text("""
            SELECT ps.id, p.name as player_name, m.season, m.round,
                   th.name as home_team, ta.name as away_team
            FROM player_stats ps
            JOIN players p ON ps.player_id = p.id
            JOIN matches m ON ps.match_id = m.id
            JOIN teams th ON m.home_team_id = th.id
            JOIN teams ta ON m.away_team_id = ta.id
            WHERE ps.team_id IS NULL
        """))
        records = list(result)

    logger.info(f"Found {len(records)} records to process")

    # Build CSV lookup: (player_name_lower, season, round) -> team
    logger.info("Loading CSV data...")
    csv_lookup = {}
    csv_files = list(CSV_DIR.glob("*_performance_details.csv"))

    for csv_file in csv_files:
        parts = csv_file.name.replace("_performance_details.csv", "").split("_")
        if len(parts) >= 2:
            player_name = f"{parts[1].title()} {parts[0].title()}"
        else:
            continue

        try:
            with open(csv_file, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    team = row.get('team', '').strip()
                    year = row.get('year', '').strip()
                    round_num = row.get('round', '').strip()
                    opponent = row.get('opponent', '').strip()

                    if team and year:
                        team = TEAM_MAPPINGS.get(team, team)
                        key = (player_name.lower(), int(year), round_num)
                        csv_lookup[key] = team
                        # Also with opponent
                        key2 = (player_name.lower(), int(year), round_num, opponent)
                        csv_lookup[key2] = team
        except:
            continue

    logger.info(f"Loaded {len(csv_lookup)} CSV records")

    # Process records and build updates
    logger.info("Matching records to CSV data...")
    updates = []
    not_found = 0

    for ps_id, player_name, season, round_num, home_team, away_team in records:
        key = (player_name.lower(), season, round_num)
        team_name = csv_lookup.get(key)

        if not team_name:
            # Try with opponent
            key1 = (player_name.lower(), season, round_num, away_team)
            key2 = (player_name.lower(), season, round_num, home_team)
            team_name = csv_lookup.get(key1) or csv_lookup.get(key2)

        if team_name:
            team_id = team_ids.get(team_name)
            if team_id:
                updates.append((team_id, ps_id))
        else:
            not_found += 1

    logger.info(f"Found teams for {len(updates)} records, {not_found} not found")

    # Execute batch updates
    if updates:
        logger.info("Executing batch updates...")
        batch_size = 10000

        with engine.connect() as conn:
            for i in range(0, len(updates), batch_size):
                batch = updates[i:i+batch_size]
                # Build VALUES clause
                for team_id, ps_id in batch:
                    conn.execute(text(
                        "UPDATE player_stats SET team_id = :team_id WHERE id = :id"
                    ), {"team_id": team_id, "id": ps_id})
                conn.commit()
                logger.info(f"Updated batch {i//batch_size + 1}: {min(i+batch_size, len(updates))}/{len(updates)}")

    # Final stats
    with engine.connect() as conn:
        result = conn.execute(text('SELECT COUNT(*) FROM player_stats WHERE team_id IS NOT NULL'))
        populated = result.fetchone()[0]
        result = conn.execute(text('SELECT COUNT(*) FROM player_stats WHERE team_id IS NULL'))
        remaining = result.fetchone()[0]

    logger.info("=" * 60)
    logger.info(f"COMPLETE: {populated} populated, {remaining} remaining NULL")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
