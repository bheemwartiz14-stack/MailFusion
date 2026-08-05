"""
Task/health utilities for the background synchronization engine.
"""

from django.conf import settings


def broker_healthy():
    """Return True if the Celery broker (Redis) is reachable."""
    try:
        from celery import current_app

        conn = current_app.connection()
        conn.connect()
        conn.release()
        return True
    except Exception:  # noqa: BLE001
        return False


def queue_depth():
    """Approximate number of messages waiting on the default queue."""
    try:
        from celery import current_app

        conn = current_app.connection()
        try:
            reserve = conn.default_channel.client.llen(
                current_app.conf.get("task_default_queue", "celery")
            )
            return reserve
        finally:
            conn.release()
    except Exception:  # noqa: BLE001
        return -1


def worker_status():
    """Best-effort check for live Celery workers (active / count)."""
    try:
        from celery import current_app

        pinged = current_app.control.ping(timeout=3)
        return {"active": bool(pinged), "count": len(pinged)}
    except Exception:  # noqa: BLE001
        return {"active": False, "count": 0}