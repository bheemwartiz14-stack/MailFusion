from django.urls import path
from portal.views.accounts_views import AccountsAddView, AccountsCallbackView, AccountsDisconnectConfirmView, AccountsDisconnectView, AccountsListView, AccountsPauseView, AccountsReconnectView, AccountsRenameView, AccountsResumeView, AccountsSyncAllView, AccountsSyncView
from portal.views.audit_views import AuditLogExportView, AuditLogsView
from portal.views.auth_views import LoginView, LogoutView, PasswordChangeDoneView, PasswordChangeView, PasswordResetCompleteView, PasswordResetConfirmView, PasswordResetDoneView, PasswordResetView, ProfileView
from portal.views.dashboard_view import DashboardView
from portal.views.error_views import error_403, error_404, error_500, maintenance
from portal.views.inbox_module_views import (
    AttachmentDownloadAllView, AttachmentDownloadView, AttachmentPreviewView,
    ComposeSubmitView, EmailActionView,
    EmailDetailView, EmailDownloadEmlView, EmailHeadersPartialView, EmailListView,
    EmailPreviewPartialView, EmailThreadPartialView, InboxView, UnreadCountPartialView,
)
from portal.views.notification_views import NotificationActionView, NotificationBulkActionView, NotificationsView
from portal.views.sync import sync_api
from portal.views.system_monitor_views import (
    AccountDetailView, HealthPartialView, OAuthStatusView, QueueStatusView,
    SyncLogDetailView, SyncLogsPartialView, SyncLogsView, SystemHealthView,
    SystemMonitorPartialView, SystemMonitorView,
)




urlpatterns = [
     path("api/sync/", sync_api, name="sync-api"),
    # auth - Django built-in views, custom Bootstrap templates
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path("forgot-password/", PasswordResetView.as_view(), name="password_reset"),
    path("forgot-password/done/", PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset-password/<uidb64>/<token>/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset-password/<uidb64>/set-password/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset-password/complete/", PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("change-password/", PasswordChangeView.as_view(), name="change_password"),
    path("change-password/done/", PasswordChangeDoneView.as_view(), name="password_change_done"),
    path("profile/", ProfileView.as_view(), name="profile"),
    # dashboard
    path("", DashboardView.as_view(), name="dashboard"),
    # accounts
    path("accounts/", AccountsListView.as_view(), name="accounts"),
    path("accounts/connect/", AccountsAddView.as_view(), name="accounts_connect"),
    path("accounts/callback/", AccountsCallbackView.as_view(), name="accounts_callback"),
    path("accounts/<uuid:account_id>/reconnect/", AccountsReconnectView.as_view(), name="accounts_reconnect"),
    path("accounts/<uuid:account_id>/disconnect/", AccountsDisconnectConfirmView.as_view(), name="accounts_disconnect_confirm"),
    path("accounts/<uuid:account_id>/disconnect/confirm/", AccountsDisconnectView.as_view(), name="accounts_disconnect"),
    path("accounts/<uuid:account_id>/sync/", AccountsSyncView.as_view(), name="accounts_sync"),
    path("accounts/sync-all/", AccountsSyncAllView.as_view(), name="accounts_sync_all"),
    path("accounts/<uuid:account_id>/pause/", AccountsPauseView.as_view(), name="accounts_pause"),
    path("accounts/<uuid:account_id>/resume/", AccountsResumeView.as_view(), name="accounts_resume"),
    path("accounts/<uuid:account_id>/rename/", AccountsRenameView.as_view(), name="accounts_rename"),
    path("accounts/<uuid:account_id>/", AccountDetailView.as_view(), name="account_detail"),
    # emails - unified inbox module
    path("inbox/", InboxView.as_view(), name="inbox"),
    path("inbox/list/", EmailListView.as_view(), name="inbox_list"),
    path("inbox/unread/", UnreadCountPartialView.as_view(), name="inbox_unread"),
    path("inbox/actions/", EmailActionView.as_view(), name="email_action"),
    path("inbox/emails/<uuid:email_id>/", EmailDetailView.as_view(), name="email_detail"),
    path("inbox/emails/<uuid:email_id>/preview/", EmailPreviewPartialView.as_view(), name="email_preview"),
    path("inbox/emails/<uuid:email_id>/download-eml/", EmailDownloadEmlView.as_view(), name="email_download_eml"),
    path("inbox/emails/<uuid:email_id>/thread/", EmailThreadPartialView.as_view(), name="email_thread"),
    path("inbox/emails/<uuid:email_id>/headers/", EmailHeadersPartialView.as_view(), name="email_headers"),
    path("inbox/emails/<uuid:email_id>/attachments/download-all/", AttachmentDownloadAllView.as_view(), name="attachment_download_all"),
    path("inbox/emails/<uuid:email_id>/attachments/<uuid:attachment_id>/download/", AttachmentDownloadView.as_view(), name="attachment_download"),
    path("inbox/emails/<uuid:email_id>/attachments/<uuid:attachment_id>/preview/", AttachmentPreviewView.as_view(), name="attachment_preview"),
    # compose / reply
    path("compose/submit/", ComposeSubmitView.as_view(), name="compose_submit"),
    # notifications
    path("notifications/", NotificationsView.as_view(), name="notifications"),
    path("notifications/<uuid:notification_id>/toggle/", NotificationActionView.as_view(), kwargs={"action": "toggle"}, name="notification_toggle"),
    path("notifications/<uuid:notification_id>/delete/", NotificationActionView.as_view(), kwargs={"action": "delete"}, name="notification_delete"),
    path("notifications/read-all/", NotificationActionView.as_view(), kwargs={"action": "mark_all_read"}, name="notifications_read_all"),
    path("notifications/bulk/", NotificationBulkActionView.as_view(), name="notifications_bulk"),
    # audit logs
    path("audit-logs/", AuditLogsView.as_view(), name="audit_logs"),
    path("audit-logs/export/", AuditLogExportView.as_view(), name="audit_logs_export"),
    # system monitor (renamed from /sync/)
    path("system-monitor/", SystemMonitorView.as_view(), name="sync_dashboard"),
    path("system-monitor/dashboard/stats/", SystemMonitorPartialView.as_view(), name="sync_dashboard_stats"),
    path("system-monitor/logs/", SyncLogsView.as_view(), name="sync_logs"),
    path("system-monitor/logs/partial/", SyncLogsPartialView.as_view(), name="sync_logs_partial"),
    path("system-monitor/logs/<uuid:pk>/", SyncLogDetailView.as_view(), name="sync_log_detail"),
    path("system-monitor/health/", SystemHealthView.as_view(), name="sync_health"),
    path("system-monitor/health/partial/", HealthPartialView.as_view(), name="sync_health_partial"),
    path("system-monitor/queue/", QueueStatusView.as_view(), name="sync_queue"),
    path("system-monitor/oauth/", OAuthStatusView.as_view(), name="sync_oauth"),
    # errors (development preview)
    path("403/", error_403, name="preview_403"),
    path("404/", error_404, name="preview_404"),
    path("500/", error_500, name="preview_500"),
    path("maintenance/", maintenance, name="preview_maintenance"),
]

# Production error handlers (for DEBUG=False)
handler403 = "portal.views.error_403"
handler404 = "portal.views.error_404"
handler500 = "portal.views.error_500"
