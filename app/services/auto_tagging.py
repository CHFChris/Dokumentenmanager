# app/services/auto_tagging.py
from __future__ import annotations

from app.models.document import Document
from app.services.keyword_extraction import extract_keywords_from_text

from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models.category import Category


def build_category_keywords(db: Session, user_id: int) -> Dict[int, List[str]]:
    """
    Baut eine dynamische Map:
        { category_id: [keyword1, keyword2, ...] }

    Aktuell: nur der Kategoriename selbst als Keyword.
    Später kannst du z.B. noch ein Feld "keywords" in Category ergänzen.
    """
    categories = (
        db.query(Category)
        .filter(Category.user_id == user_id)
        .all()
    )

    mapping: Dict[int, List[str]] = {}

    for cat in categories:
        if not cat.name:
            continue
        name_kw = cat.name.strip().lower()
        if not name_kw:
            continue

        # Basis: der Kategoriename selbst ist ein Keyword
        keywords = [name_kw]

        # Hier könntest du später zusätzliche Keywords aus einem Feld übernehmen
        # z.B. wenn Category ein Feld "extra_keywords" bekäme.

        mapping[cat.id] = keywords

    return mapping


def guess_category_for_text(
    db: Session,
    user_id: int,
    text: str,
) -> Optional[int]:
    """
    Versucht anhand des OCR-Textes eine passende Kategorie zu finden.
    Very simple: prüft, ob der Kategoriename irgendwo im Text vorkommt.
    Gibt die ID der Kategorie mit den meisten Treffern zurück.
    """
    if not text:
        return None

    text_l = text.lower()
    mapping = build_category_keywords(db, user_id)

    best_cat_id: Optional[int] = None
    best_hits = 0

    for cat_id, keywords in mapping.items():
        hits = 0
        for kw in keywords:
            if kw in text_l:
                hits += 1

        if hits > best_hits:
            best_hits = hits
            best_cat_id = cat_id

    if best_hits == 0:
        return None

    return best_cat_id

def _parse_existing_keywords(raw: str | None) -> List[str]:
    """
    Hilfsfunktion: Kommagetrennte Keywords in Liste umwandeln.
    """
    if not raw:
        return []
    parts = [p.strip().lower() for p in raw.split(",")]
    return [p for p in parts if p]


def _serialize_keywords(keywords: List[str]) -> str:
    """
    Liste von Keywords in Komma-String wandeln.
    (Wird genutzt, wenn du später Keywords speicherst.)
    """
    return ", ".join(sorted(set(k.strip().lower() for k in keywords if k.strip())))


def suggest_keywords_for_category(
    db: Session,
    user_id: int,
    category_id: int,
    top_n: int = 15,
) -> dict:
    """
    Liefert Vorschläge für neue Keywords einer Kategorie auf Basis der OCR-Texte.

    Rückgabe-Struktur:
    {
        "category_id": ...,
        "category_name": "...",
        "existing_keywords": [...],
        "suggested_keywords": [...],  # nur die, die noch nicht existieren
    }
    """
    # Kategorie holen (inkl. Besitzerprüfung)
    cat = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.user_id == user_id,
        )
        .first()
    )
    if not cat:
        raise ValueError("Category not found or not owned by user")

    existing = _parse_existing_keywords(cat.keywords)

    # Alle Dokumente dieser Kategorie mit OCR-Text holen
    docs = (
        db.query(Document)
        .filter(
            Document.owner_user_id == user_id,
            Document.category_id == category_id,
            Document.is_deleted == False,  # noqa: E712
            Document.ocr_text.isnot(None),
        )
        .all()
    )

    if not docs:
        return {
            "category_id": cat.id,
            "category_name": cat.name,
            "existing_keywords": existing,
            "suggested_keywords": [],
        }

    # Alle OCR-Texte zusammenfassen
    combined_text = " ".join(d.ocr_text for d in docs if d.ocr_text)

    # Keywords aus OCR-Text extrahieren
    raw_suggestions = extract_keywords_from_text(combined_text, top_n=top_n)

    # Nur Vorschläge, die noch nicht in existing sind
    existing_set = set(existing)
    suggestions = [w for w in raw_suggestions if w not in existing_set]

    return {
        "category_id": cat.id,
        "category_name": cat.name,
        "existing_keywords": existing,
        "suggested_keywords": suggestions,
    }
