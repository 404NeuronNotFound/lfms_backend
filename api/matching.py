"""
matching.py — AI Matching Engine (Enhanced: Multilingual + Description-Aware)

Scores lost vs found report pairs using weighted text + date similarity.
No ML dependencies — uses only Python stdlib (difflib, re) and Django ORM.

NEW in this version:
  • Bisaya / Cebuano / Filipino / Tagalog keyword normalization
  • Description field scoring (item descriptions are compared after translation)
  • Colour / brand / size extraction from any language
  • Smarter tokenization: strips diacritics, expands common abbreviations
  • Cross-language synonym matching (bisaya word → english canonical form)

Scoring weights:
  category match    25%  (hard bonus — same category is a strong signal)
  item name         25%  (normalised + translated before comparison)
  description       25%  (new — compares full descriptions cross-language)
  location          15%  (keyword overlap, location synonyms expanded)
  date proximity    10%  (sliding scale: same day=1.0, ±10 days, beyond=0)

Confidence thresholds:
  high    >= 0.72
  medium  >= 0.48
  low      < 0.48
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import LostReport


# ── Weight constants ──────────────────────────────────────────────────────────
W_CATEGORY    = 0.25
W_NAME        = 0.25
W_DESCRIPTION = 0.25
W_LOCATION    = 0.15
W_DATE        = 0.10

DATE_WINDOW_DAYS = 10   # wider window — local reporters often approximate dates


# ── Bisaya / Cebuano / Filipino / Tagalog → English dictionary ────────────────
# Format: "local word or phrase": "english equivalent(s) space-separated"
# Empty string "" = stop word (dropped during normalisation)

LOCAL_TO_ENGLISH: dict[str, str] = {
    # ── Pronouns / helpers (stop words) ──────────────────────────────────
    "akong": "", "akoa": "", "ako": "", "nako": "", "naku": "",
    "among": "", "amo": "", "namo": "",
    "imong": "", "imo": "", "nimo": "",
    "iyang": "", "iya": "", "niya": "",
    "atong": "", "ato": "", "nato": "",
    "ilang": "", "ila": "", "nila": "",
    "ang": "", "sa": "", "og": "", "ug": "", "nga": "", "na": "",
    "ko": "", "ka": "", "ni": "", "si": "", "kang": "",
    "adto": "", "diri": "", "dinhi": "", "didto": "",
    "naa": "", "wala": "", "dili": "", "duna": "",
    "kanang": "", "kini": "", "kana": "",
    "pero": "", "kaso": "", "busa": "",

    # ── Common report phrases ──────────────────────────────────────────────
    "nawala": "lost",
    "nawalan": "lost",
    "nahulog": "dropped fallen",
    "nahibilin": "left behind forgotten",
    "nakalimtan": "forgotten left",
    "nakit-an": "found",
    "nakita": "found",
    "nakit an": "found",
    "nakakaplag": "found",
    "nakaplag": "found",
    "natagbo": "found",
    "gitagbo": "found",
    "gibiyaan": "left abandoned",
    "gikuha": "taken",
    "nawagtang": "lost missing",
    "nawagta": "lost missing",
    "dala": "brought carried",
    "gidala": "brought carried",
    "gibutang": "placed put",
    "nabutangan": "placed left",
    "misplace": "misplaced",
    "wala ko": "lost",
    "nawala ko": "i lost",
    "nawala ang": "lost",
    "nakit-an nako": "i found",
    "nakita nako": "i found",

    # ── Colours / kulay ───────────────────────────────────────────────────
    "pula": "red",
    "puti": "white",
    "itom": "black",
    "asul": "blue",
    "berde": "green",
    "dilaw": "yellow",
    "orange": "orange",
    "brown": "brown",
    "kayumanggi": "brown",
    "abohon": "gray grey",
    "abo": "gray grey",
    "pilak": "silver",
    "bulawan": "gold golden",
    "rosas": "pink",
    "morado": "purple violet",
    "lila": "purple violet",
    "cream": "cream beige",
    "maliwanag": "light bright",
    "madilim": "dark",
    "transparent": "transparent clear",
    "klaro": "clear transparent",

    # ── Sizes / gidak-on ─────────────────────────────────────────────────
    "gamay": "small little",
    "dako": "big large",
    "dakong": "big large",
    "taas": "tall long",
    "mubo": "short small",
    "manipis": "thin slim",
    "baga": "thick fat",
    "bag-o": "new",
    "bago": "new",
    "daan": "old",
    "luma": "old worn",
    "guba": "broken damaged",
    "sira": "broken damaged",
    "punit": "torn ripped",
    "medyo": "slightly",
    "importante": "important valuable",

    # ── Common lost items ─────────────────────────────────────────────────
    "telepono": "phone cellphone",
    "selpon": "phone cellphone",
    "cp": "phone cellphone",
    "laplap": "laptop",
    "kompyuter": "computer",
    "earphone": "earphone earphones",
    "relo": "watch",
    "singsing": "ring",
    "kwentas": "necklace",
    "hikaw": "earrings",
    "pulseras": "bracelet",
    "mochila": "backpack",
    "pitaka": "wallet",
    "karteras": "wallet purse",
    "payong": "umbrella",
    "sumbrero": "hat cap",
    "kalo": "hat cap",
    "sapatos": "shoes",
    "tsinelas": "slippers sandals",
    "salawal": "pants trousers",
    "sinina": "shirt dress",
    "blusa": "blouse shirt",
    "dyaket": "jacket",
    "kwaderno": "notebook",
    "libro": "book",
    "bolpen": "pen ballpen",
    "lapis": "pencil",
    "susi": "key keys",
    "yabi": "key keys",
    "lisensya": "license id card",
    "atm": "atm card",
    "dokumento": "document",
    "papel": "paper document",
    "salamin": "glasses eyeglasses",
    "shades": "sunglasses shades",
    "power bank": "powerbank",
    "helmet": "helmet",
    "id card": "id card identification",
    "id": "id identification",

    # ── Brands (normalise alternate spellings) ────────────────────────────
    "iphone": "iphone apple",
    "samsung": "samsung",
    "oppo": "oppo",
    "vivo": "vivo",
    "realme": "realme",
    "xiaomi": "xiaomi",
    "huawei": "huawei",
    "nokia": "nokia",
    "apple": "apple",
    "nike": "nike",
    "adidas": "adidas",
    "jansport": "jansport",

    # ── Location words ────────────────────────────────────────────────────
    "eskwelahan": "school",
    "paaralan": "school",
    "simbahan": "church",
    "ospital": "hospital",
    "palengke": "market",
    "tindahan": "store shop",
    "bangko": "bank",
    "terminal": "terminal bus terminal",
    "estasyon": "station",
    "parke": "park",
    "kalsada": "road street",
    "dalan": "road street path",
    "balay": "house home",
    "opisina": "office",
    "canteen": "canteen cafeteria",
    "kantina": "canteen cafeteria",
    "cr": "comfort room restroom bathroom",
    "comfort room": "comfort room restroom bathroom",
    "jeepney": "jeepney",
    "jeep": "jeep jeepney",

    # ── Tagalog equivalents ───────────────────────────────────────────────
    "nahanap": "found",
    "natagpuan": "found",
    "naiwanan": "left behind",
    "nakalimutan": "forgotten",
    "itim": "black",
    "malaki": "big large",
    "maliit": "small little",
    "damit": "clothes clothing",

    # ── Numbers in Bisaya ─────────────────────────────────────────────────
    "usa": "one 1",
    "duha": "two 2",
    "tulo": "three 3",
    "upat": "four 4",
    "lima": "five 5",
}

# Pre-sort phrase keys longest-first so multi-word phrases match before single words
_PHRASE_KEYS = sorted(
    [k for k in LOCAL_TO_ENGLISH if " " in k],
    key=len, reverse=True,
)


# ── Text normalisation helpers ────────────────────────────────────────────────

def _strip_diacritics(text: str) -> str:
    """Remove accent marks: é→e, ñ→n, etc."""
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize(text: str) -> str:
    """
    Full normalisation pipeline:
    1. Lowercase + strip diacritics
    2. Replace punctuation with spaces
    3. Translate multi-word local phrases
    4. Translate single local words / drop stop-words
    5. Collapse whitespace
    """
    if not text:
        return ""
    text = _strip_diacritics(text.lower().strip())
    text = re.sub(r"[^\w\s]", " ", text)

    # Multi-word phrase pass
    for phrase in _PHRASE_KEYS:
        replacement = LOCAL_TO_ENGLISH[phrase]
        text = text.replace(phrase, f" {replacement} ")

    # Single-word pass
    tokens = text.split()
    out = []
    for tok in tokens:
        mapped = LOCAL_TO_ENGLISH.get(tok)
        if mapped is None:
            out.append(tok)            # keep (possibly English)
        elif mapped:                   # non-empty → translated word(s)
            out.extend(mapped.split())
        # empty string → stop word, silently dropped
    return " ".join(out).strip()


def _token_set(text: str) -> set[str]:
    """Return set of meaningful tokens from normalised text (len >= 2)."""
    return set(w for w in normalize(text).split() if len(w) >= 2)


# ── Attribute extraction ──────────────────────────────────────────────────────

COLOUR_WORDS = {
    "red","blue","green","yellow","black","white","gray","grey","brown",
    "orange","pink","purple","violet","gold","golden","silver","cream",
    "beige","maroon","navy","teal","cyan","dark","light",
}
SIZE_WORDS      = {"small","big","large","medium","tall","short","thin","thick","mini"}
CONDITION_WORDS = {"new","old","broken","damaged","torn","worn","cracked","scratched"}


def _extract_attributes(text: str) -> dict[str, set]:
    tokens = set(normalize(text).split())
    return {
        "colours":    tokens & COLOUR_WORDS,
        "sizes":      tokens & SIZE_WORDS,
        "conditions": tokens & CONDITION_WORDS,
    }


def _attribute_bonus(a_text: str, b_text: str) -> float:
    """
    Returns 0.0–1.0 bonus for shared attributes (colour/size/condition).
    Penalises conflicting attributes (e.g. red vs blue).
    """
    attrs_a = _extract_attributes(a_text)
    attrs_b = _extract_attributes(b_text)
    bonus, penalty = 0.0, 0.0
    for key in ("colours", "sizes", "conditions"):
        sa, sb = attrs_a[key], attrs_b[key]
        if not sa or not sb:
            continue
        shared   = sa & sb
        conflict = sa ^ sb
        if shared:
            bonus   += len(shared) * 0.15
        if conflict and not shared:
            penalty += len(conflict) * 0.10
    return max(0.0, min(1.0, bonus - penalty))


# ── Individual scorers ────────────────────────────────────────────────────────

def _jaccard(a: set, b: set) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def _score_category(a: "LostReport", b: "LostReport") -> float:
    return 1.0 if a.category == b.category else 0.0


def _score_name(a: "LostReport", b: "LostReport") -> float:
    """
    Compare item names after full normalisation (Bisaya/Tagalog → English).
    """
    norm_a = normalize(a.item_name)
    norm_b = normalize(b.item_name)
    seq    = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    jac    = _jaccard(_token_set(a.item_name), _token_set(b.item_name))
    attr   = _attribute_bonus(a.item_name, b.item_name)
    base   = seq * 0.55 + jac * 0.45
    return min(1.0, base + attr * 0.20)


def _score_description(a: "LostReport", b: "LostReport") -> float:
    """
    Compare item descriptions after normalisation.
    Handles Bisaya / Tagalog / mixed text.
    Missing description → neutral 0.30 (doesn't hurt the score).
    """
    desc_a = (
        getattr(a, "description", None)
        or getattr(a, "item_description", None)
        or ""
    ).strip()
    desc_b = (
        getattr(b, "description", None)
        or getattr(b, "item_description", None)
        or ""
    ).strip()

    if not desc_a or not desc_b:
        return 0.30

    norm_a = normalize(desc_a)
    norm_b = normalize(desc_b)
    jac    = _jaccard(_token_set(desc_a), _token_set(desc_b))
    seq    = difflib.SequenceMatcher(None, norm_a, norm_b).ratio()
    attr   = _attribute_bonus(desc_a, desc_b)
    base   = jac * 0.65 + seq * 0.35
    return min(1.0, base + attr * 0.25)


def _score_location(a: "LostReport", b: "LostReport") -> float:
    """Keyword overlap on normalised (translated) location strings."""
    def _loc(r: "LostReport") -> set[str]:
        base   = (r.location or "").lower()
        detail = (getattr(r, "location_detail", None) or "").lower()
        return set(w for w in normalize(f"{base} {detail}").split() if len(w) > 2)
    return _jaccard(_loc(a), _loc(b))


def _score_date(a: "LostReport", b: "LostReport") -> float:
    gap = abs((a.date_event - b.date_event).days)
    if gap == 0:   return 1.0
    if gap > DATE_WINDOW_DAYS: return 0.0
    return 1.0 - (gap / DATE_WINDOW_DAYS)


# ── Main scorer ───────────────────────────────────────────────────────────────

def score_pair(lost: "LostReport", found: "LostReport") -> dict:
    """
    Compute a composite match score for a (lost, found) pair.
    Returns total score, per-component breakdown, and confidence label.
    """
    cat_score  = _score_category(lost, found)
    name_score = _score_name(lost, found)
    desc_score = _score_description(lost, found)
    loc_score  = _score_location(lost, found)
    date_score = _score_date(lost, found)

    total = (
        cat_score  * W_CATEGORY    +
        name_score * W_NAME        +
        desc_score * W_DESCRIPTION +
        loc_score  * W_LOCATION    +
        date_score * W_DATE
    )

    # Wrong category caps total at 0.42 — strong disqualifier
    if cat_score == 0.0:
        total = min(total, 0.42)

    # Small reward when both name AND description match well
    if name_score >= 0.70 and desc_score >= 0.55:
        total = min(1.0, total + 0.05)

    confidence = (
        "high"   if total >= 0.72 else
        "medium" if total >= 0.48 else
        "low"
    )

    return {
        "score":      round(total, 4),
        "confidence": confidence,
        "breakdown": {
            "category":    round(cat_score,  4),
            "name":        round(name_score, 4),
            "description": round(desc_score, 4),
            "location":    round(loc_score,  4),
            "date":        round(date_score, 4),
        },
    }


# ── Engine entry point ────────────────────────────────────────────────────────

def find_matches(report: "LostReport", top_n: int = 5) -> list:
    """
    Given a single report (lost OR found), find the best matching counterparts.
    Saves/updates MatchSuggestion rows and returns the top_n queryset.
    """
    from .models import LostReport as Report, MatchSuggestion
    from django.db import transaction

    ACTIVE_STATUSES = [
        Report.STATUS_OPEN,
        Report.STATUS_UNDER_REVIEW,
        Report.STATUS_MATCHED,
    ]

    if report.report_type == Report.TYPE_LOST:
        candidates   = Report.objects.filter(report_type=Report.TYPE_FOUND,  status__in=ACTIVE_STATUSES).exclude(pk=report.pk)
        lost_report  = report
        found_lookup = True
    else:
        candidates   = Report.objects.filter(report_type=Report.TYPE_LOST, status__in=ACTIVE_STATUSES).exclude(pk=report.pk)
        found_report = report
        found_lookup = False

    scored = []
    for candidate in candidates:
        lost_r, found_r = (report, candidate) if found_lookup else (candidate, report)
        result = score_pair(lost_r, found_r)
        scored.append((result["score"], result["confidence"], result["breakdown"], lost_r, found_r))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    suggestion_ids = []
    with transaction.atomic():
        for total_score, confidence, breakdown, lost_r, found_r in top:
            obj, _ = MatchSuggestion.objects.update_or_create(
                lost_report=lost_r,
                found_report=found_r,
                defaults={
                    "score":           total_score,
                    "score_breakdown": breakdown,
                    "confidence":      confidence,
                    "status":          MatchSuggestion.STATUS_PENDING,
                },
            )
            suggestion_ids.append(obj.pk)

    return MatchSuggestion.objects.filter(pk__in=suggestion_ids).order_by("-score")