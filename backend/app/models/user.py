import enum
import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Boolean, DateTime, Date, Text, Enum as SAEnum,
    func, ForeignKey, CHAR
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base


class UserRole(str, enum.Enum):
    APPLICANT = "APPLICANT"
    REVIEWER = "REVIEWER"
    SENIOR_REVIEWER = "SENIOR_REVIEWER"
    SCHEME_ADMIN = "SCHEME_ADMIN"
    SUPER_ADMIN = "SUPER_ADMIN"


class Gender(str, enum.Enum):
    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    PREFER_NOT_TO_SAY = "PREFER_NOT_TO_SAY"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=True)
    mobile = Column(String(15), unique=True, nullable=False)
    password_hash = Column(Text, nullable=True)
    role = Column(SAEnum(UserRole, name="user_role"), nullable=False, default=UserRole.APPLICANT)
    is_active = Column(Boolean, nullable=False, default=True)
    is_verified = Column(Boolean, nullable=False, default=False)
    aadhaar_hash = Column(Text, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    gender = Column(SAEnum(Gender, name="gender"), nullable=True)
    state_code = Column(CHAR(2), nullable=True)
    district = Column(String(100), nullable=True)
    address_line1 = Column(Text, nullable=True)
    address_line2 = Column(Text, nullable=True)
    pincode = Column(CHAR(6), nullable=True)
    profile_photo_url = Column(Text, nullable=True)
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    applications = relationship("Application", back_populates="applicant", foreign_keys="Application.applicant_id")
    assigned_applications = relationship("Application", back_populates="assigned_reviewer", foreign_keys="Application.assigned_reviewer_id")
    documents = relationship("Document", back_populates="uploader", foreign_keys="Document.uploader_id")
    notifications = relationship("Notification", back_populates="user")
    audit_logs = relationship("AuditLog", back_populates="actor")
