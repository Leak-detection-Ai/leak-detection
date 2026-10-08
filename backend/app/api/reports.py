import csv
import io
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.db.session import get_db
from app.models.models import User, AnalysisResult, Incident, SocialContent

router = APIRouter(prefix="/reports", tags=["reports"])

def rows_for_user(user, db):
    incidents = db.query(Incident).filter_by(user_id=user.id).order_by(Incident.created_at.desc()).all()
    output = []
    for incident in incidents:
        analysis = db.get(AnalysisResult, incident.analysis_id) if incident.analysis_id else None
        content = db.get(SocialContent, analysis.content_id) if analysis and analysis.content_id else None
        if not analysis:
            continue
        output.append({
            "incident_id": incident.id,
            "status": incident.status,
            "title": incident.title,
            "risk_score": analysis.risk_score,
            "severity": analysis.severity,
            "decision": analysis.decision,
            "confidence": analysis.confidence,
            "findings": analysis.findings or [],
            "recommendations": analysis.recommendations or [],
            "explanation": analysis.explanation,
            "platform": content.platform if content else "manual",
            "source_url": content.source_url if content else None,
            "source_content": content.content if content else analysis.input_text,
            "created_at": analysis.created_at.isoformat(),
        })
    return output

@router.get("/json")
def report_json(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return {
        "generated_for": user.email,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "platform": "Mastodon",
        "incidents": rows_for_user(user, db),
    }

@router.get("/csv")
def report_csv(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = io.StringIO()
    writer = csv.writer(rows)
    writer.writerow([
        "incident_id", "status", "title", "risk_score", "severity", "decision",
        "confidence", "platform", "source_url", "created_at",
    ])
    for item in rows_for_user(user, db):
        writer.writerow([
            item["incident_id"], item["status"], item["title"], item["risk_score"],
            item["severity"], item["decision"], item["confidence"], item["platform"],
            item["source_url"] or "", item["created_at"],
        ])
    return StreamingResponse(
        iter([rows.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leakguard-report.csv"},
    )
