from io import BytesIO
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import AnalyzeIn, AnalysisOut
from app.services.ai_engine import analyze_content
from app.services.openai_service import explain_with_openai
from app.services.analysis import persist_manual_analysis
from app.services.audit import audit
from app.core.config import settings

router = APIRouter(prefix="/scan", tags=["scan"])

@router.post("", response_model=AnalysisOut)
async def scan(data: AnalyzeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    result = analyze_content(data.content)
    enhanced = await explain_with_openai(result)
    if enhanced:
        result["explanation"] = enhanced
    ai = await persist_manual_analysis(db, user, data.content, result)
    return AnalysisOut(id=ai.id, **result)

@router.post("/image", response_model=AnalysisOut)
async def scan_image(file: UploadFile = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    allowed = {"image/png", "image/jpeg", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(415, "Only PNG, JPEG and WebP images are supported")
    data = await file.read()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, "Image exceeds configured upload limit")
    try:
        from PIL import Image
        image = Image.open(BytesIO(data))
        image.verify()
        image = Image.open(BytesIO(data))
    except Exception as exc:
        raise HTTPException(400, "Invalid or corrupted image") from exc

    try:
        import pytesseract
        text = pytesseract.image_to_string(image)
    except ImportError as exc:
        raise HTTPException(503, "OCR is not installed. Install the backend OCR dependencies.") from exc
    except pytesseract.pytesseract.TesseractNotFoundError as exc:
        raise HTTPException(503, "Tesseract OCR is not installed or is not on PATH.") from exc

    text = text.strip()
    if not text:
        raise HTTPException(422, "No readable text was found in the image")

    result = analyze_content(text)
    enhanced = await explain_with_openai(result)
    if enhanced:
        result["explanation"] = enhanced
    ai = await persist_manual_analysis(db, user, text, result)
    audit(db, user.id, "IMAGE_SCAN_EXECUTED", "analysis", ai.id,
          metadata={"filename": file.filename or "upload", "ocr": True})
    db.commit()
    return AnalysisOut(id=ai.id, **result)
