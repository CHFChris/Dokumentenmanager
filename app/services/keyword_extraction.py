# app/services/keyword_extraction.py
from __future__ import annotations

from collections import Counter
from typing import List, Iterable

# sehr einfache Stopwortliste, gern erweitern
STOPWORDS = {
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
    - rudimentäre Bereinigung von Satzzeichen
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
        if t in STOPWORDS:
            continue
        tokens.append(t)
    return tokens


def extract_keywords_from_text(text: str, top_n: int = 20) -> List[str]:
    """
    Nimmt den gesamten OCR-Text und liefert die häufigsten Wörter zurück.
    KEINE Mindestanzahl an Vorkommen -> auch bei wenigen Dokumenten kommen Vorschläge.
    """
    tokens = _tokenize(text)
    if not tokens:
        return []

    counter = Counter(tokens)
    # einfach die häufigsten N Wörter
    most_common = counter.most_common(top_n)
    keywords = [word for word, count in most_common]
    return keywords
