"""
Synchronization engine.

Implements the hybrid sync strategy:
    Primary   - Microsoft Graph Change Notifications (webhooks)
    Secondary - Microsoft Graph Delta Queries
    Fallback  - scheduled sync via the recurring maintenance task (5-10 minutes)

The engine is idempotent and safe to run concurrently: it tracks a stable
``@odata.deltaLink`` per account and only commits it after a fully successful
run, so any interrupted sync is replayed on the next attempt.
"""

import logging
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from portal.models import Attachment, Email, OutlookAccount
from portal.repositories import (
    MicrosoftAuthRepository,
    SubscriptionRepository,
    SyncRepository,
)
from portal.services.graph_service import GraphService

logger = logging.getLogger(__name__)

MAX_SYNC_ERROR_LEN = 1000


@dataclass
class SyncResult:
    """Aggregated outcome of a single account sync run."""

    processed: int = 0
    added: int = 0
    updated: int = 0
    removed: int = 0
    attachments_downloaded: int = 0
    delta_link: str = ""
    error: str = ""
    success: bool = True


class SyncService:
    def __init__(
        self,
        graph_service=None,
        auth_service=None,
        sync_repository=None,
        auth_repository=None,
        subscription_repository=None,
    ):
        from portal.services.microsoft_auth_service import MicrosoftAuthService

        self.graph = graph_service or GraphService()
        self.auth_service = auth_service or MicrosoftAuthService()
        self.sync_repository = sync_repository or SyncRepository()
        self.auth_repository = auth_repository or MicrosoftAuthRepository()
        self.subscription_repository = subscription_repository or SubscriptionRepository()

    # -------------------- public entry points --------------------

    def sync_account(self, account, worker=""):
        """
        Synchronize a single account via the delta feed.

        Returns a :class:`SyncResult`. Safe to call repeatedly (idempotent)
        and safe to schedule concurrently for different accounts.
        """
        result = SyncResult()
        if account.is_sync_paused:
            logger.info("Skipping sync for %s (paused)", account.email)
            result.error = "Synchronization paused"
            return result

        state = self.sync_repository.get_or_create_state(account)
        start = timezone.now()
        log = self.sync_repository.create_log(
            account=account, status="started", start_time=start, worker=worker
        )
        self.sync_repository.mark_sync_started(state, worker=worker)

        try:
            access_token = self.auth_service.get_valid_access_token(account)
            if not access_token:
                result.success = False
                result.error = "No valid access token (reauthorization required)"
                raise RuntimeError(result.error)

            result = self._sync_delta(account, access_token, state, result)

            # Only persist the delta link after a fully successful run.
            self.sync_repository.mark_sync_success(state, delta_link=result.delta_link)
            self._record_success(account, result, log, start, worker)
            return result

        except Exception as exc:  # noqa: BLE001 - keep the worker alive
            logger.exception("Sync failed for %s", account.email)
            result.success = False
            result.error = str(exc)
            self.sync_repository.mark_sync_failure(state, result.error)
            self._record_failure(account, result, log, start, worker)
            self._update_health(account, oauth_ok=False, graph_ok=False, error=result.error)
            return result

    def sync_all(self, worker=""):
        """Synchronize every account that is active and not paused."""
        accounts = OutlookAccount.objects.filter(
            is_sync_paused=False,
            oauth_status__in=["connected", "expired"],
            status__in=["active", "error"],
        )
        results = []
        for account in accounts:
            results.append(self.sync_account(account, worker=worker))
        return results

    # -------------------- delta engine --------------------

    def _sync_delta(self, account, access_token, state, result):
        """Walk the delta feed pages and apply changes idempotently."""
        delta_link = state.delta_link
        while True:
            messages, next_link, new_delta_link = self.graph.fetch_message_delta(
                access_token, delta_link=delta_link
            )
            if messages is None:
                raise RuntimeError("Failed to fetch delta feed from Microsoft Graph")

            if messages:
                self._apply_messages(account, messages, result)

            result.delta_link = new_delta_link or result.delta_link or delta_link
            if not next_link:
                break
            delta_link = next_link

        self._update_health(
            account,
            oauth_ok=True,
            graph_ok=True,
            webhook_ok=self._has_active_subscription(account),
            error="",
        )
        return result

    def _apply_messages(self, account, messages, result):
        """Apply a page of delta messages to the database in bulk."""
        incoming = []
        removed_ids = []
        for message in messages:
            if message.pop("_removed", False):
                removed_ids.append(message["graph_message_id"])
            else:
                incoming.append(message)

        if removed_ids:
            deleted, _ = Email.objects.filter(
                outlook_account=account, graph_message_id__in=removed_ids
            ).delete()
            result.removed += deleted

        if not incoming:
            return

        result.processed += len(incoming)
        existing_map = self._load_existing(account, incoming)
        to_create, to_update = [], []
        for message in incoming:
            graph_id = message["graph_message_id"]
            if graph_id in existing_map:
                email = existing_map[graph_id]
                if self._apply_provided(email, message):
                    to_update.append(email)
                result.updated += 1
            else:
                to_create.append(self._build_email(account, message))
                result.added += 1

        if to_create:
            Email.objects.bulk_create(to_create, ignore_conflicts=True)
        if to_update:
            self._bulk_update(to_update)
        self._sync_attachments(account, access_token=None, new_count=len(to_create))

    def _load_existing(self, account, incoming):
        ids = [m["graph_message_id"] for m in incoming]
        emails = Email.objects.filter(outlook_account=account, graph_message_id__in=ids)
        return {e.graph_message_id: e for e in emails.only("id", "graph_message_id")}

    def _build_email(self, account, message):
        return Email(
            outlook_account=account,
            graph_message_id=message["graph_message_id"],
            subject=self._field(message, "subject", ""),
            body_html=self._field(message, "body_html", ""),
            body_text=self._field(message, "body_text", ""),
            preview_text=self._field(message, "preview_text", ""),
            from_name=self._field(message, "from_name", ""),
            from_email=self._field(message, "from_email", ""),
            ccRecipients=self._field(message, "ccRecipients", ""),
            bccRecipients=self._field(message, "bccRecipients", ""),
            toRecipients=self._field(message, "toRecipients", ""),
            conversation_id=self._field(message, "conversation_id", ""),
            internet_message_id=self._field(message, "internet_message_id", ""),
            received_at=self._received_at(message),
            importance=self._field(message, "importance", Email.Importance.NORMAL),
            is_read=message.get("is_read", False),
            has_attachments=bool(message.get("has_attachments", False)),
            folder="Inbox",
        )

    @staticmethod
    def _apply_provided(email, message):
        """Apply only fields present in a delta message; return True if changed."""
        changed = False
        if "subject" in message and email.subject != message["subject"]:
            email.subject = message["subject"]
            changed = True
        if "body_html" in message and email.body_html != message["body_html"]:
            email.body_html = message["body_html"]
            changed = True
        if "from_name" in message and email.from_name != message["from_name"]:
            email.from_name = message["from_name"]
            changed = True
        if "from_email" in message and email.from_email != message["from_email"]:
            email.from_email = message["from_email"]
            changed = True
        if "ccRecipients" in message and email.ccRecipients != message["ccRecipients"]:
            email.ccRecipients = message["ccRecipients"]
            changed = True
        if "bccRecipients" in message and email.bccRecipients != message["bccRecipients"]:
            email.bccRecipients = message["bccRecipients"]
            changed = True
        if "toRecipients" in message and email.toRecipients != message["toRecipients"]:
            email.toRecipients = message["toRecipients"]
            changed = True
        if "received_at" in message:
            dt = self._received_at(message)
            if email.received_at != dt:
                email.received_at = dt
                changed = True
        if "is_read" in message and email.is_read != message["is_read"]:
            email.is_read = message["is_read"]
            changed = True
        if "has_attachments" in message and email.has_attachments != message["has_attachments"]:
            email.has_attachments = message["has_attachments"]
            changed = True
        if "conversation_id" in message and email.conversation_id != message["conversation_id"]:
            email.conversation_id = message["conversation_id"]
            changed = True
        if "preview_text" in message and email.preview_text != message["preview_text"]:
            email.preview_text = message["preview_text"]
            changed = True
        if "body_text" in message and email.body_text != message["body_text"]:
            email.body_text = message["body_text"]
            changed = True
        if "importance" in message and email.importance != message["importance"]:
            email.importance = message["importance"]
            changed = True
        return changed

    @staticmethod
    def _field(message, key, default):
        value = message.get(key)
        return value if value not in (None, "") else default

    @staticmethod
    def _received_at(message):
        dt = parse_datetime(message.get("received_at", "")) if message.get("received_at") else None
        return dt or timezone.now()

    @staticmethod
    def _bulk_update(emails):
        fields = [
            "subject",
            "body_html",
            "body_text",
            "preview_text",
            "from_name",
            "from_email",
            "ccRecipients",
            "bccRecipients",
            "toRecipients",
            "conversation_id",
            "internet_message_id",
            "received_at",
            "importance",
            "is_read",
            "has_attachments",
            "updated_at",
        ]
        Email.objects.bulk_update(emails, fields)

    # -------------------- attachments --------------------

    def _sync_attachments(self, account, access_token, new_count):
        """Placeholder hook; real downloads run as a background task.

        Kept intentionally light - binary attachment fetching is handled by the
        ``download_attachment`` task to avoid blocking the sync call.
        """
        return None

    def download_attachment(self, attachment_id):
        """
        Download a single attachment's binary content.

        Returns True on success, False on failure. Idempotent.
        """
        attachment = self.sync_repository.get_attachment(attachment_id)
        account = attachment.email.outlook_account
        access_token = self.auth_service.get_valid_access_token(account)
        if not access_token:
            return False
        content = self.graph.download_attachment(
            access_token, attachment.email.graph_message_id, attachment.graph_attachment_id
        )
        if content is None:
            self.sync_repository.store_attachment_content(
                attachment, None, is_downloaded=False, error="Graph download failed"
            )
            return False
        self.sync_repository.store_attachment_content(attachment, content)
        return True

    # -------------------- token / webhook maintenance --------------------

    def refresh_expired_tokens(self, worker=""):
        """Refresh tokens for all accounts whose access tokens are expired."""
        from portal.models import OAuthToken

        refreshed, failed = 0, 0
        for token in OAuthToken.objects.select_related("account").filter(
            account__is_sync_paused=False
        ):
            account = token.account
            if not token.is_expired():
                continue
            access_token = self.auth_service.refresh_token(account)
            if access_token:
                refreshed += 1
            else:
                failed += 1
        logger.info("Token refresh: %s ok, %s failed", refreshed, failed)
        return refreshed, failed

    def renew_webhooks(self, worker=""):
        """Renew expiring Graph subscriptions before they lapse."""
        from datetime import timedelta

        renewed, failed = 0, 0
        for subscription in self.subscription_repository.list_expiring():
            account = subscription.account
            access_token = self.auth_service.get_valid_access_token(account)
            if not access_token:
                failed += 1
                self.subscription_repository.mark_expired(subscription)
                continue
            new_expiration = timezone.now() + timedelta(
                days=settings.SYNC_WEBHOOK_EXPIRATION_DAYS
            )
            if self.graph.renew_subscription(
                access_token, subscription.subscription_id, new_expiration
            ):
                self.subscription_repository.update_subscription(
                    subscription, expiration_date_time=new_expiration, status="active"
                )
                renewed += 1
            else:
                failed += 1
        logger.info("Webhook renew: %s ok, %s failed", renewed, failed)
        return renewed, failed

    # -------------------- bookkeeping --------------------

    def _has_active_subscription(self, account):
        return self.subscription_repository.list_active(account=account).exists()

    def _record_success(self, account, result, log, start, worker):
        end = timezone.now()
        self.sync_repository.update_state(
            self.sync_repository.get_or_create_state(account),
            last_error="",
        )
        self.auth_repository.update_account(
            account,
            status="active",
            oauth_status="connected",
            sync_error="",
            last_sync_at=end,
            last_successful_sync_at=end,
            total_emails_synced=account.emails.count(),
        )
        log.status = "completed"
        log.end_time = end
        log.duration_seconds = (end - start).total_seconds()
        log.emails_processed = result.processed
        log.emails_added = result.added
        log.emails_updated = result.updated
        log.attachments_downloaded = result.attachments_downloaded
        log.save(update_fields=[
            "status", "end_time", "duration_seconds",
            "emails_processed", "emails_added", "emails_updated",
            "attachments_downloaded",
        ])

    def _record_failure(self, account, result, log, start, worker):
        end = timezone.now()
        self.auth_repository.update_account(
            account,
            status="error",
            sync_error=result.error[:MAX_SYNC_ERROR_LEN],
            last_sync_at=end,
        )
        log.status = "failed"
        log.end_time = end
        log.duration_seconds = (end - start).total_seconds()
        log.error = result.error[:MAX_SYNC_ERROR_LEN]
        log.emails_processed = result.processed
        log.emails_added = result.added
        log.emails_updated = result.updated
        log.retry_count = self.sync_repository.get_or_create_state(account).consecutive_failures
        log.save(update_fields=[
            "status", "end_time", "duration_seconds", "error",
            "emails_processed", "emails_added", "emails_updated", "retry_count",
        ])

    def _update_health(self, account, oauth_ok=False, graph_ok=False, webhook_ok=None, error=""):
        health = self.subscription_repository.get_or_create_health(account)
        if graph_ok and oauth_ok:
            self.subscription_repository.update_health(
                health,
                oauth_ok=True,
                graph_ok=True,
                webhook_ok=webhook_ok if webhook_ok is not None else health.webhook_ok,
                last_checked_at=timezone.now(),
                consecutive_failures=0,
                last_error="",
            )
        else:
            self.subscription_repository.update_health(
                health,
                oauth_ok=oauth_ok,
                graph_ok=graph_ok,
                webhook_ok=webhook_ok if webhook_ok is not None else health.webhook_ok,
                last_checked_at=timezone.now(),
                consecutive_failures=health.consecutive_failures + 1,
                last_error=error[:MAX_SYNC_ERROR_LEN],
            )

    # -------------------- metrics --------------------

    def sync_metrics(self):
        """Dashboard metrics computed with aggregate queries."""
        from django.db.models import Count, Q, Sum

        from portal.models import Notification, SyncJob, SyncLog

        accounts = OutlookAccount.objects.all()
        logs = SyncLog.objects.filter(
            start_time__gte=timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        )
        return {
            "total_accounts": accounts.count(),
            "active_accounts": accounts.filter(status="active").count(),
            "paused_accounts": accounts.filter(is_sync_paused=True).count(),
            "needs_reauthorization": accounts.filter(oauth_status__in=["revoked", "expired"]).count(),
            "total_syncs": SyncLog.objects.count(),
            "successful_syncs": SyncLog.objects.filter(status="completed").count(),
            "failed_syncs": SyncLog.objects.filter(status="failed").count(),
            "emails_synced_today": Email.objects.filter(
                updated_at__gte=timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
            ).count(),
            "queued_jobs": SyncJob.objects.filter(status="queued").count(),
            "running_jobs": SyncJob.objects.filter(status="running").count(),
            "failed_jobs": SyncJob.objects.filter(status="failed").count(),
            "unread_notifications": Notification.objects.filter(is_read=False).count(),
            "last_sync": SyncLog.objects.order_by("-start_time").values_list(
                "start_time", flat=True
            ).first(),
            "next_scheduled_sync": timezone.now() + timedelta(
                seconds=getattr(settings, "SYNC_INTERVAL_SECONDS", 300)
            ),
        }