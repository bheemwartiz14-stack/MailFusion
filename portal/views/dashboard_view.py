from django.contrib.auth.mixins import LoginRequiredMixin

from portal.base_view import PortalView
from portal.models import Email, OutlookAccount
from portal.utils.monitor import health_cards, system_metrics
from portal.utils.tasks import broker_healthy, worker_status


class DashboardView(LoginRequiredMixin, PortalView):
    template_name = "dashboard/index.html"
    title = "Dashboard"
    breadcrumbs = [{"label": "Dashboard"}]
    active_page = "dashboard"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        metrics = system_metrics()
        broker = broker_healthy()
        worker = worker_status()

        total_emails = Email.objects.count()
        unread = Email.objects.filter(is_read=False).count()
        connected = OutlookAccount.objects.filter(oauth_status="connected").count()
        total_accounts = metrics["total_accounts"]

        stats = [
            {
                "label": "Connected Accounts",
                "value": f"{connected} of {total_accounts}",
                "icon": "group",
                "tone": "primary",
                "trend": metrics["active_accounts"],
                "trend_label": "active",
            },
            {
                "label": "Total Emails",
                "value": f"{total_emails:,}",
                "icon": "mail",
                "tone": "info",
                "trend": metrics["emails_synced_today"],
                "trend_label": "synced today",
            },
            {
                "label": "Unread Emails",
                "value": f"{unread:,}",
                "icon": "mark_email_unread",
                "tone": "warning",
                "trend": metrics["syncs_today"],
                "trend_label": "syncs today",
            },
            {
                "label": "Emails Today",
                "value": f"{metrics['emails_processed_today']:,}",
                "icon": "inbox",
                "tone": "success",
                "trend": metrics["avg_sync_seconds"],
                "trend_label": "avg sync sec",
            },
        ]

        context.update(
            stats=stats,
            status=overall_status(broker, worker, metrics),
            health=health_cards(broker, worker, queue_depth_safe()),
            metrics=metrics,
            broker=broker,
            worker=worker,
        )
        return context


def overall_status(broker, worker, metrics):
    if not broker or not worker.get("active"):
        return "critical"
    if metrics.get("needs_reauthorization"):
        return "critical"
    if metrics.get("failed_jobs"):
        return "degraded"
    return "healthy"


def queue_depth_safe():
    try:
        from portal.utils.tasks import queue_depth

        return queue_depth()
    except Exception:  # noqa: BLE001
        return 0
