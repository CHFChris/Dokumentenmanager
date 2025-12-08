# app/services/auto_tagging.py
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.category import Category
from app.schemas.category import CategoryKeywordSuggestionOut
from app.utils.crypto_utils import decrypt_text


# Basis-Stopwörter (sollten mit keyword_extraction grob übereinstimmen)
SIMPLE_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",
    "sie", "ihre", "ihr", "ihren", "ihnen",
    "wir", "uns", "man",
    "diese", "dieser", "dieses", "diesem", "diesen",
}


def _tokenize(text: str) -> List[str]:
    """
    Sehr einfache Tokenisierung:
    - lowercasing
    - split auf whitespace
    - Satzzeichen wegschneiden
    - Filter: Länge >= 3, kein Stopwort
    """
    if not text:
        return []

    raw_tokens = text.lower().split()
    tokens: List[str] = []
    for t in raw_tokens:
        t = t.strip(".,;:!?()[]{}\"'`<>|/\\+-=_")
        if not t:
            continue
        if len(t) < 3:
            continue
        if t in SIMPLE_STOPWORDS:
            continue
        tokens.append(t)
    return tokens


def _score_keyword(token: str, count: int) -> float:
    """
    Heuristisches Scoring für Keyword-Vorschläge (Kategorie-intern).
    Domain-agnostisch.
    """
    score = float(count)

    if len(token) >= 10:
        score += 2.0
    elif len(token) >= 7:
        score += 1.0

    if any(ch.isdigit() for ch in token):
        score -= 1.5

    if len(token) <= 3:
        score -= 1.0

    return score


# -------------------------------------------------------------------
# 1) Kategorie aus OCR-Text vorschlagen (Auto-Kategorisierung)
# -------------------------------------------------------------------
def suggest_category_for_document(
    db: Session,
    user_id: int,
    ocr_plaintext: str,
    min_score: int = 1,
) -> Optional[Category]:
    """
    Bestimmt anhand des OCR-Textes eine passende Kategorie für den User.

    Idee:
    - OCR-Text in Tokens zerlegen
    - Kategorie-Keywords ebenfalls tokenisieren
    - Score = Anzahl der Keyword-Tokens, die im Dokument vorkommen
      + leichte Fuzzy-Komponente:
        * 'vertrag' matcht auch 'arbeitsvertrag', 'mietvertrag'
    Domain-agnostisch – funktioniert für Geld, Verträge, Schule, Arzt, etc.
    """
    text = (ocr_plaintext or "")
    if not text.strip():
        print("[AUTO_CAT_DEBUG] OCR-Text ist leer, keine Kategorie möglich.")
        return None

    doc_tokens = _tokenize(text)
    if not doc_tokens:
        print("[AUTO_CAT_DEBUG] Keine verwertbaren Tokens im OCR-Text.")
        return None

    doc_token_set = set(doc_tokens)

    categories: List[Category] = (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .all()
    )

    best_cat: Optional[Category] = None
    best_score: int = 0
    debug_rows: List[tuple[str, int, List[str]]] = []

    for cat in categories:
        if not cat.keywords:
            continue

        raw_keywords = [
            k.strip()
            for k in cat.keywords.split(",")
            if k.strip()
        ]
        if not raw_keywords:
            continue

        # Keywords -> Token-Liste
        kw_tokens: List[str] = []
        for kw in raw_keywords:
            kw_tokens.extend(_tokenize(kw))

        if not kw_tokens:
            continue

        hits: List[str] = []
        score = 0

        for kw_tok in kw_tokens:
            if kw_tok in doc_token_set:
                score += 2
                hits.append(kw_tok)
                continue

            # Fuzzy: Token-Stämme matchen (vertrag -> arbeitsvertrag)
            for dt in doc_token_set:
                if len(kw_tok) >= 5 and dt.startswith(kw_tok):
                    score += 1
                    hits.append(f"{kw_tok}->{dt}")
                    break

        debug_rows.append((cat.name, score, hits))

        if score > best_score:
            best_score = score
            best_cat = cat

    if debug_rows:
        print("[AUTO_CAT_DEBUG] Scores pro Kategorie (Token-basiert + fuzzy):")
        for name, score, hits in debug_rows:
            print(f"  - {name}: score={score}, hits={hits}")
    else:
        print("[AUTO_CAT_DEBUG] Keine Kategorien mit Keywords gefunden.")

    if best_cat is None or best_score < min_score:
        print(
            f"[AUTO_CAT_DEBUG] Keine Kategorie über Schwellwert: "
            f"best_score={best_score}, min_score={min_score}"
        )
        return None

    print(
        f"[AUTO_CAT_DEBUG] Gewählte Kategorie: {best_cat.name} "
        f"(score={best_score}, min_score={min_score})"
    )
    return best_cat


def guess_category_for_text(
    db: Session,
    user_id: int,
    text: str,
    min_score: int = 1,
) -> Optional[int]:
    """
    Rückwärtskompatibilität: liefert nur Kategorie-ID.
    """
    cat = suggest_category_for_document(
        db=db,
        user_id=user_id,
        ocr_plaintext=text,
        min_score=min_score,
    )
    return cat.id if cat else None


# -------------------------------------------------------------------
# 2) Schlagwörter aus OCR-Texten für eine Kategorie vorschlagen
# -------------------------------------------------------------------
def suggest_keywords_for_category(
    db: Session,
    user_id: int,
    category_id: int,
    top_n: int = 15,
) -> CategoryKeywordSuggestionOut:
    """
    Liefert Keyword-Vorschläge für eine Kategorie:
    - verwendet _tokenize + _score_keyword
    - ohne Spezialisierung auf Rechnungen
    """
    category: Optional[Category] = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id,
        )
        .first()
    )
    if not category:
        raise ValueError("Category not found")

    docs: List[Document] = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.category_id == category_id,
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    print(f"[KEYWORDS] Kategorie {category_id}: {len(docs)} Dokument(e) mit OCR-Text gefunden")

    existing_keywords: List[str] = []
    if category.keywords:
        existing_keywords = [
            k.strip()
            for k in category.keywords.split(",")
            if k.strip()
        ]

    existing_lower = {k.lower() for k in existing_keywords}

    counter: Counter[str] = Counter()

    for d in docs:
        enc = d.ocr_text
        if not enc:
            continue

        try:
            plain = decrypt_text(enc)
        except Exception:
            plain = enc

        tokens = _tokenize(plain)
        counter.update(tokens)

    scored_tokens: List[tuple[str, float, int]] = []
    for token, count in counter.items():
        if token.lower() in existing_lower:
            continue
        score = _score_keyword(token, count)
        if score <= 0:
            continue
        scored_tokens.append((token, score, count))

    scored_tokens.sort(key=lambda x: (-x[1], -x[2], x[0]))

    suggested: List[str] = [token for token, _s, _c in scored_tokens[:top_n]]

    print(f"[KEYWORDS] Vorschläge für Kategorie {category_id}: {suggested}")

    return CategoryKeywordSuggestionOut(
        category_id=category.id,
        category_name=category.name,
        existing_keywords=existing_keywords,
        suggested_keywords=suggested,
    )
