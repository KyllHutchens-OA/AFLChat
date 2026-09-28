"""1C step 10: player stats for every completed match that has none, via the stats
ingester, reading AFL Tables pages through the 1C cache (AFL_1C_CACHE).

    python -m app.data.fixes_1c.backfill

Commits per match (as the ingester does); a re-run only targets what is still missing.
"""
import logging

from app.data.fixes_1c.sources import fetch_aflt
from app.data.ingestion.stats_ingester import ingest_from_afl_tables


def main():
    logging.basicConfig(level=logging.WARNING)
    out = ingest_from_afl_tables(fetch=fetch_aflt)
    print({k: (v if k != "unavailable" else len(v)) for k, v in out.items()})
    for u in out["unavailable"]:
        print("  still unavailable:", u)


if __name__ == "__main__":
    main()
