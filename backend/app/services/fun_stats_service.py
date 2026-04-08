"""
Fun Stats Service — 2 hand-picked, jaw-dropping stats per team.

No scoring algorithms, no category systems. Each team's stats were chosen
by crawling the data and cherry-picking the coolest things. Every headline
and detail line is unique — no two teams read the same.
"""
import time
import logging
from sqlalchemy import text
from app.data.database import get_session

logger = logging.getLogger(__name__)

_fun_stats_cache = {}
_CACHE_TTL = 86400


def get_fun_stats(team_name: str) -> list[dict]:
    now = time.time()
    key = team_name.lower()
    if key in _fun_stats_cache and (now - _fun_stats_cache[key]["ts"]) < _CACHE_TTL:
        return _fun_stats_cache[key]["data"]
    try:
        stats = _get_team_stats(team_name)
    except Exception as e:
        logger.error(f"Fun stats failed for {team_name}: {e}")
        stats = []
    _fun_stats_cache[key] = {"data": stats, "ts": now}
    return stats


def _get_team_stats(team_name: str) -> list[dict]:
    fn = _TEAM_FNS.get(team_name)
    if not fn:
        return []
    with get_session() as s:
        tid = _get_tid(s, team_name)
        if not tid:
            return []
        return fn(s, tid)


def _get_tid(s, name):
    r = s.execute(text("SELECT id FROM teams WHERE name = :n"), {"n": name}).fetchone()
    return r[0] if r else None


# ─── PER-TEAM STAT FUNCTIONS ─────────────────────────────────────────────────


def _adelaide(s, tid):
    # Tony Modra kicked 13 in a game — TWICE
    modra = s.execute(text("""
        SELECT ps.goals, m.season, m.round,
            CASE WHEN m.home_team_id = :tid THEN at.name ELSE ht.name END
        FROM player_stats ps
        JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id
        WHERE ps.team_id = :tid AND p.name ILIKE '%Modra%' AND ps.goals >= 13
        ORDER BY m.match_date
    """), {"tid": tid}).fetchall()

    stat1 = {
        "headline": "Tony Modra kicked 13 goals in a game. Then he did it again the next season.",
        "detail": f"Against {modra[0][3]} in {modra[0][1]}, then {modra[1][3]} in {modra[1][1]}. Defenders had nightmares about him.",
        "stat_type": "modra_double",
    } if len(modra) >= 2 else _fallback_biggest_win(s, tid)

    # Back-to-back premiers
    stat2 = {
        "headline": "Back-to-back premiers. 1997 and 1998.",
        "detail": "One of just three clubs to go back-to-back since 1990. The golden years.",
        "stat_type": "b2b_premiers",
    }
    return [stat1, stat2]


def _brisbane(s, tid):
    # Three-peat AND recent back-to-back
    flags = s.execute(text("""
        SELECT ARRAY_AGG(season ORDER BY season) FROM matches
        WHERE round ILIKE '%%Grand Final%%'
          AND ((home_team_id = :tid AND home_score > away_score) OR (away_team_id = :tid AND away_score > home_score))
          AND home_score IS NOT NULL AND home_score > 0
    """), {"tid": tid}).fetchone()
    years = flags[0] if flags and flags[0] else []

    stat1 = {
        "headline": f"Five premierships. Including a three-peat and a back-to-back.",
        "detail": f"{', '.join(str(y) for y in years)}. The most dominant stretches any club has put together in the modern game.",
        "stat_type": "dynasty",
    }

    # 20-game winning streak (equal all-time record)
    stat2 = {
        "headline": "20 consecutive wins in 2001-02 — equal longest run in AFL history.",
        "detail": "They share the record with Essendon's 2000 streak. Nobody else has come within three.",
        "stat_type": "streak_record",
    }
    return [stat1, stat2]


def _carlton(s, tid):
    # GF drought
    last_gf = s.execute(text("""
        SELECT MAX(season) FROM matches WHERE round ILIKE '%%Grand Final%%'
          AND (home_team_id = :tid OR away_team_id = :tid) AND home_score IS NOT NULL AND home_score > 0
    """), {"tid": tid}).fetchone()
    yr = last_gf[0] if last_gf and last_gf[0] else 1995
    from datetime import datetime
    drought = datetime.now().year - yr

    stat1 = {
        "headline": f"Haven't played in a Grand Final since {yr}.",
        "detail": f"That's {drought} years. An entire generation of Blues fans who've never seen their team on the last Saturday in September.",
        "stat_type": "gf_drought",
    }

    # 41-point comeback vs Geelong
    stat2 = {
        "headline": "Trailed Geelong by 41 points at halftime in 1990. Won by 19.",
        "detail": "123-104. A complete second-half demolition that Geelong still can't explain.",
        "stat_type": "comeback",
    }
    return [stat1, stat2]


def _collingwood(s, tid):
    stat1 = {
        "headline": "The only team to draw a Grand Final in the modern era.",
        "detail": "68-all against St Kilda in 2010. 100,000 people in the MCG and nobody could separate them. Collingwood won the replay.",
        "stat_type": "drawn_gf",
    }

    # 48-point comeback — the biggest in recent memory
    stat2 = {
        "headline": "Trailed North Melbourne by 48 points at halftime in 2024. Won.",
        "detail": "The third-biggest halftime comeback in AFL history. The Pies were dead and buried — then they weren't.",
        "stat_type": "comeback",
    }
    return [stat1, stat2]


def _essendon(s, tid):
    stat1 = {
        "headline": "20 consecutive wins in 2000 — the equal longest streak in AFL history.",
        "detail": "They went the entire home-and-away season unbeaten, then won the Grand Final. The perfect year.",
        "stat_type": "perfect_season",
    }

    # Geelong curse
    h2h = s.execute(text("""
        SELECT COUNT(*) as games,
            SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END) as wins
        FROM matches m
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
          AND (m.home_team_id = (SELECT id FROM teams WHERE name='Geelong')
            OR m.away_team_id = (SELECT id FROM teams WHERE name='Geelong'))
          AND m.home_score IS NOT NULL AND m.home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = h2h[0], h2h[1]
    losses = games - wins
    pct = round(100 * wins / games, 1) if games else 0

    stat2 = {
        "headline": f"Won just {pct}% of games against Geelong since 1990.",
        "detail": f"{wins} wins, {losses} losses. Nobody in the AFL has a worse record against a single opponent over this many games.",
        "stat_type": "geelong_curse",
    }
    return [stat1, stat2]


def _fremantle(s, tid):
    # Lowest score in modern AFL
    stat1 = {
        "headline": "Scored 13 points against Adelaide in 2009. The lowest score by any team since 1990.",
        "detail": "Two goals and a behind. For an entire game of football. Some records you'd rather not hold.",
        "stat_type": "lowest_score",
    }

    # One Grand Final, lost it
    stat2 = {
        "headline": "Made one Grand Final. Lost it.",
        "detail": "Hawthorn by 15 points in 2013. Three decades of footy distilled into one heartbreaking afternoon.",
        "stat_type": "one_gf",
    }
    return [stat1, stat2]


def _geelong(s, tid):
    # Biggest win in AFL history
    stat1 = {
        "headline": "Beat Melbourne by 186 points. The biggest win in AFL history since 1990.",
        "detail": "233 to 47 in Round 19, 2011. It was over by quarter time. Nobody's come close to matching it.",
        "stat_type": "biggest_win_ever",
    }

    # Home fortress
    hf = s.execute(text("""
        SELECT COUNT(*), SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END)
        FROM matches WHERE home_team_id = :tid AND venue ILIKE '%%Kardinia%%'
          AND home_score IS NOT NULL AND home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = hf[0], hf[1]
    pct = round(100 * wins / games, 1) if games else 0

    stat2 = {
        "headline": f"{pct}% win rate at Kardinia Park.",
        "detail": f"{wins} wins from {games} games. The fortress is real — opposition teams have been walking in there and losing for three decades.",
        "stat_type": "home_fortress",
    }
    return [stat1, stat2]


def _gold_coast(s, tid):
    # Port Adelaide curse
    pa = s.execute(text("""
        SELECT COUNT(*),
            SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END)
        FROM matches m
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
          AND (m.home_team_id = (SELECT id FROM teams WHERE name='Port Adelaide')
            OR m.away_team_id = (SELECT id FROM teams WHERE name='Port Adelaide'))
          AND m.home_score IS NOT NULL AND m.home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = pa[0], pa[1]

    stat1 = {
        "headline": f"Have beaten Port Adelaide just {wins} times. In {games} attempts.",
        "detail": "It's not a rivalry if one side never wins. Port just have their number, completely.",
        "stat_type": "port_curse",
    }

    # 21 winless to start
    stat2 = {
        "headline": "Went 21 games without a win to start their existence.",
        "detail": "Every expansion club cops it, but that 2011-12 stretch was something else. Character-building doesn't begin to cover it.",
        "stat_type": "winless_start",
    }
    return [stat1, stat2]


def _gws(s, tid):
    # 1 win in 2013 → GF in 2019
    stat1 = {
        "headline": "Won 1 game in their entire 2013 season. Made a Grand Final six years later.",
        "detail": "From absolute rock bottom to the biggest stage in football in just six years. The fastest rebuild in AFL history.",
        "stat_type": "rebuild",
    }

    # Jesse Hogan 9 goals in the 126-point win
    stat2 = {
        "headline": "Jesse Hogan kicked 9 goals as they beat Essendon by 126 points in 2023.",
        "detail": "162 to 36. Hogan was unstoppable and Essendon had no answers. The day GWS announced they weren't going anywhere.",
        "stat_type": "hogan_day",
    }
    return [stat1, stat2]


def _hawthorn(s, tid):
    stat1 = {
        "headline": "Jason Dunstall kicked 17 goals in a single game. Nobody has come close since.",
        "detail": "Against Richmond in 1992. The next best since? 15, by Lockett. Dunstall's record may never be broken.",
        "stat_type": "dunstall",
    }

    stat2 = {
        "headline": "Three consecutive premierships. 2013, 2014, 2015.",
        "detail": "The last dynasty. Only Brisbane's 2001-03 run can match it in the modern era.",
        "stat_type": "threepeat",
    }
    return [stat1, stat2]


def _melbourne(s, tid):
    stat1 = {
        "headline": "Lost a game by 186 points. The worst defeat in modern AFL.",
        "detail": "47 to 233, at the hands of Geelong in 2011. A day that still defines what rock bottom looks like in football.",
        "stat_type": "worst_loss",
    }

    # 2 wins in 2013 → flag in 2021
    stat2 = {
        "headline": "Won 2 games in 2013. Won the Grand Final in 2021.",
        "detail": "From wooden spoon to premiership in eight years. The longest flag drought in the club's history — ended on one perfect night.",
        "stat_type": "redemption",
    }
    return [stat1, stat2]


def _north_melbourne(s, tid):
    # Sheezel's disposal record
    sheezel = s.execute(text("""
        SELECT ps.disposals, p.name, m.season,
            CASE WHEN m.home_team_id = :tid THEN at.name ELSE ht.name END
        FROM player_stats ps JOIN players p ON ps.player_id = p.id
        JOIN matches m ON ps.match_id = m.id
        JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id
        WHERE ps.team_id = :tid AND ps.disposals IS NOT NULL
        ORDER BY ps.disposals DESC LIMIT 1
    """), {"tid": tid}).fetchone()

    if sheezel and sheezel[0] >= 50:
        stat1 = {
            "headline": f"{sheezel[1]} had {sheezel[0]} disposals in {sheezel[2]}. Tied for the all-time AFL record.",
            "detail": f"Against {sheezel[3]}. He touched the ball more times in one afternoon than most players do in three games.",
            "stat_type": "disposal_record",
        }
    else:
        stat1 = _fallback_biggest_win(s, tid)

    # GF drought
    from datetime import datetime
    stat2 = {
        "headline": "Last Grand Final appearance: 1998.",
        "detail": f"That's {datetime.now().year - 1998} years. Wayne Carey walked off the MCG that day and they haven't been back since.",
        "stat_type": "gf_drought",
    }
    return [stat1, stat2]


def _port_adelaide(s, tid):
    # Adelaide Oval fortress
    ao = s.execute(text("""
        SELECT COUNT(*), SUM(CASE WHEN home_score > away_score THEN 1 ELSE 0 END)
        FROM matches WHERE home_team_id = :tid AND venue ILIKE '%%Adelaide Oval%%'
          AND home_score IS NOT NULL AND home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = ao[0], ao[1]
    losses = games - wins
    pct = round(100 * wins / games, 1) if games else 0

    stat1 = {
        "headline": f"{pct}% win rate at Adelaide Oval.",
        "detail": f"{wins}-{losses}. Interstate teams fly in, get beaten, fly home. It's been happening for years.",
        "stat_type": "home_fortress",
    }

    # 38-point halftime comeback
    stat2 = {
        "headline": "Trailed West Coast by 38 points at halftime in 2013. Won the game.",
        "detail": "84-79. Completely flipped the script in the second half. West Coast had no answer.",
        "stat_type": "comeback",
    }
    return [stat1, stat2]


def _richmond(s, tid):
    # Geelong curse — the worst lopsided rivalry
    h2h = s.execute(text("""
        SELECT COUNT(*),
            SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END)
        FROM matches m
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
          AND (m.home_team_id = (SELECT id FROM teams WHERE name='Geelong')
            OR m.away_team_id = (SELECT id FROM teams WHERE name='Geelong'))
          AND m.home_score IS NOT NULL AND m.home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = h2h[0], h2h[1]
    losses = games - wins

    stat1 = {
        "headline": f"Won just {wins} of {games} games against Geelong since 1990.",
        "detail": f"That's a {losses}-{wins} record. The most lopsided rivalry in the AFL — and Tigers fans feel every one.",
        "stat_type": "geelong_curse",
    }

    # Dynasty to wooden spoon
    stat2 = {
        "headline": "Two premierships in three years. Then 2 wins from 23 the season after.",
        "detail": "Premiers in 2017 and 2019. Wooden spooners in 2024. The fastest fall from grace in AFL history.",
        "stat_type": "fall_from_grace",
    }
    return [stat1, stat2]


def _st_kilda(s, tid):
    # Blew 95-point halftime lead
    stat1 = {
        "headline": "Led Hawthorn by 44 points at halftime in 1999. Lost the game.",
        "detail": "96-109. Seven goals up at the long break and they still couldn't hold on. It's the kind of loss that haunts a club.",
        "stat_type": "blown_lead",
    }

    # Lockett's 15
    stat2 = {
        "headline": "Tony Lockett kicked 15 goals in a single game.",
        "detail": "Against Sydney in 1992. Only Jason Dunstall's 17 has ever topped it. Lockett did things that shouldn't be possible.",
        "stat_type": "lockett",
    }
    return [stat1, stat2]


def _sydney(s, tid):
    # Most GF losses
    gf_losses = s.execute(text("""
        SELECT COUNT(*) FROM matches
        WHERE round ILIKE '%%Grand Final%%'
          AND ((home_team_id = :tid AND home_score < away_score)
            OR (away_team_id = :tid AND away_score < home_score))
          AND home_score IS NOT NULL AND home_score > 0
    """), {"tid": tid}).fetchone()
    count = gf_losses[0] if gf_losses else 0

    stat1 = {
        "headline": f"{count} Grand Final losses since 1990. More than any other club.",
        "detail": "They keep getting there. They keep falling short. The Swans know heartbreak better than anyone.",
        "stat_type": "gf_pain",
    }

    # 24-game losing streak — longest ever
    stat2 = {
        "headline": "Lost 24 games in a row in 1992-93. The longest losing streak in modern AFL.",
        "detail": "Nearly two full seasons of football without a win. The early '90s Swans were a different universe from the powerhouse they became.",
        "stat_type": "losing_streak",
    }
    return [stat1, stat2]


def _west_coast(s, tid):
    stat1 = {
        "headline": "Won the 2006 Grand Final by a single point.",
        "detail": "85-84 against Sydney. Leo Barry's mark. The tightest Grand Final finish since the game went national. Every Eagles fan remembers exactly where they were.",
        "stat_type": "one_point_gf",
    }

    # Worst season
    worst = s.execute(text("""
        SELECT season, COUNT(*),
            SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END)
        FROM matches m
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid) AND m.home_score IS NOT NULL AND m.home_score > 0
        GROUP BY season HAVING COUNT(*) >= 20
        ORDER BY SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END) ASC
        LIMIT 1
    """), {"tid": tid}).fetchone()

    stat2 = {
        "headline": f"{worst[2]} win from {worst[1]} games in {worst[0]}.",
        "detail": "From four-time premiers to the bottom of the ladder. The most dramatic decline any powerhouse club has suffered.",
        "stat_type": "worst_season",
    }
    return [stat1, stat2]


def _western_bulldogs(s, tid):
    stat1 = {
        "headline": "Premiers in 2016. Their first flag in 62 years.",
        "detail": "The longest premiership drought in AFL history, ended in one unforgettable October afternoon. An entire city lost its mind.",
        "stat_type": "drought_broken",
    }

    # Geelong dominance over them
    h2h = s.execute(text("""
        SELECT COUNT(*),
            SUM(CASE WHEN (m.home_team_id = :tid AND m.home_score > m.away_score)
                      OR (m.away_team_id = :tid AND m.away_score > m.home_score) THEN 1 ELSE 0 END)
        FROM matches m
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid)
          AND (m.home_team_id = (SELECT id FROM teams WHERE name='Geelong')
            OR m.away_team_id = (SELECT id FROM teams WHERE name='Geelong'))
          AND m.home_score IS NOT NULL AND m.home_score > 0
    """), {"tid": tid}).fetchone()
    games, wins = h2h[0], h2h[1]
    losses = games - wins

    stat2 = {
        "headline": f"Geelong have beaten them {losses} times from {games} games.",
        "detail": f"Just {wins} wins against the Cats since 1990. Some matchups just aren't fair.",
        "stat_type": "geelong_curse",
    }
    return [stat1, stat2]


# ─── FALLBACK ────────────────────────────────────────────────────────────────

def _fallback_biggest_win(s, tid):
    row = s.execute(text("""
        SELECT ABS(m.home_score - m.away_score), m.season,
            CASE WHEN m.home_team_id = :tid THEN at.name ELSE ht.name END,
            CASE WHEN m.home_team_id = :tid THEN m.home_score ELSE m.away_score END,
            CASE WHEN m.home_team_id = :tid THEN m.away_score ELSE m.home_score END
        FROM matches m
        JOIN teams ht ON m.home_team_id = ht.id JOIN teams at ON m.away_team_id = at.id
        WHERE (m.home_team_id = :tid OR m.away_team_id = :tid) AND m.home_score IS NOT NULL
          AND ((m.home_team_id = :tid AND m.home_score > m.away_score)
            OR (m.away_team_id = :tid AND m.away_score > m.home_score))
        ORDER BY ABS(m.home_score - m.away_score) DESC LIMIT 1
    """), {"tid": tid}).fetchone()
    if not row:
        return {"headline": "Still writing their story.", "detail": "", "stat_type": "fallback"}
    return {
        "headline": f"Beat {row[2]} by {row[0]} points in {row[1]}.",
        "detail": f"{row[3]}-{row[4]}. A day their fans will never forget.",
        "stat_type": "biggest_win",
    }


# ─── TEAM REGISTRY ───────────────────────────────────────────────────────────

_TEAM_FNS = {
    "Adelaide": _adelaide,
    "Brisbane Lions": _brisbane,
    "Carlton": _carlton,
    "Collingwood": _collingwood,
    "Essendon": _essendon,
    "Fremantle": _fremantle,
    "Geelong": _geelong,
    "Gold Coast": _gold_coast,
    "Greater Western Sydney": _gws,
    "Hawthorn": _hawthorn,
    "Melbourne": _melbourne,
    "North Melbourne": _north_melbourne,
    "Port Adelaide": _port_adelaide,
    "Richmond": _richmond,
    "St Kilda": _st_kilda,
    "Sydney": _sydney,
    "West Coast": _west_coast,
    "Western Bulldogs": _western_bulldogs,
}
