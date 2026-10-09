from io import BytesIO

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
)
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import settings
from app.db.session import get_db
from app.models.models import User
from app.schemas.schemas import (
    AnalyzeIn,
    AnalysisOut,
)
from app.services.ai_engine import analyze_content
from app.services.analysis import (
    persist_manual_analysis,
)
from app.services.audit import audit


router = APIRouter(
    prefix="/scan",
    tags=["scan"],
)


@router.post(
    "",
    response_model=AnalysisOut,
)
async def scan(
    data: AnalyzeIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Local LeakGuard text analysis.

    No external AI API is required.
    """

    result = analyze_content(
        data.content
    )

    ai = await persist_manual_analysis(
        db,
        user,
        data.content,
        result,
    )

    return AnalysisOut(
        id=ai.id,
        **result,
    )


@router.post(
    "/image",
    response_model=AnalysisOut,
)
async def scan_image(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Compatibility endpoint for direct image uploads.

    The frontend normally uses Tesseract.js in the browser,
    so no external OCR API is required.
    """

    allowed = {
        "image/png",
        "image/jpeg",
        "image/webp",
    }

    if file.content_type not in allowed:
        raise HTTPException(
            415,
            "Only PNG, JPEG and WebP images are supported",
        )

    data = await file.read()

    if len(data) > (
        settings.max_upload_mb
        * 1024
        * 1024
    ):
        raise HTTPException(
            413,
            "Image exceeds configured upload limit",
        )

    try:

        from PIL import Image

        image = Image.open(
            BytesIO(data)
        )

        image.verify()

        image = Image.open(
            BytesIO(data)
        )

    except Exception as exc:

        raise HTTPException(
            400,
            "Invalid or corrupted image",
        ) from exc

    # Server-side Tesseract is kept only for compatibility.
    # The main frontend image scanner uses Tesseract.js.
    try:

        import pytesseract

        text = (
            pytesseract
            .image_to_string(
                image
            )
            .strip()
        )

    except ImportError as exc:

        raise HTTPException(
            503,
            "Browser Image OCR is the recommended image scanner.",
        ) from exc

    except pytesseract.pytesseract.TesseractNotFoundError as exc:

        raise HTTPException(
            503,
            "Server Tesseract is not installed. Use the browser Image OCR scanner.",
        ) from exc

    if not text:

        raise HTTPException(
            422,
            "No readable text was found in the image",
        )

    result = analyze_content(
        text
    )

    ai = await persist_manual_analysis(
        db,
        user,
        text,
        result,
    )

    audit(
        db,
        user.id,
        "IMAGE_SCAN_EXECUTED",
        "analysis",
        ai.id,
        metadata={
            "filename": (
                file.filename
                or "upload"
            ),
            "ocr": True,
        },
    )

    db.commit()

    return AnalysisOut(
        id=ai.id,
        **result,
    )