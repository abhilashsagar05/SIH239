"""
Security helpers — JWT token management and password/OTP hashing.

Uses bcrypt directly (passlib is incompatible with bcrypt >= 4.x on Python 3.13).
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()


# ── Password / OTP hashing ────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Return a bcrypt-hashed password string."""
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def hash_otp(otp: str) -> str:
    """Return a bcrypt-hashed OTP (same algo, lower cost for speed)."""
    salt = bcrypt.gensalt(rounds=10)
    return bcrypt.hashpw(otp.encode("utf-8"), salt).decode("utf-8")


def verify_otp(plain: str, hashed: str) -> bool:
    """Verify a plaintext OTP against its bcrypt hash."""
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict[str, Any]) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises JWTError if invalid or expired."""
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
