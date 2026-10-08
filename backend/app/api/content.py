from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User, SocialAccount, SocialContent

router = APIRouter(prefix="/content", tags=["content"])

@router.get("")
def content(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(SocialContent).join(SocialAccount).filter(SocialAccount.user_id == user.id).order_by(SocialContent.remote_created_at.desc()).limit(100).all()
    return [{
        "id": r.id, "platform": r.platform, "content": r.content,
        "source_url": r.source_url, "created_at": r.remote_created_at or r.created_at
    } for r in rows]
