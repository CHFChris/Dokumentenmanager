# app/services/keyword_extraction.py
from __future__ import annotations

from collections import Counter
from typing import List

# gemeinsame Stopwort-Liste (de + en + typischer Vorlagen-/Hilfetext)
STOPWORDS = {
    # Funktionswörter / Artikel / Pronomen
    "der", "die", "das", "und", "oder", "ein", "eine", "einer", "einem", "einen",
    "den", "im", "in", "ist", "sind", "war", "waren", "von", "mit", "auf", "für",
    "an", "am", "als", "zu", "zum", "zur", "bei", "aus", "dem",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "at", "by",
    "this", "that", "these", "those", "it", "its", "be", "was", "were", "are",

    "sie", "ihre", "ihr", "ihren", "ihnen",
    "wir", "uns", "man",
    "diese", "dieser", "dieses", "diesem", "diesen",

    # typische Vorlagen-/Hilfetexte (kein inhaltlicher Mehrwert)
    "beschreibung",
    "entfernen",
    "fußzeile", "fusszeile",
    "beratung",
    "können", "koennen",
    "dürfen", "duerfen",
    "vorlage", "vorlagen",
    "anpassen",
    "seite", "seiten",
    "kopf",
    "bearbeiten",
    "muster", "beispiel", "etc", "zb", "z.b.",
    "bitte", "hier", "oben", "unten",
}


def _tokenize(text: str) -> List[str]:
    """
    Simple Tokenisierung:
    - lowercasing
    - Split auf Whitespace
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


def _score_keyword(token: str, count: int) -> float:
    """
    Heuristische Bewertung eines Tokens:
    - Basis: Häufigkeit im Text
    - + Bonus für längere Wörter
    - - Malus, wenn viele Ziffern enthalten sind (konkrete Beträge, Nummern)
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


def extract_keywords_from_text(text: str, top_n: int = 20) -> List[str]:
    """
    Nimmt den gesamten OCR-Text und liefert sinnvolle Schlüsselwörter zurück.
    - generisch, nicht auf Rechnungen oder bestimmte Kategorien beschränkt
    - basiert auf Häufigkeit + heuristischem Score
    """
    tokens = _tokenize(text)
    if not tokens:
        return []

    counter = Counter(tokens)

    scored: list[tuple[str, float, int]] = []
    for token, cnt in counter.items():
        score = _score_keyword(token, cnt)
        if score <= 0:
            continue
        scored.append((token, score, cnt))

    # sortiert nach:
    #   1. Score (absteigend)
    #   2. Rohhäufigkeit (absteigend)
    #   3. alphabetisch (stabil)
    scored.sort(key=lambda x: (-x[1], -x[2], x[0]))

    return [token for token, _score, _cnt in scored[:top_n]]
