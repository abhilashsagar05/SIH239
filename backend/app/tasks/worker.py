"""Celery worker configuration — connects to Redis broker."""
from celery import Celery
from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "mota_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.tasks.ocr_task",
        "app.tasks.notification_task",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_routes={
        "app.tasks.ocr_task.*": {"queue": "ocr"},
        "app.tasks.notification_task.*": {"queue": "notifications"},
    },
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
