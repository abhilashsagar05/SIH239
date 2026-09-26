"""Pydantic schemas for Auth endpoints."""
from pydantic import BaseModel, Field, field_validator
import re


class OTPRequestSchema(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=15)
    purpose: str = Field(..., pattern="^(REGISTRATION|LOGIN|RESET)$")

    @field_validator("mobile")
    @classmethod
    def validate_mobile(cls, v: str) -> str:
        if not re.match(r"^\+?[0-9]{10,15}$", v):
            raise ValueError("Invalid mobile number format")
        return v


class OTPVerifySchema(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=4, max_length=8)
    purpose: str = Field(..., pattern="^(REGISTRATION|LOGIN|RESET)$")


class RegisterSchema(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=255)
    mobile: str = Field(..., min_length=10, max_length=15)
    email: str | None = None
    password: str = Field(..., min_length=8, max_length=128)
    otp: str = Field(..., min_length=4, max_length=8)


class LoginSchema(BaseModel):
    mobile: str = Field(..., min_length=10, max_length=15)
    otp: str = Field(..., min_length=4, max_length=8)


class TokenResponseSchema(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    full_name: str


class RefreshTokenSchema(BaseModel):
    refresh_token: str
