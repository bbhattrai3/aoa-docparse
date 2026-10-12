from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
import httpx
from functools import lru_cache
from app.config import settings
from app.models.account import Account
from app.models.parish_member import ParishMember
from app.database import get_db
from sqlalchemy.orm import Session

security = HTTPBearer()

@lru_cache()
def get_signing_key():
    """Fetch Auth0 JWKS (cached)."""
    jwks_url = f"https://{settings.auth0_domain}/.well-known/jwks.json"
    response = httpx.get(jwks_url)
    return response.json()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Verify the Auth0 JWT and return the decoded payload."""
    token = credentials.credentials
    try:
        jwks = get_signing_key()
        unverified_header = jwt.get_unverified_header(token)

        rsa_key = {}
        for key in jwks["keys"]:
            if key["kid"] == unverified_header["kid"]:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }

        if not rsa_key:
            raise HTTPException(status_code=401, detail="Unable to find signing key")

        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=[settings.auth0_algorithms],
            audience=settings.auth0_api_audience,
            issuer=f"https://{settings.auth0_domain}/",
        )
        return payload

    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Token validation failed: {str(e)}")


def current_account(user=Depends(verify_token), db: Session = Depends(get_db)):
    sub = user.get("sub")
    email = (user.get("email") or "").strip().lower()
    if not sub:
        raise HTTPException(status_code=401, detail="Authenticated user ID is missing")
    identity = email or f"auth0:{sub}"
    account = db.query(Account).filter(Account.auth0_sub == sub).first()
    if account:
        return account
    pending = db.query(ParishMember).filter(
        ParishMember.email == email, ParishMember.account_id.is_(None)
    ).all() if email else []
    account = Account(auth0_sub=sub, email=identity, role="viewer" if pending else "admin")
    db.add(account)
    db.flush()
    for membership in pending:
        membership.account_id = account.id
        membership.invitation_token = None
    db.commit()
    db.refresh(account)
    return account


def require_admin_account(account=Depends(current_account)):
    if account.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access required")
    return account


def parish_access(parish_id: int, account=Depends(current_account), db: Session = Depends(get_db)):
    member = db.query(ParishMember).filter(
        ParishMember.parish_id == parish_id,
        ParishMember.account_id == account.id,
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Parish not found")
    return member


def parish_admin_access(parish_id: int, account=Depends(require_admin_account), db: Session = Depends(get_db)):
    member = db.query(ParishMember).filter(
        ParishMember.parish_id == parish_id,
        ParishMember.account_id == account.id,
        ParishMember.role == "admin",
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Parish not found")
    return member