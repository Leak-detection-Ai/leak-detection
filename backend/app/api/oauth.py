from urllib.parse import urlencode
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.api.deps import current_user
from app.core.config import settings
from app.core.oauth import pkce_pair
from app.db.session import get_db
from app.models.models import User
from app.services.audit import audit
from app.services.social import mastodon_exchange, mastodon_me, save_account

router = APIRouter(prefix="/oauth", tags=["oauth"])

@router.get("/mastodon/start")
async def mastodon_start(instance: str | None = None, user: User = Depends(current_user)):
    instance = (instance or settings.mastodon_instance).rstrip("/")
    if not settings.mastodon_client_id or not settings.mastodon_client_secret:
        raise HTTPException(503, "Mastodon OAuth is not configured")
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(32)
    params = {
        "response_type": "code",
        "client_id": settings.mastodon_client_id,
        "redirect_uri": settings.mastodon_redirect_uri,
        "scope": settings.mastodon_scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    url = f"{instance}/oauth/authorize?" + urlencode(params)
    out = RedirectResponse(url)
    for name, value in [
        ("oauth_state_mastodon", state),
        ("oauth_verifier_mastodon", verifier),
        ("oauth_user", user.id),
        ("oauth_instance", instance),
    ]:
        out.set_cookie(name, value, httponly=True, secure=settings.cookie_secure,
                       samesite="lax", max_age=600, path="/api/oauth")
    return out

@router.get("/mastodon/callback")
async def mastodon_callback(request: Request, db: Session = Depends(get_db)):
    q = request.query_params
    state, code = q.get("state"), q.get("code")
    if not state or state != request.cookies.get("oauth_state_mastodon"):
        raise HTTPException(400, "Invalid OAuth state")
    user_id = request.cookies.get("oauth_user")
    verifier = request.cookies.get("oauth_verifier_mastodon")
    instance = request.cookies.get("oauth_instance")
    if not all([user_id, verifier, instance, code]):
        raise HTTPException(400, "OAuth callback missing required data")
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(401, "OAuth user session expired")
    token = await mastodon_exchange(instance, code, verifier)
    profile = await mastodon_me(instance, token["access_token"])
    account = save_account(db, user.id, profile, token, instance)
    audit(db, user.id, "ACCOUNT_CONNECTED", "social_account", account.id,
          metadata={"platform": "mastodon", "instance": instance})
    db.commit()
    out = RedirectResponse(settings.frontend_origin + "/accounts?connected=mastodon")
    for name in ["oauth_state_mastodon", "oauth_verifier_mastodon", "oauth_user", "oauth_instance"]:
        out.delete_cookie(name, path="/api/oauth")
    return out
