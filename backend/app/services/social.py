from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.models import (
    AnalysisResult,
    Incident,
    SocialAccount,
    SocialContent,
)


async def mastodon_register(instance: str):
    base = instance.rstrip("/")

    payload = {
        "client_name": settings.mastodon_client_name,
        "redirect_uris": settings.mastodon_redirect_uri,
        "scopes": settings.mastodon_scopes,
        "website": settings.mastodon_client_website,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base}/api/v1/apps",
            json=payload,
        )
        response.raise_for_status()
        return response.json()


async def mastodon_exchange(
    instance: str,
    code: str,
    verifier: str,
):
    base = instance.rstrip("/")

    data = {
        "client_id": settings.mastodon_client_id,
        "client_secret": settings.mastodon_client_secret,
        "redirect_uri": settings.mastodon_redirect_uri,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": verifier,
        "scope": settings.mastodon_scopes,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base}/oauth/token",
            data=data,
        )
        response.raise_for_status()
        return response.json()


async def mastodon_refresh(
    instance: str,
    refresh_token: str,
):
    base = instance.rstrip("/")

    data = {
        "client_id": settings.mastodon_client_id,
        "client_secret": settings.mastodon_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(
            f"{base}/oauth/token",
            data=data,
        )
        response.raise_for_status()
        return response.json()


async def mastodon_me(
    instance: str,
    access_token: str,
):
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{instance.rstrip('/')}/api/v1/accounts/verify_credentials",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        response.raise_for_status()
        return response.json()


async def mastodon_statuses(
    instance: str,
    access_token: str,
):
    me = await mastodon_me(
        instance,
        access_token,
    )

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            f"{instance.rstrip('/')}/api/v1/accounts/{me['id']}/statuses",
            params={
                "limit": 40,
                "exclude_replies": "false",
            },
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )
        response.raise_for_status()

        return me, response.json()


async def mastodon_status(
    instance: str,
    access_token: str,
    status_id: str,
):
    """
    Fetch one specific Mastodon status.

    Used to distinguish:
    - still exists
    - deleted
    - temporary API/network failure
    """

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(
            connect=10.0,
            read=15.0,
            write=10.0,
            pool=10.0,
        ),
        follow_redirects=True,
    ) as client:

        response = await client.get(
            f"{instance.rstrip('/')}/api/v1/statuses/{status_id}",
            headers={
                "Authorization": f"Bearer {access_token}",
            },
        )

        if response.status_code in (404, 410):
            return None

        response.raise_for_status()

        return response.json()


def save_account(
    db: Session,
    user_id: str,
    profile: dict,
    token: dict,
    instance: str,
):
    expires_at = None

    if token.get("expires_in"):
        expires_at = (
            datetime.now(timezone.utc)
            + __import__("datetime").timedelta(
                seconds=int(token["expires_in"])
            )
        )

    provider_id = str(profile["id"])

    username = (
        profile.get("acct")
        or profile.get("username")
        or profile.get("display_name")
        or provider_id
    )

    account = (
        db.query(SocialAccount)
        .filter_by(
            user_id=user_id,
            platform="mastodon",
            instance_url=instance,
        )
        .first()
    )

    if not account:
        account = SocialAccount(
            user_id=user_id,
            platform="mastodon",
            instance_url=instance,
            provider_user_id=provider_id,
            username=username,
            access_token_encrypted=encrypt_secret(
                token["access_token"]
            ),
            refresh_token_encrypted=(
                encrypt_secret(token["refresh_token"])
                if token.get("refresh_token")
                else None
            ),
            token_expires_at=expires_at,
            scopes=token.get(
                "scope",
                settings.mastodon_scopes,
            ),
        )

        db.add(account)

    else:
        account.provider_user_id = provider_id
        account.username = username

        account.access_token_encrypted = encrypt_secret(
            token["access_token"]
        )

        if token.get("refresh_token"):
            account.refresh_token_encrypted = encrypt_secret(
                token["refresh_token"]
            )

        account.scopes = token.get(
            "scope",
            account.scopes,
        )

        if expires_at:
            account.token_expires_at = expires_at

        account.connected = True

    db.commit()

    return account


def _parse_created_at(value):
    if not value:
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None


def _mastodon_media(item: dict) -> list[dict]:
    output = []

    for attachment in (
        item.get("media_attachments")
        or []
    ):
        if not attachment.get("url"):
            continue

        output.append(
            {
                "type": attachment.get("type"),
                "url": attachment.get("url"),
                "preview_url": attachment.get(
                    "preview_url"
                ),
                "description": (
                    attachment.get("description")
                    or ""
                ),
            }
        )

    return output


def store_content(
    db: Session,
    account: SocialAccount,
    items: list[dict],
):
    """
    Insert new Mastodon statuses and update statuses
    that were edited after the previous sync.
    """

    inserted = 0
    changed = 0

    now = datetime.now(timezone.utc)

    for item in items:
        cid = str(item["id"])

        existing = (
            db.query(SocialContent)
            .filter_by(
                account_id=account.id,
                content_id=cid,
            )
            .first()
        )

        text = item.get("content", "") or ""
        url = item.get("url")
        remote_created_at = _parse_created_at(
            item.get("created_at")
        )
        media = _mastodon_media(item)
        sensitive = bool(
            item.get("sensitive")
        )

        new_metadata = {
            "sensitive": sensitive,
            "media": media,
        }

        if not existing:
            new_metadata.update(
                {
                    "source_state": "active",
                    "analysis_pending": True,
                    "last_seen_at": now.isoformat(),
                }
            )

            db.add(
                SocialContent(
                    account_id=account.id,
                    platform="mastodon",
                    content_id=cid,
                    content_type="status",
                    content=text,
                    source_url=url,
                    remote_created_at=remote_created_at,
                    metadata_json=new_metadata,
                )
            )

            inserted += 1
            continue

        old_metadata = dict(
            existing.metadata_json or {}
        )

        old_media = old_metadata.get(
            "media",
            [],
        )

        old_sensitive = bool(
            old_metadata.get(
                "sensitive",
                False,
            )
        )

        content_changed = (
            (existing.content or "") != text
            or (existing.source_url or "") != (
                url or ""
            )
            or old_media != media
            or old_sensitive != sensitive
        )

        existing.content = text
        existing.source_url = url
        existing.remote_created_at = (
            remote_created_at
            or existing.remote_created_at
        )

        old_metadata.update(
            new_metadata
        )

        old_metadata["source_state"] = "active"
        old_metadata["last_seen_at"] = (
            now.isoformat()
        )

        if content_changed:
            old_metadata["analysis_pending"] = True
            old_metadata["source_changed_at"] = (
                now.isoformat()
            )
            changed += 1

        elif "analysis_pending" not in old_metadata:
            old_metadata["analysis_pending"] = False

        existing.metadata_json = old_metadata

    account.last_sync = now

    db.commit()

    return {
        "inserted": inserted,
        "changed": changed,
        "total": inserted + changed,
    }


async def find_deleted_open_incident_content(
    db: Session,
    account: SocialAccount,
    access_token: str,
) -> list[str]:
    """
    Check only statuses that matter for active incidents.

    A status is considered deleted only when Mastodon explicitly
    returns 404/410.

    Temporary timeout/network/auth errors are ignored and never
    interpreted as deletion.
    """

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
            SocialContent.account_id == account.id,
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

    deleted_ids = []

    for content, analysis, incident in rows:

        metadata = dict(
            content.metadata_json or {}
        )

        if metadata.get(
            "source_state"
        ) == "deleted":
            deleted_ids.append(
                content.id
            )
            continue

        try:
            remote = await mastodon_status(
                account.instance_url,
                access_token,
                content.content_id,
            )

            if remote is not None:
                continue

            metadata["source_state"] = "deleted"
            metadata["deleted_at"] = (
                datetime.now(
                    timezone.utc
                ).isoformat()
            )
            metadata["analysis_pending"] = False

            content.metadata_json = metadata

            deleted_ids.append(
                content.id
            )

        except httpx.HTTPStatusError:
            # Any HTTP error other than the explicit 404/410 handled
            # in mastodon_status() is NOT considered deletion.
            continue

        except Exception:
            # Network timeout / temporary remote failure.
            continue

    if deleted_ids:
        db.commit()

    return deleted_ids