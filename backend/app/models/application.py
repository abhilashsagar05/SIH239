import enum
import uuid
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Text, Numeric,
    SmallInteger, Integer, Enum as SAEnum, func, ForeignKey, CHAR, BigInteger
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.user import Gender


class ApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    AI_REVIEW = "AI_REVIEW"
    DEFICIENT = "DEFICIENT"
    MANUAL_SCRUTINY = "MANUAL_SCRUTINY"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    DISBURSED = "DISBURSED"


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    VERIFIED = "VERIFIED"
    FLAGGED = "FLAGGED"
    REJECTED = "REJECTED"


class DisbursementStatus(str, enum.Enum):
    PENDING = "PENDING"
    INITIATED = "INITIATED"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


# ── Valid State Transitions ──────────────────────────────────────────────────
VALID_TRANSITIONS: dict[ApplicationStatus, list[ApplicationStatus]] = {
    ApplicationStatus.DRAFT: [ApplicationStatus.SUBMITTED],
    ApplicationStatus.SUBMITTED: [ApplicationStatus.AI_REVIEW],
    ApplicationStatus.AI_REVIEW: [ApplicationStatus.DEFICIENT, ApplicationStatus.MANUAL_SCRUTINY],
    ApplicationStatus.DEFICIENT: [ApplicationStatus.SUBMITTED],
    ApplicationStatus.MANUAL_SCRUTINY: [ApplicationStatus.APPROVED, ApplicationStatus.REJECTED, ApplicationStatus.DEFICIENT],
    ApplicationStatus.APPROVED: [ApplicationStatus.DISBURSED],
    ApplicationStatus.REJECTED: [],
    ApplicationStatus.DISBURSED: [],
}


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    return target in VALID_TRANSITIONS.get(current, [])


class Application(Base):
    __tablename__ = "applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_number = Column(String(30), unique=True, nullable=False)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("schemes.id"), nullable=False)
    applicant_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    assigned_reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    status = Column(SAEnum(ApplicationStatus, name="application_status"), nullable=False, default=ApplicationStatus.DRAFT)
    academic_year = Column(String(9), nullable=False)

    # Personal snapshot
    applicant_name = Column(String(255), nullable=False)
    applicant_dob = Column(Date, nullable=False)
    applicant_gender = Column(SAEnum(Gender, name="gender"), nullable=False)
    state_code = Column(CHAR(2), nullable=False)
    district = Column(String(100), nullable=True)
    category = Column(String(10), nullable=False, default="ST")
    aadhaar_last4 = Column(CHAR(4), nullable=True)

    # Academic
    institution_name = Column(String(500), nullable=True)
    institution_state = Column(CHAR(2), nullable=True)
    course_name = Column(String(255), nullable=True)
    course_level = Column(String(50), nullable=True)
    admission_year = Column(SmallInteger, nullable=True)
    current_year = Column(SmallInteger, nullable=True)
    percentage_10 = Column(Numeric(5, 2), nullable=True)
    percentage_12 = Column(Numeric(5, 2), nullable=True)
    percentage_ug = Column(Numeric(5, 2), nullable=True)
    percentage_pg = Column(Numeric(5, 2), nullable=True)

    # Financial
    annual_family_income = Column(Numeric(12, 2), nullable=True)
    bank_account_number = Column(Text, nullable=True)  # encrypted
    bank_ifsc = Column(String(11), nullable=True)
    bank_name = Column(String(255), nullable=True)

    # AI
    overall_ai_score = Column(Numeric(5, 2), nullable=True)
    ai_processing_done = Column(Boolean, nullable=False, default=False)
    ai_flags = Column(JSONB, default=list)
    merit_score = Column(Numeric(8, 4), nullable=True)
    merit_rank = Column(Integer, nullable=True)

    # Timestamps
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    ai_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    manually_reviewed_at = Column(DateTime(timezone=True), nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)
    rejected_at = Column(DateTime(timezone=True), nullable=True)
    disbursed_at = Column(DateTime(timezone=True), nullable=True)

    rejection_reason = Column(Text, nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    deficiency_notes = Column(JSONB, default=list)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    scheme = relationship("Scheme", back_populates="applications")
    applicant = relationship("User", back_populates="applications", foreign_keys=[applicant_id])
    assigned_reviewer = relationship("User", back_populates="assigned_applications", foreign_keys=[assigned_reviewer_id])
    documents = relationship("Document", back_populates="application", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="application")
    disbursements = relationship("Disbursement", back_populates="application")


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False)
    uploader_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    document_type = Column(String(50), nullable=False)
    original_filename = Column(String(500), nullable=False)
    storage_key = Column(Text, unique=True, nullable=False)
    storage_bucket = Column(String(100), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    mime_type = Column(String(100), nullable=False)
    checksum_sha256 = Column(CHAR(64), nullable=False)
    status = Column(SAEnum(DocumentStatus, name="document_status"), nullable=False, default=DocumentStatus.PENDING)
    version = Column(SmallInteger, nullable=False, default=1)

    # AI
    extracted_text = Column(Text, nullable=True)
    extracted_fields = Column(JSONB, default=dict)
    confidence_score = Column(Numeric(5, 2), nullable=True)
    match_score = Column(Numeric(5, 2), nullable=True)
    ocr_engine = Column(String(50), nullable=True)
    ocr_processed_at = Column(DateTime(timezone=True), nullable=True)
    ai_flags = Column(JSONB, default=list)

    # Manual review
    reviewed_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewer_notes = Column(Text, nullable=True)
    is_tampered = Column(Boolean, default=False)
    is_blurry = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    application = relationship("Application", back_populates="documents")
    uploader = relationship("User", back_populates="documents", foreign_keys=[uploader_id])


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    actor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    actor_role = Column(String(50), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    old_value = Column(JSONB, nullable=True)
    new_value = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(Text, nullable=True)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    actor = relationship("User", back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    channel = Column(String(20), nullable=False)
    subject = Column(String(500), nullable=True)
    body = Column(Text, nullable=False)
    is_read = Column(Boolean, nullable=False, default=False)
    sent_at = Column(DateTime(timezone=True), nullable=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="notifications")
    application = relationship("Application", back_populates="notifications")


class Disbursement(Base):
    __tablename__ = "disbursements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id = Column(UUID(as_uuid=True), ForeignKey("applications.id"), nullable=False)
    amount = Column(Numeric(12, 2), nullable=False)
    disbursement_type = Column(String(50), nullable=False)
    status = Column(SAEnum(DisbursementStatus, name="disbursement_status"), nullable=False, default=DisbursementStatus.PENDING)
    pfms_transaction_id = Column(String(100), nullable=True)
    payment_date = Column(Date, nullable=True)
    utr_number = Column(String(50), nullable=True)
    bank_account_number = Column(Text, nullable=True)
    bank_ifsc = Column(String(11), nullable=True)
    initiated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    initiated_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    failure_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    application = relationship("Application", back_populates="disbursements")


class MeritList(Base):
    __tablename__ = "merit_lists"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scheme_id = Column(UUID(as_uuid=True), ForeignKey("schemes.id"), nullable=False)
    academic_year = Column(String(9), nullable=False)
    generated_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_final = Column(Boolean, nullable=False, default=False)
    total_applicants = Column(Integer, nullable=True)
    total_selected = Column(Integer, nullable=True)
    list_data = Column(JSONB, nullable=False, default=list)
    published_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(Text, nullable=True)

    scheme = relationship("Scheme", back_populates="merit_lists")
