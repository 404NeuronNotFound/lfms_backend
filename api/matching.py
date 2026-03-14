"""
matching.py — Findify Intelligent Matching Engine v3.0
═══════════════════════════════════════════════════════════════════════════════

Pure Python — zero external dependencies beyond Django ORM.
No API keys. No rate limits. No billing. Works offline.

SCORING ARCHITECTURE
────────────────────
  Stage 1 — Hard disqualifiers (short-circuit)
    • Date gap > 60 days → score = 0

  Stage 2 — Component scores (weighted sum)
    category          20%  — same=1.0, related family=0.45, else=0
    item name         25%  — weighted Jaccard + sequence ratio + brand/color bonus
    description       20%  — weighted token overlap + shared ID number bonus
    features          15%  — distinguishing_features (highest-signal field)
    location          12%  — token overlap + campus synonym cluster bonus
    date              08%  — quadratic decay: same day=1.0, >20 days=0

  Stage 3 — Bonus / penalty adjustments
    +0.12  exact brand AND color match across all text fields
    +0.20  shared serial / student number / IMEI (per number, capped)
    +0.08  name >= 0.80 AND description >= 0.60 (double confirmation)
    +0.05  name + description + features all agree (triple confirmation)
    −0.15  conflicting colors explicitly stated (red vs blue)
    −0.20  conflicting brands explicitly stated (Apple vs Samsung)
    cap    wrong category → total capped at 0.40

  Stage 4 — Confidence label
    high    >= 0.72
    medium  >= 0.48
    low      < 0.48

MULTILINGUAL SUPPORT
────────────────────
  Full Bisaya (Cebuano) / Tagalog / Filipino normalisation:
  200+ word dictionary, diacritic stripping, abbreviation expansion,
  multi-word phrase matching, campus location synonym clustering.
"""

from __future__ import annotations

import difflib
import re
import unicodedata
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import LostReport


# ═══════════════════════════════════════════════════════════════════════════════
#  WEIGHT CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
W_CATEGORY    = 0.20
W_NAME        = 0.25
W_DESCRIPTION = 0.20
W_FEATURES    = 0.15
W_LOCATION    = 0.12
W_DATE        = 0.08

DATE_WINDOW_DAYS = 20


# ═══════════════════════════════════════════════════════════════════════════════
#  MULTILINGUAL DICTIONARY
# ═══════════════════════════════════════════════════════════════════════════════
LOCAL_TO_ENGLISH: dict[str, str] = {
    # Stop words
    "akong":"","akoa":"","ako":"","nako":"","naku":"",
    "among":"","amo":"","namo":"","kamo":"","mo":"",
    "imong":"","imo":"","nimo":"","ikaw":"","ka":"",
    "iyang":"","iya":"","niya":"","siya":"",
    "atong":"","ato":"","nato":"","kita":"","ta":"",
    "ilang":"","ila":"","nila":"","sila":"",
    "ang":"","sa":"","og":"","ug":"","nga":"","na":"",
    "ko":"","ni":"","si":"","kang":"","man":"","lang":"",
    "adto":"","diri":"","dinhi":"","didto":"",
    "naa":"","wala":"","dili":"","duna":"","walay":"",
    "kanang":"","kini":"","kana":"","kining":"",
    "pero":"","kaso":"","busa":"","mao":"","unya":"",
    "gyud":"","kaayo":"","ra":"","pod":"","pud":"","sad":"",
    "ba":"","ha":"","oy":"","ay":"","eh":"","ah":"",
    "yung":"","nung":"","mga":"","po":"","ho":"","din":"",
    "daw":"","raw":"","kasi":"","kaya":"","naman":"",
    # Report actions
    "nawala":"lost","nawalan":"lost","nawagtang":"lost missing",
    "nawagta":"lost missing","nahulog":"dropped fallen",
    "nalaglag":"dropped fallen","nahibilin":"left behind forgotten",
    "nabiyaan":"left behind","nakalimtan":"forgotten left",
    "nakalimutan":"forgotten left","naiiwan":"left behind",
    "naiwanan":"left behind","nakit-an":"found","nakit an":"found",
    "nakita":"found","nakakaplag":"found","nakaplag":"found",
    "natagbo":"found","nahanap":"found","natagpuan":"found",
    "nakahanap":"found","gitagbo":"found",
    "nakit-an nako":"i found","nakita nako":"i found",
    "gibiyaan":"left abandoned","gikuha":"taken picked up",
    "gidala":"brought carried","dala":"brought carried",
    "gibutang":"placed put","nabutangan":"placed left",
    "misplace":"misplaced","inabandona":"abandoned",
    # Colors
    "pula":"red","pulang":"red",
    "puti":"white","puting":"white",
    "itom":"black","itong":"black","itim":"black",
    "asul":"blue","asong":"blue",
    "berde":"green","berdeng":"green",
    "dilaw":"yellow","dilawng":"yellow",
    "kayumanggi":"brown","abohon":"gray grey","abo":"gray grey",
    "pilak":"silver","bulawan":"gold golden","ginto":"gold golden",
    "rosas":"pink","morado":"purple violet","lila":"purple violet",
    "ube":"purple","cream":"cream beige",
    "maliwanag":"light bright","madilim":"dark","maitim":"dark black",
    "transparent":"transparent clear","klaro":"clear transparent",
    "multicolored":"multicolor","maraming kulay":"multicolor",
    # Sizes / condition
    "gamay":"small little","gagmay":"small",
    "dako":"big large","dakong":"big large","dagko":"big large",
    "taas":"tall long","mubo":"short small","manipis":"thin slim",
    "baga":"thick","bag-o":"new","bago":"new",
    "daan":"old","luma":"old worn","guba":"broken damaged",
    "sira":"broken damaged","punit":"torn ripped","biak":"cracked split",
    "medyo":"slightly","importante":"important valuable","mahal":"expensive valuable",
    # Electronics
    "telepono":"phone cellphone","selpon":"phone cellphone",
    "cp":"phone cellphone","sel":"phone cellphone",
    "laplap":"laptop","kompyuter":"computer",
    "earphone":"earphone earphones","headset":"headset headphones",
    "charger":"charger","saksakan":"charger plug",
    "baterya":"battery","power bank":"powerbank","powerbank":"powerbank",
    "flash drive":"flash drive usb","usb":"usb flash drive",
    "hard drive":"hard drive storage","calculator":"calculator",
    "camera":"camera","cam":"camera","tablet":"tablet","ipad":"tablet ipad",
    "smartwatch":"smartwatch watch","relo":"watch",
    # Bags & accessories
    "bolsa":"bag","mochila":"backpack","sako":"backpack bag",
    "pitaka":"wallet","karteras":"wallet purse",
    "payong":"umbrella","sombrero":"hat cap",
    "sumbrero":"hat cap","kalo":"hat cap","sinturon":"belt",
    # Clothing
    "sapatos":"shoes","tsinelas":"slippers sandals",
    "medyas":"socks","salawal":"pants trousers","pantalon":"pants",
    "sinina":"shirt dress","damit":"clothes clothing",
    "blusa":"blouse shirt","dyaket":"jacket",
    "uniporme":"uniform","hoodie":"hoodie sweatshirt",
    # Documents
    "kwaderno":"notebook","libro":"book",
    "bolpen":"pen ballpen","lapis":"pencil",
    "susi":"key keys","yabi":"key keys",
    "lisensya":"license id card","atm":"atm card bank card",
    "dokumento":"document","papel":"paper document",
    "passport":"passport","pasaporte":"passport",
    "id card":"id card","id":"identification id",
    # Jewelry
    "salamin":"glasses eyeglasses","shades":"sunglasses",
    "singsing":"ring","kwentas":"necklace",
    "hikaw":"earrings","pulseras":"bracelet","alahas":"jewelry jewellery",
    # Location
    "eskwelahan":"school campus","paaralan":"school",
    "simbahan":"church chapel","kapilya":"chapel",
    "ospital":"hospital clinic","klinika":"clinic",
    "palengke":"market","tindahan":"store shop",
    "bangko":"bank","estasyon":"station","parke":"park",
    "kalsada":"road street","dalan":"road street path",
    "balay":"house home","opisina":"office",
    "canteen":"canteen cafeteria","kantina":"canteen cafeteria",
    "cr":"comfort room restroom","comfort room":"restroom bathroom",
    "jeepney":"jeepney","jeep":"jeepney",
    # Brands
    "iphone":"iphone apple","samsung":"samsung galaxy",
    "oppo":"oppo","vivo":"vivo","realme":"realme",
    "xiaomi":"xiaomi redmi","huawei":"huawei","nokia":"nokia",
    "apple":"apple","google":"google pixel",
    "nike":"nike","adidas":"adidas","jansport":"jansport",
    "sony":"sony","jbl":"jbl","anker":"anker",
    "lenovo":"lenovo thinkpad","hp":"hp hewlett packard",
    "asus":"asus","acer":"acer","dell":"dell",
    "canon":"canon","fujifilm":"fujifilm","nikon":"nikon",
    "casio":"casio","seiko":"seiko","fossil":"fossil",
    "hydro flask":"hydro flask","yonex":"yonex","spalding":"spalding",
    "littmann":"littmann stethoscope",
    # Numbers
    "usa":"one 1","duha":"two 2","tulo":"three 3",
    "upat":"four 4","lima":"five 5","unom":"six 6",
}

_PHRASE_KEYS = sorted(
    [k for k in LOCAL_TO_ENGLISH if " " in k],
    key=len, reverse=True,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  CAMPUS LOCATION SYNONYM CLUSTERS
# ═══════════════════════════════════════════════════════════════════════════════
LOCATION_CLUSTERS: list[frozenset] = [
    frozenset({"library","main library","lib","reading room","study area","study room"}),
    frozenset({"cafeteria","canteen","caf","food court","dining","kantina","eating area"}),
    frozenset({"gym","gymnasium","covered court","sports complex","basketball court","court"}),
    frozenset({"chapel","church","simbahan","oratory","prayer room"}),
    frozenset({"admin","administration","registrar","admin building","main office"}),
    frozenset({"engineering","engg","engineering building","eng building"}),
    frozenset({"nursing","nursing building","college of nursing","clinical"}),
    frozenset({"it building","it lab","computer lab","cs lab","it center"}),
    frozenset({"arts","arts and sciences","as hall","as building","arts hall"}),
    frozenset({"business","business school","business building","bsba"}),
    frozenset({"medicine","med building","medical school","medicine building"}),
    frozenset({"architecture","arch hall","architecture hall","arch building"}),
    frozenset({"parking","parking lot","parking area","car park"}),
    frozenset({"oval","track","oval track","jogging area","running track"}),
    frozenset({"dorm","dormitory","dorm 1","dorm 2","residence hall","dormitory 1","dormitory 2"}),
    frozenset({"gate","main gate","guard house","guard station","entrance"}),
    frozenset({"pool","swimming pool","aquatic center","pool area"}),
    frozenset({"science","science complex","science building","chem lab","physics lab"}),
    frozenset({"graduate","graduate school","grad school","graduate building"}),
    frozenset({"student center","student affairs","osa","student services"}),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  CATEGORY FAMILIES
# ═══════════════════════════════════════════════════════════════════════════════
CATEGORY_FAMILIES: dict[str, str] = {
    "Electronics": "tech", "Wallets & Bags": "personal",
    "Clothing": "personal", "Keys": "personal", "Jewelry": "personal",
    "Documents": "documents", "Sports": "sports",
    "Books": "academic", "Other": "other", "Pets": "pets",
}

COLOR_WORDS = {
    "red","blue","green","yellow","black","white","gray","grey","brown",
    "orange","pink","purple","violet","gold","golden","silver","cream",
    "beige","maroon","navy","teal","cyan","dark","light","transparent",
    "clear","multicolor","colorful",
}
BRAND_WORDS = {
    "apple","samsung","xiaomi","huawei","oppo","vivo","realme","nokia","google",
    "sony","jbl","anker","bose","sennheiser","lenovo","hp","asus","acer","dell",
    "canon","nikon","fujifilm","gopro","casio","seiko","fossil","tissot",
    "nike","adidas","puma","jansport","hydro flask","thermos",
    "yonex","spalding","wilson","littmann",
}
_STOP_TOKENS = {
    "the","a","an","is","in","on","at","to","of","and","or","with",
    "my","i","was","were","it","its","this","that","have","has","been",
    "found","lost","item","report","please","return","help","contact",
    "thank","thanks","reward","urgent","asap","needed","looking",
}
_SERIAL_PATTERNS = [
    re.compile(r"\b\d{4}[-\u2013]\d{4,6}\b"),
    re.compile(r"\bimei\s*:?\s*\d{10,15}\b"),
    re.compile(r"\bs/?n\s*:?\s*[a-z0-9]{6,}\b"),
    re.compile(r"\bserial\s*:?\s*[a-z0-9]{5,}\b"),
    re.compile(r"\b[a-z]{2,4}\d{5,}\b"),
    re.compile(r"\b\d{5,}\b"),
]


# ═══════════════════════════════════════════════════════════════════════════════
#  NORMALISATION
# ═══════════════════════════════════════════════════════════════════════════════
def _strip_diacritics(text: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )


def normalize(text: str) -> str:
    if not text:
        return ""
    text = _strip_diacritics(text.lower().strip())
    text = re.sub(r"[^\w\s]", " ", text)
    for phrase in _PHRASE_KEYS:
        replacement = LOCAL_TO_ENGLISH[phrase]
        text = text.replace(phrase, f" {replacement} ")
    tokens = text.split()
    out: list[str] = []
    for tok in tokens:
        mapped = LOCAL_TO_ENGLISH.get(tok)
        if mapped is None:
            out.append(tok)
        elif mapped:
            out.extend(mapped.split())
    return " ".join(out).strip()


def _token_set(text: str) -> set[str]:
    return {w for w in normalize(text).split() if len(w) >= 2}


def _token_weights(tokens: set[str]) -> dict[str, float]:
    weights: dict[str, float] = {}
    for tok in tokens:
        if tok in _STOP_TOKENS:   weights[tok] = 0.1
        elif len(tok) <= 3:       weights[tok] = 0.4
        elif len(tok) <= 5:       weights[tok] = 0.7
        elif len(tok) <= 8:       weights[tok] = 1.0
        else:                     weights[tok] = 1.3
    return weights


def _weighted_jaccard(a_tokens: set[str], b_tokens: set[str]) -> float:
    if not a_tokens or not b_tokens:
        return 0.0
    wa, wb = _token_weights(a_tokens), _token_weights(b_tokens)
    all_tokens = a_tokens | b_tokens
    inter = sum(min(wa.get(t,0), wb.get(t,0)) for t in all_tokens if t in a_tokens and t in b_tokens)
    union = sum(max(wa.get(t,0), wb.get(t,0)) for t in all_tokens)
    return inter / union if union > 0 else 0.0


def _extract_colors(text: str) -> set[str]:
    return {w for w in normalize(text).split() if w in COLOR_WORDS}


def _extract_brands(text: str) -> set[str]:
    norm = normalize(text)
    return {b for b in BRAND_WORDS if b in norm}


def _color_conflict(a: str, b: str) -> bool:
    specific = COLOR_WORDS - {"dark","light","transparent","clear","colorful","multicolor"}
    ca = _extract_colors(a) & specific
    cb = _extract_colors(b) & specific
    if not ca or not cb:
        return False
    return len(ca & cb) == 0


def _brand_conflict(a: str, b: str) -> bool:
    ba, bb = _extract_brands(a), _extract_brands(b)
    if not ba or not bb:
        return False
    return len(ba & bb) == 0


def _extract_ids(text: str) -> set[str]:
    ids: set[str] = set()
    lower = text.lower()
    for pat in _SERIAL_PATTERNS:
        for m in pat.finditer(lower):
            ids.add(m.group().strip())
    return ids


def _location_cluster(loc: str) -> frozenset:
    norm = normalize(loc).lower()
    for cluster in LOCATION_CLUSTERS:
        for member in cluster:
            if member in norm or norm in member:
                return cluster
    return frozenset()


# ═══════════════════════════════════════════════════════════════════════════════
#  COMPONENT SCORERS
# ═══════════════════════════════════════════════════════════════════════════════
def _score_category(a: "LostReport", b: "LostReport") -> float:
    if a.category == b.category:
        return 1.0
    fa, fb = CATEGORY_FAMILIES.get(a.category,""), CATEGORY_FAMILIES.get(b.category,"")
    return 0.45 if fa and fa == fb else 0.0


def _score_name(a: "LostReport", b: "LostReport") -> float:
    ta, tb = _token_set(a.item_name), _token_set(b.item_name)
    if not ta or not tb:
        return 0.0
    wjac = _weighted_jaccard(ta, tb)
    seq  = difflib.SequenceMatcher(None, normalize(a.item_name), normalize(b.item_name)).ratio()
    ba, bb = _extract_brands(a.item_name), _extract_brands(b.item_name)
    ca, cb = _extract_colors(a.item_name), _extract_colors(b.item_name)
    brand_bonus = 0.10 if ba and bb and ba & bb else 0.0
    color_bonus = 0.05 if ca and cb and ca & cb else 0.0
    return min(1.0, wjac * 0.60 + seq * 0.40 + brand_bonus + color_bonus)


def _get_text(r: "LostReport", field: str) -> str:
    return (getattr(r, field, None) or "").strip()


def _score_description(a: "LostReport", b: "LostReport") -> float:
    da = _get_text(a, "description") or _get_text(a, "item_description")
    db = _get_text(b, "description") or _get_text(b, "item_description")
    if not da or not db:
        return 0.25
    ta, tb = _token_set(da), _token_set(db)
    wjac   = _weighted_jaccard(ta, tb)
    seq    = difflib.SequenceMatcher(None, normalize(da), normalize(db)).ratio()
    id_bonus = min(0.30, len(_extract_ids(da) & _extract_ids(db)) * 0.15)
    return min(1.0, wjac * 0.65 + seq * 0.35 + id_bonus)


def _score_features(a: "LostReport", b: "LostReport") -> float:
    fa = _get_text(a, "distinguishing_features")
    fb = _get_text(b, "distinguishing_features")
    if not fa or not fb:
        return 0.25
    ta, tb = _token_set(fa), _token_set(fb)
    wjac   = _weighted_jaccard(ta, tb)
    seq    = difflib.SequenceMatcher(None, normalize(fa), normalize(fb)).ratio()
    id_bonus = min(0.30, len(_extract_ids(fa) & _extract_ids(fb)) * 0.15)
    return min(1.0, wjac * 0.70 + seq * 0.30 + id_bonus)


def _score_location(a: "LostReport", b: "LostReport") -> float:
    la = f"{a.location or ''} {_get_text(a,'location_detail')}".lower()
    lb = f"{b.location or ''} {_get_text(b,'location_detail')}".lower()
    seq = difflib.SequenceMatcher(None, normalize(la), normalize(lb)).ratio()
    if seq >= 0.85:
        return min(1.0, seq + 0.10)
    wjac = _weighted_jaccard(_token_set(la), _token_set(lb))
    ca, cb = _location_cluster(la), _location_cluster(lb)
    cluster_bonus = 0.30 if ca and cb and ca == cb else 0.0
    return min(1.0, wjac * 0.70 + seq * 0.30 + cluster_bonus)


def _score_date(a: "LostReport", b: "LostReport") -> float:
    try:
        gap = abs((a.date_event - b.date_event).days)
    except Exception:
        return 0.25
    if gap == 0:
        return 1.0
    if gap > DATE_WINDOW_DAYS:
        return 0.0
    return max(0.0, 1.0 - (gap / DATE_WINDOW_DAYS) ** 1.5)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN SCORER
# ═══════════════════════════════════════════════════════════════════════════════
def score_pair(lost: "LostReport", found: "LostReport") -> dict:
    # Hard disqualifier
    try:
        if abs((lost.date_event - found.date_event).days) > 60:
            return {"score":0.0,"confidence":"low","breakdown":{
                "category":0.0,"name":0.0,"description":0.0,
                "features":0.0,"location":0.0,"date":0.0}}
    except Exception:
        pass

    cat_s  = _score_category(lost, found)
    name_s = _score_name(lost, found)
    desc_s = _score_description(lost, found)
    feat_s = _score_features(lost, found)
    loc_s  = _score_location(lost, found)
    date_s = _score_date(lost, found)

    total = (
        cat_s  * W_CATEGORY    +
        name_s * W_NAME        +
        desc_s * W_DESCRIPTION +
        feat_s * W_FEATURES    +
        loc_s  * W_LOCATION    +
        date_s * W_DATE
    )

    # Aggregate text for bonus/penalty checks
    all_lost  = f"{lost.item_name} {_get_text(lost,'description')} {_get_text(lost,'distinguishing_features')}"
    all_found = f"{found.item_name} {_get_text(found,'description')} {_get_text(found,'distinguishing_features')}"

    # Bonuses
    bl, bf = _extract_brands(all_lost), _extract_brands(all_found)
    cl, cf = _extract_colors(all_lost), _extract_colors(all_found)
    if bl and bf and bl & bf and cl and cf and cl & cf:
        total += 0.12

    shared_ids = len(_extract_ids(all_lost) & _extract_ids(all_found))
    if shared_ids:
        total += min(0.20, shared_ids * 0.10)

    if name_s >= 0.80 and desc_s >= 0.60:
        total += 0.08

    if name_s >= 0.70 and desc_s >= 0.55 and feat_s >= 0.55:
        total += 0.05

    # Penalties
    if _color_conflict(all_lost, all_found):
        total -= 0.15
    if _brand_conflict(all_lost, all_found):
        total -= 0.20

    # Category cap
    if cat_s == 0.0:
        total = min(total, 0.40)

    total = round(max(0.0, min(1.0, total)), 4)
    confidence = "high" if total >= 0.72 else "medium" if total >= 0.48 else "low"

    return {
        "score": total,
        "confidence": confidence,
        "breakdown": {
            "category":    round(cat_s,  4),
            "name":        round(name_s, 4),
            "description": round(desc_s, 4),
            "features":    round(feat_s, 4),
            "location":    round(loc_s,  4),
            "date":        round(date_s, 4),
        },
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  ENGINE ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════════
def find_matches(report: "LostReport", top_n: int = 5) -> list:
    from .models import LostReport as Report, MatchSuggestion
    from django.db import transaction

    ACTIVE = [Report.STATUS_OPEN, Report.STATUS_UNDER_REVIEW, Report.STATUS_MATCHED]

    if report.report_type == Report.TYPE_LOST:
        candidates   = Report.objects.filter(report_type=Report.TYPE_FOUND, status__in=ACTIVE).exclude(pk=report.pk)
        found_lookup = True
    else:
        candidates   = Report.objects.filter(report_type=Report.TYPE_LOST,  status__in=ACTIVE).exclude(pk=report.pk)
        found_lookup = False

    scored = []
    for candidate in candidates:
        lr, fr = (report, candidate) if found_lookup else (candidate, report)
        result = score_pair(lr, fr)
        scored.append((result["score"], result["confidence"], result["breakdown"], lr, fr))

    scored.sort(key=lambda x: x[0], reverse=True)

    suggestion_ids = []
    with transaction.atomic():
        for score, confidence, breakdown, lr, fr in scored[:top_n]:
            obj, _ = MatchSuggestion.objects.update_or_create(
                lost_report=lr, found_report=fr,
                defaults={
                    "score": score, "score_breakdown": breakdown,
                    "confidence": confidence, "status": MatchSuggestion.STATUS_PENDING,
                },
            )
            suggestion_ids.append(obj.pk)

    return MatchSuggestion.objects.filter(pk__in=suggestion_ids).order_by("-score")