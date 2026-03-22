"""
Match Preview Service - Generates casual pre-game previews for upcoming AFL matches.
Combines weather (Open-Meteo, free), injury news (DB), and odds (DB) with a cheap
gpt-5-nano call to produce a 1-2 sentence preview per match.
"""
import logging
import os
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import httpx
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

client = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    timeout=httpx.Timeout(15.0, connect=5.0),
)

# AFL venue coordinates for Open-Meteo weather lookups
VENUE_COORDS: Dict[str, tuple] = {
    # Victoria
    "MCG": (-37.82, 144.98),
    "M.C.G.": (-37.82, 144.98),
    "Melbourne Cricket Ground": (-37.82, 144.98),
    "Marvel Stadium": (-37.82, 144.95),
    "Docklands": (-37.82, 144.95),
    "GMHBA Stadium": (-38.16, 144.35),
    "Kardinia Park": (-38.16, 144.35),
    "Mars Stadium": (-37.55, 143.85),
    # South Australia
    "Adelaide Oval": (-34.92, 138.60),
    # Western Australia
    "Optus Stadium": (-31.95, 115.89),
    "Perth Stadium": (-31.95, 115.89),
    # New South Wales
    "SCG": (-33.89, 151.22),
    "Sydney Cricket Ground": (-33.89, 151.22),
    "ENGIE Stadium": (-33.85, 151.07),
    "Sydney Showground Stadium": (-33.85, 151.07),
    "Giants Stadium": (-33.85, 151.07),
    "Manuka Oval": (-35.32, 149.13),
    # Queensland
    "Gabba": (-27.49, 153.04),
    "The Gabba": (-27.49, 153.04),
    "Brisbane Cricket Ground": (-27.49, 153.04),
    "People First Stadium": (-28.01, 153.37),
    "Heritage Bank Stadium": (-28.01, 153.37),
    "Metricon Stadium": (-28.01, 153.37),
    "Cazaly's Stadium": (-16.94, 145.76),
    # Tasmania
    "Blundstone Arena": (-42.88, 147.37),
    "UTAS Stadium": (-41.43, 147.14),
    "University of Tasmania Stadium": (-41.43, 147.14),
    # Northern Territory
    "TIO Stadium": (-12.43, 130.87),
    "TIO Traeger Park": (-23.70, 133.88),
}

# WMO weather codes → short descriptions
_WEATHER_CODES = {
    0: "clear skies",
    1: "mostly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    71: "light snow",
    73: "snow",
    80: "light showers",
    81: "showers",
    82: "heavy showers",
    95: "thunderstorms",
    96: "thunderstorms with hail",
}

# In-memory cache: squiggle_game_id → { preview: str, generated_at: float }
_preview_cache: Dict[int, Dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 24 * 3600  # 24 hours


def get_cached_preview(squiggle_id: int) -> Optional[str]:
    """Get a cached preview if it exists and hasn't expired."""
    entry = _preview_cache.get(squiggle_id)
    if entry and (time.time() - entry["generated_at"]) < _CACHE_TTL_SECONDS:
        return entry["preview"]
    return None


def _fetch_weather(venue: str, match_date: datetime) -> Optional[Dict]:
    """
    Fetch weather forecast from Open-Meteo (free, no API key).

    Returns dict with 'max_temp', 'conditions' or None.
    """
    coords = VENUE_COORDS.get(venue)
    if not coords:
        # Try partial match
        venue_lower = venue.lower()
        for name, c in VENUE_COORDS.items():
            if name.lower() in venue_lower or venue_lower in name.lower():
                coords = c
                break
    if not coords:
        return None

    # Open-Meteo only forecasts ~16 days ahead
    days_ahead = (match_date.date() - datetime.utcnow().date()).days
    if days_ahead < 0 or days_ahead > 15:
        return None

    lat, lon = coords
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "temperature_2m_max,weathercode,precipitation_probability_max",
                "timezone": "Australia/Melbourne",
                "forecast_days": min(days_ahead + 1, 16),
            },
            timeout=5.0,
        )
        if resp.status_code != 200:
            return None

        data = resp.json()
        daily = data.get("daily", {})
        dates = daily.get("time", [])
        target_date = match_date.strftime("%Y-%m-%d")

        if target_date not in dates:
            return None

        idx = dates.index(target_date)
        max_temp = daily.get("temperature_2m_max", [None])[idx]
        weather_code = daily.get("weathercode", [None])[idx]
        precip_prob = daily.get("precipitation_probability_max", [None])[idx]

        conditions = _WEATHER_CODES.get(weather_code, "")

        return {
            "max_temp": round(max_temp) if max_temp is not None else None,
            "conditions": conditions,
            "rain_chance": precip_prob,
        }
    except Exception as e:
        logger.debug(f"Weather fetch failed for {venue}: {e}")
        return None


def _fetch_team_context(home_team: str, away_team: str) -> Dict:
    """
    Query DB for recent injury news and betting odds for both teams.
    Returns a context dict with injuries, news headlines, and odds.
    """
    context: Dict[str, Any] = {
        "injuries": [],
        "news": [],
        "odds": None,
    }

    try:
        from app.data.database import get_session
        from app.data.models import NewsArticle, BettingOdds, Match, Team
        from sqlalchemy import or_, func, desc

        with get_session() as session:
            # Recent injury news (last 7 days) mentioning either team
            week_ago = datetime.utcnow() - timedelta(days=7)
            injury_articles = (
                session.query(NewsArticle)
                .filter(
                    NewsArticle.is_injury_related == True,
                    NewsArticle.published_date >= week_ago,
                )
                .order_by(NewsArticle.published_date.desc())
                .limit(20)
                .all()
            )

            for article in injury_articles:
                teams = article.related_teams or []
                if home_team in teams or away_team in teams:
                    if article.injury_details:
                        for injury in article.injury_details:
                            context["injuries"].append({
                                "player": injury.get("player", "Unknown"),
                                "team": home_team if home_team in teams else away_team,
                                "type": injury.get("type", ""),
                                "severity": injury.get("severity", ""),
                            })
                    if article.summary:
                        context["news"].append(article.summary)

            # Recent non-injury news
            recent_news = (
                session.query(NewsArticle)
                .filter(
                    NewsArticle.is_afl == True,
                    NewsArticle.is_injury_related == False,
                    NewsArticle.published_date >= week_ago,
                )
                .order_by(NewsArticle.published_date.desc())
                .limit(30)
                .all()
            )

            for article in recent_news:
                teams = article.related_teams or []
                if (home_team in teams or away_team in teams) and article.summary:
                    context["news"].append(article.summary)

            # Deduplicate and limit
            context["news"] = list(dict.fromkeys(context["news"]))[:5]

            # Latest odds - find matching upcoming match
            home_team_obj = session.query(Team).filter_by(name=home_team).first()
            away_team_obj = session.query(Team).filter_by(name=away_team).first()

            if home_team_obj and away_team_obj:
                match = (
                    session.query(Match)
                    .filter(
                        Match.home_team_id == home_team_obj.id,
                        Match.away_team_id == away_team_obj.id,
                        Match.match_date >= datetime.utcnow() - timedelta(days=1),
                    )
                    .order_by(Match.match_date.asc())
                    .first()
                )

                if match:
                    latest_odds = (
                        session.query(BettingOdds)
                        .filter_by(match_id=match.id)
                        .order_by(BettingOdds.odds_fetched_at.desc())
                        .first()
                    )
                    if latest_odds:
                        context["odds"] = {
                            "home_odds": float(latest_odds.home_odds) if latest_odds.home_odds else None,
                            "away_odds": float(latest_odds.away_odds) if latest_odds.away_odds else None,
                            "bookmaker": latest_odds.bookmaker,
                        }

    except Exception as e:
        logger.debug(f"Team context fetch failed: {e}")

    return context


def generate_preview(game: Dict) -> Optional[str]:
    """
    Generate a casual 1-2 sentence match preview.

    Args:
        game: Squiggle game dict with 'id', 'hteam', 'ateam', 'venue', 'date', 'round'

    Returns:
        Preview string or None
    """
    squiggle_id = game.get("id")

    # Check cache first
    cached = get_cached_preview(squiggle_id)
    if cached:
        return cached

    home_team = game.get("hteam", "Home")
    away_team = game.get("ateam", "Away")
    venue = game.get("venue", "")
    date_str = game.get("date", "")
    round_num = game.get("round", "")

    # Parse match date
    match_date = None
    try:
        if date_str:
            match_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        pass

    # Gather context (all free)
    weather = _fetch_weather(venue, match_date) if match_date else None
    team_context = _fetch_team_context(home_team, away_team)

    # Build context string for LLM
    context_parts = []

    context_parts.append(f"Match: {home_team} vs {away_team}")
    context_parts.append(f"Venue: {venue}")
    context_parts.append(f"Round: {round_num}")

    if weather:
        weather_str = f"Weather: {weather['max_temp']}°C"
        if weather.get("conditions"):
            weather_str += f", {weather['conditions']}"
        if weather.get("rain_chance") and weather["rain_chance"] > 30:
            weather_str += f" ({weather['rain_chance']}% chance of rain)"
        context_parts.append(weather_str)

    if team_context["injuries"]:
        injury_strs = []
        for inj in team_context["injuries"][:4]:
            severity = f" ({inj['severity']})" if inj.get("severity") else ""
            injury_strs.append(f"{inj['player']} ({inj['team']}){severity}")
        context_parts.append(f"Injury news: {'; '.join(injury_strs)}")

    if team_context["news"]:
        context_parts.append(f"Recent news: {' | '.join(team_context['news'][:3])}")

    if team_context["odds"]:
        odds = team_context["odds"]
        if odds["home_odds"] and odds["away_odds"]:
            if odds["home_odds"] < odds["away_odds"]:
                fav = home_team
                fav_odds = odds["home_odds"]
            else:
                fav = away_team
                fav_odds = odds["away_odds"]
            context_parts.append(f"Odds: {fav} favoured (${fav_odds:.2f})")

    context_str = "\n".join(context_parts)

    try:
        response = client.chat.completions.create(
            model=os.getenv("NEWS_ENRICHMENT_MODEL", "gpt-5-nano"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write casual, punchy 2-3 sentence AFL match previews. "
                        "Mention the weather if notable (hot, rainy, cold). "
                        "Mention key injuries or outs by player surname only. "
                        "Mention who's favoured if odds are available. "
                        "Reference any interesting recent form or news. "
                        "Use team nicknames naturally (e.g. 'Pies', 'Cats', 'Dogs'). "
                        "Be conversational, not formulaic. Don't start every preview the same way."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Write a brief match preview based on this context:\n\n{context_str}",
                },
            ],
            temperature=1,
            max_completion_tokens=2000,
        )

        preview = response.choices[0].message.content.strip()

        # Cache it
        _preview_cache[squiggle_id] = {
            "preview": preview,
            "generated_at": time.time(),
        }

        logger.info(f"Generated preview for {home_team} vs {away_team}: {preview[:60]}...")
        return preview

    except Exception as e:
        logger.error(f"Failed to generate preview for {home_team} vs {away_team}: {e}")
        return None


def _is_within_days(date_str: str, days: int) -> bool:
    """Check if a date string is within the next N days."""
    try:
        if not date_str:
            return False
        match_date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        # Compare as naive UTC
        if match_date.tzinfo:
            match_date = match_date.replace(tzinfo=None)
        cutoff = datetime.utcnow() + timedelta(days=days)
        return match_date <= cutoff
    except (ValueError, AttributeError):
        return False


def generate_previews_for_upcoming(games: List[Dict], days_ahead: int = 5) -> int:
    """
    Generate previews for upcoming games within the next `days_ahead` days.
    Skips cached entries. Returns count of newly generated previews.
    """
    generated = 0
    for game in games:
        if not _is_within_days(game.get("date", ""), days_ahead):
            continue
        squiggle_id = game.get("id")
        if squiggle_id and not get_cached_preview(squiggle_id):
            preview = generate_preview(game)
            if preview:
                generated += 1
    return generated
