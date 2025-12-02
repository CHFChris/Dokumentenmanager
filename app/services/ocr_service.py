# app/services/ocr_service.py
from __future__ import annotations

import os
from typing import List

from PyPDF2 import PdfReader
from PIL import Image
import pytesseract
from docx import Document as DocxDocument


def _clean_text(text: str) -> str:
    if not text:
        return ""
    # ganz einfache Bereinigung
    return text.replace("\r", "\n").strip()


# ------------------------------------------------------------
# PDF
# ------------------------------------------------------------
def extract_text_from_pdf(path: str) -> str:
    try:
        reader = PdfReader(path)
        parts: List[str] = []
        for page in reader.pages:
            try:
                t = page.extract_text() or ""
                if t.strip():
                    parts.append(t)
            except Exception as e:
                print(f"[OCR] Fehler beim Lesen einer PDF-Seite: {e}")
        text = "\n".join(parts)
        print(f"[OCR] PDF-Textlänge: {len(text)}")
        return _clean_text(text)
    except Exception as e:
        print(f"[OCR] PDF konnte nicht gelesen werden: {e}")
        return ""


# ------------------------------------------------------------
# Bilder (PNG / JPG / etc.)
# ------------------------------------------------------------
def extract_text_from_image(path: str, lang: str = "deu+eng") -> str:
    try:
        img = Image.open(path)
        text = pytesseract.image_to_string(img, lang=lang)
        print(f"[OCR] IMAGE-Textlänge: {len(text)}")
        return _clean_text(text)
    except Exception as e:
        print(f"[OCR] Bild-OCR fehlgeschlagen: {e}")
        return ""


# ------------------------------------------------------------
# DOCX
# ------------------------------------------------------------
def extract_text_from_docx(path: str) -> str:
    """
    Liest Text aus einem echten DOCX:
    - normale Absätze
    - Text in Tabellenzellen
    """
    try:
        doc = DocxDocument(path)
    except Exception as e:
        print(f"[OCR] DOCX konnte nicht geöffnet werden: {e}")
        return ""

    parts: List[str] = []

    # 1) Normale Absätze
    for p in doc.paragraphs:
        txt = p.text or ""
        if txt.strip():
            parts.append(txt)

    # 2) Tabellen
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for p in cell.paragraphs:
                    txt = p.text or ""
                    if txt.strip():
                        parts.append(txt)

    text = "\n".join(parts)
    print(f"[OCR] DOCX-Textlänge: {len(text)}")
    return _clean_text(text)


# ------------------------------------------------------------
# zentrale Funktion, die von document_service benutzt wird
# ------------------------------------------------------------
def ocr_and_clean(path: str, lang: str = "deu+eng", dpi: int = 300) -> str:
    """
    Wählt je nach Dateiendung die passende Strategie.
    Wird von run_ocr_and_auto_category() aufgerufen.
    """
    ext = os.path.splitext(path)[1].lower()
    print(f"[OCR] ocr_and_clean() für '{path}' mit Ext '{ext}'")

    text = ""

    if ext == ".pdf":
        text = extract_text_from_pdf(path)
    elif ext in (".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"):
        text = extract_text_from_image(path, lang=lang)
    elif ext == ".docx":
        text = extract_text_from_docx(path)
    else:
        print(f"[OCR] Unbekannter oder nicht unterstützter Typ: {ext}")
        return ""

    text = _clean_text(text)
    print(f"[OCR] ocr_and_clean() liefert Länge {len(text)}")
    return text
