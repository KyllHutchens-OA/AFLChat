#!/usr/bin/env python3
"""
Cleanup script to remove duplicate and malformed live game events.

This script:
1. Removes events with missing scores (home_score_after or away_score_after is NULL or 0)
2. Removes duplicate events (same game_id, team_id, and score within 5 minutes)
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import timedelta
from sqlalchemy import text
from app.data.database import get_session
from app.data.models import LiveGameEvent

def cleanup_events():
    with get_session() as session:
        # Count total events before cleanup
        total_before = session.query(LiveGameEvent).count()
        print(f"Total events before cleanup: {total_before}")

        # 1. Delete events with missing/zero scores
        bad_score_events = session.query(LiveGameEvent).filter(
            (LiveGameEvent.home_score_after.is_(None)) |
            (LiveGameEvent.away_score_after.is_(None)) |
            (LiveGameEvent.home_score_after == 0) & (LiveGameEvent.away_score_after == 0)
        ).all()

        print(f"Events with missing/zero scores: {len(bad_score_events)}")
        for event in bad_score_events:
            print(f"  - Deleting: Game {event.game_id}, {event.event_type}, scores: {event.home_score_after}-{event.away_score_after}")
            session.delete(event)

        session.commit()

        # 2. Find and remove duplicates (same game, team, score, within 5 minutes)
        # Keep only the first event for each unique combination
        all_events = session.query(LiveGameEvent).order_by(
            LiveGameEvent.game_id,
            LiveGameEvent.timestamp.asc()
        ).all()

        seen = {}  # (game_id, team_id, home_score, away_score) -> first event
        duplicates_to_delete = []

        for event in all_events:
            key = (event.game_id, event.team_id, event.home_score_after, event.away_score_after)

            if key in seen:
                first_event = seen[key]
                # If within 5 minutes of the first event, it's a duplicate
                if event.timestamp - first_event.timestamp < timedelta(minutes=5):
                    duplicates_to_delete.append(event)
                else:
                    # More than 5 minutes apart - could be a legitimate event at the same score
                    # (e.g., both teams scored to keep the same differential)
                    # Update the "first" to this one for future comparisons
                    seen[key] = event
            else:
                seen[key] = event

        print(f"Duplicate events to delete: {len(duplicates_to_delete)}")
        for event in duplicates_to_delete:
            print(f"  - Deleting duplicate: Game {event.game_id}, {event.event_type}, {event.home_score_after}-{event.away_score_after}, {event.timestamp}")
            session.delete(event)

        session.commit()

        # Count total events after cleanup
        total_after = session.query(LiveGameEvent).count()
        print(f"\nTotal events after cleanup: {total_after}")
        print(f"Removed {total_before - total_after} events")

        # Show remaining events per game
        from sqlalchemy import func
        game_counts = session.query(
            LiveGameEvent.game_id,
            func.count(LiveGameEvent.id)
        ).group_by(LiveGameEvent.game_id).all()

        print("\nRemaining events per game:")
        for game_id, count in game_counts:
            print(f"  Game {game_id}: {count} events")


if __name__ == "__main__":
    cleanup_events()
