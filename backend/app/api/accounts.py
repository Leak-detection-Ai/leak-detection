from datetime import datetime, timedelta, timezone

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Response,
)
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import (
    AnalysisResult,
    SocialAccount,
    SocialContent,
    User,
)
from app.schemas.schemas import AccountOut
from app.services.social import (
    decrypt_secret,
    encrypt_secret,
    mastodon_refresh,
    mastodon_statuses,
    store_content,
    find_deleted_open_incident_content,
)
from app.services.audit import audit
from app.services.social import (
    decrypt_secret,
    encrypt_secret,
    mastodon_refresh,
    mastodon_statuses,
    store_content,
)


router = APIRouter(
    prefix="/accounts",
    tags=["accounts"],
)


class SocialOCRIn(BaseModel):
    ocr_text: str = ""


def _image_media(
    content: SocialContent,
) -> list[dict]:
    """
    Return image attachments belonging to a Mastodon post.
    """

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
        return []

    output = []

    for index, attachment in enumerate(
        media[:4]
    ):
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

        image_url = (
            attachment.get("url")
            or attachment.get(
                "preview_url"
            )
            or ""
        )

        if not image_url:
            continue

        output.append(
            {
                "index": index,
                "description": (
                    attachment.get(
                        "description"
                    )
                    or ""
                ),
            }
        )

    return output


@router.get(
    "",
    response_model=list[AccountOut],
)
def accounts(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(
            SocialAccount
        )
        .filter_by(
            user_id=user.id,
            platform="mastodon",
            connected=True,
        )
        .order_by(
            SocialAccount.created_at.desc()
        )
        .all()
    )


@router.delete(
    "/{account_id}"
)
def disconnect(
    account_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(
            SocialAccount
        )
        .filter_by(
            id=account_id,
            user_id=user.id,
            platform="mastodon",
        )
        .first()
    )

    if not account:
        raise HTTPException(
            404,
            "Account not found",
        )

    account.connected = False

    account.access_token_encrypted = (
        "DISCONNECTED"
    )

    account.refresh_token_encrypted = None

    audit(
        db,
        user.id,
        "ACCOUNT_DISCONNECTED",
        "social_account",
        account.id,
        metadata={
            "platform": "mastodon"
        },
    )

    db.commit()

    return {
        "ok": True
    }


@router.post(
    "/{account_id}/sync"
)
async def sync(
    account_id: str,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    account = (
        db.query(
            SocialAccount
        )
        .filter_by(
            id=account_id,
            user_id=user.id,
            platform="mastodon",
            connected=True,
        )
        .first()
    )

    if not account:
        raise HTTPException(
            404,
            "Account not found",
        )

    access = decrypt_secret(
        account.access_token_encrypted
    )

    try:
        _, items = await mastodon_statuses(
            account.instance_url,
            access,
        )

    except Exception:

        if not account.refresh_token_encrypted:
            raise HTTPException(
                502,
                "Mastodon authorization expired. Reconnect the account.",
            )

        try:
            token = await mastodon_refresh(
                account.instance_url,
                decrypt_secret(
                    account.refresh_token_encrypted
                ),
            )

            account.access_token_encrypted = (
                encrypt_secret(
                    token["access_token"]
                )
            )

            if token.get(
                "refresh_token"
            ):
                account.refresh_token_encrypted = (
                    encrypt_secret(
                        token[
                            "refresh_token"
                        ]
                    )
                )

            if token.get(
                "expires_in"
            ):
                account.token_expires_at = (
                    datetime.now(
                        timezone.utc
                    )
                    + timedelta(
                        seconds=int(
                            token[
                                "expires_in"
                            ]
                        )
                    )
                )

            db.commit()

            _, items = await mastodon_statuses(
                account.instance_url,
                token["access_token"],
            )

            access = token["access_token"]

        except Exception as exc:

            raise HTTPException(
                502,
                "Mastodon sync failed. Please reconnect the account.",
            ) from exc

    # ---------------------------------------------------------
    # Save NEW statuses and UPDATE EDITED statuses
    # ---------------------------------------------------------
    sync_result = store_content(
    db,
    account,
    items,
)

deleted_ids = await find_deleted_open_incident_content(
    db,
    account,
    access,
)

deleted_resolved = reconcile_deleted_social_content(
    db,
    user,
    deleted_ids,
)

analyzed, incidents, results = (
    await analyze_unprocessed_content(
        db,
        user,
    )
)

    # ---------------------------------------------------------
    # Build browser OCR queue
    #
    # IMPORTANT:
    # Queue uses the DATABASE content UUID.
    # This allows the frontend to call:
    # /accounts/{account_id}/content/{content_id}/...
    #
    # Edited image posts are queued again because
    # store_content() sets analysis_pending=True.
    # ---------------------------------------------------------
    ocr_queue = []

    image_contents = (
        db.query(
            SocialContent
        )
        .filter_by(
            account_id=account.id
        )
        .order_by(
            SocialContent.remote_created_at.desc()
        )
        .limit(40)
        .all()
    )

    for content in image_contents:

        metadata = dict(
            content.metadata_json or {}
        )

        existing = (
            db.query(
                AnalysisResult
            )
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

        # -----------------------------------------------------
        # IMPORTANT:
        # Previously we skipped every post with an existing
        # AnalysisResult.
        #
        # That prevented edited Mastodon images from being
        # rescanned.
        #
        # Now we only skip when the analysis is already current.
        # -----------------------------------------------------
        if (
            existing
            and not analysis_pending
        ):
            continue

        media = _image_media(
            content
        )

        if not media:
            continue

        if metadata.get(
            "source_state"
        ) == "deleted":
            continue

            ocr_queue = []

    image_contents = (
        db.query(
            SocialContent
        )
        .filter_by(
            account_id=account.id
        )
        .order_by(
            SocialContent.remote_created_at.desc()
        )
        .limit(40)
        .all()
    )

    for content in image_contents:

        metadata = dict(
            content.metadata_json or {}
        )

        existing = (
            db.query(
                AnalysisResult
            )
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

        if (
            existing
            and not analysis_pending
        ):
            continue

        media = _image_media(
            content
        )

        if not media:
            continue

        if metadata.get(
            "source_state"
        ) == "deleted":
            continue

        ocr_queue.append(
            {
                "content_id": content.id,
                "source_url": content.source_url,
                "media": media,
            }
        )


@router.get(
    "/{account_id}/content/{content_id}/media/{media_index}"
)
async def get_social_media(
    account_id: str,
    content_id: str,
    media_index: int,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Server-side image proxy.

    The browser uses this endpoint so Tesseract.js does not
    need to access Mastodon's media server directly.
    """

    account = (
        db.query(
            SocialAccount
        )
        .filter_by(
            id=account_id,
            user_id=user.id,
            platform="mastodon",
        )
        .first()
    )

    if not account:
        raise HTTPException(
            404,
            "Account not found",
        )

    content = (
        db.query(
            SocialContent
        )
        .filter_by(
            id=content_id,
            account_id=account.id,
        )
        .first()
    )

    if not content:
        raise HTTPException(
            404,
            "Social content not found",
        )

    raw_media = (
        (content.metadata_json or {})
        .get(
            "media",
            [],
        )
    )

    if (
        not isinstance(
            raw_media,
            list,
        )
        or media_index < 0
        or media_index >= len(
            raw_media
        )
        or not isinstance(
            raw_media[media_index],
            dict,
        )
    ):
        raise HTTPException(
            404,
            "Image attachment not found",
        )

    attachment = raw_media[
        media_index
    ]

    if (
        str(
            attachment.get(
                "type",
                "",
            )
        ).lower().strip()
        != "image"
    ):
        raise HTTPException(
            415,
            "Attachment is not an image",
        )

    image_url = (
        attachment.get("url")
        or attachment.get(
            "preview_url"
        )
        or ""
    )

    if not image_url.startswith(
        (
            "http://",
            "https://",
        )
    ):
        raise HTTPException(
            422,
            "Invalid Mastodon image URL",
        )

    try:

        async with httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=30.0,
                write=10.0,
                pool=10.0,
            ),
            follow_redirects=True,
        ) as client:

            response = await client.get(
                image_url,
                headers={
                    "User-Agent":
                        "LeakGuard/1.3",
                    "Accept":
                        "image/*",
                },
            )

        response.raise_for_status()

        data = response.content

        if len(data) > (
            8 * 1024 * 1024
        ):
            raise HTTPException(
                413,
                "Image exceeds the 8 MB processing limit",
            )

        content_type = (
            response.headers
            .get(
                "content-type",
                "image/png",
            )
            .split(";")[0]
            .lower()
        )

        if not content_type.startswith(
            "image/"
        ):
            raise HTTPException(
                415,
                "Remote resource is not an image",
            )

        return Response(
            content=data,
            media_type=content_type,
            headers={
                "Cache-Control":
                    "private, no-store",
            },
        )

    except HTTPException:
        raise

    except Exception as exc:

        raise HTTPException(
            502,
            "Unable to retrieve Mastodon image",
        ) from exc


@router.post(
    "/{account_id}/content/{content_id}/ocr"
)
async def analyze_social_ocr(
    account_id: str,
    content_id: str,
    data: SocialOCRIn,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """
    Receive OCR text generated locally in the browser
    and run LeakGuard's existing detector.
    """

    account = (
        db.query(
            SocialAccount
        )
        .filter_by(
            id=account_id,
            user_id=user.id,
            platform="mastodon",
        )
        .first()
    )

    if not account:
        raise HTTPException(
            404,
            "Account not found",
        )

    content = (
        db.query(
            SocialContent
        )
        .filter_by(
            id=content_id,
            account_id=account.id,
        )
        .first()
    )

    if not content:
        raise HTTPException(
            404,
            "Social content not found",
        )

    metadata = dict(
        content.metadata_json or {}
    )

    if metadata.get(
        "source_state"
    ) == "deleted":
        raise HTTPException(
            409,
            "Cannot analyze a deleted Mastodon status",
        )

    ai, result, incident_created = (
        await persist_social_ocr_analysis(
            db,
            user,
            content,
            data.ocr_text,
        )
    )

    return {
        "id": ai.id,
        "risk_score": ai.risk_score,
        "severity": ai.severity,
        "decision": ai.decision,
        "incident_created": bool(
            incident_created
        ),
    }