"""
AFL Analytics Agent - SQL Validation

Prevents SQL injection and ensures queries are safe to execute.
"""
import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where
from sqlparse.tokens import Keyword, DML
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class SQLValidator:
    """
    Validates SQL queries to prevent injection attacks.

    Security measures:
    1. Only allows SELECT statements
    2. Validates table names against allowlist
    3. Blocks forbidden keywords (DROP, DELETE, UPDATE, INSERT)
    4. Ensures query is properly parsed
    """

    # Allowlisted tables
    ALLOWED_TABLES = {
        "matches",
        "live_games",  # Live/recent games table (2026+)
        "teams",
        "players",
        "player_stats",
        "team_stats",
        "betting_odds",  # Betting odds from The Odds API
        "squiggle_predictions",  # Match predictions from Squiggle
        "news_articles",  # AFL news from RSS feeds
    }

    # Forbidden keywords
    FORBIDDEN_KEYWORDS = {
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
        "CREATE", "TRUNCATE", "GRANT", "REVOKE",
        "EXEC", "EXECUTE", "CALL", "DECLARE"
    }

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, Optional[str]]:
        """
        Validate SQL query for safety.

        Args:
            sql: SQL query string

        Returns:
            Tuple of (is_valid, error_message)
        """
        try:
            # Parse SQL
            parsed = sqlparse.parse(sql)

            if not parsed:
                return False, "Unable to parse SQL query"

            statement = parsed[0]

            # 1. Check it's a SELECT statement
            if not cls._is_select_statement(statement):
                return False, "Only SELECT statements are allowed"

            # 2. Check for forbidden keywords
            forbidden_found = cls._find_forbidden_keywords(statement)
            if forbidden_found:
                return False, f"Forbidden keyword found: {forbidden_found}"

            # 3. Validate table names
            tables = cls._extract_table_names(statement)
            invalid_tables = tables - cls.ALLOWED_TABLES

            if invalid_tables:
                return False, f"Invalid table names: {', '.join(invalid_tables)}"

            # 4. Basic structure check
            if len(sql.strip()) < 10:
                return False, "Query too short to be valid"

            return True, None

        except Exception as e:
            logger.error(f"SQL validation error: {e}")
            return False, f"Validation error: {str(e)}"

    @classmethod
    def _is_select_statement(cls, statement) -> bool:
        """Check if statement is a SELECT query (including CTEs with WITH clause)."""
        sql_upper = str(statement).upper().strip()
        # Accept WITH...SELECT (CTEs) as valid SELECT statements
        if sql_upper.startswith("WITH") and "SELECT" in sql_upper:
            return True
        for token in statement.tokens:
            if token.ttype is DML and token.value.upper() == "SELECT":
                return True
        return False

    @classmethod
    def _find_forbidden_keywords(cls, statement) -> Optional[str]:
        """Find any forbidden keywords in the query."""
        sql_upper = str(statement).upper()

        for keyword in cls.FORBIDDEN_KEYWORDS:
            if keyword in sql_upper:
                return keyword

        return None

    @classmethod
    def _extract_table_names(cls, statement) -> set[str]:
        """Extract table names from SQL statement (excluding CTEs)."""
        tables = set()
        cte_names = set()

        # First, extract CTE names from WITH clauses
        cte_names = cls._extract_cte_names(statement)

        # Look for FROM and JOIN clauses
        from_seen = False
        for token in statement.tokens:
            # Check for FROM keyword
            if token.ttype is Keyword and token.value.upper() == "FROM":
                from_seen = True
                continue

            # Check for JOIN keyword
            if token.ttype is Keyword and "JOIN" in token.value.upper():
                from_seen = True
                continue

            # Extract table names after FROM or JOIN
            if from_seen:
                if isinstance(token, IdentifierList):
                    for identifier in token.get_identifiers():
                        table_name = cls._get_real_name(identifier)
                        if table_name:
                            tables.add(table_name.lower())
                elif isinstance(token, Identifier):
                    table_name = cls._get_real_name(token)
                    if table_name:
                        tables.add(table_name.lower())
                    from_seen = False
                elif token.ttype is Keyword:
                    from_seen = False

        # Remove CTE names from the table list (they're not real tables)
        tables = tables - cte_names

        return tables

    @classmethod
    def _extract_cte_names(cls, statement) -> set[str]:
        """Extract CTE (Common Table Expression) names from WITH clauses."""
        cte_names = set()
        sql_str = str(statement).upper()

        # Simple CTE detection - look for WITH ... AS pattern
        if "WITH" in sql_str:
            # Parse the query to find CTE names
            tokens_str = str(statement)
            # Extract names between WITH and AS, and between commas and AS
            import re
            # Pattern: WITH name AS or , name AS
            pattern = r'(?:WITH|,)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s+AS'
            matches = re.findall(pattern, tokens_str, re.IGNORECASE)
            for match in matches:
                cte_names.add(match.lower())

        return cte_names

    @classmethod
    def _get_real_name(cls, identifier) -> Optional[str]:
        """Get the real name of an identifier (handling aliases and subqueries)."""
        if isinstance(identifier, Identifier):
            # Check if this is a subquery (has parentheses)
            # e.g., "(SELECT ...) AS s" - we should ignore the alias "s"
            identifier_str = str(identifier)
            if identifier_str.strip().startswith('('):
                # This is a subquery alias, not a table name - ignore it
                return None

            # Handle aliases (e.g., "teams AS t" -> "teams")
            real_name = identifier.get_real_name()
            if real_name:
                return real_name
            # Fallback to first token
            return str(identifier.tokens[0]).strip()
        return str(identifier).strip()
