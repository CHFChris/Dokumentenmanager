# app/services/keyword_extraction.py
from __future__ import annotations

import re
from collections import Counter
from typing import List

# sehr einfache Stopwort-Liste (deutsch + englisch, beliebig erweiterbar)
STOPWORDS = {
    "und", "oder", "aber", "dass", "die", "der", "das", "ein", "eine", "ist",
    "im", "in", "am", "an", "auf", "mit", "für", "zu", "von", "den", "dem",
    "nicht", "sie", "er", "wir", "ihr", "als", "auch", "bei", "aus",

    "the", "and", "or", "but", "that", "this", "a", "an", "of", "to", "in",
    "on", "at", "for", "by", "from", "it", "is", "are", "was", "were",
}


def normalize_text(text: str) -> List[str]:
    """
    Macht alles klein, entfernt Sonderzeichen, splittet in Wörter.
    Gibt nur sinnvolle Wörter zurück (Laenge >= 4, nicht nur Ziffern).
    """
    text = text.lower()
    # nur Buchstaben, Zahlen und Leerzeichen erlauben
    text = re.sub(r"[^a-z0-9äöüß ]+", " ", text)
    tokens = text.split()

    cleaned = []
    for tok in tokens:
        if len(tok) < 4:
            continue
        if tok in STOPWORDS:
            continue
        if tok.isdigit():
            continue
        cleaned.append(tok)

    return cleaned


def extract_keywords_from_text(text: str, top_n: int = 15) -> List[str]:
    """
    Sehr einfacher Keyword-Extractor:
    - normalisiert Text
    - zählt Worthäufigkeiten
    - gibt die häufigsten Wörter zurück
    """
    tokens = normalize_text(text)
    if not tokens:
        return []

    counter = Counter(tokens)
    most_common = counter.most_common(top_n)
    return [word for word, _count in most_common]
