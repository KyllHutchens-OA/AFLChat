"""
Ingest player statistics data from local CSV files (from AFL-Data-Analysis repo).
Each CSV file contains performance statistics for one player across their career.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import csv
import logging
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Set
from collections import defaultdict

from sqlalchemy import and_
from sqlalchemy.dialects.postgresql import insert

from app.data.database import Session, engine
from app.data.models import Team, Match, Player, PlayerStat

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PlayerDataIngester:
    """Ingests player performance data from local CSV files."""

    # Team name mappings (CSV -> database abbreviation)
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
        "South Melbourne": "SYD",  # Relocated to Sydney in 1982
        "University": "UNI",  # Historical team (disbanded 1914)
    }

    def __init__(self, csv_dir: str):
        self.csv_dir = Path(csv_dir)
        self.session = Session()
        self.teams_cache: Dict[str, int] = {}
        self.matches_cache: Dict[Tuple, int] = {}  # (season, round, team1_id, team2_id) -> match_id
        self.players_cache: Dict[str, int] = {}  # "firstname lastname" -> player_id
        self.existing_player_stats: Set[Tuple[int, int]] = set()  # (match_id, player_id)

        # Statistics
        self.stats = {
            'files_processed': 0,
            'files_skipped': 0,
            'files_errored': 0,
            'players_created': 0,
            'stats_created': 0,
            'stats_skipped': 0,
            'match_not_found': 0,
            'data_quality_warnings': 0,
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def _load_caches(self):
        """Load teams, matches, players, and existing stats into cache."""
        logger.info("Loading caches from database...")

        # Load teams
        teams = self.session.query(Team).all()
        for team in teams:
            self.teams_cache[team.name] = team.id
            self.teams_cache[team.abbreviation] = team.id
        logger.info(f"  Loaded {len(teams)} teams")

        # Load matches into cache for quick lookup
        # Key: (season, round, home_team_id, away_team_id) and (season, round, away_team_id, home_team_id)
        matches = self.session.query(Match).all()
        for match in matches:
            # Both orderings to handle either team perspective
            key1 = (match.season, match.round, match.home_team_id, match.away_team_id)
            key2 = (match.season, match.round, match.away_team_id, match.home_team_id)
            self.matches_cache[key1] = match.id
            self.matches_cache[key2] = match.id
        logger.info(f"  Loaded {len(matches)} matches")

        # Load existing players
        players = self.session.query(Player).all()
        for player in players:
            key = player.name.lower()
            self.players_cache[key] = player.id
        logger.info(f"  Loaded {len(players)} existing players")

        # Load existing player stats to avoid duplicates
        existing = self.session.query(PlayerStat.match_id, PlayerStat.player_id).all()
        for match_id, player_id in existing:
            self.existing_player_stats.add((match_id, player_id))
        logger.info(f"  Loaded {len(self.existing_player_stats)} existing player stats")

    def get_team_id(self, team_name: str) -> Optional[int]:
        """Get team ID from name."""
        if team_name in self.teams_cache:
            return self.teams_cache[team_name]
        abbrev = self.TEAM_MAPPINGS.get(team_name)
        if abbrev:
            return self.teams_cache.get(abbrev)
        return None

    def parse_filename(self, filename: str) -> Optional[Tuple[str, str, str]]:
        """
        Parse player filename to extract name and DOB.
        Format: lastname_firstname_DDMMYYYY_performance_details.csv

        Returns: (first_name, last_name, dob_str) or None if invalid
        """
        match = re.match(r'^([a-z]+)_([a-z]+)_(\d{8})_performance_details\.csv$', filename, re.IGNORECASE)
        if not match:
            return None

        last_name = match.group(1).title()
        first_name = match.group(2).title()
        dob_str = match.group(3)

        return (first_name, last_name, dob_str)

    def get_or_create_player(self, first_name: str, last_name: str, dob_str: str, team_name: str) -> int:
        """Get existing player ID or create new player."""
        full_name = f"{first_name} {last_name}"
        cache_key = full_name.lower()

        if cache_key in self.players_cache:
            return self.players_cache[cache_key]

        # Parse DOB
        try:
            dob = datetime.strptime(dob_str, '%d%m%Y').date()
        except:
            dob = None

        # Get team ID
        team_id = self.get_team_id(team_name)

        # Create new player
        player = Player(
            name=full_name,
            first_name=first_name,
            last_name=last_name,
            team_id=team_id,
            date_of_birth=dob,
            is_active=True
        )
        self.session.add(player)
        self.session.flush()  # Get the ID

        self.players_cache[cache_key] = player.id
        self.stats['players_created'] += 1

        return player.id

    def find_match_id(self, year: int, round_str: str, team_name: str, opponent_name: str) -> Optional[int]:
        """Find match ID from year, round, and teams."""
        team_id = self.get_team_id(team_name)
        opponent_id = self.get_team_id(opponent_name)

        if not team_id or not opponent_id:
            return None

        # Try both orderings
        key1 = (year, round_str, team_id, opponent_id)
        key2 = (year, round_str, opponent_id, team_id)

        match_id = self.matches_cache.get(key1) or self.matches_cache.get(key2)
        return match_id

    def safe_int(self, value: str, default: int = 0) -> int:
        """Safely convert string to int."""
        if not value or value.strip() == '':
            return default
        try:
            # Handle cases like "35↑" (substitution markers)
            clean_value = re.sub(r'[^\d\-]', '', value)
            return int(clean_value) if clean_value else default
        except:
            return default

    def safe_float(self, value: str, default: float = None) -> Optional[float]:
        """Safely convert string to float."""
        if not value or value.strip() == '':
            return default
        try:
            return float(value)
        except:
            return default

    def validate_row(self, row: dict) -> bool:
        """Validate data quality of a row."""
        kicks = self.safe_int(row.get('kicks', '0'))
        handballs = self.safe_int(row.get('handballs', '0'))
        disposals = self.safe_int(row.get('disposals', '0'))

        # Check disposals = kicks + handballs
        if disposals > 0 and disposals != kicks + handballs:
            # Allow small discrepancies (data quality issues in source)
            if abs(disposals - (kicks + handballs)) > 2:
                self.stats['data_quality_warnings'] += 1
                return True  # Still process, just warn

        return True

    def process_csv_file(self, csv_path: Path) -> List[dict]:
        """Process a single CSV file and return list of stat records to insert."""
        filename = csv_path.name
        parsed = self.parse_filename(filename)

        if not parsed:
            logger.warning(f"Could not parse filename: {filename}")
            return []

        first_name, last_name, dob_str = parsed
        stats_to_insert = []
        player_id = None
        first_team = None

        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Skip empty rows
                    if not row.get('year') or not row.get('team'):
                        continue

                    team_name = row.get('team', '').strip()
                    if not team_name:
                        continue

                    # Store first team for player creation
                    if first_team is None:
                        first_team = team_name

                    # Get or create player (lazy, on first row)
                    if player_id is None:
                        player_id = self.get_or_create_player(first_name, last_name, dob_str, first_team)

                    # Find match
                    year = self.safe_int(row.get('year'))
                    round_str = row.get('round', '').strip()
                    opponent = row.get('opponent', '').strip()

                    if not year or not round_str or not opponent:
                        continue

                    match_id = self.find_match_id(year, round_str, team_name, opponent)

                    if not match_id:
                        self.stats['match_not_found'] += 1
                        continue

                    # Check for duplicate
                    if (match_id, player_id) in self.existing_player_stats:
                        self.stats['stats_skipped'] += 1
                        continue

                    # Validate row
                    self.validate_row(row)

                    # Build stat record
                    stat = {
                        'match_id': match_id,
                        'player_id': player_id,
                        'kicks': self.safe_int(row.get('kicks')),
                        'marks': self.safe_int(row.get('marks')),
                        'handballs': self.safe_int(row.get('handballs')),
                        'disposals': self.safe_int(row.get('disposals')),
                        'goals': self.safe_int(row.get('goals')),
                        'behinds': self.safe_int(row.get('behinds')),
                        'hitouts': self.safe_int(row.get('hit_outs')),
                        'tackles': self.safe_int(row.get('tackles')),
                        'rebound_50s': self.safe_int(row.get('rebound_50s')),
                        'inside_50s': self.safe_int(row.get('inside_50s')),
                        'clearances': self.safe_int(row.get('clearances')),
                        'clangers': self.safe_int(row.get('clangers')),
                        'free_kicks_for': self.safe_int(row.get('free_kicks_for')),
                        'free_kicks_against': self.safe_int(row.get('free_kicks_against')),
                        'brownlow_votes': self.safe_int(row.get('brownlow_votes')),
                        'contested_possessions': self.safe_int(row.get('contested_possessions')),
                        'uncontested_possessions': self.safe_int(row.get('uncontested_possessions')),
                        'contested_marks': self.safe_int(row.get('contested_marks')),
                        'marks_inside_50': self.safe_int(row.get('marks_inside_50')),
                        'one_percenters': self.safe_int(row.get('one_percenters')),
                        'bounces': self.safe_int(row.get('bounces')),
                        'goal_assist': self.safe_int(row.get('goal_assist')),
                        'time_on_ground_pct': self.safe_float(row.get('percentage_of_game_played')),
                    }

                    stats_to_insert.append(stat)
                    self.existing_player_stats.add((match_id, player_id))

        except Exception as e:
            logger.error(f"Error processing {filename}: {e}")
            self.stats['files_errored'] += 1
            return []

        return stats_to_insert

    def ingest_all(self, batch_size: int = 1000, limit: Optional[int] = None):
        """
        Ingest all player performance CSV files.

        Args:
            batch_size: Number of stats to insert per batch
            limit: Maximum number of files to process (for testing)
        """
        # Load caches
        self._load_caches()

        # Get all performance files
        pattern = "*_performance_details.csv"
        csv_files = sorted(self.csv_dir.glob(pattern))
        total_files = len(csv_files)

        if limit:
            csv_files = csv_files[:limit]
            logger.info(f"LIMIT: Processing only {limit} of {total_files} files")

        logger.info(f"Found {total_files} player performance files")
        logger.info(f"Starting ingestion (batch size: {batch_size})...")

        all_stats = []

        for i, csv_path in enumerate(csv_files):
            stats = self.process_csv_file(csv_path)
            all_stats.extend(stats)
            self.stats['files_processed'] += 1

            # Batch insert when we have enough
            if len(all_stats) >= batch_size:
                self._batch_insert_stats(all_stats)
                all_stats = []

            # Progress update every 500 files
            if (i + 1) % 500 == 0:
                logger.info(
                    f"Progress: {i + 1}/{len(csv_files)} files "
                    f"({self.stats['players_created']} players, "
                    f"{self.stats['stats_created']} stats)"
                )

        # Insert remaining stats
        if all_stats:
            self._batch_insert_stats(all_stats)

        # Final commit for any player records
        self.session.commit()

        # Print summary
        self._print_summary()

    def _batch_insert_stats(self, stats: List[dict]):
        """Batch insert player stats."""
        if not stats:
            return

        try:
            self.session.bulk_insert_mappings(PlayerStat, stats)
            self.session.commit()
            self.stats['stats_created'] += len(stats)
        except Exception as e:
            logger.error(f"Batch insert failed: {e}")
            self.session.rollback()

            # Try individual inserts for debugging
            for stat in stats:
                try:
                    self.session.execute(
                        PlayerStat.__table__.insert().values(**stat)
                    )
                    self.session.commit()
                    self.stats['stats_created'] += 1
                except Exception as inner_e:
                    self.session.rollback()
                    logger.error(f"Failed to insert stat: {inner_e}")

    def _print_summary(self):
        """Print ingestion summary."""
        logger.info("=" * 60)
        logger.info("INGESTION COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Files processed: {self.stats['files_processed']}")
        logger.info(f"Files errored: {self.stats['files_errored']}")
        logger.info(f"Players created: {self.stats['players_created']}")
        logger.info(f"Stats created: {self.stats['stats_created']}")
        logger.info(f"Stats skipped (duplicates): {self.stats['stats_skipped']}")
        logger.info(f"Matches not found: {self.stats['match_not_found']}")
        logger.info(f"Data quality warnings: {self.stats['data_quality_warnings']}")
        logger.info("=" * 60)


def main():
    """Run the player data ingestion."""
    csv_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players"

    logger.info("=" * 60)
    logger.info("AFL Player Data Ingestion")
    logger.info("=" * 60)

    with PlayerDataIngester(csv_dir) as ingester:
        # Full ingestion
        ingester.ingest_all(batch_size=1000)


if __name__ == "__main__":
    main()
