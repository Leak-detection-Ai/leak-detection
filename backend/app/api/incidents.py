from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User, Incident, Alert, AnalysisResult, SocialContent, SocialAccount
from app.schemas.schemas import IncidentOut, IncidentUpdate, AlertOut
from app.services.audit import audit

router = APIRouter(tags=["incidents"])

def incident_payload(row: Incident, db: Session):
    analysis = db.get(AnalysisResult, row.analysis_id) if row.analysis_id else None
    content = db.get(SocialContent, analysis.content_id) if analysis and analysis.content_id else None
    return IncidentOut(
        id=row.id, status=row.status, title=row.title, notes=row.notes or "",
        resolution=row.resolution, created_at=row.created_at, updated_at=row.updated_at,
        analysis_id=analysis.id if analysis else None,
        risk_score=analysis.risk_score if analysis else None,
        severity=analysis.severity if analysis else None,
        decision=analysis.decision if analysis else None,
        confidence=analysis.confidence if analysis else None,
        findings=analysis.findings or [] if analysis else [],
        recommendations=analysis.recommendations or [] if analysis else [],
        explanation=analysis.explanation if analysis else None,
        source_platform=content.platform if content else None,
        source_url=content.source_url if content else None,
        source_content=content.content if content else None,
    )

@router.get("/incidents", response_model=list[IncidentOut])
def incidents(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.query(Incident).filter_by(user_id=user.id).order_by(Incident.created_at.desc()).all()
    return [incident_payload(row, db) for row in rows]

@router.patch("/incidents/{incident_id}", response_model=IncidentOut)
def update_incident(
    incident_id: str, data: IncidentUpdate,
    user: User = Depends(current_user), db: Session = Depends(get_db)
):
    row = db.query(Incident).filter_by(id=incident_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Incident not found")
    row.status, row.notes, row.resolution = data.status, data.notes, data.resolution
    audit(db, user.id, "INCIDENT_UPDATED", "incident", row.id,
          metadata={"status": row.status})
    db.commit()
    db.refresh(row)
    return incident_payload(row, db)

@router.get("/alerts", response_model=list[AlertOut])
def alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return db.query(Alert).filter_by(user_id=user.id).order_by(Alert.created_at.desc()).limit(100).all()

@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    row = db.query(Alert).filter_by(id=alert_id, user_id=user.id).first()
    if not row:
        raise HTTPException(404, "Alert not found")
    row.read = True
    audit(db, user.id, "ALERT_READ", "alert", row.id)
    db.commit()
    return {"ok": True}
