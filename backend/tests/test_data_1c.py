"""1C data contract: round labelling, AFL Tables parsing, ingester matching, row mapping."""
from datetime import datetime
from types import SimpleNamespace

from app.data.fixes_1c.map_rows import map_match
from app.data.ingestion.afltables_pages import normalize_player_name, parse_match_page
from app.data.ingestion.stats_ingester import find_page_game
from app.data.rounds import legacy_round, round_fields_from_squiggle

_HEAD = "<tr>" + "".join(f"<th>{h}</th>" for h in ["#", "Player", "KI", "GL", "CP", "%P"]) + "</tr>"


def _club(name, players, totals):
    rows = "".join(
        f"<tr><td>1</td><td><a href='../../players/{k}.html'>{n}</a></td>"
        + "".join(f"<td>{v}</td>" for v in vals) + "</tr>"
        for k, n, vals in players)
    tot = "<tr><td colspan=2>Totals</td>" + "".join(f"<td>{v}</td>" for v in totals) + "</tr>"
    return (f"<table><thead><tr><th colspan=6>{name} Match Statistics</th></tr>{_HEAD}</thead>"
            f"<tbody>{rows}</tbody><tfoot>{tot}</tfoot></table>")


def test_squiggle_round_fields():
    assert round_fields_from_squiggle({"round": 0, "is_final": 0})["round_name"] == "Opening Round"
    gf = round_fields_from_squiggle({"round": 29, "is_final": 6})
    assert gf == {"round": "Grand Final", "round_number": 29, "round_name": "Grand Final", "is_final": True}
    assert round_fields_from_squiggle({"round": 25, "is_final": 7})["round_name"] == "Wildcard Round"
    assert legacy_round(5, "Round 5", False) == "5"


def test_match_page_blanks_are_zero_only_when_recorded():
    html = "<title>Match 26-Sep-2026</title>" + _club(
        "Brisbane Lions",
        [("H/Harris_Andrews", "Andrews, Harris", ["11", "&nbsp;", "5", "97"]),
         ("B/Bailey_Williams1", "Williams, Bailey", ["3", "2", "&nbsp;", "80"])],
        ["14", "2", "5", "&nbsp;"],
    ) + _club("Fremantle", [("J/Jye_Amiss", "Amiss, Jye", ["8", "2", "&nbsp;", "95"])], ["8", "2", "&nbsp;", "&nbsp;"])
    page = parse_match_page(html)
    bri, fre = page["teams"]
    assert bri["players"][0]["name"] == "Harris Andrews"
    assert bri["players"][1]["afltables_id"] == "B/Bailey_Williams1"
    assert bri["players"][0]["goals"] == 0                  # recorded blank -> 0
    assert bri["players"][1]["contested_possessions"] == 0  # recorded for the match (BRI total)
    assert fre["players"][0]["contested_possessions"] == 0
    assert bri["players"][0]["time_on_ground_pct"] == 97.0
    assert fre["players"][0]["clearances"] is None          # column absent -> not recorded


def test_normalize_player_name():
    assert normalize_player_name("van Rooyen, Jacob ↑") == "Jacob van Rooyen"


def test_find_page_game_uses_date_window_never_first_meeting():
    teams = {"Carlton": 13, "Collingwood": 14}
    games = [
        {"home": "Carlton", "away": "Collingwood", "is_final": False, "local_dt": datetime(2026, 3, 20, 19, 40)},
        {"home": "Collingwood", "away": "Carlton", "is_final": False, "local_dt": datetime(2026, 7, 11, 13, 45)},
    ]
    m = SimpleNamespace(id=1, home_team_id=14, away_team_id=13, is_final=False, match_date=datetime(2026, 7, 13))
    assert find_page_game(m, games, teams) is games[1]
    far = SimpleNamespace(id=2, home_team_id=14, away_team_id=13, is_final=False, match_date=datetime(2026, 5, 1))
    assert find_page_game(far, games, teams) is None


def test_map_match_prefers_stat_line_over_zeroed_name_twin():
    stats = {"kicks": 7, "handballs": 3, "marks": 2, "goals": 1, "behinds": 0, "tackles": 1, "hitouts": 0}
    zero = {k: 0 for k in stats}
    page = [{"name": "Jacob van Rooyen", "afltables_id": "J/Jacob_van_Rooyen", **stats}]
    db = [{"id": 1, "name": "Jacob Rooyen", **stats}, {"id": 2, "name": "Jacob van Rooyen", **zero}]
    pairs, dups, left_db, left_pg = map_match(db, page)
    assert [(r["id"], how) for r, _, how in pairs] == [(1, "stats+surname")]
    assert [r["id"] for r in left_db] == [2] and not left_pg and not dups
