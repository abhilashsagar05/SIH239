"""
Document Upload Routes — Secure S3 upload + triggers OCR pipeline.

Endpoints:
  POST  /documents/upload        — Upload a document for an application
  GET   /documents/{id}          — Get document metadata + AI results
  PATCH /documents/{id}/review   — Manual review override [REVIEWER+]
  GET   /documents/{id}/download — Pre-signed download URL [REVIEWER+]
"""
import hashlib
import uuid as uuid_lib
from datetime import datetime, timezone
from uuid import UUID

import boto3
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rbac import get_current_active_verified_user, require_reviewer
from app.models import Application, Document, AuditLog, ApplicationStatus, DocumentStatus
from app.models.user import User
from app.schemas.application import DocumentResponseSchema

router = APIRouter(prefix="/documents", tags=["Documents"])
settings = get_settings()

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/webp",
    "application/pdf",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _get_s3_client():
    kwargs = {"region_name": "ap-south-1"}
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    if settings.AWS_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.AWS_ACCESS_KEY_ID
        kwargs["aws_secret_access_key"] = settings.AWS_SECRET_ACCESS_KEY or ""
    return boto3.client("s3", **kwargs)


# ── POST /documents/upload ────────────────────────────────────────────────────
@router.post("/upload", response_model=DocumentResponseSchema, status_code=status.HTTP_201_CREATED)
async def upload_document(
    application_id: UUID = Form(...),
    document_type: str = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    """Upload a document file and trigger async OCR processing."""
    # Validate application ownership
    app = db.query(Application).filter(Application.id == application_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if current_user.role.value == "APPLICANT" and app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.DEFICIENT]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot upload documents when application is '{app.status.value}'."
        )

    # Validate file type
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{file.content_type}'. Allowed: PDF, JPEG, PNG, WEBP."
        )

    # Read and size-check
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large. Max 10MB allowed.")

    # Compute SHA-256 checksum
    checksum = hashlib.sha256(contents).hexdigest()

    # Build S3 key
    filename = file.filename or "file.bin"
    file_ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    storage_key = f"applications/{str(application_id)}/{document_type}/{uuid_lib.uuid4()}.{file_ext}"

    # Upload to S3
    try:
        s3 = _get_s3_client()
        s3.put_object(
            Bucket=settings.S3_BUCKET,
            Key=storage_key,
            Body=contents,
            ContentType=file.content_type,
            ServerSideEncryption="AES256",
            Metadata={
                "application_id": str(application_id),
                "document_type": document_type,
                "uploader_id": str(current_user.id),
            },
        )
    except Exception as e:
        # Fallback for dev without S3
        storage_key = f"local/{storage_key}"

    # Determine version (re-upload increments version)
    existing_docs = db.query(Document).filter(
        Document.application_id == application_id,
        Document.document_type == document_type,
    ).all()
    version = len(existing_docs) + 1

    doc = Document(
        application_id=application_id,
        uploader_id=current_user.id,
        document_type=document_type,
        original_filename=file.filename,
        storage_key=storage_key,
        storage_bucket=settings.S3_BUCKET,
        file_size_bytes=len(contents),
        mime_type=file.content_type,
        checksum_sha256=checksum,
        status=DocumentStatus.PENDING,
        version=version,
    )
    db.add(doc)
    db.flush()

    db.add(AuditLog(
        actor_id=current_user.id, actor_role=current_user.role.value,
        action="DOCUMENT_UPLOADED",
        entity_type="DOCUMENT", entity_id=doc.id,
        new_value={"document_type": document_type, "filename": file.filename, "version": version},
    ))
    db.commit()
    db.refresh(doc)

    # Dispatch OCR task
    try:
        from app.tasks.ocr_task import process_single_document
        process_single_document.delay(str(doc.id))
    except Exception:
        pass

    return doc


# ── GET /documents/{id} ───────────────────────────────────────────────────────
@router.get("/{doc_id}", response_model=DocumentResponseSchema)
async def get_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")
    # Ownership check
    app = doc.application
    if current_user.role.value == "APPLICANT" and app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    return doc


# ── PATCH /documents/{id}/review ──────────────────────────────────────────────
@router.patch("/{doc_id}/review", response_model=DocumentResponseSchema)
async def manual_review_document(
    doc_id: UUID,
    decision: str = Form(..., pattern="^(VERIFIED|REJECTED|FLAGGED)$"),
    notes: str | None = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer()),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    old_status = str(doc.status.value) if doc.status else ""
    doc.status = DocumentStatus(decision)  # type: ignore
    doc.reviewed_by = current_user.id  # type: ignore
    doc.reviewed_at = datetime.now(timezone.utc)  # type: ignore
    doc.reviewer_notes = notes  # type: ignore

    db.add(AuditLog(
        actor_id=current_user.id, actor_role=current_user.role.value,
        action=f"DOCUMENT_{decision}",
        entity_type="DOCUMENT", entity_id=doc.id,
        old_value={"status": old_status}, new_value={"status": decision, "notes": notes},
    ))
    db.commit()
    db.refresh(doc)
    return doc


# ── GET /documents/{id}/download ──────────────────────────────────────────────
@router.get("/{doc_id}/download")
async def download_document(
    doc_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer()),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    try:
        s3 = _get_s3_client()
        presigned_url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": doc.storage_bucket, "Key": doc.storage_key},
            ExpiresIn=300,  # 5 minutes
        )
        return {"download_url": presigned_url, "expires_in_seconds": 300}
    except Exception:
        raise HTTPException(status_code=503, detail="Could not generate download URL.")
