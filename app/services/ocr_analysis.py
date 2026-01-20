# app/services/ocr_analysis.py
from __future__ import annotations

import os
from typing import Optional, List

from PIL import Image
import pytesseract
from pdf2image import convert_from_path

# Optional: Pfad zu Tesseract über Umgebungsvariable setzen (Windows/Linux).
# Beispiel (Windows): TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
_tess_cmd = os.getenv("TESSERACT_CMD", "").strip()
if _tess_cmd and os.path.exists(_tess_cmd):
    pytesseract.pytesseract.tesseract_cmd = _tess_cmd


def _ocr_image(image: Image.Image, lang: str = "deu+eng") -> str:
    """
    Führt OCR auf einem bereits geladenen PIL-Image aus.
    """
    return pytesseract.image_to_string(image, lang=lang)


def run_ocr_on_file(
    path: str,
    lang: str = "deu+eng",
    dpi: int = 300,
    max_pages: Optional[int] = None,
    poppler_path: Optional[str] = None,
) -> str:
    """
    Führt OCR auf einer Datei aus.
    - Bilder: werden direkt geladen.
    - PDF: wird mit pdf2image in Seiten-Bilder umgewandelt.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")

    ext = os.path.splitext(path)[1].lower()
    image_exts = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}

    # Bildformate
    if ext in image_exts:
        image = Image.open(path)
        return _ocr_image(image, lang=lang)

    # PDF
    if ext == ".pdf":
        pages = convert_from_path(path, dpi=dpi, poppler_path=poppler_path)
        texts: List[str] = []
        for i, page in enumerate(pages):
            if max_pages is not None and i >= max_pages:
                break
            texts.append(_ocr_image(page, lang=lang))
        return "\n".join(texts)

    raise ValueError(f"Nicht unterstützte Dateiendung: {ext}")


def clean_text(text: str) -> str:
    """
    Entfernt überflüssige Zeilenumbrüche und doppelte Leerzeichen.
    """
    text = text.replace("\n", " ")
    while "  " in text:
        text = text.replace("  ", " ")
    return text.strip()


def ocr_and_clean(
    path: str,
    lang: str = "deu+eng",
    dpi: int = 300,
    max_pages: Optional[int] = None,
    poppler_path: Optional[str] = None,
) -> str:
    """
    High-Level-Funktion:
    - führt OCR auf einem Bild oder PDF aus
    - bereinigt den Text
    """
    raw = run_ocr_on_file(
        path=path,
        lang=lang,
        dpi=dpi,
        max_pages=max_pages,
        poppler_path=poppler_path,
    )
    return clean_text(raw)
