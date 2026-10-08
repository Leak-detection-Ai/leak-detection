from app.db.session import SessionLocal
from app.models.models import User
from app.core.security import hash_password
from app.core.config import settings

def main():
    if not settings.seed_demo:
        print("SEED_DEMO is false; nothing to seed.")
        return
    db = SessionLocal()
    try:
        if not db.query(User).filter_by(email=settings.demo_email.lower()).first():
            db.add(User(email=settings.demo_email.lower(), password_hash=hash_password(settings.demo_password), role="admin"))
            db.commit()
            print("Demo admin created:", settings.demo_email)
    finally:
        db.close()

if __name__ == "__main__":
    main()
