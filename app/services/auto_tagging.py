# app/services/auto_tagging.py
from __future__ import annotations

from collections import Counter
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.category import Category
from app.schemas.category import CategoryKeywordSuggestionOut
from app.utils.crypto_utils import decrypt_text


# sehr einfache Stopwort-Liste (de + en)
SIMPLE_STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",
}


def _tokenize(text: str) -> List[str]:
    """
    Sehr einfache Tokenisierung:
    - lowercasing
    - split auf whitespace
    - Filter: Länge >= 3, kein reines Sonderzeichen, keine Stopwörter
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


# -------------------------------------------------------------------
# 1) Kategorie aus OCR-Text vorschlagen (für Auto-Kategorisierung)
# -------------------------------------------------------------------
def suggest_category_for_document(
    db: Session,
    user_id: int,
    ocr_plaintext: str,
    min_score: int = 1,
) -> Optional[Category]:
    """
    Bestimmt anhand des OCR-Textes eine passende Kategorie für den User.
    - Nutzt die definierten Keywords der Kategorien (category.keywords)
    - very simple Scoring: jedes Keyword-Vorkommen erhöht den Score
    - gibt die Kategorie mit höchstem Score zurück, wenn Score >= min_score
    """
    text = (ocr_plaintext or "").lower()
    if not text.strip():
        return None

    categories: List[Category] = (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .all()
    )

    best_cat: Optional[Category] = None
    best_score: int = 0

    for cat in categories:
        if not cat.keywords:
            continue

        keywords = [k.strip().lower() for k in cat.keywords.split(",") if k.strip()]
        if not keywords:
            continue

        score = 0
        for kw in keywords:
            if kw and kw in text:
                score += 1

        if score > best_score:
            best_score = score
            best_cat = cat

    if best_cat is None or best_score < min_score:
        return None

    return best_cat


# Rückwärtskompatibilität, falls irgendwo noch verwendet:
def guess_category_for_text(
    db: Session,
    user_id: int,
    text: str,
    min_score: int = 1,
) -> Optional[int]:
    """
    Alte Helper-Funktion, liefert nur die Kategorie-ID.
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
    Liefert Schlagwort-Vorschläge für eine Kategorie basierend auf allen
    OCR-Texten der Dokumente dieses Users in dieser Kategorie.

    WICHTIG:
    - ocr_text ist in der DB verschlüsselt gespeichert -> hier wieder entschlüsseln
    - Tokens werden gezählt und nach Häufigkeit sortiert
    - bereits vorhandene Category-Keywords werden nicht nochmal vorgeschlagen
    """

    # 1) Kategorie sicherstellen (user-scope)
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

    # 2) Dokumente der Kategorie + OCR-Text holen
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

    # 3) Existierende Keywords der Kategorie (vom User eingetragen)
    existing_keywords: List[str] = []
    if category.keywords:
        existing_keywords = [
            k.strip()
            for k in category.keywords.split(",")
            if k.strip()
        ]

    existing_lower = {k.lower() for k in existing_keywords}

    # 4) OCR-Texte entschlüsseln und tokenisieren
    counter: Counter[str] = Counter()

    for d in docs:
        enc = d.ocr_text
        if not enc:
            continue

        # Verschlüsselten OCR-Text entschlüsseln
        try:
            plain = decrypt_text(enc)
        except Exception:
            # Fallback: falls doch Klartext gespeichert ist
            plain = enc

        tokens = _tokenize(plain)
        counter.update(tokens)

    # 5) Tokens nach Häufigkeit sortieren und vorhandene Keywords rausfiltern
    suggested: List[str] = []
    for token, _count in counter.most_common():
        if token.lower() in existing_lower:
            continue
        suggested.append(token)
        if len(suggested) >= top_n:
            break

    print(f"[KEYWORDS] Vorschläge für Kategorie {category_id}: {suggested}")

    # 6) Objekt für API zurückgeben (CategoryKeywordSuggestionOut)
    return CategoryKeywordSuggestionOut(
        category_id=category.id,
        category_name=category.name,
        existing_keywords=existing_keywords,
        suggested_keywords=suggested,
    )
