"""
Portal shared base view and demo data.

PortalView (and PortalContextMixin) inject the app shell context — navbar,
sidebar, current user, notification center, page title/breadcrumbs — into
every page. The demo data lives here so templates render with realistic
content until real APIs are wired up.

This module contains NO business logic.
"""

import datetime

from django.views.generic import TemplateView

APP_NAME = "MailFusion Enterprise"
APP_VERSION = "1.0.0"

NOW = datetime.datetime.now(datetime.timezone.utc)


def days_ago(days, hours=0):
    return NOW - datetime.timedelta(days=days, hours=hours)


# ---------------------------------------------------------------- shell data

USER = {
    "name": "Alex Morgan",
    "email": "alex.morgan@acme.io",
    "initials": "AM",
    "role": "Administrator",
    "avatar_hue": "primary",
}

SIDEBAR_NAV = [
    {"label": "Dashboard", "icon": "bi-grid-1x2-fill", "url": "/"},
    {
        "label": "Outlook Accounts",
        "icon": "bi-envelope-paper-fill",
        "url": "/accounts/",
    },
    {
        "label": "Unified Inbox",
        "icon": "bi-inbox-fill",
        "url": "/inbox/",
    },
    {
        "label": "Notifications",
        "icon": "bi-bell-fill",
        "url": "/notifications/",
    },
]

SIDEBAR_TOOLS = [
    {
        "label": "Audit Logs",
        "icon": "bi-journal-text",
        "url": "/audit-logs/",
    },
    {
        "label": "Sync Dashboard",
        "icon": "bi-arrow-repeat",
        "url": "/sync/",
    },
    {
        "label": "Sync Logs",
        "icon": "bi-list-check",
        "url": "/sync/logs/",
    },
    {
        "label": "Health & Queue",
        "icon": "bi-heart-pulse",
        "url": "/sync/health/",
    },
]

NOTIFICATION_CENTER = [
    {
        "title": "OAuth token refreshed",
        "detail": "work@acme.io refreshed successfully",
        "time": "2 min ago",
        "icon": "bi-check-circle-fill",
        "tone": "success",
    },
    {
        "title": "Sync failed for 1 account",
        "detail": "sales@acme.io - 2 retries remaining",
        "time": "18 min ago",
        "icon": "bi-exclamation-triangle-fill",
        "tone": "danger",
    },
    {
        "title": "New unread batch",
        "detail": "12 new messages in Unified Inbox",
        "time": "1 hr ago",
        "icon": "bi-envelope-fill",
        "tone": "primary",
    },
    {
        "title": "OTP login detected",
        "detail": "New device in San Francisco, CA",
        "time": "3 hrs ago",
        "icon": "bi-shield-lock-fill",
        "tone": "warning",
    },
]


# ---------------------------------------------------------------- demo data

ACCOUNTS = [
    {
        "id": 1,
        "name": "Work Email",
        "email": "alex.morgan@acme.io",
        "nickname": "Work",
        "status": "active",
        "last_sync": days_ago(0, 0.2),
        "unread": 12,
        "oauth": "connected",
        "fails": 0,
    },
    {
        "id": 2,
        "name": "Sales Inbox",
        "email": "sales@acme.io",
        "nickname": "Sales",
        "status": "error",
        "last_sync": days_ago(0, 1.5),
        "unread": 8,
        "oauth": "expired",
        "fails": 2,
    },
    {
        "id": 3,
        "name": "Personal",
        "email": "alex.morgan@outlook.com",
        "nickname": "Personal",
        "status": "active",
        "last_sync": days_ago(0, 0.6),
        "unread": 5,
        "oauth": "connected",
        "fails": 0,
    },
    {
        "id": 4,
        "name": "Support Queue",
        "email": "support@acme.io",
        "nickname": "Support",
        "status": "paused",
        "last_sync": days_ago(2),
        "unread": 0,
        "oauth": "connected",
        "fails": 0,
    },
    {
        "id": 5,
        "name": "Billing Team",
        "email": "billing@acme.io",
        "nickname": "Billing",
        "status": "active",
        "last_sync": days_ago(0, 3.1),
        "unread": 1,
        "oauth": "connected",
        "fails": 0,
    },
]

EMAILS = [
    {
        "id": 1001,
        "sender": "Priya Sharma",
        "sender_email": "priya.sharma@northwind.io",
        "subject": "Q3 product roadmap review",
        "preview": "Hi Alex, attaching the draft roadmap for Q3. The timeline on the partner migration item changed...",
        "date": days_ago(0, 0.1),
        "attachments": 2,
        "read": False,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": True,
    },
    {
        "id": 1002,
        "sender": "GitHub",
        "sender_email": "notifications@github.com",
        "subject": "[acme/mailfusion] PR #482: Bump bootstrap-icons",
        "preview": "dependabot[bot] wants to merge 1 commit into main from dependabot/npm_and_yarn...",
        "date": days_ago(0, 0.3),
        "attachments": 0,
        "read": False,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1003,
        "sender": "Daniel Okafor",
        "sender_email": "daniel.okafor@contoso.com",
        "subject": "Invoice #INV-2041 due next week",
        "preview": "Attached is the invoice for the infrastructure services provided in July. Payment terms 30 days...",
        "date": days_ago(0, 0.9),
        "attachments": 1,
        "read": False,
        "account": "Billing Team",
        "account_hue": "success",
        "folder": "inbox",
        "important": True,
    },
    {
        "id": 1004,
        "sender": "Maya Chen",
        "sender_email": "maya.chen@fabrikam.com",
        "subject": "Re: Partnership agreement review",
        "preview": "Looks good from our side. One small edit in section 4.2 around data retention, otherwise we can...",
        "date": days_ago(1),
        "attachments": 0,
        "read": True,
        "account": "Sales Inbox",
        "account_hue": "info",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1005,
        "sender": "AWS Billing",
        "sender_email": "aws-billing@amazon.com",
        "subject": "Your AWS invoice for July is ready",
        "preview": "View and download your July invoice. Total for this billing period $4,231.80...",
        "date": days_ago(1),
        "attachments": 0,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1006,
        "sender": "Sofia Reyes",
        "sender_email": "sofia.reyes@adatum.com",
        "subject": "Meeting notes - Sync architecture call",
        "preview": "Thanks everyone for joining. Key decisions: incremental sync every 5 min, full sync nightly...",
        "date": days_ago(1, 4),
        "attachments": 3,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1007,
        "sender": "Liam Carter",
        "sender_email": "liam.carter@proseware.com",
        "subject": "Security audit checklist",
        "preview": "Please complete the attached checklist before Friday's review. Focus on the OAuth token storage...",
        "date": days_ago(2),
        "attachments": 1,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": True,
    },
    {
        "id": 1008,
        "sender": "Olivia Bennett",
        "sender_email": "olivia@lucernepub.com",
        "subject": "Draft blog post for review",
        "preview": "Hi Alex, here's the draft on building email aggregators with Microsoft Graph. Would love your...",
        "date": days_ago(2, 6),
        "attachments": 1,
        "read": False,
        "account": "Personal",
        "account_hue": "warning",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1009,
        "sender": "Stripe",
        "sender_email": "billing@stripe.com",
        "subject": "Receipt for your recent payment",
        "preview": "You paid $49.00 to Portal. Receipt attached for your records...",
        "date": days_ago(3),
        "attachments": 1,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1010,
        "sender": "Nina Petrov",
        "sender_email": "nina.petrov@wingtiptoys.com",
        "subject": "Quarterly OKR check-in",
        "preview": "Booking 30 minutes for next week to go over the team OKRs. Please pick a slot in the calendar...",
        "date": days_ago(3, 2),
        "attachments": 0,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1011,
        "sender": "Zoom Notifications",
        "sender_email": "no-reply@zoom.us",
        "subject": "Cloud recording is ready",
        "preview": "Your recording for 'Portal Architecture Review' is ready to view. Link expires in 14 days...",
        "date": days_ago(4),
        "attachments": 0,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "inbox",
        "important": False,
    },
    {
        "id": 1012,
        "sender": "HR Team",
        "sender_email": "hr@acme.io",
        "subject": "Updated benefits guide 2026",
        "preview": "The 2026 benefits guide is now available. Notable changes to the health savings account...",
        "date": days_ago(5),
        "attachments": 2,
        "read": True,
        "account": "Work Email",
        "account_hue": "primary",
        "folder": "archive",
        "important": False,
    },
    {
        "id": 1013,
        "sender": "Marcus Webb",
        "sender_email": "marcus.webb@tailspintoys.com",
        "subject": "Great demo yesterday",
        "preview": "The team loved the unified inbox demo. When can we discuss a pilot rollout for Q4? ...",
        "date": days_ago(6),
        "attachments": 0,
        "read": True,
        "account": "Sales Inbox",
        "account_hue": "info",
        "folder": "archive",
        "important": False,
    },
]

FOLDERS = [
    {"label": "Inbox", "icon": "bi-inbox", "count": 26, "url": "/inbox/"},
    {"label": "Starred", "icon": "bi-star", "count": 7, "url": "/inbox/?folder=starred"},
    {"label": "Sent", "icon": "bi-send", "count": 214, "url": "/inbox/?folder=sent"},
    {"label": "Drafts", "icon": "bi-pencil", "count": 3, "url": "/inbox/?folder=drafts"},
    {"label": "Archive", "icon": "bi-archive", "count": 1_204, "url": "/inbox/?folder=archive"},
    {"label": "Spam", "icon": "bi-shield-exclamation", "count": 11, "url": "/inbox/?folder=spam"},
    {"label": "Trash", "icon": "bi-trash", "count": 48, "url": "/inbox/?folder=trash"},
]

ACTIVITY = [
    {
        "actor": "Alex Morgan",
        "action": "connected",
        "target": "sales@acme.io",
        "time": "2 min ago",
        "icon": "bi-plus-circle",
        "tone": "primary",
    },
    {
        "actor": "System",
        "action": "failed",
        "target": "sync job #4821",
        "time": "18 min ago",
        "icon": "bi-x-octagon",
        "tone": "danger",
    },
    {
        "actor": "Priya Sharma",
        "action": "shared",
        "target": "Q3 roadmap",
        "time": "1 hr ago",
        "icon": "bi-share",
        "tone": "info",
    },
    {
        "actor": "System",
        "action": "refreshed",
        "target": "OAuth token (work@acme.io)",
        "time": "2 hrs ago",
        "icon": "bi-arrow-clockwise",
        "tone": "success",
    },
    {
        "actor": "Maya Chen",
        "action": "replied",
        "target": "Partnership agreement",
        "time": "4 hrs ago",
        "icon": "bi-reply",
        "tone": "warning",
    },
    {
        "actor": "System",
        "action": "completed",
        "target": "nightly full sync",
        "time": "8 hrs ago",
        "icon": "bi-check2-circle",
        "tone": "success",
    },
]

USERS = [
    {"id": 1, "name": "Alex Morgan", "email": "alex.morgan@acme.io", "role": "Administrator", "status": "active", "last_active": days_ago(0, 0.1), "mfa": True, "accounts": 5},
    {"id": 2, "name": "Priya Sharma", "email": "priya.sharma@acme.io", "role": "Manager", "status": "active", "last_active": days_ago(0, 1.2), "mfa": True, "accounts": 3},
    {"id": 3, "name": "Daniel Okafor", "email": "daniel.okafor@acme.io", "role": "Operator", "status": "active", "last_active": days_ago(1), "mfa": False, "accounts": 1},
    {"id": 4, "name": "Sofia Reyes", "email": "sofia.reyes@acme.io", "role": "Analyst", "status": "active", "last_active": days_ago(2), "mfa": False, "accounts": 2},
    {"id": 5, "name": "Liam Carter", "email": "liam.carter@acme.io", "role": "Viewer", "status": "invited", "last_active": None, "mfa": False, "accounts": 0},
    {"id": 6, "name": "Olivia Bennett", "email": "olivia.bennett@acme.io", "role": "Viewer", "status": "disabled", "last_active": days_ago(40), "mfa": False, "accounts": 0},
]

AUDIT_LOGS = [
    {"id": 9001, "user": "Alex Morgan", "action": "account.create", "target": "sales@acme.io", "time": days_ago(0, 0.1), "ip": "203.0.113.24", "status": "success"},
    {"id": 9002, "user": "System", "action": "sync.run", "target": "account #2", "time": days_ago(0, 0.2), "ip": "internal", "status": "error"},
    {"id": 9003, "user": "Priya Sharma", "action": "user.role.update", "target": "daniel.okafor@acme.io", "time": days_ago(0, 1.4), "ip": "198.51.100.9", "status": "success"},
    {"id": 9004, "user": "Alex Morgan", "action": "oauth.reconnect", "target": "sales@acme.io", "time": days_ago(1), "ip": "203.0.113.24", "status": "success"},
    {"id": 9005, "user": "System", "action": "notification.otp_sent", "target": "alex.morgan@acme.io", "time": days_ago(1, 3), "ip": "internal", "status": "success"},
    {"id": 9006, "user": "Daniel Okafor", "action": "account.remove", "target": "legacy@acme.io", "time": days_ago(2), "ip": "192.0.2.77", "status": "success"},
    {"id": 9007, "user": "System", "action": "auth.failed_login", "target": "unknown@acme.io", "time": days_ago(2, 5), "ip": "45.33.90.12", "status": "error"},
    {"id": 9008, "user": "Sofia Reyes", "action": "export.analytics", "target": "analytics-q2.csv", "time": days_ago(3), "ip": "198.51.100.9", "status": "success"},
]


# ---------------------------------------------------------------- shell context

def recent_notifications(limit=4):
    """Latest notifications from the service as shell-friendly dicts."""
    from .services import NotificationService

    return NotificationService().recent(limit)


def unread_notification_count():
    from .services import NotificationService

    return NotificationService().unread_count()


def shell_user(user):
    """Map Django's built-in auth User onto the shell's user dict."""
    if user is None or not user.is_authenticated:
        return USER
    name = user.get_full_name().strip() or user.get_username()
    parts = name.split()
    initials = (parts[0][0] + (parts[1][0] if len(parts) > 1 else "")).upper()
    if user.is_superuser:
        role = "Administrator"
    elif user.is_staff:
        role = "Staff"
    else:
        role = "Member"
    return {
        "name": name,
        "email": user.email,
        "initials": initials,
        "role": role,
        "avatar_hue": "primary",
    }


def build_shell_context(auth_page=False, title="", breadcrumbs=None, active_page="", **extra):
    """Context for the app shell shared by every page (base.html)."""
    unread = unread_notification_count()
    nav = []
    for item in SIDEBAR_NAV:
        item = dict(item)
        if "badge_key" in item:
            item["badge"] = unread or None
        nav.append(item)
    context = {
        "app_name": APP_NAME,
        "app_version": APP_VERSION,
        "auth_page": auth_page,
        "title": title,
        "breadcrumbs": breadcrumbs or [],
        "active_page": active_page,
        "current_user": USER,
        "sidebar_nav": nav,
        "sidebar_tools": SIDEBAR_TOOLS,
        "unread_count": unread,
        "notification_center": recent_notifications(),
    }
    context.update(extra)
    return context


class PortalContextMixin:
    """Injects the app shell context into a class-based view."""
    app_name = APP_NAME
    app_version = APP_VERSION
    auth_page = False
    title = ""
    breadcrumbs = None
    active_page = ""
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_shell_context(
            auth_page=self.auth_page,
            title=self.title,
            breadcrumbs=self.breadcrumbs,
            active_page=self.active_page,
        ))
        user = getattr(self.request, "user", None)
        if user is not None and user.is_authenticated:
            context["current_user"] = shell_user(user)
        return context


class PortalView(PortalContextMixin, TemplateView):
    """Base view for all Portal pages."""
