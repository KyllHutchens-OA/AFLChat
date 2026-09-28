"""Warm the AFL Tables match-page cache (1.5s between requests).

    python -m app.data.fixes_1c.prefetch 2026 2024 1990-1996
Without args: every season 1990-current. Cached pages are never re-fetched.
"""
import os
import sys
import time

from app.data.fixes_1c.sources import aflt_season, fetch_aflt, _cache_path


def _years(args):
    out = []
    for a in args:
        if "-" in a:
            lo, hi = a.split("-")
            out.extend(range(int(lo), int(hi) + 1))
        else:
            out.append(int(a))
    return out or list(range(1990, time.localtime().tm_year + 1))


def main():
    for year in _years(sys.argv[1:]):
        games = aflt_season(year)
        todo = [g.stats_url for g in games if g.stats_url and not os.path.exists(
            _cache_path("aflt", g.stats_url.strip("/").replace("/", "__")))]
        print(f"{year}: {len(games)} games, {len(todo)} to fetch", flush=True)
        for url in todo:
            try:
                fetch_aflt(url)
            except Exception as e:  # keep going; a re-run retries failures
                print(f"  FAILED {url}: {e}", flush=True)


if __name__ == "__main__":
    main()
