from sqlalchemy.orm import Session

from app.models.models import (
    User,
    SocialAccount,
    SocialContent,
    AnalysisResult,
    Incident,
    Alert,
)

from app.services.ai_engine import analyze_content
from app.services.audit import audit


async def build_social_analysis_text(
    content: SocialContent,
) -> tuple[str, bool]:
    """
    Build backend analysis text from the Mastodon status
    and image descriptions.

    Actual image OCR is performed in the browser with
    Tesseract.js, so no external AI/OCR API is required.
    """

    parts: list[str] = []

    status_text = (
        content.content or ""
    ).strip()

    if status_text:
        parts.append(
            status_text
        )

    metadata = (
        content.metadata_json or {}
    )

    media = metadata.get(
        "media",
        [],
    )

    if not isinstance(
        media,
        list,
    ):
        media = []

    for attachment in media[:4]:
        if not isinstance(
            attachment,
            dict,
        ):
            continue

        media_type = str(
            attachment.get(
                "type",
                "",
            )
        ).lower().strip()

        if media_type != "image":
            continue

        description = (
            attachment.get(
                "description"
            )
            or ""
        ).strip()

        if description:
            parts.append(
                "[Mastodon image description]\n"
                + description
            )

    combined = "\n\n".join(
        part
        for part in parts
        if part.strip()
    ).strip()

    return (
        combined,
        False,
    )


def _create_incident_if_needed(
    db: Session,
    owner: User,
    ai: AnalysisResult,
    result: dict,
) -> bool:
    """
    Create an incident and alert when risk is high/critical.
    """

    if result["risk_score"] < 61:
        return False

    incident = Incident(
        user_id=owner.id,
        analysis_id=ai.id,
        title=(
            f"{result['severity']} "
            "leak detection"
        ),
    )

    db.add(incident)
    db.flush()

    db.add(
        Alert(
            user_id=owner.id,
            incident_id=incident.id,
            severity=result["severity"],
            message=(
                "LeakGuard detected a "
                f"{result['severity']} "
                "risk finding from Mastodon."
            ),
        )
    )

    return True


async def analyze_unprocessed_content(
    db: Session,
    user: User | None = None,
):
    """
    Analyze unprocessed Mastodon text posts.

    Image posts are intentionally left unprocessed here.
    They are sent to the browser OCR workflow instead.
    """

    query = (
        db.query(
            SocialContent,
            SocialAccount,
            User,
        )
        .join(
            SocialAccount,
            SocialAccount.id
            == SocialContent.account_id,
        )
        .join(
            User,
            User.id
            == SocialAccount.user_id,
        )
    )

    if user:
        query = query.filter(
            User.id == user.id
        )

    rows = (
        query
        .order_by(
            SocialContent.remote_created_at.desc()
        )
        .limit(100)
        .all()
    )

    analyzed = 0
    incidents = 0
    results = []

    for content, account, owner in rows:

        metadata = (
            content.metadata_json or {}
        )

        media = metadata.get(
            "media",
            [],
        )

        if not isinstance(
            media,
            list,
        ):
            media = []

        has_image = any(
            isinstance(
                item,
                dict,
            )
            and str(
                item.get(
                    "type",
                    "",
                )
            ).lower().strip()
            == "image"
            and (
                item.get("url")
                or item.get(
                    "preview_url"
                )
            )
            for item in media
        )

        has_text = bool(
            (content.content or "").strip()
        )

        if (
            not has_text
            and not has_image
        ):
            continue

        # -----------------------------------------------------
        # IMPORTANT:
        # Image posts must wait for browser OCR.
        # -----------------------------------------------------
        if has_image:
            continue

        existing = (
            db.query(
                AnalysisResult
            )
            .filter_by(
                content_id=content.id
            )
            .first()
        )

        if existing:
            continue

        analysis_text = (
            content.content or ""
        ).strip()

        if not analysis_text:
            continue

        result = analyze_content(
            analysis_text
        )

        ai = AnalysisResult(
            input_text=analysis_text,
            content_id=content.id,
            user_id=owner.id,
            **result,
        )

        db.add(ai)
        db.flush()

        if _create_incident_if_needed(
            db,
            owner,
            ai,
            result,
        ):
            incidents += 1

        audit(
            db,
            owner.id,
            "SOCIAL_CONTENT_ANALYZED",
            "analysis",
            ai.id,
            metadata={
                "platform": content.platform,
                "content_id": content.content_id,
                "image_ocr": False,
                "media_count": len(media),
                "has_image": False,
            },
        )

        results.append(
            (
                ai,
                result,
            )
        )

        analyzed += 1

    db.commit()

    return (
        analyzed,
        incidents,
        results,
    )


async def persist_social_ocr_analysis(
    db: Session,
    user: User,
    content: SocialContent,
    ocr_text: str,
):
    """
    Save browser-extracted OCR text and run the existing
    LeakGuard deterministic detector.

    No external AI API is used.
    """

    existing = (
        db.query(
            AnalysisResult
        )
        .filter_by(
            content_id=content.id
        )
        .first()
    )

    if existing:
        return (
            existing,
            None,
            False,
        )

    parts: list[str] = []

    status_text = (
        content.content or ""
    ).strip()

    if status_text:
        parts.append(
            status_text
        )

    metadata = (
        content.metadata_json or {}
    )

    media = metadata.get(
        "media",
        [],
    )

    if not isinstance(
        media,
        list,
    ):
        media = []

    # Add Mastodon image descriptions.
    for attachment in media[:4]:

        if not isinstance(
            attachment,
            dict,
        ):
            continue

        if (
            str(
                attachment.get(
                    "type",
                    "",
                )
            ).lower().strip()
            != "image"
        ):
            continue

        description = (
            attachment.get(
                "description"
            )
            or ""
        ).strip()

        if description:
            parts.append(
                "[Mastodon image description]\n"
                + description
            )

    # Add browser OCR.
    ocr_text = (
        ocr_text or ""
    ).strip()

    if ocr_text:
        parts.append(
            "[Text extracted from Mastodon image]\n"
            + ocr_text
        )

    analysis_text = "\n\n".join(
        part
        for part in parts
        if part.strip()
    ).strip()

    # Even an image with no readable text gets recorded.
    if not analysis_text:
        analysis_text = (
            "[Image analyzed: no readable text detected]"
        )

    result = analyze_content(
        analysis_text
    )

    ai = AnalysisResult(
        input_text=analysis_text,
        content_id=content.id,
        user_id=user.id,
        **result,
    )

    db.add(ai)
    db.flush()

    incident_created = _create_incident_if_needed(
        db,
        user,
        ai,
        result,
    )

    audit(
        db,
        user.id,
        "SOCIAL_IMAGE_ANALYZED",
        "analysis",
        ai.id,
        metadata={
            "platform": content.platform,
            "content_id": content.content_id,
            "image_ocr": True,
            "ocr_characters": len(ocr_text),
            "media_count": len(media),
        },
    )

    db.commit()

    return (
        ai,
        result,
        incident_created,
    )


async def persist_manual_analysis(
    db: Session,
    user: User,
    text: str,
    result: dict,
):
    """
    Save a manual text analysis.
    """

    ai = AnalysisResult(
        input_text=text,
        user_id=user.id,
        **result,
    )

    db.add(ai)
    db.flush()

    _create_incident_if_needed(
        db,
        user,
        ai,
        result,
    )

    audit(
        db,
        user.id,
        "SCAN_EXECUTED",
        "analysis",
        ai.id,
    )

    db.commit()

    return ai