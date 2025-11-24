# app/services/auto_tagging.py
from __future__ import annotations

from typing import List, Optional
from collections import Counter

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.document import Document
from app.utils.crypto_utils import decrypt_text
from app.schemas.category import CategoryKeywordSuggestionOut


# ------------------------------------------------------------
# Hilfsfunktionen
# ------------------------------------------------------------
def _normalize(text: str) -> str:
    return (text or "").lower().strip()


def _split_keywords(raw: Optional[str]) -> List[str]:
    """
    Keywords aus DB-Wert extrahieren:
    - falls verschlüsselt: entschlüsseln
    - Kommas/Semikolons trennen
    - saubere Liste zurückgeben
    """
    if not raw:
        return []

    plain = decrypt_text(raw)  # bei Altbestand Klartext -> einfach Rückgabe
    parts = []
    for chunk in plain.replace(";", ",").split(","):
        t = chunk.strip().lower()
        if t:
            parts.append(t)
    return parts


def _score_category_for_text(keywords: List[str], text: str) -> int:
    """
    Sehr einfache Heuristik:
    Score = Anzahl Keywords, die im Text vorkommen.
    """
    if not keywords or not text:
        return 0

    text_norm = _normalize(text)
    return sum(1 for kw in keywords if kw and kw in text_norm)


# ------------------------------------------------------------
# 1) Kategorie automatisch vorschlagen (Upload)
# ------------------------------------------------------------
def suggest_category_for_document(
    db: Session,
    user_id: int,
    ocr_plaintext: str,
    min_score: int = 1,
) -> Optional[Category]:
    """
    Wählt die Kategorie des Users mit dem höchsten Keyword-Match.
    - Kategorien des Users (user_id)
    - Keywords entschlüsselt
    - OCR-Text kommt bereits als Klartext (aus ocr_service)
    """
    categories: List[Category] = (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .all()
    )
    if not categories:
        return None

    best_cat = None
    best_score = 0

    for cat in categories:
        kws = _split_keywords(cat.keywords)
        score = _score_category_for_text(kws, ocr_plaintext)

        if score > best_score:
            best_score = score
            best_cat = cat

    if best_cat is None or best_score < min_score:
        return None

    return best_cat


# ------------------------------------------------------------
# 2) Keyword-Vorschläge für Kategorie
# ------------------------------------------------------------
def suggest_keywords_for_category(
    db: Session,
    user_id: int,
    category_id: int,
    top_n: int = 15,
) -> CategoryKeywordSuggestionOut:
    """
    Schlägt Keywords für eine Kategorie vor:
    - Nur Kategorie des Users
    - Nur Dokumente des Users
    - OCR-Texte entschlüsselt
    - Häufigste Wörter als neue Keywords
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
        raise ValueError("Category not found or forbidden")

    existing_kws = set(_split_keywords(category.keywords))

    # Dokumente dieser Kategorie
    docs: List[Document] = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.category_id == category.id,
            Document.is_deleted.is_(False),
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    counter: Counter[str] = Counter()

    for doc in docs:
        if not doc.ocr_text:
            continue

        text = decrypt_text(doc.ocr_text)
        text = _normalize(text)
        if not text:
            continue

        tokens = [
            t.strip(".,;:!?()[]{}\"'")
            for t in text.split()
            if len(t) >= 3
        ]
        counter.update(tokens)

    suggestions = []
    for word, _freq in counter.most_common():
        if word in existing_kws:
            continue
        suggestions.append(word)
        if len(suggestions) >= top_n:
            break

    return CategoryKeywordSuggestionOut(
        category_id=category.id,
        suggestions=suggestions,
    )
