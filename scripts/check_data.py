#!/usr/bin/env python3
"""
Check data ingestion results.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from app.data.database import Session
from app.data.models import Team, Player, Match, PlayerStat, TeamStat

def check_data():
    """Check ingested data counts."""
    session = Session()

    try:
        teams_count = session.query(Team).count()
        matches_count = session.query(Match).count()
        players_count = session.query(Player).count()
        player_stats_count = session.query(PlayerStat).count()
        team_stats_count = session.query(TeamStat).count()

        print("\n" + "="*60)
        print("AFL ANALYTICS DATABASE - DATA SUMMARY")
        print("="*60)
        print(f"✅ Teams: {teams_count}")
        print(f"✅ Matches: {matches_count}")
        print(f"✅ Players: {players_count}")
        print(f"✅ Player Stats: {player_stats_count}")
        print(f"✅ Team Stats: {team_stats_count}")
        print("="*60)

        # Show sample teams
        print("\nSample Teams:")
        teams = session.query(Team).limit(5).all()
        for team in teams:
            print(f"  - {team.name} ({team.abbreviation}) - {team.stadium}")

        # Show sample matches
        if matches_count > 0:
            print("\nSample Matches (latest 5):")
            matches = session.query(Match).order_by(Match.match_date.desc()).limit(5).all()
            for match in matches:
                print(f"  - {match.season} R{match.round}: {match.home_team.name} {match.home_score} vs {match.away_team.name} {match.away_score}")

        print("\n" + "="*60)

    finally:
        session.close()

if __name__ == "__main__":
    check_data()
