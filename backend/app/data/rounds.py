"""Round labelling contract for `matches` (see scripts/db/1c_01_round_columns.sql).

round_number: Opening Round = 0, H&A 1..N, finals continue numerically after
the last H&A round (Squiggle numbers rounds exactly this way for modern seasons).
round_name:   'Opening Round' | 'Round N' | 'Wildcard Round' | 'Qualifying Final' |
              'Elimination Final' | 'Semi Final' | 'Preliminary Final' | 'Grand Final'
round (legacy varchar): str(round_number) for H&A, round_name for finals.
"""
from typing import Dict, Optional

# Squiggle `is_final` codes (1 = unspecified pre-1999 final)
SQUIGGLE_FINAL_NAMES = {
    2: "Elimination Final",
    3: "Qualifying Final",
    4: "Semi Final",
    5: "Preliminary Final",
    6: "Grand Final",
    7: "Wildcard Round",
}

FINALS_NAMES = (
    "Wildcard Round", "Qualifying Final", "Elimination Final",
    "Semi Final", "Preliminary Final", "Grand Final",
)


def legacy_round(round_number: int, round_name: str, is_final: bool) -> str:
    return round_name if is_final else str(round_number)


def ha_round_name(round_number: int) -> str:
    return "Opening Round" if round_number == 0 else f"Round {round_number}"


def round_fields_from_squiggle(game: Dict) -> Optional[Dict]:
    """{round, round_number, round_name, is_final} for a Squiggle game dict."""
    try:
        number = int(game.get("round"))
    except (TypeError, ValueError):
        return None
    code = int(game.get("is_final") or 0)
    if code:
        name = SQUIGGLE_FINAL_NAMES.get(code) or (game.get("roundname") or f"Round {number}")
        return {"round": name, "round_number": number, "round_name": name, "is_final": True}
    name = ha_round_name(number)
    return {"round": str(number), "round_number": number, "round_name": name, "is_final": False}
