"""
Efficient backfill using temporary table and batch UPDATE.
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
    "Adelaide": "Adelaide", "Brisbane Lions": "Brisbane Lions", "Brisbane Bears": "Brisbane Lions",
    "Carlton": "Carlton", "Collingwood": "Collingwood", "Essendon": "Essendon", "Fitzroy": "Fitzroy",
    "Fremantle": "Fremantle", "Geelong": "Geelong", "Gold Coast": "Gold Coast",
    "Greater Western Sydney": "Greater Western Sydney", "GWS": "Greater Western Sydney",
    "Hawthorn": "Hawthorn", "Melbourne": "Melbourne", "North Melbourne": "North Melbourne",
    "Port Adelaide": "Port Adelaide", "Richmond": "Richmond", "St Kilda": "St Kilda",
    "Sydney": "Sydney", "West Coast": "West Coast", "Western Bulldogs": "Western Bulldogs",
    "Footscray": "Western Bulldogs",
}


def main():
    engine = create_engine(os.environ['DB_STRING'])

    # Load team IDs
    with engine.connect() as conn:
        result = conn.execute(text("SELECT id, name FROM teams"))
        team_ids = {row[1]: row[0] for row in result}

    # Get records that need updating
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

    # Build CSV lookup
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
                        key2 = (player_name.lower(), int(year), round_num, opponent)
                        csv_lookup[key2] = team
        except:
            continue

    logger.info(f"Loaded {len(csv_lookup)} CSV records")

    # Build updates list
    logger.info("Matching records to CSV data...")
    updates = []

    for ps_id, player_name, season, round_num, home_team, away_team in records:
        key = (player_name.lower(), season, round_num)
        team_name = csv_lookup.get(key)

        if not team_name:
            key1 = (player_name.lower(), season, round_num, away_team)
            key2 = (player_name.lower(), season, round_num, home_team)
            team_name = csv_lookup.get(key1) or csv_lookup.get(key2)

        if team_name:
            team_id = team_ids.get(team_name)
            if team_id:
                updates.append((ps_id, team_id))

    logger.info(f"Found teams for {len(updates)} records")

    # Create temp table and do batch update
    logger.info("Creating temp table and doing batch update...")

    with engine.connect() as conn:
        # Create temp table
        conn.execute(text("DROP TABLE IF EXISTS temp_team_updates"))
        conn.execute(text("""
            CREATE TEMP TABLE temp_team_updates (
                ps_id INTEGER PRIMARY KEY,
                team_id INTEGER
            )
        """))

        # Insert in batches
        batch_size = 5000
        for i in range(0, len(updates), batch_size):
            batch = updates[i:i+batch_size]
            values = ",".join(f"({ps_id},{team_id})" for ps_id, team_id in batch)
            conn.execute(text(f"INSERT INTO temp_team_updates (ps_id, team_id) VALUES {values}"))
            logger.info(f"Inserted batch {i//batch_size + 1}")

        # Do the batch update
        logger.info("Executing UPDATE...")
        result = conn.execute(text("""
            UPDATE player_stats ps
            SET team_id = t.team_id
            FROM temp_team_updates t
            WHERE ps.id = t.ps_id
        """))
        conn.commit()

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
