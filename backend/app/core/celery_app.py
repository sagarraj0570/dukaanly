from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "dukaanly_worker",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes max per task
)

# Discover tasks from these modules
celery_app.autodiscover_tasks(["app.tasks"])
