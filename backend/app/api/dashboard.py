from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User, SocialAccount, AnalysisResult, Incident, Alert

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    analyses = db.query(AnalysisResult).filter_by(user_id=user.id).all()
    accounts = db.query(SocialAccount).filter_by(user_id=user.id, platform="mastodon").all()
    incidents = db.query(Incident).filter(
        Incident.user_id == user.id,
        Incident.status.notin_(["RESOLVED", "FALSE_POSITIVE"]),
    ).count()
    unread = db.query(Alert).filter_by(user_id=user.id, read=False).count()
    avg = round(sum(a.risk_score for a in analyses) / len(analyses)) if analyses else 0
    return {
        "risk_score": avg,
        "connected_accounts": sum(a.connected for a in accounts),
        "total_scans": len(analyses),
        "open_incidents": incidents,
        "unread_alerts": unread,
        "severity_breakdown": {
            "critical": sum(a.severity == "CRITICAL" for a in analyses),
            "high": sum(a.severity == "HIGH" for a in analyses),
            "medium": sum(a.severity == "MEDIUM" for a in analyses),
            "low": sum(a.severity in {"LOW", "VERY_LOW"} for a in analyses),
        },
    }
