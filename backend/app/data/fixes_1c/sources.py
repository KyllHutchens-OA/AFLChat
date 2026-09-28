"""Source-of-truth fetchers for the 1C data fixes.

AFL Tables season pages give every match (date, local time, venue, crowd,
cumulative quarter scores, finals names, match-stats URL). Squiggle gives the
round numbers (Opening Round = 0, finals numbered after the last H&A round).
Pages are cached on disk (AFL_1C_CACHE) so re-runs do not re-hit the sites.
"""
import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

CACHE_DIR = os.getenv("AFL_1C_CACHE", "/tmp/afl_1c_cache")
AFLT_BASE = "https://afltables.com/afl"
AFLT_DELAY = 1.5  # same politeness delay as stats_ingester
AFLT_UA = {"User-Agent": "Mozilla/5.0 (AFL Analytics Research Project)"}
SQUIGGLE_UA = {"User-Agent": "Footy-NAC data audit (kyll.hutchens@gmail.com)"}

# AFL Tables / Squiggle club names -> teams.id (historic names map to the modern club id)
TEAM_IDS = {
    "Adelaide": 11, "Brisbane Lions": 12, "Brisbane Bears": 12, "Carlton": 13,
    "Collingwood": 14, "Essendon": 15, "Fremantle": 16, "Geelong": 17,
    "Gold Coast": 18, "Greater Western Sydney": 19, "Hawthorn": 20,
    "Melbourne": 21, "North Melbourne": 22, "Kangaroos": 22,
    "Port Adelaide": 23, "Richmond": 24, "St Kilda": 25, "Sydney": 26,
    "West Coast": 27, "Western Bulldogs": 28, "Footscray": 28, "Fitzroy": 29,
}

_last_aflt_fetch = 0.0


def _cache_path(*parts: str) -> str:
    path = os.path.join(CACHE_DIR, *parts)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    return path


def fetch_aflt(rel_url: str, refresh: bool = False) -> str:
    """GET an afltables.com/afl page (cached, rate limited)."""
    global _last_aflt_fetch
    path = _cache_path("aflt", rel_url.strip("/").replace("/", "__"))
    if os.path.exists(path) and not refresh:
        return open(path, encoding="utf-8").read()
    wait = AFLT_DELAY - (time.time() - _last_aflt_fetch)
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(f"{AFLT_BASE}/{rel_url.lstrip('/')}", headers=AFLT_UA, timeout=(10, 45))
    _last_aflt_fetch = time.time()
    resp.raise_for_status()
    text = resp.content.decode("latin-1") if "charset" not in resp.headers.get("content-type", "") else resp.text
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return text


def squiggle_games(year: int, refresh: bool = False) -> List[Dict]:
    path = _cache_path("squiggle", f"{year}.json")
    if os.path.exists(path) and not refresh:
        return json.load(open(path))["games"]
    resp = requests.get(f"https://api.squiggle.com.au/?q=games;year={year}", headers=SQUIGGLE_UA, timeout=30)
    resp.raise_for_status()
    with open(path, "w") as f:
        f.write(resp.text)
    time.sleep(1.0)
    return resp.json()["games"]


@dataclass
class RefGame:
    """One match as published by AFL Tables (+ Squiggle round data)."""
    season: int
    label: str                    # AFL Tables round label: '1'..'25' or a finals name
    is_final: bool
    local_dt: datetime            # venue-local kick-off
    home: str
    away: str
    home_id: int
    away_id: int
    home_q: List[tuple]           # cumulative (goals, behinds) per quarter
    away_q: List[tuple]
    home_score: int
    away_score: int
    venue: str
    attendance: Optional[int]
    stats_url: Optional[str]      # 'stats/games/YYYY/....html'
    # filled by reference.build_reference
    round_number: Optional[int] = None
    round_name: Optional[str] = None
    squiggle_id: Optional[int] = None
    extra: Dict = field(default_factory=dict)

    @property
    def pair(self):
        return frozenset((self.home_id, self.away_id))


_DT_RE = re.compile(r"(\w{3}) (\d{2}-\w{3}-\d{4})(?: (\d{1,2}:\d{2} [AP]M))?")
_SCORE_RE = re.compile(r"(\d+)\.(\d+)")


def _parse_quarters(tt_text: str) -> List[tuple]:
    return [(int(g), int(b)) for g, b in _SCORE_RE.findall(tt_text.replace("\xa0", " "))]


def aflt_season(year: int, refresh: bool = False) -> List[RefGame]:
    """Parse afltables.com/afl/seas/{year}.html into RefGames in page order."""
    soup = BeautifulSoup(fetch_aflt(f"seas/{year}.html", refresh=refresh), "html.parser")
    games: List[RefGame] = []
    label, in_finals = None, False
    for table in soup.find_all("table"):
        rows = table.find_all("tr", recursive=False) or table.find_all("tr")
        # Round / finals header tables: a single bold cell
        if len(rows) == 1:
            txt = rows[0].get_text(" ", strip=True)
            m = re.match(r"Round (\d+)\b", txt)
            if m and not table.find("tt"):
                label, in_finals = m.group(1), False
                continue
            if re.fullmatch(r"(Qualifying|Elimination|Semi|Preliminary|Grand|Wildcard) Final", txt):
                label, in_finals = txt, True
                continue
        if len(rows) != 2 or not table.find("tt"):
            continue
        cells = [r.find_all("td", recursive=False) for r in rows]
        if any(len(c) < 4 for c in cells) or label is None:
            continue
        home, away = cells[0][0].get_text(strip=True), cells[1][0].get_text(strip=True)
        if home not in TEAM_IDS or away not in TEAM_IDS:
            continue
        info = cells[0][3].get_text(" ", strip=True)
        dm = _DT_RE.search(info)
        if not dm:
            continue
        dt_txt = dm.group(2) + (" " + dm.group(3) if dm.group(3) else " 12:00 AM")
        local_dt = datetime.strptime(dt_txt, "%d-%b-%Y %I:%M %p")
        att = re.search(r"Att:\s*([\d,]+)", info)
        venue_a = cells[0][3].find("a")
        link = cells[1][3].find("a", href=re.compile(r"stats/games/"))
        hq, aq = _parse_quarters(cells[0][1].get_text()), _parse_quarters(cells[1][1].get_text())
        games.append(RefGame(
            season=year, label=label, is_final=in_finals, local_dt=local_dt,
            home=home, away=away, home_id=TEAM_IDS[home], away_id=TEAM_IDS[away],
            home_q=hq, away_q=aq,
            home_score=int(cells[0][2].get_text(strip=True)),
            away_score=int(cells[1][2].get_text(strip=True)),
            venue=venue_a.get_text(strip=True) if venue_a else "",
            attendance=int(att.group(1).replace(",", "")) if att else None,
            stats_url=link["href"].replace("../", "") if link else None,
        ))
    return games
