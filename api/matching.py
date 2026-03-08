"""
matching.py — AI Matching Engine (Basic Version)

Scores lost vs found report pairs using weighted text + date similarity.
No ML dependencies — uses only Python stdlib (difflib) and Django ORM.

Scoring weights:
  category match    35%  (hard bonus — same category is a strong signal)
  item name         30%  (SequenceMatcher ratio on lowercased names)
  location          20%  (keyword overlap between location strings)
  date proximity    15%  (sliding scale: same day=1.0, ±7 days, beyond=0)

Confidence thresholds:
  high    >= 0.75
  medium  >= 0.50
  low      < 0.50
"""

from __future__ import annotations

import difflib
from datetime import date, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import LostReport


# ── Weight constants ──────────────────────────────────────────────────────────
W_CATEGORY = 0.35
W_NAME     = 0.30
W_LOCATION = 0.20
W_DATE     = 0.15

DATE_WINDOW_DAYS = 7   # beyond this gap the date score is 0


# ── Individual scorers ────────────────────────────────────────────────────────

def _score_category(a: "LostReport", b: "LostReport") -> float:
    """Full score if same category, zero otherwise."""
    return 1.0 if a.category == b.category else 0.0


def _score_name(a: "LostReport", b: "LostReport") -> float:
    """
    SequenceMatcher ratio on lowercased item names.
    Also gives partial credit for shared keywords (bag-of-words bonus).
    """
    name_a = a.item_name.lower().strip()
    name_b = b.item_name.lower().strip()

    # Base: sequence similarity
    seq_ratio = difflib.SequenceMatcher(None, name_a, name_b).ratio()

    # Bonus: shared keyword overlap (Jaccard)
    tokens_a = set(name_a.split())
    tokens_b = set(name_b.split())
    if tokens_a | tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    else:
        jaccard = 0.0

    # Weighted average: 60% sequence, 40% keyword
    return seq_ratio * 0.6 + jaccard * 0.4


def _score_location(a: "LostReport", b: "LostReport") -> float:
    """
    Keyword overlap between location strings (Jaccard on word tokens).
    Also checks location_detail if both reports have it.
    """
    def _tokens(report: "LostReport") -> set[str]:
        base = (report.location or "").lower()
        detail = (report.location_detail or "").lower()
        combined = f"{base} {detail}".strip()
        # strip punctuation roughly
        for ch in ".,()[]{}'\"-":
            combined = combined.replace(ch, " ")
        return set(w for w in combined.split() if len(w) > 2)  # ignore short words

    tok_a = _tokens(a)
    tok_b = _tokens(b)

    if not (tok_a | tok_b):
        return 0.0

    jaccard = len(tok_a & tok_b) / len(tok_a | tok_b)
    return jaccard


def _score_date(a: "LostReport", b: "LostReport") -> float:
    """
    Sliding-scale date score.
    Same day = 1.0
    Each day apart reduces score linearly.
    Beyond DATE_WINDOW_DAYS = 0.0
    """
    date_a: date = a.date_event
    date_b: date = b.date_event

    gap = abs((date_a - date_b).days)

    if gap == 0:
        return 1.0
    if gap > DATE_WINDOW_DAYS:
        return 0.0
    return 1.0 - (gap / DATE_WINDOW_DAYS)


# ── Main scorer ───────────────────────────────────────────────────────────────

def score_pair(lost: "LostReport", found: "LostReport") -> dict:
    """
    Compute a composite match score for a (lost, found) pair.
    Returns a dict with total score, per-component breakdown, and confidence.
    """
    cat_score  = _score_category(lost, found)
    name_score = _score_name(lost, found)
    loc_score  = _score_location(lost, found)
    date_score = _score_date(lost, found)

    total = (
        cat_score  * W_CATEGORY +
        name_score * W_NAME     +
        loc_score  * W_LOCATION +
        date_score * W_DATE
    )

    # If category doesn't match at all, cap total score at 0.40
    # (wrong category is a very strong disqualifier)
    if cat_score == 0.0:
        total = min(total, 0.40)

    confidence = (
        "high"   if total >= 0.75 else
        "medium" if total >= 0.50 else
        "low"
    )

    return {
        "score": round(total, 4),
        "confidence": confidence,
        "breakdown": {
            "category": round(cat_score,  4),
            "name":     round(name_score, 4),
            "location": round(loc_score,  4),
            "date":     round(date_score, 4),
        },
    }


# ── Engine entry point ────────────────────────────────────────────────────────

def find_matches(report: "LostReport", top_n: int = 5) -> list:
    """
    Given a single report (lost OR found), find the best matching counterparts.

    - If report is LOST  → search among FOUND reports
    - If report is FOUND → search among LOST reports

    Only considers reports with status in: open, under_review, matched
    (not claimed/closed/rejected — those are done).

    Saves/updates MatchSuggestion rows and returns the top_n queryset.
    """
    from .models import LostReport as Report, MatchSuggestion

    ACTIVE_STATUSES = [
        Report.STATUS_OPEN,
        Report.STATUS_UNDER_REVIEW,
        Report.STATUS_MATCHED,
    ]

    if report.report_type == Report.TYPE_LOST:
        candidates = Report.objects.filter(
            report_type=Report.TYPE_FOUND,
            status__in=ACTIVE_STATUSES,
        ).exclude(pk=report.pk)
        lost_report  = report
        found_lookup = True
    else:
        candidates = Report.objects.filter(
            report_type=Report.TYPE_LOST,
            status__in=ACTIVE_STATUSES,
        ).exclude(pk=report.pk)
        found_report = report
        found_lookup = False

    scored = []
    for candidate in candidates:
        if found_lookup:
            lost_r  = lost_report
            found_r = candidate
        else:
            lost_r  = candidate
            found_r = found_report

        result = score_pair(lost_r, found_r)
        scored.append((result["score"], result["confidence"], result["breakdown"], lost_r, found_r))

    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:top_n]

    # Persist suggestions (upsert)
    suggestion_ids = []
    for total_score, confidence, breakdown, lost_r, found_r in top:
        obj, _ = MatchSuggestion.objects.update_or_create(
            lost_report=lost_r,
            found_report=found_r,
            defaults={
                "score":          total_score,
                "score_breakdown": breakdown,
                "confidence":     confidence,
                "status":         MatchSuggestion.STATUS_PENDING,
            },
        )
        suggestion_ids.append(obj.pk)

    return MatchSuggestion.objects.filter(pk__in=suggestion_ids).order_by("-score")