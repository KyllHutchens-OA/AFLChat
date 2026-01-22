#!/usr/bin/env python3
"""
Test Squiggle API connection.
"""
import requests

def test_squiggle_api():
    """Test fetching games from Squiggle API."""
    print("Testing Squiggle API...")

    # Test API
    url = "https://api.squiggle.com.au/?q=games&year=2024"
    print(f"\nFetching: {url}")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()

        if "games" in data:
            games = data["games"]
            print(f"✅ Success! Found {len(games)} games for 2024")

            # Show first 3 games
            print("\nSample games:")
            for game in games[:3]:
                print(f"  - Round {game.get('round')}: {game.get('hteam')} vs {game.get('ateam')}")
                print(f"    Score: {game.get('hscore')} - {game.get('ascore')}")
                print(f"    Venue: {game.get('venue')}")
                print(f"    Date: {game.get('date')}")
                print()
        else:
            print("❌ No 'games' field in response")
            print(f"Response keys: {data.keys()}")

    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    test_squiggle_api()
