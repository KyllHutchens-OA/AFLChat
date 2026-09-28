"""Parsers for afltables.com pages (pure functions: html in, dicts out).

Season page (afl/seas/{year}.html): every match with round/finals label, venue-local
kick-off, venue, crowd, cumulative quarter scores and the match-stats URL.
Match page (afl/stats/games/{year}/{id}.html): one stats table per club with each
player's AFL Tables id (players/X/First_Last[N].html) and stat columns.

Blank cells: AFL Tables leaves zero values blank. A column counts as recorded for a
match when the season is at or after the first season AFL Tables records it
(FIRST_RECORDED) or either club's Totals cell for it is non-blank; recorded blanks
become 0, unrecorded columns stay None (contested possessions before 1999, clearances
before 1998, TOG and goal assists before 2003). Brownlow votes are recorded only when
the match's Totals show votes (none in finals).
"""
import re
from datetime import datetime
from typing import Dict, List, Optional

from bs4 import BeautifulSoup

COLUMN_MAP = {
    'KI': 'kicks', 'MK': 'marks', 'HB': 'handballs', 'DI': 'disposals',
    'GL': 'goals', 'BH': 'behinds', 'HO': 'hitouts', 'TK': 'tackles',
    'RB': 'rebound_50s', 'IF': 'inside_50s', 'CL': 'clearances', 'CG': 'clangers',
    'FF': 'free_kicks_for', 'FA': 'free_kicks_against', 'BR': 'brownlow_votes',
    'CP': 'contested_possessions', 'UP': 'uncontested_possessions',
    'CM': 'contested_marks', 'MI': 'marks_inside_50', '1%': 'one_percenters',
    'BO': 'bounces', 'GA': 'goal_assist', '%P': 'time_on_ground_pct',
}
STAT_FIELDS = list(COLUMN_MAP.values())

# Historic AFL Tables club names -> canonical `teams.name`
CLUB_ALIASES = {
    'Brisbane Bears': 'Brisbane Lions',
    'Footscray': 'Western Bulldogs',
    'Kangaroos': 'North Melbourne',
    'South Melbourne': 'Sydney',
}

# First season each stat appears on AFL Tables match pages (checked against every page 1990-2026)
FIRST_RECORDED = {
    **{f: 1990 for f in ('kicks', 'marks', 'handballs', 'disposals', 'goals', 'behinds',
                         'hitouts', 'tackles', 'free_kicks_for', 'free_kicks_against')},
    **{f: 1998 for f in ('rebound_50s', 'inside_50s', 'clearances', 'clangers')},
    **{f: 1999 for f in ('contested_possessions', 'uncontested_possessions', 'contested_marks',
                         'marks_inside_50', 'one_percenters', 'bounces')},
    'goal_assist': 2003, 'time_on_ground_pct': 2003,
}

FINALS_LABELS = ("Qualifying", "Elimination", "Semi", "Preliminary", "Grand", "Wildcard")

_DT_RE = re.compile(r"(\w{3}) (\d{2}-\w{3}-\d{4})(?: (\d{1,2}:\d{2} [AP]M))?")
_SCORE_RE = re.compile(r"(\d+)\.(\d+)")


def canonical_club(name: str) -> str:
    name = (name or '').strip()
    return CLUB_ALIASES.get(name, name)


def _quarters(text: str) -> List[tuple]:
    return [(int(g), int(b)) for g, b in _SCORE_RE.findall(text.replace('\xa0', ' '))]


def parse_season_page(html: str, year: int) -> List[Dict]:
    """Matches on a season page, in page order."""
    soup = BeautifulSoup(html, 'html.parser')
    games, label, in_finals = [], None, False
    for table in soup.find_all('table'):
        rows = table.find_all('tr', recursive=False) or table.find_all('tr')
        if len(rows) == 1:
            txt = rows[0].get_text(' ', strip=True)
            m = re.match(r'Round (\d+)\b', txt)
            if m and not table.find('tt'):
                label, in_finals = m.group(1), False
                continue
            if re.fullmatch(r'(%s) Final' % '|'.join(FINALS_LABELS), txt):
                label, in_finals = txt, True
                continue
        if len(rows) != 2 or not table.find('tt') or label is None:
            continue
        cells = [r.find_all('td', recursive=False) for r in rows]
        if any(len(c) < 4 for c in cells):
            continue
        info = cells[0][3].get_text(' ', strip=True)
        dm = _DT_RE.search(info)
        if not dm:
            continue
        dt_txt = dm.group(2) + (' ' + dm.group(3) if dm.group(3) else ' 12:00 AM')
        att = re.search(r'Att:\s*([\d,]+)', info)
        venue_a = cells[0][3].find('a')
        link = cells[1][3].find('a', href=re.compile(r'stats/games/'))
        games.append({
            'season': year, 'label': label, 'is_final': in_finals,
            'local_dt': datetime.strptime(dt_txt, '%d-%b-%Y %I:%M %p'),
            'home': cells[0][0].get_text(strip=True), 'away': cells[1][0].get_text(strip=True),
            'home_q': _quarters(cells[0][1].get_text()), 'away_q': _quarters(cells[1][1].get_text()),
            'home_score': int(cells[0][2].get_text(strip=True)),
            'away_score': int(cells[1][2].get_text(strip=True)),
            'venue': venue_a.get_text(strip=True) if venue_a else '',
            'attendance': int(att.group(1).replace(',', '')) if att else None,
            'stats_url': link['href'].replace('../', '') if link else None,
        })
    return games


def player_id_from_href(href: str) -> Optional[str]:
    """'../../players/T/Tom_Green.html' -> 'T/Tom_Green' (AFL Tables player key)."""
    m = re.search(r'players/([^"]+?)\.html?', href or '')
    return m.group(1) if m else None


def normalize_player_name(raw: str) -> str:
    """AFL Tables 'Last, First' (plus sub arrows / notes) -> 'First Last'."""
    name = re.sub(r'\s*\(.*\)', '', raw).replace('↑', '').replace('↓', '').strip()
    if ',' in name:
        last, first = name.split(',', 1)
        name = f"{first.strip()} {last.strip()}"
    return re.sub(r'\s+', ' ', name)


def _cell_value(text: str, field: str):
    text = text.replace('\xa0', ' ').strip()
    if not text:
        return None
    try:
        return float(text) if field == 'time_on_ground_pct' else int(text)
    except ValueError:
        return None


def parse_match_page(html: str, season: Optional[int] = None) -> Optional[Dict]:
    """{'date', 'attendance', 'teams': [{'club', 'players': [...]}, ...]} or None.

    Each player: {'name', 'afltables_id', **stats}. Recorded blank cells are 0.
    """
    soup = BeautifulSoup(html, 'html.parser')
    out = {'date': None, 'attendance': None, 'teams': []}
    title = soup.find('title')
    if title:
        m = re.search(r'(\d{1,2})-(\w{3})-(\d{4})', title.text)
        if m:
            out['date'] = datetime.strptime('-'.join(m.groups()), '%d-%b-%Y')
    att = re.search(r'Attendance:\s*([\d,]+)', soup.get_text(' '))
    if att:
        out['attendance'] = int(att.group(1).replace(',', ''))

    for table in soup.find_all('table'):
        head = table.find('th')
        if not head or 'Match Statistics' not in head.get_text():
            continue
        club = head.get_text(' ', strip=True).split(' Match Statistics')[0].strip()
        header_row = head.find_parent('tr').find_next_sibling('tr')
        if header_row is None:
            continue
        headers = [c.get_text(strip=True) for c in header_row.find_all(['th', 'td'])]
        cols = {COLUMN_MAP[h]: i for i, h in enumerate(headers) if h in COLUMN_MAP}
        if 'Player' not in headers:
            continue
        p_idx = headers.index('Player')

        # Totals row decides which columns were recorded for this club
        totals = {}
        tfoot = table.find('tfoot')
        if tfoot:
            for tr in tfoot.find_all('tr'):
                tds = tr.find_all('td')
                if tds and 'Totals' in tds[0].get_text():
                    # Totals row: first td spans '#' + 'Player' (colspan=2)
                    for field, i in cols.items():
                        j = i - 1
                        if 0 <= j < len(tds):
                            totals[field] = _cell_value(tds[j].get_text(), field) is not None

        players = []
        body = table.find('tbody') or table
        for tr in body.find_all('tr'):
            tds = tr.find_all('td')
            if len(tds) <= p_idx:
                continue
            a = tds[p_idx].find('a', href=True)
            if not a:
                continue
            rec = {'name': normalize_player_name(a.get_text()),
                   'afltables_id': player_id_from_href(a['href'])}
            for field, i in cols.items():
                val = _cell_value(tds[i].get_text(), field) if i < len(tds) else None
                rec[field] = val
            players.append(rec)
        out['teams'].append({'club': club, 'players': players, 'recorded': totals, 'columns': list(cols)})

    # recorded: the season records it, or either club's total is non-blank
    season = season or (out['date'].year if out['date'] else None)
    recorded = {f for t in out['teams'] for f, ok in t['recorded'].items() if ok}
    if season:
        in_header = {f for t in out['teams'] for f in t['columns']}
        recorded |= {f for f in in_header if f in FIRST_RECORDED and season >= FIRST_RECORDED[f]}
    for t in out['teams']:
        for p in t['players']:
            for f in STAT_FIELDS:
                if f not in p:
                    p[f] = None
                elif p[f] is None and f in recorded:
                    p[f] = 0
    out['recorded'] = sorted(recorded)
    return out if out['teams'] else None
