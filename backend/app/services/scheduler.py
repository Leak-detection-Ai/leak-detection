import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import (
    decrypt_secret,
    encrypt_secret,
)
from app.db.session import SessionLocal
from app.models.models import (
    SocialAccount,
    User,
)
from app.services.social import (
    mastodon_statuses,
    mastodon_refresh,
    store_content,
    find_deleted_open_incident_content,
)
from app.services.analysis import (
    analyze_unprocessed_content,
    reconcile_deleted_social_content,
)


logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(
    timezone="UTC"
)

_lock = asyncio.Lock()


async def sync_connected_accounts():

    if _lock.locked():
        return

    async with _lock:

        db: Session = SessionLocal()

        try:

            accounts = (
                db.query(SocialAccount)
                .filter_by(
                    platform="mastodon",
                    connected=True,
                )
                .all()
            )

            for account in accounts:

                account_id = account.id

                try:

                    access = decrypt_secret(
                        account.access_token_encrypted
                    )

                    needs_refresh = (
                        account.token_expires_at
                        is not None
                        and account.token_expires_at
                        <= (
                            datetime.now(timezone.utc)
                            + timedelta(
                                seconds=60
                            )
                        )
                    )

                    try:

                        if (
                            needs_refresh
                            and account.refresh_token_encrypted
                        ):
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
                                        token["refresh_token"]
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
                                            token["expires_in"]
                                        )
                                    )
                                )

                            db.commit()

                            access = token[
                                "access_token"
                            ]

                        _, items = await mastodon_statuses(
                            account.instance_url,
                            access,
                        )

                    except Exception:

                        if not account.refresh_token_encrypted:
                            raise

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

                        access = token[
                            "access_token"
                        ]

                        _, items = await mastodon_statuses(
                            account.instance_url,
                            access,
                        )

                    sync_result = store_content(
                        db,
                        account,
                        items,
                    )

                    deleted_ids = (
                        await find_deleted_open_incident_content(
                            db,
                            account,
                            access,
                        )
                    )

                    user = (
                        db.query(User)
                        .filter_by(
                            id=account.user_id
                        )
                        .first()
                    )

                    if user:

                        reconcile_deleted_social_content(
                            db,
                            user,
                            deleted_ids,
                        )

                        await analyze_unprocessed_content(
                            db,
                            user,
                        )

                    logger.info(
                        (
                            "Mastodon sync completed "
                            "for account %s: inserted=%s "
                            "changed=%s deleted=%s"
                        ),
                        account_id,
                        sync_result["inserted"],
                        sync_result["changed"],
                        len(deleted_ids),
                    )

                except Exception:

                    db.rollback()

                    # IMPORTANT:
                    # Do NOT set account.connected=False
                    # for temporary network/API errors.
                    logger.exception(
                        "Mastodon sync failed for account %s",
                        account_id,
                    )

        finally:
            db.close()


def start_scheduler():

    if not scheduler.running:

        scheduler.add_job(
            sync_connected_accounts,
            "interval",
            seconds=max(
                30,
                settings.social_sync_interval_seconds,
            ),
            id="mastodon-sync",
            replace_existing=True,
            coalesce=True,
            max_instances=1,
        )

        scheduler.start()

        logger.info(
            "Mastodon background sync started"
        )


def stop_scheduler():

    if scheduler.running:

        scheduler.shutdown(
            wait=False
        )

        logger.info(
            "Mastodon background sync stopped"
        )