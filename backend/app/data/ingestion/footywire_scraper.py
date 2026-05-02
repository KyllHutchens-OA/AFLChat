"""
Footywire match stats scraper.

Used to populate the Top Performers panel and generate AI match summaries.
Scrapes cumulative player stats at quarter breaks (5 minutes into the break)
and post-game. Maximum 4 scrapes per game.

Footywire typically updates their match stats page within minutes of a quarter
ending, making it reliable for near-live data without relying on a paid API.
"""
import logging
import time
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_HEADERS = {
    'User-Agent': 'AFL-Analytics-App/1.0 (kyllhutchens@gmail.com)',
}
_REQUEST_DELAY = 2.0  # seconds between requests — be a good citizen

# Maps the URL slug from Footywire team profile links (href="/afl/footy/th-<slug>")
# to our canonical DB team names. Using slugs is unambiguous — no substring conflicts
# like 'adelaide' matching inside 'port adelaide'.
_SLUG_TO_DB_TEAM: Dict[str, str] = {
    'th-adelaide-crows': 'Adelaide',
    'th-brisbane-lions': 'Brisbane Lions',
    'th-carlton-blues': 'Carlton',
    'th-collingwood-magpies': 'Collingwood',
    'th-essendon-bombers': 'Essendon',
    'th-fremantle-dockers': 'Fremantle',
    'th-geelong-cats': 'Geelong',
    'th-gold-coast-suns': 'Gold Coast',
    'th-gws-giants': 'Greater Western Sydney',
    'th-hawthorn-hawks': 'Hawthorn',
    'th-melbourne-demons': 'Melbourne',
    'th-north-melbourne-kangaroos': 'North Melbourne',
    'th-port-adelaide-power': 'Port Adelaide',
    'th-richmond-tigers': 'Richmond',
    'th-st-kilda-saints': 'St Kilda',
    'th-sydney-swans': 'Sydney',
    'th-west-coast-eagles': 'West Coast',
    'th-western-bulldogs': 'Western Bulldogs',
}

# Fallback keyword map for when href-slug matching fails.
_TEAM_KEYWORDS: Dict[str, List[str]] = {
    'Adelaide': ['adelaide crows'],
    'Brisbane Lions': ['brisbane lions', 'brisbane'],
    'Carlton': ['carlton'],
    'Collingwood': ['collingwood'],
    'Essendon': ['essendon'],
    'Fremantle': ['fremantle'],
    'Geelong': ['geelong'],
    'Gold Coast': ['gold coast suns', 'gold coast'],
    'Greater Western Sydney': ['gws giants', 'greater western sydney', 'gws'],
    'Hawthorn': ['hawthorn'],
    'Melbourne': ['melbourne'],
    'North Melbourne': ['north melbourne'],
    'Port Adelaide': ['port adelaide'],
    'Richmond': ['richmond'],
    'St Kilda': ['st kilda'],
    'Sydney': ['sydney'],
    'West Coast': ['west coast'],
    'Western Bulldogs': ['western bulldogs'],
}


class FootywireScraper:
    """Scrapes match player statistics from Footywire."""

    BASE_URL = 'https://www.footywire.com/afl/footy'

    def __init__(self):
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._last_request_time = 0.0

    def _get(self, url: str) -> Optional[str]:
        """Rate-limited GET, returns HTML or None on failure."""
        elapsed = time.time() - self._last_request_time
        if elapsed < _REQUEST_DELAY:
            time.sleep(_REQUEST_DELAY - elapsed)
        try:
            resp = self._session.get(url, timeout=15)
            self._last_request_time = time.time()
            if resp.status_code == 200:
                return resp.text
            logger.warning(f"Footywire {resp.status_code} for {url}")
            return None
        except Exception as exc:
            logger.error(f"Footywire request failed ({url}): {exc}")
            return None

    def _team_matches(self, text: str, team_name: str) -> bool:
        """Return True if any keyword for team_name appears in text."""
        text_lower = text.lower()
        keywords = _TEAM_KEYWORDS.get(team_name, [team_name.lower()])
        return any(kw in text_lower for kw in keywords)

    def find_match_id(
        self,
        season: int,
        home_team: str,
        away_team: str,
    ) -> Optional[int]:
        """
        Scan the season match list page to find the Footywire match ID (mid).

        Each match row on ft_match_list has the structure:
          <tr><td>date</td><td>Team1 v Team2</td><td>venue</td>...<td><a href="ft_match_statistics?mid=NNN">score</a></td>...</tr>

        We find each ft_match_statistics link, walk up to the parent <tr>, and check
        that row's text for both team names. This avoids the false-positive of walking
        up to a <tbody> which contains all rows.

        Returns the integer mid or None if the game cannot be found.
        """
        html = self._get(f'{self.BASE_URL}/ft_match_list?year={season}')
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')

        for link in soup.find_all('a', href=True):
            href: str = link.get('href', '')
            if 'ft_match_statistics' not in href or 'mid=' not in href:
                continue

            try:
                mid_str = href.split('mid=')[1].split('&')[0]
                mid = int(mid_str)
            except (ValueError, IndexError):
                continue

            # Find the containing <tr> — team profile links are in a sibling <td>
            row = link.find_parent('tr')
            if not row:
                continue

            # Primary: match via team profile href slugs (unambiguous, no substring issues)
            # Footywire uses relative hrefs like 'th-adelaide-crows' (no leading slash)
            team_links = row.find_all('a', href=lambda h: h and h.startswith('th-'))
            if len(team_links) >= 2:
                slugs = [a.get('href', '').split('/')[-1] for a in team_links[:2]]
                db_teams = {_SLUG_TO_DB_TEAM.get(s) for s in slugs}
                if home_team in db_teams and away_team in db_teams:
                    logger.info(f"Footywire match ID {mid} found for {home_team} vs {away_team} ({season})")
                    return mid
                continue  # Row has team links but they don't match — don't fall through

            # Fallback: full-keyword match on row text (for pages without /th- links)
            row_text = row.get_text(' ', strip=True)
            if self._team_matches(row_text, home_team) and self._team_matches(row_text, away_team):
                logger.info(f"Footywire match ID {mid} (keyword fallback) found for {home_team} vs {away_team} ({season})")
                return mid

        logger.warning(f"No Footywire match found for {home_team} vs {away_team} ({season})")
        return None

    def scrape_match_stats(self, match_id: int) -> Optional[Dict]:
        """
        Fetch and parse player stats from a Footywire match stats page.

        Returns a dict with keys:
          top_goal_kickers, top_disposals, top_fantasy — lists of player dicts
          all_players — full list used for AI summaries and quarter snapshots
          scraped_at — UTC ISO timestamp string
          match_id — the Footywire mid
        """
        url = f'{self.BASE_URL}/ft_match_statistics?mid={match_id}&stype=P'
        html = self._get(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        all_players: List[Dict] = []

        # Footywire stats page: two per-team tables, each preceded by a team heading.
        # We identify player stat tables by looking for header rows containing
        # recognisable AFL stat abbreviations.
        # Extra tables (advanced stats, supercoach) may share the same heading — deduplicate.
        tables = soup.find_all('table')
        seen_headings: set = set()

        for table in tables:
            rows = table.find_all('tr')
            if len(rows) < 3:
                continue

            # Locate the header row
            header_texts: List[str] = []
            header_row_index = -1
            for i, row in enumerate(rows[:4]):
                cells = row.find_all(['th', 'td'])
                texts = [c.get_text(strip=True).upper() for c in cells]
                # Must have at least K (kicks) and G (goals) to be a player stat table
                if ('K' in texts or 'KI' in texts) and ('G' in texts or 'GL' in texts):
                    header_texts = texts
                    header_row_index = i
                    break

            if header_row_index == -1:
                continue

            # Build column index map
            col: Dict[str, int] = {}
            for i, text in enumerate(header_texts):
                col[text] = i

            # Resolve alternate abbreviations
            def resolve(keys: List[str]) -> Optional[int]:
                for k in keys:
                    if k in col:
                        return col[k]
                return None

            idx_name = 0  # Player name always first column
            idx_k  = resolve(['K', 'KI'])
            idx_hb = resolve(['HB'])
            idx_d  = resolve(['D', 'DI'])
            idx_m  = resolve(['M', 'MK'])
            idx_t  = resolve(['T', 'TK'])
            idx_g  = resolve(['G', 'GL'])
            idx_b  = resolve(['B', 'BH'])
            idx_ho = resolve(['HO'])
            idx_af = resolve(['AF'])  # Actual AFL Fantasy points column

            # Identify the team from the heading immediately before the table.
            # Footywire formats these as "<Team> Match Statistics (Sorted by Disposals)".
            # Skip any table whose heading doesn't follow this pattern — e.g. the
            # "View Advanced Stats" button also triggers a table parse but has wrong columns.
            team_name = 'Unknown'
            prev = table.find_previous(['h2', 'h3', 'h4', 'strong', 'b'])
            if prev:
                team_name = prev.get_text(strip=True)
            if 'match statistics' not in team_name.lower():
                continue
            if team_name in seen_headings:
                continue  # Skip duplicate tables with same heading (e.g. supercoach view)
            seen_headings.add(team_name)

            def cell_int(cells: list, idx: Optional[int]) -> int:
                if idx is None or idx >= len(cells):
                    return 0
                raw = cells[idx].get_text(strip=True)
                try:
                    return int(raw)
                except ValueError:
                    return 0

            for row in rows[header_row_index + 1:]:
                cells = row.find_all('td')
                if not cells:
                    continue

                # Player name cell
                name_cell = cells[idx_name] if idx_name < len(cells) else None
                if not name_cell:
                    continue
                name_link = name_cell.find('a')
                player_name = (name_link or name_cell).get_text(strip=True)
                if not player_name or player_name.upper() in ('TOTALS', 'TOTAL', 'PLAYER', ''):
                    continue

                kicks    = cell_int(cells, idx_k)
                handballs = cell_int(cells, idx_hb)
                disposals = cell_int(cells, idx_d) or (kicks + handballs)
                marks    = cell_int(cells, idx_m)
                tackles  = cell_int(cells, idx_t)
                goals    = cell_int(cells, idx_g)
                behinds  = cell_int(cells, idx_b)
                hitouts  = cell_int(cells, idx_ho)
                # Prefer Footywire's actual AF column; fall back to manual calculation
                af_raw = cell_int(cells, idx_af)
                fantasy = af_raw if af_raw > 0 else (
                    kicks * 3 + handballs * 2 + marks * 3 +
                    tackles * 4 + goals * 6 + behinds * 1 + hitouts * 1
                )

                # Skip completely empty rows
                if kicks == 0 and handballs == 0 and goals == 0:
                    continue

                all_players.append({
                    'name': player_name,
                    'team': team_name,
                    'goals': goals,
                    'behinds': behinds,
                    'kicks': kicks,
                    'handballs': handballs,
                    'disposals': disposals,
                    'marks': marks,
                    'tackles': tackles,
                    'hitouts': hitouts,
                    'fantasy_points': fantasy,
                })

        if not all_players:
            logger.warning(f"No player data parsed from Footywire mid={match_id} — page may not be ready yet")
            return None

        top_goals = sorted(all_players, key=lambda p: p['goals'], reverse=True)[:5]
        top_disposals = sorted(all_players, key=lambda p: p['disposals'], reverse=True)[:5]
        top_fantasy = sorted(all_players, key=lambda p: p['fantasy_points'], reverse=True)[:5]

        return {
            'top_goal_kickers': [
                {'name': p['name'], 'team': p['team'], 'goals': p['goals']}
                for p in top_goals if p['goals'] > 0
            ],
            'top_disposals': [
                {'name': p['name'], 'team': p['team'], 'disposals': p['disposals']}
                for p in top_disposals
            ],
            'top_fantasy': [
                {'name': p['name'], 'team': p['team'], 'points': p['fantasy_points']}
                for p in top_fantasy
            ],
            'all_players': all_players,
            'scraped_at': datetime.utcnow().isoformat() + 'Z',
            'match_id': match_id,
        }

    def get_top_performers(
        self,
        season: int,
        home_team: str,
        away_team: str,
    ) -> Optional[Dict]:
        """
        Find a game on Footywire and return its top performers.

        Convenience wrapper: find_match_id → scrape_match_stats.
        Returns None if the game cannot be found or stats are not yet available.
        """
        match_id = self.find_match_id(season, home_team, away_team)
        if not match_id:
            return None
        return self.scrape_match_stats(match_id)


# Module-level singleton — reuses the underlying requests.Session across calls
footywire_scraper = FootywireScraper()
