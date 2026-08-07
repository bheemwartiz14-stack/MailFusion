"""
Infrastructure health utilities for the sync engine.

These probe Redis (used for caching and coordination) rather than a Celery
broker/worker, since tasks now run on Django's in-process Task backend.
"""

import redis

from django.conf import settings


def _client():
    try:
        return redis.from_url(settings.REDIS_URL, socket_connect_timeout=2)
    except Exception:  # noqa: BLE001
        return None


def broker_healthy():
    """Return True if Redis (the coordination/cache layer) is reachable."""
    client = _client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False
    finally:
        try:
            client.close()
        except Exception:  # noqa: BLE001
            pass


def queue_depth():
    """Approximate number of jobs waiting to run (SyncJob queued count).

    Returns the DB-backed backlog since there is no external broker queue.
    """
    try:
        from portal.models import SyncJob

        return SyncJob.objects.filter(status="queued").count()
    except Exception:  # noqa: BLE001
        return 0


def worker_status():
    """Best-effort status of the in-process task backend.

    The immediate backend executes tasks synchronously; report it as the
    single active "worker" whenever the app is running.
    """
    try:
        from django.tasks import task_backends
        from django.tasks.exceptions import InvalidTaskBackend

        task_backends["default"]
        return {"active": True, "count": 1}
    except (InvalidTaskBackend, KeyError, Exception):  # noqa: BLE001
        return {"active": False, "count": 0}
