"""
MoTA Scholarship Management System — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
import time

from app.core.config import get_settings
from app.api.v1.routes import auth, schemes, applications, documents, merit

settings = get_settings()
logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO))
logger = logging.getLogger("mota")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 MoTA Scholarship System starting up...")
    # Could run DB migrations, seed checks, etc. here
    yield
    logger.info("🛑 MoTA Scholarship System shutting down...")


app = FastAPI(
    title="MoTA Scholarship & Fellowship Management System",
    description="""
    ## AI-Enabled Scholarship Portal for Ministry of Tribal Affairs

    Manages **NFST**, **NOS**, and other tribal scholarship schemes end-to-end:
    - OTP-based applicant registration & login
    - Configurable scheme rule engine (no-code)
    - AI/OCR document verification pipeline
    - State-machine application lifecycle
    - Automated merit list generation with female quota
    - RBAC: Applicant → Reviewer → Senior Reviewer → Scheme Admin → Super Admin
    - Full immutable audit trail
    """,
    version="1.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://scholarship.tribal.gov.in",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

if settings.is_production:
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["scholarship.tribal.gov.in", "*.tribal.gov.in"],
    )


@app.middleware("http")
async def add_request_timing(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    elapsed = round((time.monotonic() - start) * 1000, 2)
    response.headers["X-Process-Time-Ms"] = str(elapsed)
    logger.debug(f"{request.method} {request.url.path} → {response.status_code} ({elapsed}ms)")
    return response


# ── Global Exception Handlers ─────────────────────────────────────────────────

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception on {request.url.path}: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An internal server error occurred. Please try again later."},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

API_V1 = "/api/v1"

app.include_router(auth.router, prefix=API_V1)
app.include_router(schemes.router, prefix=API_V1)
app.include_router(applications.router, prefix=API_V1)
app.include_router(documents.router, prefix=API_V1)
app.include_router(merit.router, prefix=API_V1)


# ── Health Check ──────────────────────────────────────────────────────────────

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "service": "MoTA Scholarship API",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT,
    }


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": "MoTA Scholarship & Fellowship Management System API",
        "docs": "/api/docs",
        "version": "1.0.0",
    }
