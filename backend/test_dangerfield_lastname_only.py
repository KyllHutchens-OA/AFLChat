"""
Test with just "Dangerfield" (no first name).
"""
import asyncio
from app.agent import agent

async def test_dangerfield_lastname_only():
    """Test with just last name."""
    print("=" * 80)
    print("Testing: How many goals did Dangerfield kick in 2022?")
    print("(Using just 'Dangerfield', no first name)")
    print("=" * 80)

    query = "How many goals did Dangerfield kick in 2022"

    result = await agent.run(user_query=query)

    print(f"\nIntent: {result.get('intent')}")
    print(f"Entities extracted: {result.get('entities')}")
    print(f"\nSQL Query:")
    print(result.get('sql_query'))

    # Check what the SQL actually searches for
    print(f"\nQuery Results:")
    data = result.get('query_results')
    print(data)

    if data is not None and len(data) > 0:
        print(f"\nFirst row: {data.iloc[0].to_dict()}")

    print(f"\nResponse:")
    print(result.get('natural_language_summary'))

    # Now check how many Dangerfields are in the database
    print("\n" + "=" * 80)
    print("Checking players table for 'Dangerfield'...")
    from app.data.database import Session
    from sqlalchemy import text

    session = Session()
    result = session.execute(text("SELECT name FROM players WHERE name ILIKE '%dangerfield%'"))
    players = result.fetchall()
    session.close()

    print(f"Found {len(players)} players with 'Dangerfield' in name:")
    for player in players:
        print(f"  - {player[0]}")

if __name__ == "__main__":
    asyncio.run(test_dangerfield_lastname_only())
