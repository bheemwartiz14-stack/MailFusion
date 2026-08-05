"""
Sync repository.

Data access for the synchronization cluster: ``EmailSyncState``, ``SyncLog``,
``SyncJob`` and ``AttachmentDownloadJob``. Pure queries only - no business logic.
"""

from django.db import transaction
from django.utils import timezone

from portal.models import Attachment, AttachmentDownloadJob, EmailSyncState, SyncJob, SyncLog


class SyncRepository:
    """Persistence for synchronization state, logs and jobs."""

    # -------------------- EmailSyncState --------------------

    def get_or_create_state(self, account):
        """Return the EmailSyncState for an account, creating it if absent."""
        state, _ = EmailSyncState.objects.get_or_create(account=account)
        return state

    def update_state(self, state, **fields):
        """Update an EmailSyncState with the given fields."""
        for field, value in fields.items():
            setattr(state, field, value)
        state.save(update_fields=list(fields.keys()) + ["updated_at"])
        return state

    def mark_sync_started(self, state, worker=""):
        """Mark the start of a sync run and reset consecutive failures."""
        return self.update_state(
            state,
            last_sync_started_at=timezone.now(),
            consecutive_failures=0,
            last_error=f"worker={worker or ''}",
        )

    def mark_sync_success(self, state, delta_link=""):
        """Mark a successful sync, persisting the next delta link."""
        now = timezone.now()
        return self.update_state(
            state,
            delta_link=delta_link or state.delta_link,
            last_sync_completed_at=now,
            last_successful_sync_at=now,
            last_error="",
        )

    def mark_sync_failure(self, state, error):
        """Mark a failed sync, incrementing the consecutive failure counter."""
        state.consecutive_failures += 1
        return self.update_state(
            state,
            last_sync_completed_at=timezone.now(),
            last_error=error[:1000],
            consecutive_failures=state.consecutive_failures,
        )

    # -------------------- SyncLog --------------------

    def create_log(self, *, account, status="started", start_time, worker=""):
        """Create a SyncLog row."""
        return SyncLog.objects.create(
            account=account,
            status=status,
            start_time=start_time,
            worker=worker,
        )

    def get_log(self, pk):
        """Return a SyncLog by primary key."""
        return SyncLog.objects.select_related("account").get(pk=pk)

    def get_latest_log(self, account):
        """Return the most recent SyncLog for an account, if any."""
        return account.sync_logs.order_by("-start_time").first()

    def list_logs(self, account=None, status="", query="", limit=200):
        """Filtered list of sync logs (newest first)."""
        qs = SyncLog.objects.select_related("account").order_by("-start_time")
        if account:
            qs = qs.filter(account=account)
        if status:
            qs = qs.filter(status=status)
        if query:
            qs = qs.filter(
                account__name__icontains=query
            ) | qs.filter(account__email__icontains=query)
        return qs[:limit]

    def count_logs_by_status(self):
        """Count sync logs grouped by status."""
        from django.db.models import Count

        return dict(SyncLog.objects.values_list("status").annotate(c=Count("id")))

    def delete_older_than(self, cutoff):
        """Delete sync logs older than ``cutoff``; return deleted count."""
        deleted, _ = SyncLog.objects.filter(start_time__lt=cutoff).delete()
        return deleted

    # -------------------- SyncJob --------------------

    def create_job(self, *, job_type, priority=5, account=None, max_attempts=3, scheduled_at=None):
        """Create a queued SyncJob."""
        return SyncJob.objects.create(
            job_type=job_type,
            priority=priority,
            account=account,
            max_attempts=max_attempts,
            scheduled_at=scheduled_at or timezone.now(),
        )

    def mark_job_running(self, job, task_id=""):
        """Mark a SyncJob as running, recording attempts/start."""
        job.attempts += 1
        return self._save(
            job,
            status="running",
            task_id=task_id,
            started_at=timezone.now(),
            finished_at=None,
            attempts=job.attempts,
        )

    def mark_job_success(self, job, result=""):
        return self._save(job, status="succeeded", finished_at=timezone.now(), result=str(result)[:4000])

    def mark_job_failure(self, job, error):
        return self._save(job, status="failed", finished_at=timezone.now(), error=str(error)[:4000])

    def queue_ready_jobs(self, now=None):
        """Return ready-to-run queued jobs in priority order."""
        now = now or timezone.now()
        return SyncJob.objects.filter(
            status="queued", scheduled_at__lte=now
        ).order_by("priority", "-created_at")

    def get_running_jobs(self):
        return SyncJob.objects.filter(status="running").select_related("account")

    def gets_in_flight_job(self, account, job_type):
        """Return an unfinished job of a given type for an account, if any."""
        return SyncJob.objects.filter(
            account=account,
            job_type=job_type,
            status__in=["queued", "running"],
        ).first()

    def _save(self, job, **fields):
        for field, value in fields.items():
            setattr(job, field, value)
        job.save(update_fields=list(fields.keys()) + ["updated_at"])
        return job

    # -------------------- AttachmentDownloadJob --------------------

    def create_attachment_job(self, attachment, max_attempts=3):
        return AttachmentDownloadJob.objects.create(
            attachment=attachment, max_attempts=max_attempts
        )

    def get_or_create_attachment_job(self, attachment):
        obj, _ = AttachmentDownloadJob.objects.get_or_create(
            attachment=attachment,
            defaults={"status": "queued"},
        )
        return obj

    def get_attachment_job(self, pk):
        """Return an AttachmentDownloadJob by pk, or None."""
        return AttachmentDownloadJob.objects.filter(pk=pk).first()

    def queued_attachment_jobs(self):
        return AttachmentDownloadJob.objects.filter(status="queued").select_related(
            "attachment__email__outlook_account"
        )

    def mark_attachment_job(self, job, *, status, attempts=None, error="", finished_at=True):
        attrs = {}
        if attempts is not None:
            attrs["attempts"] = attempts
        if status == "downloading":
            attrs["started_at"] = timezone.now()
        if finished_at and status in ("downloaded", "failed"):
            attrs["finished_at"] = timezone.now()
        if error:
            attrs["error"] = error[:1000]
        attrs["status"] = status
        for field, value in attrs.items():
            setattr(job, field, value)
        job.save(update_fields=list(attrs.keys()) + ["updated_at"])
        return job

    # -------------------- Attachments --------------------

    def save_attachments(self, email, attachments):
        """Persist attachment metadata idempotently; return list saved."""
        saved = []
        for att in attachments or []:
            _, created = Attachment.objects.update_or_create(
                email=email,
                graph_attachment_id=att["id"],
                defaults={
                    "name": att.get("name", ""),
                    "content_type": att.get("contentType", ""),
                    "size_bytes": att.get("size", 0),
                    "content_id": att.get("contentId", ""),
                    "is_inline": att.get("isInline", False),
                },
            )
            saved.append((_, created))
        return saved

    def list_attachments(self, email):
        return Attachment.objects.filter(email=email).order_by("-size_bytes")

    def get_attachment(self, pk):
        return Attachment.objects.get(pk=pk)

    @transaction.atomic
    def store_attachment_content(self, attachment, content, is_downloaded=True, error=""):
        attachment.content = content
        attachment.is_downloaded = is_downloaded
        attachment.download_error = error
        attachment.save(update_fields=["content", "is_downloaded", "download_error", "updated_at"])
        return attachment