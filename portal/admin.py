"""
Django Admin customization for Portal.

Reuses Django's built-in User and Group admins 1:1 and only tweaks
usability (search, filters, list display, ordering). The authorization
model (Users / Groups / Permissions / Content Types) is untouched and is
managed through this same admin - no custom roles or permission seeders.
"""

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group, User

from .models import (
    AccountHealth,
    Attachment,
    AttachmentDownloadJob,
    AuditLog,
    Email,
    EmailSyncState,
    GraphSubscription,
    Notification,
    OAuthToken,
    OutlookAccount,
    SyncJob,
    SyncLog,
)


class PortalUserAdmin(UserAdmin):
    list_display = (
        "username",
        "email",
        "first_name",
        "last_name",
        "is_staff",
        "is_active",
        "last_login",
    )
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "date_joined")
    search_fields = ("username", "email", "first_name", "last_name")
    ordering = ("-date_joined",)


class PortalGroupAdmin(GroupAdmin):
    list_display = ("name", "get_user_count")
    search_fields = ("name",)
    ordering = ("name",)

    @admin.display(description="Users")
    def get_user_count(self, obj):
        return obj.user_set.count()


admin.site.unregister(User)
admin.site.register(User, PortalUserAdmin)

admin.site.unregister(Group)
admin.site.register(Group, PortalGroupAdmin)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "tone", "is_read", "created_at")
    list_filter = ("is_read", "tone")
    search_fields = ("title", "detail")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "actor", "action", "target", "status")
    list_filter = ("status", "action")
    search_fields = ("actor", "action", "target", "ip")
    ordering = ("-timestamp",)
    readonly_fields = ("timestamp",)
    date_hierarchy = "timestamp"


@admin.register(OutlookAccount)
class OutlookAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "user", "status", "oauth_status", "is_default", "last_sync_at", "created_at")
    list_filter = ("status", "oauth_status", "is_default", "created_at")
    search_fields = ("name", "email", "nickname", "user__username", "user__email")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "last_sync_at")
    date_hierarchy = "created_at"
    raw_id_fields = ("user",)


@admin.register(OAuthToken)
class OAuthTokenAdmin(admin.ModelAdmin):
    list_display = ("account", "token_type", "expires_at", "created_at")
    list_filter = ("token_type", "created_at")
    search_fields = ("account__email", "account__name")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at", "access_token_encrypted", "refresh_token_encrypted", "id_token_encrypted")
    date_hierarchy = "created_at"
    raw_id_fields = ("account",)


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ("subject", "from_email", "outlook_account", "folder", "is_read", "received_at")
    list_filter = ("folder", "is_read", "importance", "received_at")
    search_fields = ("subject", "from_email", "from_name", "graph_message_id")
    ordering = ("-received_at",)
    readonly_fields = ("created_at", "updated_at")
    date_hierarchy = "received_at"
    raw_id_fields = ("outlook_account",)


@admin.register(EmailSyncState)
class EmailSyncStateAdmin(admin.ModelAdmin):
    list_display = ("account", "last_sync_started_at", "last_successful_sync_at", "consecutive_failures")
    search_fields = ("account__email", "account__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(GraphSubscription)
class GraphSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("subscription_id", "account", "resource", "status", "expiration_date_time")
    list_filter = ("status", "change_type")
    search_fields = ("subscription_id", "account__email", "resource")
    ordering = ("-created_at",)
    raw_id_fields = ("account",)


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "content_type", "size_bytes", "is_downloaded", "is_inline")
    list_filter = ("is_downloaded", "is_inline", "content_type")
    search_fields = ("name", "email__subject")
    raw_id_fields = ("email",)


@admin.register(AttachmentDownloadJob)
class AttachmentDownloadJobAdmin(admin.ModelAdmin):
    list_display = ("attachment", "status", "attempts", "finished_at", "error")
    list_filter = ("status",)
    search_fields = ("attachment__name",)


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("start_time", "account", "status", "emails_processed", "emails_added", "emails_updated", "duration_seconds")
    list_filter = ("status", "start_time")
    search_fields = ("account__email", "account__name", "worker")
    ordering = ("-start_time",)
    readonly_fields = ("start_time", "created_at")
    date_hierarchy = "start_time"
    raw_id_fields = ("account",)


@admin.register(SyncJob)
class SyncJobAdmin(admin.ModelAdmin):
    list_display = ("created_at", "job_type", "account", "priority", "status", "attempts", "task_id")
    list_filter = ("job_type", "status", "created_at")
    search_fields = ("account__email", "task_id")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")
    raw_id_fields = ("account",)


@admin.register(AccountHealth)
class AccountHealthAdmin(admin.ModelAdmin):
    list_display = ("account", "oauth_ok", "graph_ok", "webhook_ok", "consecutive_failures", "last_checked_at")
    list_filter = ("oauth_ok", "graph_ok", "webhook_ok")
    search_fields = ("account__email",)
    raw_id_fields = ("account",)
