"""
Integration test: executes EVERY SQL example in app/agent/sql_examples.py
against the real database (DB_STRING from backend/.env) and asserts each one
runs without error and returns at least one row.

This is the "Executing-SQL validation of every example" check called for by
the Milestone 3b plan — marked `integration` since it hits a live DB, unlike
the rest of the M3b test suite (test_schema_docs.py, test_sql_examples.py,
test_generate_sql.py, test_retrieve_context.py), which are pure unit tests
with no DB/LLM access.

Run with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_sql_examples_integration.py -v -m integration

Run everything EXCEPT this file (the fast unit-test suite):
    venv/bin/python -m pytest tests/ -v -m "not integration"
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.sql_examples import SQL_EXAMPLES

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def db_session():
    from app.data.database import Session
    session = Session()
    yield session
    session.close()


@pytest.mark.parametrize("example", SQL_EXAMPLES, ids=[ex["id"] for ex in SQL_EXAMPLES])
def test_example_sql_executes_and_returns_rows(db_session, example):
    from sqlalchemy import text

    result = db_session.execute(text(example["sql"]))
    rows = result.fetchall()
    assert len(rows) > 0, (
        f"Example '{example['id']}' ({example['question']!r}) returned 0 rows — "
        f"either the DB has drifted since this example was verified, or the "
        f"example is broken and should be fixed/dropped."
    )


def test_every_example_sql_passes_validator():
    """Every example must also pass the same SQLValidator generated SQL is checked against."""
    from app.analytics.validators import SQLValidator

    for example in SQL_EXAMPLES:
        is_valid, error = SQLValidator.validate(example["sql"])
        assert is_valid, f"Example '{example['id']}' failed SQLValidator: {error}"
