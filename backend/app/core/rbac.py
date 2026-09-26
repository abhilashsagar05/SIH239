"""
Role-Based Access Control (RBAC) dependency guards for FastAPI routes.
Usage:
    @router.get("/admin-only")
    def admin_route(user = Depends(require_roles(["SUPER_ADMIN", "SCHEME_ADMIN"]))):
        ...
"""
from functools import wraps
from typing import Callable
from uuid import UUID

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Decode JWT and return the authenticated user from DB."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(credentials.credentials)
        user_id: str | None = payload.get("sub")
        token_type: str | None = payload.get("type")
        if user_id is None or token_type != "access":
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.id == UUID(user_id), User.is_active == True).first()
    if user is None:
        raise credentials_exception
    return user


async def get_current_active_verified_user(
    current_user: User = Depends(get_current_user),
) -> User:
    if not current_user.is_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please complete OTP verification.",
        )
    return current_user


def require_roles(allowed_roles: list[str]) -> Callable:
    """Factory that returns a FastAPI dependency enforcing role-based access."""

    async def _check_role(
        current_user: User = Depends(get_current_active_verified_user),
    ) -> User:
        if current_user.role.value not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {allowed_roles}",
            )
        return current_user

    return _check_role


# ── Pre-built role guards ────────────────────────────────────────────────────

def require_applicant():
    return require_roles(["APPLICANT", "REVIEWER", "SENIOR_REVIEWER", "SCHEME_ADMIN", "SUPER_ADMIN"])

def require_reviewer():
    return require_roles(["REVIEWER", "SENIOR_REVIEWER", "SCHEME_ADMIN", "SUPER_ADMIN"])

def require_senior_reviewer():
    return require_roles(["SENIOR_REVIEWER", "SCHEME_ADMIN", "SUPER_ADMIN"])

def require_scheme_admin():
    return require_roles(["SCHEME_ADMIN", "SUPER_ADMIN"])

def require_super_admin():
    return require_roles(["SUPER_ADMIN"])
