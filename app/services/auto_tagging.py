# app/services/auto_tagging.py
from __future__ import annotations

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.document import Document
from app.schemas.category import CategoryKeywordSuggestionOut
from app.services.keyword_extraction import extract_keywords_from_text


# Sehr einfache Stopwortliste – kann mit deiner aus document_service abgestimmt werden
STOPWORDS = {
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",
}


def _tokenize_simple(text: str) -> List[str]:
    """
    Sehr einfache Tokenizer-Funktion:
    - lowercasing
    - Split auf Whitespace
    - Entfernt Satzzeichen
    - Filtert Stopwörter und sehr kurze Tokens
    """
    if not text:
        return []
    tokens: List[str] = []
    for raw in text.lower().split():
        t = raw.strip(".,;:!?()[]{}\"'`<>|/\\+-=_")
        if not t:
            continue
        if len(t) < 3:
            continue
        if t in STOPWORDS:
            continue
        tokens.append(t)
    return tokens


def _parse_existing_keywords(raw: Optional[str]) -> List[str]:
    """
    Zerlegt das gespeicherte Komma-Feld in eine saubere, kleingeschriebene Liste.
    """
    if not raw:
        return []
    return [k.strip().lower() for k in raw.split(",") if k.strip()]


def _score_category(category_keywords: List[str], doc_tokens: List[str]) -> int:
    """
    Einfacher Score:
    - Anzahl der Überschneidungen Kategorie-Keywords vs. Dokument-Tokens.
    """
    if not category_keywords or not doc_tokens:
        return 0

    kw_set = {k.lower() for k in category_keywords if k}
    token_set = set(doc_tokens)
    return len(kw_set & token_set)


# ---------------------------------------------------------------------------
# 1) Kategorie per Keywords automatisch raten (für Upload ohne Kategorie)
# ---------------------------------------------------------------------------
def guess_category_for_text(
    db: Session,
    user_id: int,
    text: str,
) -> Optional[int]:
    """
    Versucht, anhand des OCR-/Textinhalts eine passende Kategorie zu finden.

    Logik:
    - Text wird tokenisiert (Stopwörter entfernt).
    - Für jede Kategorie des Users:
        * Keywords aus categories.keywords holen
        * Score = Schnittmenge(Keyword-Set, Text-Tokens)
    - Es wird die Kategorie mit dem höchsten Score gewählt,
      aber nur, wenn eine Mindest-Schwelle erreicht ist.
    """

    # Mindest-Schwelle: mindestens 2 Keyword-Treffer,
    # damit nicht "irgendwas" zufällig zugeordnet wird.
    MIN_SCORE = 1

    doc_tokens = _tokenize_simple(text)
    if not doc_tokens:
        return None

    categories = (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .all()
    )

    best_cat_id: Optional[int] = None
    best_score = 0

    for cat in categories:
        if not cat.keywords:
            continue

        cat_keywords = _parse_existing_keywords(cat.keywords)
        if not cat_keywords:
            continue

        score = _score_category(cat_keywords, doc_tokens)

        if score > best_score:
            best_score = score
            best_cat_id = cat.id

    if best_score >= MIN_SCORE:
        return best_cat_id

    return None


# ---------------------------------------------------------------------------
# 2) Keyword-Vorschläge für eine Kategorie (Frontend /categories/{id})
# ---------------------------------------------------------------------------
def suggest_keywords_for_category(
    db: Session,
    user_id: int,
    category_id: int,
    top_n: int = 15,
) -> CategoryKeywordSuggestionOut:
    """
    Nimmt alle Dokumente dieser Kategorie (mit OCR-Text),
    baut einen großen Text und extrahiert daraus die häufigsten Wörter.

    - vorhandene Keywords werden entfernt
    - Duplikate werden entfernt
    - Reihenfolge nach Häufigkeit (über extract_keywords_from_text)
    """
    # 1) Kategorie holen und Ownership prüfen
    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id,
        )
        .first()
    )
    if not category:
        raise ValueError("CATEGORY_NOT_FOUND")

    existing_keywords = _parse_existing_keywords(category.keywords)

    # 2) Alle Dokumente der Kategorie mit OCR-Text laden
    docs = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.category_id == category_id,
            Document.is_deleted == False,          # noqa: E712
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    combined_text_parts: List[str] = [
        d.ocr_text for d in docs if d.ocr_text
    ]
    combined_text = "\n".join(combined_text_parts)

    if not combined_text.strip():
        # Kein OCR-Text vorhanden -> leere Vorschläge
        return CategoryKeywordSuggestionOut(
            category_id=category.id,
            category_name=category.name,
            existing_keywords=existing_keywords,
            suggested_keywords=[],
        )

    # 3) Keywords aus dem kombinierten Text extrahieren
    candidates = extract_keywords_from_text(
        combined_text,
        top_n=top_n * 3,   # etwas „zu viele“ holen, wir filtern gleich noch
    )

    existing_set = set(existing_keywords)
    seen: set[str] = set()
    suggestions: List[str] = []

    for kw in candidates:
        k = kw.strip().lower()
        if not k:
            continue
        if k in existing_set:
            continue
        if k in seen:
            continue

        seen.add(k)
        suggestions.append(k)
        if len(suggestions) >= top_n:
            break

    return CategoryKeywordSuggestionOut(
        category_id=category.id,
        category_name=category.name,
        existing_keywords=existing_keywords,
        suggested_keywords=suggestions,
    )
