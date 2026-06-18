"""
Celery application configuration for the workflow orchestrator.

Uses Redis as both broker and result backend. Falls back gracefully
when Redis is unavailable — the orchestrator can still run in local mode.

Start a worker:
    cd ui/backend && celery -A celery_app worker --loglevel=info --concurrency=4

Monitor with Flower (optional):
    celery -A celery_app flower --port=5555
"""

import os

from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", REDIS_URL)

celery_app = Celery(
    "workflow_orchestrator",
    broker=CELERY_BROKER_URL,
    backend=CELERY_RESULT_BACKEND,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    result_expires=86400,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_reject_on_worker_lost=True,
    task_soft_time_limit=3600,
    task_time_limit=3900,
    task_routes={
        "celery_tasks.execute_ansible_step": {"queue": "ansible"},
        "celery_tasks.execute_parallel_group": {"queue": "ansible"},
    },
    task_default_queue="ansible",
    broker_connection_retry_on_startup=True,
)

celery_app.autodiscover_tasks(["celery_tasks"])


def is_redis_available() -> bool:
    try:
        import redis as _redis
        r = _redis.Redis.from_url(REDIS_URL, socket_connect_timeout=2)
        r.ping()
        return True
    except Exception:
        return False


def get_worker_stats() -> dict:
    try:
        inspector = celery_app.control.inspect(timeout=3)
        active = inspector.active() or {}
        stats = inspector.stats() or {}
        registered = inspector.registered() or {}
        return {
            "available": True,
            "workers": list(stats.keys()),
            "worker_count": len(stats),
            "active_tasks": sum(len(tasks) for tasks in active.values()),
            "registered_tasks": {
                name: list(tasks) for name, tasks in registered.items()
            },
        }
    except Exception as e:
        return {"available": False, "error": str(e)}
