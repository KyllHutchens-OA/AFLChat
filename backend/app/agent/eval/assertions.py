"""
Value matching against live ground truth.

Pure functions, no DB or LLM. Three targets:
  text   numbers/names extracted from the answer text
  rows   the agent's result rows (TurnResult.rows)
  chart  the plotted ChartSpecV1 data (normalised to (x, series, value) points)

Numbers: `tol` when given, else rounding-aware. A text number shown with d
decimals matches truth v when |x - v| <= 0.5 * 10^-d; a non-integer truth
needs >= 1 decimal shown (so "28" never passes for 27.65). Row/chart cells
are exact for integers and within max(0.051, 0.1%) for floats.

Names: full string, a known team alias, or (for people) the surname.
"""
import math
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# Canonical team name -> extra accepted spellings (lowercase).
TEAM_ALIASES: Dict[str, List[str]] = {
    "adelaide": ["crows"],
    "brisbane lions": ["brisbane", "lions"],
    "brisbane bears": ["brisbane", "bears"],
    "carlton": ["blues"],
    "collingwood": ["magpies", "pies"],
    "essendon": ["bombers"],
    "fremantle": ["dockers", "freo"],
    "geelong": ["cats"],
    "gold coast": ["suns", "gold coast suns"],
    "greater western sydney": ["gws", "giants", "gws giants"],
    "hawthorn": ["hawks"],
    "melbourne": ["demons"],
    "north melbourne": ["kangaroos", "north"],
    "port adelaide": ["power", "port"],
    "richmond": ["tigers"],
    "st kilda": ["saints"],
    "sydney": ["swans", "sydney swans"],
    "west coast": ["eagles", "west coast eagles"],
    "western bulldogs": ["bulldogs", "dogs", "footscray"],
    "fitzroy": ["lions"],
}

_ORDINAL_WORDS = {
    1: "first", 2: "second", 3: "third", 4: "fourth", 5: "fifth", 6: "sixth",
    7: "seventh", 8: "eighth", 9: "ninth", 10: "tenth", 11: "eleventh",
    12: "twelfth", 13: "thirteenth", 14: "fourteenth", 15: "fifteenth",
    16: "sixteenth", 17: "seventeenth", 18: "eighteenth",
}

_NUM_RE = re.compile(r"(?<![\w.])-?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?")


# ---------------------------------------------------------------------------
# Scalars
# ---------------------------------------------------------------------------
def as_number(v: Any) -> Optional[float]:
    """Numeric value of a cell (int/float/Decimal/numeric string), else None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return None if (isinstance(v, float) and math.isnan(v)) else float(v)
    try:
        s = str(v).strip().replace(",", "").rstrip("%")
        if not s or not re.fullmatch(r"-?\d+(\.\d+)?", s):
            return None
        return float(s)
    except (TypeError, ValueError):
        return None


def _is_int(v: float) -> bool:
    return abs(v - round(v)) < 1e-9


def numbers_in_text(text: str) -> List[Tuple[float, int]]:
    """(value, decimals_shown) for every number in text.

    "18.12" also yields 18 and 12 (AFL goals.behinds notation), "1,066" -> 1066,
    "3rd" -> 3.
    """
    out: List[Tuple[float, int]] = []
    for m in _NUM_RE.finditer(text or ""):
        whole = m.group(1).replace(",", "")
        frac = m.group(2)
        if frac is not None:
            out.append((float(f"{whole}.{frac}"), len(frac)))
            out.append((float(whole), 0))
            out.append((float(frac), 0))
        else:
            out.append((float(whole), 0))
    return out


def text_has_number(text: str, v: float, tol: Optional[float] = None) -> bool:
    for x, d in numbers_in_text(text):
        if tol is not None:
            if abs(x - v) <= tol + 1e-9:
                return True
            continue
        if not _is_int(v) and d == 0:
            continue
        if abs(x - v) <= 0.5 * 10 ** (-d) + 1e-9:
            return True
    return False


def cell_matches_number(cell: Any, v: float, tol: Optional[float] = None) -> bool:
    x = as_number(cell)
    if x is None:
        return False
    if tol is not None:
        return abs(x - v) <= tol + 1e-9
    if _is_int(v) and _is_int(x):
        return round(x) == round(v)
    return abs(x - v) <= max(0.051, 0.001 * abs(v))


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _word_in(haystack_norm: str, needle_norm: str) -> bool:
    if not needle_norm:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(needle_norm) + r"(?![a-z0-9])", haystack_norm) is not None


def name_variants(name: str) -> List[str]:
    """Accepted spellings of a truth string (normalised)."""
    n = _norm(name)
    variants = [n]
    if n in TEAM_ALIASES:
        variants += [_norm(a) for a in TEAM_ALIASES[n]]
    elif len(n.split()) >= 2:
        # Person: surname is enough ("Neale" for "Lachie Neale").
        last = n.split()[-1]
        if len(last) >= 3:
            variants.append(last)
    return variants


def text_has_name(text: str, name: str) -> bool:
    hay = _norm(text)
    return any(_word_in(hay, v) for v in name_variants(name))


def label_matches(label: Any, truth: Any) -> bool:
    """Chart x / series label vs a truth value (number or name)."""
    tv = as_number(truth)
    lv = as_number(label)
    if tv is not None and lv is not None:
        return abs(tv - lv) < 1e-9
    if tv is not None:
        # "2017.0" / "R5" style labels: compare digits.
        return _word_in(_norm(label), str(int(tv)) if _is_int(tv) else str(tv))
    ln = _norm(label)
    if not ln:
        return False
    # Label contains the truth name, or (>= 3 chars) is a shortening of it.
    return any(_word_in(ln, v) or (len(ln) >= 3 and _word_in(v, ln)) for v in name_variants(str(truth)))


def text_has_ordinal(text: str, v: float) -> bool:
    n = int(round(v))
    hay = (text or "").lower()
    if re.search(rf"(?<!\d){n}(st|nd|rd|th)\b", hay):
        return True
    word = _ORDINAL_WORDS.get(n)
    return bool(word and re.search(rf"\b{word}\b", hay))


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------
def rows_have_value(rows: List[Dict[str, Any]], v: Any, tol: Optional[float] = None) -> bool:
    num = as_number(v)
    for r in rows:
        for cell in r.values():
            if num is not None:
                if cell_matches_number(cell, num, tol):
                    return True
            elif isinstance(cell, str) and label_matches(cell, v):
                return True
    return False


def row_pair_match(
    rows: List[Dict[str, Any]], key: Any, value: Any, series: Any = None, tol: Optional[float] = None,
    abs_value: bool = False,
) -> bool:
    """Some agent row identifies `key` and holds `value` (under `series` if given)."""
    num = as_number(value)
    if abs_value and num is not None:
        num = abs(num)
    for r in rows:
        if not any(label_matches(c, key) for c in r.values() if c is not None):
            continue
        if series is not None:
            # Long format: a cell names the series. Wide: a column named after it.
            long_ok = any(isinstance(c, str) and label_matches(c, series) for c in r.values())
            cols = [k for k in r if label_matches(k, series)]
            cand = list(r.values()) if long_ok else [r[k] for k in cols]
        else:
            cand = list(r.values())
        for c in cand:
            cv = as_number(c)
            if num is not None and cv is not None and cell_matches_number(abs(cv) if abs_value else cv, num, tol):
                return True
            if num is None and isinstance(c, str) and label_matches(c, value):
                return True
    return False


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def chart_points(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise a ChartSpecV1 into [{x, series_labels, value}] points."""
    points: List[Dict[str, Any]] = []
    ctype = spec.get("chartType")
    data = spec.get("data") or []
    series = spec.get("series") or []
    if ctype == "pie":
        for d in data:
            points.append({"x": d.get("name"), "series": ["value"], "value": d.get("value")})
        return points
    if ctype == "scatter":
        for d in data:
            points.append({"x": d.get("x"), "series": [d.get("group") or "scatter"], "value": d.get("y")})
        return points
    for d in data:
        for s in series:
            key = s.get("key")
            if key in d:
                labels = [key] + ([s["name"]] if s.get("name") else [])
                points.append({"x": d.get("x"), "series": labels, "value": d.get(key)})
    return points


def chart_labels(spec: Dict[str, Any]) -> List[str]:
    labels = []
    for s in spec.get("series") or []:
        labels += [str(s.get("key") or ""), str(s.get("name") or "")]
    for d in spec.get("data") or []:
        labels.append(str(d.get("x", d.get("name", ""))))
    for axis in ("xAxis", "yAxis"):
        lab = (spec.get(axis) or {}).get("label")
        if lab:
            labels.append(str(lab))
    return [l for l in labels if l]


def chart_has_value(spec: Dict[str, Any], v: Any, tol: Optional[float] = None) -> bool:
    num = as_number(v)
    for p in chart_points(spec):
        if num is not None and cell_matches_number(p["value"], num, tol):
            return True
        if num is not None and cell_matches_number(p["x"], num, tol):
            return True
        if num is None and label_matches(p["x"], v):
            return True
    return False


def chart_pair_match(
    spec: Dict[str, Any], key: Any, value: Any, series: Any = None, tol: Optional[float] = None,
    abs_value: bool = False,
) -> bool:
    """A plotted point at x=key (series=series) has y=value; either orientation."""
    num = as_number(value)
    if num is None:
        return False
    if abs_value:
        num = abs(num)
    for p in chart_points(spec):
        x_is_key = label_matches(p["x"], key)
        s_is_key = any(label_matches(s, key) for s in p["series"])
        if series is None:
            ok = x_is_key
        else:
            ok = (x_is_key and any(label_matches(s, series) for s in p["series"])) or (
                s_is_key and label_matches(p["x"], series)
            )
        pv = as_number(p["value"])
        if ok and pv is not None and cell_matches_number(abs(pv) if abs_value else pv, num, tol):
            return True
    return False


def duplicate_x(spec: Dict[str, Any]) -> List[Any]:
    seen, dups = set(), []
    for d in spec.get("data") or []:
        x = str(d.get("x"))
        if x in seen:
            dups.append(x)
        seen.add(x)
    return dups


def scatter_match_frac(
    spec: Dict[str, Any], truth_rows: Iterable[Dict[str, Any]], x_col: str, y_col: str
) -> float:
    """Fraction of plotted points equal to some truth (x, y) pair (either axis order)."""
    pairs = set()
    for r in truth_rows:
        x, y = as_number(r.get(x_col)), as_number(r.get(y_col))
        if x is not None and y is not None:
            pairs.add((round(x, 1), round(y, 1)))
    data = spec.get("data") or []
    if not data:
        return 0.0
    hits = 0
    for d in data:
        x, y = as_number(d.get("x")), as_number(d.get("y"))
        if x is None or y is None:
            continue
        if (round(x, 1), round(y, 1)) in pairs or (round(y, 1), round(x, 1)) in pairs:
            hits += 1
    return hits / len(data)
