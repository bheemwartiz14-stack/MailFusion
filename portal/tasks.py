"""
Django Task background jobs for account management and synchronization.

Runs against the configured ``django.tasks`` backend (immediate, in-process
by default). Every task is idempotent and safe to call repeatedly. Heavier work
is delegated to the service layer; tasks only orchestrate and track ``SyncJob``
rows.
"""

import logging
import socket

from django.tasks import task

logger = logging.getLogger(__name__)


def _worker_id(requested_by):
    return f"{requested_by}@{socket.gethostname()}"


@task
def sync_account(pk, requested_by="web"):
    """Synchronize a single account."""
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
    repo.mark_job_running(job)

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
    return {"status": "failed", "account": account.email, "error": result.error}


@task
def sync_all_accounts():
    """Run a sync for every syncable account (scheduled)."""
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
        sync_account.enqueue(str(account.pk), requested_by="schedule")
        dispatched.append(str(account.pk))
    return {"dispatched": dispatched}


@task
def refresh_expired_tokens():
    from portal.services.sync_services import SyncService

    refreshed, failed = SyncService().refresh_expired_tokens(worker="schedule")
    return {"refreshed": refreshed, "failed": failed}


@task
def renew_webhook_subscriptions():
    from portal.services.sync_services import SyncService

    renewed, failed = SyncService().renew_webhooks(worker="schedule")
    return {"renewed": renewed, "failed": failed}


@task
def download_attachment(attachment_id, job_pk=None):
    """Download one attachment's binary content; idempotent."""
    from portal.repositories import SyncRepository
    from portal.services.sync_services import SyncService

    repo = SyncRepository()
    job = repo.get_attachment_job(job_pk) if job_pk else None
    if repo.get_attachment(attachment_id) is None:
        return {"status": "failed", "reason": "attachment missing"}
    attempts = (job.attempts + 1) if job else 1
    if job:
        repo.mark_attachment_job(job, status="downloading", attempts=attempts)
    if SyncService().download_attachment(attachment_id):
        if job:
            repo.mark_attachment_job(job, status="downloaded")
        return {"status": "downloaded", "attachment_id": str(attachment_id)}
    if job:
        repo.mark_attachment_job(
            job, status="failed", attempts=attempts, error="Graph download failed"
        )
    return {"status": "failed", "attachment_id": str(attachment_id)}


@task
def cleanup_old_logs():
    """Delete sync logs older than the configured retention window."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from portal.repositories import SyncRepository

    cutoff = timezone.now() - timedelta(days=settings.SYNC_LOG_RETENTION_DAYS)
    deleted = SyncRepository().delete_older_than(cutoff)
    return {"deleted": deleted}


@task
def run_system_health_checks():
    """Health: persistence reachability, job backlog, sync failures."""
    from django.utils import timezone

    from portal.services.notification_service import NotificationService
    from portal.services.sync_services import SyncService

    notify = NotificationService()
    alerts = []
    metrics = SyncService().sync_metrics()

    if metrics["queued_jobs"] > 100:
        notify.notify(
            title="Job backlog growing",
            detail=f"{metrics['queued_jobs']} jobs queued; processing may be behind.",
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

    from portal.models import SyncLog

    try:
        fresh = SyncLog.objects.filter(start_time__gte=timezone.now()).exists()
        if not fresh:
            notify.notify(
                title="No recent sync activity",
                detail="No sync log entries have been recorded recently.",
                icon="bi-clock-history",
                tone="warning",
            )
            alerts.append("no_activity")
    except Exception:  # noqa: BLE001
        pass

    return {
        "healthy": True,
        "alerts": alerts,
        "metrics": {
            "queued_jobs": metrics.get("queued_jobs", 0),
            "running_jobs": metrics.get("running_jobs", 0),
            "failed_jobs": metrics.get("failed_jobs", 0),
            "failed_syncs": metrics.get("failed_syncs", 0),
            "unread_notifications": metrics.get("unread_notifications", 0),
        },
    }