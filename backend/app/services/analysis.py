from datetime import datetime, timezone

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


def _severity_rank(value: str | None) -> int:
    ranks = {
        "LOW": 1,
        "MEDIUM": 2,
        "HIGH": 3,
        "CRITICAL": 4,
    }

    return ranks.get(
        (value or "").upper(),
        0,
    )


async def build_social_analysis_text(
    content: SocialContent,
) -> tuple[str, bool]:

    parts: list[str] = []

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


def _incident_query_for_content(
    db: Session,
    content_id: str,
):
    return (
        db.query(Incident)
        .join(
            AnalysisResult,
            Incident.analysis_id
            == AnalysisResult.id,
        )
        .filter(
            AnalysisResult.content_id
            == content_id
        )
        .order_by(
            Incident.created_at.desc()
        )
    )


def _create_incident(
    db: Session,
    owner: User,
    ai: AnalysisResult,
    result: dict,
):
    incident = Incident(
        user_id=owner.id,
        analysis_id=ai.id,
        title=(
            f"{result['severity']} "
            "leak detection"
        ),
        status="OPEN",
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

    return incident


def _reconcile_incident_lifecycle(
    db: Session,
    owner: User,
    content: SocialContent,
    ai: AnalysisResult,
    result: dict,
):
    """
    Keep incidents synchronized with the current analysis result.

    >= 61:
      create or maintain an incident.

    < 61:
      resolve an existing active incident.

    Existing incidents are updated rather than duplicated.
    """

    score = int(
        result.get(
            "risk_score",
            0,
        )
    )

    incident = (
        _incident_query_for_content(
            db,
            content.id,
        )
        .first()
    )

    if score >= 61:

        if incident is None:
            return _create_incident(
                db,
                owner,
                ai,
                result,
            )

        previous_status = (
            incident.status
            or ""
        ).upper()

        previous_analysis = (
            db.query(AnalysisResult)
            .filter_by(
                id=incident.analysis_id
            )
            .first()
        )

        previous_score = (
            int(
                previous_analysis.risk_score
            )
            if previous_analysis
            and previous_analysis.risk_score
            is not None
            else 0
        )

        previous_severity = (
            previous_analysis.severity
            if previous_analysis
            else None
        )

        incident.analysis_id = ai.id
        incident.title = (
            f"{result['severity']} "
            "leak detection"
        )

        if previous_status in (
            "RESOLVED",
            "FALSE_POSITIVE",
        ):
            incident.status = "OPEN"
            incident.resolution = None
            incident.notes = (
                "Incident automatically reopened "
                "because the latest Mastodon analysis "
                "again exceeded the incident threshold."
            )

            db.add(
                Alert(
                    user_id=owner.id,
                    incident_id=incident.id,
                    severity=result["severity"],
                    message=(
                        "LeakGuard reopened a Mastodon "
                        f"{result['severity']} incident "
                        "after updated content analysis."
                    ),
                )
            )

        elif (
            score > previous_score
            or _severity_rank(
                result["severity"]
            )
            > _severity_rank(
                previous_severity
            )
        ):
            db.add(
                Alert(
                    user_id=owner.id,
                    incident_id=incident.id,
                    severity=result["severity"],
                    message=(
                        "LeakGuard detected an increased "
                        "risk level after the Mastodon "
                        "content was updated."
                    ),
                )
            )

        return incident

    # Current score is below incident threshold.
    if incident is not None:

        status = (
            incident.status
            or ""
        ).upper()

        if status in (
            "OPEN",
            "ACKNOWLEDGED",
            "INVESTIGATING",
        ):
            incident.status = "RESOLVED"
            incident.analysis_id = ai.id
            incident.resolution = (
                "Automatically resolved because "
                "the latest Mastodon content analysis "
                "is below the incident threshold."
            )

            incident.notes = (
                "Incident reconciled after Mastodon "
                "content was edited."
            )

    return incident


def _upsert_social_analysis(
    db: Session,
    owner: User,
    content: SocialContent,
    analysis_text: str,
    *,
    image_ocr: bool,
):
    """
    Update the existing analysis for edited content,
    or create one for new content.
    """

    result = analyze_content(
        analysis_text
    )

    ai = (
        db.query(AnalysisResult)
        .filter_by(
            content_id=content.id
        )
        .first()
    )

    if ai is None:

        ai = AnalysisResult(
            input_text=analysis_text,
            content_id=content.id,
            user_id=owner.id,
            **result,
        )

        db.add(ai)
        db.flush()

    else:

        ai.input_text = analysis_text
        ai.user_id = owner.id
        ai.risk_score = result["risk_score"]
        ai.severity = result["severity"]
        ai.decision = result["decision"]
        ai.confidence = result["confidence"]
        ai.findings = result["findings"]
        ai.recommendations = result["recommendations"]
        ai.explanation = result["explanation"]

        db.flush()

    _reconcile_incident_lifecycle(
        db,
        owner,
        content,
        ai,
        result,
    )

    metadata = dict(
        content.metadata_json or {}
    )

    metadata["analysis_pending"] = False
    metadata["last_analyzed_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )
    metadata["image_ocr"] = bool(
        image_ocr
    )

    content.metadata_json = metadata

    audit(
        db,
        owner.id,
        (
            "SOCIAL_IMAGE_ANALYZED"
            if image_ocr
            else "SOCIAL_CONTENT_ANALYZED"
        ),
        "analysis",
        ai.id,
        metadata={
            "platform": content.platform,
            "content_id": content.content_id,
            "image_ocr": image_ocr,
        },
    )

    return ai, result


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

        metadata = dict(
            content.metadata_json or {}
        )

        if metadata.get(
            "source_state"
        ) == "deleted":
            continue

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
            isinstance(item, dict)
            and str(
                item.get(
                    "type",
                    "",
                )
            ).lower().strip()
            == "image"
            and (
                item.get("url")
                or item.get("preview_url")
            )
            for item in media
        )

        has_text = bool(
            (content.content or "").strip()
        )

        if not has_text and not has_image:
            continue

        # Images are processed by the browser OCR workflow.
        if has_image:
            continue

        existing = (
            db.query(AnalysisResult)
            .filter_by(
                content_id=content.id
            )
            .first()
        )

        analysis_pending = bool(
            metadata.get(
                "analysis_pending",
                existing is None,
            )
        )

        # Crucial:
        # existing + analysis_pending=False means current.
        # existing + analysis_pending=True means EDITED
        # and must be analyzed again.
        if (
            existing
            and not analysis_pending
        ):
            continue

        analysis_text = (
            content.content or ""
        ).strip()

        if not analysis_text:
            continue

        old_score = (
            existing.risk_score
            if existing
            else None
        )

        ai, result = _upsert_social_analysis(
            db,
            owner,
            content,
            analysis_text,
            image_ocr=False,
        )

        if existing is None:
            analyzed += 1

        if (
            result["risk_score"] >= 61
            and (
                old_score is None
                or old_score < 61
            )
        ):
            incidents += 1

        results.append(
            (
                ai,
                result,
            )
        )

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
    metadata = dict(
        content.metadata_json or {}
    )

    if metadata.get(
        "source_state"
    ) == "deleted":
        raise ValueError(
            "Cannot analyze deleted Mastodon status"
        )

    parts: list[str] = []

    status_text = (
        content.content or ""
    ).strip()

    if status_text:
        parts.append(
            status_text
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

    if not analysis_text:
        analysis_text = (
            "[Image analyzed: no readable text detected]"
        )

    existing = (
        db.query(AnalysisResult)
        .filter_by(
            content_id=content.id
        )
        .first()
    )

    old_score = (
        existing.risk_score
        if existing
        else None
    )

    ai, result = _upsert_social_analysis(
        db,
        user,
        content,
        analysis_text,
        image_ocr=True,
    )

    incident_created = (
        result["risk_score"] >= 61
        and (
            old_score is None
            or old_score < 61
        )
    )

    db.commit()

    return (
        ai,
        result,
        incident_created,
    )


def reconcile_deleted_social_content(
    db: Session,
    user: User,
    content_ids: list[str],
):
    """
    Resolve active incidents whose Mastodon statuses
    have been confirmed deleted.

    Historical AnalysisResult rows remain untouched.
    """

    if not content_ids:
        return 0

    resolved = 0

    rows = (
        db.query(
            SocialContent,
            AnalysisResult,
            Incident,
        )
        .join(
            AnalysisResult,
            AnalysisResult.content_id
            == SocialContent.id,
        )
        .join(
            Incident,
            Incident.analysis_id
            == AnalysisResult.id,
        )
        .filter(
            SocialContent.id.in_(content_ids),
            SocialContent.account_id.in_(
                db.query(SocialAccount.id)
                .filter(
                    SocialAccount.user_id
                    == user.id
                )
            ),
            Incident.status.in_(
                [
                    "OPEN",
                    "ACKNOWLEDGED",
                    "INVESTIGATING",
                ]
            ),
        )
        .all()
    )

    for content, analysis, incident in rows:

        incident.status = "RESOLVED"
        incident.resolution = (
            "Automatically resolved because the "
            "associated Mastodon status was deleted."
        )
        incident.notes = (
            "Historical analysis retained for audit "
            "purposes. Source Mastodon status no longer exists."
        )

        metadata = dict(
            content.metadata_json or {}
        )

        metadata["source_state"] = "deleted"
        metadata["analysis_pending"] = False

        content.metadata_json = metadata

        audit(
            db,
            user.id,
            "SOCIAL_CONTENT_DELETED",
            "incident",
            incident.id,
            metadata={
                "platform": content.platform,
                "content_id": content.content_id,
                "analysis_id": analysis.id,
            },
        )

        resolved += 1

    db.commit()

    return resolved


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
        _create_incident(
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