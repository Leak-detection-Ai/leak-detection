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
from app.services.openrouter_service import explain_analysis
from app.services.vision_ocr import (
    extract_text_from_image_url,
)
from app.services.audit import audit


async def build_social_analysis_text(
    content: SocialContent,
) -> tuple[str, bool]:
    """
    Build analysis input from:
    - Mastodon status text
    - Mastodon image descriptions
    - OCR text extracted from Mastodon images

    Returns:
        combined analysis text,
        whether at least one image produced OCR text
    """

    parts: list[str] = []

    # ---------------------------------------------------------
    # 1. Mastodon status text
    # ---------------------------------------------------------
    status_text = (
        content.content or ""
    ).strip()

    if status_text:
        parts.append(
            status_text
        )

    # ---------------------------------------------------------
    # 2. Media metadata
    # ---------------------------------------------------------
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

    image_analyzed = False

    # ---------------------------------------------------------
    # 3. Process image attachments
    # ---------------------------------------------------------
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

        # Prefer original image URL.
        # Fall back to preview URL if original is absent.
        image_url = (
            attachment.get("url")
            or attachment.get(
                "preview_url"
            )
            or ""
        )

        description = (
            attachment.get(
                "description"
            )
            or ""
        ).strip()

        # -----------------------------------------------------
        # 3A. Mastodon alt text
        # -----------------------------------------------------
        if description:
            parts.append(
                "[Mastodon image description]\n"
                + description
            )

        # -----------------------------------------------------
        # 3B. Actual image OCR
        # -----------------------------------------------------
        if image_url:
            logger_text = (
                image_url[:250]
            )

            print(
                f"LeakGuard: analyzing Mastodon image "
                f"{logger_text}"
            )

            extracted = (
                await extract_text_from_image_url(
                    image_url
                )
            )

            if extracted:
                image_analyzed = True

                parts.append(
                    "[Text extracted from Mastodon image]\n"
                    + extracted
                )

    # ---------------------------------------------------------
    # 4. Final analysis text
    # ---------------------------------------------------------
    combined = "\n\n".join(
        part
        for part in parts
        if isinstance(
            part,
            str,
        )
        and part.strip()
    ).strip()

    return (
        combined,
        image_analyzed,
    )


async def analyze_unprocessed_content(
    db: Session,
    user: User | None = None,
):
    """
    Analyze unprocessed Mastodon content.

    Important:
    Image-only posts MUST NOT be skipped.
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

        # -----------------------------------------------------
        # 1. Read media metadata
        # -----------------------------------------------------
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

        # -----------------------------------------------------
        # 2. Determine whether the post contains an image
        # -----------------------------------------------------
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

        has_status_text = bool(
            (content.content or "").strip()
        )

        # -----------------------------------------------------
        # 3. Skip ONLY completely empty records
        # -----------------------------------------------------
        if (
            not has_status_text
            and not has_image
        ):
            continue

        # -----------------------------------------------------
        # 4. Don't analyze same record twice
        # -----------------------------------------------------
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

        # -----------------------------------------------------
        # 5. Build text from BOTH text + image OCR
        # -----------------------------------------------------
        (
            analysis_text,
            image_analyzed,
        ) = await build_social_analysis_text(
            content
        )

        # -----------------------------------------------------
        # 6. If OCR/text produced nothing, don't create
        #    an empty AI result
        # -----------------------------------------------------
        if not analysis_text.strip():
            continue

        # -----------------------------------------------------
        # 7. Deterministic leak detector
        # -----------------------------------------------------
        result = analyze_content(
            analysis_text
        )

        # -----------------------------------------------------
        # 8. OpenRouter explanation
        # -----------------------------------------------------
        enhanced = await explain_analysis(
            result
        )

        if enhanced:
            result["explanation"] = enhanced

        # -----------------------------------------------------
        # 9. Store analysis
        # -----------------------------------------------------
        ai = AnalysisResult(
            input_text=analysis_text,
            content_id=content.id,
            user_id=owner.id,
            **result,
        )

        db.add(ai)
        db.flush()

        # -----------------------------------------------------
        # 10. Create incident + alert for high risk
        # -----------------------------------------------------
        if result["risk_score"] >= 61:

            incident = Incident(
                user_id=owner.id,
                analysis_id=ai.id,
                title=(
                    f"{result['severity']} "
                    "leak detection"
                ),
            )

            db.add(
                incident
            )

            db.flush()

            db.add(
                Alert(
                    user_id=owner.id,
                    incident_id=incident.id,
                    severity=result[
                        "severity"
                    ],
                    message=(
                        "LeakGuard detected a "
                        f"{result['severity']} "
                        "risk finding from Mastodon."
                    ),
                )
            )

            incidents += 1

        # -----------------------------------------------------
        # 11. Audit
        # -----------------------------------------------------
        audit(
            db,
            owner.id,
            "SOCIAL_CONTENT_ANALYZED",
            "analysis",
            ai.id,
            metadata={
                "platform": content.platform,
                "content_id": content.content_id,
                "image_ocr": image_analyzed,
                "media_count": len(media),
                "has_image": has_image,
                "has_status_text": has_status_text,
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


async def persist_manual_analysis(
    db: Session,
    user: User,
    text: str,
    result: dict,
):
    """
    Save manual scanner result.
    """

    ai = AnalysisResult(
        input_text=text,
        user_id=user.id,
        **result,
    )

    db.add(ai)
    db.flush()

    if result["risk_score"] >= 61:

        incident = Incident(
            user_id=user.id,
            analysis_id=ai.id,
            title=(
                f"{result['severity']} "
                "leak detection"
            ),
        )

        db.add(
            incident
        )

        db.flush()

        db.add(
            Alert(
                user_id=user.id,
                incident_id=incident.id,
                severity=result[
                    "severity"
                ],
                message=(
                    "LeakGuard detected a "
                    f"{result['severity']} "
                    "risk finding."
                ),
            )
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