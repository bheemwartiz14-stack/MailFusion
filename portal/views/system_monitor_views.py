"""
System Monitor views: dashboard, logs, health, queue, oauth and account
details. These pages render the state produced by the background sync engine
and provide HTMX partials for lightweight polling updates.

Served under the ``/system-monitor/`` URL namespace.
"""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone

from portal.base_view import PortalView
from portal.models import (
    AccountHealth,
    AttachmentDownloadJob,
    EmailSyncState,
    GraphSubscription,
    OutlookAccount,
    SyncJob,
    SyncLog,
)
from portal.utils.monitor import get_system_context
from portal.utils.querystring import _querystring
from portal.utils.tasks import broker_healthy, queue_depth, worker_status


class SystemMonitorView(LoginRequiredMixin, PortalView):
    template_name = "sync/dashboard.html"
    title = "System Monitor"
    breadcrumbs = [{"label": "System Monitor"}]
    active_page = "sync"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_system_context())
        context.update(
            accounts=OutlookAccount.objects.select_related(
                "health", "sync_state", "oauth_token"
            ).all(),
        )
        return context


class SystemMonitorPartialView(LoginRequiredMixin, PortalView):
    """HTMX partial returning the full monitor body (banner + KPIs + rails)."""

    template_name = "sync/partials/system/system_monitor.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_system_context())
        return context


class SyncLogsView(LoginRequiredMixin, PortalView):
    template_name = "sync/logs.html"
    title = "Synchronization Logs"
    breadcrumbs = [{"label": "System Monitor", "url": "/system-monitor/"}, {"label": "Logs"}]
    active_page = "sync"
    page_size = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status", "")
        q = self.request.GET.get("q", "").strip()
        account_id = self.request.GET.get("account", "")
        qs = SyncLog.objects.select_related("account").order_by("-start_time")
        if status:
            qs = qs.filter(status=status)
        if account_id:
            qs = qs.filter(account__id=account_id)
        if q:
            qs = qs.filter(account__name__icontains=q) | qs.filter(account__email__icontains=q)
        counts = dict(SyncLog.objects.values_list("status").annotate(c=Count("id")))
        page_obj = Paginator(qs, self.page_size).get_page(self.request.GET.get("page"))
        context.update(
            page_obj=page_obj,
            logs=page_obj.object_list,
            accounts=OutlookAccount.objects.all(),
            counts=counts,
            current_status=status,
            query=q,
            current_account=account_id,
            extra_querystring=_querystring(self.request),
        )
        return context


class SyncLogsPartialView(LoginRequiredMixin, PortalView):
    template_name = "sync/partials/logs_table.html"
    page_size = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = self.request.GET.get("status", "")
        qs = SyncLog.objects.select_related("account").order_by("-start_time")
        if status:
            qs = qs.filter(status=status)
        page_obj = Paginator(qs, self.page_size).get_page(self.request.GET.get("page"))
        context.update(page_obj=page_obj, logs=page_obj.object_list)
        return context


class SyncLogDetailView(LoginRequiredMixin, PortalView):
    template_name = "sync/log_detail.html"
    active_page = "sync"

    def get_context_data(self, pk, **kwargs):
        context = super().get_context_data(**kwargs)
        log = get_object_or_404(SyncLog.objects.select_related("account"), pk=pk)
        context.update(
            title=f"Sync log · {log.account.email}",
            breadcrumbs=[
                {"label": "System Monitor", "url": "/system-monitor/"},
                {"label": "Logs", "url": "/system-monitor/logs/"},
                {"label": str(log.pk)[:8]},
            ],
            log=log,
        )
        return context


class SystemHealthView(LoginRequiredMixin, PortalView):
    template_name = "sync/health.html"
    title = "Health Monitoring"
    breadcrumbs = [{"label": "System Monitor", "url": "/system-monitor/"}, {"label": "Health"}]
    active_page = "sync"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            broker=broker_healthy(),
            worker=worker_status(),
            queue_depth=queue_depth(),
            health_rows=AccountHealth.objects.select_related("account").all(),
            subscriptions=GraphSubscription.objects.select_related("account").order_by("expiration_date_time"),
            sync_states=EmailSyncState.objects.select_related("account").all(),
            systems_healthy=broker_healthy() and worker_status()["active"],
        )
        return context


class HealthPartialView(LoginRequiredMixin, PortalView):
    template_name = "sync/partials/health_rows.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            broker=broker_healthy(),
            worker=worker_status(),
            queue_depth=queue_depth(),
            health_rows=AccountHealth.objects.select_related("account").all(),
            subscriptions=GraphSubscription.objects.select_related("account").order_by("expiration_date_time"),
        )
        return context


class QueueStatusView(LoginRequiredMixin, PortalView):
    template_name = "sync/queue.html"
    title = "Queue Status"
    breadcrumbs = [{"label": "System Monitor", "url": "/system-monitor/"}, {"label": "Queue"}]
    active_page = "sync"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jobs = SyncJob.objects.select_related("account").order_by("-created_at")
        context.update(
            jobs=jobs[:100],
            queue_depth=queue_depth(),
            worker=worker_status(),
            broker=broker_healthy(),
            counts=dict(
                SyncJob.objects.values_list("status").annotate(c=Count("id"))
            ),
            attachment_jobs=AttachmentDownloadJob.objects.select_related("attachment__email__outlook_account").order_by("-created_at")[:50],
        )
        return context


class OAuthStatusView(LoginRequiredMixin, PortalView):
    template_name = "sync/oauth.html"
    title = "OAuth Status"
    breadcrumbs = [{"label": "System Monitor", "url": "/system-monitor/"}, {"label": "OAuth"}]
    active_page = "sync"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(accounts=OutlookAccount.objects.select_related("oauth_token", "health").all())
        return context


class AccountDetailView(LoginRequiredMixin, PortalView):
    template_name = "sync/account_detail.html"
    active_page = "accounts"

    def get_context_data(self, account_id, **kwargs):
        context = super().get_context_data(**kwargs)
        account = get_object_or_404(
            OutlookAccount.objects.select_related(
                "oauth_token", "sync_state", "health"
            ).prefetch_related("emails"),
            pk=account_id,
            user=self.request.user,
        )
        context.update(
            title=account.email,
            breadcrumbs=[
                {"label": "Outlook Accounts", "url": "/accounts/"},
                {"label": account.email},
            ],
            account=account,
            logs=account.sync_logs.order_by("-start_time")[:15],
            subscriptions=account.graph_subscriptions.order_by("-created_at")[:5],
            emails=account.emails.order_by("-received_at")[:20],
            total_emails=account.emails.count(),
            unread=account.emails.filter(is_read=False).count(),
        )
        return context