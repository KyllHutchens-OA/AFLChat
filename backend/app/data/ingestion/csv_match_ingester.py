"""
Ingest match data from local CSV files (from AFL-Data-Analysis repo).
This is safer and faster than web scraping.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import csv
import logging
from datetime import datetime
from typing import Optional

from app.data.database import Session
from app.data.models import Team, Match

logger = logging.getLogger(__name__)


class CSVMatchIngester:
    """Ingests match data from local CSV files."""

    # Team name mappings (CSV -> our database)
    TEAM_MAPPINGS = {
        "Adelaide": "ADE",
        "Brisbane Lions": "BRI",
        "Brisbane Bears": "BRI",
        "Carlton": "CAR",
        "Collingwood": "COL",
        "Essendon": "ESS",
        "Fitzroy": "FIT",  # Historical team (merged with Brisbane Bears in 1996)
        "Fremantle": "FRE",
        "Geelong": "GEE",
        "Gold Coast": "GCS",
        "Greater Western Sydney": "GWS",
        "Hawthorn": "HAW",
        "Melbourne": "MEL",
        "North Melbourne": "NM",
        "Port Adelaide": "PA",
        "Richmond": "RIC",
        "St Kilda": "STK",
        "Sydney": "SYD",
        "West Coast": "WCE",
        "Western Bulldogs": "WB",
        "Footscray": "WB",  # Renamed to Western Bulldogs in 1997
    }

    def __init__(self, csv_dir: str):
        self.csv_dir = Path(csv_dir)
        self.session = Session()
        self.teams_cache = {}
        self.existing_matches = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def _load_caches(self):
        """Load teams and existing matches into cache."""
        logger.info("Loading teams and existing matches...")

        # Load teams
        teams = self.session.query(Team).all()
        for team in teams:
            self.teams_cache[team.name] = team.id
            self.teams_cache[team.abbreviation] = team.id

        # Load existing matches
        matches = self.session.query(Match).all()
        for match in matches:
            key = (match.season, match.round, match.home_team_id, match.away_team_id)
            self.existing_matches.add(key)

        logger.info(
            f"Loaded {len(self.teams_cache)} team mappings, "
            f"{len(self.existing_matches)} existing matches"
        )

    def get_team_id(self, team_name: str) -> Optional[int]:
        """Get team ID from name."""
        # Try direct lookup
        if team_name in self.teams_cache:
            return self.teams_cache[team_name]

        # Try mapping
        abbrev = self.TEAM_MAPPINGS.get(team_name)
        if abbrev:
            return self.teams_cache.get(abbrev)

        return None

    def ingest_season(self, year: int, limit: Optional[int] = None, dry_run: bool = False):
        """
        Ingest matches from a single season CSV file.

        Args:
            year: Season year (e.g., 2025)
            limit: Maximum number of matches to ingest (for testing)
            dry_run: If True, don't commit to database
        """
        csv_path = self.csv_dir / f"matches_{year}.csv"

        if not csv_path.exists():
            logger.error(f"CSV file not found: {csv_path}")
            return

        if not self.teams_cache:
            self._load_caches()

        logger.info(f"Ingesting matches from {csv_path}")
        if limit:
            logger.info(f"LIMIT: Only ingesting first {limit} matches (testing mode)")
        if dry_run:
            logger.info("DRY RUN: Will not commit to database")

        added_count = 0
        skipped_count = 0
        error_count = 0

        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)

            for i, row in enumerate(reader):
                if limit and i >= limit:
                    logger.info(f"Reached limit of {limit} matches")
                    break

                try:
                    # Parse team names
                    team1_name = row['team_1_team_name']
                    team2_name = row['team_2_team_name']

                    team1_id = self.get_team_id(team1_name)
                    team2_id = self.get_team_id(team2_name)

                    if not (team1_id and team2_id):
                        logger.warning(f"Could not find teams: {team1_name} / {team2_name}")
                        error_count += 1
                        continue

                    # Check if match already exists
                    round_str = row['round_num']
                    match_key = (year, round_str, team1_id, team2_id)

                    if match_key in self.existing_matches:
                        skipped_count += 1
                        continue

                    # Parse date
                    date_str = row['date']
                    try:
                        match_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                    except:
                        match_date = datetime.strptime(date_str[:10], '%Y-%m-%d')

                    # Helper function to safely convert to int (handles decimals like "17.0")
                    def safe_int(value):
                        try:
                            return int(float(value))
                        except (ValueError, TypeError):
                            return 0

                    # Parse scores
                    team1_score = safe_int(row['team_1_final_goals']) * 6 + safe_int(row['team_1_final_behinds'])
                    team2_score = safe_int(row['team_2_final_goals']) * 6 + safe_int(row['team_2_final_behinds'])

                    # Create match
                    match = Match(
                        season=year,
                        round=round_str,
                        match_date=match_date,
                        venue=row['venue'],
                        home_team_id=team1_id,
                        away_team_id=team2_id,
                        home_score=team1_score,
                        away_score=team2_score,
                        home_q1_goals=safe_int(row['team_1_q1_goals']),
                        home_q1_behinds=safe_int(row['team_1_q1_behinds']),
                        home_q2_goals=safe_int(row['team_1_q2_goals']),
                        home_q2_behinds=safe_int(row['team_1_q2_behinds']),
                        home_q3_goals=safe_int(row['team_1_q3_goals']),
                        home_q3_behinds=safe_int(row['team_1_q3_behinds']),
                        home_q4_goals=safe_int(row['team_1_final_goals']),
                        home_q4_behinds=safe_int(row['team_1_final_behinds']),
                        away_q1_goals=safe_int(row['team_2_q1_goals']),
                        away_q1_behinds=safe_int(row['team_2_q1_behinds']),
                        away_q2_goals=safe_int(row['team_2_q2_goals']),
                        away_q2_behinds=safe_int(row['team_2_q2_behinds']),
                        away_q3_goals=safe_int(row['team_2_q3_goals']),
                        away_q3_behinds=safe_int(row['team_2_q3_behinds']),
                        away_q4_goals=safe_int(row['team_2_final_goals']),
                        away_q4_behinds=safe_int(row['team_2_final_behinds']),
                        match_status="completed"
                    )

                    if not dry_run:
                        self.session.add(match)
                        self.existing_matches.add(match_key)

                    added_count += 1

                    if added_count % 10 == 0:
                        logger.info(f"Processed {added_count} matches...")

                except Exception as e:
                    logger.error(f"Error processing row {i}: {e}")
                    logger.error(f"Row data: {row}")
                    error_count += 1
                    continue

        if not dry_run:
            self.session.commit()
            logger.info(f"✅ Committed {added_count} new matches to database")
        else:
            logger.info(f"✅ DRY RUN: Would have added {added_count} matches")

        logger.info(f"Skipped {skipped_count} existing matches")
        if error_count > 0:
            logger.warning(f"❌ {error_count} errors encountered")


def main():
    """Test the ingester with 2025 data (limited to 5 matches)."""
    logging.basicConfig(level=logging.INFO)

    csv_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/matches"

    with CSVMatchIngester(csv_dir) as ingester:
        # TEST MODE: Dry run with only 5 matches
        logger.info("=" * 60)
        logger.info("TEST MODE: Dry run with 5 matches from 2025")
        logger.info("=" * 60)
        ingester.ingest_season(2025, limit=5, dry_run=True)


if __name__ == "__main__":
    main()
