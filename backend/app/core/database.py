from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings

settings = get_settings()

# psycopg3 (psycopg[binary]) uses the 'postgresql+psycopg' URL scheme.
# Transparently upgrade legacy 'postgresql://' URLs so the same .env works.
_db_url = settings.DATABASE_URL
if _db_url.startswith("postgresql://") or _db_url.startswith("postgresql+psycopg2://"):
    _db_url = _db_url.replace("postgresql+psycopg2://", "postgresql+psycopg://", 1)
    _db_url = _db_url.replace("postgresql://", "postgresql+psycopg://", 1)

engine = create_engine(
    _db_url,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=(settings.ENVIRONMENT == "development"),
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session and closes it after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
