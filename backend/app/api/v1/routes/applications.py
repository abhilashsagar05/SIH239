"""
Application Routes — Full lifecycle management with state machine enforcement.

Endpoints:
  POST   /applications                  — Create draft application
  GET    /applications                  — List (applicant: own | reviewer: assigned | admin: all)
  GET    /applications/{id}             — Get application detail
  PATCH  /applications/{id}             — Update (DRAFT only)
  POST   /applications/{id}/submit      — Submit application (DRAFT→SUBMITTED)
  PATCH  /applications/{id}/status      — Change status [REVIEWER+]
  POST   /applications/{id}/assign      — Assign reviewer [SCHEME_ADMIN+]
  GET    /applications/{id}/documents   — List documents for application
  GET    /applications/{id}/audit       — Audit trail
  GET    /applications/admin/dashboard  — Admin stats [REVIEWER+]
"""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status, Request
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import (
    get_current_active_verified_user,
    require_reviewer, require_scheme_admin
)
from app.models import (
    User, Scheme, Application, Document, AuditLog, Notification,
    ApplicationStatus, can_transition
)
from app.schemas.application import (
    ApplicationCreateSchema, ApplicationUpdateSchema, StatusUpdateSchema,
    ReviewerAssignSchema, ApplicationResponseSchema, ApplicationListItemSchema,
    DocumentResponseSchema, AdminDashboardStatsSchema
)

router = APIRouter(prefix="/applications", tags=["Applications"])


def _generate_app_number(db: Session, scheme_code: str, year: str) -> str:
    result = db.execute(
        text("SELECT generate_application_number(:code, :year)"),
        {"code": scheme_code, "year": year}
    ).scalar()
    return str(result) if result else ""


def _audit(db, action, entity_id, actor: User, old=None, new=None, ip=None):
    db.add(AuditLog(
        actor_id=actor.id, actor_role=actor.role.value,
        action=action, entity_type="APPLICATION", entity_id=entity_id,
        old_value=old, new_value=new, ip_address=ip,
    ))


def _notify(db, user_id, app_id, body, channel="IN_APP", subject=None):
    db.add(Notification(
        user_id=user_id, application_id=app_id,
        channel=channel, subject=subject, body=body,
    ))


# ── POST /applications ────────────────────────────────────────────────────────
@router.post("", response_model=ApplicationResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_application(
    payload: ApplicationCreateSchema,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    # Only APPLICANT role can submit own applications
    if current_user.role.value not in ["APPLICANT"]:
        raise HTTPException(status_code=403, detail="Only applicants can create applications.")

    # Check scheme exists and is open
    scheme = db.query(Scheme).filter(Scheme.id == payload.scheme_id, Scheme.is_active == True).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found or not active.")

    from datetime import date
    today = date.today()
    if not (scheme.application_open_date <= today <= scheme.application_close_date):
        raise HTTPException(status_code=400, detail="Scheme is not currently accepting applications.")

    # Check duplicate
    existing = db.query(Application).filter(
        Application.scheme_id == payload.scheme_id,
        Application.applicant_id == current_user.id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="You have already applied to this scheme.")

    # Determine academic year from scheme
    academic_year = str(scheme.academic_year)
    app_number = _generate_app_number(db, str(scheme.code), academic_year.split("-")[0])

    application = Application(
        application_number=app_number,
        scheme_id=payload.scheme_id,
        applicant_id=current_user.id,
        academic_year=academic_year,
        status=ApplicationStatus.DRAFT,
        **payload.model_dump(exclude={"scheme_id"}),
    )
    db.add(application)
    db.flush()

    _audit(db, "APPLICATION_CREATED", application.id, current_user,
           new={"status": "DRAFT", "scheme": scheme.code},
           ip=request.client.host if request.client else None)
    db.commit()
    db.refresh(application)
    return application


# ── GET /applications ─────────────────────────────────────────────────────────
@router.get("", response_model=list[ApplicationListItemSchema])
async def list_applications(
    status_filter: str | None = Query(None),
    scheme_id: UUID | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    query = db.query(Application)

    if current_user.role.value == "APPLICANT":
        query = query.filter(Application.applicant_id == current_user.id)
    elif current_user.role.value == "REVIEWER":
        query = query.filter(Application.assigned_reviewer_id == current_user.id)
    # SENIOR_REVIEWER, SCHEME_ADMIN, SUPER_ADMIN: see all

    if status_filter:
        query = query.filter(Application.status == ApplicationStatus(status_filter))
    if scheme_id:
        query = query.filter(Application.scheme_id == scheme_id)

    total = query.count()
    apps = query.order_by(Application.updated_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return apps


# ── GET /applications/admin/dashboard ─────────────────────────────────────────
@router.get("/admin/dashboard", response_model=AdminDashboardStatsSchema)
async def admin_dashboard(
    scheme_id: UUID | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer()),
):
    base = db.query(Application)
    if scheme_id:
        base = base.filter(Application.scheme_id == scheme_id)

    total = base.count()

    status_counts = dict(
        base.with_entities(Application.status, func.count(Application.id))
        .group_by(Application.status).all()
    )
    state_counts = dict(
        base.with_entities(Application.state_code, func.count(Application.id))
        .group_by(Application.state_code).all()
    )
    gender_counts = dict(
        base.with_entities(Application.applicant_gender, func.count(Application.id))
        .group_by(Application.applicant_gender).all()
    )
    scheme_counts = {}
    scheme_rows = (
        db.query(Application.scheme_id, func.count(Application.id))
        .group_by(Application.scheme_id).all()
    )
    for row in scheme_rows:
        s = db.query(Scheme).filter(Scheme.id == row[0]).first()
        scheme_counts[s.code if s else str(row[0])] = row[1]

    avg_score = base.with_entities(func.avg(Application.overall_ai_score)).scalar()

    pending = base.filter(Application.status == ApplicationStatus.MANUAL_SCRUTINY).count()
    flagged = base.filter(Application.ai_flags.isnot(None)).filter(
        func.jsonb_array_length(Application.ai_flags) > 0
    ).count()

    return AdminDashboardStatsSchema(
        total_applications=total,
        by_status={k.value if hasattr(k, "value") else str(k): v for k, v in status_counts.items()},
        by_state={str(k): v for k, v in state_counts.items()},
        by_gender={str(k): v for k, v in gender_counts.items()},
        by_scheme=scheme_counts,
        avg_ai_score=round(float(avg_score), 2) if avg_score else None,
        pending_review=pending,
        flagged_by_ai=flagged,
    )


# ── GET /applications/{id} ────────────────────────────────────────────────────
@router.get("/{app_id}", response_model=ApplicationResponseSchema)
async def get_application(
    app_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    # Applicants can only see their own
    if current_user.role.value == "APPLICANT" and app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")
    # Reviewers can only see assigned
    if current_user.role.value == "REVIEWER" and app.assigned_reviewer_id != current_user.id:
        raise HTTPException(status_code=403, detail="Application not assigned to you.")

    return app


# ── PATCH /applications/{id} ─────────────────────────────────────────────────
@router.patch("/{app_id}", response_model=ApplicationResponseSchema)
async def update_application(
    app_id: UUID,
    payload: ApplicationUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    app = db.query(Application).filter(
        Application.id == app_id, Application.applicant_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app.status != ApplicationStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only DRAFT applications can be edited.")

    update_data = payload.model_dump(exclude_unset=True)
    for k, v in update_data.items():
        setattr(app, k, v)

    _audit(db, "APPLICATION_UPDATED", app.id, current_user, new=update_data)
    db.commit()
    db.refresh(app)
    return app


# ── POST /applications/{id}/submit ────────────────────────────────────────────
@router.post("/{app_id}/submit", response_model=ApplicationResponseSchema)
async def submit_application(
    app_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    app = db.query(Application).filter(
        Application.id == app_id, Application.applicant_id == current_user.id
    ).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if app.status not in [ApplicationStatus.DRAFT, ApplicationStatus.DEFICIENT]:
        raise HTTPException(status_code=400, detail=f"Cannot submit from status '{app.status.value}'.")

    # Check required documents uploaded
    scheme = db.query(Scheme).filter(Scheme.id == app.scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    uploaded_types = {d.document_type for d in app.documents if d.status.value != "REJECTED"}
    required = set(scheme.required_documents or [])  # type: ignore
    missing = required - uploaded_types
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required documents: {', '.join(missing)}"
        )

    old_status = app.status.value
    app.status = ApplicationStatus.SUBMITTED  # type: ignore
    app.submitted_at = datetime.now(timezone.utc)  # type: ignore

    _audit(db, "APPLICATION_SUBMITTED", app.id, current_user,
           old={"status": old_status}, new={"status": "SUBMITTED"},
           ip=request.client.host if request.client else None)
    _notify(db, current_user.id, app.id,
            f"Your application {app.application_number} has been submitted successfully.")

    db.commit()

    # Dispatch AI processing task (async)
    try:
        from app.tasks.ocr_task import process_application_documents
        process_application_documents.delay(str(app.id))
    except Exception:
        pass  # Celery not running in dev is OK

    db.refresh(app)
    return app


# ── PATCH /applications/{id}/status ──────────────────────────────────────────
@router.patch("/{app_id}/status", response_model=ApplicationResponseSchema)
async def update_status(
    app_id: UUID,
    payload: StatusUpdateSchema,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer()),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    try:
        new_status = ApplicationStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {payload.status}")

    if not can_transition(ApplicationStatus(app.status), new_status):  # type: ignore
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: {app.status.value} → {new_status.value}"  # type: ignore
        )

    old_status = str(app.status.value)  # type: ignore
    app.status = new_status  # type: ignore
    now = datetime.now(timezone.utc)

    # Set timestamp fields
    ts_map = {
        ApplicationStatus.APPROVED: "approved_at",
        ApplicationStatus.REJECTED: "rejected_at",
        ApplicationStatus.DISBURSED: "disbursed_at",
    }
    if ts_field := ts_map.get(new_status):
        setattr(app, ts_field, now)

    if new_status in [ApplicationStatus.MANUAL_SCRUTINY, ApplicationStatus.APPROVED, ApplicationStatus.REJECTED]:
        app.manually_reviewed_at = now  # type: ignore

    if payload.rejection_reason:
        app.rejection_reason = payload.rejection_reason  # type: ignore
    if payload.reviewer_notes:
        app.reviewer_notes = payload.reviewer_notes  # type: ignore
    if payload.deficiency_notes:
        app.deficiency_notes = payload.deficiency_notes  # type: ignore

    _audit(db, f"STATUS_CHANGED_TO_{new_status.value}", app.id, current_user,
           old={"status": old_status}, new={"status": new_status.value},
           ip=request.client.host if request.client else None)

    # Notify applicant
    msg_map = {
        ApplicationStatus.APPROVED: f"Congratulations! Your application {app.application_number} has been APPROVED.",
        ApplicationStatus.REJECTED: f"Your application {app.application_number} was not approved. Reason: {payload.rejection_reason or 'N/A'}",
        ApplicationStatus.DEFICIENT: f"Your application {app.application_number} requires additional documents. Please check the Deficiency section.",
    }
    if msg := msg_map.get(new_status):
        _notify(db, app.applicant_id, app.id, msg)

    db.commit()
    db.refresh(app)
    return app


# ── POST /applications/{id}/assign ────────────────────────────────────────────
@router.post("/{app_id}/assign", response_model=ApplicationResponseSchema)
async def assign_reviewer(
    app_id: UUID,
    payload: ReviewerAssignSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")

    reviewer = db.query(User).filter(
        User.id == payload.reviewer_id,
        User.role.in_([UserRole.REVIEWER, UserRole.SENIOR_REVIEWER]),
        User.is_active == True,
    ).first()
    if not reviewer:
        raise HTTPException(status_code=404, detail="Reviewer not found.")

    app.assigned_reviewer_id = payload.reviewer_id  # type: ignore
    _audit(db, "REVIEWER_ASSIGNED", app.id, current_user,
           new={"reviewer_id": str(payload.reviewer_id)})
    db.commit()
    db.refresh(app)
    return app


# ── GET /applications/{id}/documents ─────────────────────────────────────────
@router.get("/{app_id}/documents", response_model=list[DocumentResponseSchema])
async def get_application_documents(
    app_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_verified_user),
):
    app = db.query(Application).filter(Application.id == app_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found.")
    if current_user.role.value == "APPLICANT" and app.applicant_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied.")

    return app.documents


# ── GET /applications/{id}/audit ──────────────────────────────────────────────
@router.get("/{app_id}/audit")
async def get_audit_trail(
    app_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_reviewer()),
):
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == "APPLICATION", AuditLog.entity_id == app_id)
        .order_by(AuditLog.created_at.asc())
        .all()
    )
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor_id": str(log.actor_id) if log.actor_id else None,
            "actor_role": log.actor_role,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "created_at": log.created_at,
        }
        for log in logs
    ]


# fix missing import
from app.models.user import UserRole
