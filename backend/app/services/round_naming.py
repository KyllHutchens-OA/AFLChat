"""
Finals round naming for Live.

Prefers `matches.round_name` / `matches.is_final` (backfilled by the 1C data
pipeline for every season). Falls back to season-specific numbering when no
Match row exists yet - e.g. a finals `live_games` row before it has completed
and migrated into `matches`.
"""

# 2026 finals structure: Wildcard Round, then the four traditional weeks.
# Round 26 covers both an Elimination and a Qualifying Final; without a
# migrated Match row we can't tell which, so the fallback names the week.
FINALS_2026 = {
    25: "Wildcard Round",
    26: "Elimination/Qualifying Final",
    27: "Semi Final",
    28: "Preliminary Final",
    29: "Grand Final",
}


def _looks_like_final(value) -> bool:
    text = str(value).lower()
    return "final" in text or "wildcard" in text


def fallback_round_name(season, round_value):
    """Derive (round_name, is_final, round_number) with no DB row to read.

    Only 2026's finals numbering is known here; other seasons without a
    migrated Match row get a generic "Finals Week N" label.
    """
    try:
        round_number = int(str(round_value).strip())
    except (TypeError, ValueError):
        # Squiggle sometimes hands back a name directly (e.g. "Grand Final")
        return str(round_value), _looks_like_final(round_value), None

    if season == 2026 and round_number in FINALS_2026:
        return FINALS_2026[round_number], True, round_number
    if round_number > 24:
        return f"Finals Week {round_number - 24}", True, round_number
    return f"Round {round_number}", False, round_number


def resolve_round_display(season, round_value, match=None):
    """Round name + is_final + round_number for a live game or match.

    `match` is the linked Match row (or None if not migrated yet / not found).
    """
    if match is not None and match.round_name:
        return match.round_name, bool(match.is_final), match.round_number
    return fallback_round_name(season, round_value)
