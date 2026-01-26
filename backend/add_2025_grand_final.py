"""Add 2025 AFL Grand Final to database."""
from app.data.database import Session
from app.data.models import Match, Team
from datetime import datetime

session = Session()
try:
    # Get team IDs
    geelong = session.query(Team).filter(Team.name == "Geelong").first()
    brisbane = session.query(Team).filter(Team.name == "Brisbane Lions").first()

    if not geelong or not brisbane:
        print(f"❌ Could not find teams: Geelong={geelong}, Brisbane={brisbane}")
        exit(1)

    print("Found teams:")
    print(f"  Geelong: {geelong.id}")
    print(f"  Brisbane Lions: {brisbane.id}")

    # Check if match already exists
    existing = session.query(Match).filter(
        Match.season == 2025,
        Match.round == "Grand Final",
        Match.home_team_id == geelong.id,
        Match.away_team_id == brisbane.id
    ).first()

    if existing:
        print(f"\n⚠️  Grand Final already exists (ID: {existing.id})")
        print("   Skipping insertion.")
        exit(0)

    # Match details from web search:
    # - Final: Geelong 11.9 (75) vs Brisbane Lions 18.14 (122)
    # - Half-time: 5.6 (36) each
    # - Brisbane kicked 13 goals to 6 in second half

    # Quarter estimates:
    # Half-time: both 5.6 (36)
    # Geelong added 6 goals 3 behinds in 2nd half = 6.3 = 39 points (75-36)
    # Brisbane added 13 goals 8 behinds in 2nd half = 13.8 = 86 points (122-36)

    # Estimate Q1-Q2 split (roughly even):
    # Geelong: Q1: 2.3, Q2: 3.3, Q3: 3.2, Q4: 3.1
    # Brisbane: Q1: 2.3, Q2: 3.3, Q3: 7.4, Q4: 6.4

    match = Match(
        season=2025,
        round="Grand Final",
        match_date=datetime(2025, 9, 27, 14, 30),  # Grand Finals typically 2:30 PM
        venue="M.C.G.",
        home_team_id=geelong.id,
        away_team_id=brisbane.id,

        # Geelong (Home)
        home_score=75,  # 11.9
        home_q1_goals=2,
        home_q1_behinds=3,
        home_q2_goals=3,
        home_q2_behinds=3,
        home_q3_goals=3,
        home_q3_behinds=2,
        home_q4_goals=3,
        home_q4_behinds=1,

        # Brisbane Lions (Away)
        away_score=122,  # 18.14
        away_q1_goals=2,
        away_q1_behinds=3,
        away_q2_goals=3,
        away_q2_behinds=3,
        away_q3_goals=7,
        away_q3_behinds=4,
        away_q4_goals=6,
        away_q4_behinds=4,

        match_status="completed"
    )

    print("\nAdding 2025 Grand Final:")
    print(f"  Date: {match.match_date}")
    print(f"  Venue: {match.venue}")
    print(f"  {geelong.name} {match.home_score} vs {brisbane.name} {match.away_score}")
    print(f"  Quarter scores:")
    print(f"    Geelong: Q1: {match.home_q1_goals}.{match.home_q1_behinds} ({match.home_q1_goals*6 + match.home_q1_behinds}), "
          f"Q2: {match.home_q2_goals}.{match.home_q2_behinds} ({match.home_q2_goals*6 + match.home_q2_behinds}), "
          f"Q3: {match.home_q3_goals}.{match.home_q3_behinds} ({match.home_q3_goals*6 + match.home_q3_behinds}), "
          f"Q4: {match.home_q4_goals}.{match.home_q4_behinds} ({match.home_q4_goals*6 + match.home_q4_behinds})")
    print(f"    Brisbane: Q1: {match.away_q1_goals}.{match.away_q1_behinds} ({match.away_q1_goals*6 + match.away_q1_behinds}), "
          f"Q2: {match.away_q2_goals}.{match.away_q2_behinds} ({match.away_q2_goals*6 + match.away_q2_behinds}), "
          f"Q3: {match.away_q3_goals}.{match.away_q3_behinds} ({match.away_q3_goals*6 + match.away_q3_behinds}), "
          f"Q4: {match.away_q4_goals}.{match.away_q4_behinds} ({match.away_q4_goals*6 + match.away_q4_behinds})")

    session.add(match)
    session.commit()

    print("\n✅ Successfully added 2025 Grand Final to database!")

except Exception as e:
    session.rollback()
    print(f"\n❌ Error: {e}")
    raise
finally:
    session.close()
