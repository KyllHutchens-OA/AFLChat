"""
Automated Player Stats Ingestion Pipeline (AFL Tables).

Targets every completed match that has no player_stats rows (any season, no date
window; optional `limit`). AFL Tables typically publishes stats 1-3 days after a
round, so the scheduler runs this daily plus retries until nothing is missing.

Matching a DB match to an AFL Tables game: same season, same two clubs (either
orientation), same finals flag, kick-off within MATCH_DATE_TOLERANCE_DAYS. Exactly
one candidate or the match is skipped and reported; never "first meeting this season".

Players are identified by their AFL Tables key (players.afltables_id), so namesakes
never merge. Idempotent upsert on (match_id, player_id): existing values are kept,
only missing (NULL) fields are filled, team_id is set from the page.
"""
import logging
import time
from typing import Callable, Dict, List, Optional

import requests
from sqlalchemy import exists

from app.data.database import get_session
from app.data.ingestion.afltables_pages import (
    STAT_FIELDS, canonical_club, parse_match_page, parse_season_page,
)
from app.data.models import Match, Player, PlayerStat, Team

logger = logging.getLogger(__name__)

AFL_TABLES_BASE_URL = "https://afltables.com/afl"
AFL_TABLES_REQUEST_DELAY = 1.5  # Respectful delay between requests
MATCH_DATE_TOLERANCE_DAYS = 3   # AFL Tables vs DB kick-off date


class _AFLTablesFetcher:
    """GETs afltables.com/afl/<rel_url> with a polite delay."""

    def __init__(self):
        self.http = requests.Session()
        self.http.headers.update({'User-Agent': 'Mozilla/5.0 (AFL Analytics Research Project)'})

    def __call__(self, rel_url: str) -> Optional[str]:
        time.sleep(AFL_TABLES_REQUEST_DELAY)
        try:
            # connect=10s, read=45s — prevents indefinite hangs on stalled connections
            resp = self.http.get(f"{AFL_TABLES_BASE_URL}/{rel_url.lstrip('/')}", timeout=(10, 45))
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {rel_url}: {e}")
            return None


def get_matches_needing_stats(session, season: int = None, limit: int = None) -> List[Match]:
    """Completed matches with no player_stats rows, newest first."""
    q = session.query(Match).filter(
        Match.match_status == "completed",
        ~exists().where(PlayerStat.match_id == Match.id),
    )
    if season:
        q = q.filter(Match.season == season)
    q = q.order_by(Match.match_date.desc())
    return q.limit(limit).all() if limit else q.all()


def _calculate_fantasy_points(stats: Dict) -> int:
    """AFL fantasy points (the DB trigger recomputes this on write as well)."""
    return (
        (stats.get('kicks') or 0) * 3 + (stats.get('handballs') or 0) * 2
        + (stats.get('marks') or 0) * 3 + (stats.get('tackles') or 0) * 4
        + (stats.get('goals') or 0) * 6 + (stats.get('behinds') or 0)
        + (stats.get('hitouts') or 0) + (stats.get('free_kicks_for') or 0)
        - (stats.get('free_kicks_against') or 0) * 3
    )


def find_page_game(match: Match, games: List[Dict], team_ids: Dict[str, int]) -> Optional[Dict]:
    """The single AFL Tables game for this DB match, or None (missing or ambiguous)."""
    pair = {match.home_team_id, match.away_team_id}
    hits = []
    for g in games:
        ids = {team_ids.get(canonical_club(g['home'])), team_ids.get(canonical_club(g['away']))}
        if ids != pair or bool(g['is_final']) != bool(match.is_final):
            continue
        if abs((g['local_dt'].date() - match.match_date.date()).days) <= MATCH_DATE_TOLERANCE_DAYS:
            hits.append(g)
    if len(hits) > 1:
        logger.warning(f"AFL Tables: {len(hits)} candidates for match {match.id}; skipping")
    return hits[0] if len(hits) == 1 else None


def resolve_player(session, afltables_id: Optional[str], name: str, team_id: int,
                   cache: Dict[str, int]) -> Optional[int]:
    """players.id for an AFL Tables player, creating the player if new.

    1. players.afltables_id match.
    2. An unclaimed (afltables_id NULL) player with the exact name: the one at this
       club if several, else the only one. The key is then recorded on that player.
    3. New player.
    """
    if not name:
        return None
    key = afltables_id or f"name:{name.lower()}:{team_id}"
    if key in cache:
        return cache[key]
    player = None
    if afltables_id:
        player = session.query(Player).filter(Player.afltables_id == afltables_id).first()
    if player is None:
        cands = session.query(Player).filter(Player.name.ilike(name), Player.afltables_id.is_(None)).all()
        same_club = [p for p in cands if p.team_id == team_id]
        if len(same_club) == 1:
            player = same_club[0]
        elif len(cands) == 1:
            player = cands[0]
        if player is not None and afltables_id:
            player.afltables_id = afltables_id
    if player is None:
        parts = name.split()
        player = Player(name=name, first_name=parts[0], last_name=parts[-1] if len(parts) > 1 else "",
                        team_id=team_id, is_active=True, afltables_id=afltables_id)
        session.add(player)
        session.flush()
        logger.info(f"Created new player: {name} ({afltables_id}, team_id={team_id})")
    cache[key] = player.id
    return player.id


def apply_match_page(session, match: Match, game: Dict, page: Dict, team_ids: Dict[str, int],
                     player_cache: Dict[str, int], result: Dict) -> None:
    """Upsert one match's player stats + result from AFL Tables."""
    # Result: AFL Tables is authoritative once published
    swapped = team_ids.get(canonical_club(game['home'])) != match.home_team_id
    hq, aq = (game['away_q'], game['home_q']) if swapped else (game['home_q'], game['away_q'])
    hs, as_ = (game['away_score'], game['home_score']) if swapped else (game['home_score'], game['away_score'])
    if (match.home_score, match.away_score) != (hs, as_):
        logger.warning(f"Match {match.id} score {match.home_score}-{match.away_score} -> {hs}-{as_} (AFL Tables)")
        match.home_score, match.away_score = hs, as_
        result["scores_corrected"] += 1
    for side, q in (("home", hq), ("away", aq)):
        if len(q) >= 4:
            final = q[-1]  # extra time: last period is the result
            for i, (gl, bh) in enumerate(q[:3] + [final], start=1):
                setattr(match, f"{side}_q{i}_goals", gl)
                setattr(match, f"{side}_q{i}_behinds", bh)
    if game.get('attendance') and not match.attendance:
        match.attendance = game['attendance']

    for club in page['teams']:
        team_id = team_ids.get(canonical_club(club['club']))
        if team_id not in (match.home_team_id, match.away_team_id):
            logger.warning(f"Match {match.id}: page club {club['club']!r} not in match; skipped")
            continue
        for p in club['players']:
            player_id = resolve_player(session, p['afltables_id'], p['name'], team_id, player_cache)
            if not player_id:
                result["players_not_found"] += 1
                continue
            # every field explicitly, so unrecorded columns are NULL rather than the 0 default
            stats = {f: p.get(f) for f in STAT_FIELDS}
            existing = session.query(PlayerStat).filter_by(match_id=match.id, player_id=player_id).first()
            if existing:
                changed = existing.team_id != team_id
                existing.team_id = team_id
                for f, v in stats.items():
                    if v is not None and getattr(existing, f) is None:
                        setattr(existing, f, v)
                        changed = True
                result["stats_updated"] += int(changed)
            else:
                session.add(PlayerStat(match_id=match.id, player_id=player_id, team_id=team_id,
                                       fantasy_points=_calculate_fantasy_points(stats), **stats))
                result["stats_created"] += 1


def ingest_from_afl_tables(season: int = None, limit: int = None,
                           fetch: Callable[[str], Optional[str]] = None, **_ignored) -> Dict:
    """Backfill player stats for completed matches that have none.

    Args:
        season: restrict to one season (default: all seasons)
        limit: max matches to attempt this run (newest first)
        fetch: rel_url -> html (default: live afltables.com with a 1.5s delay)

    Returns counts plus `unavailable`: matches AFL Tables has not published yet.
    """
    fetch = fetch or _AFLTablesFetcher()
    result = {
        "matches_targeted": 0, "matches_processed": 0, "stats_created": 0,
        "stats_updated": 0, "scores_corrected": 0, "players_not_found": 0,
        "errors": 0, "unavailable": [],
    }
    with get_session() as session:
        targets = get_matches_needing_stats(session, season, limit)
        result["matches_targeted"] = len(targets)
        if not targets:
            logger.info("AFL Tables ingestion: every completed match has player stats")
            return result

        team_ids = {t.name: t.id for t in session.query(Team).all()}
        player_cache: Dict[str, int] = {}
        season_games: Dict[int, List[Dict]] = {}

        for match in targets:
            label = f"{match.season} {match.round_name or match.round} id={match.id}"
            try:
                if match.season not in season_games:
                    html = fetch(f"seas/{match.season}.html")
                    season_games[match.season] = parse_season_page(html, match.season) if html else []
                game = find_page_game(match, season_games[match.season], team_ids)
                page_html = fetch(game['stats_url']) if game and game.get('stats_url') else None
                page = parse_match_page(page_html) if page_html else None
                if not page or not any(t['players'] for t in page['teams']):
                    result["unavailable"].append(label)
                    continue
                apply_match_page(session, match, game, page, team_ids, player_cache, result)
                session.commit()  # one match per transaction
                result["matches_processed"] += 1
                logger.info(f"AFL Tables: stats ingested for {label}")
            except Exception as e:
                session.rollback()
                logger.error(f"AFL Tables error for {label}: {e}")
                result["errors"] += 1

    logger.info(
        f"AFL Tables ingestion: {result['matches_processed']}/{result['matches_targeted']} matches, "
        f"{result['stats_created']} created, {result['stats_updated']} updated, "
        f"{len(result['unavailable'])} not yet on AFL Tables, {result['errors']} errors"
    )
    return result


if __name__ == "__main__":
    # python -m app.data.ingestion.stats_ingester [season] [limit]
    import sys
    logging.basicConfig(level=logging.INFO)
    args = [int(a) for a in sys.argv[1:]]
    out = ingest_from_afl_tables(season=args[0] if args else None, limit=args[1] if len(args) > 1 else None)
    print({k: (v if k != "unavailable" else len(v)) for k, v in out.items()})
    for u in out["unavailable"]:
        print("unavailable:", u)
