from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init, worker_process_shutdown

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
    "sync-atlascloud-models": {
        "task": "app.workers.tasks.sync_provider_models",
        "schedule": crontab(hour=2, minute=0),
        "args": ("atlascloud",),
    },
    "sync-poe-models": {
        "task": "app.workers.tasks.sync_provider_models",
        "schedule": crontab(hour=2, minute=30),
        "args": ("poe",),
    },
    "sync-comfyui-models": {
        "task": "app.workers.tasks.sync_provider_models",
        "schedule": crontab(hour=3, minute=0),
        "args": ("comfyui_direct",),
    },
    "sync-ollama-models": {
        "task": "app.workers.tasks.sync_provider_models",
        "schedule": crontab(hour=3, minute=30),
        "args": ("ollama",),
    },
    "cleanup-old-notifications": {
        "task": "app.workers.tasks.cleanup_old_notifications",
        "schedule": crontab(hour=3, minute=0),
    },
}


# -- Worker lifecycle signals -------------------------------------------
@worker_process_init.connect
def _on_worker_process_init(**kwargs):
    from app.plugins.registry import discover_plugins
    from app.workers.context import ctx

    ctx.start()
    discover_plugins()


@worker_process_shutdown.connect
def _on_worker_shutdown(**kwargs):
    from app.workers.context import ctx

    ctx.stop()
