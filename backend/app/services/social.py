from datetime import datetime, timezone
import httpx
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.models import SocialAccount, SocialContent

async def mastodon_register(instance: str):
    base = instance.rstrip("/")
    payload = {
        "client_name": settings.mastodon_client_name,
        "redirect_uris": settings.mastodon_redirect_uri,
        "scopes": settings.mastodon_scopes,
        "website": settings.mastodon_client_website,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{base}/api/v1/apps", json=payload)
        r.raise_for_status()
        return r.json()

async def mastodon_exchange(instance: str, code: str, verifier: str):
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
        r = await client.post(f"{base}/oauth/token", data=data)
        r.raise_for_status()
        return r.json()

async def mastodon_refresh(instance: str, refresh_token: str):
    base = instance.rstrip("/")
    data = {
        "client_id": settings.mastodon_client_id,
        "client_secret": settings.mastodon_client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(f"{base}/oauth/token", data=data)
        r.raise_for_status()
        return r.json()

async def mastodon_me(instance: str, access_token: str):
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{instance.rstrip('/')}/api/v1/accounts/verify_credentials",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return r.json()

async def mastodon_statuses(instance: str, access_token: str):
    me = await mastodon_me(instance, access_token)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{instance.rstrip('/')}/api/v1/accounts/{me['id']}/statuses",
            params={"limit": 40, "exclude_replies": "false"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        r.raise_for_status()
        return me, r.json()

def save_account(db: Session, user_id: str, profile: dict, token: dict, instance: str):
    expires_at = None
    if token.get("expires_in"):
        expires_at = datetime.now(timezone.utc).timestamp() + int(token["expires_in"])
        expires_at = datetime.fromtimestamp(expires_at, timezone.utc)
    provider_id = str(profile["id"])
    username = profile.get("acct") or profile.get("username") or profile.get("display_name") or provider_id
    account = db.query(SocialAccount).filter_by(
        user_id=user_id, platform="mastodon", instance_url=instance
    ).first()
    if not account:
        account = SocialAccount(
            user_id=user_id,
            platform="mastodon",
            instance_url=instance,
            provider_user_id=provider_id,
            username=username,
            access_token_encrypted=encrypt_secret(token["access_token"]),
            refresh_token_encrypted=encrypt_secret(token["refresh_token"]) if token.get("refresh_token") else None,
            token_expires_at=expires_at,
            scopes=token.get("scope", settings.mastodon_scopes),
        )
        db.add(account)
    else:
        account.provider_user_id = provider_id
        account.username = username
        account.access_token_encrypted = encrypt_secret(token["access_token"])
        if token.get("refresh_token"):
            account.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
        account.scopes = token.get("scope", account.scopes)
        account.token_expires_at = expires_at or account.token_expires_at
        account.connected = True
    db.commit()
    return account

def store_content(db: Session, account: SocialAccount, items: list[dict]):
    count = 0
    for item in items:
        cid = str(item["id"])
        if db.query(SocialContent).filter_by(account_id=account.id, content_id=cid).first():
            continue
        text = item.get("content", "")
        url = item.get("url")
        created = None
        if item.get("created_at"):
            try:
                created = datetime.fromisoformat(item["created_at"].replace("Z", "+00:00"))
            except ValueError:
                created = None
        media = [
    {
        "type": a.get("type"),
        "url": a.get("url"),
        "preview_url": a.get("preview_url"),
        "description": a.get("description") or "",
    }
    for a in (
        item.get("media_attachments")
        or []
    )
    if a.get("url")
]
        db.add(SocialContent(
            account_id=account.id,
            platform="mastodon",
            content_id=cid,
            content_type="status",
            content=text,
            source_url=url,
            remote_created_at=created,
            metadata_json={"sensitive": bool(item.get("sensitive")), "media": media},
        ))
        count += 1
    account.last_sync = datetime.now(timezone.utc)
    db.commit()
    return count
