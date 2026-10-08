import hmac, secrets
from app.core.config import settings

def issue_csrf():
    return secrets.token_urlsafe(32)

def valid_csrf(cookie: str | None, header: str | None):
    return bool(cookie and header and hmac.compare_digest(cookie, header))
