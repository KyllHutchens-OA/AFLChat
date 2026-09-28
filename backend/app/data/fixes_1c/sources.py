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

from app.data.ingestion.afltables_pages import parse_match_page, parse_season_page

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


def aflt_season(year: int, refresh: bool = False) -> List[RefGame]:
    """Parse afltables.com/afl/seas/{year}.html into RefGames in page order."""
    games = []
    for d in parse_season_page(fetch_aflt(f"seas/{year}.html", refresh=refresh), year):
        if d["home"] not in TEAM_IDS or d["away"] not in TEAM_IDS:
            continue
        games.append(RefGame(
            season=year, label=d["label"], is_final=d["is_final"], local_dt=d["local_dt"],
            home=d["home"], away=d["away"], home_id=TEAM_IDS[d["home"]], away_id=TEAM_IDS[d["away"]],
            home_q=d["home_q"], away_q=d["away_q"], home_score=d["home_score"],
            away_score=d["away_score"], venue=d["venue"], attendance=d["attendance"],
            stats_url=d["stats_url"],
        ))
    return games


def aflt_match_page(stats_url: str) -> Optional[Dict]:
    """Parsed match page (cached)."""
    return parse_match_page(fetch_aflt(stats_url))
