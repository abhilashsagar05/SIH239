"""
Scheme Configurator Routes — Admin rule-engine for scholarship schemes.

Endpoints:
  GET    /schemes               — List all schemes (public: active only)
  GET    /schemes/{id}          — Get scheme detail
  POST   /schemes               — Create scheme [SCHEME_ADMIN+]
  PATCH  /schemes/{id}          — Update scheme [SCHEME_ADMIN+]
  DELETE /schemes/{id}          — Soft-deactivate scheme [SUPER_ADMIN]
  GET    /schemes/{id}/stats    — Application count stats per scheme
"""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.database import get_db
from app.core.rbac import get_current_active_verified_user, require_scheme_admin, require_super_admin
from app.models import User, Scheme, Application, AuditLog
from app.schemas.scheme import (
    SchemeCreateSchema, SchemeUpdateSchema,
    SchemeResponseSchema, SchemeListResponseSchema
)

router = APIRouter(prefix="/schemes", tags=["Scheme Configurator"])


# ── GET /schemes ─────────────────────────────────────────────────────────────
@router.get("", response_model=list[SchemeListResponseSchema])
async def list_schemes(
    active_only: bool = Query(True),
    db: Session = Depends(get_db),
):
    query = db.query(Scheme)
    if active_only:
        query = query.filter(Scheme.is_active == True)
    return query.order_by(Scheme.application_close_date.desc()).all()


# ── GET /schemes/{id} ────────────────────────────────────────────────────────
@router.get("/{scheme_id}", response_model=SchemeResponseSchema)
async def get_scheme(scheme_id: UUID, db: Session = Depends(get_db)):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    return scheme


# ── POST /schemes ─────────────────────────────────────────────────────────────
@router.post("", response_model=SchemeResponseSchema, status_code=status.HTTP_201_CREATED)
async def create_scheme(
    payload: SchemeCreateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    existing = db.query(Scheme).filter(Scheme.code == payload.code).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Scheme with code '{payload.code}' already exists.")

    scheme = Scheme(
        **payload.model_dump(),
        created_by=current_user.id,
        updated_by=current_user.id,
    )
    db.add(scheme)
    db.flush()

    db.add(AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="SCHEME_CREATED",
        entity_type="SCHEME",
        entity_id=scheme.id,
        new_value={"code": scheme.code, "name": scheme.name},
    ))
    db.commit()
    db.refresh(scheme)
    return scheme


# ── PATCH /schemes/{id} ───────────────────────────────────────────────────────
@router.patch("/{scheme_id}", response_model=SchemeResponseSchema)
async def update_scheme(
    scheme_id: UUID,
    payload: SchemeUpdateSchema,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")

    old_val = {"is_active": scheme.is_active, "name": scheme.name}
    update_data = payload.model_dump(exclude_unset=True)
    for key, val in update_data.items():
        setattr(scheme, key, val)
    scheme.updated_by = current_user.id  # type: ignore

    db.add(AuditLog(
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        action="SCHEME_UPDATED",
        entity_type="SCHEME",
        entity_id=scheme.id,
        old_value=old_val,
        new_value=update_data,
    ))
    db.commit()
    db.refresh(scheme)
    return scheme


# ── DELETE /schemes/{id} ─────────────────────────────────────────────────────
@router.delete("/{scheme_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_scheme(
    scheme_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")
    scheme.is_active = False  # type: ignore
    scheme.updated_by = current_user.id  # type: ignore
    db.add(AuditLog(
        actor_id=current_user.id, actor_role=current_user.role.value,
        action="SCHEME_DEACTIVATED", entity_type="SCHEME", entity_id=scheme.id,
    ))
    db.commit()


# ── GET /schemes/{id}/stats ──────────────────────────────────────────────────
@router.get("/{scheme_id}/stats")
async def scheme_stats(
    scheme_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")

    from app.models.application import ApplicationStatus
    counts = (
        db.query(Application.status, func.count(Application.id))
        .filter(Application.scheme_id == scheme_id)
        .group_by(Application.status)
        .all()
    )
    by_status = {row[0].value: row[1] for row in counts}
    total = sum(by_status.values())

    gender_counts = (
        db.query(Application.applicant_gender, func.count(Application.id))
        .filter(Application.scheme_id == scheme_id)
        .group_by(Application.applicant_gender)
        .all()
    )

    state_counts = (
        db.query(Application.state_code, func.count(Application.id))
        .filter(Application.scheme_id == scheme_id)
        .group_by(Application.state_code)
        .order_by(func.count(Application.id).desc())
        .limit(15)
        .all()
    )

    avg_score = (
        db.query(func.avg(Application.overall_ai_score))
        .filter(Application.scheme_id == scheme_id, Application.overall_ai_score.isnot(None))
        .scalar()
    )

    return {
        "scheme_id": str(scheme_id),
        "scheme_name": scheme.name,
        "total_applications": total,
        "by_status": by_status,
        "by_gender": {str(r[0]): r[1] for r in gender_counts},
        "by_state": {r[0]: r[1] for r in state_counts},
        "avg_ai_score": round(float(avg_score), 2) if avg_score else None,
        "seats_filled": by_status.get("APPROVED", 0) + by_status.get("DISBURSED", 0),
        "total_seats": scheme.total_seats,
    }
