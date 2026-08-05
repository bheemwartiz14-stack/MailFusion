"""
Celery tasks for account management and background synchronization.

Every task is idempotent and safe to retry. Heavier work is delegated to the
service layer; tasks only orchestrate, track ``SyncJob`` rows and perform
graceful retries with exponential backoff.
"""

import logging
import socket
from datetime import timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


def _backoff(attempt):
    """Exponential backoff in seconds, capped at one hour."""
    return min(60 * (2 ** max(attempt, 0)), 3600)


def _worker_id(requested_by):
    return f"{requested_by}@{socket.gethostname()}"


@shared_task(bind=True, name="portal.tasks.sync_account", acks_late=True, track_started=True, max_retries=5, default_retry_delay=60)
def sync_account(self, pk, requested_by="celery"):
    """Synchronize a single account; retries with exponential backoff on failure."""
    from portal.models import OutlookAccount
    from portal.repositories import SyncRepository
    from portal.services.sync_services import SyncService

    account = OutlookAccount.objects.filter(pk=pk).first()
    if not account:
        return {"status": "skipped", "reason": "account missing"}
    if account.is_sync_paused:
        return {"status": "skipped", "reason": "paused"}

    repo = SyncRepository()
    job = repo.gets_in_flight_job(account, "sync") or repo.create_job(
        job_type="sync", account=account, priority=3
    )
    repo.mark_job_running(job, task_id=self.request.id or "")

    result = SyncService().sync_account(account, worker=_worker_id(requested_by))
    if result.success:
        repo.mark_job_success(
            job,
            f"added={result.added} updated={result.updated} removed={result.removed}",
        )
        return {
            "status": "completed",
            "account": account.email,
            "added": result.added,
            "updated": result.updated,
            "removed": result.removed,
        }

    repo.mark_job_failure(job, result.error)
    if job.attempts < job.max_attempts:
        raise self.retry(countdown=_backoff(job.attempts))
    return {"status": "failed", "account": account.email, "error": result.error}


@shared_task(name="portal.tasks.sync_all_accounts", max_retries=3)
def sync_all_accounts():
    """Enqueue a sync task for every syncable account (used by Celery Beat)."""
    from portal.models import OutlookAccount
    from portal.repositories import SyncRepository

    repo = SyncRepository()
    dispatched = []
    for account in OutlookAccount.objects.filter(
        is_sync_paused=False,
        oauth_status__in=["connected", "expired"],
        status__in=["active", "error"],
    ):
        if repo.gets_in_flight_job(account, "sync"):
            continue
        sync_account.delay(account.pk, requested_by="beat")
        dispatched.append(str(account.pk))
    return {"dispatched": dispatched}


@shared_task(name="portal.tasks.refresh_expired_tokens")
def refresh_expired_tokens():
    from portal.services.sync_services import SyncService

    refreshed, failed = SyncService().refresh_expired_tokens(worker="beat")
    return {"refreshed": refreshed, "failed": failed}


@shared_task(name="portal.tasks.renew_webhook_subscriptions")
def renew_webhook_subscriptions():
    from portal.services.sync_services import SyncService

    renewed, failed = SyncService().renew_webhooks(worker="beat")
    return {"renewed": renewed, "failed": failed}


@shared_task(bind=True, name="portal.tasks.download_attachment", acks_late=True, max_retries=3, default_retry_delay=90)
def download_attachment(self, attachment_id, job_pk=None):
    """Download one attachment's binary content; idempotent and retryable."""
    from portal.repositories import SyncRepository
    from portal.services.sync_services import SyncService

    repo = SyncRepository()
    job = repo.get_attachment_job(job_pk) if job_pk else None
    try:
        att = repo.get_attachment(attachment_id)
    except Exception:
        return {"status": "failed", "reason": "attachment missing"}
    attempts = (job.attempts + 1) if job else 1
    if job:
        repo.mark_attachment_job(job, status="downloading", attempts=attempts)
    if SyncService().download_attachment(attachment_id):
        if job:
            repo.mark_attachment_job(job, status="downloaded")
        return {"status": "downloaded", "attachment_id": attachment_id}
    if job:
        repo.mark_attachment_job(
            job, status="failed", attempts=attempts, error="Graph download failed"
        )
    if attempts < (job.max_attempts if job else 3):
        raise self.retry(countdown=_backoff(attempts - 1))
    return {"status": "failed", "attachment_id": attachment_id}


@shared_task(name="portal.tasks.cleanup_old_logs")
def cleanup_old_logs():
    """Delete sync logs older than the configured retention window."""
    from django.conf import settings
    from django.utils import timezone

    from portal.repositories import SyncRepository

    cutoff = timezone.now() - timedelta(days=settings.SYNC_LOG_RETENTION_DAYS)
    deleted = SyncRepository().delete_older_than(cutoff)
    return {"deleted": deleted}


@shared_task(name="portal.tasks.run_system_health_checks")
def run_system_health_checks():
    """Health: broker/persistence reachability, queue depth, sync failures."""
    from django.conf import settings
    from django.utils import timezone

    from portal.services.notification_service import NotificationService
    from portal.services.sync_services import SyncService
    from portal.utils.tasks import broker_healthy

    notify = NotificationService()
    alerts = []

    if not broker_healthy():
        notify.notify(
            title="Celery broker unreachable",
            detail="Redis/Celery broker could not be reached by the health check.",
            icon="bi-hdd-network",
            tone="danger",
        )
        return {"healthy": False, "reason": "broker"}

    metrics = SyncService().sync_metrics()

    if metrics["queued_jobs"] > 100:
        notify.notify(
            title="Queue backlog growing",
            detail=f"{metrics['queued_jobs']} jobs queued; workers may be behind.",
            icon="bi-hourglass-split",
            tone="warning",
        )
        alerts.append("queue_backlog")

    if metrics["failed_syncs"] > 20:
        notify.notify(
            title="Synchronization failures detected",
            detail=f"{metrics['failed_syncs']} failed syncs today.",
            icon="bi-exclamation-octagon",
            tone="danger",
        )
        alerts.append("sync_failures")

    return {"healthy": True, "alerts": alerts, "metrics": metrics}


@shared_task(name="portal.tasks.monitor_queue")
def monitor_queue():
    """Low-frequency queue watcher that alerts on excessive backlog."""
    from portal.services.notification_service import NotificationService
    from portal.services.sync_services import SyncService

    metrics = SyncService().sync_metrics()
    if metrics["running_jobs"] == 0 and metrics["queued_jobs"] > 0:
        NotificationService().notify(
            title="No consumers running",
            detail="There are queued jobs but no running workers detected.",
            icon="bi-play-circle",
            tone="danger",
        )
    return {"queued": metrics["queued_jobs"], "running": metrics["running_jobs"]}