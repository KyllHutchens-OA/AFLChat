"""
Automated Player Stats Ingestion Pipeline.

Two-stage pipeline that runs on a schedule:
1. API-Sports stage (11:15 PM AEST) — basic stats available immediately after games
2. AFL Tables stage (6 AM AEST) — comprehensive stats available next morning

Only processes completed matches that are missing player stats.
Idempotent — safe to re-run without duplicating data.
"""
import logging
import re
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from app.data.database import get_session
from app.data.models import Match, Player, PlayerStat, Team, TeamStat

logger = logging.getLogger(__name__)

# AFL Tables config
AFL_TABLES_BASE_URL = "https://afltables.com/afl"
AFL_TABLES_REQUEST_DELAY = 1.5  # Respectful delay between requests

# Column header mappings from AFL Tables abbreviations
AFL_TABLES_COLUMN_MAP = {
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
    'GA': 'goal_assist',
    '%P': 'time_on_ground_pct',
}


def _get_matches_needing_stats(session, season: int = None, days_back: int = 14) -> List[Match]:
    """Find completed matches that have no player_stats rows.

    Args:
        session: DB session
        season: Specific season, defaults to current year
        days_back: Only look at matches from the last N days
    """
    if season is None:
        season = datetime.now().year

    cutoff = datetime.utcnow() - timedelta(days=days_back)

    # Subquery: match IDs that already have player stats
    matches_with_stats = (
        session.query(PlayerStat.match_id)
        .distinct()
        .subquery()
    )

    matches = (
        session.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.season == season,
            Match.match_status == "completed",
            Match.match_date >= cutoff,
            ~Match.id.in_(session.query(matches_with_stats.c.match_id)),
        )
        .order_by(Match.match_date.desc())
        .all()
    )

    return matches


def _get_matches_needing_advanced_stats(session, season: int = None, days_back: int = 14) -> List[Match]:
    """Find completed matches that have basic stats but are missing advanced stats.

    Checks for matches where player_stats exist but contested_possessions etc. are all 0/null.
    """
    if season is None:
        season = datetime.now().year

    cutoff = datetime.utcnow() - timedelta(days=days_back)

    # Subquery: match IDs that have stats but all advanced fields are 0/null
    match_ids_subquery = (
        session.query(PlayerStat.match_id)
        .join(Match, Match.id == PlayerStat.match_id)
        .filter(
            Match.season == season,
            Match.match_status == "completed",
            Match.match_date >= cutoff,
        )
        .group_by(PlayerStat.match_id)
        .having(
            func.coalesce(func.max(PlayerStat.contested_possessions), 0) == 0,
        )
        .subquery()
    )

    matches = (
        session.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(Match.id.in_(session.query(match_ids_subquery.c.match_id)))
        .all()
    )

    return matches


# ──────────────────────────────────────────────────────────────────────────────
# Stage 1: API-Sports basic stats ingestion
# ──────────────────────────────────────────────────────────────────────────────

def _find_or_create_player(session, name: str, team_id: int) -> Optional[int]:
    """Find a player by name, or create if not found.

    Handles "First Last" name format from API-Sports.
    """
    if not name or name == "Unknown" or name.isdigit():
        return None

    # Try exact match first
    player = session.query(Player).filter(
        Player.name.ilike(name)
    ).first()
    if player:
        return player.id

    # Try partial match (handles middle names, suffixes)
    player = session.query(Player).filter(
        Player.name.ilike(f"%{name}%")
    ).first()
    if player:
        return player.id

    # Try reversed name parts for "Last, First" vs "First Last"
    parts = name.split()
    if len(parts) >= 2:
        reversed_name = f"{parts[-1]}, {' '.join(parts[:-1])}"
        player = session.query(Player).filter(
            Player.name.ilike(f"%{reversed_name}%")
        ).first()
        if player:
            return player.id

        # Try "Last First" without comma
        reversed_name = f"{parts[-1]} {' '.join(parts[:-1])}"
        player = session.query(Player).filter(
            Player.name.ilike(f"%{reversed_name}%")
        ).first()
        if player:
            return player.id

    # Create new player
    first_name = parts[0] if parts else name
    last_name = parts[-1] if len(parts) > 1 else ""

    player = Player(
        name=name,
        first_name=first_name,
        last_name=last_name,
        team_id=team_id,
        is_active=True,
    )
    session.add(player)
    session.flush()
    logger.info(f"Created new player: {name} (team_id={team_id})")
    return player.id


def _calculate_fantasy_points(stats: Dict) -> int:
    """Calculate AFL fantasy points from stat values."""
    return (
        (stats.get('kicks', 0) or 0) * 3
        + (stats.get('handballs', 0) or 0) * 2
        + (stats.get('marks', 0) or 0) * 3
        + (stats.get('tackles', 0) or 0) * 4
        + (stats.get('goals', 0) or 0) * 6
        + (stats.get('behinds', 0) or 0) * 1
        + (stats.get('hitouts', 0) or 0) * 1
        + (stats.get('free_kicks_for', 0) or 0) * 1
        + (stats.get('free_kicks_against', 0) or 0) * -3
    )


def ingest_from_api_sports(season: int = None, days_back: int = 14) -> Dict:
    """Stage 1: Ingest basic player stats from API-Sports for completed matches.

    Runs at 11:15 PM AEST — basic stats available immediately after games.
    Only processes matches with no existing player_stats rows.

    Returns:
        Dict with stats about the ingestion run.
    """
    import os
    api_key = os.getenv("API_SPORTS_KEY")
    if not api_key:
        logger.warning("API_SPORTS_KEY not configured — skipping API-Sports ingestion")
        return {"skipped": True, "reason": "no_api_key"}

    from app.services.api_sports_service import APISportsService, API_SPORTS_TEAM_MAP

    result = {
        "matches_processed": 0,
        "players_created": 0,
        "stats_created": 0,
        "matches_skipped": 0,
        "errors": 0,
    }

    abbr_to_api_id = {v: k for k, v in API_SPORTS_TEAM_MAP.items()}

    with get_session() as session:
        matches = _get_matches_needing_stats(session, season, days_back)

        if not matches:
            logger.info("API-Sports ingestion: no matches need stats")
            return result

        logger.info(f"API-Sports ingestion: {len(matches)} matches need player stats")

        for match in matches:
            try:
                home_abbr = match.home_team.abbreviation
                away_abbr = match.away_team.abbreviation
                game_date = match.match_date.strftime('%Y-%m-%d') if match.match_date else None

                if not game_date:
                    result["matches_skipped"] += 1
                    continue

                # Find game in API-Sports
                api_game = APISportsService.get_game_by_teams(home_abbr, away_abbr, game_date)
                if not api_game:
                    logger.debug(f"No API-Sports game found for {home_abbr} vs {away_abbr} on {game_date}")
                    result["matches_skipped"] += 1
                    continue

                api_game_id = api_game.get('game', {}).get('id') or api_game.get('id')
                stats_data = APISportsService.get_game_player_stats(api_game_id)

                if not stats_data or 'teams' not in stats_data:
                    result["matches_skipped"] += 1
                    continue

                # Process each team's players
                home_api_id = abbr_to_api_id.get(home_abbr)
                away_api_id = abbr_to_api_id.get(away_abbr)

                for team_data in stats_data.get('teams', []):
                    team_api_id = team_data.get('team', {}).get('id')

                    if team_api_id == home_api_id:
                        team_id = match.home_team_id
                    elif team_api_id == away_api_id:
                        team_id = match.away_team_id
                    else:
                        continue

                    for player_entry in team_data.get('players', []):
                        player_info = player_entry.get('player', {})
                        api_player_id = player_info.get('id')

                        # Get player name from API-Sports cache
                        player_name = "Unknown"
                        if api_player_id:
                            cached = APISportsService.get_cached_player(api_player_id)
                            if cached:
                                player_name = cached.get('name', 'Unknown')

                        if player_name == "Unknown":
                            continue

                        player_id = _find_or_create_player(session, player_name, team_id)
                        if not player_id:
                            continue

                        # Check if stat already exists
                        existing = session.query(PlayerStat).filter_by(
                            match_id=match.id, player_id=player_id
                        ).first()
                        if existing:
                            continue

                        # Extract stats
                        goals = player_entry.get('goals', {}).get('total', 0) or 0
                        behinds = player_entry.get('behinds', 0) or 0
                        kicks = player_entry.get('kicks', 0) or 0
                        handballs = player_entry.get('handballs', 0) or 0
                        marks = player_entry.get('marks', 0) or 0
                        tackles = player_entry.get('tackles', 0) or 0
                        hitouts = player_entry.get('hitouts', 0) or 0
                        free_kicks = player_entry.get('free_kicks', {})
                        free_for = free_kicks.get('for', 0) or 0
                        free_against = free_kicks.get('against', 0) or 0
                        disposals = kicks + handballs

                        stats = {
                            'kicks': kicks, 'handballs': handballs, 'disposals': disposals,
                            'marks': marks, 'tackles': tackles, 'goals': goals, 'behinds': behinds,
                            'hitouts': hitouts, 'free_kicks_for': free_for, 'free_kicks_against': free_against,
                        }

                        player_stat = PlayerStat(
                            match_id=match.id,
                            player_id=player_id,
                            team_id=team_id,
                            **stats,
                            fantasy_points=_calculate_fantasy_points(stats),
                        )
                        session.add(player_stat)
                        result["stats_created"] += 1

                result["matches_processed"] += 1
                logger.info(
                    f"API-Sports: ingested stats for {home_abbr} vs {away_abbr} "
                    f"(R{match.round}, {game_date})"
                )

            except Exception as e:
                logger.error(f"API-Sports ingestion error for match {match.id}: {e}")
                result["errors"] += 1

        # Commit is handled by get_session context manager

    logger.info(
        f"API-Sports ingestion complete: "
        f"{result['matches_processed']} matches, "
        f"{result['stats_created']} player stats created, "
        f"{result['errors']} errors"
    )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# Stage 2: AFL Tables comprehensive stats ingestion
# ──────────────────────────────────────────────────────────────────────────────

class _AFLTablesFetcher:
    """Fetches and parses player stats from afltables.com."""

    def __init__(self):
        self.http = requests.Session()
        self.http.headers.update({
            'User-Agent': 'Mozilla/5.0 (AFL Analytics Research Project)'
        })

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        time.sleep(AFL_TABLES_REQUEST_DELAY)
        try:
            response = self.http.get(url, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            return None

    def get_season_match_urls(self, season: int) -> List[str]:
        """Get all match page URLs for a season from AFL Tables."""
        url = f"{AFL_TABLES_BASE_URL}/seas/{season}.html"
        soup = self._fetch_page(url)
        if not soup:
            return []

        match_urls = []
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            if f'stats/games/{season}/' in href:
                if href.startswith('..'):
                    href = href.replace('..', AFL_TABLES_BASE_URL)
                elif not href.startswith('http'):
                    href = f"{AFL_TABLES_BASE_URL}/{href}"
                match_urls.append(href)

        logger.info(f"AFL Tables: found {len(match_urls)} match pages for {season}")
        return match_urls

    def scrape_match_page(self, url: str) -> Optional[Dict]:
        """Scrape a single match page for team names, scores, and player stats."""
        soup = self._fetch_page(url)
        if not soup:
            return None

        result = {
            'home_team': None, 'away_team': None,
            'home_quarters': None, 'away_quarters': None,
            'home_players': [], 'away_players': [],
            'match_date': None, 'venue': None, 'round': None,
            'attendance': None,
        }

        tables = soup.find_all('table')
        if not tables:
            return None

        # Parse score table (table 0)
        score_rows = tables[0].find_all('tr')
        for row in score_rows:
            cells = row.find_all('td')
            if len(cells) >= 5:
                row_text = ' | '.join(c.text.strip() for c in cells)
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

        # Parse metadata (round, venue, attendance)
        for row in score_rows:
            text = row.text.strip()
            if 'Round:' in text:
                m = re.search(r'Round:\s*(\d+|[A-Za-z\s]+)', text)
                if m:
                    result['round'] = m.group(1).strip()
            if 'Venue:' in text:
                m = re.search(r'Venue:\s*([^←→\n]+)', text)
                if m:
                    result['venue'] = m.group(1).strip()
            if 'Att:' in text or 'Attendance:' in text:
                m = re.search(r'(?:Att|Attendance):\s*([\d,]+)', text)
                if m:
                    result['attendance'] = int(m.group(1).replace(',', ''))

        # Parse title for date
        title = soup.find('title')
        if title:
            m = re.search(r'(\d{1,2})-(\w{3})-(\d{4})', title.text)
            if m:
                try:
                    result['match_date'] = datetime.strptime(
                        f"{m.group(1)}-{m.group(2)}-{m.group(3)}", "%d-%b-%Y"
                    )
                except ValueError:
                    pass

        # Parse player stats tables
        home_parsed = False
        for table in tables[1:]:
            rows = table.find_all('tr')
            if len(rows) < 3:
                continue

            first_row_text = rows[0].text.strip()
            if any(skip in first_row_text for skip in ['Abbreviations', 'Player Details', 'Scoring progression']):
                continue

            second_row_text = rows[1].text.strip() if len(rows) > 1 else ''
            if 'KI' in second_row_text and 'Player' in second_row_text:
                players = self._parse_player_stats_table(rows)
                if not home_parsed:
                    result['home_players'] = players
                    home_parsed = True
                else:
                    result['away_players'] = players
                    break

        return result

    def _parse_quarter_scores(self, row_text: str) -> Optional[Dict]:
        pattern = r'(\d+)\.(\d+)\.\d+'
        matches = re.findall(pattern, row_text)
        if len(matches) < 4:
            return None
        return {
            'q1_goals': int(matches[0][0]), 'q1_behinds': int(matches[0][1]),
            'q2_goals': int(matches[1][0]), 'q2_behinds': int(matches[1][1]),
            'q3_goals': int(matches[2][0]), 'q3_behinds': int(matches[2][1]),
            'q4_goals': int(matches[3][0]), 'q4_behinds': int(matches[3][1]),
        }

    def _parse_player_stats_table(self, rows) -> List[Dict]:
        """Parse player stats from table rows (row 0=team, row 1=headers, row 2+=data)."""
        players = []
        header_row = rows[1]
        headers = [cell.text.strip() for cell in header_row.find_all(['th', 'td'])]

        column_indices = {}
        player_col_idx = None
        for i, header in enumerate(headers):
            if header in AFL_TABLES_COLUMN_MAP:
                column_indices[AFL_TABLES_COLUMN_MAP[header]] = i
            if header == 'Player':
                player_col_idx = i

        if player_col_idx is None:
            return players

        for row in rows[2:]:
            cells = row.find_all('td')
            if len(cells) < 3 or player_col_idx >= len(cells):
                continue

            # Skip team total/opposition rows at the bottom of AFL Tables
            first_cell = cells[0].text.strip().lower()
            if first_cell in ('totals', 'opposition', 'rushed', 'tot', 'opp'):
                continue

            player_name = cells[player_col_idx].text.strip()
            if not player_name:
                continue
            # Skip if player name is purely numeric (team total leaked into wrong column)
            if player_name.isdigit():
                continue
            player_name = re.sub(r'\s*\(.*\)', '', player_name).strip()

            stats = {'player_name': player_name}
            for field, col_idx in column_indices.items():
                if col_idx < len(cells):
                    value = cells[col_idx].text.strip()
                    if not value or value == '-':
                        stats[field] = None
                    elif field == 'time_on_ground_pct':
                        try:
                            stats[field] = float(value)
                        except ValueError:
                            stats[field] = None
                    else:
                        try:
                            stats[field] = int(value)
                        except ValueError:
                            stats[field] = None

            players.append(stats)

        return players


def _build_team_name_cache(session) -> Dict[str, int]:
    """Build a mapping from various team name forms to team IDs."""
    cache = {}
    teams = session.query(Team).all()

    # Priority 1: full names and abbreviations
    for team in teams:
        cache[team.name.lower()] = team.id
        cache[team.abbreviation.lower()] = team.id

    # Priority 2: last word of name (but don't overwrite)
    for team in teams:
        simple = team.name.split()[-1].lower()
        if simple not in cache:
            cache[simple] = team.id

    return cache


def _find_team_id(name: str, cache: Dict[str, int]) -> Optional[int]:
    """Find team ID by name using the cache."""
    if not name:
        return None
    name_lower = name.lower().strip()

    if name_lower in cache:
        return cache[name_lower]

    for cached_name, team_id in cache.items():
        if cached_name in name_lower or name_lower in cached_name:
            return team_id

    return None


def _find_match_for_scraped_game(
    session, home_team_id: int, away_team_id: int,
    season: int, match_date: Optional[datetime]
) -> Optional[Tuple[Match, bool]]:
    """Find a match in DB, returning (match, is_swapped).

    AFL Tables may list home/away differently from Squiggle, so we check both
    orientations. Also does date-range matching as a fallback since team IDs
    in the same season might match multiple times.
    """
    team_ids = {home_team_id, away_team_id}

    # Strategy 1: exact home/away by teams
    for swapped in [False, True]:
        h = away_team_id if swapped else home_team_id
        a = home_team_id if swapped else away_team_id
        matches = session.query(Match).filter(
            Match.season == season,
            Match.home_team_id == h,
            Match.away_team_id == a,
        ).all()

        if len(matches) == 1:
            return matches[0], swapped
        if matches and match_date:
            for m in matches:
                if m.match_date and m.match_date.date() == match_date.date():
                    return m, swapped
        if matches:
            return matches[0], swapped

    # Strategy 2: date-based — find any match on that date involving both teams
    # This handles cases where home/away is completely different
    if match_date:
        from sqlalchemy import or_
        date_matches = session.query(Match).filter(
            Match.season == season,
            Match.match_date >= match_date.replace(hour=0, minute=0, second=0),
            Match.match_date < match_date.replace(hour=0, minute=0, second=0) + timedelta(days=1),
        ).all()

        for m in date_matches:
            if {m.home_team_id, m.away_team_id} == team_ids:
                is_swapped = m.home_team_id != home_team_id
                return m, is_swapped

    return None, False


def _normalize_player_name(name: str) -> str:
    """Normalize AFL Tables player name format.

    AFL Tables uses "Last, First" — convert to "First Last".
    """
    if ',' in name:
        parts = name.split(',', 1)
        return f"{parts[1].strip()} {parts[0].strip()}"
    return name


def ingest_from_afl_tables(season: int = None, days_back: int = 14) -> Dict:
    """Stage 2: Scrape AFL Tables for comprehensive player stats.

    Runs at 6 AM AEST — AFL Tables typically updates overnight after games.
    Fills in advanced stats (contested possessions, inside 50s, etc.) and also
    creates stats from scratch for any matches missed by API-Sports.

    Args:
        season: Season year, defaults to current
        days_back: Only process recent matches

    Returns:
        Dict with ingestion stats
    """
    if season is None:
        season = datetime.now().year

    result = {
        "matches_processed": 0,
        "stats_created": 0,
        "stats_updated": 0,
        "quarter_scores_updated": 0,
        "players_created": 0,
        "matches_not_found": 0,
        "players_not_found": 0,
        "errors": 0,
    }

    fetcher = _AFLTablesFetcher()

    with get_session() as session:
        team_cache = _build_team_name_cache(session)

        # Get matches needing any stats (no stats at all)
        matches_no_stats = set(m.id for m in _get_matches_needing_stats(session, season, days_back))
        # Get matches needing advanced stats (have basic but not advanced)
        matches_need_advanced = set(m.id for m in _get_matches_needing_advanced_stats(session, season, days_back))

        target_match_ids = matches_no_stats | matches_need_advanced

        if not target_match_ids:
            logger.info("AFL Tables ingestion: no matches need stats updates")
            return result

        logger.info(
            f"AFL Tables ingestion: {len(matches_no_stats)} need all stats, "
            f"{len(matches_need_advanced)} need advanced stats"
        )

        # Get all match URLs for the season
        match_urls = fetcher.get_season_match_urls(season)
        if not match_urls:
            logger.warning(f"AFL Tables: no match pages found for {season}")
            return result

        # Load a player name cache for faster lookups
        player_cache: Dict[str, int] = {}  # "name_lower_teamid" -> player_id

        for url in match_urls:
            try:
                data = fetcher.scrape_match_page(url)
                if not data or not data['home_team'] or not data['away_team']:
                    continue

                home_team_id = _find_team_id(data['home_team'], team_cache)
                away_team_id = _find_team_id(data['away_team'], team_cache)

                if not home_team_id or not away_team_id:
                    continue

                # Find matching DB match
                match, is_swapped = _find_match_for_scraped_game(
                    session, home_team_id, away_team_id, season, data['match_date']
                )

                if not match or match.id not in target_match_ids:
                    continue

                # Determine correct orientation
                if is_swapped:
                    home_quarters = data['away_quarters']
                    away_quarters = data['home_quarters']
                    home_players = data['away_players']
                    away_players = data['home_players']
                    db_home_team_id = away_team_id
                    db_away_team_id = home_team_id
                else:
                    home_quarters = data['home_quarters']
                    away_quarters = data['away_quarters']
                    home_players = data['home_players']
                    away_players = data['away_players']
                    db_home_team_id = home_team_id
                    db_away_team_id = away_team_id

                # Update quarter scores if missing
                if home_quarters and not match.home_q1_goals:
                    hq = home_quarters
                    match.home_q1_goals = hq['q1_goals']
                    match.home_q1_behinds = hq['q1_behinds']
                    match.home_q2_goals = hq['q2_goals']
                    match.home_q2_behinds = hq['q2_behinds']
                    match.home_q3_goals = hq['q3_goals']
                    match.home_q3_behinds = hq['q3_behinds']
                    match.home_q4_goals = hq['q4_goals']
                    match.home_q4_behinds = hq['q4_behinds']
                    result["quarter_scores_updated"] += 1

                if away_quarters and not match.away_q1_goals:
                    aq = away_quarters
                    match.away_q1_goals = aq['q1_goals']
                    match.away_q1_behinds = aq['q1_behinds']
                    match.away_q2_goals = aq['q2_goals']
                    match.away_q2_behinds = aq['q2_behinds']
                    match.away_q3_goals = aq['q3_goals']
                    match.away_q3_behinds = aq['q3_behinds']
                    match.away_q4_goals = aq['q4_goals']
                    match.away_q4_behinds = aq['q4_behinds']
                    result["quarter_scores_updated"] += 1

                # Update attendance if missing
                if data.get('attendance') and not match.attendance:
                    match.attendance = data['attendance']

                # Process player stats for both teams
                for players, team_id in [(home_players, db_home_team_id), (away_players, db_away_team_id)]:
                    for player_data in players:
                        raw_name = player_data.get('player_name', '')
                        if not raw_name:
                            continue

                        name = _normalize_player_name(raw_name)

                        # Check player cache first
                        cache_key = f"{name.lower()}_{team_id}"
                        if cache_key in player_cache:
                            player_id = player_cache[cache_key]
                        else:
                            player_id = _find_or_create_player(session, name, team_id)
                            if player_id:
                                player_cache[cache_key] = player_id

                        if not player_id:
                            result["players_not_found"] += 1
                            continue

                        # Find or create PlayerStat
                        existing = session.query(PlayerStat).filter_by(
                            match_id=match.id, player_id=player_id
                        ).first()

                        if existing:
                            # Update with advanced stats from AFL Tables
                            updated = False
                            for field in [
                                'kicks', 'handballs', 'disposals', 'marks', 'tackles',
                                'goals', 'behinds', 'hitouts', 'clearances',
                                'inside_50s', 'rebound_50s',
                                'contested_possessions', 'uncontested_possessions',
                                'contested_marks', 'marks_inside_50',
                                'one_percenters', 'bounces', 'clangers',
                                'free_kicks_for', 'free_kicks_against',
                                'brownlow_votes', 'goal_assist', 'time_on_ground_pct',
                            ]:
                                new_val = player_data.get(field)
                                if new_val is not None:
                                    old_val = getattr(existing, field, None)
                                    # Update if the field is empty/zero or if we have advanced data
                                    if not old_val or field in (
                                        'contested_possessions', 'uncontested_possessions',
                                        'contested_marks', 'marks_inside_50',
                                        'one_percenters', 'bounces', 'clangers',
                                        'inside_50s', 'rebound_50s', 'clearances',
                                        'brownlow_votes', 'goal_assist', 'time_on_ground_pct',
                                    ):
                                        setattr(existing, field, new_val)
                                        updated = True

                            if updated:
                                # Recalculate fantasy points with all stats
                                existing.fantasy_points = _calculate_fantasy_points({
                                    'kicks': existing.kicks, 'handballs': existing.handballs,
                                    'marks': existing.marks, 'tackles': existing.tackles,
                                    'goals': existing.goals, 'behinds': existing.behinds,
                                    'hitouts': existing.hitouts,
                                    'free_kicks_for': existing.free_kicks_for,
                                    'free_kicks_against': existing.free_kicks_against,
                                })
                                result["stats_updated"] += 1
                        else:
                            # Create new stat from scratch
                            stat_fields = {}
                            for field in [
                                'kicks', 'handballs', 'disposals', 'marks', 'tackles',
                                'goals', 'behinds', 'hitouts', 'clearances',
                                'inside_50s', 'rebound_50s',
                                'contested_possessions', 'uncontested_possessions',
                                'contested_marks', 'marks_inside_50',
                                'one_percenters', 'bounces', 'clangers',
                                'free_kicks_for', 'free_kicks_against',
                                'brownlow_votes', 'goal_assist', 'time_on_ground_pct',
                            ]:
                                val = player_data.get(field)
                                if val is not None:
                                    stat_fields[field] = val

                            stat_fields['fantasy_points'] = _calculate_fantasy_points(stat_fields)

                            player_stat = PlayerStat(
                                match_id=match.id,
                                player_id=player_id,
                                team_id=team_id,
                                **stat_fields,
                            )
                            session.add(player_stat)
                            result["stats_created"] += 1

                result["matches_processed"] += 1
                logger.info(
                    f"AFL Tables: processed {data['home_team']} vs {data['away_team']} "
                    f"(R{data.get('round', '?')})"
                )

                # Remove from target set — no need to re-scrape
                target_match_ids.discard(match.id)

                # Stop early if we've processed all target matches
                if not target_match_ids:
                    logger.info("All target matches processed — stopping early")
                    break

            except Exception as e:
                logger.error(f"AFL Tables error processing {url}: {e}")
                result["errors"] += 1

    logger.info(
        f"AFL Tables ingestion complete: "
        f"{result['matches_processed']} matches, "
        f"{result['stats_created']} stats created, "
        f"{result['stats_updated']} stats updated, "
        f"{result['quarter_scores_updated']} quarter scores updated, "
        f"{result['errors']} errors"
    )
    return result
