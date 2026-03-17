"""
Backfill AI summaries for completed games that are missing them.
Run once to populate existing games, then automatic generation handles new games.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.data.database import get_session
from app.data.models import LiveGame
from app.services.game_summary_service import game_summary_service


def backfill_summaries(min_season=2026):
    """
    Generate AI summaries for all completed games from min_season onwards
    that don't already have summaries.
    """
    from sqlalchemy.orm import joinedload

    with get_session() as session:
        # Get game IDs first
        game_ids = session.query(LiveGame.id).filter(
            LiveGame.season >= min_season,
            LiveGame.status == 'completed',
            LiveGame.ai_summary.is_(None)
        ).order_by(LiveGame.match_date.asc()).all()

        game_ids = [g[0] for g in game_ids]
        total = len(game_ids)
        print(f"Found {total} games needing AI summaries")

        success_count = 0
        for i, game_id in enumerate(game_ids, 1):
            # Fresh query for each game with eager loading
            game = session.query(LiveGame).options(
                joinedload(LiveGame.home_team),
                joinedload(LiveGame.away_team)
            ).filter_by(id=game_id).first()

            if not game:
                continue

            match_str = f"{game.home_team.abbreviation} vs {game.away_team.abbreviation}"
            print(f"[{i}/{total}] Generating summary for {match_str} (R{game.round})...")

            try:
                # Call summary service directly (no API-Sports dependency)
                summary = game_summary_service.generate_summary(game, player_stats=None)

                if summary:
                    game.ai_summary = summary
                    session.commit()
                    success_count += 1
                    print(f"  ✓ Summary: {summary[:60]}...")
                else:
                    print(f"  ✗ No summary returned")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
                session.rollback()

        print(f"\nDone! Generated {success_count}/{total} summaries.")


if __name__ == '__main__':
    backfill_summaries()
