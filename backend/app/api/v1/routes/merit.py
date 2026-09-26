"""
Merit Engine Routes — Automated ranked merit list generation.

Endpoints:
  POST  /merit/{scheme_id}/generate    — Generate merit list [SCHEME_ADMIN+]
  GET   /merit/{scheme_id}/list        — Get merit list
  POST  /merit/{scheme_id}/finalize    — Lock and publish merit list [SUPER_ADMIN]
"""
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.rbac import require_scheme_admin, require_super_admin
from app.models import Application, Scheme, MeritList, ApplicationStatus, AuditLog
from app.models.user import User
from app.schemas.application import MeritListResponseSchema

router = APIRouter(prefix="/merit", tags=["Merit Engine"])


def _compute_merit_score(app: Application, weights: dict) -> float:
    """
    Compute a weighted merit score for an application.

    Default formula:
      score = (academic_score * w_academic) + (income_score * w_income)
            + (special_category * w_special) + ...

    academic_score  = best available percentage / 100 (0-1)
    income_score    = 1 - (income / max_income) clamped 0-1  (lower income = higher score)
    """
    # ── Academic component ───────────────────────────────────────────────────
    percentages = [
        float(str(p)) for p in [
            app.percentage_pg, app.percentage_ug,
            app.percentage_12, app.percentage_10,
        ] if p is not None
    ]
    academic_raw = max(percentages) / 100.0 if percentages else 0.5

    # ── Income component (inverted — lower income → higher score) ────────────
    max_income = 2_000_000  # 20L cap for normalisation
    income_raw = float(str(app.annual_family_income)) if app.annual_family_income else max_income
    income_score = max(0.0, 1.0 - float(income_raw) / max_income)

    # ── Assemble ─────────────────────────────────────────────────────────────
    score = 0.0
    score += weights.get("academic_score", 0.7) * academic_raw * 100
    score += weights.get("income_score", 0.3) * income_score * 100

    # AI confidence bonus (max 5 pts)
    if app.overall_ai_score:
        score += min(float(str(app.overall_ai_score)) / 100 * 5, 5.0)

    return round(score, 4)


# ── POST /merit/{scheme_id}/generate ─────────────────────────────────────────
@router.post("/{scheme_id}/generate", response_model=MeritListResponseSchema, status_code=status.HTTP_201_CREATED)
async def generate_merit_list(
    scheme_id: UUID,
    academic_year: str = Query(..., pattern=r"^\d{4}-\d{4}$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    scheme = db.query(Scheme).filter(Scheme.id == scheme_id).first()
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found.")

    # Fetch all APPROVED applications for this scheme & year
    apps = db.query(Application).filter(
        Application.scheme_id == scheme_id,
        Application.academic_year == academic_year,
        Application.status.in_([ApplicationStatus.APPROVED, ApplicationStatus.MANUAL_SCRUTINY]),
        Application.ai_processing_done == True,
    ).all()

    if not apps:
        raise HTTPException(status_code=400, detail="No eligible applications found for merit generation.")

    weights = dict(scheme.merit_weights or {"academic_score": 0.7, "income_score": 0.3})

    # Score & sort
    scored = []
    for app in apps:
        ms = _compute_merit_score(app, weights)
        app.merit_score = ms  # type: ignore
        scored.append((app, ms))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Apply female quota
    total_seats = int(str(scheme.total_seats)) if scheme.total_seats else len(scored)
    female_quota = int(total_seats * float(str(scheme.female_quota_pct or 30)) / 100)
    female_selected = 0
    male_list, female_list = [], []

    for app, score in scored:
        gender = str(app.applicant_gender) if app.applicant_gender else ""
        if "FEMALE" in gender and female_selected < female_quota:
            female_list.append((app, score))
            female_selected += 1
        else:
            male_list.append((app, score))

    # Merge lists maintaining rank
    combined = female_list + [x for x in male_list if len(female_list) + len(male_list) <= total_seats]
    combined = combined[:total_seats]
    combined.sort(key=lambda x: x[1], reverse=True)

    list_data = []
    for rank, (app, score) in enumerate(combined, start=1):
        app.merit_rank = rank  # type: ignore
        list_data.append({
            "rank": rank,
            "application_id": str(app.id),
            "application_number": app.application_number,
            "applicant_name": app.applicant_name,
            "state_code": app.state_code,
            "merit_score": score,
            "gender": str(app.applicant_gender),
        })

    # Delete old draft merit list if exists
    db.query(MeritList).filter(
        MeritList.scheme_id == scheme_id,
        MeritList.academic_year == academic_year,
        MeritList.is_final == False,
    ).delete()

    merit_list = MeritList(
        scheme_id=scheme_id,
        academic_year=academic_year,
        generated_by=current_user.id,
        total_applicants=len(apps),
        total_selected=len(list_data),
        list_data=list_data,
        is_final=False,
    )
    db.add(merit_list)

    db.add(AuditLog(
        actor_id=current_user.id, actor_role=current_user.role.value,
        action="MERIT_LIST_GENERATED",
        entity_type="MERIT_LIST", entity_id=merit_list.id,
        new_value={"scheme": scheme.code, "year": academic_year, "count": len(list_data)},
    ))
    db.commit()
    db.refresh(merit_list)
    return merit_list


# ── GET /merit/{scheme_id}/list ───────────────────────────────────────────────
@router.get("/{scheme_id}/list", response_model=MeritListResponseSchema)
async def get_merit_list(
    scheme_id: UUID,
    academic_year: str = Query(...),
    final_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_scheme_admin()),
):
    query = db.query(MeritList).filter(
        MeritList.scheme_id == scheme_id,
        MeritList.academic_year == academic_year,
    )
    if final_only:
        query = query.filter(MeritList.is_final == True)

    ml = query.order_by(MeritList.generated_at.desc()).first()
    if not ml:
        raise HTTPException(status_code=404, detail="Merit list not found.")
    return ml


# ── POST /merit/{scheme_id}/finalize ─────────────────────────────────────────
@router.post("/{scheme_id}/finalize", response_model=MeritListResponseSchema)
async def finalize_merit_list(
    scheme_id: UUID,
    academic_year: str = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_super_admin()),
):
    ml = db.query(MeritList).filter(
        MeritList.scheme_id == scheme_id,
        MeritList.academic_year == academic_year,
        MeritList.is_final == False,
    ).first()
    if not ml:
        raise HTTPException(status_code=404, detail="Draft merit list not found.")

    ml.is_final = True  # type: ignore
    ml.published_at = datetime.now(timezone.utc)  # type: ignore

    db.add(AuditLog(
        actor_id=current_user.id, actor_role=current_user.role.value,
        action="MERIT_LIST_FINALIZED",
        entity_type="MERIT_LIST", entity_id=ml.id,
        new_value={"published_at": ml.published_at.isoformat()},
    ))
    db.commit()
    db.refresh(ml)
    return ml
