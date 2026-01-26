"""
AFL Analytics Agent - Entity Resolver

Handles team name normalization, nickname mapping, fuzzy matching, and entity validation.
Converts natural language variations to canonical database values.
"""
from typing import Optional, Dict, List, Tuple
from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


class EntityResolver:
    """
    Resolves natural language entity references to canonical database values.

    Handles:
    - Team nicknames ("Cats" → "Geelong")
    - Abbreviations ("RIC" → "Richmond")
    - Typos ("Richmnd" → "Richmond")
    - Multiple representations ("Port Adelaide Power" → "Port Adelaide")
    - Case insensitivity
    """

    # Comprehensive team nickname mapping
    # Format: "CanonicalName": [list of all possible variations]
    TEAM_NICKNAMES = {
        "Adelaide": [
            "adelaide", "crows", "adelaide crows", "the crows", "ade"
        ],
        "Brisbane Lions": [
            "brisbane", "brisbane lions", "lions", "the lions", "bri", "brisbane bears"
        ],
        "Carlton": [
            "carlton", "blues", "the blues", "car", "navy blues"
        ],
        "Collingwood": [
            "collingwood", "magpies", "the magpies", "pies", "col", "the pies"
        ],
        "Essendon": [
            "essendon", "bombers", "the bombers", "dons", "ess", "the dons"
        ],
        "Fremantle": [
            "fremantle", "dockers", "the dockers", "freo", "fre"
        ],
        "Geelong": [
            "geelong", "cats", "geelong cats", "the cats", "gee"
        ],
        "Gold Coast": [
            "gold coast", "suns", "gold coast suns", "the suns", "gcs"
        ],
        "Greater Western Sydney": [
            "greater western sydney", "gws", "giants", "gws giants",
            "the giants", "western sydney"
        ],
        "Hawthorn": [
            "hawthorn", "hawks", "the hawks", "haw"
        ],
        "Melbourne": [
            "melbourne", "demons", "the demons", "dees", "mel", "the dees"
        ],
        "North Melbourne": [
            "north melbourne", "kangaroos", "roos", "the roos", "nm",
            "the kangaroos", "north", "shinboners"
        ],
        "Port Adelaide": [
            "port adelaide", "power", "port adelaide power", "the power",
            "pa", "port"
        ],
        "Richmond": [
            "richmond", "tigers", "richmond tigers", "the tigers", "ric", "tiges"
        ],
        "St Kilda": [
            "st kilda", "saints", "the saints", "stk", "st. kilda"
        ],
        "Sydney": [
            "sydney", "swans", "sydney swans", "the swans", "syd", "south melbourne"
        ],
        "West Coast": [
            "west coast", "eagles", "west coast eagles", "the eagles",
            "wce", "weagles"
        ],
        "Western Bulldogs": [
            "western bulldogs", "bulldogs", "dogs", "the dogs", "wb",
            "footscray", "the bulldogs"
        ]
    }

    # Reverse lookup: variation → canonical name
    _NICKNAME_LOOKUP = None

    @classmethod
    def _build_lookup(cls):
        """Build reverse lookup dictionary on first use."""
        if cls._NICKNAME_LOOKUP is None:
            cls._NICKNAME_LOOKUP = {}
            for canonical, variations in cls.TEAM_NICKNAMES.items():
                for variation in variations:
                    cls._NICKNAME_LOOKUP[variation.lower()] = canonical

    @classmethod
    def resolve_team(cls, user_input: str) -> Optional[str]:
        """
        Resolve a team name from user input to canonical database name.

        Tries in order:
        1. Exact match (case-insensitive)
        2. Nickname/abbreviation lookup
        3. Fuzzy matching for typos

        Args:
            user_input: Team name as entered by user (e.g., "Cats", "Tigers", "RIC")

        Returns:
            Canonical team name (e.g., "Geelong") or None if no match
        """
        if not user_input:
            return None

        cls._build_lookup()

        # Normalize input
        normalized = user_input.strip().lower()

        # Try exact nickname lookup
        if normalized in cls._NICKNAME_LOOKUP:
            canonical = cls._NICKNAME_LOOKUP[normalized]
            logger.info(f"Resolved '{user_input}' → '{canonical}' (exact match)")
            return canonical

        # Try fuzzy matching for typos
        fuzzy_match = cls._fuzzy_match_team(normalized)
        if fuzzy_match:
            logger.info(f"Resolved '{user_input}' → '{fuzzy_match}' (fuzzy match)")
            return fuzzy_match

        logger.warning(f"Could not resolve team name: '{user_input}'")
        return None

    @classmethod
    def _fuzzy_match_team(cls, user_input: str, threshold: float = 0.75) -> Optional[str]:
        """
        Find closest team name match using fuzzy string matching.

        Args:
            user_input: Normalized user input
            threshold: Minimum similarity ratio (0.0 to 1.0)

        Returns:
            Best matching canonical team name or None
        """
        best_match = None
        best_score = 0.0

        # Check against all variations
        for canonical, variations in cls.TEAM_NICKNAMES.items():
            for variation in variations:
                similarity = SequenceMatcher(None, user_input, variation).ratio()
                if similarity > best_score and similarity >= threshold:
                    best_score = similarity
                    best_match = canonical

        return best_match

    @classmethod
    def validate_entities(cls, entities: Dict) -> Dict:
        """
        Validate and normalize extracted entities.

        Args:
            entities: Raw entities from UNDERSTAND node
                     e.g., {"teams": ["Cats", "Tigers"], "seasons": ["2024"]}

        Returns:
            Validation result with corrected entities and warnings
        """
        result = {
            "is_valid": True,
            "corrected_entities": {},
            "warnings": [],
            "suggestions": []
        }

        # Validate and resolve teams
        if "teams" in entities and entities["teams"]:
            corrected_teams = []
            for team_input in entities["teams"]:
                resolved = cls.resolve_team(team_input)
                if resolved:
                    corrected_teams.append(resolved)
                else:
                    result["is_valid"] = False
                    result["warnings"].append(f"Unknown team: '{team_input}'")
                    result["suggestions"].append(
                        f"Did you mean one of these teams? {', '.join(list(cls.TEAM_NICKNAMES.keys())[:5])}"
                    )

            result["corrected_entities"]["teams"] = corrected_teams

        # Validate seasons (basic range check)
        if "seasons" in entities and entities["seasons"]:
            corrected_seasons = []
            for season in entities["seasons"]:
                try:
                    year = int(season)
                    if 1990 <= year <= 2025:
                        corrected_seasons.append(str(year))
                    else:
                        result["warnings"].append(f"Season {year} outside data range (1990-2025)")
                except (ValueError, TypeError):
                    result["warnings"].append(f"Invalid season: '{season}'")

            result["corrected_entities"]["seasons"] = corrected_seasons

        # Handle player disambiguation
        if "players" in entities and entities["players"]:
            from app.data.database import Session
            from sqlalchemy import text

            corrected_players = []
            seasons = result["corrected_entities"].get("seasons", entities.get("seasons", []))

            for player_name in entities["players"]:
                # Check for duplicate players in database
                disambiguation_result = cls._disambiguate_player(player_name, seasons)

                if disambiguation_result["needs_clarification"]:
                    # Multiple active players found
                    result["is_valid"] = False
                    result["needs_clarification"] = True
                    result["suggestions"].append(disambiguation_result["clarification_question"])
                    # Include all candidates in corrected entities for reference
                    corrected_players.extend(disambiguation_result["candidates"])
                elif disambiguation_result["resolved_name"]:
                    # Successfully resolved to one player
                    corrected_players.append(disambiguation_result["resolved_name"])
                    if disambiguation_result["warning"]:
                        result["warnings"].append(disambiguation_result["warning"])
                else:
                    # No matches found, pass through original
                    corrected_players.append(player_name)

            result["corrected_entities"]["players"] = corrected_players

        # Pass through other entities unchanged
        for key in ["metrics", "rounds"]:
            if key in entities:
                result["corrected_entities"][key] = entities[key]

        return result

    @classmethod
    def _disambiguate_player(cls, player_name: str, seasons: List[str] = None) -> Dict[str, any]:
        """
        Disambiguate player name when multiple players exist with similar names.

        Strategy:
        1. Find all players matching the name (exact or fuzzy)
        2. If seasons provided, filter to players active during those seasons
        3. If only 1 active player → auto-select
        4. If 0 active players → return all matches with warning
        5. If 2+ active players → ask user to clarify

        Args:
            player_name: Player name from user query
            seasons: List of season years to check activity

        Returns:
            Dict with:
            - needs_clarification: bool
            - resolved_name: str (if single match)
            - candidates: List[str] (all matching names)
            - clarification_question: str (if needs clarification)
            - warning: str (optional warning message)
        """
        from app.data.database import Session
        from sqlalchemy import text

        session = Session()
        try:
            # Find all players matching the name (using ILIKE for case-insensitive partial match)
            result = session.execute(
                text("""
                    SELECT DISTINCT p.name, p.id
                    FROM players p
                    WHERE p.name ILIKE :pattern
                    ORDER BY p.name
                """),
                {"pattern": f"%{player_name}%"}
            )
            all_matches = result.fetchall()

            if len(all_matches) == 0:
                # No matches found
                return {
                    "needs_clarification": False,
                    "resolved_name": player_name,  # Pass through original
                    "candidates": [],
                    "clarification_question": None,
                    "warning": None
                }

            if len(all_matches) == 1:
                # Single match - use it
                return {
                    "needs_clarification": False,
                    "resolved_name": all_matches[0][0],
                    "candidates": [all_matches[0][0]],
                    "clarification_question": None,
                    "warning": None
                }

            # Multiple matches - check activity during specified seasons
            logger.info(f"Found {len(all_matches)} players matching '{player_name}': {[m[0] for m in all_matches]}")

            if seasons and len(seasons) > 0:
                # Filter to players active during these seasons
                active_players = []
                for player_full_name, player_id in all_matches:
                    # Check if player has any stats in the specified seasons
                    check_result = session.execute(
                        text("""
                            SELECT COUNT(*) > 0 as is_active
                            FROM player_stats ps
                            JOIN matches m ON ps.match_id = m.id
                            WHERE ps.player_id = :player_id
                            AND m.season = ANY(:seasons)
                        """),
                        {"player_id": player_id, "seasons": [int(s) for s in seasons]}
                    )
                    is_active = check_result.fetchone()[0]

                    if is_active:
                        active_players.append(player_full_name)
                        logger.info(f"  - {player_full_name}: ACTIVE in {seasons}")
                    else:
                        logger.info(f"  - {player_full_name}: NOT active in {seasons}")

                if len(active_players) == 0:
                    # No players active in specified season - return all candidates with warning
                    all_names = [m[0] for m in all_matches]
                    return {
                        "needs_clarification": False,
                        "resolved_name": all_names[0],  # Default to first
                        "candidates": all_names,
                        "clarification_question": None,
                        "warning": f"Multiple players named '{player_name}' found ({', '.join(all_names)}), but none were active in {', '.join(seasons)}. Using {all_names[0]}."
                    }

                if len(active_players) == 1:
                    # Single active player - use it
                    return {
                        "needs_clarification": False,
                        "resolved_name": active_players[0],
                        "candidates": active_players,
                        "clarification_question": None,
                        "warning": f"Resolved '{player_name}' to {active_players[0]} (active in {', '.join(seasons)})"
                    }

                # Multiple active players - ask for clarification
                season_str = ', '.join(seasons)
                return {
                    "needs_clarification": True,
                    "resolved_name": None,
                    "candidates": active_players,
                    "clarification_question": (
                        f"Multiple players named '{player_name}' were active in {season_str}: "
                        f"{', '.join(active_players)}. Which player did you mean?"
                    ),
                    "warning": None
                }

            else:
                # No season specified - ask for clarification with all matches
                all_names = [m[0] for m in all_matches]
                return {
                    "needs_clarification": True,
                    "resolved_name": None,
                    "candidates": all_names,
                    "clarification_question": (
                        f"Multiple players named '{player_name}' found: {', '.join(all_names)}. "
                        f"Which player did you mean?"
                    ),
                    "warning": None
                }

        finally:
            session.close()

    @classmethod
    def suggest_teams(cls, partial_input: str, limit: int = 5) -> List[str]:
        """
        Suggest team names based on partial input.

        Args:
            partial_input: Partial team name
            limit: Maximum suggestions to return

        Returns:
            List of suggested canonical team names
        """
        if not partial_input:
            return []

        cls._build_lookup()
        normalized = partial_input.strip().lower()

        suggestions = []
        for canonical, variations in cls.TEAM_NICKNAMES.items():
            # Check if any variation starts with the input
            if any(v.startswith(normalized) for v in variations):
                suggestions.append(canonical)
            elif normalized in canonical.lower():
                suggestions.append(canonical)

        return suggestions[:limit]

    @classmethod
    def get_all_canonical_teams(cls) -> List[str]:
        """Get list of all canonical team names."""
        return list(cls.TEAM_NICKNAMES.keys())

    @classmethod
    def get_team_variations(cls, canonical_name: str) -> List[str]:
        """Get all variations/nicknames for a canonical team name."""
        return cls.TEAM_NICKNAMES.get(canonical_name, [])


# Metric normalization
class MetricResolver:
    """Resolves metric aliases to canonical metric names."""

    METRIC_ALIASES = {
        "wins": ["wins", "victories", "won", "win", "w"],
        "losses": ["losses", "defeats", "lost", "loss", "l"],
        "draws": ["draws", "ties", "drawn", "draw", "d"],
        "goals": ["goals", "goals scored", "total goals", "score"],
        "points": ["points", "total points", "score"],
        "margin": ["margin", "winning margin", "margin of victory", "diff", "difference"],
        "percentage": ["percentage", "pct", "%", "win percentage"],
        "ladder_position": ["ladder position", "position", "rank", "ranking", "place"],
    }

    @classmethod
    def resolve_metric(cls, user_input: str) -> Optional[str]:
        """Resolve metric name from user input to canonical name."""
        if not user_input:
            return None

        normalized = user_input.strip().lower()

        for canonical, aliases in cls.METRIC_ALIASES.items():
            if normalized in aliases:
                return canonical

        return None
