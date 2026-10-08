from sqlalchemy.orm import Session
from app.models.models import User, SocialAccount, SocialContent, AnalysisResult, Incident, Alert
from app.services.ai_engine import analyze_content
from app.services.openai_service import explain_with_openai
from app.services.audit import audit

async def analyze_unprocessed_content(db: Session, user: User | None = None):
    query = (
        db.query(SocialContent, SocialAccount, User)
        .join(SocialAccount, SocialAccount.id == SocialContent.account_id)
        .join(User, User.id == SocialAccount.user_id)
    )
    if user:
        query = query.filter(User.id == user.id)
    rows = query.order_by(SocialContent.remote_created_at.desc()).limit(100).all()
    analyzed = 0
    incidents = 0
    results = []

    for content, account, owner in rows:
        if not content.content.strip():
            continue
        if db.query(AnalysisResult).filter_by(content_id=content.id).first():
            continue

        result = analyze_content(content.content)
        enhanced = await explain_with_openai(result)
        if enhanced:
            result["explanation"] = enhanced

        ai = AnalysisResult(
            input_text=content.content,
            content_id=content.id,
            user_id=owner.id,
            **result,
        )
        db.add(ai)
        db.flush()

        if result["risk_score"] >= 61:
            incident = Incident(
                user_id=owner.id,
                analysis_id=ai.id,
                title=f"{result['severity']} leak detection",
            )
            db.add(incident)
            db.flush()
            db.add(Alert(
                user_id=owner.id,
                incident_id=incident.id,
                severity=result["severity"],
                message=f"LeakGuard detected a {result['severity']} risk finding from Mastodon.",
            ))
            incidents += 1

        audit(
            db, owner.id, "SOCIAL_CONTENT_ANALYZED", "analysis", ai.id,
            metadata={"platform": content.platform, "content_id": content.content_id},
        )
        results.append((ai, result))
        analyzed += 1

    db.commit()
    return analyzed, incidents, results

async def persist_manual_analysis(db: Session, user: User, text: str, result: dict):
    ai = AnalysisResult(input_text=text, user_id=user.id, **result)
    db.add(ai)
    db.flush()
    if result["risk_score"] >= 61:
        incident = Incident(
            user_id=user.id,
            analysis_id=ai.id,
            title=f"{result['severity']} leak detection",
        )
        db.add(incident)
        db.flush()
        db.add(Alert(
            user_id=user.id,
            incident_id=incident.id,
            severity=result["severity"],
            message=f"LeakGuard detected a {result['severity']} risk finding.",
        ))
    audit(db, user.id, "SCAN_EXECUTED", "analysis", ai.id)
    db.commit()
    return ai
