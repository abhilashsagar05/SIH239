"""Pydantic schemas for Scheme (Rule Engine) endpoints."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, Field, model_validator
from typing import Any


class SchemeCreateSchema(BaseModel):
    code: str = Field(..., min_length=2, max_length=50, pattern="^[A-Z0-9_]+$")
    name: str = Field(..., min_length=5, max_length=255)
    description: str | None = None
    is_active: bool = False
    application_open_date: date
    application_close_date: date
    academic_year: str = Field(..., pattern=r"^\d{4}-\d{4}$")

    # Eligibility
    min_age: int | None = Field(None, ge=16, le=60)
    max_age: int | None = Field(None, ge=16, le=60)
    max_annual_income: Decimal | None = Field(None, ge=Decimal(0))
    eligible_categories: list[str] = ["ST"]
    eligible_states: list[str] | None = None
    min_percentage: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))
    eligible_levels: list[str] | None = None
    eligible_institutions: list[str] | None = None

    # Documents
    required_documents: list[str] = Field(..., min_length=1)
    optional_documents: list[str] = []

    # Merit
    merit_weights: dict[str, float] = Field(
        default={"academic_score": 0.7, "income_score": 0.3}
    )
    total_seats: int | None = Field(None, ge=1)
    female_quota_pct: Decimal = Field(default=Decimal("30.0"), ge=Decimal(0), le=Decimal(100))
    state_wise_quota: dict[str, int] | None = None

    # Financial
    fellowship_amount: Decimal | None = Field(None, ge=Decimal(0))
    contingency_amount: Decimal | None = Field(None, ge=Decimal(0))
    duration_months: int | None = Field(None, ge=1, le=60)

    # AI
    ai_confidence_threshold: Decimal = Field(default=Decimal("75.0"), ge=Decimal(0), le=Decimal(100))

    @model_validator(mode="after")
    def validate_dates_and_weights(self) -> "SchemeCreateSchema":
        if self.application_close_date <= self.application_open_date:
            raise ValueError("close_date must be after open_date")
        total_weight = sum(self.merit_weights.values())
        if abs(total_weight - 1.0) > 0.01:
            raise ValueError(f"merit_weights must sum to 1.0, got {total_weight:.3f}")
        if self.min_age and self.max_age and self.min_age >= self.max_age:
            raise ValueError("min_age must be less than max_age")
        return self


class SchemeUpdateSchema(BaseModel):
    name: str | None = None
    description: str | None = None
    is_active: bool | None = None
    application_open_date: date | None = None
    application_close_date: date | None = None
    max_annual_income: Decimal | None = None
    required_documents: list[str] | None = None
    optional_documents: list[str] | None = None
    merit_weights: dict[str, float] | None = None
    total_seats: int | None = None
    fellowship_amount: Decimal | None = None
    contingency_amount: Decimal | None = None
    ai_confidence_threshold: Decimal | None = None


class SchemeResponseSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    code: str
    name: str
    description: str | None
    ministry: str
    is_active: bool
    application_open_date: date
    application_close_date: date
    academic_year: str
    min_age: int | None
    max_age: int | None
    max_annual_income: Decimal | None
    eligible_categories: list[str]
    min_percentage: Decimal | None
    eligible_levels: list[str] | None
    required_documents: list[str]
    optional_documents: list[str]
    merit_weights: dict[str, Any]
    total_seats: int | None
    female_quota_pct: Decimal
    fellowship_amount: Decimal | None
    contingency_amount: Decimal | None
    duration_months: int | None
    ai_confidence_threshold: Decimal


class SchemeListResponseSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    code: str
    name: str
    is_active: bool
    application_open_date: date
    application_close_date: date
    academic_year: str
    total_seats: int | None
    fellowship_amount: Decimal | None
