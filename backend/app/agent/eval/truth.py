"""
Live ground truth.

Each case's `verification_sql` runs against the DB at eval time, on its own
read-only psycopg connection (separate from the engine's pool), and the
resulting rows are the expected values. Nothing numeric is hard-coded in
cases, so "this season" / "last round" cases stay correct as data changes
and as 1C repairs the data.

Skips (status "skip", never "fail"):
  - `requires_columns` lists a column that does not exist yet (e.g. 1C's
    matches.round_name / is_final / round_number)
  - the verification SQL errors (UndefinedColumn etc.)
  - the truth is empty but the case has Facts / pairs that need rows
"""
import logging
import os
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from app.agent.eval.models import EvalCase

logger = logging.getLogger(__name__)


def _db_url() -> str:
    # Same env var the app uses; backend/.env is loaded by app.config.
    try:
        import app.config  # noqa: F401  (side effect: load_dotenv)
    except Exception:  # pragma: no cover - config raises if DB_STRING missing
        pass
    url = os.getenv("DB_STRING") or ""
    # SQLAlchemy-style driver suffix is not a libpq URL.
    return url.replace("postgresql+psycopg://", "postgresql://")


def _plain(v: Any) -> Any:
    """JSON-friendly scalars (Decimal -> float/int, dates -> iso)."""
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


class TruthStore:
    """Runs verification SQL read-only and caches results for the run."""

    def __init__(self, url: Optional[str] = None):
        self.url = url or _db_url()
        self._conn = None
        self._cache: Dict[str, Tuple[Optional[List[Dict[str, Any]]], Optional[str]]] = {}
        self._columns: Optional[set] = None

    def _connection(self):
        if self._conn is None:
            import psycopg

            self._conn = psycopg.connect(self.url, autocommit=True, prepare_threshold=None)
            # Belt and braces: ground truth can never write.
            self._conn.execute("SET default_transaction_read_only = on")
            self._conn.execute("SET statement_timeout = 30000")
        return self._conn

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def describe(self) -> str:
        """host/dbname for the report header (no credentials)."""
        try:
            info = self._connection().info
            return f"{info.host}:{info.port}/{info.dbname}"
        except Exception as e:
            return f"unavailable ({type(e).__name__})"

    def existing_columns(self) -> set:
        if self._columns is None:
            rows = self._connection().execute(
                "select table_name || '.' || column_name from information_schema.columns "
                "where table_schema = 'public'"
            ).fetchall()
            self._columns = {r[0] for r in rows}
        return self._columns

    def query(self, sql: str) -> List[Dict[str, Any]]:
        """Run one read-only statement; returns plain-dict rows. Raises on error."""
        with self._connection().cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                return []
            cols = [d.name for d in cur.description]
            return [{c: _plain(v) for c, v in zip(cols, r)} for r in cur.fetchall()]

    def truth_for(self, case: EvalCase) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
        """(rows, skip_reason). rows is None when the case must be skipped."""
        missing = [c for c in case.requires_columns if c not in self.existing_columns()]
        if missing:
            return None, f"requires column(s) not in DB yet: {', '.join(missing)} (pending 1C)"
        if not case.verification_sql:
            return [], None
        sql = case.verification_sql
        if sql not in self._cache:
            try:
                self._cache[sql] = (self.query(sql), None)
            except Exception as e:
                msg = str(e).strip().splitlines()[0] if str(e).strip() else ""
                self._cache[sql] = (None, f"verification_sql failed: {type(e).__name__}: {msg}")
        rows, err = self._cache[sql]
        if err:
            return None, err
        needs_rows = bool(case.truth or case.pairs or (case.chart and (case.chart.pairs or case.chart.scatter_truth)))
        if needs_rows and not rows and case.on_empty_truth == "skip":
            return None, "ground truth is empty (verification_sql returned 0 rows)"
        return rows, None


def effective_case(case: EvalCase, truth: List[Dict[str, Any]]) -> EvalCase:
    """Case as scored today: with on_empty_truth=expect_no_data and no truth
    rows, value/chart checks are dropped and a why-no-data answer is required."""
    if truth or case.on_empty_truth != "expect_no_data":
        return case
    return case.model_copy(update={
        "truth": [], "pairs": [], "chart": None, "expects_chart": False, "expects_no_data": True,
    })
