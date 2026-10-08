import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session
from datetime import datetime, timedelta, timezone

from app.core.config import settings
from app.core.security import decrypt_secret, encrypt_secret
from app.db.session import SessionLocal
from app.models.models import SocialAccount
from app.services.social import mastodon_statuses, mastodon_refresh, store_content
from app.services.analysis import analyze_unprocessed_content

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")
_lock = asyncio.Lock()

async def sync_connected_accounts():
    if _lock.locked():
        return
    async with _lock:
        db: Session = SessionLocal()
        try:
            accounts = db.query(SocialAccount).filter_by(platform="mastodon", connected=True).all()
            for account in accounts:
                try:
                    access = decrypt_secret(account.access_token_encrypted)
                    needs_refresh = (
                        account.token_expires_at is not None
                        and account.token_expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60)
                    )
                    try:
                        if needs_refresh and account.refresh_token_encrypted:
                            token = await mastodon_refresh(
                                account.instance_url,
                                decrypt_secret(account.refresh_token_encrypted),
                            )
                            account.access_token_encrypted = encrypt_secret(token["access_token"])
                            if token.get("refresh_token"):
                                account.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
                            if token.get("expires_in"):
                                account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
                            db.commit()
                            access = token["access_token"]
                        _, items = await mastodon_statuses(account.instance_url, access)
                    except Exception:
                        if not account.refresh_token_encrypted:
                            raise
                        token = await mastodon_refresh(
                            account.instance_url,
                            decrypt_secret(account.refresh_token_encrypted),
                        )
                        account.access_token_encrypted = encrypt_secret(token["access_token"])
                        if token.get("refresh_token"):
                            account.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
                        if token.get("expires_in"):
                            account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
                        db.commit()
                        _, items = await mastodon_statuses(account.instance_url, token["access_token"])
                    store_content(db, account, items)
                    await analyze_unprocessed_content(db, account.user)
                except Exception:
                    logger.exception("Mastodon sync failed for account %s", account.id)
                    account.connected = False
                    db.commit()
        finally:
            db.close()

def start_scheduler():
    if not scheduler.running:
        scheduler.add_job(
            sync_connected_accounts,
            "interval",
            seconds=max(30, settings.social_sync_interval_seconds),
            id="mastodon-sync",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )
        scheduler.start()
        logger.info("Mastodon background sync started")

def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Mastodon background sync stopped")
