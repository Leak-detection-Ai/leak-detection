from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import require_admin
from app.db.session import get_db
from app.models.models import User, AuditLog

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/audit")
def audit_logs(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    return db.query(AuditLog).order_by(AuditLog.created_at.desc()).limit(500).all()
