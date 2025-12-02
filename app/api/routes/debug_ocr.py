from fastapi import APIRouter, UploadFile, File, HTTPException
from tempfile import NamedTemporaryFile

from app.services.ocr_service import (
    extract_text_from_pdf,
    extract_text_from_image,
    extract_text_from_docx,
)

router = APIRouter(prefix="/debug-ocr", tags=["debug-ocr"])

@router.post("/test")
async def debug_ocr_test(file: UploadFile = File(...)):
    suffix = ""
    if "." in file.filename:
        suffix = "." + file.filename.rsplit(".", 1)[-1].lower()

    with NamedTemporaryFile(suffix=suffix, delete=True) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp.flush()

        if suffix == ".pdf":
            text = extract_text_from_pdf(tmp.name)
        elif suffix in [".jpg", ".jpeg", ".png"]:
            text = extract_text_from_image(tmp.name)
        elif suffix in [".docx", ".doc"]:
            text = extract_text_from_docx(tmp.name)
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported suffix: {suffix}")

    return {
        "filename": file.filename,
        "suffix": suffix,
        "length": len(text or ""),
        "preview": (text or "")[:500],
    }
