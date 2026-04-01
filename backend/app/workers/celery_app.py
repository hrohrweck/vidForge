from celery import Celery
from celery.schedules import crontab
from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "vidforge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.task_time_limit,
    worker_prefetch_multiplier=1,
)

celery_app.conf.beat_schedule = {
    "worker-heartbeat": {
        "task": "app.workers.tasks.send_heartbeat",
        "schedule": 30.0,
    },
    "cleanup-stale-workers": {
        "task": "app.workers.tasks.cleanup_stale_workers",
        "schedule": 60.0,
    },
    "reset-daily-budgets": {
        "task": "app.workers.tasks.reset_daily_budgets",
        "schedule": crontab(hour=0, minute=0),
    },
}
