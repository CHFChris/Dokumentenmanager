import pytesseract
from PIL import Image
import fitz  # PyMuPDF
from docx import Document


def extract_text_from_pdf(path: str) -> str:
    """
    Extrahiert Text aus PDFs über PyMuPDF.
    """
    text = ""
    with fitz.open(path) as pdf:
        for page in pdf:
            text += page.get_text()
    return text.strip()


def extract_text_from_image(path: str) -> str:
    """
    OCR auf Bilddateien (JPG/PNG) mit Tesseract.
    """
    img = Image.open(path)
    return pytesseract.image_to_string(img)


def extract_text_from_docx(path: str) -> str:
    """
    Liest den sichtbaren Text aus einer DOCX-Datei.
    Kein OCR – echtes strukturiertes Auslesen.
    """
    try:
        doc = Document(path)  # korrektes DOCX-Lesen
    except Exception:
        return ""

    parts: list[str] = []

    # Normale Absätze
    for p in doc.paragraphs:
        text = (p.text or "").strip()
        if text:
            parts.append(text)

    # Tabellenzellen (falls Dokument Tabellen enthält)
    for table in doc.tables:
        for row in table.rows:
            cells = [(cell.text or "").strip() for cell in row.cells]
            line = " | ".join(c for c in cells if c)
            if line:
                parts.append(line)

    return "\n".join(parts)
