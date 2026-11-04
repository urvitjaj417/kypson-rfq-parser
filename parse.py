"""Rule-based parser for short packaging RFQs.

The function deliberately uses only the Python standard library so it can run
without network access or model/API dependencies.
"""

from __future__ import annotations

import re
from difflib import get_close_matches
from typing import Optional


CATEGORIES = (
    "bopp_bag",
    "woven_sack",
    "corrugated_box",
    "pouch",
    "film",
    "mono_carton",
    "fibc",
)

# Longest/more specific phrases are checked first.
CATEGORY_ALIASES = {
    "bopp_bag": (
        "bopp laminated bag", "bopp laminated bags", "bopp bag", "bopp bags",
        "bopp", "pp woven bag", "pp woven bags", "laminated woven bag",
        "laminated bag", "laminated bags",
    ),
    "woven_sack": (
        "cement bag", "cement bags", "ad star bag", "ad star bags", "adstar bag",
        "woven sack", "woven sacks", "woven bag", "woven bags", "pp sack", "sack",
    ),
    "corrugated_box": (
        "corrugated box", "corrugated boxes", "carton box", "carton boxes",
        "shipping box", "box", "boxes",
    ),
    "pouch": ("stand up pouch", "stand-up pouch", "zipper pouch", "pouch", "pouches"),
    "film": (
        "shrink film", "shrink wrap", "shrinkfilm", "stretch film", "stretch wrap",
        "stretchfilm", "plastic film", "packaging film", "film", "films",
    ),
    "mono_carton": ("mono carton", "mono cartons", "monocarton", "monocartons"),
    "fibc": (
        "fibc", "jumbo bag", "jumbo bags", "bulk bag", "bulk bags",
        "big bag", "big bags", "flexible intermediate bulk container",
    ),
}

# A few frequent misspellings are useful, but the parser does not depend on a
# fixed list of cities or an external gazetteer.
CATEGORY_TYPO_ALIASES = {
    "bop bags": "bopp_bag",
    "bop bag": "bopp_bag",
    "bopp bage": "bopp_bag",
    "corrugted box": "corrugated_box",
    "corugated box": "corrugated_box",
    "pouuch": "pouch",
    "mon carton": "mono_carton",
    "monno carton": "mono_carton",
    "fbc bag": "fibc",
    "fib bag": "fibc",
    "jumpo bag": "fibc",
    "strech film": "film",
    "shink film": "film",
}

_NUMBER = r"\d+(?:[\d,]*\d)?(?:\.\d+)?"
_NUMBER_RE = re.compile(
    rf"(?<![\w.])(?P<num>{_NUMBER})(?:\s*(?P<mult>k|K|lakh|lakhs|lac|lacs|लाख|hazaar|hazar|thousand|million|crore|crores))?(?![\w.])",
    re.IGNORECASE,
)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u2013", "-").replace("\u2014", "-")).strip()


def _norm_phrase(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _number_value(raw: str, multiplier: Optional[str]) -> int | float:
    value: float = float(raw.replace(",", ""))
    if multiplier:
        m = multiplier.lower()
        if m in {"k", "hazaar", "hazar", "thousand"}:
            value *= 1_000
        elif m in {"lakh", "lakhs", "lac", "lacs", "लाख"}:
            value *= 100_000
        elif m == "million":
            value *= 1_000_000
        elif m in {"crore", "crores"}:
            value *= 10_000_000
    return int(value) if value.is_integer() else value


def _find_category(text: str) -> str:
    normalized = _norm_phrase(text)
    for alias, category in sorted(CATEGORY_TYPO_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if _norm_phrase(alias) in normalized:
            return category
    for category, aliases in CATEGORY_ALIASES.items():
        for alias in sorted(aliases, key=len, reverse=True):
            if _norm_phrase(alias) in normalized:
                return category

    # Conservative fuzzy fallback for a single misspelled product phrase.
    words = normalized.split()
    candidates = list(CATEGORY_ALIASES)
    for word in words:
        close = get_close_matches(word, ["bopp", "pouch", "film", "fibc", "sack", "box", "carton"] , n=1, cutoff=0.84)
        if close:
            if close[0] == "bopp":
                return "bopp_bag"
            if close[0] == "pouch":
                return "pouch"
            if close[0] == "film":
                return "film"
            if close[0] == "fibc":
                return "fibc"
            if close[0] == "sack":
                return "woven_sack"
            if close[0] in {"box", "carton"}:
                return "corrugated_box" if close[0] == "box" else "mono_carton"
    return "film"  # the worked examples and marketplace default use film for generic wrap


def _extract_measurement(text: str, labels: str) -> Optional[int | float]:
    pattern = re.compile(
        rf"(?<!\w)(?P<a>{_NUMBER})\s*(?P<label>{labels})\b|\b(?P<label2>{labels})\s*(?P<b>{_NUMBER})",
        re.IGNORECASE,
    )
    match = pattern.search(text)
    if not match:
        return None
    raw = match.group("a") or match.group("b")
    value = float(raw.replace(",", ""))
    return int(value) if value.is_integer() else value


def _unit_for_label(label: str) -> Optional[str]:
    label = label.lower().replace(".", "")
    if label in {"pc", "pcs", "piece", "pieces", "nos", "no", "bags", "bag", "boxes", "box", "roll", "rolls", "units", "unit"}:
        return "pcs"
    if label in {"kg", "kgs", "kilo", "kilos", "kilogram", "kilograms"}:
        return "kg"
    if label in {"mt", "ton", "tons", "tonne", "tonnes"}:
        return "mt"
    return None


def _extract_quantity(text: str, category: str) -> tuple[int | float, str]:
    # Measurements that describe capacity or the contents of one package are
    # never order quantities. Keep their spans out of the candidate list.
    excluded: list[tuple[int, int]] = []
    for m in re.finditer(r"\b(?:capacity|capcity|filling|fill|weight|per\s+(?:bag|piece|unit)|each)\b[^,;]*?(?=\band\b|[,;]|$)", text, re.IGNORECASE):
        excluded.append((m.start(), m.end()))

    candidates: list[tuple[int | float, str, int, int, int]] = []
    unit_re = re.compile(
        rf"(?P<num>{_NUMBER}(?:\s*(?:k|lakh|lakhs|lac|lacs|hazaar|hazar|thousand|million|crore|crores))?)\s*(?P<unit>pcs?|pieces?|nos?|bags?|boxes?|units?|rolls?|kg|kgs?|kilos?|kilograms?|mt|tons?|tonnes?)\b",
        re.IGNORECASE,
    )
    for match in unit_re.finditer(text):
        if any(a <= match.start() < b for a, b in excluded) or re.match(r"\s*(?:capacity|capcity|filling|fill|weight)\b", text[match.end():match.end() + 24], re.IGNORECASE):
            continue
        num_match = re.match(rf"(?P<base>{_NUMBER})(?:\s*(?P<mult>k|lakh|lakhs|lac|lacs|hazaar|hazar|thousand|million|crore|crores))?$", match.group("num"), re.IGNORECASE)
        if not num_match:
            continue
        value = _number_value(num_match.group("base"), num_match.group("mult"))
        unit = _unit_for_label(match.group("unit")) or "pcs"
        # Priority: explicit count units, then kg/mt, with earlier text as a tie-break.
        priority = 0 if unit == "pcs" else 1
        candidates.append((value, unit, priority, match.start(), match.end()))

    # Messages sometimes put the product name between the number and its
    # commercial unit: "30k shrink wrap kg". This is intentionally limited to
    # a short same-clause gap and still rejects capacity/fill-weight wording.
    flexible_re = re.compile(
        rf"(?P<num>{_NUMBER}(?:\s*(?:k|lakh|lakhs|lac|lacs|hazaar|hazar|thousand|million|crore|crores))?)\s+(?P<middle>[A-Za-z -]{{1,25}}?)\s*(?P<unit>kg|kgs?|kilos?|kilograms?|mt|tons?|tonnes?)\b",
        re.IGNORECASE,
    )
    for match in flexible_re.finditer(text):
        if any(a <= match.start() < b for a, b in excluded) or re.search(r"\b(?:capacity|capcity|filling|fill|weight)\b", text[match.end():match.end() + 24], re.IGNORECASE):
            continue
        num_match = re.match(rf"(?P<base>{_NUMBER})(?:\s*(?P<mult>k|lakh|lakhs|lac|lacs|hazaar|hazar|thousand|million|crore|crores))?$", match.group("num"), re.IGNORECASE)
        if num_match:
            value = _number_value(num_match.group("base"), num_match.group("mult"))
            unit = _unit_for_label(match.group("unit")) or "kg"
            candidates.append((value, unit, 1, match.start(), match.end()))

    # Bare numbers are accepted for an item request, but never if they belong
    # to GSM, micron, capacity, or another recognized measurement.
    if not candidates:
        for match in _NUMBER_RE.finditer(text):
            before = text[max(0, match.start() - 12):match.start()].lower()
            after = text[match.end():match.end() + 18].lower()
            if re.search(r"(?:gsm|micron|mic|capacity|capcity|kg\s+capacity|fill|weight)\s*$", before) or re.match(r"\s*(?:gsm|micron|mic|kg\s+capacity)", after):
                continue
            candidates.append((_number_value(match.group("num"), match.group("mult")), "pcs", 2, match.start(), match.end()))

    if not candidates:
        return 0, "pcs"
    candidates.sort(key=lambda item: (item[2], item[3]))
    value, unit = candidates[0][0], candidates[0][1]
    return value, unit


def _extract_location(text: str) -> Optional[str]:
    # Prefer explicit delivery/location prepositions. Stop at common field
    # separators so later measurements are not swallowed.
    patterns = (
        r"\b(?:deliver(?:y)?|ship(?:ping)?|send|dispatch|to)\s+(?:to|at|in)?\s*([^,;|]+)",
        r"\b(?:location|loc|place|city)\s*[:=-]\s*([^,;|]+)",
        r"\b(?:in|at|near|from)\s+([A-Za-z][A-Za-z .'-]{1,39})",
    )
    for pattern in patterns[:2]:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            value = _tidy_location(match.group(1))
            if value:
                return value

    # In these RFQs a final comma-delimited text segment is usually the city.
    parts = [p.strip() for p in re.split(r"[,;|]", text) if p.strip()]
    if len(parts) >= 2:
        candidate = _tidy_location(parts[-1])
        if candidate and not re.search(r"\b(?:gsm|mic(?:ron)?|pcs?|pieces?|kg|mt|ton(?:ne)?s?|capacity)\b", candidate, re.IGNORECASE):
            if re.search(r"[A-Za-z]", candidate):
                return candidate

    match = re.search(patterns[2], text, re.IGNORECASE)
    if match:
        value = _tidy_location(match.group(1))
        if value:
            return value

    # A common compact style is "5000 pieces to Chennai" or "80 mic Pune".
    tail = re.search(r"(?:\b(?:pcs?|pieces?|nos?|units?|kg|mt|tons?|tonnes?|mic(?:ron)?s?|gsm)\b)\s+([A-Za-z][A-Za-z .'-]{1,39})$", text, re.IGNORECASE)
    if tail:
        value = _tidy_location(tail.group(1))
        if value:
            return value
    return None


def _tidy_location(value: str) -> Optional[str]:
    value = re.sub(r"\s+", " ", value).strip(" .:-")
    value = re.sub(r"\b(?:please|pls|plz|only|required|needed|quote)\b.*$", "", value, flags=re.IGNORECASE).strip(" .:-")
    # Do not mistake a measurement tail or product phrase for a location.
    if not value or len(value) > 60 or re.search(r"\d", value):
        return None
    return value[:1].upper() + value[1:]


def parse_rfq(text: str) -> dict:
    """Parse one RFQ and return exactly the six fields required by the task."""
    text = _clean_text(str(text or ""))
    category = _find_category(text)
    quantity, unit = _extract_quantity(text, category)
    return {
        "category": category,
        "quantity": quantity,
        "unit": unit,
        "gsm": _extract_measurement(text, r"gsm"),
        "micron": _extract_measurement(text, r"mic(?:ron)?s?"),
        "location": _extract_location(text),
    }
