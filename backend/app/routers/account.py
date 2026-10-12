import secrets
import smtplib
from email.message import EmailMessage
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
import re
from sqlalchemy.orm import Session
from app.auth import current_account, parish_admin_access, verify_token
from app.config import settings
from app.database import get_db
from app.models.account import Account
from app.models.parish_member import ParishMember

router = APIRouter()


class InviteRequest(BaseModel):
    email: str

    @field_validator("email")
    @classmethod
    def valid_email(cls, value: str) -> str:
        value = value.strip().lower()
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("A valid email address is required")
        return value


def send_invitation(email: str, parish_name: str, token: str):
    if not settings.smtp_host or not settings.smtp_from:
        raise HTTPException(status_code=503, detail="Email delivery is not configured")
    message = EmailMessage()
    message["Subject"] = f"Invitation to view {parish_name}"
    message["From"] = settings.smtp_from
    message["To"] = email
    message.set_content(
        f"You have been invited to view {parish_name}.\n\n"
        f"Create or sign in to your account here:\n"
        f"{settings.frontend_url}/invite/{token}\n"
    )
    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
            server.starttls()
            if settings.smtp_username:
                server.login(settings.smtp_username, settings.smtp_password)
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise HTTPException(status_code=502, detail=f"Invitation email could not be sent: {error}") from error


@router.get("/me")
def me(account=Depends(current_account)):
    return {"email": account.email, "role": account.role}


@router.post("/parishes/{parish_id}/viewers")
def invite_viewer(
    parish_id: int,
    data: InviteRequest,
    membership=Depends(parish_admin_access),
    db: Session = Depends(get_db),
):
    email = str(data.email).strip().lower()
    existing = db.query(ParishMember).filter(
        ParishMember.parish_id == parish_id, ParishMember.email == email
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="This email already has access or an invitation")
    token = secrets.token_urlsafe(32)
    member = ParishMember(
        parish_id=parish_id,
        email=email,
        role="viewer",
        invitation_token=token,
    )
    db.add(member)
    db.flush()
    send_invitation(email, membership.parish.name, token)
    db.commit()
    return {"detail": "Invitation sent"}


@router.get("/parishes/{parish_id}/viewers")
def list_viewers(
    parish_id: int,
    membership=Depends(parish_admin_access),
    db: Session = Depends(get_db),
):
    return db.query(ParishMember).filter(
        ParishMember.parish_id == parish_id, ParishMember.role == "viewer"
    ).all()


@router.delete("/parishes/{parish_id}/viewers/{member_id}")
def remove_viewer(
    parish_id: int,
    member_id: int,
    membership=Depends(parish_admin_access),
    db: Session = Depends(get_db),
):
    viewer = db.query(ParishMember).filter(
        ParishMember.id == member_id,
        ParishMember.parish_id == parish_id,
        ParishMember.role == "viewer",
    ).first()
    if not viewer:
        raise HTTPException(status_code=404, detail="Viewer not found")
    db.delete(viewer)
    db.commit()
    return {"detail": "Viewer removed"}


@router.post("/invitations/{token}/accept")
def accept_invitation(token: str, user=Depends(verify_token), db: Session = Depends(get_db)):
    member = db.query(ParishMember).filter(ParishMember.invitation_token == token).first()
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found or already accepted")
    email = (user.get("email") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="Viewer invitations require an authenticated email address")
    if email != member.email:
        raise HTTPException(status_code=403, detail="Sign in with the invited email address")
    account = db.query(Account).filter(Account.auth0_sub == user["sub"]).first()
    if not account:
        account = Account(auth0_sub=user["sub"], email=email, role="viewer")
        db.add(account)
        db.flush()
    elif account.email != email:
        raise HTTPException(status_code=403, detail="Authenticated email does not match invitation")
    account.role = "viewer"
    member.account_id = account.id
    member.invitation_token = None
    db.commit()
    return {"detail": "Invitation accepted", "parish_id": member.parish_id}
