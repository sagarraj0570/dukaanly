from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "dukaanly_worker",
    broker=str(settings.REDIS_URL),
    backend=str(settings.REDIS_URL),
    include=[
        "app.tasks.notifications",
        "app.tasks.delivery_eta",
        "app.tasks.order_recovery",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    # Resilience & Failure Recovery (Stage 9)
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=240,  # 4 minutes soft limit: allows graceful cleanup
    task_time_limit=300,  # 5 minutes hard limit: SIGKILL safeguard
    broker_connection_retry_on_startup=True,
    result_expires=3600,
    beat_schedule={
        "reconcile-active-deliveries-eta-every-minute": {
            "task": "reconcile_active_deliveries_eta",
            "schedule": 60.0,
        },
        "reconcile-stale-pending-orders-every-minute": {
            "task": "reconcile_stale_pending_orders",
            "schedule": 60.0,
        },
        "reconcile-expired-inventory-reservations-every-minute": {
            "task": "reconcile_expired_inventory_reservations",
            "schedule": 60.0,
        },
        "reconcile-stale-unaccepted-orders-every-two-minutes": {
            "task": "reconcile_stale_unaccepted_orders",
            "schedule": 120.0,
        },
        "reconcile-stale-deliveries-every-minute": {
            "task": "reconcile_stale_deliveries",
            "schedule": 60.0,
        },
        "escalate-unassigned-dispatch-offers-every-fifteen-seconds": {
            "task": "escalate_unassigned_dispatch_offers",
            "schedule": 15.0,
        },
    },
)


def get_celery_status() -> dict:
    """Returns operational configuration and registered task metrics for Celery."""
    registered_tasks = sorted(list(celery_app.tasks.keys()))
    return {
        "broker_url_masked": settings.redis_url_masked,
        "broker_url_configured": bool(settings.REDIS_URL),
        "acks_late": celery_app.conf.task_acks_late,
        "task_acks_late": celery_app.conf.task_acks_late,
        "reject_on_worker_lost": celery_app.conf.task_reject_on_worker_lost,
        "prefetch_multiplier": celery_app.conf.worker_prefetch_multiplier,
        "worker_prefetch_multiplier": celery_app.conf.worker_prefetch_multiplier,
        "soft_time_limit": celery_app.conf.task_soft_time_limit,
        "time_limit": celery_app.conf.task_time_limit,
        "scheduled_tasks_count": len(celery_app.conf.beat_schedule or {}),
        "registered_tasks_count": len(registered_tasks),
    }
