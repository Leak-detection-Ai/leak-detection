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
    Build the complete analysis input from:
    1. Mastodon status text
    2. Image alt/description text
    3. OCR text extracted from image attachments

    Returns:
        combined_text,
        image_was_analyzed
    """

    parts = []

    status_text = (
        content.content or ""
    ).strip()

    if status_text:
        parts.append(status_text)

    metadata = (
        content.metadata_json or {}
    )

    media = metadata.get(
        "media",
        [],
    )

    image_analyzed = False

    for attachment in media[:4]:
        if not isinstance(
            attachment,
            dict,
        ):
            continue

        media_type = str(
            attachment.get("type", "")
        ).lower()

        image_url = (
            attachment.get("url")
            or ""
        )

        if media_type != "image":
            continue

        # Analyze Mastodon alt/description text too.
        description = (
            attachment.get("description")
            or ""
        ).strip()

        if description:
            parts.append(
                "[Mastodon image description]\n"
                + description
            )

        if image_url:
            extracted = await extract_text_from_image_url(
                image_url
            )

            if extracted:
                image_analyzed = True

                parts.append(
                    "[Text extracted from Mastodon image]\n"
                    + extracted
                )

    combined = "\n\n".join(
        part
        for part in parts
        if part.strip()
    )

    return combined, image_analyzed


async def analyze_unprocessed_content(
    db: Session,
    user: User | None = None,
):
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

        has_image = any(
            isinstance(item, dict)
            and str(
                item.get("type", "")
            ).lower()
            == "image"
            and item.get("url")
            for item in media
        )

        if (
            not (content.content or "").strip()
            and not has_image
        ):
            continue

        existing = (
            db.query(AnalysisResult)
            .filter_by(
                content_id=content.id
            )
            .first()
        )

        if existing:
            continue

        analysis_text, image_analyzed = (
            await build_social_analysis_text(
                content
            )
        )

        if not analysis_text.strip():
            continue

        result = analyze_content(
            analysis_text
        )

        enhanced = await explain_analysis(result)

        if enhanced:
            result["explanation"] = enhanced

        ai = AnalysisResult(
            input_text=analysis_text,
            content_id=content.id,
            user_id=owner.id,
            **result,
        )

        db.add(ai)
        db.flush()

        if result["risk_score"] >= 61:
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
                    severity=result[
                        "severity"
                    ],
                    message=(
                        "LeakGuard detected a "
                        f"{result['severity']} risk "
                        "finding from Mastodon."
                    ),
                )
            )

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
                "image_ocr": image_analyzed,
                "media_count": len(media),
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

        db.add(incident)
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