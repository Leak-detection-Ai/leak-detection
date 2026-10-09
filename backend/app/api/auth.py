from datetime import datetime, timedelta, timezone
import uuid
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token, create_refresh_token, hash_token
from app.db.session import get_db
from app.models.models import User, RefreshToken
from app.schemas.schemas import RegisterIn, LoginIn, UserOut
from app.services.audit import audit
from app.core.csrf import issue_csrf

router = APIRouter(prefix="/auth", tags=["auth"])
@router.get("/csrf")
def csrf_token(response: Response):
    token = issue_csrf()

    response.set_cookie(
        "csrf_token",
        token,
        httponly=False,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=86400,
        path="/",
    )

    return {"csrf_token": token}

def set_session(response: Response, db: Session, user: User):
    access = create_access_token(user.id)
    jti = str(uuid.uuid4())
    refresh = create_refresh_token(user.id, jti)
    row = RefreshToken(user_id=user.id, token_hash=hash_token(refresh), expires_at=datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_days))
    db.add(row)
    db.commit()
    response.set_cookie("access_token", access, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.access_token_minutes*60, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.refresh_token_days*86400, path="/auth/refresh")

@router.post("/register", response_model=UserOut)
def register(data: RegisterIn, response: Response, db: Session = Depends(get_db)):
    if db.query(User).filter_by(email=data.email.lower()).first():
        raise HTTPException(409, "Email already registered")
    user = User(email=data.email.lower(), password_hash=hash_password(data.password))
    db.add(user); db.flush()
    audit(db, user.id, "REGISTER", "user", user.id)
    set_session(response, db, user)
    db.commit()
    return user

@router.post("/login", response_model=UserOut)
def login(data: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(email=data.email.lower()).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    audit(db, user.id, "LOGIN", "user", user.id)
    set_session(response, db, user)
    db.commit()
    return user

@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(401, "Refresh session missing")
    row = db.query(RefreshToken).filter_by(token_hash=hash_token(token), revoked=False).first()
    if not row or row.expires_at < datetime.now(timezone.utc):
        raise HTTPException(401, "Refresh session expired")
    row.revoked = True
    set_session(response, db, row.user)
    audit(db, row.user.id, "REFRESH", "session", row.id)
    db.commit()
    return row.user

@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    refresh = request.cookies.get("refresh_token")
    if refresh:
        row = db.query(RefreshToken).filter_by(token_hash=hash_token(refresh)).first()
        if row:
            row.revoked = True
            audit(db, row.user_id, "LOGOUT", "session", row.id)
            db.commit()
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/auth/refresh")
    return {"ok": True}

@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
