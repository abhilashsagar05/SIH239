"""
Auth Routes — OTP-based registration & login + JWT token management.

Endpoints:
  POST /auth/otp/request   — Send OTP to mobile
  POST /auth/register      — Register new applicant with OTP verification
  POST /auth/login         — OTP-based login → returns JWT pair
  POST /auth/refresh        — Refresh access token
  GET  /auth/me            — Get current user profile
  PATCH /auth/me           — Update profile
"""
import random
import string
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from jose import JWTError

from app.core.database import get_db
from app.core.security import (
    hash_password, verify_password, hash_otp, verify_otp,
    create_access_token, create_refresh_token, decode_token
)
from app.core.rbac import get_current_active_verified_user
from app.models import User, UserRole, AuditLog
from app.schemas.auth import (
    OTPRequestSchema, OTPVerifySchema, RegisterSchema,
    LoginSchema, TokenResponseSchema, RefreshTokenSchema
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

OTP_EXPIRY_MINUTES = 10
MAX_OTP_ATTEMPTS = 3


def _generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))


def _log_audit(
    db: Session, action: str, entity_type: str, entity_id: UUID,
    actor_id: UUID | None = None, actor_role: str | None = None,
    old_val=None, new_val=None, ip: str | None = None
) -> None:
    db.add(AuditLog(
        actor_id=actor_id,
        actor_role=actor_role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_val,
        new_value=new_val,
        ip_address=ip,
    ))


# ── POST /auth/otp/request ───────────────────────────────────────────────────
@router.post("/otp/request", status_code=status.HTTP_200_OK)
async def request_otp(
    payload: OTPRequestSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """Generate and send a 6-digit OTP to the provided mobile number."""
    from app.models.application import AuditLog  # noqa: avoid circular at top

    # Rate limit: check existing unexpired OTPs
    from sqlalchemy import text
    recent = db.execute(
        text("""
            SELECT COUNT(*) FROM otp_verifications
            WHERE mobile = :mobile AND purpose = :purpose
              AND expires_at > NOW() AND is_used = FALSE
        """),
        {"mobile": payload.mobile, "purpose": payload.purpose}
    ).scalar()

    if (recent or 0) >= 3:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many OTP requests. Please wait before requesting again.",
        )

    otp = _generate_otp()
    otp_hash = hash_otp(otp)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=OTP_EXPIRY_MINUTES)

    db.execute(
        text("""
            INSERT INTO otp_verifications (mobile, otp_hash, purpose, expires_at)
            VALUES (:mobile, :otp_hash, :purpose, :expires_at)
        """),
        {"mobile": payload.mobile, "otp_hash": otp_hash,
         "purpose": payload.purpose, "expires_at": expires_at}
    )
    db.commit()

    # In production: dispatch to SMS gateway; in dev: return in response
    response_data: dict = {"message": f"OTP sent to {payload.mobile}"}
    if True:  # settings.ENVIRONMENT == "development"
        response_data["otp_dev_only"] = otp  # REMOVE IN PRODUCTION

    return response_data


# ── POST /auth/register ──────────────────────────────────────────────────────
@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponseSchema)
async def register(
    payload: RegisterSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """Register a new applicant after verifying OTP."""
    # Check mobile not already registered
    existing = db.query(User).filter(User.mobile == payload.mobile).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Mobile number is already registered.",
        )

    # Verify OTP
    from sqlalchemy import text
    otp_record = db.execute(
        text("""
            SELECT id, otp_hash, attempts FROM otp_verifications
            WHERE mobile = :mobile AND purpose = 'REGISTRATION'
              AND expires_at > NOW() AND is_used = FALSE
            ORDER BY created_at DESC LIMIT 1
        """),
        {"mobile": payload.mobile}
    ).mappings().fetchone()

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid OTP found.")

    if otp_record["attempts"] >= MAX_OTP_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP locked. Request a new one.")

    if not verify_otp(payload.otp, otp_record["otp_hash"]):
        db.execute(
            text("UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = :id"),
            {"id": otp_record["id"]}
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    # Mark OTP used
    db.execute(
        text("UPDATE otp_verifications SET is_used = TRUE WHERE id = :id"),
        {"id": otp_record["id"]}
    )

    # Create user
    new_user = User(
        full_name=payload.full_name,
        mobile=payload.mobile,
        email=payload.email,
        password_hash=hash_password(payload.password) if payload.password else None,
        role=UserRole.APPLICANT,
        is_active=True,
        is_verified=True,
    )
    db.add(new_user)
    db.flush()  # get ID before commit

    _log_audit(db, "USER_REGISTERED", "USER", new_user.id,  # type: ignore
               ip=request.client.host if request.client else None)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token({"sub": str(new_user.id), "role": new_user.role.value})
    refresh_token = create_refresh_token({"sub": str(new_user.id)})

    return TokenResponseSchema(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(new_user.id),
        role=new_user.role.value,
        full_name=str(new_user.full_name) if new_user.full_name else "",
    )


# ── POST /auth/login ─────────────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponseSchema)
async def login(
    payload: LoginSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    """OTP-based passwordless login."""
    user = db.query(User).filter(
        User.mobile == payload.mobile, User.is_active == True
    ).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found.")

    from sqlalchemy import text
    otp_record = db.execute(
        text("""
            SELECT id, otp_hash, attempts FROM otp_verifications
            WHERE mobile = :mobile AND purpose = 'LOGIN'
              AND expires_at > NOW() AND is_used = FALSE
            ORDER BY created_at DESC LIMIT 1
        """),
        {"mobile": payload.mobile}
    ).mappings().fetchone()

    if not otp_record:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid OTP found.")

    if otp_record["attempts"] >= MAX_OTP_ATTEMPTS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OTP locked.")

    if not verify_otp(payload.otp, otp_record["otp_hash"]):
        db.execute(
            text("UPDATE otp_verifications SET attempts = attempts + 1 WHERE id = :id"),
            {"id": otp_record["id"]}
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OTP.")

    db.execute(
        text("UPDATE otp_verifications SET is_used = TRUE WHERE id = :id"),
        {"id": otp_record["id"]}
    )

    user.last_login_at = datetime.now(timezone.utc)  # type: ignore
    _log_audit(db, "USER_LOGIN", "USER", user.id,  # type: ignore
               actor_id=user.id, actor_role=user.role.value,  # type: ignore
               ip=request.client.host if request.client else None)
    db.commit()

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    return TokenResponseSchema(
        access_token=access_token,
        refresh_token=refresh_token,
        user_id=str(user.id),
        role=user.role.value,
        full_name=str(user.full_name) if user.full_name else "",
    )


# ── POST /auth/refresh ───────────────────────────────────────────────────────
@router.post("/refresh", response_model=TokenResponseSchema)
async def refresh_token(payload: RefreshTokenSchema, db: Session = Depends(get_db)):
    try:
        data = decode_token(payload.refresh_token)
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type.")
        user_id = data.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token.")

    user = db.query(User).filter(User.id == UUID(user_id), User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    access_token = create_access_token({"sub": str(user.id), "role": user.role.value})
    new_refresh = create_refresh_token({"sub": str(user.id)})
    return TokenResponseSchema(
        access_token=access_token,
        refresh_token=new_refresh,
        user_id=str(user.id),
        role=user.role.value,
        full_name=user.full_name,
    )


# ── GET /auth/me ─────────────────────────────────────────────────────────────
@router.get("/me")
async def get_me(current_user: User = Depends(get_current_active_verified_user)):
    return {
        "id": str(current_user.id),
        "full_name": current_user.full_name,
        "email": current_user.email,
        "mobile": current_user.mobile,
        "role": current_user.role.value,
        "is_verified": current_user.is_verified,
        "date_of_birth": current_user.date_of_birth,
        "gender": current_user.gender,
        "state_code": current_user.state_code,
        "district": current_user.district,
        "pincode": current_user.pincode,
        "last_login_at": current_user.last_login_at,
        "created_at": current_user.created_at,
    }
