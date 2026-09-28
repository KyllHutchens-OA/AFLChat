"""
AFL Analytics Agent - SQL Validation

Gate for LLM-generated SQL before it reaches the database. Parses with sqlglot
(postgres dialect) and walks the full tree, so nested subqueries, CTEs and set
operations are all checked. Defence in depth only: the agent also runs as the
read-only `agent_ro` role inside a READ ONLY transaction (app/agent/tools.py).
"""
import re
from typing import Optional
import logging

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError

logger = logging.getLogger(__name__)


class SQLValidator:
    """
    Validates agent SQL:
    1. Exactly one statement, and it is a query (SELECT / WITH ... SELECT / set op)
    2. No write or DDL node anywhere in the tree (incl. data-modifying CTEs, SELECT INTO, FOR UPDATE)
    3. Every referenced table is allowlisted (CTE names excepted), no foreign schemas
    4. No denylisted functions (file access, sleep, dblink, large objects, config, query_to_xml...)
    5. Forbidden keywords as a word-boundary backstop
    """

    # Allowlisted tables (must match the SELECT grants of agent_ro in scripts/db/roles.sql)
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

    # Forbidden keywords (word-boundary backstop to the tree walk)
    FORBIDDEN_KEYWORDS = {
        "DROP", "DELETE", "UPDATE", "INSERT", "ALTER",
        "CREATE", "TRUNCATE", "GRANT", "REVOKE",
        "EXEC", "EXECUTE", "CALL", "DECLARE", "COPY", "MERGE",
    }

    # Node types that must never appear anywhere in an agent query
    FORBIDDEN_NODES = (
        exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop,
        exp.Alter, exp.TruncateTable, exp.Command, exp.Copy, exp.Set,
        exp.Into, exp.Lock, exp.Grant,
    )

    # Denied function names (lowercase) and prefixes
    FORBIDDEN_FUNCTIONS = {
        "set_config", "current_setting", "copy", "loread", "lowrite",
        "dblink", "dblink_exec", "dblink_connect", "dblink_send_query",
        "query_to_xml", "query_to_xmlschema", "query_to_xml_and_xmlschema",
        "cursor_to_xml", "cursor_to_xmlschema", "table_to_xml", "table_to_xmlschema",
        "table_to_xml_and_xmlschema", "schema_to_xml", "database_to_xml",
        "txid_current", "inet_server_addr", "inet_server_port",
    }
    FORBIDDEN_FUNCTION_PREFIXES = ("pg_", "lo_", "dblink", "_pg")

    @classmethod
    def validate(cls, sql: str) -> tuple[bool, Optional[str]]:
        """Return (is_valid, error_message)."""
        try:
            if not sql or len(sql.strip()) < 10:
                return False, "Query too short to be valid"

            try:
                statements = [s for s in sqlglot.parse(sql, read="postgres") if s is not None]
            except ParseError as e:
                return False, f"Unable to parse SQL query: {str(e).splitlines()[0][:200]}"

            if not statements:
                return False, "Unable to parse SQL query"
            if len(statements) > 1:
                return False, "Only a single SQL statement is allowed"

            tree = statements[0]

            if not isinstance(tree, exp.Query):
                return False, "Only SELECT statements are allowed"

            for node in tree.walk():
                if isinstance(node, cls.FORBIDDEN_NODES):
                    return False, f"Forbidden operation: {type(node).__name__.upper()}"

            forbidden_found = cls._find_forbidden_keywords(sql)
            if forbidden_found:
                return False, f"Forbidden keyword found: {forbidden_found}"

            bad_func = cls._find_forbidden_function(tree)
            if bad_func:
                return False, f"Function not allowed: {bad_func}"

            tables, bad_schema = cls._extract_tables(tree)
            if bad_schema:
                return False, f"Schema not allowed: {bad_schema}"
            invalid_tables = tables - cls.ALLOWED_TABLES
            if invalid_tables:
                return False, f"Invalid table names: {', '.join(sorted(invalid_tables))}"

            return True, None

        except Exception as e:
            logger.error(f"SQL validation error: {e}")
            return False, "Validation error"

    @classmethod
    def _find_forbidden_keywords(cls, sql) -> Optional[str]:
        """
        Word-boundary keyword match, so identifiers like `created_at` or
        `updated_by` don't trip CREATE / UPDATE. String literals are ignored.
        """
        sql_str = re.sub(r"'(?:[^']|'')*'", "''", str(sql))
        for keyword in sorted(cls.FORBIDDEN_KEYWORDS):
            if re.search(rf'\b{re.escape(keyword)}\b', sql_str, re.IGNORECASE):
                return keyword
        return None

    @classmethod
    def _find_forbidden_function(cls, tree: exp.Expression) -> Optional[str]:
        for func in tree.find_all(exp.Func):
            if isinstance(func, exp.Anonymous):
                name = str(func.this or "").lower()
            else:
                name = (func.sql_name() or "").lower()
            if name in cls.FORBIDDEN_FUNCTIONS or name.startswith(cls.FORBIDDEN_FUNCTION_PREFIXES):
                return name
        return None

    @classmethod
    def _extract_tables(cls, tree: exp.Expression) -> tuple[set[str], Optional[str]]:
        """Real table names referenced anywhere in the tree (CTE names removed), plus the first bad schema."""
        cte_names = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
        tables = set()
        for table in tree.find_all(exp.Table):
            # Table-valued functions (generate_series, unnest) are covered by the function check
            if not isinstance(table.this, exp.Identifier):
                continue
            if table.catalog or (table.db and table.db.lower() != "public"):
                return tables, ".".join(p for p in (table.catalog, table.db) if p)
            name = table.name.lower()
            if table.db or name not in cte_names:
                tables.add(name)
        return tables, None
