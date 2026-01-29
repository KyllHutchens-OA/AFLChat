"""
Test clarification response resolution.
"""
import re


def test_clarification_matching():
    """Test the clarification candidate matching logic."""
    print("Testing Clarification Response Matching")
    print("=" * 80)

    # Simulate assistant's clarification message
    clarification_msg = "Multiple players named 'Daicos' were active in 2025: Josh Daicos, Nick Daicos. Which player did you mean?"

    # Extract candidates
    match = re.search(r':\s*([^.]+?)\.\s*which', clarification_msg, re.IGNORECASE)
    if match:
        candidates_str = match.group(1)
        candidates = [name.strip() for name in candidates_str.split(',')]
        print(f"\n✅ Extracted candidates: {candidates}")
    else:
        print("\n❌ Failed to extract candidates")
        return False

    # Test various user responses
    test_cases = [
        ("Nick", "Nick Daicos"),
        ("nick", "Nick Daicos"),
        ("Nick please", "Nick Daicos"),
        ("Josh", "Josh Daicos"),
        ("josh daicos", "Josh Daicos"),
        ("Nick Daicos", "Nick Daicos"),
        ("Daicos", None),  # Ambiguous - matches both
    ]

    print("\nTesting user responses:")
    print("-" * 80)

    all_passed = True
    for user_response, expected in test_cases:
        user_response_lower = user_response.lower().strip()

        # Remove common filler words (matching new logic)
        user_response_cleaned = user_response_lower
        for filler in [' please', ' thanks', ' pls', ' thx', ',', '.', ' ?']:
            user_response_cleaned = user_response_cleaned.replace(filler, '')
        user_response_cleaned = user_response_cleaned.strip()

        # Try to find matches
        potential_matches = []
        for candidate in candidates:
            candidate_lower = candidate.lower()

            # Check exact match
            if user_response_cleaned == candidate_lower:
                potential_matches.append(candidate)
                continue

            # Check if all words in user response are in candidate
            user_words = user_response_cleaned.split()
            candidate_words = candidate_lower.split()

            # If user response is a single word, check if it matches any part of candidate name
            if len(user_words) == 1:
                if user_words[0] in candidate_words:
                    potential_matches.append(candidate)
            else:
                # Multiple words: check if all are in candidate
                if all(word in candidate_words for word in user_words):
                    potential_matches.append(candidate)

        # Only use match if exactly one candidate matches
        matched_candidate = None
        if len(potential_matches) == 1:
            matched_candidate = potential_matches[0]

        # Check result
        if expected:
            if matched_candidate == expected:
                print(f"✅ '{user_response}' → '{matched_candidate}' (expected '{expected}')")
            else:
                print(f"❌ '{user_response}' → '{matched_candidate}' (expected '{expected}')")
                all_passed = False
        else:
            if matched_candidate is None:
                print(f"✅ '{user_response}' → None (ambiguous, correctly rejected)")
            else:
                print(f"❌ '{user_response}' → '{matched_candidate}' (expected None - ambiguous)")
                all_passed = False

    print("\n" + "=" * 80)
    if all_passed:
        print("✅ All test cases passed!")
        return True
    else:
        print("❌ Some test cases failed")
        return False


if __name__ == "__main__":
    import sys
    success = test_clarification_matching()
    sys.exit(0 if success else 1)
