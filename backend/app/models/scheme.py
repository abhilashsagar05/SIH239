import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Text, Numeric, SmallInteger,
    Integer, Enum as SAEnum, func, ForeignKey, ARRAY
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import Gender


class DocumentType(str, enum.Enum):
    AADHAAR_CARD = "AADHAAR_CARD"
    CASTE_CERTIFICATE = "CASTE_CERTIFICATE"
    INCOME_CERTIFICATE = "INCOME_CERTIFICATE"
    MARKSHEET_10 = "MARKSHEET_10"
    MARKSHEET_12 = "MARKSHEET_12"
    MARKSHEET_UG = "MARKSHEET_UG"
    MARKSHEET_PG = "MARKSHEET_PG"
    ADMISSION_LETTER = "ADMISSION_LETTER"
    DOMICILE_CERTIFICATE = "DOMICILE_CERTIFICATE"
    BANK_PASSBOOK = "BANK_PASSBOOK"
    PASSPORT = "PASSPORT"
    PHOTOGRAPH = "PHOTOGRAPH"
    OTHER = "OTHER"


class Scheme(Base):
    __tablename__ = "schemes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    ministry = Column(String(255), default="Ministry of Tribal Affairs")
    is_active = Column(Boolean, nullable=False, default=False)
    application_open_date = Column(Date, nullable=False)
    application_close_date = Column(Date, nullable=False)
    academic_year = Column(String(9), nullable=False)

    # Eligibility
    min_age = Column(SmallInteger, nullable=True)
    max_age = Column(SmallInteger, nullable=True)
    max_annual_income = Column(Numeric(12, 2), nullable=True)
    eligible_categories = Column(ARRAY(Text), default=["ST"])
    eligible_states = Column(ARRAY(String(2)), nullable=True)
    min_percentage = Column(Numeric(5, 2), nullable=True)
    eligible_levels = Column(ARRAY(Text), nullable=True)
    eligible_institutions = Column(ARRAY(Text), nullable=True)

    # Documents
    required_documents = Column(ARRAY(Text), nullable=False, default=[])
    optional_documents = Column(ARRAY(Text), default=[])

    # Merit
    merit_weights = Column(JSONB, nullable=False, default={"academic_score": 0.7, "income_score": 0.3})
    total_seats = Column(Integer, nullable=True)
    female_quota_pct = Column(Numeric(5, 2), default=30.0)
    state_wise_quota = Column(JSONB, nullable=True)

    # Financial
    fellowship_amount = Column(Numeric(12, 2), nullable=True)
    contingency_amount = Column(Numeric(12, 2), nullable=True)
    duration_months = Column(SmallInteger, nullable=True)

    # AI
    ai_confidence_threshold = Column(Numeric(5, 2), default=75.0)

    # Audit
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    applications = relationship("Application", back_populates="scheme")
    merit_lists = relationship("MeritList", back_populates="scheme")
