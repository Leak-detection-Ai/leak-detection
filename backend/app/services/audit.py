from sqlalchemy.orm import Session
from app.models.models import AuditLog

def audit(db: Session, user_id: str | None, action: str, resource_type=None, resource_id=None, ip=None, metadata=None):
    # Do not pass credentials, tokens or raw secrets to this helper.
    row = AuditLog(
        user_id=user_id, action=action, resource_type=resource_type,
        resource_id=resource_id, ip_address=ip, metadata_json=metadata or {}
    )
    db.add(row)
