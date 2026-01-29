"""
Test JSON serialization fix for Timestamp objects.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime
import pandas as pd
from app.utils.json_serialization import make_json_serializable
import json


def test_timestamp_serialization():
    """Test that Timestamp objects are properly converted."""
    print("Testing JSON serialization with Timestamp objects...")
    print("=" * 80)

    # Simulate entities dictionary with Timestamp (like from database query)
    test_entities = {
        "players": ["Patrick Dangerfield"],
        "seasons": ["2022", "2023"],
        "metrics": ["goals"],
        "match_date": pd.Timestamp('2022-09-24 14:30:00'),  # Timestamp object
        "created_at": datetime.now(),  # datetime object
        "nested": {
            "player_dob": pd.Timestamp('1990-04-05'),
            "stats": [
                {"date": pd.Timestamp('2022-03-20'), "goals": 2},
                {"date": pd.Timestamp('2022-03-27'), "goals": 1}
            ]
        }
    }

    print("\nOriginal entities (with Timestamp objects):")
    print(f"  match_date type: {type(test_entities['match_date'])}")
    print(f"  created_at type: {type(test_entities['created_at'])}")
    print(f"  nested player_dob type: {type(test_entities['nested']['player_dob'])}")

    # Test that original FAILS to serialize
    print("\nAttempting to JSON serialize original (should FAIL)...")
    try:
        json.dumps(test_entities)
        print("  ❌ UNEXPECTED: Original entities serialized successfully")
    except TypeError as e:
        print(f"  ✅ EXPECTED FAILURE: {e}")

    # Apply sanitization
    print("\nApplying make_json_serializable()...")
    sanitized_entities = make_json_serializable(test_entities)

    print("\nSanitized entities:")
    print(f"  match_date type: {type(sanitized_entities['match_date'])} = {sanitized_entities['match_date']}")
    print(f"  created_at type: {type(sanitized_entities['created_at'])} = {sanitized_entities['created_at']}")
    print(f"  nested player_dob type: {type(sanitized_entities['nested']['player_dob'])} = {sanitized_entities['nested']['player_dob']}")

    # Test that sanitized version CAN serialize
    print("\nAttempting to JSON serialize sanitized (should SUCCEED)...")
    try:
        json_str = json.dumps(sanitized_entities, indent=2)
        print("  ✅ SUCCESS: Sanitized entities serialized successfully")
        print("\nJSON output (first 500 chars):")
        print(json_str[:500])
    except Exception as e:
        print(f"  ❌ FAILED: {e}")
        return False

    print("\n" + "=" * 80)
    print("✅ All tests passed! Timestamp serialization fix works correctly.")
    return True


if __name__ == "__main__":
    success = test_timestamp_serialization()
    sys.exit(0 if success else 1)
