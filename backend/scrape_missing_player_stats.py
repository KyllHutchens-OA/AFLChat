"""
Targeted Player Stats Scraper

Only scrapes players who played in matches that are missing player_stats.
Much faster than re-scraping all 12,000+ players.
"""
import sys
from pathlib import Path

# Add paths
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis")

import logging
import requests
from bs4 import BeautifulSoup
import time
from typing import List, Set, Tuple
import re

from app.data.database import Session
from app.data.models import Match, PlayerStat, Team
from player_scraper import PlayerScraper

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TargetedPlayerScraper:
    """Scrapes only players who played in missing matches."""

    BASE_URL = "https://afltables.com/afl/stats"

    # Team ID mappings for AFL Tables URLs
    TEAM_IDS = {
        "ADE": "01", "BRI": "02", "CAR": "03", "COL": "04",
        "ESS": "05", "FIT": "06", "FRE": "07", "GEE": "08",
        "GCS": "09", "GWS": "10", "HAW": "11", "MEL": "12",
        "NM": "13", "PA": "14", "RIC": "15", "STK": "16",
        "SYD": "18", "WCE": "19", "WB": "20", "UNI": "17"
    }

    def __init__(self):
        self.session = Session()
        self.player_scraper = PlayerScraper()
        self.scraped_players: Set[str] = set()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()

    def get_missing_matches(self) -> List[Match]:
        """Get all matches that don't have player_stats."""
        # Find matches without player_stats
        matches_with_stats = self.session.query(PlayerStat.match_id).distinct()

        missing_matches = (
            self.session.query(Match)
            .filter(~Match.id.in_(matches_with_stats))
            .order_by(Match.season, Match.match_date)
            .all()
        )

        return missing_matches

    def construct_match_url(self, match: Match) -> Optional[str]:
        """
        Construct AFL Tables match URL.

        Format: https://afltables.com/afl/stats/games/YYYY/TTTTYMMDD.html
        Where TTTT is team1_id(2) + team2_id(2), Y is year, MMDD is month/day
        """
        # Get team abbreviations
        home_team = self.session.query(Team).filter(Team.id == match.home_team_id).first()
        away_team = self.session.query(Team).filter(Team.id == match.away_team_id).first()

        if not home_team or not away_team:
            logger.warning(f"Could not find teams for match {match.id}")
            return None

        home_abbrev = home_team.abbreviation
        away_abbrev = away_team.abbreviation

        home_id = self.TEAM_IDS.get(home_abbrev, "00")
        away_id = self.TEAM_IDS.get(away_abbrev, "00")

        # Format date as YYYYMMDD
        date_str = match.match_date.strftime("%Y%m%d")

        game_id = f"{home_id}{away_id}{date_str}"
        url = f"{self.BASE_URL}/games/{match.season}/{game_id}.html"

        return url

    def extract_player_links_from_match(self, url: str) -> List[str]:
        """
        Extract player links from a match page.

        Returns: List of player page URLs (relative paths like "playersa/a_aaron.html")
        """
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            # Find all links to player pages
            # Player links typically look like: /afl/stats/players/A/Aaron_Aaron.html
            player_links = []

            for link in soup.find_all('a', href=True):
                href = link['href']
                # Player pages are in /afl/stats/players/ directory
                if '/players/' in href and href.endswith('.html'):
                    # Convert to relative path format used by player_scraper
                    # Example: "/afl/stats/players/A/Aaron_Aaron.html" -> "playersA/Aaron_Aaron.html"
                    match = re.search(r'/players/([A-Z])/([^/]+\.html)', href)
                    if match:
                        letter, filename = match.groups()
                        relative_path = f"players{letter}/{filename}"
                        player_links.append(relative_path)

            return list(set(player_links))  # Remove duplicates

        except Exception as e:
            logger.error(f"Error extracting players from {url}: {e}")
            return []

    def scrape_missing_player_stats(self, folder_path: str):
        """
        Main method: Scrape player stats for all missing matches.
        """
        logger.info("=" * 60)
        logger.info("Targeted Player Stats Scraper")
        logger.info("=" * 60)

        # Get missing matches
        missing_matches = self.get_missing_matches()
        logger.info(f"Found {len(missing_matches)} matches without player_stats")

        # Group by year for reporting
        by_year = {}
        for match in missing_matches:
            by_year.setdefault(match.season, []).append(match)

        for year, matches in sorted(by_year.items()):
            logger.info(f"  {year}: {len(matches)} matches")

        # Track unique players to scrape
        all_player_links: Set[str] = set()
        match_count = 0

        # Extract player links from each match
        for match in missing_matches:
            match_count += 1

            # Construct match URL
            url = self.construct_match_url(match)
            if not url:
                continue

            home_team = self.session.query(Team).filter(Team.id == match.home_team_id).first()
            away_team = self.session.query(Team).filter(Team.id == match.away_team_id).first()

            logger.info(
                f"[{match_count}/{len(missing_matches)}] "
                f"{match.season} R{match.round}: {home_team.name} vs {away_team.name}"
            )
            logger.info(f"  URL: {url}")

            # Extract player links
            player_links = self.extract_player_links_from_match(url)
            logger.info(f"  Found {len(player_links)} players")

            all_player_links.update(player_links)

            # Rate limiting
            time.sleep(1)

        logger.info("=" * 60)
        logger.info(f"Total unique players to scrape: {len(all_player_links)}")
        logger.info("=" * 60)

        # Now scrape each unique player
        player_count = 0
        for player_link in sorted(all_player_links):
            player_count += 1

            if player_link in self.scraped_players:
                logger.info(f"[{player_count}/{len(all_player_links)}] Skipping {player_link} (already scraped)")
                continue

            logger.info(f"[{player_count}/{len(all_player_links)}] Scraping {player_link}")

            try:
                self.player_scraper._process_player(player_link, folder_path)
                self.scraped_players.add(player_link)
                time.sleep(2)  # Rate limiting
            except Exception as e:
                logger.error(f"Error scraping {player_link}: {e}")
                continue

        logger.info("=" * 60)
        logger.info(f"Player scraping complete! Scraped {len(self.scraped_players)} players")
        logger.info("=" * 60)


def main():
    """Run the targeted player scraper."""
    output_dir = "/Users/kyllhutchens/Code/AFL App/data/afl-data-analysis/data/players"

    with TargetedPlayerScraper() as scraper:
        scraper.scrape_missing_player_stats(output_dir)


if __name__ == "__main__":
    main()
