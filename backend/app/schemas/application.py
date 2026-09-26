"""Pydantic schemas for Application and Document endpoints."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID
from typing import Any
from pydantic import BaseModel, Field


class ApplicationCreateSchema(BaseModel):
    scheme_id: UUID

    # Personal
    applicant_name: str = Field(..., min_length=2, max_length=255)
    applicant_dob: date
    applicant_gender: str
    state_code: str = Field(..., min_length=2, max_length=2)
    district: str | None = None
    category: str = "ST"
    aadhaar_last4: str | None = Field(None, min_length=4, max_length=4, pattern="^[0-9]{4}$")

    # Academic
    institution_name: str | None = None
    institution_state: str | None = Field(None, min_length=2, max_length=2)
    course_name: str | None = None
    course_level: str | None = None
    admission_year: int | None = Field(None, ge=2000, le=2030)
    current_year: int | None = Field(None, ge=1, le=6)
    percentage_10: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))
    percentage_12: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))
    percentage_ug: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))
    percentage_pg: Decimal | None = Field(None, ge=Decimal(0), le=Decimal(100))

    # Financial
    annual_family_income: Decimal | None = Field(None, ge=Decimal(0))
    bank_account_number: str | None = None
    bank_ifsc: str | None = Field(None, max_length=11)
    bank_name: str | None = None


class ApplicationUpdateSchema(BaseModel):
    """Allowed only in DRAFT status."""
    applicant_name: str | None = None
    applicant_dob: date | None = None
    applicant_gender: str | None = None
    institution_name: str | None = None
    course_name: str | None = None
    course_level: str | None = None
    percentage_10: Decimal | None = None
    percentage_12: Decimal | None = None
    percentage_ug: Decimal | None = None
    percentage_pg: Decimal | None = None
    annual_family_income: Decimal | None = None
    bank_account_number: str | None = None
    bank_ifsc: str | None = None
    bank_name: str | None = None


class StatusUpdateSchema(BaseModel):
    """Admin/Reviewer status transition."""
    status: str
    rejection_reason: str | None = None
    reviewer_notes: str | None = None
    deficiency_notes: list[dict[str, str]] | None = None


class ReviewerAssignSchema(BaseModel):
    reviewer_id: UUID


class ApplicationResponseSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    application_number: str
    scheme_id: UUID
    applicant_id: UUID
    status: str
    academic_year: str
    applicant_name: str
    applicant_dob: date
    applicant_gender: str
    state_code: str
    district: str | None
    category: str
    institution_name: str | None
    course_name: str | None
    course_level: str | None
    percentage_10: Decimal | None
    percentage_12: Decimal | None
    percentage_ug: Decimal | None
    percentage_pg: Decimal | None
    annual_family_income: Decimal | None
    bank_ifsc: str | None
    bank_name: str | None
    overall_ai_score: Decimal | None
    ai_processing_done: bool
    ai_flags: list[Any]
    merit_score: Decimal | None
    merit_rank: int | None
    submitted_at: datetime | None
    ai_reviewed_at: datetime | None
    approved_at: datetime | None
    rejection_reason: str | None
    deficiency_notes: list[Any]
    created_at: datetime
    updated_at: datetime


class ApplicationListItemSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    application_number: str
    status: str
    applicant_name: str
    state_code: str
    course_level: str | None
    overall_ai_score: Decimal | None
    merit_rank: int | None
    submitted_at: datetime | None
    updated_at: datetime


class DocumentResponseSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    application_id: UUID
    document_type: str
    original_filename: str
    file_size_bytes: int
    mime_type: str
    status: str
    version: int
    confidence_score: Decimal | None
    match_score: Decimal | None
    ai_flags: list[Any]
    is_tampered: bool | None
    is_blurry: bool | None
    ocr_processed_at: datetime | None
    created_at: datetime


class MeritListResponseSchema(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    scheme_id: UUID
    academic_year: str
    is_final: bool
    total_applicants: int | None
    total_selected: int | None
    list_data: list[Any]
    generated_at: datetime
    published_at: datetime | None


class AdminDashboardStatsSchema(BaseModel):
    total_applications: int
    by_status: dict[str, int]
    by_state: dict[str, int]
    by_gender: dict[str, int]
    by_scheme: dict[str, int]
    avg_ai_score: float | None
    pending_review: int
    flagged_by_ai: int
