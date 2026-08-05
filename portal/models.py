"""
Portal models.

Authentication and authorization intentionally use Django's default User and
Django's built-in authorization framework (Users / Groups / Permissions /
Content Types) - no custom user model, no custom RBAC.

The Portal app adds four application tables:
    Notification   - the notification center (manageable from the UI)
    AuditLog       - the audit trail (read-only trail of system actions)
    OutlookAccount - connected Microsoft mailboxes
    OAuthToken     - encrypted Microsoft Graph OAuth tokens

Neither touches Django's authentication or authorization model.

Primary keys for custom application models are UUIDs (see the project
standard). Django's built-in models (auth / admin / sessions / etc.) are
never modified.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class Notification(models.Model):
    """A single entry in the notification center."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=120)
    detail = models.CharField(max_length=255, blank=True)
    icon = models.CharField(max_length=40, blank=True, default="bi-bell")
    tone = models.CharField(max_length=20, default="primary")
    is_read = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ("-created_at",)
    def __str__(self):
        return self.title


class AuditLog(models.Model):
    """An immutable-ish audit trail entry (managed via Admin / read-only UI)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    actor = models.CharField(max_length=120, blank=True)
    action = models.CharField(max_length=120, db_index=True)
    target = models.CharField(max_length=255, blank=True)
    ip = models.CharField(max_length=45, blank=True)
    status = models.CharField(max_length=20, default="success", db_index=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    class Meta:
        ordering = ("-timestamp",)
    def __str__(self):
        return f"{self.action} ({self.target})"


class OutlookAccount(models.Model):
    """A connected Microsoft mailbox (Outlook/Exchange via Microsoft Graph)."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("error", "Error"),
        ("paused", "Paused"),
    ]

    OAUTH_STATUS_CHOICES = [
        ("connected", "Connected"),
        ("expired", "Expired"),
        ("revoked", "Revoked"),
        ("pending", "Pending"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="outlook_accounts",
    )
    name = models.CharField(max_length=120)
    email = models.EmailField(max_length=254)
    nickname = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    microsoft_user_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
    oauth_status = models.CharField(max_length=20, choices=OAUTH_STATUS_CHOICES, default="pending", db_index=True)
    is_default = models.BooleanField(default=True)
    is_sync_paused = models.BooleanField(default=False)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    total_emails_synced = models.PositiveIntegerField(default=0)
    sync_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        unique_together = [("user", "email")]

    def __str__(self):
        return f"{self.name} ({self.email})"

    @property
    def unread_count(self):
        """Number of unread emails synced for this account."""
        return self.emails.filter(is_read=False).count()

    @property
    def is_healthy(self):
        """Healthy when OAuth is connected and last sync succeeded."""
        return (
            self.oauth_status == "connected"
            and self.status != "error"
            and self.last_successful_sync_at is not None
        )


class OAuthToken(models.Model):
    """Encrypted storage for Microsoft Graph OAuth tokens."""

    TOKEN_TYPE_CHOICES = [
        ("access", "Access Token"),
        ("refresh", "Refresh Token"),
        ("id", "ID Token"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.OneToOneField(
        OutlookAccount,
        on_delete=models.CASCADE,
        related_name="oauth_token",
    )
    # Tokens are encrypted before storage - never store plaintext
    access_token_encrypted = models.TextField()
    refresh_token_encrypted = models.TextField(blank=True)
    id_token_encrypted = models.TextField(blank=True)
    token_type = models.CharField(max_length=20, default="Bearer")
    scope = models.TextField(blank=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Tokens for {self.account.email}"

    def is_expired(self):
        """Check if the access token is expired (with 60s buffer)."""
        return timezone.now() >= (self.expires_at - timezone.timedelta(seconds=60))


class EmailRecipient(models.Model):
    """A single TO/CC/BCC recipient resolved from a message."""

    class Type(models.TextChoices):
        TO = "to", "To"
        CC = "cc", "Cc"
        BCC = "bcc", "Bcc"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.ForeignKey(
        "Email", on_delete=models.CASCADE, related_name="recipients"
    )
    recipient_type = models.CharField(max_length=10, choices=Type.choices, db_index=True)
    name = models.CharField(max_length=255, blank=True)
    address = models.EmailField(max_length=254)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position",)
        indexes = [
            models.Index(fields=["email", "recipient_type"]),
            models.Index(fields=["address"]),
        ]

    def __str__(self):
        return f"{self.recipient_type}: {self.address}"


class Category(models.Model):
    """A user-defined label/category that can be applied to emails."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="categories"
    )
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=20, default="primary")
    icon = models.CharField(max_length=40, blank=True, default="bi-tag")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        unique_together = [("user", "name")]

    def __str__(self):
        return self.name


class Tag(models.Model):
    """A user-defined tag (lighter weight than Category)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="tags"
    )
    name = models.CharField(max_length=80)
    color = models.CharField(max_length=20, default="neutral")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("name",)
        unique_together = [("user", "name")]

    def __str__(self):
        return self.name


class Email(models.Model):
    class Importance(models.TextChoices):
        LOW = "low", "Low"
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    outlook_account = models.ForeignKey("OutlookAccount", on_delete=models.CASCADE, related_name="emails")
    graph_message_id = models.TextField()
    subject = models.CharField( max_length=998, blank=True,)
    body_html = models.TextField( blank=True,)
    body_text = models.TextField(blank=True, help_text="Plain-text version of the body")
    preview_text = models.CharField(max_length=255, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    from_email = models.EmailField(max_length=254, blank=True)
    ccRecipients = models.TextField(blank=True, help_text="Comma-separated list of CC recipients")
    bccRecipients = models.TextField(blank=True, help_text="Comma-separated list of BCC recipients")
    toRecipients = models.TextField(blank=True, help_text="Comma-separated list of TO recipients")
    reply_to = models.TextField(blank=True, help_text="Comma-separated reply-to addresses")
    conversation_id = models.TextField(blank=True, db_index=True)
    internet_message_id = models.TextField(blank=True, db_index=True)
    in_reply_to = models.TextField(blank=True)
    thread_count = models.PositiveIntegerField(default=1)
    has_attachments = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    received_at = models.DateTimeField(db_index=True)
    importance = models.CharField(max_length=10, choices=Importance.choices, default=Importance.NORMAL)
    is_read = models.BooleanField(default=False, db_index=True)
    is_starred = models.BooleanField(default=False, db_index=True)
    is_flagged = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    is_draft = models.BooleanField(default=False, db_index=True)
    is_sent = models.BooleanField(default=False, db_index=True)
    folder = models.CharField(max_length=60, default="Inbox", db_index=True)
    categories = models.ManyToManyField(Category, blank=True, related_name="emails")
    tags = models.ManyToManyField(Tag, blank=True, related_name="emails")

    class Meta:
        db_table = "portal_email"
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["outlook_account", "graph_message_id"],
                name="uniq_account_graph_message",
            ),
        ]
        indexes = [
            models.Index(fields=["outlook_account", "received_at"]),
            models.Index(fields=["outlook_account", "is_read"]),
            models.Index(fields=["outlook_account", "folder", "received_at"]),
            models.Index(fields=["outlook_account", "conversation_id"]),
            models.Index(fields=["outlook_account", "is_draft", "updated_at"]),
            models.Index(fields=["outlook_account", "is_sent", "received_at"]),
            models.Index(fields=["conversation_id", "received_at"]),
        ]
    def __str__(self) -> str:
        return f"Email {self.subject} ({self.graph_message_id})"

    @property
    def sender_display(self):
        return self.from_name or self.from_email or "Unknown sender"


class EmailSyncState(models.Model):
    """Per-account state for incremental (delta) email synchronization."""

    account = models.OneToOneField(
        OutlookAccount, on_delete=models.CASCADE, related_name="sync_state"
    )
    delta_link = models.TextField(blank=True)
    last_sync_started_at = models.DateTimeField(null=True, blank=True)
    last_sync_completed_at = models.DateTimeField(null=True, blank=True)
    last_successful_sync_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"SyncState for {self.account}"


class GraphSubscription(models.Model):
    """Microsoft Graph Change Notification (webhook) subscription."""

    STATUS_CHOICES = [
        ("active", "Active"),
        ("expiring", "Expiring"),
        ("expired", "Expired"),
        ("error", "Error"),
    ]

    CHANGETYPE_CHOICES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("deleted", "Deleted"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        OutlookAccount, on_delete=models.CASCADE, related_name="graph_subscriptions"
    )
    subscription_id = models.CharField(max_length=120, db_index=True)
    resource = models.CharField(max_length=255)
    change_type = models.CharField(max_length=20, choices=CHANGETYPE_CHOICES, default="created")
    notification_url = models.CharField(max_length=255)
    client_state = models.CharField(max_length=255, blank=True)
    expiration_date_time = models.DateTimeField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        return f"Subscription {self.subscription_id} ({self.account})"

    @property
    def expires_soon(self):
        from django.utils import timezone
        from datetime import timedelta
        return self.expiration_date_time - timezone.now() < timedelta(days=1)


class Attachment(models.Model):
    """Metadata (and optional binary content) for a synced email attachment."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.ForeignKey(
        Email,
        on_delete=models.CASCADE,
        related_name="attachments",
        related_query_name="email_attachment",
    )
    graph_attachment_id = models.CharField(max_length=120, db_index=True)
    name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.BigIntegerField(default=0)
    content_id = models.CharField(max_length=255, blank=True)
    is_inline = models.BooleanField(default=False)
    content = models.BinaryField(null=True, blank=True)
    is_downloaded = models.BooleanField(default=False)
    download_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=["email", "graph_attachment_id"],
                name="uniq_email_graph_attachment",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.email})"


class SyncLog(models.Model):
    """A single synchronization run for an account."""

    STATUS_CHOICES = [
        ("started", "Started"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        OutlookAccount, on_delete=models.CASCADE, related_name="sync_logs"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="started", db_index=True)
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.FloatField(null=True, blank=True)
    emails_processed = models.PositiveIntegerField(default=0)
    emails_added = models.PositiveIntegerField(default=0)
    emails_updated = models.PositiveIntegerField(default=0)
    attachments_downloaded = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    worker = models.CharField(max_length=120, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-start_time",)
        indexes = [
            models.Index(fields=["account", "-start_time"]),
        ]

    def __str__(self):
        return f"SyncLog {self.account} [{self.status}]"


class SyncJob(models.Model):
    """Queue/metadata record for a background Celery job."""

    JOB_TYPE_CHOICES = [
        ("sync", "Sync"),
        ("refresh_token", "Refresh Token"),
        ("download_attachments", "Download Attachments"),
        ("renew_webhook", "Renew Webhook"),
        ("health_check", "Health Check"),
    ]

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("running", "Running"),
        ("succeeded", "Succeeded"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        OutlookAccount,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sync_jobs",
    )
    job_type = models.CharField(max_length=30, choices=JOB_TYPE_CHOICES, db_index=True)
    priority = models.IntegerField(default=5, db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    task_id = models.CharField(max_length=120, blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True, db_index=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    result = models.TextField(blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-priority", "scheduled_at", "created_at")

    def __str__(self):
        return f"{self.job_type} [{self.status}]"


class AttachmentDownloadJob(models.Model):
    """Background job to fetch a single attachment's binary content."""

    STATUS_CHOICES = [
        ("queued", "Queued"),
        ("downloading", "Downloading"),
        ("downloaded", "Downloaded"),
        ("failed", "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attachment = models.ForeignKey(
        Attachment, on_delete=models.CASCADE, related_name="download_jobs"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="queued", db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    max_attempts = models.PositiveIntegerField(default=3)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return f"Attachment job for {self.attachment} [{self.status}]"


class AccountHealth(models.Model):
    """Rollup of infrastructure health for a single account."""

    account = models.OneToOneField(
        OutlookAccount, on_delete=models.CASCADE, related_name="health"
    )
    oauth_ok = models.BooleanField(default=False)
    graph_ok = models.BooleanField(default=False)
    webhook_ok = models.BooleanField(default=False)
    last_checked_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        status = "healthy" if (self.oauth_ok and self.graph_ok) else "unhealthy"
        return f"Health[{status}] for {self.account}"