from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import SocialAccount, User
from app.schemas.schemas import AccountOut
from app.services.social import decrypt_secret, encrypt_secret, mastodon_statuses, mastodon_refresh, store_content
from app.services.analysis import analyze_unprocessed_content
from app.services.audit import audit

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.get("", response_model=list[AccountOut])
def accounts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(SocialAccount).filter_by(user_id=user.id, platform="mastodon").order_by(SocialAccount.created_at.desc()).all()

@router.delete("/{account_id}")
def disconnect(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = db.query(SocialAccount).filter_by(id=account_id, user_id=user.id, platform="mastodon").first()
    if not account:
        raise HTTPException(404, "Account not found")
    account.connected = False
    account.access_token_encrypted = "DISCONNECTED"
    account.refresh_token_encrypted = None
    audit(db, user.id, "ACCOUNT_DISCONNECTED", "social_account", account.id,
          metadata={"platform": "mastodon"})
    db.commit()
    return {"ok": True}

@router.post("/{account_id}/sync")
async def sync(account_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    account = db.query(SocialAccount).filter_by(
        id=account_id, user_id=user.id, platform="mastodon", connected=True
    ).first()
    if not account:
        raise HTTPException(404, "Account not found")

    access = decrypt_secret(account.access_token_encrypted)
    try:
        _, items = await mastodon_statuses(account.instance_url, access)
    except Exception:
        if not account.refresh_token_encrypted:
            raise HTTPException(502, "Mastodon authorization expired. Reconnect the account.")
        try:
            token = await mastodon_refresh(
                account.instance_url, decrypt_secret(account.refresh_token_encrypted)
            )
            account.access_token_encrypted = encrypt_secret(token["access_token"])
            if token.get("refresh_token"):
                account.refresh_token_encrypted = encrypt_secret(token["refresh_token"])
            if token.get("expires_in"):
                account.token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
            db.commit()
            _, items = await mastodon_statuses(account.instance_url, token["access_token"])
        except Exception as exc:
            account.connected = False
            db.commit()
            raise HTTPException(502, "Mastodon sync failed. Please reconnect the account.") from exc

    synced = store_content(db, account, items)
    analyzed, incidents, results = await analyze_unprocessed_content(db, user)
    return {
        "synced": synced,
        "analyzed": analyzed,
        "incidents_created": incidents,
        "results": [
            {"id": ai.id, "risk_score": result["risk_score"], "severity": result["severity"]}
            for ai, result in results
        ],
    }
