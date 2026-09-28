"""
Unit tests for SQLValidator (app/analytics/validators.py).

Covers the word-boundary forbidden-keyword fix: naive substring matching used
to trip on column names like `created_at` (contains "CREATE") or `updated_by`
(contains "UPDATE"). The fix switches to \\b-bounded regex matching.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_validators.py -v
"""
import os
import sys

# Ensure `backend/` is importable as the project root when running this file
# directly (e.g. `python tests/test_validators.py`) rather than via `-m pytest`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.analytics.validators import SQLValidator


class TestForbiddenKeywordWordBoundary:
    """Column names that merely contain a forbidden keyword as a substring must pass."""

    def test_created_at_column_passes(self):
        sql = "SELECT id, name, created_at FROM matches WHERE created_at > '2020-01-01'"
        found = SQLValidator._find_forbidden_keywords(sql)
        assert found is None, f"Expected no forbidden keyword, but found: {found}"

    def test_updated_by_column_passes(self):
        sql = "SELECT id, updated_by FROM matches WHERE updated_by = 'admin'"
        found = SQLValidator._find_forbidden_keywords(sql)
        assert found is None, f"Expected no forbidden keyword, but found: {found}"

    def test_created_at_full_validate_passes(self):
        sql = "SELECT id, created_at FROM matches WHERE season = 2024"
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid, f"Expected valid SQL, got error: {error}"

    def test_updated_by_full_validate_passes(self):
        sql = "SELECT id, updated_by FROM players WHERE updated_by ILIKE '%system%'"
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid, f"Expected valid SQL, got error: {error}"

    def test_deleted_at_column_passes(self):
        """Bonus case: `deleted_at` contains DELETE as a substring."""
        sql = "SELECT id, deleted_at FROM matches WHERE deleted_at IS NULL"
        found = SQLValidator._find_forbidden_keywords(sql)
        assert found is None, f"Expected no forbidden keyword, but found: {found}"


class TestForbiddenKeywordStillBlocked:
    """Actual forbidden statements must still be detected and blocked."""

    def test_drop_table_blocked(self):
        sql = "DROP TABLE matches"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid
        assert "DROP" in (error or "") or "Only SELECT" in (error or "")

    def test_drop_table_keyword_detected(self):
        found = SQLValidator._find_forbidden_keywords("DROP TABLE matches")
        assert found == "DROP"

    def test_delete_statement_blocked(self):
        sql = "DELETE FROM matches WHERE id = 1"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid

    def test_update_statement_blocked(self):
        sql = "UPDATE matches SET home_score = 100 WHERE id = 1"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid

    def test_insert_statement_blocked(self):
        sql = "INSERT INTO matches (season) VALUES (2024)"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid

    def test_drop_table_embedded_in_select_blocked(self):
        """A forbidden keyword appearing anywhere (e.g. stacked statement) must still be caught."""
        sql = "SELECT * FROM matches; DROP TABLE matches;"
        found = SQLValidator._find_forbidden_keywords(sql)
        assert found == "DROP"


class TestBasicValidSelect:
    """Sanity checks that ordinary valid SELECT queries still pass."""

    def test_simple_select_passes(self):
        sql = "SELECT name, season FROM matches WHERE season = 2024"
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid, f"Expected valid SQL, got error: {error}"

    def test_select_with_join_passes(self):
        sql = (
            "SELECT p.name, SUM(ps.goals) AS total_goals "
            "FROM player_stats ps JOIN players p ON ps.player_id = p.id "
            "WHERE p.name ILIKE '%Hawkins%' GROUP BY p.id, p.name"
        )
        is_valid, error = SQLValidator.validate(sql)
        assert is_valid, f"Expected valid SQL, got error: {error}"

    def test_invalid_table_rejected(self):
        sql = "SELECT * FROM secret_table"
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid


class TestFullTreeValidation:
    """sqlglot walks the whole tree: statements, subqueries, CTEs, set ops, functions."""

    def _rejected(self, sql, fragment):
        is_valid, error = SQLValidator.validate(sql)
        assert not is_valid, f"Expected rejection for: {sql}"
        assert fragment in (error or ""), error

    def test_multiple_statements_rejected(self):
        self._rejected("SELECT * FROM matches; DROP TABLE matches;", "single SQL statement")
        self._rejected("SELECT 1 FROM matches; SELECT 2 FROM teams", "single SQL statement")

    def test_non_allowlisted_table_in_nested_subquery_rejected(self):
        self._rejected(
            "SELECT * FROM matches WHERE id IN (SELECT 1 FROM (SELECT * FROM conversations) c)",
            "conversations",
        )
        self._rejected("SELECT season FROM matches UNION SELECT 1 FROM api_usage", "api_usage")

    def test_foreign_schema_rejected(self):
        self._rejected("SELECT * FROM pg_catalog.pg_user", "Schema not allowed")
        self._rejected("SELECT * FROM information_schema.tables", "Schema not allowed")

    def test_denylisted_functions_rejected(self):
        for sql in (
            "SELECT pg_sleep(10) FROM matches",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT lo_import('/etc/passwd')",
            "SELECT set_config('statement_timeout', '0', false)",
            "SELECT query_to_xml('select * from conversations', true, true, '')",
            "SELECT dblink('host=x', 'select 1')",
        ):
            self._rejected(sql, "Function not allowed")

    def test_writes_inside_query_rejected(self):
        self._rejected("WITH x AS (DELETE FROM matches RETURNING *) SELECT * FROM x", "DELETE")
        self._rejected("SELECT * INTO new_table FROM matches", "INTO")
        self._rejected("SELECT * FROM matches FOR UPDATE", "LOCK")

    def test_cte_and_generate_series_allowed(self):
        for sql in (
            "WITH t AS (SELECT * FROM teams) SELECT * FROM t",
            "SELECT g FROM generate_series(1, 3) g",
            "SELECT name FROM players WHERE name = 'Drop Bear'",
        ):
            is_valid, error = SQLValidator.validate(sql)
            assert is_valid, f"{sql}: {error}"


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
