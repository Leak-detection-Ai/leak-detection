from datetime import datetime, timedelta, timezone
import hashlib, secrets
from cryptography.fernet import Fernet
from jose import jwt
from passlib.context import CryptContext
from .config import settings

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
fernet = Fernet(settings.token_encryption_key.encode())

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)

def create_token(subject: str, token_type: str, expires_delta: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {"sub": subject, "type": token_type, "iat": now, "exp": now + expires_delta}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

def create_access_token(user_id: str) -> str:
    return create_token(user_id, "access", timedelta(minutes=settings.access_token_minutes))

def create_refresh_token(user_id: str, jti: str) -> str:
    return create_token(user_id, "refresh", timedelta(days=settings.refresh_token_days)) + "." + jti

def random_token(n: int = 32) -> str:
    return secrets.token_urlsafe(n)

def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def encrypt_secret(value: str) -> str:
    return fernet.encrypt(value.encode()).decode()

def decrypt_secret(value: str) -> str:
    return fernet.decrypt(value.encode()).decode()
