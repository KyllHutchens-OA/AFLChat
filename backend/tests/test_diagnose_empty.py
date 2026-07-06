"""
Unit tests for the diagnose_empty node (Milestone 3c, app/agent/diagnose_empty.py).

Two groups:
  - TestWarningConsumption / TestGenericFallback: pure unit tests, no DB access —
    exercise the "an M1 EntityResolver warning already answers the question"
    fast path.
  - TestPlayerProbe / TestTeamProbe: DB probes with a mocked SQLAlchemy Session
    (no real DB access, but exercises the actual query-building logic).
  - TestRealDbProbes (marked integration): hits the real DB for a couple of
    known player/season combinations to sanity-check the probe SQL itself.

Run the fast unit tests with (from the backend/ directory, using the project venv):
    venv/bin/python -m pytest tests/test_diagnose_empty.py -v -m "not integration"
"""
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.diagnose_empty import diagnose_empty, _probe_player, _probe_team


def _mock_session(fetchone_results=None, fetchall_results=None):
    """
    Build a MagicMock standing in for a SQLAlchemy Session whose .execute(...)
    calls are answered in order by the given fetchone/fetchall result queues.
    """
    session = MagicMock()
    fetchone_queue = list(fetchone_results or [])
    fetchall_queue = list(fetchall_results or [])

    def execute_side_effect(*args, **kwargs):
        result = MagicMock()
        result.fetchone.side_effect = lambda: fetchone_queue.pop(0) if fetchone_queue else None
        result.fetchall.side_effect = lambda: fetchall_queue.pop(0) if fetchall_queue else []
        return result

    session.execute.side_effect = execute_side_effect
    return session


class TestWarningConsumptionSeasonOutOfRange:
    """diagnose_empty should consume the M1 EntityResolver 'outside data range' warning directly."""

    def test_out_of_range_season_not_fixable(self):
        result = diagnose_empty(
            user_query="Who won the 2030 grand final?",
            entities={"seasons": ["2030"]},
            warnings=["Season 2030 outside data range (1990-2026)"],
        )
        assert result["reason_code"] == "season_out_of_range"
        assert result["fixable"] is False
        assert "2030" in result["human_reason"]
        assert "1990" in result["human_reason"] and "2026" in result["human_reason"]

    def test_pre_1990_season_not_fixable(self):
        result = diagnose_empty(
            user_query="How many goals did someone kick in 1975?",
            entities={"seasons": ["1975"]},
            warnings=["Season 1975 outside data range (1990-2026)"],
        )
        assert result["reason_code"] == "season_out_of_range"
        assert result["fixable"] is False
        assert "1990" in result["human_reason"] and "2026" in result["human_reason"]


class TestWarningConsumptionPlayerSeasonMismatch:
    """diagnose_empty should consume the M1 EntityResolver player-season-mismatch warning directly."""

    def test_explicit_season_ask_is_not_fixable(self):
        result = diagnose_empty(
            user_query="What were Nick Daicos's stats in 2015?",
            entities={"players": ["Nick Daicos"], "seasons": ["2015"]},
            warnings=["Nick Daicos has no 2015 data; seasons available: 2022, 2023, 2024, 2025, 2026"],
        )
        assert result["reason_code"] == "player_season_mismatch"
        assert result["fixable"] is False
        assert "Nick Daicos" in result["human_reason"]
        assert "2015" in result["human_reason"]
        assert "2022" in result["human_reason"]

    def test_career_style_question_is_fixable(self):
        result = diagnose_empty(
            user_query="What are Nick Daicos's career stats?",
            entities={"players": ["Nick Daicos"], "seasons": ["2015"]},
            warnings=["Nick Daicos has no 2015 data; seasons available: 2022, 2023, 2024, 2025, 2026"],
        )
        assert result["reason_code"] == "player_season_mismatch"
        assert result["fixable"] is True
        assert result["suggestion"] is not None
        assert "Nick Daicos" in result["suggestion"]

    def test_no_player_data_at_all(self):
        result = diagnose_empty(
            user_query="What were X's stats?",
            entities={"players": ["X"]},
            warnings=["X has no player-stats data available for any season."],
        )
        assert result["reason_code"] == "player_no_data"
        assert result["fixable"] is False


class TestWarningConsumptionUnknownTeam:
    def test_unresolved_team_name(self):
        result = diagnose_empty(
            user_query="How did the Sharks go in 2024?",
            entities={"teams": []},
            warnings=["Unknown team: 'Sharks'"],
        )
        assert result["reason_code"] == "team_not_found"
        assert result["fixable"] is False
        assert "Sharks" in result["human_reason"]


class TestPlayerProbe:
    """No warning already answered it — diagnose_empty falls through to a DB probe."""

    def test_player_not_found(self):
        session = _mock_session(fetchone_results=[None, None])
        with patch("app.data.database.Session", return_value=session):
            result = _probe_player("Not A Real Player", [], is_career_style=False)
        assert result["reason_code"] == "player_not_found"
        assert result["fixable"] is False

    def test_player_found_season_mismatch_not_fixable(self):
        session = _mock_session(
            fetchone_results=[(42, "Nick Daicos")],
            fetchall_results=[[(2022,), (2023,), (2024,), (2025,), (2026,)]],
        )
        with patch("app.data.database.Session", return_value=session):
            result = _probe_player("Nick Daicos", ["2015"], is_career_style=False)
        assert result["reason_code"] == "player_season_mismatch"
        assert result["fixable"] is False
        assert "2022" in result["human_reason"]

    def test_player_found_season_mismatch_fixable_when_career_style(self):
        session = _mock_session(
            fetchone_results=[(42, "Nick Daicos")],
            fetchall_results=[[(2022,), (2023,), (2024,), (2025,), (2026,)]],
        )
        with patch("app.data.database.Session", return_value=session):
            result = _probe_player("Nick Daicos", ["2015"], is_career_style=True)
        assert result["reason_code"] == "player_season_mismatch"
        assert result["fixable"] is True
        assert result["suggestion"]

    def test_player_found_no_data_at_all(self):
        session = _mock_session(
            fetchone_results=[(7, "Some Player")],
            fetchall_results=[[]],
        )
        with patch("app.data.database.Session", return_value=session):
            result = _probe_player("Some Player", [], is_career_style=False)
        assert result["reason_code"] == "player_no_data"
        assert result["fixable"] is False

    def test_player_found_with_requested_season_covered_blames_other_filter(self):
        session = _mock_session(
            fetchone_results=[(42, "Nick Daicos")],
            fetchall_results=[[(2022,), (2023,), (2024,), (2025,), (2026,)]],
        )
        with patch("app.data.database.Session", return_value=session):
            result = _probe_player("Nick Daicos", ["2024"], is_career_style=False)
        assert result["reason_code"] == "filter_excludes_all"
        assert result["fixable"] is False
        assert "Nick Daicos" in result["human_reason"]


class TestTeamProbe:
    def test_team_not_found(self):
        session = _mock_session(fetchone_results=[None])
        with patch("app.data.database.Session", return_value=session):
            result = _probe_team("Not A Team", [], is_career_style=False)
        assert result["reason_code"] == "team_not_found"
        assert result["fixable"] is False

    def test_team_found_season_out_of_its_range(self):
        # e.g. Gold Coast (entered the league in 2011) queried for a 1995 season.
        calls = {"n": 0}

        def execute_side_effect(*args, **kwargs):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                result.fetchone.return_value = (20, "Gold Coast")
            else:
                result.fetchone.return_value = (2011, 2026)
            return result

        session = MagicMock()
        session.execute.side_effect = execute_side_effect

        with patch("app.data.database.Session", return_value=session):
            result = _probe_team("Gold Coast", ["1995"], is_career_style=False)
        assert result["reason_code"] == "team_season_mismatch"
        assert result["fixable"] is False
        assert "2011" in result["human_reason"]

    def test_team_found_season_in_range_blames_other_filter(self):
        calls = {"n": 0}

        def execute_side_effect(*args, **kwargs):
            calls["n"] += 1
            result = MagicMock()
            if calls["n"] == 1:
                result.fetchone.return_value = (3, "Collingwood")
            else:
                result.fetchone.return_value = (1990, 2026)
            return result

        session = MagicMock()
        session.execute.side_effect = execute_side_effect

        with patch("app.data.database.Session", return_value=session):
            result = _probe_team("Collingwood", ["2024"], is_career_style=False)
        assert result["reason_code"] == "filter_excludes_all"
        assert result["fixable"] is False


class TestGenericFallback:
    def test_no_entities_no_warnings(self):
        result = diagnose_empty(user_query="Show me something", entities={}, warnings=[])
        assert result["reason_code"] == "filter_excludes_all"
        assert result["fixable"] is False


@pytest.mark.integration
class TestRealDbProbes:
    """Sanity-check the probe SQL against the real database."""

    def test_nick_daicos_2015_mismatch_against_real_db(self):
        result = diagnose_empty(
            user_query="What were Nick Daicos's stats in 2015?",
            entities={"players": ["Nick Daicos"], "seasons": ["2015"]},
            warnings=[],
        )
        # Whether it comes from a warning or a live probe, the reason must
        # name the mismatch, not fall through to the generic fallback.
        assert result["reason_code"] in ("player_season_mismatch", "player_not_found")
        assert result["fixable"] is False
