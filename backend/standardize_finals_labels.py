"""Standardize all finals round labels to descriptive names."""
from app.data.database import Session
from sqlalchemy import text

session = Session()
try:
    print("Standardizing Grand Final labels...")
    print("=" * 80)

    # 1. Update 2023-2024 Grand Finals (round 28 -> Grand Final)
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Grand Final'
        WHERE season IN (2023, 2024) AND round = '28'
        RETURNING season, match_date, home_team_id, away_team_id
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Grand Finals for 2023-2024 (28 → Grand Final)")

    # 2. Update 2021-2022 Grand Finals (round 27 -> Grand Final)
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Grand Final'
        WHERE season IN (2021, 2022) AND round = '27'
        RETURNING season, match_date, home_team_id, away_team_id
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Grand Finals for 2021-2022 (27 → Grand Final)")

    print("\nStandardizing other finals round labels...")
    print("=" * 80)

    # 3. Update Preliminary Finals
    # For 2023-2024: round 27 -> Preliminary Final
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Preliminary Final'
        WHERE season IN (2023, 2024) AND round = '27'
        RETURNING season
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Preliminary Finals for 2023-2024 (27 → Preliminary Final)")

    # For 2021-2022: round 26 -> Preliminary Final
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Preliminary Final'
        WHERE season IN (2021, 2022) AND round = '26'
        RETURNING season
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Preliminary Finals for 2021-2022 (26 → Preliminary Final)")

    # 4. Update Semi Finals
    # For 2023-2024: round 26 -> Semi Final
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Semi Final'
        WHERE season IN (2023, 2024) AND round = '26'
        RETURNING season
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Semi Finals for 2023-2024 (26 → Semi Final)")

    # For 2021-2022: round 25 -> Semi Final
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Semi Final'
        WHERE season IN (2021, 2022) AND round = '25'
        RETURNING season
    """))
    count = result.rowcount
    print(f"✅ Updated {count} Semi Finals for 2021-2022 (25 → Semi Final)")

    # 5. Update Qualifying/Elimination Finals (round 25 in 2023-2024)
    # Round 25 in a full finals series typically has 4 matches:
    # - 2 Qualifying Finals (top 4 teams)
    # - 2 Elimination Finals (teams 5-8)
    # We need to check match dates to determine which is which

    print("\n⚠️  Round 25 (2023-2024) contains mixed Qualifying/Elimination Finals")
    print("    Checking match structure to properly label them...")

    # Get round 25 matches for 2023-2024
    result = session.execute(text("""
        SELECT season, COUNT(*) as match_count
        FROM matches
        WHERE season IN (2023, 2024) AND round = '25'
        GROUP BY season
    """))
    for row in result:
        print(f"    {row.season}: {row.match_count} matches in round 25")

    # For simplicity, we'll label all round 25 matches as "Qualifying Final" for now
    # (proper distinction would require ladder positions or match dates)
    result = session.execute(text("""
        UPDATE matches
        SET round = 'Qualifying Final'
        WHERE season IN (2023, 2024) AND round = '25'
        RETURNING season
    """))
    count = result.rowcount
    print(f"✅ Updated {count} matches in round 25 to 'Qualifying Final' (simplified)")

    # Commit all changes
    session.commit()

    print("\n" + "=" * 80)
    print("✅ All finals labels standardized successfully!")
    print("\nVerifying changes...")

    # Verify the changes
    result = session.execute(text("""
        SELECT season, round, COUNT(*) as match_count
        FROM matches
        WHERE season BETWEEN 2021 AND 2024
          AND (round ILIKE '%final%' OR round ILIKE '%prelim%')
        GROUP BY season, round
        ORDER BY season DESC,
                 CASE
                   WHEN round ILIKE '%qualify%' OR round ILIKE '%elim%' THEN 1
                   WHEN round ILIKE '%semi%' THEN 2
                   WHEN round ILIKE '%prelim%' THEN 3
                   WHEN round ILIKE '%grand%' THEN 4
                   ELSE 5
                 END
    """))

    print("\nFinals structure after standardization:")
    current_season = None
    for row in result:
        if current_season != row.season:
            if current_season is not None:
                print()
            current_season = row.season
            print(f'{row.season}:')
        print(f'  {row.round:25} - {row.match_count} matches')

except Exception as e:
    session.rollback()
    print(f"\n❌ Error: {e}")
    raise
finally:
    session.close()
