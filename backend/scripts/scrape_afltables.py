#!/usr/bin/env python3
"""
AFL Tables Scraper - Fetches missing data from afltables.com

This script scrapes quarter-by-quarter scores and detailed player statistics
that aren't available from API-Sports or Squiggle.

Data fetched:
- Match: Q1, Q2, Q3 quarter scores (goals and behinds)
- PlayerStat: inside_50s, rebound_50s, contested_possessions, uncontested_possessions,
              contested_marks, marks_inside_50, one_percenters, bounces, clangers,
              time_on_ground_pct

Usage:
    # Scrape and update 2026 data
    python scripts/scrape_afltables.py --season 2026

    # Scrape specific rounds
    python scripts/scrape_afltables.py --season 2026 --rounds 0,1

    # Dry run
    python scripts/scrape_afltables.py --season 2026 --dry-run
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import argparse
import logging
import re
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from app.data.database import get_session
from app.data.models import Match, PlayerStat, Player, Team

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

BASE_URL = "https://afltables.com/afl"
REQUEST_DELAY = 1.0  # Be respectful to the server


@dataclass
class QuarterScores:
    """Quarter-by-quarter scores for a team."""
    q1_goals: int
    q1_behinds: int
    q2_goals: int
    q2_behinds: int
    q3_goals: int
    q3_behinds: int
    q4_goals: int
    q4_behinds: int


@dataclass
class PlayerGameStats:
    """Player statistics from a match."""
    player_name: str
    kicks: Optional[int] = None
    marks: Optional[int] = None
    handballs: Optional[int] = None
    disposals: Optional[int] = None
    goals: Optional[int] = None
    behinds: Optional[int] = None
    hitouts: Optional[int] = None
    tackles: Optional[int] = None
    rebound_50s: Optional[int] = None
    inside_50s: Optional[int] = None
    clearances: Optional[int] = None
    clangers: Optional[int] = None
    free_kicks_for: Optional[int] = None
    free_kicks_against: Optional[int] = None
    brownlow_votes: Optional[int] = None
    contested_possessions: Optional[int] = None
    uncontested_possessions: Optional[int] = None
    contested_marks: Optional[int] = None
    marks_inside_50: Optional[int] = None
    one_percenters: Optional[int] = None
    bounces: Optional[int] = None
    goal_assists: Optional[int] = None
    time_on_ground_pct: Optional[float] = None


class AFLTablesScraper:
    """Scraper for AFL Tables website."""

    # Column header mappings from AFL Tables abbreviations to our field names
    COLUMN_MAP = {
        'KI': 'kicks',
        'MK': 'marks',
        'HB': 'handballs',
        'DI': 'disposals',
        'GL': 'goals',
        'BH': 'behinds',
        'HO': 'hitouts',
        'TK': 'tackles',
        'RB': 'rebound_50s',
        'IF': 'inside_50s',
        'CL': 'clearances',
        'CG': 'clangers',
        'FF': 'free_kicks_for',
        'FA': 'free_kicks_against',
        'BR': 'brownlow_votes',
        'CP': 'contested_possessions',
        'UP': 'uncontested_possessions',
        'CM': 'contested_marks',
        'MI': 'marks_inside_50',
        '1%': 'one_percenters',
        'BO': 'bounces',
        'GA': 'goal_assists',
        '%P': 'time_on_ground_pct',
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (AFL Analytics Research Project)'
        })

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page."""
        try:
            time.sleep(REQUEST_DELAY)  # Rate limiting
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def get_season_match_urls(self, season: int) -> List[str]:
        """Get all match URLs for a season."""
        url = f"{BASE_URL}/seas/{season}.html"
        soup = self._fetch_page(url)

        if not soup:
            return []

        match_urls = []
        links = soup.find_all('a', href=True)

        for link in links:
            href = link.get('href', '')
            if f'stats/games/{season}/' in href:
                # Convert relative URL to absolute
                if href.startswith('..'):
                    href = href.replace('..', BASE_URL)
                elif not href.startswith('http'):
                    href = f"{BASE_URL}/{href}"
                match_urls.append(href)

        logger.info(f"Found {len(match_urls)} matches for {season}")
        return match_urls

    def _parse_quarter_scores(self, row_text: str) -> Optional[QuarterScores]:
        """
        Parse quarter scores from a row like:
        'Sydney | 4.3.27 | 6.4.40 | 11.5.71 | 11.10.76'

        These are CUMULATIVE scores - we keep them as-is to match historical data format.
        """
        # Pattern: goals.behinds.total
        pattern = r'(\d+)\.(\d+)\.\d+'
        matches = re.findall(pattern, row_text)

        if len(matches) < 4:
            return None

        # Convert to integers - keep as cumulative to match historical data
        q1_goals, q1_behinds = int(matches[0][0]), int(matches[0][1])
        q2_goals, q2_behinds = int(matches[1][0]), int(matches[1][1])
        q3_goals, q3_behinds = int(matches[2][0]), int(matches[2][1])
        q4_goals, q4_behinds = int(matches[3][0]), int(matches[3][1])

        return QuarterScores(
            q1_goals=q1_goals, q1_behinds=q1_behinds,
            q2_goals=q2_goals, q2_behinds=q2_behinds,
            q3_goals=q3_goals, q3_behinds=q3_behinds,
            q4_goals=q4_goals, q4_behinds=q4_behinds,
        )

    def _parse_int(self, value: str) -> Optional[int]:
        """Parse integer from string, handling empty values."""
        value = value.strip()
        if not value or value == '-':
            return None
        try:
            return int(value)
        except ValueError:
            return None

    def _parse_float(self, value: str) -> Optional[float]:
        """Parse float from string."""
        value = value.strip()
        if not value or value == '-':
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _parse_player_stats_table(
        self, table: BeautifulSoup, team_name: str
    ) -> List[PlayerGameStats]:
        """Parse a player statistics table."""
        players = []
        rows = table.find_all('tr')

        if len(rows) < 2:
            return players

        # Parse header row to get column indices
        header_row = rows[0]
        headers = [th.text.strip() for th in header_row.find_all(['th', 'td'])]

        # Map header positions to our field names
        column_indices = {}
        for i, header in enumerate(headers):
            if header in self.COLUMN_MAP:
                column_indices[self.COLUMN_MAP[header]] = i

        # Parse player rows
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue

            # Player name is usually in cell 1 (cell 0 is jersey number)
            player_name = cells[1].text.strip() if len(cells) > 1 else None
            if not player_name or player_name == 'Player':
                continue

            # Clean player name (remove any extra info)
            player_name = re.sub(r'\s*\(.*\)', '', player_name).strip()

            # Parse stats
            stats = PlayerGameStats(player_name=player_name)

            for field, col_idx in column_indices.items():
                if col_idx < len(cells):
                    value = cells[col_idx].text.strip()
                    if field == 'time_on_ground_pct':
                        setattr(stats, field, self._parse_float(value))
                    else:
                        setattr(stats, field, self._parse_int(value))

            players.append(stats)

        return players

    def scrape_match(self, url: str) -> Optional[Dict]:
        """
        Scrape a single match page.

        Returns dict with:
        - home_team: str
        - away_team: str
        - home_quarters: QuarterScores
        - away_quarters: QuarterScores
        - home_players: List[PlayerGameStats]
        - away_players: List[PlayerGameStats]
        - match_date: datetime
        - venue: str
        - round: str
        """
        soup = self._fetch_page(url)
        if not soup:
            return None

        result = {
            'home_team': None,
            'away_team': None,
            'home_quarters': None,
            'away_quarters': None,
            'home_players': [],
            'away_players': [],
            'match_date': None,
            'venue': None,
            'round': None,
        }

        tables = soup.find_all('table')
        if not tables:
            return None

        # Table 0 typically has quarter scores
        score_table = tables[0]
        score_rows = score_table.find_all('tr')

        for row in score_rows:
            cells = row.find_all('td')
            if len(cells) >= 5:
                row_text = ' | '.join(c.text.strip() for c in cells)

                # Check if this looks like a score row (has the pattern X.Y.Z)
                if re.search(r'\d+\.\d+\.\d+', row_text):
                    team_name = cells[0].text.strip()
                    quarters = self._parse_quarter_scores(row_text)

                    if quarters:
                        if result['home_team'] is None:
                            result['home_team'] = team_name
                            result['home_quarters'] = quarters
                        elif result['away_team'] is None:
                            result['away_team'] = team_name
                            result['away_quarters'] = quarters

        # Find venue and round from table 0
        for row in score_rows:
            text = row.text.strip()
            if 'Round:' in text:
                round_match = re.search(r'Round:\s*(\d+|[A-Za-z\s]+)', text)
                if round_match:
                    result['round'] = round_match.group(1).strip()
            if 'Venue:' in text:
                venue_match = re.search(r'Venue:\s*([^←→]+)', text)
                if venue_match:
                    result['venue'] = venue_match.group(1).strip()

        # Parse title for date
        title = soup.find('title')
        if title:
            date_match = re.search(r'(\d{1,2})-(\w{3})-(\d{4})', title.text)
            if date_match:
                try:
                    result['match_date'] = datetime.strptime(
                        f"{date_match.group(1)}-{date_match.group(2)}-{date_match.group(3)}",
                        "%d-%b-%Y"
                    )
                except ValueError:
                    pass

        # Find player stats tables - they have "Match Statistics" in the first row
        # and column headers (KI, MK, HB, etc.) in the second row
        home_parsed = False
        for table in tables[1:]:
            rows = table.find_all('tr')
            if len(rows) < 3:  # Need at least header + 1 player row
                continue

            first_row_text = rows[0].text.strip()

            # Skip non-player tables
            if 'Abbreviations' in first_row_text:
                continue
            if 'Player Details' in first_row_text:
                continue
            if 'Scoring progression' in first_row_text:
                continue

            # Check if second row has column headers
            second_row_text = rows[1].text.strip() if len(rows) > 1 else ''
            if 'KI' in second_row_text and 'Player' in second_row_text:
                # This is a player stats table
                # Parse with header in row 1, data starting from row 2
                players = self._parse_player_stats_table_v2(table)

                if not home_parsed:
                    result['home_players'] = players
                    home_parsed = True
                else:
                    result['away_players'] = players
                    break

        return result

    def _parse_player_stats_table_v2(self, table: BeautifulSoup) -> List[PlayerGameStats]:
        """Parse a player statistics table (AFL Tables format)."""
        players = []
        rows = table.find_all('tr')

        if len(rows) < 3:
            return players

        # Row 0 is team name, Row 1 is headers, Row 2+ is player data
        header_row = rows[1]
        headers = [cell.text.strip() for cell in header_row.find_all(['th', 'td'])]

        # Map header positions to our field names
        column_indices = {}
        for i, header in enumerate(headers):
            if header in self.COLUMN_MAP:
                column_indices[self.COLUMN_MAP[header]] = i

        # Find Player column index
        player_col_idx = None
        for i, h in enumerate(headers):
            if h == 'Player':
                player_col_idx = i
                break

        if player_col_idx is None:
            return players

        # Parse player rows (starting from row 2)
        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) < 3:
                continue

            # Get player name
            if player_col_idx >= len(cells):
                continue

            player_name = cells[player_col_idx].text.strip()
            if not player_name:
                continue

            # Clean player name (remove any extra info, handle "Last, First" format)
            player_name = re.sub(r'\s*\(.*\)', '', player_name).strip()

            # Parse stats
            stats = PlayerGameStats(player_name=player_name)

            for field, col_idx in column_indices.items():
                if col_idx < len(cells):
                    value = cells[col_idx].text.strip()
                    if field == 'time_on_ground_pct':
                        setattr(stats, field, self._parse_float(value))
                    else:
                        setattr(stats, field, self._parse_int(value))

            players.append(stats)

        return players


class AFLTablesUpdater:
    """Updates database with scraped AFL Tables data."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.scraper = AFLTablesScraper()
        self.team_cache: Dict[str, int] = {}
        self.player_cache: Dict[str, int] = {}
        self.stats = {
            'matches_updated': 0,
            'player_stats_updated': 0,
            'matches_not_found': 0,
            'players_not_found': 0,
            'errors': 0,
        }

    def _load_caches(self, session):
        """Load team and player name caches."""
        # Load teams
        teams = session.query(Team).all()

        # First pass: add full names and abbreviations (highest priority)
        for team in teams:
            self.team_cache[team.name.lower()] = team.id
            self.team_cache[team.abbreviation.lower()] = team.id

        # Second pass: add simple names only if not already taken
        # This avoids "Port Adelaide" overwriting "Adelaide"
        for team in teams:
            simple_name = team.name.split()[-1].lower()
            if simple_name not in self.team_cache:
                self.team_cache[simple_name] = team.id

        logger.info(f"Loaded {len(teams)} teams into cache")

    def _find_team_id(self, team_name: str) -> Optional[int]:
        """Find team ID by name."""
        if not team_name:
            return None

        name_lower = team_name.lower().strip()

        # Direct lookup
        if name_lower in self.team_cache:
            return self.team_cache[name_lower]

        # Try partial matches
        for cached_name, team_id in self.team_cache.items():
            if cached_name in name_lower or name_lower in cached_name:
                return team_id

        return None

    def _find_player(self, session, player_name: str, team_id: int) -> Optional[int]:
        """Find player ID by name."""
        # Normalize name (Last, First -> First Last)
        if ',' in player_name:
            parts = player_name.split(',')
            player_name = f"{parts[1].strip()} {parts[0].strip()}"

        # Check cache
        cache_key = f"{player_name.lower()}_{team_id}"
        if cache_key in self.player_cache:
            return self.player_cache[cache_key]

        # Query database
        player = session.query(Player).filter(
            Player.name.ilike(f"%{player_name}%")
        ).first()

        if player:
            self.player_cache[cache_key] = player.id
            return player.id

        return None

    def _find_match(
        self, session, home_team_id: int, away_team_id: int,
        season: int, match_date: datetime
    ) -> Optional[Tuple[Match, bool]]:
        """Find a match in the database.

        Returns:
            Tuple of (match, is_swapped) where is_swapped indicates if
            home/away are reversed from the scraped data.
        """
        # Try exact home/away match first
        matches = session.query(Match).filter(
            Match.season == season,
            Match.home_team_id == home_team_id,
            Match.away_team_id == away_team_id
        ).all()

        if len(matches) == 1:
            return matches[0], False

        # If multiple matches, try to match by date
        if matches and match_date:
            for match in matches:
                if match.match_date and match.match_date.date() == match_date.date():
                    return match, False

        if matches:
            return matches[0], False

        # Try with swapped home/away (AFL Tables might list differently)
        matches = session.query(Match).filter(
            Match.season == season,
            Match.home_team_id == away_team_id,
            Match.away_team_id == home_team_id
        ).all()

        if len(matches) == 1:
            return matches[0], True

        if matches and match_date:
            for match in matches:
                if match.match_date and match.match_date.date() == match_date.date():
                    return match, True

        if matches:
            return matches[0], True

        return None, False

    def update_from_url(self, session, url: str, season: int) -> bool:
        """Update database from a single match URL."""
        data = self.scraper.scrape_match(url)
        if not data:
            logger.warning(f"Failed to scrape {url}")
            self.stats['errors'] += 1
            return False

        home_team_id = self._find_team_id(data['home_team'])
        away_team_id = self._find_team_id(data['away_team'])

        if not home_team_id or not away_team_id:
            logger.warning(f"Could not find teams: {data['home_team']} vs {data['away_team']}")
            self.stats['matches_not_found'] += 1
            return False

        # Find match in database
        result = self._find_match(session, home_team_id, away_team_id, season, data['match_date'])
        match, is_swapped = result

        if not match:
            logger.warning(f"Match not found in DB: {data['home_team']} vs {data['away_team']}")
            self.stats['matches_not_found'] += 1
            return False

        if is_swapped:
            logger.info(f"Updating (swapped): {data['home_team']} vs {data['away_team']}")
            # Swap the scraped data to match DB orientation
            home_quarters = data['away_quarters']
            away_quarters = data['home_quarters']
            home_players = data['away_players']
            away_players = data['home_players']
            db_home_team_id = away_team_id
            db_away_team_id = home_team_id
        else:
            logger.info(f"Updating: {data['home_team']} vs {data['away_team']}")
            home_quarters = data['home_quarters']
            away_quarters = data['away_quarters']
            home_players = data['home_players']
            away_players = data['away_players']
            db_home_team_id = home_team_id
            db_away_team_id = away_team_id

        if self.dry_run:
            logger.info("  [DRY RUN] Would update match and player stats")
            return True

        # Update quarter scores
        if home_quarters:
            hq = home_quarters
            match.home_q1_goals = hq.q1_goals
            match.home_q1_behinds = hq.q1_behinds
            match.home_q2_goals = hq.q2_goals
            match.home_q2_behinds = hq.q2_behinds
            match.home_q3_goals = hq.q3_goals
            match.home_q3_behinds = hq.q3_behinds
            match.home_q4_goals = hq.q4_goals
            match.home_q4_behinds = hq.q4_behinds

        if away_quarters:
            aq = away_quarters
            match.away_q1_goals = aq.q1_goals
            match.away_q1_behinds = aq.q1_behinds
            match.away_q2_goals = aq.q2_goals
            match.away_q2_behinds = aq.q2_behinds
            match.away_q3_goals = aq.q3_goals
            match.away_q3_behinds = aq.q3_behinds
            match.away_q4_goals = aq.q4_goals
            match.away_q4_behinds = aq.q4_behinds

        self.stats['matches_updated'] += 1

        # Update player stats (using potentially swapped data)
        all_players = [
            (home_players, db_home_team_id),
            (away_players, db_away_team_id)
        ]

        for players, team_id in all_players:
            for player_data in players:
                player_id = self._find_player(session, player_data.player_name, team_id)

                if not player_id:
                    self.stats['players_not_found'] += 1
                    continue

                # Find or create player stat
                player_stat = session.query(PlayerStat).filter_by(
                    match_id=match.id,
                    player_id=player_id
                ).first()

                if not player_stat:
                    # Create new player stat if it doesn't exist
                    player_stat = PlayerStat(
                        match_id=match.id,
                        player_id=player_id,
                        team_id=team_id
                    )
                    session.add(player_stat)

                # Update fields that are missing/zero from API-Sports
                if player_data.inside_50s is not None:
                    player_stat.inside_50s = player_data.inside_50s
                if player_data.rebound_50s is not None:
                    player_stat.rebound_50s = player_data.rebound_50s
                if player_data.contested_possessions is not None:
                    player_stat.contested_possessions = player_data.contested_possessions
                if player_data.uncontested_possessions is not None:
                    player_stat.uncontested_possessions = player_data.uncontested_possessions
                if player_data.contested_marks is not None:
                    player_stat.contested_marks = player_data.contested_marks
                if player_data.marks_inside_50 is not None:
                    player_stat.marks_inside_50 = player_data.marks_inside_50
                if player_data.one_percenters is not None:
                    player_stat.one_percenters = player_data.one_percenters
                if player_data.bounces is not None:
                    player_stat.bounces = player_data.bounces
                if player_data.clangers is not None:
                    player_stat.clangers = player_data.clangers
                if player_data.time_on_ground_pct is not None:
                    player_stat.time_on_ground_pct = player_data.time_on_ground_pct
                if player_data.goal_assists is not None:
                    player_stat.goal_assist = player_data.goal_assists

                self.stats['player_stats_updated'] += 1

        return True

    def update_season(self, season: int, rounds: List[int] = None):
        """Update all matches for a season."""
        match_urls = self.scraper.get_season_match_urls(season)

        if not match_urls:
            logger.warning(f"No matches found for {season}")
            return

        with get_session() as session:
            self._load_caches(session)

            for url in match_urls:
                try:
                    self.update_from_url(session, url, season)
                except Exception as e:
                    logger.error(f"Error processing {url}: {e}")
                    self.stats['errors'] += 1

            if not self.dry_run:
                session.commit()
                logger.info("Changes committed")

    def print_summary(self):
        """Print update summary."""
        logger.info("\n" + "=" * 60)
        logger.info("AFL TABLES SCRAPE COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Matches updated:        {self.stats['matches_updated']}")
        logger.info(f"Player stats updated:   {self.stats['player_stats_updated']}")
        logger.info(f"Matches not found:      {self.stats['matches_not_found']}")
        logger.info(f"Players not found:      {self.stats['players_not_found']}")
        logger.info(f"Errors:                 {self.stats['errors']}")
        logger.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Scrape AFL Tables for missing match and player data"
    )
    parser.add_argument(
        "--season", type=int, default=datetime.now().year,
        help="Season to scrape (default: current year)"
    )
    parser.add_argument(
        "--rounds", type=str, default=None,
        help="Comma-separated list of rounds (not implemented yet)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be done without making changes"
    )

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info(f"AFL Tables Scraper - Season {args.season}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("=" * 60)

    updater = AFLTablesUpdater(dry_run=args.dry_run)
    updater.update_season(args.season)
    updater.print_summary()


if __name__ == "__main__":
    main()
