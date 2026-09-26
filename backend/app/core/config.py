from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://mota_user:mota_secret_2026@localhost:5432/mota_scholarship"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    SECRET_KEY: str = "change_me_in_production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # S3
    S3_BUCKET: str = "mota-documents"
    S3_ENDPOINT_URL: str | None = None
    AWS_ACCESS_KEY_ID: str | None = None
    AWS_SECRET_ACCESS_KEY: str | None = None

    # SMS / Email
    SMS_API_KEY: str | None = None
    SMS_SENDER_ID: str = "MOTASC"
    SMTP_HOST: str = "localhost"
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None

    # App
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "DEBUG"
    AI_CONFIDENCE_DEFAULT_THRESHOLD: float = 75.0

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
