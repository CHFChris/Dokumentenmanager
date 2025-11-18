import pytesseract
from PIL import Image
import fitz  # PyMuPDF

def extract_text_from_pdf(path: str) -> str:
    text = ""
    with fitz.open(path) as pdf:
        for page in pdf:
            text += page.get_text()
    return text.strip()

def extract_text_from_image(path: str) -> str:
    img = Image.open(path)
    return pytesseract.image_to_string(img)
