"""
Match preview generation helpers for Claude Code cloud scheduled tasks.

Two-phase workflow:
  1. `gather` — fetches upcoming games from Squiggle, collects context
     (weather, injuries, predictions, news, bye status) from DB, and
     outputs JSON for Claude to write previews from.
  2. `insert` — reads JSON previews from stdin and stores them in the
     match_previews DB table.

Usage (cloud scheduled task runs these via Claude):
    cd backend
    python3 scripts/generate_match_previews.py gather     # → JSON to stdout
    python3 scripts/generate_match_previews.py insert      # ← JSON from stdin

Env vars required: DB_STRING
"""
import sys
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force production mode and suppress SQLAlchemy BEFORE importing app modules
# (database.py creates the engine at import time with echo=config.DEBUG)
os.environ["FLASK_ENV"] = "production"

# Send all logging to stderr so stdout stays clean JSON
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stderr, force=True)
logging.getLogger("sqlalchemy.engine").handlers = [logging.StreamHandler(sys.stderr)]
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("sqlalchemy").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

import httpx

from app.data.database import get_session
from app.data.models import (
    MatchPreview, NewsArticle, SquigglePrediction, Match, Team,
)

# AFL venue coordinates for Open-Meteo weather lookups
VENUE_COORDS: dict[str, tuple] = {
    "MCG": (-37.82, 144.98),
    "M.C.G.": (-37.82, 144.98),
    "Melbourne Cricket Ground": (-37.82, 144.98),
    "Marvel Stadium": (-37.82, 144.95),
    "Docklands": (-37.82, 144.95),
    "GMHBA Stadium": (-38.16, 144.35),
    "Kardinia Park": (-38.16, 144.35),
    "Mars Stadium": (-37.55, 143.85),
    "Adelaide Oval": (-34.92, 138.60),
    "Optus Stadium": (-31.95, 115.89),
    "Perth Stadium": (-31.95, 115.89),
    "SCG": (-33.89, 151.22),
    "Sydney Cricket Ground": (-33.89, 151.22),
    "ENGIE Stadium": (-33.85, 151.07),
    "Sydney Showground Stadium": (-33.85, 151.07),
    "Giants Stadium": (-33.85, 151.07),
    "Manuka Oval": (-35.32, 149.13),
    "Gabba": (-27.49, 153.04),
    "The Gabba": (-27.49, 153.04),
    "Brisbane Cricket Ground": (-27.49, 153.04),
    "People First Stadium": (-28.01, 153.37),
    "Heritage Bank Stadium": (-28.01, 153.37),
    "Metricon Stadium": (-28.01, 153.37),
    "Cazaly's Stadium": (-16.94, 145.76),
    "Blundstone Arena": (-42.88, 147.37),
    "UTAS Stadium": (-41.43, 147.14),
    "University of Tasmania Stadium": (-41.43, 147.14),
    "TIO Stadium": (-12.43, 130.87),
    "TIO Traeger Park": (-23.70, 133.88),
}

_WEATHER_CODES = {
    0: "clear skies", 1: "mostly clear", 2: "partly cloudy", 3: "overcast",
    45: "foggy", 48: "foggy", 51: "light drizzle", 53: "drizzle",
    55: "heavy drizzle", 61: "light rain", 63: "rain", 65: "heavy rain",
    71: "light snow", 73: "snow", 80: "light showers", 81: "showers",
    82: "heavy showers", 95: "thunderstorms", 96: "thunderstorms with hail",
}


def _fetch_weather(venue: str, match_date: datetime) -> Optional[dict]:
    """Fetch weather forecast from Open-Meteo (free, no API key)."""
    coords = VENUE_COORDS.get(venue)
    if not coords:
        venue_lower = venue.lower()
        for name, c in VENUE_COORDS.items():
            if name.lower() in venue_lower or venue_lower in name.lower():
                coords = c
                break
    if not coords:
        return None

    days_ahead = (match_date.date() - datetime.utcnow().date()).days
    if days_ahead < 0 or days_ahead > 15:
        return None

    lat, lon = coords
    try:
        resp = httpx.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat, "longitude": lon,
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

        return {
            "max_temp": round(max_temp) if max_temp is not None else None,
            "conditions": _WEATHER_CODES.get(weather_code, ""),
            "rain_chance": precip_prob,
        }
    except Exception as e:
        logger.debug(f"Weather fetch failed for {venue}: {e}")
        return None


def _fetch_team_context(session, home_team: str, away_team: str) -> dict:
    """Query DB for injuries, news, and Squiggle predictions."""
    context: dict = {"injuries": [], "news": [], "prediction": None}
    week_ago = datetime.utcnow() - timedelta(days=7)

    # Injury news
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
    for article in injury_articles:
        teams = article.related_teams or []
        if (home_team in teams or away_team in teams) and article.summary:
            context["news"].append(article.summary)
    context["news"] = list(dict.fromkeys(context["news"]))[:5]

    # Squiggle prediction
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
            prediction = (
                session.query(SquigglePrediction)
                .filter_by(match_id=match.id)
                .order_by(SquigglePrediction.prediction_date.desc())
                .first()
            )
            if prediction:
                winner = session.query(Team).get(prediction.predicted_winner_id)
                context["prediction"] = {
                    "winner": winner.name if winner else "Unknown",
                    "margin": float(prediction.predicted_margin) if prediction.predicted_margin else None,
                    "home_prob": float(prediction.home_win_probability) if prediction.home_win_probability else None,
                }

    return context


def _check_bye_status(session, home_team: str, away_team: str, round_num, season: int) -> Optional[str]:
    """Check if either team had no match in the previous round."""
    try:
        current_round = int(round_num)
        if current_round <= 1:
            return None
        prev_round = str(current_round - 1)
    except (ValueError, TypeError):
        return None

    bye_teams = []
    for team_name in (home_team, away_team):
        team = session.query(Team).filter_by(name=team_name).first()
        if not team:
            continue
        prev_match = (
            session.query(Match)
            .filter(Match.season == season, Match.round == prev_round)
            .filter((Match.home_team_id == team.id) | (Match.away_team_id == team.id))
            .first()
        )
        if not prev_match:
            other_matches = (
                session.query(Match)
                .filter(Match.season == season, Match.round == prev_round)
                .count()
            )
            if other_matches > 0:
                bye_teams.append(team_name)

    if bye_teams:
        return f"Coming off a bye: {', '.join(bye_teams)}"
    return None


def _determine_preview_type(match_date: datetime) -> Optional[str]:
    """Determine which preview type is needed based on days until match."""
    now = datetime.utcnow()
    days_until = (match_date.date() - now.date()).days

    if days_until <= 2:
        return "gameday"
    elif 3 <= days_until <= 5:
        return "early"
    return None


# ── Phase 1: Gather ──────────────────────────────────────────────────────────

def gather():
    """Fetch upcoming games, collect context, output JSON for Claude to write previews.

    Outputs a JSON array of objects, each with:
      - squiggle_id, home_team, away_team, venue, round, date, preview_type
      - context: { weather, injuries, news, prediction, bye }
    Only includes games that need a preview (not already in DB).
    """
    current_year = datetime.now().year
    try:
        resp = httpx.get(
            f"https://api.squiggle.com.au/?q=games;year={current_year}",
            headers={"User-Agent": "AFL-Analytics-App/1.0 (kyllhutchens@gmail.com)"},
            timeout=20,
        )
        resp.raise_for_status()
        games = resp.json().get("games", [])
    except Exception as e:
        logger.error(f"Failed to fetch from Squiggle: {e}")
        print(json.dumps([]))
        return []

    upcoming = [g for g in games if g.get("complete", 0) == 0]
    upcoming.sort(key=lambda g: g.get("date", ""))

    results = []

    with get_session() as session:
        for game in upcoming:
            squiggle_id = game.get("id")
            date_str = game.get("date", "")
            home_team = game.get("hteam", "")
            away_team = game.get("ateam", "")
            venue = game.get("venue", "")
            round_num = game.get("round", "")

            # Parse match date
            try:
                if "Z" in date_str or "+" in date_str:
                    match_date = datetime.fromisoformat(date_str.replace("Z", "+00:00")).replace(tzinfo=None)
                else:
                    match_date = datetime.fromisoformat(date_str)
            except (ValueError, AttributeError):
                continue

            preview_type = _determine_preview_type(match_date)
            if not preview_type:
                continue

            # Check if preview already exists
            existing = (
                session.query(MatchPreview)
                .filter_by(squiggle_game_id=squiggle_id, preview_type=preview_type)
                .first()
            )
            if existing:
                continue

            # Gather context
            weather = _fetch_weather(venue, match_date)
            team_context = _fetch_team_context(session, home_team, away_team)
            bye_context = _check_bye_status(session, home_team, away_team, round_num, current_year)

            results.append({
                "squiggle_id": squiggle_id,
                "home_team": home_team,
                "away_team": away_team,
                "venue": venue,
                "round": round_num,
                "date": date_str,
                "preview_type": preview_type,
                "context": {
                    "weather": weather,
                    "injuries": team_context["injuries"][:4],
                    "news": team_context["news"][:5],
                    "prediction": team_context.get("prediction"),
                    "bye": bye_context,
                },
            })

    print(json.dumps(results, indent=2))
    logger.info(f"Gathered context for {len(results)} game(s) needing previews")


# ── Phase 2: Insert ──────────────────────────────────────────────────────────

def insert():
    """Read JSON previews from stdin and insert into match_previews table.

    Expected input: JSON array of objects, each with:
      - squiggle_id (int)
      - preview_type ("early" or "gameday")
      - preview_text (str) — the preview Claude wrote
      - home_team (str)
      - away_team (str)
    """
    raw = sys.stdin.read()
    try:
        previews = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        sys.exit(1)

    if not isinstance(previews, list):
        logger.error("Expected a JSON array")
        sys.exit(1)

    inserted = 0
    skipped = 0

    with get_session() as session:
        for item in previews:
            squiggle_id = item.get("squiggle_id")
            preview_type = item.get("preview_type")
            preview_text = item.get("preview_text", "").strip()
            home_team = item.get("home_team", "")
            away_team = item.get("away_team", "")

            if not squiggle_id or not preview_type or not preview_text:
                logger.warning(f"Skipping incomplete entry: {item.get('squiggle_id')}")
                skipped += 1
                continue

            # Check for existing (idempotent)
            existing = (
                session.query(MatchPreview)
                .filter_by(squiggle_game_id=squiggle_id, preview_type=preview_type)
                .first()
            )
            if existing:
                skipped += 1
                continue

            # Try to link to a match_id
            match_id = None
            home_obj = session.query(Team).filter_by(name=home_team).first()
            away_obj = session.query(Team).filter_by(name=away_team).first()
            if home_obj and away_obj:
                match = (
                    session.query(Match)
                    .filter(
                        Match.home_team_id == home_obj.id,
                        Match.away_team_id == away_obj.id,
                        Match.match_date >= datetime.utcnow() - timedelta(days=1),
                    )
                    .order_by(Match.match_date.asc())
                    .first()
                )
                if match:
                    match_id = match.id

            preview = MatchPreview(
                squiggle_game_id=squiggle_id,
                match_id=match_id,
                preview_text=preview_text,
                preview_type=preview_type,
                generation_context=item.get("context"),
                is_validated=True,
                generated_at=datetime.utcnow(),
                model_used="claude-cloud-task",
            )
            session.add(preview)
            session.flush()
            inserted += 1
            logger.info(f"  ✓ Inserted {preview_type} preview for {home_team} vs {away_team}")

    print(json.dumps({"inserted": inserted, "skipped": skipped}))
    logger.info(f"Insert complete: {inserted} inserted, {skipped} skipped")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/generate_match_previews.py [gather|insert]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "gather":
        gather()
    elif command == "insert":
        insert()
    else:
        print(f"Unknown command: {command}. Use 'gather' or 'insert'.")
        sys.exit(1)
