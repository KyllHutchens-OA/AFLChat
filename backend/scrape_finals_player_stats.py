"""
Finals Player Stats Scraper

Scrapes player statistics from individual AFL Tables match pages for finals matches.
The player CSV files don't include finals, so we need to get them from match pages.
"""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

import logging
import requests
from bs4 import BeautifulSoup
import time
import re
from typing import List, Dict, Optional, Tuple
from datetime import datetime

from app.data.database import Session
from app.data.models import Match, Team, PlayerStat
from sqlalchemy import and_

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class FinalsPlayerStatsScraper:
    """Scrapes player stats from AFL Tables match pages for finals."""

    BASE_URL = "https://afltables.com/afl/stats/games"

    # Team ID mappings for AFL Tables URLs (verified from AFL Tables website)
    TEAM_IDS = {
        "ADE": "01",  # Adelaide
        "BRI": "19",  # Brisbane Lions
        "CAR": "03",  # Carlton
        "COL": "04",  # Collingwood
        "ESS": "05",  # Essendon
        "FIT": "06",  # Fitzroy (historical)
        "FRE": "08",  # Fremantle
        "GEE": "09",  # Geelong
        "GCS": "20",  # Gold Coast
        "GWS": "21",  # Greater Western Sydney
        "HAW": "10",  # Hawthorn
        "MEL": "11",  # Melbourne
        "NM": "12",   # North Melbourne
        "PA": "13",   # Port Adelaide
        "RIC": "14",  # Richmond
        "STK": "15",  # St Kilda
        "SYD": "16",  # Sydney
        "WCE": "18",  # West Coast
        "WB": "07"    # Western Bulldogs
    }

    def __init__(self, output_csv: str):
        self.output_csv = Path(output_csv)
        self.session = Session()
        self.stats = {
            'matches_processed': 0,
            'players_found': 0,
            'stats_written': 0,
            'errors': 0
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def get_missing_finals(self) -> List[Match]:
        """Get all finals matches without player_stats."""
        matches_with_stats = self.session.query(PlayerStat.match_id).distinct()

        missing_matches = (
            self.session.query(Match)
            .filter(~Match.id.in_(matches_with_stats))
            .order_by(Match.season, Match.match_date)
            .all()
        )

        logger.info(f"Found {len(missing_matches)} matches without player_stats")
        return missing_matches

    def construct_match_url(self, match: Match) -> Optional[str]:
        """Construct AFL Tables match URL.

        AFL Tables URL format: {lower_team_id}{higher_team_id}{YYYYMMDD}.html
        Team IDs are sorted numerically (lower first), not by home/away.
        """
        home_team = self.session.query(Team).filter(Team.id == match.home_team_id).first()
        away_team = self.session.query(Team).filter(Team.id == match.away_team_id).first()

        if not home_team or not away_team:
            return None

        home_id = self.TEAM_IDS.get(home_team.abbreviation, "00")
        away_id = self.TEAM_IDS.get(away_team.abbreviation, "00")

        # Handle Brisbane Bears (pre-1997) vs Brisbane Lions (1997+)
        # AFL Tables uses ID "02" for Brisbane Bears games before 1997
        if home_team.abbreviation == "BRI" and match.season < 1997:
            home_id = "02"
        if away_team.abbreviation == "BRI" and match.season < 1997:
            away_id = "02"

        # AFL Tables uses lower team ID first, not home team first
        team_ids = sorted([home_id, away_id])

        # Format: YYYYMMDD
        date_str = match.match_date.strftime("%Y%m%d")

        game_id = f"{team_ids[0]}{team_ids[1]}{date_str}"
        url = f"{self.BASE_URL}/{match.season}/{game_id}.html"

        return url

    def scrape_match_player_stats(self, match: Match, url: str) -> List[Dict]:
        """
        Scrape player stats from an AFL Tables match page.

        Returns list of player stat dictionaries.
        """
        try:
            logger.info(f"Scraping: {url}")
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            all_stats = []

            home_team = self.session.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = self.session.query(Team).filter(Team.id == match.away_team_id).first()

            tables = soup.find_all('table')

            # Extract team order from match info table (first table)
            # Team names appear at cells 3 and 8 in the match info
            page_teams = []
            if tables:
                match_info_cells = tables[0].find_all('td')
                for cell in match_info_cells:
                    text = cell.get_text(strip=True)
                    # Check if this cell contains a team name we know about
                    if text == home_team.name:
                        page_teams.append(home_team)
                    elif text == away_team.name:
                        page_teams.append(away_team)
                    # Also check for partial matches (e.g., "Brisbane Lions" vs "Brisbane")
                    elif home_team.name in text or text in home_team.name:
                        if home_team not in page_teams:
                            page_teams.append(home_team)
                    elif away_team.name in text or text in away_team.name:
                        if away_team not in page_teams:
                            page_teams.append(away_team)

            # Default to home/away order if extraction failed
            if len(page_teams) < 2:
                page_teams = [home_team, away_team]

            # Find all player stats tables (tables with KI, HB, DI headers)
            stats_tables = []
            for table in tables:
                all_rows = table.find_all('tr')
                if not all_rows:
                    continue

                # Check first few rows for stats headers
                for row_idx in range(min(3, len(all_rows))):
                    row = all_rows[row_idx]
                    row_cells = [cell.get_text(strip=True) for cell in row.find_all(['th', 'td'])]

                    # Player stats tables have KI (kicks), HB (handballs), DI (disposals)
                    if any(h in ['KI', 'HB', 'DI'] for h in row_cells) and 'Player' in row_cells:
                        stats_tables.append((table, row_cells, row_idx))
                        break

            # Process each stats table
            for table_idx, (table, headers, header_row_idx) in enumerate(stats_tables):
                # Assign team based on table order (first table = first team on page)
                if table_idx < len(page_teams):
                    team_for_table = page_teams[table_idx]
                else:
                    team_for_table = page_teams[0] if table_idx == 0 else page_teams[1]

                opponent = away_team if team_for_table == home_team else home_team

                logger.info(f"Found stats table for {team_for_table.name} with headers: {headers[:10]}")

                # Parse player rows
                all_rows = table.find_all('tr')
                rows = all_rows[header_row_idx + 1:]

                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) < 5:
                        continue

                    # Extract player name (usually second cell with a link, after jersey number)
                    player_link = row.find('a')
                    if not player_link:
                        continue

                    player_name = player_link.get_text(strip=True)

                    # Skip non-player rows
                    if 'Totals' in player_name or 'Opposition' in player_name or 'Season' in player_name:
                        continue

                    stat_dict = {
                        'match_id': match.id,
                        'player_name': player_name,
                        'team': team_for_table.name,
                        'year': match.season,
                        'round': match.round,
                        'opponent': opponent.name
                    }

                    # Parse stats from cells using AFL Tables column names
                    for i, cell in enumerate(cells):
                        text = cell.get_text(strip=True)
                        if i < len(headers):
                            header = headers[i]
                            # AFL Tables uses abbreviated headers: KI, HB, DI, MK, GL, BH, TK, HO
                            if header in ['KI', 'K', 'Kicks']:
                                stat_dict['kicks'] = self._safe_int(text)
                            elif header in ['MK', 'M', 'Marks']:
                                stat_dict['marks'] = self._safe_int(text)
                            elif header in ['HB', 'H', 'Handballs']:
                                stat_dict['handballs'] = self._safe_int(text)
                            elif header in ['DI', 'D', 'Disp', 'Disposals']:
                                stat_dict['disposals'] = self._safe_int(text)
                            elif header in ['GL', 'G', 'Goals']:
                                stat_dict['goals'] = self._safe_int(text)
                            elif header in ['BH', 'B', 'Behinds']:
                                stat_dict['behinds'] = self._safe_int(text)
                            elif header in ['TK', 'T', 'Tackles']:
                                stat_dict['tackles'] = self._safe_int(text)
                            elif header in ['HO', 'Hitouts']:
                                stat_dict['hitouts'] = self._safe_int(text)

                    if 'kicks' in stat_dict or 'disposals' in stat_dict:
                        all_stats.append(stat_dict)
                        self.stats['players_found'] += 1

            logger.info(f"Found {len(all_stats)} player stats for this match")
            return all_stats

        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            self.stats['errors'] += 1
            return []

    def _safe_int(self, value: str, default: int = 0) -> int:
        """Safely convert string to int."""
        try:
            # Remove any non-digit characters except minus
            clean = re.sub(r'[^\d\-]', '', str(value))
            return int(clean) if clean else default
        except:
            return default

    def scrape_all_finals(self):
        """Scrape player stats for all missing finals matches."""
        logger.info("=" * 60)
        logger.info("Finals Player Stats Scraper")
        logger.info("=" * 60)

        missing_matches = self.get_missing_finals()

        # Group by year
        by_year = {}
        for match in missing_matches:
            by_year.setdefault(match.season, []).append(match)

        logger.info("Missing matches by year:")
        for year in sorted(by_year.keys()):
            logger.info(f"  {year}: {len(by_year[year])} matches")

        logger.info("")
        logger.info(f"Starting scrape of {len(missing_matches)} matches...")
        logger.info("")

        all_stats = []

        for i, match in enumerate(missing_matches, 1):
            home_team = self.session.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = self.session.query(Team).filter(Team.id == match.away_team_id).first()

            logger.info(
                f"[{i}/{len(missing_matches)}] {match.season} {match.round}: "
                f"{home_team.name} vs {away_team.name}"
            )

            url = self.construct_match_url(match)
            if not url:
                logger.warning(f"Could not construct URL for match {match.id}")
                continue

            stats = self.scrape_match_player_stats(match, url)
            all_stats.extend(stats)
            self.stats['matches_processed'] += 1

            # Rate limiting
            time.sleep(2)

            # Save progress every 50 matches
            if i % 50 == 0:
                self._save_stats(all_stats)
                all_stats = []
                logger.info(f"Progress saved. {i}/{len(missing_matches)} complete.")

        # Save remaining stats
        if all_stats:
            self._save_stats(all_stats)

        self._print_summary()

    def _save_stats(self, stats: List[Dict]):
        """Save stats directly to database."""
        if not stats:
            return

        from app.data.models import Player

        saved_count = 0
        skipped_count = 0

        for stat in stats:
            try:
                # Find player by name
                player = self._find_or_create_player(stat['player_name'], stat['team'])

                if not player:
                    logger.warning(f"Could not find/create player: {stat['player_name']}")
                    skipped_count += 1
                    continue

                # Check if stat already exists
                existing = self.session.query(PlayerStat).filter(
                    PlayerStat.match_id == stat['match_id'],
                    PlayerStat.player_id == player.id
                ).first()

                if existing:
                    skipped_count += 1
                    continue

                # Create new PlayerStat record
                player_stat = PlayerStat(
                    match_id=stat['match_id'],
                    player_id=player.id,
                    disposals=stat.get('disposals', 0),
                    kicks=stat.get('kicks', 0),
                    handballs=stat.get('handballs', 0),
                    marks=stat.get('marks', 0),
                    tackles=stat.get('tackles', 0),
                    goals=stat.get('goals', 0),
                    behinds=stat.get('behinds', 0),
                    hitouts=stat.get('hitouts', 0)
                )

                self.session.add(player_stat)
                saved_count += 1

                # Commit every 100 records
                if saved_count % 100 == 0:
                    self.session.commit()
                    logger.info(f"Committed {saved_count} player stats")

            except Exception as e:
                logger.error(f"Error saving stat for {stat.get('player_name')}: {e}")
                self.session.rollback()
                skipped_count += 1

        # Final commit
        try:
            self.session.commit()
            logger.info(f"Saved {saved_count} player stats, skipped {skipped_count}")
            self.stats['stats_written'] += saved_count
        except Exception as e:
            logger.error(f"Error committing final batch: {e}")
            self.session.rollback()

    def _find_or_create_player(self, player_name: str, team_name: str) -> Optional['Player']:
        """Find player by name or create if not exists."""
        from app.data.models import Player, Team

        # Try exact match first
        player = self.session.query(Player).filter(
            Player.name == player_name
        ).first()

        if player:
            return player

        # Try case-insensitive match
        player = self.session.query(Player).filter(
            Player.name.ilike(player_name)
        ).first()

        if player:
            return player

        # Try splitting name and matching on parts
        # AFL Tables format is usually "Firstname Lastname"
        parts = player_name.split()
        if len(parts) >= 2:
            # Try "Lastname, Firstname" format
            alt_name = f"{parts[-1]}, {' '.join(parts[:-1])}"
            player = self.session.query(Player).filter(
                Player.name.ilike(alt_name)
            ).first()

            if player:
                return player

        # Player not found - create new one
        logger.info(f"Creating new player: {player_name}")

        # Get team_id
        team = self.session.query(Team).filter(Team.name == team_name).first()
        team_id = team.id if team else None

        try:
            new_player = Player(
                name=player_name,
                team_id=team_id
            )
            self.session.add(new_player)
            self.session.flush()  # Get the ID without committing
            return new_player
        except Exception as e:
            logger.error(f"Error creating player {player_name}: {e}")
            self.session.rollback()
            return None

    def _print_summary(self):
        """Print scraping summary."""
        logger.info("=" * 60)
        logger.info("SCRAPING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Matches processed: {self.stats['matches_processed']}")
        logger.info(f"Players found: {self.stats['players_found']}")
        logger.info(f"Stats written: {self.stats['stats_written']}")
        logger.info(f"Errors: {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    """Run the finals scraper."""
    output_csv = "/Users/kyllhutchens/Code/AFL App/data/finals_player_stats.csv"

    with FinalsPlayerStatsScraper(output_csv) as scraper:
        scraper.scrape_all_finals()


if __name__ == "__main__":
    main()
